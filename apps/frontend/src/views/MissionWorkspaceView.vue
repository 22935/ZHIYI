<template>
  <div class="mission-workspace-view">
    <!-- 320px is the visual default; a deliberate drag may widen the Inspector
         until the shared workbench main-column constraint is reached. -->
    <WorkbenchLayout
      shared-dock-geometry
      :show-right="true"
      :show-bottom-panel="Boolean(projection)"
      bottom-panel-storage-key="zhiyi.mission.workspace.bottom-panel.v1"
      :bottom-panel-default-collapsed="false"
      :bottom-panel-collapsed-height="0"
      :right-pane-min-width="280"
      :right-pane-default-width="320"
      :right-pane-max-width="960"
      storage-key="zhiyi.mission.workspace.layout.v3"
    >
      <template #left>
        <WorkbenchContributionRenderer
          v-if="projection"
          :contribution="sidebarContribution"
          :component-props="sidebarProps"
          @open="openEntry"
          @select-run="selectRun"
          @rerun="rerunSelectedRun"
          @back="returnToProjectList"
        />
        <section v-else class="workspace-loading-pane" aria-label="Workspace loading status">
          <img class="workspace-loading-pane__watermark" src="/logo.webp" alt="" aria-hidden="true" />
          <span class="workspace-loading-pane__mark">MISSION</span>
          <strong>{{ loading ? 'Loading workspace…' : 'Workspace unavailable' }}</strong>
          <span>{{ loadError || '等待 Mission 投影。' }}</span>
          <button v-if="loadError" type="button" @click="loadWorkspace()">Retry</button>
        </section>
      </template>

      <template #main="mainState">
        <section class="workspace-document-surface">
        <div v-if="projection" class="workspace-lifecycle" role="status" aria-live="polite">
          <strong>{{ lifecycleLabels[lifecycle.phase] }}</strong>
          <span>{{ lifecycle.deliveryStatus === 'MISSING' ? 'Completed · Final deliverable missing' : lifecycle.reason }}</span>
          <small>Selected: {{ selectedRunId || '未选择' }} · Latest created: {{ lifecycle.latestRunId || '未观测' }} · Active Runs: {{ activeRunIds.join(', ') || '未观测' }}</small>
          <button type="button" :aria-pressed="editorIntent.mode === 'follow'" @click="enableLifecycleFollow">{{ editorIntent.mode === 'follow' ? 'Following lifecycle' : 'Follow lifecycle' }}</button>
        </div>
        <EditorGroup
          v-if="projection"
          :projection="projection"
          :open-entries="openEntries"
          :active-editor-id="activeEditorId"
          :selected-semantic-task-key="selectedSemanticTaskKey"
          :selected-symbol-id="selectedSymbolId"
          :focus-node-id="focusNodeId"
          :registry="registry"
          :workbench-context="workbenchContext"
          :runtime-store="runtimeStore"
          :inspector-visible="mainState.rightPaneVisible"
          :inspector-auto-hidden="mainState.rightAutoHidden"
          :auxiliary-views="auxiliaryViews"
          :active-auxiliary-id="activeAuxiliaryId"
          :sidebar-hidden="mainState.leftAutoHidden"
          :cancel-pending="cancelPending"
          @restore-sidebar="mainState.restoreLeftPane()"
          @select-inspector="selectInspectorView(mainState)"
          @select-auxiliary="selectAuxiliaryView($event, mainState)"
          @activate="activateEditor"
          @close="closeEditor"
          @editor-status="activeEditorStatus = $event"
          @select-semantic-task="selectSemanticTask"
          @select-symbol="selectRunSymbol"
          @open-semantic-task="openSemanticTask"
          @locate-graph="locateGraph"
          @open-artifact="openEntry"
          @open-entry="openEntry"
          @cancel-run="cancelActiveRun"
          @content-ready="finishForegroundContent"
          @artifact-projection="artifactProjection = $event"
          @semantics-saved="loadWorkspace(selectedRunId || undefined)"
        />
        <section v-else class="workspace-main-state" role="status">
          <img class="workspace-main-state__watermark" src="/logo.webp" alt="" aria-hidden="true" />
          <strong>{{ loading ? 'Loading Mission Workspace…' : 'Mission Workspace unavailable' }}</strong>
          <span>{{ loadError || '请从 Mission 导航进入一个 Project Workspace。' }}</span>
          <button v-if="loadError" type="button" @click="loadWorkspace()">重新加载</button>
        </section>
        </section>
      </template>

      <template #right="rightState">
        <div v-if="projection" class="workspace-inspector-column">
        <WorkbenchAuxiliarySidebar
          v-if="activeAuxiliaryView"
          :view="activeAuxiliaryView"
          :component-props="auxiliaryViewProps"
          @open-file="openWorkspaceFile"
          @select-run="selectRun"
          @refresh-run="loadWorkspace(selectedRunId || undefined)"
          @cancel-run="cancelActiveRun"
        />
        <RuntimeInspector
          v-else
          :entry="inspectorEntry"
          :graph-node="inspectorGraphNode"
          :selected-symbol="selectedSymbol"
          :graph-nodes="projection?.graphNodes || []"
          :entries="projection?.entries || []"
          :artifact-document="inspectorArtifactDocument"
          :available="inspectorAvailable"
          :run-id="projection?.activeRun?.runId || selectedRunId || null"
          :mission-id="missionId"
          :graph="projection?.activeGraph || null"
          :run-status="runtimeObservation?.run?.status || projection?.activeRun?.status || null"
          :historical="isHistorical"
          :runtime-store="runtimeStore"
          :registry="registry"
          :workbench-context="workbenchContext"
          :fullscreen="rightState.rightPaneMaximized"
          @locate-graph="inspectorEntry && locateGraph(inspectorEntry)"
          @open-artifact="openEntry"
          @toggle-fullscreen="rightState.toggleRightPaneMaximized"
          @close="rightState.toggleRightPane"
        />
        </div>
      </template>

      <template #bottom="{ setCollapsed }">
        <WorkbenchBottomPanel
          headerless
          :tabs="panelTabs"
          :active-tab="panelActiveTab"
          @update:active-tab="panelActiveTab = $event"
        >
          <template #default="{ activeTab }">
            <WorkbenchContributionRenderer
              :contribution="resolvePanel(activeTab)"
              :component-props="panelProps(activeTab)"
              @select="selectRuntimeTarget"
              @open-file="openWorkspaceFile"
              @close="setCollapsed(true)"
            />
          </template>
        </WorkbenchBottomPanel>
      </template>

      <template v-if="projection" #status-bar="{ collapsed, setCollapsed }">
        <WorkbenchStatusBar
          :model-value="panelActiveTab"
          :tabs="panelTabs"
          :collapsed="collapsed"
          :editor-status="activeEditorStatus"
          :run-id="projection?.activeRun?.runId || selectedRunId || null"
          :run-status="projection?.activeRun?.status || null"
          :historical="isHistorical"
          :runs="runPickerItems"
          :can-rerun="canRerunSelectedRun"
          :rerun-pending="rerunPending"
          :rerun-disabled-reason="rerunDisabledReason"
          :rerun-label="rerunLabel"
          :deleting-run-id="deletingRunId"
          @update:model-value="selectPanelTab($event, collapsed, setCollapsed)"
          @select-run="selectRun"
          @rerun="rerunSelectedRun"
          @delete-run="deletePickerRun"
          @toggle="setCollapsed(!collapsed)"
        />
      </template>
    </WorkbenchLayout>

    <div
      v-if="loadError && projection"
      class="workspace-request-error"
      :class="{ 'is-collapsed': requestErrorCollapsed }"
      role="alert"
    >
      <span class="workspace-request-error__indicator" aria-hidden="true" />
      <span class="workspace-request-error__message">{{ loadError }}</span>
      <button
        class="workspace-request-error__toggle"
        type="button"
        :aria-expanded="!requestErrorCollapsed"
        :aria-label="requestErrorCollapsed ? '展开错误提示' : '收起错误提示'"
        :title="requestErrorCollapsed ? '展开错误提示' : '收起错误提示'"
        @click="requestErrorCollapsed = !requestErrorCollapsed"
      >
        <span aria-hidden="true">{{ requestErrorCollapsed ? '‹' : '›' }}</span>
      </button>
      <button type="button" @click="loadWorkspace()">重新加载当前 Run</button>
    </div>

    <div v-if="artifactChoices.length" class="artifact-choice" role="dialog" aria-label="选择 Artifact">
      <div class="artifact-choice__panel">
        <header>
          <div>
            <span>同一 semanticTaskKey 下有多个 Artifact</span>
            <strong>{{ selectedSemanticTaskKey }}</strong>
          </div>
          <button type="button" aria-label="关闭 Artifact 选择" @click="artifactChoices = []">×</button>
        </header>
        <button v-for="entry in artifactChoices" :key="entry.entryId" type="button" class="artifact-choice__item" @click="chooseArtifact(entry)">
          <span>{{ entry.name }}</span>
          <code>{{ entry.artifactKey }}</code>
        </button>
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { computed, inject, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, shallowRef, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import { agentosApi, type MissionWorkspaceProjection, type WorkspaceEntry, type WorkspaceFileOpenRequest, type WorkspaceGraphNode } from '@/services/api/agentos'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import EditorGroup, { type OpenWorkspaceEntry } from '@/components/workspace/EditorGroup.vue'
import type { WorkspaceFileEditorStatus } from '@/components/workbench/WorkspaceFileEditor.vue'
import { missionDocumentContent } from '@/components/workspace/missionSemanticDisplay'
import RuntimeInspector from '@/components/workspace/RuntimeInspector.vue'
import WorkbenchBottomPanel, { type WorkbenchBottomTab } from '@/components/workbench/WorkbenchBottomPanel.vue'
import WorkbenchStatusBar from '@/components/workbench/WorkbenchStatusBar.vue'
import WorkbenchContributionRenderer from '@/components/workbench/WorkbenchContributionRenderer.vue'
import WorkbenchAuxiliarySidebar from '@/components/workbench/WorkbenchAuxiliarySidebar.vue'
import { createNativeWorkbenchRegistry } from '@/workbench/composition'
import { registerOpenFile } from '@/workbench/core/openFileRequest'
import { createWorkbenchContext } from '@/workbench/context'
import { RuntimeObservationAdapter, type RuntimeObservation, type RuntimeSelection } from '@/workbench/runtime/observation'
import { acquireRunRuntimeStore, releaseRunRuntimeStore, type RunRuntimeStore } from '@/workbench/runtime/runtimeEvents'
import type { RunDocumentSymbol } from '@/workbench/runtime/runDocument'
import type { ArtifactDocumentModel } from '@/workbench/runtime/artifactProjection'
import { beginRunRecovery, pendingRunRecovery, completeRunRecovery } from '@/workbench/runtime/recoveryIdentity'
import { readRunCapabilities } from '@/workbench/runtime/runCapabilities'
import { conversationBindingKey } from '@/features/workspace/navigation'
import { lifecycleLabels } from '@/features/workspace/runLifecycle'
import { projectLifecycle } from '@/workbench/runtime/lifecycleProjection'
import { initialEditorIntent, selectLifecycleEditor } from '@/workbench/runtime/editorSelection'

const route = useRoute()
const router = useRouter()
const hasConversationBinding = inject(conversationBindingKey, () => false)
let viewActive = true
let suspended = false
const isWorkspaceVisible = () => viewActive && router.currentRoute.value.path === route.path
const emit = defineEmits<{
  'open-workspace-file': [request: WorkspaceFileOpenRequest]
}>()
const openWorkspaceFile = (request: WorkspaceFileOpenRequest) => {
  editorIntent.value.mode = 'user'
  const id = `local-file:${request.missionId}:${request.desktopWorkspaceId || request.workspaceRoot}:${request.relativePath}`
  if (openEditors.value.includes(id)) { activeEditorId.value = id; return }
  openEntry({entryId: id, kind: 'local_file',
    name: request.name, title: request.relativePath, group: 'files', displayOrder: 0,
    metadata: {fileRequest: request}})
  emit('open-workspace-file', request)
}
const missionId = computed(() => String(route.params.missionId || route.query.missionId || ''))
const registry = createNativeWorkbenchRegistry()

const projection = ref<MissionWorkspaceProjection | null>(null)
const loading = ref(false)
const loadError = ref('')
const requestErrorCollapsed = ref(false)
const activeAuxiliaryId = ref<string | null>(null)
const rerunPending = ref(false)
let recoveryUiGeneration = 0
const cancelPending = ref(false)
const selectedRunId = ref<string | null>(typeof route.query.runId === 'string' ? route.query.runId : null)
watch(selectedRunId, () => { recoveryUiGeneration++; rerunPending.value = false }, { flush: 'sync' })
const activeRunIds = computed(() => (projection.value?.runs || []).flatMap(run => {
  const capabilities = readRunCapabilities(run.actionCapabilities, missionId.value, run.runId)
  return capabilities?.isExecutionActive && !capabilities.isSuperseded ? [run.runId] : []
}))
const openEditors = ref<string[]>([])
const activeEditorId = ref<string | null>(null)
// 活动文件编辑器的元信息（语言/编码/行数/行列），转交给窗口底部状态栏展示。
const activeEditorStatus = ref<WorkspaceFileEditorStatus | null>(null)
const selectedSemanticTaskKey = ref<string | null>(null)
const selectedSymbolId = ref<string | null>(null)
const selectedSymbolType = ref<RunDocumentSymbol['type'] | null>(null)
const selectedSymbol = ref<RunDocumentSymbol | null>(null)
const artifactProjection = shallowRef<{ entryId: string; projection: ArtifactDocumentModel } | null>(null)
const focusNodeId = ref<string | null>(null)
const selectedGraphNodeId = ref<string | null>(null)
// Runtime observations can contain tens of thousands of immutable trace rows.
// The snapshot is replaced as a whole, so deep Vue proxies only add work here.
const runtimeObservation = shallowRef<RuntimeObservation | null>(null)
const runtimeStore = shallowRef<RunRuntimeStore | null>(null)
const lifecycle = computed(() => projectLifecycle({ workspace: projection.value, selectedRunId: selectedRunId.value,
  run: runtimeObservation.value?.runId === selectedRunId.value ? runtimeObservation.value.run : null }))
const editorIntent = ref(initialEditorIntent())
let runtimeStoreRunId: string | null = null
const artifactChoices = ref<WorkspaceEntry[]>([])
const entryCache = ref<Record<string, WorkspaceEntry>>({})
let controller: AbortController | null = null
const runtimeObservationAdapter = new RuntimeObservationAdapter()
let pendingObservation: { runId: string; start: () => void } | null = null
const finishForegroundContent = (runId: string | null) => {
  if (!pendingObservation || pendingObservation.runId !== runId) return
  const pending = pendingObservation
  pendingObservation = null
  if (selectedRunId.value === runId) pending.start()
}

const workspaceProjectionRetryDelays = [
  250, 500, 1000, 2000, 3000,
  ...Array.from({ length: 23 }, () => 5000)
]

// Run Progress is a first-class editor entry. Its identity is scoped to the Run
// so reopening/history switching cannot silently reuse another Run's document.
const progressEntryFor = (runId: string | null): WorkspaceEntry => ({
  entryId: runId ? `run:${runId}:progress` : 'overview:progress',
  kind: 'progress',
  name: '运行进度',
  title: '运行进度',
  group: 'overview',
  displayOrder: -1,
  runId,
  status: runId ? projection.value?.activeRun?.status || null : null,
  isActive: Boolean(runId)
})
const entriesWithProgress = computed<WorkspaceEntry[]>(() => {
  if (!projection.value) return []
  const progressEntry = progressEntryFor(projection.value.activeRun?.runId || selectedRunId.value)
  const projectedEntries = projection.value.entries
  const projectedRunIds = new Set(projectedEntries
    .filter(entry => entry.kind === 'run' && entry.runId)
    .map(entry => entry.runId))
  const runtimeRunEntries: WorkspaceEntry[] = projection.value.runs
    .filter(run => !projectedRunIds.has(run.runId))
    .map((run, index) => ({
      entryId: `run:${run.runId}`,
      kind: 'run',
      name: run.runId,
      group: 'runs',
      displayOrder: index,
      runId: run.runId,
      status: run.status,
      parentRunId: run.parentRunId,
      sourceRunId: run.sourceRunId,
      createdAt: run.createdAt,
      completedAt: run.completedAt,
      isActive: run.isActive
    }))
  const missionEntry: WorkspaceEntry[] = projectedEntries.some(entry => entry.entryId === 'overview:mission.md')
    ? []
    : [{
        entryId: 'overview:mission.md',
        kind: 'virtual_document',
        name: 'mission.md',
        group: 'overview',
        displayOrder: 1,
        content: missionDocumentContent(projection.value)
      }]
  return [progressEntry, ...missionEntry, ...projectedEntries, ...runtimeRunEntries]
})
const augmentedProjection = computed<MissionWorkspaceProjection | null>(() => (
  projection.value ? { ...projection.value, entries: entriesWithProgress.value } : null
))
const entriesById = computed(() => new Map(entriesWithProgress.value.map(entry => [entry.entryId, entry])))
const openEntries = computed<OpenWorkspaceEntry[]>(() => openEditors.value.flatMap(entryId => {
  const current = entriesById.value.get(entryId)
  const snapshot = entryCache.value[entryId]
  if (!current && !snapshot) return []
  return [{ entry: current || snapshot, available: Boolean(current) || snapshot?.kind === 'local_file' }]
}))
const activeOpened = computed(() => openEntries.value.find(item => item.entry.entryId === activeEditorId.value) || null)
const inspectorEntry = computed(() => activeOpened.value?.entry || null)
const inspectorArtifactDocument = computed(() => (
  artifactProjection.value && artifactProjection.value.entryId === inspectorEntry.value?.entryId
    ? artifactProjection.value.projection
    : null
))
const inspectorAvailable = computed(() => activeOpened.value?.available ?? false)
const inspectorGraphNode = computed<WorkspaceGraphNode | null>(() => {
  if (inspectorEntry.value?.kind === 'task') {
    return projection.value?.graphNodes.find(node => node.semanticTaskKey === inspectorEntry.value?.semanticTaskKey) || null
  }
  if (inspectorEntry.value?.kind !== 'graph' && inspectorEntry.value?.kind !== 'artifact') {
    return projection.value?.graphNodes.find(node => node.acgNodeId === selectedGraphNodeId.value) || null
  }
  if (inspectorEntry.value.kind === 'artifact') return null
  return projection.value?.graphNodes.find(node => node.acgNodeId === selectedGraphNodeId.value) || null
})
const isHistorical = computed(() => lifecycle.value.isHistorical)
const controlReadOnly = computed(() => lifecycle.value.isReadOnly || loading.value || Boolean(loadError.value))
const canRerunSelectedRun = computed(() => Boolean(
  projection.value?.activeRun?.runId && (lifecycle.value.capabilities?.canRetrySuccessor || lifecycle.value.capabilities?.canRerunSuccessor)
))
const shouldResumeSelectedRun = computed(() => lifecycle.value.capabilities?.canRetrySuccessor === true)
const canCancelActiveRun = computed(() => Boolean(
  projection.value?.activeRun?.runId
  && !controlReadOnly.value
  && lifecycle.value.capabilities?.canCancel === true
  && !cancelPending.value
))
const rerunDisabledReason = computed(() => {
  if (rerunPending.value) return '正在创建新的 Run'
  if (!canRerunSelectedRun.value) return '服务端未提供创建后继 Run 的能力'
  return shouldResumeSelectedRun.value
    ? '复用已完成节点，从失败节点继续执行'
    : '从当前 Run 创建新的执行版本'
})
const rerunLabel = computed(() => shouldResumeSelectedRun.value
  ? runtimeObservation.value?.run?.steps.length === 0 ? '重新运行（新 Run）' : '从失败处继续（新 Run）'
  : '再次运行')

const workbenchContext = computed(() => createWorkbenchContext({
  missionId: missionId.value,
  runId: projection.value?.activeRun?.runId || selectedRunId.value || null,
  selectedSemanticTaskKey: selectedSemanticTaskKey.value,
  selectedArtifactId: selectedSymbol.value?.artifactId || inspectorEntry.value?.artifactId || null,
  selectedAcgNodeId: selectedGraphNodeId.value,
  selectedSymbolId: selectedSymbolId.value,
  selectedSymbolType: selectedSymbolType.value,
  activeEditorId: activeEditorId.value,
  activeEntryKind: activeOpened.value?.entry.kind || null,
  historicalMode: isHistorical.value,
  diagnostics: projection.value?.diagnostics || [],
  runtimeObservation: runtimeObservation.value,
  lifecycle: lifecycle.value
}))

const auxiliaryViews = computed(() => registry.getAuxiliaryViews(workbenchContext.value))
const activeAuxiliaryView = computed(() => (
  activeAuxiliaryId.value
    ? registry.resolveAuxiliaryView(activeAuxiliaryId.value, workbenchContext.value)
    : null
))
const auxiliaryViewProps = computed(() => ({
  entry: inspectorEntry.value,
  graphNode: inspectorGraphNode.value,
  graphNodes: projection.value?.graphNodes || [],
  graph: projection.value?.activeGraph || null,
  runId: projection.value?.activeRun?.runId || selectedRunId.value || null,
  runStatus: projection.value?.activeRun?.status || null,
  runtimeObservation: runtimeObservation.value,
  missionId: missionId.value,
  canCancel: canCancelActiveRun.value,
  cancelPending: cancelPending.value,
  historical: isHistorical.value,
  readonly: controlReadOnly.value,
  actionCapabilities: lifecycle.value.capabilities,
  ...(activeAuxiliaryView.value?.getProps?.(workbenchContext.value) || {})
}))
type RightPaneState = {
  rightPaneVisible: boolean
  toggleRightPane: () => void
}

const selectInspectorView = (pane: RightPaneState) => {
  editorIntent.value.mode = 'user'
  if (activeAuxiliaryId.value) {
    activeAuxiliaryId.value = null
    if (!pane.rightPaneVisible) pane.toggleRightPane()
    return
  }
  pane.toggleRightPane()
}

const selectAuxiliaryView = (viewId: string, pane: RightPaneState) => {
  editorIntent.value.mode = 'user'
  if (activeAuxiliaryId.value === viewId) {
    pane.toggleRightPane()
    return
  }
  activeAuxiliaryId.value = viewId
  if (!pane.rightPaneVisible) pane.toggleRightPane()
}

const sidebarContribution = computed(() => registry.getSidebarViews(workbenchContext.value)[0] || null)
const sidebarProps = computed(() => ({
  projection: augmentedProjection.value,
  activeEditorId: activeEditorId.value,
  selectedSemanticTaskKey: selectedSemanticTaskKey.value,
  selectedRunId: selectedRunId.value
}))

const runPickerItems = computed(() => (projection.value?.runs || [])
  .map(run => ({ runId: run.runId, status: run.status || null,
    canDelete: readRunCapabilities(run.actionCapabilities, missionId.value, run.runId)?.canDelete === true })))
const panelTabs = computed<WorkbenchBottomTab[]>(() => registry.getPanels(workbenchContext.value).map(panel => ({
  id: panel.id,
  label: panel.label,
  count: panel.count?.(workbenchContext.value),
  tone: panel.tone
})))

const BOTTOM_PANEL_STORAGE_KEY = 'zhiyi.mission.workspace.bottom-panel.v1'
const readPersistedPanelTab = () => {
  if (typeof window === 'undefined') return ''
  try {
    const value = window.localStorage.getItem(`${BOTTOM_PANEL_STORAGE_KEY}.activeTab`)
    return value && panelTabs.value.some(tab => tab.id === value) ? value : panelTabs.value[0]?.id || ''
  } catch {
    return panelTabs.value[0]?.id || ''
  }
}
const panelActiveTab = ref(readPersistedPanelTab())
watch(panelActiveTab, value => {
  if (typeof window === 'undefined' || !value) return
  try { window.localStorage.setItem(`${BOTTOM_PANEL_STORAGE_KEY}.activeTab`, value) } catch { /* storage is optional */ }
})
watch(panelTabs, tabs => {
  if (!tabs.some(tab => tab.id === panelActiveTab.value)) panelActiveTab.value = tabs[0]?.id || ''
})

const selectPanelTab = (tabId: string, collapsed: boolean, setCollapsed: (value: boolean) => void) => {
  panelActiveTab.value = tabId
  if (collapsed) setCollapsed(false)
}
const resolvePanel = (panelId: string) => registry.resolvePanel(panelId, workbenchContext.value)
const panelProps = (panelId: string) => resolvePanel(panelId)?.getProps?.(workbenchContext.value) || {}

const followLifecycle = () => {
  if (!projection.value || !isWorkspaceVisible()) return
  const selection = selectLifecycleEditor(editorIntent.value, lifecycle.value)
  editorIntent.value = selection.intent
  if (!selection.handoff) return
  activeAuxiliaryId.value = ['review', 'formal'].includes(lifecycle.value.recommendedInspector) ? 'acg-copilot.sidebar' : null
  if (!openEditors.value.length) {
    const progress = progressEntryFor(selectedRunId.value)
    if (lifecycle.value.recommendedEditor === 'progress') { entryCache.value[progress.entryId] = progress; openEditors.value.push(progress.entryId) }
    const seeds = [...projection.value.entries.filter(entry => entry.kind === 'virtual_document'), ...projection.value.entries.filter(entry => entry.kind === 'graph')]
    for (const seed of seeds) {
      entryCache.value[seed.entryId] = seed
      openEditors.value.push(seed.entryId)
    }
  }
  const entry = lifecycle.value.recommendedEntryId
    ? entriesById.value.get(lifecycle.value.recommendedEntryId)
    : lifecycle.value.recommendedEditor === 'mission'
      ? entriesById.value.get('overview:mission.md') : progressEntryFor(selectedRunId.value)
  if (entry) openEntry(entry, true)
}
const enableLifecycleFollow = () => { editorIntent.value = { ...editorIntent.value, mode: 'follow', handled: null }; followLifecycle() }
const activateEditor = (id: string) => { editorIntent.value.mode = 'user'; activeEditorId.value = id }

const syncProgressEditorIdentity = (nextProjection: MissionWorkspaceProjection, requestedRunId: string | null) => {
  const nextEntry = progressEntryFor(nextProjection.activeRun?.runId || requestedRunId)
  const currentId = openEditors.value.find(entryId => entryCache.value[entryId]?.kind === 'progress')
  if (!currentId || currentId === nextEntry.entryId) {
    entryCache.value[nextEntry.entryId] = nextEntry
    return
  }
  const index = openEditors.value.indexOf(currentId)
  openEditors.value.splice(index, 1, nextEntry.entryId)
  entryCache.value[nextEntry.entryId] = nextEntry
  if (activeEditorId.value === currentId) activeEditorId.value = nextEntry.entryId
}

const focusProgressEditor = (nextProjection: MissionWorkspaceProjection, requestedRunId: string | null) => {
  const runId = nextProjection.activeRun?.runId || requestedRunId
  if (!runId) return
  const nextEntry = progressEntryFor(runId)
  const currentId = openEditors.value.find(entryId => (
    entryId === 'overview:progress' || entryCache.value[entryId]?.kind === 'progress'
  ))
  if (currentId && currentId !== nextEntry.entryId) {
    const index = openEditors.value.indexOf(currentId)
    if (index >= 0) openEditors.value.splice(index, 1, nextEntry.entryId)
  } else if (!openEditors.value.includes(nextEntry.entryId)) {
    openEditors.value.unshift(nextEntry.entryId)
  }
  entryCache.value[nextEntry.entryId] = nextEntry
  activeEditorId.value = nextEntry.entryId
}

const responseStatus = (error: unknown) => {
  const status = (error as { response?: { status?: unknown } })?.response?.status
  return typeof status === 'number' ? status : null
}

const isAbortError = (error: unknown) => {
  const name = (error as { name?: unknown })?.name
  return name === 'CanceledError' || name === 'AbortError'
}

const waitForWorkspaceRetry = (delayMs: number, signal: AbortSignal) => new Promise<void>((resolve, reject) => {
  let timer: ReturnType<typeof setTimeout> | null = setTimeout(finish, delayMs)
  const onAbort = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
    signal.removeEventListener('abort', onAbort)
    reject(new DOMException('Workspace projection request aborted', 'AbortError'))
  }
  function finish() {
    timer = null
    signal.removeEventListener('abort', onAbort)
    resolve()
  }
  if (signal.aborted) {
    onAbort()
    return
  }
  signal.addEventListener('abort', onAbort, { once: true })
})

