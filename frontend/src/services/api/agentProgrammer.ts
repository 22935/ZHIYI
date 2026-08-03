import request from '@/utils/request'
import type { AgentRoutingInfo, AgentTraceStep, FederatedInfo } from './agentLawyer'

const PROGRAMMER_AGENT_TIMEOUT_MS = 240000

export interface RequirementAnalysisResult {
  requirement?: string
  functional_requirements?: string[]
  inputs?: string[]
  outputs?: string[]
  boundary_conditions?: string[]
  acceptance_criteria?: string[]
  suggested_modules?: string[]
}

export interface CodeSearchHit {
  id?: string
  content?: string
  score?: number
  file_path?: string
  function_name?: string
  class_name?: string
  language?: string
  line?: number
  metadata?: Record<string, any>
}

export interface CodebaseSemanticSearchResult {
  query?: string
  top_k?: number
  hits?: CodeSearchHit[]
  index_status?: {
    success?: boolean
    root_path?: string
    indexed_files?: number
    indexed_docs?: number
    deleted_docs?: number
    total_files?: number
    vector_enabled?: boolean
    message?: string
  }
}

export interface CodeGenerationResult {
  target_language?: string
  code?: string
  explanation?: string
  suggested_tests?: string[]
  mermaid_code?: string
  context_refs?: Array<{
    file_path?: string
    function_name?: string
    class_name?: string
    score?: number
  }>
}

export interface DiagramGenerationResult {
  title?: string
  diagram_type?: string
  mermaid_code?: string
  source_query?: string
}

export interface ProgrammerAgentRequest {
  text: string
  sessionId?: string
}

export interface ProgrammerAgentResponse {
  success: boolean
  answer: string
  sessionId: string
  skillsUsed: string[]
  trace: AgentTraceStep[]
  routing?: AgentRoutingInfo
  acgTaskId?: string
  enabledPluginIds?: string[]
  workflowRunId?: string
  workflowId?: string
  workflowStatus?: string
  runtimeEngine?: string
  implementationId?: string
  riskLevel?: string
  federated?: FederatedInfo
  requirementAnalysis?: RequirementAnalysisResult
  requirement_analysis?: RequirementAnalysisResult
  codebaseSemanticSearch?: CodebaseSemanticSearchResult
  codebase_semantic_search?: CodebaseSemanticSearchResult
  codeGeneration?: CodeGenerationResult
  code_generation?: CodeGenerationResult
  diagramGeneration?: DiagramGenerationResult
  diagram_generation?: DiagramGenerationResult
  message?: string
  error?: string
}

export const agentProgrammerApi = {
  async chat(payload: ProgrammerAgentRequest): Promise<ProgrammerAgentResponse> {
    const response = await request.post<ProgrammerAgentResponse>(
      '/agent/programmer/chat',
      payload,
      { timeout: PROGRAMMER_AGENT_TIMEOUT_MS }
    )
    return response.data
  }
}
