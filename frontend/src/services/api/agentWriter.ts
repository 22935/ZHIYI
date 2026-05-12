import request from '@/utils/request'
import type { AgentTraceStep, FederatedInfo } from './agentLawyer'

const WRITER_AGENT_TIMEOUT_MS = 240000

export interface CreativeTreeNode {
  id: string
  label: string
  description?: string
  children?: CreativeTreeNode[]
}

export interface InspirationExpandResult {
  premise?: string
  creative_tree?: CreativeTreeNode
  creativeTree?: CreativeTreeNode
}

export interface OutlineGenerateResult {
  creative_selection?: string
  chapters_count?: number
  outline_markdown?: string
  outlineMarkdown?: string
}

export interface ContentWriteResult {
  outline_context?: string
  chapter_index?: number
  style?: string
  content?: string
}

export interface RelationGraphNode {
  id: string
  label: string
  group?: string
}

export interface RelationGraphEdge {
  from: string
  to: string
  label?: string
}

export interface RelationGraphData {
  nodes: RelationGraphNode[]
  edges: RelationGraphEdge[]
}

export interface CharacterRelationResult {
  story_description?: string
  character_list?: string[]
  relation_graph?: RelationGraphData
  relationGraph?: RelationGraphData
}

export interface WriterAgentRequest {
  text: string
  sessionId?: string
}

export interface WriterAgentResponse {
  success: boolean
  answer: string
  sessionId: string
  skillsUsed: string[]
  trace: AgentTraceStep[]
  riskLevel?: string
  federated?: FederatedInfo
  inspirationExpand?: InspirationExpandResult
  inspiration_expand?: InspirationExpandResult
  outlineGenerate?: OutlineGenerateResult
  outline_generate?: OutlineGenerateResult
  contentWrite?: ContentWriteResult
  content_write?: ContentWriteResult
  characterRelationMap?: CharacterRelationResult
  character_relation_map?: CharacterRelationResult
  message?: string
  error?: string
}

export const agentWriterApi = {
  async chat(payload: WriterAgentRequest): Promise<WriterAgentResponse> {
    const response = await request.post<WriterAgentResponse>(
      '/agent/writer/chat',
      payload,
      { timeout: WRITER_AGENT_TIMEOUT_MS }
    )
    return response.data
  }
}
