import type { PluginUiExtension } from '@/features/acg/workbench'
import LegalTaskExtension from './LegalTaskExtension.vue'
import LegalStrategyPanel from './LegalStrategyPanel.vue'
import LegalArtifactRenderer from './LegalArtifactRenderer.vue'

export interface LegalPluginDraft {
  contractText: string
  reviewGoal: string
  contractType: string
  useTemplateWorkflow: boolean
  evidenceFirst: boolean
  riskParallel: boolean
  conservativeReview: boolean
}

const defaults = (): LegalPluginDraft => ({
  contractText: '',
  reviewGoal: '识别合同风险、核验法律依据并生成修改建议',
  contractType: '',
  useTemplateWorkflow: false,
  evidenceFirst: true,
  riskParallel: true,
  conservativeReview: true
})

const DEFAULT_LEGAL_TITLE = '合同审查与风险分析'

export const legalUiExtension: PluginUiExtension = {
  pluginId: 'kinlin.legal',
  displayName: '法律能力包',
  createDefaults: () => ({
    title: DEFAULT_LEGAL_TITLE,
    taskGoal: defaults().reviewGoal,
    reviewMode: 'human_in_loop',
    pluginData: { 'kinlin.legal': defaults() as unknown as Record<string, unknown> }
  }),
  validateDraft: draft => {
    const legal = draft.pluginData['kinlin.legal'] as unknown as LegalPluginDraft | undefined
    const hasMaterial = Boolean(
      legal?.contractText?.trim() || draft.materialText.trim() || draft.materialIds.length
    )
    return hasMaterial
      ? { valid: true }
      : { valid: false, message: '启用法律能力包后，请提供合同文本或合同文件' }
  },
  buildStartRequest: draft => {
    const legal = (draft.pluginData['kinlin.legal'] || defaults()) as unknown as LegalPluginDraft
    const contractText = legal.contractText?.trim() || draft.materialText.trim()
    return {
      domain: 'legal',
      // The registered Legal workflow intent is contract_review. Dynamic mode
      // still omits workflowId and forces the shared PlanningEngine path.
      intent: 'contract_review',
      workflowId: legal.useTemplateWorkflow ? 'legal_contract_review_v1' : undefined,
      reviewMode: legal.conservativeReview ? 'human_in_loop' : draft.reviewMode,
      input: {
        userIntent: legal.reviewGoal,
        contractText,
        contractType: legal.contractType,
        legalReviewGoal: legal.reviewGoal,
        evidenceFirst: legal.evidenceFirst,
        riskParallel: legal.riskParallel,
        conservativeReview: legal.conservativeReview
      }
    }
  },
  hydratePluginData: (runInput, current) => ({
    ...current,
    ...(typeof runInput.contractText === 'string'
      ? { contractText: runInput.contractText }
      : {})
  }),
  taskInputComponent: LegalTaskExtension,
  strategyComponent: LegalStrategyPanel,
  artifactRenderer: LegalArtifactRenderer
}