// Java 网关对 AgentOS GET 的预算只有几秒；活跃 Run 执行高峰时投影查询可能暂时
// 超时变成 502/503/504。这类瞬时抖动与 404（投影未注册）一样按退避梯子重试。
const TRANSIENT_PROJECTION_STATUSES = new Set([502, 503, 504])

const requestWorkspaceProjection = async (runId: string | null, signal: AbortSignal) => {
  let projectionPending = false
  let attempt = 0
  while (true) {
    try {
      return await agentosApi.getMissionWorkspace(missionId.value, {
        runId: runId || undefined,
        signal
      })
    } catch (error: unknown) {
      const status = responseStatus(error)
      if ((error as { response?: { data?: { code?: string } } })?.response?.data?.code === 'AGENTOS_CONTRACT_INVALID') {
        throw error
      }
      const transientFailure = status !== null && TRANSIENT_PROJECTION_STATUSES.has(status)
      const pendingProjection404 = !transientFailure && Boolean(runId) && status === 404
      if ((!transientFailure && !pendingProjection404) || attempt >= workspaceProjectionRetryDelays.length) {
        throw error
      }

      if (pendingProjection404 && !projectionPending && runId) {
        try {
          const runtimeRun = await agentosApi.getWorkflowRun(runId, { signal })
          projectionPending = runtimeRun.missionId === missionId.value
        } catch (runtimeError: unknown) {
          if (isAbortError(runtimeError)) throw runtimeError
          throw error
        }
        if (!projectionPending) throw error
      }

      await waitForWorkspaceRetry(workspaceProjectionRetryDelays[attempt], signal)
      attempt += 1
    }
  }
}

