<template>
  <WorkbenchLayout :show-left="false" :show-right="false" storage-key="zhiyi.memory.layout.v1">
    <template #main>
      <main class="memory-page" aria-label="运行记忆">
        <WorkspacePageHero
          eyebrow="MEMORY"
          title="运行记忆"
        />

        <div class="memory-page__body" :class="{ 'is-loading': runsLoading }">
          <aside class="memory-runs" aria-label="运行列表" :aria-busy="runsLoading">
            <div class="memory-runs__head">
              <div>
                <span class="memory-runs__title">记忆来源</span>
                <span class="memory-runs__subtitle">Mission · Run 层级</span>
              </div>
              <div class="memory-runs__actions">
                <span class="memory-runs__count">{{ runsLoading ? '…' : `${runs.length} RUN` }}</span>
                <button
                  type="button"
                  class="memory-runs__collapse"
                  :disabled="!missionGroups.length"
                  :aria-label="allMissionsCollapsed ? '展开全部 Mission' : '折叠全部 Mission'"
                  @click="toggleAllMissions"
                >
                  {{ allMissionsCollapsed ? '展开全部' : '折叠全部' }}
                </button>
              </div>
            </div>
            <div v-if="runsLoading" class="memory-runs__loading" aria-label="正在加载运行列表">
              <div v-for="index in 6" :key="index" class="memory-run-skeleton">
                <span class="memory-run-skeleton__dot" />
                <span class="memory-run-skeleton__copy">
                  <span class="memory-skeleton-line memory-skeleton-line--title" />
                  <span class="memory-skeleton-line memory-skeleton-line--meta" />
                </span>
              </div>
            </div>
            <div v-else-if="runsError" class="memory-runs__error" role="alert">
              <p>{{ runsError }}</p>
              <button type="button" class="memory-runs__retry" @click="loadRuns">重试</button>
            </div>
            <div v-else-if="!runs.length" class="memory-runs__hint">暂无运行记录</div>
            <ul v-else class="memory-runs__list">
              <li v-for="group in missionGroups" :key="group.missionId" class="memory-mission">
                <button
                  type="button"
                  class="memory-mission__head"
                  :aria-expanded="isMissionExpanded(group.missionId)"
                  :aria-controls="`memory-mission-${group.missionId}`"
                  @click="toggleMission(group.missionId)"
                >
                  <span
                    class="memory-mission__chevron"
                    :class="{ 'is-expanded': isMissionExpanded(group.missionId) }"
                    aria-hidden="true"
                  />
                  <span class="memory-mission__identity">
                    <span class="memory-mission__eyebrow">MISSION</span>
                    <span class="memory-mission__title">{{ group.title }}</span>
                    <span class="memory-mission__id">{{ group.missionId }}</span>
                  </span>
                  <span class="memory-mission__count">{{ group.runs.length }} RUN</span>
                </button>

                <ul
                  v-if="isMissionExpanded(group.missionId)"
                  :id="`memory-mission-${group.missionId}`"
                  class="memory-mission__runs"
                >
                  <li v-for="(run, runIndex) in group.runs" :key="run.runId">
                    <button
                      type="button"
                      class="memory-run"
                      :class="{ 'is-active': run.runId === selectedRunId }"
                      :aria-current="run.runId === selectedRunId ? 'true' : undefined"
                      @click="selectRun(run.runId)"
                    >
                      <span class="memory-run__dot" :data-status="run.status" aria-hidden="true" />
                      <span class="memory-run__meta">
                        <span class="memory-run__title">
                          <span class="memory-run__index">Run {{ formatRunNumber(runIndex) }}</span>
                          <span class="memory-run__status">{{ formatRunStatus(run.status) }}</span>
                        </span>
                        <span class="memory-run__sub">{{ run.runId }} · {{ formatTime(run.updatedAt) }}</span>
                      </span>
                    </button>
                  </li>
                </ul>
              </li>
            </ul>
          </aside>

          <section class="memory-detail" aria-label="记忆详情">
            <section v-if="runsLoading" class="memory-loading-state" aria-live="polite" aria-label="正在加载记忆">
              <div class="memory-loading-state__intro">
                <div>
                  <span class="memory-detail__eyebrow">MEMORY / SYNC</span>
                  <h2>正在同步运行记忆</h2>
                  <p>正在获取最近运行，并准备记忆流向与步骤记录。</p>
                </div>
                <span class="memory-loading-state__status"><i /> SYNCING</span>
              </div>
              <div class="memory-loading-state__stats" aria-hidden="true">
                <div v-for="index in 4" :key="index" class="memory-loading-stat">
                  <span class="memory-skeleton-line memory-skeleton-line--number" />
                  <span class="memory-skeleton-line memory-skeleton-line--label" />
                </div>
              </div>
              <div class="memory-loading-state__flow" aria-hidden="true">
                <div class="memory-loading-state__flow-head">
                  <span class="memory-skeleton-line memory-skeleton-line--flow-title" />
                  <span class="memory-skeleton-line memory-skeleton-line--flow-meta" />
                </div>
                <div class="memory-loading-state__network">
                </div>
              </div>
              <div class="memory-loading-state__trace" aria-hidden="true">
                <div class="memory-loading-state__trace-head">
                  <span class="memory-skeleton-line memory-skeleton-line--trace-title" />
                  <span class="memory-skeleton-line memory-skeleton-line--trace-meta" />
                </div>
                <div class="memory-loading-state__trace-list">
                  <div v-for="index in 3" :key="index" class="memory-loading-trace">
                    <span class="memory-loading-trace__dot" />
                    <span class="memory-loading-trace__copy">
                      <span class="memory-skeleton-line memory-skeleton-line--trace-main" />
                      <span class="memory-skeleton-line memory-skeleton-line--trace-sub" />
                    </span>
                    <span class="memory-skeleton-line memory-skeleton-line--trace-state" />
                  </div>
                </div>
              </div>
            </section>
            <div v-else-if="runsError" class="memory-detail__empty memory-detail__empty--error" role="alert">
              <strong>运行记录加载失败</strong>
              <p>{{ runsError }}</p>
              <button type="button" class="memory-detail__retry" @click="loadRuns">重新加载</button>
            </div>
            <div v-else-if="!selectedRunId" class="memory-detail__empty">
              <p>选择左侧一个运行，查看它的记忆流。</p>
            </div>
            <template v-else>
              <div v-if="eventsError" class="memory-detail__error" role="alert">
                记忆事件加载失败：{{ eventsError }}
                <button type="button" class="memory-detail__retry" @click="loadEvents(true)">重试</button>
              </div>

              <header class="memory-detail__intro">
                <div class="memory-detail__identity">
                  <span class="memory-detail__eyebrow">SELECTED RUN</span>
                  <h2>{{ selectedRun?.title || selectedRun?.missionId || '未命名运行' }}</h2>
                  <code>{{ selectedRunId }}</code>
                </div>
                <span class="memory-detail__status" :data-status="selectedRun?.status">
                  {{ formatRunStatus(selectedRun?.status) }}
                </span>
              </header>

              <div class="memory-stats" aria-label="记忆统计">
                <div class="memory-stats__label">
                  <span class="memory-stats__eyebrow">RUN SIGNALS</span>
                  <span>记忆摘要</span>
                </div>
                <div class="memory-stats__grid">
                  <div class="memory-stat">
                    <strong>{{ flow?.stats.reads ?? '–' }}</strong>
                    <span>召回</span>
                  </div>
                  <div class="memory-stat">
                    <strong>{{ flow?.stats.writes ?? '–' }}</strong>
                    <span>写入</span>
                  </div>
                  <div class="memory-stat">
                    <strong>{{ flow?.stats.capsules ?? '–' }}</strong>
                    <span>阶段胶囊</span>
                  </div>
                  <div class="memory-stat">
                    <strong>{{ flow?.stats.hitEdges ?? '–' }}</strong>
                    <span>记忆流向</span>
                  </div>
                </div>
                <div v-if="eventsLoading" class="memory-stats__loading">刷新中…</div>
              </div>

              <div v-if="flow && flow.steps.length" class="memory-flow" aria-label="记忆流向图">
                <header class="memory-flow__header">
                  <div>
                    <span class="memory-flow__eyebrow">FLOW MAP</span>
                    <h2>记忆流向</h2>
                  </div>
                  <span class="memory-flow__count">{{ flow.edges.length }} 条命中</span>
                </header>
                <div class="memory-flow__scroll">
                  <svg
                    class="memory-flow__svg"
                    :viewBox="`0 0 ${flowLayout.width} ${flowLayout.height}`"
                    :style="{ width: flowLayout.width + 'px' }"
                    role="img"
                    aria-label="节点间记忆流向图"
                  >
                    <defs>
                      <marker
                        id="memory-flow-arrow"
                        viewBox="0 0 8 8"
                        refX="7"
                        refY="4"
                        markerWidth="5"
                        markerHeight="5"
                        orient="auto-start-reverse"
                      >
                        <path d="M 0 0 L 8 4 L 0 8 z" class="memory-flow__arrow" />
                      </marker>
                    </defs>
                    <g class="memory-flow__guides" aria-hidden="true">
                      <line x1="24" y1="64" :x2="flowLayout.width - 24" y2="64" />
                      <line x1="24" y1="152" :x2="flowLayout.width - 24" y2="152" />
                    </g>
                    <path
                      v-for="(edge, index) in flow.edges"
                      :key="index"
                      class="memory-flow__edge"
                      :class="{ 'is-highlight': isEdgeHighlighted(edge) }"
                      :d="edgePath(edge)"
                      marker-end="url(#memory-flow-arrow)"
                    />
                    <g
                      v-for="(node, index) in flow.nodes"
                      :key="node.stepId"
                      class="memory-flow__node"
                      :class="{ 'is-highlight': hoveredStepId === node.stepId }"
                      @mouseenter="hoveredStepId = node.stepId"
                      @mouseleave="hoveredStepId = null"
                    >
                      <circle :cx="node.x" :cy="node.y" r="22" class="memory-flow__halo" />
                      <circle
                        :cx="node.x"
                        :cy="node.y"
                        :r="hoveredStepId === node.stepId ? 18 : 14"
                        class="memory-flow__circle"
                        :class="{ 'has-write': node.hasWrite }"
                      />
                      <circle v-if="node.hasWrite" :cx="node.x" :cy="node.y" r="3" class="memory-flow__write-dot" />
                      <text :x="node.x" :y="node.y + (node.row === 0 ? -26 : 36)" class="memory-flow__label">
                        {{ shortStepLabel(node.stepId) }}
                      </text>
                      <title>{{ node.stepId }}</title>
                    </g>
                  </svg>
                </div>
                <p class="memory-flow__legend">
                  实心节点 = 已写入记忆；连线 = 后续节点召回时命中了来源节点的记忆卡片。
                </p>
              </div>
              <div v-else-if="!eventsLoading" class="memory-detail__empty">
                <p>该运行还没有记忆事件（可能在规划阶段即结束，或早于记忆系统上线）。</p>
              </div>

              <ol v-if="flow && flow.steps.length" class="memory-steps" aria-label="各步骤记忆">
                <li class="memory-steps__heading">
                  <span class="memory-flow__eyebrow">TRACE</span>
                  <h2>步骤记录</h2>
                </li>
                <li
                  v-for="(step, index) in flow.steps"
                  :id="`memory-step-${index}`"
                  :key="step.stepId"
                  class="memory-step"
                  :class="{ 'is-hover': hoveredStepId === step.stepId }"
                  @mouseenter="hoveredStepId = step.stepId"
                  @mouseleave="hoveredStepId = null"
                >
                  <div class="memory-step__head">
                    <span class="memory-step__index">#{{ index + 1 }}</span>
                    <span class="memory-step__id">{{ step.stepId }}</span>
                    <span v-if="step.access" class="memory-step__mode" :data-fallback="!!step.access.fallbackReason">
                      {{ step.access.retrievalMode || '未知检索' }}
                    </span>
                  </div>
                  <div class="memory-step__body">
                    <div v-if="step.access" class="memory-step__row">
                      <span class="memory-step__tag memory-step__tag--read">召回</span>
                      <template v-if="step.access.hitRefs.length">
                        <span
                          v-for="ref in step.access.hitRefs"
                          :key="ref"
                          class="memory-chip"
                          :class="{ 'is-hit': isKnownRef(ref) }"
                          :title="ref"
                        >
                          {{ shortStepLabel(stepIdFromMemoryRef(ref) || ref) }}
                        </span>
                      </template>
                      <span v-else class="memory-step__muted">无命中（首节点或策略只读胶囊）</span>
                      <span v-if="step.access.fallbackReason" class="memory-step__warn">
                        {{ step.access.fallbackReason }}
                      </span>
                    </div>
                    <div v-if="step.write" class="memory-step__row">
                      <span class="memory-step__tag memory-step__tag--write">写入</span>
                      <span class="memory-step__summary">{{ step.write.summary || '（无摘要）' }}</span>
                      <span
                        v-if="step.write.metrics"
                        class="memory-step__metrics"
                      >{{ formatMetrics(step.write.metrics) }}</span>
                    </div>
                    <div v-if="!step.access && !step.write" class="memory-step__muted">仅参与记忆流</div>
                  </div>
                </li>
              </ol>

              <section v-if="flow && flow.capsules.length" class="memory-capsules" aria-label="阶段胶囊">
                <header class="memory-capsules__header">
                  <div>
                    <span class="memory-flow__eyebrow">CAPSULES</span>
                    <h2>阶段胶囊</h2>
                  </div>
                  <span>{{ flow.capsules.length }} 个阶段</span>
                </header>
                <div class="memory-capsule-grid">
                  <article v-for="(capsule, index) in flow.capsules" :key="index" class="memory-capsule">
                    <header class="memory-capsule__head">
                      <span class="memory-capsule__phase">{{ capsule.phaseId || '未知阶段' }}</span>
                      <span v-if="capsule.tokenCount != null" class="memory-capsule__tokens">
                        {{ capsule.tokenCount }} tokens
                      </span>
                    </header>
                    <div class="memory-capsule__refs">
                      <span
                        v-for="ref in capsule.sourceMemoryRefs || []"
                        :key="ref"
                        class="memory-chip"
                        :title="ref"
                      >
                        {{ shortStepLabel(stepIdFromMemoryRef(ref) || ref) }}
                      </span>
                    </div>
                  </article>
                </div>
              </section>
            </template>
          </section>
        </div>
      </main>
    </template>
  </WorkbenchLayout>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import WorkspacePageHero from '@/components/app/WorkspacePageHero.vue'
