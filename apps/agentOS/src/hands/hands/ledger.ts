import { lockDataDirectory } from './writer-lock.ts'
import { receiptChecksum } from './engine.ts'
/**
 * ZhiYi Hands — durable Execution Ledger (HANDS-02B).
 *
 * Append-only JSONL with fsync-per-record. Every admission is persisted
 * BEFORE dispatch; every terminal state (with its receipt) is persisted
 * BEFORE the client can observe it. On restart the file is replayed to
 * rebuild the in-memory index, and reconcile() classifies the unfinished:
 *
 *   RECEIVED / AUTHORIZED          → FAILED  HANDS_ABANDONED_BY_RESTART
 *                                     (dispatch never began: no side effects;
 *                                      retryable — the client may re-run under
 *                                      a NEW idempotency key)
 *   STARTED (running)              → UNKNOWN HANDS_RESTARTED_DURING_EXECUTION
 *                                     (side effects may exist; NEVER auto-
 *                                      retried; awaits operator reconciliation)
 *
 * Terminal states are COMPLETED / FAILED / CANCELLED / UNKNOWN — the first
 * three carry a receipt; UNKNOWN deliberately does not (nothing about the
 * outcome is confirmed, so no receipt may be minted).
 *
 * Idempotency: uniqueness of (callerId, idempotencyKey). Same key + same
 * request digest → the SAME execution record is returned (never re-executed).
 * Same key + different digest → explicit rejection. Nonce replay is a
 * separate transport-level mechanism (hands/auth.ts) and never substitutes
 * for this.
 */

import { randomBytes } from 'node:crypto'
import { closeSync, existsSync, fsyncSync, mkdirSync, openSync, readFileSync, writeSync, truncateSync } from 'node:fs'
import { join } from 'node:path'
import { canonicalChecksum, HANDS_PROTOCOL_VERSION, type HandsCapabilityId, type HandsExecutionReceipt } from './protocol.ts'

export const LEDGER_STATES = ['RECEIVED', 'AUTHORIZED', 'STARTED', 'COMPLETED', 'FAILED', 'CANCELLED', 'UNKNOWN'] as const
export type LedgerState = (typeof LEDGER_STATES)[number]
export const TERMINAL_STATES: readonly LedgerState[] = ['COMPLETED', 'FAILED', 'CANCELLED', 'UNKNOWN']
/** States in which execution had begun — side effects may exist. */
export const SIDE_EFFECT_STATES: readonly LedgerState[] = ['STARTED']

export const ABANDONED_BY_RESTART = 'HANDS_ABANDONED_BY_RESTART'
export const RESTARTED_DURING_EXECUTION = 'HANDS_RESTARTED_DURING_EXECUTION'

export interface LedgerRequestSummary {
  capabilityId: HandsCapabilityId
  requestId: string
  invocationId: string
  workspaceId: string
  /** Caller identity from the HMAC credential, NOT from the request body. */
  callerId: string
  grantId?: string
  identity?: import('./protocol.ts').HandsIdentityRef
}

export interface ExecutionRecord {
  executionId: string
  callerId: string
  idempotencyKey: string
  /** sha256 over the RAW request body — binds the record to the exact bytes. */
  requestDigest: string
  summary: LedgerRequestSummary
  state: LedgerState
  cancelRequested: boolean
  createdAt: string
  updatedAt: string
  receipt?: HandsExecutionReceipt
  /** Populated for UNKNOWN (reconciliation hint). */
  reconciliation?: { reason: string }
}

type LedgerLine =
  | { t: 'claim'; executionId: string; callerId: string; idempotencyKey: string; requestDigest: string; summary: LedgerRequestSummary; ts: string }
  | { t: 'state'; executionId: string; state: LedgerState; ts: string }
  | { t: 'cancel-requested'; executionId: string; ts: string }
  | { t: 'receipt'; executionId: string; receipt: HandsExecutionReceipt; ts: string }
  | { t: 'unknown'; executionId: string; reason: string; ts: string }

export function newExecutionId(): string {
  return `xhexec_${randomBytes(12).toString('hex')}`
}

function idempotencySlot(callerId: string, key: string): string {
  return `${callerId}\u0000${key}`
}

function syntheticReceipt(record: ExecutionRecord, status: 'failed', error: { code: string; retryable: boolean; message: string }): HandsExecutionReceipt {
  const receipt: HandsExecutionReceipt = {
    protocolVersion: HANDS_PROTOCOL_VERSION,
    requestId: record.summary.requestId,
    invocationId: record.summary.invocationId,
    capabilityId: record.summary.capabilityId,
    grantId: record.summary.grantId ?? 'server-side-reconciliation',
    status,
    startedAt: record.createdAt,
    completedAt: record.updatedAt,
    durationMs: 0,
    error,
    checksum: '',
    ...(record.summary.identity === undefined ? {} : { identity: record.summary.identity }),
    idempotencyKey: record.idempotencyKey,
  }
  receipt.checksum = receiptChecksum(receipt)
  return receipt
}

