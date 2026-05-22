import axios from 'axios'

const agentosRequest = axios.create({
  baseURL: '/ai',
  timeout: 240000,
  headers: {
    'Content-Type': 'application/json'
  }
})

agentosRequest.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  const userId = localStorage.getItem('userId')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (userId) {
    config.headers['X-User-Id'] = userId
  }
  return config
})

export type WorkflowStatus =
  | 'pending'
  | 'planning'
  | 'running'
  | 'waiting_review'
  | 'retrying'
  | 'failed'
  | 'completed'
  | 'cancelled'

export type StepStatus =
  | 'pending'
  | 'running'
  | 'waiting_review'
  | 'retrying'
  | 'failed'
  | 'completed'
  | 'cancelled'

export interface AgentTask {
  taskId: string
  title: string
  domain: string
  intent: string
  input: Record<string, any>
  securityLevel: string
  priority: string
  status: WorkflowStatus
  recommendedWorkflow?: string
  createdAt?: string
  updatedAt?: string
}

export interface PageResponse<T> {
  items: T[]
  total: number
  page?: number
  pageSize?: number
}

export interface WorkflowStep {
  stepId: string
  name: string
  agentName: string
  capability?: string
  status: StepStatus
  input?: Record<string, any>
  output?: Record<string, any>
  error?: string
  retryCount?: number
  maxRetries?: number
  reviewRequired?: boolean
  durationMs?: number
  startedAt?: string
  completedAt?: string
}

export interface Checkpoint {
  checkpointId: string
  runId: string
  stepId: string
  stateSnapshot: Record<string, any>
  outputSnapshot: Record<string, any>
  canResume: boolean
  createdAt?: string
}

export interface TraceEvent {
  eventId: string
  runId: string
  stepId?: string
  agentName?: string
  eventType: string
  observation?: string
  payload?: Record<string, any>
  durationMs?: number
  createdAt?: string
}

export interface WorkflowRun {
  runId: string
  taskId: string
  workflowId: string
  domain: string
  status: WorkflowStatus
  currentStepId?: string
  reviewMode: string
  input: Record<string, any>
  output: Record<string, any>
  steps: WorkflowStep[]
  checkpoints: Checkpoint[]
  trace: TraceEvent[]
  error?: string
  recoveryCount?: number
  createdAt?: string
  updatedAt?: string
}

export interface WorkflowTraceExport {
  runId: string
  taskId: string
  workflowId: string
  domain: string
  status: WorkflowStatus
  eventCount: number
  events: TraceEvent[]
}

export interface WorkflowStartRequest {
  title: string
  domain: string
  intent: string
  input?: Record<string, any>
  securityLevel?: string
  priority?: string
  workflowId?: string
  reviewMode?: string
}

export interface WorkflowStartResponse {
  task: AgentTask
  run: WorkflowRun
  source?: string
}

export interface ChatWorkflowUpgradeRequest {
  text: string
  title?: string
  domain?: string
  intent?: string
  workflowId?: string
  reviewMode?: string
  roleId?: string
  contextId?: string
  context?: Array<{ role: string; content: string }>
  input?: Record<string, any>
}

export type ReviewDecision = 'approved' | 'rejected' | 'need_more_info' | 'rerun' | 'cancelled'

export interface ReviewRequest {
  stepId: string
  decision: ReviewDecision
  reviewer?: string
  comment?: string
}

export interface ReviewRecord {
  reviewId: string
  runId: string
  stepId: string
  decision: ReviewDecision
  reviewer: string
  comment?: string
  traceEventId?: string
  createdAt?: string
}

export interface WorkflowMetric {
  totalRuns: number
  completedRuns: number
  failedRuns: number
  cancelledRuns: number
  waitingReviewRuns: number
  retryingRuns: number
  completionRate: number
  failureRate: number
  recoverySuccessRate: number
  averageRecoveryCount: number
  averageTraceEvents: number
  reviewCount: number
  statusBreakdown: Record<string, number>
}

export interface EvaluationRun {
  evaluationId: string
  domain?: string
  workflowId?: string
  source?: string
  metrics: WorkflowMetric
  createdAt?: string
}

export interface WorkflowRunQuery {
  status?: WorkflowStatus | ''
  domain?: string
  workflowId?: string
  source?: string
  page?: number
  pageSize?: number
}

export const agentosApi = {
  async listWorkflowRuns(params: WorkflowRunQuery = {}): Promise<PageResponse<WorkflowRun>> {
    const response = await agentosRequest.get<PageResponse<WorkflowRun>>('/core/workflows/runs', { params })
    return response.data
  },

  async startWorkflow(payload: WorkflowStartRequest): Promise<WorkflowStartResponse> {
    const response = await agentosRequest.post<WorkflowStartResponse>('/core/workflows/start', payload)
    return response.data
  },

  async upgradeChatToWorkflow(payload: ChatWorkflowUpgradeRequest): Promise<WorkflowStartResponse> {
    const response = await agentosRequest.post<WorkflowStartResponse>('/chat/workflows/upgrade', payload)
    return response.data
  },

  async getWorkflowRun(runId: string): Promise<WorkflowRun> {
    const response = await agentosRequest.get<WorkflowRun>(`/core/workflows/runs/${runId}`)
    return response.data
  },

  async listWorkflowCheckpoints(runId: string): Promise<PageResponse<Checkpoint> & { runId: string }> {
    const response = await agentosRequest.get<PageResponse<Checkpoint> & { runId: string }>(`/core/workflows/runs/${runId}/checkpoints`)
    return response.data
  },

  async getWorkflowTrace(runId: string): Promise<WorkflowTraceExport> {
    const response = await agentosRequest.get<WorkflowTraceExport>(`/core/workflows/runs/${runId}/trace`)
    return response.data
  },

  async exportWorkflowTraceMarkdown(runId: string): Promise<string> {
    const response = await agentosRequest.get<string>(`/core/workflows/runs/${runId}/trace`, {
      params: { format: 'markdown' },
      responseType: 'text'
    })
    return response.data
  },

  async listWorkflowReviews(runId: string): Promise<PageResponse<ReviewRecord> & { runId: string }> {
    const response = await agentosRequest.get<PageResponse<ReviewRecord> & { runId: string }>(`/core/workflows/runs/${runId}/reviews`)
    return response.data
  },

  async applyWorkflowReview(runId: string, payload: ReviewRequest): Promise<WorkflowRun> {
    const response = await agentosRequest.post<WorkflowRun>(`/core/workflows/runs/${runId}/reviews`, payload)
    return response.data
  },

  async resumeWorkflow(runId: string, checkpointId: string): Promise<WorkflowRun> {
    const response = await agentosRequest.post<WorkflowRun>(`/core/workflows/runs/${runId}/resume`, { checkpointId })
    return response.data
  },

  async getWorkflowMetrics(params: Pick<WorkflowRunQuery, 'status' | 'domain' | 'workflowId' | 'source'> = {}): Promise<EvaluationRun> {
    const response = await agentosRequest.get<EvaluationRun>('/core/workflows/metrics', { params })
    return response.data
  }
}
