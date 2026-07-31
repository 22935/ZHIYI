import type { Component } from 'vue'
import type { AsyncWorkflowStartRequest } from '@/services/api/workflow'

export type WorkbenchPlanningMode = 'dynamic' | 'template_preferred'
export type PlanningDiversity = 'stable' | 'balanced' | 'exploratory'

export interface WorkbenchDraft {
  title: string
  taskGoal: string
  materialText: string
  constraints: string[]
  expectedArtifacts: string[]
  materialIds: string[]
  enabledPluginIds: string[]
  planningMode: WorkbenchPlanningMode
  planningDiversity: PlanningDiversity
  planningSeed: number | null
  thinkingMode: 'disabled' | 'standard' | 'deep'
  reviewMode: 'auto' | 'human_in_loop'
  pluginData: Record<string, Record<string, unknown>>
}

export interface PluginValidationResult {
  valid: boolean
  message?: string
}

export interface PluginArtifactRendererProps {
  deliverables: unknown[]
  finalReport: string | null
}

export interface PluginUiExtension {
  pluginId: string
  displayName: string
  createDefaults?: () => Partial<WorkbenchDraft>
  validateDraft?: (draft: WorkbenchDraft) => PluginValidationResult
  buildStartRequest?: (
    draft: WorkbenchDraft
  ) => Partial<AsyncWorkflowStartRequest>
  hydratePluginData?: (
    runInput: Record<string, unknown>,
    current: Record<string, unknown>
  ) => Record<string, unknown>
  taskInputComponent?: Component
  strategyComponent?: Component
  artifactRenderer?: Component
}

export const createNativeWorkbenchDraft = (): WorkbenchDraft => ({
  title: '基础软件项目实施方案',
  taskGoal: '设计一个基础软件项目实施方案，包括目标、阶段、风险和交付物',
  materialText: '',
  constraints: [],
  expectedArtifacts: ['实施方案'],
  materialIds: [],
  enabledPluginIds: [],
  planningMode: 'dynamic',
  planningDiversity: 'stable',
  planningSeed: null,
  thinkingMode: 'disabled',
  reviewMode: 'auto',
  pluginData: {}
})

const mergeInput = (
  base: Record<string, unknown>,
  addition: unknown
): Record<string, unknown> => (
  addition && typeof addition === 'object'
    ? { ...base, ...(addition as Record<string, unknown>) }
    : base
)

const clonePluginData = (value: WorkbenchDraft['pluginData']) =>
  JSON.parse(JSON.stringify(value)) as WorkbenchDraft['pluginData']

export const buildWorkbenchStartRequest = (
  draft: WorkbenchDraft,
  extensions: PluginUiExtension[],
  clientRequestId: string
): AsyncWorkflowStartRequest => {
  let domain = 'general'
  let intent = 'general'
  let workflowId: string | undefined
  let reviewMode = draft.reviewMode
  let input: Record<string, unknown> = {
    source: 'acg',
    userIntent: draft.taskGoal,
    taskGoal: draft.taskGoal,
    materialText: draft.materialText,
    materialIds: [...draft.materialIds],
    constraints: [...draft.constraints],
    expectedArtifacts: [...draft.expectedArtifacts],
    planningMode: draft.planningMode,
    usePlanner: true,
    forceDynamicPlanning: draft.planningMode === 'dynamic',
    thinkingMode: draft.thinkingMode,
    pluginData: clonePluginData(draft.pluginData)
  }

  for (const extension of extensions) {
    const contribution = extension.buildStartRequest?.(draft)
    if (!contribution) continue
    if (contribution.domain) domain = contribution.domain
    if (contribution.intent) intent = contribution.intent
    if (contribution.workflowId !== undefined) workflowId = contribution.workflowId
    if (contribution.reviewMode === 'auto' || contribution.reviewMode === 'human_in_loop') {
      reviewMode = contribution.reviewMode
    }
    input = mergeInput(input, contribution.input)
  }

  return {
    title: draft.title.trim(),
    domain,
    intent,
    workflowId,
    reviewMode,
    input,
    clientRequestId,
    planningDiversity: draft.planningDiversity,
    planningSeed: draft.planningSeed ?? undefined,
    enabledPluginIds: [...draft.enabledPluginIds]
  }
}
