<template>
  <main class="agentos-console ui-shell">
    <header class="console-header ui-hero ui-hero--compact">
      <div class="console-title">
        <span class="ui-icon-badge"><el-icon><Monitor /></el-icon></span>
        <div>
          <h3 class="ui-hero__title">ACG 历史记录</h3>
        </div>
      </div>
      <button class="console-refresh" type="button" :disabled="listLoading" @click="refreshAll">
        <el-icon><Refresh /></el-icon>
        <span>{{ listLoading ? '同步中' : '刷新' }}</span>
      </button>
    </header>

    <section ref="consoleLayoutRef" class="console-layout" :style="consoleLayoutStyle">
      <aside class="run-sidebar ui-surface ui-surface--pad" aria-label="Workflow 运行列表">
        <div class="filter-panel">
          <div class="filter-title">
            <el-icon><Search /></el-icon>
            <span>运行筛选</span>
          </div>
          <label>
            <span>状态</span>
            <select v-model="filters.status" @change="applyFilters">
              <option value="">默认范围</option>
              <option v-for="item in statusOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
          </label>
          <label>
            <span>Workflow / Task</span>
            <input v-model="filters.query" placeholder="输入稳定 ID" @keyup.enter="applyFilters" />
          </label>
        </div>

        <p v-if="listError" class="sync-warning" role="status">{{ listError }}</p>
        <div class="run-list-head">
          <strong>ACG 运行记录</strong>
          <span>{{ totalRuns }} 条</span>
        </div>

        <div v-if="listLoading && !runs.length" class="empty">正在同步运行索引...</div>
        <div v-else-if="!runs.length" class="empty">当前范围内没有运行记录</div>
        <div v-else class="run-groups">
          <section v-for="group in runGroups" :key="group.key" v-show="group.items.length" class="run-group">
            <header>
              <strong>{{ group.label }}</strong>
              <span>{{ group.items.length }}</span>
            </header>
            <div
              v-for="run in group.items"
              :key="run.runId"
              class="run-item-shell"
              :class="{ active: run.runId === selectedRunId }"
            >
              <button type="button" class="run-item" @click="activateRun(run.runId, true)">
                <span class="run-item__top">
                  <span class="run-status" :class="run.phase || run.status">{{ phaseLabel(run.phase, run.status) }}</span>
                  <time>{{ formatRelativeTime(run.updatedAt) }}</time>
                </span>
                <strong>{{ run.workflowId }}</strong>
                <small :title="run.runId">{{ shortRunId(run.runId) }}</small>
                <p>{{ run.message }}</p>
                <span v-if="run.percent != null" class="run-mini-progress" aria-hidden="true">
                  <span :style="{ width: `${clampPercent(run.percent)}%` }"></span>
                </span>
                <span v-else class="run-mini-progress indeterminate" aria-hidden="true"><span></span></span>
                <span class="run-item__metrics">
                  <span>{{ run.totalSteps > 0 ? `${run.completedSteps}/${run.totalSteps} 步` : '规模计算中' }}</span>
                  <span>恢复 {{ run.recoveryCount }}</span>
                  <span v-if="run.source === 'chat'">来自 Chat</span>
                  <span v-else-if="run.source === 'acg'">来自 ACG</span>
                </span>
              </button>
              <button
                v-if="canDeleteRun(run)"
                class="run-item-delete"
                type="button"
                title="删除运行记录"
                :aria-label="`删除运行：${run.runId}`"
                :disabled="deletingRunId === run.runId"
                @click="deleteRun(run.runId)"
              >
                <el-icon><DeleteIcon /></el-icon>
              </button>
            </div>
          </section>
        </div>

        <footer v-if="totalPages > 1" class="pagination">
          <button type="button" :disabled="filters.page <= 1" @click="changePage(-1)">上一页</button>
          <span>{{ filters.page }} / {{ totalPages }}</span>
          <button type="button" :disabled="filters.page >= totalPages" @click="changePage(1)">下一页</button>
        </footer>
      </aside>

      <div
        class="console-resizer console-resizer--left"
        role="separator"
        aria-label="调整运行列表宽度"
        aria-orientation="vertical"
        :aria-valuenow="leftPanelWidth"
        tabindex="0"
        @pointerdown="startPanelResize('left', $event)"
        @dblclick="resetPanelWidth('left')"
        @keydown="handleResizerKeydown('left', $event)"
      ></div>

      <section class="console-main">
        <div v-if="!selectedRunId" class="selection-empty ui-surface">
          <strong>选择一个 WorkflowRun</strong>
          <p>列表只同步轻量摘要。选中后才会启动该 Run 的实时 Progress。</p>
        </div>

        <template v-else>
          <div class="run-toolbar ui-surface">
            <div>
              <span>当前 Run</span>
              <code :title="selectedRunId">{{ shortRunId(selectedRunId) }}</code>
            </div>
            <nav aria-label="运行页面导航">
              <button type="button" @click="openAcg">进入 ACG</button>
              <button v-if="selectedReference?.conversationId" type="button" @click="openChat">返回 Chat</button>
              <button
                v-if="selectedCanDelete"
                class="run-toolbar__delete"
                type="button"
                :disabled="Boolean(deletingRunId)"
                title="删除当前运行记录"
                @click="deleteRun(selectedRunId)"
              >
                <el-icon><DeleteIcon /></el-icon>
                删除
              </button>
              <button type="button" :disabled="detailLoading" @click="toggleDetails">
                {{ detailExpanded ? '收起详情' : '加载详情' }}
              </button>
            </nav>
          </div>

          <WorkflowProgressBar
            :progress="progressTracker.progress.value"
            :loading="progressTracker.isLoading.value"
            :sync-error="progressTracker.syncError.value"
          />
          <DynamicRunSummaryCard
            :progress="progressTracker.progress.value"
            :run="selectedRun"
            :view="selectedAcgView"
          />

          <p v-if="runError" class="error-message" role="alert">{{ runError }}</p>

          <dl v-if="progressTracker.progress.value" class="run-facts ui-surface">
            <div><dt>Workflow</dt><dd>{{ progressTracker.progress.value.workflowId }}</dd></div>
            <div><dt>当前步骤</dt><dd>{{ progressTracker.progress.value.currentStepId || '准备中' }}</dd></div>
            <div><dt>活动节点</dt><dd>{{ progressTracker.progress.value.activeStepIds.length }}</dd></div>
            <div><dt>恢复次数</dt><dd>{{ progressTracker.progress.value.recoveryCount }}</dd></div>
            <div><dt>开始时间</dt><dd>{{ formatTime(progressTracker.progress.value.startedAt) }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ formatTime(progressTracker.progress.value.updatedAt) }}</dd></div>
          </dl>

          <template v-if="detailExpanded">
            <WorkflowRunPanel
              :run="selectedRun"
              :metrics="null"
              :loading="detailLoading"
              @refresh="refreshSelectedDetail"
              @export-trace="exportTrace"
            />
            <WorkflowStepList
              :steps="selectedRun?.steps || []"
              :current-step-id="selectedRun?.currentStepId"
            />
            <CheckpointPanel
              :checkpoints="checkpoints"
              :loading="detailLoading"
              @resume="resumeFromCheckpoint"
            />
            <TraceEventTimeline
              :events="traceEvents"
              :loading="detailLoading"
              @export-markdown="exportTrace"
            />
          </template>
        </template>
      </section>


      <div
        class="console-resizer console-resizer--right"
        role="separator"
        aria-label="调整摘要面板宽度"
        aria-orientation="vertical"
        :aria-valuenow="rightPanelWidth"
        tabindex="0"
        @pointerdown="startPanelResize('right', $event)"
        @dblclick="resetPanelWidth('right')"
        @keydown="handleResizerKeydown('right', $event)"
      ></div>

      <aside class="console-side">
        <WorkflowReviewPanel
          v-if="selectedRunId"
          :run-id="selectedRunId"
          :progress="progressTracker.progress.value"
          :run="selectedRun"
          :reviews="reviews"
          @reviewed="handleReviewed"
          @conflict="handleReviewConflict"
        />

        <section class="acg-summary ui-surface ui-surface--pad">
          <header><strong>ACG 摘要</strong><span>{{ selectedAcgView ? '已加载' : '按需加载' }}</span></header>
          <div v-if="selectedAcgView" class="acg-summary__facts">
            <span>节点 {{ selectedAcgView.stepStates.length }}</span>
            <span>交付物 {{ selectedAcgView.deliverables.length }}</span>
            <span>恢复 {{ selectedAcgView.lowEntropyMetrics.recoveryCount }}</span>
          </div>
          <p v-else>终态、人工审核或展开详情时才读取完整 ACG，不参与列表轮询。</p>
        </section>
        <RuntimeChangeTimeline
          v-if="selectedAcgView"
          :runtime-events="selectedAcgView.runtimeEvents"
          :applied-patches="selectedAcgView.appliedPatches"
          :branch-decisions="selectedAcgView.branchDecisions"
          :step-states="selectedAcgView.stepStates"
        />
      </aside>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import axios from 'axios'
