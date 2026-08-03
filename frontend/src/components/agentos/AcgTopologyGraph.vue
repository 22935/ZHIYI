<!-- ACG 拓扑图 — 使用 vis-network 渲染 ACG 交互式拓扑，含步骤、Agent、记忆、证据、控制节点和图例 -->
<template>
  <section ref="sectionRef" class="acg-topology ui-surface">
    <header class="panel-head">
      <div class="head-left">
        <el-icon class="head-icon"><Share /></el-icon>
        <h4>ACG 拓扑图</h4>
      </div>
      <div class="head-right">
        <span class="meta" v-if="hasData">{{ stats }}</span>
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
    </header>

    <div v-if="hasData" class="graph-toolbar">
      <div class="view-mode" aria-label="拓扑视图模式">
        <button type="button" :class="{ active: !focusMainPath }" @click="setFocusMainPath(false)">全图</button>
        <button type="button" :class="{ active: focusMainPath }" @click="setFocusMainPath(true)">
          <el-icon><Aim /></el-icon>
          主执行链
        </button>
      </div>
      <div v-if="!focusMainPath" class="edge-filters" aria-label="边类型筛选">
        <label v-for="item in EDGE_TYPES" :key="item.value" :class="{ checked: selectedEdgeTypes.includes(item.value) }">
          <input v-model="selectedEdgeTypes" type="checkbox" :value="item.value" />
          <i :style="{ backgroundColor: edgeColor(item.value) }" />
          {{ item.label }}
        </label>
      </div>
    </div>

    <div v-if="!hasData" class="empty">暂无 ACG 拓扑数据，请先运行一个 ACG 引擎工作流</div>
    <div v-else class="graph-stage" :class="{ 'has-detail': selectedNode }">
      <div ref="graphRef" class="graph-canvas" />
      <aside v-if="selectedNode" class="node-detail" aria-label="节点详情">
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
          <div v-if="selectedNodeStatus"><dt>运行状态</dt><dd class="node-status" :class="selectedNodeStatus">{{ selectedNodeStatus }}</dd></div>
          <div v-if="selectedStepState?.agentName || selectedNode.agentName"><dt>Agent</dt><dd>{{ selectedStepState?.agentName || selectedNode.agentName }}</dd></div>
          <div v-if="selectedNode.capability"><dt>能力</dt><dd>{{ selectedNode.capability }}</dd></div>
          <div v-if="selectedStepState?.currentBinding"><dt>当前 Binding</dt><dd><code>{{ bindingLabel(selectedStepState.currentBinding) }}</code></dd></div>
          <div v-if="selectedStepState?.currentBinding"><dt>来源</dt><dd>{{ bindingSourceLabel(selectedStepState.currentBinding) }}</dd></div>
          <div v-if="selectedStepState?.currentBinding?.pluginId"><dt>插件</dt><dd><code>{{ selectedStepState.currentBinding.pluginId }}</code></dd></div>
          <div v-if="selectedStepState?.currentBinding?.pluginVersion"><dt>插件版本</dt><dd>{{ selectedStepState.currentBinding.pluginVersion }}</dd></div>
          <div v-if="selectedStepState?.currentBinding?.modelName"><dt>模型</dt><dd>{{ selectedStepState.currentBinding.modelName }}</dd></div>
          <div v-if="selectedStepState?.currentBinding?.bindingId"><dt>Binding ID</dt><dd><code>{{ selectedStepState.currentBinding.bindingId }}</code></dd></div>
          <div v-if="(selectedStepState?.bindingSwitchCount || 0) > 0"><dt>替代 Binding</dt><dd>已切换 {{ selectedStepState?.bindingSwitchCount }} 次</dd></div>
          <div v-if="selectedStepState?.attempt"><dt>Attempt</dt><dd>{{ selectedStepState.attempt }} 次</dd></div>
          <div v-if="selectedStepState?.createdGraphVersion"><dt>创建图版本</dt><dd>v{{ selectedStepState.createdGraphVersion }}</dd></div>
          <div v-if="selectedStepState?.sourcePatchId"><dt>来源 Patch</dt><dd><code>{{ selectedStepState.sourcePatchId }}</code></dd></div>
          <div v-if="selectedAllowedSkills.length">
            <dt>可用技能</dt>
            <dd class="skill-list"><code v-for="skill in selectedAllowedSkills" :key="skill">{{ skill }}</code></dd>
          </div>
          <div v-if="selectedNode.controlType"><dt>控制类型</dt><dd>{{ selectedNode.controlType }}</dd></div>
        </dl>
        <p v-if="selectedNode.goal || selectedNode.description" class="node-description">
          {{ selectedNode.goal || selectedNode.description }}
        </p>
        <div v-if="selectedStepState?.attempts?.length" class="runtime-detail-group">
          <strong>Attempt 历史 · {{ selectedStepState.attempts.length }}</strong>
          <span v-for="attempt in selectedStepState.attempts" :key="attempt.attemptId">
            #{{ attempt.attemptNumber }} · {{ attempt.status }} · {{ attempt.agentName || attempt.bindingId || '默认绑定' }}
          </span>
        </div>
        <div v-if="selectedStepState?.bindingHistory?.length" class="runtime-detail-group">
          <strong>Binding 历史 · {{ selectedStepState.bindingHistory.length }}</strong>
          <span v-for="(binding, index) in selectedStepState.bindingHistory" :key="binding.sourcePatchId || `${binding.bindingId}-${index}`">
            {{ binding.bindingId }} · v{{ binding.selectedAtGraphVersion || 1 }}
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
    </div>

    <div v-if="hasData" class="legend">
      <span class="legend-item"><i class="dot step"></i>步骤</span>
      <span class="legend-item"><i class="dot agent"></i>智能体</span>
      <span class="legend-item"><i class="dot skill"></i>技能</span>
      <span class="legend-item"><i class="dot memory"></i>记忆</span>
      <span class="legend-item"><i class="dot evidence"></i>证据</span>
      <span class="legend-item"><i class="dot control"></i>控制</span>
      <span class="legend-item"><i class="ring done"></i>已完成</span>
      <span class="legend-item"><i class="ring running"></i>执行中</span>
      <span class="legend-item"><i class="ring waiting"></i>待审核/重试</span>
      <span class="legend-item"><i class="ring failed"></i>失败</span>
      <span class="legend-item"><b class="badge runtime">+</b>运行时新增</span>
      <span class="legend-item"><b class="badge binding">⇄</b>切换 Binding</span>
      <span class="legend-item"><b class="badge skipped">Skipped</b>条件跳过</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Aim, ArrowDownBold, Close, FullScreen, RefreshRight, Share } from '@element-plus/icons-vue'
