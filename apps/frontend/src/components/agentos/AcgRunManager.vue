<template>
  <div class="acg-run-manager">
    <header class="acg-explorer-header">
      <button class="acg-new-run" type="button" title="新建 ACG 任务" aria-label="新建 ACG 任务" @click="emit('new')">
        <el-icon><Plus /></el-icon>
        <span>新建 ACG 任务</span>
      </button>
    </header>

    <div class="acg-run-tools">
      <label class="acg-run-search">
        <el-icon><Search /></el-icon>
        <input v-model.trim="searchKeyword" type="search" placeholder="搜索任务 ID / 任务名称" />
      </label>
      <select v-model="statusFilter" class="acg-run-filter" aria-label="筛选运行状态">
        <option value="all">全部</option>
        <option value="active">运行中</option>
        <option value="review">待审核</option>
        <option value="failed">需处理</option>
        <option value="completed">已完成</option>
      </select>
      <span v-if="refreshing && runs.length" class="acg-run-refreshing">更新中</span>
    </div>

    <div v-if="loading && !runs.length" class="acg-run-message">正在加载运行记录…</div>
    <div v-else-if="loadError && !runs.length" class="acg-run-message acg-run-message--error">
      <span>{{ loadError }}</span>
      <button type="button" @click="loadRuns()">重试</button>
    </div>
    <div v-else-if="!visibleGroups.length" class="acg-run-message">暂无匹配的 ACG 运行</div>

    <div v-else class="acg-run-groups" role="list" aria-label="ACG 运行记录">
      <section v-for="group in visibleGroups" :key="group.key" class="acg-run-group">
        <header class="acg-run-group__head">
          <span>{{ group.label }}</span>
          <span>{{ group.items.length }}</span>
        </header>
        <div
          v-for="run in group.items"
          :key="run.runId"
          class="acg-run-item"
          :class="[`status-${group.key}`, { active: run.runId === activeRunId, selected: run.runId === selectedRunId }]"
          @focusin="selectedRunId = run.runId"
        >
          <button
            class="acg-run-item__select"
            type="button"
            :title="`${displayTitle(run)}\n${missionIdentity(run)}`"
            @click="selectRun(run.runId)"
          >
            <span
              class="acg-run-item__status"
              role="img"
              :aria-label="`${group.label}：${phaseLabel(run)}`"
              :title="`${group.label}：${phaseLabel(run)}`"
            ></span>
            <span class="acg-run-item__body">
              <span class="acg-run-item__headline">
                <strong>{{ displayTitle(run) }}</strong>
              </span>
              <span class="acg-run-item__meta">
                <span class="acg-run-item__phase">
                  {{ phaseLabel(run) }}<template v-if="run.totalSteps"> · 步骤 {{ run.completedSteps }}/{{ run.totalSteps }}</template>
                </span>
                <time
                  v-if="runActivityTime(run)"
                  :datetime="runActivityTime(run)"
                  :title="formatFullRunTime(runActivityTime(run))"
                >{{ runTimeLabel(run) }} {{ formatRunTime(runActivityTime(run)) }}</time>
              </span>
              <span v-if="showProgress(run)" class="acg-run-item__progress" aria-hidden="true">
                <span :style="{ width: `${safePercentage(run)}%` }"></span>
              </span>
            </span>
          </button>
          <button
            class="acg-run-item__actions"
            type="button"
            :tabindex="run.runId === activeRunId || run.runId === selectedRunId ? 0 : -1"
            aria-haspopup="menu"
            aria-controls="acg-run-action-menu"
            :aria-expanded="actionMenu.run?.runId === run.runId"
            :aria-label="`打开${displayTitle(run)}的任务操作`"
            @click.stop="openActionMenu($event, run)"
          >
            <el-icon><MoreFilled /></el-icon>
          </button>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="actionMenu.run" id="acg-run-action-menu" ref="actionMenuElement" class="acg-run-action-menu" role="menu" :style="{ left: `${actionMenu.x}px`, top: `${actionMenu.y}px` }">
        <button type="button" role="menuitem" @click="selectActionRun"><el-icon><View /></el-icon><span>打开任务</span></button>
        <button type="button" role="menuitem" @click="copyActionMissionId"><el-icon><CopyDocument /></el-icon><span>复制任务 ID</span></button>
        <div class="acg-run-action-menu__separator"></div>
        <button type="button" role="menuitem" :disabled="!isTerminalMission(actionMenu.run)" @click="archiveActionMission"><el-icon><FolderAdd /></el-icon><span>归档任务</span></button>
        <button class="is-danger" type="button" role="menuitem" :disabled="!isTerminalMission(actionMenu.run)" @click="deleteActionMission"><el-icon><DeleteIcon /></el-icon><span>删除任务</span></button>
      </div>
    </Teleport>


    <button class="acg-run-manage" type="button" @click="emit('manage')">
      <span class="acg-run-manage__icon"><el-icon><Clock /></el-icon></span>
      <span>
        <strong>查看运行历史记录</strong>
        <small>包含已归档任务 · 搜索与审计</small>
      </span>
      <el-icon><ArrowRight /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, reactive, ref } from 'vue'
