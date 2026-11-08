<template>
  <WorkbenchLayout :show-left="false" :show-right="false" storage-key="zhiyi.projects.layout.v1">
    <template #main>
      <main class="project-list" aria-label="Projects">
        <header class="project-list__header">
          <div>
            <span class="project-list__eyebrow">PROJECTS</span>
            <h1>工程项目</h1>
            <!-- <p>每个项目拥有独立的 Mission、Runs 与只读交付物。</p> -->
          </div>
          <button class="project-list__create" type="button" @click="createMission">
            <el-icon aria-hidden="true"><Plus /></el-icon>
            <span>新建工程</span>
          </button>
        </header>

        <section class="project-list__toolbar" aria-label="项目筛选">
          <label class="project-list__search">
            <el-icon aria-hidden="true"><Search /></el-icon>
            <input v-model="searchText" type="search" placeholder="搜索项目名称或 Mission ID" />
          </label>
          <div class="project-list__toolbar-actions">
            <span class="project-list__count"><strong>{{ filteredMissions.length }}</strong> 个项目</span>
            <button
              class="project-list__export"
              type="button"
              ref="exportButtonElement"
              aria-haspopup="menu"
              aria-controls="project-export-menu"
              :aria-expanded="exportMenu.open"
              :disabled="!filteredMissions.length"
              title="导出项目列表"
              @click="toggleExportMenu"
            >
              <el-icon aria-hidden="true"><Download /></el-icon><span>导出</span>
            </button>
            <div class="project-view-toggle" role="group" aria-label="项目显示方式">
              <button
                type="button"
                data-view-mode="list"
                :class="{ 'is-active': viewMode === 'list' }"
                :aria-pressed="viewMode === 'list'"
                title="宽版列表"
                @click="setViewMode('list')"
              >
                <el-icon aria-hidden="true"><List /></el-icon><span>列表</span>
              </button>
              <button
                type="button"
                data-view-mode="grid"
                :class="{ 'is-active': viewMode === 'grid' }"
                :aria-pressed="viewMode === 'grid'"
                title="项目网格"
                @click="setViewMode('grid')"
              >
                <el-icon aria-hidden="true"><Grid /></el-icon><span>网格</span>
              </button>
            </div>
          </div>
        </section>

        <section v-if="loading && !missions.length" class="project-list__state" role="status">
          <BrandLoader :size="96" title="正在加载项目" subtitle="读取 Mission Project 列表…" />
        </section>
        <section v-else-if="errorMessage" class="project-list__state project-list__state--error" role="alert">
          <strong>项目列表暂时不可用</strong>
          <span>{{ errorMessage }}</span>
          <button type="button" @click="loadMissions">重新加载</button>
        </section>
        <section v-else-if="!filteredMissions.length" class="project-list__state" role="status">
          <strong>{{ searchText ? '没有匹配的项目' : '还没有工程项目' }}</strong>
          <span>{{ searchText ? '换一个名称或 Mission ID 试试。' : '创建第一个 Mission，开始一次运行。' }}</span>
          <button v-if="!searchText" type="button" @click="createMission">新建工程</button>
        </section>
        <section v-else class="project-list__rows" :class="{ 'is-grid': viewMode === 'grid' }" aria-label="Mission Projects">
          <div
            v-for="mission in filteredMissions"
            :key="mission.missionId"
            class="project-row"
            :class="{ 'is-grid': viewMode === 'grid' }"
            role="button"
            tabindex="0"
            :aria-label="`打开项目：${mission.title || '未命名工程'}`"
            @click="openMission(mission)"
            @keydown.enter="handleProjectRowKeydown($event, mission)"
            @keydown.space="handleProjectRowKeydown($event, mission)"
            @contextmenu.prevent="openActionMenu($event, mission)"
          >
            <span class="project-row__icon" aria-hidden="true"><el-icon><FolderOpened /></el-icon></span>
            <span class="project-row__copy">
              <strong :title="missionDisplayTitle(mission)">{{ missionDisplayTitle(mission) }}</strong>
              <span>{{ mission.missionId }}</span>
            </span>
            <span class="project-row__meta">
              <span class="project-row__status" :class="`is-${statusTone(mission)}`">
                <i aria-hidden="true"></i>{{ statusLabel(mission) }}
              </span>
              <span>{{ mission.runCount }} 次运行</span>
              <time :datetime="mission.updatedAt">{{ formatDate(mission.updatedAt) }}</time>
            </span>
            <button
              class="project-row__actions"
              type="button"
              aria-haspopup="menu"
              aria-controls="project-action-menu"
              :aria-expanded="actionMenu.mission?.missionId === mission.missionId"
              :aria-label="`打开${mission.title || '未命名工程'}的任务操作`"
              @click.stop="openActionMenu($event, mission)"
              @contextmenu.prevent.stop="openActionMenu($event, mission)"
            >
              <el-icon><MoreFilled /></el-icon>
            </button>
            <span class="project-row__arrow" aria-hidden="true">›</span>
          </div>
        </section>
      </main>
    </template>
  </WorkbenchLayout>

  <Teleport to="body">
    <div
      v-if="actionMenu.mission"
      id="project-action-menu"
      ref="actionMenuElement"
      class="project-action-menu"
      role="menu"
      aria-label="项目操作"
      :style="{ left: `${actionMenu.x}px`, top: `${actionMenu.y}px` }"
    >
      <button type="button" role="menuitem" data-action="open" @click="openActionMission">
        <el-icon><View /></el-icon><span>打开项目</span>
      </button>
      <button type="button" role="menuitem" data-action="copy" @click="copyActionMissionId">
        <el-icon><CopyDocument /></el-icon><span>复制 Mission ID</span>
      </button>
      <button type="button" role="menuitem" data-action="export" @click="exportActionMission">
        <el-icon><Download /></el-icon><span>导出任务数据</span>
      </button>
      <div class="project-action-menu__separator"></div>
      <button
        type="button"
        role="menuitem"
        data-action="archive"
        :disabled="!isTerminalMission(actionMenu.mission)"
        :title="mutationDisabledReason(actionMenu.mission)"
        @click="archiveActionMission"
      >
        <el-icon><FolderAdd /></el-icon><span>归档任务</span>
      </button>
      <button
        class="is-danger"
        type="button"
        role="menuitem"
        data-action="delete"
        :disabled="!isTerminalMission(actionMenu.mission)"
        :title="mutationDisabledReason(actionMenu.mission)"
        @click="deleteActionMission"
      >
        <el-icon><DeleteIcon /></el-icon><span>删除任务</span>
      </button>
    </div>

    <div
      v-if="exportMenu.open"
      id="project-export-menu"
      ref="exportMenuElement"
      class="project-action-menu project-export-menu"
      role="menu"
      :aria-label="exportMenu.mission ? `导出任务：${missionDisplayTitle(exportMenu.mission)}` : '选择导出格式'"
      :style="{ left: `${exportMenu.x}px`, top: `${exportMenu.y}px` }"
    >
      <div v-if="exportMenu.mission" class="project-export-menu__context" :title="missionDisplayTitle(exportMenu.mission)">
        {{ missionDisplayTitle(exportMenu.mission) }}
      </div>
      <button type="button" role="menuitem" data-format="md" @click="exportProjects('md')">
        <el-icon><Memo /></el-icon><span>Markdown（可直接阅读）</span>
      </button>
      <button type="button" role="menuitem" data-format="csv" @click="exportProjects('csv')">
        <el-icon><Grid /></el-icon><span>CSV（表格）</span>
      </button>
      <button type="button" role="menuitem" data-format="json" @click="exportProjects('json')">
        <el-icon><Document /></el-icon><span>JSON（完整数据）</span>
      </button>
      <button type="button" role="menuitem" data-format="txt" @click="exportProjects('txt')">
        <el-icon><Tickets /></el-icon><span>TXT（纯文本）</span>
      </button>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, h, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { CopyDocument, Delete as DeleteIcon, Document, Download, FolderAdd, FolderOpened, Grid, List, Memo, MoreFilled, Plus, Search, Tickets, View } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import BrandLoader from '@/components/common/BrandLoader.vue'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import { agentosApi, type MissionListItem, type WorkflowRunSummary } from '@/services/api/agentos'
