<template>
  <div class="workspace-switch" role="tablist" aria-label="工作区模式" :aria-busy="pending">
    <button
      v-for="item in surfaces"
      :key="item.id"
      class="workspace-switch-btn"
      :class="{ active: active === item.id }"
      type="button"
      role="tab"
      :aria-selected="active === item.id"
      :disabled="pending"
      @click="emit('select', item.id)"
      @keydown="navigate($event, item.id)"
    >
      <el-icon aria-hidden="true"><component :is="item.icon" /></el-icon>
      <span>{{ item.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import { ChatDotRound, Monitor } from '@element-plus/icons-vue'
import type { WorkspaceSurface } from '@/features/workspace/shell'

defineProps<{ active: WorkspaceSurface; pending?: boolean }>()
const emit = defineEmits<{ select: [surface: WorkspaceSurface] }>()
const surfaces = [
  { id: 'workbench' as const, label: 'Workbench', icon: Monitor },
  { id: 'oscode' as const, label: 'OScode', icon: ChatDotRound }
]
function navigate(event: KeyboardEvent, current: WorkspaceSurface) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return
  event.preventDefault()
  const target = event.key === 'Home' ? 'workbench' : event.key === 'End' ? 'oscode'
    : current === 'workbench' ? 'oscode' : 'workbench'
  const index = target === 'workbench' ? 0 : 1
  ;(event.currentTarget as HTMLElement).parentElement?.querySelectorAll<HTMLButtonElement>('button')[index]?.focus()
  emit('select', target)
}
</script>

<style scoped>
.workspace-switch { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); flex-shrink: 0; gap: 4px; padding: 4px; margin: 0 0 12px; border-radius: 10px; background: var(--wb-surface-shell); }
.workspace-switch-btn { display: flex; align-items: center; justify-content: center; gap: 7px; min-width: 0; min-height: 34px; padding: 6px 8px; border: 1px solid transparent; border-radius: 8px; background: transparent; color: var(--text-secondary); font: 600 12px/1.4 var(--font-sans); cursor: pointer; transition: color 140ms ease, background 140ms ease; }
.workspace-switch-btn.active { background: var(--bg-active, var(--wb-hover)); color: var(--text-primary); border-color: var(--wb-border-soft); box-shadow: 0 2px 5px rgb(0 0 0 / 12%); }
.workspace-switch-btn:hover { color: var(--text-primary); background: var(--wb-hover); }
.workspace-switch-btn:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.workspace-switch-btn:disabled { cursor: progress; opacity: .65; }
.workspace-switch-btn .el-icon { font-size: 14px; }
@media (prefers-reduced-motion: reduce) { .workspace-switch-btn { transition: none; } }
</style>
