import { defineStore } from 'pinia'
import { ref } from 'vue'
import { chatApi, type ChatRequest } from '@/services/api/chat'
import {
  agentLawyerApi,
  type AgentTraceStep,
  type FederatedInfo
} from '@/services/api/agentLawyer'

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

const parseTraceObservation = (trace: AgentTraceStep[] | undefined, action: string) => {
  if (!trace?.length) return undefined
  const target = [...trace].reverse().find(item => item.action === action)
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
  agentMode?: 'default' | 'lawyer'
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref<Message[]>([])
  const loading = ref(false)
  const contextId = ref<string | null>(null)
  const lawyerSessionId = ref<string | null>(null)
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
  }

  return {
    messages,
    loading,
    contextId,
    lawyerSessionId,
    currentRoleId,
    sendMessage,
    sendLawyerMessage,
    clearHistory,
    setRole,
    loadHistory,
    setContextId,
    addMessage,
    setMessages,
    clearMessages
  }
})
