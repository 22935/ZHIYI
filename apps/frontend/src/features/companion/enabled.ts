// 知宝显隐开关：唯一事实源是 appSettings.companionEnabled（缺省开启）。
// 本模块只读，不写存储键——写入仍由设置页统一负责，保存后经同页事件刷新，
// 避免两个写入方争抢同一份 JSON。
import { onMounted, onUnmounted, ref, type Ref } from 'vue'

export const APP_SETTINGS_SAVED_EVENT = 'app-settings-saved'

export function readCompanionEnabled(): boolean {
  try {
    const raw = localStorage.getItem('appSettings')
    if (!raw) return true
    const parsed = JSON.parse(raw) as { companionEnabled?: unknown }
    return typeof parsed.companionEnabled === 'boolean' ? parsed.companionEnabled : true
  } catch {
    return true
  }
}

export function useCompanionEnabled(): Ref<boolean> {
  const enabled = ref(readCompanionEnabled())
  const sync = (): void => {
    enabled.value = readCompanionEnabled()
  }
  onMounted(() => window.addEventListener(APP_SETTINGS_SAVED_EVENT, sync))
  onUnmounted(() => window.removeEventListener(APP_SETTINGS_SAVED_EVENT, sync))
  return enabled
}

// 知宝开关是「即时生效」项：翻转即写盘并广播，不等设置页的「保存设置」。
// 只合并本字段，其余草稿仍归保存按钮管；写入失败（存储不可用）只放弃持久化，
// 事件照发，让本页浮层开关在当前会话内仍然生效。
export function applyCompanionEnabled(value: boolean): void {
  let stored: Record<string, unknown> = {}
  try {
    const raw = localStorage.getItem('appSettings')
    if (raw) stored = JSON.parse(raw) as Record<string, unknown>
  } catch {
    stored = {}
  }
  try {
    localStorage.setItem('appSettings', JSON.stringify({ ...stored, companionEnabled: value }))
  } catch { /* storage is optional */ }
  window.dispatchEvent(new CustomEvent(APP_SETTINGS_SAVED_EVENT))
}
