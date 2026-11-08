/**
 * 虚拟伙伴托盘的纯逻辑：状态校验、tooltip 文案、菜单描述、通知时机。
 *
 * 刻意不 import electron —— 桌面测试用 node --test 跑纯逻辑，不需要二进制；
 * Tray / Menu / Notification 的组装留在 main.ts，本文件只产出可校验的数据。
 * 不触碰窗口授权模型，也不放宽会话权限策略。
 */
// 带 .ts 后缀：本模块被 node --test 直接以 ESM 加载（与 lsp-host.ts 同构），
// esbuild 打包 main/preload 时同样能正确解析。
import { clampNumber, parseBoolean, parseBoundedText } from './validation.ts'

export const TRAY_ACTIONS = ['toggle', 'summon', 'progress', 'quiet', 'focus', 'voice'] as const
export type TrayAction = (typeof TRAY_ACTIONS)[number]

/** 托盘 tooltip 只显示这三种语音态；unknown / denied 一律按 idle 处理。 */
export const COMPANION_VOICE_PHASES = ['idle', 'listening', 'speaking'] as const
export type CompanionVoicePhase = (typeof COMPANION_VOICE_PHASES)[number]

export const isTrayAction = (value: unknown): value is TrayAction =>
  typeof value === 'string' && (TRAY_ACTIONS as readonly string[]).includes(value)

export const COMPANION_STATES = [
  'idle', 'listening', 'thinking', 'working', 'happy', 'alert', 'sleeping', 'error'
] as const

export interface CompanionSnapshot {
  state: string
  label: string
  level: number
  affinity: number
  quiet: boolean
  /** 可选：老版本渲染层不带这两个字段，托盘退化为固定名字与待机语音态。 */
  name?: string
  voice?: CompanionVoicePhase
}

export const DEFAULT_COMPANION_SNAPSHOT: CompanionSnapshot = {
  state: 'idle',
  label: '待机',
  level: 1,
  affinity: 0,
  quiet: false
}

/** Renderer 传上来的一切都当不可信输入：越界、缺字段、脏字符串一律拒绝。 */
export function parseCompanionSnapshot(raw: unknown): CompanionSnapshot | null {
  if (!raw || typeof raw !== 'object') return null
  const data = raw as Record<string, unknown>
  if (typeof data.state !== 'string' || !(COMPANION_STATES as readonly string[]).includes(data.state)) return null
  const label = parseBoundedText(data.label, 32)
  const level = clampNumber(data.level, 1, 12)
  const affinity = clampNumber(data.affinity, 0, 720)
  const quiet = parseBoolean(data.quiet)
  if (!label || level === null || affinity === null || quiet === null) return null
  const result: CompanionSnapshot = {
    state: data.state,
    label,
    level: Math.round(level),
    affinity: Math.round(affinity),
    quiet
  }
  // 可选字段只在高版本渲染层真正提供时出现，保持旧快照的 deepEqual 语义。
  if (typeof data.name === 'string') {
    const name = parseBoundedText(data.name, 12)
    if (name) result.name = name
  }
  if (typeof data.voice === 'string'
    && (COMPANION_VOICE_PHASES as readonly string[]).includes(data.voice)) {
    result.voice = data.voice as CompanionVoicePhase
  }
  return result
}

export function formatTrayTooltip(snapshot: CompanionSnapshot): string {
  const name = snapshot.name || '知宝'
  const base = `${name} · ${snapshot.label} · Lv.${snapshot.level}（好感 ${snapshot.affinity}）`
  const voice = snapshot.voice === 'listening' ? ' · 正在听'
    : snapshot.voice === 'speaking' ? ' · 正在说' : ''
  return `${base}${voice}${snapshot.quiet ? ' · 免打扰' : ''}`
}

export interface TrayMenuItem {
  kind: 'item' | 'checkbox' | 'separator'
  label?: string
  checked?: boolean
  /** 'quit' 由 Main 直接处理，不进入 Renderer 事件通道。 */
  action?: TrayAction | 'quit'
}

/** 固定文案：托盘菜单不接受 Renderer 提供的任意字符串，避免注入与漂移。 */
export function trayMenuDescriptor(snapshot: CompanionSnapshot): TrayMenuItem[] {
  return [
    { kind: 'item', label: '叫一声知宝', action: 'summon' },
    { kind: 'item', label: '听我说话', action: 'voice' },
    { kind: 'item', label: '查看当前进度', action: 'progress' },
    { kind: 'separator' },
    { kind: 'checkbox', label: '免打扰', checked: snapshot.quiet, action: 'quiet' },
    { kind: 'separator' },
    { kind: 'item', label: '显示主窗口', action: 'focus' },
    { kind: 'item', label: '退出知弈', action: 'quit' }
  ]
}

/** 用户正看着窗口时不需要系统弹窗；免打扰优先级最高。 */
export function shouldDeliverNotification(
  snapshot: CompanionSnapshot,
  windowFocused: boolean,
  windowMinimized: boolean
): boolean {
  if (snapshot.quiet) return false
  return !(windowFocused && !windowMinimized)
}

export function parseNotification(raw: unknown): { title: string; body: string | undefined } | null {
  if (!raw || typeof raw !== 'object') return null
  const data = raw as Record<string, unknown>
  const title = parseBoundedText(data.title, 200)
  if (!title) return null
  return { title, body: parseBoundedText(data.body, 2000) ?? undefined }
}
