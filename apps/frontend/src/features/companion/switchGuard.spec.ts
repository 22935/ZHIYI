import { describe, expect, it } from 'vitest'
import { createSwitchGuard } from './switchGuard'

describe('createSwitchGuard', () => {
  it('lets a lone switch land', () => {
    const guard = createSwitchGuard()
    expect(guard.begin()()).toBe(true)
  })

  it('tells the slow switch it has been superseded', () => {
    const guard = createSwitchGuard()
    const slow = guard.begin()
    const fast = guard.begin()
    // 慢的那次回来时必须认出自己已经过期，否则会把新形象覆盖掉。
    expect(slow()).toBe(false)
    expect(fast()).toBe(true)
  })

  it('keeps every earlier ticket stale no matter how many switches follow', () => {
    const guard = createSwitchGuard()
    const first = guard.begin()
    const second = guard.begin()
    const third = guard.begin()
    expect(first()).toBe(false)
    expect(second()).toBe(false)
    expect(third()).toBe(true)
  })

  it('keeps independent guards independent', () => {
    const skin = createSwitchGuard()
    const voice = createSwitchGuard()
    const skinTicket = skin.begin()
    voice.begin()
    expect(skinTicket()).toBe(true)
  })
})
