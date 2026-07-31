<!-- 证据分析卡片 — 展示法律证据项（名称、类型、强度、备注）、缺失证据清单和法律依据 -->
<template>
  <section class="card">
    <header class="card-head">
      <h4>证据分析</h4>
      <span class="count">证据项 {{ evidenceItems.length }}</span>
    </header>

    <p class="summary">{{ overallAssessment || '暂无证据分析结果。' }}</p>

    <div v-if="evidenceItems.length" class="evidence-list">
      <div v-for="(item, index) in evidenceItems" :key="`${item.name}-${index}`" class="evidence-item">
        <div class="line"><span class="label">名称</span>{{ item.name }}</div>
        <div class="line"><span class="label">类型</span>{{ item.type }}</div>
        <div class="line"><span class="label">证明力</span>{{ item.strength }}</div>
        <div class="line"><span class="label">备注</span>{{ item.notes }}</div>
      </div>
    </div>
    <div v-else class="empty">暂无可展示证据清单</div>

    <div class="sub-section">
      <div class="sub-title">缺失证据</div>
      <ul v-if="missingEvidence.length" class="list">
        <li v-for="item in missingEvidence" :key="item">{{ item }}</li>
      </ul>
      <div v-else class="empty">暂无缺失项</div>
    </div>

    <div class="sub-section">
      <div class="sub-title">法律依据</div>
      <ul v-if="legalBasis.length" class="list">
        <li v-for="item in legalBasis" :key="item">{{ item }}</li>
      </ul>
      <div v-else class="empty">暂无引用</div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface EvidenceItem {
  name: string
  type: string
  strength: string
  notes: string
}

interface EvidenceAnalysisResult {
  evidence_items?: EvidenceItem[]
  missing_evidence?: string[]
  overall_assessment?: string
  legal_basis?: string[] | string
}

const props = defineProps<{
  data?: EvidenceAnalysisResult
}>()

const evidenceItems = computed(() => props.data?.evidence_items || [])
const missingEvidence = computed(() => props.data?.missing_evidence || [])
const overallAssessment = computed(() => props.data?.overall_assessment || '')
const legalBasis = computed(() => {
  const value = props.data?.legal_basis
  if (Array.isArray(value)) return value
  if (typeof value === 'string' && value.trim()) return [value]
  return []
})
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
  color: #047857;
  background: var(--success-fade);
  border: 1px solid #a7f3d0;
  border-radius: 999px;
  padding: 2px 8px;
}

.summary {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.55;
}

.evidence-list {
  display: grid;
  gap: 8px;
}

.evidence-item {
  border: 1px solid #d1fae5;
  background: var(--success-fade);
  border-radius: 10px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.line {
  font-size: 12px;
  color: var(--text-primary);
}

.label {
  display: inline-block;
  min-width: 48px;
  color: var(--text-secondary);
  font-weight: 600;
  margin-right: 6px;
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
