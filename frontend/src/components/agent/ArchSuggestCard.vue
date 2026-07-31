<!-- 架构建议卡片 — 展示架构优化建议，含优先级标签、分类和实现细节 -->
<template>
  <section class="card arch-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Connection /></el-icon>
        <h4>架构建议</h4>
      </div>
      <span class="pattern-pill" v-if="pattern">{{ pattern }}</span>
    </header>

    <div v-if="!suggestions?.length && !overview" class="empty">
      <div class="empty-illustration">
        <el-icon><Operation /></el-icon>
      </div>
      <span>暂无架构建议</span>
    </div>

    <template v-else>
      <div v-if="overview" class="overview-block">
        <p>{{ overview }}</p>
      </div>

      <div v-if="suggestions?.length" class="suggestions-list">
        <div
          v-for="(item, idx) in suggestions"
          :key="idx"
          class="suggest-item"
          :class="priorityClass(item.priority)"
        >
          <div class="suggest-head">
            <span class="priority-badge" :class="priorityClass(item.priority)">
              {{ priorityLabel(item.priority) }}
            </span>
            <span class="suggest-category" v-if="item.category">{{ item.category }}</span>
          </div>
          <h5 class="suggest-title">{{ item.title || item.name }}</h5>
          <p class="suggest-desc">{{ item.description || item.reason }}</p>
          <div v-if="item.implementation" class="suggest-impl">
            <span class="impl-label">
              <el-icon><DocumentChecked /></el-icon>
              实施要点
            </span>
            <span>{{ item.implementation }}</span>
          </div>
        </div>
      </div>

      <div v-if="techStack?.length" class="tech-block">
        <div class="tech-label">推荐技术栈</div>
        <div class="tech-tags">
          <span v-for="tech in techStack" :key="tech" class="tech-tag">{{ tech }}</span>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Connection, DocumentChecked, Operation } from '@element-plus/icons-vue'

interface ArchSuggestion {
  title?: string
  name?: string
  description?: string
  reason?: string
  priority?: string
  category?: string
  implementation?: string
}

const props = defineProps<{
  data?: {
    overview?: string
    pattern?: string
    suggestions?: ArchSuggestion[]
    tech_stack?: string[]
    techStack?: string[]
  }
}>()

const overview = computed(() => props.data?.overview)
const pattern = computed(() => props.data?.pattern)
const suggestions = computed(() => props.data?.suggestions)
const techStack = computed(() => props.data?.tech_stack || props.data?.techStack)

const priorityClass = (priority?: string) => {
  const p = (priority || '').toLowerCase()
  if (p === 'high' || p === 'critical') return 'high'
  if (p === 'medium') return 'medium'
  return 'low'
}

const priorityLabel = (priority?: string) => {
  const p = (priority || '').toLowerCase()
  if (p === 'high' || p === 'critical') return '高优'
  if (p === 'medium') return '中优'
  return '建议'
}
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
  overflow: hidden;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(135deg, var(--accent-fade), var(--accent-fade));
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

.pattern-pill {
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  background: var(--accent-fade);
  color: #5b21b6;
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

.overview-block {
  padding: 10px 12px;
  background: linear-gradient(135deg, var(--accent-fade), var(--accent-fade));
  border-bottom: 1px solid #e9e5f5;
}

.overview-block p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
}

.suggestions-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
}

.suggest-item {
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid;
  transition: transform 0.15s ease;
}

.suggest-item:hover {
  transform: translateX(2px);
}

.suggest-item.high {
  background: linear-gradient(135deg, var(--danger-fade), var(--danger-fade));
  border-color: #fca5a5;
}

.suggest-item.medium {
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-color: #fcd34d;
}

.suggest-item.low {
  background: linear-gradient(135deg, var(--accent-fade), var(--accent-fade));
  border-color: #c4b5fd;
}

.suggest-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.priority-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
}

.priority-badge.high {
  background: var(--danger-fade);
  color: #991b1b;
}

.priority-badge.medium {
  background: var(--warning-fade);
  color: #92400e;
}

.priority-badge.low {
  background: var(--accent-fade);
  color: #5b21b6;
}

.suggest-category {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-secondary);
}

.suggest-title {
  margin: 0 0 4px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.suggest-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
}

.suggest-impl {
  margin-top: 6px;
  font-size: 11px;
  color: #6d28d9;
  padding: 4px 8px;
  background: var(--accent-fade);
  border-radius: 6px;
  border-left: 3px solid #7c3aed;
}

.impl-label {
  font-weight: 600;
  margin-right: 4px;
}

.tech-block {
  padding: 10px 12px;
  border-top: 1px solid var(--border-light);
  background: var(--accent-fade);
}

.tech-label {
  font-size: 11px;
  font-weight: 700;
  color: #7c3aed;
  margin-bottom: 6px;
}

.tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tech-tag {
  font-size: 11px;
  padding: 3px 10px;
  border-radius: 999px;
  background: var(--accent-fade);
  color: #5b21b6;
  border: 1px solid #c4b5fd;
  font-weight: 500;
}
</style>
