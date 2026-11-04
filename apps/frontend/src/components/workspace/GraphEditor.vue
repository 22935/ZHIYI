<template>
  <section class="graph-editor" aria-label="graph.acg">
    <header class="graph-editor__header">
      <div class="graph-editor__title">
        <span class="graph-editor__eyebrow">GRAPH EDITOR</span>
        <strong>graph.acg</strong>
        <small v-if="graph">Graph {{ graph.graphId }} · v{{ graphVersion || '—' }}</small>
      </div>
      <span v-if="selectedSemanticTaskKey" class="graph-editor__selection">{{ selectedSemanticTaskKey }}</span>
    </header>
    <div class="graph-editor__canvas">
      <AcgTopologyGraph
        :blueprint="graph"
        :focus-node-id="focusNodeId"
        :runtime-phases="runtimePhases"
        :step-states="stepStates"
        :completed-step-ids="completedStepIds"
        :run-id="runId"
        :workbench="true"
        :observe-resize="true"
        @node-selected="handleNodeSelected"
        @node-double-clicked="handleNodeDoubleClicked"
      />
      <div v-if="!graph" class="graph-editor__empty">
        <strong>Graph unavailable</strong>
        <span>当前 Run 没有可展示的图快照。</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RuntimeEventStore } from '@/workbench/runtime/runtimeEvents'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import { stepStatesFromRun } from '@/services/api/agentos/api/acg'
import AcgTopologyGraph from '@/components/agentos/AcgTopologyGraph.vue'
import type { GraphProjection, WorkspaceGraphNode } from '@/services/api/agentos'

const props = defineProps<{
  graph: GraphProjection | null
  graphNodes: WorkspaceGraphNode[]
  selectedSemanticTaskKey: string | null
  focusNodeId: string | null
  runId?: string | null
  runtimeStore?: RuntimeEventStore | null
  runtimeObservation?: RuntimeObservation | null
}>()
const runtimePhases = computed(() => Object.fromEntries(Object.entries(props.runtimeStore?.nodes || {}).map(([id, state]) => [id, state.phase])))
// SSE 只覆盖本次连接之后的事件（无历史回放），刷新后 runtimeStore 为空。
// 图节点状态必须回落到 runtimeObservation 轮询的 run.steps 持久投影（StepStatus）。
const observedRun = computed(() => (
  props.runtimeObservation?.run && props.runtimeObservation.runId === props.runId
    ? props.runtimeObservation.run : null
))
const stepStates = computed(() => observedRun.value
  ? stepStatesFromRun(observedRun.value, props.runtimeObservation?.executionTree, props.runtimeObservation?.lifecycles)
  : [])
const completedStepIds = computed(() => observedRun.value?.completedStepIds || [])

const emit = defineEmits<{
  selectSemanticTask: [semanticTaskKey: string | null]
  openSemanticTask: [semanticTaskKey: string | null]
}>()

const graphVersion = computed(() => {
  const snapshot = props.graph as (GraphProjection & { graphVersion?: number }) | null
  return snapshot?.graphVersion
})

const resolveSemanticKey = (nodeId: string) => props.graphNodes.find(node => node.acgNodeId === nodeId)?.semanticTaskKey || null
const handleNodeSelected = (nodeId: string) => emit('selectSemanticTask', resolveSemanticKey(nodeId))
const handleNodeDoubleClicked = (nodeId: string) => emit('openSemanticTask', resolveSemanticKey(nodeId))
</script>

<style scoped>
.graph-editor { display: flex; flex: 1 1 auto; flex-direction: column; width: 100%; min-width: 0; height: 100%; min-height: 0; overflow: hidden; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-section); background: var(--wb-surface-section); color: var(--wb-text); box-shadow: var(--wb-shadow-section); }
.graph-editor__header { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 26px; padding: 3px 16px; border-bottom: 1px solid var(--wb-border-soft); background: var(--wb-surface-section); }
.graph-editor__title { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
.graph-editor__header strong { color: var(--wb-text); font-size: 12px; }
.graph-editor__header small { overflow: hidden; color: var(--wb-text-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.graph-editor__eyebrow { color: var(--wb-accent); font: 10px var(--font-mono, monospace); letter-spacing: .1em; }
.graph-editor__selection { max-width: 40%; overflow: hidden; color: var(--wb-text-secondary); font: 10px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.graph-editor__canvas { position: relative; flex: 1; min-height: 0; overflow: hidden; }
.graph-editor__canvas :deep(.acg-topology) { height: 100%; border: 0; border-radius: 0; box-shadow: none; }
.graph-editor__canvas :deep(.acg-topology .panel-head) { display: none; }
.graph-editor__canvas :deep(.acg-topology .graph-surface) { height: 100%; }
.graph-editor__canvas :deep(.acg-topology .graph-stage) { height: 100%; }
.graph-editor__empty { position: absolute; inset: 50% auto auto 50%; display: grid; gap: 5px; transform: translate(-50%, -50%); color: var(--wb-text-secondary); text-align: center; }
.graph-editor__empty strong { color: var(--wb-text); font-size: 14px; }
.graph-editor__empty span { font-size: 12px; }
</style>
