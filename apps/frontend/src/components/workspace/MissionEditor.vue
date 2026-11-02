<template>
  <article class="mission-editor editor-document" aria-label="mission.md">
    <header class="editor-document__header">
      <div>
        <span class="editor-document__eyebrow">VIRTUAL DOCUMENT</span>
        <h1>mission.md</h1>
        <p>{{ projection.missionSemanticView ? 'Mission brief · formal semantics' : 'Mission brief · read-only projection' }}</p>
      </div>
      <code>{{ projection.mission.missionId }}</code>
      <button v-if="projection.missionSemanticView && !editing" type="button" @click="beginEdit">{{ projection.missionSemanticView.semanticStatus === 'INITIALIZED' ? '编辑目标与约束' : '初始化正式语义' }}</button>
    </header>

    <MissionRevisionNotice v-if="projection.missionSemanticView && projection.activeRun"
      :mission-id="projection.mission.missionId" :run-id="projection.activeRun.runId"
      :revision="projection.missionSemanticView.missionRevision" :run-status="projection.activeRun.status || ''"
      :readonly="readonly"
      :action-capabilities="actionCapabilities"
      @changed="emit('semanticsSaved')" />

    <form v-if="editing" class="mission-editor__meta" @submit.prevent="saveSemantics">
      <label>正式目标<textarea v-model="objective" aria-label="正式目标" :disabled="saving" required rows="6" /></label>
      <div v-for="(constraint, index) in constraints" :key="constraint.constraintId">
        <label>约束 {{ index + 1 }}<textarea v-model="constraint.text" :aria-label="`约束 ${index + 1}`" :disabled="saving" required /></label>
        <button type="button" :disabled="saving" @click="constraints.splice(index, 1)">移除约束</button>
      </div>
      <button type="button" :disabled="saving" @click="addConstraint">添加约束</button>
      <p>修改作用于后续新 Run；所选 Run 继续使用历史依据。</p>
      <p v-if="saveError" role="alert">{{ saveError }}</p>
      <button type="submit" :disabled="saving || conflicted || !objective.trim()">{{ saving ? '保存中…' : '保存正式语义' }}</button>
      <button v-if="conflicted" type="button" @click="emit('semanticsSaved'); editing = false">刷新当前版本</button>
      <button type="button" :disabled="saving" @click="editing = false">取消</button>
    </form>

    <div class="editor-document__body markdown-body" v-html="renderedContent" />

    <section class="mission-editor__meta" aria-label="Mission metadata">
      <div class="property-row"><span>Mission 目标</span><span>{{ missionDisplayLabel(projection) }}</span></div>
      <div v-if="projection.selectedRunBasis" class="property-row"><span>所选 Run 依据</span><span>{{ projection.selectedRunBasis.sourceType }} · revision {{ projection.selectedRunBasis.sourceRevision }}</span></div>
      <div v-else-if="projection.selectedRunBasisStatus" class="property-row"><span>所选 Run 依据</span><span>{{ runDisplayObjective(projection) }}</span></div>
      <div class="property-row"><span>status</span><code>{{ projection.mission.status }}</code></div>
      <div v-if="projection.activeRun" class="property-row"><span>active Run</span><code>{{ projection.activeRun.runId }}</code></div>
      <div v-if="projection.activeRun" class="property-row"><span>Run status</span><code>{{ projection.activeRun.status }}</code></div>
    </section>
    <section v-if="projection.inputAttachments?.length" class="mission-editor__meta" aria-label="Run input attachments">
      <div class="property-row"><strong>Input attachments</strong><span>{{ projection.inputAttachments.length }}</span></div>
      <div v-for="attachment in projection.inputAttachments" :key="attachment.attachmentId" class="property-row">
        <span>{{ attachment.originalFilename }}</span>
        <code>{{ attachment.status }} · {{ formatBytes(attachment.sizeBytes) }}</code>
      </div>
    </section>
  </article>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import MissionRevisionNotice from './MissionRevisionNotice.vue'
import { agentosApi, type MissionSemanticEditRequest } from '@/services/api/agentos'
import { missionDocumentContent, missionDisplayLabel, runDisplayObjective } from './missionSemanticDisplay'
import { renderMarkdown } from '@/utils/markdown'
import type { MissionWorkspaceProjection, WorkspaceEntry, RunActionCapabilities } from '@/services/api/agentos'

