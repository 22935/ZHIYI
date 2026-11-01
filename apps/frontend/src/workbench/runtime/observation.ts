import {
  agentosApi,
  type ProvenanceConsumption,
  type ProvenanceProduction,
  type ResourceFailoverObservation,
  type ResourceObservation,
  type RunContextPackSummary,
  type RunOperationalState,
  type RunLineage,
  type RunExecutionTree,
  type NodeLifecycleQuery,
  type RuntimeInteraction,
  type RunProvenanceProjection,
  type TraceEvent,
  type WorkflowRun,
  type WorkflowTraceExport,
  type WorkspaceDiagnostic
} from '@/services/api/agentos'
import { loadResourceObservation } from './resourceObservation'

export interface RuntimeTraceObservation {
  eventId: string
  runId: string
  stepId: string | null
  eventType: string
  observation: string | null
  timestamp: string | null
  durationMs: number | null
  status: string | null
  payload: Record<string, any>
  source: 'trace'
}

export interface RuntimeCommunicationObservation {
  id: string
  source: 'provenance' | 'trace'
  sourceEventId: string
  timestamp: string | null
  producerStepId: string | null
  consumerStepId: string | null
  artifactRef: string | null
  fields: string[]
  tokenCount: number | null
  status: string | null
  summary: string
}

export interface RuntimeEventObservation {
  eventId: string
  eventType: string
  timestamp: string | null
  stepId: string | null
  target: string | null
  summary: string
  source: 'trace'
}

export interface RuntimeToolCallObservation {
  eventId: string
  tool: string | null
  name: string | null
  stepId: string | null
  status: string | null
  startedAt: string | null
  durationMs: number | null
  latencyMs: number | null
  source: 'trace'
}

export interface RuntimeProblem extends WorkspaceDiagnostic {
  source: 'projection' | 'trace'
  targetStepId?: string | null
}

export interface RuntimeAuditObservation {
  provenanceStatus: string | null
  provenanceRecordCount: number
  evidenceCount: number
  contractViolationCount: number
  recoveryCount: number
  reviewCount: number | null
}

export interface RuntimeProvenanceObservation {
  schemaVersion: number | null
  integrityStatus: string | null
  productions: ProvenanceProduction[]
  consumptions: ProvenanceConsumption[]
  interactions: RuntimeInteraction[]
}

export interface RuntimeLowEntropyObservation {
  observed: boolean
  source: 'provenance' | null
  averageSavingRatio: number | null
  effectiveSavingRatio: number | null
  tokensAvailable: number | null
  tokensDelivered: number | null
  tokensSaved: number | null
  recoveryCount: number
  degradationCount: number
  interactionCount: number
  contractViolationCount: number
  integrityStatus: string | null
}

export interface RuntimeSelection {
  stepId?: string | null
  semanticTaskKey?: string | null
}

export interface RuntimeObservation {
  executionTree?: RunExecutionTree | null
  run?: WorkflowRun | null
  runId: string
  runStatus: string | null
  traces: RuntimeTraceObservation[]
  events: RuntimeEventObservation[]
  communication: RuntimeCommunicationObservation[]
  toolCalls: RuntimeToolCallObservation[]
  problems: RuntimeProblem[]
  audit: RuntimeAuditObservation
  provenance: RuntimeProvenanceObservation
  operational: RunOperationalState | null
  lineage: RunLineage | null
  lifecycles: NodeLifecycleQuery[]
  recoveryTrace: RuntimeTraceObservation[]
  contractViolations: RuntimeTraceObservation[]
  scheduleTrace: RuntimeTraceObservation[]
  patchRefs: string[]
  lowEntropy: RuntimeLowEntropyObservation
  resourceObservation: ResourceObservation | null
  contextPacks: RunContextPackSummary[] | null
  unavailableSources: string[]
}

export interface RuntimeObservationAdapterOptions {
  historical?: boolean
  diagnostics?: readonly WorkspaceDiagnostic[]
  pollIntervalMs?: number
  onUpdate: (observation: RuntimeObservation) => void
}

export class RuntimeObservationStaleError extends Error {
  constructor() {
    super('Runtime observation request became stale')
    this.name = 'RuntimeObservationStaleError'
  }
}

