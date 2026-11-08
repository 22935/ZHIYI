<template>
  <div class="inspector-section-stack">
    <InspectorSection title="节点状态" :badge="graphNode.status || '未观测'">
      <div class="inspector-status">
        <span class="inspector-status__dot" :class="`is-${graphNode.status || 'unobserved'}`" aria-hidden="true"></span>
        <strong>{{ inspectorValue(graphNode.status) }}</strong>
      </div>
      <InspectorPropertyList :rows="[
        { label: 'title', value: graphNode.name },
        { label: 'artifacts', value: graphNode.artifactCount || 0 },
        { label: 'attemptId', value: graphNode.attemptId, code: true }
      ]" />
    </InspectorSection>

    <InspectorSection title="工程身份" :badge="graphNode.identityQuality || 'unproven'">
      <InspectorPropertyList :rows="[
        { label: 'semanticTaskKey', value: graphNode.semanticTaskKey, code: true },
        { label: 'acgNodeId', value: graphNode.acgNodeId, code: true },
        { label: 'taskId', value: graphNode.taskId, code: true }
      ]" />
    </InspectorSection>
  </div>
</template>

<script setup lang="ts">
import type { WorkspaceGraphNode } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import { inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import InspectorSection from '@/components/workbench/InspectorSection.vue'

defineProps<{
  graphNode: WorkspaceGraphNode
}>()
</script>

<style scoped>
.inspector-section-stack { display: contents; }
.inspector-status { display: flex; align-items: center; gap: 8px; min-height: 30px; margin-bottom: 4px; color: var(--wb-text); }
.inspector-status strong { font-size: 13px; line-height: 1.6; font-weight: 650; }
.inspector-status__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--wb-text-muted); }
.inspector-status__dot.is-completed,
.inspector-status__dot.is-succeeded { background: var(--wb-success); }
.inspector-status__dot.is-failed { background: var(--wb-danger); }
.inspector-status__dot.is-running { background: var(--wb-accent); }
</style>
