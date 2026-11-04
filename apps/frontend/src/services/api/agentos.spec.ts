import { beforeEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, agentosRequest, WorkflowApiContractError } from './agentos'
import { decodeOutputContent, stepStatesFromRun, type OutputContentValue } from './agentos/api/acg'

// The output endpoint returns ContentValueQuery, not the reconstructed product object.
const outputValue = (value: unknown): OutputContentValue => {
  if (value === null) return { kind: 'null' }
  if (typeof value === 'string') return { kind: 'string', text: value }
  if (typeof value === 'number') return { kind: 'number', number: value }
  if (typeof value === 'boolean') return { kind: 'boolean', bool: value }
  if (Array.isArray(value)) return { kind: 'list', items: value.map(outputValue) }
  if (value && typeof value === 'object') return {
    kind: 'object', members: Object.entries(value).map(([name, item]) => ({ name, value: outputValue(item) }))
  }
  throw new Error('Invalid output fixture')
}

const run = {
  runId: 'run_1', missionId: 'mission_1', workflowId: 'legal.contract_review', domain: 'legal',
  status: 'completed' as const,
  outputRef: 'output:run_1:deliver',
  steps: [{
    stepId: 'deliver', name: 'Deliver', agentName: 'legal.drafter', status: 'completed' as const,
    outputRef: 'output:run_1:deliver', outputSummary: 'Contract review ready'
  }],
  completedStepIds: ['deliver'], activeStepIds: [],
  outputs: [{ stepId: "deliver", outputRef: 'output:run_1:deliver' }]
}

const executionTree = (nodes: Array<Record<string, unknown>> = [], lifecycles: Array<Record<string, unknown>> = []) => ({
  run: { runId: 'run_1', missionId: 'mission_1', status: 'succeeded', graphVersion: 2 },
  graph: { graphId: 'graph_1', graphVersion: 2, nodes: [], edges: [] },
  nodes, lineage: {}, lifecycles
})

