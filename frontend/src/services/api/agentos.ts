import axios from 'axios'

export const agentosRequest = axios.create({
  baseURL: '/ai',
  timeout: 240000,
  headers: {
    'Content-Type': 'application/json'
  }
})

agentosRequest.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
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
  | 'skipped_by_condition'

export type WorkflowProgressPhase =
  | 'understanding'
  | 'planning'
  | 'graph_building'
  | 'executing'
  | 'recovery'
  | 'review'
  | 'completed'
  | 'failed'
  | 'cancelled'

export interface WorkflowProgress {
  taskId: string
  runId: string
  workflowId: string
  status: string
  phase: WorkflowProgressPhase
  message: string
  percent: number | null
  totalSteps: number
  pendingSteps: number
  runningSteps: number
  waitingReviewSteps: number
  retryingSteps: number
  failedSteps: number
  completedSteps: number
  cancelledSteps: number
  currentStepId: string | null
  activeStepIds: string[]
  recoveryCount: number
  graphVersion?: number | null
  dynamicStepCount?: number
  bindingSwitchCount?: number
  skippedByConditionCount?: number
  conditionalDecisionCount?: number
  startedAt: string | null
  updatedAt: string | null
  progress: number
  percentage: number
}

export interface WorkflowRunSummary extends WorkflowProgress {
  source?: string | null
  title?: string | null
  createdAt?: string | null
}

export interface WorkflowRunDeleteResponse {
  runId: string
  taskId: string
  deleted: boolean
  taskDeleted: boolean
}

export type StepStatus =
  | 'pending'
  | 'running'
  | 'waiting_review'
  | 'retrying'
  | 'failed'
  | 'completed'
  | 'cancelled'
  | 'skipped_by_condition'

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
  enabledPluginIds?: string[] | null
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
  outputSpec?: Record<string, any>
  resolvedInput?: Record<string, any>
  output?: Record<string, any>
  error?: string
  retryCount?: number
  attempt?: number
  maxRetries?: number
  timeout?: number
  priority?: number
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
  title?: string | null
  workflowId: string
  domain: string
  runtimeEngine?: string
  implementationId?: string
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
  enabledPluginIds?: string[]
  resolvedEnabledPluginIds?: string[]
  pluginSnapshot?: PluginSnapshot[]
  capabilityCatalogRevision?: string | null
  planningDiversity?: 'stable' | 'balanced' | 'exploratory'
  planningSeed?: number | null
  plannerAlgorithmVersion?: string | null
  planningCandidateCount?: number
  selectedPlanningVariantId?: string | null
  executionScope?: RunExecutionScope | null
  legacyPluginScope?: boolean
  completedStepIds?: string[]
  activeStepIds?: string[]
  provenance?: Record<string, any>
  executionState?: Record<string, any>
  runtimeGraph?: Record<string, any> | null
  graphVersion?: number | null
  dynamicStepCount?: number
  bindingSwitchCount?: number
  appliedPatches?: AppliedPatchProjection[]
  runtimeEvents?: RuntimeEventProjection[]
  branchDecisions?: BranchDecision[]
  skippedByConditionCount?: number
  conditionalDecisionCount?: number
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
  enabledPluginIds?: string[] | null
  planningDiversity?: 'stable' | 'balanced' | 'exploratory'
  planningSeed?: number
}

export interface PluginSnapshot {
  pluginId: string
  version: string
  manifestHash: string
  contributionRevision: string
}

export interface InstalledPlugin {
  pluginId: string
  version: string
  displayName: string
  description: string
  available: boolean
  capabilityCount: number
  agentCount: number
  workflowCount: number
  uiExtensionId?: string | null
}

export interface RunExecutionScope {
  enabledPluginIds: string[]
  capabilityIds: string[]
  agentIds: string[]
  workflowIds: string[]
  pluginSnapshots: PluginSnapshot[]
  capabilityCatalogRevision: string
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
  operationId?: string
  expectedRunUpdatedAt?: string
  expectedStepStatus?: StepStatus
}

export interface RuntimeEventProjection {
  eventId: string
  eventType: string
  graphVersion?: number
  runtimeNodeId?: string
  attemptId?: string
  bindingId?: string
  payload?: Record<string, any>
  status?: string
  statusReason?: string
  createdAt?: string
}

export interface AppliedPatchProjection {
  patchId: string
  operationType: string
  baseGraphVersion?: number
  resultGraphVersion?: number
  sourceEventId?: string
  appliedAt?: string
}

export interface RuntimeAttemptProjection {
  attemptId: string
  attemptNumber: number
  graphVersion?: number
  bindingId?: string
  agentName?: string
  modelName?: string
  status: StepStatus
  startedAt?: string
  endedAt?: string | null
  errorSummary?: string | null
}