import { downloadFile, exportMissionDetailToCsv, exportMissionDetailToJson, exportMissionDetailToMarkdown, exportMissionDetailToTxt, exportMissionsToCsv, exportMissionsToJson, exportMissionsToMarkdown, exportMissionsToTxt, type MissionDetailExport } from '@/utils/export'
import { plainMissionTitle } from '@/utils/missionTitle'

const router = useRouter()
const missions = ref<MissionListItem[]>([])
const searchText = ref('')
const loading = ref(false)
const errorMessage = ref('')
let controller: AbortController | null = null
const actionMenu = reactive<{ mission: MissionListItem | null; x: number; y: number }>({ mission: null, x: 0, y: 0 })
const actionMenuElement = ref<HTMLElement | null>(null)
type ProjectViewMode = 'list' | 'grid'
const PROJECT_VIEW_MODE_STORAGE_KEY = 'zhiyi.projects.view-mode.v1'
const viewMode = ref<ProjectViewMode>(
  typeof window !== 'undefined' && window.localStorage.getItem(PROJECT_VIEW_MODE_STORAGE_KEY) === 'grid' ? 'grid' : 'list'
)

const filteredMissions = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase()
  if (!query) return missions.value
  return missions.value.filter(mission => [mission.title, mission.missionId, mission.description]
    .some(value => value.toLocaleLowerCase().includes(query)))
})

