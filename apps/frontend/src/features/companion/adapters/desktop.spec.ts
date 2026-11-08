import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  NOOP_DESKTOP_PORT, createDesktopPort, isTrayAction, type CompanionDesktopState
} from './desktop'

type CompanionBridgeMock = {
  publishState: ReturnType<typeof vi.fn>
  notifyIfBackground: ReturnType<typeof vi.fn>
  onTrayAction: ReturnType<typeof vi.fn>
}

const install = (companion?: CompanionBridgeMock): void => {
  const bridge = companion ? { companion } : {}
  ;(window as unknown as { kinlinDesktop?: unknown }).kinlinDesktop = bridge
}

const build = (): CompanionBridgeMock => ({
  publishState: vi.fn(async (_snapshot: unknown) => undefined),
  notifyIfBackground: vi.fn(async (_title: string, _body: string) => undefined),
  onTrayAction: vi.fn((_cb: (action: string) => void) => () => undefined)
})

const snapshot = (overrides: Partial<CompanionDesktopState> = {}): CompanionDesktopState => ({
  state: 'idle', label: '待机', level: 1, affinity: 0, quiet: false, ...overrides
})

describe('companion desktop port', () => {
  afterEach(() => {
    delete (window as unknown as { kinlinDesktop?: unknown }).kinlinDesktop
    vi.restoreAllMocks()
  })

  it('degrades to a safe no-op on Web and on older preload shells', () => {
    expect(createDesktopPort().available).toBe(false)
    install()
    const port = createDesktopPort()
    expect(port).toBe(NOOP_DESKTOP_PORT)
    expect(() => port.publishState(snapshot())).not.toThrow()
    expect(() => port.notifyIfBackground('a', 'b')).not.toThrow()
    expect(typeof port.onTrayAction(() => undefined)).toBe('function')
  })

  it('dedupes identical snapshots and throttles non-urgent churn', () => {
    const bridge = build()
    install(bridge)
    let clock = 1000
    const port = createDesktopPort(() => clock)
    expect(port.available).toBe(true)

    port.publishState(snapshot())
    port.publishState(snapshot())
    expect(bridge.publishState).toHaveBeenCalledTimes(1)

    clock = 1100
    port.publishState(snapshot({ affinity: 3 }))
    expect(bridge.publishState).toHaveBeenCalledTimes(1)

    clock = 2000
    port.publishState(snapshot({ affinity: 8 }))
    expect(bridge.publishState).toHaveBeenCalledTimes(2)
    expect(bridge.publishState).toHaveBeenLastCalledWith(snapshot({ affinity: 8 }))
  })

  it('never throttles away error and alert states', () => {
    const bridge = build()
    install(bridge)
    const port = createDesktopPort(() => 5000)
    port.publishState(snapshot())
    port.publishState(snapshot({ state: 'error', label: '出错了' }))
    expect(bridge.publishState).toHaveBeenCalledTimes(2)
    expect(bridge.publishState).toHaveBeenLastCalledWith(snapshot({ state: 'error', label: '出错了' }))
  })

  it('forwards background notifications and swallows IPC rejection', async () => {
    const bridge = build()
    bridge.notifyIfBackground.mockRejectedValueOnce(new Error('no main process'))
    install(bridge)
    const port = createDesktopPort()
    port.notifyIfBackground('知宝 · 需要关注', '有个运行出问题了')
    await Promise.resolve()
    expect(bridge.notifyIfBackground).toHaveBeenCalledWith('知宝 · 需要关注', '有个运行出问题了')
    expect(isTrayAction('progress')).toBe(true)
    expect(isTrayAction('quit')).toBe(false)
  })

  it('narrows tray actions through a whitelist and unsubscribes cleanly', () => {
    const bridge = build()
    const unsubscribe = vi.fn()
    let listener: ((action: string) => void) | null = null
    bridge.onTrayAction.mockImplementation((cb: (action: string) => void) => {
      listener = cb
      return unsubscribe
    })
    install(bridge)
    const received: string[] = []
    const off = createDesktopPort().onTrayAction(action => received.push(action))
    listener?.('summon')
    listener?.('quit')
    listener?.('__proto__')
    expect(received).toEqual(['summon'])
    off()
    expect(unsubscribe).toHaveBeenCalledTimes(1)
  })
})