// 降级投影重拉：PLANNING_PROJECTION_PENDING 表示 identity graph 尚未注册，
// Run 活跃期间周期性重拉投影，注册完成后 STEPS/OUTPUT/RUNS/Graph 即刻出现。
const PROJECTION_REFRESH_MS = 8000
const ACTIVE_PROJECTION_RUN_STATUSES = new Set(['pending', 'planning', 'running', 'retrying', 'waiting_review'])
let projectionRefreshTimer: ReturnType<typeof setTimeout> | null = null

const stopProjectionRefresh = () => {
  if (projectionRefreshTimer !== null) {
    clearTimeout(projectionRefreshTimer)
    projectionRefreshTimer = null
  }
}

const projectionActive = (projection: MissionWorkspaceProjection) => (
  ACTIVE_PROJECTION_RUN_STATUSES.has(projection.activeRun?.status || '')
)

const scheduleProjectionRefresh = () => {
  stopProjectionRefresh()
  if (!isWorkspaceVisible()) return
  projectionRefreshTimer = setTimeout(async () => {
    projectionRefreshTimer = null
    if (!viewActive || loading.value) return
    const projectionSnapshot = projection.value
    if (projectionSnapshot) await loadWorkspace(selectedRunId.value)
  }, PROJECTION_REFRESH_MS)
}

