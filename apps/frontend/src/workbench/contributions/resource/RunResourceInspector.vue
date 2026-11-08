<template>
  <InspectorSection title="Resource" :badge="resourceObservation ? 'runtime observation' : 'not observed'">
    <InspectorPropertyList :rows="[
      { label: 'runId', value: resourceObservation?.runId || runId, code: true },
      { label: 'attempts', value: resourceObservation?.attemptCount ?? '未观测' },
      { label: 'bound attempts', value: resourceObservation ? resourceObservation.bindings.length : '未观测' },
      { label: 'source', value: resourceObservation?.source || '未观测' }
    ]" />

    <div v-if="resourceObservation?.bindings.length" class="resource-binding-list">
      <article v-for="resource in boundResources" :key="resource.resourceId" class="resource-binding-row">
        <div class="resource-binding-row__heading">
          <strong>{{ resource.resourceId }}</strong>
          <span>{{ tierLabel(resource.deploymentTier) }} · {{ inspectorValue(healthLabel(resource.health)) }}</span>
        </div>
        <div class="resource-binding-row__meta">
          <span>智能体 {{ resource.agentId }}</span>
          <span>模型 {{ resource.modelId }}</span>
          <span>{{ resource.attemptCount }} 次执行</span>
          <span>延迟 {{ formatMetric(resource.latencyMs, 'ms') }}</span>
        </div>
      </article>
    </div>
    <div v-if="resourceObservation?.failoverEvents?.length" class="resource-failover-list" aria-label="端边云切换记录">
      <strong>端边云切换记录</strong>
      <article v-for="event in resourceObservation.failoverEvents" :key="event.eventId" class="resource-failover-row">
        <span>{{ formatDate(event.timestamp) }}</span>
        <p>{{ failoverSummary(event) }}</p>
      </article>
    </div>
    <p v-if="!resourceObservation?.bindings.length" class="resource-empty">{{ resourceObservation ? '当前快照没有资源绑定记录。' : '资源数据尚未获取。' }}</p>
  </InspectorSection>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ResourceObservation } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import { inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import { failoverSummary, formatDate, formatMetric, healthLabel, tierLabel } from '@/utils/resourceFormat'

const props = defineProps<{
  runId: string | null
  resourceObservation: ResourceObservation | null
}>()

const boundResources = computed(() => {
  const observation = props.resourceObservation
  if (!observation) return []
  const grouped = new Map<string, {
    resourceId: string
    agentId: string
    modelId: string
    attemptCount: number
    health: string
    deploymentTier: string | null
    latencyMs: number | null | undefined
  }>()
  for (const binding of observation.bindings) {
    const profile = observation.items.find(item => item.profile.resourceId === binding.resourceId)
    const existing = grouped.get(binding.resourceId)
    if (existing) {
      existing.attemptCount += 1
      continue
    }
    grouped.set(binding.resourceId, {
      resourceId: binding.resourceId,
      agentId: binding.agentId,
      modelId: binding.modelId,
      attemptCount: 1,
      health: profile?.snapshot.healthStatus || 'unknown',
      deploymentTier: binding.deploymentTier || profile?.profile.deploymentTier || null,
      latencyMs: profile?.snapshot.latencyMs
    })
  }
  return [...grouped.values()]
})
</script>

<style scoped>
.resource-binding-list { margin-top: 8px; border-top: 1px solid var(--border-light); }
.resource-binding-row { padding: 9px 0; border-bottom: 1px solid var(--border-light); }
.resource-binding-row__heading, .resource-binding-row__meta { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; }
.resource-binding-row__heading strong { min-width: 0; overflow: hidden; color: var(--text-primary); font: 10px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.resource-binding-row__heading span { flex: 0 0 auto; color: var(--text-muted); font-size: 10px; }
.resource-binding-row__meta { justify-content: flex-start; margin-top: 4px; color: var(--text-muted); font-size: 10px; flex-wrap: wrap; }
.resource-reasons { display: flex; gap: 5px; margin-top: 6px; flex-wrap: wrap; }
.resource-reasons span { padding: 2px 5px; border: 1px solid var(--border-light); color: var(--text-muted); font: 9px var(--font-mono, monospace); }
.resource-failover-list { display: grid; gap: 7px; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border-light); color: var(--text-muted); font-size: 10px; }
.resource-failover-row { display: grid; gap: 3px; padding: 7px 8px; border-left: 2px solid var(--warning, #a36a16); background: color-mix(in srgb, var(--warning, #a36a16) 8%, transparent); }
.resource-failover-row p { margin: 0; color: var(--text-secondary); line-height: 1.5; }
.resource-empty { margin: 10px 0 0; color: var(--text-muted); font-size: 11px; line-height: 1.5; }
</style>