import { Delete as DeleteIcon, Monitor, Refresh, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import CheckpointPanel from '@/components/agentos/CheckpointPanel.vue'
import TraceEventTimeline from '@/components/agentos/TraceEventTimeline.vue'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import DynamicRunSummaryCard from '@/components/agentos/DynamicRunSummaryCard.vue'
import RuntimeChangeTimeline from '@/components/agentos/RuntimeChangeTimeline.vue'
import WorkflowReviewPanel from '@/components/agentos/WorkflowReviewPanel.vue'
import WorkflowRunPanel from '@/components/agentos/WorkflowRunPanel.vue'
import WorkflowStepList from '@/components/agentos/WorkflowStepList.vue'
import { useWorkflowProgress } from '@/composables/useWorkflowProgress'
import {
  workflowApi,
  type AcgView,
  type Checkpoint,
  type ReviewRecord,
  type TraceEvent,
  type WorkflowProgress,
  type WorkflowRun,
  type WorkflowRunSummary,
  type WorkflowStatus
} from '@/services/api/workflow'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { isWorkflowReviewPending } from '@/utils/workflowReviewState'
import { runtimeProjectionChanged } from '@/utils/runtimePresentation'

const DEFAULT_STATUSES = ['pending', 'planning', 'running', 'retrying', 'waiting_review', 'completed', 'failed', 'cancelled']
const TERMINAL = new Set(['completed', 'failed', 'cancelled'])
const LIST_INTERVAL_MS = 7000
const PAGE_SIZE = 50
const CONSOLE_LEFT_WIDTH_KEY = 'agentos.console.left_width'
const CONSOLE_RIGHT_WIDTH_KEY = 'agentos.console.right_width'
const DEFAULT_LEFT_WIDTH = 320
const DEFAULT_RIGHT_WIDTH = 340
const MIN_LEFT_WIDTH = 240
const MAX_LEFT_WIDTH = 420
const MIN_RIGHT_WIDTH = 260
const MAX_RIGHT_WIDTH = 460
const MIN_MAIN_WIDTH = 360

const route = useRoute()
const router = useRouter()
const workflowRunsStore = useWorkflowRunsStore()
const runs = ref<WorkflowRunSummary[]>([])
const totalRuns = ref(0)
const selectedRunId = ref('')
const selectedRun = ref<WorkflowRun | null>(null)
const selectedAcgView = ref<AcgView | null>(null)
const traceEvents = ref<TraceEvent[]>([])
const checkpoints = ref<Checkpoint[]>([])
const reviews = ref<ReviewRecord[]>([])
const consoleLayoutRef = ref<HTMLElement | null>(null)
const leftPanelWidth = ref(Number(localStorage.getItem(CONSOLE_LEFT_WIDTH_KEY)) || DEFAULT_LEFT_WIDTH)
const rightPanelWidth = ref(Number(localStorage.getItem(CONSOLE_RIGHT_WIDTH_KEY)) || DEFAULT_RIGHT_WIDTH)
const listLoading = ref(false)
const detailLoading = ref(false)
const detailExpanded = ref(false)
const deletingRunId = ref('')
const listError = ref('')
const runError = ref('')
const consoleLayoutStyle = computed(() => ({
  '--console-left-width': `${leftPanelWidth.value}px`,
  '--console-right-width': `${rightPanelWidth.value}px`
}))

let stopPanelResize: (() => void) | null = null
const clampPanelWidth = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value))