import { DataSet } from 'vis-data'
import { Network } from 'vis-network'
import type { AcgBlueprint, AcgNode, AcgEdge, AcgStepState } from '@/services/api/agentos'
import { mapEdgeVisualState, mapNodeVisualState } from '@/utils/runtimePresentation'
import { edgeActivationOpacity, graphEdgeWidth, mixGraphColor } from '@/utils/acgGraphVisuals'

const props = defineProps<{
  blueprint: AcgBlueprint | null
  completedStepIds?: string[]
  stepStates?: AcgStepState[]
  collapsible?: boolean
}>()

const emit = defineEmits<{
  collapse: []
}>()

const graphRef = ref<HTMLElement | null>(null)
const sectionRef = ref<HTMLElement | null>(null)
const selectedNodeId = ref('')
const focusMainPath = ref(false)
const isFullscreen = ref(false)
const fullscreenSupported = typeof document !== 'undefined' && typeof document.documentElement.requestFullscreen === 'function'
let network: Network | null = null
let nodesData: DataSet<any> | null = null
let edgesData: DataSet<any> | null = null
let graphStructureKey = ''
let stabilizationTimer: number | undefined
let themeObserver: MutationObserver | null = null
let layoutFinalized = false
let pendingViewState: { position: { x: number; y: number }; scale: number } | null = null

const ENDPOINT_MIN_GAP = 190
const ENDPOINT_MAX_GAP = 280
const SAFE_VIEW_SCALE = 0.86

