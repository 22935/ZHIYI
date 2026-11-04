import { agentosRequest } from '../client'
import type { GraphProjection, AcgDeliverable, AcgFinalArtifact, AcgStepState, AcgView, NodeExecutionPhase, ProvenanceConsumption, ProvenanceProduction, RunExecutionNode, RunExecutionTree, RuntimeInteraction, StepStatus, WorkflowRun, WorkflowTraceExport } from '../types'
import { runPath } from '../paths'
import axios from 'axios'
import { isRunDeliverableEntry } from '@/workbench/runtime/deliverableIdentity'
import type { AcgApiDependencies } from '../dependencies'

/**
 * 输出正文专用 wire 合同（ContentValueQuery grammar）的解码入口：后端把用户产物
 * 正文表达为 kind + 标量/列表/成员行的自引用结构，这里还原成既有消费结构的普通
 * JSON 对象，字段名、嵌套、数组顺序、布尔、null 与数字全部保持不变。
 */
export interface OutputContentValue {
  kind: 'string' | 'boolean' | 'number' | 'list' | 'object' | 'null'
  text?: string
  bool?: boolean
  number?: number
  items?: OutputContentValue[]
  members?: Array<{ name: string; value: OutputContentValue }>
}

export const decodeOutputContent = (value: OutputContentValue | null | undefined): any => {
  if (!value || value.kind === 'null') return null
  if (value.kind === 'object') {
    const result: Record<string, any> = {}
    for (const member of value.members || []) {
      Object.defineProperty(result, member.name, {
        value: decodeOutputContent(member.value), enumerable: true, writable: true, configurable: true
      })
    }
    return result
  }
  if (value.kind === 'list') return (value.items || []).map(item => decodeOutputContent(item))
  if (value.kind === 'boolean') return value.bool === true
  if (value.kind === 'number') return value.number == null ? null : Number(value.number)
  return value.text ?? ''
}

const outputMarkdown = (content: Record<string, any>): string | null => {
  for (const key of ['final_answer', 'report_markdown', 'report', 'final_report', 'content']) {
    const value = content[key]
    if (typeof value === 'string' && value.trim()) return value
  }
  return null
}

const provenanceProjection = (raw: {
  schemaVersion?: number
  integrityStatus?: string
  events?: Array<Record<string, any>>
  productions?: ProvenanceProduction[]
  consumptions?: ProvenanceConsumption[]
  interactions?: RuntimeInteraction[]
}) => {
  const events = Array.isArray(raw.events) ? raw.events : []
  const payloads = events.map(event => ({ eventType: String(event.eventType || ''), ...(event.payload || {}) }))
  const productions = events.length
    ? payloads.filter(item => item.producerStepId && !item.consumerStepId) as unknown as ProvenanceProduction[]
    : (Array.isArray(raw.productions) ? raw.productions : [])
  const consumptions = events.length
    ? payloads.filter(item => item.consumerStepId && !item.interactionId) as unknown as ProvenanceConsumption[]
    : (Array.isArray(raw.consumptions) ? raw.consumptions : [])
  const interactions = events.length
    ? payloads.filter(item => item.interactionId) as unknown as RuntimeInteraction[]
    : (Array.isArray(raw.interactions) ? raw.interactions : [])
  return { schemaVersion: raw.schemaVersion, integrityStatus: raw.integrityStatus, productions, consumptions, interactions }
}

const identityStepStatus = (phase: NodeExecutionPhase): StepStatus => ({
  prepared: 'running',
  executed: 'running',
  audited: 'running',
  committed: 'completed',
  waiting_review: 'waiting_review',
  failed: 'failed',
  cancelled: 'cancelled'
}[phase] as StepStatus)

