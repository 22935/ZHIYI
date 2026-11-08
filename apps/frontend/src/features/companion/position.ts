/**
 * 虚拟伙伴的拖拽位置：纯几何 + 可校验的持久化格式。
 *
 * 关键：位置以「角色自身右下角到视口右下角的距离」记录，而不是根节点左上角。
 * 根节点是 flex 列，面板在角色上方；若按 top 锚定，把角色拖到屏幕下方后
 * 展开面板会整体溢出屏幕。用 right/bottom 锚定后，面板永远向上、向左生长。
 */
export interface CompanionPosition {
  right: number
  bottom: number
}

export const COMPANION_POSITION_KEY = 'companion.position.v1'
export const AVATAR_SIZE = 76
export const EDGE_MARGIN = 12
/**
 * 角色上方为展开面板预留的空间：面板最小可用高度 240 + 头像/气泡/间距 132。
 * 拖得越靠上，可用空间越少；限制 bottom 上限比让面板溢出、或压缩到只剩一条更可预测。
 */
export const PANEL_RESERVE = 372
/** 展开后面板的宽度；根节点比收起态的角色宽得多，靠左拖拽时需要额外预留。 */
export const PANEL_WIDTH = 320

export interface Viewport {
  width: number
  height: number
}

export function clampCompanionPosition(position: CompanionPosition, viewport: Viewport): CompanionPosition {
  const maxRight = Math.max(EDGE_MARGIN, viewport.width - AVATAR_SIZE - EDGE_MARGIN)
  // 面板在角色上方展开，因此离屏幕底部不能太远，否则面板顶部会溢出视口。
  const maxBottom = Math.max(EDGE_MARGIN, viewport.height - PANEL_RESERVE)
  return {
    right: Math.min(maxRight, Math.max(EDGE_MARGIN, Math.round(position.right))),
    bottom: Math.min(maxBottom, Math.max(EDGE_MARGIN, Math.round(position.bottom)))
  }
}

/** 由「按住点相对角色的偏移」换算成 right/bottom，保证拖动时手指不跳位。 */
export function companionPositionFromDrag(
  avatarSize: { width: number; height: number },
  pointer: { x: number; y: number },
  offset: { x: number; y: number },
  viewport: Viewport
): CompanionPosition {
  const width = avatarSize.width > 0 ? avatarSize.width : AVATAR_SIZE
  const height = avatarSize.height > 0 ? avatarSize.height : AVATAR_SIZE
  const left = pointer.x - offset.x
  const top = pointer.y - offset.y
  return clampCompanionPosition({
    right: viewport.width - (left + width),
    bottom: viewport.height - (top + height)
  }, viewport)
}

/**
 * 展开时的额外约束：root 以 right 锚定，宽度由 76 变成面板的 320，
 * 拖到屏幕左侧再展开会向左溢出。展开前把角色平移到仍有完整面板空间的位置，
 * 收起态则保持自由拖拽。
 */
export function clampExpandedPosition(position: CompanionPosition, viewport: Viewport): CompanionPosition {
  const clamped = clampCompanionPosition(position, viewport)
  const maxRight = Math.max(EDGE_MARGIN, viewport.width - PANEL_WIDTH - EDGE_MARGIN)
  return { right: Math.min(clamped.right, maxRight), bottom: clamped.bottom }
}

export function parseCompanionPosition(raw: unknown): CompanionPosition | null {
  if (!raw || typeof raw !== 'object') return null
  const data = raw as Record<string, unknown>
  if (typeof data.right !== 'number' || typeof data.bottom !== 'number') return null
  if (!Number.isFinite(data.right) || !Number.isFinite(data.bottom)) return null
  return { right: data.right, bottom: data.bottom }
}

export function loadCompanionPosition(
  storage: Pick<Storage, 'getItem'> | null
): CompanionPosition | null {
  if (!storage) return null
  try {
    const raw = storage.getItem(COMPANION_POSITION_KEY)
    return raw ? parseCompanionPosition(JSON.parse(raw)) : null
  } catch {
    return null
  }
}