const statusTone = (mission: MissionListItem) => {
  const status = mission.latestRunStatus || mission.status
  if (['completed', 'succeeded'].includes(status)) return 'success'
  if (['failed', 'cancelled'].includes(status)) return 'danger'
  if (['running', 'planning', 'pending', 'waiting_review', 'retrying'].includes(status)) return 'active'
  return 'muted'
}

const STATUS_LABELS: Record<string, string> = {
  completed: '已完成', succeeded: '已完成', running: '运行中', planning: '规划中',
  pending: '待启动', waiting_review: '待审核', retrying: '重试中', failed: '失败',
  cancelled: '已取消', archived: '已归档', created: '已创建'
}

const statusLabel = (mission: MissionListItem) => {
  const status = mission.latestRunStatus || mission.status
  return STATUS_LABELS[status] || status || '未知'
}

const RUN_PHASE_LABELS: Record<string, string> = {
  understanding: '理解', planning: '规划', graph_building: '构图', executing: '执行',
  recovery: '恢复', review: '审核', completed: '完成', failed: '失败', cancelled: '取消'
}

const runStatusLabel = (status: string | null | undefined) => (status ? STATUS_LABELS[status] || status : '无')

const formatDate = (value: string) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}

const missionIdentity = (mission: MissionListItem) => mission.missionId
const isTerminalMission = (mission: MissionListItem) => {
  if (mission.runCount === 0) return true
  const status = mission.latestRunStatus || mission.status
  return ['completed', 'succeeded', 'failed', 'cancelled', 'superseded'].includes(status)
}
const mutationDisabledReason = (mission: MissionListItem) => (
  isTerminalMission(mission) ? '' : '运行中的任务不能归档或删除'
)

const loadMissions = async () => {
  controller?.abort()
  controller = new AbortController()
  const requestController = controller
  loading.value = true
  errorMessage.value = ''
  try {
    const response = await agentosApi.listMissions({ page: 1, pageSize: 100 }, { signal: requestController.signal })
    if (requestController.signal.aborted) return
    missions.value = response.items
  } catch (error: any) {
    if (requestController.signal.aborted || error?.name === 'CanceledError' || error?.name === 'AbortError') return
    errorMessage.value = error?.response?.data?.detail || error?.message || '请稍后重试。'
  } finally {
    if (controller === requestController && !requestController.signal.aborted) loading.value = false
  }
}

const openMission = (mission: MissionListItem) => {
  closeActionMenu()
  void router.push({
    name: 'MissionWorkspace',
    params: { missionId: mission.missionId },
    query: mission.latestRunId ? { runId: mission.latestRunId } : undefined
  })
}

const handleProjectRowKeydown = (event: KeyboardEvent, mission: MissionListItem) => {
  if (event.target !== event.currentTarget) return
  event.preventDefault()
  openMission(mission)
}

const createMission = () => {
  void router.push({ name: 'CreateMission' })
}

const setViewMode = (mode: ProjectViewMode) => {
  viewMode.value = mode
  window.localStorage.setItem(PROJECT_VIEW_MODE_STORAGE_KEY, mode)
}

const closeActionMenu = () => { actionMenu.mission = null }

type ProjectExportFormat = 'md' | 'csv' | 'json' | 'txt'
const PROJECT_EXPORT_FORMAT_LABEL: Record<ProjectExportFormat, string> = { md: 'Markdown', csv: 'CSV', json: 'JSON', txt: 'TXT' }
const exportMenu = reactive<{ open: boolean; mission: MissionListItem | null; x: number; y: number }>({ open: false, mission: null, x: 0, y: 0 })
const exportMenuElement = ref<HTMLElement | null>(null)
const exportButtonElement = ref<HTMLElement | null>(null)

