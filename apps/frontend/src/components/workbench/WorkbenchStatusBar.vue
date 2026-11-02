<template>
  <footer ref="rootRef" class="workbench-status-bar" role="contentinfo" aria-label="运行状态栏">
    <div class="workbench-status-bar__primary">
      <div v-if="runId" class="workbench-status-bar__run">
        <button
          class="workbench-status-bar__run-trigger"
          type="button"
          :aria-haspopup="runs.length ? 'listbox' : undefined"
          :aria-expanded="runs.length ? runPickerOpen : undefined"
          :title="runTitle"
          @click="toggleRunPicker"
        >
          <span class="workbench-status-bar__run-dot" :style="{ background: runDotColor }" aria-hidden="true"></span>
          <code class="workbench-status-bar__run-id">Run {{ runId }}</code>
          <span v-if="historical" class="workbench-status-bar__run-mode">read-only</span>
        </button>

        <div v-if="runPickerOpen" class="workbench-status-bar__run-picker" role="listbox" aria-label="切换 Run">
          <button
            class="workbench-status-bar__run-action"
            type="button"
            :disabled="!canRerun || rerunPending"
            :title="rerunDisabledReason"
            @click="requestRerun"
          >
            <span aria-hidden="true">+</span>
            <span>{{ rerunPending ? '正在创建…' : rerunLabel }}</span>
          </button>
          <div v-for="run in orderedRuns" :key="run.runId" class="workbench-status-bar__run-row" role="presentation">
            <button
              class="workbench-status-bar__run-item"
              :class="{ 'is-current': run.runId === runId }"
              type="button"
              role="option"
              :aria-selected="run.runId === runId"
              @click="chooseRun(run.runId)"
            >
              <span class="workbench-status-bar__run-dot" :style="{ background: statusSemanticColor(run.status) }" aria-hidden="true"></span>
              <code class="workbench-status-bar__run-item-id">{{ run.runId }}</code>
              <span class="workbench-status-bar__run-item-state">{{ runStateLabel(run.status) }}</span>
              <el-icon v-if="run.runId === runId" class="workbench-status-bar__run-item-check" aria-hidden="true"><Check /></el-icon>
            </button>
            <button
              v-if="runDeletable(run)"
              class="workbench-status-bar__run-delete"
              type="button"
              :aria-label="`删除 ${run.runId}`"
              :title="`删除 ${run.runId}`"
              :disabled="deletingRunId === run.runId"
              @click.stop="requestDeleteRun(run.runId)"
            >
              <el-icon aria-hidden="true"><Delete /></el-icon>
            </button>
          </div>
        </div>
      </div>

      <nav class="workbench-status-bar__tabs" role="tablist" aria-label="运行面板视图">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          class="workbench-status-bar__tab"
          :class="{ active: modelValue === tab.id }"
          type="button"
          role="tab"
          :aria-selected="modelValue === tab.id"
          @click="emit('update:modelValue', tab.id)"
        >
          <span class="workbench-status-bar__tab-label">{{ tab.label }}</span>
          <small
            v-if="tab.count !== undefined"
            class="workbench-status-bar__tab-count"
            :class="{ 'is-alert': tab.tone === 'failed' && tab.count > 0 }"
          >{{ tab.count }}</small>
        </button>
      </nav>
    </div>

    <div class="workbench-status-bar__actions">
      <div v-if="editorStatus" class="workbench-status-bar__editor" role="status" aria-label="编辑器文件信息">
        <span
          class="workbench-status-bar__editor-segment"
          :class="{ 'is-readonly': !editorStatus.editable }"
          :title="editorStatus.editable ? '本地文件，支持版本保护保存' : '只读 · 当前执行后端不支持版本保护保存'"
        >{{ editorStatus.editable ? '本地文件' : '只读' }}</span>
        <span class="workbench-status-bar__editor-segment" :title="`语言 ${editorStatus.language}`">{{ editorStatus.language }}</span>
        <span class="workbench-status-bar__editor-segment" title="文件编码 UTF-8">UTF-8</span>
        <span class="workbench-status-bar__editor-segment" :title="`共 ${editorStatus.lines} 行`">{{ editorStatus.lines }} 行</span>
        <span class="workbench-status-bar__editor-segment" :title="`光标位置 ${editorStatus.cursor}`">{{ editorStatus.cursor }}</span>
      </div>
      <button
        class="workbench-status-bar__toggle"
        type="button"
        :aria-expanded="!collapsed"
        :aria-label="collapsed ? '展开运行面板' : '收起运行面板'"
        :title="collapsed ? '展开运行面板' : '收起运行面板'"
        @click="emit('toggle')"
      >
        <span aria-hidden="true">运行面板</span>
        <el-icon aria-hidden="true"><ArrowUp v-if="!collapsed" /><ArrowDown v-else /></el-icon>
      </button>
    </div>
  </footer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowDown, ArrowUp, Check, Delete } from '@element-plus/icons-vue'
