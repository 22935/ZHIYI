<template>
  <section class="resource-topology" aria-label="端边云资源分布">
    <header class="resource-topology__head">
      <div><span>DEPLOYMENT OVERVIEW</span><h2>资源部署</h2></div>
      <p>任务会根据数据位置、隐私和能力要求选择可用资源。</p>
    </header>
    <p v-if="nodesError" class="resource-topology__error" role="status">{{ nodesError }}</p>
    <div v-if="attentionItems.length" class="resource-topology__attention" role="status">
      <strong>需要关注</strong>
      <button v-for="item in attentionItems" :key="item.profile.resourceId" type="button" @click="emit('open', item)">
        {{ item.profile.displayName || item.profile.resourceId }} · {{ connectionGuidance(item.snapshot.healthStatus).action }}
      </button>
    </div>
    <div class="resource-topology__grid">
      <section v-for="group in groups" :key="group.id" class="resource-topology__column" :class="`is-${group.id}`">
        <header><strong>{{ group.label }}</strong><span>{{ group.items.length }}</span></header>
        <button v-for="item in group.items" :key="item.profile.resourceId" type="button" class="resource-topology__card" @click="emit('open', item)">
          <span class="resource-topology__status" :class="`is-${item.snapshot.healthStatus}`"></span>
          <span class="resource-topology__identity"><strong>{{ item.profile.displayName || item.profile.resourceId }}</strong><small>{{ customerResourceType(item.profile.runtimeKind || item.profile.resourceType) }}</small></span>
          <small>{{ item.profile.dataZone || item.profile.location || '位置未标注' }} · {{ item.snapshot.availableSlots ?? item.profile.capacity }} 可用位</small>
        </button>
        <article v-for="node in group.nodes" :key="node.profile.nodeId" class="resource-topology__card resource-topology__card--node">
          <span class="resource-topology__status" :class="`is-${node.healthStatus}`"></span>
          <span class="resource-topology__identity"><strong>{{ node.profile.displayName || node.profile.nodeId }}</strong><small>设备</small></span>
          <small>{{ node.profile.placement }} · {{ nodeCapacity(node) }}</small>
          <button type="button" class="resource-topology__manage" :disabled="pendingNodes.includes(node.profile.nodeId)" @click="emit('toggle-node', { nodeId: node.profile.nodeId, enabled: !node.profile.enabled })">
            {{ pendingNodes.includes(node.profile.nodeId) ? '保存中…' : node.profile.enabled ? '停用设备' : '启用设备' }}
          </button>
        </article>
        <p v-if="!group.items.length && !group.nodes.length">暂无已连接资源</p>
      </section>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { NodeCatalogItem, RuntimeResourceItem } from '@/services/api/agentos'
import { connectionGuidance, customerResourceType, deploymentGroup } from './resourceCenterPresentation'

const props = defineProps<{ items: RuntimeResourceItem[]; nodes?: NodeCatalogItem[]; nodesError?: string; pendingNodes?: string[] }>()
const emit = defineEmits<{
  (event: 'open', item: RuntimeResourceItem): void
  (event: 'toggle-node', payload: { nodeId: string; enabled: boolean }): void
}>()
const groupDefinitions = [
  { id: 'device', label: '我的设备' },
  { id: 'edge', label: '边缘节点' },
  { id: 'cloud', label: '云端服务' }
] as const
const groups = computed(() => {
  const representedNodes = new Set(props.items.map(item => item.profile.nodeId).filter((nodeId): nodeId is string => Boolean(nodeId)))
  return groupDefinitions.map(group => ({
    ...group,
    items: props.items.filter(item => deploymentGroup(item.profile.deploymentTier).id === group.id),
    nodes: (props.nodes || []).filter(node => deploymentGroup(node.profile.placement).id === group.id && !representedNodes.has(node.profile.nodeId))
  }))
})
const attentionItems = computed(() => props.items.filter(item => ['offline', 'degraded', 'unknown'].includes(item.snapshot.healthStatus)).slice(0, 3))
const nodeCapacity = (node: NodeCatalogItem) => {
  const capacity = node.profile.computeCapacity
  if (!capacity) return '算力未登记'
  const parts = []
  if (capacity.cpuCores) parts.push(`${capacity.cpuCores} 核 CPU`)
  if (capacity.memoryMb) parts.push(`${Math.round(capacity.memoryMb / 1024)} GB 内存`)
  if (capacity.gpuType) parts.push(capacity.gpuType)
  return parts.join(' · ') || '算力未登记'
}
</script>

<style scoped>
.resource-topology { margin: 18px 0; padding: 18px; border: 1px solid var(--border-light); border-radius: var(--radius-card, 8px); background: var(--bg-card); }
.resource-topology__head { display: flex; align-items: end; justify-content: space-between; gap: 20px; }
.resource-topology__head span { color: var(--primary-color); font: 10px var(--font-mono, monospace); letter-spacing: .08em; }.resource-topology__head h2 { margin: 4px 0 0; font-size: 15px; }.resource-topology__head p { max-width: 390px; margin: 0; color: var(--text-muted); font-size: 11px; line-height: 1.6; }
.resource-topology__attention { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 14px 0; padding: 9px 10px; border-left: 3px solid var(--warning); background: color-mix(in srgb, var(--warning) 8%, var(--bg-input)); font-size: 11px; }.resource-topology__attention button { border: 0; color: var(--primary-color); background: transparent; cursor: pointer; font: inherit; }
.resource-topology__error { color: var(--text-muted); font-size: 11px; }
.resource-topology__grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }.resource-topology__column { min-width: 0; padding: 10px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-input); }.resource-topology__column > header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; color: var(--text-secondary); font-size: 11px; }.resource-topology__column > header span { color: var(--text-muted); font: 11px var(--font-mono, monospace); }.resource-topology__column > p { margin: 14px 0 4px; color: var(--text-muted); font-size: 10px; }
.resource-topology__card { display: grid; grid-template-columns: 7px minmax(0, 1fr); gap: 8px; width: 100%; margin-top: 7px; padding: 9px; border: 1px solid var(--border-light); border-radius: 5px; color: inherit; background: var(--bg-card); cursor: pointer; text-align: left; }.resource-topology__card:hover { border-color: var(--primary-line); }.resource-topology__card > small { grid-column: 2; color: var(--text-muted); font-size: 10px; }.resource-topology__identity { display: grid; gap: 3px; min-width: 0; }.resource-topology__identity strong { overflow: hidden; color: var(--text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }.resource-topology__identity small { color: var(--text-secondary); font-size: 10px; }.resource-topology__status { width: 7px; height: 7px; margin-top: 3px; border-radius: 50%; background: var(--text-muted); }.resource-topology__status.is-online { background: var(--success); }.resource-topology__status.is-degraded { background: var(--warning); }.resource-topology__status.is-offline { background: var(--danger); }
.resource-topology__manage { grid-column: 2; justify-self: start; min-height: 28px; padding: 0 9px; border: 1px solid var(--border-light); border-radius: 4px; color: var(--text-secondary); background: var(--bg-card); cursor: pointer; font: inherit; font-size: 10px; }.resource-topology__manage:hover:not(:disabled) { border-color: var(--primary-line); color: var(--primary-color); }.resource-topology__manage:disabled { cursor: wait; opacity: .6; }
@media (max-width: 760px) { .resource-topology__head { align-items: start; flex-direction: column; gap: 8px; }.resource-topology__grid { grid-template-columns: 1fr; } }
</style>
