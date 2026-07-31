<!-- 追踪事件时间线 — 渲染工作流运行的 Trace 事件时间线，含事件类型、时间戳、观察、步骤标签和耗时 -->
<template>
  <section class="trace-event-timeline ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><Connection /></el-icon>
        <h3>Trace 事件</h3>
      </div>
      <button type="button" :disabled="!events.length" @click="$emit('export-markdown')">
        <el-icon><Download /></el-icon>
        Markdown
      </button>
    </div>

    <div v-if="loading" class="empty">正在加载 Trace...</div>
    <div v-else-if="!events.length" class="empty">暂无 Trace 事件</div>

    <div v-else class="events" :class="{ 'is-managed': shouldManageScroll }">
      <article v-for="event in events" :key="event.eventId" class="event-item">
        <div class="event-dot" :class="event.eventType"></div>
        <div class="event-content">
          <div class="event-top">
            <strong>{{ eventLabel(event.eventType) }}</strong>
            <time>{{ formatTime(event.createdAt) }}</time>
          </div>
          <p>{{ event.observation || '无观察记录' }}</p>
          <div class="event-meta">
            <span v-if="event.stepId">step={{ event.stepId }}</span>
            <span v-if="event.agentName">agent={{ event.agentName }}</span>
            <span v-if="event.durationMs">{{ event.durationMs }}ms</span>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Connection, Download } from '@element-plus/icons-vue'
import type { TraceEvent } from '@/services/api/workflow'

const props = defineProps<{
  events: TraceEvent[]
  loading?: boolean
}>()

defineEmits<{
  'export-markdown': []
}>()

const eventLabel = (eventType: string) => {
  const labels: Record<string, string> = {
    task_created: '任务创建',
    run_started: '运行启动',
    step_started: '步骤开始',
    agent_called: 'Agent 调用',
    tool_called: '工具调用',
    checkpoint_created: '创建恢复点',
    review_required: '等待审核',
    review_decided: '审核决定',
    step_failed: '步骤失败',
    run_failed: '运行失败',
    run_recovered: '运行恢复',
    run_completed: '运行完成',
    run_cancelled: '运行取消'
  }
  return labels[eventType] || eventType
}

const formatTime = (value?: string) => {
  if (!value) return ''
  return new Date(value).toLocaleString()
}

const shouldManageScroll = computed(() => {
  return props.events.length > 6 || props.events.some(event => (event.observation || '').length > 360)
})
</script>

<style scoped>
.trace-event-timeline {
  min-width: 0;
}

.section-head,
.event-top,
.event-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-head {
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
p {
  margin: 0;
}

h3 {
  color: var(--text-primary);
  font-size: 15px;
}

button {
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
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
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.events {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.events.is-managed {
  max-height: clamp(320px, 46vh, 560px);
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.events.is-managed::-webkit-scrollbar {
  width: 5px;
}

.events.is-managed::-webkit-scrollbar-track {
  background: transparent;
}

.events.is-managed::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--scrollbar-thumb);
}

.event-item {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 10px;
}

.event-dot {
  width: 10px;
  height: 10px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--text-disabled);
}

.event-dot.agent_called,
.event-dot.run_completed {
  background: var(--success);
}

.event-dot.review_required,
.event-dot.review_decided,
.event-dot.checkpoint_created {
  background: var(--warning);
}

.event-dot.step_failed,
.event-dot.run_failed,
.event-dot.run_cancelled {
  background: var(--danger);
}

.event-content {
  min-width: 0;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.event-top {
  justify-content: space-between;
}

strong {
  color: var(--text-primary);
  font-size: 13px;
}

time,
p,
.event-meta {
  color: var(--text-secondary);
  font-size: 12px;
}

p {
  margin-top: 6px;
  overflow-wrap: anywhere;
  line-height: 1.45;
}

.event-meta {
  flex-wrap: wrap;
  margin-top: 8px;
}
</style>
