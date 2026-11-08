/**
 * 桌面能力端口：把 Electron 托盘 / 原生通知收敛成一个可选 Port。
 *
 * - Web 宿主或旧版 preload（没有 companion 命名空间）→ 返回 no-op，主流程零感知；
 * - Renderer 永不 import 'electron'，只经 window.kinlinDesktop 白名单桥；
 * - 托盘菜单的动作类型是固定白名单，未识别事件直接丢弃。
 */
import { getElectronBridge } from '@/platform/electron/bridge'
import type { CompanionState } from '../types'

export const TRAY_ACTIONS = ['toggle', 'summon', 'progress', 'quiet', 'focus', 'voice'] as const
export type TrayAction = (typeof TRAY_ACTIONS)[number]
export type TrayVoicePhase = 'idle' | 'listening' | 'speaking'

export const isTrayAction = (value: unknown): value is TrayAction =>
  typeof value === 'string' && (TRAY_ACTIONS as readonly string[]).includes(value)

export interface CompanionDesktopState {
  state: CompanionState
  label: string
  level: number
  affinity: number
  quiet: boolean
  name?: string
  voice?: TrayVoicePhase
}

export interface DesktopPort {
  readonly available: boolean
  publishState(snapshot: CompanionDesktopState): void
  notifyIfBackground(title: string, body: string): void
  onTrayAction(listener: (action: TrayAction) => void): () => void
}

export const NOOP_DESKTOP_PORT: DesktopPort = {
  available: false,
  publishState: () => undefined,
  notifyIfBackground: () => undefined,
  onTrayAction: () => () => undefined
}

/**
 * 托盘 tooltip 不需要逐帧同步：按内容签名合并 400ms 内的高频变化。
 * 告警/错误态例外，必须立刻下发，不能被节流吞掉；被节流时不更新签名，
 * 后续调用仍会把最新快照送到托盘，不会停在过期状态。
 */
const PUBLISH_THROTTLE_MS = 400

export function createDesktopPort(now: () => number = () => Date.now()): DesktopPort {
  const bridge = getElectronBridge()?.companion
  if (!bridge) return NOOP_DESKTOP_PORT
  let lastPublishAt = Number.NEGATIVE_INFINITY
  let lastSignature = ''

  return {
    available: true,
    publishState(snapshot) {
      const signature = JSON.stringify(snapshot)
      if (signature === lastSignature) return
      const at = now()
      const urgent = snapshot.state === 'error' || snapshot.state === 'alert'
      if (!urgent && lastSignature && at - lastPublishAt < PUBLISH_THROTTLE_MS) return
      lastPublishAt = at
      lastSignature = signature
      void Promise.resolve(bridge.publishState(snapshot)).catch(() => undefined)
    },
    notifyIfBackground(title, body) {
      void Promise.resolve(bridge.notifyIfBackground(title, body)).catch(() => undefined)
    },
    onTrayAction(listener) {
      return bridge.onTrayAction((raw: unknown) => {
        if (isTrayAction(raw)) listener(raw)
      })
    }
  }
}
