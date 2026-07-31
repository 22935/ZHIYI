<!-- 调用结果面板 — 列出 Agent 和工具调用结果，含标题、类型、摘要、Agent 名、状态、耗时和可展开详情 -->
<template>
  <section class="call-result-panel ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><Cpu /></el-icon>
        <h3>调用结果</h3>
      </div>
      <span>{{ results.length }} 条</span>
    </div>

    <div v-if="loading" class="empty">正在整理调用结果...</div>
    <div v-else-if="!results.length" class="empty">启动审查后显示 Agent 与工具调用结果</div>

    <div v-else class="result-list" :class="{ 'is-managed': shouldManageScroll }">
      <article v-for="result in visibleResults" :key="result.id" class="result-item">
        <div class="result-top">
          <strong>{{ result.title }}</strong>
          <span>{{ result.kind }}</span>
        </div>
        <p>{{ result.summary }}</p>
        <div class="result-meta">
          <span v-if="result.agentName">agent={{ result.agentName }}</span>
          <span v-if="result.status">status={{ result.status }}</span>
          <span v-if="result.durationMs">{{ result.durationMs }}ms</span>
        </div>
        <details v-if="result.hasDetails" @toggle="handleDetailsToggle(result.id, $event)">
          <summary>原始输出</summary>
          <pre v-if="expandedDetails.has(result.id)" :class="{ 'is-managed': shouldManageDetails(result) }">{{ detailsText(result) }}</pre>
        </details>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Cpu } from '@element-plus/icons-vue'
import type { TraceEvent, WorkflowRun, WorkflowStep } from '@/services/api/workflow'

const props = defineProps<{
  run: WorkflowRun | null
  events: TraceEvent[]
  loading?: boolean
}>()

interface CallResultItem {
  id: string
  title: string
  kind: string
  summary: string
  hasDetails?: boolean
  detailSource?: unknown
  detailSize?: number
  agentName?: string
  status?: string
  durationMs?: number
  timestamp?: string
}

const expandedDetails = ref(new Set<string>())

const preferredKeys = [
  'summary',
  'result',
  'message',
  'observation',
  'analysis',
  'conclusion',
  'suggestion',
  'reportMarkdown',
  'report_markdown',
  'risks',
  'evidences'
]

const compact = (text: string, limit = 220) => {
  const normalized = text.replace(/\s+/g, ' ').trim()
  if (normalized.length <= limit) return normalized
  return `${normalized.slice(0, limit - 1)}...`
}

const isRecord = (value: unknown): value is Record<string, unknown> => {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

const summarize = (value: unknown, depth = 0): string => {
  if (value == null) return ''
  if (typeof value === 'string') return compact(value)
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)

  if (Array.isArray(value)) {
    if (!value.length) return '空列表'
    if (value.every(item => ['string', 'number', 'boolean'].includes(typeof item))) {
      return compact(value.map(String).join('、'))
    }
    const samples = value.slice(0, 2).map(item => summarize(item, depth + 1)).filter(Boolean)
    return compact(`${value.length} 项：${samples.join('；') || '结构化结果'}`)
  }

  if (isRecord(value)) {
    for (const key of preferredKeys) {
      if (key in value) {
        const summary = summarize(value[key], depth + 1)
        if (summary) return summary
      }
    }

    const keys = Object.keys(value)
    if (!keys.length) return '空对象'

    if (depth < 1) {
      const samples = keys
        .slice(0, 3)
        .map(key => `${key}: ${summarize(value[key], depth + 1)}`)
        .filter(Boolean)
      return compact(samples.join('；') || keys.slice(0, 6).join('、'))
    }

    return compact(keys.slice(0, 6).join('、'))
  }

  return compact(String(value))
}

const estimateDetailsSize = (value: unknown) => {
  if (value == null) return 0
  if (typeof value === 'string') return value.length
  if (typeof value === 'number' || typeof value === 'boolean') return String(value).length
  if (Array.isArray(value)) return Math.min(value.length * 160, 5000)
  if (isRecord(value)) return Math.min(Object.keys(value).length * 220, 5000)
  return 0
}