import { workflowApi } from '@/services/api/workflow'
import { agentosApi, type MemoryWriteEvent, type MissionListItem, type RunMemoryEvent, type WorkflowRunSummary } from '@/services/api/agentos'
import {
  projectMemoryFlow,
  shortStepLabel,
  stepIdFromMemoryRef,
  type MemoryFlowEdge,
  type MemoryFlowProjection
} from './memoryFlow'

interface FlowNode {
  stepId: string
  x: number
  y: number
  row: 0 | 1
  hasWrite: boolean
}

interface FlowWithNodes extends MemoryFlowProjection {
  nodes: FlowNode[]
}

interface MemoryMissionGroup {
  missionId: string
  title: string
  runs: WorkflowRunSummary[]
}

const route = useRoute()
const runs = ref<WorkflowRunSummary[]>([])
const missions = ref<MissionListItem[]>([])
const runsLoading = ref(false)
const runsError = ref<string | null>(null)
const selectedRunId = ref<string | null>(null)
const expandedMissionIds = ref<Set<string>>(new Set())
const eventsLoading = ref(false)
const eventsError = ref<string | null>(null)
const rawEvents = ref<RunMemoryEvent[]>([])
const hoveredStepId = ref<string | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let pollGeneration = 0

const ACTIVE_STATUSES = new Set(['running', 'pending', 'planning', 'executing', 'graph_building', 'understanding'])