const loadWorkspace = async (runId = selectedRunId.value, options: { focusProgress?: boolean } = {}) => {
  if (!isWorkspaceVisible()) return
  if (!missionId.value) {
    loadError.value = '缺少 missionId，无法加载 Mission Workspace。'
    return
  }
  // Keep the rendered projection and runtime observation visible while the
  // periodic projection refresh is in flight. Clearing them here made the
  // inspector and bottom panels flash on every refresh cycle.
  const runSelectionChanged = Boolean(
    runId
    && projection.value?.activeRun?.runId
    && projection.value.activeRun.runId !== runId
  )
  const preserveRenderedWorkspace = Boolean(projection.value && !runSelectionChanged)
  controller?.abort()
  if (!preserveRenderedWorkspace) {
    pendingObservation = null
    runtimeObservationAdapter.stop()
    runtimeObservation.value = null
    artifactProjection.value = null
    projection.value = null
    if (runSelectionChanged) {
      releaseRunRuntimeStore(runtimeStoreRunId, runtimeStore.value)
      runtimeStore.value = null
      runtimeStoreRunId = null
    }
  }
  if (runId) selectedRunId.value = runId
  stopProjectionRefresh()
  controller = new AbortController()
  const requestController = controller
  if (!preserveRenderedWorkspace) runtimeObservation.value = null
  loading.value = true
  loadError.value = ''
  try {
    const nextProjection = await requestWorkspaceProjection(runId, requestController.signal)
    if (!isWorkspaceVisible() || controller !== requestController || requestController.signal.aborted) return
    if (nextProjection.mission.missionId !== missionId.value
      || (runId && nextProjection.activeRun?.runId !== runId)) throw new Error('Workspace identity mismatch')
    projection.value = nextProjection
    selectedRunId.value = nextProjection.activeRun?.runId || runId || null
    nextProjection.entries.forEach(entry => { entryCache.value[entry.entryId] = entry })
    syncProgressEditorIdentity(nextProjection, runId)
    followLifecycle()
    if (options.focusProgress) { focusProgressEditor(nextProjection, runId); editorIntent.value.mode = 'user' }
    const nextRunId = nextProjection.activeRun?.runId || runId || null
    const streamRunId = projectionActive(nextProjection) ? nextRunId : null
    if (runtimeStoreRunId !== streamRunId) {
      releaseRunRuntimeStore(runtimeStoreRunId, runtimeStore.value)
      runtimeStore.value = acquireRunRuntimeStore(streamRunId)
      runtimeStoreRunId = streamRunId
    }
    if (nextRunId) {
      if (runtimeObservation.value?.runId !== nextRunId) runtimeObservation.value = null
      const startObservation = () => runtimeObservationAdapter.start(nextRunId, {
        historical: !projectionActive(nextProjection),
        diagnostics: nextProjection.diagnostics,
        onUpdate: observation => {
          if (controller === requestController && !requestController.signal.aborted
            && selectedRunId.value === observation.runId && observation.run?.missionId === missionId.value) {
            runtimeObservation.value = observation
          }
        }
      })
      // Give the foreground document the first read slot. Inspector/Trace
      // requests start when its read finishes, including failures.
      const opened = activeOpened.value
      if (!preserveRenderedWorkspace && !runtimeObservation.value && opened?.available && opened.entry.kind === 'artifact'
        && (opened.entry.contentRef || opened.entry.artifactId)) {
        pendingObservation = { runId: nextRunId, start: startObservation }
      } else startObservation()
    }
    // 降级投影等待 identity 注册：活跃 Run 期间周期重拉，直到 PLANNING_PROJECTION_PENDING 消失。
    scheduleProjectionRefresh()
    if (!route.query.runId && selectedRunId.value) void persistRunInUrl(selectedRunId.value)
  } catch (error: unknown) {
    if (!viewActive || controller !== requestController || requestController.signal.aborted) return
    if (isAbortError(error)) return
    // 重试梯子耗尽才到这里：活跃 Run 期间继续周期重拉，抖动恢复后错误条自动
    // 消失；一次网关抖动不应把报错钉在右上角并让工作台停止自愈。
    const status = responseStatus(error)
    loadError.value = status === 401 || status === 403 ? '无权访问所选 Run，未切换到其他 Run。'
      : status === 404 ? '所选 Run 不存在，未切换到其他 Run。' : projection.value
      ? 'Mission Workspace Projection 暂时刷新失败，正在自动重试…'
      : '无法加载 Mission Workspace Projection，请稍后重试。'
    scheduleProjectionRefresh()
  } finally {
    if (controller === requestController && !requestController.signal.aborted) loading.value = false
  }
}

