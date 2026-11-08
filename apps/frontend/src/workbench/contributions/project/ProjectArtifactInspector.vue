<template>
  <InspectorSection title="当前产物" :badge="available ? undefined : 'missing'">
    <button class="inspector-link" type="button" :disabled="!canLocateGraph" @click="emit('locateGraph')">在图中定位</button>
    <InspectorPropertyList :rows="[{ label: '名称', value: entry.title || entry.name }, { label: '内容格式', value: entry.mediaType }, { label: '身份状态', value: entry.identityQuality }]" />
    <p v-if="evidenceLoading" role="status">正在读取产物验证与来源…</p>
    <p v-else-if="evidenceError" role="status">{{ evidenceError }}</p>
    <ArtifactVerification v-else-if="outputProjection?.artifactKind === 'final_report' || outputProjection?.verification" :verification="outputProjection?.verification" />
    <InspectorDetails v-if="outputProjection?.inspector.evidenceRefs.length" title="证据与来源引用" :count="outputProjection.inspector.evidenceRefs.length">
      <p v-for="reference in outputProjection.inspector.evidenceRefs" :key="reference" class="artifact-source">{{ reference }}</p>
    </InspectorDetails>
    <InspectorDetails title="产物技术详情" description="产物编号、正文校验值与生成它的执行记录。">
    <InspectorPropertyList :rows="[
      { label: 'semanticTaskKey', value: entry.semanticTaskKey, code: true },
      { label: 'artifactKey', value: entry.artifactKey, code: true },
      { label: 'artifactId', value: entry.artifactId, code: true },
      { label: 'producerAttemptId', value: entry.attemptId, code: true },
      { label: 'runId', value: entry.runId || runId, code: true },
      { label: 'acgNodeId', value: entry.acgNodeId, code: true },
      { label: 'mediaType', value: entry.mediaType, code: true },
      { label: 'checksum', value: entry.checksum || '由 ContentManifest 提供', code: true },
      { label: 'disposition', value: entry.disposition, code: true },
      { label: 'sourceRunId', value: entry.sourceRunId, code: true }
    ]" />
    </InspectorDetails>
  </InspectorSection>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { agentosApi, type WorkspaceEntry } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import InspectorDetails from '@/components/workbench/InspectorDetails.vue'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import ArtifactVerification from '@/components/workspace/ArtifactVerification.vue'
import { projectArtifactDocument, type ArtifactDocumentModel } from '@/workbench/runtime/artifactProjection'

const props = defineProps<{
  entry: WorkspaceEntry
  available: boolean
  runId: string | null
  entries?: WorkspaceEntry[]
}>()

const outputProjection = ref<ArtifactDocumentModel | null>(null)
const evidenceLoading = ref(false)
const evidenceError = ref('')
const outputRef = computed(() => {
  const task = props.entries?.find(item => item.kind === 'task' && item.semanticTaskKey
    && item.semanticTaskKey === props.entry.semanticTaskKey && (!item.runId || item.runId === props.runId))
  const value = props.entry.metadata?.outputRef || task?.metadata?.outputRef
  return typeof value === 'string' ? value : null
})
watch([() => props.entry, () => props.runId, () => props.available, outputRef], async (_value, _old, onCleanup) => {
  outputProjection.value = null
  evidenceError.value = ''
  evidenceLoading.value = false
  if (!props.available || !props.runId || !outputRef.value) return
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  const entry = props.entry
  const runId = props.runId
  evidenceLoading.value = true
  try {
    const result = await agentosApi.getRunOutput(runId, outputRef.value, { signal: controller.signal })
    if (!controller.signal.aborted) outputProjection.value = projectArtifactDocument({ entry, output: result.content })
  } catch {
    if (!controller.signal.aborted) evidenceError.value = '产物验证与来源暂时无法读取；当前空白不代表没有记录。'
  } finally {
    if (!controller.signal.aborted) evidenceLoading.value = false
  }
}, { immediate: true })

const emit = defineEmits<{ locateGraph: [] }>()
const canLocateGraph = computed(() => props.available && props.entry.identityQuality !== 'legacy' && Boolean(props.entry.semanticTaskKey))
</script>

<style scoped>
.artifact-source { overflow-wrap: anywhere; color: var(--wb-text-secondary); font: 11px/1.7 var(--font-mono, monospace); }
.inspector-link { margin: 0 0 10px; padding: 0; border: 0; color: var(--primary-color); background: transparent; cursor: pointer; font-size: 11px; }
.inspector-link:disabled { color: var(--text-disabled); cursor: not-allowed; }
</style>