const selectedRun = computed(() => runs.value.find(run => run.runId === selectedRunId.value) || null)

const missionGroups = computed<MemoryMissionGroup[]>(() => {
  const missionTitles = new Map(missions.value.map(mission => [mission.missionId, mission.title]))
  const groups = new Map<string, MemoryMissionGroup>()

  for (const run of runs.value) {
    const existing = groups.get(run.missionId)
    if (existing) {
      existing.runs.push(run)
      continue
    }
    groups.set(run.missionId, {
      missionId: run.missionId,
      title: missionTitles.get(run.missionId) || run.title || run.missionId,
      runs: [run]
    })
  }

  return [...groups.values()]
})

const allMissionsCollapsed = computed(() => missionGroups.value.every(group => !expandedMissionIds.value.has(group.missionId)))

const flow = computed<FlowWithNodes | null>(() => {
  if (!rawEvents.value.length) {
    return null
  }
  const projection = projectMemoryFlow(rawEvents.value)
  const nodeGap = 148
  const rowY = [64, 152]
  const nodes = projection.steps.map((step, index) => {
    const row = (index % 2) as 0 | 1
    return {
      stepId: step.stepId,
      x: 82 + index * nodeGap,
      y: rowY[row],
      row,
      hasWrite: step.write != null
    }
  })
  return { ...projection, nodes }
})

const flowLayout = computed(() => {
  const count = flow.value?.steps.length ?? 0
  return {
    width: Math.max(count * 148 + 46, 520),
    height: 214
  }
})

const stepIndex = computed(() => {
  const map = new Map<string, number>()
  flow.value?.steps.forEach((step, index) => map.set(step.stepId, index))
  return map
})

function nodePoint(stepId: string): { x: number; y: number } {
  const node = flow.value?.nodes.find(item => item.stepId === stepId)
  return node ? { x: node.x, y: node.y } : { x: 0, y: 0 }
}