const persistRunInUrl = async (runId: string | null, push = false) => {
  if (!isWorkspaceVisible()) return
  const query = { ...route.query }
  if (runId) query.runId = runId
  else delete query.runId
  await router[push ? 'push' : 'replace']({ query })
}

const selectRun = async (runId: string, userSelected = true) => {
  if (runId === selectedRunId.value && runId === projection.value?.activeRun?.runId && projection.value && !loading.value) {
    const progress = entriesWithProgress.value.find(entry => entry.kind === 'progress')
    if (progress) openEntry(progress)
    return
  }
  selectedRunId.value = runId
  selectedSymbolId.value = null
  selectedSymbolType.value = null
  selectedSymbol.value = null
  selectedSemanticTaskKey.value = null
  selectedGraphNodeId.value = null
  focusNodeId.value = null
  // Retire old facts before the URL changes, including failed new selections.
  controller?.abort()
  runtimeObservationAdapter.stop()
  releaseRunRuntimeStore(runtimeStoreRunId, runtimeStore.value)
  runtimeStore.value = null; runtimeStoreRunId = null
  runtimeObservation.value = null; artifactProjection.value = null; projection.value = null
  if (userSelected) await persistRunInUrl(runId, true)
  await loadWorkspace(runId, { focusProgress: userSelected })
}

const createClientRequestId = () => globalThis.crypto?.randomUUID?.()
  || `rerun-${Date.now()}-${Math.random().toString(36).slice(2)}`

const rerunErrorMessage = (error: unknown) => {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown; message?: unknown } } })?.response
  const detail = [response?.data?.detail, response?.data?.message]
    .find(value => typeof value === 'string' && value.trim())
  if (typeof detail === 'string') return detail
  if (response?.status === 401 || response?.status === 403) return '当前账户无权创建新的 Run'
  if (response?.status === 404) return '当前 Mission 或源 Run 不存在'
  if (response?.status === 422) return '历史运行配置无法用于再次运行'
  return '创建新的 Run 失败，请稍后重试'
}

watch(loadError, (nextError, previousError) => {
  if (!nextError || nextError !== previousError) requestErrorCollapsed.value = false
})

const cancelErrorMessage = (error: unknown) => {
  const status = responseStatus(error)
  if (status === 401 || status === 403) return '当前账户无权停止这个 Run'
  if (status === 404) return '当前 Run 不存在，工作台需要重新加载'
  return '停止运行失败，请稍后重试'
}