const EDGE_TYPES: Array<{ value: AcgEdge['edgeType']; label: string }> = [
  { value: 'dependency', label: '依赖' },
  { value: 'communication', label: '通信' },
  { value: 'execution', label: '执行' },
  { value: 'write', label: '写入' },
  { value: 'read', label: '读取' },
  { value: 'support', label: '证据' },
  { value: 'control_flow', label: '控制流' }
]
const selectedEdgeTypes = ref<AcgEdge['edgeType'][]>(EDGE_TYPES.map(item => item.value))

const hasData = computed(() => {
  return !!props.blueprint && Array.isArray(props.blueprint.nodes) && props.blueprint.nodes.length > 0
})

const renderableBlueprint = computed<AcgBlueprint | null>(() => {
  if (!props.blueprint) return null
  const connectedNodeIds = new Set(
    props.blueprint.edges.flatMap(edge => [edge.sourceId, edge.targetId])
  )
  const nodes = props.blueprint.nodes.filter(
    node => node.nodeType !== 'skill' || connectedNodeIds.has(node.nodeId)
  )
  return { ...props.blueprint, nodes }
})

const visibleBlueprint = computed<AcgBlueprint | null>(() => {
  const blueprint = renderableBlueprint.value
  if (!blueprint) return null
  if (focusMainPath.value) {
    const nodes = blueprint.nodes.filter(node => node.nodeType === 'step' || node.nodeType === 'control')
    const nodeIds = new Set(nodes.map(node => node.nodeId))
    const edges = blueprint.edges.filter(edge =>
      (edge.edgeType === 'dependency' || edge.edgeType === 'control_flow')
      && nodeIds.has(edge.sourceId)
      && nodeIds.has(edge.targetId)
    )
    return { ...blueprint, nodes, edges }
  }

  const selected = new Set(selectedEdgeTypes.value)
  const edges = blueprint.edges.filter(edge => selected.has(edge.edgeType))
  if (selected.size === EDGE_TYPES.length) return blueprint
  const connectedNodeIds = new Set(edges.flatMap(edge => [edge.sourceId, edge.targetId]))
  const nodes = blueprint.nodes.filter(node => node.nodeType === 'step' || connectedNodeIds.has(node.nodeId))
  return { ...blueprint, nodes, edges }
})

const selectedNode = computed(() =>
  props.blueprint?.nodes.find(node => node.nodeId === selectedNodeId.value) || null
)
const selectedAllowedSkills = computed(() => {
  const value = selectedNode.value?.metadata?.allowedSkills
  return Array.isArray(value) ? value.map(String).filter(Boolean) : []
})
const stateByStep = computed(() => new Map((props.stepStates || []).map(item => [item.stepId, item])))
const selectedStepState = computed(() => selectedNode.value ? stateByStep.value.get(selectedNode.value.nodeId) : undefined)
const selectedNodeStatus = computed(() => {
  if (!selectedNode.value) return ''
  return stateByStep.value.get(selectedNode.value.nodeId)?.status
    || ((props.completedStepIds || []).includes(selectedNode.value.nodeId) ? 'completed' : '')
})
const bindingLabel = (binding: Record<string, any>) =>
  String(binding.agentName || binding.bindingId || binding.assignedAgentId || '默认绑定')
const bindingSourceLabel = (binding: Record<string, any>) =>
  binding.source === 'plugin' ? 'Plugin' : 'Native'
const incomingConnections = computed(() =>
  visibleBlueprint.value?.edges.filter(edge => edge.targetId === selectedNodeId.value) || []
)
const outgoingConnections = computed(() =>
  visibleBlueprint.value?.edges.filter(edge => edge.sourceId === selectedNodeId.value) || []
)

const stats = computed(() => {
  if (!renderableBlueprint.value || !visibleBlueprint.value) return ''
  const visible = `${visibleBlueprint.value.nodes.length} 节点 / ${visibleBlueprint.value.edges.length} 边`
  if (visibleBlueprint.value.nodes.length === renderableBlueprint.value.nodes.length
    && visibleBlueprint.value.edges.length === renderableBlueprint.value.edges.length) return visible
  return `${visible}（全图 ${renderableBlueprint.value.nodes.length} / ${renderableBlueprint.value.edges.length}）`
})