const availablePanelWidth = (side: 'left' | 'right') => {
  const total = consoleLayoutRef.value?.clientWidth || window.innerWidth
  const opposite = side === 'left' ? rightPanelWidth.value : leftPanelWidth.value
  return Math.max(0, total - opposite - MIN_MAIN_WIDTH - 10)
}

const setPanelWidth = (side: 'left' | 'right', value: number) => {
  if (side === 'left') {
    leftPanelWidth.value = clampPanelWidth(value, MIN_LEFT_WIDTH, Math.min(MAX_LEFT_WIDTH, availablePanelWidth(side)))
    return
  }
  rightPanelWidth.value = clampPanelWidth(value, MIN_RIGHT_WIDTH, Math.min(MAX_RIGHT_WIDTH, availablePanelWidth(side)))
}

const persistPanelWidths = () => {
  localStorage.setItem(CONSOLE_LEFT_WIDTH_KEY, String(Math.round(leftPanelWidth.value)))
  localStorage.setItem(CONSOLE_RIGHT_WIDTH_KEY, String(Math.round(rightPanelWidth.value)))
}

const startPanelResize = (side: 'left' | 'right', event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  stopPanelResize?.()
  const startX = event.clientX
  const startWidth = side === 'left' ? leftPanelWidth.value : rightPanelWidth.value
  document.body.classList.add('console-panel-resizing')

  const move = (moveEvent: PointerEvent) => {
    const delta = moveEvent.clientX - startX
    setPanelWidth(side, startWidth + (side === 'left' ? delta : -delta))
  }
  const stop = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', stop)
    document.body.classList.remove('console-panel-resizing')
    persistPanelWidths()
    stopPanelResize = null
  }
  stopPanelResize = stop
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', stop, { once: true })
}

const resetPanelWidth = (side: 'left' | 'right') => {
  setPanelWidth(side, side === 'left' ? DEFAULT_LEFT_WIDTH : DEFAULT_RIGHT_WIDTH)
  persistPanelWidths()
}

