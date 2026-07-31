import {
  agentosApi,
  type AcgView,
  type AcgBlueprint,
  type AcgNode,
  type AcgEdge,
  type AcgLowEntropyMetrics,
  type AcgDeliverable,
  type AcgFinalArtifact,
  type ProvenanceConsumption,
  type ProvenanceProduction,
  type RuntimeInteraction,
  type AcgStepState,
  type Checkpoint,
  type EvaluationRun,
  type PageResponse,
  type ReviewRecord,
  type ReviewRequest,
  type WorkflowStartRequest,
  type WorkflowStartResponse,
  type AsyncWorkflowStartRequest,
  type AsyncWorkflowStartResponse,
  type WorkflowProgress,
  type WorkflowProgressPhase,
  type WorkflowRunSummary,
  type WorkflowRunDeleteResponse,
  type ReviewDecision,
  type StepStatus,
  type TraceEvent,
  type WorkflowRun,
  type WorkflowRunQuery,
  type WorkflowStep,
  type WorkflowStatus,
  type WorkflowTraceExport,
  type InstalledPlugin
} from './agentos'

export type {
  AcgView,
  AcgBlueprint,
  AcgNode,
  AcgEdge,
  AcgLowEntropyMetrics,
  AcgDeliverable,
  AcgFinalArtifact,
  ProvenanceConsumption,
  ProvenanceProduction,
  RuntimeInteraction,
  AcgStepState,
  Checkpoint,
  EvaluationRun,
  PageResponse,
  ReviewRecord,
  ReviewRequest,
  WorkflowStartRequest,
  WorkflowStartResponse,
  AsyncWorkflowStartRequest,
  AsyncWorkflowStartResponse,
  WorkflowProgress,
  WorkflowProgressPhase,
  WorkflowRunSummary,
  WorkflowRunDeleteResponse,
  ReviewDecision,
  StepStatus,
  TraceEvent,
  WorkflowRun,
  WorkflowRunQuery,
  WorkflowStep,
  WorkflowStatus,
  WorkflowTraceExport,
  InstalledPlugin
}

export const workflowApi = {
  listInstalledPlugins(): Promise<InstalledPlugin[]> {
    return agentosApi.listInstalledPlugins()
  },

  startWorkflow(payload: WorkflowStartRequest): Promise<WorkflowStartResponse> {
    return agentosApi.startWorkflow(payload)
  },

  startWorkflowAsync(
    payload: AsyncWorkflowStartRequest,
    options: { signal?: AbortSignal } = {}
  ): Promise<AsyncWorkflowStartResponse> {
    return agentosApi.startWorkflowAsync(payload, options)
  },

  getWorkflowProgress(
    runId: string,
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkflowProgress> {
    return agentosApi.getWorkflowProgress(runId, options)
  },

  listRuns(
    params: WorkflowRunQuery = {},
    options: { signal?: AbortSignal } = {}
  ): Promise<PageResponse<WorkflowRunSummary>> {
    return agentosApi.listWorkflowRuns({ page: 1, pageSize: 20, ...params }, options)
  },

  getRun(runId: string, options: { signal?: AbortSignal } = {}): Promise<WorkflowRun> {
    return agentosApi.getWorkflowRun(runId, options)
  },

  deleteRun(
    runId: string,
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkflowRunDeleteResponse> {
    return agentosApi.deleteWorkflowRun(runId, options)
  },

  getTrace(runId: string, options: { signal?: AbortSignal } = {}): Promise<WorkflowTraceExport> {
    return agentosApi.getWorkflowTrace(runId, options)
  },

  exportTraceMarkdown(runId: string): Promise<string> {
    return agentosApi.exportWorkflowTraceMarkdown(runId)
  },

  listCheckpoints(runId: string, options: { signal?: AbortSignal } = {}): Promise<PageResponse<Checkpoint> & { runId: string }> {
    return agentosApi.listWorkflowCheckpoints(runId, options)
  },

  listReviews(runId: string, options: { signal?: AbortSignal } = {}): Promise<PageResponse<ReviewRecord> & { runId: string }> {
    return agentosApi.listWorkflowReviews(runId, options)
  },

  submitReview(runId: string, payload: ReviewRequest, options: { signal?: AbortSignal } = {}): Promise<WorkflowRun> {
    return agentosApi.applyWorkflowReview(runId, payload, options)
  },

  resumeFromCheckpoint(runId: string, checkpointId: string): Promise<WorkflowRun> {
    return agentosApi.resumeWorkflow(runId, checkpointId)
  },

  getMetrics(params: Pick<WorkflowRunQuery, 'status' | 'domain' | 'workflowId' | 'source'> = {}): Promise<EvaluationRun> {
    return agentosApi.getWorkflowMetrics(params)
  },

  getAcgView(runId: string, options: { signal?: AbortSignal } = {}): Promise<AcgView> {
    return agentosApi.getAcgView(runId, options)
  }
}
