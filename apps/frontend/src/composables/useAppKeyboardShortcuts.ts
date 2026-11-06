/**
 * 应用级全局快捷键（AuthenticatedAppShell 装载）：
 * - Ctrl+B 对话记录子栏 开/关（web/桌面都生效；仅 OScode/Workbench 页面，页面切换逻辑不在快捷键里）；
 * - Ctrl+R / F5 刷新页面（放渲染进程而非 Main：内置终端里 Ctrl+R 是 shell 历史搜索，
 *   需按焦点让位；页面崩溃场景已有 render-process-gone 弹窗兜底）；
 * - Alt+← / Alt+→ 路由后退/前进（与顶栏按钮同效）；
 * - F1 / ? 打开快捷键速查浮层（? 仅在非输入焦点时触发）。
 *
 * 命令定义集中注册到 workbench 命令表，快捷键派发由 installCommandKeybindings 统一完成；
 * 统一让位规则：焦点在 `.desktop-terminal` 内时全部交还 shell
 * （Ctrl+B=backward-char、Alt+B/F=词跳转、`?` 是常用字符）。
 * 窗口级 F11/F12 在 Electron Main 的 before-input-event 处理，不经这里。
 */

import { commands, installCommandKeybindings, type CommandDescriptor } from '@/workbench/core/commands'

export interface AppKeyboardShortcutOptions {
  /** 仅桌面构建启用（Web 下 Ctrl+R / Alt 导航无窗口语义；Ctrl+B 与桌面无关，web 也注册）。 */
  desktop: boolean
  /** 对话记录子栏 开/关；只翻面板状态，不导航（目标页无面板时为 no-op）。 */
  toggleChatPanel: () => void
  historyBack: () => void
  historyForward: () => void
  onShowShortcuts: () => void
  /** 刷新落点；缺省整页重载（依赖注入便于测试替换）。 */
  reload?: () => void
}

let disposer: (() => void) | null = null

/** 焦点在内置终端（含 xterm 辅助 textarea）内时，所有应用快捷键让位。 */
export const isTerminalFocusTarget = (): boolean => {
  const active = document.activeElement
  return Boolean(active && active.closest('.desktop-terminal'))
}

const isEditableTarget = (target: EventTarget | null): boolean => {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable) return true
  const tag = target.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
}

/** 初始化全局快捷键接管；幂等，重复调用返回同一个清理函数。 */
export function initAppKeyboardShortcuts(options: AppKeyboardShortcutOptions): () => void {
  if (disposer) return disposer
  const registered: Array<() => void> = []
  const register = (command: CommandDescriptor): void => {
    registered.push(commands.register(command))
  }

  // F1 与 ? 是同一个动作的两个入口，但输入焦点下只允许 F1：? 是常用字符。
  register({
    id: 'app.showShortcuts',
    title: '快捷键速查',
    category: '通用',
    order: 20,
    keys: ['f1'],
    editableSafe: true,
    run: options.onShowShortcuts
  })
  register({
    id: 'app.showShortcuts.question',
    title: '快捷键速查',
    category: '通用',
    order: 21,
    keys: ['?'],
    run: options.onShowShortcuts
  })

  // Ctrl+B — чисто страничное действие (панель), работает и в web-сборке;
  // editableSafe: не подавляется в полях ввода (иначе «закрыть» не сработает
  // после того, как панель сфокусировала поле сообщения);
  // терминал НЕ отдан: там Ctrl+B = backward-char (правило терминала ниже).
  register({
    id: 'app.toggleChatPanel',
    title: '对话记录栏 开/关',
    category: '桌面',
    order: 30,
    keys: ['mod+b'],
    editableSafe: true,
    run: options.toggleChatPanel
  })

  if (options.desktop) {
    register({
      id: 'app.reload',
      title: '刷新页面',
      category: '桌面',
      order: 40,
      keys: ['f5', 'mod+r'],
      run: options.reload || (() => window.location.reload())
    })
    register({ id: 'app.historyBack', title: '后退', category: '桌面', order: 50, keys: ['alt+arrowleft'], run: options.historyBack })
    register({ id: 'app.historyForward', title: '前进', category: '桌面', order: 60, keys: ['alt+arrowright'], run: options.historyForward })
  }

  const removeKeybindings = installCommandKeybindings({
    isTerminalFocused: isTerminalFocusTarget,
    isEditableTarget
  })

  disposer = () => {
    removeKeybindings()
    registered.forEach(unregister => unregister())
    registered.length = 0
    disposer = null
  }
  return disposer
}
