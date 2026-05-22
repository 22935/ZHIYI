<template>
  <section class="contract-risk-panel ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><Warning /></el-icon>
        <h3>风险点</h3>
      </div>
      <span>{{ risks.length }} 项</span>
    </div>

    <div v-if="!risks.length" class="empty">暂无风险点</div>

    <div v-else class="risk-list">
      <article v-for="risk in risks" :key="risk.id || risk.title" class="risk-item">
        <div class="risk-top">
          <strong>{{ risk.title || risk.id || '未命名风险' }}</strong>
          <span class="level" :class="risk.level">{{ levelLabel(risk.level) }}</span>
        </div>
        <p v-if="risk.clause" class="clause">{{ risk.clause }}</p>
        <p v-if="risk.reason">{{ risk.reason }}</p>
        <p v-if="risk.consequence"><b>后果</b>{{ risk.consequence }}</p>
        <p v-if="risk.suggestion"><b>建议</b>{{ risk.suggestion }}</p>
        <div v-if="risk.evidenceIds?.length" class="evidence-links">
          <span v-for="id in risk.evidenceIds" :key="id">{{ id }}</span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Warning } from '@element-plus/icons-vue'
import type { ContractRiskItem } from '@/utils/agentos/contractReviewArtifactExtractor'

defineProps<{
  risks: ContractRiskItem[]
}>()

const levelLabel = (level?: string) => {
  const labels: Record<string, string> = {
    high: '高',
    medium: '中',
    low: '低'
  }
  return labels[level || ''] || level || '未分级'
}
</script>

<style scoped>
.contract-risk-panel {
  min-width: 0;
}

.section-head,
.section-title,
.risk-top,
.evidence-links {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-head {
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  color: var(--primary-color);
}

h3,
p {
  margin: 0;
}

h3 {
  color: var(--text-primary);
  font-size: 15px;
}

.section-head span,
.empty,
p {
  color: var(--text-secondary);
  font-size: 12px;
}

.risk-list {
  display: grid;
  gap: 10px;
}

.risk-item {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.risk-top {
  justify-content: space-between;
}

strong {
  color: var(--text-primary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.level {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 800;
}

.level.high {
  background: rgba(178, 74, 74, 0.12);
  color: var(--danger);
}

.level.medium {
  background: rgba(154, 116, 50, 0.12);
  color: var(--warning);
}

.level.low {
  background: rgba(61, 118, 86, 0.12);
  color: var(--success);
}

.clause {
  padding: 8px;
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
}

b {
  margin-right: 6px;
  color: var(--text-primary);
}

.evidence-links {
  flex-wrap: wrap;
}

.evidence-links span {
  padding: 3px 7px;
  border-radius: 999px;
  background: rgba(73, 107, 143, 0.1);
  color: var(--info);
  font-size: 11px;
  font-weight: 700;
}
</style>