const props = defineProps<{
  projection: MissionWorkspaceProjection
  entry: WorkspaceEntry
  readonly?: boolean
  actionCapabilities?: RunActionCapabilities | null
}>()
const emit = defineEmits<{ semanticsSaved: [] }>()
const editing = ref(false)
const saving = ref(false)
const conflicted = ref(false)
const saveError = ref('')
const objective = ref('')
const constraints = ref<MissionSemanticEditRequest['constraints']>([])
let expectedRevision = 0
let sourceRefs: string[] = []
let pending: MissionSemanticEditRequest | null = null
const newOperationId = () => crypto.randomUUID()
const beginEdit = () => {
  const view = props.projection.missionSemanticView
  objective.value = view?.objective || ''
  constraints.value = (view?.constraints || []).map(item => ({ ...item, sourceRefs: [...(item.sourceRefs || [])] }))
  sourceRefs = [...(view?.sourceReferences || [])]
  expectedRevision = view?.missionRevision || 0
  pending = null
  saveError.value = ''
  conflicted.value = false
  editing.value = true
}
const addConstraint = () => constraints.value.push({ constraintId: newOperationId(), text: '', sourceRefs: [] })
const saveSemantics = async () => {
  if (saving.value || conflicted.value) return
  const content = { objective: objective.value, constraints: constraints.value, sourceRefs }
  if (!pending || JSON.stringify(content) !== JSON.stringify({ objective: pending.objective, constraints: pending.constraints, sourceRefs: pending.sourceRefs })) {
    pending = JSON.parse(JSON.stringify({ ...content, expectedMissionRevision: expectedRevision, operationId: newOperationId() }))
  }
  saving.value = true
  saveError.value = ''
  try {
    await agentosApi.editMissionSemantics(props.projection.mission.missionId, pending!)
    editing.value = false
    pending = null
    emit('semanticsSaved')
  } catch (error: any) {
    conflicted.value = error?.response?.status === 409
    saveError.value = conflicted.value ? '版本冲突，请刷新当前版本后重新编辑。' : '保存失败，可重试相同内容。'
  } finally {
    saving.value = false
  }
}

const renderedContent = computed(() => {
  const source = props.projection.missionSemanticView
    ? missionDocumentContent(props.projection)
    : props.entry.content || missionDocumentContent(props.projection)
  return renderMarkdown(source)
})

const formatBytes = (bytes: number) => bytes < 1024
  ? `${bytes} B`
  : bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`
</script>

<style scoped>
.mission-editor {
  flex: 1 1 auto;
  height: 100%;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: stable;
  padding: 34px clamp(24px, 6vw, 92px) 56px;
  border: 1px solid var(--wb-border-soft);
  border-radius: var(--wb-radius-section);
  background: var(--wb-surface-section);
  box-shadow: var(--wb-shadow-section);
  color: var(--wb-text);
}

.editor-document__header {
  display: flex;
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 22px;
  border-bottom: 1px solid var(--wb-border-soft);
}

.editor-document__header h1 { max-width: 820px; margin: 7px 0 4px; font-size: 19px; line-height: 1.3; text-wrap: pretty; overflow-wrap: anywhere; }
.editor-document__header p { margin: 0; color: var(--wb-text-secondary); font-size: 12px; }
.editor-document__header code { align-self: flex-start; max-width: 220px; overflow: hidden; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.editor-document__eyebrow { color: var(--wb-accent); font: 10px var(--font-mono, monospace); letter-spacing: .1em; }

.editor-document__body { width: min(100%, 820px); padding-top: 24px; }
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) { color: var(--wb-text); line-height: 1.35; text-wrap: pretty; }
.markdown-body :deep(h1) { margin: 0 0 18px; font-size: 25px; }
.markdown-body :deep(h2) { margin: 28px 0 10px; padding-bottom: 6px; border-bottom: 1px solid var(--wb-border); font-size: 17px; }
.markdown-body :deep(h3) { margin: 20px 0 8px; font-size: 14px; }
.markdown-body :deep(p),
.markdown-body :deep(li) { color: var(--wb-text-secondary); font-size: 13px; line-height: 1.75; overflow-wrap: anywhere; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { padding-left: 23px; }
.markdown-body :deep(code) { padding: 2px 4px; color: var(--wb-text); background: var(--wb-surface-inset); font: 11px var(--font-mono, monospace); }
.markdown-body :deep(pre) { overflow: auto; padding: 12px; border: 1px solid var(--wb-border); background: var(--wb-surface-inset); }
.markdown-body :deep(pre code) { padding: 0; background: transparent; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding-left: 12px; border-left: 2px solid var(--wb-accent); color: var(--wb-text-secondary); }
.markdown-body :deep(a) { color: var(--wb-accent); }
/* Markdown 表格样式收敛到 global.css 的全局三线表 */

.mission-editor__meta { width: min(100%, 820px); margin-top: 30px; padding-top: 14px; border-top: 1px solid var(--wb-border-soft); }
.mission-editor__meta textarea { display: block; width: 100%; margin: 8px 0; padding: 10px; color: var(--wb-text); background: var(--wb-surface-inset); border: 1px solid var(--wb-border-soft); font: inherit; }
.mission-editor button { padding: 6px 10px; margin: 4px; color: var(--wb-text); background: var(--wb-surface-inset); border: 1px solid var(--wb-border-soft); cursor: pointer; }
.property-row { display: flex; justify-content: space-between; gap: 24px; min-height: 30px; padding: 7px 0; color: var(--wb-text-secondary); font-size: 12px; }
.property-row + .property-row { border-top: 1px solid color-mix(in srgb, var(--wb-border-soft) 70%, transparent); }
.property-row code { color: var(--wb-text); font: 11px var(--font-mono, monospace); }
</style>
