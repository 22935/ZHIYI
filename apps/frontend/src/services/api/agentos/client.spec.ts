import { beforeEach, describe, expect, it } from 'vitest'
import { agentosRequest } from './client'

describe('AgentOS local platform requests', () => {
  beforeEach(() => localStorage.clear())
  it('preserves gateway paths and carries the local request marker without JWT', async () => {
    localStorage.setItem('token', 'obsolete-token')
    await agentosRequest.request({ url: '/missions', method: 'post', adapter: async config => {
      expect(config.baseURL).toContain('/api/agentos/v2')
      expect(config.headers.Authorization).toBeUndefined()
      expect(config.headers['X-Zhiyi-Local-Request']).toBe('1')
      return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
    } })
  })
  it('preserves backend business errors and local identity', async () => {
    localStorage.setItem('userId', 'local-owner')
    const failure = { response: { status: 403, data: { code: 'WORKSPACE_ACCESS_DENIED' } } }
    await expect(agentosRequest.request({ url: '/workspaces/current', adapter: async () => Promise.reject(failure) })).rejects.toBe(failure)
    expect(localStorage.getItem('userId')).toBe('local-owner')
  })
})
