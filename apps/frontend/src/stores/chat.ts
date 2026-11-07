import { localFetch } from '@/platform/api'
import type { ChatApprovalMode } from '@/config/chatApproval'
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatStreamErrorMessage, parseChatStreamFrame, type ChatStreamEvent } from '@/utils/sse'
import { apiUrl } from '@/platform'
import type { AsyncWorkflowStartResponse } from '@/services/api/workflow'
import type { ConversationLaunchContext } from '@/features/mission/request'
import { conversationInput, projectedInput, type ContextCheckpoint } from '@/features/chat/compaction'
import { conversationLaunchCommand, matchesConversationLaunchContext } from '@/features/mission/command'
import { createMissionLaunchAttempt, MissionLaunchStateError } from '@/features/mission/launchAttempt'
import type { MissionLaunchResult } from '@/features/mission/launch'
import { chatApi, type ChatRequest } from '@/services/api/chat'
import { loadModelSettings, toModelRequestSettings, type ModelSettings } from '@/config/modelSettings'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { conversationApi } from '@/services/api/conversation'
import { getConversationWorkspace, setConversationWorkspace, type ConversationWorkspaceMode } from '@/utils/conversationWorkspace'
import { conversationBindings, mergeDraftBindings, isActiveRunStatus } from '@/features/workspace/session'

export interface TerminalExecution {
  command: string
  cwd: string
  exitCode: number | null
  stdout: string
  stderr: string
  timedOut: boolean
  truncated: boolean
  durationMs?: number
}

export interface ToolExecutionActivity {
  kind: 'file_read' | 'file_list' | 'file_write' | 'file_patch' | 'terminal' | string
  capabilityId?: string
  relativePath?: string
  status?: string
  summary?: string
  addedLines?: number
  removedLines?: number
  entryCount?: number
  errorCode?: string
}

export interface ChatApproval {
  approvalId: string
  toolCallId: string
  invocationId: string
  toolName: string
  capabilityId: string
  relativePath?: string
  operationSummary: string
  createdAt: string
  status: 'pending' | 'approved' | 'denied' | 'expired' | string
  sessionId: string
  operation?: string
  command?: string
  cwd?: string
  riskNotice?: string
}

export interface ExecutionSummaryItem {
  stage: string
  status: string
  description: string
  durationMs?: number
  terminal?: TerminalExecution
  activity?: ToolExecutionActivity
  approval?: ChatApproval
}

export interface Message {
  id: number | string
  role: 'user' | 'assistant'
  content: string
  fileUrl?: string
  createdAt?: Date
  timestamp?: number
  audioUrl?: string
  animation?: any
  confidence?: number
  tokensUsed?: number
  sources?: any[]
  reasoningPath?: any[]
  modelInfo?: string
  thinkingState?: 'thinking' | 'complete' | 'error'
  streamError?: string
  streamActivity?: 'receiving' | 'waiting' | 'complete'
  streamPhase?: string
  thinkingDurationMs?: number
  reasoningContent?: string
  reasoningTruncated?: boolean
  requestedThinkingMode?: string
  effectiveThinkingMode?: string
  effectiveReasoningEffort?: string
  inputTokens?: number
  reasoningTokens?: number
  outputTokens?: number
  latencyMs?: number
  executionSummary?: ExecutionSummaryItem[]
  skillsUsed?: string[]
  trace?: Array<Record<string, unknown>>

  agentMode?: 'default'
  acgTaskId?: string
  workflowRunId?: string
  workflowMissionId?: string
  workflowId?: string
  workflowStatus?: string
  workflowClientRequestId?: string
  runtimeEngine?: string
  implementationId?: string
}

export interface ChatWorkflowBinding {
  conversationId: string
  conversationAliases?: string[]
  messageId?: string
  missionId: string
  acgTaskId: string
  runId: string
  workflowId?: string
  source: 'agent' | 'chat'
  clientRequestId: string
  createdAt: string
  status: string
  invalidAt?: string
}

export interface ChatWorkflowStartResult {
  response: AsyncWorkflowStartResponse
  binding: ChatWorkflowBinding
  launch: MissionLaunchResult
}

