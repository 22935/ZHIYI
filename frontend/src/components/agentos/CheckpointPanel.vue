<!-- 检查点面板 — 展示工作流检查点（恢复点）列表，含步骤 ID、检查点 ID、创建时间和恢复按钮 -->
<template>
  <section class="checkpoint-panel ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><Clock /></el-icon>
        <h3>恢复点</h3>
      </div>
      <span>{{ checkpoints.length }} 个</span>
    </div>

    <div v-if="loading" class="empty">正在加载恢复点...</div>
    <div v-else-if="!checkpoints.length" class="empty">暂无可用恢复点</div>

    <div v-else class="checkpoint-list">
      <article v-for="checkpoint in checkpoints" :key="checkpoint.checkpointId" class="checkpoint-item">
        <div>
          <strong>{{ checkpoint.stepId }}</strong>
          <span>{{ checkpoint.checkpointId }}</span>
          <time>{{ formatTime(checkpoint.createdAt) }}</time>
        </div>
        <button
          type="button"
          :disabled="!checkpoint.canResume"
          @click="$emit('resume', checkpoint.checkpointId)"
        >
          <el-icon><Refresh /></el-icon>
          恢复
        </button>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Clock, Refresh } from '@element-plus/icons-vue'
import type { Checkpoint } from '@/services/api/workflow'

defineProps<{
  checkpoints: Checkpoint[]
  loading?: boolean
}>()

defineEmits<{
  resume: [checkpointId: string]
}>()

const formatTime = (value?: string) => {
  if (!value) return '时间未知'
  return new Date(value).toLocaleString()
}
</script>

<style scoped>
.checkpoint-panel {
  min-width: 0;
}

.section-head,
.checkpoint-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.section-head {
  margin-bottom: 12px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
}

h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
}

.section-head span,
.empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.checkpoint-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.checkpoint-item {
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.checkpoint-item > div {
  min-width: 0;
}

strong,
span,
time {
  display: block;
}

strong {
  color: var(--text-primary);
  font-size: 13px;
}

span,
time {
  margin-top: 3px;
  overflow-wrap: anywhere;
  color: var(--text-secondary);
  font-size: 12px;
}

button {
  flex: 0 0 auto;
  height: 30px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
</style>
