<!-- 工作流运行详情面板 — 展示 WorkflowRun 顶层信息：工作流 ID、状态、当前步骤、域、Run ID、引擎，含刷新和导出 -->
<template>
  <section class="workflow-run-panel ui-surface ui-surface--pad">
    <div class="panel-head">
      <div>
        <span class="eyebrow">WorkflowRun</span>
        <h2>{{ run?.workflowId || '暂无运行' }}</h2>
      </div>
      <div class="actions">
        <button type="button" @click="$emit('refresh')" :disabled="loading">
          <el-icon><Refresh /></el-icon>
          <span>刷新</span>
        </button>
        <button type="button" @click="$emit('export-trace')" :disabled="!run || loading">
          <el-icon><Download /></el-icon>
          <span>导出 Trace</span>
        </button>
      </div>
    </div>

    <div v-if="!run" class="empty">选择左侧运行记录后查看详情</div>

    <template v-else>
      <div class="status-row">
        <span class="status-pill" :class="run.status">{{ statusLabel(run.status) }}</span>
        <span>当前步骤：{{ run.currentStepId || '已结束' }}</span>
        <span>领域：{{ run.domain }}</span>
      </div>

      <div class="meta-grid">
        <div>
          <small>Run ID</small>
          <strong>{{ run.runId }}</strong>
        </div>
        <div>
          <small>Task ID</small>
          <strong>{{ run.taskId }}</strong>
        </div>
        <div>
          <small>Engine</small>
          <strong>{{ run.runtimeEngine || 'unknown' }}</strong>
        </div>
        <div>
          <small>Implementation</small>
          <strong>{{ run.implementationId || run.workflowId }}</strong>
        </div>
        <div>
          <small>审核模式</small>
          <strong>{{ run.reviewMode }}</strong>
        </div>
        <div>
          <small>恢复次数</small>
          <strong>{{ run.recoveryCount || 0 }}</strong>
        </div>
      </div>

      <div class="metric-strip">
        <div>
          <small>完成率</small>
          <strong>{{ percent(metrics?.metrics.completionRate) }}</strong>
        </div>
        <div>
          <small>失败率</small>
          <strong>{{ percent(metrics?.metrics.failureRate) }}</strong>
        </div>
        <div>
          <small>恢复成功率</small>
          <strong>{{ percent(metrics?.metrics.recoverySuccessRate) }}</strong>
        </div>
        <div>
          <small>审核记录</small>
          <strong>{{ metrics?.metrics.reviewCount ?? 0 }}</strong>
        </div>
      </div>

      <p v-if="run.error" class="error-line">{{ run.error }}</p>
    </template>
  </section>
</template>

<script setup lang="ts">
import { Download, Refresh } from '@element-plus/icons-vue'
import type { EvaluationRun, WorkflowRun, WorkflowStatus } from '@/services/api/workflow'

defineProps<{
  run: WorkflowRun | null
  metrics: EvaluationRun | null
  loading?: boolean
}>()

defineEmits<{
  refresh: []
  'export-trace': []
}>()

const statusLabel = (status: WorkflowStatus) => {
  const labels: Record<WorkflowStatus, string> = {
    pending: '等待中',
    planning: '规划中',
    running: '运行中',
    waiting_review: '待审核',
    retrying: '重试中',
    failed: '失败',
    completed: '已完成',
    cancelled: '已取消',
    skipped_by_condition: '条件跳过'
  }
  return labels[status] || status
}

const percent = (value?: number) => `${Math.round((value || 0) * 100)}%`
</script>

<style scoped>
.workflow-run-panel {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel-head,
.status-row,
.actions,
.metric-strip {
  display: flex;
  align-items: center;
  gap: 10px;
}

.panel-head {
  justify-content: space-between;
}

.eyebrow,
small {
  color: var(--text-secondary);
  font-size: 12px;
}

h2 {
  margin: 4px 0 0;
  font-size: 18px;
  color: var(--text-primary);
}

button {
  height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--surface-solid);
  color: var(--text-primary);
  cursor: pointer;
  transition: var(--transition);
}

button:hover:not(:disabled) {
  border-color: var(--border-hover);
  color: var(--primary-color);
  transform: translateY(-1px);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.status-row {
  flex-wrap: wrap;
  color: var(--text-secondary);
  font-size: 13px;
}

.status-pill {
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.status-pill.running,
.status-pill.retrying {
  background: rgba(73, 107, 143, 0.12);
  color: var(--info);
}

.status-pill.waiting_review {
  background: rgba(154, 116, 50, 0.12);
  color: var(--warning);
}

.status-pill.completed {
  background: rgba(61, 118, 86, 0.12);
  color: var(--success);
}

.status-pill.failed,
.status-pill.cancelled {
  background: rgba(178, 74, 74, 0.12);
  color: var(--danger);
}

.meta-grid,
.metric-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 10px;
}

.meta-grid > div,
.metric-strip > div {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

strong {
  display: block;
  margin-top: 4px;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 13px;
}

.metric-strip strong {
  font-size: 18px;
}

.empty,
.error-line {
  color: var(--text-secondary);
  font-size: 13px;
}

.error-line {
  padding: 10px;
  border: 1px solid rgba(178, 74, 74, 0.18);
  border-radius: 8px;
  background: rgba(178, 74, 74, 0.08);
  color: var(--danger);
}

@media (max-width: 900px) {
  .panel-head,
  .actions {
    align-items: flex-start;
    flex-direction: column;
  }

  .meta-grid,
  .metric-strip {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
