<template>
  <div class="training-curve">
    <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="curve-svg">
      <defs>
        <linearGradient id="accGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.2" />
          <stop offset="100%" stop-color="#22d3ee" stop-opacity="0.01" />
        </linearGradient>
        <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#f472b6" stop-opacity="0.12" />
          <stop offset="100%" stop-color="#f472b6" stop-opacity="0.01" />
        </linearGradient>
        <filter id="curveGlow">
          <feGaussianBlur stdDeviation="1.5" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="dotShadow">
          <feDropShadow dx="0" dy="1" stdDeviation="1.5" flood-color="#22d3ee" flood-opacity="0.3" />
        </filter>
      </defs>

      <g class="grid-lines">
        <line v-for="i in 5" :key="`h-${i}`"
          :x1="padLeft" :y1="padTop + (plotH * (i - 1)) / 4"
          :x2="padLeft + plotW" :y2="padTop + (plotH * (i - 1)) / 4"
          stroke="#f1f5f9" stroke-width="0.8"
        />
        <line v-for="i in 6" :key="`v-${i}`"
          :x1="padLeft + (plotW * (i - 1)) / 5" :y1="padTop"
          :x2="padLeft + (plotW * (i - 1)) / 5" :y2="padTop + plotH"
          stroke="#f1f5f9" stroke-width="0.8"
        />
      </g>

      <g class="axis-lines">
        <line :x1="padLeft" :y1="padTop" :x2="padLeft" :y2="padTop + plotH" stroke="#e2e8f0" stroke-width="1" />
        <line :x1="padLeft" :y1="padTop + plotH" :x2="padLeft + plotW" :y2="padTop + plotH" stroke="#e2e8f0" stroke-width="1" />
      </g>

      <g class="y-axis-labels">
        <text v-for="(label, i) in yLabels" :key="`yl-${i}`"
          :x="padLeft - 8" :y="padTop + (plotH * i) / 4 + 3"
          text-anchor="end" fill="#94a3b8" font-size="8"
        >{{ label }}</text>
      </g>

      <g class="x-axis-labels">
        <text v-for="(label, i) in xLabels" :key="`xl-${i}`"
          :x="padLeft + (plotW * i) / (xLabels.length - 1)" :y="padTop + plotH + 14"
          text-anchor="middle" fill="#94a3b8" font-size="8"
        >{{ label }}</text>
      </g>

      <path
        v-if="accAreaPath"
        :d="accAreaPath"
        fill="url(#accGrad)"
      />
      <path
        v-if="accLinePath"
        :d="accLinePath"
        fill="none"
        stroke="#22d3ee"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        filter="url(#curveGlow)"
        class="curve-line"
      />

      <path
        v-if="lossAreaPath"
        :d="lossAreaPath"
        fill="url(#lossGrad)"
      />
      <path
        v-if="lossLinePath"
        :d="lossLinePath"
        fill="none"
        stroke="#f472b6"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-dasharray="5 3"
        class="curve-line"
      />

      <g class="data-points">
        <circle
          v-for="(pt, i) in accPoints"
          :key="`ap-${i}`"
          :cx="pt.x" :cy="pt.y"
          r="3" fill="white" stroke="#22d3ee" stroke-width="1.5"
          filter="url(#dotShadow)"
          class="data-dot"
        />
      </g>

      <g v-if="latestAcc" class="latest-marker">
        <line :x1="latestAcc.x" :y1="padTop" :x2="latestAcc.x" :y2="latestAcc.y - 8" stroke="#22d3ee" stroke-width="0.5" stroke-dasharray="2 2" opacity="0.4" />
        <rect :x="latestAcc.x - 22" :y="latestAcc.y - 20" width="44" height="16" rx="4" fill="white" stroke="#22d3ee" stroke-width="0.8" />
        <text :x="latestAcc.x" :y="latestAcc.y - 9" text-anchor="middle" fill="#0891b2" font-size="8" font-weight="600">{{ accuracyData[accuracyData.length - 1] }}%</text>
      </g>

      <text :x="padLeft + 4" :y="padTop + 12" fill="#94a3b8" font-size="7">准确率 / 损失值</text>
    </svg>

    <div class="curve-legend">
      <div class="legend-item">
        <span class="legend-line acc"></span>
        <span>准确率</span>
      </div>
      <div class="legend-item">
        <span class="legend-line loss"></span>
        <span>损失值</span>
      </div>
      <div class="legend-item legend-round">
        <span class="round-indicator">R{{ rounds.length }}</span>
        <span>轮次</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  accuracyData?: number[]
  lossData?: number[]
  rounds?: number[]
}>(), {
  accuracyData: () => [62.1, 68.4, 73.7, 77.9, 81.2, 83.5, 85.1, 86.3, 87.0, 87.3],
  lossData: () => [1.24, 1.05, 0.89, 0.76, 0.64, 0.55, 0.48, 0.42, 0.38, 0.35],
  rounds: () => [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
})

