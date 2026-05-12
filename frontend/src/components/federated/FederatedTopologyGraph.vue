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
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.3" />
          <stop offset="60%" stop-color="#6366f1" stop-opacity="0.08" />
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
        </radialGradient>
        <radialGradient id="clientGlow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.25" />
          <stop offset="100%" stop-color="#22d3ee" stop-opacity="0" />
        </radialGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="coloredBlur" />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="softShadow">
          <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#6366f1" flood-opacity="0.15" />
        </filter>
        <linearGradient id="lineGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.5" />
          <stop offset="50%" stop-color="#22d3ee" stop-opacity="0.3" />
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0.1" />
        </linearGradient>
        <linearGradient id="lineGradReverse" x1="100%" y1="0%" x2="0%" y2="0%">
          <stop offset="0%" stop-color="#6366f1" stop-opacity="0.5" />
          <stop offset="50%" stop-color="#22d3ee" stop-opacity="0.3" />
          <stop offset="100%" stop-color="#6366f1" stop-opacity="0.1" />
        </linearGradient>
        <linearGradient id="centerFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#4f46e5" />
          <stop offset="100%" stop-color="#6366f1" />
        </linearGradient>
        <linearGradient id="clientFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#0e7490" />
          <stop offset="100%" stop-color="#0891b2" />
        </linearGradient>
        <linearGradient id="clientFillInactive" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#94a3b8" />
          <stop offset="100%" stop-color="#cbd5e1" />
        </linearGradient>
      </defs>

      <g class="background-rings">
        <circle :cx="cx" :cy="cy" :r="orbitRadius * 0.5" fill="none" stroke="#e2e8f0" stroke-width="0.5" stroke-dasharray="3 5" />
        <circle :cx="cx" :cy="cy" :r="orbitRadius * 0.75" fill="none" stroke="#e2e8f0" stroke-width="0.5" stroke-dasharray="3 5" />
        <circle :cx="cx" :cy="cy" :r="orbitRadius" fill="none" stroke="#e2e8f0" stroke-width="0.5" stroke-dasharray="3 5" />
      </g>

      <g class="connections">
        <g v-for="(client, idx) in clientPositions" :key="`conn-${idx}`">
          <line
            :x1="cx"
            :y1="cy"
            :x2="client.x"
            :y2="client.y"
            stroke="#e2e8f0"
            stroke-width="1"
          />
          <line
            v-if="client.active"
            :x1="cx"
            :y1="cy"
            :x2="client.x"
            :y2="client.y"
            stroke="url(#lineGrad)"
            stroke-width="1.5"
            stroke-opacity="0.5"
            class="data-flow-line"
            :style="{ animationDelay: `${idx * 0.4}s` }"
          />
          <circle
            v-if="client.active"
            :cx="interpolateX(cx, client.x, flowProgress[idx] || 0)"
            :cy="interpolateY(cy, client.y, flowProgress[idx] || 0)"
            r="2.5"
            fill="#22d3ee"
            filter="url(#glow)"
            class="flow-particle"
            :style="{ animationDelay: `${idx * 0.3}s` }"
          />
          <circle
            v-if="client.active"
            :cx="interpolateX(client.x, cx, flowProgress[idx] || 0)"
            :cy="interpolateY(client.y, cy, flowProgress[idx] || 0)"
            r="2"
            fill="#a78bfa"
            filter="url(#glow)"
            class="flow-particle-reverse"
            :style="{ animationDelay: `${idx * 0.5 + 0.2}s` }"
          />
        </g>
      </g>

      <g class="center-node" :transform="`translate(${cx}, ${cy})`">
        <circle r="50" fill="url(#centerGlow)" class="center-pulse-ring" />
        <circle r="36" fill="url(#centerFill)" filter="url(#softShadow)" />
        <circle r="33" fill="none" stroke="rgba(255,255,255,0.15)" stroke-width="0.5" stroke-dasharray="2 3" class="center-rotate" />
        <text y="-7" text-anchor="middle" fill="white" font-size="10" font-weight="600">全局模型</text>
        <text y="6" text-anchor="middle" fill="rgba(255,255,255,0.7)" font-size="8">FedAvg</text>
        <text y="17" text-anchor="middle" fill="rgba(255,255,255,0.5)" font-size="7">v{{ globalVersion }}</text>
        <g class="aggregation-arcs" v-if="aggregating">
          <path d="M -25 -25 A 36 36 0 0 1 25 -25" fill="none" stroke="#22d3ee" stroke-width="2" stroke-linecap="round" class="arc-anim-1" />
          <path d="M 25 25 A 36 36 0 0 1 -25 25" fill="none" stroke="#a78bfa" stroke-width="2" stroke-linecap="round" class="arc-anim-2" />
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
        <circle r="26" :fill="client.active ? 'url(#clientGlow)' : 'transparent'" class="client-pulse" v-if="client.active" />
        <circle
          :r="22"
          :fill="client.active ? 'url(#clientFill)' : 'url(#clientFillInactive)'"
          :stroke="client.active ? '#22d3ee' : '#cbd5e1'"
          :stroke-width="hoveredClient === idx ? 2 : 1"
          filter="url(#softShadow)"
          class="client-circle"
        />
        <circle r="19" fill="none" :stroke="client.active ? 'rgba(255,255,255,0.15)' : '#e2e8f0'" stroke-width="0.5" stroke-dasharray="2 2" class="client-rotate" v-if="client.active" />
        <text y="-3" text-anchor="middle" fill="white" font-size="8" font-weight="500">{{ client.label }}</text>
        <text y="8" text-anchor="middle" :fill="client.active ? 'rgba(255,255,255,0.7)' : '#94a3b8'" font-size="6.5">{{ client.active ? '活跃' : '离线' }}</text>
        <circle cx="14" cy="-14" r="3.5" :fill="client.active ? '#10b981' : '#94a3b8'" class="status-blink" v-if="client.active" />
        <circle cx="14" cy="-14" r="5" :fill="client.active ? 'rgba(16,185,129,0.2)' : 'transparent'" class="status-ring" v-if="client.active" />

        <g v-if="hoveredClient === idx" class="tooltip-group">
          <rect x="-48" y="-52" width="96" height="24" rx="6" fill="white" stroke="#e2e8f0" stroke-width="0.5" filter="url(#softShadow)" />
          <text x="0" y="-40" text-anchor="middle" fill="#1e293b" font-size="7" font-weight="500">
            精度: {{ client.accuracy?.toFixed(1) || '--' }}%
          </text>
          <text x="0" y="-32" text-anchor="middle" fill="#94a3b8" font-size="6">
            数据: {{ client.dataSize?.toLocaleString() || '--' }}条
          </text>
        </g>
      </g>
    </svg>

    <div class="topology-legend">
      <div class="legend-item">
        <span class="legend-dot center"></span>
        <span>全局聚合</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot active"></span>
        <span>活跃Agent</span>
      </div>
      <div class="legend-item">
        <span class="legend-dot inactive"></span>
        <span>离线Agent</span>
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
    { id: 'c1', label: '律师Agent', active: true, accuracy: 87.3, dataSize: 12450 },
    { id: 'c2', label: '教师Agent', active: true, accuracy: 84.6, dataSize: 8920 },
    { id: 'c3', label: '程序员Agent', active: true, accuracy: 86.1, dataSize: 15380 },
    { id: 'c4', label: '作家Agent', active: true, accuracy: 83.2, dataSize: 6740 }
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

