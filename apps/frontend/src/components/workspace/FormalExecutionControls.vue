<template>
  <section v-if="visible" class="formal-control" :class="{ 'is-embedded': embedded }" aria-label="正式运行控制">
    <FormalToolApprovals v-if="!historical && !readonly && runId" :run-id="runId" :active="run?.status === 'running'" />
    <header><strong>{{ embedded ? '任务进展' : '运行控制' }}</strong><button type="button" :disabled="pending" @click="emit('refresh')">刷新</button></header>
    <dl v-if="!embedded" aria-live="polite">
      <div><dt>任务</dt><dd>{{ run?.status || '状态不可用' }}</dd></div>
      <div><dt>图</dt><dd>{{ control?.status || '证据不可用' }}</dd></div>
      <div><dt>许可</dt><dd>{{ control?.permitStatus || '尚未签发' }}</dd></div>
      <div><dt>执行命令</dt><dd>{{ control?.dispatch?.status || '尚未提交' }}</dd></div>
    </dl>
    <p class="formal-control__hint">{{ explanation }}</p>
    <p v-if="run?.failureCode || run?.error?.code" role="status" class="formal-control__error">{{ run.failureCode || run.error?.code }}</p>
    <div class="formal-control__actions">
      <button v-if="action" type="button" class="formal-control__primary" :disabled="disabled" @click="submit">
        {{ pending ? '正在提交…' : error && !blocked ? '重试原操作' : formalActionLabels[action] }}
      </button>
      <button v-if="canCancel && !historical" type="button" :disabled="readonly || pending || cancelPending || !run" @click="emit('cancel')">
        {{ cancelPending ? '正在取消…' : '取消任务' }}
      </button>
    </div>
    <p v-if="error" class="formal-control__error" role="alert">{{ error }}</p>
    <small v-if="readonly && !historical && action">当前视图仅供查看，正式操作已禁用。</small>
    <WorkflowReviewPanel v-if="showReview && run?.status === 'waiting_review' && !historical && !blocked && !readonly" :run-id="run.runId"
      :run="reviewRun" :progress="null" compact @reviewed="emit('refresh')" @conflict="emit('refresh')" />
    <details v-if="control"><summary>{{ embedded ? '运行状态与授权引用' : '授权与关联引用' }}</summary><dl>
      <template v-if="embedded">
        <div><dt>任务</dt><dd>{{ run?.status || '状态不可用' }}</dd></div>
        <div><dt>图</dt><dd>{{ control.status }}</dd></div>
        <div><dt>许可</dt><dd>{{ control.permitStatus || '尚未签发' }}</dd></div>
        <div><dt>执行命令</dt><dd>{{ control.dispatch?.status || '尚未提交' }}</dd></div>
      </template>
      <div v-for="(value, key) in references" :key="key"><dt>{{ key }}</dt><dd :title="String(value)">{{ value || '—' }}</dd></div>
    </dl></details>
  </section>
</template>

<script setup lang="ts">
import FormalToolApprovals from './FormalToolApprovals.vue'
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { agentosApi, type WorkflowRun } from '@/services/api/agentos'
import WorkflowReviewPanel from '@/components/agentos/WorkflowReviewPanel.vue'
import { formalActionLabels, formalSource, nextFormalAction, prepareFormalCommand } from '@/features/acg/formalControl'

const props = withDefaults(defineProps<{ run: WorkflowRun | null; runId: string | null; missionId: string; historical: boolean; canCancel: boolean; cancelPending: boolean; embedded?: boolean; readonly?: boolean; showReview?: boolean }>(), { embedded: false, readonly: false, showReview: true })
const emit = defineEmits<{ refresh: []; cancel: [] }>()
const pending = ref(false)
const error = ref('')
const blocked = ref(false)
const acknowledged = ref('')
const seenFormal = ref(false)
let generation = 0
onBeforeUnmount(() => { generation++ })
watch(() => props.runId, () => { generation++; pending.value = false; error.value = ''; blocked.value = false; acknowledged.value = ''; seenFormal.value = false })
watch(() => props.run?.formalControl, c => { if (c) seenFormal.value = true }, { immediate: true })
const control = computed(() => props.run?.formalControl)
const visible = computed(() => seenFormal.value || Boolean(control.value) || props.run?.executionState?.planningCommitRequired)
const action = computed(() => props.run?.runId === props.runId && props.run?.missionId === props.missionId ? nextFormalAction(props.run) : null)
const source = computed(() => action.value && props.run ? formalSource(props.run, action.value) : '')
watch(source, () => { error.value = ''; blocked.value = false })
const disabled = computed(() => props.readonly || pending.value || blocked.value || props.historical || acknowledged.value === source.value)
const reviewRun = computed(() => props.run ? { ...props.run, review: props.run.review || props.run.executionState?.reviewPayload } : null)
const references = computed(() => ({ Commit: control.value?.commitId, Graph: control.value?.graphId, Version: control.value?.graphVersion,
  Activation: control.value?.activationId, Handoff: control.value?.handoffId, Permit: control.value?.permitId, Dispatch: control.value?.dispatch?.dispatchId }))
