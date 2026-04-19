<template>
  <section class="card plot-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">📖</span>
        <h4>情节逻辑检查</h4>
      </div>
      <span class="logic-pill" :class="logicClass">逻辑 {{ logicLabel }}</span>
    </header>

    <div v-if="!issues?.length && !summary" class="empty">
      <div class="empty-illustration">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
          <circle cx="20" cy="20" r="14" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4 3"/>
          <path d="M14 20h12M20 14v12" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
      <span>暂无情节逻辑检查</span>
    </div>

    <template v-else>
      <div v-if="summary" class="summary-block">
        <p>{{ summary }}</p>
      </div>

      <div v-if="timeline?.length" class="timeline-section">
        <div class="section-label">📍 情节时间线</div>
        <div class="timeline-list">
          <div
            v-for="(event, idx) in timeline"
            :key="idx"
            class="timeline-item"
          >
            <div class="tl-marker">
              <span class="tl-dot"></span>
              <span v-if="idx < timeline.length - 1" class="tl-line"></span>
            </div>
            <div class="tl-body">
              <span class="tl-label" v-if="event.chapter || event.time">{{ event.chapter || event.time }}</span>
              <span class="tl-text">{{ event.event || event.description }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="issues?.length" class="issues-section">
        <div class="section-label">⚠️ 逻辑问题</div>
        <div class="issues-list">
          <div
            v-for="(issue, idx) in issues"
            :key="idx"
            class="issue-item"
            :class="issueTypeClass(issue.type)"
          >
            <div class="issue-head">
              <span class="issue-type-badge" :class="issueTypeClass(issue.type)">
                {{ issueTypeLabel(issue.type) }}
              </span>
              <span class="issue-location" v-if="issue.chapter || issue.location">
                {{ issue.chapter || issue.location }}
              </span>
            </div>
            <p class="issue-desc">{{ issue.description || issue.message }}</p>
            <div v-if="issue.suggestion" class="issue-fix">
              💡 {{ issue.suggestion }}
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface PlotIssue {
  type?: string
  description?: string
  message?: string
  chapter?: string
  location?: string
  suggestion?: string
}

interface PlotEvent {
  chapter?: string
  time?: string
  event?: string
  description?: string
}

const props = defineProps<{
  data?: {
    summary?: string
    logic_score?: number
    logicScore?: number
    timeline?: PlotEvent[]
    issues?: PlotIssue[]
  }
}>()

const summary = computed(() => props.data?.summary)
const timeline = computed(() => props.data?.timeline)
const issues = computed(() => props.data?.issues)

const logicLabel = computed(() => {
  const s = props.data?.logic_score ?? props.data?.logicScore
  if (s == null) return '--'
  if (s >= 90) return '严密'
  if (s >= 70) return '基本合理'
  if (s >= 50) return '有漏洞'
  return '需重构'
})

const logicClass = computed(() => {
  const s = props.data?.logic_score ?? props.data?.logicScore
  if (s == null) return ''
  if (s >= 90) return 'excellent'
  if (s >= 70) return 'good'
  if (s >= 50) return 'fair'
  return 'poor'
})

const issueTypeClass = (type?: string) => {
  const t = (type || '').toLowerCase()
  if (t === 'contradiction' || t === 'plothole') return 'critical'
  if (t === 'inconsistency' || t === 'timing') return 'warning'
  return 'info'
}

const issueTypeLabel = (type?: string) => {
  const t = (type || '').toLowerCase()
  if (t === 'contradiction') return '矛盾'
  if (t === 'plothole') return '漏洞'
  if (t === 'inconsistency') return '不一致'
  if (t === 'timing') return '时间线'
  return '建议'
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

.logic-pill {
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  font-weight: 600;
}

.logic-pill.excellent {
  background: #dcfce7;
  color: #166534;
}

.logic-pill.good {
  background: #dbeafe;
  color: #1e40af;
}

.logic-pill.fair {
  background: #fef3c7;
  color: #92400e;
}

.logic-pill.poor {
  background: #fee2e2;
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
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
  border-bottom: 1px solid #fde68a;
}

.summary-block p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
}

.section-label {
  font-size: 11px;
  font-weight: 700;
  color: #d97706;
  margin-bottom: 6px;
}

.timeline-section {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.timeline-item {
  display: grid;
  grid-template-columns: 24px 1fr;
  gap: 8px;
}

.tl-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.tl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d97706;
  flex-shrink: 0;
}

.tl-line {
  width: 2px;
  flex: 1;
  background: #fde68a;
  min-height: 8px;
}

.tl-body {
  padding-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tl-label {
  font-size: 10px;
  font-weight: 600;
  color: #92400e;
}

.tl-text {
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.4;
}

.issues-section {
  padding: 10px 12px;
}

.issues-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.issue-item {
  border-radius: 10px;
  padding: 8px 10px;
  border: 1px solid;
  transition: transform 0.15s ease;
}

.issue-item:hover {
  transform: translateX(2px);
}

.issue-item.critical {
  background: linear-gradient(135deg, #fef2f2, #fee2e2);
  border-color: #fca5a5;
}

.issue-item.warning {
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
  border-color: #fcd34d;
}

.issue-item.info {
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
  border-color: #fde68a;
}

.issue-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.issue-type-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 8px;
  border-radius: 999px;
}

.issue-type-badge.critical {
  background: #fee2e2;
  color: #991b1b;
}

.issue-type-badge.warning {
  background: #fef3c7;
  color: #92400e;
}

.issue-type-badge.info {
  background: #fef3c7;
  color: #92400e;
}

.issue-location {
  font-size: 11px;
  color: #6b7280;
}

.issue-desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-primary);
}

.issue-fix {
  margin-top: 4px;
  font-size: 11px;
  color: #92400e;
  padding: 4px 8px;
  background: #fffbeb;
  border-radius: 6px;
  border-left: 3px solid #d97706;
}
</style>
