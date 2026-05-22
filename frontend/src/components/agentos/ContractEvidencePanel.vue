<template>
  <section class="contract-evidence-panel ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><Link /></el-icon>
        <h3>Evidence 依据链</h3>
      </div>
      <span>{{ evidences.length }} 条</span>
    </div>

    <div v-if="!evidences.length" class="empty">暂无依据链</div>

    <div v-else class="evidence-list">
      <article v-for="item in evidences" :key="item.id || item.sourceName" class="evidence-item">
        <div class="evidence-top">
          <strong>{{ item.sourceName || item.id || '未命名依据' }}</strong>
          <span>{{ item.sourceType || 'source' }}</span>
        </div>
        <p v-if="item.citationText" class="citation">{{ item.citationText }}</p>
        <p v-if="item.content">{{ item.content }}</p>
        <div class="evidence-meta">
          <span v-if="item.id">id={{ item.id }}</span>
          <span v-if="item.riskId">risk={{ item.riskId }}</span>
          <span v-if="item.stepId">step={{ item.stepId }}</span>
          <span v-if="typeof item.confidence === 'number'">confidence={{ Math.round(item.confidence * 100) }}%</span>
          <span v-if="typeof item.retrievalScore === 'number'">score={{ item.retrievalScore.toFixed(1) }}</span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Link } from '@element-plus/icons-vue'
import type { ContractEvidenceItem } from '@/utils/agentos/contractReviewArtifactExtractor'

defineProps<{
  evidences: ContractEvidenceItem[]
}>()
</script>

<style scoped>
.contract-evidence-panel {
  min-width: 0;
}

.section-head,
.section-title,
.evidence-top,
.evidence-meta {
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
p,
.evidence-meta {
  color: var(--text-secondary);
  font-size: 12px;
}

.evidence-list {
  display: grid;
  gap: 10px;
}

.evidence-item {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.evidence-top {
  justify-content: space-between;
}

strong {
  color: var(--text-primary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.evidence-top span {
  flex: 0 0 auto;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 800;
}

.citation {
  padding: 8px;
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
}

.evidence-meta {
  flex-wrap: wrap;
}
</style>
