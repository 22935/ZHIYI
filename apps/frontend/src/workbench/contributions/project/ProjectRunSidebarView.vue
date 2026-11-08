<template>
  <div class="sidebar-view-stack">
    <LifecycleEvidence v-if="context?.lifecycle" :lifecycle="context.lifecycle" :observation="runtimeObservation" @open-artifact="emit('openArtifact', $event)" />
    <InspectorSection v-else title="运行状态" :badge="statusLabel" badge-tone="status">
      <p>{{ inspectorValue(statusLabel) }}</p>
      <InspectorPropertyList :rows="[{ label: '当前对象', value: objectLabel }]" />
      <InspectorDetails title="运行技术详情"><InspectorPropertyList :rows="[{ label: '运行编号', value: runId, code: true }, { label: '查看模式', value: historical ? '历史记录 · 只读' : '只读' }]" /></InspectorDetails>
    </InspectorSection>
    <InspectorSection v-if="liveNode" title="实时输出" :badge="liveNode.phase">
      <InspectorPropertyList :rows="[{ label: '当前节点', value: objectLabel }, { label: '耗时', value: liveDuration }]" />
      <pre class="live-output" data-testid="formal-live-output">{{ liveNode.outputBuffer || '正在等待模型输出…' }}</pre>
    </InspectorSection>
    <InspectorSection v-if="showGraphSummary" title="执行图概览" :badge="graphIdentity" :badge-tone="graphIdentityTone">
      <div class="sidebar-metrics" aria-label="图统计">
        <div><strong>{{ nodeCount ?? '—' }}</strong><span>{{ nodeCount == null ? '待编译节点' : '执行节点' }}</span></div>
        <div><strong>{{ edgeCount ?? '—' }}</strong><span>{{ edgeCount == null ? '待编译连线' : '依赖连线' }}</span></div>
        <div><strong>{{ graphVersion ?? '—' }}</strong><span>执行图版本</span></div>
      </div>
      <InspectorDetails title="执行图技术详情">
        <InspectorPropertyList :rows="[{ label: 'Graph ID', value: graph?.graphId || entry?.graphId, code: true }, { label: 'Task plan', value: entry?.metadata?.taskPlanVersion == null ? null : String(entry.metadata.taskPlanVersion) }]" />
      </InspectorDetails>
    </InspectorSection>
    <InspectorSection v-if="showTaskSummary" title="当前步骤" :badge="statusLabel">
      <p>{{ objectLabel }}</p>
      <div class="sidebar-metrics sidebar-metrics--two" aria-label="任务执行统计">
        <div><strong>{{ attemptCount }}</strong><span>执行次数</span></div>
        <div><strong>{{ artifactCount }}</strong><span>任务产物</span></div>
      </div>
      <InspectorDetails title="步骤技术详情">
        <InspectorPropertyList :rows="[{ label: 'semanticTaskKey', value: taskKey, code: true }, { label: 'taskId', value: graphNode?.taskId || entry?.taskId, code: true }, { label: 'latest attempt', value: latestAttemptId, code: true }]" />
      </InspectorDetails>
    </InspectorSection>
    <ProjectArtifactInspector v-if="showArtifactSummary && entry" :entry="entry" :run-id="runId" :entries="entries" :available="available ?? true" @locate-graph="emit('locateGraph')" />
    <InspectorSection v-if="runtimeObservation" title="上下文传递" :badge="lowEntropy?.observed ? '已获取统计' : '暂未获取'">
      <div class="low-entropy-hero">
        <div><strong>{{ savingRatioLabel }}</strong><span>有效 Token 节省率</span></div>
        <div class="low-entropy-hero__saved"><span>累计节省</span><strong>{{ tokenLabel(lowEntropy?.tokensSaved) }}</strong><small v-if="lowEntropy?.tokensSaved != null">Token</small></div>
      </div>
      <InspectorPropertyList :rows="[{ label: '实际投递 / 可获取', value: tokenLabel(lowEntropy?.tokensDelivered) + ' / ' + tokenLabel(lowEntropy?.tokensAvailable) }]" />
      <p class="sidebar-empty">反映步骤之间传递上下文的节省情况，不代表模型调用账单。</p>
      <div class="sidebar-metrics low-entropy-signals" aria-label="上下文传递统计">
        <div><strong>{{ lowEntropy?.interactionCount ?? '—' }}</strong><span>运行交互</span></div>
        <div><strong :class="{ 'is-retry': (lowEntropy?.recoveryCount ?? 0) > 0 }">{{ lowEntropy?.recoveryCount ?? '—' }}</strong><span>恢复次数</span></div>
        <div><strong :class="{ 'is-danger': (lowEntropy?.contractViolationCount ?? 0) > 0 }">{{ lowEntropy?.contractViolationCount ?? '—' }}</strong><span>合同异常</span></div>
      </div>
      <div v-if="lowEntropy?.observed" class="low-entropy-footer"><span>统计来源：执行来源记录</span><strong>{{ integrityLabel }}</strong></div>
      <p v-else class="sidebar-empty">当前快照尚未提供上下文传递指标。</p>
    </InspectorSection>
    <InspectorSection v-if="runtimeObservation" title="执行记录" :badge="runtimeObservation.traces.length + ' 条追踪'">
      <div class="sidebar-metrics sidebar-metrics--four" aria-label="运行观测统计">
        <div><strong>{{ runtimeObservation.traces.length }}</strong><span>执行追踪</span></div>
        <div><strong>{{ runtimeObservation.events.length }}</strong><span>运行事件</span></div>
        <div><strong>{{ runtimeObservation.communication.length }}</strong><span>通信记录</span></div>
        <div><strong>{{ runtimeObservation.toolCalls.length }}</strong><span>工具调用</span></div>
      </div>
      <InspectorDetails title="最近执行记录" :count="recentTraces.length">
        <div v-if="recentTraces.length" class="recent-traces" aria-label="最近运行记录">
          <div v-for="item in recentTraces" :key="item.eventId" class="recent-traces__item">
            <div><strong>{{ inspectorEventLabel(item.eventType) }}</strong><time>{{ formatTraceTime(item.timestamp) }}</time></div>
            <span>{{ item.stepId ? stepLabel(item.stepId) : '整次运行' }}</span>
            <span v-if="item.observation">{{ item.observation }}</span>
          </div>
        </div>
        <p v-else class="sidebar-empty">当前快照没有执行追踪记录。</p>
      </InspectorDetails>
      <InspectorDetails v-if="runtimeObservation?.operational" title="节点执行记录" :count="nodeExecutions.length">
        <div v-if="nodeExecutions.length" class="record-list" aria-label="节点生命周期记录">
          <article v-for="record in nodeExecutions" :key="record.executionInstanceId" class="record-list__item">
            <div class="record-list__heading"><strong>{{ stepLabel(record.stepId) }}</strong><span class="phase" :class="phaseToneClass(record.phase)">{{ phaseLabel(record.phase) }}</span></div>
            <code :title="record.executionInstanceId">{{ shortId(record.executionInstanceId) }}</code>
            <small>执行编号 {{ shortId(record.attemptId) }}<template v-if="record.loopPath.length"> · 循环 {{ record.loopPath.join('.') }}</template></small>
            <small v-if="record.commitId">提交 {{ shortId(record.commitId) }}</small>
            <small v-if="record.failureCode" class="record-list__failure">{{ record.failureCode }}</small>
          </article>
        </div>
        <p v-else class="sidebar-empty">当前快照没有节点执行记录。</p>
      </InspectorDetails>
    </InspectorSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { GraphProjection, WorkspaceEntry, WorkspaceGraphNode } from '@/services/api/agentos'
