<template>
  <aside class="workspace-explorer" aria-label="Mission Project Explorer">
    <header class="workspace-explorer__header">
      <div class="workspace-explorer__header-card">
        <button class="workspace-explorer__back" type="button" @click="emit('back')">
          <el-icon class="workspace-explorer__back-icon" aria-hidden="true"><ArrowLeft /></el-icon>
          <span>Projects</span>
        </button>
      </div>
      <div class="workspace-explorer__project-card">
        <div class="workspace-explorer__title-row">
          <span class="workspace-explorer__mark" aria-hidden="true"><el-icon><FolderOpened /></el-icon></span>
          <div>
            <strong>{{ missionDisplayObjective(projection) }}</strong>
            <small>PROJECT · {{ missionDisplayLabel(projection) }}</small>
          </div>
        </div>
        <code class="workspace-explorer__mission-id" :title="projection.mission.missionId">{{ projection.mission.missionId }}</code>
      </div>
    </header>

    <nav class="workspace-tree" aria-label="Project files">
      <section v-for="section in sections" :key="section.group" class="workspace-tree__section">
        <button class="workspace-tree__section-toggle" type="button" :aria-expanded="isExpanded(section.group)" @click="toggleSection(section.group)">
          <span>{{ section.label }}</span>
          <small v-if="section.items.length">{{ section.items.length }}</small>
        </button>
        <div v-if="isExpanded(section.group)" class="workspace-tree__items">
          <template v-for="entry in section.items" :key="entry.entryId">
            <button
              type="button"
              class="workspace-tree__entry"
              :class="{
                'is-active': entry.entryId === activeEditorId,
                'is-selected-symbol': entry.kind === 'task' && entry.semanticTaskKey === selectedSemanticTaskKey,
                'is-legacy': entry.identityQuality === 'legacy',
                'is-task': entry.kind === 'task'
              }"
              :title="entry.name"
              @click="handleEntryClick(entry)"
            >
              <span v-if="entry.kind === 'task'" class="workspace-tree__order">{{ formatOrder(entry.displayOrder) }}</span>
              <el-icon class="workspace-tree__entry-icon"><component :is="entryIcon(entry)" /></el-icon>
              <span class="workspace-tree__entry-name">{{ entry.name }}</span>
              <span
                v-if="entry.kind === 'task'"
                class="workspace-tree__task-state"
                :class="`is-${entry.status || 'pending'}`"
                :title="taskStatusLabel(entry.status)"
                :aria-label="taskStatusLabel(entry.status)"
              >
                <span class="workspace-tree__task-state-icon" aria-hidden="true">{{ taskStatusMark(entry.status) }}</span>
                <span class="workspace-tree__task-state-label">{{ taskStatusLabel(entry.status) }}</span>
              </span>
              <span v-if="entry.kind === 'task' && entry.artifactCount" class="workspace-tree__artifact-count">{{ entry.artifactCount }}</span>
              <span v-if="entry.identityQuality === 'legacy'" class="workspace-tree__legacy">legacy</span>
            </button>
            <div v-if="entry.kind === 'task' && taskChildren(entry).length" class="workspace-tree__children">
              <button
                v-for="child in taskChildren(entry)"
                :key="child.entryId"
                type="button"
                class="workspace-tree__entry workspace-tree__entry--child"
                :class="{ 'is-active': child.entryId === activeEditorId }"
                :title="child.name"
                @click="handleEntryClick(child)"
              >
                <el-icon class="workspace-tree__entry-icon"><component :is="entryIcon(child)" /></el-icon>
                <span class="workspace-tree__entry-name">{{ child.name }}</span>
                <code>{{ child.artifactKey }}</code>
              </button>
            </div>
          </template>
          <p v-if="!section.items.length" class="workspace-tree__empty">{{ section.empty }}</p>
        </div>
      </section>
    </nav>

    <footer class="workspace-explorer__footer">
      <span class="workspace-explorer__status-dot" :class="{ 'is-active': Boolean(projection.activeRun) }" aria-hidden="true"></span>
      <span>{{ projection.activeRun ? `Run ${projection.activeRun.runId}` : 'No active Run' }}</span>
      <span v-if="projection.activeRun" class="workspace-explorer__readonly">read-only</span>
    </footer>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { missionDisplayObjective, missionDisplayLabel } from './missionSemanticDisplay'
import { ArrowLeft, FolderOpened } from '@element-plus/icons-vue'
import type { MissionWorkspaceProjection, WorkspaceEntry } from '@/services/api/agentos'
import { workspaceEntryIcon } from './workspaceEntryIcon'

