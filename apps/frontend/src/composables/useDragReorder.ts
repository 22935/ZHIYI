import { ref, type Ref } from 'vue'

export type DragReorderOrientation = 'vertical' | 'horizontal'
export type DragReorderGhost = 'default' | 'none'

interface ActiveDrag {
  group: string
  index: number
}

// dragover/drop 会派发到别的组件实例渲染的元素上（比如把任务行拖过其他分区头），
// 活跃拖拽必须放在模块级，让所有 useDragReorder 实例共享同一份「谁在拖」的事实。
let activeDrag: ActiveDrag | null = null

// ghost:'none' 共用的 1×1 透明锚点：setDragImage 指向它即等于隐藏浏览器默认的半透明快照。
let ghostAnchor: HTMLElement | null = null

const hideNativeGhost = (event: DragEvent) => {
  if (!event.dataTransfer) return
  if (!ghostAnchor) {
    ghostAnchor = document.createElement('div')
    ghostAnchor.style.cssText = 'position:fixed;top:-100px;left:-100px;width:1px;height:1px;opacity:0;pointer-events:none;'
    document.body.appendChild(ghostAnchor)
  }
  event.dataTransfer.setDragImage(ghostAnchor, 0, 0)
}

export interface DragReorderOptions {
  /** 列表方向：vertical 按纵向中点判定前后，horizontal 按横向中点。 */
  orientation?: DragReorderOrientation
  /** 列表身份：拖拽只在同 group 的条目之间生效，跨 group 的 dragover 不响应。 */
  group: string
  /**
   * 拖拽投影：default=浏览器默认快照（适合标签页/文件行）；none=隐藏快照，
   * 只留源项淡化 + 落点指示线（适合活动栏小图标，避免快照叠在真实图标上）。
   */
  ghost?: DragReorderGhost
  /**
   * 重排回调。from/to 都是「移除源项之后」的坐标：
   * to === from 表示原位（调用方应视为 no-op），to > from 表示向后移一格以上。
   */
  onReorder: (from: number, to: number) => void
}

export interface DragReorderState {
  draggingIndex: Ref<number | null>
  /** drop 落点的「插入前」坐标（0..items.length）。 */
  dropIndex: Ref<number | null>
  /** 绑定到可拖条目上的属性集（draggable + 拖拽事件处理器）。 */
  itemProps: (index: number) => Record<string, unknown>
  /** 组件卸载/KeepAlive 失活时兜底清态。 */
  resetDrag: () => void
}

export const useDragReorder = (options: DragReorderOptions): DragReorderState => {
  const { group, onReorder } = options
  const orientation: DragReorderOrientation = options.orientation || 'vertical'
  const draggingIndex = ref<number | null>(null)
  const dropIndex = ref<number | null>(null)

  const clearDropMarker = () => {
    if (activeDrag && activeDrag.group !== group) return
    dropIndex.value = null
  }

  const clearDrag = () => {
    if (activeDrag && activeDrag.group === group) activeDrag = null
    draggingIndex.value = null
    dropIndex.value = null
  }

  const onDragstart = (event: DragEvent) => {
    // 序号统一从 data-drag-index 属性回读：itemProps 只生成一份处理器，
    // 不给每个条目都闭包一个新函数，dragover 也能走同一条回读路径。
    const index = readIndex(event.currentTarget)
    if (index === null) return
    activeDrag = { group, index }
    draggingIndex.value = index
    dropIndex.value = null
    if (event.dataTransfer) {
      // Chromium 不强制 setData，但补上是跨浏览器（Firefox）能拖起来的卫生习惯。
      event.dataTransfer.effectAllowed = 'move'
      event.dataTransfer.setData('text/plain', String(index))
    }
    if (options.ghost === 'none') hideNativeGhost(event)
  }

  const onDragover = (event: DragEvent) => {
    if (!activeDrag || activeDrag.group !== group) return
    const index = readIndex(event.currentTarget)
    if (index === null || index === activeDrag.index) return
    event.preventDefault()
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'move'
    const target = event.currentTarget as HTMLElement
    const rect = target.getBoundingClientRect()
    const size = orientation === 'horizontal' ? rect.width : rect.height
    const position = orientation === 'horizontal' ? event.clientX - rect.left : event.clientY - rect.top
    dropIndex.value = position >= size / 2 ? index + 1 : index
  }

  const onDrop = (event: DragEvent) => {
    if (!activeDrag || activeDrag.group !== group) return
    event.preventDefault()
    const from = activeDrag.index
    const before = dropIndex.value
    clearDrag()
    if (before === null) return
    // 「插入前」坐标换算成移除源项后的坐标；落在自己原位则为 no-op。
    const to = before > from ? before - 1 : before
    if (to === from) return
    onReorder(from, to)
  }

  const onDragleave = () => clearDropMarker()
  const onDragend = () => clearDrag()

  const itemProps = (index: number): Record<string, unknown> => ({
    draggable: 'true',
    'data-drag-index': String(index),
    onDragstart,
    onDragover,
    onDrop,
    onDragleave,
    onDragend
  })

  const resetDrag = () => {
    if (activeDrag && activeDrag.group === group) activeDrag = null
    draggingIndex.value = null
    dropIndex.value = null
  }

  return { draggingIndex, dropIndex, itemProps, resetDrag }
}

const readIndex = (target: EventTarget | null): number | null => {
  const raw = (target as HTMLElement | null)?.getAttribute?.('data-drag-index')
  if (raw === null || raw === undefined) return null
  const index = Number(raw)
  return Number.isInteger(index) && index >= 0 ? index : null
}

/** 模板侧的落点指示判定：条目上缘 / 下缘是否应显示指示线。 */
export const isDropAbove = (dropIndex: Ref<number | null>, index: number) => dropIndex.value === index
export const isDropBelow = (dropIndex: Ref<number | null>, index: number) => dropIndex.value === index + 1
