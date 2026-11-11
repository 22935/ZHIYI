<!-- ACG 拓扑图 — 主执行链用 AcgExecutionFlow 渲染，异常路径回退 vis-network 画布，含步骤、控制节点和图例 -->
<!-- 注：蓝图内核自 2026-09 a5011660 收敛后只产 step/control 节点与 dependency 边（后端 EdgeType 枚举仅剩依赖），
     旧「完整拓扑/数据流」页签、关系筛选与 agent/skill/memory/evidence 死类型样式已随之移除，勿凭旧印象恢复 -->
<template>
  <section ref="sectionRef" class="acg-topology ui-surface" :class="{ 'is-workbench': workbench }">
    <header class="panel-head">
      <div class="head-left">
        <el-icon class="head-icon"><Share /></el-icon>
        <h4>ACG 拓扑图</h4>
      </div>
      <div class="head-right">
        <span class="meta" v-if="hasData">{{ stats }}</span>
        <div class="action-group">
          <button v-if="hasData" class="action-btn" type="button" @click="resetView()" title="复位视图" aria-label="复位拓扑视图">
            <el-icon><RefreshRight /></el-icon>
          </button>
          <button
            v-if="hasData && fullscreenSupported"
            class="action-btn"
            :class="{ active: isFullscreen }"
            type="button"
            :title="isFullscreen ? '退出全屏' : '全屏显示'"
            :aria-label="isFullscreen ? '退出全屏显示' : '全屏显示拓扑'"
            @click="toggleFullscreen"
          >
            <el-icon><Close v-if="isFullscreen" /><FullScreen v-else /></el-icon>
          </button>
          <button
            v-if="collapsible"
            class="action-btn"
            type="button"
            aria-label="收起 ACG 拓扑"
            title="收起 ACG 拓扑"
            @click="emit('collapse')"
          >
            <el-icon><ArrowDownBold /></el-icon>
          </button>
        </div>
      </div>
    </header>

    <div v-if="!hasData" class="empty">
      <span class="empty__badge" aria-hidden="true"><el-icon><Share /></el-icon></span>
      <p class="empty__title">暂无 ACG 拓扑数据</p>
      <p class="empty__hint">启动一个 ACG 引擎工作流后，这里会呈现任务步骤的执行拓扑。</p>
    </div>
    <div v-else class="graph-surface">
      <div class="graph-toolbar" aria-label="拓扑分析视图">
        <div class="view-mode">
          <button type="button" :class="{ active: viewMode === 'main' }" @click="setViewMode('main')">主执行链</button>
          <button type="button" :class="{ active: viewMode === 'exceptions' }" @click="setViewMode('exceptions')">异常路径</button>
        </div>
        <div v-if="focusMainPath" class="execution-context__scope" role="group" aria-label="执行链范围切换">
          <button type="button" :class="{ active: localScope }" :aria-pressed="localScope" @click="setExecutionScope(true)">当前步骤及关联</button>
          <button type="button" :class="{ active: !localScope }" :aria-pressed="!localScope" @click="setExecutionScope(false)">全部步骤</button>
          <span v-if="localScope && contextAnchorId" class="execution-context__anchor" :title="`焦点步骤：${contextAnchorName}`">
            焦点：{{ contextAnchorName }}
          </span>
        </div>
      </div>
      <div class="graph-stage" :class="{ 'has-detail': detailAsideVisible }">
        <div v-if="focusMainPath && visibleBlueprint" class="graph-canvas">
          <AcgExecutionFlow ref="executionFlow" :blueprint="visibleBlueprint" :positions="executionPositions"
            :selected-id="detailAsideOpen ? '' : selectedNodeId" :anchor-id="contextAnchorId" :statuses="flowStatuses"
            @select="onFlowSelect" @double-click="emit('nodeDoubleClicked', $event)" @zoom="zoomPercent = $event">
            <template #detail>
        <article v-if="umlCardVisible" class="uml-card execution-detail" :data-node-id="selectedNodeId" aria-label="节点详情卡片">
          <header class="uml-card__head">
            <strong class="uml-card__title">{{ selectedNode?.name || selectedNode?.nodeId }}</strong>
            <span class="uml-card__status" :data-status="selectedNodeStatus">{{ runtimeStatusLabel(selectedNodeStatus) }}</span>
            <button type="button" class="uml-card__close" title="收起详情" aria-label="收起节点详情" @click="clearSelection">
              <el-icon><Close /></el-icon>
            </button>
          </header>
          <div class="uml-card__body">
            <p v-if="cardObjective" class="uml-card__objective">{{ cardObjective }}</p>
            <section class="uml-card__section">
              <h6>Token 消耗<em v-if="selectedTokenUsage">{{ selectedTokenUsage.calls }} 次调用</em></h6>
              <p v-if="tokenUsageLoading" class="uml-card__empty">正在读取模型调用记录…</p>
              <p v-else-if="!props.runId" class="uml-card__empty">当前视图未关联 Run，无模型调用记录</p>
              <p v-else-if="tokenUsageError" class="uml-card__empty">{{ tokenUsageError }}</p>
              <p v-else-if="!selectedTokenUsage" class="uml-card__empty">未观测到模型调用</p>
              <template v-else>
                <div class="uml-card__tokens">
                  <div><b>{{ formatTokenCount(Math.max(0, selectedTokenUsage.inputTokens - selectedTokenUsage.cacheReadTokens)) }}</b><span>输入·未命中</span></div>
                  <div><b>{{ formatTokenCount(selectedTokenUsage.cacheReadTokens) }}</b><span>输入·缓存</span></div>
                  <div><b>{{ formatTokenCount(selectedTokenUsage.outputTokens) }}</b><span>输出</span></div>
                  <div><b>{{ formatTokenCount(selectedTokenUsage.totalTokens) }}</b><span>合计</span></div>
                </div>
                <p v-if="selectedTokenUsage.models.length" class="uml-card__models">{{ selectedTokenUsage.models.join(' · ') }}</p>
              </template>
            </section>
            <section class="uml-card__section">
              <h6>产物</h6>
              <p v-if="selectedStepState?.outputSummary">{{ selectedStepState.outputSummary }}</p>
              <p v-else class="uml-card__empty">{{ ['completed'].includes(selectedNodeStatus) ? '暂无产物摘要' : '尚未产出' }}</p>
            </section>
            <section v-if="cardAgentLabel || selectedStepState?.resourceUse?.modelId || selectedStepState?.attempt" class="uml-card__section uml-card__meta">
              <span v-if="cardAgentLabel">Agent · {{ cardAgentLabel }}</span>
              <span v-if="selectedStepState?.resourceUse?.modelId">模型 · {{ selectedStepState.resourceUse.modelId }}</span>
              <span v-if="selectedStepState">Attempt · {{ selectedStepState.attempt }}</span>
            </section>
            <section class="uml-card__section">
              <h6>依赖</h6>
              <div class="uml-card__deps">
                <div class="uml-card__dep-group">
                  <span>输入 · {{ incomingConnections.length }}</span>
                  <button
                    v-for="edge in incomingConnections.slice(0, 4)"
                    :key="edge.edgeId"
                    type="button"
                    :title="peerNodeName(edge.sourceId)"
                    @click="selectRelatedNode(edge.sourceId)"
                  >{{ peerNodeName(edge.sourceId) }}</button>
                  <em v-if="incomingConnections.length > 4">+{{ incomingConnections.length - 4 }}</em>
                </div>
                <div class="uml-card__dep-group">
                  <span>输出 · {{ outgoingConnections.length }}</span>
                  <button
                    v-for="edge in outgoingConnections.slice(0, 4)"
                    :key="edge.edgeId"
                    type="button"
                    :title="peerNodeName(edge.targetId)"
                    @click="selectRelatedNode(edge.targetId)"
                  >{{ peerNodeName(edge.targetId) }}</button>
                  <em v-if="outgoingConnections.length > 4">+{{ outgoingConnections.length - 4 }}</em>
                </div>
              </div>
            </section>
            <button v-if="selectedStepState" type="button" class="uml-card__more" @click="detailAsideOpen = true">完整详情</button>
          </div>
        </article>
            </template>
          </AcgExecutionFlow>
        </div>
        <div v-else ref="graphRef" class="graph-canvas" />
        <p v-if="viewHint" class="view-hint">{{ viewHint }}</p>
        <aside v-if="detailAsideVisible" class="node-detail" aria-label="节点详情">
        <header>
          <div>
            <span>{{ nodeTypeLabel(selectedNode.nodeType) }}</span>
            <h5>{{ selectedNode.name || selectedNode.nodeId }}</h5>
          </div>
          <button type="button" title="关闭节点详情" aria-label="关闭节点详情" @click="clearSelection">
            <el-icon><Close /></el-icon>
          </button>
        </header>
        <dl>
          <div><dt>节点 ID</dt><dd><code>{{ selectedNode.nodeId }}</code></dd></div>
          <div v-if="selectedStepState?.task"><dt>子任务号</dt><dd><code>{{ selectedStepState.task.taskId }}</code></dd></div>
          <div v-if="selectedStepState?.task"><dt>语义标题</dt><dd>{{ selectedStepState.task.title }}</dd></div>
          <div v-if="selectedNodeStatus"><dt>运行状态</dt><dd class="node-status" :class="selectedNodeStatus">{{ runtimeStatusLabel(selectedNodeStatus) }}</dd></div>
          <div v-if="selectedStepState?.agentName || selectedNode.agentName"><dt>Agent</dt><dd>{{ selectedStepState?.agentName || selectedNode.agentName }}</dd></div>
          <div v-if="selectedNode.capability"><dt>能力</dt><dd>{{ selectedNode.capability }}</dd></div>
          <div v-if="selectedStepState?.resourceUse"><dt>使用资源</dt><dd><code>{{ bindingLabel(selectedStepState.resourceUse) }}</code></dd></div>
          <div v-if="selectedStepState?.resourceUse?.modelId"><dt>模型</dt><dd>{{ selectedStepState.resourceUse.modelId }}</dd></div>
          <div v-if="selectedStepState?.attempt"><dt>Attempt</dt><dd>{{ selectedStepState.attempt }} 次</dd></div>
          <div v-if="selectedStepState?.createdGraphVersion"><dt>创建图版本</dt><dd>v{{ selectedStepState.createdGraphVersion }}</dd></div>
          <div v-if="selectedAllowedSkills.length">
            <dt>可用技能</dt>
            <dd class="skill-list"><code v-for="skill in selectedAllowedSkills" :key="skill">{{ skill }}</code></dd>
          </div>
          <div v-if="selectedNode.controlType"><dt>控制类型</dt><dd>{{ controlTypeLabel(selectedNode.controlType) }}</dd></div>
        </dl>
        <p v-if="selectedStepState?.task?.objective || selectedNode.goal || selectedNode.description" class="node-description">
          {{ selectedStepState?.task?.objective || selectedNode.goal || selectedNode.description }}
        </p>
        <div v-if="selectedStepState?.nodeExecutions?.length" class="runtime-detail-group execution-history">
          <strong>节点生命周期 · {{ selectedStepState.nodeExecutions.length }}</strong>
          <article v-for="record in selectedStepState.nodeExecutions" :key="record.sequence">
            <span>{{ phaseLabel(record.phase) }}</span>
            <code>Attempt {{ record.attemptId }}</code>
            <span v-if="record.failureCode" class="failure">{{ record.failureCode }}</span>
          </article>
        </div>
        <p v-else-if="selectedNode.nodeType === 'step'" class="projection-pending">Identity 执行记录尚未投影</p>
        <div v-if="selectedStepState?.stepExecutions?.length" class="runtime-detail-group">
          <strong>StepExecution · {{ selectedStepState.stepExecutions.length }}</strong>
          <span v-for="execution in selectedStepState.stepExecutions" :key="execution.stepExecutionId">
            {{ execution.stepExecutionId }} · {{ execution.status }}
          </span>
        </div>
        <div v-if="selectedStepState?.attempts?.length" class="runtime-detail-group">
          <strong>Attempt 历史 · {{ selectedStepState.attempts.length }}</strong>
          <span v-for="attempt in selectedStepState.attempts" :key="attempt.attemptId">
            #{{ attempt.attemptNumber }} · {{ attempt.status }} · {{ attempt.agentName || '未观察到 Agent' }}
          </span>
        </div>

        <p v-if="selectedStepState?.errorSummary" class="runtime-summary is-error">{{ selectedStepState.errorSummary }}</p>
        <p v-if="selectedStepState?.outputSummary" class="runtime-summary">{{ selectedStepState.outputSummary }}</p>
        <div class="connection-group">
          <strong>输入关系 · {{ incomingConnections.length }}</strong>
          <span v-if="!incomingConnections.length">无</span>
          <button v-for="edge in incomingConnections" :key="edge.edgeId" type="button" @click="selectRelatedNode(edge.sourceId)">
            <small>{{ edgeTypeLabel(edge.edgeType) }}</small>{{ edge.sourceId }}
          </button>
        </div>
        <div class="connection-group">
          <strong>输出关系 · {{ outgoingConnections.length }}</strong>
          <span v-if="!outgoingConnections.length">无</span>
          <button v-for="edge in outgoingConnections" :key="edge.edgeId" type="button" @click="selectRelatedNode(edge.targetId)">
            <small>{{ edgeTypeLabel(edge.edgeType) }}</small>{{ edge.targetId }}
          </button>
        </div>
        </aside>
        <div ref="fabRef" class="graph-fab" :class="{ expanded: controlsExpanded }" :style="!controlsExpanded && fabPos ? { left: `${fabPos.x}px`, top: `${fabPos.y}px`, right: 'auto', bottom: 'auto' } : undefined">
          <div v-if="controlsExpanded" class="graph-fab__panel">
            <div class="legend">
              <div class="legend-group">
                <span class="legend-label">节点类型</span>
                <span class="legend-item"><i class="dot step"></i>步骤</span>
                <span class="legend-item"><i class="dot control"></i>控制</span>
              </div>
              <div class="legend-group">
                <span class="legend-label">运行状态</span>
                <span class="legend-item"><i class="ring done"></i>已完成</span>
                <span class="legend-item"><i class="ring running"></i>执行中</span>
                <span class="legend-item"><i class="ring waiting"></i>待审核/重试</span>
                <span class="legend-item"><i class="ring failed"></i>失败</span>
              </div>
              <div class="legend-group legend-group--notes">
                <span class="legend-label">运行注记</span>
                <span class="legend-item"><b class="badge runtime">+</b>运行时新增</span>
                <span class="legend-item"><b class="badge binding">⇄</b>切换 Binding</span>
                <span class="legend-item"><b class="badge skipped">Skipped</b>条件跳过</span>
              </div>
            </div>
            <div class="canvas-controls" aria-label="画布控制">
              <button type="button" class="canvas-controls__text" @click="showOverview">全图总览</button>
              <button type="button" class="canvas-controls__text" @click="actualSize">实际大小</button>
              <button v-if="focusMainPath" type="button" class="canvas-controls__text" :disabled="!currentTaskId" @click="locateCurrentTask">定位任务</button>
              <button type="button" title="缩小" aria-label="缩小拓扑" @click="zoomGraph(0.86)"><el-icon><Minus /></el-icon></button>
              <span class="canvas-controls__scale" aria-label="缩放比例">{{ zoomPercent }}%</span>
              <button type="button" title="放大" aria-label="放大拓扑" @click="zoomGraph(1.16)"><el-icon><Plus /></el-icon></button>
            </div>
          </div>
          <button type="button" class="graph-fab__ball" :aria-expanded="controlsExpanded" :aria-label="controlsExpanded ? '收起画布控制' : '展开画布控制'" @pointerdown="onFabBallPointerDown" @pointermove="onFabBallPointerMove" @pointerup="onFabBallPointerUp" @pointercancel="onFabBallPointerUp" @click="toggleControls">
            <el-icon class="graph-fab__ball-icon"><Share /></el-icon>
            <i class="graph-fab__ball-divider" aria-hidden="true"></i>
            <el-icon class="graph-fab__ball-icon"><Close v-if="controlsExpanded" /><Aim v-else /></el-icon>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Aim, ArrowDownBold, Close, FullScreen, Minus, Plus, RefreshRight, Share } from '@element-plus/icons-vue'
