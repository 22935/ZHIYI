<template>
  <div class="inspector-section-stack">
    <InspectorSection title="运行状态" :badge="runStatus || '未观测'">
      <div class="inspector-status">
        <span class="inspector-status__dot" :class="`is-${runStatus || 'unobserved'}`" aria-hidden="true"></span>
        <strong>{{ inspectorValue(runStatus) }}</strong>
      </div>
      <InspectorPropertyList :rows="[
        { label: 'Run', value: runId, code: true }
      ]" />
    </InspectorSection>

    <InspectorSection title="图信息" :badge="graphIdentity">
      <div class="inspector-metrics" aria-label="图统计">
        <div><strong>{{ graph?.nodes.length || graphNodes.length }}</strong><span>节点</span></div>
        <div><strong>{{ graph?.edges.length || 0 }}</strong><span>边</span></div>
        <div><strong>{{ graphVersion ?? '—' }}</strong><span>版本</span></div>
      </div>
      <InspectorPropertyList :rows="[
        { label: 'Graph ID', value: graph?.graphId || entry?.graphId, code: true },
        { label: 'Task plan', value: taskPlanVersion, code: true }
      ]" />
    </InspectorSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { GraphProjection, WorkspaceEntry, WorkspaceGraphNode } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import { inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import InspectorSection from '@/components/workbench/InspectorSection.vue'

const props = defineProps<{
  entry: WorkspaceEntry | null
  graphNodes: WorkspaceGraphNode[]
  runId: string | null
  graph: GraphProjection | null
  runStatus: string | null
}>()

const graphVersion = computed(() => {
  return props.graph?.graphVersion ?? props.entry?.graphVersion ?? null
})

const taskPlanVersion = computed(() => {
  const value = props.graph?.taskPlanVersion ?? props.entry?.metadata?.taskPlanVersion
  return value == null ? '—' : String(value)
})

const graphIdentity = computed(() => {
  if (!props.graphNodes.length) return 'unproven'
  if (props.graphNodes.every(node => node.identityQuality === 'canonical')) return 'canonical'
  if (props.graphNodes.some(node => node.identityQuality === 'legacy')) return 'mixed / legacy'
  return 'unproven'
})
</script>

<style scoped>
.inspector-section-stack { display: contents; }
.inspector-status { display: flex; align-items: center; gap: 8px; min-height: 30px; margin-bottom: 4px; color: var(--wb-text); }
.inspector-status strong { font-size: 13px; line-height: 1.6; font-weight: 650; }
.inspector-status__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--wb-text-muted); }
.inspector-status__dot.is-succeeded,
.inspector-status__dot.is-completed { background: var(--wb-success); }
.inspector-status__dot.is-failed { background: var(--wb-danger); }
.inspector-status__dot.is-running { background: var(--wb-accent); }
.inspector-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 8px; }
.inspector-metrics > div { display: grid; gap: 2px; min-width: 0; }
.inspector-metrics strong { color: var(--wb-text); font: 16px var(--font-mono, monospace); }
.inspector-metrics span { color: var(--wb-text-muted); font-size: 10px; }
</style>