const projectIdentityStepState = (
  base: AcgStepState,
  identityNode: RunExecutionNode | undefined,
  lifecycles: import('../types/identity').NodeLifecycleQuery[]
): AcgStepState => {
  if (!identityNode) return base
  const attempts = [...identityNode.attempts].sort((left, right) =>
    left.attempt.attemptNumber - right.attempt.attemptNumber
  )
  const attemptNumberById = new Map(attempts.map(item => [item.attempt.attemptId, item.attempt.attemptNumber]))
  const nodeIds = new Set([base.stepId, identityNode.task.taskId, identityNode.acgNodeId].filter(Boolean))
  const nodeExecutions = lifecycles
    .filter(item => nodeIds.has(item.stepId))
    .sort((left, right) => {
      const attemptDifference = (attemptNumberById.get(left.attemptId) || 0) - (attemptNumberById.get(right.attemptId) || 0)
      return attemptDifference || left.sequence - right.sequence
    })
  const latestAttempt = attempts[attempts.length - 1]
  const latestExecution = nodeExecutions[nodeExecutions.length - 1]
  const stepExecutions = attempts.flatMap(item => item.executions || [])
  return {
    ...base,
    status: latestExecution ? identityStepStatus(latestExecution.phase) : base.status,
    attempt: latestAttempt?.attempt.attemptNumber ?? base.attempt,
    retryCount: Math.max(0, attempts.length - 1),
    resourceUse: latestAttempt?.resourceUse || base.resourceUse,
    attempts: attempts.map(item => ({
      attemptId: item.attempt.attemptId,
      attemptNumber: item.attempt.attemptNumber,
      agentName: item.resourceUse?.agentId,
      modelName: item.resourceUse?.modelId,
      status: item.attempt.status === 'succeeded' ? 'completed' : item.attempt.status as StepStatus,
      startedAt: item.attempt.startedAt || undefined,
      endedAt: item.attempt.finishedAt,
      errorSummary: item.attempt.failureReason
    })),
    task: identityNode.task,
    acgNodeId: identityNode.acgNodeId || base.stepId,
    identityAttempts: attempts,
    stepExecutions,
    nodeExecutions,
    errorSummary: latestExecution?.failureCode || latestAttempt?.attempt.failureReason || base.errorSummary
  }
}

/**
 * Run 持久步骤 → 图节点状态的唯一映射：getAcgView 与 workspace 图挂载点
 * （GraphEditor/RunProgressEditor 经 runtimeObservation）共用，保证执行树
 * 命中时的状态、Attempt 与生命周期增强口径一致。
 */
export const stepStatesFromRun = (
  run: Pick<WorkflowRun, 'steps'>,
  executionTree?: RunExecutionTree | null,
  lifecycles?: import('../types/identity').NodeLifecycleQuery[]
): AcgStepState[] => {
  const identityNodesByAcgId = new Map<string, RunExecutionNode>(
    (executionTree?.nodes || []).filter(item => item.acgNodeId).map(item => [item.acgNodeId as string, item] as const)
  )
  return run.steps.map(step => projectIdentityStepState({
    stepId: step.stepId,
    status: step.status,
    name: step.name,
    agentName: step.agentName,
    attempt: step.attempt || 0,
    retryCount: step.retryCount || 0,
    resourceUse: null,
    outputSummary: step.outputSummary
  }, identityNodesByAcgId.get(step.stepId), lifecycles || executionTree?.lifecycles || []))
}