import AcgExecutionFlow from './AcgExecutionFlow.vue'
import { DataSet } from 'vis-data'
import { Network } from 'vis-network'
import type { GraphProjection, AcgNode, AcgEdge, AcgStepState } from '@/services/api/agentos'
import { workflowApi } from '@/services/api/workflow'
import { mapEdgeVisualState, mapNodeVisualState } from '@/utils/acgGraphPresentation'
import { edgeActivationOpacity, graphEdgeWidth, mixGraphColor } from '@/utils/acgGraphVisuals'
import { executionLayout, executionNodeLabel } from '@/utils/acgExecutionLayout'

const props = defineProps<{
  blueprint: GraphProjection | null
  completedStepIds?: string[]
  stepStates?: AcgStepState[]
  collapsible?: boolean
  workbench?: boolean
  focusNodeId?: string | null
  runtimePhases?: Record<string, string>
  /** 关联的 Run：提供后节点详情卡片可以展示逐节点模型调用与 Token 用量 */
  runId?: string | null
  /** 容器尺寸变化时保持缩放并重定位视图（仅独立编辑器画布开启；内嵌多列场景会与列宽布局互相干扰） */
  observeResize?: boolean
}>()

const emit = defineEmits<{
  collapse: []
  nodeSelected: [nodeId: string]
  nodeDoubleClicked: [nodeId: string]
}>()

const graphRef = ref<HTMLElement | null>(null)
const sectionRef = ref<HTMLElement | null>(null)
const executionFlow = ref<InstanceType<typeof AcgExecutionFlow> | null>(null)
const selectedNodeId = ref('')
type GraphViewMode = 'main' | 'exceptions'
const viewMode = ref<GraphViewMode>('main')
const focusMainPath = computed(() => viewMode.value === 'main')
const localScope = ref(Boolean(props.workbench && props.observeResize))
const contextNodeId = ref('')
const zoomPercent = ref(100)
const controlsExpanded = ref(false)
const fabRef = ref<HTMLElement | null>(null)
const FAB_POSITION_KEY = 'acg.graph.fab.position'
const fabPos = ref<{ x: number; y: number } | null>(null)
try {
  const savedFabPos = JSON.parse(localStorage.getItem(FAB_POSITION_KEY) || 'null')
  if (savedFabPos && Number.isFinite(savedFabPos.x) && Number.isFinite(savedFabPos.y)) fabPos.value = savedFabPos
} catch {}
let fabDrag: { startX: number; startY: number; baseX: number; baseY: number; moved: boolean } | null = null
let suppressFabClick = false
const onFabBallPointerDown = (e: PointerEvent) => {
  if (controlsExpanded.value) return
  const el = fabRef.value
  const parent = el?.offsetParent as HTMLElement | null
  if (!el || !parent) return
  const base = fabPos.value ?? (() => {
    const er = el.getBoundingClientRect()
    const pr = parent.getBoundingClientRect()
    return { x: er.left - pr.left, y: er.top - pr.top }
  })()
  fabDrag = { startX: e.clientX, startY: e.clientY, baseX: base.x, baseY: base.y, moved: false }
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
}
const onFabBallPointerMove = (e: PointerEvent) => {
  if (!fabDrag) return
  const el = fabRef.value
  const parent = el?.offsetParent as HTMLElement | null
  if (!el || !parent) return
  const dx = e.clientX - fabDrag.startX
  const dy = e.clientY - fabDrag.startY
  if (!fabDrag.moved && Math.hypot(dx, dy) < 4) return
  fabDrag.moved = true
  const maxX = Math.max(0, parent.clientWidth - el.offsetWidth)
  const maxY = Math.max(0, parent.clientHeight - el.offsetHeight)
  fabPos.value = {
    x: Math.min(maxX, Math.max(0, fabDrag.baseX + dx)),
    y: Math.min(maxY, Math.max(0, fabDrag.baseY + dy)),
  }
}
const onFabBallPointerUp = () => {
  if (!fabDrag) return
  const moved = fabDrag.moved
  fabDrag = null
  if (moved && fabPos.value) {
    suppressFabClick = true
    try { localStorage.setItem(FAB_POSITION_KEY, JSON.stringify(fabPos.value)) } catch {}
  }
}
const toggleControls = () => {
  if (suppressFabClick) {
    suppressFabClick = false
    return
  }
  controlsExpanded.value = !controlsExpanded.value
}
const isFullscreen = ref(false)
const fullscreenSupported = typeof document !== 'undefined' && typeof document.documentElement.requestFullscreen === 'function'
let network: Network | null = null
let nodesData: DataSet<any> | null = null
let edgesData: DataSet<any> | null = null
let graphStructureKey = ''
let graphDataKey = ''
let stabilizationTimer: number | undefined
let themeObserver: MutationObserver | null = null
let renderRequest = 0
let renderTimer: number | undefined
let layoutFinalized = false
let pendingViewState: { position: { x: number; y: number }; scale: number } | null = null
let graphResizeObserver: ResizeObserver | null = null
let graphResizeTarget: Element | null = null
let graphResizeTimer: number | undefined
let graphResizeFrame: number | undefined

const ENDPOINT_MIN_GAP = 190
const ENDPOINT_MAX_GAP = 280
// vis-network.fit() already keeps the full graph inside the canvas. Retain only
// a slight optical inset so the topology reads as the primary canvas content.
const SAFE_VIEW_SCALE = 0.98

