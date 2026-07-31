import type {
  AcgStepState,
  AppliedPatchProjection,
  BranchDecision,
  RuntimeEventProjection
} from '@/services/api/agentos'

export interface DynamicRunSummary {
  status: string
  graphVersion: number
  dynamicStepCount: number
  bindingSwitchCount: number
  conditionalDecisionCount: number
  skippedByConditionCount: number
  appliedPatchCount: number
  pendingRuntimeEventCount: number
}

export interface RuntimeTimelineItem {
  id: string
  kind: 'event' | 'patch' | 'decision' | 'binding'
  type: string
  time: string
  graphVersionBefore?: number
  graphVersionAfter?: number
  runtimeNodeId?: string
  targetNodeId?: string
  reasonCode?: string
  patchId?: string
  eventId?: string
  description: string
  detail: unknown
}

interface RuntimeProjection {
  status?: string
  graphVersion?: number | null
  dynamicStepCount?: number
  bindingSwitchCount?: number
  conditionalDecisionCount?: number
  skippedByConditionCount?: number
  runtimeEvents?: readonly RuntimeEventProjection[]
  appliedPatches?: readonly AppliedPatchProjection[]
}

interface RuntimeCounterProjection {
  graphVersion?: number | null
  dynamicStepCount?: number
  bindingSwitchCount?: number
  conditionalDecisionCount?: number
  skippedByConditionCount?: number
}

const numberFrom = (...values: unknown[]): number => {
  const value = values.find(item => typeof item === 'number' && Number.isFinite(item))
  return typeof value === 'number' ? value : 0
}

export const buildDynamicRunSummary = (
  progress?: RuntimeProjection,
  run?: RuntimeProjection,
  view?: RuntimeProjection
): DynamicRunSummary => {
  const events = view?.runtimeEvents ?? run?.runtimeEvents ?? []
  const patches = view?.appliedPatches ?? run?.appliedPatches ?? []
  return {
    status: String(progress?.status || run?.status || view?.status || 'pending'),
    graphVersion: numberFrom(view?.graphVersion, run?.graphVersion, progress?.graphVersion, 1),
    dynamicStepCount: numberFrom(view?.dynamicStepCount, run?.dynamicStepCount, progress?.dynamicStepCount),
    bindingSwitchCount: numberFrom(view?.bindingSwitchCount, run?.bindingSwitchCount, progress?.bindingSwitchCount),
    conditionalDecisionCount: numberFrom(
      view?.conditionalDecisionCount,
      run?.conditionalDecisionCount,
      progress?.conditionalDecisionCount
    ),
    skippedByConditionCount: numberFrom(
      view?.skippedByConditionCount,
      run?.skippedByConditionCount,
      progress?.skippedByConditionCount
    ),
    appliedPatchCount: patches.length,
    pendingRuntimeEventCount: events.filter(event => event.status === 'PENDING').length
  }
}

const RUNTIME_COUNTER_KEYS: Array<keyof RuntimeCounterProjection> = [
  'graphVersion',
  'dynamicStepCount',
  'bindingSwitchCount',
  'conditionalDecisionCount',
  'skippedByConditionCount'
]

export const runtimeProjectionChanged = (
  current: RuntimeCounterProjection,
  previous: RuntimeCounterProjection | null
): boolean => {
  if (previous === null) {
    return numberFrom(current.graphVersion, 1) > 1
      || numberFrom(current.dynamicStepCount) > 0
      || numberFrom(current.bindingSwitchCount) > 0
      || numberFrom(current.conditionalDecisionCount) > 0
      || numberFrom(current.skippedByConditionCount) > 0
  }
  return RUNTIME_COUNTER_KEYS.some(key => current[key] !== previous[key])
}

export const graphVersionChanged = (
  current: RuntimeCounterProjection,
  previous: RuntimeCounterProjection | null
): boolean => previous !== null && current.graphVersion !== previous.graphVersion

const stringValue = (value: unknown): string => typeof value === 'string' ? value : ''