// 节点类型 → 配色（沿用项目色板）
const NODE_STYLE: Record<string, { background: string; border: string; shape: string }> = {
  step: { background: '#dbe7e3', border: '#3f6b63', shape: 'box' },
  agent: { background: '#cfe0f0', border: '#496b8f', shape: 'ellipse' },
  skill: { background: '#e6e0f0', border: '#6b5b95', shape: 'ellipse' },
  memory: { background: '#fcefd6', border: '#9a7432', shape: 'database' },
  evidence: { background: '#f6dede', border: '#b24a4a', shape: 'diamond' },
  control: { background: '#e2e8e0', border: '#727c76', shape: 'hexagon' }
}

// 边类型 → 样式
const EDGE_STYLE: Record<string, { color: string; dashes: boolean | number[] }> = {
  dependency: { color: '#3f6b63', dashes: false },
  communication: { color: '#496b8f', dashes: [4, 4] },
  control_flow: { color: '#9a7432', dashes: [2, 3] },
  write: { color: '#9a7432', dashes: [6, 3] },
  read: { color: '#9a7432', dashes: [6, 3] },
  support: { color: '#b24a4a', dashes: [2, 2] },
  execution: { color: '#727c76', dashes: false }
}

const edgeColor = (edgeType: AcgEdge['edgeType']) => EDGE_STYLE[edgeType]?.color || '#727c76'
const edgeTypeLabel = (edgeType: AcgEdge['edgeType']) =>
  EDGE_TYPES.find(item => item.value === edgeType)?.label || edgeType