// 蓝图内核自 a5011660 收敛后只产 step/control 节点与 dependency 边（后端 EdgeType 枚举仅剩依赖）
const EDGE_TYPES: Array<{ value: AcgEdge['edgeType']; label: string }> = [
  { value: 'dependency', label: '依赖' }
]

const hasData = computed(() => {
  return !!props.blueprint && Array.isArray(props.blueprint.nodes) && props.blueprint.nodes.length > 0
})

const executionBlueprint = computed<GraphProjection | null>(() => {
  const blueprint = props.blueprint
  if (!blueprint) return null
  const nodes = blueprint.nodes.filter(node => node.nodeType === 'step' || node.nodeType === 'control')
  const nodeIds = new Set(nodes.map(node => node.nodeId))
  const edges = blueprint.edges.filter(edge =>
    edge.edgeType === 'dependency'
    && nodeIds.has(edge.sourceId)
    && nodeIds.has(edge.targetId)
  )
  return { ...blueprint, nodes, edges }
})

const nodeStatus = (id: string) => {
  const status = String(props.runtimePhases?.[id]
    || props.stepStates?.find(state => state.stepId === id)?.status
    || (props.completedStepIds?.includes(id) ? 'completed' : 'pending')).toLowerCase()
  return ['model_starting', 'streaming', 'finalizing'].includes(status) ? 'running'
    : status === 'waiting' ? 'pending' : status
}
const runtimeStatusLabel = (status: string) => ({
  completed: '已完成', running: '运行中', retrying: '重试中', waiting_review: '待审核',
  failed: '失败', cancelled: '已取消', skipped_by_condition: '已跳过', pending: '待执行',
  prepared: '已准备', executed: '已执行', audited: '已审计', committed: '已提交'
} as Record<string, string>)[status || 'pending'] || status
const currentTaskId = computed(() => {
  const nodes = executionBlueprint.value?.nodes || []
  const steps = nodes.filter(node => node.nodeType === 'step')
  return steps.find(node => ['running', 'retrying', 'waiting_review'].includes(nodeStatus(node.nodeId)))?.nodeId
    || steps.find(node => nodeStatus(node.nodeId) === 'failed')?.nodeId
    || steps.find(node => !['completed', 'cancelled', 'skipped_by_condition'].includes(nodeStatus(node.nodeId)))?.nodeId
    || steps[steps.length - 1]?.nodeId || nodes[0]?.nodeId || ''
})
const contextAnchorId = computed(() => {
  const nodes = executionBlueprint.value?.nodes || []
  const requested = contextNodeId.value || props.focusNodeId
  return nodes.some(node => node.nodeId === requested) ? requested! : currentTaskId.value
})
const contextAnchorName = computed(() =>
  executionBlueprint.value?.nodes.find(node => node.nodeId === contextAnchorId.value)?.name || contextAnchorId.value)
// Use positions from the whole execution graph so stepping through adjacent tasks does not shuffle columns.
const executionPositions = computed(() => {
  const parents = new Map<string, string>()
  for (const state of props.stepStates || []) {
    if (state.task?.parentTaskId) parents.set(state.stepId, state.task.parentTaskId)
  }
  return executionLayout(executionBlueprint.value?.nodes || [], executionBlueprint.value?.edges || [], parents)
})

const visibleBlueprint = computed<GraphProjection | null>(() => {
  const blueprint = props.blueprint
  if (!blueprint) return null
  if (viewMode.value === 'main') {
    const execution = executionBlueprint.value!
    if (!localScope.value || !contextAnchorId.value) return execution
    const ids = new Set([contextAnchorId.value])
    for (const edge of execution.edges) {
      if (edge.sourceId === contextAnchorId.value) ids.add(edge.targetId)
      if (edge.targetId === contextAnchorId.value) ids.add(edge.sourceId)
    }
    return { ...execution, nodes: execution.nodes.filter(node => ids.has(node.nodeId)),
      edges: execution.edges.filter(edge => ids.has(edge.sourceId) && ids.has(edge.targetId)) }
  }

  if (viewMode.value === 'exceptions') {
    const abnormalStatuses = new Set(['failed', 'waiting_review', 'retrying', 'cancelled'])
    const abnormalIds = new Set(
      (props.stepStates || [])
        .filter(state => abnormalStatuses.has(String(state.status || '')) || Boolean(state.errorSummary))
        .map(state => state.stepId)
    )
    const edges = blueprint.edges.filter(edge => abnormalIds.has(edge.sourceId) || abnormalIds.has(edge.targetId))
    const nodeIds = new Set([...abnormalIds, ...edges.flatMap(edge => [edge.sourceId, edge.targetId])])
    const nodes = blueprint.nodes.filter(node => nodeIds.has(node.nodeId))
    return { ...blueprint, nodes, edges }
  }

  return blueprint
})

const viewHint = computed(() => {
  if (viewMode.value === 'exceptions' && !visibleBlueprint.value?.nodes.length) return '当前运行没有异常路径'
  return ''
})

const selectedNode = computed(() =>
  props.blueprint?.nodes.find(node => node.nodeId === selectedNodeId.value) || null
)
const selectedAllowedSkills = computed(() => {
  const value = selectedNode.value?.display?.allowedSkills
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
})
const stateByStep = computed(() => new Map((props.stepStates || []).map(item => [item.stepId, item])))
const selectedStepState = computed(() => selectedNode.value ? stateByStep.value.get(selectedNode.value.nodeId) : undefined)
const selectedNodeStatus = computed(() => {
  if (!selectedNode.value) return ''
  return nodeStatus(selectedNode.value.nodeId)
})
const bindingLabel = (binding: import('@/services/api/agentos').ResourceUseQuery) =>
  String(binding.agentId || binding.resourceId)
const phaseLabel = (phase: string) => ({
  prepared: '已准备', executed: '已执行', audited: '已审计', committed: '已提交',
  waiting_review: '待审核', failed: '失败', cancelled: '已取消'
}[phase] || phase)
const controlTypeLabel = (value: string) => ({
  start: 'START', end: 'END', if: 'IF', parallel: 'PARALLEL', loop: 'LOOP',
  consensus: 'CONSENSUS', debate: 'DEBATE'
}[value.toLowerCase()] || `${value}（未识别）`)
const incomingConnections = computed(() =>
  (focusMainPath.value ? executionBlueprint.value : visibleBlueprint.value)?.edges.filter(edge => edge.targetId === selectedNodeId.value) || []
)
const outgoingConnections = computed(() =>
  (focusMainPath.value ? executionBlueprint.value : visibleBlueprint.value)?.edges.filter(edge => edge.sourceId === selectedNodeId.value) || []
)

// Detail data is shared with the Vue Flow execution node.
interface NodeTokenUsage {
  calls: number
  inputTokens: number
  cacheReadTokens: number
  outputTokens: number
  totalTokens: number
  models: string[]
}
const tokenByStep = ref(new Map<string, NodeTokenUsage>())
const tokenUsageLoading = ref(false)
const tokenUsageError = ref('')
const tokenUsageRunId = ref('')
let tokenUsageGeneration = 0

const loadTokenUsage = async () => {
  const runId = props.runId
  if (!runId || tokenUsageRunId.value === runId) return
  const generation = ++tokenUsageGeneration
  tokenUsageRunId.value = runId
  tokenUsageLoading.value = true
  tokenUsageError.value = ''
  try {
    const aggregated = new Map<string, NodeTokenUsage>()
    let cursor: string | null = null
    do {
      const page = await workflowApi.listRunResourceCalls(runId, { pageSize: 100, cursor: cursor || undefined })
      if (generation !== tokenUsageGeneration) return
      for (const call of page.items) {
        if (!call.stepId) continue
        const bucket = aggregated.get(call.stepId) || {
          calls: 0, inputTokens: 0, cacheReadTokens: 0, outputTokens: 0, totalTokens: 0, models: []
        }
        bucket.calls += 1
        bucket.inputTokens += call.usage.inputTokens || 0
        bucket.cacheReadTokens += call.usage.cacheReadTokens || 0
        bucket.outputTokens += call.usage.outputTokens || 0
        bucket.totalTokens += call.usage.totalTokens || (call.usage.inputTokens || 0) + (call.usage.outputTokens || 0)
        if (call.model && !bucket.models.includes(call.model)) bucket.models.push(call.model)
        aggregated.set(call.stepId, bucket)
      }
      cursor = page.nextCursor || null
    } while (cursor)
    tokenByStep.value = aggregated
  } catch {
    if (generation === tokenUsageGeneration) tokenUsageError.value = '模型调用记录读取失败'
  } finally {
    if (generation === tokenUsageGeneration) tokenUsageLoading.value = false
  }
}
watch(() => props.runId, () => {
  tokenUsageRunId.value = ''
  tokenByStep.value = new Map()
  if (props.runId) void loadTokenUsage()
}, { immediate: true })

const selectedTokenUsage = computed(() =>
  selectedNodeId.value ? tokenByStep.value.get(selectedNodeId.value) : undefined)
const detailAsideOpen = ref(false)
const detailAsideVisible = computed(() => Boolean(selectedNode.value && (!focusMainPath.value || detailAsideOpen.value)))
const umlCardVisible = computed(() => Boolean(focusMainPath.value && selectedNode.value && !detailAsideOpen.value))
const cardObjective = computed(() =>
  selectedStepState.value?.task?.objective || selectedNode.value?.goal || selectedNode.value?.description || '')
const cardAgentLabel = computed(() => selectedStepState.value?.agentName || selectedNode.value?.agentName || '')
const peerNodeName = (nodeId: string) =>
  props.blueprint?.nodes.find(node => node.nodeId === nodeId)?.name || nodeId
const formatTokenCount = (value: number) => value.toLocaleString('zh-CN')

const flowStatuses = computed(() => Object.fromEntries((executionBlueprint.value?.nodes || []).map(node => {
  const status = nodeStatus(node.nodeId)
  return [node.nodeId, { status, label: runtimeStatusLabel(status) }]
})))
const onFlowSelect = (id: string) => {
  selectedNodeId.value = id
  detailAsideOpen.value = false
  if (id) emit('nodeSelected', id)
}

const stats = computed(() => {
  if (!props.blueprint || !visibleBlueprint.value) return ''
  const visible = `${visibleBlueprint.value.nodes.length} 节点 / ${visibleBlueprint.value.edges.length} 边`
  if (visibleBlueprint.value.nodes.length === props.blueprint.nodes.length
    && visibleBlueprint.value.edges.length === props.blueprint.edges.length) return visible
  return `${visible}（全图 ${props.blueprint.nodes.length} / ${props.blueprint.edges.length}）`
})

// 节点类型 → 配色（沿用项目色板；蓝图内核只产 step/control，其余类型走 fallback）
const NODE_STYLE: Record<string, { background: string; border: string; shape: string }> = {
  step: { background: '#ddeafa', border: '#6EA8FE', shape: 'box' },
  control: { background: '#e9e2f5', border: '#B39DDB', shape: 'hexagon' }
}

