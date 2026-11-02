import type { GraphProjection } from './graph'

export type WorkflowStatus =
  | 'pending'
  | 'planning'
  | 'running'
  | 'waiting_review'
  | 'retrying'
  | 'failed'
  | 'completed'
  | 'succeeded'
  | 'superseded'
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
  missionId: string
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
  completedStepIds?: string[]
  startedAt: string | null
  updatedAt: string | null
  runtimeRevision?: number
  progress: number
  percentage: number
}
export interface WorkflowRunSummary extends WorkflowProgress {
  source?: string | null
  title?: string | null
  createdAt?: string | null
}
export interface MemoryAccessEvent {
  kind: 'memory_access'
  stepId: string | null
  retrievalMode: string | null
  hitRefs: string[]
  fallbackReason: string | null
  createdAt: string | null
}
export interface MemoryWriteEvent {
  kind: 'memory_event'
  stepId?: string | null
  summary?: string
  createdAt?: string | null
  metrics?: {
    fieldCount?: number
    evidenceCount?: number
    modelInvocationCount?: number
    toolCallCount?: number
  }
}
export interface PhaseCapsuleEvent {
  kind: 'phase_capsule'
  phaseId?: string
  sourceMemoryRefs?: string[]
  /** 上游对 tokenCount 一律打 [redacted] 标记，wire 上是文本而不是数字。 */
  tokenCount?: string | null
}
export type RunMemoryEvent = MemoryAccessEvent | MemoryWriteEvent | PhaseCapsuleEvent
export interface RunMemoryEventsResponse {
  runId: string
  items: RunMemoryEvent[]
  total: number
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
export interface RuntimeMissionRecord {
  missionId: string
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

/** One row in the canonical Project list. A Mission owns its Runs. */
export interface MissionListItem {
  missionId: string
  userId: string
  title: string
  description: string
  status: string
  latestRunId?: string | null
  latestRunStatus?: string | null
  createdAt: string
  updatedAt: string
  runCount: number
}
export interface MissionListQuery {
  status?: string
  page?: number
  pageSize?: number
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
  outputRef?: string | null
  outputSummary?: string
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
  version: number
  canResume: boolean
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
  actionCapabilities?: RunActionCapabilities | null
  formalControl?: FormalControl | null
  error?: { code?: string } | null
  failureCode?: string | null
  executionState?: { reviewPayload?: WorkflowRun['review']; planningCommitRequired?: boolean }
  runId: string
  missionId: string
  title?: string | null
  workflowId: string
  workflowSelectionSource?: 'explicit' | 'recommended'
  domain: string
  runtimeEngine?: string
  implementationId?: string
  status: WorkflowStatus
  currentStepId?: string
  steps: WorkflowStep[]
  lifecyclePhase?: WorkflowProgressPhase | null
  lifecycleMessage?: string | null
  outputRef?: string | null
  completedStepIds?: string[]
  activeStepIds?: string[]
  skippedStepIds?: string[]
  outputs?: Array<{ stepId: string; outputRef: string; summary?: string }>
  review?: { subjectType?: string; subjectId?: string; controlId?: string; stepId?: string; reasonCode?: string; iteration?: number; approvals?: number; quorum?: number; accepted?: boolean; strategy?: string }
  lineage?: { parentRunId?: string; sourceRunId?: string; rerunReason?: string; supersedesRunId?: string; supersededByRunId?: string }
  graphVersion?: number
  acgBlueprint?: GraphProjection | null
  createdAt?: string
  updatedAt?: string
  runtimeRevision?: number
  startedAt?: string | null
  planningDiversity?: 'stable' | 'balanced' | 'exploratory'
  planningSeed?: number | null
  plannerAlgorithmVersion?: string | null
  planningCandidateCount?: number
  selectedPlanningVariantId?: string | null
}
/** Per-Run UI offers. Commands always recheck their existing server authority. */
export interface RunActionCapabilities {
  schemaVersion: 1
  missionId: string
  runId: string
  runtimeRevision: number
  status: string
  isExecutionActive: boolean
  isSuperseded: boolean
  lineage: NonNullable<WorkflowRun['lineage']>
  canInspect: boolean
  canDiscuss: boolean
  canCancel: boolean
  canReview: boolean
  canExecuteFormalAction: boolean
  formalActions: Array<'materialize' | 'activate' | 'handoff' | 'permit' | 'dispatch'>
  canResolveToolApproval: boolean
  canAnswerPlanner: boolean
  canCollaborate: boolean
  canRetrySuccessor: boolean
  retryStepId: string | null
  canRerunSuccessor: boolean
  canDecideRevision: boolean
  canApplyRevision: boolean
  canDelete: boolean
  unavailableReasons: Array<{ action: string; code: string }>
}
/** Read-only projection of server facts; never an executable snapshot. */
export interface FormalControl {
  status: string
  executionAuthorized: boolean
  permitIssued: boolean
  dispatchEligible: boolean
  dispatchEnabled: boolean
  commitId: string | null
  commitmentRevision: number | null
  materializationId: string | null
  activationId: string | null
  graphId: string | null
  graphVersion: number | null
  handoffId: string | null
  handoffStatus: string | null
  permitId: string | null
  permitStatus: string | null
  dispatch: { dispatchId: string; runId: string; permitId: string; graphVersion: number; status: string } | null
}
export interface WorkflowTraceExport {
  runId: string
  missionId: string
  workflowId: string
  domain: string
  status: WorkflowStatus
  eventCount: number
  events: TraceEvent[]
}
export interface WorkflowStartRequest {
  semantics?: MissionSemanticContent
  title: string
  domain: string
  intent: string
  input?: Record<string, any>
  securityLevel?: string
  priority?: string
  workflowId?: string
  reviewMode?: string
  enabledPluginIds?: string[] | null
  materialRefs?: string[]
  attachmentIds?: string[]
}
export interface MissionSemanticContent {
  objective: string
  constraints: Array<{ constraintId: string; text: string; sourceRefs?: string[] }>
  sourceRefs: string[]
}
export interface MissionSemanticEditRequest extends MissionSemanticContent {
  operationId: string
  expectedMissionRevision: number
}
export interface MissionSemanticResult {
  status: 'COMMITTED' | 'NO_OP' | 'REVISION_CONFLICT' | 'OPERATION_CONFLICT'
  missionId: string
  operationId: string
  missionRevision: number
  commitId?: string | null
}
export interface ContentManifestSummary {
  manifestId: string
  kind: 'material' | 'intermediate' | 'artifact'
  mediaType: string
  checksum?: string | null
  byteLength: number
  fragmentCount: number
  estimatedTokens?: number | null
  chunkingVersion: string
  sealed: boolean
}
export type WorkflowStartResponse = WorkflowRun
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
export interface WorkflowRunQuery {
  status?: WorkflowStatus | ''
  statuses?: string
  domain?: string
  workflowId?: string
  missionId?: string
  lifecyclePhase?: WorkflowProgressPhase | ''
  source?: string
  sources?: string
  recordState?: 'active' | 'archived'
  summary?: boolean
  page?: number
  pageSize?: number
}

// ===== ACG 动态群体智能引擎可视化视图类型 =====
export interface AsyncWorkflowStartRequest extends WorkflowStartRequest {
  clientRequestId: string
}
export interface WorkflowRerunRequest {
  workflowId?: string
  reviewMode?: string
  input?: Record<string, any>
  enabledPluginIds?: string[] | null
  materialRefs?: string[]
  attachmentIds?: string[]
  clientRequestId: string
  sourceRunId: string
  rerunReason: 'manual_rerun' | 'current_configuration' | 'retry_after_failure' | 'planning_variant' | 'review_rerun'
}
export interface SingleStepRetryRequest {
  clientRequestId: string
  reason?: string
  expectedRuntimeRevision?: number
  mode?: 'successor_run' | 'current_run'
}
export type AsyncWorkflowStartResponse = WorkflowRun
export class WorkflowApiContractError extends Error {
  readonly code = 'INVALID_ASYNC_WORKFLOW_RESPONSE'

  constructor(message = '异步启动响应缺少有效的 run.runId') {
    super(message)
    this.name = 'WorkflowApiContractError'
  }
}
/** 后端 history-config wire 的 pluginData typed 关联行；API 入口解码回 Record。 */
export interface WorkflowHistoryPluginEntry {
  name: string
  text?: string | null
  bool?: boolean | null
  number?: number | string | null
}
export interface WorkflowHistoryConfig {
  runId: string
  title?: string | null
  reviewMode?: string
  enabledPluginIds?: string[]
  input?: Record<string, unknown>
}