const cancelActiveRun = async () => {
  const run = projection.value?.activeRun
  if (!run?.runId || !canCancelActiveRun.value) return
  const expectedRuntimeRevision = lifecycle.value.capabilities!.runtimeRevision
  try {
    await ElMessageBox.confirm(
      '确定要停止当前运行吗？已完成的步骤会保留，后续步骤不再执行。',
      run.status === 'waiting_review' ? '放弃审核' : '停止运行',
      { confirmButtonText: '停止运行', cancelButtonText: '继续运行', type: 'warning' }
    )
  } catch {
    return
  }
  if (selectedRunId.value !== run.runId || !canCancelActiveRun.value) return
  cancelPending.value = true
  loadError.value = ''
  try {
    await agentosApi.cancelWorkflowRun(run.runId, { expectedRuntimeRevision })
    if (selectedRunId.value !== run.runId) return
    runtimeObservation.value = null
    await loadWorkspace(run.runId)
    ElMessage.success('运行已停止')
  } catch (error: unknown) {
    if (responseStatus(error) === 409) {
      ElMessage.warning('该运行已结束，无需停止')
      await loadWorkspace(run.runId)
    } else {
      ElMessage.error(cancelErrorMessage(error))
    }
  } finally {
    cancelPending.value = false
  }
}

const rerunSelectedRun = async () => {
  const sourceRunId = projection.value?.activeRun?.runId
  if (!sourceRunId || !canRerunSelectedRun.value || rerunPending.value) return
  const { canRetrySuccessor, runtimeRevision, retryStepId } = lifecycle.value.capabilities!
  rerunPending.value = true
  loadError.value = ''
  const sourceMission = missionId.value
  const ownerGeneration = recoveryUiGeneration
  const stillSelected = () => ownerGeneration === recoveryUiGeneration && isWorkspaceVisible()
    && missionId.value === sourceMission && selectedRunId.value === sourceRunId
  try {
    let identity = pendingRunRecovery(sourceMission, sourceRunId, sessionStorage)
    if (!identity && canRetrySuccessor) {
      const sourceRun = await agentosApi.getWorkflowRun(sourceRunId)
      if (sourceRun.runId !== sourceRunId || sourceRun.missionId !== sourceMission) throw new Error('源 Run 身份不匹配')
      if (sourceRun.runtimeRevision !== runtimeRevision) throw new Error('源 Run 版本已变化，请刷新能力后重试')
      const failedStep = sourceRun.steps.find(step => step.stepId === retryStepId && step.status === 'failed')
      if (!failedStep) throw new Error('服务端恢复目标已变化，禁止改为其他恢复操作')
      identity = beginRunRecovery(sourceMission, sourceRunId, { kind: 'retry', stepId: failedStep.stepId, payload: {
        clientRequestId: createClientRequestId(),
        reason: 'resume_failed',
        expectedRuntimeRevision: runtimeRevision,
        mode: 'successor_run'
      } }, sessionStorage)
    }
    if (!identity) {
      const history = await agentosApi.getWorkflowHistoryConfig(sourceRunId)
      if (history.runId !== sourceRunId) throw new Error('源配置身份不匹配')
      identity = beginRunRecovery(sourceMission, sourceRunId, { kind: 'rerun', payload: {
      reviewMode: history.reviewMode || 'auto',
      input: history.input || {},
      enabledPluginIds: history.enabledPluginIds || null,
      clientRequestId: createClientRequestId(),
      sourceRunId,
      rerunReason: 'manual_rerun'
      } }, sessionStorage)
    }
    const nextRun = identity.kind === 'retry'
      ? await agentosApi.retryWorkflowStepAsync(sourceRunId, identity.stepId, identity.payload)
      : await agentosApi.rerunWorkflowAsync(sourceMission, identity.payload)
    if (nextRun.missionId !== sourceMission || nextRun.runId === sourceRunId
      || nextRun.lineage?.sourceRunId !== sourceRunId) throw new Error('Successor 响应身份或 lineage 不匹配，保留原操作等待核对')
    completeRunRecovery(identity, sessionStorage)
    if (stillSelected()) await selectRun(nextRun.runId)
  } catch (error: unknown) {
    if (stillSelected() && !isAbortError(error)) loadError.value = `${rerunErrorMessage(error)}；结果未确认时将重试同一操作。`
  } finally {
    if (ownerGeneration === recoveryUiGeneration) rerunPending.value = false
  }
}

const deletingRunId = ref<string | null>(null)

const deleteRunErrorMessage = (error: unknown) => {
  const status = responseStatus(error)
  if (status === 401 || status === 403) return '当前账户无权删除这个 Run'
  if (status === 404) return 'Run 不存在或已被删除'
  if (status === 409) return '运行尚未结束，暂时不能删除'
  return '删除 Run 失败，请稍后重试'
}

const deletePickerRun = async (runId: string) => {
  if (deletingRunId.value) return
  const source = projection.value?.runs.find(item => item.runId === runId)
  if (!readRunCapabilities(source?.actionCapabilities, missionId.value, runId)?.canDelete) return
  try {
    await ElMessageBox.confirm(
      `Run ${runId} 将从运行列表移除，执行审计事实仍会保留。`,
      '删除 Run',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'destructive-confirm',
        confirmButtonClass: 'el-button--danger'
      }
    )
  } catch {
    return
  }
  deletingRunId.value = runId
  loadError.value = ''
  try {
    await agentosApi.deleteWorkflowRun(runId)
    ElMessage.success(`Run ${runId} 已删除`)
    const remaining = (projection.value?.runs || []).filter(item => item.runId !== runId)
    if (selectedRunId.value === runId || projection.value?.activeRun?.runId === runId) {
      // 被删的是当前 Run：优先切到剩余 Run 的默认选择，全部删完则回到
      // Mission 级空工作区。
      const nextRunId = null
      selectedRunId.value = nextRunId
      await persistRunInUrl(nextRunId)
      await loadWorkspace(nextRunId)
      return
    }
    await loadWorkspace()
  } catch (error: unknown) {
    if (!isAbortError(error)) ElMessage.error(deleteRunErrorMessage(error))
  } finally {
    deletingRunId.value = null
  }
}

const openEntry = (entry: WorkspaceEntry, system = false) => {
  if (!system) editorIntent.value.mode = 'user'
  entryCache.value[entry.entryId] = entry
  if (!openEditors.value.includes(entry.entryId)) openEditors.value.push(entry.entryId)
  activeEditorId.value = entry.entryId
  artifactChoices.value = []
  if (entry.kind === 'task' || entry.kind === 'artifact') {
    const type = entry.kind
    selectedSymbolType.value = type
    selectedSymbolId.value = `${type}:${entry.kind === 'artifact' ? (entry.artifactKey || entry.artifactId || entry.entryId) : (entry.semanticTaskKey || entry.acgNodeId || entry.entryId)}`
    selectedSymbol.value = {
      id: selectedSymbolId.value,
      type,
      status: ['completed', 'succeeded'].includes(entry.status || '') ? 'completed' : ['failed', 'cancelled'].includes(entry.status || '') ? 'failed' : ['running', 'pending', 'planning'].includes(entry.status || '') ? 'running' : 'pending',
      title: entry.name,
      subtitle: entry.semanticTaskKey || entry.artifactKey || undefined,
      runId: entry.runId || projection.value?.activeRun?.runId || '',
      semanticTaskKey: entry.semanticTaskKey,
      graphNodeId: entry.acgNodeId,
      artifactKey: entry.artifactKey,
      artifactId: entry.artifactId,
      children: []
    }
    if (entry.semanticTaskKey) selectSemanticTask(entry.semanticTaskKey)
  } else if (entry.kind !== 'progress' && entry.kind !== 'run') {
    selectedSymbolId.value = null
    selectedSymbolType.value = null
    selectedSymbol.value = null
  }
}

const confirmFileNavigation = () => !openEntries.value.some(item => item.entry.metadata?.dirty)
  || window.confirm('文件尚未保存，离开将放弃修改。是否继续？')