// 边类型 → 样式（蓝图内核只产 dependency）
const EDGE_STYLE: Record<string, { color: string; dashes: boolean | number[] }> = {
  dependency: { color: '#9AA3B2', dashes: false }
}

const edgeTypeLabel = (edgeType: AcgEdge['edgeType']) =>
  EDGE_TYPES.find(item => item.value === edgeType)?.label || edgeType
const nodeTypeLabel = (nodeType: AcgNode['nodeType']) => ({
  step: '步骤',
  control: '控制'
}[nodeType] || nodeType)

const endpointRole = (node: AcgNode) => {
  if (node.nodeType !== 'control') return ''
  const controlType = String(node.controlType || '').toLowerCase()
  if (controlType === 'start' || node.nodeId === 'ctrl_start') return 'start'
  if (controlType === 'end' || node.nodeId === 'ctrl_end') return 'end'
  return ''
}

const cssColor = (name: string, fallback: string) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback

function applyThemeToGraphStyles() {
  // The topology is a technical drawing surface: node fills stay bright, but
  // category, edge and status hues come from the global semantic tokens so the
  // graph speaks the same color language as the rest of the workbench
  // (task=blue, control/artifact=purple, structure=muted gray).
  const running = cssColor('--sem-running', '#6EA8FE')
  const artifact = cssColor('--sem-artifact', '#B39DDB')
  const textSecondary = cssColor('--sem-text-2', '#9AA3B2')
  const nodeSurfaceStrong = '#f8faf9'

  Object.assign(NODE_STYLE, {
    step: { background: mixGraphColor(running, nodeSurfaceStrong, 0.09), border: running, shape: 'box' },
    control: { background: mixGraphColor(artifact, nodeSurfaceStrong, 0.08), border: artifact, shape: 'hexagon' }
  })
  Object.assign(EDGE_STYLE, {
    dependency: { color: textSecondary, dashes: false }
  })
}

const buildNodeRows = (nodes: AcgNode[], completed: Set<string>, states: Map<string, AcgStepState>) => {
  applyThemeToGraphStyles()
  const done = cssColor('--sem-success', '#8BCB78')
  const textPrimary = '#26332f'
  const textSecondary = '#66736f'
  const info = cssColor('--sem-running', '#6EA8FE')
  const warning = cssColor('--sem-waiting', '#D9B86C')
  const retry = cssColor('--sem-retry', '#E69A62')
  const danger = cssColor('--sem-failed', '#E06C75')
  const selectedId = selectedNodeId.value
  const relatedNodeIds = new Set<string>(selectedId ? [selectedId] : [])
  if (selectedId) {
    for (const edge of visibleBlueprint.value?.edges || []) {
      if (edge.sourceId === selectedId) relatedNodeIds.add(edge.targetId)
      if (edge.targetId === selectedId) relatedNodeIds.add(edge.sourceId)
    }
  }
  return nodes.map((node) => {
    const style = NODE_STYLE[node.nodeType] || NODE_STYLE.step
    const stepState = states.get(node.nodeId)
    const visual = mapNodeVisualState(stepState)
    const status = focusMainPath.value ? nodeStatus(node.nodeId)
      : (props.runtimePhases?.[node.nodeId] || stepState?.status || (completed.has(node.nodeId) ? 'completed' : '')).toLowerCase()
    const isDone = status === 'completed'
    const role = endpointRole(node)
    const isStart = role === 'start'
    const isEnd = role === 'end'
    const endpointColor = isStart ? done : isEnd ? info : ''
    const statusColor = isDone
      ? done
      : status === 'running'
        ? info
        : status === 'retrying'
          ? retry
          : status === 'waiting_review'
            ? warning
            : status === 'failed'
              ? danger
              : status === 'cancelled' || status === 'skipped_by_condition'
                ? textSecondary
                : ''
    const badges = [
      visual.runtimeAdded ? '+' : '',
      visual.bindingSwitched ? '⇄' : '',
      visual.conditionalSkipped ? 'Skipped' : '',
      visual.targetRetried ? `A${stepState?.attempt}` : ''
    ].filter(Boolean).join(' · ')
    const baseLabel = isStart
      ? '任务起点\nSTART'
      : isEnd
        ? '任务终点\nEND'
        : node.name || node.nodeId
    const statusText = runtimeStatusLabel(status)
    // vis-network 的 md 多字体没有转义机制，先抹掉会吞字的标记符再包标记
    const executionTitle = executionNodeLabel(node.name || node.nodeId).replace(/[*`]/g, '')
    const executionStatus = `${statusText}${badges ? ` · ${badges}` : ''}`.replace(/[*`]/g, '')
    const label = focusMainPath.value
      ? `*${Array.from(executionTitle.replace(/\n/g, '')).slice(0, 16).join('')}${Array.from(executionTitle.replace(/\n/g, '')).length > 16 ? '…' : ''}*  \`${executionStatus}\``
      : badges ? `${baseLabel}\n[${badges}]` : baseLabel
    const isStep = node.nodeType === 'step'
    const isEndpoint = isStart || isEnd
    const isSelected = node.nodeId === selectedId
    const isRelated = relatedNodeIds.has(node.nodeId)

    // 轻卡片观感：常态弱化描边加中性投影，状态色只留给边框与状态文字
    const nodeOpacity = selectedId && !isRelated
      ? 0.22
      : visual.conditionalSkipped ? 0.48 : status === 'cancelled' ? 0.62 : 1
    const border = statusColor || endpointColor
      || (node.nodeId === contextAnchorId.value ? info : mixGraphColor(style.border, '#ffffff', 0.55))

    const nodeShadow = nodeOpacity < 1
      ? false
      : isEndpoint
        ? { enabled: true, color: endpointColor, size: 16, x: 0, y: 3 }
        : isSelected
          ? { enabled: true, color: border, size: 18, x: 0, y: 4 }
          : { enabled: true, color: 'rgba(15,35,40,0.12)', size: 8, x: 0, y: 2 }

    return {
      id: node.nodeId,
      label,
      title: `${node.name || node.nodeId}\n${node.nodeId}\n${node.nodeType}${status ? `\n${status}` : ''}${badges ? `\n${badges}` : ''}`,
      shape: focusMainPath.value ? 'box' : isStart ? 'circle' : isEnd ? 'box' : style.shape,
      shapeProperties: { borderRadius: focusMainPath.value ? 22 : 10 },
      color: {
        background: endpointColor || style.background,
        border,
        highlight: { background: endpointColor || style.background, border },
        hover: { background: endpointColor || style.background, border }
      },
      borderWidth: isEndpoint ? 3 : isSelected ? 2.6 : status || visual.runtimeAdded ? 2 : 1.4,
      borderWidthSelected: isEndpoint ? 4 : 3,
      opacity: nodeOpacity,
      shadow: nodeShadow,
      // Refined sizing - slightly larger for better legibility
      size: isEndpoint ? 36 : isStep ? 28 : 18,
      font: {
        size: isEndpoint ? 14 : isStep ? (focusMainPath.value ? 15 : 14) : 12,
        color: isEndpoint ? '#ffffff' : isStep ? textPrimary : textSecondary,
        face: isEndpoint ? 'sans-serif' : 'inherit',
        bold: isEndpoint ? { color: '#ffffff', size: 14 } : undefined
      },
      mass: isEndpoint ? 5 : isStep ? 3 : 1,
      margin: isEndpoint ? 14 : isStep ? 12 : 8,
      fixed: isEndpoint ? { x: true, y: true } : false,
      ...(isStart ? { x: 0, y: -440 } : isEnd ? { x: 0, y: 440 } : {}),
      ...(focusMainPath.value ? {
        ...executionPositions.value.get(node.nodeId),
        fixed: false, physics: false, widthConstraint: { minimum: 160, maximum: 340 },
        heightConstraint: { minimum: 24 }, margin: { top: 9, bottom: 9, left: 18, right: 18 },
        font: {
          multi: 'md', size: 14, face: 'sans-serif', color: isEndpoint ? '#ffffff' : textPrimary,
          bold: { size: 14, color: isEndpoint ? '#ffffff' : textPrimary, face: 'sans-serif' },
          boldItalic: { size: 14, color: isEndpoint ? '#ffffff' : textPrimary, face: 'sans-serif' },
          mono: { size: 11, color: isEndpoint ? '#ffffff' : (statusColor || textSecondary), face: 'sans-serif' }
        },
        shadow: nodeShadow, borderWidth: node.nodeId === contextAnchorId.value ? 2.4 : isSelected ? 2.6 : 1.4,
      } : {}),

    }
  })
}

const buildEdgeRows = (edges: AcgEdge[]) => {
  return edges.map((edge, index) => {
    const style = EDGE_STYLE[edge.edgeType] || EDGE_STYLE.dependency
    const activation = mapEdgeVisualState(edge.activation)
    const relatedToSelection = !selectedNodeId.value
      || edge.sourceId === selectedNodeId.value
      || edge.targetId === selectedNodeId.value
    const length = ({
      dependency: 220,
      control_flow: 200
    } as Record<string, number>)[edge.edgeType] || 170
    const fromPosition = executionPositions.value.get(edge.sourceId)
    const toPosition = executionPositions.value.get(edge.targetId)
    const isReturnEdge = focusMainPath.value && fromPosition && toPosition && toPosition.x <= fromPosition.x

    // Enhanced edge opacity for better visual hierarchy
    const baseOpacity = edgeActivationOpacity(activation)
    const selectionOpacity = relatedToSelection ? 1 : 0.12
    const finalOpacity = baseOpacity * selectionOpacity

    return {
      id: edge.edgeId || `e-${index}`,
      from: edge.sourceId,
      to: edge.targetId,
      arrows: { to: { enabled: true, scaleFactor: 0.9, type: 'arrow' } },
      arrowStrikethrough: false,
      endPointOffset: { from: 2, to: 4 },
      color: {
        color: style.color,
        highlight: style.color,
        hover: style.color,
        opacity: finalOpacity
      },
      dashes: activation === 'inactive' ? [6, 5] : activation === 'terminated' ? [2, 6] : style.dashes,
      label: activation === 'active' ? undefined : activation.toUpperCase(),
      smooth: focusMainPath.value
        ? { enabled: true, type: isReturnEdge ? 'curvedCW' : 'cubicBezier', forceDirection: 'horizontal', roundness: isReturnEdge ? 0.4 : 0.35 }
        : { enabled: true, type: 'cubicBezier', roundness: 0.25 },
      // Enhanced edge width for better visibility
      width: focusMainPath.value
        ? (selectedNodeId.value && relatedToSelection ? 2.5 : 1.5)
        : graphEdgeWidth(edge.edgeType) * (selectedNodeId.value && relatedToSelection ? 1.6 : 1),
      selectionWidth: 1.6,
      hoverWidth: 1,
      length
    }
  })
}

