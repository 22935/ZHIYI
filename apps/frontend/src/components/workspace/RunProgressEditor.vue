<template>
  <section class="run-progress" aria-label="运行进度文档">
    <div class="run-progress__document-head">
      <RunBreadcrumb :mission-title="missionTitle" :items="breadcrumbItems" @locate="locateBreadcrumb" />
      <header class="run-progress__header">
        <div class="run-progress__eyebrow">RUN DOCUMENT</div>
        <div class="run-progress__heading-row">
          <div class="run-progress__heading-copy">
            <h1 class="run-progress__goal">{{ goalTitle }}</h1>
          </div>
          <button type="button" class="run-progress__mission-link" @click="openMission">查看 mission.md</button>
        </div>
        <div class="run-progress__meta">
          <span class="run-progress__status" :class="'is-' + runState">{{ stateLabel }}</span>
          <span v-if="durationText" class="run-progress__duration">{{ durationText }}</span>
          <span v-if="resolvedRunId" class="run-progress__runid">{{ resolvedRunId }}</span>
        </div>
      </header>
    </div>

    <div v-if="!resolvedRunId" class="run-progress__empty">运行开始后，这里会显示任务规划和执行过程。</div>

    <template v-else>
      <p v-if="lifecycle.failure" class="run-progress__waiting" role="status">{{ lifecycle.failure.layer }} · {{ lifecycle.failure.objectId }} · {{ lifecycle.failure.reason }} · Checkpoint / side effects: NOT_OBSERVED</p>
      <p v-if="lifecycle.deliveryStatus === 'MISSING'" class="run-progress__waiting" role="status">Completed · Final deliverable missing</p>
      <div class="run-progress__toolbar">
        <div class="run-progress__toolbar-leading">
          <span class="run-progress__toolbar-label">OVERVIEW</span>
          <nav class="run-progress__directory" aria-label="运行目录层级">
            <span class="run-progress__directory-separator" aria-hidden="true">/</span>
            <span class="run-progress__directory-item is-current">OUTLINE</span>
            <template v-for="(item, index) in breadcrumbItems" :key="`directory-${item.id}`">
              <span class="run-progress__directory-separator" aria-hidden="true">/</span>
              <button
                type="button"
                class="run-progress__directory-item"
                :class="{ 'is-current': index === breadcrumbItems.length - 1 }"
                :title="item.title"
                @click="locateBreadcrumb(item.id)"
              >
                {{ item.title }}
              </button>
            </template>
          </nav>
        </div>
        <label class="run-progress__filter">
          <span>Filter</span>
          <input v-model="filterText" type="search" placeholder="symbols" aria-label="过滤 Run symbols" />
        </label>
      </div>

      <div
        ref="scrollBody"
        class="run-progress__body"
        :class="{ 'is-graph-mode': hasGraphColumn }"
        @scroll="onScroll"
      >
        <div class="run-progress__stream">
          <div v-if="visibleSymbols.length" class="run-progress__browser" aria-label="Run document columns">
            <section
              v-for="column in browserColumns"
              :key="column.id"
              class="run-progress__column"
              :class="{
                'is-graph-column': column.graph,
                'is-detail-column': column.detail,
                'is-terminal-column': !column.graph && !column.detail && column.context?.type === 'task'
              }"
              :style="column.detail ? detailColumnStyle : column.graph ? graphColumnStyle : undefined"
            >
              <div class="run-progress__column-head">
                {{ column.context?.type === 'task' && !column.detail ? 'TASK DETAIL' : column.title }}
              </div>
              <div
                v-if="column.detail"
                class="run-progress__resize-handle"
                data-testid="detail-resize-handle"
                role="separator"
                aria-label="调整详情栏宽度"
                :aria-valuenow="detailColumnWidth || undefined"
                aria-valuemin="320"
                aria-valuemax="720"
                tabindex="0"
                @pointerdown="startDetailResize"
                @keydown="handleDetailResizeKeydown"
              ></div>
              <div v-if="column.graph" class="run-progress__graph-preview">
                <AcgTopologyGraph
                  :blueprint="projection.activeGraph || null"
                  :focus-node-id="graphFocusNodeId"
                  :runtime-phases="graphRuntimePhases"
                  :step-states="graphStepStates"
                  :completed-step-ids="graphCompletedStepIds"
                  :run-id="resolvedRunId"
                  workbench
                  @node-selected="selectGraphNode"
                  @node-double-clicked="openGraphNode"
                />
              </div>
              <div v-else-if="column.detail && column.detail.viewKey === 'intent-profile'" class="run-progress__detail run-progress__detail--artifact">
                <IntentProfileArtifact
                  :symbol="column.detail"
                  :mission-goal="goalSource"
                  :run-id="resolvedRunId"
                  :profile="runtimeStore?.planning.profile || null"
                />
              </div>
              <div v-else-if="column.detail && planningStageViewKey(column.detail)" class="run-progress__detail run-progress__detail--artifact">
                <PlanningStageArtifact
                  :symbol="column.detail"
                  :mission-goal="goalSource"
                  :run-id="resolvedRunId"
                  :view-key="planningStageViewKey(column.detail) || 'detail'"
                  :plan="runtimeStore?.planning.plan || null"
                  :fallback-nodes="graphNodes"
                  :fallback-edges="projection.activeGraph?.edges || []"
                />
              </div>
              <div v-else-if="column.detail" class="run-progress__detail">
                <div class="run-progress__detail-status">
                  <span class="run-progress__detail-mark" :class="`is-${column.detail.status}`">{{ detailStatusMark(column.detail.status) }}</span>
                  <strong>{{ column.detail.title }}</strong>
                </div>
                <p v-if="column.detail.subtitle" class="run-progress__detail-summary">{{ column.detail.subtitle }}</p>
                <dl v-if="detailRows(column.detail).length" class="run-progress__detail-list">
                  <div v-for="row in detailRows(column.detail)" :key="row.label">
                    <dt>{{ row.label }}</dt>
                    <dd>{{ row.value }}</dd>
                  </div>
                </dl>
                <pre v-if="column.detail.content" class="run-progress__detail-content">{{ column.detail.content }}</pre>
              </div>
              <div
                v-else
                class="run-progress__column-body"
                :class="{ 'is-terminal-body': !column.graph && !column.detail && column.context?.type === 'task' }"
              >
                <section v-if="column.context?.type === 'task'" class="run-progress__terminal-summary" aria-label="任务摘要">
                  <div class="run-progress__terminal-summary-head">
                    <span class="run-progress__terminal-eyebrow">SELECTED TASK</span>
                    <span class="run-progress__terminal-status" :class="`is-${column.context.status}`">
                      <span aria-hidden="true">{{ detailStatusMark(column.context.status) }}</span>
                      {{ column.context.status === 'completed' ? '已完成' : column.context.status === 'running' ? '进行中' : column.context.status === 'failed' ? '失败' : column.context.status === 'warning' ? '需关注' : '待开始' }}
                    </span>
                  </div>
                  <h2>{{ column.context.title }}</h2>
                  <p v-if="column.context.detail" class="run-progress__terminal-detail">{{ column.context.detail }}</p>
                  <p v-if="column.context.subtitle" class="run-progress__terminal-summary-copy">{{ column.context.subtitle }}</p>
                  <dl v-if="detailRows(column.context).length" class="run-progress__terminal-metrics">
                    <div v-for="row in detailRows(column.context).slice(0, 6)" :key="row.label">
                      <dt>{{ row.label }}</dt>
                      <dd :title="String(row.value)">{{ row.value }}</dd>
                    </div>
                  </dl>
                </section>
                <div v-if="column.context?.type === 'task'" class="run-progress__activity-heading">
                  <span>ACTIVITY</span>
                  <small>{{ column.symbols.length }} 项<span v-if="column.symbols.length"> · {{ activitySummary(column.symbols) }}</span></small>
                </div>
                <p v-if="column.context?.type === 'task' && !column.symbols.length" class="run-progress__activity-empty">暂无可展示的运行活动</p>
                <RunSymbolRow
                  v-for="item in column.symbols"
                  :key="item.id"
                  :symbol="item"
                  :selected-symbol-id="selectedSymbolIdForView"
                  :is-expanded="isBrowserExpanded"
                  horizontal
                  @toggle="toggleBrowser"
                  @select="selectSymbol"
                  @open="openSymbol"
                />
              </div>
            </section>
          </div>
          <p v-if="!visibleSymbols.length" class="run-progress__waiting">
            {{ filterText ? '没有匹配的 Symbol。' : runState === 'running' ? '等待 Runtime Projection…' : '该 Run 暂无可展示的 Runtime facts。' }}
          </p>
        </div>

        <button v-if="!followLatest" type="button" class="run-progress__follow" @click="scrollToLatest">跟随最新运行</button>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { runDisplayObjective, missionDocumentContent } from './missionSemanticDisplay'
