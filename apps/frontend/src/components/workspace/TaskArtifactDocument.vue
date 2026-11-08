<template>
  <section class="task-editor" aria-label="Artifact document editor">
    <!-- 面包屑必须是滚动容器的直接子元素：sticky 只在父容器范围内生效，
         留在 header 里会随 header 一起滚出视口 -->
    <nav class="task-document__breadcrumb" aria-label="Document breadcrumb">
      <button type="button" @click="openMission">{{ missionTitle }}</button>
      <span aria-hidden="true">/</span>
      <span>运行 {{ runNumber }}</span>
      <span aria-hidden="true">/</span>
      <strong>步骤 {{ taskNumber }}</strong>
    </nav>

    <header class="task-document__header">
      <div class="task-document__heading-row">
        <div class="task-document__heading task-editor__heading">
          <h1>{{ document.title }}</h1>
          <div class="task-document__meta">
            <span class="task-document__status-mark" :class="`is-${entry.status || 'pending'}`" aria-hidden="true">{{ statusMark(entry.status) }}</span>
            <span class="task-document__status task-editor__status" :class="`is-${entry.status || 'pending'}`">{{ statusLabel(entry.status) }}</span>
            <span v-if="entry.attemptCount != null">执行 {{ entry.attemptCount }} 次</span>
          </div>
        </div>
        <div class="task-document__actions task-editor__actions">
          <button type="button" :disabled="!graphNode" @click="emit('locateGraph')">在图中定位</button>
        </div>
      </div>
    </header>

    <div class="task-document__body">
      <article class="task-document__canvas">
        <ArtifactVerification v-if="stageOutputContent && (document.artifactKind === 'final_report' || (document.artifactKind !== 'unknown' && document.verification))" :verification="document.verification" />
        <p v-if="!stageOutputContent && stageOutputLoading" role="status">{{ stageOutputPlaceholder }}</p>
        <p v-else-if="!stageOutputContent && stageOutputError" role="alert">{{ stageOutputError }}</p>
        <p v-else-if="!stageOutputContent && isTerminal" role="status">{{ stageOutputPlaceholder }}</p>
        <StageOutputRenderer v-else-if="document.artifactKind === 'unknown'" class="task-document__blocks" :value="stageOutputContent"
          :selected-id="selectedSymbolId" :id-prefix="resultIdPrefix" :document-title="document.title"
          @select="emit('selectResult', $event)" @reference="emit('selectResult', $event)" />
        <div v-else class="task-document__blocks" aria-label="Artifact document blocks">
          <div
            v-for="group in blockGroups"
            :key="group.blockId"
            class="task-document__block"
            :class="{ 'is-focused': focusedBlockId === group.blockId }"
            :data-block-id="group.blockId"
          >
            <span
              class="task-document__gutter"
              :data-block-id="group.blockId"
              :title="`定位段落 ${group.displayIndex}`"
              @click.stop="focusBlock(group.blockId)"
            >{{ group.displayIndex }}</span>
            <div class="task-document__block-content task-document__markdown markdown-body" v-html="renderedBlock(group.blocks)" />
          </div>
        </div>

        <section v-if="artifacts.length" class="task-document__links task-editor__section--artifacts" aria-labelledby="task-artifacts-title">
          <div class="task-document__section-heading">
            <h2 id="task-artifacts-title">相关产物</h2>
            <span class="task-editor__section-meta">{{ artifacts.length }}</span>
          </div>
          <div class="task-document__artifact-links task-editor__artifacts">
            <button v-for="artifact in artifacts" :key="artifact.entryId" type="button" @click="emit('openArtifact', artifact)">
              <span>{{ artifact.name }}</span>
              <span>查看</span>
            </button>
          </div>
        </section>

      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { missionDocumentContent } from './missionSemanticDisplay'
import type { MissionWorkspaceProjection, WorkspaceEntry, WorkspaceGraphNode } from '@/services/api/agentos'
import type { StageOutputSelection } from './StageOutputRenderer.vue'
import StageOutputRenderer from './StageOutputRenderer.vue'
import ArtifactVerification from './ArtifactVerification.vue'
import { renderArtifactDocument, type ArtifactDocumentBlock, type ArtifactDocumentModel } from '@/workbench/runtime/artifactProjection'
import { renderMarkdown } from '@/utils/markdown'
import { withoutRepeatedTitle } from '@/workbench/runtime/documentContent'

const props = defineProps<{
  entry: WorkspaceEntry
  projection: MissionWorkspaceProjection
  graphNode: WorkspaceGraphNode | null
  artifacts: WorkspaceEntry[]
  document: ArtifactDocumentModel
  stageOutputContent: string
  stageOutputLoading?: boolean
  stageOutputError: string
  selectedSymbolId?: string | null
  resultIdPrefix: string
  runNumber: string
  taskNumber: string
  missionTitle: string
}>()