const props = withDefaults(defineProps<{
  projection: MissionWorkspaceProjection
  activeEditorId: string | null
  selectedSemanticTaskKey?: string | null
  selectedRunId: string | null
}>(), {
  selectedSemanticTaskKey: null
})

const emit = defineEmits<{
  back: []
  open: [entry: WorkspaceEntry]
  selectRun: [runId: string]
}>()

const expandedSections = ref<Record<string, boolean>>({
  overview: true,
  steps: true,
  output: true
})

const groupLabels: Record<string, { label: string; empty: string }> = {
  overview: { label: 'EXPLORER', empty: '当前 Run 尚未生成概览文件' },
  runs: { label: 'RUNS', empty: '尚无 Run' },
  steps: { label: 'TASKS', empty: '当前 Run 尚无逻辑步骤' },
  output: { label: 'ARTIFACTS', empty: '当前 Run 尚无 Artifact' }
}

const sections = computed(() => Object.entries(groupLabels).map(([group, meta]) => ({
  group,
  ...meta,
  items: props.projection.entries
    .filter(entry => entry.group === group && (
      group !== 'steps'
      || entry.kind === 'task'
      || (entry.kind === 'artifact' && (!entry.parentEntryId || !props.projection.entries.some(parent => parent.entryId === entry.parentEntryId && parent.kind === 'task')))
    ) && entry.kind !== 'folder')
    .sort((left, right) => left.displayOrder - right.displayOrder || left.entryId.localeCompare(right.entryId))
})))

const toggleSection = (group: string) => {
  expandedSections.value[group] = !expandedSections.value[group]
}

const isExpanded = (group: string) => expandedSections.value[group] !== false

const taskChildren = (task: WorkspaceEntry) => props.projection.entries
  .filter(entry => entry.parentEntryId === task.entryId && entry.kind === 'artifact')
  .sort((left, right) => left.displayOrder - right.displayOrder || left.entryId.localeCompare(right.entryId))

const handleEntryClick = (entry: WorkspaceEntry) => {
  if (entry.kind === 'run' && entry.runId) { emit('selectRun', entry.runId); return }
  emit('open', entry)
}

const entryIcon = (entry: WorkspaceEntry) => {
  return workspaceEntryIcon(entry.kind)
}

const taskStatusLabel = (status?: string | null) => ({
  pending: 'pending',
  ready: 'ready',
  running: 'running',
  completed: 'completed',
  failed: 'failed',
  skipped: 'skipped'
}[status || ''] || status || 'pending')

const taskStatusMark = (status?: string | null) => ({
  pending: '○',
  ready: '○',
  running: '●',
  completed: '✓',
  failed: '!',
  skipped: '×'
}[status || ''] || '○')

const formatOrder = (order: number) => String(order + 1).padStart(2, '0')
</script>

<style scoped>
.workspace-explorer {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  height: 100%;
  color: var(--wb-text);
  background: var(--wb-surface-1);
}

.workspace-explorer__header {
  flex: 0 0 auto;
  margin: 8px 8px 6px;
}

/* 重叠卡片：Projects 背衬卡底部留出叠压区，项目卡同宽对齐、上提盖在其上 */
.workspace-explorer__header-card {
  padding: 6px 12px 18px;
  border: 1px solid var(--wb-border-soft);
  border-radius: var(--wb-radius-section);
  background: var(--wb-surface-inset);
}

.workspace-explorer__project-card {
  position: relative;
  margin: -14px 0 0;
  padding: 11px 12px 10px;
  border: 1px solid var(--wb-border);
  border-radius: var(--wb-radius-section);
  background: var(--wb-surface-section);
  box-shadow: var(--wb-shadow-section);
}

.workspace-explorer__back { display: inline-flex; align-items: center; gap: 3px; margin: 0; padding: 0; border: 0; color: var(--wb-text-muted); background: transparent; cursor: pointer; font-size: 11px; }
.workspace-explorer__back-icon { font-size: 13px; }
.workspace-explorer__back:hover { color: var(--wb-accent); }


.workspace-explorer__title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.workspace-explorer__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 28px;
  width: 28px;
  height: 28px;
  border: 1px solid color-mix(in srgb, var(--wb-accent) 28%, var(--wb-border));
  border-radius: var(--wb-radius-md);
  color: var(--wb-accent);
  background: var(--wb-accent-soft);
}

.workspace-explorer__title-row div {
  min-width: 0;
}

.workspace-explorer__title-row strong,
.workspace-explorer__title-row small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-explorer__title-row strong {
  font-size: 12px;
  font-weight: 700;
}

.workspace-explorer__title-row small {
  margin-top: 2px;
  color: var(--wb-text-secondary);
  font-size: 11px;
}