export interface ReviewRecord {
  reviewId: string
  runId: string
  stepId: string
  decision: ReviewDecision
  reviewer: string
  comment?: string
  operationId?: string
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
  statuses?: string
  domain?: string
  workflowId?: string
  taskId?: string
  lifecyclePhase?: WorkflowProgressPhase | ''
  source?: string
  summary?: boolean
  page?: number
  pageSize?: number
}

// ===== ACG 动态群体智能引擎可视化视图类型 =====

export interface AcgNode {
  nodeId: string
  nodeType: 'step' | 'agent' | 'skill' | 'memory' | 'evidence' | 'control'
  name?: string
  description?: string
  goal?: string
  agentName?: string
  capability?: string
  controlType?: string
  metadata?: Record<string, any>
}

export interface AcgEdge {
  edgeId: string
  sourceId: string
  targetId: string
  edgeType: 'dependency' | 'communication' | 'control_flow' | 'execution' | 'write' | 'read' | 'support'
  condition?: string
  activation?: 'inactive' | 'active' | 'terminated' | 'superseded'
  metadata?: Record<string, any>
}

export interface AcgBlueprint {
  graphId: string
  taskId?: string
  objective?: string
  complexityLevel?: string
  nodes: AcgNode[]
  edges: AcgEdge[]
  metadata?: Record<string, any>
}

export interface ProvenanceProduction {
  eventId: string
  producerStepId: string
  checksum?: string
  fieldNames?: string[]
  tokenSize?: number
  runId?: string
  taskId?: string
  agentName?: string
  attempt?: number
  previousHash?: string
  eventHash?: string
  createdAt?: string
  evidenceRefs?: string[]
}

export interface BranchDecision {
  decisionId: string
  controlNodeId: string
  sourceNodeId: string
  sourceOutputVersion: number
  inputHash: string
  selectedCaseKey: string
  selectedEdgeIds: string[]
  terminatedEdgeIds: string[]
  skippedNodeIds: string[]
  joinNodeId: string
  sourceEventId: string
  sourcePatchId: string
  decidedAtGraphVersion: number
  decidedAt: string
}

export interface AsyncWorkflowStartRequest extends WorkflowStartRequest {
  clientRequestId: string
  roleType?: string
  taskType?: string
}

export interface AsyncWorkflowStartResponse {
  accepted: boolean
  task: {
    taskId: string
    status: string
  }
  run: {
    runId: string
    status: string
    workflowId?: string
    lifecyclePhase?: WorkflowProgressPhase
    lifecycleMessage?: string
  }
}

export class WorkflowApiContractError extends Error {
  readonly code = 'INVALID_ASYNC_WORKFLOW_RESPONSE'

  constructor(message = '异步启动响应缺少有效的 run.runId') {
    super(message)
    this.name = 'WorkflowApiContractError'
  }
}

export interface ProvenanceConsumption {
  eventId: string
  consumerStepId: string
  producerStepIds: string[]
  runId?: string
  taskId?: string
  consumerAgentName?: string
  attempt?: number
  producerEventIds?: string[]
  consumedFields?: string[]
  fieldsByProducer?: Record<string, string[]>
  tokensDelivered?: number
  tokensAvailable?: number
  savingRatio?: number
  contractStatus?: string
  checksum?: string
  previousHash?: string
  eventHash?: string
  createdAt?: string
}

export interface RuntimeInteraction {
  interactionId: string
  eventId: string
  runId?: string
  taskId?: string
  edgeIds: string[]
  producerStepIds: string[]
  consumerStepId: string
  producerAgentNames: string[]
  consumerAgentName: string
  fieldsByProducer: Record<string, string[]>
  tokensDelivered: number
  tokensAvailable: number
  savingRatio: number
  evidenceRefs: string[]
  contractStatus: string
  checksum?: string
  previousHash?: string
  eventHash?: string
  createdAt?: string
}

export interface AcgStepState {
  stepId: string
  status: StepStatus
  agentName: string
  attempt: number
  retryCount: number
  currentBinding?: Record<string, any> | null
  bindingHistory?: Array<Record<string, any>>
  bindingSwitchCount?: number
  attempts?: RuntimeAttemptProjection[]
  sourcePatchId?: string | null
  createdGraphVersion?: number
  outputVersion?: number
  outputSummary?: string
  errorSummary?: string | null
}

export interface AcgLowEntropyMetrics {
  averageSavingRatio: number
  effectiveSavingRatio: number
  tokensAvailable: number
  tokensDelivered: number
  tokensSaved: number
  recoveryCount: number
  interactionCount: number
  contractViolationCount: number
  integrityStatus: string
}

export interface AcgDeliverable {
  stepId: string
  name: string
  status: string
  output: Record<string, any>
}

