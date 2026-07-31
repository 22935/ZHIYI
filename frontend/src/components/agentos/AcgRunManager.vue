<template>
  <div class="acg-run-manager">
    <button class="acg-new-run" type="button" @click="emit('new')">
      <el-icon><Plus /></el-icon>
      <span>新建 ACG 任务</span>
    </button>

    <div class="acg-run-tools">
      <label class="acg-run-search">
        <el-icon><Search /></el-icon>
        <input v-model.trim="searchKeyword" type="search" placeholder="搜索运行 ID / 任务名称" />
      </label>
      <select v-model="statusFilter" class="acg-run-filter" aria-label="筛选运行状态">
        <option value="all">全部</option>
        <option value="active">运行中</option>
        <option value="review">待审核</option>
        <option value="failed">需处理</option>
        <option value="completed">已完成</option>
      </select>
    </div>

    <div v-if="loading" class="acg-run-message">正在加载运行记录…</div>
    <div v-else-if="loadError" class="acg-run-message acg-run-message--error">
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
          :class="[`status-${group.key}`, { active: run.runId === activeRunId }]"
        >
          <button
            class="acg-run-item__select"
            type="button"
            :title="`${displayTitle(run)}\n${run.runId}`"
            @click="emit('select', run.runId)"
          >
            <span class="acg-run-item__status" aria-hidden="true"></span>
            <span class="acg-run-item__body">
              <span class="acg-run-item__headline">
                <strong>{{ displayTitle(run) }}</strong>
                <time>{{ formatRunTime(run.updatedAt || run.startedAt || run.createdAt) }}</time>
              </span>
              <span class="acg-run-item__identity"><code>{{ shortenRunId(run.runId) }}</code></span>
              <span class="acg-run-item__phase">
                {{ phaseLabel(run) }}<template v-if="run.totalSteps"> · {{ run.completedSteps }}/{{ run.totalSteps }}</template>
              </span>
              <span v-if="showProgress(run)" class="acg-run-item__progress" aria-hidden="true">
                <span :style="{ width: `${safePercentage(run)}%` }"></span>
              </span>
            </span>
          </button>
          <span class="acg-run-actions">
            <button class="acg-run-action" type="button" title="复制完整 Run ID" :aria-label="`复制 Run ID：${run.runId}`" @click="copyRunId(run.runId)">
              <el-icon><CopyDocument /></el-icon>
            </button>
            <button
              v-if="canDelete(run)"
              class="acg-run-action acg-run-delete"
              type="button"
              title="删除运行记录"
              :aria-label="`删除运行：${displayTitle(run)}`"
              :disabled="deletingRunId === run.runId"
              @click="deleteRun(run)"
            >
              <el-icon><DeleteIcon /></el-icon>
            </button>
          </span>
        </div>
      </section>
    </div>

    <button class="acg-run-manage" type="button" @click="emit('manage')">
      <span class="acg-run-manage__icon"><el-icon><Clock /></el-icon></span>
      <span>
        <strong>查看全部运行记录</strong>
        <small>搜索、审计与运行管理</small>
      </span>
      <el-icon><ArrowRight /></el-icon>
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ArrowRight, Clock, CopyDocument, Delete as DeleteIcon, Plus, Search } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { workflowApi, type WorkflowRunSummary } from '@/services/api/workflow'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { resolveAcgTaskTitle } from '@/utils/acgTaskTitle'

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
const loadError = ref('')
const searchKeyword = ref('')
const statusFilter = ref<'all' | RunGroupKey>('all')
const deletingRunId = ref('')
const workflowRunsStore = useWorkflowRunsStore()
let loadController: AbortController | null = null
let refreshTimer: ReturnType<typeof window.setInterval> | null = null

const groupKey = (run: WorkflowRunSummary): RunGroupKey => {
  if (run.status === 'waiting_review' || run.phase === 'review') return 'review'
  if (run.status === 'failed' || run.status === 'cancelled' || run.phase === 'failed') return 'failed'
  if (run.status === 'completed' || run.phase === 'completed') return 'completed'
  return 'active'
}