import type { MissionWorkspaceProjection, WorkspaceEntry, WorkspaceGraphNode } from '@/services/api/agentos'
import { stepStatesFromRun } from '@/services/api/agentos/api/acg'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import type { RuntimeEventStore } from '@/workbench/runtime/runtimeEvents'
import AcgTopologyGraph from '@/components/agentos/AcgTopologyGraph.vue'
import IntentProfileArtifact from './IntentProfileArtifact.vue'
import PlanningStageArtifact from './PlanningStageArtifact.vue'
import RunBreadcrumb from './RunBreadcrumb.vue'
import RunSymbolRow from './RunSymbolRow.vue'
import { findRunDocumentSymbol, projectRunDocument, type RunDocumentSymbol, type RunDocumentViewKey } from '@/workbench/runtime/runDocument'
import { projectLifecycle } from '@/workbench/runtime/lifecycleProjection'

type PlanningStageViewKey = Exclude<RunDocumentViewKey, 'intent-profile'>

const props = defineProps<{
  entry: WorkspaceEntry
  projection: MissionWorkspaceProjection
  graphNodes: WorkspaceGraphNode[]
  runId: string | null
  selectedSemanticTaskKey?: string | null
  selectedSymbolId?: string | null
  runtimeObservation: RuntimeObservation | null
  runtimeStore?: RuntimeEventStore | null
}>()

const emit = defineEmits<{
  selectSemanticTask: [semanticTaskKey: string | null]
  selectSymbol: [symbol: RunDocumentSymbol]
  openArtifact: [entry: WorkspaceEntry]
  openEntry: [entry: WorkspaceEntry]
  openSemanticTask: [semanticTaskKey: string | null]
}>()

const resolvedRunId = computed(() => props.runId || (props.entry.kind === 'run' ? props.entry.runId || null : null))
const lifecycle = computed(() => projectLifecycle({ workspace: props.projection, selectedRunId: resolvedRunId.value,
  run: props.runtimeObservation?.runId === resolvedRunId.value ? props.runtimeObservation.run : null }))
const observedRun = computed(() => props.projection.runs.find(item => item.runId === resolvedRunId.value) || null)
const runStatus = computed(() => (
  props.runtimeObservation?.runId === resolvedRunId.value
    ? props.runtimeObservation.runStatus
    : observedRun.value?.status || props.runtimeObservation?.runStatus || null
))

const TERMINAL_OK = new Set(['completed', 'succeeded'])
const TERMINAL_BAD = new Set(['failed'])
const formalControl = computed(() => props.runtimeObservation?.run?.runId === resolvedRunId.value
  ? props.runtimeObservation.run.formalControl : null)
