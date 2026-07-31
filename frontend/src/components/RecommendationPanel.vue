<!-- 推荐面板组件 — 展示 AI 生成的推荐项列表，含置信度百分比、刷新和可选择功能 -->
<template>
  <section class="recommendation-panel">
    <div class="recommendation-head">
      <div>
        <h4>{{ title }}</h4>
        <p v-if="subtitle">{{ subtitle }}</p>
      </div>
      <button
        v-if="refreshable"
        type="button"
        class="refresh-button"
        :disabled="loading"
        @click="$emit('refresh')"
      >
        {{ loading ? '刷新中...' : '刷新' }}
      </button>
    </div>

    <div v-if="loading" class="recommendation-state">正在生成推荐...</div>
    <div v-else-if="!items.length" class="recommendation-state">暂无推荐内容</div>
    <div v-else class="recommendation-list">
      <button
        v-for="(item, index) in items"
        :key="`${item.text}-${index}`"
        type="button"
        class="recommendation-item"
        @click="$emit('select', item)"
      >
        <div class="recommendation-main">
          <strong>{{ item.text }}</strong>
          <span class="confidence">{{ Math.round((item.confidence || 0) * 100) }}%</span>
        </div>
        <p>{{ item.reason }}</p>
      </button>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { RecommendationItem } from '@/services/api/recommendation'

defineProps<{
  title?: string
  subtitle?: string
  items: RecommendationItem[]
  loading?: boolean
  refreshable?: boolean
}>()

defineEmits<{
  select: [item: RecommendationItem]
  refresh: []
}>()
</script>

<style scoped>
.recommendation-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.recommendation-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.recommendation-head h4 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.recommendation-head p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.refresh-button {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--surface-solid);
  color: var(--text-secondary);
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
}

.refresh-button:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.recommendation-state {
  padding: 14px 12px;
  border-radius: 10px;
  background: var(--bg-input);
  border: 1px dashed var(--border-light);
  color: var(--text-secondary);
  font-size: 12px;
}

.recommendation-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recommendation-item {
  border: 1px solid var(--border-light);
  background: var(--surface-solid);
  border-radius: 12px;
  padding: 12px;
  text-align: left;
  cursor: pointer;
  transition: all 0.2s ease;
}

.recommendation-item:hover {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}

.recommendation-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.recommendation-main strong {
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.5;
}

.confidence {
  flex-shrink: 0;
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 600;
}

.recommendation-item p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.45;
}
</style>