import type { NodeExecutionPhase } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import InspectorDetails from '@/components/workbench/InspectorDetails.vue'
import { inspectorValue, inspectorEventLabel } from '@/workbench/runtime/inspectorPresentation'
import LifecycleEvidence from './LifecycleEvidence.vue'
import ProjectArtifactInspector from './ProjectArtifactInspector.vue'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import type { WorkbenchInspectorContext } from '@/workbench/types'
import type { RuntimeEventStore } from '@/workbench/runtime/runtimeEvents'
import type { SemanticTone } from '@/utils/statusSemantic'

const props = defineProps<{
  entry: WorkspaceEntry | null
  graphNode: WorkspaceGraphNode | null
  graphNodes: WorkspaceGraphNode[]
  runId: string | null
  graph: GraphProjection | null
  runStatus: string | null
  historical: boolean
  context?: WorkbenchInspectorContext
  runtimeObservation?: RuntimeObservation | null
  runtimeStore?: RuntimeEventStore | null
  available?: boolean
  entries?: WorkspaceEntry[]
}>()

const emit = defineEmits<{ openArtifact: [entry: WorkspaceEntry]; locateGraph: [] }>()
const stepLabel = (id: string) => props.graphNodes.find(node => node.acgNodeId === id)?.name || id

const liveNode = computed(() => (
  props.graphNode?.acgNodeId ? props.runtimeStore?.nodes[props.graphNode.acgNodeId] || null : null
))
const liveDuration = computed(() => {
  if (!liveNode.value?.modelStartedAt) return '—'
  const end = liveNode.value.completedAt ? Date.parse(liveNode.value.completedAt) : Date.now()
  const start = Date.parse(liveNode.value.modelStartedAt)
  return Number.isFinite(start) && Number.isFinite(end) ? `${Math.max(0, end - start)} ms` : '—'
})

