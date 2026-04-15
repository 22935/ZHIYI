<template>
  <div class="trace-timeline">
    <div v-if="!trace.length" class="empty">暂无执行轨迹</div>
    <div v-else class="trace-list">
      <div v-for="item in displayTrace" :key="item.step" class="trace-item">
        <div class="step-index">#{{ item.step }}</div>
        <div class="step-content">
          <div class="line"><span class="label">思考</span>{{ item.thoughtZh }}</div>
          <div class="line"><span class="label">动作</span>{{ item.actionZh }}</div>
          <div class="line"><span class="label">观察</span>{{ item.observationZh }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { summarizeObservationZh, toActionLabelZh, toThoughtZh } from '@/utils/agentDisplay'

export interface TraceStep {
  step: number
  thought?: string
  action?: string
  observation?: string
}

const props = defineProps<{
  trace: TraceStep[]
}>()

const displayTrace = computed(() => {
  return (props.trace || []).map(item => {
    const action = item.action || ''
    return {
      ...item,
      thoughtZh: toThoughtZh(item.thought || '', action),
      actionZh: toActionLabelZh(action),
      observationZh: summarizeObservationZh(action, item.observation || '')
    }
  })
})
</script>

<style scoped>
.trace-timeline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.empty {
  color: var(--text-secondary);
  font-size: 13px;
}

.trace-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.trace-item {
  display: grid;
  grid-template-columns: 48px 1fr;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: #fff;
}

.step-index {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 700;
}

.step-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.line {
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.45;
  word-break: break-word;
}

.label {
  display: inline-block;
  min-width: 56px;
  margin-right: 6px;
  color: var(--text-secondary);
  font-weight: 600;
}
</style>