const ACTIVE_RUN_STATUSES = new Set(['pending', 'planning', 'running', 'retrying', 'waiting_review'])
const DEDICATED_TRACE_TYPES = new Set(['data_produced', 'data_consumed', 'model_called', 'tool_called'])
const RECOVERY_TRACE_TYPES = new Set(['step_failed', 'run_recovered', 'run_degraded', 'contract_violation'])

const asRecord = (value: unknown): Record<string, any> => (
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, any> : {}
)

const stringOrNull = (value: unknown): string | null => typeof value === 'string' && value ? value : null
const numberOrNull = (value: unknown): number | null => typeof value === 'number' && Number.isFinite(value) ? value : null

const eventSummary = (event: RuntimeTraceObservation | TraceEvent) => {
  const observation = 'observation' in event ? event.observation : null
  const payload = asRecord(event.payload)
  return stringOrNull(observation) || stringOrNull(payload.message) || event.eventType
}

const normalizeTrace = (trace: WorkflowTraceExport | null): RuntimeTraceObservation[] => (
  (trace?.events || []).map(event => {
    const payload = asRecord(event.payload)
    const duration = numberOrNull(event.durationMs)
    return {
      eventId: event.eventId,
      runId: event.runId,
      stepId: stringOrNull(event.stepId),
      eventType: event.eventType,
      observation: stringOrNull(event.observation),
      timestamp: stringOrNull(event.createdAt),
      durationMs: duration != null && duration > 0 ? duration : null,
      status: stringOrNull(payload.status),
      payload,
      source: 'trace'
    }
  })
)

const normalizeResourceFailoverEvents = (traces: RuntimeTraceObservation[]): ResourceFailoverObservation[] => (
  traces.flatMap(event => {
    if (event.eventType !== 'run_recovered') return []
    const payload = asRecord(event.payload)
    if (payload.action !== 'resource_failover' && !Array.isArray(payload.resources) && !Array.isArray(payload.failedResources)) {
      return []
    }
    const rawResources = Array.isArray(payload.resources)
      ? payload.resources
      : Array.isArray(payload.failedResources) ? payload.failedResources : []
    const failedResources = rawResources.flatMap(value => {
      const item = asRecord(value)
      const resourceId = stringOrNull(item.resourceId)
      if (!resourceId) return []
      return [{
        stepId: stringOrNull(item.stepId) || undefined,
        resourceId,
        error: stringOrNull(item.error)
      }]
    })
    if (!failedResources.length) return []
    return [{
      eventId: event.eventId,
      stepId: event.stepId,
      timestamp: event.timestamp,
      failedResources,
      retryStepIds: Array.isArray(payload.retryStepIds)
        ? payload.retryStepIds.filter((value): value is string => typeof value === 'string')
        : []
    }]
  })
)

const fieldsFromPayload = (payload: Record<string, any>) => {
  if (Array.isArray(payload.fields)) return payload.fields.filter((value): value is string => typeof value === 'string')
  if (Array.isArray(payload.consumedFields)) return payload.consumedFields.filter((value): value is string => typeof value === 'string')
  // Typed producer→fields association rows (the trace/provenance projections);
  // the legacy dynamic fieldsByProducer map stays readable until both producers migrated.
  if (Array.isArray(payload.producerFields)) {
    return payload.producerFields.flatMap(row => {
      const association = asRecord(row)
      return Array.isArray(association.fields)
        ? association.fields.filter((value): value is string => typeof value === 'string')
        : []
    })
  }
  const fieldsByProducer = asRecord(payload.fieldsByProducer)
  return Object.values(fieldsByProducer).flatMap(value => Array.isArray(value) ? value : [])
    .filter((value): value is string => typeof value === 'string')
}

const communicationItem = (
  payload: Record<string, any>,
  source: 'provenance' | 'trace',
  sourceEventId: string,
  timestamp: string | null,
  index: number
): RuntimeCommunicationObservation | null => {
  const producerStepId = stringOrNull(payload.producerStepId)
    || (Array.isArray(payload.producerStepIds) ? stringOrNull(payload.producerStepIds[0]) : null)
  const consumerStepId = stringOrNull(payload.consumerStepId)
  const interaction = Boolean(payload.interactionId)
  const communicationShape = Boolean(producerStepId && consumerStepId && (
    payload.outputRef || payload.artifactRef || payload.channel || payload.fields || payload.consumedFields || interaction
  ))
  if (!communicationShape) return null
  const fields = fieldsFromPayload(payload)
  const tokenCount = numberOrNull(payload.tokens) ?? numberOrNull(payload.tokensDelivered)
  return {
    id: `${source}:${sourceEventId}:${index}`,
    source,
    sourceEventId,
    timestamp,
    producerStepId,
    consumerStepId,
    artifactRef: stringOrNull(payload.outputRef) || stringOrNull(payload.artifactRef),
    fields,
    tokenCount,
    status: stringOrNull(payload.contractStatus) || stringOrNull(payload.status),
    summary: `${producerStepId} → ${consumerStepId}${fields.length ? ` · ${fields.join(', ')}` : ''}`
  }
}

