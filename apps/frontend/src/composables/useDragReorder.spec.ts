import { describe, expect, it, vi } from 'vitest'
import { useDragReorder } from './useDragReorder'

const makeTarget = (index: number, rect: { left?: number; top?: number; width?: number; height?: number } = {}) => {
  const { left = 0, top = 0, width = 100, height = 40 } = rect
  return {
    getAttribute: (name: string) => (name === 'data-drag-index' ? String(index) : null),
    getBoundingClientRect: () => ({ left, top, width, height, right: left + width, bottom: top + height, x: left, y: top, toJSON: () => ({}) })
  } as unknown as HTMLElement
}

const makeEvent = (currentTarget: HTMLElement, point: { x?: number; y?: number } = {}) => {
  const dataTransfer = { effectAllowed: '', dropEffect: '', setData: vi.fn() }
  const raw = { currentTarget, clientX: point.x ?? 0, clientY: point.y ?? 0, dataTransfer, preventDefault: vi.fn() }
  return { event: raw as unknown as DragEvent, dataTransfer, preventDefault: raw.preventDefault }
}

const vertical = (onReorder = vi.fn()) => useDragReorder({ orientation: 'vertical', group: 'list-a', onReorder })

describe('useDragReorder', () => {
  it('declares draggable + index marker and the drag lifecycle handlers on itemProps', () => {
    const props = vertical().itemProps(3)
    expect(props.draggable).toBe('true')
    expect(props['data-drag-index']).toBe('3')
    expect(props.onDragstart).toBeInstanceOf(Function)
    expect(props.onDragover).toBeInstanceOf(Function)
    expect(props.onDrop).toBeInstanceOf(Function)
    expect(props.onDragend).toBeInstanceOf(Function)
  })

  it('records the drag start with the move effect and the source index', () => {
    const drag = vertical()
    const { event, dataTransfer } = makeEvent(makeTarget(1))
    drag.itemProps(1).onDragstart(event)
    expect(drag.draggingIndex.value).toBe(1)
    expect(dataTransfer.effectAllowed).toBe('move')
    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', '1')
  })

  it('marks below-midpoint dragover as insert-after and lands (from, to) in post-removal coordinates', () => {
    const onReorder = vi.fn()
    const drag = vertical(onReorder)
    const props = drag.itemProps(0)
    props.onDragstart(makeEvent(makeTarget(0)).event)
    // 目标行高 40，y=30 越过中点 → 插到它后面（before=3）→ 移除源项后 to=2。
    const over = makeEvent(makeTarget(2), { y: 30 })
    props.onDragover(over.event)
    expect(drag.dropIndex.value).toBe(3)
    expect(over.preventDefault).toHaveBeenCalled()
    props.onDrop(makeEvent(makeTarget(2), { y: 30 }).event)
    expect(onReorder).toHaveBeenCalledTimes(1)
    expect(onReorder).toHaveBeenCalledWith(0, 2)
    expect(drag.draggingIndex.value).toBeNull()
    expect(drag.dropIndex.value).toBeNull()
  })

  it('treats above-midpoint drops past a single neighbor as a no-op', () => {
    const onReorder = vi.fn()
    const drag = vertical(onReorder)
    const props = drag.itemProps(0)
    props.onDragstart(makeEvent(makeTarget(0)).event)
    props.onDragover(makeEvent(makeTarget(1), { y: 10 }).event)
    expect(drag.dropIndex.value).toBe(1)
    props.onDrop(makeEvent(makeTarget(1)).event)
    expect(onReorder).not.toHaveBeenCalled()
  })

  it('keeps the insertion index when moving backward', () => {
    const onReorder = vi.fn()
    const drag = vertical(onReorder)
    const props = drag.itemProps(2)
    props.onDragstart(makeEvent(makeTarget(2)).event)
    props.onDragover(makeEvent(makeTarget(0), { y: 30 }).event)
    expect(drag.dropIndex.value).toBe(1)
    props.onDrop(makeEvent(makeTarget(0)).event)
    expect(onReorder).toHaveBeenCalledWith(2, 1)
  })

  it('never sets a drop marker while hovering the dragged item itself', () => {
    const onReorder = vi.fn()
    const drag = vertical(onReorder)
    const props = drag.itemProps(1)
    const { event, preventDefault } = makeEvent(makeTarget(1), { y: 30 })
    props.onDragstart(makeEvent(makeTarget(1)).event)
    props.onDragover(event)
    expect(drag.dropIndex.value).toBeNull()
    expect(preventDefault).not.toHaveBeenCalled()
    props.onDrop(makeEvent(makeTarget(1)).event)
    expect(onReorder).not.toHaveBeenCalled()
  })

  it('drops without a prior dragover is a no-op', () => {
    const onReorder = vi.fn()
    const drag = vertical(onReorder)
    const props = drag.itemProps(0)
    props.onDragstart(makeEvent(makeTarget(0)).event)
    props.onDrop(makeEvent(makeTarget(2)).event)
    expect(onReorder).not.toHaveBeenCalled()
  })

  it('ignores dragover/drop from another group and keeps its own state untouched', () => {
    const onReorderA = vi.fn()
    const onReorderB = vi.fn()
    const listA = useDragReorder({ group: 'list-a', onReorder: onReorderA })
    const listB = useDragReorder({ group: 'list-b', onReorder: onReorderB })
    listA.itemProps(0).onDragstart(makeEvent(makeTarget(0)).event)
    const over = makeEvent(makeTarget(1))
    listB.itemProps(1).onDragover(over.event)
    expect(listB.dropIndex.value).toBeNull()
    expect(over.preventDefault).not.toHaveBeenCalled()
    listB.itemProps(1).onDrop(makeEvent(makeTarget(1)).event)
    expect(onReorderB).not.toHaveBeenCalled()
    expect(onReorderA).not.toHaveBeenCalled()
  })

  it('dragend clears the in-flight drag so later drops cannot replay it', () => {
    const onReorder = vi.fn()
    const drag = vertical(onReorder)
    const props = drag.itemProps(0)
    props.onDragstart(makeEvent(makeTarget(0)).event)
    props.onDragover(makeEvent(makeTarget(2), { y: 30 }).event)
    props.onDragend(makeEvent(makeTarget(0)).event)
    expect(drag.draggingIndex.value).toBeNull()
    expect(drag.dropIndex.value).toBeNull()
    props.onDrop(makeEvent(makeTarget(2), { y: 30 }).event)
    expect(onReorder).not.toHaveBeenCalled()
  })

  it('resetDrag detaches the group from an in-flight drag', () => {
    const onReorderA = vi.fn()
    const listA = useDragReorder({ group: 'list-a', onReorder: onReorderA })
    listA.itemProps(0).onDragstart(makeEvent(makeTarget(0)).event)
    listA.resetDrag()
    expect(listA.draggingIndex.value).toBeNull()
    listA.itemProps(2).onDrop(makeEvent(makeTarget(2)).event)
    expect(onReorderA).not.toHaveBeenCalled()
  })

  it('splits on the x midpoint for horizontal lists', () => {
    const onReorder = vi.fn()
    const drag = useDragReorder({ orientation: 'horizontal', group: 'list-a', onReorder })
    const props = drag.itemProps(0)
    props.onDragstart(makeEvent(makeTarget(0)).event)
    // 目标宽 100，x=80 越过中点 → 插到后面 → 移除源项后 to=1。
    props.onDragover(makeEvent(makeTarget(1), { x: 80 }).event)
    expect(drag.dropIndex.value).toBe(2)
    props.onDrop(makeEvent(makeTarget(1), { x: 80 }).event)
    expect(onReorder).toHaveBeenCalledWith(0, 1)
  })
})