const handleResizerKeydown = (side: 'left' | 'right', event: KeyboardEvent) => {
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return
  event.preventDefault()
  const current = side === 'left' ? leftPanelWidth.value : rightPanelWidth.value
  const direction = event.key === 'ArrowRight' ? 1 : -1
  setPanelWidth(side, current + direction * (side === 'left' ? 12 : -12))
  persistPanelWidths()
}
const terminalDetailsLoaded = new Set<string>()
const reviewDetailsLoaded = new Set<string>()
const terminalDetailCache = new Map<string, { run: WorkflowRun; acg: AcgView }>()

const filters = reactive({ status: '' as WorkflowStatus | '', query: '', page: 1 })
let listTimer: ReturnType<typeof setTimeout> | null = null
let listController: AbortController | null = null
let listGeneration = 0
let detailController: AbortController | null = null
let detailGeneration = 0

const progressTracker = useWorkflowProgress({
  intervalMs: 2000,
  onProgressChanged: handleProgressChanged,
  onTerminal: handleTerminal
})

const statusOptions = [
  { value: 'pending', label: '等待中' },
  { value: 'running', label: '运行中' },
  { value: 'waiting_review', label: '待审核' },
  { value: 'retrying', label: '恢复中' },
  { value: 'completed', label: '已完成' },
  { value: 'failed', label: '失败' },
  { value: 'cancelled', label: '已取消' }
]

const runGroups = computed(() => [
  {
    key: 'review', label: '需要处理',
    items: runs.value.filter(run => isWorkflowReviewPending(run))
  },
  {
    key: 'running', label: '正在运行',
    items: runs.value.filter(run => !TERMINAL.has(run.status) && !isWorkflowReviewPending(run))
  },
  {
    key: 'terminal', label: '最近结束',
    items: runs.value.filter(run => TERMINAL.has(run.status)).slice(0, 12)
  }
])
const totalPages = computed(() => Math.max(1, Math.ceil(totalRuns.value / PAGE_SIZE)))
const selectedReference = computed(() => workflowRunsStore.getReference(selectedRunId.value))
const selectedSummary = computed(() => runs.value.find(run => run.runId === selectedRunId.value))
const selectedCanDelete = computed(() => {
  const status = selectedSummary.value?.status || progressTracker.progress.value?.status || selectedRun.value?.status
  return Boolean(status && TERMINAL.has(status))
})

const canDeleteRun = (run: WorkflowRunSummary) => TERMINAL.has(run.status)

const listParams = () => {
  const query = filters.query.trim()
  return {
    status: filters.status,
    statuses: filters.status ? undefined : DEFAULT_STATUSES.join(','),
    workflowId: query.startsWith('task_') ? undefined : query || undefined,
    taskId: query.startsWith('task_') ? query : undefined,
    summary: true,
    page: filters.page,
    pageSize: PAGE_SIZE
  }
}

const clearListTimer = () => {
  if (listTimer) window.clearTimeout(listTimer)
  listTimer = null
}

const scheduleListRefresh = () => {
  clearListTimer()
  if (document.visibilityState === 'hidden') return
  listTimer = window.setTimeout(() => void loadRuns(false), LIST_INTERVAL_MS)
}

const loadRuns = async (force = false) => {
  if (listLoading.value && !force) return
  const generation = ++listGeneration
  listController?.abort()
  listController = new AbortController()
  listLoading.value = true
  try {
    const page = await workflowApi.listRuns(listParams(), { signal: listController.signal })
    if (generation !== listGeneration) return
    runs.value = page.items || []
    totalRuns.value = page.total || 0
    workflowRunsStore.mergeSummaries(runs.value)
    listError.value = ''
  } catch (error: unknown) {
    if (!axios.isCancel(error) && generation === listGeneration) {
      listError.value = '运行列表同步暂时中断，保留上次成功结果'
    }
  } finally {
    if (generation === listGeneration) {
      listController = null
      listLoading.value = false
      scheduleListRefresh()
    }
  }
}

const applyFilters = () => {
  filters.page = 1
  void loadRuns(true)
}
const changePage = (offset: number) => {
  filters.page = Math.min(totalPages.value, Math.max(1, filters.page + offset))
  void loadRuns(true)
}

const clearSelectedDetails = () => {
  detailGeneration += 1
  detailController?.abort()
  detailController = null
  selectedRun.value = null
  selectedAcgView.value = null
  traceEvents.value = []
  checkpoints.value = []
  reviews.value = []
  detailExpanded.value = false
  detailLoading.value = false
  runError.value = ''
}

const removeMissingRun = async (runId: string) => {
  const existed = Boolean(workflowRunsStore.getReference(runId)) || runs.value.some(run => run.runId === runId)
  workflowRunsStore.removeReference(runId)
  runs.value = runs.value.filter(run => run.runId !== runId)
  if (existed) totalRuns.value = Math.max(0, totalRuns.value - 1)
  if (selectedRunId.value === runId) {
    progressTracker.reset()
    clearSelectedDetails()
    selectedRunId.value = ''
    const query = { ...route.query }
    delete query.runId
    await router.replace({ query })
  }
  if (existed) ElMessage.warning('该运行记录已不存在。')
}

