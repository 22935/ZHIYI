<template>
  <main class="editor-group" aria-label="Workspace editor">
    <nav v-if="activeOpened" class="editor-tabs" aria-label="Open editors" role="tablist">
      <div class="editor-tabs__scroll">
        <button
          v-if="sidebarHidden"
          class="editor-navigator-trigger"
          type="button"
          aria-label="唤醒项目导航"
          title="唤醒项目导航（窗口放不下时会让出右侧详情的空间）"
          @click="emit('restoreSidebar')"
        >
          <span class="editor-navigator-trigger__mark" aria-hidden="true">
            <el-icon><Expand /></el-icon>
          </span>
        </button>
        <div v-for="opened in openEntries" :key="opened.entry.entryId" class="editor-tab" :class="{ 'is-active': opened.entry.entryId === activeEditorId }">
          <button class="editor-tab__main" type="button" role="tab" :title="editorTitle(opened.entry)" :aria-selected="opened.entry.entryId === activeEditorId" @click="emit('activate', opened.entry.entryId)">
            <span v-if="tabStatusMark(opened.entry)" class="editor-tab__status" :class="'is-' + tabStatus(opened.entry)" aria-hidden="true">{{ tabStatusMark(opened.entry) }}</span>
            <span class="editor-tab__kind" aria-hidden="true">
              <el-icon><component :is="workspaceEntryIcon(opened.entry.kind)" /></el-icon>
            </span>
            <span class="editor-tab__name">{{ editorTitle(opened.entry) }}{{ opened.entry.metadata?.dirty ? ' ●' : '' }}</span>
            <span v-if="!opened.available" class="editor-tab__missing">missing</span>
          </button>
          <button class="editor-tab__close" type="button" :aria-label="`关闭 ${opened.entry.name}`" :title="`关闭 ${opened.entry.name}`" @click="closeEditor(opened.entry.entryId)">×</button>
        </div>
        <span v-if="!openEntries.length" class="editor-tabs__empty">从 Explorer 打开一个文件</span>
      </div>
      <div class="editor-tabs__actions">
        <button
          v-for="view in auxiliaryViews"
          :key="view.id"
          class="editor-auxiliary-trigger"
          type="button"
          :class="{ 'is-active': inspectorVisible && activeAuxiliaryId === view.id }"
          :aria-pressed="inspectorVisible && activeAuxiliaryId === view.id"
          :aria-label="inspectorVisible && activeAuxiliaryId === view.id ? `收起 ${view.title}` : `打开 ${view.title}`"
          :title="inspectorVisible && activeAuxiliaryId === view.id ? `收起 ${view.title}` : `打开 ${view.title}`"
          @click="emit('selectAuxiliary', view.id)"
        >
          <span class="editor-auxiliary-trigger__mark" aria-hidden="true">
            <img v-if="view.iconImage" class="editor-auxiliary-trigger__img" :src="view.iconImage" alt="" />
            <el-icon v-else><component :is="view.icon" /></el-icon>
          </span>
        </button>
        <button
          class="editor-inspector-trigger"
          type="button"
          :class="{
            'is-active': inspectorVisible && !activeAuxiliaryId,
            'is-unavailable': inspectorAutoHidden
          }"
          :aria-pressed="inspectorVisible && !activeAuxiliaryId"
          :aria-label="inspectorVisible && !activeAuxiliaryId ? '收起 Inspector' : '打开 Inspector'"
          :title="inspectorVisible && !activeAuxiliaryId
            ? '收起 Inspector'
            : (inspectorAutoHidden ? '打开 Inspector（当前窗口空间不足时会自动隐藏）' : '打开 Inspector')"
          @click="emit('selectInspector')"
        >
          <span class="editor-inspector-trigger__mark" aria-hidden="true">
            <el-icon><View /></el-icon>
          </span>
        </button>
      </div>
    </nav>

    <section class="editor-group__surface" :class="{ 'editor-group__surface--task': activeOpened?.entry.kind === 'task' }">
      <WorkspaceFileEditor
        v-for="opened in localFiles" :key="opened.entry.entryId"
        v-show="opened.entry.entryId === activeEditorId"
        :request="fileRequest(opened.entry)"
        @dirty-change="setDirty(opened.entry, $event)"
        @status-change="recordEditorStatus(opened.entry.entryId, $event)"
      />
      <component
        v-if="activeOpened && activeOpened.entry.kind !== 'local_file' && editorContribution"
        :is="editorContribution.component"
        :key="editorKey"
        :entry="activeOpened.entry"
        :projection="projection"
        :graph="projection.activeGraph || null"
        :graph-nodes="projection.graphNodes"
        :selected-semantic-task-key="selectedSemanticTaskKey"
        :selected-symbol-id="selectedSymbolId"
        :focus-node-id="focusNodeId"
        :run-id="projection.activeRun?.runId || null"
        :run-status="projection.activeRun?.status || null"
        :cancel-pending="cancelPending"
        :available="activeOpened.available"
        :runtime-observation="workbenchContext.runtimeObservation"
        :runtime-store="props.runtimeStore"
        :readonly="workbenchContext.lifecycle?.isReadOnly"
        :action-capabilities="workbenchContext.actionCapabilities"
        @select-semantic-task="emit('selectSemanticTask', $event)"
        @select-symbol="emit('selectSymbol', $event)"
        @open-semantic-task="emit('openSemanticTask', $event)"
        @locate-graph="emit('locateGraph', $event || activeOpened.entry)"
        @open-artifact="emit('openArtifact', $event)"
        @open-entry="emit('openEntry', $event)"
        @cancel-run="emit('cancelRun')"
        @content-ready="emit('contentReady', $event)"
        @artifact-projection="emit('artifactProjection', $event)"
        @semantics-saved="emit('semanticsSaved')"
      />
      <div v-else-if="activeOpened?.entry.kind !== 'local_file'" class="editor-group__empty">
        <img class="editor-group__empty-watermark" src="/logo.webp" alt="" aria-hidden="true" />
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import WorkspaceFileEditor, { type WorkspaceFileEditorStatus } from '@/components/workbench/WorkspaceFileEditor.vue'
import type { WorkspaceFileOpenRequest } from '@/services/api/agentos'
import { Expand, View } from '@element-plus/icons-vue'
import type { MissionWorkspaceProjection, WorkspaceEntry } from '@/services/api/agentos'
import type { AuxiliaryViewContribution, WorkbenchContext } from '@/workbench/types'
import type { WorkbenchContributionRegistry } from '@/workbench/registry'
import type { RuntimeEventStore } from '@/workbench/runtime/runtimeEvents'
import type { RunDocumentSymbol } from '@/workbench/runtime/runDocument'
import type { ArtifactDocumentModel } from '@/workbench/runtime/artifactProjection'
import { workspaceEntryIcon } from './workspaceEntryIcon'