function edgePath(edge: MemoryFlowEdge): string {
  const from = nodePoint(edge.sourceStepId)
  const to = nodePoint(edge.targetStepId)
  const bend = Math.max(36, Math.abs(to.x - from.x) * 0.28)
  return `M ${from.x} ${from.y} C ${from.x + bend} ${from.y}, ${to.x - bend} ${to.y}, ${to.x} ${to.y}`
}

function isEdgeHighlighted(edge: MemoryFlowEdge): boolean {
  return !!hoveredStepId.value && (edge.sourceStepId === hoveredStepId.value || edge.targetStepId === hoveredStepId.value)
}

function isKnownRef(ref: string): boolean {
  const stepId = stepIdFromMemoryRef(ref)
  return !!stepId && stepIndex.value.has(stepId)
}

function formatMetrics(metrics: NonNullable<MemoryWriteEvent['metrics']>): string {
  const parts: string[] = []
  if (metrics.fieldCount != null) parts.push(`${metrics.fieldCount} 字段`)
  if (metrics.modelInvocationCount != null) parts.push(`${metrics.modelInvocationCount} 次模型`)
  if (metrics.toolCallCount != null) parts.push(`${metrics.toolCallCount} 次工具`)
  if (metrics.evidenceCount != null) parts.push(`${metrics.evidenceCount} 证据`)
  return parts.join(' · ')
}

function formatTime(iso: string | null | undefined): string {
  if (!iso) return '–'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '–'
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function formatRunNumber(index: number): string {
  return String(index + 1).padStart(2, '0')
}

function isMissionExpanded(missionId: string): boolean {
  return expandedMissionIds.value.has(missionId)
}

function toggleMission(missionId: string): void {
  const next = new Set(expandedMissionIds.value)
  if (next.has(missionId)) {
    next.delete(missionId)
  } else {
    next.add(missionId)
  }
  expandedMissionIds.value = next
}

function toggleAllMissions(): void {
  expandedMissionIds.value = allMissionsCollapsed.value
    ? new Set(missionGroups.value.map(group => group.missionId))
    : new Set()
}

function formatRunStatus(status: string | null | undefined): string {
  const labels: Record<string, string> = {
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
    running: '运行中',
    executing: '执行中',
    planning: '规划中',
    pending: '等待中'
  }
  return labels[status || ''] || status || '未知状态'
}

function formatRunsError(error: unknown): string {
  const status = (error as { response?: { status?: number } } | null)?.response?.status
  if (status === 401 || status === 403) return '本机服务认证失败，请检查运行配置后重试。'
  if (status != null && status >= 500) return '运行服务暂时不可用，请稍后重试。'
  return error instanceof Error && error.message ? error.message : '运行记录暂时无法加载，请重试。'
}

async function loadRuns(): Promise<void> {
  runsLoading.value = true
  runsError.value = null
  const missionsRequest = agentosApi.listMissions({ page: 1, pageSize: 100 })
    .then(page => {
      missions.value = page.items
    })
    .catch(() => {
      // Mission metadata is supplemental. Run IDs still provide a usable fallback grouping.
      missions.value = []
    })
  try {
    const page = await workflowApi.listRuns({ page: 1, pageSize: 50 })
    runs.value = page.items
    expandedMissionIds.value = new Set()
    if (!selectedRunId.value && runs.value.length) {
      const fromQuery = typeof route.query.runId === 'string' ? route.query.runId : null
      const target = fromQuery && runs.value.some(run => run.runId === fromQuery) ? fromQuery : runs.value[0].runId
      selectRun(target)
    }
  } catch (error) {
    runs.value = []
    selectedRunId.value = null
    rawEvents.value = []
    runsError.value = formatRunsError(error)
  } finally {
    runsLoading.value = false
  }
  await missionsRequest
}

function selectRun(runId: string): void {
  if (selectedRunId.value === runId) {
    return
  }
  const run = runs.value.find(item => item.runId === runId)
  if (run) {
    const next = new Set(expandedMissionIds.value)
    next.add(run.missionId)
    expandedMissionIds.value = next
  }
  selectedRunId.value = runId
  void loadEvents(true)
}

async function loadEvents(reset: boolean): Promise<void> {
  const runId = selectedRunId.value
  if (!runId) {
    return
  }
  if (reset) {
    eventsError.value = null
  }
  eventsLoading.value = true
  const generation = ++pollGeneration
  try {
    const response = await workflowApi.listMemoryEvents(runId)
    if (generation !== pollGeneration || selectedRunId.value !== runId) {
      return
    }
    rawEvents.value = response.items
  } catch (error) {
    if (generation !== pollGeneration || selectedRunId.value !== runId) {
      return
    }
    eventsError.value = error instanceof Error ? error.message : String(error)
    if (reset) {
      rawEvents.value = []
    }
  } finally {
    if (generation === pollGeneration) {
      eventsLoading.value = false
    }
  }
}

function syncPolling(): void {
  const shouldPoll = !!selectedRun.value && ACTIVE_STATUSES.has(selectedRun.value.status)
  if (shouldPoll && pollTimer == null) {
    pollTimer = setInterval(() => void loadEvents(false), 8000)
  } else if (!shouldPoll && pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

watch(selectedRun, syncPolling)

onMounted(() => {
  void loadRuns()
})

onUnmounted(() => {
  pollGeneration += 1
  if (pollTimer != null) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})
</script>

<style scoped>
.memory-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 0 clamp(18px, 3.4vw, 56px) 48px;
  box-sizing: border-box;
  color: var(--wb-text);
  background: var(--wb-surface-shell);
}

.memory-page :deep(.workspace-page-hero) {
  width: min(100%, 1400px);
  margin: 0 auto;
}

.memory-page__body {
  display: grid;
  grid-template-columns: minmax(232px, 264px) minmax(0, 1fr);
  gap: 16px;
  width: min(100%, 1400px);
  margin: 20px auto 0;
  align-items: stretch;
}

.memory-page__body.is-loading {
  flex: 1 1 auto;
  min-height: 0;
}

.memory-page__body.is-loading .memory-detail,
.memory-page__body.is-loading .memory-loading-state {
  min-height: 0;
  height: 100%;
}

.memory-runs,
.memory-stats,
.memory-flow,
.memory-step,
.memory-capsule {
  border: 1px solid var(--wb-border-soft);
  border-radius: var(--wb-radius-section);
  background: var(--wb-surface-section);
  box-shadow: var(--wb-shadow-section);
}

.memory-runs {
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 146px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.memory-runs__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 58px;
  padding: 11px 14px 10px;
  border-bottom: 1px solid var(--wb-border-soft);
  background: color-mix(in srgb, var(--wb-surface-pane) 58%, var(--wb-surface-section));
}

.memory-runs__title,
.memory-runs__subtitle {
  display: block;
}

.memory-runs__title {
  color: var(--wb-text);
  font-size: 13px;
  font-weight: 650;
}

.memory-runs__subtitle {
  margin-top: 2px;
  color: var(--wb-text-muted);
  font-size: 10px;
}

.memory-runs__actions {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 5px;
}

.memory-runs__count,
.memory-flow__count {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border: 1px solid color-mix(in srgb, var(--wb-accent) 24%, var(--wb-border-soft));
  border-radius: var(--wb-radius-sm);
  color: var(--wb-accent);
  background: color-mix(in srgb, var(--wb-accent-soft) 72%, var(--wb-surface-section));
  font: 10px var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
}

.memory-runs__collapse {
  padding: 0;
  border: 0;
  color: var(--wb-accent);
  background: transparent;
  cursor: pointer;
  font-size: 10px;
  white-space: nowrap;
}

.memory-runs__collapse:hover {
  color: var(--wb-text);
}

.memory-runs__collapse:disabled {
  color: var(--wb-text-muted);
  cursor: default;
}

.memory-runs__collapse:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
  border-radius: 3px;
}

.memory-runs__hint {
  padding: 18px 14px;
  color: var(--wb-text-secondary);
  font-size: 12px;
}

.memory-runs__error {
  display: grid;
  gap: 8px;
  padding: 16px 14px 18px;
  color: var(--wb-danger);
  background: color-mix(in srgb, var(--wb-danger) 5%, var(--wb-surface-section));
  font-size: 12px;
}

.memory-runs__error p {
  margin: 0;
  line-height: 1.55;
}

.memory-runs__retry {
  justify-self: start;
  padding: 0;
  border: 0;
  color: var(--wb-accent);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
}

.memory-runs__loading {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  gap: 2px;
  padding: 8px;
  align-content: stretch;
}

.memory-run-skeleton {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 54px;
  padding: 8px 9px;
}

.memory-run-skeleton__dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: color-mix(in srgb, var(--wb-accent) 24%, var(--wb-surface-inset));
}