.workspace-explorer__mission-id {
  display: block;
  margin-top: 9px;
  overflow: hidden;
  color: var(--wb-text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-tree {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 7px 5px;
  scrollbar-gutter: stable;
}

.workspace-tree__section { margin-bottom: 4px; }

.workspace-tree__section-toggle,
.workspace-tree__entry {
  display: flex;
  align-items: center;
  width: 100%;
  border: 0;
  color: var(--wb-text-secondary);
  background: transparent;
  text-align: left;
}

.workspace-tree__section-toggle {
  gap: 0;
  min-height: 27px;
  padding: 0 7px;
  cursor: pointer;
  /* 一级标题（OVERVIEW/STEPS/OUTPUT）用强调蓝与条目行区分，参考 VS Code 侧栏分区头 */
  color: var(--wb-accent, var(--primary-color));
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .08em;
}

.workspace-tree__section-toggle:hover { color: color-mix(in srgb, var(--wb-accent, var(--primary-color)) 60%, var(--wb-text)); }
.workspace-tree__section-toggle small { margin-left: auto; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }

.workspace-tree__items { padding: 1px 0 4px; }

.workspace-tree__entry {
  position: relative;
  gap: 6px;
  min-height: 30px;
  padding: 0 8px 0 15px;
  border-left: 2px solid transparent;
  cursor: pointer;
  font-size: 12px;
  transition: background 160ms var(--ease-out), color 160ms var(--ease-out), border-color 160ms var(--ease-out);
}

.workspace-tree__entry:hover { border-radius: var(--wb-radius-sm); color: var(--wb-text); background: var(--wb-hover); }
.workspace-tree__entry.is-active {
  /* 选中态走 Agent 侧栏工程项目行的简洁样式：平底+主色文字，不描边不加左侧色条 */
  border-left-color: transparent;
  border-radius: var(--wb-radius-sm);
  color: var(--primary-color, var(--wb-accent));
  background: var(--wb-selected);
}
.workspace-tree__entry.is-selected-symbol { color: var(--wb-text); background: color-mix(in srgb, var(--wb-selected) 58%, transparent); }
.workspace-tree__entry.is-legacy { color: var(--wb-warning); }
.workspace-tree__entry.is-task { min-height: 32px; padding-left: 6px; }
.workspace-tree__entry--child { min-height: 28px; padding-left: 43px; font-size: 11px; }
.workspace-tree__children { padding-bottom: 2px; }
.workspace-tree__order { flex: 0 0 20px; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); text-align: right; }
.workspace-tree__entry-icon { flex: 0 0 auto; color: var(--wb-text-muted); }
.workspace-tree__entry.is-active .workspace-tree__entry-icon { color: var(--primary-color, var(--wb-accent)); }
.workspace-tree__entry-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workspace-tree__task-state { display: inline-flex; align-items: center; gap: 5px; margin-left: auto; color: var(--wb-text-muted); font: 11px var(--font-mono, monospace); }
.workspace-tree__task-state-icon { display: inline-grid; place-items: center; width: 16px; height: 16px; }
.workspace-tree__task-state-label { width: 0; overflow: hidden; opacity: 0; transition: width 160ms var(--ease-out), opacity 160ms var(--ease-out); }
.workspace-tree__entry:hover .workspace-tree__task-state-label, .workspace-tree__entry.is-active .workspace-tree__task-state-label { width: auto; opacity: 1; }
.workspace-tree__task-state.is-completed { color: var(--wb-success); }
.workspace-tree__task-state.is-running { color: var(--wb-accent); }
.workspace-tree__task-state.is-failed { color: var(--wb-danger); }
.workspace-tree__artifact-count { margin-left: 0; color: var(--wb-accent); font: 10px var(--font-mono, monospace); }
.workspace-tree__entry--child code { margin-left: auto; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.workspace-tree__legacy { margin-left: auto; color: var(--wb-warning); font: 10px var(--font-mono, monospace); }
.workspace-tree__empty { margin: 4px 10px 8px 31px; color: var(--wb-text-muted); font-size: 11px; line-height: 1.5; }

.workspace-explorer__footer {
  display: flex;
  align-items: center;
  gap: 7px;
  min-height: 34px;
  padding: 0 13px;
  border-top: 0;
  color: var(--wb-text-muted);
  font-size: 10px;
}

.workspace-explorer__status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--text-disabled); }
.workspace-explorer__status-dot.is-active { background: var(--wb-success); }
.workspace-explorer__readonly { margin-left: auto; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }

.workspace-tree__entry:focus-visible,
.workspace-tree__section-toggle:focus-visible,
.workspace-explorer__back:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: -2px; }

@media (prefers-reduced-motion: reduce) {
  .workspace-tree__entry { transition-duration: 1ms; }
}
</style>
