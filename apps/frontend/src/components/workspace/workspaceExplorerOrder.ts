import type { WorkspaceEntry } from '@/services/api/agentos'

// Explorer 拖拽排序的显示偏好持久化。惯例对齐 useWorkbenchLayout.ts：
// localStorage JSON + 读取时逐字段类型校验，坏数据一律回退默认而不是报错。
const STORAGE_KEY = 'zhiyi.mission.workspace.explorer.order.v1'

export const EXPLORER_SECTION_ORDER = ['overview', 'runs', 'steps', 'output']

export interface ExplorerOrderPersistence {
  /** 分区显示顺序（全局偏好，跨 Mission 共享）。 */
  sectionOrder?: string[]
  /** steps 分区条目视觉顺序快照，key 为 `${missionId}|${runId || 'none'}`。 */
  stepsOrders?: Record<string, string[]>
}

export const explorerOrderStorageKey = STORAGE_KEY

export const stepsOrderKey = (missionId: string, runId: string | null): string => (
  `${missionId}|${runId || 'none'}`
)

const asStringArray = (value: unknown): string[] | undefined => {
  if (!Array.isArray(value)) return undefined
  const items = value.filter((item): item is string => typeof item === 'string')
  return items.length === value.length && items.length > 0 ? items : undefined
}

export const readExplorerOrderPersistence = (): ExplorerOrderPersistence => {
  if (typeof window === 'undefined') return {}
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}')
    if (!parsed || typeof parsed !== 'object') return {}
    const record = parsed as Record<string, unknown>
    const stepsOrdersRecord = record.stepsOrders
    const stepsOrders = stepsOrdersRecord && typeof stepsOrdersRecord === 'object'
      ? Object.fromEntries(
          Object.entries(stepsOrdersRecord as Record<string, unknown>)
            .map(([key, value]) => [key, asStringArray(value)])
            .filter(([, value]) => Boolean(value))
        )
      : undefined
    return {
      sectionOrder: asStringArray(record.sectionOrder),
      stepsOrders: stepsOrders as Record<string, string[]> | undefined
    }
  } catch {
    return {}
  }
}

export const writeExplorerOrderPersistence = (patch: ExplorerOrderPersistence) => {
  if (typeof window === 'undefined') return
  const current = readExplorerOrderPersistence()
  const next: ExplorerOrderPersistence = {
    sectionOrder: patch.sectionOrder ?? current.sectionOrder,
    stepsOrders: patch.stepsOrders
      ? { ...(current.stepsOrders || {}), ...patch.stepsOrders }
      : current.stepsOrders
  }
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}

/** 把持久化的分区顺序收敛到已知分区上：去重、剔未知组、缺失组按默认顺序补尾。 */
export const applySectionOrder = (order: string[] | undefined): string[] => {
  if (!order || !order.length) return [...EXPLORER_SECTION_ORDER]
  const known = order.filter(group => EXPLORER_SECTION_ORDER.includes(group))
  const missing = EXPLORER_SECTION_ORDER.filter(group => !known.includes(group))
  return [...known, ...missing]
}

/**
 * steps 分区视觉排序：快照里还存在的条目按快照顺序在前，其余条目
 * （新到达的条目等）按 displayOrder 追加在后，保持现有排序语义不变。
 */
export const applyStepsOrder = (items: WorkspaceEntry[], snapshot: string[] | undefined): WorkspaceEntry[] => {
  if (!snapshot || !snapshot.length) return items
  const byId = new Map(items.map(item => [item.entryId, item]))
  const ordered = snapshot.map(entryId => byId.get(entryId)).filter((item): item is WorkspaceEntry => Boolean(item))
  const seen = new Set(ordered.map(item => item.entryId))
  const remaining = items.filter(item => !seen.has(item.entryId))
  return [...ordered, ...remaining]
}

/** 重排 steps 条目并生成要持久化的快照：只保留当前还存在的 entryId。 */
export const reorderStepsItems = (items: WorkspaceEntry[], from: number, to: number): { items: WorkspaceEntry[]; snapshot: string[] } => {
  const next = [...items]
  const [moved] = next.splice(from, 1)
  if (!moved) return { items, snapshot: items.map(item => item.entryId) }
  next.splice(to, 0, moved)
  return { items: next, snapshot: next.map(item => item.entryId) }
}
