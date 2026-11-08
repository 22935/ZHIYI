<template>
  <div class="sidebar-view-stack">
    <p class="sidebar-intro">查看步骤收到的上下文、前置依赖和来源引用。展开单条记录可查看字段。</p>
    <InspectorSection v-if="hasStepSnapshot" title="步骤上下文" badge="projection">
      <InspectorPropertyList :rows="[
        { label: 'objective', value: context.entry?.objective },
        { label: 'dependencies', value: dependencyKeys.length }
      ]" />
      <div v-if="dependencyKeys.length" class="dependency-list">
        <code v-for="dependency in dependencyKeys" :key="dependency">{{ dependency }}</code>
      </div>
    </InspectorSection>

    <InspectorSection v-if="operational" title="控制协同" :badge="operational ? `${controlRecordCount} records` : '未观测'">
      <div v-if="operational" class="sidebar-metrics" aria-label="控制协同统计">
        <div><strong>{{ operational.controlFrames.length }}</strong><span>控制记录</span></div>
        <div><strong>{{ Object.keys(operational.loopIterations).length }}</strong><span>循环</span></div>
        <div><strong>{{ Object.keys(operational.consensusResults).length }}</strong><span>共识</span></div>
        <div><strong>{{ Object.keys(operational.debateSessions).length }}</strong><span>讨论</span></div>
      </div>
      <p v-if="!operational" class="sidebar-empty">未观测到控制协同数据。</p>
      <template v-else>
        <OperationalRecords title="控制记录" :items="operational.controlFrames" />
        <OperationalMap title="循环迭代" :value="operational.loopIterations" />
        <OperationalMap title="共识结果" :value="operational.consensusResults" />
        <OperationalMap title="讨论过程" :value="operational.debateSessions" />
      </template>
    </InspectorSection>

    <InspectorSection v-if="operational" title="通信上下文" :badge="operational ? `${contextReferenceCount} refs` : '未观测'">
      <p v-if="!operational" class="sidebar-empty">未观测到通信上下文数据。</p>
      <template v-else>
        <ReferenceGroup title="通信" :items="operational.communicationRefs" />
        <ReferenceGroup title="记忆" :items="operational.memoryRefs" />
        <ReferenceGroup title="证据" :items="operational.evidenceRefs" />
        <OperationalMap title="资源租约" :value="operational.leaseStatuses" />
      </template>
    </InspectorSection>

    <p v-if="!operational" class="sidebar-empty">当前快照尚未提供控制协同和通信引用。</p>
    <InspectorSection title="上下文数据" :badge="contextPacks ? `${contextPacks.length} packs` : '未观测'">
      <p v-if="!contextPacks" class="sidebar-empty">当前快照尚未提供上下文包。</p>
      <ContextPackRecords v-else :items="contextPacks" />
    </InspectorSection>
  </div>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, type PropType } from 'vue'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import { inspectorLabel, inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import type { RunContextPackSummary } from '@/services/api/agentos'
import type { WorkbenchInspectorContext } from '@/workbench/types'

const props = defineProps<{
  context: WorkbenchInspectorContext
  runtimeObservation: RuntimeObservation | null
}>()
const dependencyKeys = computed(() => props.context.entry?.dependencyKeys || [])
const hasStepSnapshot = computed(() => Boolean(props.context.entry?.objective || dependencyKeys.value.length))
const operational = computed(() => props.runtimeObservation?.operational || null)
const contextPacks = computed(() => props.runtimeObservation?.contextPacks || null)
const controlRecordCount = computed(() => {
  const value = operational.value
  return value
    ? value.controlFrames.length
      + Object.keys(value.loopIterations).length
      + Object.keys(value.consensusResults).length
      + Object.keys(value.debateSessions).length
    : 0
})
const contextReferenceCount = computed(() => {
  const value = operational.value
  return value
    ? value.communicationRefs.length
      + value.memoryRefs.length
      + value.evidenceRefs.length
      + Object.keys(value.leaseStatuses).length
    : 0
})

const recordTitle = (item: Record<string, unknown>, index: number) => {
  const step = typeof item.stepId === 'string' ? item.stepId : null
  const name = step ? props.context.graph?.nodes.find(node => node.nodeId === step)?.name : null
  return name || (typeof item.stepGoal === 'string' ? item.stepGoal : null) || (step ? step : '记录 ' + String(index + 1).padStart(2, '0'))
}
const formatValue = (value: unknown) => {
  try {
    return JSON.stringify(value, null, 2) ?? String(value)
  } catch {
    return String(value)
  }
}

const renderStructuredValue = (value: unknown) => {
  if (!value || typeof value !== 'object') {
    return h('span', { class: 'structured-value' }, String(inspectorValue(typeof value === 'number' || typeof value === 'string' ? value : value == null ? null : String(value))))
  }
  const entries = Object.entries(value as Record<string, unknown>)
  if (!entries.length) return h('span', { class: 'structured-value' }, '空对象')
  return h('div', { class: 'structured-fields' }, [
    ...entries.map(([key, item]) => h('div', { class: 'structured-field', key }, [
      h('span', { class: 'structured-field__label' }, inspectorLabel(key)),
      renderFieldValue(item)
    ])),
    h('details', { class: 'structured-raw' }, [
      h('summary', '展开原始数据'),
      h('pre', formatValue(value))
    ])
  ])
}

const renderFieldValue = (value: unknown) => {
  if (value && typeof value === 'object') {
    return h('details', { class: 'structured-field__nested' }, [
      h('summary', Array.isArray(value) ? `${value.length} 项` : '展开'),
      h('pre', formatValue(value))
    ])
  }
  return h('strong', { class: 'structured-field__value' }, String(inspectorValue(typeof value === 'number' || typeof value === 'string' ? value : value == null ? null : String(value))))
}

const ReferenceGroup = defineComponent({
  props: {
    title: { type: String, required: true },
    items: { type: Array as PropType<string[]>, required: true }
  },
  setup(componentProps) {
    return () => h('div', { class: 'context-record-group' }, [
      h('div', { class: 'context-record-group__heading' }, [
        h('strong', componentProps.title),
        h('span', String(componentProps.items.length))
      ]),
      componentProps.items.length
        ? h('div', { class: 'reference-list' }, componentProps.items.map((item, index) => h('code', {
          class: 'reference-item',
          key: `${item}:${index}`,
          title: item
        }, item)))
        : h('p', { class: 'sidebar-empty' }, `暂无 ${componentProps.title} 引用。`)
    ])
  }
})

const OperationalRecords = defineComponent({
  props: {
    title: { type: String, required: true },
    items: { type: Array as PropType<Array<Record<string, unknown>>>, required: true }
  },
  setup(componentProps) {
    return () => h('div', { class: 'context-record-group' }, [
      h('div', { class: 'context-record-group__heading' }, [
        h('strong', componentProps.title),
        h('span', String(componentProps.items.length))
      ]),
      componentProps.items.length
        ? h('div', { class: 'structured-list' }, componentProps.items.map((item, index) => h('details', {
          class: 'structured-record',
          key: index
        }, [
          h('summary', recordTitle(item, index)),
          renderStructuredValue(item)
        ])))
        : h('p', { class: 'sidebar-empty' }, `暂无 ${componentProps.title} 数据。`)
    ])
  }
})

const OperationalMap = defineComponent({
  props: {
    title: { type: String, required: true },
    value: { type: Object as PropType<Record<string, unknown>>, required: true }
  },
  setup(componentProps) {
    return () => h('div', { class: 'context-record-group' }, [
      h('div', { class: 'context-record-group__heading' }, [
        h('strong', componentProps.title),
        h('span', String(Object.keys(componentProps.value).length))
      ]),
      Object.keys(componentProps.value).length
        ? h('div', { class: 'structured-list' }, Object.entries(componentProps.value).map(([key, value]) => h('details', {
          class: 'structured-record',
          key
        }, [
          h('summary', { title: key }, inspectorLabel(key)),
          renderStructuredValue(value)
        ])))
        : h('p', { class: 'sidebar-empty' }, `暂无 ${componentProps.title} 数据。`)
    ])
  }
})

// 上下文包是形状稳定的投影（RunContextPackSummary），用专用渲染替代通用字段表：
// 状态徽标 + Token 指标 + 目标正文 + 来源/证据 chips，技术编号与内部计数收进折叠区。
const isHealthyContract = (status: string): boolean => /^(valid|verified)$/i.test(status)

const packMetric = (label: string, value: unknown) => h('div', { class: 'context-pack__metric', key: label }, [
  h('strong', value == null || value === '' ? '暂无' : String(value)),
  h('span', label)
])

const goalBlock = (label: string, value: unknown) => {
  const text = typeof value === 'string' ? value.trim() : ''
  if (!text) return []
  return [h('div', { class: 'context-pack__goal', key: label }, [
    h('span', { class: 'context-pack__goal-label' }, label),
    h('p', { class: 'context-pack__goal-text' }, text)
  ])]
}

const chipRow = (label: string, items: string[], warn = false) => h('div', { class: 'context-pack__row', key: label }, [
  h('span', { class: 'context-pack__row-label' }, label),
  items.length
    ? h('div', { class: ['context-pack__chips', { 'is-warn': warn }] }, items.map((item, chipIndex) => h('code', {
      class: 'reference-item',
      key: `${item}:${chipIndex}`,
      title: item
    }, item)))
    : h('span', { class: 'context-pack__row-empty' }, '暂无')
])

const techRow = (label: string, value: unknown) => {
  if (value == null || value === '') return null
  return h('div', { class: 'context-pack__tech-row', key: label }, [
    h('span', label),
    h('code', String(value))
  ])
}

const ContextPackRecords = defineComponent({
  props: {
    items: { type: Array as PropType<RunContextPackSummary[]>, required: true }
  },
  setup(componentProps) {
    return () => {
      if (!componentProps.items.length) {
        return h('p', { class: 'sidebar-empty' }, '暂无上下文包数据。')
      }
      return h('div', { class: 'structured-list' }, componentProps.items.map((item, index) => {
        const title = recordTitle(item, index)
        return h('details', { class: 'structured-record context-pack', key: `${item.stepId}:${index}` }, [
          h('summary', { title }, [
            h('span', { class: 'context-pack__title' }, title),
            h('span', { class: 'context-pack__meta' }, [
              h('span', { class: ['context-pack__state', { 'is-off': item.available === false }] },
                item.available === false ? '未就绪' : '已就绪'),
              item.contractStatus
                ? h('span', { class: 'context-pack__contract', 'data-ok': isHealthyContract(item.contractStatus) ? 'true' : 'false' },
                  String(inspectorValue(item.contractStatus)))
                : null
            ])
          ]),
          h('div', { class: 'context-pack__body' }, [
            h('div', { class: 'context-pack__metrics' }, [
              packMetric('可获取 Token', item.tokensAvailable),
              packMetric('实际投递 Token', item.tokensDelivered),
              packMetric('节省比例', `${(Number(item.savingRatio || 0) * 100).toFixed(1)}%`)
            ]),
            ...goalBlock('任务目标', item.objective),
            ...goalBlock('步骤目标', item.stepGoal),
            chipRow('来源步骤', item.sourceStepIds || []),
            chipRow('证据引用', item.evidenceRefs || []),
            item.missingFields?.length ? chipRow('缺失字段', item.missingFields, true) : null,
            h('details', { class: 'context-pack__technical' }, [
              h('summary', '技术字段'),
              h('div', { class: 'context-pack__tech-rows' }, [
                techRow('步骤编号', item.stepId),
                techRow('上下文引用', item.contextRef),
                techRow('字段数量', item.fieldCount),
                techRow('来源数量', item.sourceCount),
                item.dataKeys?.length ? techRow('数据字段', item.dataKeys.join('、')) : null,
                item.sourceDataKeys?.length ? techRow('来源数据字段', item.sourceDataKeys.join('、')) : null
              ])
            ])
          ])
        ])
      }))
    }
  }
})
</script>

<style scoped>
.sidebar-view-stack { display: contents; }
.sidebar-intro { margin: 10px 0; color: var(--wb-text-secondary); font: 12px/1.7 var(--font-sans, sans-serif); }
:deep(.structured-record > summary) { display: flex; align-items: center; gap: 9px; min-width: 0; padding: 8px 11px; cursor: pointer; list-style: none; color: var(--wb-text-secondary); font: 500 12px/1.55 var(--font-sans, sans-serif); transition: background-color 140ms var(--ease-out, ease), color 140ms var(--ease-out, ease); }
:deep(.structured-record > summary::-webkit-details-marker) { display: none; }
:deep(.structured-record > summary::before) { content: ''; flex: 0 0 auto; width: 6px; height: 6px; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; opacity: .72; transform: rotate(-45deg); transition: transform 160ms var(--ease-out, ease); }
:deep(.structured-record[open] > summary::before) { transform: rotate(45deg); }
:deep(.structured-record > summary:hover) { color: var(--wb-text); background: var(--wb-hover); }
:deep(.structured-record[open] > summary) { color: var(--wb-text); }
:deep(.structured-record > summary:focus-visible) { outline: 2px solid var(--wb-accent); outline-offset: -2px; }
.dependency-list { display: grid; gap: 5px; margin-top: 10px; }
.dependency-list code { overflow-wrap: anywhere; color: var(--wb-text); font: 10px/1.4 var(--font-mono, monospace); }
.sidebar-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-bottom: 10px; }
.sidebar-metrics > div { display: grid; gap: 2px; min-width: 0; }
.sidebar-metrics strong { color: var(--wb-text); font: 15px var(--font-mono, monospace); }
.sidebar-metrics span { color: var(--wb-text-muted); font-size: 11px; line-height: 1.3; }
:deep(.context-record-group) { display: grid; gap: 8px; margin-top: 12px; }
:deep(.context-record-group:first-child) { margin-top: 0; }
:deep(.context-record-group__heading) { display: flex; align-items: center; justify-content: space-between; gap: 10px; min-width: 0; }
:deep(.context-record-group__heading strong) { min-width: 0; overflow-wrap: anywhere; color: var(--wb-text-secondary); font-size: 12px; font-weight: 650; letter-spacing: .01em; }
:deep(.context-record-group__heading span) { flex: 0 0 auto; padding: 2px 5px; border-radius: 4px; color: var(--wb-accent); background: var(--wb-accent-soft); font: 9px var(--font-mono, monospace); }
:deep(.reference-list), :deep(.structured-list) { display: grid; gap: 6px; }
:deep(.reference-item) { display: block; min-width: 0; overflow-wrap: anywhere; padding: 7px 9px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); color: var(--wb-text-secondary); background: var(--wb-surface-inset); font: 9px/1.4 var(--font-mono, monospace); }
:deep(.reference-item:hover) { border-color: color-mix(in srgb, var(--wb-accent) 24%, var(--wb-border-soft)); background: var(--wb-hover); }
:deep(.structured-record) { display: block; min-width: 0; overflow: hidden; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-md); background: color-mix(in srgb, var(--wb-surface-inset) 68%, var(--wb-surface-section)); box-shadow: 0 1px 2px color-mix(in srgb, var(--wb-text) 3%, transparent); transition: border-color 160ms var(--ease-out, ease); }
:deep(.structured-record[open]) { border-color: color-mix(in srgb, var(--wb-accent) 30%, var(--wb-border-soft)); }
:deep(.structured-record > .structured-value), :deep(.structured-record > .structured-fields) { margin: 0 11px 10px; }
:deep(.structured-record > strong), :deep(.structured-record > code) { overflow-wrap: anywhere; color: var(--wb-text-secondary); font: 10px/1.4 var(--font-mono, monospace); }
:deep(.structured-record > strong) { color: var(--wb-text); font-weight: 650; }
:deep(.structured-fields) { display: grid; gap: 0; min-width: 0; overflow: hidden; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); background: color-mix(in srgb, var(--wb-surface-section) 72%, transparent); }
:deep(.structured-field) { display: grid; grid-template-columns: minmax(118px, .85fr) minmax(0, 1.15fr); align-items: baseline; gap: 14px; min-width: 0; padding: 7px 9px; border-bottom: 1px solid var(--wb-border-soft); }
:deep(.structured-field:last-of-type) { border-bottom: 0; }
:deep(.structured-field__label) { min-width: 0; overflow-wrap: anywhere; color: var(--wb-text-muted); font: 11px/1.65 var(--font-mono, monospace); }
:deep(.structured-field__value) { min-width: 0; overflow-wrap: anywhere; color: var(--wb-text); font: 12px/1.65 var(--font-mono, monospace); text-align: left; }
:deep(.structured-field__nested) { min-width: 0; color: var(--wb-accent); font: 11px/1.65 var(--font-mono, monospace); text-align: right; }
:deep(.structured-field__nested) summary, :deep(.structured-raw) summary { cursor: pointer; }
:deep(.structured-field__nested) summary:hover, :deep(.structured-raw) summary:hover { color: var(--wb-text); }
:deep(.structured-field__nested) pre, :deep(.structured-raw) pre { max-height: 180px; margin: 5px 0 0; overflow: auto; color: var(--wb-text-muted); font: 9px/1.5 var(--font-mono, monospace); text-align: left; white-space: pre-wrap; overflow-wrap: anywhere; }
:deep(.structured-raw) { padding: 7px 9px; color: var(--wb-text-muted); font-size: 11px; }
:deep(.structured-value) { min-width: 0; overflow-wrap: anywhere; color: var(--wb-text); font: 12px/1.65 var(--font-mono, monospace); }
:deep(.sidebar-empty) { margin: 0; color: var(--wb-text-muted); font-size: 11px; line-height: 1.6; }
/* 上下文包专用卡片：标题行徽标 + 指标行 + 目标正文 + chips，技术字段折叠收纳。 */
:deep(.context-pack__title) { flex: 1 1 auto; min-width: 0; overflow: hidden; color: var(--wb-text); text-overflow: ellipsis; white-space: nowrap; }
:deep(.context-pack__meta) { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 6px; }
:deep(.context-pack__state) { padding: 1px 7px; border-radius: 999px; color: var(--wb-success); background: color-mix(in srgb, var(--wb-success) 13%, transparent); font: 10px/1.5 var(--font-sans, sans-serif); }
:deep(.context-pack__state.is-off) { color: var(--wb-warning); background: color-mix(in srgb, var(--wb-warning) 13%, transparent); }
:deep(.context-pack__contract) { padding: 1px 7px; border-radius: 999px; color: var(--wb-text-secondary); background: var(--wb-hover); font: 10px/1.5 var(--font-sans, sans-serif); }
:deep(.context-pack__contract[data-ok="true"]) { color: var(--wb-success); background: color-mix(in srgb, var(--wb-success) 13%, transparent); }
:deep(.context-pack__body) { display: grid; gap: 10px; margin: 0 11px 11px; padding-top: 10px; border-top: 1px solid var(--wb-border-soft); }
:deep(.context-pack__metrics) { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
:deep(.context-pack__metric) { display: grid; gap: 2px; min-width: 0; padding: 7px 10px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); background: var(--wb-surface-inset); }
:deep(.context-pack__metric strong) { min-width: 0; overflow-wrap: anywhere; color: var(--wb-text); font: 13px var(--font-mono, monospace); }
:deep(.context-pack__metric span) { color: var(--wb-text-muted); font-size: 10px; line-height: 1.3; }
:deep(.context-pack__goal), :deep(.context-pack__row) { display: grid; grid-template-columns: minmax(52px, 64px) minmax(0, 1fr); gap: 10px; align-items: start; }
:deep(.context-pack__goal-label), :deep(.context-pack__row-label) { padding-top: 2px; color: var(--wb-text-muted); font-size: 11px; line-height: 1.6; }
:deep(.context-pack__row-label) { padding-top: 6px; }
:deep(.context-pack__goal-text) { margin: 0; color: var(--wb-text-secondary); font: 12px/1.7 var(--font-sans, sans-serif); text-wrap: pretty; }
:deep(.context-pack__chips) { display: flex; flex-wrap: wrap; gap: 6px; min-width: 0; }
:deep(.context-pack__chips .reference-item) { display: inline-block; width: auto; max-width: 100%; margin: 0; padding: 4px 9px; border-radius: 999px; font: 10px/1.4 var(--font-mono, monospace); }
:deep(.context-pack__chips.is-warn .reference-item) { color: var(--wb-warning); border-color: color-mix(in srgb, var(--wb-warning) 32%, var(--wb-border-soft)); background: color-mix(in srgb, var(--wb-warning) 9%, transparent); }
:deep(.context-pack__row-empty) { color: var(--wb-text-muted); font-size: 11px; line-height: 1.6; }
:deep(.context-pack__technical) { min-width: 0; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); background: color-mix(in srgb, var(--wb-surface-section) 72%, transparent); }
:deep(.context-pack__technical > summary) { display: flex; align-items: center; gap: 8px; padding: 7px 10px; cursor: pointer; list-style: none; color: var(--wb-text-muted); font-size: 11px; transition: color 140ms var(--ease-out, ease); }
:deep(.context-pack__technical > summary::-webkit-details-marker) { display: none; }
:deep(.context-pack__technical > summary::before) { content: ''; flex: 0 0 auto; width: 6px; height: 6px; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; opacity: .72; transform: rotate(-45deg); transition: transform 160ms var(--ease-out, ease); }
:deep(.context-pack__technical[open] > summary::before) { transform: rotate(45deg); }
:deep(.context-pack__technical > summary:hover) { color: var(--wb-text); }
:deep(.context-pack__tech-rows) { display: grid; padding: 0 10px 8px; }
:deep(.context-pack__tech-row) { display: grid; grid-template-columns: minmax(64px, 88px) minmax(0, 1fr); gap: 10px; align-items: baseline; padding: 5px 0; }
:deep(.context-pack__tech-row + .context-pack__tech-row) { border-top: 1px solid var(--wb-border-soft); }
:deep(.context-pack__tech-row span) { color: var(--wb-text-muted); font-size: 11px; }
:deep(.context-pack__tech-row code) { min-width: 0; overflow-wrap: anywhere; color: var(--wb-text-secondary); font: 10px/1.5 var(--font-mono, monospace); user-select: text; }
@media (max-width: 480px) { .sidebar-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