const normalizeProvenance = (provenance: RunProvenanceProjection | null): RuntimeProvenanceObservation => {
  if (!provenance) {
    return { schemaVersion: null, integrityStatus: null, productions: [], consumptions: [], interactions: [] }
  }

  const events = provenance.events || []
  if (!events.length) {
    return {
      schemaVersion: null,
      integrityStatus: stringOrNull(provenance.integrityStatus),
      productions: provenance.productions || [],
      consumptions: provenance.consumptions || [],
      interactions: provenance.interactions || []
    }
  }

  const payloads: Record<string, any>[] = events.map(event => ({
    ...asRecord(event.payload),
    createdAt: stringOrNull(event.createdAt) || stringOrNull(asRecord(event.payload).createdAt) || undefined
  }))
  return {
    schemaVersion: null,
    integrityStatus: stringOrNull(provenance.integrityStatus),
    productions: payloads.filter(item => item.producerStepId && !item.consumerStepId) as ProvenanceProduction[],
    consumptions: payloads.filter(item => item.consumerStepId && !item.interactionId) as ProvenanceConsumption[],
    interactions: payloads.filter(item => item.interactionId) as RuntimeInteraction[]
  }
}

const provenanceCommunication = (provenance: RuntimeProvenanceObservation) => {
  const normalizedProvenance = provenance
  const items: RuntimeCommunicationObservation[] = []
  for (const [index, interactionRecord] of normalizedProvenance.interactions.entries()) {
    const payload = interactionPayload(interactionRecord)
    const normalized = communicationItem(
      payload,
      'provenance',
      interactionRecord.eventId || `event-${index}`,
      interactionRecord.createdAt || null,
      index
    )
    if (normalized) items.push(normalized)
  }
  for (const [index, item] of normalizedProvenance.consumptions.entries()) {
    const consumption = consumptionPayload(item)
    const normalized = communicationItem(consumption, 'provenance', item.eventId, item.createdAt || null, index)
    if (normalized) items.push(normalized)
  }
  return items
}

const interactionPayload = (item: RuntimeInteraction): Record<string, any> => ({
  interactionId: item.interactionId,
  eventId: item.eventId,
  producerStepIds: item.producerStepIds,
  consumerStepId: item.consumerStepId,
  producerFields: item.producerFields,
  tokensDelivered: item.tokensDelivered,
  tokensAvailable: item.tokensAvailable,
  contractStatus: item.contractStatus
})

const consumptionPayload = (item: ProvenanceConsumption): Record<string, any> => ({
  eventId: item.eventId,
  producerStepIds: item.producerStepIds,
  consumerStepId: item.consumerStepId,
  consumedFields: item.consumedFields,
  producerFields: item.producerFields,
  tokensDelivered: item.tokensDelivered,
  tokensAvailable: item.tokensAvailable,
  contractStatus: item.contractStatus
})

const traceCommunication = (traces: RuntimeTraceObservation[]) => traces.flatMap((event, index) => {
  const item = communicationItem(event.payload, 'trace', event.eventId, event.timestamp, index)
  return item ? [item] : []
})

const normalizeEvents = (traces: RuntimeTraceObservation[]): RuntimeEventObservation[] => traces
  .filter(event => !DEDICATED_TRACE_TYPES.has(event.eventType))
  .map(event => ({
    eventId: event.eventId,
    eventType: event.eventType,
    timestamp: event.timestamp,
    stepId: event.stepId,
    target: event.stepId || stringOrNull(event.payload.target) || stringOrNull(event.payload.component) || null,
    summary: eventSummary(event),
    source: 'trace'
  }))