function interpolateX(x1: number, x2: number, t: number) {
  return x1 + (x2 - x1) * t
}

function interpolateY(y1: number, y2: number, t: number) {
  return y1 + (y2 - y1) * t
}

function animate() {
  const progresses = flowProgress.value.map((p, i) => {
    const speed = 0.006 + (i % 3) * 0.002
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
  --primary: #6366f1;
  --primary-light: #818cf8;
  --primary-bg: rgba(99, 102, 241, 0.06);
  --cyan: #22d3ee;
  --cyan-dark: #0891b2;
  --purple: #a78bfa;
  --green: #34d399;
  --surface: #ffffff;
  --surface-alt: #f8fafc;
  --text-primary: #1e293b;
  --text-secondary: #475569;
  --text-muted: #94a3b8;
  --radius-sm: 8px;
  --transition-base: 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);

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
  0%, 100% { r: 50; opacity: 0.5; }
  50% { r: 60; opacity: 0.15; }
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
  0%, 100% { r: 26; opacity: 0.4; }
  50% { r: 34; opacity: 0.08; }
}

.data-flow-line {
  stroke-dasharray: 6 10;
  animation: flowLine 2s linear infinite;
}

@keyframes flowLine {
  from { stroke-dashoffset: 0; }
  to { stroke-dashoffset: -32; }
}

.flow-particle {
  animation: particleFade 1.5s ease-in-out infinite alternate;
}

.flow-particle-reverse {
  animation: particleFade 1.8s ease-in-out infinite alternate-reverse;
}

@keyframes particleFade {
  0% { opacity: 0.2; r: 1.5; }
  100% { opacity: 0.9; r: 3; }
}

.status-blink {
  animation: statusBlink 2s ease-in-out infinite;
}

.status-ring {
  animation: statusRing 2s ease-in-out infinite;
}

@keyframes statusBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

@keyframes statusRing {
  0%, 100% { opacity: 0.3; r: 5; }
  50% { opacity: 0; r: 8; }
}

.arc-anim-1 {
  animation: arcDraw 3s ease-in-out infinite;
}

.arc-anim-2 {
  animation: arcDraw 3s ease-in-out infinite 1.5s;
}

@keyframes arcDraw {
  0% { stroke-dashoffset: 40; }
  50% { stroke-dashoffset: 0; }
  100% { stroke-dashoffset: -40; }
}

.client-circle {
  transition: all var(--transition-base);
}

.client-node-group {
  cursor: pointer;
}

.tooltip-group {
  pointer-events: none;
}

.topology-legend {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 14px;
  font-size: 10px;
  color: var(--text-muted);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.legend-dot.center {
  background: var(--primary);
  box-shadow: 0 0 4px rgba(99, 102, 241, 0.4);
}

.legend-dot.active {
  background: var(--cyan-dark);
  box-shadow: 0 0 4px rgba(34, 211, 238, 0.4);
}

.legend-dot.inactive {
  background: #cbd5e1;
}

.legend-line {
  width: 14px;
  height: 2px;
  background: linear-gradient(90deg, var(--primary), var(--cyan));
  border-radius: 1px;
  opacity: 0.6;
}
</style>