const options = {
  autoResize: !props.workbench,
  layout: { improvedLayout: true, randomSeed: 42 },
  physics: {
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {
      gravitationalConstant: -120,  // Increased for more spacing
      centralGravity: 0.008,         // Slightly stronger center pull
      springLength: 200,             // Longer springs for more room
      springConstant: 0.06,          // Softer springs for smoother layout
      damping: 0.6,                  // More damping for stability
      avoidOverlap: 1
    },
    maxVelocity: 32,                 // Slightly faster movement
    minVelocity: 0.4,
    timestep: 0.48,
    adaptiveTimestep: true,
    stabilization: { enabled: true, iterations: 400, fit: true }  // More iterations for better convergence
  },
  interaction: {
    hover: true,
    dragNodes: true,
    zoomView: true,
    navigationButtons: false,
    tooltipDelay: 200,               // Faster tooltip
    hideEdgesOnDrag: false,
    hideEdgesOnZoom: false
  }
}

const getStructureKey = (blueprint: GraphProjection) => JSON.stringify({
  mode: viewMode.value,
  context: focusMainPath.value && localScope.value ? contextAnchorId.value : '',
  nodes: blueprint.nodes.map(node => [node.nodeId, node.nodeType]),
  executionLayout: focusMainPath.value
    ? blueprint.nodes.map(node => [node.nodeId, executionPositions.value.get(node.nodeId)]) : undefined,
  edges: blueprint.edges.map(edge => [edge.edgeId, edge.sourceId, edge.targetId, edge.edgeType])
})

const stopPhysics = () => {
  if (stabilizationTimer) {
    window.clearTimeout(stabilizationTimer)
    stabilizationTimer = undefined
  }
  network?.setOptions({ physics: { enabled: false } } as any)
}

const placeEndpointsSafely = () => {
  const blueprint = visibleBlueprint.value
  if (!network || !blueprint || focusMainPath.value) return

  const startNode = blueprint.nodes.find(node => endpointRole(node) === 'start')
  const endNode = blueprint.nodes.find(node => endpointRole(node) === 'end')
  if (!startNode && !endNode) return

  const contentNodes = blueprint.nodes.filter(node => !endpointRole(node))
  const positions = network.getPositions(contentNodes.map(node => node.nodeId))
  const contentPositions = Object.values(positions).filter(position =>
    Number.isFinite(position.x) && Number.isFinite(position.y)
  )

  if (!contentPositions.length) {
    if (startNode) network.moveNode(startNode.nodeId, 0, -ENDPOINT_MIN_GAP)
    if (endNode) network.moveNode(endNode.nodeId, 0, ENDPOINT_MIN_GAP)
    return
  }

  const xValues = contentPositions.map(position => position.x)
  const yValues = contentPositions.map(position => position.y)
  const minX = Math.min(...xValues)
  const maxX = Math.max(...xValues)
  const minY = Math.min(...yValues)
  const maxY = Math.max(...yValues)
  const centerX = (minX + maxX) / 2
  const contentHeight = Math.max(1, maxY - minY)
  const safeGap = Math.min(ENDPOINT_MAX_GAP, Math.max(ENDPOINT_MIN_GAP, contentHeight * 0.18))

  if (startNode) network.moveNode(startNode.nodeId, centerX, minY - safeGap)
  if (endNode) network.moveNode(endNode.nodeId, centerX, maxY + safeGap)
}

const fitWithSafePadding = (animation = true) => {
  if (!network) return
  if (!visibleBlueprint.value?.nodes.length) return
  network.fit({ animation: false })
  const fittedScale = network.getScale()
  // Keep fit's bounding-box center; the node centroid can crop sparse branches.
  const position = network.getViewPosition()
  network.moveTo({
    position,
    scale: fittedScale * SAFE_VIEW_SCALE,
    animation: animation ? { duration: 360, easingFunction: 'easeInOutQuad' } : false
  })
  zoomPercent.value = Math.round(fittedScale * SAFE_VIEW_SCALE * 100)
}

const finalizeGraphLayout = (animation = true) => {
  if (layoutFinalized) return
  layoutFinalized = true
  stopPhysics()
  placeEndpointsSafely()
  if (pendingViewState) {
    network?.moveTo({
      position: pendingViewState.position,
      scale: pendingViewState.scale,
      animation: false
    })
    pendingViewState = null
  } else {
    if (focusMainPath.value) actualSize(animation)
    else fitWithSafePadding(animation)
  }
}

const render = async (preserveCamera = false) => {
  const request = ++renderRequest
  await nextTick()
  if (request !== renderRequest) return
  const blueprint = visibleBlueprint.value
  if (!hasData.value || !blueprint) return
  if (selectedNodeId.value && !blueprint.nodes.some(node => node.nodeId === selectedNodeId.value)) {
    selectedNodeId.value = ''
  }
  if (focusMainPath.value || !graphRef.value) return
  const completed = new Set(props.completedStepIds || [])
  const states = new Map<string, AcgStepState>((props.stepStates || []).map(item => [item.stepId, item]))
  const nodeRows = buildNodeRows(blueprint.nodes, completed, states)
  const edgeRows = buildEdgeRows(blueprint.edges)
  const nextStructureKey = getStructureKey(blueprint)
  const nextDataKey = JSON.stringify({ nodes: nodeRows, edges: edgeRows })

  // Polling frequently returns a new object with the same graph structure.
  // Update labels/status in place so existing positions and user dragging are preserved.
  if (network && nodesData && edgesData && graphDataKey === nextDataKey) return
  if (network && nodesData && edgesData && graphStructureKey === nextStructureKey) {
    // 起终点行的初始坐标 (0,±440) 只是首次布局的占位：placeEndpointsSafely
    // 已把它们摆到内容包围盒外。就地更新时必须剥掉坐标，否则每次投影刷新
    // 都会把起终点拽回图中央（内容 cluster 内部）。
    nodesData.update(nodeRows.map(({ x: _initX, y: _initY, ...row }) => row))
    edgesData.update(edgeRows)
    graphDataKey = nextDataKey
    return
  }

  pendingViewState = network && (!focusMainPath.value || preserveCamera)
    ? { position: network.getViewPosition(), scale: network.getScale() }
    : null
  stopPhysics()
  if (network) {
    network.destroy()
    network = null
  }
  nodesData = new DataSet(nodeRows)
  edgesData = new DataSet(edgeRows)
  graphStructureKey = nextStructureKey
  graphDataKey = nextDataKey
  layoutFinalized = false
  const data = { nodes: nodesData, edges: edgesData }
  network = new Network(graphRef.value, data as any, {
    ...options,
    ...(focusMainPath.value ? { layout: { improvedLayout: false }, physics: { enabled: false } } : {})
  } as any)
  network.on('zoom', () => {
    zoomPercent.value = Math.round((network?.getScale() || 1) * 100)
  })
  network.on('animationFinished', () => { zoomPercent.value = Math.round((network?.getScale() || 1) * 100) })
  ensureGraphResizeObserver()
  if (selectedNodeId.value) network.selectNodes([selectedNodeId.value])
  network.on('selectNode', params => {
    selectedNodeId.value = String(params.nodes[0] || '')
    if (selectedNodeId.value) emit('nodeSelected', selectedNodeId.value)
    scheduleRender()
  })
  // UML 语义：再次点击已展开的节点 = 收起详情。已选中节点不会再次触发 selectNode，挂在 click 上。
  network.on('click', params => {
    const clicked = String(params.nodes?.[0] || '')
    if (clicked && clicked === selectedNodeId.value) clearSelection()
  })
  network.on('doubleClick', params => {
    const nodeId = String(params.nodes?.[0] || '')
    if (nodeId) emit('nodeDoubleClicked', nodeId)
  })
  network.on('deselectNode', () => {
    selectedNodeId.value = ''
    scheduleRender()
  })

  if (focusMainPath.value) {
    finalizeGraphLayout(false)
    return
  }

  // 布局展开成形后，完全冻结 physics —— 节点定住不再漂移抖动。
  // physics 关闭后 dragNodes 仍有效：拖动只移动被拖的单个节点，
  // 其余节点保持不动，不会触发整图重新布局/旋转。
  network.once('stabilizationIterationsDone', () => {
    finalizeGraphLayout(true)
  })
  network.once('stabilized', () => finalizeGraphLayout(true))
  // Tiny or sparse graphs may not emit the iteration event consistently.
  stabilizationTimer = window.setTimeout(() => finalizeGraphLayout(false), 2400)
}

const resetView = (animation = true) => {
  placeEndpointsSafely()
  if (focusMainPath.value) actualSize(animation)
  else fitWithSafePadding(animation)
}

const actualSize = (animation: boolean | MouseEvent = true) => {
  if (focusMainPath.value) return executionFlow.value?.actualSize(selectedNodeId.value || contextAnchorId.value, animation === false ? 0 : 240)
  if (!network) return
  const id = selectedNodeId.value || contextAnchorId.value
  const position = focusMainPath.value && id ? network.getPositions([id])[id] : network.getViewPosition()
  network.moveTo({ position, scale: 1, animation: animation === false ? false : { duration: 240, easingFunction: 'easeInOutQuad' } })
  zoomPercent.value = 100
}

const setExecutionScope = async (local: boolean) => {
  localScope.value = local
  selectedNodeId.value = ''
  network?.unselectAll()
  await render()
  await actualSize(false)
}

const showOverview = async () => {
  if (focusMainPath.value) await setExecutionScope(false)
  if (focusMainPath.value) await executionFlow.value?.overview()
  else fitWithSafePadding()
}

const locateCurrentTask = async () => {
  if (!currentTaskId.value) return
  contextNodeId.value = currentTaskId.value
  localScope.value = true
  selectedNodeId.value = ''
  await render()
  actualSize()
}

const zoomGraph = (factor: number) => {
  if (focusMainPath.value) return executionFlow.value?.zoomBy(factor)
  if (!network) return
  const scale = Math.min(2.4, Math.max(0.18, network.getScale() * factor))
  network.moveTo({
    position: network.getViewPosition(),
    scale,
    animation: { duration: 180, easingFunction: 'easeInOutQuad' }
  })
  zoomPercent.value = Math.round(scale * 100)
}

const syncFullscreenState = () => {
  isFullscreen.value = document.fullscreenElement === sectionRef.value
  window.setTimeout(() => {
    network?.redraw()
    resetView(false)
  }, 120)
}

// 容器尺寸响应分三种场景：非 workbench 独立页面走原生 autoResize；
// observeResize 的画布（graph.acg 编辑器）autoResize 关闭以省持续开销，
// 由下方防抖 ResizeObserver 补齐：只更新位图尺寸并保持用户视图
// （position/scale），不重新 fit、不动布局；内嵌多列场景（运行进度
// GRAPH 列等）不开启：列宽由内容布局决定，resize 时的相机恢复会与
// 列宽互相干扰导致视图爆炸，保持渲染即可。
const ensureGraphResizeObserver = () => {
  if (!props.observeResize || typeof ResizeObserver !== 'function') return
  const target = graphRef.value
  if (!target) return
  if (graphResizeObserver) {
    if (graphResizeTarget === target) return
    graphResizeObserver.disconnect()
  }
  graphResizeTarget = target
  graphResizeObserver = new ResizeObserver(() => scheduleGraphRedraw())
  graphResizeObserver.observe(target)
}