.memory-run-skeleton__copy {
  display: grid;
  flex: 1;
  gap: 7px;
}

.memory-runs__list {
  list-style: none;
  margin: 0;
  padding: 8px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.memory-mission {
  margin-bottom: 4px;
}

.memory-mission:last-child {
  margin-bottom: 0;
}

.memory-mission__head {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 62px;
  padding: 9px 10px;
  border: 1px solid transparent;
  border-radius: var(--wb-radius-sm);
  color: inherit;
  background: color-mix(in srgb, var(--wb-surface-pane) 42%, transparent);
  cursor: pointer;
  text-align: left;
  transition: var(--transition);
}

.memory-mission__head:hover {
  border-color: var(--wb-border-soft);
  background: var(--wb-hover);
}

.memory-mission__head:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
}

.memory-mission__chevron {
  width: 7px;
  height: 7px;
  margin-left: 2px;
  border-right: 1.5px solid var(--wb-text-muted);
  border-bottom: 1.5px solid var(--wb-text-muted);
  transform: rotate(-45deg);
  transition: transform 160ms ease;
}

.memory-mission__chevron.is-expanded {
  transform: rotate(45deg) translate(-1px, -1px);
}

.memory-mission__identity {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.memory-mission__eyebrow {
  color: var(--wb-accent);
  font: 9px var(--font-mono, monospace);
  letter-spacing: .1em;
}

.memory-mission__title,
.memory-mission__id {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.memory-mission__title {
  color: var(--wb-text);
  font-size: 12px;
  font-weight: 650;
}

.memory-mission__id {
  color: var(--wb-text-muted);
  font: 10px var(--font-mono, monospace);
}

.memory-mission__count {
  align-self: start;
  margin-top: 2px;
  color: var(--wb-text-muted);
  font: 10px var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.memory-mission__runs {
  list-style: none;
  margin: 0 8px 7px 20px;
  padding: 3px 0 2px 10px;
  border-left: 1px solid color-mix(in srgb, var(--wb-accent) 20%, var(--wb-border-soft));
}

.memory-run {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 54px;
  padding: 8px 9px;
  border: 1px solid transparent;
  border-radius: var(--wb-radius-sm);
  color: inherit;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: var(--transition);
}

.memory-mission__runs .memory-run {
  min-height: 49px;
  padding: 7px 8px;
  border-radius: 6px;
}

.memory-run:hover {
  border-color: var(--wb-border-soft);
  background: var(--wb-hover);
}

.memory-run:focus-visible,
.memory-detail__retry:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 2px;
}

.memory-run.is-active {
  border-color: color-mix(in srgb, var(--wb-accent) 48%, var(--wb-border-soft));
  background: color-mix(in srgb, var(--wb-accent-soft) 58%, var(--wb-surface-section));
  box-shadow: inset 2px 0 0 var(--wb-accent);
}

.memory-run__dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: var(--wb-text-muted);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--wb-text-muted) 10%, transparent);
}