const detailsText = (result: CallResultItem) => {
  if (result.detailSource == null) return ''
  try {
    const text = JSON.stringify(result.detailSource, null, 2)
    return text.length > 4000 ? `${text.slice(0, 3999)}...` : text
  } catch {
    return String(result.detailSource)
  }
}

const handleDetailsToggle = (id: string, event: Event) => {
  const next = new Set(expandedDetails.value)
  if ((event.target as HTMLDetailsElement).open) {
    next.add(id)
  } else {
    next.delete(id)
  }
  expandedDetails.value = next
}

const stepToResult = (step: WorkflowStep): CallResultItem | null => {
  const hasOutput = step.output && Object.keys(step.output).length > 0
  if (!hasOutput && !step.error) return null

  return {
    id: `step:${step.stepId}`,
    title: step.name || step.stepId,
    kind: step.capability || 'step',
    summary: step.error || summarize(step.output),
    hasDetails: hasOutput,
    detailSource: hasOutput ? step.output : undefined,
    detailSize: hasOutput ? estimateDetailsSize(step.output) : 0,
    agentName: step.agentName,
    status: step.status,
    durationMs: step.durationMs,
    timestamp: step.completedAt || step.startedAt
  }
}

const eventToResult = (event: TraceEvent): CallResultItem | null => {
  const isCallEvent = ['agent_called', 'tool_called', 'run_completed', 'review_decided'].includes(event.eventType)
  if (!isCallEvent && !event.observation && !event.payload) return null

  const payloadSummary = summarize(event.payload)
  const summary = event.observation || payloadSummary
  if (!summary) return null

  return {
    id: `event:${event.eventId}`,
    title: event.stepId || event.eventType,
    kind: event.eventType,
    summary,
    hasDetails: Boolean(event.payload),
    detailSource: event.payload,
    detailSize: estimateDetailsSize(event.payload),
    agentName: event.agentName,
    durationMs: event.durationMs,
    timestamp: event.createdAt
  }
}

const results = computed(() => {
  const stepResults = (props.run?.steps || [])
    .map(stepToResult)
    .filter((item): item is CallResultItem => Boolean(item))

  const eventResults = props.events
    .map(eventToResult)
    .filter((item): item is CallResultItem => Boolean(item))

  return [...stepResults, ...eventResults]
    .sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''))
})

const shouldManageScroll = computed(() => results.value.length > 4)

const visibleResults = computed(() => results.value)

const shouldManageDetails = (result: CallResultItem) => {
  return (result.detailSize || 0) > 900
}
</script>

<style scoped>
.call-result-panel {
  min-width: 0;
}

.section-head,
.section-title,
.result-top,
.result-meta {
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
.result-meta,
summary {
  color: var(--text-secondary);
  font-size: 12px;
}

.result-list {
  display: grid;
  gap: 10px;
}

.result-list.is-managed {
  max-height: clamp(360px, 52vh, 640px);
  overflow-y: auto;
  overflow-x: hidden;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.result-list.is-managed::-webkit-scrollbar,
pre.is-managed::-webkit-scrollbar {
  width: 5px;
}

.result-list.is-managed::-webkit-scrollbar-track,
pre.is-managed::-webkit-scrollbar-track {
  background: transparent;
}

.result-list.is-managed::-webkit-scrollbar-thumb,
pre.is-managed::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--scrollbar-thumb);
}

.result-item {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.result-top {
  justify-content: space-between;
}

strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-size: 13px;
}

.result-top span {
  flex: 0 0 auto;
  padding: 3px 7px;
  border-radius: 999px;
  background: rgba(73, 107, 143, 0.1);
  color: var(--info);
  font-size: 11px;
  font-weight: 800;
}

p {
  overflow-wrap: anywhere;
  line-height: 1.45;
}

.result-meta {
  flex-wrap: wrap;
}

details {
  min-width: 0;
}

summary {
  cursor: pointer;
  font-weight: 700;
}

pre {
  margin: 8px 0 0;
  padding: 8px;
  border-radius: 6px;
  background: var(--surface-solid);
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

pre.is-managed {
  max-height: 240px;
  overflow-y: auto;
  overflow-x: hidden;
  scrollbar-gutter: stable;
}
</style>
