<template>
  <div class="topology-graph">
    <svg
      ref="svgRef"
      viewBox="0 0 960 500"
      class="topology-svg"
      role="img"
      aria-label="联邦学习参与方与全局模型的同步拓扑"
    >
      <defs>
        <filter id="topology-shadow" x="-20%" y="-25%" width="140%" height="150%">
          <feDropShadow dx="0" dy="8" stdDeviation="10" flood-color="var(--shadow-color)" flood-opacity="0.32" />
        </filter>
        <filter id="packet-glow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g class="topology-guides" aria-hidden="true">
        <path d="M 118 250 H 842" />
        <path d="M 480 66 V 434" />
        <circle cx="480" cy="250" r="112" />
      </g>

      <g class="topology-connections">
        <g v-for="(client, index) in clientPositions" :key="`connection-${client.id}`">
          <path :d="connectionPath(client)" class="connection-base" />
          <path
            v-if="client.active"
            :d="connectionPath(client)"
            class="connection-active"
            :style="{ animationDelay: `${index * -0.55}s` }"
          />
          <circle
            v-if="client.active"
            :cx="interpolate(cx, client.x, flowProgress[index] ?? 0)"
            :cy="interpolate(cy, client.y, flowProgress[index] ?? 0)"
            r="4"
            class="data-packet data-packet-out"
            filter="url(#packet-glow)"
          />
          <circle
            v-if="client.active"
            :cx="interpolate(client.x, cx, flowProgress[index] ?? 0)"
            :cy="interpolate(client.y, cy, flowProgress[index] ?? 0)"
            r="3"
            class="data-packet data-packet-in"
            filter="url(#packet-glow)"
          />
        </g>
      </g>

      <g class="aggregation-node" :transform="`translate(${cx}, ${cy})`" filter="url(#topology-shadow)">
        <rect x="-116" y="-68" width="232" height="136" rx="18" class="aggregation-halo" />
        <rect x="-104" y="-56" width="208" height="112" rx="14" class="aggregation-surface" />
        <g class="aggregation-symbol" aria-hidden="true">
          <circle cx="-70" cy="-20" r="5" />
          <circle cx="-50" cy="-20" r="5" />
          <circle cx="-60" cy="-4" r="5" />
          <path d="M -66 -18 L -54 -18 M -67 -16 L -61 -8 M -53 -16 L -59 -8" />
        </g>
        <text x="-38" y="-22" class="aggregation-kicker">全局聚合器</text>
        <text x="-38" y="4" class="aggregation-title">FedAvg</text>
        <text x="-38" y="24" class="aggregation-version">模型版本 v{{ globalVersion }}</text>
        <line x1="-82" y1="38" x2="82" y2="38" class="aggregation-rule" />
        <text x="0" y="52" text-anchor="middle" class="aggregation-status">
          {{ activeClientCount }}/{{ clients.length }} 节点已同步
        </text>
      </g>

      <g
        v-for="(client, index) in clientPositions"
        :key="client.id"
        class="participant-node"
        :class="{ 'is-active': client.active, 'is-hovered': hoveredClient === index }"
        :transform="`translate(${client.x}, ${client.y})`"
        @mouseenter="hoveredClient = index"
        @mouseleave="hoveredClient = -1"
      >
        <rect x="-112" y="-42" width="224" height="84" rx="12" class="participant-surface" filter="url(#topology-shadow)" />
        <rect x="-112" y="-42" width="4" height="84" rx="2" class="participant-accent" />
        <circle cx="-80" cy="-12" r="13" class="participant-avatar" />
        <path d="M -86 -12 H -74 M -80 -18 V -6" class="participant-mark" />
        <circle cx="-63" cy="-23" r="5" class="participant-state" />
        <text x="-56" y="-10" class="participant-label">{{ client.label }}</text>
        <text x="-56" y="11" class="participant-meta">{{ client.active ? '本地训练完成' : '等待节点重连' }}</text>
        <text x="-56" y="29" class="participant-detail">
          准确率 {{ formatAccuracy(client.accuracy) }} · {{ formatDataSize(client.dataSize) }} 样本
        </text>
        <g v-if="hoveredClient === index" class="participant-tooltip">
          <rect x="-100" y="-76" width="200" height="24" rx="6" />
          <text x="0" y="-60" text-anchor="middle">
            {{ client.active ? '正在与聚合器交换参数' : '节点暂未参与当前轮次' }}
          </text>
        </g>
      </g>
    </svg>

    <div class="topology-legend" aria-label="拓扑图例">
      <div class="legend-item">
        <span class="legend-center"></span>
        <span>全局聚合</span>
      </div>
      <div class="legend-item">
        <span class="legend-online"></span>
        <span>在线参与方</span>
      </div>
      <div class="legend-item">
        <span class="legend-offline"></span>
        <span>离线参与方</span>
      </div>
      <div class="legend-item">
        <span class="legend-flow"></span>
        <span>参数双向同步</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