export interface AcgFinalArtifact {
  artifactId: string
  type: string
  title: string
  mediaType: string
  content: string
  structuredData: Record<string, any>
  stepId?: string | null
  legacy?: boolean
}

export interface AcgView {
  runId: string
  status: WorkflowStatus
  engine: string
  acgBlueprint: AcgBlueprint | null
  graphVersion?: number | null
  dynamicStepCount?: number
  bindingSwitchCount?: number
  skippedByConditionCount?: number
  conditionalDecisionCount?: number
  branchDecisions?: BranchDecision[]
  selectedEdgeIds?: string[]
  terminatedEdgeIds?: string[]
  appliedPatches?: AppliedPatchProjection[]
  runtimeEvents?: RuntimeEventProjection[]
  completedStepIds: string[]
  activeStepIds: string[]
  stepStates: AcgStepState[]
  provenance: {
    schemaVersion?: number
    productions: ProvenanceProduction[]
    consumptions: ProvenanceConsumption[]
    interactions: RuntimeInteraction[]
    integrityStatus?: string
  }
  interactions: RuntimeInteraction[]
  contractViolations: TraceEvent[]
  recoveryTrace: TraceEvent[]
  scheduleTrace: TraceEvent[]
  deliverables: AcgDeliverable[]
  stepOutputs?: AcgDeliverable[]
  finalArtifacts?: AcgFinalArtifact[]
  finalReport: string | null
  lowEntropyMetrics: AcgLowEntropyMetrics
}

const normalizeAcgView = (view: AcgView): AcgView => ({
  ...view,
  graphVersion: view.graphVersion ?? null,
  dynamicStepCount: view.dynamicStepCount ?? 0,
  bindingSwitchCount: view.bindingSwitchCount ?? 0,
  skippedByConditionCount: view.skippedByConditionCount ?? 0,
  conditionalDecisionCount: view.conditionalDecisionCount ?? 0,
  appliedPatches: Array.isArray(view.appliedPatches) ? view.appliedPatches : [],
  runtimeEvents: Array.isArray(view.runtimeEvents) ? view.runtimeEvents : [],
  branchDecisions: Array.isArray(view.branchDecisions) ? view.branchDecisions : [],
  selectedEdgeIds: Array.isArray(view.selectedEdgeIds) ? view.selectedEdgeIds : [],
  terminatedEdgeIds: Array.isArray(view.terminatedEdgeIds) ? view.terminatedEdgeIds : [],
  completedStepIds: Array.isArray(view.completedStepIds) ? view.completedStepIds : [],
  activeStepIds: Array.isArray(view.activeStepIds) ? view.activeStepIds : [],
  stepStates: Array.isArray(view.stepStates) ? view.stepStates : [],
  provenance: {
    schemaVersion: view.provenance?.schemaVersion,
    productions: Array.isArray(view.provenance?.productions) ? view.provenance.productions : [],
    consumptions: Array.isArray(view.provenance?.consumptions) ? view.provenance.consumptions : [],
    interactions: Array.isArray(view.provenance?.interactions) ? view.provenance.interactions : [],
    integrityStatus: view.provenance?.integrityStatus
  },
  interactions: Array.isArray(view.interactions) ? view.interactions : [],
  contractViolations: Array.isArray(view.contractViolations) ? view.contractViolations : [],
  recoveryTrace: Array.isArray(view.recoveryTrace) ? view.recoveryTrace : [],
  scheduleTrace: Array.isArray(view.scheduleTrace) ? view.scheduleTrace : [],
  deliverables: Array.isArray(view.deliverables) ? view.deliverables : [],
  stepOutputs: Array.isArray(view.stepOutputs)
    ? view.stepOutputs
    : (Array.isArray(view.deliverables) ? view.deliverables : []),
  finalArtifacts: Array.isArray(view.finalArtifacts) ? view.finalArtifacts : [],
  finalReport: typeof view.finalReport === 'string' ? view.finalReport : null,
  lowEntropyMetrics: {
    averageSavingRatio: 0,
    effectiveSavingRatio: 0,
    tokensAvailable: 0,
    tokensDelivered: 0,
    tokensSaved: 0,
    recoveryCount: 0,
    interactionCount: 0,
    contractViolationCount: 0,
    integrityStatus: 'valid',
    ...(view.lowEntropyMetrics || {})
  }
})

