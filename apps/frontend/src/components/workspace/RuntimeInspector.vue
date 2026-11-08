<template>
  <aside class="runtime-inspector" aria-label="Workspace Secondary Sidebar">
    <RuntimeObservationNotice :observation="workbenchContext.runtimeObservation" :run-id="runId" />
    <SecondarySidebar
      v-if="secondarySidebarViews.length && !isTaskInspector"
      :registry="registry"
      :context="inspectorContext"
      :title="inspectorTitle"
      :historical="historical"
      :fullscreen="fullscreen"
      :component-props="baseProps"
      @locate-graph="emit('locateGraph')"
      @open-artifact="emit('openArtifact', $event)"
      @toggle-fullscreen="emit('toggleFullscreen')"
      @close="emit('close')"
    />
    <InspectorFrame
      v-else-if="inspectorContribution || inspectorSections.length"
      :title="inspectorTitle"
      :historical="historical"
      :fullscreen="fullscreen"
      @toggle-fullscreen="emit('toggleFullscreen')"
      @close="emit('close')"
    >
      <template #header-meta>
        <div v-if="inspectorSummary" class="runtime-inspector__summary">
          <div class="runtime-inspector__summary-line">
            <span v-if="inspectorSummary.role" class="runtime-inspector__role">{{ inspectorSummary.role }}</span>
            <span v-if="inspectorSummary.status" class="runtime-inspector__status" :class="`is-${inspectorSummary.statusTone}`">
              <i aria-hidden="true"></i>{{ inspectorSummary.status }}
            </span>
            <span class="runtime-inspector__artifact">
              {{ inspectorSummary.artifactCount ? `${inspectorSummary.artifactCount} 个产物` : '暂无产物' }}
            </span>
          </div>

        </div>
      </template>
      <template v-if="isTaskInspector">
        <nav class="runtime-inspector__tabs" aria-label="任务详情视角" role="tablist" @keydown="handleInspectorTabKeydown">
          <button
            v-for="tab in taskInspectorTabs"
            :key="tab.id"
            type="button"
            role="tab"
            :aria-selected="activeTaskTab === tab.id"
            :tabindex="activeTaskTab === tab.id ? 0 : -1"
            :id="'task-inspector-tab-' + tab.id"
            :aria-controls="'task-inspector-panel-' + tab.id"
            :class="{ 'is-active': activeTaskTab === tab.id }"
            @click="activeTaskTab = tab.id"
          >{{ tab.label }}</button>
        </nav>

        <div v-if="activeTaskTab === 'task-info'" class="runtime-inspector__tab-panel" role="tabpanel" id="task-inspector-panel-task-info" aria-labelledby="task-inspector-tab-task-info">
          <InspectorSection v-if="entry?.objective" title="步骤目标">
            <p class="runtime-inspector__objective">{{ entry.objective }}</p>
          </InspectorSection>
          <component
            v-for="section in taskInfoSections"
            :key="section.id"
            :is="section.component"
            v-bind="sectionProps(section)"
            @locate-graph="emit('locateGraph')"
          />
          <InspectorDetails v-if="inspectorContext.lifecycle" title="整次运行与最终交付物">
            <LifecycleEvidence :lifecycle="inspectorContext.lifecycle" :observation="workbenchContext.runtimeObservation" @open-artifact="emit('openArtifact', $event)" />
          </InspectorDetails>
        </div>
        <div v-else-if="activeTaskTab === 'evidence'" class="runtime-inspector__tab-panel" role="tabpanel" id="task-inspector-panel-evidence" aria-labelledby="task-inspector-tab-evidence">
          <InspectorSection title="证据概览" :badge="artifactDocument?.kindLabel || '状态快照'">
            <p class="runtime-inspector__hint">用于追溯当前步骤采用的输入和生成的输出；引用存在不代表结论已通过实际测试。</p>
            <div v-if="artifactDocument" class="runtime-inspector__projection-meta">
              <div><span>产物类型</span><code>{{ artifactDocument.artifactKind }}</code></div>
              <div v-if="evidenceSummary.confidence"><span>置信信息</span><strong>{{ evidenceSummary.confidence }}</strong></div>
            </div>
            <InspectorDetails v-if="evidenceSummary.evidenceRefs.length" title="证据引用" :count="evidenceSummary.evidenceRefs.length">
              <div class="runtime-inspector__reference-list">
                <code v-for="reference in evidenceSummary.evidenceRefs" :key="reference">{{ reference }}</code>
              </div>
            </InspectorDetails>
            <InspectorDetails v-if="evidenceSummary.upstreamInputs.length" title="上游输入" :count="evidenceSummary.upstreamInputs.length">
              <div class="runtime-inspector__reference-list">
                <code v-for="input in evidenceSummary.upstreamInputs" :key="input">{{ input }}</code>
              </div>
            </InspectorDetails>
            <div v-if="evidenceSummary.provenance.length" class="runtime-inspector__reference-group">
              <span>来源关联</span>
              <dl class="runtime-inspector__provenance">
                <div v-for="item in evidenceSummary.provenance" :key="item.label">
                  <dt>{{ inspectorLabel(item.label) }}</dt>
                  <dd :class="{ 'is-code': item.code }">{{ item.code ? item.value : inspectorValue(item.value) }}</dd>
                </div>
              </dl>
            </div>
            <InspectorDetails v-if="evidenceSummary.traceLinks.length" title="追踪记录" :count="evidenceSummary.traceLinks.length">
              <div class="runtime-inspector__reference-list">
                <code v-for="trace in evidenceSummary.traceLinks" :key="trace">{{ trace }}</code>
              </div>
            </InspectorDetails>
          </InspectorSection>
          <InspectorSection title="运行证据" badge="projection">
            <div class="runtime-inspector__evidence-list">
              <div><span>追踪事件</span><strong>{{ evidenceSummary.traceCount }}</strong></div>
              <div><span>通信记录</span><strong>{{ evidenceSummary.communicationCount }}</strong></div>
            </div>
            <InspectorDetails title="输出技术引用"><code class="runtime-inspector__raw-ref">{{ evidenceSummary.outputRef }}</code></InspectorDetails>
          </InspectorSection>
          <InspectorSection v-if="graphNode && safeLiveOutput" title="结构化输出" :badge="liveNode?.phase || '经筛选的输出'">
            <InspectorDetails title="结构化输出原文"><pre class="runtime-output" data-testid="formal-live-output">{{ safeLiveOutput }}</pre></InspectorDetails>
          </InspectorSection>
          <component
            v-for="section in taskEvidenceSections"
            :key="section.id"
            :is="section.component"
            v-bind="sectionProps(section)"
            @locate-graph="emit('locateGraph')"
          />
        </div>
        <div v-else-if="activeTaskTab === 'files'" class="runtime-inspector__tab-panel" role="tabpanel" id="task-inspector-panel-files" aria-labelledby="task-inspector-tab-files">
          <TaskRelatedFilesInspector
            :entry="entry as WorkspaceEntry"
            :entries="entries"
            @open-artifact="emit('openArtifact', $event)"
          />
        </div>
        <div v-else class="runtime-inspector__tab-panel" role="tabpanel" id="task-inspector-panel-discussion" aria-labelledby="task-inspector-tab-discussion">
          <InspectorSection title="讨论" badge="empty">
            <p class="runtime-inspector__discussion-empty">当前还没有讨论记录。</p>
          </InspectorSection>
        </div>
      </template>
      <template v-else>
        <InspectorSection v-if="graphNode && safeLiveOutput" title="结构化输出" :badge="liveNode?.phase || '经筛选的输出'">
          <InspectorDetails title="结构化输出原文"><pre class="runtime-output" data-testid="formal-live-output">{{ safeLiveOutput }}</pre></InspectorDetails>
        </InspectorSection>
        <component
          v-for="section in inspectorSections"
          :key="section.id"
          :is="section.component"
          v-bind="sectionProps(section)"
          @locate-graph="emit('locateGraph')"
        />
        <component
          v-if="!inspectorSections.length && inspectorContribution"
          :is="inspectorContribution.component"
          v-bind="baseProps"
          @locate-graph="emit('locateGraph')"
        />
      </template>
    </InspectorFrame>
    <div v-else class="runtime-inspector__empty">选择任务步骤、交付物或执行图，查看详细信息。</div>
  </aside>
