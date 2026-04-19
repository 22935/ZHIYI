<template>
  <section class="card test-card">
    <header class="card-head">
      <div class="head-left">
        <span class="head-icon">🧪</span>
        <h4>单元测试生成</h4>
      </div>
      <span class="coverage-pill" :class="coverageClass">覆盖率 {{ coverageLabel }}</span>
    </header>

    <div v-if="!testCases?.length && !summary" class="empty">
      <div class="empty-illustration">
        <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
          <rect x="8" y="6" width="24" height="28" rx="3" stroke="#d1d5db" stroke-width="1.5"/>
          <path d="M14 14h12M14 18h12M14 22h8" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round"/>
          <circle cx="30" cy="30" r="6" fill="#dcfce7" stroke="#16a34a" stroke-width="1.5"/>
          <path d="M27 30l2 2 4-4" stroke="#16a34a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
      <span>暂无测试用例</span>
    </div>

    <template v-else>
      <div v-if="summary" class="summary-block">
        <p>{{ summary }}</p>
      </div>

      <div v-if="testCases?.length" class="test-list">
        <div
          v-for="(tc, idx) in testCases"
          :key="idx"
          class="test-item"
          :class="testStatusClass(tc.status)"
        >
          <div class="test-head">
            <span class="test-status-icon">{{ testStatusIcon(tc.status) }}</span>
            <span class="test-name">{{ tc.name || tc.test_name || `测试用例 ${idx + 1}` }}</span>
          </div>
          <p v-if="tc.description" class="test-desc">{{ tc.description }}</p>
          <div v-if="tc.code || tc.test_code" class="test-code">
            <pre><code>{{ tc.code || tc.test_code }}</code></pre>
          </div>
          <div v-if="tc.assertions" class="test-assertions">
            <span class="assert-label">断言</span>
            <span class="assert-count">{{ tc.assertions }} 项</span>
          </div>
        </div>
      </div>

      <div v-if="coverage != null" class="coverage-bar-wrap">
        <div class="coverage-bar-track">
          <div class="coverage-bar-fill" :style="{ width: `${coverage}%` }"></div>
        </div>
        <div class="coverage-markers">
          <span class="marker">0%</span>
          <span class="marker">50%</span>
          <span class="marker">100%</span>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface TestCase {
  name?: string
  test_name?: string
  description?: string
  code?: string
  test_code?: string
  status?: string
  assertions?: number
}

const props = defineProps<{
  data?: {
    summary?: string
    test_cases?: TestCase[]
    testCases?: TestCase[]
    coverage?: number
  }
}>()

const summary = computed(() => props.data?.summary)
const testCases = computed(() => props.data?.test_cases || props.data?.testCases)
const coverage = computed(() => props.data?.coverage)

const coverageLabel = computed(() => {
  if (coverage.value == null) return '--'
  return `${Math.round(coverage.value)}%`
})

const coverageClass = computed(() => {
  if (coverage.value == null) return ''
  if (coverage.value >= 80) return 'high'
  if (coverage.value >= 50) return 'medium'
  return 'low'
})

const testStatusClass = (status?: string) => {
  const s = (status || '').toLowerCase()
  if (s === 'pass' || s === 'passed' || s === 'success') return 'passed'
  if (s === 'fail' || s === 'failed' || s === 'error') return 'failed'
  return 'pending'
}

const testStatusIcon = (status?: string) => {
  const s = (status || '').toLowerCase()
  if (s === 'pass' || s === 'passed' || s === 'success') return '✅'
  if (s === 'fail' || s === 'failed' || s === 'error') return '❌'
  return '⏳'
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

.coverage-pill {
  font-size: 11px;
  border-radius: 999px;
  padding: 2px 10px;
  font-weight: 600;
}

.coverage-pill.high {
  background: #dcfce7;
  color: #166534;
}

.coverage-pill.medium {
  background: #fef3c7;
  color: #92400e;
}

.coverage-pill.low {
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
  background: linear-gradient(135deg, #f5f3ff, #ede9fe);
  border-bottom: 1px solid #e9e5f5;
}

.summary-block p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
}

.test-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
}

.test-item {
  border-radius: 10px;
  padding: 10px 12px;
  border: 1px solid;
  transition: transform 0.15s ease;
}

.test-item:hover {
  transform: translateX(2px);
}

.test-item.passed {
  background: linear-gradient(135deg, #f0fdf4, #dcfce7);
  border-color: #86efac;
}

.test-item.failed {
  background: linear-gradient(135deg, #fef2f2, #fee2e2);
  border-color: #fca5a5;
}

.test-item.pending {
  background: linear-gradient(135deg, #f5f3ff, #ede9fe);
  border-color: #c4b5fd;
}

.test-head {
  display: flex;
  align-items: center;
  gap: 6px;
}

.test-status-icon {
  font-size: 13px;
}

.test-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.test-desc {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.test-code {
  margin-top: 6px;
  background: #1e1e2e;
  border-radius: 8px;
  padding: 8px 10px;
  overflow-x: auto;
}

.test-code pre {
  margin: 0;
}

.test-code code {
  font-family: 'Fira Code', 'Consolas', monospace;
  font-size: 11px;
  line-height: 1.5;
  color: #cdd6f4;
}

.test-assertions {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
  font-size: 11px;
}

.assert-label {
  font-weight: 600;
  color: #7c3aed;
}

.assert-count {
  color: var(--text-secondary);
}

.coverage-bar-wrap {
  padding: 10px 12px;
  border-top: 1px solid var(--border-light);
  background: #faf9ff;
}

.coverage-bar-track {
  height: 8px;
  background: #e9e5f5;
  border-radius: 999px;
  overflow: hidden;
}

.coverage-bar-fill {
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #7c3aed, #a78bfa);
  transition: width 0.6s ease;
}

.coverage-markers {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
}

.marker {
  font-size: 10px;
  color: var(--text-secondary);
}
</style>
