<template>
  <div class="topology-graph">
    <svg
      ref="svgRef"
      :viewBox="`0 0 ${width} ${height}`"
      :width="width"
      :height="height"
      class="topology-svg"
    >
      <defs>
        <radialGradient id="centerGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.6" />
          <stop offset="60%" stop-color="#6366f1" stop-opacity="0.15" />
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="clientGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.5" />
          <stop offset="100%" stop-color="#22d3ee" stop-opacity="0" />
        </radialGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="3" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="strongGlow">
          <feGaussianBlur stdDeviation="6" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.8" />
          <stop offset="50%" stop-color="#22d3ee" stop-opacity="0.4" />
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0.1" />
        </linearGradient>
        <linearGradient id="lineGradReverse" x1="100%" y1="0%" x2="0%" y2="0%">
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.8" />
          <stop offset="50%" stop-color="#22d3ee" stop-opacity="0.4" />
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0.1" />
        </linearGradient>
        <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
          <polygon points="0 0, 8 3, 0 6" fill="#6366f1" opacity="0.6" />
        </marker>
      </defs>

      <g class="background-rings">
        <circle :cx="cx" :cy="cy" :r="orbitRadius * 0.5" fill="none" stroke="#6366f1" stroke-opacity="0.06" stroke-width="1" stroke-dasharray="4 6" />
        <circle :cx="cx" :cy="cy" :r="orbitRadius * 0.75" fill="none" stroke="#6366f1" stroke-opacity="0.04" stroke-width="1" stroke-dasharray="4 6" />
        <circle :cx="cx" :cy="cy" :r="orbitRadius" fill="none" stroke="#6366f1" stroke-opacity="0.03" stroke-width="1" stroke-dasharray="4 6" />
      </g>

      <g class="connections">
        <g v-for="(client, idx) in clientPositions" :key="`conn-${idx}`">
          <line
            :x1="cx"
            :y1="cy"
            :x2="client.x"
            :y2="client.y"
            stroke="url(#lineGrad)"
            stroke-width="1.5"
            stroke-opacity="0.3"
          />
          <line
            v-if="client.active"
            :x1="cx"
            :y1="cy"
            :x2="client.x"
            :y2="client.y"
            stroke="url(#lineGrad)"
            stroke-width="2"
            stroke-opacity="0.6"
            class="data-flow-line"
            :style="{ animationDelay: `${idx * 0.4}s` }"
          />
          <circle
            v-if="client.active"
            :cx="interpolateX(cx, client.x, flowProgress[idx] || 0)"
            :cy="interpolateY(cy, client.y, flowProgress[idx] || 0)"
            r="3"
            fill="#22d3ee"
            filter="url(#glow)"
            class="flow-particle"
            :style="{ animationDelay: `${idx * 0.3}s` }"
          />
          <circle
            v-if="client.active"
            :cx="interpolateX(client.x, cx, flowProgress[idx] || 0)"
            :cy="interpolateY(client.y, cy, flowProgress[idx] || 0)"
            r="2.5"
            fill="#a78bfa"
            filter="url(#glow)"
            class="flow-particle-reverse"
            :style="{ animationDelay: `${idx * 0.5 + 0.2}s` }"
          />
        </g>
      </g>

      <g class="center-node" :transform="`translate(${cx}, ${cy})`">
        <circle r="55" fill="url(#centerGlow)" class="center-pulse-ring" />
        <circle r="40" fill="#1e1b4b" stroke="#6366f1" stroke-width="2" filter="url(#strongGlow)" />
        <circle r="36" fill="none" stroke="#818cf8" stroke-width="0.5" stroke-dasharray="3 3" class="center-rotate" />
        <text y="-8" text-anchor="middle" fill="white" font-size="11" font-weight="600">全局模型</text>
        <text y="8" text-anchor="middle" fill="#a78bfa" font-size="9">FedAvg</text>
        <text y="20" text-anchor="middle" fill="#818cf8" font-size="8">v{{ globalVersion }}</text>
        <g class="aggregation-arcs">
          <path d="M -28 -28 A 40 40 0 0 1 28 -28" fill="none" stroke="#22d3ee" stroke-width="2" stroke-linecap="round" :stroke-dasharray="aggregationDash" class="arc-anim-1" />
          <path d="M 28 28 A 40 40 0 0 1 -28 28" fill="none" stroke="#a78bfa" stroke-width="2" stroke-linecap="round" :stroke-dasharray="aggregationDash" class="arc-anim-2" />
        </g>
      </g>

      <g
        v-for="(client, idx) in clientPositions"
        :key="`client-${idx}`"
        :transform="`translate(${client.x}, ${client.y})`"
        class="client-node-group"
        @mouseenter="hoveredClient = idx"
        @mouseleave="hoveredClient = -1"
      >
        <circle r="30" :fill="client.active ? 'url(#clientGlow)' : 'transparent'" class="client-pulse" v-if="client.active" />
        <circle
          :r="24"
          :fill="client.active ? '#0f172a' : '#1e293b'"
          :stroke="client.active ? '#22d3ee' : '#475569'"
          :stroke-width="hoveredClient === idx ? 2.5 : 1.5"
          :filter="client.active ? 'url(#glow)' : ''"
          class="client-circle"
        />
        <circle r="21" fill="none" :stroke="client.active ? '#22d3ee' : '#475569'" stroke-width="0.5" stroke-dasharray="2 2" class="client-rotate" v-if="client.active" />
        <text y="-4" text-anchor="middle" :fill="client.active ? 'white' : '#94a3b8'" font-size="9" font-weight="500">{{ client.label }}</text>
        <text y="8" text-anchor="middle" :fill="client.active ? '#22d3ee' : '#64748b'" font-size="7">{{ client.active ? '活跃' : '离线' }}</text>
        <circle cx="16" cy="-16" r="4" :fill="client.active ? '#10b981' : '#64748b'" class="status-blink" v-if="client.active" />
      </g>
    </svg>

    <div class="topology-legend">
      <div class="legend-item">
        <span class="legend-dot center"></span>
        <span>全局聚合节点</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot active"></span>
        <span>活跃客户端</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot inactive"></span>
        <span>离线客户端</span>
      </div>
      <div class="legend-item">
        <span class="legend-line"></span>
        <span>参数传输</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'

