<!-- 学习诊断雷达图 — SVG 雷达图展示学生多维度学习诊断指标，含进度条和掌握程度总结 -->
<template>
  <section class="card diagnosis-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Search /></el-icon>
        <h4>学情诊断</h4>
      </div>
      <span class="level" :class="masteryLevelClass">掌握度 {{ masteryLevelText }}</span>
    </header>

    <div class="radar-wrap">
      <div class="radar-container">
        <svg viewBox="0 0 220 220" class="radar-svg" aria-label="diagnosis-radar">
          <defs>
            <linearGradient id="radarFill" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stop-color="rgba(5, 150, 105, 0.25)" />
              <stop offset="100%" stop-color="rgba(13, 148, 136, 0.15)" />
            </linearGradient>
          </defs>
          <polygon v-for="(ring, idx) in rings" :key="idx" :points="ring" class="radar-ring" />
          <line v-for="axis in axes" :key="axis" x1="110" y1="110" :x2="axisPoint(axis).x" :y2="axisPoint(axis).y" class="radar-axis" />
          <polygon :points="polygonPoints" class="radar-area" />
          <circle v-for="(item, idx) in scoreItems" :key="idx" :cx="axisPoint(idx, item.value).x" :cy="axisPoint(idx, item.value).y" r="4" class="radar-dot" />
        </svg>
      </div>
      <div class="metrics">
        <div class="metric" v-for="item in scoreItems" :key="item.key">
          <div class="metric-header">
            <span class="label">{{ item.label }}</span>
            <span class="metric-value">{{ Math.round(item.value) }}</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" :style="{ width: `${item.value}%` }"></div>
          </div>
        </div>
      </div>
    </div>

    <p class="summary">{{ data?.diagnosis_summary || '暂无学情诊断说明。' }}</p>

    <div class="blocks-row">
      <div class="block">
        <div class="title weakness-title">薄弱点</div>
        <ul v-if="weakPoints.length" class="list weakness-list">
          <li v-for="item in weakPoints" :key="item">{{ item }}</li>
        </ul>
        <div v-else class="empty">暂无</div>
      </div>
      <div class="block">
        <div class="title strength-title">优势项</div>
        <ul v-if="strengths.length" class="list strength-list">
          <li v-for="item in strengths" :key="item">{{ item }}</li>
        </ul>
        <div v-else class="empty">暂无</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Search } from '@element-plus/icons-vue'

interface DiagnosisData {
  weak_points?: string[]
  strengths?: string[]
  mastery_level?: string
  mastery_score?: number
  volatility?: number
  trend?: string
  learning_style?: string
  diagnosis_summary?: string
}

const props = defineProps<{ data?: DiagnosisData }>()

const data = computed(() => props.data || {})
const weakPoints = computed(() => data.value.weak_points || [])
const strengths = computed(() => data.value.strengths || [])

const masteryLevelText = computed(() => {
  const level = String(data.value.mastery_level || '').toLowerCase()
  if (level === 'high') return '高'
  if (level === 'medium') return '中'
  if (level === 'low') return '低'
  return '未知'
})

const masteryLevelClass = computed(() => {
  const level = String(data.value.mastery_level || '').toLowerCase()
  if (level === 'high') return 'high'
  if (level === 'medium') return 'medium'
  if (level === 'low') return 'low'
  return ''
})

const trendScore = computed(() => {
  const trend = String(data.value.trend || '').toLowerCase()
  if (trend === 'up') return 85
  if (trend === 'flat') return 65
  if (trend === 'down') return 40
  return 55
})

const styleScore = computed(() => {
  const style = String(data.value.learning_style || '')
  if (!style) return 60
  return style.includes('稳') ? 75 : 62
})

const stabilityScore = computed(() => {
  const volatility = Number(data.value.volatility ?? 10)
  return Math.max(0, Math.min(100, 100 - volatility * 5))
})

const scoreItems = computed(() => {
  return [
    { key: 'mastery', label: '掌握水平', value: Number(data.value.mastery_score ?? 65) },
    { key: 'trend', label: '进步趋势', value: trendScore.value },
    { key: 'stability', label: '学习稳定性', value: stabilityScore.value },
    { key: 'style', label: '学习状态', value: styleScore.value }
  ]
})

const axes = [0, 1, 2, 3]

const axisPoint = (axis: number, scale = 100) => {
  const angle = (-90 + axis * 90) * (Math.PI / 180)
  const radius = (scale / 100) * 80
  return {
    x: 110 + Math.cos(angle) * radius,
    y: 110 + Math.sin(angle) * radius
  }
}

const rings = computed(() => {
  return [25, 50, 75, 100].map(scale =>
    axes.map(axis => {
      const p = axisPoint(axis, scale)
      return `${p.x},${p.y}`
    }).join(' ')
  )
})

const polygonPoints = computed(() => {
  return scoreItems.value.map((item, idx) => {
    const p = axisPoint(idx, item.value)
    return `${p.x},${p.y}`
  }).join(' ')
})
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.head-icon {
  font-size: 16px;
}

.card-head h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}

.level {
  font-size: 12px;
  border-radius: 999px;
  padding: 3px 10px;
  background: var(--bg-input);
  color: var(--text-regular);
  font-weight: 600;
}

.level.high {
  background: var(--success-fade);
  color: #166534;
}

.level.medium {
  background: var(--warning-fade);
  color: #92400e;
}

.level.low {
  background: var(--danger-fade);
  color: #b91c1c;
}

.radar-wrap {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 14px;
  align-items: center;
}

.radar-container {
  position: relative;
}

.radar-svg {
  width: 200px;
  height: 200px;
}

.radar-ring {
  fill: none;
  stroke: #d1fae5;
  stroke-width: 1;
}

.radar-axis {
  stroke: #e5e7eb;
  stroke-width: 1;
}

.radar-area {
  fill: url(#radarFill);
  stroke: #059669;
  stroke-width: 2;
}

.radar-dot {
  fill: #059669;
  stroke: #fff;
  stroke-width: 2;
}

.metrics {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.metric .label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}

.metric-value {
  font-size: 13px;
  font-weight: 700;
  color: #059669;
}

.progress-track {
  height: 6px;
  border-radius: 999px;
  background: var(--success-fade);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--success), var(--success));
  transition: width 0.6s ease;
}

.summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  padding: 8px 10px;
  background: var(--success-fade);
  border-radius: 8px;
  border-left: 3px solid #059669;
}

.blocks-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 4px;
}

.weakness-title::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}

.strength-title::before {
  content: '';
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: currentColor;
}

.list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.6;
}

.weakness-list li {
  color: #b45309;
}

.strength-list li {
  color: #047857;
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 900px) {
  .radar-wrap {
    grid-template-columns: 1fr;
  }
  .radar-svg {
    margin: 0 auto;
  }
  .blocks-row {
    grid-template-columns: 1fr;
  }
}
</style>