const redrawPreservingView = () => {
  if (!network || !graphRef.value) return
  if (graphRef.value.clientWidth <= 0 || graphRef.value.clientHeight <= 0) return
  const position = network.getViewPosition()
  const scale = network.getScale()
  // redraw() 内部会先触发 canvas 的 setSize 拾取容器新尺寸（内部按宽高比临时缩放视图），
  // 随后用 moveTo 恢复原缩放，并把原视野中心的内容放回新画布正中 —— 不重新 fit、不动布局。
  network.redraw()
  network.moveTo({ position, scale, animation: false })
}

const scheduleGraphRedraw = () => {
  if (graphResizeTimer !== undefined) window.clearTimeout(graphResizeTimer)
  // 收起/展开侧栏时 flex 布局会连续发出多次通知，合并成一次重绘。
  graphResizeTimer = window.setTimeout(() => {
    graphResizeTimer = undefined
    if (graphResizeFrame !== undefined) return
    graphResizeFrame = typeof window.requestAnimationFrame === 'function'
      ? window.requestAnimationFrame(() => {
          graphResizeFrame = undefined
          redrawPreservingView()
        })
      : window.setTimeout(() => {
          graphResizeFrame = undefined
          redrawPreservingView()
        }, 16)
  }, 64)
}

const cancelGraphRedraw = () => {
  if (graphResizeTimer !== undefined) {
    window.clearTimeout(graphResizeTimer)
    graphResizeTimer = undefined
  }
  if (graphResizeFrame !== undefined) {
    if (typeof window.cancelAnimationFrame === 'function') window.cancelAnimationFrame(graphResizeFrame)
    else window.clearTimeout(graphResizeFrame)
    graphResizeFrame = undefined
  }
}

const toggleFullscreen = async () => {
  if (!sectionRef.value || !fullscreenSupported) return
  try {
    if (document.fullscreenElement === sectionRef.value) {
      await document.exitFullscreen()
      return
    }
    if (document.fullscreenElement) await document.exitFullscreen()
    await sectionRef.value.requestFullscreen()
  } catch (error) {
    console.warn('ACG topology fullscreen request failed', error)
    syncFullscreenState()
  }
}

const handleFullscreenEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && selectedNodeId.value) {
    clearSelection()
    return
  }
  if (event.key === 'Escape' && document.fullscreenElement === sectionRef.value) {
    void document.exitFullscreen()
  }
}

const clearSelection = () => {
  if (focusMainPath.value && !detailAsideOpen.value) { executionFlow.value?.close(); return }
  selectedNodeId.value = ''
  detailAsideOpen.value = false
  network?.unselectAll()
  scheduleRender()
}

const selectRelatedNode = (nodeId: string) => { void focusNode(nodeId) }

const setViewMode = (mode: GraphViewMode) => {
  if (viewMode.value === mode) return
  viewMode.value = mode
  selectedNodeId.value = ''
  stopPhysics()
  network?.destroy()
  network = null
  nodesData = null
  edgesData = null
  graphStructureKey = ''
  graphDataKey = ''
  pendingViewState = null
}

const focusNode = async (nodeId: string) => {
  if (!props.blueprint?.nodes.some(node => node.nodeId === nodeId)) return
  // Selection is echoed back through the workspace props. It must not start a second camera animation.
  if (selectedNodeId.value === nodeId) return
  if (focusMainPath.value) {
    contextNodeId.value = nodeId
    selectedNodeId.value = nodeId
    detailAsideOpen.value = false
    await nextTick()
    await executionFlow.value?.actualSize(nodeId)
    emit('nodeSelected', nodeId)
    return
  }
  if (focusMainPath.value) contextNodeId.value = nodeId
  await render(true)
  if (!network || !visibleBlueprint.value?.nodes.some(node => node.nodeId === nodeId)) return
  selectedNodeId.value = nodeId
  network.selectNodes([nodeId])
  // Wait for the card measurement, then position the node and card together.
  // focus() locks onto the node and competes with the card's camera correction.
  await nextTick()
  if (!network || selectedNodeId.value !== nodeId) return
  const position = network.getPositions([nodeId])[nodeId]
  if (!position) return
  network.moveTo({
    position: { x: position.x, y: position.y },
    scale: 1,
    animation: { duration: 240, easingFunction: 'easeInOutQuad' }
  })
  emit('nodeSelected', nodeId)
  scheduleRender()
}

const scheduleRender = () => {
  if (renderTimer !== undefined) return
  renderTimer = window.setTimeout(() => {
    renderTimer = undefined
    void render()
  }, 100)
}

const cancelScheduledRender = () => {
  if (renderTimer === undefined) return
  window.clearTimeout(renderTimer)
  renderTimer = undefined
}

watch(
  () => [props.blueprint, props.completedStepIds, props.stepStates, props.runtimePhases, viewMode.value, localScope.value, contextAnchorId.value],
  () => scheduleRender(),
  { deep: true }
)
watch(
  () => props.focusNodeId,
  nodeId => {
    if (nodeId) void nextTick(() => focusNode(nodeId))
  }
)
onMounted(() => {
  document.addEventListener('fullscreenchange', syncFullscreenState)
  document.addEventListener('keydown', handleFullscreenEscape)
  themeObserver = new MutationObserver(() => scheduleRender())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-color-scheme'] })
  render()
})
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncFullscreenState)
  document.removeEventListener('keydown', handleFullscreenEscape)
  if (document.fullscreenElement === sectionRef.value) {
    void document.exitFullscreen()
  }
  tokenUsageGeneration += 1
  stopPhysics()
  cancelScheduledRender()
  cancelGraphRedraw()
  graphResizeObserver?.disconnect()
  graphResizeObserver = null
  graphResizeTarget = null
  themeObserver?.disconnect()
  themeObserver = null
  network?.destroy()
  network = null
  nodesData = null
  edgesData = null
})
</script>

