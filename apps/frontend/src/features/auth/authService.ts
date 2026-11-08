/**
 * 登录注册编排：校验 → 口令派生 → 账号库比对 → 建立本机会话。
 * 只控制前端路由入口；后端 LocalIdentity / PG users 不受影响。
 */
import { derivePasswordHash, PBKDF2_ITERATIONS, randomId, randomSalt, safeEqual } from './crypto'
import {
  clearAttempts,
  clearSession,
  readAccounts,
  readAttempts,
  readSession,
  writeAccounts,
  writeAttempts,
  writeSession
} from './storage'
import { validateLogin, validateRegister } from './validation'
import type {
  AuthResult,
  AuthSession,
  LoginPayload,
  PublicAccount,
  RegisterPayload,
  StoredAccount
} from './types'

/** 与 router 中恢复的 LoginView 路由保持一致（原登录页路径）。 */
export const AUTH_ROUTE = '/login'
export const DEFAULT_REDIRECT = '/chat'

const SESSION_TTL_MS = 7 * 24 * 60 * 60 * 1000
const REMEMBER_TTL_MS = 30 * 24 * 60 * 60 * 1000
const MAX_ATTEMPTS = 5
const LOCK_MS = 30_000

const ok = (value: PublicAccount, message: string): AuthResult => ({ ok: true, value, message })
const fail = (message: string): AuthResult => ({ ok: false, message })

const toPublic = (account: StoredAccount): PublicAccount => ({
  id: account.id,
  username: account.username,
  email: account.email,
  createdAt: account.createdAt
})

const startSession = (account: StoredAccount, remember: boolean): AuthSession => {
  const session: AuthSession = {
    accountId: account.id,
    username: account.username,
    expiresAt: Date.now() + (remember ? REMEMBER_TTL_MS : SESSION_TTL_MS),
    remember
  }
  writeSession(session)
  clearAttempts()
  return session
}

export const currentSession = (): AuthSession | null => readSession()

export const isAuthenticated = (): boolean => readSession() !== null

export const currentAccount = (): PublicAccount | null => {
  const session = readSession()
  if (!session) return null
  const account = readAccounts().find(item => item.id === session.accountId)
  return account ? toPublic(account) : null
}

/** 剩余锁定秒数，0 表示未锁定。 */
export const lockSecondsLeft = (): number => {
  const { lockedUntil } = readAttempts()
  return lockedUntil > Date.now() ? Math.ceil((lockedUntil - Date.now()) / 1000) : 0
}

const recordFailure = (): string => {
  const previous = readAttempts()
  const count = previous.lockedUntil > Date.now() ? previous.count : previous.count + 1
  const remaining = Math.max(0, MAX_ATTEMPTS - count)
  const lockedUntil = remaining === 0 ? Date.now() + LOCK_MS : 0
  writeAttempts({ count: remaining === 0 ? 0 : count, lockedUntil })
  if (remaining === 0) return '尝试次数过多，请 30 秒后重试'
  return `账号或密码错误，还可尝试 ${remaining} 次`
}

/**
 * @param options.signIn 注册后是否立即建立会话。原登录页要求「注册成功后回到登录页，
 * 由用户再完成一次密码验证」，因此页面侧会显式传 false；默认行为保持自动登录。
 */
export async function register(
  payload: RegisterPayload,
  options: { signIn?: boolean } = {}
): Promise<AuthResult> {
  const issues = validateRegister(payload)
  if (issues.length) return fail(issues[0].message)

  const username = payload.username.trim()
  const email = payload.email.trim().toLowerCase()
  const accounts = readAccounts()
  if (accounts.some(item => item.username.toLowerCase() === username.toLowerCase())) {
    return fail('该用户名已被注册')
  }
  if (accounts.some(item => item.email.toLowerCase() === email)) {
    return fail('该邮箱已被注册')
  }

  const salt = randomSalt()
  const passwordHash = await derivePasswordHash(payload.password, salt, PBKDF2_ITERATIONS)
  const account: StoredAccount = {
    id: randomId(),
    username,
    email,
    salt,
    passwordHash,
    iterations: PBKDF2_ITERATIONS,
    createdAt: new Date().toISOString()
  }
  writeAccounts([...accounts, account])
  if (options.signIn !== false) startSession(account, false)
  return ok(toPublic(account), '注册成功，正在进入工作台')
}

export async function login(payload: LoginPayload): Promise<AuthResult> {
  const issues = validateLogin(payload)
  if (issues.length) return fail(issues[0].message)

  const locked = lockSecondsLeft()
  if (locked > 0) return fail(`尝试次数过多，请 ${locked} 秒后重试`)

  const identifier = payload.identifier.trim().toLowerCase()
  const account = readAccounts().find(item =>
    item.username.toLowerCase() === identifier || item.email.toLowerCase() === identifier
  )
  // 账号不存在与口令错误使用同一句提示，避免账号枚举。
  if (!account) return fail(recordFailure())

  const candidate = await derivePasswordHash(payload.password, account.salt, account.iterations)
  if (!safeEqual(candidate, account.passwordHash)) return fail(recordFailure())

  startSession(account, Boolean(payload.remember))
  return ok(toPublic(account), `欢迎回来，${account.username}`)
}

export const logout = (): void => {
  clearSession()
  clearAttempts()
}
