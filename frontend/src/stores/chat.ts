import { defineStore } from 'pinia'
import { ref } from 'vue'
import { parseChatStreamData, parseSseDataLine, type ChatStreamEvent } from '@/utils/sse'
import { workflowApi, type AsyncWorkflowStartResponse } from '@/services/api/workflow'
import { chatApi, type ChatRequest } from '@/services/api/chat'
import { loadModelSettings, toModelRequestSettings, type ModelSettings } from '@/config/modelSettings'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import {
  agentLawyerApi,
  type AgentRoutingInfo,
  type AgentTraceStep,
  type FederatedInfo
} from '@/services/api/agentLawyer'
import {
  agentTeacherApi,
  type StudentDiagnosisResult,
  type LessonPlanResult,
  type HomeworkGradingResult,
  type ErrorQuestionPushResult
} from '@/services/api/agentTeacher'
import {
  agentProgrammerApi,
  type RequirementAnalysisResult,
  type CodebaseSemanticSearchResult,
  type CodeGenerationResult,
  type DiagramGenerationResult
} from '@/services/api/agentProgrammer'
import {
  agentWriterApi,
  type InspirationExpandResult,
  type OutlineGenerateResult,
  type ContentWriteResult,
  type CharacterRelationResult
} from '@/services/api/agentWriter'

export interface EvidenceAnalysisResult {
  evidence_items: Array<{ name: string; type: string; strength: string; notes: string }>
  missing_evidence: string[]
  overall_assessment: string
  legal_basis: string[]
}

export interface LimitationCalcResult {
  limitation_period?: string
  start_date?: string
  deadline?: string
  expiry_date?: string
  is_expired?: boolean
  days_remaining?: number
  interruption_events?: string[]
  interruption_hints?: string[]
  legal_basis?: string[] | string
  status?: string
  suggestion?: string
  limitation_years?: number
}

export interface JurisdictionResult {
  courts?: Array<{ name: string; basis: string }>
  recommended_courts?: Array<{ court: string; reason: string; priority?: string }>
  recommendation?: string
  legal_basis?: string[] | string
}

export interface HearingOutlineResult {
  outline_markdown?: string
  outline?: string
  agenda?: string[]
  question_points?: string[]
  risk_focus?: string[]
}

const parseTraceObservation = (
  trace: AgentTraceStep[] | undefined,
  action: string | string[]
) => {
  if (!trace?.length) return undefined
  const actionList = Array.isArray(action) ? action : [action]
  const target = [...trace].reverse().find(item => actionList.includes(item.action))
  if (!target?.observation) return undefined
  try {
    const parsed = JSON.parse(target.observation)
    return parsed && typeof parsed === 'object' ? parsed : undefined
  } catch {
    return undefined
  }
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
  thinkingDurationMs?: number
  reasoningContent?: string
  requestedThinkingMode?: string
  effectiveThinkingMode?: string
  effectiveReasoningEffort?: string
  inputTokens?: number
  reasoningTokens?: number
  outputTokens?: number
  latencyMs?: number
  executionSummary?: Array<{ stage: string; status: string; description: string; durationMs?: number }>
  skillsUsed?: string[]
  trace?: AgentTraceStep[]
  federated?: FederatedInfo
  riskLevel?: string
  evidenceAnalysis?: EvidenceAnalysisResult
  limitationCalc?: LimitationCalcResult
  jurisdiction?: JurisdictionResult
  hearingOutline?: HearingOutlineResult
  studentDiagnosis?: StudentDiagnosisResult
  lessonPlan?: LessonPlanResult
  homeworkGrading?: HomeworkGradingResult
  errorQuestionPush?: ErrorQuestionPushResult
  requirementAnalysis?: RequirementAnalysisResult
  codebaseSemanticSearch?: CodebaseSemanticSearchResult
  codeGeneration?: CodeGenerationResult
  diagramGeneration?: DiagramGenerationResult
  inspirationExpand?: InspirationExpandResult
  outlineGenerate?: OutlineGenerateResult
  contentWrite?: ContentWriteResult
  characterRelationMap?: CharacterRelationResult
  agentMode?: 'default' | 'lawyer' | 'teacher' | 'programmer' | 'writer'
  routing?: AgentRoutingInfo
  acgTaskId?: string
  workflowRunId?: string
  workflowTaskId?: string
  workflowId?: string
  workflowStatus?: string
  workflowClientRequestId?: string
  runtimeEngine?: string
  implementationId?: string
}

