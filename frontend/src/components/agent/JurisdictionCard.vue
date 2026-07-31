<!-- 管辖建议卡片 — 展示法院管辖建议，含推荐法院标签、依据说明和法律基础引用 -->
<template>
  <section class="card">
    <header class="card-head">
      <h4>管辖法院确定</h4>
      <span class="count">法院建议 {{ normalizedCourts.length }}</span>
    </header>

    <div v-if="normalizedCourts.length" class="court-list">
      <div
        v-for="(item, index) in normalizedCourts"
        :key="`${item.name}-${index}`"
        class="court-item"
        :class="{ recommended: isRecommended(item, index) }"
      >
        <div class="name-row">
          <strong>{{ item.name }}</strong>
          <el-tag v-if="isRecommended(item, index)" size="small" type="success">推荐</el-tag>
        </div>
        <div class="basis">{{ item.basis }}</div>
      </div>
    </div>
    <div v-else class="empty">暂无可展示法院选项</div>

    <div v-if="recommendationText" class="recommendation">
      <span class="label">推荐意见</span>
      <span>{{ recommendationText }}</span>
    </div>

    <div class="sub-section">
      <div class="sub-title">法律依据</div>
      <ul v-if="legalBasisList.length" class="list">
        <li v-for="item in legalBasisList" :key="item">{{ item }}</li>
      </ul>
      <div v-else class="empty">暂无依据</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface CourtOption {
  name: string
  basis: string
  priority?: string
}

interface JurisdictionResult {
  courts?: Array<{ name: string; basis: string }>
  recommended_courts?: Array<{ court: string; reason: string; priority?: string }>
  recommendation?: string
  legal_basis?: string[] | string
}

const props = defineProps<{
  data?: JurisdictionResult
}>()

const normalizedCourts = computed<CourtOption[]>(() => {
  if (Array.isArray(props.data?.courts) && props.data?.courts.length) {
    return props.data.courts.map(item => ({
      name: item.name,
      basis: item.basis,
      priority: undefined
    }))
  }
  if (Array.isArray(props.data?.recommended_courts)) {
    return props.data.recommended_courts.map(item => ({
      name: item.court,
      basis: item.reason,
      priority: item.priority
    }))
  }
  return []
})

const recommendationText = computed(() => props.data?.recommendation || '')
const legalBasisList = computed(() => {
  const basis = props.data?.legal_basis
  if (Array.isArray(basis)) return basis
  if (typeof basis === 'string' && basis.trim()) return [basis]
  return []
})

const isRecommended = (item: CourtOption, index: number) => item.priority === 'high' || index === 0
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
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

.count {
  font-size: 12px;
  color: #6d28d9;
  background: var(--accent-fade);
  border: 1px solid #ddd6fe;
  border-radius: 999px;
  padding: 2px 8px;
}

.court-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.court-item {
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 8px;
  background: var(--bg-input);
}

.court-item.recommended {
  border-color: #86efac;
  background: var(--success-fade);
}

.name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.name-row strong {
  color: var(--text-primary);
  font-size: 13px;
}

.basis {
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
}

.recommendation {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  font-size: 12px;
  color: var(--text-primary);
}

.label {
  color: var(--text-secondary);
  font-weight: 700;
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