const statusValue = computed(() => props.graphNode?.status || props.entry?.status || props.runStatus || null)
const statusLabel = computed(() => String(inspectorValue(statusValue.value || '未观测')))
const graphIdentityTone = computed(() => {
  const identity = graphIdentity.value
  if (identity === 'canonical') return 'artifact' as const
  if (identity === '等待编译') return 'muted' as const
  return 'waiting' as const
})
const objectLabel = computed(() => props.graphNode?.name || props.entry?.name || 'Mission')
const taskKey = computed(() => props.graphNode?.semanticTaskKey || props.entry?.semanticTaskKey || null)
const isArtifact = computed(() => props.entry?.kind === 'artifact')
const isTask = computed(() => props.entry?.kind === 'task')
const isGraph = computed(() => props.entry?.kind === 'graph' || props.entry?.kind === 'run' || !props.entry)
const showGraphSummary = computed(() => isGraph.value && !props.graphNode)
const showTaskSummary = computed(() => Boolean(props.graphNode || isTask.value))
const showArtifactSummary = computed(() => isArtifact.value)
const attemptCount = computed(() => props.graphNode?.attemptId ? 1 : props.entry?.attemptCount ?? 0)
const artifactCount = computed(() => props.graphNode?.artifactCount ?? props.entry?.artifactCount ?? 0)
const latestAttemptId = computed(() => props.graphNode?.attemptId || props.entry?.latestAttemptId || props.entry?.attemptId || null)
const nodeCount = computed(() => props.graph?.nodes?.length ?? (props.graphNodes.length > 0 ? props.graphNodes.length : null))
const edgeCount = computed(() => props.graph?.edges?.length ?? null)
const graphVersion = computed(() => {
  const graph = props.graph as (GraphProjection & { graphVersion?: number }) | null
  return graph?.graphVersion ?? graph?.graphVersion ?? props.entry?.graphVersion ?? null
})
const graphIdentity = computed(() => {
  if (!props.graph && !props.graphNodes.length) return '等待编译'
  if (!props.graphNodes.length) return 'unproven'
  if (props.graphNodes.every(node => node.identityQuality === 'canonical')) return 'canonical'
  if (props.graphNodes.some(node => node.identityQuality === 'legacy')) return 'mixed / legacy'
  return 'unproven'
})
const runtimeObservation = computed(() => props.runtimeObservation || props.context?.runtimeObservation || null)
const nodeExecutions = computed(() => runtimeObservation.value?.operational?.nodeExecutions || [])
const lowEntropy = computed(() => runtimeObservation.value?.lowEntropy || null)
const savingRatioLabel = computed(() => {
  const ratio = lowEntropy.value?.effectiveSavingRatio ?? lowEntropy.value?.averageSavingRatio
  return ratio == null ? '未观测' : `${(ratio * 100).toFixed(1)}%`
})
const integrityLabel = computed(() => {
  const status = lowEntropy.value?.integrityStatus
  if (!status) return '完整性未观测'
  if (['verified', 'valid'].includes(status.toLowerCase())) return '来源关联有效'
  return status
})
const recentTraces = computed(() => runtimeObservation.value?.traces.slice(-3).reverse() || [])
const tokenLabel = (value: number | null | undefined) => {
  if (value == null) return '未观测'
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(value)
}
const formatTraceTime = (value: string | null) => value
  ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false })
  : '时间未观测'
const shortId = (value: string) => value.length > 26 ? `${value.slice(0, 12)}…${value.slice(-8)}` : value
const phaseLabel = (phase: NodeExecutionPhase) => ({
  prepared: '已准备',
  executed: '已执行',
  audited: '已审计',
  committed: '已提交',
  waiting_review: '待审核',
  failed: '失败',
  cancelled: '已取消'
}[phase] || phase)
const PHASE_TONE: Record<NodeExecutionPhase, SemanticTone> = {
  prepared: 'waiting',
  executed: 'running',
  audited: 'artifact',
  committed: 'success',
  waiting_review: 'waiting',
  failed: 'failed',
  cancelled: 'failed'
}
const phaseToneClass = (phase: NodeExecutionPhase) => `tone-${PHASE_TONE[phase] || 'muted'}`
</script>