const runState = computed<'idle' | 'unknown' | 'running' | 'completed' | 'failed' | 'paused' | 'cancelled' | 'superseded'>(() => {
  if (!resolvedRunId.value) return 'idle'
  const status = runStatus.value
  if (!status) return 'unknown'
  if (status === 'cancelled' || status === 'superseded') return status
  if (TERMINAL_OK.has(status)) return 'completed'
  if (TERMINAL_BAD.has(status)) return 'failed'
  if (status === 'waiting_review') return 'paused'
  if (formalControl.value && ['pending', 'planning'].includes(status)) return 'paused'
  if (['queued', 'starting', 'running', 'executing', 'planning', 'pending', 'retrying'].includes(status)) return 'running'
  return 'unknown'
})

const STATE_LABELS: Record<string, string> = {
  idle: '尚未运行',
  running: 'RUNNING',
  completed: '运行完成',
  failed: '运行失败',
  paused: '等待审核',
  cancelled: '已取消',
  superseded: '已由后继 Run 替代',
  unknown: '状态未知'
}
const stateLabel = computed(() => {
  const formal = formalControl.value
  if (formal && ['pending', 'planning'].includes(runStatus.value || '')) {
    return formal.dispatch ? `Dispatch ${formal.dispatch.status}` : formal.permitStatus === 'ISSUED' ? 'Permit ISSUED'
      : formal.handoffStatus === 'STATE_PREPARED' ? 'STATE_PREPARED' : formal.status
  }
  // Temporary planner SSE remains in the live output, not the durable Run label.
  if (!resolvedRunId.value) return STATE_LABELS.idle
  return ({ PLANNING: 'PLANNING', QUEUED: '等待执行', RUNNING: 'RUNNING', RECOVERING: '正在恢复',
    WAITING_REVIEW: '等待审核', FAILED: '运行失败', COMPLETED: '运行完成', CANCELLED: '已取消',
    SUPERSEDED: '已由后继 Run 替代' } as Record<string, string>)[lifecycle.value.phase] || '状态未知'
})

const shorten = (value: string, length: number) => value.length > length ? `${value.slice(0, length)}…` : value
const goalSource = computed(() => runDisplayObjective(props.projection))
const goalTitle = computed(() => {
  const firstLine = goalSource.value.split(/[\n。！？!?]/)[0].trim()
  return shorten(firstLine || '运行进度', 58)
})
const missionTitle = computed(() => shorten(goalTitle.value, 32))

const nowTick = ref(0)
let durationTimer: ReturnType<typeof setInterval> | null = null
let viewActive = true
const syncDurationTimer = () => {
  if (viewActive && runState.value === 'running' && durationTimer === null) durationTimer = setInterval(() => { nowTick.value += 1 }, 1000)
  else if ((!viewActive || runState.value !== 'running') && durationTimer !== null) {
    clearInterval(durationTimer)
    durationTimer = null
  }
}
watch(runState, syncDurationTimer, { immediate: true })
onActivated(() => { viewActive = true; syncDurationTimer() })
onDeactivated(() => { viewActive = false; syncDurationTimer(); stopDetailResize() })
onBeforeUnmount(() => {
  if (durationTimer !== null) clearInterval(durationTimer)
  stopDetailResize()
})

const formatDuration = (ms: number) => {
  const total = Math.max(0, Math.floor(ms / 1000))
  const minutes = Math.floor(total / 60)
  const seconds = total % 60
  if (minutes) return `${minutes}m ${String(seconds).padStart(2, '0')}s`
  return `${total}s`
}
const durationText = computed(() => {
  void nowTick.value
  const liveElapsed = props.runtimeStore?.planning.elapsedMs
  const planningStatus = props.runtimeStore?.planning.status
  if (planningStatus && ['STARTING', 'RUNNING'].includes(planningStatus) && liveElapsed != null) return formatDuration(liveElapsed)
  const start = observedRun.value?.createdAt
  if (!start) return null
  const startedAt = new Date(start).getTime()
  if (Number.isNaN(startedAt)) return null
  const finishedAt = observedRun.value?.completedAt
  const end = finishedAt && !Number.isNaN(new Date(finishedAt).getTime()) ? new Date(finishedAt).getTime() : Date.now()
  return formatDuration(end - startedAt)
})

const documentModel = computed(() => projectRunDocument({
  runId: resolvedRunId.value,
  mission: props.projection.mission,
  graph: props.projection.activeGraph,
  graphNodes: props.graphNodes,
  entries: props.projection.entries,
  runtimeObservation: props.runtimeObservation,
  runtimeStore: props.runtimeStore
}))

const expandedSymbols = ref(new Map<string, boolean>())
const defaultExpanded = (symbol: RunDocumentSymbol) => symbol.defaultExpanded ?? ['running', 'warning', 'failed'].includes(symbol.status)
const isExpanded = (symbol: RunDocumentSymbol) => expandedSymbols.value.get(symbol.id) ?? defaultExpanded(symbol)
const toggleExpanded = (symbol: RunDocumentSymbol) => {
  const next = new Map(expandedSymbols.value)
  next.set(symbol.id, !isExpanded(symbol))
  expandedSymbols.value = next
}

const filterText = ref('')
const symbolMatches = (symbol: RunDocumentSymbol, needle: string) => [symbol.title, symbol.subtitle, symbol.type, symbol.semanticTaskKey, symbol.graphNodeId, symbol.artifactKey]
  .filter(Boolean)
  .some(value => String(value).toLowerCase().includes(needle))
const filterTree = (symbols: RunDocumentSymbol[], needle: string): RunDocumentSymbol[] => {
  if (!needle) return symbols
  return symbols.reduce<RunDocumentSymbol[]>((result, item) => {
    const children = filterTree(item.children, needle)
    if (symbolMatches(item, needle) || children.length) result.push({ ...item, children })
    return result
  }, [])
}
const visibleSymbols = computed(() => filterTree(documentModel.value.symbols, filterText.value.trim().toLowerCase()))

