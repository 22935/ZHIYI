import { webcrypto } from 'node:crypto'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  currentAccount,
  currentSession,
  isAuthenticated,
  lockSecondsLeft,
  login,
  logout,
  register
} from './authService'
import { derivePasswordHash, PBKDF2_ITERATIONS, randomSalt, safeEqual } from './crypto'
import { ACCOUNTS_KEY, SESSION_KEY, readAccounts } from './storage'
import { validateLogin, validateRegister } from './validation'

const validRegister = {
  username: 'kinlin_user',
  email: 'kinlin@example.com',
  password: 'agentOS2026',
  confirmPassword: 'agentOS2026'
}

beforeEach(() => {
  localStorage.clear()
  sessionStorage.clear()
  vi.stubGlobal('crypto', webcrypto)
})

describe('表单校验', () => {
  it('接受合法的注册信息', () => {
    expect(validateRegister(validRegister)).toEqual([])
  })

  it.each([
    [{ ...validRegister, username: 'ab' }, 'username'],
    [{ ...validRegister, username: 'bad name!' }, 'username'],
    [{ ...validRegister, email: 'not-an-email' }, 'email'],
    [{ ...validRegister, password: 'short1' }, 'password'],
    [{ ...validRegister, password: 'onlyletters' }, 'password'],
    [{ ...validRegister, confirmPassword: 'different1' }, 'confirmPassword']
  ])('拒绝非法字段 %j', (payload, field) => {
    expect(validateRegister(payload).some(issue => issue.field === field)).toBe(true)
  })

  it('登录只要求账号与密码非空', () => {
    expect(validateLogin({ identifier: '', password: '' })).toHaveLength(2)
    expect(validateLogin({ identifier: 'kinlin_user', password: 'x' })).toEqual([])
  })
})

describe('口令派生', () => {
  it('同盐同口令得到同样摘要，换盐或换口令即不同', async () => {
    const salt = randomSalt()
    const first = await derivePasswordHash('agentOS2026', salt)
    const again = await derivePasswordHash('agentOS2026', salt)
    const otherSalt = await derivePasswordHash('agentOS2026', randomSalt())
    const otherPassword = await derivePasswordHash('agentOS2027', salt)
    expect(first).toBe(again)
    expect(first).toHaveLength(64)
    expect(first).not.toBe(otherSalt)
    expect(first).not.toBe(otherPassword)
  })

  it('safeEqual 不把长度不同或内容不同的摘要判为相等', () => {
    expect(safeEqual('abc', 'abc')).toBe(true)
    expect(safeEqual('abc', 'abd')).toBe(false)
    expect(safeEqual('abc', 'abcd')).toBe(false)
  })
})

describe('注册与登录闭环', () => {
  it('注册后写入加盐摘要、不存明文，并自动建立会话', async () => {
    const result = await register(validRegister)
    expect(result.ok).toBe(true)
    const accounts = readAccounts()
    expect(accounts).toHaveLength(1)
    expect(accounts[0].iterations).toBe(PBKDF2_ITERATIONS)
    expect(accounts[0].passwordHash).not.toContain(validRegister.password)
    expect(accounts[0].salt).not.toBe('')
    expect(localStorage.getItem(ACCOUNTS_KEY)).not.toContain(validRegister.password)
    expect(isAuthenticated()).toBe(true)
    expect(currentAccount()?.username).toBe('kinlin_user')
  })

  it('拒绝重复用户名和重复邮箱', async () => {
    await register(validRegister)
    logout()
    expect((await register(validRegister)).message).toBe('该用户名已被注册')
    expect((await register({
      ...validRegister,
      username: 'another_user',
      email: 'KINLIN@example.com'
    })).message).toBe('该邮箱已被注册')
  })

  it('可用用户名或邮箱登录，标识符大小写不敏感', async () => {
    await register(validRegister)
    logout()
    expect((await login({ identifier: 'KINLIN_USER', password: validRegister.password })).ok).toBe(true)
    logout()
    expect((await login({ identifier: 'kinlin@example.com', password: validRegister.password })).ok).toBe(true)
  })

  it('密码错误给出统一提示并累计失败次数', async () => {
    await register(validRegister)
    logout()
    const first = await login({ identifier: validRegister.username, password: 'wrongpass1' })
    expect(first.ok).toBe(false)
    expect(first.message).toContain('还可尝试 4 次')
    expect(isAuthenticated()).toBe(false)
  })

  it('连续 5 次失败后锁定 30 秒，正确密码也被拒绝', async () => {
    await register(validRegister)
    logout()
    for (let i = 0; i < 5; i += 1) {
      await login({ identifier: validRegister.username, password: 'wrongpass1' })
    }
    expect(lockSecondsLeft()).toBeGreaterThan(0)
    expect((await login({
      identifier: validRegister.username,
      password: validRegister.password
    })).message).toContain('请')
    expect(isAuthenticated()).toBe(false)
  })

  it('登录成功后清空失败计数', async () => {
    await register(validRegister)
    logout()
    await login({ identifier: validRegister.username, password: 'wrongpass1' })
    expect((await login({ identifier: validRegister.username, password: validRegister.password })).ok).toBe(true)
    expect(lockSecondsLeft()).toBe(0)
  })

  it('记住登录写 localStorage，否则写 sessionStorage', async () => {
    await register(validRegister)
    logout()
    await login({ identifier: validRegister.username, password: validRegister.password })
    expect(sessionStorage.getItem(SESSION_KEY)).not.toBeNull()
    expect(localStorage.getItem(SESSION_KEY)).toBeNull()
    logout()
    await login({ identifier: validRegister.username, password: validRegister.password, remember: true })
    expect(localStorage.getItem(SESSION_KEY)).not.toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
    expect(currentSession()?.remember).toBe(true)
  })

  it('过期会话视为未登录', async () => {
    await register(validRegister)
    const expired = JSON.stringify({
      accountId: 'expired',
      username: 'kinlin_user',
      expiresAt: Date.now() - 1,
      remember: false
    })
    sessionStorage.setItem(SESSION_KEY, expired)
    expect(isAuthenticated()).toBe(false)
    expect(currentAccount()).toBeNull()
  })

  it('登出清除两个存储位', async () => {
    await register(validRegister)
    logout()
    expect(isAuthenticated()).toBe(false)
    expect(localStorage.getItem(SESSION_KEY)).toBeNull()
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull()
  })

  it('损坏的账号库不会导致崩溃', async () => {
    localStorage.setItem(ACCOUNTS_KEY, '{not json')
    expect((await login({ identifier: 'nobody', password: 'whatever1' })).ok).toBe(false)
  })
})
