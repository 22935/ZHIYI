<template>
  <InspectorSection title="本次运行" :badge="phaseLabel" :badge-tone="statusSemanticTone(lifecycle.normalizedStatus)">
    <p class="lifecycle-summary">{{ description }}</p>
    <p v-if="lifecycle.isHistorical" class="lifecycle-note">你正在查看历史运行，其执行记录保持只读。</p>
    <div v-if="lifecycle.phase === 'COMPLETED'" class="lifecycle-delivery" :class="{ 'is-missing': !lifecycle.deliverable }">
      <strong>{{ lifecycle.deliverable ? '最终交付物已就绪' : '尚未确认最终交付物' }}</strong>
      <span>{{ lifecycle.deliverable?.title || lifecycle.deliverable?.name || '运行已结束，但当前快照没有可确认的正式交付物。' }}</span>
      <button v-if="lifecycle.deliverable" type="button" @click="emit('openArtifact', lifecycle.deliverable)">查看交付物</button>
      <p v-if="provenance">来源关联：{{ inspectorValue(provenance) }}。此校验只说明产物与执行记录的关联情况。</p>
    </div>
    <div v-if="lifecycle.failure" class="lifecycle-failure">
      <strong>本次执行未完成</strong>
      <p>{{ lifecycle.failure.reason }}</p>
      <p>恢复时将创建新的运行，并重新校验执行条件。</p>
    </div>
    <InspectorPropertyList v-if="lifecycle.successorRunId || isOlderSelection" :rows="[
      ...(isOlderSelection ? [{ label: '最近创建', value: lifecycle.latestRunId, code: true }] : []),
      ...(lifecycle.successorRunId ? [{ label: '后续运行', value: lifecycle.successorRunId, code: true }] : [])
    ]" />
    <div v-if="availableActions.length" class="lifecycle-available">
      <span>当前可用</span>
      <div><span v-for="action in availableActions" :key="action">{{ capabilityLabels[action] }}</span></div>
    </div>
    <p v-else-if="!lifecycle.capabilities" class="lifecycle-note">操作状态暂时无法确认，请等待运行记录刷新。</p>
    <InspectorDetails title="其他操作为何不可用" :count="lifecycle.capabilities?.unavailableReasons.length">
      <dl class="lifecycle-reasons">
        <div v-for="reason in lifecycle.capabilities?.unavailableReasons || []" :key="reason.action">
          <dt>{{ capabilityLabels[reason.action] || '其他操作' }}</dt>
          <dd>{{ capabilityReason(reason.code) }}</dd>
        </div>
      </dl>
      <p v-if="!lifecycle.capabilities">当前缺少经校验的操作状态，系统暂不提供执行操作。</p>
    </InspectorDetails>
    <InspectorDetails title="技术详情与事实来源" description="编号、状态版本和原因码用于定位问题，可选中文字复制。">
      <InspectorPropertyList :rows="[
        { label: '运行编号', value: lifecycle.runId, code: true },
        { label: '状态版本', value: lifecycle.capabilities?.runtimeRevision },
        { label: '原始状态', value: lifecycle.rawStatus, code: true },
        { label: '后续运行', value: lifecycle.successorRunId, code: true, emptyLabel: '尚未发现' },
        { label: '产物编号', value: lifecycle.deliverable?.artifactId, code: true },
        { label: '正文引用', value: lifecycle.deliverable?.contentRef, code: true }
      ]" />
      <ul class="lifecycle-raw"><li v-for="reason in lifecycle.capabilities?.unavailableReasons || []" :key="reason.action"><code>{{ reason.action }}: {{ reason.code }}</code></li></ul>
      <InspectorDetails title="状态证据" :count="lifecycle.evidenceReferences.length">
        <ul class="lifecycle-raw"><li v-for="source in lifecycle.evidenceReferences" :key="source"><code>{{ source }}</code></li></ul>
        <p v-if="lifecycle.notObserved.length" class="lifecycle-note">尚未获取：{{ lifecycle.notObserved.join('、') }}</p>
      </InspectorDetails>
    </InspectorDetails>
  </InspectorSection>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import InspectorSection from '@/components/workbench/InspectorSection.vue'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import InspectorDetails from '@/components/workbench/InspectorDetails.vue'