export interface OpenWorkspaceEntry {
  entry: WorkspaceEntry
  available: boolean
}

const props = defineProps<{
  projection: MissionWorkspaceProjection
  openEntries: OpenWorkspaceEntry[]
  activeEditorId: string | null
  selectedSemanticTaskKey: string | null
  selectedSymbolId?: string | null
  focusNodeId: string | null
  registry: WorkbenchContributionRegistry
  workbenchContext: WorkbenchContext
  inspectorVisible: boolean
  inspectorAutoHidden: boolean
  auxiliaryViews?: AuxiliaryViewContribution[]
  activeAuxiliaryId?: string | null
  sidebarHidden?: boolean
  cancelPending?: boolean
  runtimeStore?: RuntimeEventStore | null
}>()

const emit = defineEmits<{
  activate: [entryId: string]
  contentReady: [runId: string | null]
  close: [entryId: string]
  editorStatus: [status: WorkspaceFileEditorStatus | null]
  selectSemanticTask: [semanticTaskKey: string | null]
  selectSymbol: [symbol: RunDocumentSymbol]
  openSemanticTask: [semanticTaskKey: string | null]
  locateGraph: [entry: WorkspaceEntry]
  openArtifact: [entry: WorkspaceEntry]
  openEntry: [entry: WorkspaceEntry]
  restoreSidebar: []
  selectInspector: []
  selectAuxiliary: [viewId: string]
  cancelRun: []
  semanticsSaved: []
  artifactProjection: [payload: { entryId: string; projection: ArtifactDocumentModel }]
}>()

const localFiles = computed(() => props.openEntries.filter(item => item.entry.kind === 'local_file'))
const fileRequest = (entry: WorkspaceEntry) => entry.metadata!.fileRequest as WorkspaceFileOpenRequest
const setDirty = (entry: WorkspaceEntry, dirty: boolean) => { entry.metadata!.dirty = dirty }
// 各文件编辑器把元信息上报到这里，只有活动编辑器的那份会转发给窗口状态栏。
const editorStatuses = ref<Record<string, WorkspaceFileEditorStatus>>({})
const recordEditorStatus = (entryId: string, status: WorkspaceFileEditorStatus) => { editorStatuses.value[entryId] = status }
const closeEditor = (entryId: string) => { delete editorStatuses.value[entryId]; emit('close', entryId) }
const activeEditorStatus = computed(() => editorStatuses.value[props.activeEditorId || ''] || null)
watch(activeEditorStatus, status => emit('editorStatus', status), {immediate: true})
const activeOpened = computed(() => props.openEntries.find(item => item.entry.entryId === props.activeEditorId))
const editorContribution = computed(() => props.registry.resolveEditor(activeOpened.value?.entry || null, props.workbenchContext))
const editorKey = computed(() => {
  if (!activeOpened.value) return 'empty'
  return `${activeOpened.value.entry.entryId}:${activeOpened.value.entry.artifactId || 'entry'}:${props.projection.activeRun?.runId || 'none'}`
})