<style scoped>
.acg-topology {
  display: flex;
  flex-direction: column;
  min-width: 0;
  box-sizing: border-box;
  padding: 16px;
  overflow: hidden;
  color: var(--text-primary);
  background: linear-gradient(135deg, color-mix(in srgb, var(--bg-input) 52%, var(--bg-panel)) 0%, color-mix(in srgb, var(--bg-input) 45%, var(--bg-panel)) 100%);
  border-color: var(--border-light);
  box-shadow: 0 2px 8px rgba(38, 51, 47, .06), 0 8px 24px rgba(38, 51, 47, .04);
  border-radius: 12px;
}
.acg-topology.is-workbench {
  height: 100%;
  min-height: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: var(--wb-surface-2);
  box-shadow: none;
}
.acg-topology.is-workbench .panel-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  justify-content: initial;
  flex: 0 0 34px;
  box-sizing: border-box;
  min-height: 34px;
  margin: 0;
  padding: 0 10px;
  border-bottom: 1px solid var(--wb-border);
}
.acg-topology.is-workbench .head-left {
  min-width: 0;
  justify-content: flex-start;
}
.acg-topology.is-workbench .panel-head h4 {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.acg-topology.is-workbench .head-right {
  position: static;
  min-width: 0;
  justify-self: end;
}
.acg-topology.is-workbench .meta {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.acg-topology.is-workbench .action-group { padding: 2px; border: 1px solid var(--wb-border); border-radius: var(--wb-radius-sm); background: var(--wb-surface-inset); box-shadow: none; }
.acg-topology.is-workbench .action-btn { width: 28px; height: 28px; border-radius: 4px; }
.acg-topology.is-workbench .action-btn:hover, .acg-topology.is-workbench .action-btn.active { border-color: color-mix(in srgb, var(--wb-accent) 42%, var(--wb-border)); background: var(--wb-surface-2); box-shadow: none; }
.acg-topology.is-workbench .graph-surface { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; overflow: hidden; }
.acg-topology.is-workbench .graph-toolbar {
  position: static;
  flex: 0 0 35px;
  box-sizing: border-box;
  width: 100%;
  max-width: none;
  min-width: 0;
  padding: 0 10px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}
.acg-topology.is-workbench .view-mode { min-width: 0; gap: 2px; padding: 2px; border-radius: 9px; background: var(--wb-surface-inset); }
.acg-topology.is-workbench .view-mode button {
  min-height: 30px;
  padding: 0 12px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--wb-text-muted);
}
.acg-topology.is-workbench .view-mode button:hover { background: var(--wb-hover); color: var(--wb-text); }
.acg-topology.is-workbench .view-mode button.active { background: var(--wb-surface-2); color: var(--wb-accent); box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 2px 8px rgba(0,0,0,.04); font-weight: 650; }
.acg-topology.is-workbench .execution-context__scope { margin-left: auto; }
.acg-topology.is-workbench .execution-context__scope button { min-height: 30px; padding: 0 12px; }
.acg-topology.is-workbench .empty { flex: 1 1 auto; min-height: 0; }
.acg-topology.is-workbench .graph-stage { flex: 1 1 auto; min-height: 0; grid-template-rows: minmax(0, 1fr); border: 0; border-radius: 0; background: transparent; }
.acg-topology.is-workbench .graph-canvas { flex: 1 1 auto; height: 100%; min-height: 0; }
.acg-topology.is-workbench .node-detail { height: auto; min-height: 0; }
.acg-topology.is-workbench .meta { padding: 2px 5px; border-radius: 3px; background: transparent; }
.acg-topology.is-workbench .view-hint { border-color: var(--wb-border); background: color-mix(in srgb, var(--wb-surface-2) 94%, transparent); box-shadow: none; }
.acg-topology.is-workbench .canvas-controls button { color: var(--wb-text-secondary); }
.acg-topology.is-workbench .canvas-controls button:hover { background: var(--wb-hover); color: var(--wb-accent); }
.acg-topology.is-workbench .node-detail { border-left-color: var(--wb-border); background: var(--wb-surface-1); }
.acg-topology.is-workbench .node-detail header span,
.acg-topology.is-workbench .node-detail header button:hover { color: var(--wb-accent); }
.acg-topology.is-workbench .node-detail header button { background: var(--wb-surface-inset); color: var(--wb-text-secondary); }
.acg-topology.is-workbench .runtime-detail-group,
.acg-topology.is-workbench .runtime-summary { border-color: var(--wb-border); background: var(--wb-surface-inset); }
.graph-surface { position: relative; min-width: 0; }
.execution-context__scope { display: inline-flex; flex: 0 0 auto; gap: 2px; padding: 2px; border-radius: 9px; background: var(--wb-surface-inset, var(--bg-input)); }
.execution-context__anchor { max-width: 220px; overflow: hidden; padding: 0 8px; color: var(--wb-text-muted, var(--text-muted)); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; align-self: center; }
.execution-context__scope button { padding: 7px 12px; border: 0; border-radius: 7px; background: transparent; color: var(--wb-text-muted, var(--text-muted)); font-size: 12px; font-weight: 500; cursor: pointer; transition: all .2s cubic-bezier(0.4, 0, 0.2, 1); }
.execution-context__scope button:hover { background: var(--wb-hover, transparent); color: var(--wb-text-secondary, var(--text-secondary)); }
.execution-context__scope button.active { background: var(--wb-surface-2, var(--bg-panel)); color: var(--wb-accent, var(--primary-color)); box-shadow: 0 1px 3px rgba(0,0,0,.08), 0 2px 8px rgba(0,0,0,.04); font-weight: 650; }
.acg-topology.is-workbench .view-mode button { font-size: 12px; }
.canvas-controls .canvas-controls__text { width: auto; padding: 0 10px; font-size: 12px; font-weight: 500; white-space: nowrap; }
.canvas-controls__scale { display: grid; place-items: center; min-width: 48px; font: 11px var(--font-mono, monospace); color: var(--wb-text-secondary, var(--text-secondary)); font-weight: 600; }
.canvas-controls button:disabled { opacity: .35; cursor: not-allowed; }
.graph-stage.has-detail .graph-fab { right: 308px; }
.execution-context__scope button:focus-visible, .canvas-controls button:focus-visible { outline: 2px solid var(--wb-accent, var(--primary-color)); outline-offset: 2px; border-radius: 6px; }
.panel-head {
  display: flex;
  justify-content: flex-start;
  align-items: center;
  gap: 12px;
  position: relative;
  min-height: 32px;
  margin-bottom: 8px;
  padding-bottom: 7px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent);
}
.head-left { display: flex; align-items: center; justify-content: flex-start; gap: 7px; }
.head-icon { font-size: 16px; color: var(--primary-color); }
.panel-head h4 { margin: 0; font-size: 14px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em; }
.head-right { position: absolute; right: 0; display: flex; align-items: center; gap: 8px; }
.meta { padding: 3px 8px; border-radius: 999px; background: var(--primary-fade); color: var(--text-secondary); font-size: 10px; font-weight: 650; white-space: nowrap; letter-spacing: -0.01em; }
.action-group { display: inline-flex; align-items: center; gap: 2px; padding: 2px; border: 1px solid color-mix(in srgb, var(--border-light) 82%, transparent); border-radius: 7px; background: var(--bg-input); box-shadow: none; }
.action-btn {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border: 0; background: transparent; color: var(--text-secondary);
  border-radius: 5px; cursor: pointer; transition: background-color 0.16s ease, color 0.16s ease;
}
.action-btn:hover, .action-btn.active { background: var(--primary-fade); color: var(--primary-color); }
.graph-toolbar {
  position: absolute; z-index: 5; top: 20px; left: 20px;
  display: flex; align-items: center; justify-content: flex-start; gap: 4px;
  width: max-content; max-width: calc(100% - 40px); padding: 6px;
  border: 1px solid color-mix(in srgb, var(--border-light) 82%, transparent);
  border-radius: 12px;
  background: color-mix(in srgb, var(--bg-card) 92%, transparent);
  box-shadow: var(--shadow-md);
  backdrop-filter: var(--backdrop-blur);
}
.view-mode { display: inline-flex; gap: 3px; padding: 3px; background: color-mix(in srgb, var(--bg-app) 65%, transparent); border-radius: 9px; }
.view-mode button {
  min-height: 34px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 0 16px;
  border: 0; border-radius: 7px; background: transparent; color: var(--text-secondary);
  font-size: 13px; font-weight: 500; cursor: pointer; letter-spacing: -0.01em;
  transition: background-color 0.18s var(--ease-out), color 0.18s var(--ease-out);
  position: relative;
}
.view-mode button:hover:not(.active) {
  background: color-mix(in srgb, var(--bg-app) 45%, transparent);
  color: var(--text-primary);
}
.view-mode button.active {
  background: var(--bg-panel);
  color: var(--primary-color);
  box-shadow: var(--shadow-sm);
  font-weight: 600;
}
.empty {
  display: flex;
  flex: 1 1 auto;
  min-height: 240px;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 48px 20px;
  text-align: center;
}
.empty__badge {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  margin-bottom: 10px;
  border-radius: 13px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 26px;
}
.empty__title { margin: 0; color: var(--text-primary); font-size: 15px; font-weight: 600; letter-spacing: -0.02em; }
.empty__hint { margin: 0; max-width: 440px; color: var(--text-secondary); font-size: 13px; line-height: 1.65; letter-spacing: -0.01em; }
.graph-stage {
  position: relative; display: grid; grid-template-columns: minmax(0, 1fr); min-height: 560px; overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--border-light) 92%, var(--bg-panel)); border-radius: 12px;
  background: var(--bg-panel);
}
.graph-stage.has-detail { grid-template-columns: minmax(0, 1fr) 300px; }
.graph-canvas { width: 100%; max-width: 100%; min-width: 0; height: 560px; min-height: 420px; }
.view-hint {
  position: absolute; z-index: 4; inset: 50% auto auto 50%; transform: translate(-50%, -50%); margin: 0;
  padding: 10px 14px; border: 1px solid var(--border-light); border-radius: 9px;
  background: color-mix(in srgb, var(--bg-panel) 96%, transparent);
  color: var(--text-secondary); font-size: 12px; font-weight: 500;
  box-shadow: 0 4px 12px rgba(38, 51, 47, .06);
  backdrop-filter: blur(12px);
}
.node-detail {
  position: relative; z-index: 6; height: 560px; min-width: 0; overflow-y: auto; padding: 18px;
  border-left: 1px solid color-mix(in srgb, var(--border-light) 82%, transparent);
  background: var(--bg-sidebar);
}
.node-detail header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 4px; }
.node-detail header span { font-size: 10px; color: var(--primary-color); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; opacity: 0.9; }
.node-detail h5 { margin: 4px 0 0; font-size: 16px; font-weight: 600; color: var(--text-primary); overflow-wrap: anywhere; letter-spacing: -0.02em; line-height: 1.4; }
.node-detail header button {
  width: 32px; height: 32px; flex: 0 0 auto; display: grid; place-items: center;
  border: 0; border-radius: 7px; background: var(--bg-input); color: var(--text-secondary); cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}
