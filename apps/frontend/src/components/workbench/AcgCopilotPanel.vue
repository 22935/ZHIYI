<template>
  <section class="acg-copilot" aria-label="ACG Copilot 任务助手">
    <div class="context-strip"><el-icon><Share /></el-icon><span :title="targetTitle">{{ targetTitle }}</span><small>{{ statusLabel }}</small></div>
    <nav class="copilot-tabs" aria-label="助手视图">
      <button :class="{ active: tab === 'chat' }" @click="tab = 'chat'">对话 <i v-if="state?.question || state?.review" class="attention-dot"></i></button>
      <button :class="{ active: tab === 'trace' }" @click="tab = 'trace'">轨迹 <small v-if="trajectory.length">{{ trajectory.length }}</small></button>
    </nav>

    <div v-show="tab === 'chat'" ref="messageList" class="conversation" :class="{ 'has-run-controls': hasFormalControl }" aria-live="polite" @scroll="trackScroll">
      <FormalExecutionControls :key="runId || ''" :run="controlRun" :run-id="runId"
        :mission-id="missionId || state?.missionId || ''" :historical="historical"
        :can-cancel="canCancel" :cancel-pending="cancelPending" embedded
        :readonly="readonly || historical || busy || loading || !state || permission !== 'task_collaboration'"
        :show-review="!state?.review" @refresh="refreshRun" @cancel="emit('cancel-run')" />
      <div v-if="loading && !state" class="empty-state"><el-icon class="is-loading"><Loading /></el-icon><p>正在读取任务对话…</p></div>
      <div v-else-if="!messages.length && !state?.question && !state?.review" class="empty-state">
        <img class="empty-watermark" src="/logo.webp" alt="" aria-hidden="true" />
        <h3>{{ runId ? '一起推进这项任务' : '从一项任务开始' }}</h3>
        <p>{{ runId ? '检查进展、理解问题，或一起梳理下一步。' : '选择或启动任务后，在这里与任务助手交流。' }}</p>
      </div>
      <article v-for="message in messages" :key="message.id" v-memo="[message.content, message.planner, receipts[receiptKey(message.sourceRunId, message.proposalId)], busy, loading, permission, historical]" class="message" :class="`is-${message.role}`">
        <div v-if="message.planner" class="message-meta"><small>任务澄清</small></div>
        <div class="message-content" v-html="renderMarkdown(message.content)"></div>
        <div v-if="message.action" class="operation-card">
          <strong>{{ actionLabel(message.action.kind) }}</strong>
          <p v-if="message.action.kind === 'user_input'">在当前执行片段结束后，由 Planner 重新观察并处理补充要求。</p>
          <template v-else><p>重新执行：{{ stepNames(message.action.executeStepIds) }}</p><p>复用结果：{{ stepNames(message.action.reusedStepIds) || '无' }}</p><p v-if="message.action.executionEnvironmentChanged">执行环境已更新：保持原计划与输入，使用当前可用能力重新执行。</p><small>创建新 Run，保留原运行记录与上游证据。</small></template>
          <button type="button" :disabled="busy || loading || permission !== 'task_collaboration' || readonly || historical || !!receipts[receiptKey(message.sourceRunId, message.proposalId)]" @click="confirmAction(message.proposalId, message.action, message.sourceRunId)">{{ receipts[receiptKey(message.sourceRunId, message.proposalId)] ? '已提交' : '确认操作' }}</button>
        </div>
        <div v-if="message.receipt" class="operation-receipt"><span>{{ message.receipt.kind === 'user_input' ? '等待 Planner 处理' : '运行已提交' }}</span><button v-if="message.receipt.runId !== runId" type="button" @click="emit('select-run', message.receipt.runId)">查看新运行 <el-icon><ArrowRight /></el-icon></button></div>
      </article>
      <article v-if="busy && pendingUser" class="stream-turn"><div v-if="!answering" class="message is-user"><div class="message-content">{{ pendingUser }}</div></div><div v-if="streamContent" class="message-content streaming-content" v-html="renderMarkdown(streamContent)"></div><div v-else class="stream-activity"><el-icon class="is-loading"><Loading /></el-icon><span>{{ answering ? '正在提交回答' : '正在生成回复' }}</span><div class="thinking-line"></div></div></article>
      <article v-if="state?.question" class="question-card">
        <div class="question-heading"><el-icon><ChatDotRound /></el-icon><span>需要你的补充</span><small>任务已暂停</small></div>
        <p>{{ state.question.prompt }}</p>
        <div v-if="state.question.choices.length" class="question-choices"><button v-for="choice in state.question.choices" :key="choice" :disabled="busy" @click="draft = choice; answering = true; focusComposer()">{{ choice }}</button></div>
        <button v-if="state" class="reply-link" @click="answering = true; focusComposer()">回答后继续规划 <el-icon><ArrowRight /></el-icon></button>
      </article>
      <article v-if="state?.review && !state.question" class="review-card">
          <div class="question-heading"><el-icon><Clock /></el-icon><strong>{{ state.review.decisionRejected ? (state.decision?.action === 'recover' ? '任务暂停，未能自动恢复' : '任务暂停，下一步尚未执行') : state.review.subjectType === 'planner' ? '等待继续条件确认' : '请审核当前步骤的结果' }}</strong></div>
          <p>{{ state.review.decisionRejected ? '系统未能执行建议的处理方案，任务仍处于暂停状态。可先查看失败详情，再说明需要补充的材料或调整的执行要求，生成新的处理方案。' : state.review.subjectType === 'planner' ? '确认下方说明中的等待条件已满足后，系统会重新判断能否继续执行。' : '请检查当前步骤的结果。批准后继续执行后续工作；拒绝将结束本次运行，保留已有记录。' }}</p>
        <ul v-if="failedSteps.length"><li v-for="step in failedSteps" :key="step.stepId">{{ step.name }} · 执行失败</li></ul>
          <details><summary>{{ state.review.decisionRejected ? '查看技术详情' : '查看等待原因与处理建议' }}</summary><p>暂停记录：{{ state.review.reason }}</p><p v-if="state.decision?.reason">运行决策：{{ state.decision.reason }}</p></details>
          <textarea v-model="reviewComment" rows="2" maxlength="2000" :placeholder="state.review.subjectType === 'planner' ? '说明要补充的材料或调整的执行要求…' : '填写审核意见…'" aria-label="审核意见" :disabled="busy" />
        <div class="review-actions">
          <button v-if="state.review.canApprove" :disabled="busy || loading || permission !== 'task_collaboration' || readonly || historical" @click="submitReview('approved')">{{ state.review.subjectType === 'planner' ? '确认条件已满足' : '批准并继续' }}</button>
            <button v-if="state.review.subjectType === 'planner'" :disabled="busy || loading || permission !== 'task_collaboration' || readonly || historical || !reviewComment.trim()" @click="submitReviewInput">预览调整方案</button>
          <button v-if="failedSteps.length" @click="tab = 'trace'">查看失败详情</button>
            <button :disabled="busy || loading || permission !== 'task_collaboration' || readonly || historical" @click="submitReview('rejected')">{{ state.review.subjectType === 'planner' ? '结束本次运行' : '拒绝并结束本次运行' }}</button>
        </div>
        <small v-if="permission !== 'task_collaboration' && !readonly && !historical">切换为“按需确认”权限后可操作。</small>
        <small v-if="historical">请前往当前运行处理审核。</small>
          <small v-else-if="state.review.subjectType === 'planner'">先填写调整要求并预览方案；确认后，系统才会据此重新规划。</small>
      </article>
      <div v-else-if="state?.decision && state.status === 'waiting_review' && !state.question" class="wait-note"><el-icon><Clock /></el-icon><span>{{ state.decision.reason }}</span></div>
    </div>

    <div v-if="tab === 'trace'" class="trajectory-view">
      <div class="trace-toolbar"><span>运行记录 · {{ trajectory.length }}</span><input v-model="traceSearch" placeholder="搜索步骤或调用" aria-label="搜索运行轨迹" /></div>
      <div v-if="!trajectory.length" class="empty-state"><el-icon><Connection /></el-icon><h3>尚无运行轨迹</h3><p>模型、执行步骤和工具调用会在这里留下记录。</p></div>
      <div v-else class="trace-lanes" aria-label="轨迹来源概览"><span v-for="lane in lanes" :key="lane" :class="`lane-${lane}`">{{ laneLabel(lane) }}</span><div><i v-for="event in trajectory" :key="event.id" :class="`lane-${event.kind}`" :title="event.title"></i></div></div>
      <div class="trace-list">
        <details v-for="event in filteredTrajectory" :key="event.id" class="trace-event" :class="`lane-${event.kind}`">
          <summary><span class="trace-dot"></span><span class="trace-kind">{{ laneLabel(event.kind) }}</span><div><strong>{{ event.title }}</strong><small>{{ event.step || 'Run' }} <span v-if="event.duration != null">· {{ event.duration }} ms</span></small></div><time>{{ formatTime(event.time) }}</time><el-icon><ArrowDown /></el-icon></summary>
          <pre>{{ event.detail }}</pre>
        </details>
      </div>
      <p v-if="callError" class="no-results">{{ callError }}</p>
      <button v-if="callCursor" class="load-more" :disabled="callsLoading" @click="loadCalls(true)">加载更多模型调用</button>
      <p v-if="trajectory.length && !filteredTrajectory.length" class="no-results">没有匹配的运行记录</p>
      <small class="trace-footnote">点击展开详情，查看所属步骤、调用链和运行结果。</small>
    </div>

    <div v-if="reviewReceipt" class="wait-note" role="status">{{ reviewReceipt }}</div>
    <div v-if="error" class="error-note" role="alert"><span>{{ error }}</span><button @click="refresh()">刷新</button></div>
    <div v-if="historical || readonly" class="readonly-note">{{ historical ? '历史 Run 只读，可讨论原始证据。' : '当前 Run 身份未确认，仅可讨论。' }}<button v-if="state?.latestRunId && state.latestRunId !== runId" type="button" @click="emit('select-run', state.latestRunId)">查看最新创建的 Run</button></div>
    <form ref="composerRoot" class="composer" :class="{ 'is-answering': answering && state?.question }" @submit.prevent="send" @keydown.esc="openMenu = null">
      <div v-if="state?.question" class="composer-mode"><button type="button" :class="{ selected: answering }" @click="answering = true">回答问题</button><button type="button" :class="{ selected: !answering }" @click="answering = false">询问助手</button></div>
      <textarea ref="composerInput" v-model="draft" rows="3" :maxlength="answering && state?.question ? 2000 : 4000" :disabled="!runId || busy" :placeholder="composerPlaceholder" aria-label="任务对话输入" @keydown="onKeydown"></textarea>
      <div class="composer-footer">
        <div class="composer-picker"><button type="button" class="picker-trigger" aria-label="任务操作" :disabled="busy || loading || !state || permission !== 'task_collaboration' || readonly || historical" :aria-expanded="openMenu === 'operation'" @click="openMenu = openMenu === 'operation' ? null : 'operation'"><el-icon><CircleCheck /></el-icon></button>
          <div v-if="openMenu === 'operation'" class="picker-menu operation-menu">
            <div class="menu-heading">任务操作</div>
            <button type="button" @click="prepareOperation('rerun')"><span><strong>原样重跑</strong><small>沿用当前计划与输入，创建新运行</small></span></button>
            <label>起始节点<select v-model="operationStep" aria-label="选择重跑节点"><option value="" disabled>选择一个节点</option><option v-for="step in state?.steps" :key="step.stepId" :value="step.stepId">{{ step.name }}</option></select></label>
            <button type="button" :disabled="!operationStep" @click="prepareOperation('rerun_node')"><span><strong>从指定节点重跑</strong><small>重新执行该节点及其受影响的后续步骤</small></span></button>
            <button type="button" @click="prepareOperation('recover')"><span><strong>恢复失败任务</strong><small>复用已提交结果，重试失败节点</small></span></button>
            <button type="button" :disabled="!draft.trim()" @click="prepareOperation('user_input')"><span><strong>提交补充要求</strong><small>将输入框中的要求交给 Planner 重新决策</small></span></button>
          </div>
        </div>
        <div class="composer-picker permission-picker">
          <button type="button" class="picker-trigger" aria-label="选择权限" aria-haspopup="menu" :aria-expanded="openMenu === 'permission'" :disabled="busy || !state || readonly || historical" @click="openMenu = openMenu === 'permission' ? null : 'permission'"><el-icon><Lock /></el-icon><span>{{ readonly || historical || permission === 'read_only' ? '仅对话' : '按需确认' }}</span><el-icon class="chevron"><ArrowDown /></el-icon></button>
          <div v-if="openMenu === 'permission'" class="picker-menu permission-menu" role="menu" aria-label="任务助手权限">
            <div class="menu-heading">权限范围 · 整个任务</div>
            <button v-for="option in permissionOptions" :key="option.value" type="button" role="menuitemradio" :aria-checked="permission === option.value" @click="changePermission(option.value)"><el-icon><Lock v-if="option.value === 'read_only'" /><CircleCheck v-else /></el-icon><span><strong>{{ option.label }}</strong><small>{{ option.description }}</small></span><el-icon v-if="permission === option.value" class="selected-check"><Check /></el-icon></button>
            <p>权限选择不会绕过任务的审计与执行约束。</p>
          </div>
        </div>
        <div class="composer-picker model-picker">
          <button type="button" class="picker-trigger" aria-label="选择对话模型" aria-haspopup="menu" :aria-expanded="openMenu === 'model'" :disabled="busy || !state || answering && !!state.question" @click="openMenu = openMenu === 'model' ? null : 'model'"><span :title="modelLabel">{{ modelLabel }}</span><small v-if="reasoningOptions.length">· {{ effortLabel(reasoningEffort) }}</small><el-icon class="chevron"><ArrowDown /></el-icon></button>
          <div v-if="openMenu === 'model'" class="picker-menu model-menu" role="menu" aria-label="对话模型">
            <div class="menu-heading">对话模型 <small>{{ availableModels.length }} 个可用</small></div>
            <button type="button" role="menuitemradio" :aria-checked="!selectedModel" @click="selectedModel = ''; openMenu = null"><span><strong>跟随任务模型</strong><small>{{ defaultModelLabel }}</small></span><el-icon v-if="!selectedModel" class="selected-check"><Check /></el-icon></button>
            <button v-for="model in availableModels" :key="model.id" type="button" role="menuitemradio" :aria-checked="selectedModel === model.id" @click="selectedModel = model.id; openMenu = null"><span><strong>{{ model.model }}</strong><small>{{ model.provider }}</small></span><el-icon v-if="selectedModel === model.id" class="selected-check"><Check /></el-icon></button>
            <div class="reasoning-controls"><div class="menu-heading">思考程度</div><div v-if="reasoningOptions.length" class="effort-options" role="group" aria-label="思考程度"><button v-for="effort in ['', ...reasoningOptions]" :key="effort" type="button" :aria-pressed="reasoningEffort === effort" @click="reasoningEffort = effort">{{ effortLabel(effort) }}</button></div><small v-else>此模型未声明可选的思考档位</small></div>
            <p>仅用于本次对话，不修改任务执行模型。</p>
          </div>
        </div>
        <button class="send-button" type="submit" :disabled="!canSend" :aria-label="answering && state?.question ? '提交回答并继续' : '发送消息'"><el-icon v-if="busy" class="is-loading"><Loading /></el-icon><el-icon v-else><ArrowUp /></el-icon></button>
      </div>
    </form>
    <div class="composer-caption">{{ answering && state?.question ? permission === 'read_only' ? '选择「按需确认」后，可提交回答并继续任务' : '回答由任务规划模型处理 · Enter 提交' : 'Enter 发送 · Shift + Enter 换行' }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { ArrowDown, ArrowRight, ArrowUp, ChatDotRound, Check, CircleCheck, Clock, Connection, Cpu, Loading, Lock, Share } from '@element-plus/icons-vue'
import { agentosApi, type GraphProjection, type WorkspaceEntry, type WorkspaceGraphNode, type ModelCallUsage } from '@/services/api/agentos'
import type { CopilotPermission, CopilotState, CopilotAction, CopilotActionKind } from '@/services/api/agentos/api/copilot'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
import { renderMarkdown } from '@/utils/markdown'
import { clearCopilotSession, getCopilotSession, saveCopilotSession } from './copilotSessionCache'
import FormalExecutionControls from '@/components/workspace/FormalExecutionControls.vue'

const props = withDefaults(defineProps<{
  entry?: WorkspaceEntry | null; graphNode?: WorkspaceGraphNode | null; graphNodes?: WorkspaceGraphNode[]
  graph?: GraphProjection | null; runId?: string | null; runStatus?: string | null
  runtimeObservation?: RuntimeObservation | null; historical?: boolean; readonly?: boolean
  missionId?: string; canCancel?: boolean; cancelPending?: boolean
}>(), { entry: null, graphNode: null, graphNodes: () => [], graph: null, runId: null, runStatus: null, runtimeObservation: null, historical: false, readonly: false, missionId: '', canCancel: false, cancelPending: false })
const emit = defineEmits<{ 'select-run': [runId: string]; 'refresh-run': []; 'cancel-run': [] }>()
const controlRun = computed(() => props.runtimeObservation?.runId === props.runId ? props.runtimeObservation?.run || null : null)
const hasFormalControl = computed(() => Boolean(controlRun.value?.formalControl || controlRun.value?.executionState?.planningCommitRequired))
const refreshRun = () => { emit('refresh-run'); void refresh() }
const state = ref<CopilotState | null>(null)
const sessionOwnerToken = localStorage.getItem('token')
const tab = ref<'chat' | 'trace'>('chat')
const draft = ref(''), error = ref(''), traceSearch = ref('')
const reviewComment = ref(''), reviewReceipt = ref('')
let reviewRequest: { subject: string; revision: string; decision: string; comment: string; id: string } | undefined
const loading = ref(false), busy = ref(false), answering = ref(false)
const messageList = ref<HTMLElement>(), composerInput = ref<HTMLTextAreaElement>()
const followBottom = ref(true)
const composerRoot = ref<HTMLElement>(), openMenu = ref<'model' | 'permission' | 'operation' | null>(null)
const operationStep = ref('')
const actionLabel = (kind: CopilotActionKind) => ({ rerun: '原样重跑', rerun_node: '从指定节点重跑', recover: '恢复失败任务', user_input: '提交补充要求' })[kind]
const stepNames = (ids: string[]) => ids.map(id => state.value?.steps.find(s => s.stepId === id)?.name || id).join('、')
const receiptKey = (sourceRunId: string | undefined, proposalId: string) => `${sourceRunId || props.runId}:${proposalId}`
const receipts = computed(() => Object.fromEntries((state.value?.exchanges || []).filter(e => e.receipt).map(e => [receiptKey(e.sourceRunId, e.receipt!.proposalId), e.receipt!])))
const selectedModel = ref(''), permission = ref<CopilotPermission>('task_collaboration')
const reasoningEffort = ref(''), streamContent = ref(''), pendingUser = ref('')
const availableModels = computed(() => state.value?.models || [])
const reasoningOptions = computed(() => availableModels.value.find(m => m.id === (selectedModel.value || state.value?.defaultModelId))?.reasoningEfforts || [])
const effortLabel = (value: string) => ({ low: '低', medium: '中', high: '高', max: '最高' } as Record<string, string>)[value] || '关闭'
const defaultModelLabel = computed(() => availableModels.value.find(m => m.id === state.value?.defaultModelId)?.model || state.value?.defaultModelId?.split('/').slice(1).join('/') || (state.value?.modelAvailable ? '当前任务模型' : '尚未配置模型'))
const modelLabel = computed(() => answering.value && state.value?.question ? defaultModelLabel.value : selectedModel.value ? availableModels.value.find(m => m.id === selectedModel.value)?.model || '模型已不可用' : defaultModelLabel.value)
const permissionOptions = [
  { value: 'read_only' as const, label: '仅对话', description: '查看状态、解释问题和提供建议' },
  { value: 'task_collaboration' as const, label: '按需确认', description: '对整个任务生效，跨运行持续协作；操作仍需确认与系统校验' }
]
const modelCalls = ref<ModelCallUsage[]>([]), callCursor = ref<string | null>(null), callError = ref(''), callsLoading = ref(false)
let generation = 0, timer: ReturnType<typeof setTimeout> | undefined, controller: AbortController | undefined
let viewActive = true
let viewSuspended = false
let requestKey: { content: string; target: string; id: string; options: string } | undefined
const targetTitle = computed(() => props.graphNode?.name || props.entry?.name || '当前任务')
const failedSteps = computed(() => state.value?.steps.filter(step => step.status === 'failed') || [])
const statusLabel = computed(() => ({ pending: '等待执行', planning: '规划中', running: '执行中', retrying: '准备恢复', waiting_review: state.value?.question ? '等待你的回答' : '已暂停', completed: '已完成', failed: '执行失败', cancelled: '已取消', superseded: '已替换' } as Record<string, string>)[state.value?.status || props.runStatus || ''] || '尚未启动')
const composerPlaceholder = computed(() => !props.runId ? '先选择一项任务' : answering.value && state.value?.question ? '补充你的选择或信息，让任务继续…' : '询问当前任务，或一起梳理下一步…')
const canSend = computed(() => !!props.runId && !!state.value && !loading.value && !busy.value && !!draft.value.trim() && (answering.value && state.value.question ? permission.value === 'task_collaboration' : selectedModel.value ? availableModels.value.some(m => m.id === selectedModel.value) : state.value.modelAvailable))
const messages = computed(() => [
  ...(state.value?.exchanges || []).flatMap(e => [ ...(e.user ? [{ id: `${e.sourceRunId || props.runId}:${e.operationId}-u`, role: 'user', content: e.user, time: e.createdAt, planner: false, action: undefined, receipt: undefined, proposalId: e.operationId, sourceRunId: e.sourceRunId || props.runId || undefined }] : []), { id: `${e.sourceRunId || props.runId}:${e.operationId}-a`, role: 'assistant', content: e.assistant, time: e.createdAt, planner: false, action: e.action, receipt: e.receipt, proposalId: e.operationId, sourceRunId: e.sourceRunId || props.runId || undefined }]),
  ...(state.value?.humanAnswers || []).flatMap(a => [{ id: `${a.questionId}-q`, role: 'assistant', content: a.prompt, time: a.answeredAt, planner: true, action: undefined, receipt: undefined, proposalId: '', sourceRunId: a.sourceRunId }, { id: `${a.questionId}-r`, role: 'user', content: a.answer, time: a.answeredAt, planner: true, action: undefined, receipt: undefined, proposalId: '', sourceRunId: a.sourceRunId }])
].sort((a, b) => a.time.localeCompare(b.time)))
const lanes = ['planner', 'model', 'tool', 'execution']
const laneLabel = (kind: string) => ({ planner: '规划', model: '模型', tool: '工具', execution: '执行' } as Record<string, string>)[kind] || kind
const trajectory = computed(() => {
  const calls = modelCalls.value.map(c => ({ id: `model:${c.callId}`, kind: 'model', title: `${c.model || '模型调用'} · ${c.usage.totalTokens} tokens`, time: c.createdAt || null,
    step: [c.stepId || 'Run', c.callChainId ? `调用链 ${c.callChainId}${c.partIndex != null ? ` · part ${c.partIndex}` : ''}` : ''].filter(Boolean).join(' → '), duration: c.latencyMs, detail: JSON.stringify(c, null, 2) }))
  const ids = new Set(modelCalls.value.map(c => c.callId))
  const traces = (props.runtimeObservation?.runId === props.runId ? props.runtimeObservation.traces : []).filter(e => !ids.has(String(e.payload?.callId || ''))).map(e => {
  const kind = String(e.payload?.runtimeEvent || '').startsWith('planner.') ? 'planner' : e.eventType.includes('model') ? 'model' : e.eventType.includes('tool') ? 'tool' : 'execution'
  return { id: e.eventId, kind, title: e.observation || e.eventType, time: e.timestamp, step: e.stepId, duration: e.durationMs, detail: JSON.stringify(e.payload, null, 2).slice(0, 12000) }
  })
  return [...traces, ...calls].sort((a, b) => (a.time || '').localeCompare(b.time || ''))
})
const filteredTrajectory = computed(() => trajectory.value.filter(e => `${e.title} ${e.step || ''} ${laneLabel(e.kind)}`.toLowerCase().includes(traceSearch.value.toLowerCase())))
const formatTime = (value?: string | null) => value ? new Date(value).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }) : ''
function focusComposer() { void nextTick(() => composerInput.value?.focus()) }
function trackScroll() { const e = messageList.value; if (e) followBottom.value = e.scrollHeight - e.scrollTop - e.clientHeight < 80 }
function scrollBottom() { if (followBottom.value) void nextTick(() => { const e = messageList.value; if (e) e.scrollTop = e.scrollHeight }) }
function errorMessage(e: any) { return typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : e?.response?.data?.message || e?.message || '连接暂时不可用，请重试。你的输入已保留。' }
async function changePermission(value: CopilotPermission) {
  if (!props.runId || busy.value || props.historical || props.readonly) return
  const token = generation
  busy.value = true; openMenu.value = null
  try {
    const result = await agentosApi.setCopilotPermission(props.runId, value)
    if (token === generation) { permission.value = result.taskPermission; if (state.value) state.value.taskPermission = result.taskPermission }
  } catch (e) { if (token === generation) error.value = errorMessage(e) }
  finally { if (token === generation) busy.value = false }
}
async function refresh(silent = false) {
  const id = props.runId, token = generation
  if (!id) return
  if (!silent) loading.value = true
  try {
    const next = await agentosApi.getCopilot(id, controller?.signal)
    if (token !== generation) return
    const changedQuestion = next.question?.questionId !== state.value?.question?.questionId
    state.value = next
    if (next.taskPermission) permission.value = next.taskPermission
    if (requestKey && next.exchanges.some(e => e.operationId === requestKey?.id)) { draft.value = ''; requestKey = undefined }
    if (changedQuestion) { answering.value = !!next.question; requestKey = undefined }
    if (!silent) error.value = ''
    scrollBottom()
    if (tab.value === 'trace' && !silent) void loadCalls()
  } catch (e: any) { if (token === generation && e?.code !== 'ERR_CANCELED') { error.value = errorMessage(e); if ([401, 403, 404].includes(e?.response?.status)) { state.value = null; clearCopilotSession(id) } } }
  finally { if (token === generation) loading.value = false }
}
async function loadCalls(more = false) {
  const id = props.runId, token = generation
  if (!id || callsLoading.value) return
  callsLoading.value = true
  try {
    const page = await agentosApi.listRunResourceCalls(id, { cursor: more ? callCursor.value || undefined : undefined, pageSize: 50 }, { signal: controller?.signal })
    if (token !== generation) return
    modelCalls.value = more ? [...modelCalls.value, ...page.items] : page.items
    callCursor.value = page.nextCursor || null; callError.value = ''
  } catch (e: any) { if (token === generation && e?.code !== 'ERR_CANCELED') callError.value = '模型调用记录暂时不可用，仍可查看运行事件。' }
  finally { if (token === generation) callsLoading.value = false }
}
async function send() {
  if (!canSend.value || !state.value || !props.runId) return
  const id = props.runId, token = generation, content = draft.value.trim(), question = answering.value && !props.historical && !props.readonly ? state.value.question : null
  const target = question?.questionId || 'chat'
  const options = JSON.stringify([question ? '' : selectedModel.value, permission.value, reasoningEffort.value])
  if (!requestKey || requestKey.content !== content || requestKey.target !== target || requestKey.options !== options) requestKey = { content, target, options, id: crypto.randomUUID() }
  openMenu.value = null
  busy.value = true; error.value = ''; followBottom.value = true; tab.value = 'chat'
  pendingUser.value = content; streamContent.value = ''
  try {
    if (question) await agentosApi.answerPlanner(id, question.questionId, content, state.value.revision, requestKey.id, permission.value)
    else {
      const exchange = await agentosApi.streamCopilotMessage(id, content, requestKey.id, event => {
        if (token !== generation) return
        if (event.type === 'content') { streamContent.value = event.content || ''; scrollBottom() }
      }, controller?.signal, { ...(selectedModel.value ? { modelId: selectedModel.value } : {}), permission: props.historical || props.readonly ? 'read_only' : permission.value, ...(reasoningEffort.value ? { reasoningEffort: reasoningEffort.value } : {}) })
      if (token === generation && !state.value.exchanges.some(e => e.operationId === exchange.operationId)) state.value.exchanges.push(exchange)
      if (token === generation) { pendingUser.value = ''; streamContent.value = '' }
    }
    if (token !== generation) return
    draft.value = ''; requestKey = undefined
    await refresh()
  } catch (e) { if (token === generation) { error.value = errorMessage(e); if ((e as any)?.response?.status === 409) await refresh(true) } }
  finally { if (token === generation) { busy.value = false; streamContent.value = ''; pendingUser.value = '' } }
}
async function prepareOperation(kind: CopilotActionKind) {
  if (!state.value || !props.runId || busy.value || props.historical || props.readonly || permission.value !== 'task_collaboration') return
  const id = props.runId, token = generation
  const stepId = kind === 'rerun_node' ? operationStep.value : undefined
  const content = kind === 'user_input' ? draft.value.trim() : `${actionLabel(kind)}${stepId ? `：${stepNames([stepId])}` : ''}`
  if (!content) return
  const target = `operation:${kind}:${stepId || ''}`, options = permission.value
  if (!requestKey || requestKey.content !== content || requestKey.target !== target || requestKey.options !== options) requestKey = { content, target, options, id: crypto.randomUUID() }
  busy.value = true; error.value = ''; openMenu.value = null
  try {
    const exchange = await agentosApi.previewCopilotAction(id, kind, content, requestKey.id, permission.value, stepId)
    if (token !== generation) return
    if (!state.value.exchanges.some(e => e.operationId === exchange.operationId)) state.value.exchanges.push(exchange)
    requestKey = undefined; if (kind === 'user_input') draft.value = ''
    followBottom.value = true; scrollBottom()
  } catch (e) { if (token === generation) error.value = errorMessage(e) }
  finally { if (token === generation) busy.value = false }
}
async function submitReviewInput() {
  if (!reviewComment.value.trim()) return
  draft.value = reviewComment.value.trim()
  await prepareOperation('user_input')
  tab.value = 'chat'
}
async function submitReview(decision: 'approved' | 'rejected') {
  const review = state.value?.review, id = props.runId, token = generation
  if (!review || !id || busy.value || props.historical || props.readonly || permission.value !== 'task_collaboration' || (decision === 'approved' && !review.canApprove)) return
  const comment = reviewComment.value.trim()
  if (!reviewRequest || reviewRequest.subject !== review.subjectId || reviewRequest.revision !== review.expectedRunUpdatedAt || reviewRequest.decision !== decision || reviewRequest.comment !== comment) reviewRequest = { subject: review.subjectId, revision: review.expectedRunUpdatedAt, decision, comment, id: crypto.randomUUID() }
  busy.value = true; error.value = ''
  try {
    await agentosApi.applyWorkflowReview(id, { stepId: review.subjectId, decision, comment, operationId: reviewRequest.id, expectedRunUpdatedAt: review.expectedRunUpdatedAt })
    if (token !== generation) return
    reviewReceipt.value = decision === 'approved' ? '审核已提交，正在重新判断下一步。' : '已拒绝，本次运行已结束。'
    reviewRequest = undefined; reviewComment.value = ''
    await refresh(true)
  } catch (e) { if (token === generation) { error.value = errorMessage(e); await refresh(true) } }
  finally { if (token === generation) busy.value = false }
}
async function confirmAction(proposalId: string, action: CopilotAction, sourceRunId?: string) {
  if (!props.runId || busy.value || props.historical || props.readonly || permission.value !== 'task_collaboration') return
  const id = props.runId, token = generation
  busy.value = true; error.value = ''
  try {
    const receipt = await agentosApi.applyCopilotAction(sourceRunId || id, proposalId, action.expectedRevision, permission.value)
    if (token !== generation) return
    if (state.value && !state.value.exchanges.some(e => e.operationId === receipt.operationId)) state.value.exchanges.push(receipt)
    await refresh(true); scrollBottom()
  } catch (e) { if (token === generation) { error.value = errorMessage(e); await refresh(true) } }
  finally { if (token === generation) busy.value = false }
}
watch(() => props.graphNode?.acgNodeId || props.entry?.acgNodeId, id => { operationStep.value = id || '' }, { immediate: true })
function onKeydown(e: KeyboardEvent) { if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); void send() } }
function poll() { clearTimeout(timer); if (!viewActive) return; const token = generation; const terminal = ['completed', 'failed', 'cancelled', 'superseded'].includes(state.value?.status || ''); timer = setTimeout(async () => { if (viewActive && !busy.value && !loading.value && props.runId && !document.hidden) await refresh(true); if (token === generation && viewActive) poll() }, document.hidden ? 30000 : terminal ? 15000 : 3000) }
function saveSession(id = props.runId) { if (id && state.value) saveCopilotSession(id, { state: state.value, draft: draft.value, model: selectedModel.value, permission: permission.value, effort: reasoningEffort.value, operation: requestKey }, sessionOwnerToken) }
watch(() => props.runId, (_next, previous) => {
  saveSession(previous)
  generation++; controller?.abort(); controller = new AbortController(); clearTimeout(timer)
  state.value = null; draft.value = ''; error.value = ''; busy.value = false; requestKey = undefined; answering.value = false
  reviewComment.value = ''; reviewReceipt.value = ''; reviewRequest = undefined
  selectedModel.value = ''; permission.value = 'task_collaboration'; openMenu.value = null
  reasoningEffort.value = ''; streamContent.value = ''; pendingUser.value = ''
  modelCalls.value = []; callCursor.value = null; callError.value = ''; callsLoading.value = false
  const cached = props.runId ? getCopilotSession(props.runId) : undefined
  if (cached) { state.value = cached.state; draft.value = cached.draft; selectedModel.value = cached.model; permission.value = cached.permission; reasoningEffort.value = cached.effort; requestKey = cached.operation; answering.value = !!cached.state.question }
  void refresh(); poll()
}, { immediate: true })
watch(tab, value => { if (value === 'trace') void loadCalls() })
watch(reasoningOptions, options => { if (!options.includes(reasoningEffort.value)) reasoningEffort.value = '' })
watch(draft, () => void nextTick(() => { const e = composerInput.value; if (e) { e.style.height = 'auto'; e.style.height = `${Math.min(180, Math.max(76, e.scrollHeight))}px` } }))
function closePickers(e: PointerEvent) { if (!composerRoot.value?.contains(e.target as Node)) openMenu.value = null }
onMounted(() => document.addEventListener('pointerdown', closePickers))
onDeactivated(() => { viewActive = false; viewSuspended = true; clearTimeout(timer); document.removeEventListener('pointerdown', closePickers) })
onActivated(() => { if (!viewSuspended) return; viewSuspended = false; viewActive = true; document.addEventListener('pointerdown', closePickers); if (!busy.value && !loading.value) void refresh(true); poll() })
onBeforeUnmount(() => { saveSession(); generation++; controller?.abort(); clearTimeout(timer); document.removeEventListener('pointerdown', closePickers) })
</script>

