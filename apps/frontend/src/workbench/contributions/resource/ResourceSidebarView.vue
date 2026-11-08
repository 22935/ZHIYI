<template>
  <div class="sidebar-view-stack">
    <InspectorSection v-if="selectedBinding" title="当前节点的执行资源" :badge="String(inspectorValue(healthLabel(selectedHealth)))">
      <InspectorPropertyList :rows="[
        { label: '部署位置', value: tierLabel(selectedBinding.deploymentTier) },
        { label: '模型', value: selectedBinding.modelId === 'runtime-default' ? '运行时默认模型' : selectedBinding.modelId },
        { label: '健康状态', value: healthLabel(selectedHealth) }
      ]" />
      <InspectorDetails title="资源绑定技术详情">
        <InspectorPropertyList :rows="[{ label: 'resourceId', value: selectedBinding.resourceId, code: true }, { label: 'agentId', value: selectedBinding.agentId, code: true }, { label: '执行编号', value: selectedBinding.attemptId, code: true }]" />
      </InspectorDetails>
    </InspectorSection>
    <InspectorSection v-else title="运行资源" :badge="resourceObservation ? '已获取统计' : '暂未获取'">
      <div class="sidebar-metrics" aria-label="资源绑定统计">
        <div><strong>{{ resourceObservation ? boundResourceCount : '—' }}</strong><span>执行资源</span></div>
        <div><strong>{{ resourceObservation ? agentCount : '—' }}</strong><span>智能体</span></div>
        <div><strong>{{ resourceObservation ? modelCount : '—' }}</strong><span>模型配置</span></div>
      </div>
      <p class="sidebar-empty">展示本次运行已登记的执行资源及其健康状态。</p>
      <div v-if="boundResources.length" class="resource-list">
        <div v-for="(resource, index) in boundResources" :key="resource.resourceId" class="resource-list__row">
          <div><strong>{{ resource.resourceId === 'runtime:embedded-agents' ? '内置执行资源' : '执行资源 ' + (index + 1) }}</strong><span>{{ tierLabel(resource.deploymentTier) }} · {{ inspectorValue(resource.modelId) }}</span></div>
          <span>{{ inspectorValue(healthLabel(resource.health)) }}</span>
        </div>
      </div>
      <InspectorDetails v-if="resourceObservation" title="资源绑定详情" :count="resourceObservation.bindings.length">
        <InspectorPropertyList :rows="[{ label: 'bound attempts', value: resourceObservation.bindings.length }, { label: 'source', value: resourceObservation.source }]" />
        <InspectorPropertyList v-for="resource in boundResources" :key="resource.resourceId" :rows="[{ label: 'resourceId', value: resource.resourceId, code: true }, { label: 'agentId', value: resource.agentId, code: true }, { label: 'modelId', value: resource.modelId, code: true }]" />
      </InspectorDetails>
      <InspectorDetails v-if="resourceObservation?.failoverEvents?.length" title="资源切换记录" :count="resourceObservation.failoverEvents.length">
        <p v-for="event in resourceObservation.failoverEvents" :key="event.eventId">{{ event.failedResources.map(item => item.resourceId).join('、') }} → {{ event.retryStepIds.join('、') || '原步骤' }}</p>
      </InspectorDetails>
      <p v-if="!boundResources.length" class="sidebar-empty">{{ resourceObservation ? '当前快照没有记录资源绑定。' : '资源数据尚未获取。' }}</p>
    </InspectorSection>
    <RunUsagePanel :run-id="context.runId" :run-status="context.runStatus" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ResourceBindingObservation, ResourceObservation } from '@/services/api/agentos'
import RunUsagePanel from './RunUsagePanel.vue'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import InspectorDetails from '@/components/workbench/InspectorDetails.vue'
import { inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import type { WorkbenchInspectorContext } from '@/workbench/types'
import { healthLabel, tierLabel } from '@/utils/resourceFormat'

const props = defineProps<{
  context: WorkbenchInspectorContext
  resourceObservation: ResourceObservation | null
}>()

const selectedBinding = computed<ResourceBindingObservation | null>(() => {
  const observation = props.resourceObservation
  const node = props.context.graphNode
  if (!observation || !node) return null
  return observation.bindings.find(item => (
    (node.attemptId && item.attemptId === node.attemptId)
    || (item.acgNodeId === node.acgNodeId && item.semanticTaskKey === node.semanticTaskKey)
  )) || null
})

const selectedHealth = computed(() => {
  const resourceId = selectedBinding.value?.resourceId
  return props.resourceObservation?.items.find(item => item.profile.resourceId === resourceId)?.snapshot.healthStatus || 'unknown'
})

const boundResources = computed(() => {
  const observation = props.resourceObservation
  if (!observation) return []
  const grouped = new Map<string, { resourceId: string; agentId: string; modelId: string; health: string; deploymentTier: string | null }>()
  for (const binding of observation.bindings) {
    if (grouped.has(binding.resourceId)) continue
    const profile = observation.items.find(item => item.profile.resourceId === binding.resourceId)
    grouped.set(binding.resourceId, {
      resourceId: binding.resourceId,
      agentId: binding.agentId,
      modelId: binding.modelId,
      health: profile?.snapshot.healthStatus || 'unknown',
      deploymentTier: binding.deploymentTier || profile?.profile.deploymentTier || null
    })
  }
  return [...grouped.values()]
})

const boundResourceCount = computed(() => boundResources.value.length)
const agentCount = computed(() => new Set((props.resourceObservation?.bindings || []).map(item => item.agentId)).size)
const modelCount = computed(() => new Set((props.resourceObservation?.bindings || []).map(item => item.modelId)).size)
</script>

<style scoped>
.sidebar-view-stack { display: contents; }
.sidebar-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 8px; }
.sidebar-metrics > div { display: grid; gap: 2px; min-width: 0; }
.sidebar-metrics strong { color: var(--wb-text); font: 16px var(--font-mono, monospace); }
.sidebar-metrics span { color: var(--wb-text-muted); font-size: 12px; }
.resource-list { display: grid; gap: 8px; margin-top: 10px; }
.resource-list__row { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding-top: 8px; border-top: 1px solid color-mix(in srgb, var(--wb-border-soft) 70%, transparent); }
.resource-list__row > div { display: grid; gap: 3px; min-width: 0; }
.resource-list__row strong { overflow: hidden; color: var(--wb-text); font: 600 13px var(--font-sans, sans-serif); text-overflow: ellipsis; white-space: nowrap; }
.resource-list__row div span, .resource-list__row > span { color: var(--wb-text-muted); font-size: 12px; }
.resource-list__row > span { flex: 0 0 auto; }
.resource-switch-list { display: grid; gap: 5px; margin-top: 10px; padding-top: 8px; border-top: 1px solid color-mix(in srgb, var(--wb-border-soft) 70%, transparent); color: var(--wb-text-muted); font-size: 12px; }
.resource-switch-list span { color: var(--wb-text-secondary); font: 9px var(--font-mono, monospace); }
.sidebar-empty { margin: 10px 0 0; color: var(--wb-text-muted); font-size: 12px; line-height: 1.5; }
</style>