// This guard also protects a dirty Mission while it is hidden in the cache.
// A second Mission replaces that cache slot; cancellation must happen first.
const removeFileNavigationGuard = router.beforeEach(to => {
  if (to.path === `/agentos/missions/${encodeURIComponent(missionId.value)}/workspace`) return true
  const context = typeof to.query.contextId === 'string' ? to.query.contextId
    : localStorage.getItem('chat.workflow_draft_conversation_id') || ''
  if (to.path === '/chat' && to.query.newConversation !== '1'
    && to.query.missionId === missionId.value && to.query.runId === selectedRunId.value
    && hasConversationBinding(context, missionId.value, selectedRunId.value)) return true
  return confirmFileNavigation()
})

const closeEditor = (entryId: string) => {
  if (entryCache.value[entryId]?.metadata?.dirty && !window.confirm('文件尚未保存，确定关闭并放弃修改？')) return
  const index = openEditors.value.indexOf(entryId)
  if (index < 0) return
  editorIntent.value.mode = 'user'
  openEditors.value.splice(index, 1)
  if (activeEditorId.value !== entryId) return
  activeEditorId.value = openEditors.value[Math.max(0, index - 1)] || openEditors.value[0] || null
}

const selectSemanticTask = (semanticTaskKey: string | null) => {
  selectedSemanticTaskKey.value = semanticTaskKey
  selectedGraphNodeId.value = projection.value?.graphNodes.find(node => node.semanticTaskKey === semanticTaskKey)?.acgNodeId || null
  if (selectedGraphNodeId.value) focusNodeId.value = selectedGraphNodeId.value
}

const selectRunSymbol = (item: RunDocumentSymbol) => {
  selectedSymbolId.value = item.id
  selectedSymbolType.value = item.type
  selectedSymbol.value = item
  if (item.graphNodeId) {
    selectedGraphNodeId.value = item.graphNodeId
    focusNodeId.value = item.graphNodeId
  }
  if (item.semanticTaskKey) selectSemanticTask(item.semanticTaskKey)
}

const selectRuntimeTarget = (selection: RuntimeSelection) => {
  const node = projection.value?.graphNodes.find(item => (
    (selection.stepId && item.acgNodeId === selection.stepId)
    || (selection.semanticTaskKey && item.semanticTaskKey === selection.semanticTaskKey)
  ))
  if (!node) return
  selectedSemanticTaskKey.value = node.semanticTaskKey || null
  selectedGraphNodeId.value = node.acgNodeId
  focusNodeId.value = node.acgNodeId
  const graphEntry = projection.value?.entries.find(item => item.kind === 'graph')
  if (graphEntry && inspectorEntry.value?.kind === 'artifact') openEntry(graphEntry)
}

const openSemanticTask = (semanticTaskKey: string | null) => {
  selectSemanticTask(semanticTaskKey)
  if (!semanticTaskKey || !projection.value) return
  const task = projection.value.entries.find(entry => entry.kind === 'task' && entry.semanticTaskKey === semanticTaskKey)
  if (task) {
    openEntry(task)
    return
  }
  const artifacts = projection.value.entries.filter(entry => entry.kind === 'artifact' && entry.semanticTaskKey === semanticTaskKey)
  if (artifacts.length === 1) {
    openEntry(artifacts[0])
  } else if (artifacts.length > 1) {
    artifactChoices.value = artifacts
  }
}

const chooseArtifact = (entry: WorkspaceEntry) => {
  artifactChoices.value = []
  openEntry(entry)
}

const returnToProjectList = () => {
  void router.push({ name: 'AcgVisualization' })
}

const locateGraph = (entry: WorkspaceEntry) => {
  if (!projection.value) return
  // Run Progress 的 ACG Compile 直接携带 graph entry：打开既有 Graph Editor 即可。
  if (entry.kind === 'graph') {
    openEntry(entry)
    return
  }
  if (entry.identityQuality === 'legacy' || !entry.semanticTaskKey) return
  const graphEntry = projection.value.entries.find(item => item.kind === 'graph')
  const graphNode = projection.value.graphNodes.find(item => item.semanticTaskKey === entry.semanticTaskKey)
  if (!graphEntry || !graphNode) return
  selectedSemanticTaskKey.value = entry.semanticTaskKey
  selectedGraphNodeId.value = graphNode.acgNodeId
  // 先打开 Graph Editor，再写入 focusNodeId，确保首次挂载时也能被图组件的 watcher 捕获。
  focusNodeId.value = null
  openEntry(graphEntry)
  void nextTick(() => {
    focusNodeId.value = graphNode.acgNodeId
  })
}

void loadWorkspace()
watch(lifecycle, followLifecycle)
watch(() => route.query.runId, value => {
  const runId = typeof value === 'string' ? value : null
  if (!viewActive || runId === selectedRunId.value) return
  if (runId) void selectRun(runId, false)
  else { selectedRunId.value = null; void loadWorkspace(null) }
})
watch(activeEditorId, () => {
  if (activeOpened.value?.entry.kind !== 'artifact') finishForegroundContent(selectedRunId.value)
})
// LSP 跳转定义等跨文件动作通过总线回到这里，复用同一套打开逻辑。
let unregisterOpenFile: (() => void) | null = null
onMounted(() => {
  unregisterOpenFile = registerOpenFile(openWorkspaceFile)
})
const suspendWorkspace = () => {
  viewActive = false
  unregisterOpenFile?.()
  unregisterOpenFile = null
  pendingObservation = null
  controller?.abort()
  runtimeObservationAdapter.stop()
  stopProjectionRefresh()
  // Runtime output is transient and cannot be replayed. The cached Mission owns
  // its one shared SSE reference even while hidden; only polling is suspended.
  loading.value = false
}
onDeactivated(() => { suspended = true; suspendWorkspace() })
onActivated(() => {
  if (!suspended) return
  suspended = false
  viewActive = true
  unregisterOpenFile = registerOpenFile(openWorkspaceFile)
  const routeRunId = typeof route.query.runId === 'string' ? route.query.runId : selectedRunId.value
  void loadWorkspace(routeRunId)
})
onBeforeUnmount(() => {
  removeFileNavigationGuard()
  suspendWorkspace()
  releaseRunRuntimeStore(runtimeStoreRunId, runtimeStore.value)
  runtimeStore.value = null
  runtimeStoreRunId = null
})
</script>

