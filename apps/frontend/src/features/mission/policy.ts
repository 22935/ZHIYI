import type { AsyncWorkflowStartRequest } from '@/services/api/workflow'
import type { PluginUiExtension, WorkbenchDraft } from '@/features/acg/workbench'

export interface MissionLaunchPolicy {
  domain: string
  intent: string
  workflowId?: string
  reviewMode?: string
  enabledPluginIds?: string[] | null
}
export type MissionLaunchEntry = 'conversation' | 'workbench' | 'legacy-acg'

// undefined means omitted/inherit; '' is an explicit cleared string, [] is
// explicitly no plugins, null preserves the API's automatic scope semantics.
export function resolveMissionLaunchPolicy(input:
  | { entry: 'conversation'; explicit: Partial<MissionLaunchPolicy>; inherited?: Partial<MissionLaunchPolicy>; profile?: 'conversation-workspace' }
  | { entry: 'workbench' | 'legacy-acg'; draft: WorkbenchDraft; extensions: PluginUiExtension[] }
): MissionLaunchPolicy & { input: Record<string, unknown> } {
  if (input.entry === 'conversation') {
    const select = <K extends keyof MissionLaunchPolicy>(key: K, fallback: MissionLaunchPolicy[K]): MissionLaunchPolicy[K] =>
      (input.explicit[key] !== undefined ? input.explicit[key]
        : input.inherited?.[key] !== undefined ? input.inherited[key] : fallback) as MissionLaunchPolicy[K]
    return { domain: select('domain', 'general'), intent: select('intent', 'general'),
      workflowId: select('workflowId', undefined), reviewMode: select('reviewMode', 'auto'),
      enabledPluginIds: select('enabledPluginIds', undefined), input: {} }
  }
  const result: MissionLaunchPolicy & { input: Record<string, unknown> } = {
    domain: 'general', intent: 'general', reviewMode: input.draft.reviewMode,
    enabledPluginIds: [...input.draft.enabledPluginIds], input: {}
  }
  for (const extension of input.extensions) {
    const contribution: Partial<AsyncWorkflowStartRequest> = extension.buildStartRequest?.(input.draft) || {}
    if (contribution.domain) result.domain = contribution.domain
    if (contribution.intent) result.intent = contribution.intent
    if (contribution.workflowId !== undefined) result.workflowId = contribution.workflowId
    if (contribution.reviewMode === 'auto' || contribution.reviewMode === 'human_in_loop') result.reviewMode = contribution.reviewMode
    if (contribution.input && typeof contribution.input === 'object') Object.assign(result.input, contribution.input)
  }
  return result
}
