import { agentosRequest } from '../client'
import type { Checkpoint, PageResponse, ReviewRecord, ReviewRequest, RunMemoryEventsResponse, SingleStepRetryRequest, StepStatus, WorkflowHistoryConfig, WorkflowHistoryPluginEntry, WorkflowProgress, WorkflowProgressPhase, WorkflowRerunRequest, WorkflowRun, WorkflowRunQuery, WorkflowRunSummary, WorkflowTraceExport } from '../types'
import { WorkflowApiContractError } from '../types'
import { runPath } from '../paths'
import type { WorkflowApiDependencies } from '../dependencies'

const phaseOf = (run: WorkflowRun): WorkflowProgressPhase => {
  if (run.status === 'completed' || run.status === 'failed' || run.status === 'cancelled') return run.status
  if (run.lifecyclePhase) return run.lifecyclePhase
  if (run.status === 'waiting_review') return 'review'
  if (run.status === 'pending' || run.status === 'planning') return 'planning'
  return 'executing'
}

const projectProgress = (run: WorkflowRun): WorkflowProgress => {
  const steps = Array.isArray(run.steps) ? run.steps : []
  const count = (status: StepStatus) => steps.filter(step => step.status === status).length
  const completed = count('completed') + count('skipped_by_condition')
  const total = steps.length
  const percent = run.status === 'completed' ? 100 : total ? Math.round((completed / total) * 10000) / 100 : null
  return {
    missionId: run.missionId,
    runId: run.runId,
    workflowId: run.workflowId,
    status: run.status,
    phase: phaseOf(run),
    message: run.lifecycleMessage || '',
    percent,
    totalSteps: total,
    pendingSteps: count('pending'),
    runningSteps: count('running'),
    waitingReviewSteps: count('waiting_review'),
    retryingSteps: count('retrying'),
    failedSteps: count('failed'),
    completedSteps: completed,
    cancelledSteps: count('cancelled'),
    currentStepId: run.currentStepId || null,
    activeStepIds: run.activeStepIds || [],
    completedStepIds: run.completedStepIds || [],
    startedAt: run.startedAt || null,
    updatedAt: run.updatedAt || null,
    runtimeRevision: run.runtimeRevision,
    progress: percent === null ? 0 : percent / 100,
    percentage: percent === null ? 0 : percent
  }
}