.memory-run__dot[data-status='completed'] { background: var(--wb-success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--wb-success) 12%, transparent); }
.memory-run__dot[data-status='failed'] { background: var(--wb-danger); box-shadow: 0 0 0 3px color-mix(in srgb, var(--wb-danger) 12%, transparent); }
.memory-run__dot[data-status='running'],
.memory-run__dot[data-status='executing'],
.memory-run__dot[data-status='planning'] { background: var(--wb-accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--wb-accent) 12%, transparent); }

.memory-run__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.memory-run__title,
.memory-run__sub {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.memory-run__title {
  display: flex;
  align-items: baseline;
  gap: 8px;
  color: var(--wb-text);
  font-size: 12px;
  font-weight: 520;
}

.memory-run__index {
  color: var(--wb-text-secondary);
  font: 11px var(--font-mono, monospace);
  font-variant-numeric: tabular-nums;
}

.memory-run__status {
  color: var(--wb-text-muted);
  font-size: 10px;
  font-weight: 450;
}

.memory-run__sub {
  color: var(--wb-text-muted);
  font: 10px var(--font-mono, monospace);
}

.memory-detail {
  min-width: 0;
}

.memory-detail__empty {
  padding: 56px 20px;
  border: 1px dashed var(--wb-border);
  border-radius: var(--wb-radius-section);
  color: var(--wb-text-secondary);
  font-size: 13px;
  text-align: center;
}

.memory-detail__empty--error {
  border-style: solid;
  border-color: color-mix(in srgb, var(--wb-danger) 26%, var(--wb-border-soft));
  background: color-mix(in srgb, var(--wb-danger) 5%, var(--wb-surface-section));
}

.memory-detail__empty--error strong {
  display: block;
  color: var(--wb-text);
}

.memory-detail__empty--error p {
  margin: 8px 0 14px;
  color: var(--wb-danger);
}

.memory-loading-state {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 410px;
  overflow: hidden;
  padding: 22px;
  border: 1px solid var(--wb-border-soft);
  border-radius: var(--wb-radius-section);
  background: var(--wb-surface-section);
  box-shadow: var(--wb-shadow-section);
}

.memory-loading-state::before {
  position: absolute;
  top: -120px;
  right: 12%;
  width: 280px;
  height: 220px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--wb-accent) 9%, transparent);
  content: '';
  filter: blur(24px);
  pointer-events: none;
}

.memory-loading-state__intro {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding-bottom: 18px;
  border-bottom: 1px solid var(--wb-border-soft);
}

.memory-loading-state__intro h2 {
  margin: 6px 0 4px;
  color: var(--wb-text);
  font-size: 18px;
  font-weight: 650;
}

.memory-loading-state__intro p {
  margin: 0;
  color: var(--wb-text-secondary);
  font-size: 12px;
}

.memory-loading-state__status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border: 1px solid color-mix(in srgb, var(--wb-accent) 25%, var(--wb-border-soft));
  border-radius: var(--wb-radius-full);
  color: var(--wb-accent);
  background: var(--wb-accent-soft);
  font: 10px var(--font-mono, monospace);
  letter-spacing: .05em;
}

.memory-loading-state__status i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--wb-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--wb-accent) 12%, transparent);
  animation: memory-pulse 1.5s ease-in-out infinite;
}

.memory-loading-state__stats {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  margin: 18px 0;
  border: 1px solid var(--wb-border-soft);
  border-radius: var(--wb-radius-sm);
  background: var(--wb-surface-inset);
}

.memory-loading-stat {
  display: grid;
  gap: 8px;
  padding: 14px 16px;
  border-right: 1px solid var(--wb-border-soft);
}

.memory-loading-stat:nth-child(2) .memory-skeleton-line { animation-delay: 120ms; }
.memory-loading-stat:nth-child(3) .memory-skeleton-line { animation-delay: 240ms; }
.memory-loading-stat:nth-child(4) .memory-skeleton-line { animation-delay: 360ms; }

.memory-loading-stat:last-child { border-right: 0; }

.memory-loading-state__flow {
  position: relative;
  z-index: 1;
  flex: 0 0 220px;
  min-height: 220px;
  overflow: hidden;
  border: 1px solid var(--wb-border-soft);
  border-radius: var(--wb-radius-sm);
  background: color-mix(in srgb, var(--wb-surface-inset) 60%, var(--wb-surface-section));
}

.memory-loading-state__flow::after {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -24%;
  width: 24%;
  background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--wb-accent) 7%, transparent), transparent);
  content: '';
  animation: memory-flow-scan 3.6s ease-in-out infinite;
  pointer-events: none;
}

.memory-loading-state__flow-head {
  display: flex;
  justify-content: space-between;
  padding: 15px 16px;
  border-bottom: 1px solid var(--wb-border-soft);
}

.memory-loading-state__trace {
  position: relative;
  z-index: 1;
  display: flex;
  flex: 1 1 auto;
  flex-direction: column;
  min-height: 180px;
  margin-top: 16px;
  overflow: hidden;
  border: 1px solid var(--wb-border-soft);
  border-radius: var(--wb-radius-sm);
  background: color-mix(in srgb, var(--wb-surface-inset) 48%, var(--wb-surface-section));
}

.memory-loading-state__trace-head {
  display: flex;
  justify-content: space-between;
  padding: 15px 16px;
  border-bottom: 1px solid var(--wb-border-soft);
}

.memory-loading-state__trace-list {
  display: grid;
  flex: 1 1 auto;
  grid-template-rows: repeat(3, minmax(52px, 1fr));
  padding: 2px 16px 10px;
}

.memory-loading-trace {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  border-bottom: 1px solid color-mix(in srgb, var(--wb-border-soft) 72%, transparent);
}

.memory-loading-trace:last-child { border-bottom: 0; }

.memory-loading-trace__dot {
  width: 7px;
  height: 7px;
  flex: none;
  border-radius: 50%;
  background: color-mix(in srgb, var(--wb-accent) 26%, var(--wb-surface-inset));
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--wb-accent) 7%, transparent);
}

.memory-loading-trace__copy {
  display: grid;
  flex: 1;
  gap: 7px;
  min-width: 0;
}

