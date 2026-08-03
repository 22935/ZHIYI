import { beforeEach, describe, expect, it, vi } from 'vitest'

const { errorMessage } = vi.hoisted(() => ({ errorMessage: vi.fn() }))

vi.mock('element-plus', () => ({
  ElMessage: { error: errorMessage }
}))

import request, { wasErrorUserNotified } from './request'

describe('request error notifications', () => {
  beforeEach(() => {
    errorMessage.mockClear()
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
})
