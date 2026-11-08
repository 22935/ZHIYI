<template>
  <InspectorSection title="Artifacts" :badge="String(artifacts)">
    <div class="artifact-summary" :class="{ 'is-empty': !artifacts }">
      <div class="artifact-summary__count">
        <strong>{{ artifacts }}</strong>
        <span>个产物</span>
      </div>
      <div class="artifact-summary__message">
        <strong>{{ artifacts ? '已生成任务产物' : '暂无任务产物' }}</strong>
        <span>{{ artifacts ? '在“相关文件”中打开并查看内容' : '当前快照没有可查看的产物' }}</span>
      </div>
    </div>
  </InspectorSection>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WorkspaceEntry } from '@/services/api/agentos'
import InspectorSection from '@/components/workbench/InspectorSection.vue'

const props = defineProps<{ entry: WorkspaceEntry }>()

const artifacts = computed(() => props.entry.artifactCount ?? 0)
</script>

<style scoped>
.artifact-summary { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 12px; align-items: center; padding: 10px; border: 1px solid color-mix(in srgb, var(--wb-accent) 18%, var(--wb-border-soft)); border-radius: var(--wb-radius-sm); background: color-mix(in srgb, var(--wb-accent-soft) 38%, var(--wb-surface-inset)); }
.artifact-summary.is-empty { border-color: var(--wb-border-soft); background: var(--wb-surface-inset); }
.artifact-summary__count { display: grid; justify-items: center; min-width: 48px; padding-right: 12px; border-right: 1px solid var(--wb-border-soft); }
.artifact-summary__count strong { color: var(--wb-text); font: 600 20px/1 var(--font-mono, monospace); font-variant-numeric: tabular-nums; }
.artifact-summary__count span { margin-top: 4px; color: var(--wb-text-muted); font-size: 9px; }
.artifact-summary__message { display: grid; gap: 3px; min-width: 0; }
.artifact-summary__message strong { color: var(--wb-text-secondary); font-size: 11px; font-weight: 600; }
.artifact-summary__message span { color: var(--wb-text-muted); font-size: 10px; line-height: 1.45; }
</style>