const nodeTypeLabel = (nodeType: AcgNode['nodeType']) => ({
  step: '步骤',
  agent: '智能体',
  skill: '技能',
  memory: '记忆',
  evidence: '证据',
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
  // The topology is a technical drawing surface. Keep its semantic palette
  // stable and bright even when the surrounding application uses a dark theme.
  const primary = '#716c9e'
  const info = '#4d7fdf'
  const warning = '#a97626'
  const danger = '#c94e54'
  const success = '#387a5b'
  const textSecondary = '#6f7284'
  const nodeSurface = '#fcfdfd'
  const nodeSurfaceStrong = '#f8faf9'

  Object.assign(NODE_STYLE, {
    step: { background: mixGraphColor(success, nodeSurfaceStrong, 0.18), border: success, shape: 'box' },
    agent: { background: mixGraphColor(info, nodeSurface, 0.15), border: info, shape: 'ellipse' },
    skill: { background: mixGraphColor(primary, nodeSurface, 0.14), border: primary, shape: 'ellipse' },
    memory: { background: mixGraphColor(warning, nodeSurfaceStrong, 0.19), border: warning, shape: 'database' },
    evidence: { background: mixGraphColor(danger, nodeSurfaceStrong, 0.15), border: danger, shape: 'diamond' },
    control: { background: mixGraphColor(textSecondary, nodeSurfaceStrong, 0.13), border: textSecondary, shape: 'hexagon' }
  })
  Object.assign(EDGE_STYLE, {
    dependency: { color: success, dashes: false },
    communication: { color: info, dashes: [4, 4] },
    control_flow: { color: warning, dashes: [2, 3] },
    write: { color: warning, dashes: [6, 3] },
    read: { color: warning, dashes: [6, 3] },
    support: { color: danger, dashes: [2, 2] },
    execution: { color: textSecondary, dashes: false }
  })
}

const buildNodeRows = (nodes: AcgNode[], completed: Set<string>, states: Map<string, AcgStepState>) => {
  applyThemeToGraphStyles()
  const done = '#387a5b'
  const textPrimary = '#26332f'
  const textSecondary = '#66736f'
  const info = '#4d7fdf'
  const warning = '#a97626'
  const danger = '#c94e54'
  return nodes.map((node) => {
    const style = NODE_STYLE[node.nodeType] || NODE_STYLE.step
    const stepState = states.get(node.nodeId)
    const visual = mapNodeVisualState(stepState)
    const status = stepState?.status || (completed.has(node.nodeId) ? 'completed' : '')
    const isDone = status === 'completed'
    const role = endpointRole(node)
    const isStart = role === 'start'
    const isEnd = role === 'end'
    const endpointColor = isStart ? done : isEnd ? info : ''
    const statusColor = isDone
      ? done
      : status === 'running'
        ? info
        : status === 'waiting_review' || status === 'retrying'
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
    const label = badges ? `${baseLabel}\n[${badges}]` : baseLabel
    const isStep = node.nodeType === 'step'
    const isEndpoint = isStart || isEnd
    return {
      id: node.nodeId,
      label,
      title: `${node.nodeId}\n${node.nodeType}${status ? `\n${status}` : ''}${badges ? `\n${badges}` : ''}`,
      shape: isStart ? 'circle' : isEnd ? 'box' : style.shape,
      color: {
        background: endpointColor || style.background,
        border: endpointColor || style.border,
        highlight: { background: endpointColor || style.background, border: endpointColor || style.border },
        hover: { background: endpointColor || style.background, border: endpointColor || style.border }
      },
      borderWidth: isEndpoint ? 3.5 : status || visual.runtimeAdded ? 2.6 : 1.8,
      borderWidthSelected: isEndpoint ? 5 : 4,
      opacity: visual.conditionalSkipped ? 0.42 : status === 'cancelled' ? 0.58 : 1,
      shadow: isEndpoint
        ? { enabled: true, color: endpointColor, size: 12, x: 0, y: 2 }
        : statusColor
          ? {
              enabled: true,
              color: statusColor,
              size: status === 'running' ? 12 : status === 'failed' ? 9 : isDone ? 2 : 7,
              x: 0,
              y: 0
            }
          : visual.runtimeAdded
            ? { enabled: true, color: '#5b5bd6', size: 7, x: 0, y: 0 }
            : false,
      // Step 为主干节点（大、醒目）；Agent/Memory/Evidence 为认知卫星节点（小）
      size: isEndpoint ? 32 : isStep ? 26 : 16,
      font: {
        size: isEndpoint ? 14 : isStep ? (focusMainPath.value ? 15 : 14) : 12,
        color: isEndpoint ? '#ffffff' : isStep ? textPrimary : textSecondary,
        face: isEndpoint ? 'sans-serif' : 'inherit',
        bold: isEndpoint ? { color: '#ffffff', size: 14 } : undefined
      },
      mass: isEndpoint ? 5 : isStep ? 3 : 1,
      margin: isEndpoint ? 12 : isStep ? 10 : 6,
      fixed: isEndpoint ? { x: true, y: true } : false,
      ...(isStart ? { x: 0, y: -440 } : isEnd ? { x: 0, y: 440 } : {})
    }
  })
}

const buildEdgeRows = (edges: AcgEdge[]) => {
  return edges.map((edge, index) => {
    const style = EDGE_STYLE[edge.edgeType] || EDGE_STYLE.dependency
    const activation = mapEdgeVisualState(edge.activation)
    const length = ({
      dependency: 190,
      communication: 165,
      control_flow: 180,
      execution: 125,
      write: 120,
      read: 130,
      support: 135
    } as Record<string, number>)[edge.edgeType] || 150
    return {
      id: edge.edgeId || `e-${index}`,
      from: edge.sourceId,
      to: edge.targetId,
      arrows: { to: { enabled: true, scaleFactor: 0.84, type: 'arrow' } },
      arrowStrikethrough: false,
      endPointOffset: { from: 2, to: 4 },
      color: {
        color: style.color,
        highlight: style.color,
        hover: style.color,
        opacity: edgeActivationOpacity(activation)
      },
      dashes: activation === 'inactive' ? [6, 5] : activation === 'terminated' ? [2, 6] : style.dashes,
      label: activation === 'active' ? undefined : activation.toUpperCase(),
      smooth: { enabled: true, type: 'continuous' },
      // 依赖主干边更粗更短（强弹簧），认知关联边更细
      width: graphEdgeWidth(edge.edgeType),
      selectionWidth: 1.4,
      hoverWidth: 0.8,
      length
    }
  })
}

const options = {
  autoResize: true,
  layout: { improvedLayout: true, randomSeed: 42 },
  physics: {
    enabled: true,
    solver: 'forceAtlas2Based',
    forceAtlas2Based: {
      gravitationalConstant: -85,
      centralGravity: 0.006,
      springLength: 170,
      springConstant: 0.075,
      damping: 0.5,
      avoidOverlap: 1
    },
    maxVelocity: 28,
    minVelocity: 0.45,
    timestep: 0.5,
    adaptiveTimestep: true,
    stabilization: { enabled: true, iterations: 360, fit: true }
  },
  interaction: { hover: true, dragNodes: true, zoomView: true, navigationButtons: false }
}

const getStructureKey = (blueprint: AcgBlueprint) => JSON.stringify({
  nodes: blueprint.nodes.map(node => [node.nodeId, node.nodeType]),
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
  if (!network || !blueprint) return

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
  network.fit({ animation: false })
  const fittedScale = network.getScale()
  const position = network.getViewPosition()
  network.moveTo({
    position,
    scale: fittedScale * SAFE_VIEW_SCALE,
    animation: animation ? { duration: 360, easingFunction: 'easeInOutQuad' } : false
  })
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
    fitWithSafePadding(animation)
  }
}

const render = async () => {
  await nextTick()
  const blueprint = visibleBlueprint.value
  if (!graphRef.value || !hasData.value || !blueprint) return
  if (selectedNodeId.value && !blueprint.nodes.some(node => node.nodeId === selectedNodeId.value)) {
    selectedNodeId.value = ''
  }
  const completed = new Set(props.completedStepIds || [])
  const states = new Map<string, AcgStepState>((props.stepStates || []).map(item => [item.stepId, item]))
  const nodeRows = buildNodeRows(blueprint.nodes, completed, states)
  const edgeRows = buildEdgeRows(blueprint.edges)
  const nextStructureKey = getStructureKey(blueprint)

  // Polling frequently returns a new object with the same graph structure.
  // Update labels/status in place so existing positions and user dragging are preserved.
  if (network && nodesData && edgesData && graphStructureKey === nextStructureKey) {
    nodesData.update(nodeRows)
    edgesData.update(edgeRows)
    network.redraw()
    return
  }

  pendingViewState = network
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
  layoutFinalized = false
  const data = { nodes: nodesData, edges: edgesData }
  network = new Network(graphRef.value, data as any, options as any)
  if (selectedNodeId.value) network.selectNodes([selectedNodeId.value])
  network.on('selectNode', params => {
    selectedNodeId.value = String(params.nodes[0] || '')
    window.setTimeout(() => resetView(false), 140)
  })
  network.on('deselectNode', () => {
    selectedNodeId.value = ''
    window.setTimeout(() => resetView(false), 140)
  })

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
  fitWithSafePadding(animation)
}

const syncFullscreenState = () => {
  isFullscreen.value = document.fullscreenElement === sectionRef.value
  window.setTimeout(() => {
    network?.redraw()
    resetView(false)
  }, 120)
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
  if (event.key === 'Escape' && document.fullscreenElement === sectionRef.value) {
    void document.exitFullscreen()
  }
}

const clearSelection = () => {
  selectedNodeId.value = ''
  network?.unselectAll()
}

const selectRelatedNode = (nodeId: string) => {
  if (!visibleBlueprint.value?.nodes.some(node => node.nodeId === nodeId)) return
  selectedNodeId.value = nodeId
  network?.selectNodes([nodeId])
  network?.focus(nodeId, { scale: 1.2, animation: true })
}

const setFocusMainPath = (value: boolean) => {
  focusMainPath.value = value
  clearSelection()
}

watch(
  () => [props.blueprint, props.completedStepIds, props.stepStates, selectedEdgeTypes.value, focusMainPath.value],
  () => render(),
  { deep: true }
)
onMounted(() => {
  document.addEventListener('fullscreenchange', syncFullscreenState)
  document.addEventListener('keydown', handleFullscreenEscape)
  themeObserver = new MutationObserver(() => render())
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-color-scheme'] })
  render()
})
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', syncFullscreenState)
  document.removeEventListener('keydown', handleFullscreenEscape)
  if (document.fullscreenElement === sectionRef.value) {
    void document.exitFullscreen()
  }
  stopPhysics()
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
  --primary-color: #5b5bd6;
  --primary-fade: #ececff;
  --success: #387a5b;
  --info: #4d7fdf;
  --warning: #a97626;
  --danger: #c94e54;
  --text-primary: #26332f;
  --text-secondary: #66736f;
  --text-muted: #7e8985;
  --text-disabled: #919b97;
  --bg-panel: #ffffff;
  --bg-input: #f3f5f4;
  --border-light: #dfe4e8;
  --border-strong: #bcc6c2;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
  color: var(--text-primary);
  background: #fcfdfd;
  border-color: var(--border-light);
  box-shadow: 0 1px 3px rgba(34, 61, 52, 0.08);
}
.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-sm);
}
.head-left { display: flex; align-items: center; gap: 6px; }
.head-icon { font-size: 15px; color: var(--primary-color); }
.panel-head h4 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.head-right { display: flex; align-items: center; gap: 8px; }
.meta { font-size: 11px; color: var(--text-secondary); font-weight: 600; }
.action-btn {
  width: 28px; height: 28px; display: flex; align-items: center; justify-content: center;
  border: none; background: var(--primary-fade); color: var(--primary-color);
  border-radius: 6px; cursor: pointer; transition: all .2s ease;
}
.action-btn:hover { background: var(--primary-color); color: #fff; }
.action-btn.active { background: var(--primary-color); color: #fff; }
.graph-toolbar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 0 0 var(--space-sm); margin-bottom: var(--space-sm);
  border-bottom: 1px solid var(--border-light);
}
.view-mode { display: inline-flex; padding: 2px; background: var(--bg-input); border-radius: 6px; }
.view-mode button {
  min-height: 28px; display: inline-flex; align-items: center; gap: 4px; padding: 0 9px;
  border: 0; border-radius: 5px; background: transparent; color: var(--text-secondary);
  font-size: 11px; cursor: pointer;
}
.view-mode button.active { background: var(--primary-color); color: #fff; }
.edge-filters { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; }
.edge-filters label {
  min-height: 26px; display: inline-flex; align-items: center; gap: 5px; padding: 0 7px;
  border: 1px solid var(--border-light); border-radius: 6px; color: var(--text-disabled);
  font-size: 10px; cursor: pointer; transition: border-color .18s ease, color .18s ease;
}
.edge-filters label.checked { color: var(--text-secondary); border-color: var(--border-strong); }
.edge-filters input { position: absolute; opacity: 0; pointer-events: none; }
.edge-filters i { width: 12px; height: 2px; border-radius: 1px; opacity: .35; }
.edge-filters label.checked i { opacity: 1; }
.empty { padding: 32px 12px; text-align: center; color: var(--text-secondary); font-size: 13px; }
.graph-stage { display: grid; grid-template-columns: minmax(0, 1fr); min-height: 460px; }
.graph-stage.has-detail { grid-template-columns: minmax(0, 1fr) 280px; }
.graph-canvas { width: 100%; max-width: 100%; min-width: 0; height: 460px; min-height: 360px; }
.node-detail {
  height: 460px; min-width: 0; overflow-y: auto; padding: 12px;
  border-left: 1px solid var(--border-light); background: var(--bg-panel);
}
.node-detail header { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
.node-detail header span { font-size: 10px; color: var(--primary-color); font-weight: 700; }
.node-detail h5 { margin: 2px 0 0; font-size: 14px; color: var(--text-primary); overflow-wrap: anywhere; }
.node-detail header button {
  width: 28px; height: 28px; flex: 0 0 auto; display: grid; place-items: center;
  border: 0; border-radius: 6px; background: var(--bg-input); color: var(--text-secondary); cursor: pointer;
}
.node-detail dl { display: flex; flex-direction: column; gap: 7px; margin: 14px 0; }
.node-detail dl div { display: grid; grid-template-columns: 66px minmax(0, 1fr); gap: 8px; }
.node-detail dt { font-size: 10px; color: var(--text-disabled); }
.node-detail dd { margin: 0; min-width: 0; font-size: 11px; color: var(--text-secondary); overflow-wrap: anywhere; }
.node-detail code { color: var(--text-primary); }
.node-detail .skill-list { display: flex; flex-wrap: wrap; gap: 4px; }
.node-detail .skill-list code {
  padding: 2px 5px; border: 1px solid var(--border-light); border-radius: 4px; background: var(--bg-input);
}
.node-status { font-weight: 700; }
.node-status.completed { color: var(--success); }
.node-status.running { color: var(--info); }
.node-status.waiting_review, .node-status.retrying { color: var(--warning); }
.node-status.failed { color: var(--danger); }
.node-status.skipped_by_condition { color: var(--text-secondary); }
.node-description { margin: 0 0 14px; font-size: 11px; line-height: 1.55; color: var(--text-secondary); }
.runtime-detail-group { display: flex; flex-direction: column; gap: 4px; margin: 10px 0; padding: 8px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-input); }
.runtime-detail-group strong { color: var(--text-primary); font-size: 10px; }
.runtime-detail-group span { color: var(--text-secondary); font: 10px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.runtime-summary { max-height: 90px; margin: 8px 0; padding: 7px; overflow: auto; border-radius: 5px; background: var(--bg-input); color: var(--text-secondary); font: 10px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; overflow-wrap: anywhere; }
.runtime-summary.is-error { color: var(--danger); }
.connection-group { display: flex; flex-direction: column; gap: 5px; margin-top: 12px; }
.connection-group strong { font-size: 11px; color: var(--text-primary); }
.connection-group > span { font-size: 10px; color: var(--text-disabled); }
.connection-group button {
  display: flex; align-items: center; gap: 6px; min-width: 0; padding: 5px 7px;
  border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-input);
  color: var(--text-secondary); font: 10px monospace; text-align: left; cursor: pointer; overflow-wrap: anywhere;
}
.connection-group button:hover { border-color: var(--primary-color); color: var(--text-primary); }
.connection-group small { flex: 0 0 auto; color: var(--primary-color); font: 9px sans-serif; }
.legend {
  display: flex; flex-wrap: wrap; gap: 12px; padding-top: var(--space-sm);
  border-top: 1px solid var(--border-light); margin-top: var(--space-sm);
}
.legend-item { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-secondary); }
.dot { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
.dot.step { background: color-mix(in srgb, var(--success) 18%, var(--bg-input)); border: 1.5px solid var(--success); }
.dot.agent { background: color-mix(in srgb, var(--info) 15%, var(--bg-panel)); border: 1.5px solid var(--info); border-radius: 50%; }
.dot.skill { background: color-mix(in srgb, #716c9e 14%, var(--bg-panel)); border: 1.5px solid #716c9e; border-radius: 50%; }
.dot.memory { background: color-mix(in srgb, var(--warning) 19%, var(--bg-input)); border: 1.5px solid var(--warning); }
.dot.evidence { background: color-mix(in srgb, var(--danger) 15%, var(--bg-input)); border: 1.5px solid var(--danger); transform: rotate(45deg); }
.dot.control { background: color-mix(in srgb, var(--text-secondary) 13%, var(--bg-input)); border: 1.5px solid var(--text-secondary); }
.ring { width: 10px; height: 10px; border-radius: 50%; display: inline-block; border: 3px solid var(--success); }
.ring.running { border-color: var(--info); }
.ring.waiting { border-color: var(--warning); }
.ring.failed { border-color: var(--danger); }
.badge { min-width: 15px; padding: 1px 3px; border-radius: 4px; color: #fff; font-size: 9px; line-height: 13px; text-align: center; }
.badge.runtime { background: var(--primary-color); }
.badge.binding { background: var(--info); }
.badge.skipped { background: var(--text-muted); }

.acg-topology:fullscreen {
  width: 100vw;
  height: 100vh;
  padding: 16px;
  background: #fcfdfd;
}
.acg-topology:fullscreen .graph-stage { flex: 1 1 auto; min-height: 0; }
.acg-topology:fullscreen .graph-canvas,
.acg-topology:fullscreen .node-detail { height: 100%; min-height: 0; }
.acg-topology:fullscreen .graph-toolbar,
.acg-topology:fullscreen .legend,
.acg-topology:fullscreen .panel-head { flex: 0 0 auto; }

@media (max-width: 760px) {
  .graph-stage.has-detail { grid-template-columns: 1fr; }
  .node-detail { height: auto; max-height: 320px; border-left: 0; border-top: 1px solid var(--border-light); }
  .meta { display: none; }
}
</style>
