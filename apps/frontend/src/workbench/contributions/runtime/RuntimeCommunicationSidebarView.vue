<template>
  <div class="sidebar-view-stack">
    <InspectorSection title="通信摘要" :badge="items.length ? `${items.length} records` : '未观测'">
      <div class="sidebar-metrics" aria-label="通信统计">
        <div><strong>{{ targetIds.size ? inboundCount : '—' }}</strong><span>相关接收</span></div>
        <div><strong>{{ targetIds.size ? outboundCount : '—' }}</strong><span>相关发送</span></div>
        <div><strong>{{ provenanceCount }}</strong><span>全局来源记录</span></div>
      </div>
      <InspectorPropertyList :rows="[
        { label: '当前对象', value: objectLabel },
        { label: '字段观测', value: observedFieldCount },
        { label: 'Artifact refs', value: artifactRefCount },
        { label: 'source', value: items.length ? '来源记录与执行追踪' : '未观测' }
      ]" />
      <p v-if="!runtimeObservation" class="sidebar-empty">未观测到通信数据。</p>
      <p v-else-if="!relatedItems.length" class="sidebar-empty">当前对象没有可证明的相关通信。</p>
    </InspectorSection>

    <InspectorSection v-if="relatedItems.length" title="最近相关通信" badge="只读摘要">
      <div class="communication-list">
        <div v-for="item in relatedItems" :key="item.id" class="communication-list__item">
          <strong>{{ communicationTitle(item) }}</strong>
          <span>{{ inspectorValue(item.source) }} · {{ formatDate(item.timestamp) }}</span>
          <InspectorDetails title="字段与来源引用"><p>{{ item.fields.length ? item.fields.map(inspectorLabel).join('、') : '当前没有记录字段列表。' }}</p><code v-if="item.artifactRef">{{ item.artifactRef }}</code></InspectorDetails>
        </div>
      </div>
    </InspectorSection>

    <InspectorSection title="数据流转" :badge="`${consumptions.length} records`">
      <InspectorDetails title="整次运行的读取记录" :count="consumptions.length"><div v-if="consumptions.length" class="record-list" aria-label="数据血缘记录">
        <article v-for="item in consumptions" :key="item.eventId" class="record-list__item">
          <div class="flow">
            <span v-for="producer in item.producerStepIds" :key="producer" class="node-tag producer">{{ stepLabel(producer) }}</span>
            <span class="flow-arrow" aria-hidden="true">→</span>
            <span class="node-tag consumer">{{ stepLabel(item.consumerStepId) }}</span>
          </div>
          <div v-if="item.consumedFields?.length" class="record-list__fields">
            <span>消费字段</span>
            <code v-for="field in item.consumedFields" :key="field">{{ field }}</code>
          </div>
          <small>event {{ item.eventId }}<template v-if="item.contractStatus"> · {{ item.contractStatus }}</template></small>
        </article>
      </div>
      <p v-else class="sidebar-empty">当前快照没有数据流转记录。</p></InspectorDetails>
      <InspectorDetails v-if="productions.length" title="整次运行的生成记录" :count="productions.length"><div class="production-list" aria-label="数据生产记录">
        <div class="subsection-label">生产记录 · {{ productions.length }}</div>
        <article v-for="item in productions" :key="item.eventId" class="production-list__item">
          <strong>{{ stepLabel(item.producerStepId) }}</strong>
          <span>{{ item.fieldNames?.join(', ') || '字段未观测' }}</span>
          <small>event {{ item.eventId }}</small>
        </article>
      </div></InspectorDetails>
    </InspectorSection>

    <InspectorSection title="运行交互" :badge="`${interactions.length} records`">
      <p class="sidebar-empty">查看步骤之间传递的数据字段与 Token 用量。</p>
      <InspectorDetails title="整次运行的交互记录" :count="interactions.length"><div v-if="interactions.length" class="record-list" aria-label="运行交互记录">
        <article v-for="item in interactions" :key="item.interactionId || item.eventId" class="record-list__item">
          <div class="flow">
            <span class="node-tag producer">{{ participantLabel(item.producerAgentNames, item.producerStepIds) }}</span>
            <span class="flow-arrow" aria-hidden="true">→</span>
            <span class="node-tag consumer">{{ item.consumerAgentName || stepLabel(item.consumerStepId) }}</span>
          </div>
          <div class="interaction-meta">
            <span>{{ formatNumber(item.tokensDelivered) }} / {{ formatNumber(item.tokensAvailable) }} Token</span>
            <span>节省 {{ (Number(item.savingRatio || 0) * 100).toFixed(1) }}%</span>
            <span>{{ inspectorValue(item.contractStatus) }}</span>
          </div>
          <div v-if="interactionFields(item).length" class="record-list__fields">
            <span>投递字段</span>
            <code v-for="field in interactionFields(item)" :key="field">{{ field }}</code>
          </div>
          <small>interaction {{ item.interactionId }} · event {{ item.eventId }}</small>
        </article>
      </div>
      <p v-else class="sidebar-empty">当前快照没有交互记录。</p></InspectorDetails>
    </InspectorSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import InspectorDetails from '@/components/workbench/InspectorDetails.vue'