const horizontalPath = ref<string[]>([])
const scrollBody = ref<HTMLElement | null>(null)
const activeSymbolId = ref<string | null>(props.selectedSymbolId || null)
const selectedSymbolIdForView = computed(() => props.selectedSymbolId || activeSymbolId.value)
const detailStatusMark = (status: RunDocumentSymbol['status']) => ({
  running: '●',
  completed: '✓',
  warning: '!',
  failed: '×',
  pending: '○'
}[status])
const detailRows = (symbol: RunDocumentSymbol) => {
  const rows: Array<{ label: string; value: string | number }> = [
    { label: 'Status', value: symbol.status },
    { label: 'Type', value: symbol.type },
    { label: 'Activity', value: `${symbol.children.length} items` },
    ...(symbol.semanticTaskKey ? [{ label: 'semanticTaskKey', value: symbol.semanticTaskKey }] : []),
    ...(symbol.graphNodeId ? [{ label: 'ACG Node', value: symbol.graphNodeId }] : []),
    ...(symbol.artifactKey ? [{ label: 'artifactKey', value: symbol.artifactKey }] : []),
    ...(symbol.artifactId ? [{ label: 'artifactId', value: symbol.artifactId }] : [])
  ]
  for (const [key, value] of Object.entries(symbol.metrics || {})) {
    rows.push({ label: key, value: key === 'Duration' && typeof value === 'number' ? `${value} ms` : value })
  }
  const seen = new Set<string>()
  return rows.filter(row => {
    if (seen.has(row.label)) return false
    seen.add(row.label)
    return true
  })
}
const activitySummary = (symbols: RunDocumentSymbol[]) => {
  const labels: Record<RunDocumentSymbol['type'], string> = {
    run: '运行', planner: '规划', execution: '执行', stage: '阶段', task: '任务', agent: 'Agent',
    model: '模型', tool: '工具', artifact: '产物', acg: 'ACG', 'acg-node': '节点', result: '结果', runtime: '输出'
  }
  const counts = new Map<string, number>()
  symbols.forEach(symbol => counts.set(symbol.type, (counts.get(symbol.type) || 0) + 1))
  return Array.from(counts.entries()).map(([type, count]) => `${labels[type as RunDocumentSymbol['type']] || type} ${count}`).join(' · ')
}
const planningStageViewKey = (symbol: RunDocumentSymbol): PlanningStageViewKey | null => {
  const key = symbol.viewKey
  return key && key !== 'intent-profile' ? key : null
}
const browserColumns = computed(() => {
  const columns: Array<{ id: string; title: string; symbols: RunDocumentSymbol[]; detail?: RunDocumentSymbol; graph?: boolean; context?: RunDocumentSymbol }> = [{
    id: 'root',
    title: 'OUTLINE',
    symbols: visibleSymbols.value
  }]
  let currentSymbols = visibleSymbols.value
  for (const selectedId of horizontalPath.value) {
    const selected = currentSymbols.find(item => item.id === selectedId)
    if (!selected || !selected.children.length) break
    columns.push({ id: selected.id, title: selected.title, symbols: selected.children, context: selected })
    currentSymbols = selected.children
  }
  const selected = findRunDocumentSymbol(documentModel.value.symbols, selectedSymbolIdForView.value)
  const selectedIsVisible = selected && columns.some(column => column.symbols.some(item => item.id === selected.id))
  if (selected && selectedIsVisible && (selected.viewKey || !selected.children.length)) {
    columns.push(selected.type === 'acg'
      ? { id: `graph:${selected.id}`, title: 'GRAPH', symbols: [], graph: true }
      : { id: `detail:${selected.id}`, title: 'INSPECTOR', symbols: [], detail: selected })
  }
  return columns
})
const scrollToBrowserColumn = async (columnIndex?: number) => {
  await nextTick()
  const container = scrollBody.value
  if (!container) return
  const columns = Array.from(container.querySelectorAll<HTMLElement>('.run-progress__column'))
  if (!columns.length) return
  const index = Math.min(Math.max(columnIndex ?? columns.length - 1, 0), columns.length - 1)
  const column = columns[index]
  const containerRect = container.getBoundingClientRect()
  const columnRect = column.getBoundingClientRect()
  const leftOverflow = columnRect.left - containerRect.left
  const rightOverflow = columnRect.right - containerRect.right
  const delta = rightOverflow > 0 ? rightOverflow : leftOverflow < 0 ? leftOverflow : 0
  if (Math.abs(delta) < 1) return
  const targetLeft = Math.max(0, container.scrollLeft + delta)
  if (typeof container.scrollTo === 'function') {
    container.scrollTo({ left: targetLeft, behavior: 'smooth' })
  } else {
    container.scrollLeft = targetLeft
  }
}
const setHorizontalPath = (nextPath: string[], options: { scroll?: boolean; targetColumn?: number } = {}) => {
  const scroll = options.scroll ?? true
  const previousDepth = horizontalPath.value.length
  const nextDepth = nextPath.length
  const changed = previousDepth !== nextDepth
    || horizontalPath.value.some((item, index) => item !== nextPath[index])
  horizontalPath.value = nextPath
  if (!scroll) return
  // 新路径的列索引与路径深度一致：返回时要把父级列本身带回视口，
  // 而不是再向左多退一列。
  const targetColumn = options.targetColumn ?? nextDepth
  // 路径未变时，可能只是刚刚出现了 Inspector 列，也需要将新列带入视口。
  if (changed || options.targetColumn != null) void scrollToBrowserColumn(targetColumn)
}
const hasGraphColumn = computed(() => browserColumns.value.some(column => column.graph))
const graphColumnWidth = ref<number | null>(null)
const graphColumnStyle = computed(() => graphColumnWidth.value == null ? undefined : {
  flex: `0 0 ${graphColumnWidth.value}px`,
  width: `${graphColumnWidth.value}px`
})
const DETAIL_COLUMN_MIN_WIDTH = 320
const DETAIL_COLUMN_MAX_WIDTH = 720
const detailColumnWidth = ref<number | null>(null)
const detailColumnStyle = computed(() => detailColumnWidth.value == null ? undefined : {
  flex: `0 0 ${detailColumnWidth.value}px`,
  width: `${detailColumnWidth.value}px`
})
let detailResizeCleanup: (() => void) | null = null
const clampDetailColumnWidth = (width: number) => Math.min(
  DETAIL_COLUMN_MAX_WIDTH,
  Math.max(DETAIL_COLUMN_MIN_WIDTH, Math.round(width))
)
const stopDetailResize = () => {
  detailResizeCleanup?.()
  detailResizeCleanup = null
}
const startDetailResize = (event: PointerEvent) => {
  if (event.button !== 0) return
  const handle = event.currentTarget as HTMLElement
  const column = handle.closest<HTMLElement>('.run-progress__column')
  const startWidth = column?.getBoundingClientRect().width || 480
  const startX = event.clientX
  const previousCursor = document.body.style.cursor
  const previousUserSelect = document.body.style.userSelect
  detailColumnWidth.value = clampDetailColumnWidth(startWidth)
  const onMove = (moveEvent: PointerEvent) => {
    detailColumnWidth.value = clampDetailColumnWidth(startWidth - (moveEvent.clientX - startX))
  }
  const onUp = () => stopDetailResize()
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  detailResizeCleanup = () => {
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
    document.body.style.cursor = previousCursor
    document.body.style.userSelect = previousUserSelect
  }
  event.preventDefault()
}
const handleDetailResizeKeydown = (event: KeyboardEvent) => {
  if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return
  event.preventDefault()
  const handle = event.currentTarget as HTMLElement
  const column = handle.closest<HTMLElement>('.run-progress__column')
  const currentWidth = detailColumnWidth.value || column?.getBoundingClientRect().width || 480
  detailColumnWidth.value = clampDetailColumnWidth(currentWidth + (event.key === 'ArrowLeft' ? 24 : -24))
}
const graphRuntimePhases = computed(() => Object.fromEntries(
  Object.entries(props.runtimeStore?.nodes || {}).map(([nodeId, state]) => [nodeId, state.phase])
))
// SSE 只覆盖本次连接之后的事件（无历史回放），刷新后 runtimeStore 为空。
// 图节点状态必须回落到 runtimeObservation 轮询的 run.steps 持久投影（StepStatus）。
const graphObservedRun = computed(() => (
  props.runtimeObservation?.runId === resolvedRunId.value ? props.runtimeObservation.run : null
))
const graphStepStates = computed(() => graphObservedRun.value
  ? stepStatesFromRun(graphObservedRun.value, props.runtimeObservation?.executionTree, props.runtimeObservation?.lifecycles)
  : [])