<style scoped>
.workspace-inspector-column { display: flex; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; }
.workspace-document-surface { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 0; }
.workspace-document-surface > :deep(.editor-group) { flex: 1 1 0; height: auto; min-height: 0; }
.workspace-lifecycle { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; padding: 6px 10px; color: var(--wb-text-muted); font-size: 11px; }
.workspace-lifecycle span { flex: 1; }
.workspace-inspector-column > :deep(.runtime-inspector), .workspace-inspector-column > :deep(.workbench-auxiliary-sidebar) { flex: 1; min-height: 0; }
.mission-workspace-view { --editor-rail-height: 32px; width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; background: var(--bg-app); }
.mission-workspace-view :deep(.workbench-pane--left),
.mission-workspace-view :deep(.workbench-pane--right) { box-sizing: border-box; }
.mission-workspace-view :deep(.editor-group__surface) { padding: 0; }
.mission-workspace-view :deep(.artifact-editor),
.mission-workspace-view :deep(.mission-editor) { border: 0; border-radius: 0; box-shadow: none; background: var(--wb-surface-shell); }
.mission-workspace-view :deep(.editor-tabs) { box-sizing: border-box; height: var(--editor-rail-height, var(--wb-tab-height)); }
.mission-workspace-view :deep(.secondary-sidebar__header) { box-sizing: border-box; height: var(--editor-rail-height, var(--wb-tab-height)); min-height: var(--editor-rail-height, var(--wb-tab-height)); }
.mission-workspace-view :deep(.workspace-explorer__header-card) { padding-bottom: 10px; border: 0; background: transparent; }
.mission-workspace-view :deep(.workspace-explorer__project-card) { margin-top: 0; border: 0; box-shadow: none; }
.mission-workspace-view :deep(.workspace-explorer__mark) { border: 0; }
.mission-workspace-view :deep(.editor-document__header),
.mission-workspace-view :deep(.mission-editor__meta),
.mission-workspace-view :deep(.resource-list__row),
.mission-workspace-view :deep(.resource-switch-list),
.mission-workspace-view :deep(.markdown-body h1),
.mission-workspace-view :deep(.markdown-body h2) { border: 0; }
.workspace-loading-pane { display: grid; place-items: center; align-content: center; gap: 8px; box-sizing: border-box; height: 100%; padding: 22px; color: var(--text-secondary); font-size: 12px; text-align: center; }
.workspace-loading-pane__watermark,
.workspace-main-state__watermark { display: block; object-fit: contain; animation: workspace-state-pulse 3.2s ease-in-out infinite; }
.workspace-loading-pane__watermark { width: 78px; height: 78px; }
.workspace-main-state__watermark { width: 148px; height: 148px; }
.workspace-loading-pane strong { color: var(--text-primary); font-size: 13px; }
.workspace-loading-pane span:not(.workspace-loading-pane__mark) { max-width: 230px; line-height: 1.6; }
.workspace-loading-pane__mark { color: var(--primary-color); font: 10px var(--font-mono, monospace); letter-spacing: .08em; }
.workspace-loading-pane button, .workspace-main-state button { width: max-content; min-height: 29px; padding: 0 10px; border: 1px solid var(--border-light); border-radius: 5px; color: var(--text-secondary); background: transparent; cursor: pointer; font-size: 11px; }
.workspace-loading-pane button:hover, .workspace-main-state button:hover { color: var(--primary-color); border-color: var(--primary-line); background: var(--primary-fade); }
.workspace-main-state { display: grid; place-items: center; align-content: center; gap: 8px; box-sizing: border-box; height: 100%; min-height: 260px; padding: 24px; color: var(--text-secondary); font-size: 12px; text-align: center; }
.workspace-main-state strong { color: var(--text-primary); font-size: 14px; font-weight: 650; }
.workspace-main-state > span { max-width: 320px; line-height: 1.65; }
.workspace-main-state button { margin-top: 3px; }

@keyframes workspace-state-pulse {
  0%, 100% { opacity: .85; transform: scale(.985); }
  50% { opacity: 1; transform: scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .workspace-loading-pane__watermark,
  .workspace-main-state__watermark { animation: none; }
}
.workspace-request-error {
  /* Keep the notice in the route viewport. Fixed positioning put it under the
     desktop title bar, so only the lower edge was visible in the desktop shell. */
  position: absolute;
  top: 14px;
  right: 18px;
  z-index: 12;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: min(560px, calc(100% - 36px));
  min-width: 0;
  box-sizing: border-box;
  padding: 10px 12px 10px 14px;
  border: 1px solid color-mix(in srgb, var(--danger) 48%, var(--border-light));
  border-radius: 10px;
  color: var(--danger);
  background: color-mix(in srgb, var(--bg-card) 94%, var(--danger) 6%);
  box-shadow: var(--shadow-md), 0 1px 0 color-mix(in srgb, var(--text-primary) 7%, transparent) inset;
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
  font-size: 11px;
  transition: width 180ms var(--ease-out), padding 180ms var(--ease-out), border-radius 180ms ease, box-shadow 180ms ease;
  animation: workspace-request-error-enter 180ms var(--ease-out);
}
.workspace-request-error__indicator {
  flex: 0 0 7px;
  width: 7px;
  height: 7px;
  margin-top: 5px;
  border-radius: 50%;
  background: var(--danger);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--danger) 12%, transparent);
}
.workspace-request-error__message {
  flex: 1 1 auto;
  order: 1;
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
  text-wrap: pretty;
  line-height: 1.45;
}
.workspace-request-error > button:not(.workspace-request-error__toggle) {
  order: 2;
  flex: 0 0 auto;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid var(--border-light);
  border-radius: 7px;
  color: var(--text-secondary);
  background: var(--surface-subtle);
  cursor: pointer;
  font-size: 10px;
  font-weight: 650;
  white-space: nowrap;
  transition: color 140ms ease, border-color 140ms ease, background-color 140ms ease, transform 140ms ease;
}
.workspace-request-error > button:not(.workspace-request-error__toggle):hover {
  border-color: color-mix(in srgb, var(--danger) 38%, var(--border-light));
  color: var(--danger);
  background: var(--surface-hover);
}
.workspace-request-error > button:not(.workspace-request-error__toggle):active { transform: translateY(1px); }
.workspace-request-error > button:not(.workspace-request-error__toggle):focus-visible {
  outline: 2px solid color-mix(in srgb, var(--danger) 55%, transparent);
  outline-offset: 2px;
}
.workspace-request-error__toggle {
  order: 3;
  display: grid;
  flex: 0 0 28px;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 1px solid transparent;
  border-radius: 7px;
  color: var(--text-muted);
  background: transparent;
  cursor: pointer;
  font-size: 17px;
  line-height: 1;
  transition: color 140ms ease, border-color 140ms ease, background-color 140ms ease;
}
.workspace-request-error__toggle:hover,
.workspace-request-error__toggle:focus-visible {
  border-color: var(--border-light);
  color: var(--text-primary);
  background: var(--surface-subtle);
}
.workspace-request-error__toggle:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--danger) 55%, transparent);
  outline-offset: 2px;
}
.workspace-request-error.is-collapsed {
  align-items: center;
  justify-content: center;
  width: 42px;
  min-height: 46px;
  gap: 8px;
  padding: 8px 6px;
  border-radius: 12px;
  box-shadow: var(--shadow-md), 0 0 0 1px color-mix(in srgb, var(--danger) 9%, transparent) inset;
}
.workspace-request-error.is-collapsed .workspace-request-error__indicator {
  flex-basis: 7px;
  margin-top: 0;
}
.workspace-request-error.is-collapsed .workspace-request-error__message,
.workspace-request-error.is-collapsed > button:not(.workspace-request-error__toggle) {
  display: none;
}
.workspace-request-error.is-collapsed .workspace-request-error__toggle {
  order: 2;
}
@keyframes workspace-request-error-enter {
  from { opacity: 0; transform: translateX(16px); }
  to { opacity: 1; transform: translateX(0); }
}
@media (prefers-reduced-motion: reduce) {
  .workspace-request-error,
  .workspace-request-error__toggle,
  .workspace-request-error > button:not(.workspace-request-error__toggle) {
    animation: none;
    transition: none;
  }
}
@media (max-width: 760px) {
  .workspace-request-error {
    top: 10px;
    right: 12px;
    width: calc(100% - 24px);
  }
}
.artifact-choice { position: fixed; inset: 0; z-index: 20; display: grid; place-items: center; padding: 18px; background: color-mix(in srgb, var(--bg-app) 55%, transparent); }
.artifact-choice__panel { width: min(420px, 100%); border: 1px solid var(--border-light); background: var(--bg-card); box-shadow: var(--shadow-md); }
.artifact-choice__panel header { display: flex; justify-content: space-between; gap: 18px; padding: 14px 16px; border-bottom: 1px solid var(--border-light); }
.artifact-choice__panel header span, .artifact-choice__panel header strong { display: block; }
.artifact-choice__panel header span { color: var(--text-secondary); font-size: 12px; }
.artifact-choice__panel header strong { margin-top: 5px; color: var(--primary-color); font: 11px var(--font-mono, monospace); }
.artifact-choice__panel header button { width: 26px; height: 26px; border: 0; color: var(--text-muted); background: transparent; cursor: pointer; font-size: 18px; }
.artifact-choice__item { display: flex; justify-content: space-between; width: 100%; padding: 11px 16px; border: 0; border-bottom: 1px solid var(--border-light); color: var(--text-primary); background: transparent; cursor: pointer; text-align: left; }
.artifact-choice__item:hover { background: var(--primary-fade); }
.artifact-choice__item code { color: var(--text-muted); font: 10px var(--font-mono, monospace); }
</style>