<style scoped>
.sidebar-view-stack { display: contents; }
.sidebar-status { display: flex; align-items: center; gap: 8px; min-height: 30px; margin-bottom: 4px; color: var(--wb-text); }
.sidebar-status strong { font-size: 14px; font-weight: 650; }
.sidebar-status__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--wb-text-muted); }
.sidebar-metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 8px; }
.sidebar-metrics--two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.sidebar-metrics--four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.sidebar-metrics > div { display: grid; justify-items: center; gap: 2px; min-width: 0; text-align: center; }
.sidebar-metrics strong { color: var(--wb-text); font: 500 22px/1.1 var(--font-serif, serif); font-variant-numeric: tabular-nums; }
.sidebar-metrics span { color: var(--wb-text-muted); font: 10px/1.35 var(--font-sans, sans-serif); letter-spacing: .01em; }
.low-entropy-hero { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding-bottom: 8px; }
.low-entropy-hero > div:first-child { display: grid; gap: 4px; min-width: 0; }
.low-entropy-hero > div:first-child strong { color: var(--wb-accent); font: 500 26px/1.05 var(--font-serif, serif); font-variant-numeric: tabular-nums; letter-spacing: -.02em; }
.low-entropy-hero span, .low-entropy-hero small { color: var(--wb-text-muted); font: 10px/1.35 var(--font-sans, sans-serif); }
.low-entropy-hero__saved { display: grid; justify-items: end; gap: 2px; padding-left: 14px; text-align: right; }
.low-entropy-hero__saved strong { color: var(--wb-text); font: 500 22px/1.1 var(--font-serif, serif); font-variant-numeric: tabular-nums; }
.low-entropy-signals { margin-top: 4px; }
.sidebar-metrics strong.is-retry { color: var(--wb-retry); }
.sidebar-metrics strong.is-danger { color: var(--wb-danger); }
.low-entropy-footer { display: flex; justify-content: space-between; gap: 10px; margin-top: 8px; padding-top: 9px; color: var(--wb-text-muted); font: 10px/1.35 var(--font-sans, sans-serif); }
.low-entropy-footer strong { color: var(--wb-success); font-weight: 650; }
.sidebar-empty { margin: 10px 0 0; color: var(--wb-text-muted); font-size: 11px; line-height: 1.5; }
.recent-traces { display: grid; gap: 8px; }
.recent-traces__item { display: grid; gap: 3px; padding-top: 8px; }
.recent-traces__item:first-child { padding-top: 0; }
.recent-traces__item > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.recent-traces__item strong { overflow: hidden; color: var(--wb-text); font: 10px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.recent-traces__item time, .recent-traces__item span { overflow: hidden; color: var(--wb-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.recent-traces__item time { flex: 0 0 auto; }
.record-list { display: grid; gap: 8px; }
.record-list__item { display: grid; gap: 3px; min-width: 0; padding: 9px 10px; border: 0; border-radius: var(--wb-radius-sm); background: var(--wb-surface-inset); }
.record-list__heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.record-list__heading strong { overflow: hidden; color: var(--wb-text); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.record-list__item code, .record-list__item small { overflow-wrap: anywhere; color: var(--wb-text-muted); font: 10px/1.4 var(--font-mono, monospace); }
.record-list__item code { color: var(--sem-running); }
.record-list__failure { color: var(--wb-danger) !important; }
.phase { flex: 0 0 auto; padding: 2px 6px; border-radius: 999px; color: var(--tone, var(--wb-accent)); background: var(--tone-fade, var(--wb-accent-soft)); font-size: 9px; }
.live-output { max-height: 220px; overflow: auto; margin: 9px 0 0; padding: 10px; border: 0; border-radius: var(--wb-radius-sm); color: var(--wb-text); background: var(--wb-surface-inset); font: 11px/1.55 var(--font-mono, monospace); white-space: pre-wrap; word-break: break-word; }
@media (max-width: 360px) { .sidebar-metrics--four { grid-template-columns: repeat(2, minmax(0, 1fr)); row-gap: 14px; } }
</style>