.memory-loading-state__network {
  position: relative;
  height: 164px;
  margin: 0 18px;
}

.memory-loading-state__network::before {
  position: absolute;
  inset: 18px 4% 16px;
  background-image: linear-gradient(color-mix(in srgb, var(--wb-border) 48%, transparent) 1px, transparent 1px), linear-gradient(90deg, color-mix(in srgb, var(--wb-border) 48%, transparent) 1px, transparent 1px);
  background-size: 42px 42px;
  content: '';
  opacity: .34;
  mask-image: linear-gradient(90deg, transparent, #000 12%, #000 88%, transparent);
}

.memory-skeleton-line {
  display: block;
  height: 9px;
  border-radius: 3px;
  background: linear-gradient(90deg, color-mix(in srgb, var(--wb-text-muted) 12%, var(--wb-surface-inset)), color-mix(in srgb, var(--wb-accent) 12%, var(--wb-surface-inset)), color-mix(in srgb, var(--wb-text-muted) 12%, var(--wb-surface-inset)));
  background-size: 220% 100%;
  animation: memory-shimmer 1.7s ease-in-out infinite;
}

.memory-skeleton-line--title { width: 82%; }
.memory-skeleton-line--meta { width: 58%; height: 7px; }
.memory-skeleton-line--number { width: 42px; height: 18px; }
.memory-skeleton-line--label { width: 48px; height: 7px; }
.memory-skeleton-line--flow-title { width: 92px; }
.memory-skeleton-line--flow-meta { width: 64px; height: 7px; }
.memory-skeleton-line--trace-title { width: 108px; }
.memory-skeleton-line--trace-meta { width: 72px; height: 7px; }
.memory-skeleton-line--trace-main { width: min(42%, 280px); }
.memory-skeleton-line--trace-sub { width: min(27%, 180px); height: 7px; }
.memory-skeleton-line--trace-state { width: 54px; height: 7px; flex: none; }

@keyframes memory-shimmer {
  0%, 100% { background-position: 100% 0; opacity: .64; }
  50% { background-position: 0 0; opacity: 1; }
}

@keyframes memory-pulse {
  0%, 100% { opacity: .45; transform: scale(.86); }
  50% { opacity: 1; transform: scale(1); }
}

@keyframes memory-flow-scan {
  0%, 20% { transform: translateX(0); opacity: 0; }
  35% { opacity: 1; }
  80%, 100% { transform: translateX(560%); opacity: 0; }
}

@media (prefers-reduced-motion: reduce) {
  .memory-skeleton-line,
  .memory-loading-state__status i,
  .memory-loading-state__flow::after { animation: none; }
}

.memory-detail__error {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  padding: 10px 13px;
  border: 1px solid color-mix(in srgb, var(--wb-danger) 26%, var(--wb-border-soft));
  border-radius: var(--wb-radius-sm);
  color: var(--wb-danger);
  background: color-mix(in srgb, var(--wb-danger) 8%, var(--wb-surface-section));
  font-size: 12px;
}

.memory-detail__retry {
  margin-left: auto;
  padding: 0;
  border: 0;
  color: var(--wb-accent);
  background: none;
  cursor: pointer;
  font-size: 12px;
}

.memory-detail__intro {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 18px;
  margin-bottom: 12px;
}

.memory-detail__identity h2,
.memory-flow__header h2,
.memory-capsules__header h2,
.memory-steps__heading h2 {
  margin: 2px 0 0;
  color: var(--wb-text);
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.01em;
}

.memory-detail__eyebrow,
.memory-stats__eyebrow,
.memory-flow__eyebrow {
  color: var(--wb-accent);
  font: 9px var(--font-mono, monospace);
  letter-spacing: .12em;
}

.memory-detail__identity code {
  display: block;
  margin-top: 4px;
  overflow: hidden;
  color: var(--wb-text-muted);
  font: 10px var(--font-mono, monospace);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.memory-detail__status {
  flex: none;
  padding: 4px 9px;
  border: 1px solid color-mix(in srgb, var(--wb-accent) 26%, var(--wb-border-soft));
  border-radius: var(--wb-radius-full);
  color: var(--wb-accent);
  background: var(--wb-accent-soft);
  font-size: 11px;
}

.memory-detail__status[data-status='completed'] { color: var(--wb-success); background: var(--success-fade); border-color: color-mix(in srgb, var(--wb-success) 28%, var(--wb-border-soft)); }
.memory-detail__status[data-status='failed'],
.memory-detail__status[data-status='cancelled'] { color: var(--wb-danger); background: var(--danger-fade); border-color: color-mix(in srgb, var(--wb-danger) 28%, var(--wb-border-soft)); }

.memory-stats {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr) auto;
  gap: 16px;
  align-items: stretch;
  margin-bottom: 16px;
  padding: 13px 16px;
}

.memory-stats__label {
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 3px;
  color: var(--wb-text-secondary);
  font-size: 11px;
}

.memory-stats__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(70px, 1fr));
  border-left: 1px solid var(--wb-border-soft);
}

.memory-stat {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 0 16px;
  border-right: 1px solid var(--wb-border-soft);
}

.memory-stat:last-child { border-right: 0; }
.memory-stat strong { color: var(--wb-text); font: 650 22px/1.1 var(--font-mono, monospace); font-variant-numeric: tabular-nums; }
.memory-stat span { color: var(--wb-text-muted); font-size: 10px; }
.memory-stats__loading { align-self: center; color: var(--wb-text-muted); font-size: 10px; white-space: nowrap; }

.memory-flow {
  margin-bottom: 18px;
  padding: 0 0 12px;
  overflow: hidden;
}

.memory-flow__header,
.memory-capsules__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 55px;
  padding: 11px 16px 10px;
  border-bottom: 1px solid var(--wb-border-soft);
}