const normalizeToolCalls = (traces: RuntimeTraceObservation[]): RuntimeToolCallObservation[] => traces
  .filter(event => event.eventType === 'tool_called')
  .map(event => ({
    eventId: event.eventId,
    tool: stringOrNull(event.payload.tool),
    name: stringOrNull(event.payload.name),
    stepId: event.stepId,
    status: stringOrNull(event.payload.status),
    startedAt: event.timestamp,
    durationMs: event.durationMs,
    latencyMs: numberOrNull(event.payload.latencyMs),
    source: 'trace'
  }))

export interface ModelOutputMetrics {
  taskCount?: number
  dependencyCount?: number
  nodeCount?: number
  edgeCount?: number
  constraintCount?: number
  requiredCapabilityCount?: number
  expectedArtifactCount?: number
  timeoutSeconds?: number
}

export interface ModelOutputItem {
  id: string
  timestamp: string | null
  category: 'planner' | 'runtime'
  kind: string
  stage: string | null
  status: 'running' | 'success' | 'warning' | 'failed'
  title: string
  detail: string | null
  attempt: number
  retryCount: number
  metrics: ModelOutputMetrics
}

const PLANNER_STAGE_LABELS: Record<string, string> = {
  planning: '规划流程',
  intent_profile: '意图解析',
  outline: '结构规划',
  detail: '任务细化',
  relations: '依赖构建',
  decompose: '任务分解',
  repair: '结果修复',
  'detail.repair': '细化修复',
  'relations.repair': '关系修复',
  repair_coverage: '覆盖修复'
}

const plannerStageLabel = (stage: string | null) => (
  stage ? PLANNER_STAGE_LABELS[stage] || `阶段 ${stage}` : '规划'
)

const kindFromLegacyStatus = (status: string | null) => (
  status === 'started' ? 'stage_started'
    : status === 'completed' ? 'stage_completed'
      : status === 'retrying' ? 'retry'
        : 'stage_updated'
)

const scalarCount = (value: unknown): number | null => {
  const parsed = Number(value)
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null
}

const joinedCount = (parts: string[]) => parts.length ? ` · ${parts.join(' · ')}` : ''

const modelOutputTitle = (kind: string, stage: string | null, payload: Record<string, any>) => {
  switch (kind) {
    case 'started':
      return '开始规划任务'
    case 'stage_started':
      return `${plannerStageLabel(stage)}开始`
    case 'stage_completed':
      return `${plannerStageLabel(stage)}完成`
    case 'profile_resolved': {
      const constraints = scalarCount(payload.constraintCount)
      return constraints != null
        ? `已解析任务约束 · ${constraints} 条`
        : '任务画像已解析'
    }
    case 'plan_parsed': {
      const taskCount = scalarCount(payload.taskCount)
      const dependencyCount = scalarCount(payload.dependencyCount)
      return '任务规划完成' + joinedCount([
        ...(taskCount != null ? [`${taskCount} 个任务`] : []),
        ...(dependencyCount != null ? [`${dependencyCount} 条依赖`] : [])
      ])
    }
    case 'graph_compiled': {
      const nodeCount = scalarCount(payload.nodeCount)
      const edgeCount = scalarCount(payload.edgeCount)
      return 'ACG 编译完成' + joinedCount([
        ...(nodeCount != null ? [`${nodeCount} 个节点`] : []),
        ...(edgeCount != null ? [`${edgeCount} 条边`] : [])
      ])
    }
    case 'completed':
      return '规划完成'
    case 'retry':
      return '规划请求重试'
    case 'failed':
      return '规划失败'
    default:
      return `${plannerStageLabel(stage)}更新`
  }
}

const modelOutputStatusState = (kind: string): ModelOutputItem['status'] => (
  kind === 'failed' ? 'failed'
    : kind === 'retry' ? 'warning'
      : kind === 'started' || kind === 'stage_started' ? 'running'
        : 'success'
)

/**
 * Project planner Trace events into Model Output items.
 *
 * Every title must be traceable to one Runtime Event: kind-driven facts first
 * (new category="planner" payloads), engineering-stage wording as the legacy
 * fallback. A retried stage replaces its still-running start instead of
 * stacking a duplicate row; no timer or stage guesswork ever runs here.
 */