export const agentosApi = {
  async listInstalledPlugins(): Promise<InstalledPlugin[]> {
    const response = await agentosRequest.get<InstalledPlugin[]>('/core/plugins')
    return response.data
  },

  async listWorkflowRuns(
    params: WorkflowRunQuery = {},
    options: { signal?: AbortSignal } = {}
  ): Promise<PageResponse<WorkflowRunSummary>> {
    const response = await agentosRequest.get<PageResponse<WorkflowRunSummary>>('/core/workflows/runs', {
      params: { summary: true, ...params },
      signal: options.signal
    })
    return response.data
  },

  async startWorkflow(payload: WorkflowStartRequest): Promise<WorkflowStartResponse> {
    const response = await agentosRequest.post<WorkflowStartResponse>('/core/workflows/start', payload)
    return response.data
  },

  async startWorkflowAsync(
    payload: AsyncWorkflowStartRequest,
    options: { signal?: AbortSignal } = {}
  ): Promise<AsyncWorkflowStartResponse> {
    const response = await agentosRequest.post<AsyncWorkflowStartResponse>(
      '/core/workflows/start-async',
      payload,
      { signal: options.signal }
    )
    const data = response.data
    if (
      data?.accepted !== true
      || !data.task
      || typeof data.task.taskId !== 'string'
      || !data.task.taskId.trim()
      || !data.run
      || typeof data.run.runId !== 'string'
      || !data.run.runId.trim()
    ) {
      throw new WorkflowApiContractError('异步启动响应缺少 accepted、task.taskId 或 run.runId')
    }
    return data
  },

  async getWorkflowProgress(
    runId: string,
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkflowProgress> {
    const response = await agentosRequest.get<WorkflowProgress>(
      `/core/workflows/runs/${encodeURIComponent(runId)}/progress`,
      { signal: options.signal }
    )
    return response.data
  },

  async upgradeChatToWorkflow(payload: ChatWorkflowUpgradeRequest): Promise<WorkflowStartResponse> {
    const response = await agentosRequest.post<WorkflowStartResponse>('/chat/workflows/upgrade', payload)
    return response.data
  },

  async getWorkflowRun(runId: string, options: { signal?: AbortSignal } = {}): Promise<WorkflowRun> {
    const response = await agentosRequest.get<WorkflowRun>(`/core/workflows/runs/${runId}`, {
      signal: options.signal
    })
    return response.data
  },

  async deleteWorkflowRun(
    runId: string,
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkflowRunDeleteResponse> {
    const response = await agentosRequest.delete<WorkflowRunDeleteResponse>(
      `/core/workflows/runs/${encodeURIComponent(runId)}`,
      { signal: options.signal }
    )
    return response.data
  },

  async listWorkflowCheckpoints(runId: string, options: { signal?: AbortSignal } = {}): Promise<PageResponse<Checkpoint> & { runId: string }> {
    const response = await agentosRequest.get<PageResponse<Checkpoint> & { runId: string }>(`/core/workflows/runs/${runId}/checkpoints`, { signal: options.signal })
    return response.data
  },

  async getWorkflowTrace(runId: string, options: { signal?: AbortSignal } = {}): Promise<WorkflowTraceExport> {
    const response = await agentosRequest.get<WorkflowTraceExport>(`/core/workflows/runs/${runId}/trace`, { signal: options.signal })
    return response.data
  },

  async exportWorkflowTraceMarkdown(runId: string): Promise<string> {
    const response = await agentosRequest.get<string>(`/core/workflows/runs/${runId}/trace`, {
      params: { format: 'markdown' },
      responseType: 'text'
    })
    return response.data
  },

  async listWorkflowReviews(runId: string, options: { signal?: AbortSignal } = {}): Promise<PageResponse<ReviewRecord> & { runId: string }> {
    const response = await agentosRequest.get<PageResponse<ReviewRecord> & { runId: string }>(`/core/workflows/runs/${runId}/reviews`, { signal: options.signal })
    return response.data
  },

  async applyWorkflowReview(runId: string, payload: ReviewRequest, options: { signal?: AbortSignal } = {}): Promise<WorkflowRun> {
    const response = await agentosRequest.post<WorkflowRun>(`/core/workflows/runs/${runId}/reviews`, payload, { signal: options.signal })
    return response.data
  },

  async resumeWorkflow(runId: string, checkpointId: string): Promise<WorkflowRun> {
    const response = await agentosRequest.post<WorkflowRun>(`/core/workflows/runs/${runId}/resume`, { checkpointId })
    return response.data
  },

  async getWorkflowMetrics(params: Pick<WorkflowRunQuery, 'status' | 'domain' | 'workflowId' | 'source'> = {}): Promise<EvaluationRun> {
    const response = await agentosRequest.get<EvaluationRun>('/core/workflows/metrics', { params })
    return response.data
  },

  async getAcgView(runId: string, options: { signal?: AbortSignal } = {}): Promise<AcgView> {
    const response = await agentosRequest.get<AcgView>(`/core/workflows/runs/${runId}/acg`, {
      signal: options.signal
    })
    return normalizeAcgView(response.data)
  }
}
