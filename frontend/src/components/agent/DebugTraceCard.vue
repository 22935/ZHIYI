<template>
  <section class="card debug-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">🐛</span>
        <h4>调试追踪</h4>
      </div>
      <span class="status-pill" :class="statusClass">{{ statusLabel }}</span>
    </header>

    <div v-if="!steps?.length && !rootCause" class="empty">
      <div class="empty-illustration">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
          <circle cx="20" cy="20" r="14" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4 3"/>
          <path d="M16 16l8 8M24 16l-8 8" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round"/>
        </svg>
      </div>
      <span>暂无调试追踪信息</span>
    </div>

    <template v-else>
      <div v-if="rootCause" class="root-cause-block">
        <div class="cause-label">🎯 根因定位</div>
        <p class="cause-text">{{ rootCause }}</p>
      </div>

      <div v-if="steps?.length" class="steps-list">
        <div
          v-for="(step, idx) in steps"
          :key="idx"
          class="step-item"
          :class="stepStatusClass(step.status)"
        >
          <div class="step-marker">
            <span class="step-num">{{ idx + 1 }}</span>
            <span v-if="idx < steps.length - 1" class="step-line"></span>
          </div>
          <div class="step-body">
            <div class="step-head">
              <span class="step-action">{{ step.action || step.description }}</span>
              <span class="step-status" :class="stepStatusClass(step.status)">{{ stepStatusLabel(step.status) }}</span>
            </div>
            <div v-if="step.file || step.line" class="step-location">
              📄 {{ step.file }}{{ step.line ? `:${step.line}` : '' }}
            </div>
            <div v-if="step.detail || step.output" class="step-detail">
              {{ step.detail || step.output }}
            </div>
          </div>
        </div>
      </div>

      <div v-if="fixSuggestion" class="fix-block">
        <div class="fix-label">🔧 修复建议</div>
        <p class="fix-text">{{ fixSuggestion }}</p>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface DebugStep {
  action?: string
  description?: string
  file?: string
  line?: number
  status?: string
  detail?: string
  output?: string
}

const props = defineProps<{
  data?: {
    root_cause?: string
    rootCause?: string
    steps?: DebugStep[]
    fix_suggestion?: string
    fixSuggestion?: string
    status?: string
  }
}>()

const rootCause = computed(() => props.data?.root_cause || props.data?.rootCause)
const steps = computed(() => props.data?.steps)
const fixSuggestion = computed(() => props.data?.fix_suggestion || props.data?.fixSuggestion)

const statusLabel = computed(() => {
  const s = (props.data?.status || '').toLowerCase()
  if (s === 'resolved' || s === 'fixed') return '已解决'
  if (s === 'in_progress' || s === 'debugging') return '调试中'
  if (s === 'unresolved') return '未解决'
  return '待分析'
})

const statusClass = computed(() => {
  const s = (props.data?.status || '').toLowerCase()
  if (s === 'resolved' || s === 'fixed') return 'resolved'
  if (s === 'in_progress' || s === 'debugging') return 'progress'
  return 'pending'
})

const stepStatusClass = (status?: string) => {
  const s = (status || '').toLowerCase()
  if (s === 'success' || s === 'pass') return 'success'
  if (s === 'fail' || s === 'error') return 'fail'
  return 'running'
}

const stepStatusLabel = (status?: string) => {
  const s = (status || '').toLowerCase()
  if (s === 'success' || s === 'pass') return '通过'
  if (s === 'fail' || s === 'error') return '失败'
  return '执行中'
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
  background: linear-gradient(135deg, #f5f3ff, #ede9fe);
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

.status-pill {
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  font-weight: 600;
}

.status-pill.resolved {
  background: #dcfce7;
  color: #166534;
}

.status-pill.progress {
  background: #dbeafe;
  color: #1e40af;
}

.status-pill.pending {
  background: #f3f4f6;
  color: #374151;
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

.root-cause-block {
  padding: 10px 12px;
  background: linear-gradient(135deg, #fef2f2, #fee2e2);
  border-bottom: 1px solid #fecaca;
}

.cause-label {
  font-size: 11px;
  font-weight: 700;
  color: #991b1b;
  margin-bottom: 4px;
}

.cause-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #7f1d1d;
}

.steps-list {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.step-item {
  display: grid;
  grid-template-columns: 32px 1fr;
  gap: 8px;
  min-height: 48px;
}

.step-marker {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

.step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #7c3aed;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-line {
  width: 2px;
  flex: 1;
  background: #e9e5f5;
  min-height: 8px;
}

.step-body {
  padding-bottom: 10px;
}

.step-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.step-action {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.step-status {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 999px;
}

.step-status.success {
  background: #dcfce7;
  color: #166534;
}

.step-status.fail {
  background: #fee2e2;
  color: #991b1b;
}

.step-status.running {
  background: #ede9fe;
  color: #5b21b6;
}

.step-location {
  font-size: 11px;
  color: #6b7280;
  font-family: 'Fira Code', 'Consolas', monospace;
  margin-top: 2px;
}

.step-detail {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
  padding: 4px 8px;
  background: #f9fafb;
  border-radius: 6px;
  line-height: 1.4;
}

.fix-block {
  padding: 10px 12px;
  background: linear-gradient(135deg, #f0fdf4, #dcfce7);
  border-top: 1px solid #bbf7d0;
}

.fix-label {
  font-size: 11px;
  font-weight: 700;
  color: #166534;
  margin-bottom: 4px;
}

.fix-text {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  color: #14532d;
}
</style>