export class ExecutionLedger {
  readonly #records = new Map<string, ExecutionRecord>()
  readonly #byIdempotency = new Map<string, string>()
  readonly #path: string
  #fd: number | undefined
  #unlock: (() => void) | undefined

  constructor(readonly dataDir: string) {
    mkdirSync(dataDir, { recursive: true })
    this.#path = join(dataDir, 'ledger.jsonl')
    this.#unlock = lockDataDirectory(dataDir)
    try {
      if (existsSync(this.#path)) this.#load()
      this.#fd = openSync(this.#path, 'a')
      for (const record of this.#records.values()) {
        if (record.state !== 'UNKNOWN' && TERMINAL_STATES.includes(record.state) && !record.receipt) {
          record.state = 'STARTED'
          this.markUnknown(record.executionId, 'HANDS_TERMINAL_WITHOUT_RECEIPT')
        }
      }
    } catch (error) { this.#unlock(); this.#unlock = undefined; throw error }
  }

  #append(line: LedgerLine): void {
    if (this.#fd === undefined) throw new Error('ledger closed')
    writeSync(this.#fd, `${JSON.stringify(line)}\n`)
    fsyncSync(this.#fd)
  }

  #load(): void {
    const bytes = readFileSync(this.#path)
    const boundary = bytes.lastIndexOf(10) + 1
    if (boundary !== bytes.length) {
      // A crash can leave an unterminated tail. Preserve it separately, then
      // truncate before appending so a new valid line cannot join torn bytes.
      const tail = openSync(this.#path + '.torn-' + Date.now(), 'wx')
      try { writeSync(tail, bytes.subarray(boundary)); fsyncSync(tail) } finally { closeSync(tail) }
      truncateSync(this.#path, boundary)
    }
    for (const raw of bytes.subarray(0,boundary).toString('utf8').split('\n')) {
      if (raw.trim() === '') continue
      let parsed: LedgerLine
      try {
        parsed = JSON.parse(raw) as LedgerLine
      } catch {
        throw new Error('HANDS_LEDGER_CORRUPT_COMPLETE_LINE')
      }
      switch (parsed.t) {
        case 'claim': {
          const slot = idempotencySlot(parsed.callerId, parsed.idempotencyKey)
          if (this.#byIdempotency.has(slot)) break // duplicate claim line: first wins
          this.#byIdempotency.set(slot, parsed.executionId)
          this.#records.set(parsed.executionId, {
            executionId: parsed.executionId,
            callerId: parsed.callerId,
            idempotencyKey: parsed.idempotencyKey,
            requestDigest: parsed.requestDigest,
            summary: parsed.summary,
            state: 'RECEIVED',
            cancelRequested: false,
            createdAt: parsed.ts,
            updatedAt: parsed.ts,
          })
          break
        }
        case 'state': {
          const record = this.#records.get(parsed.executionId)
          if (record !== undefined && !TERMINAL_STATES.includes(record.state)) {
            record.state = parsed.state
            record.updatedAt = parsed.ts
          }
          break
        }
        case 'cancel-requested': {
          const record = this.#records.get(parsed.executionId)
          if (record !== undefined) record.cancelRequested = true
          break
        }
        case 'receipt': {
          const record = this.#records.get(parsed.executionId)
          if (record !== undefined) {
            this.#validateReceipt(record, parsed.receipt)
            record.receipt = parsed.receipt
            record.state = parsed.receipt.status.toUpperCase() as LedgerState
            record.updatedAt = parsed.ts
          }
          break
        }
        case 'unknown': {
          const record = this.#records.get(parsed.executionId)
          if (record !== undefined && !TERMINAL_STATES.includes(record.state)) {
            record.state = 'UNKNOWN'
            record.reconciliation = { reason: parsed.reason }
          }
          break
        }
      }
    }
  }

  /**
   * Claim the (callerId, idempotencyKey) slot for one execution.
   * Same digest → {claimed:false} with the existing record (replay: return it,
   * do NOT re-run). Different digest → {claimed:false, conflict:true}.
   */
  claim(input: { callerId: string; idempotencyKey: string; requestDigest: string; summary: LedgerRequestSummary }):
    { claimed: true; record: ExecutionRecord } | { claimed: false; conflict: boolean; existing?: ExecutionRecord } {
    const slot = idempotencySlot(input.callerId, input.idempotencyKey)
    const existingId = this.#byIdempotency.get(slot)
    if (existingId !== undefined) {
      const existing = this.#records.get(existingId)
      if (existing !== undefined && existing.requestDigest === input.requestDigest) {
        return { claimed: false, conflict: false, existing }
      }
      return { claimed: false, conflict: true, existing }
    }
    const ts = new Date().toISOString()
    const executionId = newExecutionId()
    this.#append({
      t: 'claim', executionId, callerId: input.callerId, idempotencyKey: input.idempotencyKey,
      requestDigest: input.requestDigest, summary: input.summary, ts,
    })
    const record: ExecutionRecord = {
      executionId,
      callerId: input.callerId,
      idempotencyKey: input.idempotencyKey,
      requestDigest: input.requestDigest,
      summary: input.summary,
      state: 'RECEIVED',
      cancelRequested: false,
      createdAt: ts,
      updatedAt: ts,
    }
    this.#byIdempotency.set(slot, executionId)
    this.#records.set(executionId, record)
    return { claimed: true, record }
  }

  /** Persist a state transition (transitions out of terminal states are ignored). */
  setState(executionId: string, state: LedgerState): void {
    const record = this.#records.get(executionId)
    if (record === undefined) throw new Error(`unknown execution ${executionId}`)
    if (TERMINAL_STATES.includes(record.state)) return
    const ts = new Date().toISOString()
    this.#append({ t: 'state', executionId, state, ts })
    record.state = state
    record.updatedAt = ts
  }

  /** Record a cancellation REQUEST (distinct from the terminal cancelled state). */
  markCancelRequested(executionId: string): void {
    const record = this.#records.get(executionId)
    if (record === undefined || record.cancelRequested) return
    const ts = new Date().toISOString()
    this.#append({ t: 'cancel-requested', executionId, ts })
    record.cancelRequested = true
    record.updatedAt = ts
  }

  /** Persist the terminal receipt — before the client observes the terminal state. */
  attachReceipt(executionId: string, receipt: HandsExecutionReceipt): void {
    const record = this.#records.get(executionId)
    if (record === undefined) throw new Error(`unknown execution ${executionId}`)
    this.#validateReceipt(record, receipt)
    if (record.receipt !== undefined) {
      if (record.receipt.checksum !== receipt.checksum) throw new Error('HANDS_TERMINAL_RECEIPT_CONFLICT')
      return
    }
    const ts = new Date().toISOString()
    this.#append({ t: 'receipt', executionId, receipt, ts })
    record.receipt = receipt
    record.state = receipt.status.toUpperCase() as LedgerState
    record.updatedAt = ts
  }

  /** Mark an unfinished execution UNKNOWN (crash recovery); never auto-retried. */
  markUnknown(executionId: string, reason: string): void {
    const record = this.#records.get(executionId)
    if (record === undefined || TERMINAL_STATES.includes(record.state)) return
    const ts = new Date().toISOString()
    this.#append({ t: 'unknown', executionId, reason, ts })
    record.state = 'UNKNOWN'
    record.reconciliation = { reason }
    record.updatedAt = ts
  }

  get(executionId: string): ExecutionRecord | undefined {
    return this.#records.get(executionId)
  }

  findIdempotent(callerId: string, idempotencyKey: string): ExecutionRecord | undefined {
    const id = this.#byIdempotency.get(idempotencySlot(callerId, idempotencyKey))
    return id === undefined ? undefined : this.#records.get(id)
  }

  /** All records still in a pre-terminal state (crash-recovery candidates). */
  unfinished(): ExecutionRecord[] {
    return [...this.#records.values()].filter((record) => !TERMINAL_STATES.includes(record.state))
  }

  /**
   * Crash recovery, run once at boot AFTER replay. Side-effect-free states get
   * an honest retryable failure; STARTED goes UNKNOWN (conservative — no
   * exactly-once claim about external side effects).
   */
  reconcile(onReconciled?: (record: ExecutionRecord) => void): void {
    for (const record of this.unfinished()) {
      if (SIDE_EFFECT_STATES.includes(record.state)) {
        this.markUnknown(record.executionId, RESTARTED_DURING_EXECUTION)
      } else {
        this.attachReceipt(record.executionId, syntheticReceipt(record, 'failed', {
          code: ABANDONED_BY_RESTART,
          retryable: true,
          message: 'server restarted before execution began; no side effects occurred; retry with a new idempotency key',
        }))
      }
      const final = this.get(record.executionId)
      if (final !== undefined) onReconciled?.(final)
    }
  }

  #validateReceipt(record: ExecutionRecord, receipt: HandsExecutionReceipt): void {
    if (receiptChecksum(receipt) !== receipt.checksum || receipt.requestId !== record.summary.requestId
      || receipt.invocationId !== record.summary.invocationId || receipt.idempotencyKey !== record.idempotencyKey
      || receipt.capabilityId !== record.summary.capabilityId
      || (record.summary.grantId !== undefined && receipt.grantId !== record.summary.grantId)
      || canonicalChecksum(receipt.identity ?? null) !== canonicalChecksum(record.summary.identity ?? null)) {
      throw new Error('HANDS_INVALID_RECEIPT')
    }
    if (record.state === 'UNKNOWN' || (TERMINAL_STATES.includes(record.state)
      && record.state !== receipt.status.toUpperCase())) throw new Error('HANDS_TERMINAL_RECEIPT_CONFLICT')
  }

  close(): void {
    if (this.#fd !== undefined) {
      closeSync(this.#fd)
      this.#fd = undefined
    }
    this.#unlock?.(); this.#unlock = undefined
  }
}
