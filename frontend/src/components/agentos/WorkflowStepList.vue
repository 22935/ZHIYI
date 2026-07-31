<!-- 工作流步骤列表 — 卡片列表展示各步骤状态，含名称、Agent、能力、审核需求、重试次数、耗时和错误 -->
<template>
  <section class="workflow-step-list ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><Operation /></el-icon>
        <h3>步骤状态</h3>
      </div>
      <span>{{ steps.length }} 个步骤</span>
    </div>

    <div v-if="!steps.length" class="empty">暂无步骤</div>

    <div v-else class="steps">
      <article
        v-for="step in steps"
        :key="step.stepId"
        class="step-card"
        :class="[step.status, { active: step.stepId === currentStepId }]"
      >
        <div class="step-top">
          <span>{{ step.stepId }}</span>
          <strong>{{ statusLabel(step.status) }}</strong>
        </div>
        <h4>{{ step.name }}</h4>
        <p>{{ step.agentName }}{{ step.capability ? ` · ${step.capability}` : '' }}</p>
        <div class="step-meta">
          <span v-if="step.reviewRequired">需要审核</span>
          <span v-if="step.retryCount">重试 {{ step.retryCount }} 次</span>
          <span v-if="step.durationMs">{{ step.durationMs }}ms</span>
        </div>
        <p v-if="step.error" class="step-error">{{ step.error }}</p>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Operation } from '@element-plus/icons-vue'
import type { StepStatus, WorkflowStep } from '@/services/api/agentos'

defineProps<{
  steps: WorkflowStep[]
  currentStepId?: string
}>()

const statusLabel = (status: StepStatus) => {
  const labels: Record<StepStatus, string> = {
    pending: '等待',
    running: '运行',
    waiting_review: '待审',
    retrying: '重试',
    failed: '失败',
    completed: '完成',
    cancelled: '取消',
    skipped_by_condition: '条件跳过'
  }
  return labels[status] || status
}
</script>

<style scoped>
.workflow-step-list {
  min-width: 0;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
}

h3,
h4,
p {
  margin: 0;
}

h3 {
  font-size: 15px;
  color: var(--text-primary);
}

.section-head span,
.empty,
p,
.step-meta {
  color: var(--text-secondary);
  font-size: 12px;
}

.steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
}

.step-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 138px;
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
  transition: var(--transition);
}

.step-card.active {
  border-color: var(--primary-line);
  background: var(--surface-solid);
  box-shadow: inset 2px 0 0 var(--primary-color), var(--shadow-sm);
}

.step-top,
.step-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.step-top span {
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.step-top strong {
  flex: 0 0 auto;
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 11px;
}

.running .step-top strong,
.retrying .step-top strong {
  background: rgba(73, 107, 143, 0.12);
  color: var(--info);
}

.waiting_review .step-top strong {
  background: rgba(154, 116, 50, 0.12);
  color: var(--warning);
}

.completed .step-top strong {
  background: rgba(61, 118, 86, 0.12);
  color: var(--success);
}

.failed .step-top strong,
.cancelled .step-top strong {
  background: rgba(178, 74, 74, 0.12);
  color: var(--danger);
}

h4 {
  color: var(--text-primary);
  font-size: 14px;
}

.step-meta {
  flex-wrap: wrap;
  justify-content: flex-start;
}

.step-error {
  padding: 8px;
  border-radius: 6px;
  background: rgba(178, 74, 74, 0.08);
  color: var(--danger);
  overflow-wrap: anywhere;
}
</style>