import type { WorkbenchBottomTab } from './WorkbenchBottomPanel.vue'
import type { WorkspaceFileEditorStatus } from './WorkspaceFileEditor.vue'
import { statusSemanticColor } from '@/utils/statusSemantic'

export interface WorkbenchRunSummary {
  runId: string
  status?: string | null
  canDelete?: boolean
}

const props = withDefaults(defineProps<{
  tabs: WorkbenchBottomTab[]
  /** Active panel tab id. */
  modelValue: string
  /** Whether the panel body above is collapsed. */
  collapsed: boolean
  /** Left-corner run identity; omitted renders no run block. */
  runId?: string | null
  runStatus?: string | null
  historical?: boolean
  /** Runs offered by the branch-picker style switcher. */
  runs?: WorkbenchRunSummary[]
  canRerun?: boolean
  rerunPending?: boolean
  rerunDisabledReason?: string
  rerunLabel?: string
  /** Run whose delete request is in flight; its button shows a busy state. */
  deletingRunId?: string | null
  /** Active file editor meta (language/encoding/lines/cursor); omitted renders no editor block. */
  editorStatus?: WorkspaceFileEditorStatus | null
}>(), {
  runs: () => [],
  canRerun: false,
  rerunPending: false,
  rerunDisabledReason: '当前运行尚未结束',
  rerunLabel: '再次运行',
  deletingRunId: null,
  editorStatus: null
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  toggle: []
  'select-run': [runId: string]
  rerun: []
  'delete-run': [runId: string]
}>()

const runDotColor = computed(() => statusSemanticColor(props.runStatus))
const runTitle = computed(() => {
  const status = (props.runStatus || '未观测').toLowerCase()
  const suffix = props.runs.length ? '，点击切换 Run' : ''
  return props.historical ? `历史运行 ${props.runId}（${status}，只读）${suffix}` : `当前运行 ${props.runId}（${status}）${suffix}`
})

const runStateLabel = (status?: string | null) => ({
  pending: 'pending',
  running: 'running',
  succeeded: 'succeeded',
  failed: 'failed',
  cancelled: 'cancelled',
  superseded: 'superseded'
}[status || ''] || status || '')

// VS Code branch-picker ordering: the current run first, then the rest.
const orderedRuns = computed(() => {
  const runs = props.runs || []
  return [...runs].sort((left, right) => Number(right.runId === props.runId) - Number(left.runId === props.runId))
})

const rootRef = ref<HTMLElement | null>(null)
const runPickerOpen = ref(false)

const toggleRunPicker = () => {
  if (!props.runs.length) return
  runPickerOpen.value = !runPickerOpen.value
}

const chooseRun = (runId: string) => {
  runPickerOpen.value = false
  emit('select-run', runId)
}

const requestRerun = () => {
  if (!props.canRerun || props.rerunPending) return
  runPickerOpen.value = false
  emit('rerun')
}

const runDeletable = (run: WorkbenchRunSummary) => run.canDelete === true
const requestDeleteRun = (runId: string) => {
  if (props.deletingRunId === runId || !props.runs.some(run => run.runId === runId && runDeletable(run))) return
  emit('delete-run', runId)
}

const handleDocumentPointerDown = (event: PointerEvent) => {
  if (!runPickerOpen.value) return
  if (rootRef.value && !rootRef.value.contains(event.target as Node)) runPickerOpen.value = false
}

const handleDocumentKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && runPickerOpen.value) {
    runPickerOpen.value = false
    event.stopPropagation()
  }
}

// Break out of the workbench column: fix the bar to the viewport bottom and
// let the app shell reserve this row (see global.css) so the icon rail and
// main content stay clear of it.
onMounted(() => {
  if (typeof document === 'undefined') return
  document.documentElement.dataset.workbenchStatusBar = 'on'
  document.addEventListener('pointerdown', handleDocumentPointerDown, true)
  document.addEventListener('keydown', handleDocumentKeydown, true)
})
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    delete document.documentElement.dataset.workbenchStatusBar
    document.removeEventListener('pointerdown', handleDocumentPointerDown, true)
    document.removeEventListener('keydown', handleDocumentKeydown, true)
  }
})
</script>

<style scoped>
.workbench-status-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 60;
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 10px;
  width: 100%;
  min-width: 0;
  height: var(--workbench-status-bar-height, 22px);
  border-top: 0;
  background: var(--wb-surface-section);
  color: var(--wb-text-muted);
  font-size: 10px;
  user-select: none;
}

.workbench-status-bar__primary { min-width: 0; flex: 1 1 auto; display: flex; align-items: stretch; }