import { lifecycleLabels } from '@/features/workspace/runLifecycle'
import { capabilityLabels, capabilityReason, inspectorValue } from '@/workbench/runtime/inspectorPresentation'
import { statusSemanticTone } from '@/utils/statusSemantic'
import type { WorkspaceEntry } from '@/services/api/agentos'
import type { LifecycleProjection } from '@/workbench/runtime/lifecycleProjection'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
const props = defineProps<{ lifecycle: LifecycleProjection; observation?: RuntimeObservation | null }>()
const emit = defineEmits<{ openArtifact: [entry: WorkspaceEntry] }>()
const provenance = computed(() => props.observation?.runId === props.lifecycle.runId ? props.observation.provenance.integrityStatus : null)
const phaseLabel = computed(() => lifecycleLabels[props.lifecycle.phase])
const isOlderSelection = computed(() => props.lifecycle.latestRunId && props.lifecycle.latestRunId !== props.lifecycle.runId)
const availableActions = computed(() => Object.keys(capabilityLabels).filter(action =>
  props.lifecycle.capabilities?.[action as keyof NonNullable<LifecycleProjection['capabilities']>] === true))
const description = computed(() => ({
  COMPLETED: '本次运行已完成，可以查看交付物和执行记录。',
  FAILED: '运行未能完成，请查看失败原因和可用的恢复操作。',
  CANCELLED: '本次运行已取消，已保存的执行记录仍可查看。',
  SUPERSEDED: '后续运行已接替本次运行，可以继续查看原有记录。',
  CREATED: '任务已创建，尚未选择运行。', QUEUED: '任务正在排队，等待开始执行。',
  PLANNING: '正在理解任务并编排执行计划。', RUNNING: '正在执行任务，状态会自动更新。',
  WAITING_REVIEW: '执行已暂停，等待你处理人工审核。', RECOVERING: '正在恢复执行，请留意新的运行状态。',
  AWAITING_CONFIRMATION: '计划已准备好，等待确认后继续。', ACTIVATED_PAUSED: '执行图已激活，当前处于暂停状态。',
  READY_TO_DISPATCH: '执行条件已准备好，等待正式派发。', DISPATCHED: '执行请求已派发，正在等待运行反馈。',
  UNKNOWN: '暂时无法确认运行状态，请等待记录刷新后再操作。',
}[props.lifecycle.phase]))
</script>

<style scoped>
.lifecycle-summary { margin: 0 0 12px; color: var(--wb-text); }
.lifecycle-note { color: var(--wb-text-muted); font-size: 12px; }
.lifecycle-delivery { display: grid; gap: 7px; margin: 14px 0; padding: 14px; border-radius: var(--wb-radius-md, 8px); background: var(--wb-surface-inset); }
.lifecycle-delivery > strong { font-size: 13px; color: var(--wb-text); }
.lifecycle-delivery > span { color: var(--wb-text-secondary); font-size: 12px; line-height: 1.7; }
.lifecycle-delivery > p { font-size: 11px; color: var(--wb-text-muted); }
.lifecycle-delivery button { justify-self: start; margin-top: 3px; min-height: 32px; padding: 5px 12px; border: 1px solid var(--wb-border-soft); border-radius: 6px; color: var(--wb-accent); background: var(--wb-surface-2); font: 500 12px var(--font-sans, sans-serif); cursor: pointer; }
.lifecycle-delivery button:hover { background: var(--wb-hover); }
.lifecycle-delivery button:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: 2px; }
.lifecycle-delivery.is-missing, .lifecycle-failure { border-left: 2px solid var(--wb-warning); padding-left: 12px; }
.lifecycle-available { margin-top: 14px; color: var(--wb-text-secondary); font-size: 12px; }
.lifecycle-available > div { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.lifecycle-available > div span { padding: 2px 8px; border-radius: 4px; background: var(--wb-surface-inset); }
.lifecycle-reasons { margin: 0; }
.lifecycle-reasons > div { margin-bottom: 12px; }
.lifecycle-reasons dt { font-weight: 550; color: var(--wb-text-secondary); font-size: 12px; }
.lifecycle-reasons dd { margin: 3px 0 0; color: var(--wb-text-muted); font-size: 12px; line-height: 1.65; }
.lifecycle-raw { padding-left: 16px; margin: 10px 0; }
.lifecycle-raw li { margin: 6px 0; color: var(--wb-text-muted); overflow-wrap: anywhere; font: 11px/1.65 var(--font-mono, monospace); }
</style>