export const useChatStore = defineStore('chat', () => {
  const approvalMode = ref<ChatApprovalMode>('ask')
  const WORKFLOW_BINDINGS_KEY = 'chat.workflow_bindings.v1'
  const loadWorkflowBindings = (): Record<string, ChatWorkflowBinding[]> => {
    try {
      const parsed = JSON.parse(localStorage.getItem(WORKFLOW_BINDINGS_KEY) || '{}')
      if (!parsed || typeof parsed !== 'object') return {}
      return Object.fromEntries(
        Object.entries(parsed).map(([conversationId, value]) => [
          conversationId,
          (Array.isArray(value) ? value : [])
            .filter(item => item && typeof item.runId === 'string' && item.runId.trim())
            .map(item => ({
              ...item,
              conversationAliases: Array.isArray(item.conversationAliases)
                ? item.conversationAliases.filter((key: unknown) => typeof key === 'string') : undefined,
              acgTaskId: typeof item.acgTaskId === 'string' && item.acgTaskId.trim()
                ? item.acgTaskId.trim()
                : item.runId.trim(),
              source: item.source === 'agent' ? 'agent' : 'chat'
            }))
        ])
      ) as Record<string, ChatWorkflowBinding[]>
    } catch {
      return {}
    }
  }
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const isStreaming = ref(false)
  const isLoadingConversation = ref(false)
  const isCompacting = ref(false)
  const compactionNotice = ref('')
  // Page-lifetime projections only; raw messages and stored history stay intact.
  const contextCheckpoints = new Map<string, ContextCheckpoint>()
  const workflowBindings = ref<Record<string, ChatWorkflowBinding[]>>(loadWorkflowBindings())
  const workflowRunsStore = useWorkflowRunsStore()
  let activeStreamController: AbortController | null = null
  let activeRequestId: string | null = null
  const contextId = ref<string | null>(null)
  const currentRoleId = ref<string | null>(null)
  const historyError = ref<string | null>(null)
  const conversationWorkspaceMode = ref<ConversationWorkspaceMode | null>(null)
  let historyGeneration = 0
  let messageGeneration = 0
  // Transport cancellation is best effort; only the current owner may write UI state.
  const invalidateMessageRequest = () => {
    ++messageGeneration
    activeStreamController?.abort()
    activeStreamController = null
    activeRequestId = null
    isStreaming.value = false
    isCompacting.value = false
    compactionNotice.value = ''
    loading.value = false
  }
  // Context window usage for the composer indicator: tokens consumed by the
  // latest exchange (input + output ≈ what the next request will carry) and
  // the resolved model context window.
  const contextUsedTokens = ref<number | null>(null)
  const contextWindowTokens = ref<number | null>(null)
  const contextModel = ref<string | null>(null)
  const contextModels = ref<Record<string, number>>({})

  const applyContextUsage = (used: number | null, model?: string | null, windowTokens?: number | null) => {
    if (model) contextModel.value = model
    if (typeof windowTokens === 'number' && windowTokens > 0) {
      contextWindowTokens.value = windowTokens
      if (model) contextModels.value = { ...contextModels.value, [model]: windowTokens }
    } else if (model && contextModels.value[model]) {
      contextWindowTokens.value = contextModels.value[model]
    }
    contextUsedTokens.value = typeof used === 'number' && used >= 0 ? used : null
  }

  const fetchContextWindows = async () => {
    try {

      const response = await localFetch(apiUrl('/ai/chat/models'), {
      })
      if (!response.ok) return
      const data = await response.json() as { context_windows?: Record<string, unknown> }
      const windows = data?.context_windows && typeof data.context_windows === 'object'
        ? Object.fromEntries(
            Object.entries(data.context_windows)
              .filter(([, value]) => typeof value === 'number' && (value as number) > 0)
          )
        : {}
      if (!Object.keys(windows).length) return
      contextModels.value = { ...contextModels.value, ...windows } as Record<string, number>
      if (!contextWindowTokens.value && contextModel.value && windows[contextModel.value]) {
        contextWindowTokens.value = windows[contextModel.value] as number
      }
    } catch {
      // The indicator simply stays hidden when the catalog is unavailable.
    }
  }

  const pushUserMessage = (text: string, fileUrl?: string) => {
    const userMessage: Message = {
      id: Date.now(),
      role: 'user',
      content: text || (fileUrl ? '[文件]' : ''),
      createdAt: new Date()
    }
    if (fileUrl) {
      userMessage.fileUrl = fileUrl
    }
    messages.value.push(userMessage)
    return userMessage
  }

  const persistWorkflowBindings = () => {
    localStorage.setItem(WORKFLOW_BINDINGS_KEY, JSON.stringify(workflowBindings.value))
  }

  const addWorkflowBinding = (binding: ChatWorkflowBinding) => {
    const associated = conversationBindings(workflowBindings.value, binding.conversationId)
      .find(item => item.runId === binding.runId)
    if (associated) binding = { ...binding, conversationId: associated.conversationId,
      conversationAliases: associated.conversationAliases }
    const existing = workflowBindings.value[binding.conversationId] || []
    workflowBindings.value = {
      ...workflowBindings.value,
      [binding.conversationId]: [...existing.filter(item => item.runId !== binding.runId), binding]
    }
    persistWorkflowBindings()
    workflowRunsStore.registerChatBinding(binding)
  }

  const getLatestWorkflowBinding = (conversationId: string) => {
    const bindings = conversationBindings(workflowBindings.value, conversationId)
    return [...bindings].reverse().find(binding => !binding.invalidAt)
  }

  const getActiveWorkflowBinding = (conversationId: string) => {
    const bindings = conversationBindings(workflowBindings.value, conversationId)
    return [...bindings].reverse().find(binding =>
      !binding.invalidAt && isActiveRunStatus(binding.status)
    )
  }

  const migrateDraftBindings = (draft: string, targetContextId: string) => {
    if (contextId.value !== targetContextId || isLoadingConversation.value) return
    const sourceRuns = (workflowBindings.value[draft] || []).map(item => item.runId)
    const next = mergeDraftBindings(workflowBindings.value, draft, targetContextId)
    if (next === workflowBindings.value) return
    workflowBindings.value = next
    persistWorkflowBindings()
    workflowRunsStore.reassociateConversation(draft, targetContextId, sourceRuns)
  }

  const updateWorkflowBindingStatus = (conversationId: string, runId: string, status: string) => {
    conversationId = conversationBindings(workflowBindings.value, conversationId).find(item => item.runId === runId)?.conversationId || conversationId
    const bindings = workflowBindings.value[conversationId] || []
    if (!bindings.some(binding => binding.runId === runId)) return
    workflowBindings.value = {
      ...workflowBindings.value,
      [conversationId]: bindings.map(binding => binding.runId === runId
        ? { ...binding, status }
        : binding)
    }
    persistWorkflowBindings()
    workflowRunsStore.updateObservedState(runId, status)
  }

  const markWorkflowBindingInvalid = (conversationId: string, runId: string) => {
    conversationId = conversationBindings(workflowBindings.value, conversationId).find(item => item.runId === runId)?.conversationId || conversationId
    const bindings = workflowBindings.value[conversationId] || []
    if (!bindings.some(binding => binding.runId === runId)) return
    workflowBindings.value = {
      ...workflowBindings.value,
      [conversationId]: bindings.map(binding => binding.runId === runId
        ? { ...binding, invalidAt: new Date().toISOString() }
        : binding)
    }
    persistWorkflowBindings()
    workflowRunsStore.markInvalid(runId)
  }

  const emitHistoryRefresh = () => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('history-refresh'))
    }
  }

  const compactionModelKey = (settings: ModelSettings) => JSON.stringify([
    settings.provider, settings.selectedModel, settings.provider === 'system' ? '' : settings.baseUrl, currentRoleId.value
  ])

  const currentProjectedInput = (settings: ModelSettings) => {
    if (!contextId.value || conversationWorkspaceMode.value === 'agent') return
    const checkpoint = contextCheckpoints.get(contextId.value)
    const projected = projectedInput(checkpoint, conversationInput(messages.value), compactionModelKey(settings))
    if (checkpoint && !projected) contextCheckpoints.delete(contextId.value)
    return projected
  }

  const compactContext = async (settings: ModelSettings = loadModelSettings()) => {
    if (loading.value || isLoadingConversation.value) return
    if (historyError.value) throw new Error(historyError.value)
    if (conversationWorkspaceMode.value === 'agent') throw new Error('/compact 仅用于 OScode 对话')
    const owner = contextId.value
    const source = conversationInput(messages.value)
    if (!owner || !source.length) {
      compactionNotice.value = '暂无可压缩的上下文，请先开始对话。'
      return
    }
    const generation = ++messageGeneration
    const isCurrent = () => generation === messageGeneration && contextId.value === owner
    const modelKey = compactionModelKey(settings)
    const controller = new AbortController()
    activeStreamController = controller
    loading.value = true
    isCompacting.value = true
    compactionNotice.value = '正在压缩上下文，完整聊天记录会保留…'
    try {
      const model = toModelRequestSettings(settings)
      const response = await chatApi.compactContext({
        context_id: owner, context: currentProjectedInput(settings) || source,
        role_id: currentRoleId.value || undefined, model: model.model,
        base_url: settings.provider === 'system' ? undefined : settings.baseUrl,
        api_key: settings.provider === 'system' ? undefined : settings.apiKey
      }, controller.signal)
      if (!isCurrent()) return
      if (response.contextId !== owner || JSON.stringify(conversationInput(messages.value)) !== JSON.stringify(source)) {
        throw new Error('对话内容已变化，本次压缩结果未应用，请重试。')
      }
      if (response.status === 'summarized' || response.status === 'pruned') {
        if (contextCheckpoints.size >= 8 && !contextCheckpoints.has(owner)) {
          contextCheckpoints.delete(contextCheckpoints.keys().next().value!)
        }
        contextCheckpoints.set(owner, { source, projected: response.messages, modelKey })
        const before = Number(response.metrics.inputTokens), after = Number(response.metrics.outputTokens)
        applyContextUsage(after, response.model, response.contextWindowTokens)
        compactionNotice.value = `上下文已压缩：估算 ${before.toLocaleString()} → ${after.toLocaleString()} Token。本页后续对话使用摘要，完整记录保留。`
      } else if (response.status === 'failed_passthrough') {
        compactionNotice.value = '本次摘要未通过压缩校验，继续使用原上下文。可以稍后重试。'
      } else {
        compactionNotice.value = '暂无可压缩的历史内容，近期对话已保留。'
      }
      return response
    } catch (error) {
      if (isCurrent()) {
        compactionNotice.value = '上下文压缩未完成，原上下文已保留。'
        throw error
      }
    } finally {
      if (isCurrent()) {
        isCompacting.value = false
        loading.value = false
        activeStreamController = null
      }
    }
  }

  const sendMessage = async (
    text: string,
    fileUrl?: string,
    runtimeSettings?: ModelSettings,
    workspaceMode: 'agent' | 'chat' = 'chat'
  ) => {
    if ((!text.trim() && !fileUrl) || loading.value) return
    if (historyError.value) throw new Error(historyError.value)

    const generation = ++messageGeneration
    const isCurrent = () => generation === messageGeneration
    const settings = runtimeSettings || loadModelSettings()
    const compacted = workspaceMode === 'chat' ? currentProjectedInput(settings) : undefined
    pushUserMessage(text, fileUrl)

    loading.value = true
    try {
      const request: ChatRequest = {
        text: text || '',
        roleId: currentRoleId.value || undefined,
        contextId: contextId.value || undefined,
        workspaceMode: contextId.value ? conversationWorkspaceMode.value || workspaceMode : workspaceMode,
        fileUrl: fileUrl || undefined,
        context: compacted,
        ...toModelRequestSettings(runtimeSettings || loadModelSettings())
      }

      const response = await chatApi.sendMessage(request)
      if (!isCurrent()) return
      contextId.value = response.contextId

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.text,
        createdAt: new Date(),
        confidence: response.confidence,
        tokensUsed: response.tokensUsed,
        sources: response.sources,
        reasoningPath: response.reasoningPath,
        modelInfo: response.modelInfo,
        requestedThinkingMode: response.metadata?.requestedThinkingMode,
        effectiveThinkingMode: response.metadata?.effectiveThinkingMode,
        effectiveReasoningEffort: response.metadata?.effectiveReasoningEffort,
        inputTokens: response.metadata?.inputTokens,
        reasoningTokens: response.metadata?.reasoningTokens,
        outputTokens: response.metadata?.outputTokens,
        latencyMs: response.metadata?.latencyMs,
        executionSummary: response.metadata?.executionSummary,
        agentMode: 'default'
      }
      messages.value.push(assistantMessage)
      emitHistoryRefresh()

      return response
    } catch (error) {
      if (isCurrent()) throw error
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  // ---- 流式发送（SSE）----

  const sendMessageStream = async (
    text: string,
    agentMode: 'default' = 'default',
    runtimeSettings: ModelSettings = loadModelSettings(),
    workspaceMode: 'agent' | 'chat' = 'chat'
  ) => {
    if ((!text.trim()) || loading.value) return
    if (historyError.value) throw new Error(historyError.value)

    const generation = ++messageGeneration
    const isCurrent = () => generation === messageGeneration
    const modelRequestSettings = toModelRequestSettings(runtimeSettings)
    const compacted = workspaceMode === 'chat' ? currentProjectedInput(runtimeSettings) : undefined

    pushUserMessage(text)
    loading.value = true
    isStreaming.value = true

    const streamMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
      modelInfo: runtimeSettings.selectedModel || '系统默认',
      thinkingState: runtimeSettings.thinkingMode === 'disabled' ? undefined : 'thinking',
      requestedThinkingMode: runtimeSettings.thinkingMode,
      reasoningContent: '',
      streamActivity: 'receiving',
      streamPhase: '解析任务意图',
      agentMode
    }
    messages.value.push(streamMsg)
    const streamMessage = messages.value[messages.value.length - 1]
    const ownedMessage = () => isCurrent() ? streamMessage : undefined
    const thinkingStartedAt = performance.now()
    let terminal: 'done' | 'error' | 'cancelled' | null = null
    const finishThinking = (state: 'complete' | 'error', durationMs?: number) => {
      const message = ownedMessage()
      if (!message) return
      if (!message.thinkingState && message.requestedThinkingMode === 'disabled') return
      message.thinkingState = state
      message.thinkingDurationMs = Math.max(0, durationMs ?? (performance.now() - thinkingStartedAt))
    }
    const appendStreamContent = (delta: string) => {
      const message = ownedMessage()
      if (message) {
        finishThinking('complete')
        message.content = (message.content || '') + delta
      }
    }
    const appendReasoningContent = (delta: string) => {
      const message = ownedMessage()
      if (message) message.reasoningContent = (message.reasoningContent || '') + delta
    }
    const failStream = (description: string, state: 'error' | 'cancelled' = 'error') => {
      terminal = state
      finishThinking('error')
      const message = ownedMessage()
      if (!message) return
      message.streamActivity = 'complete'
      message.streamPhase = state === 'cancelled' ? '已停止生成' : '请求未完成'
      message.streamError = description
      if (!message.content) message.content = description
    }
    const applyStreamEvent = (event: ChatStreamEvent) => {
      if (terminal === 'error' || terminal === 'cancelled') return
      const message = ownedMessage()
      if (!message) return
      const data = event.data || {}
      if (event.event !== 'heartbeat' && event.event !== 'done' && event.event !== 'error') {
        message.streamActivity = 'receiving'
      }
      if (event.requestId && event.requestId !== 'unknown' && event.requestId !== 'legacy') {
        activeRequestId = event.requestId
      }
      const upsertToolSummary = (status: string, payload: Record<string, any> = data) => {
        const approval = payload.approval && typeof payload.approval === 'object'
          ? payload.approval as ChatApproval
          : undefined
        const toolName = String(payload.toolName || approval?.toolName || 'unknown')
        const callId = String(payload.callId || approval?.toolCallId || toolName)
        const stage = `tool:${toolName}:${callId}`
        const duration = typeof payload.durationMs === 'number' ? payload.durationMs : undefined
        const description = status === 'completed'
          ? `${toolName} 调用完成${duration === undefined ? '' : `（${duration}ms）`}`
          : status === 'failed'
            ? `${toolName} 调用失败：${payload.errorCode || 'TOOL_FAILED'}`
            : `${toolName} 调用中`
        const summaries = message.executionSummary || []
        const index = summaries.findIndex(item => item.stage === stage)
        const existing = index >= 0 ? summaries[index] : undefined
        const terminal = payload.terminal && typeof payload.terminal === 'object'
          ? payload.terminal as TerminalExecution
          : existing?.terminal
        const activity = payload.activity && typeof payload.activity === 'object'
          ? payload.activity as ToolExecutionActivity
          : existing?.activity
        const next: ExecutionSummaryItem = {
          stage,
          status,
          description,
          durationMs: duration,
          ...(terminal ? { terminal } : {}),
          ...(activity ? { activity } : {}),
          ...(approval ? { approval } : existing?.approval ? { approval: existing.approval } : {})
        }
        if (index >= 0) summaries[index] = next
        else summaries.push(next)
        message.executionSummary = [...summaries]
      }
      const phaseForTool = (toolName: string) => {
        const phases: Record<string, string> = {
          read_file: '读取工作文件',
          list_files: '浏览工作区',
          write_file: '写入目标文件',
          patch_file: '应用局部修改',
          run_command: '执行受控命令',
          terminal: '执行受控命令'
        }
        return phases[toolName] || '调用工作工具'
      }
      const mergeSources = (items: unknown) => {
        if (!Array.isArray(items)) return
        const existing = message.sources || []
        const keys = new Set(existing.map(item => item.citationId || item.url || item.title))
        for (const source of items) {
          if (!source || typeof source !== 'object') continue
          const typed = source as Record<string, any>
          const key = typed.citationId || typed.url || typed.title
          if (!keys.has(key)) {
            existing.push(typed)
            keys.add(key)
          }
        }
        message.sources = [...existing]
      }
      switch (event.event) {
        case 'heartbeat':
          message.streamActivity = 'waiting'
          message.streamPhase = '等待模型继续'
          break
        case 'reasoning_start':
          message.streamActivity = 'receiving'
          message.streamPhase = '解析任务意图'
          message.thinkingState = 'thinking'
          message.requestedThinkingMode = data.requestedThinkingMode || message.requestedThinkingMode
          message.effectiveThinkingMode = data.effectiveThinkingMode
          message.effectiveReasoningEffort = data.effectiveReasoningEffort
          break
        case 'reasoning_delta':
          message.streamActivity = 'receiving'
          if (typeof data.delta === 'string') appendReasoningContent(data.delta)
          break
        case 'reasoning_end':
          message.streamPhase = '构建工作上下文'
          finishThinking('complete', typeof data.reasoningPhaseMs === 'number' ? data.reasoningPhaseMs : undefined)
          break
        case 'content_delta':
          message.streamActivity = 'receiving'
          message.streamPhase = '组织最终回复'
          if (typeof data.delta === 'string') appendStreamContent(data.delta)
          break
        case 'tool_start':
          message.streamActivity = 'receiving'
          message.streamPhase = phaseForTool(String(data.toolName || ''))
          upsertToolSummary('running')
          break
        case 'tool_result':
          message.streamActivity = 'receiving'
          message.streamPhase = '整理工具结果'
          upsertToolSummary('completed', data)
          mergeSources(data.sources)
          break
        case 'tool_error':
          message.streamPhase = '处理工具异常'
          upsertToolSummary('failed', data)
          break
        case 'approval_required':
          message.streamPhase = '等待操作确认'
          upsertToolSummary('approval_required', data)
          break
        case 'approval_resolved':
          message.streamPhase = '确认已通过，继续执行'
          upsertToolSummary('approval_resolved', data)
          break
        case 'execution_started':
          message.streamPhase = '执行受控命令'
          upsertToolSummary('running', data)
          break
        case 'stdout_delta':
        case 'stderr_delta':
          message.streamPhase = '读取命令输出'
          upsertToolSummary('running', data)
          break
        case 'execution_completed':
          message.streamPhase = '整理执行结果'
          upsertToolSummary('completed', data)
          break
        case 'execution_failed':
          message.streamPhase = '处理执行异常'
          upsertToolSummary('failed', data)
          break
        case 'execution_cancelled':
          message.streamPhase = '执行已取消'
          upsertToolSummary('cancelled', data)
          break
        case 'usage':
          message.inputTokens = data.input_tokens ?? data.inputTokens
          message.reasoningTokens = data.reasoning_tokens ?? data.reasoningTokens
          message.outputTokens = data.output_tokens ?? data.outputTokens
          message.tokensUsed = data.total_tokens ?? data.totalTokens
          message.latencyMs = data.latencyMs
          message.modelInfo = data.effectiveModel || message.modelInfo
          message.requestedThinkingMode = data.requestedThinkingMode || message.requestedThinkingMode
          message.effectiveThinkingMode = data.effectiveThinkingMode || message.effectiveThinkingMode
          message.effectiveReasoningEffort = data.effectiveReasoningEffort || message.effectiveReasoningEffort
          {
            const usedInput = message.inputTokens
            const usedOutput = message.outputTokens
            const contextUsed = typeof usedInput === 'number'
              ? usedInput + (typeof usedOutput === 'number' ? usedOutput : 0)
              : (typeof message.tokensUsed === 'number' ? message.tokensUsed : null)
            applyContextUsage(
              contextUsed,
              message.modelInfo || null,
              data.contextWindowTokens ?? data.context_window_tokens
            )
          }
          break
        case 'done':
          if (data.status && data.status !== 'completed') {
            failStream(data.status === 'cancelled' ? '已停止生成' : chatStreamErrorMessage(data.code, data.message),
              data.status === 'cancelled' ? 'cancelled' : 'error')
            break
          }
          terminal = 'done'
          message.streamActivity = 'complete'
          message.streamPhase = '已完成'
          if (typeof data.contextId === 'string' && data.contextId) contextId.value = data.contextId
          if (Array.isArray(data.toolExecutions)) {
            for (const execution of data.toolExecutions) {
              if (execution && typeof execution === 'object') {
                upsertToolSummary(
                  execution.status === 'completed' ? 'completed' : 'failed',
                  execution as Record<string, any>
                )
              }
            }
          }
          mergeSources(data.sources)
          finishThinking(message.content ? 'complete' : 'error')
          break
        case 'error':
          failStream(chatStreamErrorMessage(data.code, data.message))
          break
      }
    }

    const streamController = new AbortController()
    activeStreamController = streamController
    activeRequestId = null
    try {
      const resp = await localFetch(apiUrl('/ai/chat/text/stream'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        signal: streamController.signal,
        body: JSON.stringify({
          text,
          role_id: currentRoleId.value || undefined,
          model: runtimeSettings.provider === 'system' && runtimeSettings.selectedModel === '系统默认'
            ? undefined
            : runtimeSettings.selectedModel,
          base_url: runtimeSettings.provider === 'system' ? undefined : runtimeSettings.baseUrl,
          api_key: runtimeSettings.provider === 'system' ? undefined : runtimeSettings.apiKey,
          thinking_mode: runtimeSettings.thinkingMode,
          reasoning_effort: modelRequestSettings.reasoningEffort,
          tool_mode: 'auto',
          approval_mode: approvalMode.value,
          context_id: contextId.value || undefined,
          context: compacted,
          workspace_mode: contextId.value ? conversationWorkspaceMode.value || workspaceMode : workspaceMode
        })
      })

      if (!isCurrent()) {
        await resp.body?.cancel().catch(() => {})
        return
      }
      const streamContextId = resp.headers.get('X-Chat-Context-Id')
      if (streamContextId) contextId.value = streamContextId
      if (!resp.ok) {
        failStream(resp.status === 401 ? '本机服务认证失败，请检查运行配置'
          : `回复请求失败（HTTP ${resp.status}），请重试`)
        return
      }

      const reader = resp.body?.getReader()
      if (!reader) {
        failStream('流式读取失败，请重试')
        return
      }
      const decoder = new TextDecoder()
      let buffer = ''
      const consumeFrame = (frame: string) => {
        const event = parseChatStreamFrame(frame)
        if (event) applyStreamEvent(event)
      }

      while (true) {
        const { done, value } = await reader.read()
        if (!isCurrent()) {
          await reader.cancel().catch(() => {})
          return
        }
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const frames = buffer.split(/\r?\n\r?\n/)
        buffer = frames.pop() || ''
        for (const frame of frames) consumeFrame(frame)
      }
      buffer += decoder.decode()
      if (buffer.trim()) consumeFrame(buffer)
      if (terminal === 'done') {
        if (!streamMsg.content) {
          failStream('AI 返回了空响应，请重试')
        } else {
          finishThinking('complete')
        }
        emitHistoryRefresh()
      } else if (!terminal) {
        failStream('流式响应意外结束，请重试')
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') {
        failStream('已停止生成', 'cancelled')
      } else {
        failStream('流式请求失败: ' + (e as Error).message)
      }
    } finally {
      const message = ownedMessage()
      if (message) message.streamActivity = 'complete'
      if (message?.thinkingState === 'thinking') {
        finishThinking(terminal === 'done' ? 'complete' : 'error')
      }
      if (isCurrent()) {
        if (activeStreamController === streamController) activeStreamController = null
        activeRequestId = null
        isStreaming.value = false
        loading.value = false
      }
    }
  }

  const cancelMessageStream = async () => {
    const requestId = activeRequestId
    const controller = activeStreamController
    if (requestId) {
      try {
        await chatApi.cancelExecution(requestId)
      } catch {
        // The abort below still closes the UI stream if the control request races shutdown.
      }
    }
    controller?.abort()
  }

  interface ConversationWorkflowOptions {
    domain?: string
    intent?: string
    workflowId?: string
    reviewMode?: string
    title?: string
    conversationId: string
    clientRequestId?: string
    enabledPluginIds?: string[] | null
    execution?: ConversationLaunchContext['execution']
    policyProfile?: ConversationLaunchContext['policyProfile']
  }

  const pendingConversationStarts = new Map<string, Promise<ChatWorkflowStartResult | undefined>>()
  const pendingMissionLaunch = (conversationId: string) => createMissionLaunchAttempt({ slot: `conversation:${conversationId}` }).pending()
  const startConversationWorkflow = async (
    text: string, options: ConversationWorkflowOptions, source: 'agent' | 'chat'
  ): Promise<ChatWorkflowStartResult | undefined> => {
    if (!text.trim()) return undefined
    const attempt = createMissionLaunchAttempt({ slot: `conversation:${options.conversationId}` })
    let identity = attempt.pending()
    if (identity) {
      if ((options.clientRequestId && options.clientRequestId !== identity.operationId)
        || !matchesConversationLaunchContext(identity.commandSnapshot, { ...options, goal: text, source })) {
        throw new MissionLaunchStateError('BUSY', '会话已有另一个待确认提交，请先恢复原操作。')
      }
    } else {
      const command = conversationLaunchCommand({
        ...options, goal: text, source, chatContextId: contextId.value, chatRoleId: currentRoleId.value,
        messages: [...messages.value, { role: 'user', content: text }]
      })
      identity = attempt.begin(command, options.clientRequestId)
    }
    const operationId = identity.operationId
    const pending = pendingConversationStarts.get(operationId)
    if (pending) return pending
    const conversationOwner = historyGeneration
    const operation = Promise.resolve().then(async () => {
      const userMessage = conversationOwner === historyGeneration
        ? messages.value.find(message => message.role === 'user' && message.workflowClientRequestId === operationId) || pushUserMessage(text)
        : { id: Date.now(), role: 'user' as const, content: text, workflowClientRequestId: operationId }
      userMessage.workflowClientRequestId = operationId
      const launch = await attempt.resume(operationId)
      const response = launch.run
      const binding: ChatWorkflowBinding = {
        conversationId: options.conversationId, messageId: String(userMessage.id), missionId: response.missionId,
        acgTaskId: response.runId, runId: response.runId, workflowId: response.workflowId || options.workflowId,
        source, clientRequestId: launch.clientRequestId, createdAt: new Date().toISOString(), status: response.status
      }
      addWorkflowBinding(binding)
      if (conversationOwner === historyGeneration
        && !messages.value.some(message => message.workflowRunId === binding.runId && message.workflowClientRequestId === operationId)) {
        messages.value.push({
          id: Date.now() + 1, role: 'assistant', content: '已创建 ACG 运行任务', createdAt: new Date(),
          modelInfo: 'AgentOS Workflow', agentMode: 'default', acgTaskId: binding.acgTaskId,
          workflowMissionId: binding.missionId, workflowRunId: binding.runId, workflowId: binding.workflowId,
          workflowStatus: binding.status, workflowClientRequestId: operationId
        })
      }
      emitHistoryRefresh()
      attempt.complete(operationId)
      return { response, binding, launch }
    }).finally(() => pendingConversationStarts.delete(operationId))
    pendingConversationStarts.set(operationId, operation)
    return operation
  }

  const upgradeToWorkflow = (
    text: string,
    options: ConversationWorkflowOptions
  ) => startConversationWorkflow(text, options, 'chat')

  const startAgentRun = (
    text: string,
    options: ConversationWorkflowOptions
  ) => startConversationWorkflow(text, options, 'agent')

  const resumeMissionLaunch = (conversationId: string) => {
    const identity = pendingMissionLaunch(conversationId)
    if (!identity) throw new MissionLaunchStateError('RECONCILIATION_REQUIRED', '没有可恢复的会话提交。')
    return startConversationWorkflow(identity.commandSnapshot.semantics!.objective,
      { conversationId, clientRequestId: identity.operationId }, identity.commandSnapshot.input?.source === 'agent' ? 'agent' : 'chat')
  }

  const clearHistory = async () => {
    const generation = ++historyGeneration
    const targetContextId = contextId.value
    invalidateMessageRequest()
    const owner = messageGeneration
    if (targetContextId) await chatApi.clearHistory(targetContextId)
    if (targetContextId) contextCheckpoints.delete(targetContextId)
    if (generation === historyGeneration && owner === messageGeneration && contextId.value === targetContextId) clearMessages()
  }

  const setRole = (roleId: string | null) => {
    currentRoleId.value = roleId
  }

  const loadHistory = async (targetContextId: string) => {
    if (!targetContextId || targetContextId.startsWith('draft:')) return
    invalidateMessageRequest()
    const generation = ++historyGeneration
    loading.value = true
    isLoadingConversation.value = true
    contextId.value = targetContextId
    messages.value = []
    currentRoleId.value = null
    historyError.value = null
    conversationWorkspaceMode.value = getConversationWorkspace(targetContextId,
      new Set(conversationBindings(workflowBindings.value, targetContextId).filter(item => item.source === 'agent').map(() => targetContextId)))

    try {
      const [history, metadata] = await Promise.all([
        chatApi.getHistory(targetContextId),
        conversationApi.getConversation(targetContextId).catch(() => null)
      ])
      if (generation !== historyGeneration || contextId.value !== targetContextId) return
      if (metadata?.contextId === targetContextId) {
        currentRoleId.value = metadata.roleId || null
        if (metadata.workspaceMode === 'agent' || metadata.workspaceMode === 'chat') {
          conversationWorkspaceMode.value = metadata.workspaceMode
          setConversationWorkspace(targetContextId, metadata.workspaceMode)
        }
      } else {
        historyError.value = '会话元数据未能恢复，请重试后继续发送'
      }

      messages.value = history.map((msg: any) => ({
        id: msg.id || Date.now() + Math.random(),
        role: msg.role?.toLowerCase() === 'user' ? 'user' : 'assistant',
        content: msg.content || '',
        createdAt: msg.createdAt ? new Date(msg.createdAt) : new Date(),
        fileUrl: msg.fileUrl,
        confidence: msg.metadata?.confidence,
        tokensUsed: msg.metadata?.totalTokens ?? msg.metadata?.tokens_used,
        modelInfo: msg.metadata?.effectiveModel ?? msg.metadata?.model_info,
        requestedThinkingMode: msg.metadata?.requestedThinkingMode,
        effectiveThinkingMode: msg.metadata?.effectiveThinkingMode,
        effectiveReasoningEffort: msg.metadata?.effectiveReasoningEffort,
        thinkingDurationMs: msg.metadata?.reasoningPhaseMs,
        reasoningContent: msg.metadata?.reasoningContent,
        reasoningTruncated: msg.metadata?.reasoningTruncated,
        inputTokens: msg.metadata?.inputTokens,
        reasoningTokens: msg.metadata?.reasoningTokens,
        outputTokens: msg.metadata?.outputTokens,
        latencyMs: msg.metadata?.latencyMs,
        executionSummary: msg.metadata?.executionSummary,
        streamError: msg.metadata?.executionSummary?.find((stage: ExecutionSummaryItem) =>
          stage.stage === 'chat_stream' && stage.status !== 'completed')?.description,
        streamActivity: msg.role?.toLowerCase() === 'user' ? undefined : 'complete',
        thinkingState: msg.metadata?.executionSummary?.some((stage: ExecutionSummaryItem) =>
          stage.stage === 'chat_stream' && stage.status !== 'completed') ? 'error'
          : msg.metadata?.thinkingEnabled ? 'complete' : undefined,
        agentMode: 'default'
      }))

      contextId.value = targetContextId

      const lastWithUsage = [...messages.value]
        .reverse()
        .find(msg => msg.role === 'assistant' && (
          typeof msg.inputTokens === 'number' ||
          typeof msg.outputTokens === 'number' ||
          typeof msg.tokensUsed === 'number'
        ))
      if (lastWithUsage) {
        const used = typeof lastWithUsage.inputTokens === 'number'
          ? lastWithUsage.inputTokens + (typeof lastWithUsage.outputTokens === 'number' ? lastWithUsage.outputTokens : 0)
          : (lastWithUsage.tokensUsed ?? null)
        applyContextUsage(used, lastWithUsage.modelInfo || null)
      } else {
        contextUsedTokens.value = null
      }
    } catch (error: any) {
      if (generation !== historyGeneration || contextId.value !== targetContextId) return
      console.error('加载对话历史失败:', error)
      messages.value = []
      historyError.value = '加载对话历史失败'
    } finally {
      if (generation === historyGeneration && contextId.value === targetContextId) {
        isLoadingConversation.value = false
        loading.value = false
      }
    }
  }

  const setContextId = (id: string | null) => {
    if (id) {
      return loadHistory(id)
    } else {
      invalidateMessageRequest()
      ++historyGeneration
      contextId.value = null
      conversationWorkspaceMode.value = null
      historyError.value = null
      isLoadingConversation.value = false
      loading.value = false
      messages.value = []
      contextUsedTokens.value = null
      contextWindowTokens.value = null
    }
  }

  const addMessage = (message: Message) => {
    const completeMessage: Message = {
      ...message,
      id: message.id || Date.now().toString(),
      role: message.role || 'user',
      content: message.content || '',
      createdAt: message.createdAt || (message.timestamp ? new Date(message.timestamp) : new Date()),
      timestamp: message.timestamp || (message.createdAt ? message.createdAt.getTime() : Date.now())
    }
    messages.value.push(completeMessage)
  }

  const setMessages = (newMessages: Message[]) => {
    invalidateMessageRequest()
    messages.value = newMessages.map(msg => ({
      ...msg,
      createdAt: msg.createdAt || (msg.timestamp ? new Date(msg.timestamp) : new Date())
    }))
  }

  const clearMessages = () => {
    invalidateMessageRequest()
    ++historyGeneration
    conversationWorkspaceMode.value = null
    historyError.value = null
    isLoadingConversation.value = false
    messages.value = []
    contextId.value = null
    contextUsedTokens.value = null
    contextWindowTokens.value = null
  }

  return {
    isCompacting,
    compactionNotice,
    compactContext,
    approvalMode,
    messages,
    loading,
    isStreaming,
    isLoadingConversation,
    workflowBindings,
    contextId,
    currentRoleId,
    conversationWorkspaceMode,
    historyError,
    migrateDraftBindings,
    contextUsedTokens,
    contextWindowTokens,
    contextModel,
    contextModels,
    fetchContextWindows,
    sendMessage,
    sendMessageStream,
    cancelMessageStream,
    upgradeToWorkflow,
    startAgentRun,
    pendingMissionLaunch,
    resumeMissionLaunch,
    addWorkflowBinding,
    getLatestWorkflowBinding,
    getActiveWorkflowBinding,
    updateWorkflowBindingStatus,
    markWorkflowBindingInvalid,
    clearHistory,
    setRole,
    loadHistory,
    setContextId,
    addMessage,
    setMessages,
    clearMessages
  }
})