.node-detail header button:hover { background: var(--primary-fade); color: var(--primary-color); }
.node-detail dl { display: flex; flex-direction: column; gap: 10px; margin: 20px 0; }
.node-detail dl div { display: grid; grid-template-columns: 80px minmax(0, 1fr); gap: 12px; align-items: start; }
.node-detail dt { font-size: 11px; color: var(--text-disabled); font-weight: 600; text-transform: uppercase; letter-spacing: 0.02em; padding-top: 2px; }
.node-detail dd { margin: 0; min-width: 0; font-size: 13px; color: var(--text-secondary); overflow-wrap: anywhere; line-height: 1.5; }
.node-detail code { color: var(--text-primary); font-weight: 500; background: var(--bg-input); padding: 2px 5px; border-radius: 4px; }
.node-detail .skill-list { display: flex; flex-wrap: wrap; gap: 6px; }
.node-detail .skill-list code {
  padding: 4px 8px; border: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent); border-radius: 6px; background: var(--bg-input);
  font-size: 11px;
}
.node-status { font-weight: 700; }
.node-status.completed { color: var(--sem-success); }
.node-status.running { color: var(--sem-running); }
.node-status.waiting_review { color: var(--sem-waiting); }
.node-status.retrying { color: var(--sem-retry); }
.node-status.failed { color: var(--sem-failed); }
.node-status.skipped_by_condition { color: var(--text-secondary); }
.node-description { margin: 0 0 16px; font-size: 12px; line-height: 1.6; color: var(--text-secondary); letter-spacing: -0.01em; }
.runtime-detail-group { display: flex; flex-direction: column; gap: 5px; margin: 12px 0; padding: 10px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-input); }
.runtime-detail-group strong { color: var(--text-primary); font-size: 11px; font-weight: 600; }
.runtime-detail-group span { color: var(--text-secondary); font: 11px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.execution-history article { display: grid; gap: 4px; padding: 8px 0; border-top: 1px solid var(--border-light); }
.execution-history article:first-of-type { border-top: 0; padding-top: 0; }
.execution-history article code { overflow-wrap: anywhere; color: var(--text-secondary); font-size: 10px; }
.execution-history article b { color: var(--sem-running); }
.execution-history .failure { color: var(--sem-failed); }
.projection-pending { margin: 10px 0; padding: 8px; border-radius: 6px; background: var(--sem-waiting-fade); color: var(--sem-waiting); font-size: 11px; }
.runtime-summary { max-height: 100px; margin: 10px 0; padding: 8px; overflow: auto; border-radius: 6px; background: var(--bg-input); color: var(--text-secondary); font: 11px/1.6 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.runtime-summary.is-error { color: var(--sem-failed); background: color-mix(in srgb, var(--sem-failed) 8%, var(--bg-input)); }
.connection-group { display: flex; flex-direction: column; gap: 6px; margin-top: 14px; }
.connection-group strong { font-size: 11px; font-weight: 600; color: var(--text-primary); }
.connection-group > span { font-size: 11px; color: var(--text-disabled); }
.connection-group button {
  display: flex; align-items: center; gap: 7px; min-width: 0; padding: 6px 8px;
  border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-input);
  color: var(--text-secondary); font: 11px monospace; text-align: left; cursor: pointer; overflow-wrap: anywhere;
  transition: all .2s cubic-bezier(0.4, 0, 0.2, 1);
}
.connection-group button:hover { border-color: var(--primary-color); color: var(--text-primary); background: color-mix(in srgb, var(--primary-color) 6%, var(--bg-input)); }
.connection-group small { flex: 0 0 auto; color: var(--primary-color); font: 10px sans-serif; font-weight: 600; }
.graph-fab {
  position: absolute; z-index: 6; right: 20px; bottom: 20px;
  display: flex; flex-direction: column; align-items: flex-end; gap: 10px;
  width: 40px;
  pointer-events: none;
}
.graph-fab__panel,
.graph-fab__ball { pointer-events: auto; }
.graph-fab__panel {
  display: flex; flex-direction: column; gap: 10px;
  width: 100%;
  padding: 14px 16px;
  border: 1px solid var(--wb-border, var(--border-light));
  border-radius: 14px;
  background: var(--wb-surface-2, var(--bg-panel));
  box-shadow: 0 16px 40px var(--shadow-color, rgba(0, 0, 0, 0.12)),
              0 4px 12px var(--shadow-color, rgba(0, 0, 0, 0.1));
  backdrop-filter: blur(32px) saturate(180%);
}
.graph-fab__ball {
  width: 40px; padding: 11px 0; display: flex; flex-direction: column; align-items: center; gap: 7px;
  border: 0; border-radius: 999px;
  background: var(--primary-color); color: #ffffff; cursor: grab;
  touch-action: none; user-select: none;
  box-shadow: 0 4px 14px var(--shadow-color, rgba(15, 18, 26, 0.28)), 0 2px 6px var(--shadow-color, rgba(15, 18, 26, 0.18));
  transition: transform .2s cubic-bezier(0.4, 0, 0.2, 1), background .2s cubic-bezier(0.4, 0, 0.2, 1), box-shadow .2s cubic-bezier(0.4, 0, 0.2, 1);
}
.graph-fab__ball:active { cursor: grabbing; }
.graph-fab__ball:hover { transform: scale(1.06); background: var(--primary-hover); }
.graph-fab__ball:active { transform: scale(0.98); }
.graph-fab__ball:focus-visible { outline: 2px solid var(--wb-accent, var(--primary-color)); outline-offset: 2px; }
.graph-fab__ball-icon { font-size: 18px; }
.graph-fab__ball-divider { width: 14px; height: 1px; background: rgba(255, 255, 255, 0.32); }
.graph-fab.expanded {
  inset: 20px;
  width: auto;
  align-items: stretch;
}
.graph-fab.expanded .graph-fab__panel { flex: 1 1 auto; min-height: 0; }
.graph-fab.expanded .graph-fab__ball { position: absolute; right: -17px; top: 50%; transform: translateY(-50%); }
.graph-fab.expanded .graph-fab__ball:hover { transform: translateY(-50%) scale(1.06); }
.graph-fab.expanded .graph-fab__ball:active { transform: translateY(-50%) scale(0.98); }
.graph-fab.expanded .legend {
  flex: 1 1 auto; min-height: 0; max-height: none;
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 18px;
  align-content: start; align-items: start;
}
.graph-fab.expanded .legend-group { flex-direction: column; align-items: flex-start; gap: 10px; }
.graph-fab.expanded .canvas-controls { margin-top: auto; }
.legend {
  display: flex; flex-direction: row; flex-wrap: wrap; align-content: flex-start; gap: 12px 32px;
  width: 100%; max-height: min(320px, 42vh); padding: 2px;
  overflow-y: auto; overscroll-behavior: contain;
}
.legend-group { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 12px; }
.legend-label { color: var(--text-muted); font-size: 10px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; opacity: 0.7; }
.legend-item { display: inline-flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-secondary); white-space: nowrap; font-weight: 500; }
.dot { width: 12px; height: 12px; border-radius: 4px; display: inline-block; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.12); }
.dot.step { background: color-mix(in srgb, var(--sem-running) 18%, var(--bg-input)); border: 2px solid var(--sem-running); }
.dot.control { background: color-mix(in srgb, var(--sem-artifact) 13%, var(--bg-input)); border: 2px solid var(--sem-artifact); }
.ring { width: 12px; height: 12px; border-radius: 50%; display: inline-block; border: 3px solid var(--success); box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.5), 0 1px 3px rgba(0, 0, 0, 0.12); }
.ring.done { border-color: var(--sem-success); }
.ring.running { border-color: var(--sem-running); }
.ring.waiting { border-color: var(--sem-waiting); }
.ring.failed { border-color: var(--sem-failed); }
.ring.retrying { border-color: var(--sem-retry); }
.badge { min-width: 18px; padding: 3px 6px; border-radius: 5px; color: #fff; font-size: 10px; line-height: 12px; text-align: center; font-weight: 600; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15); }
.badge.runtime { background: var(--sem-running); }
.badge.binding { background: var(--sem-flow); }
.badge.skipped { background: var(--text-muted); }
.canvas-controls {
  display: inline-flex; align-items: center; gap: 2px; padding: 8px 2px 2px;
  border-top: 1px solid var(--wb-border-soft, rgba(0, 0, 0, 0.06));
}
.canvas-controls button {
  width: 34px; height: 34px; display: grid; place-items: center; border: 0; border-radius: 9px;
  background: transparent; color: var(--text-secondary); cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
  font-weight: 500;
}
.canvas-controls button:hover:not(:disabled) {
  background: var(--primary-fade);
  color: var(--primary-color);
}

.acg-topology:fullscreen {
  width: 100vw;
  height: 100vh;
  padding: 20px;
  background: var(--wb-surface-2, var(--bg-panel));
}
.acg-topology:fullscreen .graph-stage { flex: 1 1 auto; min-height: 0; }
.acg-topology:fullscreen .graph-canvas,
.acg-topology:fullscreen .node-detail { height: 100%; min-height: 0; }
.acg-topology:fullscreen .graph-toolbar,
.acg-topology:fullscreen .graph-fab,
.acg-topology:fullscreen .panel-head { flex: 0 0 auto; }

/* Shared detail content inside a Vue Flow execution node. */
.uml-card {
  position: absolute;
  z-index: 6;
  box-sizing: border-box;
  width: 340px;
  max-height: 420px;
  overflow: hidden auto;
  border: 1px solid var(--wb-border, var(--border-light));
  border-radius: 16px;
  background: var(--wb-surface-1, rgba(255, 255, 255, 0.98));
  box-shadow: 0 6px 18px rgba(15, 35, 40, 0.12);
  color: var(--wb-text, var(--text-primary));
}
.uml-card__head {
  position: sticky;
  top: 0;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--wb-border, var(--border-light));
  background: var(--wb-surface-2, var(--bg-panel));
}
.uml-card__title { flex: 1; min-width: 0; overflow-wrap: anywhere; font-size: 13px; line-height: 1.5; }
.uml-card__status { flex-shrink: 0; font-size: 11px; font-weight: 600; color: var(--wb-text-secondary, var(--text-secondary)); }
.uml-card__status[data-status="running"] { color: var(--sem-running, #6EA8FE); }
.uml-card__status[data-status="failed"] { color: var(--sem-failed, #E06C75); }
.uml-card__status[data-status="completed"] { color: var(--sem-success, #8BCB78); }
.uml-card__status[data-status="waiting_review"] { color: var(--sem-waiting, #D9B86C); }
.uml-card__status[data-status="retrying"] { color: var(--sem-retry, #E69A62); }
.uml-card__close {
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0; width: 28px; height: 28px; padding: 0; border: 0; border-radius: 5px;
  background: transparent; color: var(--wb-text-muted, var(--text-secondary)); cursor: pointer;
}
.uml-card__close:hover { background: var(--wb-hover, rgba(0, 0, 0, 0.05)); color: var(--wb-text, var(--text-primary)); }
.uml-card__body { display: grid; gap: 14px; padding: 14px; }
.uml-card__objective {
  margin: 0; padding: 7px 8px; border-radius: 7px;
  background: var(--wb-surface-inset, rgba(0, 0, 0, 0.03));
  color: var(--wb-text-secondary, var(--text-secondary));
  font-size: 13px; line-height: 1.7; overflow-wrap: anywhere;
}
.uml-card__section h6 {
  display: flex; align-items: baseline; justify-content: space-between; gap: 6px;
  margin: 0 0 5px; color: var(--wb-accent, var(--primary-color));
  font: 600 10px/1 var(--font-mono, monospace); letter-spacing: .08em;
}
.uml-card__section h6 em { color: var(--wb-text-muted, var(--text-secondary)); font: 400 10px/1 var(--font-mono, monospace); letter-spacing: 0; }
.uml-card__section > p { margin: 0; color: var(--wb-text-secondary, var(--text-secondary)); font-size: 11px; line-height: 1.55; }
.uml-card__empty { color: var(--wb-text-muted, var(--text-secondary)); }
.uml-card__tokens { display: grid; grid-template-columns: repeat(4, 1fr); gap: 5px; }
.uml-card__tokens div {
  display: grid; gap: 2px; padding: 5px 3px; text-align: center;
  border: 1px solid var(--wb-border-soft, var(--border-light)); border-radius: 7px;
  background: var(--wb-surface-section, transparent);
}
.uml-card__tokens b { font: 600 11px/1.2 var(--font-mono, monospace); color: var(--wb-text, var(--text-primary)); }
.uml-card__tokens span { color: var(--wb-text-muted, var(--text-secondary)); font-size: 10px; white-space: nowrap; }
.uml-card__models { margin: 5px 0 0; color: var(--wb-text-muted, var(--text-secondary)); font: 10px var(--font-mono, monospace); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.uml-card__meta { display: flex; flex-wrap: wrap; gap: 4px 10px; }
.uml-card__meta span { color: var(--wb-text-secondary, var(--text-secondary)); font: 10px var(--font-mono, monospace); }
.uml-card__deps { display: grid; gap: 6px; }
.uml-card__dep-group { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.uml-card__dep-group > span { min-width: 52px; color: var(--wb-text-muted, var(--text-secondary)); font-size: 10px; }
.uml-card__dep-group button {
  max-width: 86px; padding: 2px 7px; overflow: hidden; border: 1px solid var(--wb-border-soft, var(--border-light));
  border-radius: 999px; background: var(--wb-surface-section, transparent); color: var(--wb-text-secondary, var(--text-secondary));
  font-size: 10px; text-overflow: ellipsis; white-space: nowrap; cursor: pointer;
}
.uml-card__dep-group button:hover { border-color: var(--wb-accent, var(--primary-color)); color: var(--wb-accent, var(--primary-color)); }
.uml-card__dep-group em { color: var(--wb-text-muted, var(--text-secondary)); font-size: 10px; font-style: normal; }
.uml-card__more {
  padding: 5px 0; border: 1px dashed var(--wb-border, var(--border-light)); border-radius: 7px;
  background: transparent; color: var(--wb-text-secondary, var(--text-secondary)); font-size: 11px; cursor: pointer;
}
.uml-card__more:hover { border-color: var(--wb-accent, var(--primary-color)); color: var(--wb-accent, var(--primary-color)); }
.acg-topology.is-workbench .uml-card { border-color: var(--wb-border); background: var(--wb-surface-1); box-shadow: var(--wb-shadow-section, 0 6px 18px rgba(15, 35, 40, 0.12)); }

.acg-topology .uml-card.execution-detail {
  position: relative; z-index: auto; width: 100%; max-height: 520px;
  border: 0; border-radius: 0; box-shadow: none;
}

@media (max-width: 760px) {
  .graph-stage.has-detail .graph-fab { right: 16px; }
  .graph-stage.has-detail { grid-template-columns: 1fr; }
  .node-detail { height: auto; max-height: 340px; border-left: 0; border-top: 1px solid var(--border-light); }
  .head-right { position: static; }
  .panel-head { justify-content: space-between; }
  .meta { display: none; }
  .graph-toolbar { top: 12px; left: 12px; width: calc(100% - 24px); box-sizing: border-box; overflow-x: auto; justify-content: flex-start; }
  .view-mode { flex: 0 0 auto; }
  .view-mode button { padding: 0 8px; }
  .legend.expanded { right: 16px; width: auto; max-width: none; max-height: 280px; }
}
</style>