export const projectModelOutput = (traces: RuntimeTraceObservation[]): ModelOutputItem[] => {
  const items: ModelOutputItem[] = []
  const openStartedIndex = new Map<string, number>()
  for (const event of traces) {
    const payload = asRecord(event.payload)
    if (!payload.planningProgress) continue
    const category: ModelOutputItem['category'] = payload.category === 'planner' ? 'planner' : 'runtime'
    const stage = stringOrNull(payload.stage)
    const legacyStatus = stringOrNull(payload.status)
    const kind = stringOrNull(payload.kind) || kindFromLegacyStatus(legacyStatus)
    const errorCode = stringOrNull(payload.errorCode)
    const item: ModelOutputItem = {
      id: event.eventId,
      timestamp: event.timestamp,
      category,
      kind,
      stage,
      status: modelOutputStatusState(kind),
      title: modelOutputTitle(kind, stage, payload),
      detail: errorCode ? `错误码 ${errorCode}` : null,
      attempt: scalarCount(payload.attempt) ?? 1,
      retryCount: scalarCount(payload.retryCount) ?? 0,
      metrics: {
        taskCount: scalarCount(payload.taskCount) ?? undefined,
        dependencyCount: scalarCount(payload.dependencyCount) ?? undefined,
        nodeCount: scalarCount(payload.nodeCount) ?? undefined,
        edgeCount: scalarCount(payload.edgeCount) ?? undefined,
        constraintCount: scalarCount(payload.constraintCount) ?? undefined,
        requiredCapabilityCount: scalarCount(payload.requiredCapabilityCount) ?? undefined,
        expectedArtifactCount: scalarCount(payload.expectedArtifactCount) ?? undefined,
        timeoutSeconds: scalarCount(payload.timeoutSeconds) ?? undefined
      }
    }
    if (kind === 'stage_started' && legacyStatus === 'started' && stage) {
      const openIndex = openStartedIndex.get(stage)
      if (openIndex != null && items[openIndex]?.kind === 'stage_started') {
        items[openIndex] = item
        continue
      }
      openStartedIndex.set(stage, items.length)
    }
    if (kind === 'stage_completed' && stage) openStartedIndex.delete(stage)
    items.push(item)
  }
  return items
}

const normalizeProblems = (
  traces: RuntimeTraceObservation[],
  diagnostics: readonly WorkspaceDiagnostic[]
): RuntimeProblem[] => [
  ...diagnostics.map(item => ({ ...item, source: 'projection' as const })),
  ...traces
    .filter(event => event.eventType.includes('failed') || event.eventType.includes('violation') || event.eventType.includes('error'))
    .map(event => ({
      code: stringOrNull(event.payload.errorCode) || event.eventType.toUpperCase(),
      message: event.payload.errorCode === 'model_connection_interrupted'
        ? '模型服务连接中断，系统已完成一次重试，请稍后重新运行。'
        : event.payload.errorCode === 'model_timeout'
          ? '模型服务响应超时，系统已完成一次重试，请稍后重新运行。'
          : eventSummary(event),
      severity: 'warning' as const,
      details: event.payload,
      source: 'trace' as const,
      targetStepId: event.stepId
    }))
]

const normalizeAudit = (
  provenance: RuntimeProvenanceObservation,
  traces: RuntimeTraceObservation[],
  reviewCount: number | null
): RuntimeAuditObservation => ({
  provenanceStatus: provenance.integrityStatus,
  provenanceRecordCount: provenance.productions.length + provenance.consumptions.length + provenance.interactions.length,
  evidenceCount: provenance.productions.reduce((count, production) => count + (production.evidenceRefs?.length || 0), 0),
  contractViolationCount: traces.filter(event => event.eventType === 'contract_violation').length,
  recoveryCount: traces.filter(event => ['run_recovered', 'run_degraded'].includes(event.eventType)).length,
  reviewCount
})

type LowEntropyMetricRecord = {
  tokensAvailable?: number
  tokensDelivered?: number
  savingRatio?: number
}

const hasLowEntropyMetric = (item: LowEntropyMetricRecord) => (
  typeof item.tokensAvailable === 'number'
  || typeof item.tokensDelivered === 'number'
  || typeof item.savingRatio === 'number'
)