const activateRun = async (runId: string, syncRoute: boolean) => {
  if (!runId || (runId === selectedRunId.value && progressTracker.runId.value === runId)) return
  progressTracker.reset()
  clearSelectedDetails()
  selectedRunId.value = runId
  const cachedTerminal = terminalDetailCache.get(runId)
  if (cachedTerminal) {
    selectedRun.value = cachedTerminal.run
    selectedAcgView.value = cachedTerminal.acg
  }
  const summary = runs.value.find(item => item.runId === runId)
  workflowRunsStore.register({
    runId,
    taskId: summary?.taskId,
    workflowId: summary?.workflowId,
    source: 'console',
    status: summary?.status,
    phase: summary?.phase,
    createdAt: summary?.createdAt || undefined,
    updatedAt: summary?.updatedAt || undefined
  })
  if (syncRoute && route.query.runId !== runId) {
    await router.replace({ query: { ...route.query, runId } })
  }
  void progressTracker.start(runId, { fresh: false })
  if (isWorkflowReviewPending(summary)) void loadSelectedDetail({ review: true })
  if (TERMINAL.has(summary?.status || '') && !cachedTerminal) void loadSelectedDetail({ acg: true })
}

const loadSelectedDetail = async (options: { full?: boolean; acg?: boolean; review?: boolean } = {}) => {
  const runId = selectedRunId.value
  if (!runId) return
  const generation = ++detailGeneration
  detailController?.abort()
  detailController = new AbortController()
  const signal = detailController.signal
  detailLoading.value = true
  try {
    const runPromise = workflowApi.getRun(runId, { signal })
    const acgPromise = options.acg || options.full ? workflowApi.getAcgView(runId, { signal }) : Promise.resolve(null)
    const reviewsPromise = options.review || options.full
      ? workflowApi.listReviews(runId, { signal })
      : Promise.resolve({ items: [] as ReviewRecord[], total: 0, runId })
    const tracePromise = options.full
      ? workflowApi.getTrace(runId, { signal })
      : Promise.resolve({ runId, taskId: '', workflowId: '', domain: '', status: 'pending' as WorkflowStatus, eventCount: 0, events: [] })
    const checkpointsPromise = options.full
      ? workflowApi.listCheckpoints(runId, { signal })
      : Promise.resolve({ items: [] as Checkpoint[], total: 0, runId })
    const [run, acg, reviewPage, trace, checkpointPage] = await Promise.all([
      runPromise, acgPromise, reviewsPromise, tracePromise, checkpointsPromise
    ])
    if (generation !== detailGeneration || runId !== selectedRunId.value) return
    selectedRun.value = run
    if (acg) selectedAcgView.value = acg
    if (acg && TERMINAL.has(run.status)) terminalDetailCache.set(runId, { run, acg })
    if (options.review || options.full) {
      reviews.value = reviewPage.items || []
      reviewDetailsLoaded.add(runId)
    }
    if (options.full) {
      traceEvents.value = trace.events || []
      checkpoints.value = checkpointPage.items || []
    }
    runError.value = ''
  } catch (error: unknown) {
    if (axios.isCancel(error) || generation !== detailGeneration) return
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      await removeMissingRun(runId)
      runError.value = ''
    } else {
      runError.value = '运行详情暂时无法加载'
    }
    if (options.review || options.full) reviewDetailsLoaded.delete(runId)
  } finally {
    if (generation === detailGeneration) {
      detailController = null
      detailLoading.value = false
    }
  }
}

function handleProgressChanged(current: WorkflowProgress, previous: WorkflowProgress | null) {
  if (current.runId !== selectedRunId.value) return
  workflowRunsStore.updateObservedState(current.runId, current.status, current.phase, current.updatedAt)
  const index = runs.value.findIndex(item => item.runId === current.runId)
  if (index >= 0) runs.value[index] = { ...runs.value[index], ...current }
  if (runtimeProjectionChanged(current, previous) && !TERMINAL.has(current.status)) {
    void loadSelectedDetail({ acg: true })
  }
  if (isWorkflowReviewPending(current) && !isWorkflowReviewPending(previous) && !reviewDetailsLoaded.has(current.runId)) {
    void loadSelectedDetail({ review: true })
  }
}

async function handleTerminal(progress: WorkflowProgress) {
  if (progress.runId !== selectedRunId.value || terminalDetailsLoaded.has(progress.runId)) return
  terminalDetailsLoaded.add(progress.runId)
  await loadSelectedDetail({ acg: true })
  await loadRuns(true)
}