<style scoped>
.review-card { margin: 16px 0; padding: 18px; border: 1px solid var(--cp-border); border-radius: 12px; background: var(--wb-surface-section); font-size: 13px; line-height: 1.7; }
.review-card strong { color: var(--wb-text); }
.review-card p { margin: 10px 0; }
.review-card details { color: var(--wb-text-secondary); margin: 12px 0; }
.review-card textarea { box-sizing: border-box; width: 100%; padding: 10px; border: 1px solid var(--cp-border); border-radius: 8px; background: transparent; color: inherit; resize: vertical; font: inherit; }
.review-actions { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.review-actions button { padding: 7px 10px; border: 1px solid var(--cp-border); border-radius: 7px; background: var(--wb-accent-soft); color: var(--wb-accent); cursor: pointer; }
.review-actions button:disabled { opacity: .45; cursor: not-allowed; }
.acg-copilot { display:flex; flex-direction:column; width:100%; height:100%; min-height:0; color:var(--wb-text); background:var(--wb-surface-1); font-family:var(--font-sans,sans-serif); --cp-border:var(--wb-border-soft); }
button { font:inherit; cursor:pointer; }
button:disabled { cursor:not-allowed; opacity:.4; }
button:focus-visible, input:focus-visible { outline:2px solid var(--wb-accent); outline-offset:2px; }
.context-strip { display:flex; align-items:center; gap:7px; margin:0 14px 12px; padding-top:13px; font-size:11px; color:var(--wb-text-muted); }
.context-strip > span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }
.context-strip > small { margin-left:auto; flex-shrink:0; color:var(--wb-text-secondary); background:var(--wb-surface-section); padding:3px 7px; border-radius:5px; font-size:10px; }
.copilot-tabs { display:flex; gap:22px; padding:0 16px; border-bottom:1px solid var(--cp-border); }
.copilot-tabs button { position:relative; padding:0 0 10px; border:0; color:var(--wb-text-muted); background:transparent; font-size:12px; }
.copilot-tabs button.active { color:var(--wb-text); }
.copilot-tabs button.active::after { content:''; position:absolute; left:0; right:0; bottom:-1px; height:2px; background:var(--wb-accent); border-radius:2px; }
.copilot-tabs small { margin-left:4px; font:10px var(--font-mono,monospace); }
.attention-dot { display:inline-block; width:5px; height:5px; border-radius:50%; margin-left:4px; background:var(--wb-accent); }
.conversation,.trajectory-view { flex:1; min-height:0; overflow:auto; scrollbar-width:thin; padding:18px 16px; }
.empty-state { display:flex; flex-direction:column; align-items:center; justify-content:center; text-align:center; min-height:230px; height:100%; color:var(--wb-text-muted); }
.conversation.has-run-controls > .empty-state { height:auto; min-height:180px; padding:24px 0; }
.empty-watermark { display:block; width:148px; height:148px; object-fit:contain; margin-bottom:6px; animation:copilot-watermark-pulse 3.2s ease-in-out infinite; }
.empty-state h3 { margin:0 0 7px; color:var(--wb-text); font-size:14px; font-weight:650; }
.empty-state p { margin:0; max-width:280px; color:var(--wb-text-secondary); font-size:12px; line-height:1.65; }
.message { margin-bottom:24px; min-width:0; }
.message-meta { display:flex; align-items:center; gap:6px; margin-bottom:8px; color:var(--wb-text-muted); font-size:10px; }
.message-meta > .el-icon { color:var(--wb-accent); }
.message-meta time { margin-left:auto; font:9px var(--font-mono,monospace); }
.message-meta small { color:var(--wb-accent); font-size:9px; }
.stream-activity { display:flex; align-items:center; gap:7px; color:var(--wb-text-muted); font-size:11px; }
.stream-turn { margin-bottom:24px; }
.streaming-content { min-height:24px; }
.message.is-user { width:fit-content; max-width:92%; margin-left:auto; padding:10px 13px; border-radius:12px; background:var(--wb-surface-section); border:1px solid var(--cp-border); }
.message-content { color:var(--wb-text-secondary); font-size:13px; line-height:1.75; overflow-wrap:anywhere; text-wrap:pretty; }
.message-content :deep(p) { margin:0 0 10px; }
.message-content :deep(p:last-child) { margin-bottom:0; }
.message-content :deep(h1),.message-content :deep(h2),.message-content :deep(h3) { margin:16px 0 8px; font-size:14px; color:var(--wb-text); }
.message-content :deep(ul),.message-content :deep(ol) { padding-left:20px; }
.message-content :deep(pre) { overflow:auto; padding:10px; border-radius:8px; background:var(--wb-surface-inset); font:11px/1.6 var(--font-mono,monospace); }
.message-content :deep(a) { color:var(--wb-accent); }
.message-content :deep(table) { display:block; max-width:100%; overflow:auto; border-collapse:collapse; }
.message-content :deep(td),.message-content :deep(th) { padding:6px; border:1px solid var(--cp-border); }
.question-card { margin:8px 0 18px; padding:14px; border:1px solid color-mix(in srgb,var(--wb-accent) 45%,var(--cp-border)); border-radius:12px; background:color-mix(in srgb,var(--wb-accent) 4%,var(--wb-surface-section)); }
.operation-card { margin-top:12px; padding:12px; border:1px solid var(--cp-border); border-radius:10px; background:var(--wb-surface-section); font-size:12px; }
.operation-card p { margin:9px 0; line-height:1.7; overflow-wrap:anywhere; }
.operation-card small { display:block; color:var(--wb-text-muted); line-height:1.6; }
.operation-card button,.operation-receipt button { margin-top:10px; padding:7px 10px; border:1px solid var(--cp-border); border-radius:6px; background:var(--wb-accent-soft); color:var(--wb-accent); font-size:11px; }
.operation-receipt { display:flex; gap:10px; align-items:center; font-size:11px; color:var(--wb-text-muted); }
.operation-receipt button { margin:0; }
.operation-menu label { display:grid; gap:7px; padding:8px; font-size:11px; color:var(--wb-text-muted); }
.operation-menu select { width:100%; padding:7px; border:1px solid var(--cp-border); border-radius:6px; color:var(--wb-text); background:var(--wb-surface-1); }
.question-heading { display:flex; align-items:center; gap:7px; color:var(--wb-accent); font-size:11px; }
.question-heading small { margin-left:auto; color:var(--wb-text-muted); font-size:10px; }
.question-card p { font-size:13px; line-height:1.7; margin:12px 0; white-space:pre-wrap; overflow-wrap:anywhere; }
.question-choices { display:grid; gap:7px; }
.question-choices button { padding:9px 11px; border:1px solid var(--cp-border); border-radius:7px; color:var(--wb-text-secondary); background:var(--wb-surface-1); text-align:left; font-size:12px; }
.question-choices button:hover { border-color:var(--wb-accent); }
.reply-link { display:flex; align-items:center; gap:7px; padding:0; margin-top:13px; border:0; background:transparent; color:var(--wb-accent); font-size:11px; }
.wait-note { display:flex; gap:8px; padding:12px; color:var(--wb-text-muted); font-size:12px; line-height:1.6; border:1px solid var(--cp-border); border-radius:9px; }
.composer { position:relative; margin:8px 12px 0; padding:16px 14px 10px; border:1px solid var(--cp-border); border-radius:17px; background:var(--wb-surface-section); box-shadow:0 3px 12px #0000000a; }
.composer:focus-within { border-color:color-mix(in srgb,var(--wb-text-muted) 60%,var(--cp-border)); }
.composer textarea { display:block; box-sizing:border-box; width:100%; min-height:76px; max-height:180px; resize:none; padding:0 2px; border:0; outline:0; background:transparent; color:var(--wb-text); font:13px/1.7 var(--font-sans,sans-serif); scrollbar-width:thin; }
.composer textarea::placeholder { color:var(--wb-text-muted); }
.composer-footer { display:flex; align-items:center; gap:6px; margin-top:12px; min-width:0; }
.composer-picker { min-width:0; }
.permission-picker { flex-shrink:0; }
.model-picker { margin-left:auto; flex:0 1 auto; }
.picker-trigger { display:flex; align-items:center; gap:5px; max-width:100%; padding:5px 3px; border:0; border-radius:6px; background:transparent; color:var(--wb-text-secondary); font-size:11px; }
.picker-trigger:hover,.picker-trigger[aria-expanded=true] { background:var(--wb-hover); color:var(--wb-text); }
.picker-trigger > span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; min-width:0; }
.picker-trigger .el-icon { flex-shrink:0; font-size:12px; }
.picker-trigger .chevron { font-size:9px; color:var(--wb-text-muted); }
.picker-trigger > small { flex-shrink:0; font-size:10px; color:var(--wb-text-muted); }
.permission-picker .picker-trigger > .el-icon:first-child { color:var(--wb-warning); }
.picker-menu { position:absolute; z-index:20; bottom:52px; right:8px; left:8px; padding:6px; max-height:320px; overflow:auto; scrollbar-width:thin; border:1px solid var(--wb-border); border-radius:12px; background:var(--wb-surface-section); box-shadow:0 8px 28px #00000040; }
.menu-heading { display:flex; justify-content:space-between; padding:8px 8px 7px; color:var(--wb-text-muted); font-size:10px; }
.menu-heading small { font-size:10px; }
.picker-menu button { display:flex; align-items:center; gap:9px; width:100%; padding:10px 8px; border:0; border-radius:7px; text-align:left; background:transparent; color:var(--wb-text-secondary); }
.picker-menu button:hover,.picker-menu button[aria-checked=true] { background:var(--wb-hover); color:var(--wb-text); }
.picker-menu button > span { min-width:0; flex:1; }
.picker-menu strong { display:block; font-size:12px; font-weight:500; overflow-wrap:anywhere; }
.picker-menu small { display:block; margin-top:4px; font-size:10px; line-height:1.5; color:var(--wb-text-muted); }
.picker-menu .selected-check { color:var(--wb-accent); }
.picker-menu p { margin:7px 8px 4px; padding-top:8px; border-top:1px solid var(--cp-border); color:var(--wb-text-muted); font-size:10px; line-height:1.5; }
.reasoning-controls { border-top:1px solid var(--cp-border); padding:4px 4px 8px; }
.reasoning-controls > small { display:block; padding:4px 8px; }
.effort-options { display:flex; gap:4px; }
.effort-options button { justify-content:center; padding:7px 3px; font-size:11px; }
.effort-options button[aria-pressed=true] { background:var(--wb-accent-soft); color:var(--wb-accent); }
.send-button { display:grid; place-items:center; width:30px; height:30px; flex-shrink:0; border:0; border-radius:50%; background:var(--wb-text); color:var(--wb-surface-1); font-size:17px; }
.send-button:disabled { background:var(--wb-hover); color:var(--wb-text-muted); opacity:.7; }
.composer-caption { text-align:center; padding:8px 12px 10px; color:var(--wb-text-muted); font-size:9px; }
.composer-mode { display:flex; gap:5px; margin-bottom:10px; }
.composer-mode button { border:0; background:transparent; color:var(--wb-text-muted); border-radius:5px; padding:4px 7px; font-size:10px; }
.composer-mode .selected { color:var(--wb-accent); background:var(--wb-accent-soft); }
.error-note { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:8px 12px; padding:10px; background:var(--wb-surface-section); border:1px solid var(--cp-border); border-radius:8px; color:var(--wb-text-secondary); font-size:11px; line-height:1.5; }
.error-note button { flex-shrink:0; border:0; color:var(--wb-accent); background:transparent; }
.readonly-note { padding:6px 16px; color:var(--wb-text-muted); font-size:10px; }
.thinking-line { height:3px; width:70px; background:var(--wb-accent-soft); border-radius:4px; animation:pulse 1.3s infinite alternate; }
.trajectory-view { padding:12px 0; }
.trace-toolbar { display:flex; gap:10px; align-items:center; padding:0 12px 12px; color:var(--wb-text-muted); font-size:10px; }
.trace-toolbar span { flex-shrink:0; }
.trace-toolbar input { min-width:0; width:100%; border:1px solid var(--cp-border); border-radius:6px; color:var(--wb-text); background:var(--wb-surface-section); padding:6px 8px; font:10px var(--font-sans,sans-serif); }
.trace-lanes { display:flex; align-items:center; flex-wrap:wrap; gap:7px; padding:10px 12px; border-block:1px solid var(--cp-border); font-size:9px; }
.trace-lanes > div { flex:1 1 100%; display:flex; gap:3px; overflow:hidden; min-width:0; }
.trace-lanes i { width:5px; height:7px; min-width:3px; background:currentColor; border-radius:1px; }
.lane-planner { color:var(--wb-accent); }.lane-model { color:var(--wb-artifact); }.lane-tool { color:var(--wb-warning); }.lane-execution { color:var(--wb-success); }
.trace-event { border-bottom:1px solid var(--cp-border); }
.trace-event summary { display:flex; align-items:center; gap:7px; padding:11px 12px; cursor:pointer; list-style:none; }
.trace-event summary::-webkit-details-marker { display:none; }
.trace-event summary:hover { background:var(--wb-hover); }
.trace-dot { flex-shrink:0; width:5px; height:5px; border-radius:50%; background:currentColor; }
.trace-kind { font-size:9px; flex-shrink:0; }
.trace-event summary > div { flex:1; min-width:0; }
.trace-event strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:11px; font-weight:450; color:var(--wb-text-secondary); }
.trace-event small { display:block; margin-top:4px; color:var(--wb-text-muted); font:9px var(--font-mono,monospace); }
.trace-event time { font-size:9px; color:var(--wb-text-muted); flex-shrink:0; }
.trace-event summary > .el-icon { font-size:10px; color:var(--wb-text-muted); }
.trace-event pre { margin:0; padding:12px; overflow:auto; max-height:220px; background:var(--wb-surface-inset); color:var(--wb-text-secondary); font:10px/1.6 var(--font-mono,monospace); }
.trace-footnote { display:block; padding:14px; color:var(--wb-text-muted); font-size:10px; line-height:1.6; }
.no-results { padding:15px; color:var(--wb-text-muted); font-size:12px; }
.load-more { display:block; margin:12px auto; padding:7px 12px; border:1px solid var(--cp-border); border-radius:7px; background:transparent; color:var(--wb-text-secondary); font-size:11px; }
@keyframes copilot-watermark-pulse { 0%,100% { opacity:.85; transform:scale(.985); } 50% { opacity:1; transform:scale(1); } }
@keyframes pulse { from { opacity:.4; } to { opacity:1; } }
@media(prefers-reduced-motion:reduce) { .thinking-line { animation:none; } .empty-watermark { animation:none; } }
@media(max-width:340px) { .conversation { padding:14px 12px; }.trace-event time { display:none; } }
</style>
