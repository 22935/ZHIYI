import type {
  LoginPayload,
  RegisterPayload,
  ValidationIssue
} from './types'

const USERNAME_RE = /^[A-Za-z0-9_\u4e00-\u9fa5]{3,20}$/
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$/

export const validateUsername = (value: string): string | null => {
  const username = value.trim()
  if (!username) return '请输入用户名'
  if (!USERNAME_RE.test(username)) return '用户名需为 3–20 位字母、数字、下划线或中文'
  return null
}

export const validateEmail = (value: string): string | null => {
  const email = value.trim()
  if (!email) return '请输入邮箱'
  if (email.length > 120 || !EMAIL_RE.test(email)) return '邮箱格式不正确'
  return null
}

export const validatePassword = (value: string): string | null => {
  if (!value) return '请输入密码'
  if (value.length < 8 || value.length > 32) return '密码长度需为 8–32 位'
  if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) return '密码需同时包含字母和数字'
  return null
}

export const validateLogin = (payload: LoginPayload): ValidationIssue[] => {
  const issues: ValidationIssue[] = []
  if (!payload.identifier.trim()) {
    issues.push({ field: 'identifier', message: '请输入用户名或邮箱' })
  }
  if (!payload.password) {
    issues.push({ field: 'password', message: '请输入密码' })
  }
  return issues
}

export const validateRegister = (payload: RegisterPayload): ValidationIssue[] => {
  const issues: ValidationIssue[] = []
  const username = validateUsername(payload.username)
  if (username) issues.push({ field: 'username', message: username })
  const email = validateEmail(payload.email)
  if (email) issues.push({ field: 'email', message: email })
  const password = validatePassword(payload.password)
  if (password) issues.push({ field: 'password', message: password })
  if (!payload.confirmPassword) {
    issues.push({ field: 'confirmPassword', message: '请再次输入密码' })
  } else if (payload.confirmPassword !== payload.password) {
    issues.push({ field: 'confirmPassword', message: '两次输入的密码不一致' })
  }
  return issues
}

export const issueFor = (
  issues: ValidationIssue[],
  field: ValidationIssue['field']
): string | undefined => issues.find(issue => issue.field === field)?.message