const chartWidth = 400
const chartHeight = 220
const padLeft = 36
const padRight = 16
const padTop = 16
const padBottom = 24
const plotW = chartWidth - padLeft - padRight
const plotH = chartHeight - padTop - padBottom

const yLabels = computed(() => ['100', '75', '50', '25', '0'])
const xLabels = computed(() => {
  const data = props.rounds
  const step = Math.max(1, Math.floor(data.length / 5))
  return data.filter((_, i) => i % step === 0 || i === data.length - 1).map(String)
})

function toX(idx: number) {
  return padLeft + (plotW * idx) / (props.accuracyData.length - 1)
}

function toYAcc(val: number) {
  return padTop + plotH - (plotH * val) / 100
}

function toYLoss(val: number) {
  return padTop + plotH - (plotH * val) / 1.0
}

const accPoints = computed(() =>
  props.accuracyData.map((v, i) => ({ x: toX(i), y: toYAcc(v) }))
)

const lossPoints = computed(() =>
  props.lossData.map((v, i) => ({ x: toX(i), y: toYLoss(v) }))
)

function buildSmoothLinePath(points: { x: number; y: number }[]) {
  if (points.length < 2) return ''
  let d = `M ${points[0].x} ${points[0].y}`
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1]
    const curr = points[i]
    const cpx1 = prev.x + (curr.x - prev.x) * 0.4
    const cpx2 = prev.x + (curr.x - prev.x) * 0.6
    d += ` C ${cpx1} ${prev.y}, ${cpx2} ${curr.y}, ${curr.x} ${curr.y}`
  }
  return d
}

function buildAreaPath(points: { x: number; y: number }[]) {
  if (points.length < 2) return ''
  const linePath = buildSmoothLinePath(points)
  return `${linePath} L ${points[points.length - 1].x} ${padTop + plotH} L ${points[0].x} ${padTop + plotH} Z`
}

const accLinePath = computed(() => buildSmoothLinePath(accPoints.value))
const accAreaPath = computed(() => buildAreaPath(accPoints.value))
const lossLinePath = computed(() => buildSmoothLinePath(lossPoints.value))
const lossAreaPath = computed(() => buildAreaPath(lossPoints.value))

const latestAcc = computed(() => {
  if (!accPoints.value.length) return null
  return accPoints.value[accPoints.value.length - 1]
})
</script>

<style scoped>
.training-curve {
  --primary: #6366f1;
  --primary-bg: rgba(99, 102, 241, 0.06);
  --cyan: #22d3ee;
  --pink: #f472b6;
  --text-muted: #94a3b8;
  --radius-sm: 8px;
  --transition-base: 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);

  position: relative;
  width: 100%;
}

.curve-svg {
  width: 100%;
  height: auto;
  display: block;
}

.curve-line {
  animation: drawLine 1.5s ease-out forwards;
}

@keyframes drawLine {
  from { stroke-dashoffset: 800; stroke-dasharray: 800; }
  to { stroke-dashoffset: 0; stroke-dasharray: 800; }
}

.data-dot {
  transition: all var(--transition-base);
}

.data-dot:hover {
  r: 5;
}

.curve-legend {
  display: flex;
  justify-content: center;
  gap: 16px;
  margin-top: 8px;
  font-size: 10px;
  color: var(--text-muted);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 5px;
}

.legend-line {
  width: 16px;
  height: 2px;
  border-radius: 1px;
}

.legend-line.acc {
  background: var(--cyan);
  box-shadow: 0 0 4px rgba(34, 211, 238, 0.4);
}

.legend-line.loss {
  background: repeating-linear-gradient(90deg, var(--pink) 0, var(--pink) 5px, transparent 5px, transparent 8px);
}

.round-indicator {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 1px 5px;
  background: #f1f5f9;
  border-radius: 4px;
  font-size: 9px;
  font-weight: 600;
  color: var(--primary);
}
</style>