const toggleDetails = async () => {
  detailExpanded.value = !detailExpanded.value
  if (detailExpanded.value) await loadSelectedDetail({ full: true, acg: true, review: true })
}
const refreshSelectedDetail = async () => {
  await progressTracker.refresh()
  await loadSelectedDetail({ full: detailExpanded.value, acg: detailExpanded.value, review: true })
}
const handleReviewed = async (run: WorkflowRun) => {
  if (run.runId !== selectedRunId.value) return
  selectedRun.value = run
  await progressTracker.refresh()
  await Promise.all([loadRuns(true), loadSelectedDetail({ review: true })])
}
const handleReviewConflict = async () => {
  await progressTracker.refresh()
  await loadSelectedDetail({ review: true })
}

const resumeFromCheckpoint = async (checkpointId: string) => {
  if (!selectedRunId.value || detailLoading.value) return
  detailLoading.value = true
  try {
    await workflowApi.resumeFromCheckpoint(selectedRunId.value, checkpointId)
    await progressTracker.refresh()
    await loadSelectedDetail({ full: true, acg: true, review: true })
  } catch {
    runError.value = '恢复请求未能完成'
  } finally {
    detailLoading.value = false
  }
}

const exportTrace = async () => {
  if (!selectedRunId.value) return
  const markdown = await workflowApi.exportTraceMarkdown(selectedRunId.value)
  const url = URL.createObjectURL(new Blob([markdown], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `agentos-trace-${selectedRunId.value}.md`
  link.click()
  URL.revokeObjectURL(url)
}

const refreshAll = async () => {
  await loadRuns(true)
  if (selectedRunId.value) await progressTracker.refresh()
}
const deleteRun = async (runId: string) => {
  const summary = runs.value.find(run => run.runId === runId)
  if (summary && !canDeleteRun(summary)) {
    ElMessage.warning('运行中的任务需先取消后才能删除')
    return
  }
  try {
    await ElMessageBox.confirm(
      '该操作将永久删除本次运行的步骤、动态历史和执行结果，无法恢复。',
      '删除运行记录？',
      {
        confirmButtonText: '永久删除',
        cancelButtonText: '取消',
        type: 'warning',
        distinguishCancelAndClose: true
      }
    )
    deletingRunId.value = runId
    const wasSelected = selectedRunId.value === runId
    const nextRunId = runs.value.find(run => run.runId !== runId)?.runId || ''
    await workflowApi.deleteRun(runId)
    terminalDetailsLoaded.delete(runId)
    reviewDetailsLoaded.delete(runId)
    terminalDetailCache.delete(runId)
    workflowRunsStore.removeReference(runId)
    runs.value = runs.value.filter(run => run.runId !== runId)
    totalRuns.value = Math.max(0, totalRuns.value - 1)
    if (wasSelected) {
      progressTracker.reset()
      clearSelectedDetails()
      selectedRunId.value = ''
      const query = { ...route.query }
      delete query.runId
      await router.replace({ query })
      if (nextRunId) await activateRun(nextRunId, true)
    }
    window.dispatchEvent(new Event('acg-runs-refresh'))
    ElMessage.success('ACG 运行记录已删除')
    await loadRuns(true)
  } catch (error: unknown) {
    if (error === 'cancel' || error === 'close') return
    const data = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data
    ElMessage.error(data?.message || data?.detail || '删除失败，请稍后重试')
  } finally {
    deletingRunId.value = ''
  }
}
const openAcg = () => void router.push({ path: '/agentos/acg', query: { runId: selectedRunId.value } })
const openChat = () => {
  const conversationId = selectedReference.value?.conversationId
  if (!conversationId) return
  void router.push({ path: '/chat', query: { workspace: 'agent', contextId: conversationId, runId: selectedRunId.value } })
}

const handleVisibility = () => {
  if (document.visibilityState === 'hidden') clearListTimer()
  else void loadRuns(true)
}

watch(
  () => route.query.runId,
  runId => {
    const value = typeof runId === 'string' ? runId.trim() : ''
    if (value && value !== selectedRunId.value) void activateRun(value, false)
  },
  { immediate: true }
)

watch(() => progressTracker.syncError.value, error => {
  if (error === '该运行记录不存在或当前账户无权访问' && selectedRunId.value) {
    void removeMissingRun(selectedRunId.value)
  }
})

onMounted(() => {
  document.addEventListener('visibilitychange', handleVisibility)
  void loadRuns(true)
})

onBeforeUnmount(() => {
  stopPanelResize?.()
  document.removeEventListener('visibilitychange', handleVisibility)
  clearListTimer()
  listGeneration += 1
  listController?.abort()
  detailGeneration += 1
  detailController?.abort()
  progressTracker.reset()
})

const phaseLabel = (phase: string, status: string) => ({
  understanding: '理解任务', planning: '规划任务', graph_building: '构建 ACG', executing: '执行节点',
  recovery: '恢复执行', review: '等待审核', completed: '执行完成', failed: '执行失败', cancelled: '已取消'
}[phase] || ({ pending: '等待中', running: '运行中', retrying: '恢复中', waiting_review: '等待审核' }[status] || status))
const shortRunId = (value: string) => value.length > 22 ? `${value.slice(0, 11)}...${value.slice(-7)}` : value
const clampPercent = (value: number) => Math.min(100, Math.max(0, value))
const formatTime = (value?: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '准备中'
const formatRelativeTime = (value?: string | null) => value ? new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''
</script>

<style scoped>
.agentos-console { height: 100%; min-height: 0; padding: 0; gap: 0; color: var(--text-primary); overflow: hidden; }
.console-header { z-index: 1; flex: 0 0 50px; min-height: 50px; border-width: 0 0 1px; border-radius: 0; box-shadow: none; }
.console-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
.console-refresh,
.run-toolbar button,
.pagination button {
  min-height: 34px; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 0 12px; border: 1px solid var(--border-light); border-radius: 7px;
  background: var(--surface-solid); color: var(--text-primary); cursor: pointer; transition: var(--transition);
}
.console-refresh:hover:not(:disabled), .run-toolbar button:hover:not(:disabled), .pagination button:hover:not(:disabled) { border-color: var(--primary-line); color: var(--primary-color); }
button:disabled { cursor: not-allowed; opacity: 0.55; }
.console-layout { display: grid; grid-template-columns: var(--console-left-width) 5px minmax(360px, 1fr) 5px var(--console-right-width); align-items: stretch; gap: 0; flex: 1 1 auto; height: auto; min-height: 0; overflow: hidden; border: 0; border-radius: 0; background: var(--bg-card); }
.run-sidebar, .console-main, .console-side { min-width: 0; min-height: 0; height: 100%; }
.run-sidebar, .console-main, .console-side { overflow-y: auto; scrollbar-gutter: stable; }
.run-sidebar { padding: 12px; border: 0; border-radius: 0; box-shadow: none; }
.console-main, .console-side { display: flex; flex-direction: column; gap: 0; background: var(--bg-card); }
.console-main { border-left: 1px solid var(--border-light); border-right: 1px solid var(--border-light); }
.console-main > .ui-surface,
.console-main > :deep(.ui-surface),
.console-side > .ui-surface,
.console-side > :deep(.ui-surface) { border-width: 0 0 1px; border-radius: 0; box-shadow: none; }
.console-side { padding: 0; }
.console-resizer { position: relative; z-index: 3; width: 5px; min-width: 5px; cursor: col-resize; background: var(--bg-panel); outline: none; touch-action: none; }
.console-resizer::after { content: ''; position: absolute; inset: 0 1px; background: transparent; transition: background-color 120ms ease; }
.console-resizer:hover::after,
.console-resizer:focus-visible::after { background: var(--primary-color); }
.acg-summary { box-sizing: border-box; min-height: 84px; max-height: 280px; resize: vertical; overflow: auto; }
.console-main > * { flex-shrink: 0; }
.console-main > .selection-empty:last-child,
.console-main > .run-facts:last-child,
.console-main > :deep(.trace-event-timeline:last-child),
.console-side > .acg-summary:last-child { flex: 1 0 auto; min-height: 0; }
.console-main > :deep(.trace-event-timeline:last-child) { min-height: 260px; }
.filter-panel { display: grid; gap: 10px; }
.filter-title, .run-list-head, .run-group > header, .run-item__top, .run-item__metrics, .run-toolbar, .run-toolbar nav, .acg-summary header, .acg-summary__facts, .pagination { display: flex; align-items: center; }
.filter-title { gap: 7px; font-size: 14px; font-weight: 700; }
label { display: grid; gap: 5px; }
label > span { color: var(--text-secondary); font-size: 12px; font-weight: 650; }
select, input { width: 100%; height: 34px; padding: 0 9px; border: 1px solid transparent; border-radius: 7px; background: var(--bg-input); color: var(--text-primary); outline: none; }
select:focus, input:focus { border-color: var(--primary-line); box-shadow: 0 0 0 3px var(--primary-fade); }
.sync-warning, .error-message { margin: 0; padding: 8px 10px; border-radius: 6px; font-size: 12px; overflow-wrap: anywhere; }
.sync-warning { background: var(--warning-fade); color: var(--warning); }
.error-message { background: var(--danger-fade); color: var(--danger); }
.run-list-head { justify-content: space-between; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-light); font-size: 13px; }
.run-list-head span, .empty { color: var(--text-secondary); font-size: 12px; }
.empty { padding: 14px 0; }
.run-groups { display: grid; gap: 14px; margin-top: 10px; }
.run-group { display: grid; gap: 7px; }
.run-group > header { justify-content: space-between; color: var(--text-secondary); font-size: 11px; text-transform: uppercase; }
.run-item-shell { position: relative; border-radius: 7px; }
.run-item { display: grid; gap: 5px; width: 100%; padding: 10px; border: 1px solid var(--border-light); border-radius: inherit; background: color-mix(in srgb, var(--bg-card) 76%, transparent); color: var(--text-primary); text-align: left; cursor: pointer; transition: var(--transition); }
.run-item:hover { border-color: var(--border-hover); }
.run-item-shell.active .run-item { border-color: var(--primary-line); background: var(--surface-solid); box-shadow: inset 2px 0 var(--primary-color); }
.run-item-delete { position: absolute; top: 7px; right: 7px; display: inline-grid; place-items: center; width: 24px; height: 24px; padding: 0; border: 0; border-radius: 6px; background: color-mix(in srgb, var(--bg-card) 90%, transparent); color: var(--text-disabled); cursor: pointer; opacity: 0; transition: var(--transition); }
.run-item-shell:hover .run-item-delete, .run-item-shell.active .run-item-delete, .run-item-delete:focus-visible { opacity: 1; }
.run-item-delete:hover { background: var(--danger-fade); color: var(--danger); }
.run-item-delete:disabled { cursor: wait; opacity: .55; }
.run-toolbar__delete { color: var(--danger) !important; }
.run-toolbar__delete:hover:not(:disabled) { border-color: color-mix(in srgb, var(--danger) 38%, var(--border-light)) !important; background: var(--danger-fade) !important; }
.run-item__top { justify-content: space-between; gap: 8px; padding-right: 30px; }
.run-item__top time, .run-item small, .run-item p, .run-item__metrics { color: var(--text-secondary); font-size: 11px; }
.run-item strong, .run-item small, .run-item p { overflow-wrap: anywhere; }
.run-item p { margin: 0; line-height: 1.4; }
.run-status { padding: 2px 6px; border-radius: 999px; background: var(--bg-input); color: var(--info); font-size: 10px; font-weight: 750; }
.run-status.review, .run-status.recovery { color: var(--warning); }
.run-status.completed { color: var(--success); }
.run-status.failed { color: var(--danger); }
.run-status.cancelled { color: var(--text-muted); }
.run-mini-progress { position: relative; height: 3px; overflow: hidden; border-radius: 2px; background: var(--bg-input); }
.run-mini-progress > span { display: block; height: 100%; background: var(--primary-color); }
.run-mini-progress.indeterminate > span { width: 38%; animation: list-progress 1.5s ease-in-out infinite; }
.run-item__metrics { gap: 9px; flex-wrap: wrap; }
.pagination { justify-content: center; gap: 9px; margin-top: 12px; }
.pagination button { min-height: 30px; padding: 0 9px; }
.pagination span { color: var(--text-secondary); font-size: 12px; }
.selection-empty { display: grid; place-content: center; min-height: 260px; padding: 24px; text-align: center; }
.selection-empty p { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; }
.run-toolbar { justify-content: space-between; gap: 12px; padding: 10px 12px; }
.run-toolbar > div { display: grid; gap: 2px; min-width: 0; }
.run-toolbar > div span { color: var(--text-secondary); font-size: 11px; }
.run-toolbar code { overflow-wrap: anywhere; font-size: 12px; }
.run-toolbar nav { justify-content: flex-end; gap: 7px; flex-wrap: wrap; }
.run-facts { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); align-content: start; grid-auto-rows: max-content; gap: 1px; overflow: hidden; }
.run-facts > div { min-width: 0; padding: 11px 12px; background: var(--bg-card); }
.run-facts dt { color: var(--text-secondary); font-size: 11px; }
.run-facts dd { margin: 4px 0 0; overflow-wrap: anywhere; font-size: 12px; font-weight: 650; }
.acg-summary { display: grid; align-content: start; gap: 10px; }
.acg-summary header { justify-content: space-between; gap: 8px; }
.acg-summary header span, .acg-summary p { color: var(--text-secondary); font-size: 12px; }
.acg-summary p { margin: 0; line-height: 1.55; }
.acg-summary__facts { gap: 8px; flex-wrap: wrap; }
.acg-summary__facts span { padding: 4px 7px; border-radius: 5px; background: var(--bg-input); font-size: 11px; }
@keyframes list-progress { 0% { transform: translateX(-110%); } 100% { transform: translateX(270%); } }
@media (prefers-reduced-motion: reduce) { .run-mini-progress.indeterminate > span { animation: none; transform: translateX(80%); } }
@media (max-width: 1180px) { .agentos-console { height: auto; min-height: 100%; overflow: visible; } .console-layout { grid-template-columns: minmax(260px, 320px) minmax(0, 1fr); flex: none; height: auto; overflow: visible; } .console-resizer { display: none; } .run-sidebar, .console-main, .console-side { height: auto; } .console-side { grid-column: 2; } .run-sidebar { max-height: 720px; } }
@media (max-width: 760px) { .agentos-console { padding: 0; } .console-header { align-items: flex-start; flex-direction: column; flex-basis: auto; } .console-layout { grid-template-columns: 1fr; } .console-side { grid-column: 1; } .run-sidebar { max-height: none; } .run-facts { grid-template-columns: repeat(2, minmax(0, 1fr)); } .run-toolbar { align-items: flex-start; flex-direction: column; } .run-toolbar nav { justify-content: flex-start; } }
</style>