const graphCompletedStepIds = computed(() => graphObservedRun.value?.completedStepIds || [])
const graphFocusNodeId = computed(() => (
  props.graphNodes.find(node => node.semanticTaskKey === props.selectedSemanticTaskKey)?.acgNodeId || null
))
const selectGraphNode = (nodeId: string) => {
  const node = props.graphNodes.find(item => item.acgNodeId === nodeId)
  if (node?.semanticTaskKey) emit('selectSemanticTask', node.semanticTaskKey)
}
const openGraphNode = (nodeId: string) => {
  const node = props.graphNodes.find(item => item.acgNodeId === nodeId)
  emit('openSemanticTask', node?.semanticTaskKey || null)
}
const isBrowserExpanded = (symbol: RunDocumentSymbol) => horizontalPath.value.includes(symbol.id)
const toggleBrowser = (symbol: RunDocumentSymbol) => {
  const columnIndex = browserColumns.value.findIndex(column => column.symbols.some(item => item.id === symbol.id))
  if (columnIndex < 0 || !symbol.children.length || symbol.viewKey) return
  const prefix = horizontalPath.value.slice(0, columnIndex)
  const isOpen = horizontalPath.value[columnIndex] === symbol.id
  if (isOpen) return
  setHorizontalPath([...prefix, symbol.id])
}
const parentPathFor = (symbols: RunDocumentSymbol[], targetId: string, parents: string[] = []): string[] | null => {
  for (const item of symbols) {
    if (item.id === targetId) return parents
    const nested = parentPathFor(item.children, targetId, [...parents, item.id])
    if (nested) return nested
  }
  return null
}
const syncHorizontalPathForSelection = (selectedId: string | null, symbols = documentModel.value.symbols, scroll = true) => {
  if (!selectedId) return
  const selected = findRunDocumentSymbol(symbols, selectedId)
  const parentPath = parentPathFor(symbols, selectedId)
  if (!selected || !parentPath) return
  // A selected parent owns the next column; a selected leaf owns the
  // inspector column attached to its existing parent column.
  if (selected.viewKey) {
    setHorizontalPath(parentPath, {
      scroll,
      targetColumn: parentPath.length + 1
    })
    return
  }
  if (selected.children.length) {
    setHorizontalPath([...parentPath, selected.id], {
      scroll,
      targetColumn: parentPath.length + 1
    })
    return
  }
  // A leaf owns the inspector column attached to its parent. Resetting the
  // path is important for root-level selections: clicking Planning while an
  // Execution branch is open must not append a third column to that branch.
  setHorizontalPath(parentPath, {
    scroll,
    targetColumn: parentPath.length + 1
  })
}
const defaultPathFor = (symbols: RunDocumentSymbol[]) => {
  const path: string[] = []
  let current = symbols
  while (true) {
    const next = current.find(item => item.defaultExpanded && item.children.length)
    if (!next) return path
    path.push(next.id)
    current = next.children
  }
}

