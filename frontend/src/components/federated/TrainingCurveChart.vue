<template>
  <div class="training-curve">
    <svg :viewBox="`0 0 ${chartWidth} ${chartHeight}`" class="curve-svg">
      <defs>
        <linearGradient id="accGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.3" />
          <stop offset="100%" stop-color="#22d3ee" stop-opacity="0.02" />
        </linearGradient>
        <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#f472b6" stop-opacity="0.2" />
          <stop offset="100%" stop-color="#f472b6" stop-opacity="0.02" />
        </linearGradient>
        <filter id="curveGlow">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      <g class="grid-lines">
        <line v-for="i in 5" :key="`h-${i}`"
          :x1="padLeft" :y1="padTop + (plotH * (i - 1)) / 4"
          :x2="padLeft + plotW" :y2="padTop + (plotH * (i - 1)) / 4"
          stroke="#334155" stroke-width="0.5" stroke-dasharray="2 4"
        />
        <line v-for="i in 6" :key="`v-${i}`"
          :x1="padLeft + (plotW * (i - 1)) / 5" :y1="padTop"
          :x2="padLeft + (plotW * (i - 1)) / 5" :y2="padTop + plotH"
          stroke="#334155" stroke-width="0.5" stroke-dasharray="2 4"
        />
      </g>

      <g class="y-axis-labels">
        <text v-for="(label, i) in yLabels" :key="`yl-${i}`"
          :x="padLeft - 8" :y="padTop + (plotH * i) / 4 + 3"
          text-anchor="end" fill="#64748b" font-size="8"
        >{{ label }}</text>
      </g>

      <g class="x-axis-labels">
        <text v-for="(label, i) in xLabels" :key="`xl-${i}`"
          :x="padLeft + (plotW * i) / (xLabels.length - 1)" :y="padTop + plotH + 14"
          text-anchor="middle" fill="#64748b" font-size="8"
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
        stroke-dasharray="6 3"
        class="curve-line"
      />

      <g class="data-points">
        <circle
          v-for="(pt, i) in accPoints"
          :key="`ap-${i}`"
          :cx="pt.x" :cy="pt.y"
          r="3" fill="#0f172a" stroke="#22d3ee" stroke-width="1.5"
          class="data-dot"
        />
      </g>

      <g v-if="latestAcc" class="latest-marker">
        <line :x1="latestAcc.x" :y1="padTop" :x2="latestAcc.x" :y2="latestAcc.y - 6" stroke="#22d3ee" stroke-width="0.5" stroke-dasharray="3 2" />
        <rect :x="latestAcc.x - 20" :y="latestAcc.y - 18" width="40" height="14" rx="3" fill="#22d3ee" fill-opacity="0.15" stroke="#22d3ee" stroke-width="0.5" />
        <text :x="latestAcc.x" :y="latestAcc.y - 9" text-anchor="middle" fill="#22d3ee" font-size="8" font-weight="600">{{ accuracyData[accuracyData.length - 1] }}%</text>
      </g>
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
  accuracyData: () => [72.3, 78.5, 83.1, 86.4, 88.9, 90.2, 91.5, 92.1, 92.8, 93.2],
  lossData: () => [0.68, 0.55, 0.44, 0.36, 0.29, 0.24, 0.20, 0.17, 0.15, 0.13],
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

function buildLinePath(points: { x: number; y: number }[]) {
  if (points.length < 2) return ''
  return points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ')
}

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
  position: relative;
  width: 100%;
}

.curve-svg {
  width: 100%;
  height: auto;
  display: block;
}

.curve-line {
  animation: drawLine 2s ease-out forwards;
}

@keyframes drawLine {
  from { stroke-dashoffset: 1000; stroke-dasharray: 1000; }
  to { stroke-dashoffset: 0; stroke-dasharray: 1000; }
}

.data-dot {
  transition: all 0.2s ease;
}

.data-dot:hover {
  r: 5;
}

.curve-legend {
  display: flex;
  justify-content: center;
  gap: 20px;
  margin-top: 8px;
  font-size: 11px;
  color: #94a3b8;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

.legend-line {
  width: 20px;
  height: 2px;
  border-radius: 1px;
}

.legend-line.acc {
  background: #22d3ee;
  box-shadow: 0 0 4px #22d3ee;
}

.legend-line.loss {
  background: #f472b6;
  background: repeating-linear-gradient(90deg, #f472b6 0, #f472b6 6px, transparent 6px, transparent 9px);
}
</style>
