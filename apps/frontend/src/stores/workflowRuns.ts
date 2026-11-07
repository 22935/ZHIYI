import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  workflowApi,
  type WorkflowProgressPhase,
  type WorkflowRunSummary
} from '@/services/api/workflow'
import { ACG_HISTORY_SOURCES } from '@/utils/acgHistoryFilter'
import { ACTIVE_RUN_STATUSES, belongsToConversation, isActiveRunStatus } from '@/features/workspace/session'

export type WorkflowRunSource = 'agent' | 'chat' | 'acg' | 'legacy_agent_chat' | 'console' | 'restored'

export interface WorkflowRunReference {
  runId: string
  missionId?: string
  workflowId?: string
  conversationId?: string
  conversationAliases?: string[]
  messageId?: string
  source: WorkflowRunSource
  status?: string
  phase?: WorkflowProgressPhase
  createdAt?: string
  updatedAt?: string
  lastSeenAt?: string
  invalid?: boolean
}

interface ChatWorkflowBindingLike {
  conversationId: string
  conversationAliases?: string[]
  messageId?: string
  missionId?: string
  runId: string
  source?: 'agent' | 'chat'
  workflowId?: string
  status?: string
  createdAt?: string
  invalidAt?: string
}

const STORAGE_KEY = 'workflow.run.references.v1'
const CHAT_BINDINGS_KEY = 'chat.workflow_bindings.v1'
const NON_TERMINAL_STATUSES = ACTIVE_RUN_STATUSES
const PROGRESS_PHASES = new Set<WorkflowProgressPhase>([
  'understanding', 'planning', 'graph_building', 'executing', 'recovery',
  'review', 'completed', 'failed', 'cancelled'
])

const safeObject = (value: string | null): Record<string, unknown> => {
  try {
    const parsed = JSON.parse(value || '{}')
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}
  } catch {
    return {}
  }
}

const normalizeSource = (value: unknown): WorkflowRunSource => {
  return value === 'agent' || value === 'chat' || value === 'acg' || value === 'legacy_agent_chat' || value === 'console'
    ? value
    : 'restored'
}

const normalizeReference = (value: unknown): WorkflowRunReference | null => {
  if (!value || typeof value !== 'object') return null
  const item = value as Record<string, unknown>
  const runId = typeof item.runId === 'string' ? item.runId.trim() : ''
  if (!runId) return null
  const phase = typeof item.phase === 'string' && PROGRESS_PHASES.has(item.phase as WorkflowProgressPhase)
    ? item.phase as WorkflowProgressPhase
    : undefined
  return {
    runId,
    missionId: typeof item.missionId === 'string' ? item.missionId : undefined,
    workflowId: typeof item.workflowId === 'string' ? item.workflowId : undefined,
    conversationId: typeof item.conversationId === 'string' ? item.conversationId : undefined,
    conversationAliases: Array.isArray(item.conversationAliases) ? item.conversationAliases.filter((key): key is string => typeof key === 'string') : undefined,
    messageId: typeof item.messageId === 'string' ? item.messageId : undefined,
    source: normalizeSource(item.source),
    status: typeof item.status === 'string' ? item.status : undefined,
    phase,
    createdAt: typeof item.createdAt === 'string' ? item.createdAt : undefined,
    updatedAt: typeof item.updatedAt === 'string' ? item.updatedAt : undefined,
    lastSeenAt: typeof item.lastSeenAt === 'string' ? item.lastSeenAt : undefined,
    invalid: item.invalid === true
  }
}

const loadReferences = (): Record<string, WorkflowRunReference> => {
  const persisted = safeObject(localStorage.getItem(STORAGE_KEY))
  const references: Record<string, WorkflowRunReference> = {}
  for (const value of Object.values(persisted)) {
    const reference = normalizeReference(value)
    if (reference) references[reference.runId] = reference
  }

  const legacyBindings = safeObject(localStorage.getItem(CHAT_BINDINGS_KEY))
  for (const value of Object.values(legacyBindings)) {
    if (!Array.isArray(value)) continue
    for (const item of value as ChatWorkflowBindingLike[]) {
      if (!item?.runId || references[item.runId]) continue
      references[item.runId] = {
        runId: item.runId,
        missionId: item.missionId,
        workflowId: item.workflowId,
        conversationId: item.conversationId,
        conversationAliases: item.conversationAliases,
        messageId: item.messageId,
        source: item.source === 'agent' ? 'agent' : 'chat',
        status: item.status,
        createdAt: item.createdAt,
        invalid: Boolean(item.invalidAt)
      }
    }
  }
  return references
}

