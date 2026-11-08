<template>
  <div class="inspector-frame">
    <header class="inspector-frame__header">
      <div class="inspector-frame__title">
        <span>详情</span>
        <strong>{{ title }}</strong>
      </div>
      <div class="inspector-frame__meta">
        <slot name="header-meta" />
        <div class="inspector-frame__actions">
          <span v-if="historical" class="inspector-frame__badge">历史记录</span>
          <InspectorHeaderActions
            :fullscreen="fullscreen"
            @toggle-fullscreen="emit('toggleFullscreen')"
            @close="emit('close')"
          />
        </div>
      </div>
    </header>
    <div class="inspector-frame__body">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
import InspectorHeaderActions from './InspectorHeaderActions.vue'

defineProps<{
  title: string
  historical?: boolean
  fullscreen?: boolean
}>()

const emit = defineEmits<{
  close: []
  toggleFullscreen: []
}>()
</script>

<style scoped>
.inspector-frame { display: flex; flex-direction: column; min-width: 0; min-height: 0; height: 100%; color: var(--wb-text); background: var(--wb-surface-pane); }
.inspector-frame__header { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 16px 18px 12px; border-bottom: 0; background: var(--wb-surface-pane); }
.inspector-frame__title { flex: 1 1 auto; min-width: 0; }
.inspector-frame__meta { display: flex; flex: 1 1 100%; align-items: flex-start; justify-content: space-between; gap: 8px; min-width: 0; }
.inspector-frame__actions { display: flex; flex: 0 0 auto; align-items: flex-start; gap: 7px; }
.inspector-frame__title > span:first-child { display: block; color: var(--wb-accent); font: 10px var(--font-mono, monospace); letter-spacing: .1em; }
.inspector-frame__header strong { display: block; margin-top: 6px; overflow-wrap: anywhere; font-size: 14px; font-weight: 600; line-height: 1.6; }
.inspector-frame__badge { align-self: flex-start; padding: 3px 6px; border: 1px solid var(--wb-border); border-radius: var(--wb-radius-sm); color: var(--wb-warning); font: 10px var(--font-mono, monospace); }
.inspector-frame__body { container-type: inline-size; min-width: 0; min-height: 0; overflow: auto; padding: 0 18px 24px; background: var(--wb-surface-1); scrollbar-gutter: stable; }
.inspector-frame__body :deep(.inspector-section + .inspector-section) { border-top: 1px solid var(--wb-border-soft); }
.inspector-frame__body :deep(.inspector-section) { margin-bottom: 10px; }
.inspector-frame__body :deep(.inspector-section:last-child) { margin-bottom: 0; }
@media (max-width: 820px) {
  .inspector-frame__header { flex-wrap: wrap; }
  .inspector-frame__title { flex: 1 1 180px; }
  .inspector-frame__meta { flex: 1 1 100%; justify-content: space-between; }
}
</style>