const eventDescription = (event: RuntimeEventProjection): string => {
  const target = stringValue(event.payload?.targetNodeId) || event.runtimeNodeId || '当前节点'
  const descriptions: Record<string, string> = {
    EVIDENCE_MISSING: `“${target}”缺少执行所需证据，系统正在评估补救步骤。`,
    BINDING_UNAVAILABLE: `“${target}”的当前执行绑定不可用，系统正在选择备用执行者。`,
    INPUT_CONTRACT_VIOLATION: `“${target}”的输入未满足契约，系统正在评估适配步骤。`,
    OUTPUT_CONTRACT_VIOLATION: `“${target}”的输出未满足契约，系统正在评估修复步骤。`,
    LOW_CONFIDENCE: `“${target}”返回低置信度结果，系统已记录该运行事实。`,
    STEP_EXECUTION_FAILED: `“${target}”执行失败，系统已记录该运行事实。`
  }
  return descriptions[event.eventType] || `系统记录了“${target}”的运行时事件 ${event.eventType}。`
}

const patchDescription = (
  patch: AppliedPatchProjection,
  events: RuntimeEventProjection[],
  stepStates: AcgStepState[]
): string => {
  const event = events.find(item => item.eventId === patch.sourceEventId)
  const target = stringValue(event?.payload?.targetNodeId) || event?.runtimeNodeId || '目标节点'
  if (patch.operationType === 'ADD_SUBGRAPH') {
    const added = stepStates
      .filter(step => step.sourcePatchId === patch.patchId && (step.createdGraphVersion ?? 1) > 1)
      .map(step => step.stepId)
    const nodes = added.length ? `新增节点：${added.join(' → ')}。` : '已插入受控补救子图。'
    return `系统在“${target}”前补充了运行步骤，${nodes}`
  }
  if (patch.operationType === 'RETRY_ALTERNATE_BINDING') {
    const step = stepStates.find(item =>
      item.bindingHistory?.some(history => history.sourcePatchId === patch.patchId)
    )
    const history = step?.bindingHistory ?? []
    const selected = history.find(item => item.sourcePatchId === patch.patchId)
    const selectedIndex = selected ? history.indexOf(selected) : -1
    const previous = selectedIndex > 0 ? history[selectedIndex - 1] : undefined
    const from = stringValue(previous?.bindingId) || 'primary'
    const to = stringValue(selected?.bindingId) || stringValue(step?.currentBinding?.bindingId) || 'backup'
    return `“${step?.stepId || target}”的执行绑定已从 ${from} 切换为 ${to}，失败 Attempt 保留。`
  }
  if (patch.operationType === 'ACTIVATE_CONDITIONAL_BRANCH') {
    return `条件节点已选择一条确定性路径，并终结未选路径。`
  }
  return `系统已应用运行图变更 ${patch.operationType}。`
}

const decisionDescription = (decision: BranchDecision): string =>
  `条件节点“${decision.controlNodeId}”选择了“${decision.selectedCaseKey}”路径，终结 ${decision.terminatedEdgeIds.length} 条未选边，跳过 ${decision.skippedNodeIds.length} 个节点。`

const bindingTimelineItems = (stepStates: AcgStepState[]): RuntimeTimelineItem[] =>
  stepStates.flatMap(step => (step.bindingHistory ?? [])
    .filter(history => history.sourcePatchId)
    .map((history, index, records) => {
      const previous = index > 0 ? records[index - 1] : undefined
      const time = stringValue(history.selectedAt)
      const patchId = stringValue(history.sourcePatchId)
      const eventId = stringValue(history.sourceEventId)
      const from = stringValue(previous?.bindingId) || 'primary'
      const to = stringValue(history.bindingId) || stringValue(step.currentBinding?.bindingId) || 'backup'
      return {
        id: `binding:${step.stepId}:${patchId || index}`,
        kind: 'binding' as const,
        type: 'BINDING_SWITCH',
        time,
        graphVersionAfter: typeof history.selectedAtGraphVersion === 'number'
          ? history.selectedAtGraphVersion
          : undefined,
        runtimeNodeId: step.stepId,
        reasonCode: stringValue(history.reasonCode),
        patchId,
        eventId,
        description: `“${step.stepId}”的执行绑定从 ${from} 切换为 ${to}。`,
        detail: history
      }
    }))