export const createAcgApi = (getApi: () => AcgApiDependencies) => ({
  async getAcgView(runId: string, options: { signal?: AbortSignal; run?: WorkflowRun | Promise<WorkflowRun> } = {}): Promise<AcgView> {
    const coreRequests = [
      options.run || getApi().getWorkflowRun(runId, options),
      agentosRequest.get<any>(`${runPath(runId)}/graph`, { signal: options.signal }),
      agentosRequest.get<any>(`${runPath(runId)}/provenance`, { signal: options.signal }),
      getApi().getWorkflowTrace(runId, options)
    ] as const
    const identityRequest = getApi().getExecutionTree(runId, options)
      .then(executionTree => ({ executionTree, projection: { status: 'available' as const } }))
      .catch((error: unknown) => {
        if (axios.isCancel(error)) throw error
        const status = axios.isAxiosError(error) ? error.response?.status : undefined
        return {
          executionTree: null,
          projection: {
            status: status === 404 ? 'pending' as const : 'unavailable' as const,
            message: status === 404 ? 'Identity 投影同步中' : 'Identity 投影暂时不可用'
          }
        }
      })
    // Run 是主投影，图/血缘/Trace/Identity/输出都是可降级的辅助投影。
    // 某一路暂时失败时仍返回其它已取得的增量数据，避免运行中的节点答案消失。
    const coreResults = await Promise.allSettled(coreRequests)
    const runResult = coreResults[0]
    if (runResult.status === 'rejected') throw runResult.reason
    const run = runResult.value
    const graphResult = coreResults[1]
    const provenanceResult = coreResults[2]
    const traceResult = coreResults[3]
    for (const result of [graphResult, provenanceResult, traceResult]) {
      if (result.status === 'rejected' && axios.isCancel(result.reason)) throw result.reason
    }
    const graph = graphResult.status === 'fulfilled'
      ? graphResult.value.data
      : (run.acgBlueprint || null)
    const provenance = provenanceResult.status === 'fulfilled'
      ? provenanceProjection(provenanceResult.value.data)
      : { schemaVersion: undefined, integrityStatus: 'unknown', productions: [], consumptions: [], interactions: [] }
    const trace: WorkflowTraceExport = traceResult.status === 'fulfilled'
      ? traceResult.value
      : { runId, missionId: run.missionId, workflowId: run.workflowId, domain: run.domain, status: run.status, eventCount: 0, events: [] }
    const identityResult = await identityRequest
    const outputRefs = (run.outputs || []).map(item => [item.stepId, item.outputRef] as [string, string])
    const outputResults: PromiseSettledResult<AcgDeliverable>[] = outputRefs.length
      ? await Promise.allSettled(outputRefs.map(async ([stepId, outputRef]) => {
        const response = await agentosRequest.get<{ content: OutputContentValue }>(
          `${runPath(runId)}/outputs/${encodeURIComponent(outputRef)}`,
          { signal: options.signal }
        )
        const step = run.steps.find(item => item.stepId === stepId)
        return { stepId, outputRef, name: step?.name || stepId, status: step?.status || 'completed', output: decodeOutputContent(response.data.content) }
      }))
      : []
    const outputByKey = new Map<string, AcgDeliverable>()
    for (const result of outputResults) {
      if (result.status === 'rejected' && axios.isCancel(result.reason)) throw result.reason
      if (result.status !== 'fulfilled') continue
      const item = result.value
      outputByKey.set(`${item.stepId}:${item.outputRef || ''}`, item)
    }
    const outputs = [...outputByKey.values()].sort((left, right) => {
      const leftIndex = run.steps.findIndex(step => step.stepId === left.stepId)
      const rightIndex = run.steps.findIndex(step => step.stepId === right.stepId)
      return (leftIndex < 0 ? Number.MAX_SAFE_INTEGER : leftIndex)
        - (rightIndex < 0 ? Number.MAX_SAFE_INTEGER : rightIndex)
        || left.stepId.localeCompare(right.stepId)
        || (left.outputRef || '').localeCompare(right.outputRef || '')
    })
    const interactions = provenance.interactions
    // 原生直连等新引擎路径只落 prod/cons 投递信封，不生成带 interactionId 的
    // RuntimeInteraction 记录；此时退回按消费投递聚合，否则指标在数据已存在时仍归零。
    const metricSource = interactions.length
      ? interactions
      : provenance.consumptions.filter(item => item.tokensAvailable != null || item.tokensDelivered != null)
    const tokensAvailable = metricSource.reduce((sum, item) => sum + Number(item.tokensAvailable || 0), 0)
    const tokensDelivered = metricSource.reduce((sum, item) => sum + Number(item.tokensDelivered || 0), 0)
    // 运行中每个 outputRef 都是节点级中间结果；只有 Runtime 在终态写入的
    // run.outputRef 才能升级为最终交付，避免把最后一个中间节点冒充报告。
    const finalOutput = run.status === 'completed' && run.outputRef
      ? outputs.find(item => item.outputRef === run.outputRef)
      : undefined
    const finalArtifacts = finalOutput ? (() => {
      const item = finalOutput
      const artifact = item.output.artifact
      if (!artifact || typeof artifact !== 'object') return []
      const candidate = artifact as Record<string, unknown>
      if (typeof candidate.artifactId !== 'string' || typeof candidate.content !== 'string') return []
      if (!isRunDeliverableEntry({
        artifactKey: typeof candidate.artifactKey === 'string' ? candidate.artifactKey : null,
        artifactType: typeof candidate.artifactType === 'string'
          ? candidate.artifactType
          : typeof candidate.type === 'string' ? candidate.type : null,
      })) return []
      return [{
        artifactId: candidate.artifactId,
        type: typeof candidate.type === 'string' ? candidate.type : 'report',
        artifactKey: typeof candidate.artifactKey === 'string' ? candidate.artifactKey : undefined,
        artifactType: typeof candidate.artifactType === 'string'
          ? candidate.artifactType
          : typeof candidate.type === 'string' ? candidate.type : undefined,
        title: typeof candidate.title === 'string' ? candidate.title : item.name,
        mediaType: typeof candidate.mediaType === 'string' ? candidate.mediaType : 'text/markdown',
        content: candidate.content,
        structuredData: candidate.structuredData && typeof candidate.structuredData === 'object'
          ? candidate.structuredData as Record<string, any>
          : {},
        stepId: item.stepId
      } satisfies AcgFinalArtifact]
    })() : []
    const finalReport = finalArtifacts.length && finalOutput ? outputMarkdown(finalOutput.output) : null
    const executionTree = identityResult.executionTree
    const stepStates = stepStatesFromRun(run, executionTree)
    return {
      runId,
      status: run.status,
      engine: run.runtimeEngine || 'acg',
      runtimeRevision: run.runtimeRevision,
      acgBlueprint: graph as GraphProjection | null,
      graphVersion: graph?.graphVersion || run.graphVersion || null,
      completedStepIds: run.completedStepIds || [],
      activeStepIds: run.activeStepIds || [],
      stepStates,
      provenance,
      interactions,
      contractViolations: trace.events.filter(event => event.eventType === 'contract_violation'),
      recoveryTrace: trace.events.filter(event => ['step_failed', 'run_recovered', 'run_degraded'].includes(event.eventType)),
      scheduleTrace: trace.events.filter(event => event.eventType.includes('schedule') || event.eventType.includes('superstep')),
      deliverables: outputs,
      stepOutputs: outputs,
      finalArtifacts,
      finalReport,
      lowEntropyMetrics: {
        averageSavingRatio: metricSource.length ? metricSource.reduce((sum, item) => sum + Number(item.savingRatio || 0), 0) / metricSource.length : 0,
        effectiveSavingRatio: tokensAvailable ? (tokensAvailable - tokensDelivered) / tokensAvailable : 0,
        tokensAvailable,
        tokensDelivered,
        tokensSaved: Math.max(0, tokensAvailable - tokensDelivered),
        recoveryCount: trace.events.filter(event => event.eventType === 'run_recovered').length,
        interactionCount: metricSource.length,
        contractViolationCount: trace.events.filter(event => event.eventType === 'contract_violation').length,
        integrityStatus: provenance.integrityStatus || 'invalid'
      },
      executionTree,
      lineage: executionTree?.lineage || run.lineage || null,
      lifecycles: executionTree?.lifecycles || [],
      operational: null,
      identityProjection: identityResult.projection
    }
  }
})
