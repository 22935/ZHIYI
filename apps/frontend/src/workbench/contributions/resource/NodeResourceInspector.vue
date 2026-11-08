<template>
  <InspectorSection title="Resource" :badge="binding ? tierLabel(binding.deploymentTier) : '未观测'">
    <div class="resource-overview">
      <div class="resource-overview__row">
        <span>智能体</span>
        <code :title="binding?.agentId || undefined">{{ binding?.agentId || '未观测' }}</code>
      </div>
      <div class="resource-overview__row">
        <span>模型</span>
        <code :title="binding?.modelId || undefined">{{ modelLabel }}</code>
      </div>
      <div class="resource-overview__row">
        <span>健康状态</span>
        <strong class="resource-health" :class="`is-${resourceHealth}`">{{ binding ? inspectorValue(healthLabel(resourceHealth)) : '暂未获取' }}</strong>
      </div>
    </div>
    <button
      type="button"
      class="inspector-disclosure"
      :aria-expanded="detailsExpanded"
      @click="detailsExpanded = !detailsExpanded"
    >
      <span>资源技术详情</span>
      <span class="inspector-disclosure__action">{{ detailsExpanded ? '收起' : '展开' }}</span>
    </button>
    <div v-if="detailsExpanded" class="resource-details">
      <InspectorPropertyList :rows="[
        { label: 'Resource ID', value: binding?.resourceId, code: true },
        { label: 'Attempt ID', value: binding?.attemptId || graphNode.attemptId, code: true },
        { label: 'Deployment Tier', value: tierLabel(binding?.deploymentTier) }
      ]" />
    </div>
    <p v-if="!binding" class="resource-empty">当前快照没有此节点的资源使用记录。</p>
  </InspectorSection>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ResourceBindingObservation, ResourceObservation, WorkspaceGraphNode } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import { inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import { healthLabel, tierLabel } from '@/utils/resourceFormat'

const props = defineProps<{
  graphNode: WorkspaceGraphNode
  resourceObservation: ResourceObservation | null
}>()
const detailsExpanded = ref(false)

const binding = computed<ResourceBindingObservation | null>(() => {
  const observation = props.resourceObservation
  if (!observation) return null
  return observation.bindings.find(item => (
    (props.graphNode.attemptId && item.attemptId === props.graphNode.attemptId)
    || (item.acgNodeId === props.graphNode.acgNodeId && item.semanticTaskKey === props.graphNode.semanticTaskKey)
  )) || null
})

const resourceHealth = computed(() => {
  const resourceId = binding.value?.resourceId
  return props.resourceObservation?.items.find(item => item.profile.resourceId === resourceId)?.snapshot.healthStatus || 'unknown'
})
const modelLabel = computed(() => binding.value?.modelId === 'runtime-default' ? '运行时默认模型' : (binding.value?.modelId || '未观测'))

</script>

<style scoped>
.resource-overview { display: grid; gap: 8px; padding: 1px 0 3px; }
.resource-overview__row { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 12px; align-items: center; min-width: 0; }
.resource-overview__row > span { color: var(--wb-text-muted); font-size: 12px; }
.resource-overview__row code { min-width: 0; overflow: hidden; color: var(--wb-text); font: 11px/1.4 var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.resource-health { font-size: 11px; font-weight: 500; }
.resource-health.is-online { color: var(--wb-success); }
.resource-health.is-degraded, .resource-health.is-offline { color: var(--wb-warning); }
.resource-health.is-unknown { color: var(--wb-text-muted); }
.inspector-disclosure { display: flex; align-items: center; justify-content: space-between; width: 100%; margin-top: 10px; padding: 8px 0; border: 0; border-top: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: transparent; cursor: pointer; font-size: 11px; text-align: left; }
.inspector-disclosure:hover { color: var(--wb-text); }
.inspector-disclosure__action { color: var(--wb-accent); font: 10px var(--font-mono, monospace); }
.resource-details { padding-top: 1px; }
.resource-empty { margin: 10px 0 0; color: var(--text-muted); font-size: 11px; line-height: 1.5; }
.resource-reasons { display: flex; gap: 5px; margin-top: 11px; flex-wrap: wrap; }
.resource-reasons strong { width: 100%; color: var(--text-muted); font-size: 10px; font-weight: 500; }
.resource-reasons span { padding: 3px 6px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); color: var(--wb-text-muted); font-size: 10px; }
</style>
