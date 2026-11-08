/**
 * 账号库 / 会话 / 失败次数的本机持久化。
 * 所有读写都做异常隔离：隐私模式或存储被禁用时退化为「本次会话内可用」。
 */
import type { AuthSession, StoredAccount } from './types'

export const ACCOUNTS_KEY = 'kinlin.auth.accounts.v1'
export const SESSION_KEY = 'kinlin.auth.session.v1'
export const ATTEMPTS_KEY = 'kinlin.auth.attempts.v1'

export interface AttemptState {
  count: number
  lockedUntil: number
}

const safeGet = (store: Storage | undefined, key: string): string | null => {
  try {
    return store?.getItem(key) ?? null
  } catch {
    return null
  }
}

const safeSet = (store: Storage | undefined, key: string, value: string): void => {
  try {
    store?.setItem(key, value)
  } catch {
    // 存储不可写时不影响当前会话内的内存态。
  }
}

const safeRemove = (store: Storage | undefined, key: string): void => {
  try {
    store?.removeItem(key)
  } catch {
    // 同上。
  }
}

const storage = (kind: 'local' | 'session'): Storage | undefined => {
  try {
    return kind === 'local' ? window.localStorage : window.sessionStorage
  } catch {
    return undefined
  }
}

const parseJson = <T>(raw: string | null, fallback: T): T => {
  if (!raw) return fallback
  try {
    return JSON.parse(raw) as T
  } catch {
    return fallback
  }
}

const isStoredAccount = (value: unknown): value is StoredAccount => {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return typeof item.id === 'string'
    && typeof item.username === 'string'
    && typeof item.email === 'string'
    && typeof item.salt === 'string'
    && typeof item.passwordHash === 'string'
    && typeof item.iterations === 'number'
    && typeof item.createdAt === 'string'
}

export const readAccounts = (): StoredAccount[] => {
  const parsed = parseJson<unknown>(safeGet(storage('local'), ACCOUNTS_KEY), [])
  return Array.isArray(parsed) ? parsed.filter(isStoredAccount) : []
}

export const writeAccounts = (accounts: StoredAccount[]): void => {
  safeSet(storage('local'), ACCOUNTS_KEY, JSON.stringify(accounts))
}

const isSession = (value: unknown): value is AuthSession => {
  if (!value || typeof value !== 'object') return false
  const item = value as Record<string, unknown>
  return typeof item.accountId === 'string'
    && typeof item.username === 'string'
    && typeof item.expiresAt === 'number'
}

/** 同时读两个存储位，兼容「记住登录」与「仅本次会话」两种写法。 */
export const readSession = (): AuthSession | null => {
  const candidates = [
    parseJson<unknown>(safeGet(storage('local'), SESSION_KEY), null),
    parseJson<unknown>(safeGet(storage('session'), SESSION_KEY), null)
  ]
  const valid = candidates.find(isSession)
  if (!valid || !isSession(valid) || valid.expiresAt <= Date.now()) return null
  return valid as AuthSession
}

export const writeSession = (session: AuthSession): void => {
  const payload = JSON.stringify(session)
  if (session.remember) {
    safeSet(storage('local'), SESSION_KEY, payload)
    safeRemove(storage('session'), SESSION_KEY)
  } else {
    safeSet(storage('session'), SESSION_KEY, payload)
    safeRemove(storage('local'), SESSION_KEY)
  }
}

export const clearSession = (): void => {
  safeRemove(storage('local'), SESSION_KEY)
  safeRemove(storage('session'), SESSION_KEY)
}

export const readAttempts = (): AttemptState => {
  const parsed = parseJson<unknown>(safeGet(storage('session'), ATTEMPTS_KEY), null)
  if (!parsed || typeof parsed !== 'object') return { count: 0, lockedUntil: 0 }
  const item = parsed as Record<string, unknown>
  return {
    count: typeof item.count === 'number' ? item.count : 0,
    lockedUntil: typeof item.lockedUntil === 'number' ? item.lockedUntil : 0
  }
}

export const writeAttempts = (state: AttemptState): void => {
  safeSet(storage('session'), ATTEMPTS_KEY, JSON.stringify(state))
}

export const clearAttempts = (): void => {
  safeRemove(storage('session'), ATTEMPTS_KEY)
}
