<template>
  <TaskArtifactDocument
    :entry="entry"
    :projection="projection"
    :graph-node="graphNode"
    :artifacts="artifacts"
    :document="artifactDocument"
    :stage-output-content="stageOutputContent"
    :stage-output-loading="stageOutputLoading"
    :stage-output-error="stageOutputError"
    :selected-symbol-id="selectedSymbolId"
    :result-id-prefix="resultIdPrefix"
    :run-number="runNumber"
    :task-number="taskNumber"
    :mission-title="missionTitle"
    @locate-graph="emit('locateGraph')"
    @open-artifact="emit('openArtifact', $event)"
    @open-entry="emit('openEntry', $event)"
    @select-result="selectResultItem"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { runDisplayObjective } from './missionSemanticDisplay'
import { agentosApi } from '@/services/api/agentos'
import type {
  MissionWorkspaceProjection,
  WorkspaceEntry,
  WorkspaceGraphNode
} from '@/services/api/agentos'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import type { RuntimeEventStore } from '@/workbench/runtime/runtimeEvents'
import type { RunDocumentSymbol } from '@/workbench/runtime/runDocument'
import { projectArtifactDocument, type ArtifactDocumentModel } from '@/workbench/runtime/artifactProjection'
import TaskArtifactDocument from './TaskArtifactDocument.vue'
import type { StageOutputSelection } from './StageOutputRenderer.vue'

const props = defineProps<{
  entry: WorkspaceEntry
  projection: MissionWorkspaceProjection
  graphNodes: WorkspaceGraphNode[]
  selectedSymbolId?: string | null
  runtimeObservation: RuntimeObservation | null
  runtimeStore?: RuntimeEventStore | null
}>()

const emit = defineEmits<{
  locateGraph: []
  openArtifact: [entry: WorkspaceEntry]
  openEntry: [entry: WorkspaceEntry]
  selectSymbol: [symbol: RunDocumentSymbol]
  artifactProjection: [payload: { entryId: string; projection: ArtifactDocumentModel }]
}>()

const graphNode = computed(() => props.graphNodes.find(node => (
  (props.entry.semanticTaskKey && node.semanticTaskKey === props.entry.semanticTaskKey)
  || (props.entry.acgNodeId && node.acgNodeId === props.entry.acgNodeId)
)) || null)
const artifacts = computed(() => props.projection.entries
  .filter(item => item.kind === 'artifact' && item.semanticTaskKey === props.entry.semanticTaskKey)
  .sort((left, right) => left.displayOrder - right.displayOrder || left.entryId.localeCompare(right.entryId)))
const liveNode = computed(() => {
  const nodeId = graphNode.value?.acgNodeId || props.entry.acgNodeId
  return nodeId ? props.runtimeStore?.nodes[nodeId] || null : null
})
const outputRef = computed(() => {
  const candidates = [
    props.entry.metadata?.outputRef,
    ...artifacts.value.map(item => item.metadata?.outputRef)
  ]
  return candidates.find(value => typeof value === 'string' && value) as string | undefined || null
})
const outputRunId = computed(() => props.entry.runId || props.projection.activeRun?.runId || null)
const persistedStageOutput = ref('')
const stageOutputLoading = ref(false)
const stageOutputError = ref('')

const formatStageOutput = (value: unknown) => {
  if (typeof value === 'string') return value
  try { return JSON.stringify(value, null, 2) } catch { return String(value ?? '') }
}

watch([outputRunId, outputRef], async ([runId, refValue], _previous, onCleanup) => {
  persistedStageOutput.value = ''
  stageOutputError.value = ''
  stageOutputLoading.value = false
  if (!runId || !refValue) return
  const controller = new AbortController()
  onCleanup(() => controller.abort())
  stageOutputLoading.value = true
  try {
    const result = await agentosApi.getRunOutput(runId, refValue, { signal: controller.signal })
    if (controller.signal.aborted) return
    persistedStageOutput.value = result.content == null ? '' : formatStageOutput(result.content)
    if (result.content == null || persistedStageOutput.value.trim() === '') {
      stageOutputError.value = '步骤已完成，但结果正文为空。'
    }
  } catch {
    if (!controller.signal.aborted) stageOutputError.value = '阶段结果暂时无法读取。'
  } finally {
    if (!controller.signal.aborted) stageOutputLoading.value = false
  }
}, { immediate: true })

const stageOutputContent = computed(() => {
  const node = liveNode.value
  // A completed stream can be partial or truncated; the committed result is authoritative.
  if (node && !['COMPLETED', 'FAILED', 'CANCELLED'].includes(node.status) && node.outputBuffer) {
    return node.outputBuffer
  }
  return persistedStageOutput.value
})
const resultIdPrefix = computed(() => `task-result:${props.entry.semanticTaskKey || props.entry.entryId}`)
const artifactDocument = computed(() => projectArtifactDocument({
  entry: props.entry,
  artifacts: artifacts.value,
  output: stageOutputContent.value
}))
watch(artifactDocument, projection => emit('artifactProjection', {
  entryId: props.entry.entryId,
  projection
}), { immediate: true })

const shorten = (value: string, length: number) => value.length > length ? `${value.slice(0, length)}…` : value
const missionTitle = computed(() => shorten(runDisplayObjective(props.projection).split(/[\n。！？!?]/)[0].trim(), 34))
const runId = computed(() => props.entry.runId || props.projection.activeRun?.runId || null)
const runNumber = computed(() => {
  const index = props.projection.runs.findIndex(run => run.runId === runId.value)
  return String(index >= 0 ? index + 1 : 1).padStart(2, '0')
})
const taskNumber = computed(() => {
  const tasks = props.projection.entries.filter(item => item.kind === 'task').sort((left, right) => left.displayOrder - right.displayOrder)
  const index = tasks.findIndex(item => item.entryId === props.entry.entryId)
  return String(index >= 0 ? index + 1 : 1).padStart(2, '0')
})
const resultSymbol = (selection: StageOutputSelection): RunDocumentSymbol => ({
  id: `${resultIdPrefix.value}:${selection.sectionKey}:${selection.index}`,
  type: 'result',
  status: 'completed',
  title: selection.title,
  subtitle: selection.source ? `${selection.sectionKey} · ${selection.source}` : selection.sectionKey,
  detail: selection.source ? `Reference ${selection.source}` : selection.sectionKey,
  runId: outputRunId.value || '',
  semanticTaskKey: props.entry.semanticTaskKey,
  graphNodeId: graphNode.value?.acgNodeId,
  children: [],
  content: formatStageOutput(selection.value)
})
const selectResultItem = (selection: StageOutputSelection) => emit('selectSymbol', resultSymbol(selection))
</script>
