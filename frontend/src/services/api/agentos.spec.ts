import { beforeEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, agentosRequest, WorkflowApiContractError } from './agentos'

describe('AgentOS async workflow API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('loads the installed plugin projection without executable manifest details', async () => {
    const plugins = [{
      pluginId: 'kinlin.legal', version: '0.1.0', displayName: '法律能力包',
      description: '法律能力', available: true, capabilityCount: 7,
      agentCount: 14, workflowCount: 2, uiExtensionId: 'kinlin.legal'
    }]
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: plugins } as never)

    await expect(agentosApi.listInstalledPlugins()).resolves.toEqual(plugins)
    expect(get).toHaveBeenCalledWith('/core/plugins')
  })

  it('starts through the Java gateway with clientRequestId and AbortSignal', async () => {
    const signal = new AbortController().signal
    const response = {
      accepted: true,
      task: { taskId: 'task_1', status: 'pending' },
      run: { runId: 'run_1', status: 'pending' }
    }
    const post = vi.spyOn(agentosRequest, 'post').mockResolvedValue({ data: response } as never)

    await expect(agentosApi.startWorkflowAsync({
      title: '合同审查',
      domain: 'legal',
      intent: 'contract_review',
      clientRequestId: 'request_1'
    }, { signal })).resolves.toEqual(response)

    expect(post).toHaveBeenCalledWith('/core/workflows/start-async', expect.objectContaining({
      clientRequestId: 'request_1'
    }), { signal })
  })

  it('rejects a successful-looking response that has no runId', async () => {
    vi.spyOn(agentosRequest, 'post').mockResolvedValue({
      data: { accepted: true, task: { taskId: 'task_1', status: 'pending' }, run: { status: 'pending' } }
    } as never)

    await expect(agentosApi.startWorkflowAsync({
      title: '合同审查', domain: 'legal', intent: 'review', clientRequestId: 'request_1'
    })).rejects.toBeInstanceOf(WorkflowApiContractError)
  })

  it.each([
    { accepted: false, task: { taskId: 'task_1', status: 'pending' }, run: { runId: 'run_1', status: 'pending' } },
    { accepted: true, task: { taskId: '', status: 'pending' }, run: { runId: 'run_1', status: 'pending' } }
  ])('rejects an incomplete accepted/task contract', async (data) => {
    vi.spyOn(agentosRequest, 'post').mockResolvedValue({ data } as never)
    await expect(agentosApi.startWorkflowAsync({
      title: '合同审查', domain: 'legal', intent: 'review', clientRequestId: 'request_1'
    })).rejects.toBeInstanceOf(WorkflowApiContractError)
  })

  it('queries progress through Java, preserves null percent, and forwards cancellation', async () => {
    const signal = new AbortController().signal
    const payload = {
      runId: 'run/1', phase: 'planning', percent: null, graphVersion: 2,
      dynamicStepCount: 2, bindingSwitchCount: 1,
      skippedByConditionCount: 2, conditionalDecisionCount: 1
    }
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: payload } as never)

    const result = await agentosApi.getWorkflowProgress('run/1', { signal })

    expect(result.percent).toBeNull()
    expect(result.graphVersion).toBe(2)
    expect(result.dynamicStepCount).toBe(2)
    expect(result.bindingSwitchCount).toBe(1)
    expect(result.skippedByConditionCount).toBe(2)
    expect(result.conditionalDecisionCount).toBe(1)
    expect(get).toHaveBeenCalledWith('/core/workflows/runs/run%2F1/progress', { signal })
  })

  it.each([409, 404, 503])('does not swallow HTTP %s', async (status) => {
    const error = { response: { status } }
    vi.spyOn(agentosRequest, 'get').mockRejectedValue(error)
    await expect(agentosApi.getWorkflowProgress('run_1')).rejects.toBe(error)
  })

  it('queries a bounded summary list through Java with one AbortSignal', async () => {
    const signal = new AbortController().signal
    const payload = { items: [{ runId: 'run_1', phase: 'planning', percent: null }], total: 1 }
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: payload } as never)

    const result = await agentosApi.listWorkflowRuns({
      statuses: 'running,waiting_review', page: 1, pageSize: 50
    }, { signal })

    expect(result.items[0].percent).toBeNull()
    expect(get).toHaveBeenCalledWith('/core/workflows/runs', {
      params: { summary: true, statuses: 'running,waiting_review', page: 1, pageSize: 50 },
      signal
    })
  })

  it('normalizes final artifacts separately from legacy step deliverables', async () => {
    const legacyStep = {
      stepId: 'analysis', name: 'Analysis', status: 'completed', output: { analysis: 'done' }
    }
    const artifact = {
      artifactId: 'artifact_1', type: 'report', title: 'Final result',
      mediaType: 'text/markdown', content: '# Final', structuredData: {}
    }
    vi.spyOn(agentosRequest, 'get').mockResolvedValue({
      data: {
        runId: 'run_1', status: 'completed', engine: 'acg', acgBlueprint: null,
        completedStepIds: ['analysis'], activeStepIds: [], stepStates: [],
        provenance: { productions: [], consumptions: [], interactions: [] },
        interactions: [], contractViolations: [], recoveryTrace: [], scheduleTrace: [],
        deliverables: [legacyStep], finalArtifacts: [artifact], finalReport: '# Final',
        lowEntropyMetrics: {}
      }
    } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.deliverables).toEqual([legacyStep])
    expect(result.stepOutputs).toEqual([legacyStep])
    expect(result.finalArtifacts).toEqual([artifact])
  })

  it('forwards review concurrency fields and preserves 409', async () => {
    const conflict = { response: { status: 409 } }
    const post = vi.spyOn(agentosRequest, 'post').mockRejectedValue(conflict)
    const signal = new AbortController().signal
    const payload = {
      stepId: 'human_review', decision: 'approved' as const, operationId: 'operation_1',
      expectedRunUpdatedAt: '2026-07-22T00:00:00Z', expectedStepStatus: 'waiting_review' as const
    }

    await expect(agentosApi.applyWorkflowReview('run_1', payload, { signal })).rejects.toBe(conflict)
    expect(post).toHaveBeenCalledWith('/core/workflows/runs/run_1/reviews', payload, { signal })
  })
})