const closeExportMenu = () => {
  exportMenu.open = false
  exportMenu.mission = null
}

const openExportMenuAt = async (anchorX: number, anchorY: number, mission: MissionListItem | null) => {
  exportMenu.mission = mission
  exportMenu.open = true
  await nextTick()
  const width = exportMenuElement.value?.offsetWidth ?? 216
  exportMenu.x = Math.max(8, Math.min(anchorX - width, window.innerWidth - width - 8))
  exportMenu.y = Math.max(8, Math.min(anchorY, window.innerHeight - (exportMenuElement.value?.offsetHeight ?? 160) - 8))
}

const toggleExportMenu = async () => {
  if (exportMenu.open) {
    closeExportMenu()
    return
  }
  const rect = exportButtonElement.value?.getBoundingClientRect()
  await openExportMenuAt(rect ? rect.right : 8, (rect ? rect.bottom : 8) + 6, null)
}

const formatFullDate = (value: string) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}

const missionExportRecord = (mission: MissionListItem) => ({
  name: missionDisplayTitle(mission),
  missionId: mission.missionId,
  status: statusLabel(mission),
  latestRunStatus: mission.latestRunStatus || '',
  runCount: mission.runCount,
  latestRunId: mission.latestRunId || '',
  description: mission.description || '',
  createdAt: formatFullDate(mission.createdAt),
  updatedAt: formatFullDate(mission.updatedAt)
})

const exportProjects = (format: ProjectExportFormat) => {
  const mission = exportMenu.mission
  closeExportMenu()
  if (mission) void exportSingleMission(mission, format)
  else exportProjectList(format)
}

const exportProjectList = (format: ProjectExportFormat) => {
  const items = filteredMissions.value
  if (!items.length) {
    ElMessage.warning('当前没有可导出的项目')
    return
  }
  const exportedAt = new Date().toISOString()
  const filename = `工程项目导出_${exportedAt.replace(/[:.]/g, '-').slice(0, 19)}.${format}`
  if (format === 'json') {
    downloadFile(exportMissionsToJson({ exportedAt, total: items.length, missions: items }), filename, 'application/json;charset=utf-8')
  } else {
    const table = { exportedAt, total: items.length, missions: items.map(missionExportRecord) }
    if (format === 'csv') downloadFile(exportMissionsToCsv(table), filename, 'text/csv;charset=utf-8')
    else if (format === 'md') downloadFile(exportMissionsToMarkdown(table), filename, 'text/markdown;charset=utf-8')
    else downloadFile(exportMissionsToTxt(table), filename, 'text/plain;charset=utf-8')
  }
  showMissionSuccess(`已导出 ${items.length} 个项目（${PROJECT_EXPORT_FORMAT_LABEL[format]}），文件已开始下载`)
}