const provenanceMetricSource = (provenance: RuntimeProvenanceObservation): LowEntropyMetricRecord[] => {
  // Both legacy arrays and ledger-backed events are normalized before this
  // point. Prefer interactions when they carry metrics, then delivery
  // envelopes. A production event is never a low-entropy metric record.
  const interactions = provenance.interactions.filter(hasLowEntropyMetric)
  if (interactions.length) return interactions

  const consumptions = provenance.consumptions.filter(hasLowEntropyMetric)
  if (consumptions.length) return consumptions

  return []
}

const normalizeLowEntropy = (
  provenance: RuntimeProvenanceObservation,
  traces: RuntimeTraceObservation[]
): RuntimeLowEntropyObservation => {
  const metricSource = provenanceMetricSource(provenance)
  const tokenSource = metricSource.filter(item => item.tokensAvailable != null || item.tokensDelivered != null)
  const hasSavingRatios = metricSource.some(item => typeof item.savingRatio === 'number' && Number.isFinite(item.savingRatio))
  const tokensAvailable = tokenSource.length
    ? tokenSource.reduce((sum, item) => sum + Number(item.tokensAvailable || 0), 0)
    : null
  const tokensDelivered = tokenSource.length
    ? tokenSource.reduce((sum, item) => sum + Number(item.tokensDelivered || 0), 0)
    : null

  return {
    observed: metricSource.length > 0,
    source: metricSource.length ? 'provenance' : null,
    averageSavingRatio: hasSavingRatios
      ? metricSource.reduce((sum, item) => sum + Number(item.savingRatio || 0), 0) / metricSource.length
      : null,
    effectiveSavingRatio: tokensAvailable && tokensAvailable > 0 && tokensDelivered != null
      ? (tokensAvailable - tokensDelivered) / tokensAvailable
      : null,
    tokensAvailable,
    tokensDelivered,
    tokensSaved: tokensAvailable != null && tokensDelivered != null
      ? Math.max(0, tokensAvailable - tokensDelivered)
      : null,
    recoveryCount: traces.filter(event => event.eventType === 'run_recovered').length,
    degradationCount: traces.filter(event => event.eventType === 'run_degraded').length,
    interactionCount: metricSource.length,
    contractViolationCount: traces.filter(event => event.eventType === 'contract_violation').length,
    integrityStatus: stringOrNull(provenance?.integrityStatus)
  }
}

export const emptyRuntimeObservation = (runId: string, diagnostics: readonly WorkspaceDiagnostic[] = []): RuntimeObservation => ({
  runId,
  runStatus: null,
  traces: [],
  events: [],
  communication: [],
  toolCalls: [],
  problems: normalizeProblems([], diagnostics),
  audit: {
    provenanceStatus: null,
    provenanceRecordCount: 0,
    evidenceCount: 0,
    contractViolationCount: 0,
    recoveryCount: 0,
    reviewCount: null
  },
  provenance: {
    schemaVersion: null,
    integrityStatus: null,
    productions: [],
    consumptions: [],
    interactions: []
  },
  operational: null,
  lineage: null,
  lifecycles: [],
  recoveryTrace: [],
  contractViolations: [],
  scheduleTrace: [],
  patchRefs: [],
  lowEntropy: {
    observed: false,
    source: null,
    averageSavingRatio: null,
    effectiveSavingRatio: null,
    tokensAvailable: null,
    tokensDelivered: null,
    tokensSaved: null,
    recoveryCount: 0,
    degradationCount: 0,
    interactionCount: 0,
    contractViolationCount: 0,
    integrityStatus: null
  },
  resourceObservation: null,
  contextPacks: null,
  unavailableSources: ['run', 'trace', 'provenance', 'resource', 'context']
})

