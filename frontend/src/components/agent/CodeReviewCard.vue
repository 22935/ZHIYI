<!-- 代码审查卡片 — 展示代码审查结果，含严重度分类问题、文件/位置信息和修改建议 -->
<template>
  <section class="card review-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Search /></el-icon>
        <h4>代码审查</h4>
      </div>
      <span class="quality-pill" :class="qualityClass">质量 {{ qualityLabel }}</span>
    </header>

    <div v-if="!issues?.length && !summary" class="empty">
      <div class="empty-illustration">
        <el-icon><Document /></el-icon>
      </div>
      <span>暂无代码审查结果</span>
    </div>

    <template v-else>
      <div v-if="summary" class="summary-block">
        <p>{{ summary }}</p>
      </div>

      <div v-if="issues?.length" class="issues-list">
        <div
          v-for="(issue, idx) in issues"
          :key="idx"
          class="issue-item"
          :class="issueSeverityClass(issue.severity)"
        >
          <div class="issue-head">
            <span class="severity-badge" :class="issueSeverityClass(issue.severity)">
              {{ issueSeverityLabel(issue.severity) }}
            </span>
            <span class="issue-location" v-if="issue.file || issue.line">
              {{ issue.file }}{{ issue.line ? `:${issue.line}` : '' }}
            </span>
          </div>
          <p class="issue-msg">{{ issue.message || issue.description }}</p>
          <div v-if="issue.suggestion" class="issue-suggestion">
            <span class="suggestion-label">
              <el-icon><MagicStick /></el-icon>
              建议
            </span>
            <span>{{ issue.suggestion }}</span>
          </div>
        </div>
      </div>

      <div v-if="metrics" class="metrics-row">
        <div class="metric-item">
          <span class="metric-value">{{ metrics.complexity ?? '--' }}</span>
          <span class="metric-label">复杂度</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">{{ metrics.coverage ?? '--' }}</span>
          <span class="metric-label">覆盖率</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">{{ metrics.duplicates ?? '--' }}</span>
          <span class="metric-label">重复率</span>
        </div>
        <div class="metric-item">
          <span class="metric-value">{{ metrics.debt ?? '--' }}</span>
          <span class="metric-label">技术债</span>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document, MagicStick, Search } from '@element-plus/icons-vue'

interface CodeIssue {
  severity?: string
  message?: string
  description?: string
  file?: string
  line?: number
  suggestion?: string
}

interface CodeMetrics {
  complexity?: number | string
  coverage?: number | string
  duplicates?: number | string
  debt?: number | string
}

const props = defineProps<{
  data?: {
    summary?: string
    issues?: CodeIssue[]
    quality_score?: number
    metrics?: CodeMetrics
  }
}>()

const summary = computed(() => props.data?.summary)
const issues = computed(() => props.data?.issues)
const metrics = computed(() => props.data?.metrics)

const qualityLabel = computed(() => {
  const score = props.data?.quality_score
  if (score == null) return '--'
  if (score >= 90) return '优秀'
  if (score >= 70) return '良好'
  if (score >= 50) return '一般'
  return '需改进'
})

const qualityClass = computed(() => {
  const score = props.data?.quality_score
  if (score == null) return ''
  if (score >= 90) return 'excellent'
  if (score >= 70) return 'good'
  if (score >= 50) return 'fair'
  return 'poor'
})

const issueSeverityClass = (severity?: string) => {
  const s = (severity || '').toLowerCase()
  if (s === 'critical' || s === 'error') return 'critical'
  if (s === 'warning' || s === 'major') return 'warning'
  return 'info'
}

const issueSeverityLabel = (severity?: string) => {
  const s = (severity || '').toLowerCase()
  if (s === 'critical' || s === 'error') return '严重'
  if (s === 'warning' || s === 'major') return '警告'
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

.quality-pill {
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  font-weight: 600;
}

.quality-pill.excellent {
  background: var(--success-fade);
  color: #166534;
}

.quality-pill.good {
  background: var(--primary-fade);
  color: #1e40af;
}

.quality-pill.fair {
  background: var(--warning-fade);
  color: #92400e;
}

.quality-pill.poor {
  background: var(--danger-fade);
  color: #991b1b;
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

.summary-block {
  padding: 10px 12px;
  background: linear-gradient(135deg, var(--accent-fade), var(--accent-fade));
  border-bottom: 1px solid #e9e5f5;
}

.summary-block p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
}

.issue-item {
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid;
  transition: transform 0.15s ease;
}

.issue-item:hover {
  transform: translateX(2px);
}

.issue-item.critical {
  background: linear-gradient(135deg, var(--danger-fade), var(--danger-fade));
  border-color: #fca5a5;
}

.issue-item.warning {
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-color: #fcd34d;
}

.issue-item.info {
  background: linear-gradient(135deg, var(--accent-fade), var(--accent-fade));
  border-color: #c4b5fd;
}

.issue-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.severity-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
}

.severity-badge.critical {
  background: var(--danger-fade);
  color: #991b1b;
}

.severity-badge.warning {
  background: var(--warning-fade);
  color: #92400e;
}

.severity-badge.info {
  background: var(--accent-fade);
  color: #5b21b6;
}

.issue-location {
  font-size: 11px;
  color: var(--text-secondary);
  font-family: 'Fira Code', 'Consolas', monospace;
}

.issue-msg {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
}

.issue-suggestion {
  margin-top: 6px;
  font-size: 11px;
  color: #6d28d9;
  padding: 4px 8px;
  background: var(--accent-fade);
  border-radius: 6px;
  border-left: 3px solid #7c3aed;
}

.suggestion-label {
  font-weight: 600;
  margin-right: 4px;
}

.metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border-light);
  background: var(--accent-fade);
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}

.metric-value {
  font-size: 16px;
  font-weight: 700;
  color: #7c3aed;
}

.metric-label {
  font-size: 10px;
  color: var(--text-secondary);
}
</style>