</template>

<script setup lang="ts">
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, shallowRef, watch } from 'vue'
import type { GraphProjection, WorkspaceEntry, WorkspaceGraphNode } from '@/services/api/agentos'
import type { WorkbenchContributionRegistry } from '@/workbench/registry'
import InspectorFrame from '@/components/workbench/InspectorFrame.vue'
import SecondarySidebar from '@/components/workbench/SecondarySidebar.vue'
import type { WorkbenchContext, WorkbenchInspectorContext } from '@/workbench/types'
import type { RunDocumentSymbol } from '@/workbench/runtime/runDocument'
import { safeStructuredOutput } from '@/workbench/runtime/runDocument'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import InspectorDetails from '@/components/workbench/InspectorDetails.vue'
import LifecycleEvidence from '@/workbench/contributions/project/LifecycleEvidence.vue'
import { handleInspectorTabKeydown, inspectorLabel, inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import TaskRelatedFilesInspector from './TaskRelatedFilesInspector.vue'
import RuntimeObservationNotice from './RuntimeObservationNotice.vue'
import {
  RunRuntimeStore,
  acquireRunRuntimeStore,
  releaseRunRuntimeStore
} from '@/workbench/runtime/runtimeEvents'
import type { RuntimeEventStore } from '@/workbench/runtime/runtimeEvents'
import { statusSemanticTone } from '@/utils/statusSemantic'
import type { ArtifactDocumentModel } from '@/workbench/runtime/artifactProjection'

const props = defineProps<{
  registry: WorkbenchContributionRegistry
  workbenchContext: WorkbenchContext
  entry: WorkspaceEntry | null
  graphNode: WorkspaceGraphNode | null
  selectedSymbol?: RunDocumentSymbol | null
  graphNodes: WorkspaceGraphNode[]
  available: boolean
  runId: string | null
  missionId: string
  graph: GraphProjection | null
  runStatus: string | null
  historical: boolean
  runtimeStore?: RuntimeEventStore | null
  entries?: WorkspaceEntry[]
  artifactDocument?: ArtifactDocumentModel | null
  fullscreen?: boolean
}>()
const ownedRuntimeStore = shallowRef<RunRuntimeStore | null>(null)
const ownedRunId = ref<string | null>(null)
let viewActive = true
const runtimeStore = computed(() => props.runtimeStore || ownedRuntimeStore.value)
const liveNode = computed(() => props.graphNode?.acgNodeId ? runtimeStore.value?.nodes[props.graphNode.acgNodeId] || null : null)
const safeLiveOutput = computed(() => {
  const type = props.selectedSymbol?.type
  if (type && ['agent', 'artifact', 'result', 'tool'].includes(type)) return null
  return safeStructuredOutput(liveNode.value?.outputBuffer)
})
const connectRuntime = (runId: string | null) => {
  if (!viewActive) return
  if (props.runtimeStore || props.historical || !['pending', 'planning', 'running', 'retrying', 'waiting_review'].includes(props.runStatus || '')) {
    releaseRunRuntimeStore(ownedRunId.value, ownedRuntimeStore.value)
    ownedRuntimeStore.value = null
    ownedRunId.value = null
    return
  }
  if (ownedRunId.value === runId) return
  releaseRunRuntimeStore(ownedRunId.value, ownedRuntimeStore.value)
  ownedRuntimeStore.value = acquireRunRuntimeStore(runId)
  ownedRunId.value = runId
}
watch([() => props.runId, () => props.runStatus, () => props.historical, () => props.runtimeStore], () => connectRuntime(props.runId))
onMounted(() => connectRuntime(props.runId))
const disconnectRuntime = () => {
  releaseRunRuntimeStore(ownedRunId.value, ownedRuntimeStore.value)
  ownedRuntimeStore.value = null
  ownedRunId.value = null
}
onDeactivated(() => { viewActive = false; disconnectRuntime() })
onActivated(() => { viewActive = true; connectRuntime(props.runId) })
onBeforeUnmount(disconnectRuntime)

const emit = defineEmits<{
  locateGraph: []
  openArtifact: [entry: WorkspaceEntry]
  close: []
  toggleFullscreen: []
}>()

const inspectorContext = computed(() => ({
  ...props.workbenchContext,
  entry: props.entry,
  graphNode: props.graphNode,
  available: props.available,
  graph: props.graph,
  runStatus: props.runStatus
}) as WorkbenchInspectorContext)

const inspectorContribution = computed(() => props.registry.resolveInspector(inspectorContext.value))
const inspectorSections = computed(() => props.registry.resolveInspectorSections(inspectorContext.value))
const secondarySidebarViews = computed(() => props.registry.resolveSecondarySidebarViews(inspectorContext.value))
const isTaskInspector = computed(() => props.entry?.kind === 'task')
const taskInspectorTabs = [
  { id: 'task-info', label: '任务信息' },
  { id: 'evidence', label: '证据与引用' },
  { id: 'files', label: '相关文件' },
  { id: 'discussion', label: '讨论' }
] as const
type TaskInspectorTab = typeof taskInspectorTabs[number]['id']
const activeTaskTab = ref<TaskInspectorTab>('task-info')
const taskInfoSections = computed(() => inspectorSections.value.filter(section => (
  section.id === 'project.task-identity-section' || section.id === 'project.task-execution-section'
)))
const taskEvidenceSections = computed(() => inspectorSections.value.filter(section => section.id === 'project.task-result-section'))
const evidenceSummary = computed(() => {
  const outputRef = props.entry?.metadata?.outputRef
  const nodeId = props.graphNode?.acgNodeId || props.entry?.acgNodeId
  const observation = props.workbenchContext.runtimeObservation
  const traces = nodeId ? observation?.traces.filter(item => item.stepId === nodeId) || [] : []
  const communications = nodeId
    ? observation?.communication.filter(item => (
      item.producerStepId === nodeId || item.consumerStepId === nodeId
    )) || []
    : []
  const contextPacks = nodeId
    ? observation?.contextPacks?.filter(item => item.stepId === nodeId) || []
    : []
  const provenance = observation?.provenance
  const productionEvents = nodeId ? provenance?.productions.filter(item => item.producerStepId === nodeId) || [] : []
  const consumptionEvents = nodeId ? provenance?.consumptions.filter(item => item.consumerStepId === nodeId) || [] : []
  const interactions = nodeId
    ? provenance?.interactions.filter(item => item.consumerStepId === nodeId || item.producerStepIds.includes(nodeId)) || []
    : []
  const artifactInspector = props.artifactDocument?.inspector
  const evidenceRefs = [
    ...(artifactInspector?.evidenceRefs || []),
    ...contextPacks.flatMap(item => item.evidenceRefs || []),
    ...productionEvents.flatMap(item => item.evidenceRefs || []),
    ...interactions.flatMap(item => item.evidenceRefs || [])
  ]
  const upstreamInputs = [
    ...(artifactInspector?.upstreamInputs || []),
    ...contextPacks.flatMap(item => item.sourceStepIds || []),
    ...communications.flatMap(item => item.producerStepId ? [item.producerStepId] : [])
  ]
  const traceLinks = [
    ...(artifactInspector?.traceLinks || []),
    ...traces.map(item => item.eventId)
  ]
  const provenanceRows = [
    ...(artifactInspector?.provenance || []),
    ...(provenance?.integrityStatus ? [{ label: 'Integrity', value: provenance.integrityStatus }] : []),
    ...(productionEvents.length ? [{ label: 'Productions', value: String(productionEvents.length) }] : []),
    ...(consumptionEvents.length ? [{ label: 'Consumptions', value: String(consumptionEvents.length) }] : []),
    ...(interactions.length ? [{ label: 'Interactions', value: String(interactions.length) }] : [])
  ]
  return {
    outputRef: typeof outputRef === 'string' && outputRef
      ? outputRef
      : artifactInspector?.traceLinks[0] || '未观测',
    traceCount: nodeId ? String(traces.length) : '未观测',
    communicationCount: nodeId ? String(communications.length) : '未观测',
    evidenceRefs: [...new Set(evidenceRefs.filter(Boolean))],
    confidence: artifactInspector?.confidence || null,
    upstreamInputs: [...new Set(upstreamInputs.filter(Boolean))],
    provenance: provenanceRows,
    traceLinks: [...new Set(traceLinks.filter(Boolean))]
  }
})
watch([() => props.entry?.entryId, () => props.selectedSymbol?.type], ([entryId, symbolType], previous) => {
  if (entryId !== previous?.[0]) activeTaskTab.value = 'task-info'
  if (symbolType === 'result') activeTaskTab.value = 'evidence'
  else if (previous?.[1] === 'result') activeTaskTab.value = 'task-info'
}, { immediate: true })
const inspectorTitle = computed(() => (
  props.selectedSymbol?.title
  || props.graphNode?.name
  || props.entry?.name
  || (props.entry?.kind === 'graph' ? '执行图' : '任务详情')
))
const inspectorSummary = computed(() => {
  const taskLike = props.entry?.kind === 'task' || Boolean(props.graphNode)
  if (!taskLike) return null
  const status = props.graphNode?.status || props.entry?.status || props.selectedSymbol?.status || null
  const role = props.entry?.logicalRole ? inspectorLabel(props.entry.logicalRole) : null
  const key = props.graphNode?.semanticTaskKey || props.entry?.semanticTaskKey || props.selectedSymbol?.semanticTaskKey || props.selectedSymbol?.subtitle || null
  const artifactCount = props.graphNode?.artifactCount ?? props.entry?.artifactCount ?? 0
  const tone = statusSemanticTone(status)
  const statusTone = tone === 'success' ? 'success'
    : tone === 'failed' ? 'danger'
      : tone === 'running' ? 'active'
        : tone === 'waiting' ? 'waiting'
          : tone === 'retry' ? 'retry'
            : 'muted'
  const statusLabel: Record<string, string> = {
    completed: '已完成',
    succeeded: '已完成',
    failed: '失败',
    cancelled: '已取消',
    running: '运行中',
    planning: '规划中',
    executing: '执行中',
    pending: '待执行'
  }
  return {
    role,
    status: status ? (statusLabel[status] || status) : null,
    statusTone,
    key,
    artifactCount
  }
})
const baseProps = computed(() => ({
  entry: props.entry,
  graphNode: props.graphNode,
  selectedSymbol: props.selectedSymbol || null,
  graphNodes: props.graphNodes,
  available: props.available,
  runId: props.runId,
  missionId: props.missionId,
  graph: props.graph,
  runStatus: props.runStatus,
  historical: props.historical,
  runtimeStore: runtimeStore.value,
  entries: props.entries || [],
  resourceObservation: props.workbenchContext.runtimeObservation?.resourceObservation || null,
  runtimeObservation: props.workbenchContext.runtimeObservation || null
}))
const sectionProps = (section: { getProps?: (context: WorkbenchInspectorContext) => Record<string, unknown> }) => ({
  ...baseProps.value,
  ...(section.getProps?.(inspectorContext.value) || {})
})
</script>

<style scoped>
.runtime-inspector { display: flex; flex-direction: column; min-width: 0; min-height: 0; height: 100%; background: var(--wb-surface-pane); color: var(--wb-text); }
.runtime-inspector__empty { padding: 22px 15px; color: var(--wb-text-muted); font-size: 12px; line-height: 1.6; }
.runtime-inspector__summary { display: grid; gap: 4px; min-width: 0; padding-top: 1px; }
.runtime-inspector__summary-line { display: flex; align-items: center; justify-content: flex-start; flex-wrap: wrap; gap: 5px; min-width: 0; }
.runtime-inspector__role, .runtime-inspector__status, .runtime-inspector__artifact { display: inline-flex; align-items: center; min-height: 19px; padding: 2px 6px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); font-size: 11px; line-height: 1.4; white-space: nowrap; }
.runtime-inspector__role { color: var(--wb-text-secondary); background: var(--wb-surface-inset); }
.runtime-inspector__status { gap: 5px; color: var(--wb-text-secondary); }
.runtime-inspector__status i { width: 6px; height: 6px; border-radius: 50%; background: var(--wb-text-muted); }
.runtime-inspector__status.is-success { color: var(--wb-success); border-color: color-mix(in srgb, var(--wb-success) 24%, var(--wb-border-soft)); background: color-mix(in srgb, var(--wb-success) 7%, transparent); }
.runtime-inspector__status.is-success i { background: var(--wb-success); }
.runtime-inspector__status.is-danger { color: var(--wb-danger); border-color: color-mix(in srgb, var(--wb-danger) 24%, var(--wb-border-soft)); background: color-mix(in srgb, var(--wb-danger) 7%, transparent); }
.runtime-inspector__status.is-danger i { background: var(--wb-danger); }
.runtime-inspector__status.is-active { color: var(--wb-accent); border-color: color-mix(in srgb, var(--wb-accent) 24%, var(--wb-border-soft)); background: color-mix(in srgb, var(--wb-accent) 7%, transparent); }
.runtime-inspector__status.is-active i { background: var(--wb-accent); }
.runtime-inspector__status.is-waiting { color: var(--wb-warning); border-color: color-mix(in srgb, var(--wb-warning) 24%, var(--wb-border-soft)); background: color-mix(in srgb, var(--wb-warning) 7%, transparent); }
.runtime-inspector__status.is-waiting i { background: var(--wb-warning); }
.runtime-inspector__status.is-retry { color: var(--wb-retry); border-color: color-mix(in srgb, var(--wb-retry) 24%, var(--wb-border-soft)); background: color-mix(in srgb, var(--wb-retry) 7%, transparent); }
.runtime-inspector__status.is-retry i { background: var(--wb-retry); }
.runtime-inspector__artifact { color: var(--wb-text-muted); }
.runtime-inspector__key { max-width: 100%; min-width: 0; overflow: hidden; color: var(--wb-text-muted); font: 9px/1.3 var(--font-mono, monospace); text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.runtime-inspector__tabs { display: flex; gap: 2px; min-height: 38px; margin: 4px 0 2px; padding: 2px; border: 0; border-radius: 9px; background: var(--wb-surface-inset); overflow-x: auto; scrollbar-width: none; }
.runtime-inspector__tabs::-webkit-scrollbar { display: none; }
.runtime-inspector__tabs button { flex: 1 0 auto; min-height: 32px; padding: 0 9px; border: 1px solid transparent; border-radius: 7px; color: var(--wb-text-muted); background: transparent; cursor: pointer; font-size: 12px; font-weight: 500; white-space: nowrap; transition: color 140ms var(--ease-out), background 140ms var(--ease-out), box-shadow 140ms var(--ease-out), transform 140ms var(--ease-out); }
.runtime-inspector__tabs button:hover { color: var(--wb-text-secondary); background: var(--wb-hover); }
.runtime-inspector__tabs button.is-active { color: var(--wb-accent); background: color-mix(in srgb, var(--wb-accent) 10%, var(--wb-surface-section)); box-shadow: none; font-weight: 650; }
.runtime-inspector__tabs button:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: -1px; }
.runtime-inspector__tab-panel { min-width: 0; }
.runtime-inspector__raw-ref { overflow-wrap: anywhere; font: 11px/1.65 var(--font-mono, monospace); color: var(--wb-text-secondary); }
.runtime-inspector__objective { margin: 0; color: var(--wb-text-secondary); font-size: 13px; line-height: 1.75; }
.runtime-inspector__task-run { display: grid; gap: 7px; }
.runtime-inspector__task-run > div { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1.45fr); gap: 10px; align-items: baseline; }
.runtime-inspector__task-run span { color: var(--wb-text-muted); font-size: 11px; }
.runtime-inspector__task-run strong, .runtime-inspector__task-run code { min-width: 0; overflow: hidden; color: var(--wb-text-secondary); font: 10px/1.45 var(--font-mono, monospace); text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.runtime-inspector__task-run strong { font-family: var(--font-sans, system-ui, sans-serif); font-size: 11px; font-weight: 550; }
.runtime-inspector__projection-meta { display: grid; gap: 7px; margin-bottom: 11px; }
.runtime-inspector__projection-meta > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: baseline; }
.runtime-inspector__projection-meta span, .runtime-inspector__reference-group > span { color: var(--wb-text-muted); font-size: 11px; }
.runtime-inspector__projection-meta code, .runtime-inspector__projection-meta strong { color: var(--wb-text-secondary); font: 10px var(--font-mono, monospace); text-align: right; }
.runtime-inspector__reference-group { display: grid; gap: 6px; margin-top: 12px; padding-top: 10px; border-top: 0; }
.runtime-inspector__reference-list { display: flex; flex-wrap: wrap; gap: 5px; }
.runtime-inspector__reference-list code { max-width: 100%; padding: 3px 5px; overflow-wrap: anywhere; color: var(--wb-text-secondary); background: var(--wb-surface-inset); font: 10px var(--font-mono, monospace); }
.runtime-inspector__provenance { display: grid; gap: 5px; margin: 0; }
.runtime-inspector__provenance > div { display: grid; grid-template-columns: minmax(84px, auto) minmax(0, 1fr); gap: 8px; }
.runtime-inspector__provenance dt { color: var(--wb-text-muted); font-size: 10px; }
.runtime-inspector__provenance dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: var(--wb-text-secondary); font-size: 10px; text-align: right; }
.runtime-inspector__provenance dd.is-code { font-family: var(--font-mono, monospace); }
.runtime-inspector__evidence-list { display: grid; gap: 7px; }
.runtime-inspector__evidence-list > div { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 12px; align-items: baseline; padding-bottom: 6px; border-bottom: 0; }
.runtime-inspector__evidence-list span { color: var(--wb-text-muted); font-size: 11px; }
.runtime-inspector__evidence-list code, .runtime-inspector__evidence-list strong { max-width: 150px; overflow: hidden; color: var(--wb-text-secondary); font: 10px var(--font-mono, monospace); text-align: right; text-overflow: ellipsis; white-space: nowrap; }
.runtime-inspector__hint, .runtime-inspector__discussion-empty { margin: 11px 0 0; color: var(--wb-text-muted); font-size: 11px; line-height: 1.6; }
.runtime-output { max-height: 220px; margin: 0; overflow: auto; color: var(--wb-text-secondary); font: 10px/1.5 var(--font-mono, monospace); white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
