import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { initAppKeyboardShortcuts } from './useAppKeyboardShortcuts'

const fireKeydown = (init: KeyboardEventInit & { key: string }, target: EventTarget = window): Event => {
  const event = new KeyboardEvent('keydown', { cancelable: true, bubbles: true, ...init })
  target.dispatchEvent(event)
  return event
}

const mountTerminalFocus = (): { host: HTMLElement; focusable: HTMLElement; cleanup: () => void } => {
  const host = document.createElement('div')
  host.className = 'desktop-terminal'
  const focusable = document.createElement('textarea')
  host.appendChild(focusable)
  document.body.appendChild(host)
  focusable.focus()
  return {
    host,
    focusable,
    cleanup: () => {
      focusable.blur()
      host.remove()
    }
  }
}

describe('useAppKeyboardShortcuts', () => {
  let toggleChatPanel: ReturnType<typeof vi.fn>
  let historyBack: ReturnType<typeof vi.fn>
  let historyForward: ReturnType<typeof vi.fn>
  let onShowShortcuts: ReturnType<typeof vi.fn>
  let reload: ReturnType<typeof vi.fn>
  let dispose: (() => void) | null = null

  const init = (desktop = true): void => {
    dispose = initAppKeyboardShortcuts({
      desktop,
      toggleChatPanel,
      historyBack,
      historyForward,
      onShowShortcuts,
      reload
    })
  }

  beforeEach(() => {
    toggleChatPanel = vi.fn()
    historyBack = vi.fn()
    historyForward = vi.fn()
    onShowShortcuts = vi.fn()
    reload = vi.fn()
  })

  afterEach(() => {
    dispose?.()
    dispose = null
  })

  it('Ctrl+B 开合对话栏、Ctrl+R/F5 刷新、Alt+方向键路由导航', () => {
    init()

    const panelEvent = fireKeydown({ key: 'b', ctrlKey: true })
    expect(toggleChatPanel).toHaveBeenCalledTimes(1)
    expect(panelEvent.defaultPrevented).toBe(true)

    fireKeydown({ key: 'r', ctrlKey: true })
    expect(reload).toHaveBeenCalledTimes(1)

    fireKeydown({ key: 'F5' })
    expect(reload).toHaveBeenCalledTimes(2)

    fireKeydown({ key: 'ArrowLeft', altKey: true })
    expect(historyBack).toHaveBeenCalledTimes(1)

    fireKeydown({ key: 'ArrowRight', altKey: true })
    expect(historyForward).toHaveBeenCalledTimes(1)
  })

  it('F1 与非输入焦点下的 ? 都打开速查浮层（Web 构建同样可用）', () => {
    init(false)

    const f1Event = fireKeydown({ key: 'F1' })
    expect(onShowShortcuts).toHaveBeenCalledTimes(1)
    expect(f1Event.defaultPrevented).toBe(true)

    const questionEvent = fireKeydown({ key: '?', shiftKey: true })
    expect(onShowShortcuts).toHaveBeenCalledTimes(2)
    expect(questionEvent.defaultPrevented).toBe(true)
  })

  it('Web 构建（desktop=false）：Ctrl+B 开合对话栏；Ctrl+R/Alt 导航不接管', () => {
    init(false)

    fireKeydown({ key: 'b', ctrlKey: true })
    expect(toggleChatPanel).toHaveBeenCalledTimes(1)

    fireKeydown({ key: 'r', ctrlKey: true })
    fireKeydown({ key: 'ArrowLeft', altKey: true })
    fireKeydown({ key: 'ArrowRight', altKey: true })

    expect(reload).not.toHaveBeenCalled()
    expect(historyBack).not.toHaveBeenCalled()
    expect(historyForward).not.toHaveBeenCalled()
  })

  it('焦点在内置终端内时全部让位给 shell', () => {
    init()
    const terminal = mountTerminalFocus()

    fireKeydown({ key: 'b', ctrlKey: true }, terminal.focusable)
    fireKeydown({ key: 'r', ctrlKey: true }, terminal.focusable)
    fireKeydown({ key: '?', shiftKey: true }, terminal.focusable)
    fireKeydown({ key: 'ArrowLeft', altKey: true }, terminal.focusable)

    expect(toggleChatPanel).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
    expect(onShowShortcuts).not.toHaveBeenCalled()
    expect(historyBack).not.toHaveBeenCalled()
    terminal.cleanup()
  })

  it('Ctrl+B срабатывает и в поле ввода (editableSafe), но не в терминале', () => {
    init()
    const input = document.createElement('textarea')
    document.body.appendChild(input)
    input.focus()

    fireKeydown({ key: 'b', ctrlKey: true }, input)
    expect(toggleChatPanel).toHaveBeenCalledTimes(1)
    input.remove()

    const terminal = mountTerminalFocus()
    fireKeydown({ key: 'b', ctrlKey: true }, terminal.focusable)
    expect(toggleChatPanel).toHaveBeenCalledTimes(1)
    terminal.cleanup()
  })

  it('? 在输入框焦点下不触发浮层', () => {
    init()
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()

    fireKeydown({ key: '?', shiftKey: true }, input)
    expect(onShowShortcuts).not.toHaveBeenCalled()

    // F1 不受输入焦点限制，仍是浮层入口。
    fireKeydown({ key: 'F1' }, input)
    expect(onShowShortcuts).toHaveBeenCalledTimes(1)
    input.remove()
  })

  it('按键重复与组合键修饰符边界不触发', () => {
    init()

    const repeatEvent = new KeyboardEvent('keydown', { cancelable: true, bubbles: true, key: 'r', ctrlKey: true })
    Object.defineProperty(repeatEvent, 'repeat', { value: true })
    window.dispatchEvent(repeatEvent)
    expect(reload).not.toHaveBeenCalled()

    // Ctrl+Shift+B 不是对话栏键（避免误吞其他语义组合）；Ctrl+Alt+R 不是刷新键。
    fireKeydown({ key: 'b', ctrlKey: true, shiftKey: true })
    fireKeydown({ key: 'r', ctrlKey: true, altKey: true })
    fireKeydown({ key: 'ArrowLeft', altKey: true, ctrlKey: true })

    expect(toggleChatPanel).not.toHaveBeenCalled()
    expect(reload).not.toHaveBeenCalled()
    expect(historyBack).not.toHaveBeenCalled()
  })

  it('未初始化时不响应任何快捷键', () => {
    fireKeydown({ key: 'b', ctrlKey: true })
    fireKeydown({ key: 'F1' })
    expect(toggleChatPanel).not.toHaveBeenCalled()
    expect(onShowShortcuts).not.toHaveBeenCalled()
  })

  it('清理后监听全部移除；重复初始化幂等', () => {
    init()
    const second = initAppKeyboardShortcuts({
      desktop: true,
      toggleChatPanel,
      historyBack,
      historyForward,
      onShowShortcuts,
      reload
    })
    expect(second).toBe(dispose)

    dispose?.()
    dispose = null

    fireKeydown({ key: 'b', ctrlKey: true })
    fireKeydown({ key: 'F1' })
    expect(toggleChatPanel).not.toHaveBeenCalled()
    expect(onShowShortcuts).not.toHaveBeenCalled()
  })
})