export const useWorkflowRunsStore = defineStore('workflowRuns', () => {
  const references = ref<Record<string, WorkflowRunReference>>(loadReferences())
  const initialized = ref(false)
  const isSyncing = ref(false)
  const syncError = ref<string | null>(null)
  let bootstrapPromise: Promise<void> | null = null

  const persist = () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(references.value))
  }

  const register = (reference: WorkflowRunReference) => {
    const safeReference = normalizeReference(reference)
    if (!safeReference) return
    const current = references.value[reference.runId]
    references.value = {
      ...references.value,
      [reference.runId]: {
        ...current,
        ...safeReference,
        source: current && current.source !== 'restored' ? current.source : safeReference.source,
        invalid: false,
        lastSeenAt: new Date().toISOString()
      }
    }
    persist()
  }

  const registerChatBinding = (binding: ChatWorkflowBindingLike) => {
    register({
      runId: binding.runId,
      missionId: binding.missionId,
      workflowId: binding.workflowId,
      conversationId: binding.conversationId,
      conversationAliases: binding.conversationAliases,
      messageId: binding.messageId,
      source: binding.source === 'agent' ? 'agent' : 'chat',
      status: binding.status,
      createdAt: binding.createdAt,
      invalid: Boolean(binding.invalidAt)
    })
  }

  const mergeSummaries = (items: WorkflowRunSummary[]) => {
    const now = new Date().toISOString()
    const next = { ...references.value }
    for (const item of items) {
      const current = next[item.runId]
      next[item.runId] = {
        ...current,
        runId: item.runId,
        missionId: item.missionId,
        workflowId: item.workflowId,
        source: current?.source || normalizeSource(item.source),
        status: item.status,
        phase: item.phase,
        createdAt: current?.createdAt || item.createdAt || item.startedAt || undefined,
        updatedAt: item.updatedAt || undefined,
        lastSeenAt: now,
        invalid: false
      }
    }
    references.value = next
    persist()
  }

  const updateObservedState = (runId: string, status: string, phase?: WorkflowProgressPhase, updatedAt?: string | null) => {
    const current = references.value[runId]
    if (!current) return
    references.value = {
      ...references.value,
      [runId]: {
        ...current,
        status,
        phase: phase || current.phase,
        updatedAt: updatedAt || current.updatedAt,
        lastSeenAt: new Date().toISOString(),
        invalid: false
      }
    }
    persist()
  }

  const markInvalid = (runId: string) => {
    const current = references.value[runId]
    if (!current) return
    references.value = {
      ...references.value,
      [runId]: { ...current, invalid: true, lastSeenAt: new Date().toISOString() }
    }
    persist()
  }

  const removeReference = (runId: string) => {
    if (!references.value[runId]) return
    const next = { ...references.value }
    delete next[runId]
    references.value = next
    persist()
  }

  const getReference = (runId: string) => references.value[runId]
  const reassociateConversation = (draft: string, contextId: string, runIds: readonly string[]) => {
    if (!draft.startsWith('draft:') || !contextId || contextId.startsWith('draft:')) return
    references.value = Object.fromEntries(Object.entries(references.value).map(([id, item]) => [id,
      runIds.includes(item.runId) && (item.conversationId === draft || item.conversationId === contextId) ? { ...item, conversationId: contextId,
        conversationAliases: [...new Set([...(item.conversationAliases || []), draft])] } : item
    ]))
    persist()
  }
  const getByConversation = (conversationId: string) => Object.values(references.value)
    .filter(item => belongsToConversation({ ...item, conversationId: item.conversationId || '' }, conversationId) && !item.invalid)
    .sort((a, b) => (b.createdAt || '').localeCompare(a.createdAt || ''))

  const activeReferences = computed(() => Object.values(references.value).filter(item =>
    !item.invalid && isActiveRunStatus(item.status)
  ))

  const bootstrap = () => {
    if (bootstrapPromise) return bootstrapPromise
    bootstrapPromise = (async () => {
      isSyncing.value = true
      syncError.value = null
      try {
        const page = await workflowApi.listRuns({
          statuses: NON_TERMINAL_STATUSES.join(','),
          sources: ACG_HISTORY_SOURCES,
          summary: true,
          page: 1,
          pageSize: 100
        })
        mergeSummaries(page.items || [])
        if ((page.items || []).length === page.total) {
          const visible = new Set((page.items || []).map(item => item.runId))
          const next = { ...references.value }
          let changed = false
          for (const item of Object.values(next)) {
            if (isActiveRunStatus(item.status) && !visible.has(item.runId)) {
              next[item.runId] = { ...item, invalid: true }
              changed = true
            }
          }
          if (changed) {
            references.value = next
            persist()
          }
        }
      } catch {
        syncError.value = '全局运行索引同步暂时中断'
      } finally {
        initialized.value = true
        isSyncing.value = false
      }
    })()
    return bootstrapPromise
  }

  return {
    references,
    activeReferences,
    initialized,
    isSyncing,
    syncError,
    register,
    registerChatBinding,
    reassociateConversation,
    mergeSummaries,
    updateObservedState,
    markInvalid,
    removeReference,
    getReference,
    getByConversation,
    bootstrap
  }
})
