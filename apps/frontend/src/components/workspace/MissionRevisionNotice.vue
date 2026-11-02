<template>
  <section v-if="state && state.status !== 'CURRENT'" class="revision-notice" aria-label="Mission 版本差异">
    <p>当前 Mission r{{ state.targetRevision }} · 所选 Run {{ state.sourceRevision ? `r${state.sourceRevision}` : '未绑定正式版本' }}</p>
    <p>目标或约束版本已变化，尚未分析任务影响。旧 Run 保留原依据。</p>
    <p v-if="latest">已记录：{{ latest.decision === 'CONTINUE' ? '继续按旧依据执行' : '申请按所选版本重新规划' }}（目标 r{{ latest.targetRevision }}）</p>
    <p v-if="state.successorRunId">已创建后继 Run：{{ state.successorRunId }}。可在运行历史中打开。</p>
    <p v-else-if="state.decisionStatus === 'DECISION_STALE'">已记录的目标版本过期。请重新选择；旧 Run 已取消时，可从现有新建 Run 入口使用当前版本。</p>
    <template v-if="!terminal && state.targetRevision > 0">
      <button :disabled="busy || readonly || !capabilities?.canDecideRevision" @click="decide('CONTINUE')">继续按旧依据执行</button>
      <button :disabled="busy || readonly || !capabilities?.canDecideRevision" @click="decide('REQUEST_REPLAN')">申请按最新版本重新规划</button>
    </template>
    <button v-if="latest?.decision === 'REQUEST_REPLAN' && state.runStatus === 'cancelled' && !state.successorRunId && state.decisionStatus !== 'DECISION_STALE'" :disabled="busy || readonly || !capabilities?.canApplyRevision" @click="apply">按已选版本新建 Run</button>
    <p v-if="latest?.decision === 'REQUEST_REPLAN' && !terminal">请先通过 Run 的取消入口停止旧 Run，再按已选版本新建 Run。取消不会撤销已发生的操作。</p>
    <button v-if="error" :disabled="busy" @click="refresh">刷新版本与决定</button>
    <p v-if="error" role="alert">{{ error }}</p>
  </section>
  <p v-else-if="error" role="alert">{{ error }} <button @click="refresh">重试版本观察</button></p>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { agentosApi } from '@/services/api/agentos'
import type { MissionRunRevision, MissionRunRevisionDecision } from '@/services/api/agentos/api/mission'
import type { RunActionCapabilities } from '@/services/api/agentos'
import { readRunCapabilities } from '@/workbench/runtime/runCapabilities'
const props = defineProps<{ missionId: string; runId: string; revision: number; runStatus: string; readonly?: boolean; actionCapabilities?: RunActionCapabilities | null }>()
const capabilities = computed(() => readRunCapabilities(props.actionCapabilities, props.missionId, props.runId, undefined, props.runStatus))
const emit = defineEmits<{ changed: [] }>()
const state = ref<MissionRunRevision | null>(null)
const error = ref('')
const busy = ref(false)
let pending: MissionRunRevisionDecision | null = null
let generation = 0
const terminal = computed(() => ['completed', 'failed', 'cancelled', 'superseded'].includes(state.value?.runStatus || ''))
const latest = computed(() => state.value?.decisions[state.value.decisions.length - 1])
async function refresh() {
  const current = ++generation
  try {
    const result = await agentosApi.getRunRevision(props.missionId, props.runId)
    if (current === generation) { state.value = result; error.value = '' }
  } catch {
    if (current === generation) error.value = '版本观察暂不可用，请重试。'
  }
}
watch(() => [props.missionId, props.runId, props.revision], () => {
  state.value = null; pending = null; error.value = ''; void refresh()
}, { immediate: true })
watch(() => props.runStatus, () => { void refresh() })
async function decide(decision: MissionRunRevisionDecision['decision']) {
  if (!state.value || props.readonly || busy.value || !capabilities.value?.canDecideRevision) return
  if (!pending || pending.decision !== decision) pending = {
    operationId: crypto.randomUUID(), decision,
    sourceRevision: state.value.sourceRevision, targetRevision: state.value.targetRevision,
  }
  busy.value = true
  const current = generation
  const mission = props.missionId, run = props.runId
  try {
    await agentosApi.decideRunRevision(mission, run, pending)
    if (current === generation) { pending = null; await refresh(); emit('changed') }
  } catch (e: any) {
    if (current === generation) {
      error.value = e?.response?.status === 409 ? '决定已过期或冲突，请刷新后重新选择。' : '决定保存失败，重试将使用同一操作标识。'
      if (e?.response?.status === 409) pending = null
    }
  } finally { busy.value = false }
}
async function apply() {
  if (!latest.value || props.readonly || busy.value || !capabilities.value?.canApplyRevision) return
  busy.value = true
  const current = generation
  const mission = props.missionId, run = props.runId, operation = latest.value.operationId
  try {
    const result = await agentosApi.applyRunRevision(mission, run, operation)
    if (current === generation) {
      await refresh()
      error.value = result.status === 'WAITING_CANCELLATION' ? '旧 Run 正在退出，请稍后重试。' : ''
      emit('changed')
    }
  } catch (e: any) {
    if (current === generation) error.value = e?.response?.status === 409 ? '版本或运行状态已变化，请刷新。' : '新建 Run 失败，可重试已记录的决定。'
  } finally { busy.value = false }
}
</script>

<style scoped>
.revision-notice { margin-top: 16px; padding: 12px; border: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); font-size: 12px; }
button { margin: 4px; padding: 6px 10px; color: var(--wb-text); background: var(--wb-surface-inset); border: 1px solid var(--wb-border-soft); cursor: pointer; }
</style>