.memory-flow__count { min-height: 20px; }
.memory-flow__scroll {
  overflow-x: auto;
  margin: 12px 12px 0;
  padding: 3px 0;
  border: 1px solid color-mix(in srgb, var(--wb-accent) 9%, var(--wb-border-soft));
  border-radius: var(--wb-radius-sm);
  background:
    linear-gradient(90deg, color-mix(in srgb, var(--wb-accent) 3%, transparent) 1px, transparent 1px) 0 0 / 148px 100%,
    color-mix(in srgb, var(--wb-surface-inset) 48%, var(--wb-surface-section));
}
.memory-flow__svg { display: block; height: 214px; }
.memory-flow__guides line { stroke: color-mix(in srgb, var(--wb-accent) 14%, var(--wb-border-soft)); stroke-width: 1; stroke-dasharray: 2 7; }
.memory-flow__edge { fill: none; stroke: color-mix(in srgb, var(--wb-accent) 46%, var(--wb-border)); stroke-width: 1.1; opacity: .16; transition: opacity 160ms ease, stroke 160ms ease, stroke-width 160ms ease; }
.memory-flow__edge.is-highlight { stroke: var(--wb-accent); stroke-width: 2.2; opacity: .92; }
.memory-flow__arrow { fill: color-mix(in srgb, var(--wb-accent) 48%, var(--wb-border)); opacity: .4; }
.memory-flow__node { outline: none; }
.memory-flow__halo { fill: color-mix(in srgb, var(--wb-accent-soft) 70%, transparent); opacity: 0; transition: opacity 160ms ease; }
.memory-flow__circle { fill: var(--wb-surface-inset); stroke: color-mix(in srgb, var(--wb-accent) 58%, var(--wb-border)); stroke-width: 1.5; cursor: default; transition: fill 160ms ease, stroke 160ms ease, r 160ms ease; }
.memory-flow__circle.has-write { fill: var(--wb-accent-soft); stroke: var(--wb-accent); }
.memory-flow__write-dot { fill: var(--wb-accent); pointer-events: none; }
.memory-flow__node.is-highlight .memory-flow__halo { opacity: .9; }
.memory-flow__node.is-highlight .memory-flow__circle { stroke-width: 2.6; }
.memory-flow__label { fill: var(--wb-text-secondary); font: 10px var(--font-mono, monospace); text-anchor: middle; paint-order: stroke; stroke: var(--wb-surface-section); stroke-width: 5px; stroke-linejoin: round; }
.memory-flow__legend { margin: 8px 16px 0; color: var(--wb-text-muted); font-size: 10px; }

.memory-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0 0 20px;
  padding: 0;
  list-style: none;
}

.memory-steps__heading {
  display: flex;
  align-items: baseline;
  gap: 9px;
  padding: 0 2px 2px;
}

.memory-step {
  padding: 12px 14px;
  transition: border-color 160ms ease, background-color 160ms ease;
}

.memory-step.is-hover { border-color: color-mix(in srgb, var(--wb-accent) 48%, var(--wb-border-soft)); background: color-mix(in srgb, var(--wb-accent-soft) 18%, var(--wb-surface-section)); }
.memory-step__head { display: flex; align-items: center; gap: 9px; margin-bottom: 8px; }
.memory-step__index { color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); font-variant-numeric: tabular-nums; }
.memory-step__id { min-width: 0; overflow: hidden; color: var(--wb-text); font: 600 12px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.memory-step__mode { margin-left: auto; padding: 2px 7px; border: 1px solid color-mix(in srgb, var(--wb-accent) 22%, var(--wb-border-soft)); border-radius: var(--wb-radius-full); color: var(--wb-accent); background: var(--wb-accent-soft); font: 10px var(--font-mono, monospace); }
.memory-step__mode[data-fallback='true'] { color: var(--wb-warning); background: var(--warning-fade); border-color: color-mix(in srgb, var(--wb-warning) 24%, var(--wb-border-soft)); }
.memory-step__body { display: flex; flex-direction: column; gap: 6px; }
.memory-step__row { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px; color: var(--wb-text-secondary); font-size: 11px; }
.memory-step__tag { flex: none; padding: 2px 7px; border-radius: 4px; font-size: 10px; }
.memory-step__tag--read { color: var(--wb-success); background: var(--success-fade); }
.memory-step__tag--write { color: var(--wb-accent); background: var(--wb-accent-soft); }
.memory-step__summary { color: var(--wb-text-secondary); }
.memory-step__metrics { color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.memory-step__muted { color: var(--wb-text-muted); }
.memory-step__warn { color: var(--wb-warning); font-size: 10px; }

.memory-chip { display: inline-flex; align-items: center; padding: 2px 7px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-full); color: var(--wb-text-secondary); background: var(--wb-surface-inset); font: 10px var(--font-mono, monospace); }
.memory-chip.is-hit { border-color: color-mix(in srgb, var(--wb-success) 42%, var(--wb-border-soft)); color: var(--wb-success); background: var(--success-fade); }

.memory-capsules { margin-bottom: 20px; }
.memory-capsules__header { min-height: 45px; padding: 5px 2px 9px; border-bottom: 0; }
.memory-capsules__header > span { color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.memory-capsule-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 10px; }
.memory-capsule { padding: 12px 13px; }
.memory-capsule__head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 9px; }
.memory-capsule__phase { color: var(--wb-text); font: 600 12px var(--font-mono, monospace); }
.memory-capsule__tokens { color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.memory-capsule__refs { display: flex; flex-wrap: wrap; gap: 6px; }

@media (max-width: 900px) {
  .memory-page__body { grid-template-columns: 1fr; }
  .memory-runs { position: static; max-height: 280px; }
}

@media (max-width: 640px) {
  .memory-page { padding-right: 14px; padding-left: 14px; }
  .memory-stats { grid-template-columns: 1fr; gap: 10px; }
  .memory-stats__grid { border-top: 1px solid var(--wb-border-soft); border-left: 0; padding-top: 10px; }
  .memory-stat { padding: 0 10px; }
  .memory-stat:first-child { padding-left: 0; }
  .memory-stat:last-child { padding-right: 0; }
  .memory-stats__loading { justify-self: end; }
}
</style>