import { ArrowRight, Clock, CopyDocument, Delete as DeleteIcon, FolderAdd, MoreFilled, Plus, Search, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import axios from 'axios'
import { workflowApi, type WorkflowRunSummary } from '@/services/api/workflow'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { resolveAcgTaskTitle } from '@/utils/acgTaskTitle'
import {
  ACG_RUN_INVALIDATED_EVENT,
  ACG_HISTORY_SOURCES
} from '@/utils/acgHistoryFilter'

defineProps<{ activeRunId?: string }>()

const emit = defineEmits<{
  new: []
  select: [runId: string]
  deleted: [runId: string]
  manage: []
}>()

type RunGroupKey = 'active' | 'review' | 'failed' | 'completed'

const runs = ref<WorkflowRunSummary[]>([])
const loading = ref(false)
const refreshing = ref(false)
const loadError = ref('')
const searchKeyword = ref('')
const statusFilter = ref<'all' | RunGroupKey>('all')
const selectedRunId = ref('')
const actionMenuElement = ref<HTMLElement | null>(null)
const actionMenu = reactive<{ run: WorkflowRunSummary | null; x: number; y: number }>({ run: null, x: 0, y: 0 })
const workflowRunsStore = useWorkflowRunsStore()
let loadController: AbortController | null = null
let loadPromise: Promise<void> | null = null
let refreshTimer: ReturnType<typeof window.setTimeout> | null = null
let unmounted = false
const invalidatedRunIds = new Set<string>()
const ACTIVE_REFRESH_INTERVAL_MS = 8_000
const IDLE_REFRESH_INTERVAL_MS = 30_000
const RUN_LIST_TIMEOUT_MS = 12_000
const RUN_LIST_PAGE_SIZE = 20
const RUN_LIST_STATUSES = 'pending,planning,running,waiting_review,retrying,failed,completed,cancelled'

const groupKey = (run: WorkflowRunSummary): RunGroupKey => {
  if (run.status === 'waiting_review' || run.phase === 'review') return 'review'
  if (run.status === 'failed' || run.status === 'cancelled' || run.phase === 'failed') return 'failed'
  if (run.status === 'completed' || run.phase === 'completed') return 'completed'
  return 'active'
}


const filteredRuns = computed(() => {
  const keyword = searchKeyword.value.toLocaleLowerCase('zh-CN')
  const latestByMission = new Map<string, WorkflowRunSummary>()
  for (const run of runs.value) {
    const identity = run.missionId || run.runId
    const current = latestByMission.get(identity)
    const timestamp = Date.parse(run.updatedAt || run.startedAt || run.createdAt || '') || 0
    const currentTimestamp = current
      ? Date.parse(current.updatedAt || current.startedAt || current.createdAt || '') || 0
      : -1
    if (!current || timestamp >= currentTimestamp) latestByMission.set(identity, run)
  }
  return [...latestByMission.values()]
    .filter(run => {
      const key = groupKey(run)
      if (statusFilter.value !== 'all' && statusFilter.value !== key) return false
      if (!keyword) return true
      return [run.missionId, run.runId, run.title, run.workflowId, run.message]
        .filter(Boolean)
        .some(value => String(value).toLocaleLowerCase('zh-CN').includes(keyword))
    })
    .sort((left, right) => runTimestamp(right) - runTimestamp(left))
})

const visibleGroups = computed(() => {
  const definitions: Array<{ key: RunGroupKey; label: string }> = [
    { key: 'active', label: '运行中' },
    { key: 'review', label: '等待审核' },
    { key: 'failed', label: '需要处理' },
    { key: 'completed', label: '最近完成' }
  ]
  return definitions
    .map(group => ({ ...group, items: filteredRuns.value.filter(run => groupKey(run) === group.key) }))
    .filter(group => group.items.length)
})

const displayTitle = (run: WorkflowRunSummary) => resolveAcgTaskTitle(run)

const missionIdentity = (run: WorkflowRunSummary) => run.missionId || run.runId
const isTerminalMission = (run: WorkflowRunSummary) => ['completed', 'failed', 'cancelled'].includes(run.status)
const runActivityTime = (run: WorkflowRunSummary) => run.updatedAt || run.startedAt || run.createdAt || ''
const runTimestamp = (run: WorkflowRunSummary) => Date.parse(runActivityTime(run)) || 0
const runTimeLabel = (run: WorkflowRunSummary) => {
  const key = groupKey(run)
  if (key === 'completed') return '完成于'
  if (key === 'failed') return '结束于'
  return '更新于'
}

const safePercentage = (run: WorkflowRunSummary) => {
  const value = run.percent ?? run.percentage ?? run.progress ?? 0
  return Math.min(100, Math.max(0, Math.round(value)))
}

const showProgress = (run: WorkflowRunSummary) => groupKey(run) === 'active' || groupKey(run) === 'review'


const phaseLabel = (run: WorkflowRunSummary) => {
  if (run.status === 'waiting_review' || run.phase === 'review') return '人工审核门'
  const labels: Record<string, string> = {
    understanding: '理解任务', planning: '智能规划', graph_building: '构建任务图',
    executing: run.currentStepId || '执行节点', recovery: '故障恢复', completed: '执行完成',
    failed: '执行失败', cancelled: '已取消'
  }
  return labels[run.phase] || run.message || '等待启动'
}

const formatRunTime = (value?: string | null) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate())
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate())
  const dayDifference = Math.round((startOfToday.getTime() - startOfDate.getTime()) / 86_400_000)
  const clock = date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })

  if (date.toDateString() === now.toDateString()) {
    return `今天 ${clock}`
  }
  if (dayDifference === 1) return `昨天 ${clock}`
  if (date.getFullYear() === now.getFullYear()) return `${date.getMonth() + 1}月${date.getDate()}日 ${clock}`
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日 ${clock}`
}

const formatFullRunTime = (value?: string | null) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return `最后更新：${date.toLocaleString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
  })}`
}

const copyMissionId = async (missionId: string) => {
  try {
    await navigator.clipboard.writeText(missionId)
    ElMessage.success('任务 ID 已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择任务 ID')
  }
}

const loadRuns = (silent = false): Promise<void> => {
  if (loadPromise) return loadPromise

  const controller = new AbortController()
  loadController = controller
  if (!silent && !runs.value.length) loading.value = true
  refreshing.value = true
  loadError.value = ''
  let timedOut = false
  const timeoutId = window.setTimeout(() => {
    timedOut = true
    controller.abort()
  }, RUN_LIST_TIMEOUT_MS)
  const pending = (async () => {
    try {
      const page = await workflowApi.listRuns(
        {
          sources: ACG_HISTORY_SOURCES,
          statuses: RUN_LIST_STATUSES,
          summary: true,
          page: 1,
          pageSize: RUN_LIST_PAGE_SIZE,
          recordState: 'active'
        },
        { signal: controller.signal }
      )
      if (!controller.signal.aborted) {
        const authoritativeRuns = page.items || []
        for (const run of authoritativeRuns) invalidatedRunIds.delete(run.runId)
        runs.value = authoritativeRuns
      }
    } catch (error: unknown) {
      if (timedOut) {
        loadError.value = '运行服务响应超时，请重试'
      } else if ((error as { code?: string })?.code !== 'ERR_CANCELED' && !controller.signal.aborted) {
        loadError.value = '运行记录暂时无法加载'
      }
    } finally {
      window.clearTimeout(timeoutId)
      if (loadController === controller) {
        loadController = null
        loadPromise = null
        loading.value = false
        refreshing.value = false
      }
    }
  })()
  loadPromise = pending
  return pending
}

const closeActionMenu = () => { actionMenu.run = null }
const selectRun = (runId: string) => {
  selectedRunId.value = runId
  closeActionMenu()
  emit('select', runId)
}
const openActionMenu = async (event: MouseEvent, run: WorkflowRunSummary) => {
  selectedRunId.value = run.runId
  actionMenu.run = run
  const target = event.currentTarget as HTMLElement | null
  const rect = target?.getBoundingClientRect()
  actionMenu.x = rect ? rect.left - 18 : event.clientX - 84
  actionMenu.y = rect ? rect.bottom + 6 : event.clientY
  await nextTick()
  const menu = actionMenuElement.value
  if (!menu) return
  actionMenu.x = Math.max(8, Math.min(actionMenu.x, window.innerWidth - menu.offsetWidth - 8))
  actionMenu.y = Math.max(8, Math.min(actionMenu.y, window.innerHeight - menu.offsetHeight - 8))
}
const selectActionRun = () => { if (actionMenu.run) selectRun(actionMenu.run.runId); closeActionMenu() }
const copyActionMissionId = () => { if (actionMenu.run) void copyMissionId(missionIdentity(actionMenu.run)); closeActionMenu() }
const missionMutationError = (error: unknown, action: string) => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409) return `任务仍有活动执行，暂时不能${action}`
    if (error.response?.status === 404) return '任务不存在或当前账户无权操作'
    const data = error.response?.data as { message?: unknown; detail?: unknown } | undefined
    const detail = [data?.message, data?.detail].find(value => typeof value === 'string' && value.trim())
    if (typeof detail === 'string') return `${action}失败：${detail.slice(0, 160)}`
  }
  return `任务${action}失败，请稍后重试`
}
const archiveActionMission = async () => {
  const run = actionMenu.run
  if (!run || !isTerminalMission(run)) return
  try { await workflowApi.archiveMission(missionIdentity(run)); ElMessage.success('任务已归档'); closeActionMenu(); await loadRuns(true) }
  catch (error: unknown) { ElMessage.error(missionMutationError(error, '归档')) }
}
const deleteActionMission = async () => {
  const run = actionMenu.run
  if (!run || !isTerminalMission(run)) return
  try {
    await ElMessageBox.confirm(
      `“${displayTitle(run)}”将从任务列表永久移除，执行审计事实仍会保留。`,
      '删除任务',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', customClass: 'destructive-confirm', confirmButtonClass: 'el-button--danger' }
    )
  } catch { return }
  try {
    await workflowApi.deleteMission(missionIdentity(run))
    ElMessage.success('任务已删除')
    closeActionMenu()
    emit('deleted', run.runId)
    await loadRuns(true)
  }
  catch (error: unknown) { ElMessage.error(missionMutationError(error, '删除')) }
}
const handleActionDismiss = (event: PointerEvent) => { if (!actionMenuElement.value?.contains(event.target as Node)) closeActionMenu() }
const handleActionKeydown = (event: KeyboardEvent) => { if (event.key === 'Escape') closeActionMenu() }

const scheduleRefresh = () => {
  if (unmounted) return
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  const hasActiveRuns = runs.value.some(run => groupKey(run) === 'active' || groupKey(run) === 'review')
  refreshTimer = window.setTimeout(async () => {
    refreshTimer = null
    if (document.visibilityState !== 'hidden') await loadRuns(true)
    scheduleRefresh()
  }, hasActiveRuns ? ACTIVE_REFRESH_INTERVAL_MS : IDLE_REFRESH_INTERVAL_MS)
}

// External mutations refresh the usable local list in the background and reset the poll window.
const handleRunsRefresh = () => {
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  refreshTimer = null
  void loadRuns(true).finally(scheduleRefresh)
}

const handleRunInvalidated = (event: Event) => {
  const runId = (event as CustomEvent<{ runId?: unknown }>).detail?.runId
  if (typeof runId !== 'string' || !runId.trim()) return
  const normalizedRunId = runId.trim()
  invalidatedRunIds.add(normalizedRunId)
  runs.value = runs.value.filter(run => run.runId !== normalizedRunId)
  workflowRunsStore.removeReference(normalizedRunId)
}

onMounted(() => {
  window.addEventListener('acg-runs-refresh', handleRunsRefresh)
  window.addEventListener(ACG_RUN_INVALIDATED_EVENT, handleRunInvalidated)
  window.addEventListener('pointerdown', handleActionDismiss)
  window.addEventListener('keydown', handleActionKeydown)
  void loadRuns().finally(scheduleRefresh)
})

onUnmounted(() => {
  unmounted = true
  loadController?.abort()
  if (refreshTimer !== null) window.clearTimeout(refreshTimer)
  window.removeEventListener('acg-runs-refresh', handleRunsRefresh)
  window.removeEventListener(ACG_RUN_INVALIDATED_EVENT, handleRunInvalidated)
  window.removeEventListener('pointerdown', handleActionDismiss)
  window.removeEventListener('keydown', handleActionKeydown)
})
</script>

<style scoped>
.acg-run-manager { min-width: 210px; flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 10px 8px 10px; overflow: hidden; }
.acg-new-run { min-height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--border-light); border-radius: 7px; background: color-mix(in srgb, var(--bg-card) 84%, transparent); color: var(--text-primary); box-shadow: var(--shadow-sm); font: inherit; font-size: 12px; font-weight: 650; cursor: pointer; transition: var(--transition); }
.acg-new-run:hover { border-color: var(--primary-line); background: var(--bg-card); color: var(--primary-color); }
.acg-new-run:focus-visible, .acg-run-item__select:focus-visible, .acg-run-manage:focus-visible, .acg-run-search:focus-within, .acg-run-filter:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
.acg-run-tools { position: relative; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; margin: 8px 0 6px; }
.acg-run-refreshing { position: absolute; right: 4px; top: 34px; z-index: 1; color: var(--primary-color); font-size: 9px; }
.acg-run-search { grid-column: 1 / -1; min-width: 0; height: 30px; display: flex; align-items: center; gap: 6px; padding: 0 8px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-input); color: var(--text-disabled); }
.acg-run-search input { width: 100%; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); font: inherit; font-size: 10px; }
.acg-run-search input::placeholder { color: var(--text-disabled); }
.acg-run-filter { height: 30px; min-width: 0; padding: 0 6px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-input); color: var(--text-secondary); font: inherit; font-size: 10px; }
.acg-run-groups { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; }
.acg-run-groups::-webkit-scrollbar { width: 4px; }
.acg-run-groups::-webkit-scrollbar-thumb { border-radius: 999px; background: var(--scrollbar-thumb); }
.acg-run-group + .acg-run-group { margin-top: 8px; }
.acg-run-group__head { height: 28px; display: flex; align-items: center; justify-content: space-between; padding: 5px 8px 4px; color: var(--text-disabled); font-size: 11px; font-weight: 700; }
.acg-run-group__head span:last-child { min-width: 16px; height: 16px; display: inline-grid; place-items: center; padding: 0 4px; border-radius: 999px; background: var(--primary-fade); color: var(--primary-color); font-size: 10px; }
.acg-run-item { position: relative; width: 100%; border-radius: var(--radius-control); background: transparent; color: var(--text-secondary); transition: background-color 160ms ease, color 160ms ease; }
.acg-run-item__select { width: 100%; display: grid; grid-template-columns: 15px minmax(0, 1fr); gap: 6px; padding: 8px 34px 8px 7px; border: 0; border-radius: inherit; background: transparent; color: inherit; text-align: left; font: inherit; cursor: pointer; }
.acg-run-item__actions {
  position: absolute; top: 50%; right: 6px; width: 24px; height: 24px; display: inline-grid; place-items: center;
  padding: 0; border: 0; border-radius: var(--radius-control);
  background: transparent; color: var(--text-secondary);
  cursor: pointer; opacity: 0; pointer-events: none; transform: translate(4px, -50%);
  transition: opacity 220ms var(--ease-out) 35ms, transform 220ms var(--ease-out) 35ms, color 160ms ease;
}
.acg-run-item:hover .acg-run-item__actions,
.acg-run-item__actions:focus-visible {
  opacity: 1; pointer-events: auto; transform: translate(0, -50%);
}
.acg-run-item__actions:hover, .acg-run-item__actions:focus-visible, .acg-run-item__actions[aria-expanded="true"] {
  background: transparent; color: var(--primary-color); outline: none;
}
.acg-run-item__actions:focus-visible { outline: 2px solid color-mix(in srgb, var(--primary-color) 45%, transparent); outline-offset: 2px; }
.acg-run-item__actions .el-icon { font-size: 15px; }
.acg-run-item::before { content: ''; position: absolute; inset: 5px auto 5px 0; width: 2px; border-radius: 0 2px 2px 0; background: transparent; }
.acg-run-item:hover { background: var(--bg-panel); color: var(--text-primary); }
.acg-run-item.active { background: var(--primary-fade); color: var(--text-primary); }
.acg-run-item.selected:not(.active) { background: color-mix(in srgb, var(--primary-fade) 68%, transparent); color: var(--text-primary); }
.acg-run-item.active::before { background: var(--primary-color); }
.acg-run-item__status { width: 13px; height: 13px; margin-top: 1px; display: inline-grid; place-items: center; border: 1px solid var(--text-disabled); border-radius: 50%; background: var(--bg-card); color: var(--text-disabled); font-size: 9px; font-weight: 800; line-height: 1; }
.status-active .acg-run-item__status { border-color: var(--sem-running); background: var(--sem-running-fade); color: var(--sem-running); animation: acg-status-pulse 1.8s ease-in-out infinite; }
.status-active .acg-run-item__status::after { width: 5px; height: 5px; border-radius: 50%; background: currentColor; content: ''; }
.status-review .acg-run-item__status { border-color: var(--sem-waiting); background: var(--sem-waiting-fade); color: var(--sem-waiting); }
.status-review .acg-run-item__status::after { content: '!'; }
.status-failed .acg-run-item__status { border-color: var(--sem-failed); background: var(--sem-failed-fade); color: var(--sem-failed); }
.status-failed .acg-run-item__status::after { content: '\00d7'; }
.status-completed .acg-run-item__status { border-color: var(--sem-success); background: var(--sem-success-fade); color: var(--sem-success); }
.status-completed .acg-run-item__status::after { content: '\2713'; }

@keyframes acg-status-pulse {
  0%, 100% { box-shadow: 0 0 0 2px var(--primary-fade); }
  50% { box-shadow: 0 0 0 4px transparent; }
}

@media (prefers-reduced-motion: reduce) {
  .status-active .acg-run-item__status { animation: none; }
}
.acg-run-item__body { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.acg-run-item__headline { min-width: 0; display: flex; align-items: center; }
.acg-run-item__headline strong { overflow: hidden; color: inherit; font-size: 11px; font-weight: 700; line-height: 1.3; text-overflow: ellipsis; white-space: nowrap; }
.acg-run-item__meta { min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.acg-run-item__meta time { flex: 0 0 auto; color: var(--text-disabled); font-size: 9px; font-variant-numeric: tabular-nums; white-space: nowrap; }
.acg-run-item:hover .acg-run-item__headline { padding-right: 0; }
.acg-run-delete:hover { background: var(--danger-fade); color: var(--danger); }
.acg-run-action:disabled { cursor: wait; opacity: .55; }
.acg-run-item__phase { overflow: hidden; color: var(--text-secondary); font-size: 10px; line-height: 1.3; text-overflow: ellipsis; white-space: nowrap; }
.acg-run-item__progress { height: 2px; margin-top: 2px; overflow: hidden; border-radius: 999px; background: var(--border-light); }
.acg-run-item__progress span { display: block; height: 100%; border-radius: inherit; background: var(--primary-color); transition: width 240ms ease; }
.status-review .acg-run-item__progress span { background: var(--warning); }
.acg-run-message { flex: 1; display: flex; align-items: flex-start; gap: 8px; padding: 12px 9px; color: var(--text-disabled); font-size: 11px; }
.acg-run-message--error { color: var(--danger); }
.acg-run-message button { border: 0; background: transparent; color: var(--primary-color); cursor: pointer; }
.acg-run-manage { box-sizing: border-box; height: 38px; min-height: 38px; flex: 0 0 38px; display: flex; align-items: center; gap: 7px; margin-top: 5px; padding: 0 8px; border: 1px solid var(--primary-line); border-radius: 7px; background: color-mix(in srgb, var(--primary-fade) 72%, var(--bg-card)); color: var(--primary-color); font: inherit; text-align: left; cursor: pointer; transition: var(--transition); }
.acg-run-manage:hover { border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-fade) 88%, var(--bg-card)); }
.acg-run-manage__icon { width: 22px; height: 22px; flex: 0 0 22px; display: inline-grid; place-items: center; border-radius: 5px; background: var(--bg-card); }
.acg-run-manage > span:nth-child(2) { min-width: 0; flex: 1; display: block; }
.acg-run-manage strong, .acg-run-manage small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.acg-run-manage strong { color: var(--text-primary); font-size: 12px; }
.acg-run-manage small { display: none; }
.acg-explorer-header { flex: 0 0 auto; display: flex; min-width: 0; padding: 0; }
.acg-new-run { width: 100%; min-width: 0; min-height: 48px; height: 48px; display: inline-flex; align-items: center; justify-content: flex-start; gap: 10px; padding: 0 14px; border: 1px solid var(--wb-border, var(--border-light)); border-radius: 10px; background: var(--surface-solid); box-shadow: inset 0 1px 0 rgba(255, 255, 255, .92), 0 2px 5px rgba(46, 50, 78, .1); color: var(--wb-text, var(--text-primary)); font-size: 13px; font-weight: 760; white-space: nowrap; }
.acg-new-run .el-icon { color: var(--wb-muted, var(--text-secondary)); font-size: 16px; }
.acg-new-run > span { overflow: hidden; text-overflow: ellipsis; }
.acg-new-run:hover { border-color: var(--primary-line); color: var(--wb-accent, var(--primary-color)); box-shadow: inset 0 1px 0 rgba(255, 255, 255, .96), 0 3px 7px rgba(46, 50, 78, .13); }
.acg-new-run:hover .el-icon { color: var(--wb-accent, var(--primary-color)); }
.acg-new-run:active { transform: translateY(1px); box-shadow: inset 0 1px 2px rgba(46, 50, 78, .14), 0 1px 2px rgba(46, 50, 78, .08); }
.acg-run-tools { gap: 4px; margin: 5px 0 4px; }
.acg-run-search, .acg-run-filter { height: 28px; border-radius: 4px; }
.acg-run-groups { scrollbar-gutter: stable; }
.acg-run-group + .acg-run-group { margin-top: 4px; }
.acg-run-group__head { height: 26px; padding: 4px 5px 3px; font-size: 10px; }
.acg-run-group__head span:last-child { min-width: 15px; height: 15px; border-radius: 3px; font-size: 9px; }
.acg-run-item { border-radius: 3px; }
.acg-run-item__select { gap: 5px; padding: 6px 30px 6px 5px; }
.acg-run-item__body { gap: 2px; }
.acg-run-item__headline strong { font-size: 11px; }
.acg-run-item__phase { font-size: 9px; }
.acg-run-manage { height: 32px; min-height: 32px; flex-basis: 32px; margin-top: 4px; padding: 0 5px; border: 0; border-top: 1px solid var(--wb-border, var(--border-light)); border-radius: 0; background: transparent; }
.acg-run-manage:hover { border-color: var(--wb-border, var(--border-light)); background: var(--wb-hover, var(--bg-input)); }
.acg-run-manage__icon { width: 20px; height: 20px; flex-basis: 20px; border-radius: 3px; background: transparent; }
@media (prefers-reduced-motion: reduce) { .acg-run-item, .acg-run-item__actions, .acg-run-item__progress span, .acg-new-run, .acg-run-manage { transition-duration: 1ms; transition-delay: 0ms; } }
</style>

<style>
.acg-run-action-menu {
  position: fixed; z-index: 3000; box-sizing: border-box; width: 168px; padding: 5px;
  border: 1px solid var(--border-light); border-radius: var(--radius-card); background: var(--bg-card);
  box-shadow: var(--shadow-lg); color: var(--text-primary); animation: acg-run-action-menu-in 180ms var(--ease-out) both;
}
.acg-run-action-menu button { width: 100%; min-height: 32px; display: grid; grid-template-columns: 20px minmax(0, 1fr); align-items: center; gap: 6px; padding: 0 9px; border: 0; border-radius: var(--radius-control); background: transparent; color: inherit; font: inherit; font-size: 12px; text-align: left; cursor: pointer; }
.acg-run-action-menu button:hover:not(:disabled), .acg-run-action-menu button:focus-visible { background: var(--primary-fade); color: var(--primary-color); outline: none; }
.acg-run-action-menu button.is-danger { color: var(--danger); }
.acg-run-action-menu button:disabled { color: var(--text-disabled); cursor: not-allowed; }
.acg-run-action-menu__separator { height: 1px; margin: 4px 6px; background: var(--border-light); }
@keyframes acg-run-action-menu-in {
  from { opacity: 0; transform: translateY(-4px) scale(.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@media (prefers-reduced-motion: reduce) { .acg-run-action-menu { animation: none; } }
</style>
