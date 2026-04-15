<template>
  <section class="card">
    <header class="card-head">
      <h4>诉讼时效计算</h4>
      <span class="status" :class="{ expired: isExpired }">{{ statusText }}</span>
    </header>

    <div class="grid">
      <div class="item"><span class="label">起算日期</span>{{ startDate || '--' }}</div>
      <div class="item"><span class="label">截止日期</span>{{ deadline || '--' }}</div>
      <div class="item"><span class="label">时效期间</span>{{ limitationPeriodText }}</div>
      <div class="item"><span class="label">剩余天数</span>{{ remainingText }}</div>
    </div>

    <el-progress
      :percentage="progressPercent"
      :status="isExpired ? 'exception' : undefined"
      :stroke-width="10"
      :show-text="false"
    />

    <div class="sub-section">
      <div class="sub-title">中断/中止事件</div>
      <ul v-if="interruptionEvents.length" class="list">
        <li v-for="item in interruptionEvents" :key="item">{{ item }}</li>
      </ul>
      <div v-else class="empty">暂无事件记录</div>
    </div>

    <div class="sub-section">
      <div class="sub-title">法律依据</div>
      <ul v-if="legalBasisList.length" class="list">
        <li v-for="item in legalBasisList" :key="item">{{ item }}</li>
      </ul>
      <div v-else class="empty">暂无法律依据</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface LimitationCalcResult {
  limitation_period?: string
  limitation_years?: number
  start_date?: string
  deadline?: string
  expiry_date?: string
  is_expired?: boolean
  days_remaining?: number
  interruption_events?: string[]
  interruption_hints?: string[]
  legal_basis?: string[] | string
  status?: string
}

const props = defineProps<{
  data?: LimitationCalcResult
}>()

const startDate = computed(() => props.data?.start_date || '')
const deadline = computed(() => props.data?.deadline || props.data?.expiry_date || '')
const isExpired = computed(() => !!props.data?.is_expired || ((props.data?.days_remaining ?? 1) < 0))
const statusText = computed(() => props.data?.status || (isExpired.value ? '可能已过时效' : '时效尚可'))

const limitationPeriodText = computed(() => {
  if (props.data?.limitation_period) return props.data.limitation_period
  if (typeof props.data?.limitation_years === 'number' && props.data.limitation_years > 0) {
    return `${props.data.limitation_years} 年`
  }
  return '--'
})

const remainingText = computed(() => {
  const days = props.data?.days_remaining
  if (typeof days !== 'number') return '--'
  return days >= 0 ? `${days} 天` : `已超期 ${Math.abs(days)} 天`
})

const progressPercent = computed(() => {
  const days = props.data?.days_remaining
  if (typeof days !== 'number') return 0
  if (days <= 0) return 0
  if (days >= 365) return 100
  return Math.max(1, Math.min(100, Math.round((days / 365) * 100)))
})

const interruptionEvents = computed(() => {
  const events = props.data?.interruption_events || props.data?.interruption_hints || []
  return Array.isArray(events) ? events : []
})

const legalBasisList = computed(() => {
  const basis = props.data?.legal_basis
  if (Array.isArray(basis)) return basis
  if (typeof basis === 'string' && basis.trim()) return [basis]
  return []
})
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: #fff;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-head h4 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.status {
  font-size: 12px;
  color: #166534;
  background: #dcfce7;
  border: 1px solid #86efac;
  border-radius: 999px;
  padding: 2px 8px;
}

.status.expired {
  color: #b91c1c;
  background: #fee2e2;
  border-color: #fecaca;
}

.grid {
  display: grid;
  gap: 8px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.item {
  font-size: 12px;
  color: var(--text-primary);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 7px 8px;
  background: #f8fafc;
}

.label {
  display: inline-block;
  margin-right: 6px;
  color: var(--text-secondary);
  font-weight: 600;
}

.sub-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sub-title {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 700;
}

.list {
  margin: 0;
  padding-left: 18px;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.5;
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