interface ClientNode {
  id: string
  label: string
  active: boolean
  accuracy?: number
  dataSize?: number
}

interface PositionedClient extends ClientNode {
  x: number
  y: number
}

const props = withDefaults(defineProps<{
  clients?: ClientNode[]
  globalVersion?: string
  aggregating?: boolean
}>(), {
  clients: () => [
    { id: 'c1', label: '律师 Agent', active: true, accuracy: 87.3, dataSize: 12450 },
    { id: 'c2', label: '教师 Agent', active: true, accuracy: 84.6, dataSize: 8920 },
    { id: 'c3', label: '程序员 Agent', active: true, accuracy: 86.1, dataSize: 15380 },
    { id: 'c4', label: '作家 Agent', active: true, accuracy: 83.2, dataSize: 6740 }
  ],
  globalVersion: '3.2',
  aggregating: false
})

const svgRef = ref<SVGSVGElement>()
const cx = 480
const cy = 250
const nodePositions = [
  { x: 164, y: 106 },
  { x: 796, y: 106 },
  { x: 164, y: 394 },
  { x: 796, y: 394 }
]
const hoveredClient = ref(-1)
const flowProgress = ref<number[]>([])
let animationFrame = 0

const clientPositions = computed<PositionedClient[]>(() => props.clients.map((client, index) => ({
  ...client,
  ...nodePositions[index % nodePositions.length]
})))

const activeClientCount = computed(() => props.clients.filter((client) => client.active).length)

function connectionPath(client: PositionedClient) {
  return `M ${cx} ${cy} L ${client.x} ${client.y}`
}

function interpolate(start: number, end: number, progress: number) {
  return start + (end - start) * progress
}

function formatAccuracy(accuracy?: number) {
  return accuracy == null ? '--' : `${accuracy.toFixed(1)}%`
}

function formatDataSize(dataSize?: number) {
  return dataSize == null ? '--' : dataSize.toLocaleString()
}

function animate() {
  flowProgress.value = flowProgress.value.map((progress, index) => {
    const next = progress + 0.0045 + index * 0.00055
    return next >= 1 ? 0 : next
  })
  animationFrame = requestAnimationFrame(animate)
}

onMounted(() => {
  flowProgress.value = props.clients.map((_, index) => (index + 1) / (props.clients.length + 1))
  animate()
})

onUnmounted(() => {
  if (animationFrame) cancelAnimationFrame(animationFrame)
})
</script>

<style scoped>
.topology-graph {
  position: relative;
  width: 100%;
  min-width: 0;
  color: var(--text-primary);
}

.topology-svg {
  display: block;
  width: 100%;
  height: auto;
  min-height: 360px;
  overflow: visible;
}

.topology-guides {
  fill: none;
  stroke: var(--border-light);
  stroke-width: 1;
  stroke-dasharray: 3 10;
  opacity: 0.62;
}

.topology-guides circle {
  stroke-dasharray: 3 8;
}