export const buildRuntimeTimeline = (
  runtimeEvents: RuntimeEventProjection[] = [],
  appliedPatches: AppliedPatchProjection[] = [],
  branchDecisions: BranchDecision[] = [],
  stepStates: AcgStepState[] = []
): RuntimeTimelineItem[] => {
  const events: RuntimeTimelineItem[] = runtimeEvents.map(event => ({
    id: `event:${event.eventId}`,
    kind: 'event',
    type: event.eventType,
    time: event.createdAt || '',
    graphVersionAfter: event.graphVersion,
    runtimeNodeId: event.runtimeNodeId,
    targetNodeId: stringValue(event.payload?.targetNodeId) || event.runtimeNodeId,
    reasonCode: stringValue(event.payload?.reasonCode),
    eventId: event.eventId,
    description: eventDescription(event),
    detail: event
  }))
  const patches: RuntimeTimelineItem[] = appliedPatches.map(patch => ({
    id: `patch:${patch.patchId}`,
    kind: 'patch',
    type: patch.operationType,
    time: patch.appliedAt || '',
    graphVersionBefore: patch.baseGraphVersion,
    graphVersionAfter: patch.resultGraphVersion,
    patchId: patch.patchId,
    eventId: patch.sourceEventId,
    description: patchDescription(patch, runtimeEvents, stepStates),
    detail: patch
  }))
  const decisions: RuntimeTimelineItem[] = branchDecisions.map(decision => ({
    id: `decision:${decision.decisionId}`,
    kind: 'decision',
    type: 'CONDITIONAL_DECISION',
    time: decision.decidedAt || '',
    graphVersionAfter: decision.decidedAtGraphVersion,
    runtimeNodeId: decision.controlNodeId,
    patchId: decision.sourcePatchId,
    eventId: decision.sourceEventId,
    description: decisionDescription(decision),
    detail: decision
  }))
  const kindOrder = { event: 0, patch: 1, decision: 2, binding: 3 }
  return [...events, ...patches, ...decisions, ...bindingTimelineItems(stepStates)].sort((a, b) => {
    const byTime = a.time.localeCompare(b.time)
    if (byTime) return byTime
    const byKind = kindOrder[a.kind] - kindOrder[b.kind]
    return byKind || a.id.localeCompare(b.id)
  })
}

const SENSITIVE_KEY = /(authorization|password|secret|token|cookie|api.?key|stack|traceback)/i

export const safeStructuredDetail = (value: unknown, depth = 0): unknown => {
  if (depth > 6) return '[已截断]'
  if (Array.isArray(value)) return value.slice(0, 50).map(item => safeStructuredDetail(item, depth + 1))
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>).map(([key, item]) => [
      key,
      SENSITIVE_KEY.test(key) ? '[已隐藏]' : safeStructuredDetail(item, depth + 1)
    ]))
  }
  if (typeof value === 'string' && value.length > 1200) return `${value.slice(0, 1200)}…`
  return value
}

export const formatRuntimeDetail = (value: unknown): string =>
  JSON.stringify(safeStructuredDetail(value), null, 2)

export const mapNodeVisualState = (step?: AcgStepState) => ({
  status: step?.status || 'pending',
  runtimeAdded: (step?.createdGraphVersion ?? 1) > 1,
  bindingSwitched: (step?.bindingSwitchCount ?? 0) > 0,
  conditionalSkipped: step?.status === 'skipped_by_condition',
  targetRetried: (step?.attempt ?? 0) > 1
})

export const mapEdgeVisualState = (activation?: string) => {
  const normalized = String(activation || 'active').toLowerCase()
  return ['inactive', 'terminated', 'superseded'].includes(normalized) ? normalized : 'active'
}