export const readRuntimeObservation = async (
  runId: string,
  diagnostics: readonly WorkspaceDiagnostic[] = [],
  options: { signal?: AbortSignal } = {}
): Promise<RuntimeObservation> => {
  const executionTreeRequest = agentosApi.getExecutionTree(runId, options)
  const results = await Promise.allSettled([
    agentosApi.getWorkflowRun(runId, options),
    agentosApi.getWorkflowTrace(runId, { ...options, view: 'workspace' }),
    agentosApi.getRunProvenance(runId, options),
    executionTreeRequest,
    loadResourceObservation(runId, options, executionTreeRequest),
    agentosApi.listWorkflowReviews(runId, options),
    agentosApi.listRunContextPacks(runId, options)
  ])
  const run = results[0].status === 'fulfilled' ? results[0].value : null
  const trace = results[1].status === 'fulfilled' ? results[1].value : null
  const rawProvenance = results[2].status === 'fulfilled' ? results[2].value : null
  const executionTree = results[3].status === 'fulfilled' ? results[3].value : null
  const reviews = results[5].status === 'fulfilled' ? results[5].value : null
  const contextPacks = results[6].status === 'fulfilled' ? results[6].value.items : null
  const provenance = normalizeProvenance(rawProvenance)
  const traces = normalizeTrace(trace)
  const resourceObservationBase = results[4].status === 'fulfilled' ? results[4].value : null
  const resourceObservation = resourceObservationBase
    ? { ...resourceObservationBase, failoverEvents: normalizeResourceFailoverEvents(traces) }
    : null
  const unavailableSources = [
    results[0].status === 'rejected' ? 'run' : null,
    results[1].status === 'rejected' ? 'trace' : null,
    results[2].status === 'rejected' ? 'provenance' : null,
    results[3].status === 'rejected' ? 'operational' : null,
    results[4].status === 'rejected' ? 'resource' : null,
    results[5].status === 'rejected' ? 'review' : null,
    results[6].status === 'rejected' ? 'context' : null
  ].filter((value): value is string => Boolean(value))
  const recoveryTrace = traces.filter(event => RECOVERY_TRACE_TYPES.has(event.eventType))
  const contractViolations = traces.filter(event => event.eventType === 'contract_violation')
  const scheduleTrace = traces.filter(event => event.eventType.includes('schedule') || event.eventType.includes('superstep'))
  return {
    runId,
    run,
    ...(executionTree?.run?.runId === runId ? { executionTree } : {}),
    runStatus: run?.status || trace?.status || null,
    traces,
    events: normalizeEvents(traces),
    communication: [...provenanceCommunication(provenance), ...traceCommunication(traces)],
    toolCalls: normalizeToolCalls(traces),
    problems: normalizeProblems(traces, diagnostics),
    audit: normalizeAudit(provenance, traces, reviews?.items.length ?? null),
    provenance,
    operational: null,
    lineage: executionTree?.lineage || run?.lineage || null,
    lifecycles: executionTree?.lifecycles || [],
    recoveryTrace,
    contractViolations,
    scheduleTrace,
    patchRefs: [],
    lowEntropy: normalizeLowEntropy(provenance, traces),
    resourceObservation,
    contextPacks,
    unavailableSources
  }
}

export class RuntimeObservationAdapter {
  private runId: string | null = null
  private options: RuntimeObservationAdapterOptions | null = null
  private generation = 0
  private controller: AbortController | null = null
  private timer: ReturnType<typeof setTimeout> | null = null
  private unavailableSettled = false

  start(runId: string, options: RuntimeObservationAdapterOptions): void {
    // Projection refreshes update diagnostics/callbacks without cancelling the
    // independent observation request or fetching a terminal Run again.
    if (this.runId === runId && this.options?.historical === options.historical && !this.unavailableSettled) {
      this.options = options
      return
    }
    this.stop()
    this.runId = runId
    this.options = options
    const generation = ++this.generation
    const interval = options.pollIntervalMs ?? 2000
    const refresh = async () => {
      if (generation !== this.generation) return
      this.controller?.abort()
      const controller = new AbortController()
      this.controller = controller
      try {
        const observation = await readRuntimeObservation(runId, this.options?.diagnostics || [], { signal: controller.signal })
        if (generation !== this.generation || controller.signal.aborted) return
        // A transient gateway outage can leave no lifecycle status, which ends
        // polling. Allow a later same-Run refresh to recover that settled read;
        // preserve the existing in-flight and confirmed terminal behavior.
        this.unavailableSettled = !observation.run && !ACTIVE_RUN_STATUSES.has(observation.runStatus || '')
        this.options?.onUpdate(observation)
        if (!this.options?.historical && ACTIVE_RUN_STATUSES.has(observation.runStatus || '')) {
          this.timer = setTimeout(() => { void refresh() }, interval)
        }
      } finally {
        if (this.controller === controller) this.controller = null
      }
    }
    void refresh()
  }

  stop(): void {
    this.unavailableSettled = false
    this.runId = null
    this.options = null
    this.generation += 1
    this.controller?.abort()
    this.controller = null
    if (this.timer !== null) clearTimeout(this.timer)
    this.timer = null
  }
}