const editorTitle = (entry: WorkspaceEntry) => (
  props.registry.resolveEditor(entry, props.workbenchContext)?.title?.(entry, props.workbenchContext) || entry.name
)

// Run / Progress 标签的运行状态符号：● 运行中 ✓ 成功 × 失败
const TAB_RUNNING = new Set(['running', 'pending', 'planning', 'retrying'])
const TAB_OK = new Set(['completed', 'succeeded'])
const TAB_BAD = new Set(['failed', 'cancelled'])
const tabStatus = (entry: WorkspaceEntry) => {
  const status = entry.kind === 'run'
    ? entry.status
    : entry.kind === 'progress'
      ? props.workbenchContext.runtimeObservation?.runStatus
      : null
  if (!status) return 'idle'
  if (TAB_OK.has(status)) return 'success'
  if (TAB_BAD.has(status)) return 'failed'
  if (TAB_RUNNING.has(status)) return 'running'
  return 'idle'
}
const tabStatusMark = (entry: WorkspaceEntry) => {
  const state = tabStatus(entry)
  return state === 'running' ? '●' : state === 'success' ? '✓' : state === 'failed' ? '×' : null
}

</script>

<style scoped>
.editor-group { display: flex; flex-direction: column; width: 100%; height: 100%; min-width: 0; min-height: 0; color: var(--wb-text); background: var(--wb-surface-shell); }
.editor-tabs { --editor-tab-bg: var(--wb-surface-1); display: flex; align-items: stretch; min-height: var(--editor-rail-height, var(--wb-tab-height)); overflow: hidden; border-bottom: 0; background: var(--editor-tab-bg); }
.editor-tabs__scroll { display: flex; flex: 1 1 auto; align-items: stretch; min-width: 0; overflow-x: auto; scrollbar-gutter: stable; scrollbar-width: thin; scrollbar-color: var(--wb-border-strong) transparent; }
.editor-tabs__actions { display: flex; flex: 0 0 auto; align-items: stretch; min-width: 32px; background: var(--editor-tab-bg); }
.editor-tab { display: flex; align-items: center; flex: 1 1 0; min-width: 100px; max-width: 300px; box-sizing: border-box; border-right: 0; background: var(--editor-tab-bg); }
.editor-tab:hover { background: var(--wb-hover); }
.editor-tab.is-active { background: var(--wb-surface-shell); box-shadow: none; }
.editor-tab__main, .editor-tab__close { border: 0; color: var(--wb-text-secondary); background: transparent; cursor: pointer; }
.editor-tab__main { display: flex; flex: 1 1 auto; align-items: center; align-self: stretch; gap: 7px; min-width: 0; padding: 0 8px 0 12px; text-align: left; font-size: 11px; }
.editor-tab__main:hover, .editor-tab.is-active .editor-tab__main { color: var(--wb-text); }
.editor-tab__main:focus-visible, .editor-tab__close:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: -2px; }
.editor-tab__kind { display: inline-flex; align-items: center; justify-content: center; width: 15px; min-width: 15px; color: var(--wb-accent); font: 12px var(--font-mono, monospace); }
.editor-tab:not(.is-active) .editor-tab__kind { color: var(--wb-text-muted); }
.editor-tab__kind .el-icon { font-size: 14px; }
.editor-tab__status { flex: 0 0 auto; color: var(--wb-accent); font-size: 10px; }
.editor-tab__status.is-success { color: var(--wb-success); }
.editor-tab__status.is-failed { color: var(--wb-danger); }
.editor-tab__name { min-width: 0; flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.editor-tab__missing { color: var(--wb-warning); font: 9px var(--font-mono, monospace); }
.editor-tab__close { display: grid; place-items: center; width: 20px; height: 20px; min-width: 20px; flex: 0 0 20px; margin-right: 8px; padding: 0; border-radius: 3px; color: var(--wb-text-secondary); font-size: 15px; opacity: 0; }
.editor-tab:hover .editor-tab__close, .editor-tab.is-active .editor-tab__close, .editor-tab__close:focus-visible { opacity: 1; }
.editor-tab__close:hover { color: var(--wb-text); background: var(--wb-hover); }
.editor-tabs__empty { align-self: center; padding: 0 14px; color: var(--wb-text-muted); font-size: 11px; }
.editor-tabs__scroll::-webkit-scrollbar { height: 4px; }
.editor-tabs__scroll::-webkit-scrollbar-thumb { background: var(--wb-border-strong); }
.editor-navigator-trigger {
  position: sticky;
  left: 0;
  z-index: 1;
  display: grid;
  flex: 0 0 32px;
  place-items: center;
  width: 32px;
  min-width: 32px;
  min-height: var(--editor-rail-height, var(--wb-tab-height));
  padding: 0;
  border: 0;
  border-right: 0;
  color: var(--wb-text-muted);
  background: var(--editor-tab-bg);
  cursor: pointer;
}
.editor-navigator-trigger__mark {
  display: grid;
  width: 23px;
  height: 23px;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 15px;
  transition: background-color 140ms var(--ease-out), border-color 140ms var(--ease-out), color 140ms var(--ease-out);
}
.editor-navigator-trigger:hover .editor-navigator-trigger__mark,
.editor-navigator-trigger:focus-visible .editor-navigator-trigger__mark {
  border-color: color-mix(in srgb, var(--wb-accent) 24%, var(--wb-border));
  color: var(--wb-accent);
  background: var(--wb-hover);
}
.editor-navigator-trigger:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: -2px; }
.editor-inspector-trigger,
.editor-auxiliary-trigger {
  z-index: 1;
  display: grid;
  flex: 0 0 32px;
  place-items: center;
  width: 32px;
  min-width: 32px;
  min-height: var(--editor-rail-height, var(--wb-tab-height));
  padding: 0;
  border: 0;
  color: var(--wb-text-muted);
  background: var(--editor-tab-bg);
  cursor: pointer;
}
.editor-inspector-trigger__mark,
.editor-auxiliary-trigger__mark {
  display: grid;
  width: 23px;
  height: 23px;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 6px;
  font-size: 15px;
  transition: background-color 140ms var(--ease-out), border-color 140ms var(--ease-out), color 140ms var(--ease-out), box-shadow 140ms var(--ease-out);
}
.editor-auxiliary-trigger__img { width: 16px; height: 16px; object-fit: contain; }
.editor-inspector-trigger:hover .editor-inspector-trigger__mark,
.editor-inspector-trigger:focus-visible .editor-inspector-trigger__mark,
.editor-auxiliary-trigger:hover .editor-auxiliary-trigger__mark,
.editor-auxiliary-trigger:focus-visible .editor-auxiliary-trigger__mark {
  border-color: color-mix(in srgb, var(--wb-accent) 24%, var(--wb-border));
  color: var(--wb-accent);
  background: var(--wb-hover);
}
.editor-inspector-trigger.is-active .editor-inspector-trigger__mark,
.editor-auxiliary-trigger.is-active .editor-auxiliary-trigger__mark {
  border-color: color-mix(in srgb, var(--wb-accent) 28%, var(--wb-border));
  color: var(--wb-accent);
  background: var(--wb-active);
  box-shadow: 0 1px 2px color-mix(in srgb, var(--wb-accent) 10%, transparent);
}
.editor-inspector-trigger.is-unavailable .editor-inspector-trigger__mark { opacity: .72; }
.editor-inspector-trigger:focus-visible,
.editor-auxiliary-trigger:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: -2px; }
.editor-group__surface { display: flex; flex: 1; min-width: 0; min-height: 0; overflow: hidden; padding: 10px 12px 12px; background: var(--wb-surface-shell); }
.editor-group__surface--task { padding: 0; }
.editor-group__empty {
  position: relative;
  isolation: isolate;
  display: grid;
  place-items: center;
  align-content: center;
  gap: 17px;
  width: 100%;
  height: 100%;
  min-height: 260px;
  box-sizing: border-box;
  overflow: hidden;
  padding: 42px 24px;
  color: var(--wb-text-muted);
  background: var(--wb-surface-shell);
  text-align: center;
}
.editor-group__empty-watermark {
  position: relative;
  z-index: 1;
  width: min(440px, 58vw);
  height: min(440px, 58vw);
  object-fit: contain;
  opacity: .12;
  filter: grayscale(1) saturate(.55) contrast(.82) brightness(1.12);
  mix-blend-mode: screen;
  pointer-events: none;
}

</style>