const emit = defineEmits<{
  locateGraph: []
  openArtifact: [entry: WorkspaceEntry]
  openEntry: [entry: WorkspaceEntry]
  selectResult: [selection: StageOutputSelection]
}>()

const isTerminal = computed(() => ['completed', 'succeeded', 'failed', 'cancelled', 'skipped'].includes(props.entry.status || ''))
const stageOutputPlaceholder = computed(() => {
  if (props.stageOutputLoading) return '正在读取已保存的步骤结果…'
  if (isTerminal.value) {
    return '没有可读取的步骤结果正文。'
  }
  return '等待模型输出…'
})

const statusLabel = (status?: string | null) => ({
  pending: '待执行',
  ready: '已就绪',
  running: '执行中',
  completed: '已完成',
  succeeded: '已完成',
  failed: '执行失败',
  cancelled: '已取消',
  skipped: '已跳过'
}[status || ''] || status || '待执行')

const statusMark = (status?: string | null) => {
  if (['completed', 'succeeded'].includes(status || '')) return '✓'
  if (['failed', 'cancelled'].includes(status || '')) return '×'
  if (['running', 'ready'].includes(status || '')) return '●'
  return '○'
}

const focusedBlockId = ref<string | null>(null)

const blockGroups = computed(() => {
  const groups: Array<{ blockId: string; blocks: ArtifactDocumentBlock[]; displayIndex: string }> = []
  for (const block of props.document.blocks) {
    const previous = groups[groups.length - 1]
    if (previous?.blockId === block.blockId) {
      previous.blocks.push(block)
      continue
    }
    groups.push({
      blockId: block.blockId,
      blocks: [block],
      displayIndex: String(groups.length + 1).padStart(2, '0')
    })
  }
  return groups
})

const renderedBlock = (blocks: ArtifactDocumentBlock[]) => {
  const content = renderArtifactDocument({ ...props.document, blocks })
  return renderMarkdown(blocks[0] === props.document.blocks[0] ? withoutRepeatedTitle(content, props.document.title) : content)
}

const focusBlock = (blockId: string) => {
  focusedBlockId.value = blockId
}

const openMission = () => emit('openEntry', {
  entryId: 'overview:mission.md',
  kind: 'virtual_document',
  name: 'mission.md',
  title: 'mission.md',
  group: 'overview',
  displayOrder: 0,
  content: missionDocumentContent(props.projection)
})
</script>