const sanitizeFilename = (title: string) => (
  title.replace(/[\\/:*?"<>|]/g, '').replace(/\s+/g, ' ').trim().slice(0, 24) || '未命名工程'
)

const missionRunRecord = (run: WorkflowRunSummary) => ({
  runId: run.runId,
  status: run.status,
  statusLabel: runStatusLabel(run.status),
  phase: run.phase,
  phaseLabel: RUN_PHASE_LABELS[run.phase] || run.phase,
  message: run.message || '',
  totalSteps: run.totalSteps ?? 0,
  completedSteps: run.completedSteps ?? 0,
  failedSteps: run.failedSteps ?? 0,
  startedAt: formatFullDate(run.startedAt || ''),
  updatedAt: formatFullDate(run.updatedAt || '')
})

const exportSingleMission = async (mission: MissionListItem, format: ProjectExportFormat) => {
  try {
    const page = await agentosApi.listWorkflowRuns({ missionId: missionIdentity(mission), page: 1, pageSize: 100 })
    const exportedAt = new Date().toISOString()
    const payload: MissionDetailExport = {
      exportedAt,
      mission: {
        missionId: mission.missionId,
        title: missionDisplayTitle(mission),
        description: mission.description || '',
        status: mission.status,
        statusLabel: statusLabel(mission),
        runCount: mission.runCount,
        createdAt: formatFullDate(mission.createdAt),
        updatedAt: formatFullDate(mission.updatedAt)
      },
      totalRuns: page.items.length,
      runs: page.items.map(missionRunRecord)
    }
    const filename = `任务导出_${sanitizeFilename(missionDisplayTitle(mission))}_${exportedAt.replace(/[:.]/g, '-').slice(0, 19)}.${format}`
    if (format === 'json') {
      downloadFile(exportMissionDetailToJson(payload), filename, 'application/json;charset=utf-8')
    } else if (format === 'csv') {
      downloadFile(exportMissionDetailToCsv(payload), filename, 'text/csv;charset=utf-8')
    } else if (format === 'md') {
      downloadFile(exportMissionDetailToMarkdown(payload), filename, 'text/markdown;charset=utf-8')
    } else {
      downloadFile(exportMissionDetailToTxt(payload), filename, 'text/plain;charset=utf-8')
    }
    showMissionSuccess(`已导出「${payload.mission.title}」（${payload.totalRuns} 条运行记录，${PROJECT_EXPORT_FORMAT_LABEL[format]}）`)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || '读取运行记录失败，请稍后重试。')
  }
}

const openActionMenu = async (event: MouseEvent, mission: MissionListItem) => {
  actionMenu.mission = mission
  const target = event.currentTarget as HTMLElement | null
  const rect = target?.getBoundingClientRect()
  actionMenu.x = event.clientX || (rect ? rect.right - 184 : 8)
  actionMenu.y = event.clientY || (rect ? rect.bottom + 6 : 8)
  await nextTick()
  const menu = actionMenuElement.value
  if (!menu) return
  actionMenu.x = Math.max(8, Math.min(actionMenu.x, window.innerWidth - menu.offsetWidth - 8))
  actionMenu.y = Math.max(8, Math.min(actionMenu.y, window.innerHeight - menu.offsetHeight - 8))
}

const copyMissionId = async (missionId: string) => {
  try {
    if (!navigator.clipboard?.writeText) throw new Error('clipboard unavailable')
    await navigator.clipboard.writeText(missionId)
    ElMessage.success('Mission ID 已复制')
  } catch {
    ElMessage.warning('复制失败，请手动选择 Mission ID')
  }
}

const openActionMission = () => {
  const mission = actionMenu.mission
  if (!mission) return
  closeActionMenu()
  void openMission(mission)
}

const copyActionMissionId = () => {
  const mission = actionMenu.mission
  if (!mission) return
  closeActionMenu()
  void copyMissionId(missionIdentity(mission))
}

const exportActionMission = async () => {
  const mission = actionMenu.mission
  if (!mission) return
  const { x, y } = actionMenu
  closeActionMenu()
  await openExportMenuAt(x, y, mission)
}

const missionMutationError = (error: unknown, action: string) => {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown; message?: unknown } } })?.response
  const detail = [response?.data?.message, response?.data?.detail]
    .find(value => typeof value === 'string' && value.trim())
  if (response?.status === 409 && detail === 'mission has active runs') {
    return `任务仍有活动执行，暂时不能${action}`
  }
  if (response?.status === 404) return '任务不存在或当前账户无权操作'
  return typeof detail === 'string' ? `${action}失败：${detail.slice(0, 160)}` : `任务${action}失败，请稍后重试`
}

const removeMission = (missionId: string) => {
  missions.value = missions.value.filter(mission => mission.missionId !== missionId)
}

const missionDisplayTitle = (mission: MissionListItem) => plainMissionTitle(mission.title)

const missionDeleteMessage = (mission: MissionListItem) => {
  const title = missionDisplayTitle(mission)
  return h('div', { class: 'mission-delete-message' }, [
    h('p', { class: 'mission-delete-message__prompt' }, '确定删除以下任务？'),
    h('p', { class: 'mission-delete-message__title', 'aria-label': title }, title),
    h('p', { class: 'mission-delete-message__note' }, '删除后，执行审计事实仍会保留。')
  ])
}

const showMissionSuccess = (message: string) => {
  ElMessage({
    message,
    type: 'success',
    customClass: 'mission-toast mission-toast--success',
    duration: 2400,
    showClose: false,
    offset: 18
  })
}

const archiveActionMission = async () => {
  const mission = actionMenu.mission
  if (!mission || !isTerminalMission(mission)) return
  try {
    await agentosApi.archiveMission(missionIdentity(mission))
    removeMission(missionIdentity(mission))
    closeActionMenu()
    showMissionSuccess('任务已归档')
  } catch (error: unknown) {
    ElMessage.error(missionMutationError(error, '归档'))
  }
}