export const createWorkflowApi = (getApi: () => WorkflowApiDependencies) => ({
  async listWorkflowRuns(
    params: WorkflowRunQuery = {},
    options: { signal?: AbortSignal } = {}
  ): Promise<PageResponse<WorkflowRunSummary>> {
    const response = await agentosRequest.get<PageResponse<WorkflowRun>>('/runs', {
      params: {
        status: params.status || undefined,
        statuses: params.statuses || undefined,
        domain: params.domain,
        workflowId: params.workflowId,
        missionId: params.missionId,
        lifecyclePhase: params.lifecyclePhase || undefined,
        source: params.source,
        sources: params.sources,
        recordState: params.recordState,
        summary: params.summary,
        page: params.page,
        pageSize: params.pageSize
      },
      signal: options.signal
    })
    return {
      ...response.data,
      items: response.data.items.map(run => ({
        ...projectProgress(run),
        title: run.title,
        createdAt: run.createdAt
      }))
    }
  },

  async getWorkflowProgress(
    runId: string,
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkflowProgress> {
    return projectProgress(await getApi().getWorkflowRun(runId, options))
  },

  async getWorkflowRun(runId: string, options: { signal?: AbortSignal } = {}): Promise<WorkflowRun> {
    const response = await agentosRequest.get<WorkflowRun>(runPath(runId), {
      signal: options.signal
    })
    return response.data
  },

  async listMemoryEvents(
    runId: string,
    options: { signal?: AbortSignal } = {}
  ): Promise<RunMemoryEventsResponse> {
    const response = await agentosRequest.get<RunMemoryEventsResponse>(`${runPath(runId)}/memory-events`, {
      signal: options.signal
    })
    return response.data
  },

  async rerunWorkflowAsync(
    missionId: string,
    payload: WorkflowRerunRequest,
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkflowRun> {
    const response = await agentosRequest.post<WorkflowRun>(
      `/missions/${encodeURIComponent(missionId)}/runs`,
      payload,
      { signal: options.signal }
    )
    if (!response.data?.runId || response.data.missionId !== missionId) {
      throw new WorkflowApiContractError('重新运行响应缺少有效的同 Mission Run')
    }
    return response.data
  },

  async retryWorkflowStepAsync(
    runId: string,
    stepId: string,
    payload: SingleStepRetryRequest,
    options: { signal?: AbortSignal } = {}
  ): Promise<WorkflowRun> {
    const response = await agentosRequest.post<WorkflowRun>(
      `${runPath(runId)}/steps/${encodeURIComponent(stepId)}/retry`,
      payload,
      { signal: options.signal }
    )
    if (!response.data?.runId) {
      throw new WorkflowApiContractError('single-step retry response is missing a valid Run')
    }
    return response.data
  },

  async getWorkflowHistoryConfig(runId: string, options: { signal?: AbortSignal } = {}): Promise<WorkflowHistoryConfig> {
    // 后端把 pluginData 表达为 typed 关联行（WorkflowHistoryPluginEntry[]）；
    // 在此还原成既有重开流程消费的 Record 结构（扁平标量），restoreWorkbenchDraft、
    // hydratePluginData 与 clonePluginData 的读取全部保持不变。
    const response = await agentosRequest.get<{
      runId: string
      title?: string | null
      reviewMode?: string
      enabledPluginIds?: string[]
      input?: { pluginData?: Array<{ pluginId: string; entries?: WorkflowHistoryPluginEntry[] }> | null }
    }>(`${runPath(runId)}/history-config`, { signal: options.signal })
    const wire = response.data
    const config: WorkflowHistoryConfig = {
      runId: wire.runId,
      title: wire.title,
      reviewMode: wire.reviewMode,
      enabledPluginIds: wire.enabledPluginIds,
      input: { ...(wire.input || {}) }
    }
    const rows = wire.input?.pluginData
    if (config.input && Array.isArray(rows)) {
      const pluginData: Record<string, Record<string, unknown>> = {}
      for (const block of rows) {
        const entries: Record<string, unknown> = {}
        for (const entry of block.entries || []) {
          if (entry.text != null) entries[entry.name] = entry.text
          else if (entry.bool != null) entries[entry.name] = entry.bool
          else if (entry.number != null) entries[entry.name] = Number(entry.number)
        }
        pluginData[block.pluginId] = entries
      }
      config.input.pluginData = pluginData
    }
    return config
  },

  async listWorkflowCheckpoints(runId: string, options: { signal?: AbortSignal } = {}): Promise<PageResponse<Checkpoint> & { runId: string }> {
    const response = await agentosRequest.get<PageResponse<Checkpoint> & { runId: string }>(`${runPath(runId)}/checkpoints`, { signal: options.signal })
    return response.data
  },

  async getWorkflowTrace(runId: string, options: { signal?: AbortSignal; view?: 'workspace' } = {}): Promise<WorkflowTraceExport> {
    const response = await agentosRequest.get<WorkflowTraceExport>(`${runPath(runId)}/trace`, { signal: options.signal, params: { view: options.view } })
    return response.data
  },

  async exportWorkflowTraceMarkdown(runId: string): Promise<string> {
    const trace = await getApi().getWorkflowTrace(runId)
    return ['# AgentOS Trace', '', ...trace.events.map(event =>
      `- ${event.createdAt || ''} **${event.eventType}**${event.stepId ? ` · ${event.stepId}` : ''}`
    )].join('\n')
  },

  async listWorkflowReviews(runId: string, options: { signal?: AbortSignal } = {}): Promise<PageResponse<ReviewRecord> & { runId: string }> {
    const response = await agentosRequest.get<PageResponse<ReviewRecord> & { runId: string }>(`${runPath(runId)}/reviews`, { signal: options.signal })
    return response.data
  },

  async applyWorkflowReview(runId: string, payload: ReviewRequest, options: { signal?: AbortSignal } = {}): Promise<WorkflowRun> {
    const request = { ...payload, operationId: payload.operationId || crypto.randomUUID() }
    const response = await agentosRequest.post<WorkflowRun>(`${runPath(runId)}/reviews`, request, { signal: options.signal })
    return response.data
  },

  async cancelWorkflowRun(runId: string, options: { signal?: AbortSignal; expectedRuntimeRevision?: number } = {}): Promise<WorkflowRun> {
    const response = await agentosRequest.post<WorkflowRun>(`${runPath(runId)}/cancel`,
      options.expectedRuntimeRevision === undefined ? {} : { expectedRuntimeRevision: options.expectedRuntimeRevision }, { signal: options.signal })
    return response.data
  },

  async deleteWorkflowRun(runId: string, options: { signal?: AbortSignal } = {}): Promise<void> {
    await agentosRequest.delete(runPath(runId), { signal: options.signal })
  }
})