const filteredRuns = computed(() => {
  const keyword = searchKeyword.value.toLocaleLowerCase('zh-CN')
  return runs.value.filter(run => {
    const key = groupKey(run)
    if (statusFilter.value !== 'all' && statusFilter.value !== key) return false
    if (!keyword) return true
    return [run.runId, run.title, run.workflowId, run.message]
      .filter(Boolean)
      .some(value => String(value).toLocaleLowerCase('zh-CN').includes(keyword))
  })
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

const shortenRunId = (runId: string) => runId.length > 18 ? `${runId.slice(0, 15)}…` : runId

const safePercentage = (run: WorkflowRunSummary) => {
  const value = run.percent ?? run.percentage ?? run.progress ?? 0
  return Math.min(100, Math.max(0, Math.round(value)))
}

const showProgress = (run: WorkflowRunSummary) => groupKey(run) === 'active' || groupKey(run) === 'review'

const canDelete = (run: WorkflowRunSummary) => ['completed', 'failed', 'cancelled'].includes(run.status)

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
  if (date.toDateString() === now.toDateString()) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

const copyRunId = async (runId: string) => {
  try {
    await navigator.clipboard.writeText(runId)
    ElMessage.success('Run ID 已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择 Run ID')
  }
}

const deleteRun = async (run: WorkflowRunSummary) => {
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
    deletingRunId.value = run.runId
    await workflowApi.deleteRun(run.runId)
    runs.value = runs.value.filter(item => item.runId !== run.runId)
    workflowRunsStore.removeReference(run.runId)
    emit('deleted', run.runId)
    window.dispatchEvent(new Event('acg-runs-refresh'))
    ElMessage.success('ACG 运行记录已删除')
  } catch (error: unknown) {
    if (error === 'cancel' || error === 'close') return
    const data = (error as { response?: { data?: { detail?: string; message?: string } } })?.response?.data
    ElMessage.error(data?.message || data?.detail || '删除失败，请稍后重试')
  } finally {
    deletingRunId.value = ''
  }
}

const loadRuns = async (silent = false) => {
  loadController?.abort()
  loadController = new AbortController()
  if (!silent) loading.value = true
  loadError.value = ''
  try {
    const page = await workflowApi.listRuns(
      { source: 'acg', summary: true, page: 1, pageSize: 100 },
      { signal: loadController.signal }
    )
    runs.value = page.items || []
  } catch (error: unknown) {
    if ((error as { code?: string })?.code !== 'ERR_CANCELED') loadError.value = '运行记录暂时无法加载'
  } finally {
    if (!silent) loading.value = false
  }
}

const handleRunsRefresh = () => void loadRuns()

onMounted(() => {
  window.addEventListener('acg-runs-refresh', handleRunsRefresh)
  void loadRuns()
  refreshTimer = window.setInterval(() => void loadRuns(true), 8000)
})

onUnmounted(() => {
  loadController?.abort()
  if (refreshTimer !== null) window.clearInterval(refreshTimer)
  window.removeEventListener('acg-runs-refresh', handleRunsRefresh)
})
</script>

<style scoped>
.acg-run-manager { min-width: 210px; flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 10px 8px 10px; overflow: hidden; }
.acg-new-run { min-height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 10px; border: 1px solid var(--border-light); border-radius: 7px; background: color-mix(in srgb, var(--bg-card) 84%, transparent); color: var(--text-primary); box-shadow: var(--shadow-sm); font: inherit; font-size: 12px; font-weight: 650; cursor: pointer; transition: var(--transition); }
.acg-new-run:hover { border-color: var(--primary-line); background: var(--bg-card); color: var(--primary-color); }
.acg-new-run:focus-visible, .acg-run-item__select:focus-visible, .acg-run-manage:focus-visible, .acg-run-search:focus-within, .acg-run-filter:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
.acg-run-tools { display: grid; grid-template-columns: minmax(0, 1fr) 72px; gap: 6px; margin: 8px 0 6px; }
.acg-run-search { min-width: 0; height: 30px; display: flex; align-items: center; gap: 6px; padding: 0 8px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-input); color: var(--text-disabled); }
.acg-run-search input { width: 100%; min-width: 0; border: 0; outline: 0; background: transparent; color: var(--text-primary); font: inherit; font-size: 10px; }
.acg-run-search input::placeholder { color: var(--text-disabled); }
.acg-run-filter { height: 30px; min-width: 0; padding: 0 6px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-input); color: var(--text-secondary); font: inherit; font-size: 10px; }
.acg-run-groups { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--scrollbar-thumb) transparent; }
.acg-run-groups::-webkit-scrollbar { width: 4px; }
.acg-run-groups::-webkit-scrollbar-thumb { border-radius: 999px; background: var(--scrollbar-thumb); }
.acg-run-group + .acg-run-group { margin-top: 8px; }
.acg-run-group__head { height: 28px; display: flex; align-items: center; justify-content: space-between; padding: 5px 8px 4px; color: var(--text-disabled); font-size: 11px; font-weight: 700; }
.acg-run-group__head span:last-child { min-width: 16px; height: 16px; display: inline-grid; place-items: center; padding: 0 4px; border-radius: 999px; background: var(--primary-fade); color: var(--primary-color); font-size: 10px; }
.acg-run-item { position: relative; width: 100%; border-radius: 7px; background: transparent; color: var(--text-secondary); transition: background-color 160ms ease, color 160ms ease; }
.acg-run-item__select { width: 100%; display: grid; grid-template-columns: 9px minmax(0, 1fr); gap: 6px; padding: 8px 8px 8px 7px; border: 0; border-radius: inherit; background: transparent; color: inherit; text-align: left; font: inherit; cursor: pointer; }
.acg-run-item::before { content: ''; position: absolute; inset: 5px auto 5px 0; width: 2px; border-radius: 0 2px 2px 0; background: transparent; }
.acg-run-item:hover { background: var(--bg-panel); color: var(--text-primary); }
.acg-run-item.active { background: var(--primary-fade); color: var(--text-primary); }
.acg-run-item.active::before { background: var(--primary-color); }
.acg-run-item__status { width: 7px; height: 7px; margin-top: 4px; border-radius: 50%; background: var(--text-disabled); }
.status-active .acg-run-item__status { background: var(--primary-color); box-shadow: 0 0 0 3px var(--primary-fade); }
.status-review .acg-run-item__status { background: var(--warning); }
.status-failed .acg-run-item__status { background: var(--danger); }
.status-completed .acg-run-item__status { background: var(--success); }
.acg-run-item__body { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.acg-run-item__headline, .acg-run-item__identity { min-width: 0; display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.acg-run-item__headline strong { overflow: hidden; color: inherit; font-size: 11px; font-weight: 700; line-height: 1.3; text-overflow: ellipsis; white-space: nowrap; }
.acg-run-item__headline time { flex: 0 0 auto; color: var(--text-disabled); font-size: 9px; font-variant-numeric: tabular-nums; }
.acg-run-item__identity code { overflow: hidden; color: var(--text-muted); font-family: var(--font-mono, ui-monospace, SFMono-Regular, Consolas, monospace); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.acg-run-actions { position: absolute; z-index: 1; top: 27px; right: 5px; display: flex; align-items: center; gap: 1px; opacity: 0; transition: opacity 160ms ease; }
.acg-run-item:hover .acg-run-actions, .acg-run-actions:focus-within { opacity: 1; }
.acg-run-action { display: inline-grid; place-items: center; width: 20px; height: 20px; padding: 0; border: 0; border-radius: 5px; background: color-mix(in srgb, var(--bg-card) 88%, transparent); color: var(--text-disabled); cursor: pointer; transition: color 160ms ease, background-color 160ms ease; }
.acg-run-action:hover { background: var(--bg-card); color: var(--primary-color); }
.acg-run-delete:hover { background: var(--danger-fade); color: var(--danger); }
.acg-run-action:disabled { cursor: wait; opacity: .55; }
.acg-run-item:hover .acg-run-item__identity { padding-right: 44px; }
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
@media (prefers-reduced-motion: reduce) { .acg-run-item, .acg-run-item__progress span, .acg-new-run, .acg-run-manage { transition-duration: 1ms; } }
</style>
