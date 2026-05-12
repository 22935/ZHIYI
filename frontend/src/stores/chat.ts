import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi, type ChatRequest } from '@/services/api/chat'
import {
  agentLawyerApi,
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
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const loading = ref(false)
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
  }

  const emitHistoryRefresh = () => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('history-refresh'))
    }
  }

  const sendMessage = async (text: string, fileUrl?: string) => {
    if ((!text.trim() && !fileUrl) || loading.value) return

    pushUserMessage(text, fileUrl)

    loading.value = true
    try {
      const request: ChatRequest = {
        text: text || '',
        roleId: currentRoleId.value || undefined,
        contextId: contextId.value || undefined,
        fileUrl: fileUrl || undefined
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
        modelInfo: 'Lawyer Agent',
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
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
  const sendLawyerMessageStream = async (text: string) => {
    if (!text.trim() || loading.value) return

    pushUserMessage(text)
    loading.value = true

    const streamMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
      modelInfo: 'Lawyer Agent (streaming)',
      agentMode: 'lawyer'
    }
    messages.value.push(streamMsg)
    const streamIndex = messages.value.length - 1
    const setStreamContent = (content: string) => {
      const message = messages.value[streamIndex]
      if (message) message.content = content
    }
    const appendStreamContent = (delta: string) => {
      const message = messages.value[streamIndex]
      if (message) message.content = (message.content || '') + delta
    }

    const token = localStorage.getItem('token')
    try {
      const resp = await fetch('/ai/chat/text/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({ text, role_id: currentRoleId.value || undefined })
      })

      const reader = resp.body?.getReader()
      if (!reader) { setStreamContent('流式读取失败'); return }
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') continue
            try {
              const parsed = JSON.parse(data)
              if (parsed.delta) {
                appendStreamContent(parsed.delta)
              }
            } catch { /* skip parse errors */ }
          }
        }
      }
      emitHistoryRefresh()
    } catch (e) {
      setStreamContent('流式请求失败: ' + (e as Error).message)
    } finally {
      loading.value = false
    }
  }

  const sendMessageStream = async (text: string) => {
    if ((!text.trim()) || loading.value) return

    pushUserMessage(text)
    loading.value = true

    const streamMsg: Message = {
      id: Date.now() + 1,
      role: 'assistant',
      content: '',
      createdAt: new Date(),
      modelInfo: 'AI (streaming)',
      agentMode: 'default'
    }
    messages.value.push(streamMsg)
    const streamIndex = messages.value.length - 1
    const setStreamContent = (content: string) => {
      const message = messages.value[streamIndex]
      if (message) message.content = content
    }
    const appendStreamContent = (delta: string) => {
      const message = messages.value[streamIndex]
      if (message) message.content = (message.content || '') + delta
    }

    const token = localStorage.getItem('token')
    try {
      const resp = await fetch('/ai/chat/text/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        },
        body: JSON.stringify({ text, role_id: currentRoleId.value || undefined })
      })

      const reader = resp.body?.getReader()
      if (!reader) { setStreamContent('流式读取失败'); return }
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const data = line.slice(6)
            if (data === '[DONE]') continue
            try {
              const parsed = JSON.parse(data)
              if (parsed.delta) {
                appendStreamContent(parsed.delta)
              }
            } catch { /* skip parse errors */ }
          }
        }
      }
      emitHistoryRefresh()
    } catch (e) {
      setStreamContent('流式请求失败: ' + (e as Error).message)
    } finally {
      loading.value = false
    }
  }

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
        modelInfo: 'Teacher Agent',
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
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
        modelInfo: 'Programmer Agent',
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
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
        modelInfo: 'Writer Agent',
        skillsUsed: response.skillsUsed || [],
        trace: response.trace || [],
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
    try {
      const history = await chatApi.getHistory(targetContextId)

      messages.value = history.map((msg: any) => ({
        id: msg.id || Date.now() + Math.random(),
        role: msg.role?.toLowerCase() === 'user' ? 'user' : 'assistant',
        content: msg.content || '',
        createdAt: msg.createdAt ? new Date(msg.createdAt) : new Date(),
        fileUrl: msg.fileUrl,
        agentMode: 'default'
      }))

      contextId.value = targetContextId
    } catch (error: any) {
      console.error('加载对话历史失败:', error)
      messages.value = []
    } finally {
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
    sendTeacherMessage,
    sendProgrammerMessage,
    sendWriterMessage,
    clearHistory,
    setRole,
    loadHistory,
    setContextId,
    addMessage,
    setMessages,
    clearMessages
  }
})