const deleteActionMission = async () => {
  const mission = actionMenu.mission
  if (!mission || !isTerminalMission(mission)) return
  try {
    await ElMessageBox.confirm(
      missionDeleteMessage(mission),
      '删除任务',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'apple-delete-message-box',
        modalClass: 'apple-delete-message-box__overlay',
        confirmButtonClass: 'apple-delete-confirm-button',
        cancelButtonClass: 'apple-delete-cancel-button',
        roundButton: true,
        showClose: true,
        closeOnClickModal: true
      }
    )
  } catch {
    return
  }
  try {
    await agentosApi.deleteMission(missionIdentity(mission))
    removeMission(missionIdentity(mission))
    closeActionMenu()
    showMissionSuccess('任务已删除')
  } catch (error: unknown) {
    ElMessage.error(missionMutationError(error, '删除'))
  }
}

const handleActionDismiss = (event: PointerEvent) => {
  const target = event.target as Node
  if (!actionMenuElement.value?.contains(target)) closeActionMenu()
  if (!exportMenuElement.value?.contains(target) && !exportButtonElement.value?.contains(target)) closeExportMenu()
}
const handleActionKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    closeActionMenu()
    closeExportMenu()
  }
}

onMounted(() => {
  window.addEventListener('pointerdown', handleActionDismiss)
  window.addEventListener('keydown', handleActionKeydown)
  void loadMissions()
})
onBeforeUnmount(() => {
  controller?.abort()
  window.removeEventListener('pointerdown', handleActionDismiss)
  window.removeEventListener('keydown', handleActionKeydown)
})
</script>