const firstRunningTask = (symbols: RunDocumentSymbol[]): RunDocumentSymbol | null => {
  for (const item of symbols) {
    if (item.type === 'task' && item.status === 'running') return item
    const nested = firstRunningTask(item.children)
    if (nested) return nested
  }
  return null
}
watch(documentModel, model => {
  // The runtime may expose the current task before the user has selected a
  // symbol. Following that real active node keeps the Inspector useful while
  // leaving completed/pending Runs unselected.
  if (props.selectedSymbolId) {
    // Planning children may arrive after the click; reconcile the path so a
    // second click is not required to reveal the detail column.
    syncHorizontalPathForSelection(props.selectedSymbolId, model.symbols, false)
    return
  }
  if (props.selectedSemanticTaskKey) return
  const current = firstRunningTask(model.symbols)
  if (current) {
    const currentPath = parentPathFor(model.symbols, current.id)
    setHorizontalPath(
      currentPath
        ? current.children.length ? [...currentPath, current.id] : currentPath
        : horizontalPath.value,
      { scroll: false }
    )
    emit('selectSymbol', current)
    emit('selectSemanticTask', current.semanticTaskKey || null)
  } else if (!horizontalPath.value.length) {
    horizontalPath.value = defaultPathFor(model.symbols)
  }
}, { immediate: true })
watch(() => props.selectedSymbolId, selectedId => {
  activeSymbolId.value = selectedId || null
  syncHorizontalPathForSelection(selectedId)
}, { immediate: true })

const breadcrumbItems = computed(() => {
  const selected = findRunDocumentSymbol(documentModel.value.symbols, selectedSymbolIdForView.value)
  if (!selected) return []
  const path: RunDocumentSymbol[] = []
  const visit = (items: RunDocumentSymbol[]): boolean => {
    for (const item of items) {
      if (item.id === selected.id) { path.push(item); return true }
      if (visit(item.children)) { path.unshift(item); return true }
    }
    return false
  }
  visit(documentModel.value.symbols)
  return path
    .filter(item => !(item.type === 'result' && item.viewKey))
    .filter((item, index, items) => index === 0 || item.title !== items[index - 1].title)
})

const symbolEntry = (item: RunDocumentSymbol) => props.projection.entries.find(entry => (
  (item.artifactId && entry.artifactId === item.artifactId)
  || (item.artifactKey && entry.artifactKey === item.artifactKey)
  || (item.semanticTaskKey && entry.kind === 'task' && entry.semanticTaskKey === item.semanticTaskKey)
)) || null

const selectSymbol = (item: RunDocumentSymbol) => {
  activeSymbolId.value = item.id
  syncHorizontalPathForSelection(item.id)
  emit('selectSymbol', item)
  if (item.semanticTaskKey) emit('selectSemanticTask', item.semanticTaskKey)
  if (item.type === 'artifact') {
    const entry = symbolEntry(item)
    if (entry) emit('openArtifact', entry)
  }
}

const openSymbol = (item: RunDocumentSymbol) => {
  if (item.type === 'task' || item.type === 'acg-node') {
    emit('openSemanticTask', item.semanticTaskKey || null)
    return
  }
  if (item.type === 'artifact') {
    const entry = symbolEntry(item)
    if (entry) emit('openArtifact', entry)
  }
}

const openMission = () => {
  const mission = props.projection.entries.find(entry => entry.kind === 'virtual_document' && entry.name === 'mission.md')
    || {
      entryId: 'overview:mission.md', kind: 'virtual_document' as const, name: 'mission.md', title: 'mission.md', group: 'overview', displayOrder: 0,
      content: missionDocumentContent(props.projection)
    }
  emit('openEntry', mission)
}

const locateBreadcrumb = (id: string) => {
  if (id === 'mission') {
    openMission()
    return
  }
  if (id === 'run') return
  const item = findRunDocumentSymbol(documentModel.value.symbols, id)
  if (item) selectSymbol(item)
}

const captureGraphColumnWidth = async () => {
  if (!hasGraphColumn.value || graphColumnWidth.value !== null) return
  await nextTick()
  const column = scrollBody.value?.querySelector<HTMLElement>('.run-progress__column.is-graph-column')
  const width = column?.getBoundingClientRect().width || column?.offsetWidth || 0
  if (width > 0) graphColumnWidth.value = Math.round(width)
}
watch(hasGraphColumn, visible => {
  if (!visible) {
    graphColumnWidth.value = null
    return
  }
  void captureGraphColumnWidth()
}, { immediate: true })
const followLatest = ref(true)
let lastVerticalScrollTop = 0
const onScroll = () => {
  const el = scrollBody.value
  if (!el || Math.abs(el.scrollTop - lastVerticalScrollTop) < 1) return
  lastVerticalScrollTop = el.scrollTop
  followLatest.value = el.scrollHeight - el.scrollTop - el.clientHeight < 48
}
const scrollToLatest = async () => {
  followLatest.value = true
  await nextTick()
  const el = scrollBody.value
  if (el) el.scrollTop = el.scrollHeight
}
watch(documentModel, async () => {
  if (!followLatest.value) return
  await nextTick()
  const el = scrollBody.value
  if (el) el.scrollTop = el.scrollHeight
})
</script>

