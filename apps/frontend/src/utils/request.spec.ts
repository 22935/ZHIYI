import { beforeEach, describe, expect, it, vi } from 'vitest'

const { errorMessage, isDesktop } = vi.hoisted(() => ({
  errorMessage: vi.fn(),
  isDesktop: vi.fn(() => false)
}))

vi.mock('element-plus', () => ({
  ElMessage: { error: errorMessage }
}))

vi.mock('@/platform', () => ({
  apiUrl: (path: string) => path,
  LOCAL_REQUEST_HEADERS: { 'X-Zhiyi-Local-Request': '1' },
  isDesktop
}))

import request, { wasErrorUserNotified } from './request'

describe('request error notifications', () => {
  beforeEach(() => {
    errorMessage.mockClear()
    isDesktop.mockReturnValue(false)
    localStorage.clear()
    window.location.hash = ''
  })

  it('marks a rejected business response after notifying the user once', async () => {
    const pending = request.request({
      url: '/agent/lawyer/chat',
      method: 'post',
      adapter: async config => ({
        data: { success: false, message: 'Python agent unavailable' },
        status: 200,
        statusText: 'OK',
        headers: {},
        config
      })
    })

    const error = await pending.catch(reason => reason)

    expect(errorMessage).toHaveBeenCalledOnce()
    expect(errorMessage).toHaveBeenCalledWith('Python agent unavailable')
    expect(wasErrorUserNotified(error)).toBe(true)
  })

  it('does not classify ordinary errors as already displayed', () => {
    expect(wasErrorUserNotified(new Error('local failure'))).toBe(false)
    expect(wasErrorUserNotified({ message: 'not an Error instance' })).toBe(false)
  })

  it('reports service authentication errors without navigation or identity removal', async () => {
    window.location.hash = '#/chat'
    localStorage.setItem('userId', 'local-owner')
    await request.request({
      url: '/roles/builtin', method: 'get',
      adapter: async config => Promise.reject({ config, response: { status: 401, data: {} } })
    }).catch(() => undefined)
    expect(window.location.hash).toBe('#/chat')
    expect(localStorage.getItem('userId')).toBe('local-owner')
    expect(errorMessage).toHaveBeenCalledWith('本机服务认证失败，请检查运行配置')
  })

  it('adds the local write header and ignores a historical user token', async () => {
    localStorage.setItem('token', 'obsolete-token')
    await request.request({
      url: '/conversations', method: 'post',
      adapter: async config => {
        expect(config.headers.Authorization).toBeUndefined()
        expect(config.headers['X-Zhiyi-Local-Request']).toBe('1')
        return { data: {}, status: 200, statusText: 'OK', headers: {}, config }
      }
    })
  })

  it('keeps global forbidden notifications on the shared request client', async () => {
    const pending = request.request({
      url: '/roles/builtin',
      method: 'get',
      adapter: async config => Promise.reject({
        config,
        response: { status: 403, data: { message: 'role access denied' } }
      })
    })

    await pending.catch(() => undefined)

    expect(errorMessage).toHaveBeenCalledWith('role access denied')
  })

})
