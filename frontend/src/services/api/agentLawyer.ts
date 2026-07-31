import request from '@/utils/request'

const LAWYER_AGENT_TIMEOUT_MS = 240000

export interface AgentTraceStep {
  step: number
  thought: string
  action: string
  observation: string
}

export interface FederatedInfo {
  enabled?: boolean
  applied?: boolean
  risk_adjustment?: number
  confidence?: number
  federated_nodes_count?: number
}

export interface AgentRoutingInfo {
  decision?: 'direct' | 'workflow' | string
  workflowRequired?: boolean
  reason?: string
  confidence?: number
  source?: string
  provider?: string
  model?: string
  directAnswerType?: string
  workflowId?: string
  runtimeEngine?: string
  implementationId?: string
}

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

export interface LawyerAgentRequest {
  text: string
  sessionId?: string
}

export interface LawyerAgentResponse {
  success: boolean
  answer: string
  sessionId: string
  skillsUsed: string[]
  trace: AgentTraceStep[]
  routing?: AgentRoutingInfo
  workflowRunId?: string
  workflowId?: string
  workflowStatus?: string
  runtimeEngine?: string
  implementationId?: string
  riskLevel?: string
  federated?: FederatedInfo
  evidenceAnalysis?: EvidenceAnalysisResult
  evidence_analysis?: EvidenceAnalysisResult
  limitationCalc?: LimitationCalcResult
  limitation_calculation?: LimitationCalcResult
  jurisdiction?: JurisdictionResult
  jurisdiction_determination?: JurisdictionResult
  hearingOutline?: HearingOutlineResult
  hearing_outline_generation?: HearingOutlineResult
  message?: string
  error?: string
}

export const agentLawyerApi = {
  async chat(payload: LawyerAgentRequest): Promise<LawyerAgentResponse> {
    const response = await request.post<LawyerAgentResponse>(
      '/agent/lawyer/chat',
      payload,
      { timeout: LAWYER_AGENT_TIMEOUT_MS }
    )
    return response.data
  }
}