import { inspectorLabel, inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import type { WorkbenchInspectorContext } from '@/workbench/types'

const props = defineProps<{
  context: WorkbenchInspectorContext
  runtimeObservation: RuntimeObservation | null
}>()

const stepLabel = (id: string) => props.context.graph?.nodes.find(node => node.nodeId === id)?.name || id
const communicationTitle = (item: NonNullable<RuntimeObservation['communication']>[number]) => {
  if (item.producerStepId || item.consumerStepId) return (item.producerStepId ? stepLabel(item.producerStepId) : '上游数据') + ' → ' + (item.consumerStepId ? stepLabel(item.consumerStepId) : '下游步骤')
  return item.summary
}
const items = computed(() => props.runtimeObservation?.communication || [])
const provenance = computed(() => props.runtimeObservation?.provenance || null)
const productions = computed(() => provenance.value?.productions || [])
const consumptions = computed(() => provenance.value?.consumptions || [])
const interactions = computed(() => provenance.value?.interactions || [])
const objectLabel = computed(() => props.context.graphNode?.name || props.context.entry?.name || 'Mission')
const targetIds = computed(() => new Set([
  props.context.selectedAcgNodeId,
  props.context.graphNode?.acgNodeId,
  props.context.graphNode?.taskId,
  props.context.entry?.acgNodeId,
  props.context.entry?.taskId
].filter((value): value is string => Boolean(value))))
const relatedItems = computed(() => {
  const entry = props.context.entry
  const targets = targetIds.value
  const artifactRefs = new Set([entry?.artifactId, entry?.contentRef].filter((value): value is string => Boolean(value)))
  const related = items.value.filter(item => (
    targets.has(item.producerStepId || '')
    || targets.has(item.consumerStepId || '')
    || Boolean(item.artifactRef && artifactRefs.has(item.artifactRef))
  ))
  const source = related.length || targets.size || artifactRefs.size ? related : items.value
  return source.slice(-3).reverse()
})
const inboundCount = computed(() => {
  const targets = targetIds.value
  return targets.size ? items.value.filter(item => targets.has(item.consumerStepId || '')).length : 0
})
const outboundCount = computed(() => {
  const targets = targetIds.value
  return targets.size ? items.value.filter(item => targets.has(item.producerStepId || '')).length : 0
})
const provenanceCount = computed(() => items.value.filter(item => item.source === 'provenance').length)
const observedFieldCount = computed(() => new Set(items.value.flatMap(item => item.fields)).size)
const artifactRefCount = computed(() => new Set(items.value.map(item => item.artifactRef).filter(Boolean)).size)
const formatDate = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '时间未观测'
const participantLabel = (names: string[] | undefined, stepIds: string[]) => {
  const values = names?.length ? names : stepIds
  return values.join(' + ') || '来源未观测'
}
const interactionFields = (item: typeof interactions.value[number]) => Array.from(new Set((item.producerFields || []).flatMap(row => row.fields || [])))
const formatNumber = (value: number | undefined) => {
  if (value == null) return '未观测'
  return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value)
}
</script>

<style scoped>
.sidebar-view-stack { display: contents; }
.sidebar-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 8px; }
.sidebar-metrics > div { display: grid; gap: 2px; min-width: 0; }
.sidebar-metrics strong { color: var(--wb-text); font: 16px var(--font-mono, monospace); }
.sidebar-metrics span { color: var(--wb-text-muted); font-size: 12px; }
.communication-list { display: grid; gap: 10px; }
.communication-list__item { display: grid; gap: 3px; padding-top: 8px; border-top: 1px solid color-mix(in srgb, var(--wb-border-soft) 70%, transparent); }
.communication-list__item:first-child { padding-top: 0; border-top: 0; }
.communication-list__item strong { overflow: hidden; color: var(--wb-text); font: 500 12px/1.65 var(--font-sans, sans-serif); overflow-wrap: anywhere; white-space: normal; }
.communication-list__item span, .communication-list__item small { overflow: hidden; color: var(--wb-text-muted); font-size: 12px; overflow-wrap: anywhere; white-space: normal; }
.sidebar-empty { margin: 10px 0 0; color: var(--wb-text-muted); font-size: 11px; line-height: 1.5; }
.record-list { display: grid; gap: 8px; }
.record-list__item { display: grid; gap: 6px; min-width: 0; padding: 9px 10px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); background: var(--wb-surface-inset); }
.flow { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; min-width: 0; }
.node-tag { min-width: 0; max-width: 100%; padding: 3px 7px; border-radius: 999px; overflow-wrap: anywhere; font-size: 12px; line-height: 1.3; }
.node-tag.producer { border: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: var(--wb-surface-pane); }
.node-tag.consumer { color: var(--wb-accent); background: var(--wb-accent-soft); }
.flow-arrow { color: var(--wb-text-muted); }
.record-list__fields { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; color: var(--wb-text-muted); font-size: 12px; }
.record-list__fields code { padding: 2px 5px; border-radius: 4px; color: var(--wb-text-secondary); background: var(--wb-surface-pane); font: 11px var(--font-mono, monospace); }
.record-list__item small, .production-list__item small { color: var(--wb-text-muted); font: 11px var(--font-mono, monospace); }
.interaction-meta { display: flex; gap: 8px; flex-wrap: wrap; color: var(--wb-text-muted); font-size: 12px; }
.interaction-meta span:first-child { color: var(--wb-text-secondary); font-family: var(--font-mono, monospace); }
.subsection-label { margin-top: 12px; margin-bottom: 7px; color: var(--wb-text-muted); font-size: 12px; }
.production-list { display: grid; gap: 7px; }
.production-list__item { display: grid; gap: 3px; padding: 7px 9px; border-top: 1px solid var(--wb-border-soft); }
.production-list__item strong { color: var(--wb-text); font-size: 12px; }
.production-list__item span { color: var(--wb-text-secondary); font-size: 12px; }
</style>
