<template>
  <section class="card style-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">🎨</span>
        <h4>风格分析</h4>
      </div>
      <span class="style-pill" v-if="dominantStyle">{{ dominantStyle }}</span>
    </header>

    <div v-if="!dimensions?.length && !overallScore" class="empty">
      <div class="empty-illustration">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
          <circle cx="20" cy="20" r="14" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4 3"/>
          <path d="M14 18l3 3 5-6" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <span>暂无风格分析</span>
    </div>

    <template v-else>
      <div v-if="overallScore != null" class="score-row">
        <div class="score-circle">
          <span class="score-value">{{ overallScore }}</span>
          <span class="score-unit">分</span>
        </div>
        <div class="score-desc">
          <span class="score-label">综合风格评分</span>
          <span class="score-hint">{{ scoreHint }}</span>
        </div>
      </div>

      <div v-if="dimensions?.length" class="dimensions-list">
        <div
          v-for="(dim, idx) in dimensions"
          :key="idx"
          class="dim-item"
        >
          <div class="dim-head">
            <span class="dim-name">{{ dim.name || dim.dimension }}</span>
            <span class="dim-score">{{ dim.score ?? dim.value ?? '--' }}</span>
          </div>
          <div class="dim-bar-track">
            <div class="dim-bar-fill" :style="{ width: `${dimScorePercent(dim)}%` }"></div>
          </div>
          <p v-if="dim.comment || dim.description" class="dim-desc">{{ dim.comment || dim.description }}</p>
        </div>
      </div>

      <div v-if="suggestions?.length" class="suggestions-block">
        <div class="sug-label">✍️ 改进建议</div>
        <ul class="sug-list">
          <li v-for="(sug, idx) in suggestions" :key="idx">{{ sug }}</li>
        </ul>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface StyleDimension {
  name?: string
  dimension?: string
  score?: number
  value?: number
  comment?: string
  description?: string
}

const props = defineProps<{
  data?: {
    overall_score?: number
    overallScore?: number
    dominant_style?: string
    dominantStyle?: string
    dimensions?: StyleDimension[]
    suggestions?: string[]
  }
}>()

const overallScore = computed(() => props.data?.overall_score ?? props.data?.overallScore)
const dominantStyle = computed(() => props.data?.dominant_style || props.data?.dominantStyle)
const dimensions = computed(() => props.data?.dimensions)
const suggestions = computed(() => props.data?.suggestions)

const scoreHint = computed(() => {
  const s = overallScore.value
  if (s == null) return ''
  if (s >= 90) return '文笔出色，风格鲜明'
  if (s >= 70) return '行文流畅，有提升空间'
  if (s >= 50) return '基本达意，需加强锤炼'
  return '需要较多改进'
})

const dimScorePercent = (dim: StyleDimension) => {
  const v = dim.score ?? dim.value
  if (v == null) return 0
  return Math.min(100, Math.max(0, v))
}
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
}

.head-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.head-icon {
  font-size: 14px;
}

.card-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.style-pill {
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  background: #fef3c7;
  color: #92400e;
  font-weight: 600;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 24px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-illustration {
  opacity: 0.7;
  margin-bottom: 4px;
}

.score-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
  border-bottom: 1px solid #fde68a;
}

.score-circle {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: linear-gradient(135deg, #d97706, #f59e0b);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(217, 119, 6, 0.25);
}

.score-value {
  font-size: 18px;
  font-weight: 800;
  color: #fff;
  line-height: 1;
}

.score-unit {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.85);
}

.score-desc {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.score-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.score-hint {
  font-size: 11px;
  color: #92400e;
}

.dimensions-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 12px;
}

.dim-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dim-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.dim-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.dim-score {
  font-size: 12px;
  font-weight: 700;
  color: #d97706;
}

.dim-bar-track {
  height: 6px;
  background: #fef3c7;
  border-radius: 999px;
  overflow: hidden;
}

.dim-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #d97706, #f59e0b);
  transition: width 0.5s ease;
}

.dim-desc {
  margin: 0;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.suggestions-block {
  padding: 10px 12px;
  border-top: 1px solid var(--border-light);
  background: #fffdf5;
}

.sug-label {
  font-size: 11px;
  font-weight: 700;
  color: #d97706;
  margin-bottom: 6px;
}

.sug-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary);
}

.sug-list li {
  margin-bottom: 2px;
}
</style>
