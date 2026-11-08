<template>
  <div
    class="workbench-resize-handle"
    :class="`workbench-resize-handle--${side}`"
    role="separator"
    aria-orientation="vertical"
    :aria-label="ariaLabel"
    :aria-valuemin="min"
    :aria-valuemax="max"
    :aria-valuenow="value"
    :title="`${ariaLabel}，双击恢复默认`"
    tabindex="0"
    @pointerdown="emit('resize-start', $event)"
    @keydown="emit('resize-keydown', $event)"
    @dblclick="emit('reset')"
  ></div>
</template>

<script setup lang="ts">
import type { WorkbenchPaneSide } from '@/composables/useWorkbenchLayout'

defineProps<{
  side: WorkbenchPaneSide
  value: number
  min: number
  max: number
  ariaLabel: string
}>()

const emit = defineEmits<{
  'resize-start': [event: PointerEvent]
  'resize-keydown': [event: KeyboardEvent]
  reset: []
}>()
</script>

<style scoped>
/* 占据真实宽度而非负 margin 悬浮：悬浮式会盖住两侧窗格贴边滚动条（任务文档 padding 为 0），
   用户想拖滚动条却拖到分隔条。改为 6px 实体槽位，滚动条回到窗格内部可抓取。 */
.workbench-resize-handle {
  position: relative;
  z-index: 2;
  flex: 0 0 6px;
  width: 6px;
  min-width: 6px;
  align-self: stretch;
  cursor: col-resize;
  touch-action: none;
  outline: none;
}

.workbench-resize-handle::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 50%;
  width: 1px;
  transform: translateX(-50%);
  background: transparent;
  opacity: 0;
  transition: background-color 160ms ease, box-shadow 160ms ease, opacity 160ms ease;
}

.workbench-resize-handle:hover::after,
.workbench-resize-handle:focus-visible::after {
  background: var(--primary-color);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 18%, transparent);
  opacity: .9;
}

.workbench-resize-handle:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 42%, transparent);
  outline-offset: -1px;
}

.workbench-layout.is-resizing .workbench-resize-handle::after {
  background: var(--primary-color);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 24%, transparent);
  opacity: 1;
}
</style>