const explanation = computed(() => {
  if (!props.run || !control.value) return '无法验证正式状态，控制操作已禁用。'
  if (props.historical) return '历史 Run 只读。'
  if (props.run.status === 'completed') return props.embedded ? '任务已完成，可从左侧查看或下载交付文件。' : '运行已完成；已登记的 Artifact 可从左侧打开或下载，最终交付以正式引用为准。'
  if (['failed', 'cancelled'].includes(props.run.status)) return props.run.lifecycleMessage || '运行已停止。请查看下方故障与恢复证据。'
  if (props.run.status === 'waiting_review') return '等待审核；审核决定由正式接口处理。'
  if (props.run.status === 'running' || props.run.status === 'retrying') return '以 Run 查询与节点事件观察实际执行。'
  if (control.value.dispatch) return '执行命令已持久接受，等待正式运行状态更新。202 不代表完成。'
  if (control.value.permitStatus === 'ISSUED') return control.value.dispatchEnabled
    ? '许可已签发，尚未执行。点击“执行任务”才会提交执行命令。'
    : '许可已签发；当前服务未开启正式 Dispatch，控制保持只读。'
  if (control.value.handoffStatus === 'STATE_PREPARED') return '执行交接已准备，仍需申请许可。'
  if (control.value.status === 'ACTIVATED_PAUSED') return '任务图已激活，执行保持暂停。'
  if (control.value.status === 'PLANNING_ACCEPTED') return '正式规划已接受，可准备任务图。'
  if (action.value === 'activate') return '任务图已物化，尚未激活。'
  return '等待正式规划或可验证状态；未识别的状态禁止控制操作。'
})
const submit = async () => {
  if (!action.value || !props.run || disabled.value) return
  const current = generation
  const run = props.run
  const requestedAction = action.value
  const requestedSource = source.value
  pending.value = true
  error.value = ''
  let prepared = false
  try {
    const command = prepareFormalCommand(run, requestedAction, localStorage)
    prepared = true
    await agentosApi.submitFormalControl(props.missionId, run.runId, requestedAction, command)
    if (current !== generation) return
    acknowledged.value = requestedSource
    emit('refresh') // No optimistic Run/Permit state and no follow-on command.
  } catch (failure: unknown) {
    if (current !== generation) return
    const status = (failure as { response?: { status?: number } }).response?.status
    blocked.value = !prepared || status === 401 || status === 403 || status === 409 || status === 422
    error.value = !prepared ? '操作重试记录不可用或已损坏，控制已禁用。'
      : blocked.value ? '授权或版本校验未通过，控制已禁用。请刷新检查正式状态。'
      : '提交结果未确认。可重试原操作；不会生成新的 operationId。'
    emit('refresh')
  } finally {
    if (current === generation) pending.value = false
  }
}
</script>

<style scoped>
.formal-control { flex: 0 0 auto; max-height: 58%; overflow: auto; padding: 10px 12px; border-bottom: 1px solid var(--wb-border-soft); color: var(--wb-text); background: var(--wb-surface-pane); font-size: 12px; }
.formal-control.is-embedded { max-height: none; overflow: visible; margin-bottom: 16px; padding: 10px 12px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); background: var(--wb-surface-inset); }
header, .formal-control__actions { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
header strong { font-size: 12px; font-weight: 600; }
dl { display: grid; gap: 5px; margin: 10px 0; }
dl > div { display: grid; grid-template-columns: 70px minmax(0, 1fr); gap: 8px; }
dt { color: var(--wb-text-muted); }
dd { margin: 0; min-width: 0; overflow-wrap: anywhere; font: 11px/1.5 var(--font-mono, monospace); }
button { min-height: 26px; padding: 3px 8px; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-sm); color: var(--wb-text); background: var(--wb-surface-inset); cursor: pointer; font-size: 12px; }
button:hover:not(:disabled) { background: var(--surface-hover); }
button:focus-visible, summary:focus-visible { outline: 1px solid var(--wb-accent); outline-offset: 2px; }
button:disabled { opacity: .5; cursor: default; }
.formal-control__primary { color: var(--on-primary); background: var(--primary-color); }
.formal-control__primary:hover:not(:disabled) { background: var(--primary-hover); }
.formal-control__hint { color: var(--wb-text-secondary); line-height: 1.6; margin: 8px 0; }
.formal-control__error { color: var(--wb-danger); line-height: 1.6; overflow-wrap: anywhere; }
details { margin-top: 10px; color: var(--wb-text-muted); }
summary { cursor: pointer; }
</style>
