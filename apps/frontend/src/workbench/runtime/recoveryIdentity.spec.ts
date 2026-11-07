import { beforeEach, expect, it } from 'vitest'
import { beginRunRecovery, completeRunRecovery, pendingRunRecovery } from './recoveryIdentity'
beforeEach(() => { sessionStorage.clear(); localStorage.clear(); localStorage.setItem('userId', 'local-owner') })
const retry = (mode = 'successor_run') => ({ kind: 'retry', stepId: 'step', payload: { mode, clientRequestId: 'same-id', expectedRuntimeRevision: 4 } } as any)
it('refuses current_run for every source, including historical failed Runs', () => {
  expect(() => beginRunRecovery('m', 'a', retry('current_run'), sessionStorage)).toThrow('身份损坏')
  expect(sessionStorage.length).toBe(0)
})
it('retains exact identity and fingerprint across lost responses and reloads', () => {
  const first = beginRunRecovery('m', 'a', retry(), sessionStorage)
  expect(pendingRunRecovery('m', 'a', sessionStorage)).toEqual(first)
  expect(beginRunRecovery('m', 'a', retry(), sessionStorage)).toEqual(first)
  expect(() => beginRunRecovery('m', 'a', { ...retry(), payload: { ...retry().payload, clientRequestId: 'new-id' } }, sessionStorage)).toThrow('原恢复结果未确认')
  completeRunRecovery(first, sessionStorage); expect(pendingRunRecovery('m', 'a', sessionStorage)).toBeNull()
})
it('fails closed for corrupt payload and account changes', () => {
  localStorage.setItem('userId', 'alice')
  beginRunRecovery('m', 'a', retry(), sessionStorage)
  localStorage.setItem('userId', 'bob'); expect(pendingRunRecovery('m', 'a', sessionStorage)).toBeNull()
  localStorage.setItem('userId', 'alice')
  const key = sessionStorage.key(0)!
  const value = JSON.parse(sessionStorage.getItem(key)!); value.payload.expectedRuntimeRevision++
  sessionStorage.setItem(key, JSON.stringify(value))
  expect(() => pendingRunRecovery('m', 'a', sessionStorage)).toThrow('身份损坏')
})