<style scoped>
/* 滚动宿主是整节：面包屑 sticky 钉顶常驻，标题行与正文随内容一起滚 */
.task-editor { display: flex; flex: 1 1 auto; flex-direction: column; height: 100%; min-height: 0; overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; background: var(--wb-surface-shell); color: var(--wb-text); }
.task-document__header { flex: 0 0 auto; width: 100%; box-sizing: border-box; padding: 0 clamp(20px, 4vw, 64px) 12px; }
.task-document__breadcrumb { position: sticky; top: 0; z-index: 4; flex: 0 0 auto; display: flex; align-items: center; gap: 7px; min-width: 0; margin: 0 0 5px; padding: 15px clamp(20px, 4vw, 64px) 12px; overflow: hidden; background: var(--wb-surface-shell); color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); white-space: nowrap; }
.task-document__breadcrumb button { flex: 0 1 auto; min-width: 0; overflow: hidden; padding: 0; border: 0; color: var(--wb-text-secondary); background: transparent; cursor: pointer; font: inherit; text-overflow: ellipsis; white-space: nowrap; }
.task-document__breadcrumb button:hover { color: var(--wb-accent); text-decoration: underline; }
.task-document__breadcrumb strong { min-width: 0; overflow: hidden; color: var(--wb-text-secondary); font-weight: 500; text-overflow: ellipsis; }
.task-document__heading-row { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; padding-bottom: 18px; border-bottom: 0; }
.task-document__heading { min-width: 0; }
.task-document__filename { display: flex; align-items: center; gap: 7px; margin-bottom: 8px; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.task-document__filename span { color: var(--wb-accent); font-size: 13px; }
.task-document__filename code { color: var(--wb-text-secondary); font: inherit; }
.task-document__heading h1 { margin: 0; color: var(--wb-text); font-size: clamp(24px, 2.1vw, 32px); font-weight: 650; line-height: 1.2; text-wrap: pretty; }
.task-document__meta { display: flex; align-items: center; flex-wrap: wrap; gap: 0; margin-top: 10px; color: var(--wb-text-muted); font: 11px var(--font-mono, monospace); }
.task-document__meta > span + span::before { content: '·'; margin: 0 9px; color: var(--wb-border-strong); }
.task-document__status-mark { margin-right: 6px; }
.task-document__status-mark.is-completed, .task-document__status.is-completed { color: var(--wb-success); }
.task-document__status-mark.is-failed, .task-document__status.is-failed, .task-document__status.is-cancelled { color: var(--wb-danger); }
.task-document__status-mark.is-running, .task-document__status.is-running { color: var(--wb-accent); }
.task-document__actions { display: flex; flex: 0 0 auto; align-items: center; }
.task-document__actions button { min-height: 28px; padding: 0 9px; border: 1px solid var(--wb-border); border-radius: var(--wb-radius-sm); color: var(--wb-text-secondary); background: transparent; cursor: pointer; font-size: 11px; }
.task-document__actions button:hover:not(:disabled) { color: var(--wb-accent); border-color: color-mix(in srgb, var(--wb-accent) 42%, var(--wb-border)); background: var(--wb-accent-soft); }
.task-document__actions button:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: 1px; }
.task-document__actions button:disabled { color: var(--text-disabled); cursor: not-allowed; }
.task-document__body { flex: 0 0 auto; }
.task-document__canvas { width: min(calc(100% - 48px), 920px); margin: 0 auto; padding: 28px 0 56px; }
.task-document__blocks { min-width: 0; }
.task-document__block { display: grid; grid-template-columns: minmax(32px, 40px) minmax(0, 1fr); column-gap: 12px; align-items: start; min-width: 0; }
.task-document__block + .task-document__block { margin-top: 24px; }
.task-document__gutter { padding-top: 6px; color: color-mix(in srgb, var(--wb-text-muted) 72%, transparent); font: 500 14px/1.35 var(--font-mono, monospace); letter-spacing: .02em; text-align: right; user-select: none; cursor: pointer; transition: color 140ms ease, opacity 140ms ease; opacity: .82; }
.task-document__block:hover .task-document__gutter, .task-document__block.is-focused .task-document__gutter { color: var(--wb-text-secondary); opacity: 1; }
.task-document__block.is-focused .task-document__gutter { color: var(--wb-accent); }
.task-document__block-content { min-width: 0; }
.markdown-body { color: var(--wb-text-secondary); }
.markdown-body :deep(h2) { margin: 30px 0 11px; padding-top: 4px; color: var(--wb-text); font-size: 18px; font-weight: 650; line-height: 1.35; text-wrap: pretty; }
.task-document__block-content :deep(h2:first-child), .task-document__block-content :deep(h3:first-child) { margin-top: 0; }
.markdown-body :deep(h3) { margin: 22px 0 8px; color: var(--wb-text); font-size: 15px; font-weight: 650; line-height: 1.4; text-wrap: pretty; }
.markdown-body :deep(p), .markdown-body :deep(li) { color: var(--wb-text-secondary); font-size: 14px; line-height: 1.85; text-wrap: pretty; }
.markdown-body :deep(p) { margin: 0 0 14px; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { margin: 8px 0 18px; padding-left: 24px; }
.markdown-body :deep(li) { margin: 4px 0; padding-left: 4px; }
.markdown-body :deep(blockquote) { margin: 22px 0; padding: 12px 16px; border-left: 2px solid var(--wb-accent); color: var(--wb-text-secondary); background: color-mix(in srgb, var(--wb-accent) 5%, transparent); }
.markdown-body :deep(blockquote p) { margin: 0; font-size: 12px; line-height: 1.7; }
/* Markdown 表格样式收敛到 global.css 的全局三线表 */
.markdown-body :deep(strong) { color: var(--wb-text); font-weight: 650; }
.markdown-body :deep(code) { padding: 2px 4px; color: var(--wb-text); background: var(--wb-surface-inset); font: 11px var(--font-mono, monospace); }
.task-document__links { margin-top: 34px; padding-top: 20px; border-top: 1px solid var(--wb-border-soft); }
.task-document__section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.task-document__section-heading h2 { margin: 0; color: var(--wb-text); font-size: 15px; font-weight: 650; }
.task-editor__section-meta { color: var(--wb-text-muted); font: 11px var(--font-mono, monospace); }
.task-document__artifact-links { display: grid; gap: 0; margin-top: 11px; }
.task-document__artifact-links button { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 33px; padding: 0 8px; border: 0; border-bottom: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: transparent; cursor: pointer; text-align: left; }
.task-document__artifact-links button:hover { color: var(--wb-accent); background: var(--wb-hover); }
.task-document__artifact-links button:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: -1px; }
.task-document__artifact-links code { color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
@media (max-width: 760px) {
  .task-document__header { padding-inline: 20px; }
  .task-document__heading-row { align-items: flex-start; flex-direction: column; gap: 12px; }
  .task-document__actions { width: 100%; }
  .task-document__actions button { width: 100%; }
  .task-document__canvas { width: min(calc(100% - 28px), 920px); padding-top: 20px; }
}
</style>
