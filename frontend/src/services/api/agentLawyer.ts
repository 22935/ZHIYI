import request from '@/utils/request'

const LAWYER_AGENT_TIMEOUT_MS = 120000

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
  riskLevel?: string
  federated?: FederatedInfo
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
