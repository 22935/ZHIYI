import type { WorkbenchSidebar } from '@/features/workspace/shell'

// Workbench 左侧活动栏（文件/搜索文件/Git/思维链）图标顺序的显示偏好持久化。
// 惯例对齐 workspaceExplorerOrder.ts / useWorkbenchLayout.ts：localStorage JSON +
// 读取校验，坏数据回退默认顺序。该栏是应用级 UI，顺序全局共享、不按 Mission 隔离。
const STORAGE_KEY = 'zhiyi.workbench.activity.order.v1'

export const WORKBENCH_ACTIVITY_ORDER: WorkbenchSidebar[] = ['files', 'search', 'git', 'thought']

const isWorkbenchSidebar = (value: unknown): value is WorkbenchSidebar => (
  typeof value === 'string' && (WORKBENCH_ACTIVITY_ORDER as string[]).includes(value)
)

/** 读取持久化顺序，返回收敛到已知视图 id 的数组；无有效数据时返回 undefined。 */
export const readWorkbenchActivityOrder = (): WorkbenchSidebar[] | undefined => {
  if (typeof window === 'undefined') return undefined
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || 'null')
    if (!parsed || typeof parsed !== 'object') return undefined
    const raw = (parsed as Record<string, unknown>).activityOrder
    if (!Array.isArray(raw)) return undefined
    const known = raw.filter(isWorkbenchSidebar)
    return known.length === WORKBENCH_ACTIVITY_ORDER.length && new Set(known).size === known.length
      ? known
      : undefined
  } catch {
    return undefined
  }
}

/** 把持久化顺序收敛为完整可用顺序：剔未知项、缺失项按默认顺序补尾。 */
export const applyWorkbenchActivityOrder = (order: WorkbenchSidebar[] | undefined): WorkbenchSidebar[] => {
  if (!order || !order.length) return [...WORKBENCH_ACTIVITY_ORDER]
  const known = order.filter(isWorkbenchSidebar)
  const missing = WORKBENCH_ACTIVITY_ORDER.filter(id => !known.includes(id))
  return [...known, ...missing]
}

export const writeWorkbenchActivityOrder = (order: WorkbenchSidebar[]) => {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ activityOrder: order }))
}
