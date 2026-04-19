<template>
  <section class="card grading-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">✅</span>
        <h4>作业批改结果</h4>
      </div>
      <span class="score-pill" :class="scoreLevelClass">评分 {{ scoreText }}</span>
    </header>

    <div class="score-bar-wrap">
      <div class="score-bar-track">
        <div class="score-bar-fill" :style="{ width: `${scoreValue}%` }"></div>
      </div>
      <div class="score-markers">
        <span class="marker low-mark">0</span>
        <span class="marker mid-mark">50</span>
        <span class="marker high-mark">100</span>
      </div>
    </div>

    <div class="block">
      <div class="title">评语</div>
      <p class="text feedback-text">{{ data?.feedback || '暂无评语。' }}</p>
    </div>

    <div class="block">
      <div class="title correction-title">修改建议</div>
      <ul v-if="corrections.length" class="list correction-list">
        <li v-for="(item, idx) in corrections" :key="idx">{{ item }}</li>
      </ul>
      <div v-else class="empty">暂无建议</div>
    </div>

    <div class="block">
      <div class="title reference-title">参考范文/答案</div>
      <p class="text reference-text">{{ data?.model_answer || '暂无参考内容。' }}</p>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface GradingData {
  score?: number
  feedback?: string
  corrections?: string[]
  model_answer?: string
}

const props = defineProps<{ data?: GradingData }>()

const scoreValue = computed(() => {
  const value = Number(props.data?.score ?? 0)
  return Math.max(0, Math.min(100, Math.round(value)))
})

const scoreText = computed(() => `${scoreValue.value}/100`)
const corrections = computed(() => props.data?.corrections || [])

const scoreLevelClass = computed(() => {
  if (scoreValue.value >= 80) return 'high'
  if (scoreValue.value >= 60) return 'medium'
  return 'low'
})
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: #fff;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
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

.score-pill {
  font-size: 12px;
  border-radius: 999px;
  padding: 3px 10px;
  font-weight: 600;
}

.score-pill.high {
  color: #166534;
  background: #dcfce7;
  border: 1px solid #86efac;
}

.score-pill.medium {
  color: #92400e;
  background: #fef3c7;
  border: 1px solid #fcd34d;
}

.score-pill.low {
  color: #b91c1c;
  background: #fee2e2;
  border: 1px solid #fca5a5;
}

.score-bar-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.score-bar-track {
  height: 8px;
  border-radius: 999px;
  background: #f1f5f9;
  overflow: hidden;
}

.score-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #059669, #0d9488);
  transition: width 0.6s ease;
}

.score-markers {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: #9ca3af;
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
}

.feedback-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 10px;
  background: #f0fdf4;
  border-radius: 8px;
  border-left: 3px solid #059669;
}

.correction-title::before {
  content: '🔧 ';
}

.correction-list {
  margin: 0;
  padding-left: 16px;
  font-size: 12px;
  line-height: 1.6;
}

.correction-list li {
  color: #b45309;
  margin-bottom: 2px;
}

.reference-title::before {
  content: '📖 ';
}

.reference-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  padding: 8px 10px;
  background: #eff6ff;
  border-radius: 8px;
  border-left: 3px solid #3b82f6;
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