export interface ChatWorkflowBinding {
  conversationId: string
  messageId?: string
  taskId: string
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
}

type AgentMode = NonNullable<Message['agentMode']>

export const useChatStore = defineStore('chat', () => {
  const WORKFLOW_BINDINGS_KEY = 'chat.workflow_bindings.v1'
  const TERMINAL_WORKFLOW_STATUSES = new Set(['completed', 'failed', 'cancelled'])
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
  const workflowBindings = ref<Record<string, ChatWorkflowBinding[]>>(loadWorkflowBindings())
  const workflowRunsStore = useWorkflowRunsStore()
  let activeStreamController: AbortController | null = null
  const contextId = ref<string | null>(null)
  const lawyerSessionId = ref<string | null>(null)
  const teacherSessionId = ref<string | null>(null)
  const programmerSessionId = ref<string | null>(null)
  const writerSessionId = ref<string | null>(null)
  const currentRoleId = ref<string | null>(null)

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
    const existing = workflowBindings.value[binding.conversationId] || []
    workflowBindings.value = {
      ...workflowBindings.value,
      [binding.conversationId]: [...existing.filter(item => item.runId !== binding.runId), binding]
    }
    persistWorkflowBindings()
    workflowRunsStore.registerChatBinding(binding)
  }

  const getLatestWorkflowBinding = (conversationId: string) => {
    const bindings = workflowBindings.value[conversationId] || []
    return [...bindings].reverse().find(binding => !binding.invalidAt)
  }

  const getActiveWorkflowBinding = (conversationId: string) => {
    const bindings = workflowBindings.value[conversationId] || []
    return [...bindings].reverse().find(binding =>
      !binding.invalidAt && !TERMINAL_WORKFLOW_STATUSES.has(binding.status)
    )
  }

  const updateWorkflowBindingStatus = (conversationId: string, runId: string, status: string) => {
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

  const sendMessage = async (
    text: string,
    fileUrl?: string,
    runtimeSettings?: ModelSettings,
    workspaceMode: 'agent' | 'chat' = 'chat'
  ) => {
    if ((!text.trim() && !fileUrl) || loading.value) return

    pushUserMessage(text, fileUrl)

    loading.value = true
    try {
      const request: ChatRequest = {
        text: text || '',
        roleId: currentRoleId.value || undefined,
        contextId: contextId.value || undefined,
        workspaceMode,
        fileUrl: fileUrl || undefined,
        ...toModelRequestSettings(runtimeSettings || loadModelSettings())
      }

      const response = await chatApi.sendMessage(request)
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
    } finally {
      loading.value = false
    }
  }

  const sendLawyerMessage = async (text: string) => {
    if (!text.trim() || loading.value) return

    pushUserMessage(text)

    loading.value = true
    try {
      const response = await agentLawyerApi.chat({
        text,
        sessionId: lawyerSessionId.value || undefined
      })

      lawyerSessionId.value = response.sessionId || lawyerSessionId.value
      const traceEvidence = parseTraceObservation(response.trace, 'evidence_analysis')
      const traceLimitation = parseTraceObservation(response.trace, 'limitation_calculation')
      const traceJurisdiction = parseTraceObservation(response.trace, 'jurisdiction_determination')
      const traceHearing = parseTraceObservation(response.trace, 'hearing_outline_generation')

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.answer || '',
        createdAt: new Date(),
        modelInfo: (response.acgTaskId || response.workflowRunId) ? 'AgentOS Workflow' : undefined,
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
        routing: response.routing,
        acgTaskId: response.acgTaskId || response.workflowRunId,
        workflowRunId: response.acgTaskId || response.workflowRunId,
        workflowId: response.workflowId,
        workflowStatus: response.workflowStatus,
        runtimeEngine: response.runtimeEngine,
        implementationId: response.implementationId,
        federated: response.federated || {},
        riskLevel: response.riskLevel,
        evidenceAnalysis: response.evidenceAnalysis || response.evidence_analysis || traceEvidence,
        limitationCalc: response.limitationCalc || response.limitation_calculation || traceLimitation,
        jurisdiction: response.jurisdiction || response.jurisdiction_determination || traceJurisdiction,
        hearingOutline: response.hearingOutline || response.hearing_outline_generation || traceHearing,
        agentMode: 'lawyer'
      }
      messages.value.push(assistantMessage)
      emitHistoryRefresh()

      return response
    } finally {
      loading.value = false
    }
  }

  // ---- 流式发送（SSE）----
  const streamModelInfo: Record<AgentMode, string> = {
    default: 'AI (streaming)',
    lawyer: 'Lawyer Agent (streaming)',
    teacher: 'Teacher Agent (streaming)',
    programmer: 'Programmer Agent (streaming)',
    writer: 'Writer Agent (streaming)'
  }

  const sendMessageStream = async (
    text: string,
    agentMode: AgentMode = 'default',
    runtimeSettings: ModelSettings = loadModelSettings(),
    workspaceMode: 'agent' | 'chat' = 'chat'
  ) => {
    if ((!text.trim()) || loading.value) return

    pushUserMessage(text)
    loading.value = true
    isStreaming.value = true

    const streamMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
      modelInfo: runtimeSettings.provider === 'system'
        ? streamModelInfo[agentMode]
        : runtimeSettings.selectedModel,
      thinkingState: runtimeSettings.thinkingMode === 'disabled' ? undefined : 'thinking',
      requestedThinkingMode: runtimeSettings.thinkingMode,
      reasoningContent: '',
      agentMode
    }
    messages.value.push(streamMsg)
    const streamIndex = messages.value.length - 1
    const thinkingStartedAt = Date.now()
    const finishThinking = (state: 'complete' | 'error', durationMs?: number) => {
      const message = messages.value[streamIndex]
      if (!message) return
      if (!message.thinkingState && message.requestedThinkingMode === 'disabled') return
      message.thinkingState = state
      message.thinkingDurationMs = Math.max(0, durationMs ?? (Date.now() - thinkingStartedAt))
    }
    const setStreamContent = (content: string) => {
      const message = messages.value[streamIndex]
      if (message) message.content = content
    }
    const appendStreamContent = (delta: string) => {
      const message = messages.value[streamIndex]
      if (message) {
        finishThinking('complete')
        message.content = (message.content || '') + delta
      }
    }
    const appendReasoningContent = (delta: string) => {
      const message = messages.value[streamIndex]
      if (message) message.reasoningContent = (message.reasoningContent || '') + delta
    }
    const applyStreamEvent = (event: ChatStreamEvent) => {
      const message = messages.value[streamIndex]
      if (!message) return
      const data = event.data || {}
      const upsertToolSummary = (status: string) => {
        const toolName = String(data.toolName || 'unknown')
        const callId = String(data.callId || toolName)
        const stage = `tool:${toolName}:${callId}`
        const duration = typeof data.durationMs === 'number' ? data.durationMs : undefined
        const description = status === 'completed'
          ? `${toolName} 调用完成${duration === undefined ? '' : `（${duration}ms）`}`
          : status === 'failed'
            ? `${toolName} 调用失败：${data.errorCode || 'TOOL_FAILED'}`
            : `${toolName} 调用中`
        const summaries = message.executionSummary || []
        const index = summaries.findIndex(item => item.stage === stage)
        const next = { stage, status, description, durationMs: duration }
        if (index >= 0) summaries[index] = next
        else summaries.push(next)
        message.executionSummary = [...summaries]
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
        case 'reasoning_start':
          message.thinkingState = 'thinking'
          message.requestedThinkingMode = data.requestedThinkingMode || message.requestedThinkingMode
          message.effectiveThinkingMode = data.effectiveThinkingMode
          message.effectiveReasoningEffort = data.effectiveReasoningEffort
          break
        case 'reasoning_delta':
          if (typeof data.delta === 'string') appendReasoningContent(data.delta)
          break
        case 'reasoning_end':
          finishThinking('complete', typeof data.reasoningPhaseMs === 'number' ? data.reasoningPhaseMs : undefined)
          break
        case 'content_delta':
          if (typeof data.delta === 'string') appendStreamContent(data.delta)
          break
        case 'tool_start':
          upsertToolSummary('running')
          break
        case 'tool_result':
          upsertToolSummary('completed')
          mergeSources(data.sources)
          break
        case 'tool_error':
          upsertToolSummary('failed')
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
          break
        case 'done':
          if (typeof data.contextId === 'string' && data.contextId) contextId.value = data.contextId
          mergeSources(data.sources)
          finishThinking(message.content ? 'complete' : 'error')
          break
        case 'error':
          finishThinking('error')
          if (!message.content) message.content = `Stream request failed: ${data.code || 'AI_STREAM_FAILED'}`
          break
      }
    }

    const token = localStorage.getItem('token')
    const streamController = new AbortController()
    activeStreamController = streamController
    try {
      const resp = await fetch('/ai/chat/text/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
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
          tool_mode: 'auto',
          context_id: contextId.value || undefined,
          workspace_mode: workspaceMode
        })
      })

      if (!resp.ok) {
        finishThinking('error')
        setStreamContent(`Stream request failed: HTTP ${resp.status}`)
        return
      }

      const reader = resp.body?.getReader()
      if (!reader) {
        finishThinking('error')
        setStreamContent('流式读取失败')
        return
      }
      const decoder = new TextDecoder()
      let buffer = ''
      let streamComplete = false

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          const data = parseSseDataLine(line)
          if (data !== null) {
            const event = parseChatStreamData(data)
            if (!event) continue
            applyStreamEvent(event)
            if (event.event === 'done') {
              streamComplete = true
            }
          }
        }
      }
      if (streamComplete) {
        if (!streamMsg.content) {
          finishThinking('error')
          setStreamContent('AI 返回了空响应，请重试')
        } else {
          finishThinking('complete')
        }
        emitHistoryRefresh()
      } else if (!streamMsg.content) {
        finishThinking('error')
        setStreamContent('流式响应意外结束，请重试')
      }
    } catch (e) {
      finishThinking('error')
      if ((e as Error).name === 'AbortError') {
        if (!streamMsg.content) setStreamContent('已停止生成')
      } else {
        setStreamContent('流式请求失败: ' + (e as Error).message)
      }
    } finally {
      const message = messages.value[streamIndex]
      if (message?.thinkingState === 'thinking') {
        finishThinking(message.content && !message.content.startsWith('Stream request failed:') ? 'complete' : 'error')
      }
      if (activeStreamController === streamController) activeStreamController = null
      isStreaming.value = false
      loading.value = false
    }
  }

  const cancelMessageStream = () => {
    activeStreamController?.abort()
  }

  const sendLawyerMessageStream = async (text: string) => sendMessageStream(text, 'lawyer')

  const sendTeacherMessage = async (text: string) => {
    if (!text.trim() || loading.value) return

    pushUserMessage(text)

    loading.value = true
    try {
      const response = await agentTeacherApi.chat({
        text,
        sessionId: teacherSessionId.value || undefined
      })

      teacherSessionId.value = response.sessionId || teacherSessionId.value
      const traceDiagnosis = parseTraceObservation(response.trace, ['student_diagnosis'])
      const traceLessonPlan = parseTraceObservation(response.trace, ['lesson_plan_generation', 'lesson_plan'])
      const traceGrading = parseTraceObservation(response.trace, ['homework_grading', 'grading'])
      const tracePush = parseTraceObservation(response.trace, ['error_analysis_question_push', 'error_attribution'])

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.answer || '',
        createdAt: new Date(),
        modelInfo: (response.acgTaskId || response.workflowRunId) ? 'AgentOS Workflow' : undefined,
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
        routing: response.routing,
        acgTaskId: response.acgTaskId || response.workflowRunId,
        workflowRunId: response.acgTaskId || response.workflowRunId,
        workflowId: response.workflowId,
        workflowStatus: response.workflowStatus,
        runtimeEngine: response.runtimeEngine,
        implementationId: response.implementationId,
        federated: response.federated || {},
        riskLevel: response.riskLevel,
        studentDiagnosis: response.studentDiagnosis || response.student_diagnosis || traceDiagnosis,
        lessonPlan: response.lessonPlan || response.lesson_plan_generation || traceLessonPlan,
        homeworkGrading: response.homeworkGrading || response.homework_grading || traceGrading,
        errorQuestionPush: response.errorQuestionPush || response.error_analysis_question_push || tracePush,
        agentMode: 'teacher'
      }
      messages.value.push(assistantMessage)
      emitHistoryRefresh()

      return response
    } finally {
      loading.value = false
    }
  }

  const sendProgrammerMessage = async (text: string) => {
    if (!text.trim() || loading.value) return

    pushUserMessage(text)

    loading.value = true
    try {
      const response = await agentProgrammerApi.chat({
        text,
        sessionId: programmerSessionId.value || undefined
      })

      programmerSessionId.value = response.sessionId || programmerSessionId.value
      const traceRequirement = parseTraceObservation(response.trace, 'requirement_analysis')
      const traceSearch = parseTraceObservation(response.trace, 'codebase_semantic_search')
      const traceCodeGeneration = parseTraceObservation(response.trace, 'code_generation')
      const traceDiagram = parseTraceObservation(response.trace, 'diagram_generation')

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.answer || '',
        createdAt: new Date(),
        modelInfo: (response.acgTaskId || response.workflowRunId) ? 'AgentOS Workflow' : undefined,
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
        routing: response.routing,
        acgTaskId: response.acgTaskId || response.workflowRunId,
        workflowRunId: response.acgTaskId || response.workflowRunId,
        workflowId: response.workflowId,
        workflowStatus: response.workflowStatus,
        runtimeEngine: response.runtimeEngine,
        implementationId: response.implementationId,
        federated: response.federated || {},
        riskLevel: response.riskLevel,
        requirementAnalysis: response.requirementAnalysis || response.requirement_analysis || traceRequirement,
        codebaseSemanticSearch: response.codebaseSemanticSearch || response.codebase_semantic_search || traceSearch,
        codeGeneration: response.codeGeneration || response.code_generation || traceCodeGeneration,
        diagramGeneration: response.diagramGeneration || response.diagram_generation || traceDiagram,
        agentMode: 'programmer'
      }
      messages.value.push(assistantMessage)
      emitHistoryRefresh()

      return response
    } finally {
      loading.value = false
    }
  }

  const sendWriterMessage = async (text: string) => {
    if (!text.trim() || loading.value) return

    pushUserMessage(text)

    loading.value = true
    try {
      const response = await agentWriterApi.chat({
        text,
        sessionId: writerSessionId.value || undefined
      })

      writerSessionId.value = response.sessionId || writerSessionId.value
      const traceInspiration = parseTraceObservation(response.trace, 'inspiration_expand')
      const traceOutline = parseTraceObservation(response.trace, 'outline_generate')
      const traceContent = parseTraceObservation(response.trace, 'content_write')
      const traceRelation = parseTraceObservation(response.trace, 'character_relation_map')

      const assistantMessage: Message = {
        id: Date.now() + 1,
        role: 'assistant',
        content: response.answer || '',
        createdAt: new Date(),
        modelInfo: (response.acgTaskId || response.workflowRunId) ? 'AgentOS Workflow' : undefined,
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
        routing: response.routing,
        acgTaskId: response.acgTaskId || response.workflowRunId,
        workflowRunId: response.acgTaskId || response.workflowRunId,
        workflowId: response.workflowId,
        workflowStatus: response.workflowStatus,
        runtimeEngine: response.runtimeEngine,
        implementationId: response.implementationId,
        federated: response.federated || {},
        riskLevel: response.riskLevel,
        inspirationExpand: response.inspirationExpand || response.inspiration_expand || traceInspiration,
        outlineGenerate: response.outlineGenerate || response.outline_generate || traceOutline,
        contentWrite: response.contentWrite || response.content_write || traceContent,
        characterRelationMap: response.characterRelationMap || response.character_relation_map || traceRelation,
        agentMode: 'writer'
      }
      messages.value.push(assistantMessage)
      emitHistoryRefresh()

      return response
    } finally {
      loading.value = false
    }
  }

  interface ConversationWorkflowOptions {
    domain?: string
    intent?: string
    workflowId?: string
    reviewMode?: string
    title?: string
    conversationId: string
    clientRequestId: string
    enabledPluginIds?: string[]
  }

  const startConversationWorkflow = async (
    text: string,
    options: ConversationWorkflowOptions,
    source: 'agent' | 'chat'
  ): Promise<ChatWorkflowStartResult | undefined> => {
    if (!text.trim()) return undefined

    const userMessage = messages.value.find(message =>
      message.role === 'user' && message.workflowClientRequestId === options.clientRequestId
    ) || pushUserMessage(text)
    userMessage.workflowClientRequestId = options.clientRequestId

    const context = messages.value
      .slice(-8)
      .filter(message => message.content)
      .map(message => ({ role: message.role, content: message.content }))

    const response = await workflowApi.startWorkflowAsync({
      title: options.title || `${source === 'agent' ? 'Agent' : 'Chat'} ACG：${text.slice(0, 40)}`,
      domain: options.domain || 'legal',
      intent: options.intent || 'case_analysis',
      workflowId: options.workflowId,
      reviewMode: options.reviewMode || 'human_in_loop',
      clientRequestId: options.clientRequestId,
      enabledPluginIds: options.enabledPluginIds,
      input: {
        source,
        ...(source === 'agent'
          ? { userIntent: text, taskGoal: text }
          : { caseText: text, chatText: text }),
        chatContextId: contextId.value,
        chatRoleId: currentRoleId.value,
        chatContext: context
      }
    })

    const acgTaskId = response.acgTaskId || response.run.runId
    const binding: ChatWorkflowBinding = {
      conversationId: options.conversationId,
      messageId: String(userMessage.id),
      taskId: response.task.taskId,
      acgTaskId,
      runId: acgTaskId,
      workflowId: response.run.workflowId || options.workflowId,
      source,
      clientRequestId: options.clientRequestId,
      createdAt: new Date().toISOString(),
      status: response.run.status
    }
    addWorkflowBinding(binding)

    messages.value.push({
      id: Date.now() + 1,
      role: 'assistant',
      content: '已创建 ACG 运行任务',
      createdAt: new Date(),
      modelInfo: 'AgentOS Workflow',
      agentMode: 'default',
      acgTaskId: binding.acgTaskId,
      workflowTaskId: binding.taskId,
      workflowRunId: binding.runId,
      workflowId: binding.workflowId,
      workflowStatus: binding.status,
      workflowClientRequestId: binding.clientRequestId
    })
    emitHistoryRefresh()
    return { response, binding }
  }

  const upgradeToWorkflow = (
    text: string,
    options: ConversationWorkflowOptions
  ) => startConversationWorkflow(text, options, 'chat')

  const startAgentRun = (
    text: string,
    options: ConversationWorkflowOptions
  ) => startConversationWorkflow(text, options, 'agent')

  const clearHistory = async () => {
    if (contextId.value) {
      await chatApi.clearHistory(contextId.value)
    }
    messages.value = []
    contextId.value = null
    lawyerSessionId.value = null
    teacherSessionId.value = null
    programmerSessionId.value = null
    writerSessionId.value = null
  }

  const setRole = (roleId: string | null) => {
    currentRoleId.value = roleId
  }

  const loadHistory = async (targetContextId: string) => {
    if (!targetContextId) return

    loading.value = true
    isLoadingConversation.value = true
    try {
      const history = await chatApi.getHistory(targetContextId)

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
        inputTokens: msg.metadata?.inputTokens,
        reasoningTokens: msg.metadata?.reasoningTokens,
        outputTokens: msg.metadata?.outputTokens,
        latencyMs: msg.metadata?.latencyMs,
        executionSummary: msg.metadata?.executionSummary,
        thinkingState: msg.metadata?.thinkingEnabled ? 'complete' : undefined,
        agentMode: 'default'
      }))

      contextId.value = targetContextId
    } catch (error: any) {
      console.error('加载对话历史失败:', error)
      messages.value = []
    } finally {
      isLoadingConversation.value = false
      loading.value = false
    }
  }

  const setContextId = (id: string | null) => {
    contextId.value = id
    if (id) {
      loadHistory(id)
    } else {
      messages.value = []
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
    messages.value = newMessages.map(msg => ({
      ...msg,
      createdAt: msg.createdAt || (msg.timestamp ? new Date(msg.timestamp) : new Date())
    }))
  }

  const clearMessages = () => {
    messages.value = []
    contextId.value = null
    lawyerSessionId.value = null
    teacherSessionId.value = null
    programmerSessionId.value = null
    writerSessionId.value = null
  }

  return {
    messages,
    loading,
    isStreaming,
    isLoadingConversation,
    workflowBindings,
    contextId,
    lawyerSessionId,
    teacherSessionId,
    programmerSessionId,
    writerSessionId,
    currentRoleId,
    sendMessage,
    sendLawyerMessage,
    sendLawyerMessageStream,
    sendMessageStream,
    cancelMessageStream,
    sendTeacherMessage,
    sendProgrammerMessage,
    sendWriterMessage,
    upgradeToWorkflow,
    startAgentRun,
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