describe('AgentOS v2 application API', () => {
  it('keeps prototype-shaped content keys as own product data', () => {
    const result = decodeOutputContent({ kind: 'object', members: [
      { name: '__proto__', value: outputValue({ publicValue: '正文' }) },
      { name: 'constructor', value: outputValue('正文构造字段') }
    ] })
    expect(Object.getPrototypeOf(result)).toBe(Object.prototype)
    expect(Object.prototype.hasOwnProperty.call(result, '__proto__')).toBe(true)
    expect(result.__proto__).toEqual({ publicValue: '正文' })
    expect(Object.prototype.hasOwnProperty.call(result, 'constructor')).toBe(true)
    expect(JSON.parse(JSON.stringify(result)).__proto__).toEqual({ publicValue: '正文' })
  })
  beforeEach(() => vi.restoreAllMocks())

  it('shows completed lightweight history rows as completed even with a stale execution phase', async () => {
    vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: {
      items: [{ ...run, lifecyclePhase: 'executing', steps: [], completedStepIds: [], outputs: [] }],
      total: 1, page: 1, pageSize: 20
    } } as never)
    const page = await agentosApi.listWorkflowRuns({ summary: true })
    expect(page.items[0]).toMatchObject({ status: 'completed', phase: 'completed', percent: 100, totalSteps: 0 })
  })

  it('preserves file bytes as FormData while ordinary requests still use JSON', async () => {
    const file = new File(['Upload integration check'], 'check.txt', { type: 'text/plain' })
    const originalAdapter = agentosRequest.defaults.adapter
    const requests: Array<{ data: unknown; contentType: unknown }> = []
    agentosRequest.defaults.adapter = async config => {
      requests.push({ data: config.data, contentType: config.headers.getContentType() })
      return { data: {}, status: 201, statusText: 'Created', headers: {}, config }
    }
    try {
      await agentosApi.uploadAttachment(file)
      await agentosApi.createMaterial('Context')
      expect(requests[0].data).toBeInstanceOf(FormData)
      expect((requests[0].data as FormData).get('file')).toBe(file)
      expect(requests[0].contentType).not.toBe('application/json')
      expect(requests[1].contentType).toBe('application/json')
      expect(JSON.parse(requests[1].data as string)).toEqual({ content: 'Context', mediaType: 'text/plain' })
    } finally {
      agentosRequest.defaults.adapter = originalAdapter
    }
  })

  it('decodes persisted intermediate output at the shared API boundary', async () => {
    const signal = new AbortController().signal
    const content = {
      summary: '活动整体方案',
      agenda: [{ title: '交流讨论', minutes: 30, required: true, note: null }],
      kind: 'user-defined'
    }
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: {
      runId: 'run/1', outputRef: 'output:design/1', content: outputValue(content)
    } } as never)

    await expect(agentosApi.getRunOutput('run/1', 'output:design/1', { signal })).resolves.toEqual({
      runId: 'run/1', outputRef: 'output:design/1', content
    })
    expect(get).toHaveBeenCalledWith('/runs/run%2F1/outputs/output%3Adesign%2F1', { signal })
  })

  it('starts a run through the v2 gateway and preserves clientRequestId', async () => {
    const signal = new AbortController().signal
    const post = vi.spyOn(agentosRequest, 'post').mockResolvedValue({ data: run } as never)
    await expect(agentosApi.startWorkflowAsync({
      title: 'Contract review', domain: 'legal', intent: 'contract_review', clientRequestId: 'request_1'
    }, { signal })).resolves.toEqual(run)
    expect(post).toHaveBeenCalledWith('/missions', expect.objectContaining({ clientRequestId: 'request_1' }), { signal })
  })

  it('rejects a successful-looking create response without run identity', async () => {
    vi.spyOn(agentosRequest, 'post').mockResolvedValue({ data: { taskId: 'task_1' } } as never)
    await expect(agentosApi.startWorkflowAsync({
      title: 'Contract review', domain: 'legal', intent: 'contract_review', clientRequestId: 'request_1'
    })).rejects.toBeInstanceOf(WorkflowApiContractError)
  })

  it('creates a rerun under the existing Mission identity', async () => {
    const signal = new AbortController().signal
    const rerun = { ...run, runId: 'run_2', missionId: 'mission/1' }
    const post = vi.spyOn(agentosRequest, 'post').mockResolvedValue({ data: rerun } as never)

    await expect(agentosApi.rerunWorkflowAsync('mission/1', {
      workflowId: 'legal.contract_review',
      clientRequestId: 'request_2',
      sourceRunId: 'run_1',
      rerunReason: 'current_configuration'
    }, { signal })).resolves.toEqual(rerun)

    expect(post).toHaveBeenCalledWith(
      '/missions/mission%2F1/runs',
      expect.objectContaining({ sourceRunId: 'run_1', rerunReason: 'current_configuration' }),
      { signal }
    )
  })

  it('requests a controlled retry for one failed step', async () => {
    const signal = new AbortController().signal
    const retry = { ...run, runId: 'run_retry', status: 'running' as const }
    const post = vi.spyOn(agentosRequest, 'post').mockResolvedValue({ data: retry } as never)

    await expect(agentosApi.retryWorkflowStepAsync('run/1', 'final/node', {
      clientRequestId: 'request_retry',
      reason: 'retry final synthesis',
      expectedRuntimeRevision: 7
    }, { signal })).resolves.toEqual(retry)

    expect(post).toHaveBeenCalledWith(
      '/runs/run%2F1/steps/final%2Fnode/retry',
      expect.objectContaining({ clientRequestId: 'request_retry', expectedRuntimeRevision: 7 }),
      { signal }
    )
  })

  it('derives progress only from the reference-first run projection', async () => {
    const signal = new AbortController().signal
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: run } as never)
    const progress = await agentosApi.getWorkflowProgress('run/1', { signal })
    expect(progress.percent).toBe(100)
    expect(progress.completedSteps).toBe(1)
    expect(get).toHaveBeenCalledWith('/runs/run%2F1', { signal })
  })

  it('loads the protected workbench configuration for a historical Run', async () => {
    const signal = new AbortController().signal
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({
      data: { runId: 'run/1', title: '历史任务', input: { taskGoal: '恢复目标' } }
    } as never)

    await expect(agentosApi.getWorkflowHistoryConfig('run/1', { signal })).resolves.toMatchObject({
      title: '历史任务', input: { taskGoal: '恢复目标' }
    })
    expect(get).toHaveBeenCalledWith('/runs/run%2F1/history-config', { signal })
  })

  it('preserves task titles in run history summaries', async () => {
    vi.spyOn(agentosRequest, 'get').mockResolvedValue({
      data: { items: [{ ...run, title: 'IC-200智能装配生产线立项实施方案' }], total: 1, page: 1, pageSize: 20 }
    } as never)

    const result = await agentosApi.listWorkflowRuns()

    expect(result.items[0].title).toBe('IC-200智能装配生产线立项实施方案')
  })

  it('forwards the complete run history filter contract', async () => {
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({
      data: { items: [], total: 0, page: 2, pageSize: 50 }
    } as never)

    await agentosApi.listWorkflowRuns({
      statuses: 'running,waiting_review', domain: 'legal', workflowId: 'workflow_1',
      missionId: 'mission_1', lifecyclePhase: 'review', source: 'acg', sources: 'acg,chat',
      summary: true, page: 2, pageSize: 50
    })

    expect(get).toHaveBeenCalledWith('/runs', expect.objectContaining({
      params: expect.objectContaining({
        statuses: 'running,waiting_review', domain: 'legal', workflowId: 'workflow_1',
        missionId: 'mission_1', lifecyclePhase: 'review', source: 'acg', sources: 'acg,chat',
        summary: true, page: 2, pageSize: 50
      })
    }))
  })

  it('dereferences owned outputs and projects real artifacts', async () => {
    const artifact = {
      artifactId: 'artifact_1', type: 'run_deliverable', artifactKey: 'final', artifactType: 'run_deliverable', title: 'Final result',
      mediaType: 'text/markdown', content: '# Final', structuredData: { riskCount: 2 }
    }
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: run } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_1', graphVersion: 2, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: { integrityStatus: 'valid', events: [] } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree() } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ final_answer: '# Final', artifact }) } } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.deliverables[0].output.final_answer).toBe('# Final')
    expect(result.finalArtifacts).toEqual([{ ...artifact, stepId: 'deliver' }])
    expect(result.stepStates[0].resourceUse).toBeNull()
    expect(get).toHaveBeenLastCalledWith('/runs/run_1/outputs/output%3Arun_1%3Adeliver', { signal: undefined })
  })

  it('reuses an already loaded Run when projecting the ACG view', async () => {
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: { graphId: 'graph_1', graphVersion: 2, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: { integrityStatus: 'valid', events: [] } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree() } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ final_answer: '# Final' }) } } as never)

    await agentosApi.getAcgView('run_1', { run })

    expect(get).not.toHaveBeenCalledWith('/runs/run_1', expect.anything())
    expect(get).toHaveBeenCalledTimes(5)
  })

  it('does not probe removed legacy outputs when a run has no committed output references', async () => {
    const pendingRun = {
      ...run,
      status: 'running' as const,
      steps: [{ ...run.steps[0], outputRef: undefined }],
      outputs: []
    }
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: pendingRun } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_1', graphVersion: 1, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: { integrityStatus: 'valid', events: [] } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree() } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.stepOutputs).toEqual([])
    expect(result.finalReport).toBeNull()
    expect(get).toHaveBeenCalledTimes(5)
    expect(get).not.toHaveBeenCalledWith(expect.stringContaining('legacy-outputs'), expect.anything())
  })

  it('keeps completed node outputs when auxiliary projections fail and withholds final delivery while running', async () => {
    const liveRun = {
      ...run,
      status: 'running' as const,
      steps: [
        { ...run.steps[0], status: 'completed' as const },
        { stepId: 'research', name: 'Research', agentName: 'researcher', status: 'running' as const }
      ],
      completedStepIds: ['deliver'],
      activeStepIds: ['research'],
      outputs: [{ stepId: "deliver", outputRef: 'output:run_1:deliver' }]
    }
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: liveRun } as never)
      .mockRejectedValueOnce(new Error('graph unavailable'))
      .mockRejectedValueOnce(new Error('provenance unavailable'))
      .mockRejectedValueOnce(new Error('trace unavailable'))
      .mockRejectedValueOnce(Object.assign(new Error('identity pending'), {
        isAxiosError: true,
        response: { status: 404 }
      }))
      .mockResolvedValueOnce({ data: { content: outputValue({ answer: '节点已完成的完整答案' }) } } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.stepOutputs).toEqual([expect.objectContaining({
      stepId: 'deliver', outputRef: 'output:run_1:deliver', output: { answer: '节点已完成的完整答案' }
    })])
    expect(result.stepStates).toEqual([
      expect.objectContaining({ stepId: 'deliver', status: 'completed', name: 'Deliver' }),
      expect.objectContaining({ stepId: 'research', status: 'running', name: 'Research' })
    ])
    expect(result.finalReport).toBeNull()
    expect(result.finalArtifacts).toEqual([])
    expect(result.identityProjection?.status).toBe('pending')
    expect(get).toHaveBeenCalledTimes(6)
  })

  it('orders multiple node outputs by run steps and does not infer a final report from them', async () => {
    const completedRun = {
      ...run,
      outputRef: undefined,
      steps: [
        { stepId: 'first', name: 'First', agentName: 'runner', status: 'completed' as const, outputRef: 'output:run_1:first' },
        { stepId: 'second', name: 'Second', agentName: 'runner', status: 'completed' as const, outputRef: 'output:run_1:second' }
      ],
      completedStepIds: ['first', 'second'],
      activeStepIds: [],
      outputs: [{ stepId: "second", outputRef: 'output:run_1:second' }, { stepId: "first", outputRef: 'output:run_1:first' }]
    }
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: completedRun } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_1', graphVersion: 2, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: { integrityStatus: 'valid', events: [] } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree() } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ answer: 'first' }) } } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ answer: 'second' }) } } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.stepOutputs.map(item => item.stepId)).toEqual(['first', 'second'])
    expect(result.finalReport).toBeNull()
    expect(result.finalArtifacts).toEqual([])
    expect(get).toHaveBeenCalledTimes(7)
  })

  it('does not infer a final report from one completed node without run outputRef', async () => {
    const completedRun = {
      ...run,
      outputRef: undefined,
      steps: [{ ...run.steps[0], outputRef: 'output:run_1:deliver' }],
      outputs: [{ stepId: "deliver", outputRef: 'output:run_1:deliver' }]
    }
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: completedRun } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_1', graphVersion: 2, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: { integrityStatus: 'valid', events: [] } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree() } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ answer: 'only intermediate output' }) } } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.stepOutputs).toHaveLength(1)
    expect(result.finalReport).toBeNull()
    expect(result.finalArtifacts).toEqual([])
    expect(get).toHaveBeenCalledTimes(6)
  })

  it('projects low-entropy metrics and lineage from legacy provenance snapshots', async () => {
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: run } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_legacy', graphVersion: 1, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: {
        schemaVersion: 2,
        integrityStatus: 'valid',
        productions: [{ eventId: 'prod_000001', producerStepId: 'research', fieldNames: ['findings'] }],
        consumptions: [{ eventId: 'cons_000002', consumerStepId: 'deliver', producerStepIds: ['research'], tokensAvailable: 100, tokensDelivered: 40, savingRatio: 0.6 }],
        interactions: [{ eventId: 'int_000003', interactionId: 'int_000003', consumerStepId: 'deliver', producerStepIds: ['research'], tokensAvailable: 100, tokensDelivered: 40, savingRatio: 0.6 }]
      } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree() } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ final_answer: '# Final' }) } } as never)

    const result = await agentosApi.getAcgView('run_legacy_provenance')

    expect(result.provenance.productions).toHaveLength(1)
    expect(result.provenance.consumptions[0].producerStepIds).toEqual(['research'])
    expect(result.interactions).toHaveLength(1)
    expect(result.lowEntropyMetrics).toMatchObject({
      effectiveSavingRatio: 0.6,
      tokensAvailable: 100,
      tokensDelivered: 40,
      tokensSaved: 60,
      interactionCount: 1,
      integrityStatus: 'valid'
    })
  })

  it('derives low-entropy metrics from delivery envelopes when no interaction records exist', async () => {
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: run } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_native', graphVersion: 1, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: {
        integrityStatus: 'valid',
        events: [
          { eventType: 'data_produced', payload: { eventId: 'prod_000001', producerStepId: 'ctrl_start', fieldNames: ['intent'] } },
          { eventType: 'data_consumed', payload: { eventId: 'cons_000002', consumerStepId: 'native_general_agent', producerStepIds: ['ctrl_start'], tokensAvailable: 14702, tokensDelivered: 11352, savingRatio: 0.228 } }
        ]
      } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree() } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ final_answer: '# Final' }) } } as never)

    const result = await agentosApi.getAcgView('run_native_delivery')

    expect(result.provenance.consumptions).toHaveLength(1)
    expect(result.lowEntropyMetrics).toMatchObject({
      averageSavingRatio: 0.228,
      tokensAvailable: 14702,
      tokensDelivered: 11352,
      tokensSaved: 3350,
      interactionCount: 1,
      integrityStatus: 'valid'
    })
    expect(result.lowEntropyMetrics.effectiveSavingRatio).toBeCloseTo(0.2279, 3)
  })

  it('merges Identity nodes and orders loop executions by attempt and loop path', async () => {
    const identityNode = {
      task: { nodeId: 'semantic_task_1', taskId: 'task_1', missionId: 'mission_1', title: 'Deliver', objective: 'Ship result', constraints: [], status: 'running', metadata: {} },
      acgNodeId: 'deliver',
      attempts: [{
        attempt: { attemptId: 'attempt_1', runId: 'run_1', nodeId: 'semantic_task_1', status: 'running', attemptNumber: 1 },
        resourceUse: { ignoredInternalKey: 'binding_1', attemptId: 'attempt_1', acgNodeId: 'deliver', resourceId: 'resource_1', agentId: 'agent_1', modelId: 'model_1', metadata: {} },
        executions: [{ stepExecutionId: 'step_execution_1', runId: 'run_1', nodeId: 'semantic_task_1', attemptId: 'attempt_1', status: 'running' }]
      }]
    }
    const records = [2, 1].map(iteration => ({
      operationId: `operation_${iteration}`, executionInstanceId: `instance_${iteration}`, runId: 'run_1', stepId: 'deliver',
      attemptId: 'attempt_1', phase: iteration === 2 ? 'committed' : 'audited', sequence: iteration
    }))
    vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: run } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_1', graphVersion: 2, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: { integrityStatus: 'valid', events: [] } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockResolvedValueOnce({ data: executionTree([identityNode], records) } as never)
      .mockResolvedValueOnce({ data: { content: outputValue({ final_answer: '# Final' }) } } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.identityProjection?.status).toBe('available')
    expect(result.stepStates[0].task?.nodeId).toBe('semantic_task_1')
    expect(result.stepStates[0].resourceUse).toMatchObject({ resourceId: 'resource_1' })
    expect(result.stepStates[0].stepExecutions?.[0].stepExecutionId).toBe('step_execution_1')
    expect(result.stepStates[0].nodeExecutions?.map(item => item.sequence)).toEqual([1, 2])
    expect(result.stepStates[0].status).toBe('completed')
  })

  it('keeps the 执行运行时 view available while an Identity projection is pending', async () => {
    vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: run } as never)
      .mockResolvedValueOnce({ data: { graphId: 'graph_1', graphVersion: 2, nodes: [], edges: [] } } as never)
      .mockResolvedValueOnce({ data: { integrityStatus: 'valid', events: [] } } as never)
      .mockResolvedValueOnce({ data: { events: [] } } as never)
      .mockRejectedValueOnce({ isAxiosError: true, response: { status: 404 } })
      .mockResolvedValueOnce({ data: { content: outputValue({ final_answer: '# Final' }) } } as never)

    const result = await agentosApi.getAcgView('run_1')

    expect(result.identityProjection).toMatchObject({ status: 'pending' })
    expect(result.executionTree).toBeNull()
    expect(result.stepStates[0].resourceUse).toBeNull()
  })

  it('forwards review concurrency fields and does not swallow conflicts', async () => {
    const conflict = { response: { status: 409 } }
    const post = vi.spyOn(agentosRequest, 'post').mockRejectedValue(conflict)
    const payload = {
      stepId: 'human_review', decision: 'approved' as const, operationId: 'operation_1',
      expectedRunUpdatedAt: '2026-07-22T00:00:00Z', expectedStepStatus: 'waiting_review' as const
    }
    await expect(agentosApi.applyWorkflowReview('run_1', payload)).rejects.toBe(conflict)
    expect(post).toHaveBeenCalledWith('/runs/run_1/reviews', payload, { signal: undefined })
  })

  it('loads one Mission Workspace projection with an optional Run selection', async () => {
    const signal = new AbortController().signal
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({
      data: { mission: { missionId: 'mission_1' }, entries: [], runs: [], graphNodes: [], diagnostics: [] }
    } as never)

    await agentosApi.getMissionWorkspace('mission/1', { runId: 'run/2', signal })

    expect(get).toHaveBeenCalledWith('/missions/mission%2F1/workspace', {
      params: { runId: 'run/2' }, signal
    })
  })

  it('does not request Artifact content as part of Workspace projection loading', async () => {
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({
      data: { mission: { missionId: 'mission_1' }, entries: [{ entryId: 'task:one:primary', kind: 'artifact' }], runs: [], graphNodes: [], diagnostics: [] }
    } as never)

    await agentosApi.getMissionWorkspace('mission_1')

    expect(get).toHaveBeenCalledTimes(1)
    expect(get).not.toHaveBeenCalledWith(expect.stringContaining('/artifacts/'), expect.anything())
  })

  it('reads sealed Artifact content through the streaming assembly endpoint', async () => {
    const get = vi.spyOn(agentosRequest, 'get')
      .mockResolvedValueOnce({ data: new Blob(['first second'], { type: 'text/plain' }) } as never)

    await expect(agentosApi.getArtifactContent('run_1', 'manifest_1')).resolves.toMatchObject({
      manifestId: 'manifest_1', mediaType: 'text/plain', byteLength: 12, content: 'first second'
    })
    expect(get).toHaveBeenCalledWith('/runs/run_1/artifacts/manifest_1/download', expect.objectContaining({
      responseType: 'blob'
    }))
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('lists one workspace directory without requesting a recursive tree scan', async () => {
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({
      data: { workspaceRoot: 'C:/work/project', path: 'apps', entries: [] }
    } as never)

    await agentosApi.listWorkspaceFiles('mission/1', 'apps/ui')

    expect(get).toHaveBeenCalledWith('/missions/mission%2F1/workspace/files', {
      params: { path: 'apps/ui', maxEntries: 1000 }, signal: undefined
    })
  })

  it('uses the existing Artifact download endpoint rather than a second content store', async () => {
    const signal = new AbortController().signal
    const get = vi.spyOn(agentosRequest, 'get').mockResolvedValue({ data: new Blob(['body']) } as never)
    await agentosApi.downloadArtifact('run/1', 'manifest/1', { signal })
    expect(get).toHaveBeenCalledWith('/runs/run%2F1/artifacts/manifest%2F1/download', {
      responseType: 'blob', signal
    })
  })

  it('projects persisted run steps into base graph node states', () => {
    const states = stepStatesFromRun({ steps: [
      { stepId: 'n1', name: '时间轴转写', agentName: 'editor.a', status: 'completed', attempt: 1, retryCount: 0, outputSummary: 'ok' },
      { stepId: 'n2', name: '一致性检查', agentName: 'checker.b', status: 'waiting_review', attempt: 2, retryCount: 1 }
    ] })
    expect(states).toHaveLength(2)
    expect(states[0]).toMatchObject({ stepId: 'n1', status: 'completed', name: '时间轴转写', agentName: 'editor.a', attempt: 1, outputSummary: 'ok' })
    expect(states[1]).toMatchObject({ stepId: 'n2', status: 'waiting_review', retryCount: 1 })
  })

  it('enriches execution-tree matched nodes and falls back to base for unmatched ones', () => {
    const identityNode = {
      task: { taskId: 'task_2', missionId: 'mission_1', title: '一致性检查', objective: '核对素材', constraints: [], status: 'running', metadata: {} },
      acgNodeId: 'n2',
      attempts: [{
        attempt: { attemptId: 'att_2', runId: 'run_1', taskId: 'task_2', status: 'running', attemptNumber: 2 },
        resourceUse: { resourceId: 'res_1', agentId: 'checker.b', modelId: 'glm-4' },
        executions: [{ stepExecutionId: 'se_1', runId: 'run_1', taskId: 'task_2', attemptId: 'att_2', status: 'running' }]
      }]
    }
    const lifecycles = [
      { stepId: 'n2', attemptId: 'att_2', phase: 'waiting_review', sequence: 3 },
      { stepId: 'n2', attemptId: 'att_1', phase: 'executed', sequence: 1 }
    ]
    const [first, second] = stepStatesFromRun({ steps: [
      { stepId: 'n1', name: '时间轴转写', agentName: 'editor.a', status: 'completed' },
      { stepId: 'n2', name: '一致性检查', agentName: 'checker.b', status: 'waiting_review' }
    ] }, executionTree([identityNode], lifecycles), lifecycles)

    expect(first).toMatchObject({ stepId: 'n1', status: 'completed' })
    expect(second).toMatchObject({
      stepId: 'n2',
      status: 'waiting_review',
      attempt: 2,
      retryCount: 0,
      acgNodeId: 'n2',
      task: { taskId: 'task_2' },
      resourceUse: { resourceId: 'res_1' }
    })
    expect(second.nodeExecutions?.map(item => item.phase)).toEqual(['executed', 'waiting_review'])
  })

  it('maps in-flight identity phases to running so a refreshed workspace graph keeps 运行中', () => {
    const identityNode = {
      task: { taskId: 'task_1', missionId: 'mission_1', title: '转写', objective: '', constraints: [], status: 'running', metadata: {} },
      acgNodeId: 'n1',
      attempts: [{
        attempt: { attemptId: 'att_1', runId: 'run_1', taskId: 'task_1', status: 'running', attemptNumber: 1 },
        resourceUse: null,
        executions: []
      }]
    }
    const lifecycles = [{ stepId: 'n1', attemptId: 'att_1', phase: 'executed', sequence: 1 }]
    const [state] = stepStatesFromRun({ steps: [
      { stepId: 'n1', name: '时间轴转写', agentName: 'editor.a', status: 'running' }
    ] }, executionTree([identityNode], lifecycles), lifecycles)
    expect(state).toMatchObject({ stepId: 'n1', status: 'running' })
  })
})