<style scoped>
.run-progress { --run-content-max: 1440px; --run-content-inset: clamp(18px, 2.4vw, 34px); display: flex; flex: 1 1 auto; flex-direction: column; width: 100%; height: 100%; min-width: 0; min-height: 0; color: var(--wb-text); }
.run-progress__document-head, .run-progress__toolbar { box-sizing: border-box; width: min(100%, var(--run-content-max)); margin-inline: auto; padding-inline: var(--run-content-inset); }
.run-progress__document-head { padding-bottom: 2px; }
.run-progress__header { display: grid; gap: 6px; padding-bottom: 14px; border-bottom: 1px solid var(--wb-border-soft); }
.run-progress__eyebrow { color: var(--wb-accent); font: 12px var(--font-mono, monospace); letter-spacing: .12em; }
.run-progress__heading-row { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.run-progress__heading-copy { min-width: 0; }
.run-progress__goal { margin: 0; color: var(--wb-text); font-size: 22px; font-weight: 650; line-height: 1.35; text-wrap: pretty; }
.run-progress__mission-link { flex: 0 0 auto; padding: 3px 0; border: 0; color: var(--wb-accent); background: transparent; cursor: pointer; font: 12px var(--font-mono, monospace); }
.run-progress__mission-link:hover { text-decoration: underline; }
.run-progress__meta { display: flex; align-items: baseline; flex-wrap: wrap; gap: 12px; margin-top: 4px; }
.run-progress__status { color: var(--wb-accent); font: 12px var(--font-mono, monospace); letter-spacing: .08em; }
.run-progress__status.is-completed { color: var(--wb-success); }
.run-progress__status.is-failed { color: var(--wb-danger); }
.run-progress__status.is-paused { color: var(--wb-warning); }
.run-progress__duration, .run-progress__runid { color: var(--wb-text-muted); font: 12px var(--font-mono, monospace); }
.run-progress__runid { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.run-progress__empty { display: grid; flex: 1; place-items: center; color: var(--wb-text-muted); font-size: 14px; }
.run-progress__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 0 7px; }
.run-progress__toolbar-leading { display: flex; align-items: center; min-width: 0; gap: 14px; }
.run-progress__toolbar-label { color: var(--wb-text-muted); font: 12px var(--font-mono, monospace); letter-spacing: .1em; }
.run-progress__directory { display: flex; align-items: center; min-width: 0; gap: 7px; overflow: hidden; color: var(--wb-text-muted); white-space: nowrap; }
.run-progress__directory-separator { flex: 0 0 auto; color: var(--wb-border-strong); font: 13px var(--font-mono, monospace); }
.run-progress__directory-item { max-width: 220px; overflow: hidden; padding: 2px 0; border: 0; color: var(--wb-text-muted); background: transparent; cursor: pointer; font: 12px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.run-progress__directory-item:hover, .run-progress__directory-item:focus-visible { color: var(--wb-accent); outline: 0; }
.run-progress__directory-item.is-current { color: var(--wb-text-secondary); }
.run-progress__filter { display: flex; align-items: center; gap: 7px; color: var(--wb-text-muted); font: 12px var(--font-mono, monospace); }
.run-progress__filter input { width: 145px; padding: 5px 8px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); outline: 0; color: var(--wb-text-secondary); background: var(--wb-surface-inset); font: 12px var(--font-mono, monospace); }
.run-progress__filter input:focus { border-color: var(--wb-accent); }
@media (max-width: 760px) {
  .run-progress__toolbar { align-items: flex-start; flex-direction: column; }
  .run-progress__toolbar-leading { width: 100%; }
  .run-progress__directory { flex: 1 1 auto; }
  .run-progress__filter { align-self: flex-end; }
}
.run-progress__body { position: relative; display: flex; flex: 1; flex-direction: column; min-height: 0; overflow: auto; }
.run-progress__body.is-graph-mode { overflow-x: auto; overflow-y: hidden; overscroll-behavior: contain; }
.run-progress__stream { box-sizing: border-box; display: flex; flex: 1 0 auto; flex-direction: column; width: max-content; min-width: 100%; min-height: 100%; padding-bottom: 42px; }
.run-progress__browser { display: flex; flex: 1 0 auto; align-items: stretch; min-width: 100%; min-height: 100%; padding-inline: var(--run-content-inset); }
.run-progress__column { flex: 0 0 clamp(280px, 30vw, 380px); align-self: stretch; min-width: 0; min-height: 100%; border-right: 1px solid var(--wb-border-soft); }
.run-progress__column.is-detail-column { position: relative; flex-basis: clamp(400px, 34vw, 560px); }
.run-progress__column.is-graph-column { display: flex; flex: 1 1 0; flex-direction: column; min-width: 0; }
.run-progress__body.is-graph-mode .run-progress__stream,
.run-progress__body.is-graph-mode .run-progress__browser,
.run-progress__body.is-graph-mode .run-progress__column { min-height: 0; height: 100%; }
.run-progress__body.is-graph-mode .run-progress__stream { flex: 1 1 auto; padding-bottom: 0; }
.run-progress__column:first-child { border-left: 1px solid var(--wb-border-soft); }
.run-progress__column-head { padding: 10px 12px 9px; border-bottom: 1px solid var(--wb-border-soft); color: var(--wb-text-muted); font: 12px var(--font-mono, monospace); letter-spacing: .1em; }
.run-progress__resize-handle { position: absolute; z-index: 3; top: 0; bottom: 0; left: -5px; width: 10px; cursor: col-resize; touch-action: none; }
.run-progress__resize-handle::after { position: absolute; top: 0; bottom: 0; left: 4px; width: 1px; background: var(--wb-accent); content: ''; opacity: 0; transition: opacity .15s ease; }
.run-progress__resize-handle:hover::after, .run-progress__resize-handle:focus-visible::after { opacity: .75; }
.run-progress__resize-handle:focus-visible { outline: 1px solid var(--wb-accent); outline-offset: -1px; }
.run-progress__column-body { padding: 4px 8px 24px; }
.run-progress__column-body.is-terminal-body { padding: 14px 16px 28px; }
.run-progress__terminal-summary { padding: 1px 0 15px; border-bottom: 1px solid var(--wb-border-soft); }
.run-progress__terminal-summary-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.run-progress__terminal-eyebrow { color: var(--wb-accent); font: 10px var(--font-mono, monospace); letter-spacing: .1em; }
.run-progress__terminal-status { display: inline-flex; align-items: center; gap: 5px; padding: 3px 7px; border: 1px solid color-mix(in srgb, var(--wb-border-strong) 72%, transparent); border-radius: 999px; color: var(--wb-text-muted); font: 11px var(--font-mono, monospace); white-space: nowrap; }
.run-progress__terminal-status.is-running { border-color: color-mix(in srgb, var(--wb-accent) 34%, var(--wb-border)); color: var(--wb-accent); }
.run-progress__terminal-status.is-completed { border-color: color-mix(in srgb, var(--wb-success) 34%, var(--wb-border)); color: var(--wb-success); }
.run-progress__terminal-status.is-warning { border-color: color-mix(in srgb, var(--wb-warning) 34%, var(--wb-border)); color: var(--wb-warning); }
.run-progress__terminal-status.is-failed { border-color: color-mix(in srgb, var(--wb-danger) 34%, var(--wb-border)); color: var(--wb-danger); }
.run-progress__terminal-summary h2 { margin: 10px 0 0; color: var(--wb-text); font-size: 16px; font-weight: 650; line-height: 1.4; overflow-wrap: anywhere; }
.run-progress__terminal-detail { margin: 7px 0 0; color: var(--wb-text-secondary); font-size: 12px; line-height: 1.55; overflow-wrap: anywhere; }
.run-progress__terminal-summary-copy { margin: 6px 0 0; color: var(--wb-text-secondary); font-size: 12px; line-height: 1.5; }
.run-progress__terminal-metrics { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 13px 0 0; border-top: 1px solid var(--wb-border-soft); }
.run-progress__terminal-metrics > div { min-width: 0; padding: 9px 0 1px; }
.run-progress__terminal-metrics > div:nth-child(odd) { padding-right: 14px; }
.run-progress__terminal-metrics > div:nth-child(even) { padding-left: 14px; border-left: 1px solid var(--wb-border-soft); }
.run-progress__terminal-metrics > div:nth-child(n + 3) { border-top: 1px solid var(--wb-border-soft); }
.run-progress__terminal-metrics dt { color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.run-progress__terminal-metrics dd { min-width: 0; margin: 4px 0 0; overflow: hidden; color: var(--wb-text-secondary); font: 11px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.run-progress__activity-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; margin: 20px 2px 7px; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); letter-spacing: .1em; }
.run-progress__activity-heading small { color: var(--wb-text-muted); font: 11px var(--font-mono, monospace); letter-spacing: 0; }
.run-progress__activity-empty { margin: 0; padding: 10px 0; border-bottom: 1px solid var(--wb-border-soft); color: var(--wb-text-muted); font-size: 12px; }
.run-progress__column-body.is-terminal-body :deep(.run-symbol) { border-bottom: 1px solid var(--wb-border-soft); background: transparent; }
.run-progress__column-body.is-terminal-body :deep(.run-symbol:first-of-type) { border-top: 1px solid var(--wb-border-soft); }
.run-progress__column-body.is-terminal-body :deep(.run-symbol + .run-symbol) { margin-top: 0; }
.run-progress__column-body.is-terminal-body :deep(.editor-object-row) { min-height: 42px; }
.run-progress__graph-preview { display: flex; flex: 1 1 auto; height: auto; min-height: 540px; overflow: hidden; }
.run-progress__body.is-graph-mode .run-progress__graph-preview { min-height: 0; height: auto; }
.run-progress__graph-preview :deep(.acg-topology) { height: 100%; min-height: 0; border: 0; border-radius: 0; box-shadow: none; }
.run-progress__detail { padding: 14px 16px 24px; }
.run-progress__detail-status { display: flex; align-items: center; gap: 8px; min-height: 28px; color: var(--wb-text); }
.run-progress__detail-status strong { font-size: 14px; font-weight: 650; }
.run-progress__detail-mark { width: 14px; color: var(--wb-text-muted); font: 13px var(--font-mono, monospace); text-align: center; }
.run-progress__detail-mark.is-running { color: var(--wb-accent); }
.run-progress__detail-mark.is-completed { color: var(--wb-success); }
.run-progress__detail-mark.is-warning { color: var(--wb-warning); }
.run-progress__detail-mark.is-failed { color: var(--wb-danger); }
.run-progress__detail-summary { margin: 5px 0 14px; color: var(--wb-text-secondary); font-size: 13px; line-height: 1.5; }
.run-progress__detail-list { margin: 0; border-top: 1px solid var(--wb-border-soft); }
.run-progress__detail-list > div { display: grid; grid-template-columns: minmax(80px, .65fr) minmax(0, 1.35fr); gap: 12px; padding: 8px 0; border-bottom: 1px solid var(--wb-border-soft); }
.run-progress__detail-list dt { color: var(--wb-text-muted); font: 12px var(--font-mono, monospace); }
.run-progress__detail-list dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: var(--wb-text-secondary); font: 12px/1.45 var(--font-mono, monospace); }
.run-progress__detail-content { max-height: 360px; margin: 14px 0 0; padding: 10px 0; overflow: auto; border-top: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: transparent; font: 12px/1.5 var(--font-mono, monospace); white-space: pre-wrap; overflow-wrap: anywhere; }
.run-progress__waiting { padding: 16px var(--run-content-inset); color: var(--wb-text-muted); font-size: 14px; }
.run-progress__follow { position: sticky; bottom: 10px; display: block; margin: 0 auto; padding: 6px 15px; border: 1px solid color-mix(in srgb, var(--wb-accent) 34%, var(--wb-border)); border-radius: 999px; color: var(--wb-accent); background: var(--wb-surface-2); cursor: pointer; font-size: 12px; box-shadow: 0 2px 8px rgb(0 0 0 / 18%); }

@media (max-width: 680px) {
  .run-progress { --run-content-inset: 16px; }
  .run-progress__column.is-graph-column { min-width: 520px; }
  .run-progress__heading-row { display: grid; gap: 8px; }
  .run-progress__mission-link { justify-self: start; }
}
</style>