.workbench-status-bar__run { position: relative; flex: 0 0 auto; display: inline-flex; align-items: stretch; }
.workbench-status-bar__run-trigger { display: inline-flex; align-items: center; gap: 6px; padding: 0 10px; border: 0; border-right: 1px solid var(--wb-border-soft); background: transparent; color: inherit; font: inherit; cursor: pointer; }
.workbench-status-bar__run-trigger:hover { color: var(--wb-text); background: var(--wb-hover); }
.workbench-status-bar__run-dot { flex: 0 0 6px; width: 6px; height: 6px; border-radius: 50%; }
.workbench-status-bar__run-id { color: var(--sem-running); font: 600 10px var(--font-mono, monospace); letter-spacing: .02em; }
.workbench-status-bar__run-mode { color: var(--wb-text-muted); font: 9px var(--font-mono, monospace); letter-spacing: .05em; }

/* Branch-picker style dropdown; opens upward from the fixed bottom bar. */
.workbench-status-bar__run-picker {
  position: absolute;
  left: 0;
  bottom: calc(100% + 6px);
  z-index: 70;
  display: grid;
  gap: 2px;
  min-width: 280px;
  max-height: 320px;
  overflow: auto;
  padding: 5px;
  border: 1px solid var(--wb-border);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 96%, transparent);
  box-shadow: var(--shadow-md);
  backdrop-filter: blur(14px);
}

.workbench-status-bar__run-row {
  display: flex;
  align-items: stretch;
  gap: 2px;
}

.workbench-status-bar__run-row .workbench-status-bar__run-item { flex: 1 1 auto; min-width: 0; }

.workbench-status-bar__run-action,
.workbench-status-bar__run-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 26px;
  padding: 3px 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--wb-text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.workbench-status-bar__run-delete {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  min-height: 26px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--wb-text-muted);
  font: inherit;
  cursor: pointer;
  opacity: 0;
  transition: opacity .12s ease, color .12s ease, background .12s ease;
}

.workbench-status-bar__run-delete .el-icon { font-size: 12px; }
.workbench-status-bar__run-row:hover .workbench-status-bar__run-delete,
.workbench-status-bar__run-delete:focus-visible { opacity: 1; }
.workbench-status-bar__run-delete:hover:not(:disabled) { color: var(--wb-danger, #d4574e); background: var(--wb-hover); }
.workbench-status-bar__run-delete:disabled { cursor: not-allowed; opacity: .6; }

.workbench-status-bar__run-action { color: var(--wb-text-muted); }
.workbench-status-bar__run-action:hover:not(:disabled) { color: var(--wb-text); background: var(--wb-hover); }
.workbench-status-bar__run-action:disabled { opacity: .5; cursor: not-allowed; }

.workbench-status-bar__run-item:hover { color: var(--wb-text); background: var(--wb-hover); }
.workbench-status-bar__run-item.is-current { color: var(--wb-text); background: color-mix(in srgb, var(--wb-accent) 8%, transparent); }
.workbench-status-bar__run-item-id { flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--sem-running); font: 600 10px var(--font-mono, monospace); }
.workbench-status-bar__run-item-state { margin-left: auto; color: var(--wb-text-muted); font-size: 9px; letter-spacing: .03em; }
.workbench-status-bar__run-item-check { flex: 0 0 auto; color: var(--wb-accent); font-size: 12px; }

.workbench-status-bar__tabs {
  min-width: 0;
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  scrollbar-width: none;
}

.workbench-status-bar__tabs::-webkit-scrollbar { display: none; }

.workbench-status-bar__tab {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 9px;
  border: 0;
  border-right: 1px solid var(--wb-border-soft);
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.workbench-status-bar__tab:hover { color: var(--wb-text); background: var(--wb-hover); }
.workbench-status-bar__tab.active { color: var(--wb-accent); background: color-mix(in srgb, var(--wb-accent) 9%, transparent); font-weight: 700; }
.workbench-status-bar__tab-count { color: inherit; font: 600 9px var(--font-mono, monospace); opacity: .72; }
.workbench-status-bar__tab-count.is-alert { color: var(--wb-danger); opacity: 1; }

.workbench-status-bar__actions { flex: 0 0 auto; display: inline-flex; align-items: stretch; }

/* VS Code style editor meta segments on the right side of the window bar. */
.workbench-status-bar__editor { flex: 0 0 auto; display: inline-flex; align-items: stretch; }
.workbench-status-bar__editor-segment {
  display: inline-flex;
  align-items: center;
  padding: 0 9px;
  border-left: 1px solid var(--wb-border-soft);
  color: var(--wb-text-muted);
  white-space: nowrap;
}
.workbench-status-bar__editor-segment:hover { color: var(--wb-text); background: var(--wb-hover); }
.workbench-status-bar__editor-segment.is-readonly { color: var(--wb-warning); }

.workbench-status-bar__toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 10px;
  border: 0;
  border-left: 1px solid var(--wb-border-soft);
  background: transparent;
  color: inherit;
  font: inherit;
  letter-spacing: .04em;
  cursor: pointer;
}

.workbench-status-bar__toggle:hover { color: var(--wb-text); background: var(--wb-hover); }
.workbench-status-bar__toggle .el-icon { font-size: 11px; }
</style>