.connection-base {
  fill: none;
  stroke: var(--border-color);
  stroke-width: 2;
  stroke-linecap: round;
}

.connection-active {
  fill: none;
  stroke: var(--primary-color);
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-dasharray: 7 16;
  opacity: 0.7;
  animation: parameterFlow 2.6s linear infinite;
}

.data-packet-out {
  fill: var(--primary-color);
}

.data-packet-in {
  fill: var(--info);
}

.aggregation-halo {
  fill: var(--primary-fade);
  opacity: 0.54;
  animation: aggregationBreathe 3.6s ease-in-out infinite;
}

.aggregation-surface {
  fill: var(--bg-card);
  stroke: var(--primary-color);
  stroke-width: 1.5;
}

.aggregation-symbol circle {
  fill: var(--primary-color);
}

.aggregation-symbol path {
  fill: none;
  stroke: var(--primary-color);
  stroke-width: 1.6;
  stroke-linecap: round;
}

.aggregation-kicker {
  fill: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
}

.aggregation-title {
  fill: var(--text-primary);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0;
}

.aggregation-version,
.aggregation-status {
  fill: var(--text-secondary);
  font-size: 11px;
}

.aggregation-rule {
  stroke: var(--border-light);
  stroke-width: 1;
}

.participant-node {
  cursor: default;
}

.participant-surface {
  fill: var(--bg-panel);
  stroke: var(--border-color);
  stroke-width: 1;
  transition: fill 180ms ease, stroke 180ms ease, transform 180ms ease;
}

.participant-node.is-active .participant-surface {
  stroke: var(--border-light);
}

.participant-node.is-hovered .participant-surface {
  fill: var(--bg-card);
  stroke: var(--primary-color);
  stroke-width: 1.5;
}

.participant-accent {
  fill: var(--border-color);
}

.participant-node.is-active .participant-accent {
  fill: var(--primary-color);
}

.participant-avatar {
  fill: var(--primary-fade);
  stroke: var(--primary-color);
  stroke-width: 1;
}

.participant-mark {
  fill: none;
  stroke: var(--primary-color);
  stroke-width: 1.3;
  stroke-linecap: round;
}

.participant-state {
  fill: var(--text-muted);
  stroke: var(--bg-panel);
  stroke-width: 2;
}

.participant-node.is-active .participant-state {
  fill: var(--success);
}

.participant-label {
  fill: var(--text-primary);
  font-size: 15px;
  font-weight: 650;
}

.participant-meta {
  fill: var(--text-secondary);
  font-size: 11px;
}

.participant-detail {
  fill: var(--text-muted);
  font-size: 10px;
}

.participant-tooltip rect {
  fill: var(--bg-card);
  stroke: var(--border-light);
  stroke-width: 1;
}

.participant-tooltip text {
  fill: var(--text-secondary);
  font-size: 10px;
}

.topology-legend {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px 18px;
  padding: 0 12px 8px;
  color: var(--text-muted);
  font-size: 12px;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  white-space: nowrap;
}

.legend-center,
.legend-online,
.legend-offline {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-center {
  background: var(--primary-color);
  box-shadow: 0 0 0 4px var(--primary-fade);
}

.legend-online {
  background: var(--success);
}

.legend-offline {
  background: var(--text-muted);
}

.legend-flow {
  width: 18px;
  height: 2px;
  background: var(--primary-color);
  border-radius: 1px;
  box-shadow: 7px 0 0 -0.2px var(--info);
}

@keyframes parameterFlow {
  to { stroke-dashoffset: -46; }
}

@keyframes aggregationBreathe {
  0%, 100% { opacity: 0.42; }
  50% { opacity: 0.72; }
}

@media (max-width: 760px) {
  .topology-svg {
    min-width: 620px;
  }

  .topology-graph {
    overflow-x: auto;
  }

  .topology-legend {
    justify-content: flex-start;
    min-width: 620px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .connection-active,
  .aggregation-halo {
    animation: none;
  }
}
</style>