<style scoped>
.project-list { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 34px clamp(24px, 5vw, 76px) 56px; color: var(--text-primary); background: var(--bg-app); }
.project-list__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; max-width: 1040px; width: 100%; margin: 0 auto; padding-bottom: 28px; }
.project-list__eyebrow { color: var(--primary-color); font: 10px var(--font-mono, monospace); letter-spacing: .14em; }
.project-list h1 { margin: 8px 0 5px; font-size: 25px; line-height: 1.2; }
.project-list__header p { margin: 0; color: var(--text-secondary); font-size: 12px; }
/* 按钮配色取自首页花环：白花 #E2E1DA / 松果褐 #482E19 */
.project-list__create, .project-list__state button { display: inline-flex; align-items: center; gap: 7px; border: 1px solid transparent; border-radius: 7px; padding: 10px 15px; color: #482E19; background: #E2E1DA; cursor: pointer; font-size: 12px; }
.project-list__create:hover, .project-list__state button:hover, .project-list__create:focus-visible, .project-list__state button:focus-visible { background: #EFEEE6; }
.project-list__toolbar, .project-list__rows, .project-list__state { max-width: 1040px; width: 100%; margin: 0 auto; }
.project-list__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 14px 0; }
.project-list__search { display: flex; align-items: center; gap: 10px; box-sizing: border-box; width: min(460px, 100%); min-height: 38px; padding: 0 12px; border: 1px solid var(--border-light); border-radius: 9px; color: var(--text-muted); background: color-mix(in srgb, var(--surface-subtle) 82%, transparent); transition: border-color 160ms var(--ease-out), background-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out); }
.project-list__search:focus-within { border-color: color-mix(in srgb, var(--primary-color) 58%, var(--border-light)); background: var(--surface-solid); box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary-color) 12%, transparent); }
.project-list__search .el-icon { flex: 0 0 auto; font-size: 16px; }
.project-list__search input { min-width: 0; width: 100%; border: 0; outline: 0; color: var(--text-primary); background: transparent; font-size: 13px; }
.project-list__search input::placeholder { color: var(--text-muted); opacity: .9; }
.project-list__toolbar-actions { display: flex; align-items: center; gap: 10px; }
.project-list__count { display: inline-flex; align-items: center; min-height: 24px; padding-right: 13px; border-right: 1px solid var(--border-light); color: var(--text-muted); font: 11px var(--font-mono, monospace); white-space: nowrap; }
.project-list__count strong { margin-right: 4px; color: var(--text-secondary); font: 12px var(--font-mono, monospace); }
.project-list__export { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 34px; padding: 0 12px; border: 1px solid var(--border-light); border-radius: 8px; color: var(--text-secondary); background: transparent; cursor: pointer; font-size: 11px; transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out), background-color 160ms var(--ease-out); }
.project-list__export:hover:not(:disabled), .project-list__export:focus-visible { color: var(--text-primary); border-color: var(--primary-line); background: var(--surface-subtle); outline: none; }
.project-list__export:disabled { color: var(--text-disabled); cursor: not-allowed; }
.project-view-toggle { display: inline-flex; align-items: center; gap: 2px; padding: 3px; border: 1px solid var(--border-light); border-radius: 8px; background: var(--surface-subtle); }
.project-view-toggle button { display: inline-flex; align-items: center; justify-content: center; gap: 5px; min-width: 58px; height: 28px; padding: 0 8px; border: 0; border-radius: 6px; color: var(--text-muted); background: transparent; cursor: pointer; font-size: 11px; transition: color 160ms var(--ease-out), background-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out); }
.project-view-toggle button:hover, .project-view-toggle button:focus-visible { color: var(--text-primary); outline: none; }
.project-view-toggle button.is-active { color: var(--primary-color); background: var(--surface-solid); box-shadow: var(--shadow-sm); }
.project-list__rows { padding-top: 18px; }
.project-row { display: grid; grid-template-columns: 40px minmax(0, 1fr) auto 34px 20px; align-items: center; gap: 16px; width: 100%; min-height: 82px; padding: 14px 16px; border: 1px solid transparent; border-radius: 12px; color: inherit; background: transparent; text-align: left; cursor: pointer; transition: background-color 180ms var(--ease-out), border-color 180ms var(--ease-out), box-shadow 180ms var(--ease-out); }
.project-row + .project-row { margin-top: 4px; }
.project-row:hover { border-color: color-mix(in srgb, var(--primary-line) 42%, var(--border-light)); background: color-mix(in srgb, var(--primary-fade) 56%, transparent); box-shadow: var(--shadow-sm); }
.project-row:focus-visible { border-color: var(--primary-line); outline: 2px solid color-mix(in srgb, var(--primary-color) 38%, transparent); outline-offset: 1px; }
.project-row__icon { display: inline-flex; align-items: center; justify-content: center; width: 38px; height: 38px; border: 1px solid color-mix(in srgb, var(--primary-line) 82%, var(--border-light)); border-radius: 10px; color: var(--primary-color); background: color-mix(in srgb, var(--primary-fade) 72%, var(--surface-subtle)); transition: background-color 180ms var(--ease-out), border-color 180ms var(--ease-out), transform 180ms var(--ease-out); }
.project-row:hover .project-row__icon { border-color: var(--primary-line); background: var(--primary-fade); transform: translateY(-1px); }
.project-row__copy { min-width: 0; }
.project-row__copy strong, .project-row__copy span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.project-row__copy strong { color: var(--text-primary); font-size: 14px; font-weight: 600; line-height: 1.4; }
.project-row__copy span { margin-top: 6px; color: var(--text-muted); font: 11px var(--font-mono, monospace); }
.project-row__meta { display: flex; align-items: center; justify-content: flex-end; gap: 18px; color: var(--text-secondary); font-size: 11px; white-space: nowrap; }
.project-row__status { display: inline-flex; align-items: center; gap: 6px; }
.project-row__status i { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); box-shadow: 0 0 0 3px color-mix(in srgb, var(--text-muted) 10%, transparent); }
.project-row__status.is-success i { background: var(--success); }
.project-row__status.is-active i { background: var(--primary-color); }
.project-row__status.is-danger i { background: var(--danger); }
.project-row__actions { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; border: 0; border-radius: 8px; color: var(--text-muted); background: transparent; cursor: pointer; opacity: .28; transition: background-color 160ms var(--ease-out), color 160ms var(--ease-out), opacity 160ms var(--ease-out); }
.project-row:hover .project-row__actions, .project-row:focus-within .project-row__actions { opacity: .82; }
.project-row__actions:hover, .project-row__actions:focus-visible { color: var(--primary-color); background: var(--surface-solid); opacity: 1; outline: none; }
.project-row__arrow { color: var(--text-muted); font-size: 21px; opacity: .45; transition: color 160ms var(--ease-out), opacity 160ms var(--ease-out), transform 160ms var(--ease-out); }
.project-row:hover .project-row__arrow { color: var(--primary-color); opacity: 1; transform: translateX(2px); }
.project-list__rows.is-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; padding-top: 16px; }
.project-row.is-grid { grid-template-columns: 40px minmax(0, 1fr) 32px 20px; align-content: center; min-height: 154px; padding: 18px; border: 1px solid var(--border-light); border-radius: 14px; background: var(--surface-raised); box-shadow: var(--shadow-sm); }
.project-row.is-grid + .project-row.is-grid { margin-top: 0; }
.project-row.is-grid:hover, .project-row.is-grid:focus-visible { border-color: var(--primary-line); box-shadow: var(--shadow-md); }
.project-row.is-grid .project-row__copy strong { font-size: 13px; line-height: 1.5; white-space: normal; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; text-wrap: pretty; }
.project-row.is-grid .project-row__meta { grid-column: 1 / -1; gap: 12px; justify-content: space-between; width: 100%; padding-top: 10px; border-top: 1px solid var(--border-light); font-size: 10px; }
.project-row.is-grid .project-row__meta time { margin-left: auto; }
.project-row.is-grid .project-row__actions { grid-column: 3; grid-row: 1; }
.project-row.is-grid .project-row__arrow { grid-column: 4; grid-row: 1; }
.project-list__state { display: grid; justify-items: center; gap: 8px; padding: 100px 20px; color: var(--text-secondary); text-align: center; }
.project-list__state strong { color: var(--text-primary); font-size: 15px; }
.project-list__state span { font-size: 12px; }
.project-list__state button { margin-top: 8px; }
.project-list__state--error strong { color: var(--danger); }
@media (max-width: 960px) { .project-list__rows.is-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 720px) { .project-list { padding: 24px 18px 40px; } .project-list__header { display: block; } .project-list__create { margin-top: 18px; } .project-list__toolbar { align-items: stretch; flex-direction: column; gap: 12px; padding: 12px 0; } .project-list__search { width: 100%; } .project-list__toolbar-actions { justify-content: flex-end; gap: 8px; flex-wrap: wrap; } .project-view-toggle button { min-width: 30px; padding: 0 7px; } .project-view-toggle button span { display: none; } .project-row { grid-template-columns: 40px minmax(0, 1fr) 32px 20px; gap: 12px; min-height: 76px; padding: 12px; } .project-row__meta { grid-column: 2 / 3; gap: 12px; margin-top: -8px; font-size: 10px; } .project-row__actions { grid-column: 3; grid-row: 1 / 3; } .project-row__arrow { grid-column: 4; grid-row: 1 / 3; } .project-list__rows.is-grid { grid-template-columns: 1fr; } .project-row.is-grid { grid-template-columns: 40px minmax(0, 1fr) 32px 20px; } .project-row.is-grid .project-row__meta { grid-column: 1 / -1; margin-top: 0; } }
</style>