interface ClientNode {
  id: string
  label: string
  active: boolean
  accuracy?: number
  dataSize?: number
}

const props = withDefaults(defineProps<{
  clients?: ClientNode[]
  globalVersion?: string
  aggregating?: boolean
}>(), {
  clients: () => [
    { id: 'c1', label: '律师节点', active: true, accuracy: 92.5, dataSize: 245 },
    { id: 'c2', label: '教师节点', active: true, accuracy: 88.7, dataSize: 187 },
    { id: 'c3', label: '程序员节点', active: true, accuracy: 91.3, dataSize: 312 },
    { id: 'c4', label: '作家节点', active: true, accuracy: 89.1, dataSize: 156 },
    { id: 'c5', label: '风控节点', active: false, accuracy: 85.2, dataSize: 0 },
    { id: 'c6', label: 'NLP节点', active: true, accuracy: 90.4, dataSize: 278 }
  ],
  globalVersion: '3.2',
  aggregating: false
})

const width = 520
const height = 400
const cx = width / 2
const cy = height / 2
const orbitRadius = 150

const hoveredClient = ref(-1)
const flowProgress = ref<number[]>([])
let animFrame = 0

const clientPositions = computed(() => {
  const count = props.clients.length
  return props.clients.map((client, idx) => {
    const angle = (2 * Math.PI * idx) / count - Math.PI / 2
    return {
      ...client,
      x: cx + orbitRadius * Math.cos(angle),
      y: cy + orbitRadius * Math.sin(angle)
    }
  })
})

const aggregationDash = computed(() => {
  return props.aggregating ? '20 10' : '50 0'
})

function interpolateX(x1: number, x2: number, t: number) {
  return x1 + (x2 - x1) * t
}

function interpolateY(y1: number, y2: number, t: number) {
  return y1 + (y2 - y1) * t
}

function animate() {
  const progresses = flowProgress.value.map((p, i) => {
    const speed = 0.008 + (i % 3) * 0.003
    const next = p + speed
    return next > 1 ? 0 : next
  })
  flowProgress.value = progresses
  animFrame = requestAnimationFrame(animate)
}

onMounted(() => {
  flowProgress.value = props.clients.map(() => Math.random())
  animate()
})

onUnmounted(() => {
  if (animFrame) cancelAnimationFrame(animFrame)
})
</script>

<style scoped>
.topology-graph {
  position: relative;
  width: 100%;
}

.topology-svg {
  width: 100%;
  height: auto;
  display: block;
}

.center-pulse-ring {
  animation: centerPulse 3s ease-in-out infinite;
}

@keyframes centerPulse {
  0%, 100% { r: 55; opacity: 0.6; }
  50% { r: 65; opacity: 0.2; }
}

.center-rotate {
  animation: rotateSlow 20s linear infinite;
  transform-origin: center;
}

@keyframes rotateSlow {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.client-rotate {
  animation: rotateSlow 15s linear infinite reverse;
  transform-origin: center;
}

.client-pulse {
  animation: clientPulse 2.5s ease-in-out infinite;
}

@keyframes clientPulse {
  0%, 100% { r: 30; opacity: 0.5; }
  50% { r: 38; opacity: 0.1; }
}

.data-flow-line {
  stroke-dasharray: 8 12;
  animation: flowLine 2s linear infinite;
}

@keyframes flowLine {
  from { stroke-dashoffset: 0; }
  to { stroke-dashoffset: -40; }
}

.flow-particle {
  animation: particleFade 1.5s ease-in-out infinite alternate;
}

.flow-particle-reverse {
  animation: particleFade 1.8s ease-in-out infinite alternate-reverse;
}

@keyframes particleFade {
  0% { opacity: 0.3; r: 2; }
  100% { opacity: 1; r: 4; }
}

.status-blink {
  animation: statusBlink 2s ease-in-out infinite;
}

@keyframes statusBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.arc-anim-1 {
  animation: arcDraw 3s ease-in-out infinite;
}

.arc-anim-2 {
  animation: arcDraw 3s ease-in-out infinite 1.5s;
}

@keyframes arcDraw {
  0% { stroke-dashoffset: 50; }
  50% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: -50; }
}

.client-circle {
  transition: all 0.3s ease;
}

.client-node-group {
  cursor: pointer;
}

.topology-legend {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 16px;
  font-size: 11px;
  color: #94a3b8;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-dot.center {
  background: #6366f1;
  box-shadow: 0 0 6px #6366f1;
}

.legend-dot.active {
  background: #22d3ee;
  box-shadow: 0 0 6px #22d3ee;
}

.legend-dot.inactive {
  background: #475569;
}

.legend-line {
  width: 16px;
  height: 2px;
  background: linear-gradient(90deg, #6366f1, #22d3ee);
  border-radius: 1px;
}
</style>
