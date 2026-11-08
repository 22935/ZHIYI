/** 本机账号体系的数据结构。账号只保存在浏览器本机存储，不上传、不参与后端 LocalIdentity。 */
export interface StoredAccount {
  id: string
  username: string
  email: string
  /** 每个账号独立的随机盐（hex）。 */
  salt: string
  /** PBKDF2-SHA256 派生的密码摘要（hex），永不保存明文。 */
  passwordHash: string
  iterations: number
  createdAt: string
}

export type PublicAccount = Pick<StoredAccount, 'id' | 'username' | 'email' | 'createdAt'>

export interface AuthSession {
  accountId: string
  username: string
  expiresAt: number
  remember: boolean
}

export type AuthMode = 'login' | 'register'

export interface LoginPayload {
  /** 用户名或邮箱。 */
  identifier: string
  password: string
  remember?: boolean
}

export interface RegisterPayload {
  username: string
  email: string
  password: string
  confirmPassword: string
}

export type AuthField =
  | 'identifier'
  | 'username'
  | 'email'
  | 'password'
  | 'confirmPassword'

export interface ValidationIssue {
  field: AuthField
  message: string
}

export type AuthResult<T = PublicAccount> =
  | { ok: true; value: T; message: string }
  | { ok: false; message: string }