<style>
.project-action-menu { position: fixed; z-index: 3000; box-sizing: border-box; width: 190px; padding: 5px; border: 1px solid var(--border-light); border-radius: var(--radius-card); background: var(--bg-card); box-shadow: var(--shadow-lg); color: var(--text-primary); animation: project-action-menu-in 180ms var(--ease-out) both; }
.project-action-menu button { width: 100%; min-height: 32px; display: grid; grid-template-columns: 20px minmax(0, 1fr); align-items: center; gap: 6px; padding: 0 9px; border: 0; border-radius: var(--radius-control); background: transparent; color: inherit; font: inherit; font-size: 12px; text-align: left; cursor: pointer; }
.project-action-menu button:hover:not(:disabled), .project-action-menu button:focus-visible { background: var(--primary-fade); color: var(--primary-color); outline: none; }
.project-action-menu button.is-danger { color: var(--danger); }
.project-action-menu button:disabled { color: var(--text-disabled); cursor: not-allowed; }
.project-action-menu__separator { height: 1px; margin: 4px 6px; background: var(--border-light); }
.project-export-menu { width: 216px; }
.project-export-menu__context { padding: 4px 9px 5px; border-bottom: 1px solid var(--border-light); margin-bottom: 4px; color: var(--text-muted); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@keyframes project-action-menu-in { from { opacity: 0; transform: translateY(-4px) scale(.98); } to { opacity: 1; transform: translateY(0) scale(1); } }
@media (prefers-reduced-motion: reduce) { .project-action-menu { animation: none; } }
</style>
