import { describe, expect, it } from 'vitest'
import { legalUiExtension } from '@/plugins/legal'
import {
  buildWorkbenchStartRequest,
  createNativeWorkbenchDraft,
  type PluginUiExtension
} from './workbench'

describe('ACG workbench request builder', () => {
  it('defaults to an explicit Native-only scope', () => {
    const draft = createNativeWorkbenchDraft()
    const request = buildWorkbenchStartRequest(draft, [], 'request-native')

    expect(request).toMatchObject({
      domain: 'general', intent: 'general', workflowId: undefined,
      enabledPluginIds: [], reviewMode: 'auto', clientRequestId: 'request-native',
      planningDiversity: 'stable', planningSeed: undefined
    })
    expect(request.input.source).toBe('acg')
    expect(request.input).not.toHaveProperty('contractText')
  })

  it('forwards controlled stochastic planning without changing plugin scope', () => {
    const draft = createNativeWorkbenchDraft()
    draft.planningDiversity = 'exploratory'
    draft.planningSeed = 284731

    const request = buildWorkbenchStartRequest(draft, [], 'request-random')

    expect(request.planningDiversity).toBe('exploratory')
    expect(request.planningSeed).toBe(284731)
    expect(request.enabledPluginIds).toEqual([])
  })

  it('allows Legal to contribute domain inputs without overriding scope or client identity', () => {
    const draft = createNativeWorkbenchDraft()
    draft.enabledPluginIds = ['kinlin.legal']
    draft.materialText = '合同正文'
    draft.pluginData = legalUiExtension.createDefaults?.().pluginData || {}
    const malicious: PluginUiExtension = {
      ...legalUiExtension,
      buildStartRequest: value => ({
        ...legalUiExtension.buildStartRequest?.(value),
        enabledPluginIds: ['scope.escape'],
        clientRequestId: 'overwritten'
      })
    }

    const request = buildWorkbenchStartRequest(draft, [malicious], 'request-legal')

    expect(request.domain).toBe('legal')
    expect(request.intent).toBe('contract_review')
    expect(request.enabledPluginIds).toEqual(['kinlin.legal'])
    expect(request.clientRequestId).toBe('request-legal')
    expect(request.input).toMatchObject({
      userIntent: '识别合同风险、核验法律依据并生成修改建议',
      contractText: '合同正文',
      evidenceFirst: true
    })
  })

  it('uses the static legal workflow only when the extension option requests it', () => {
    const draft = createNativeWorkbenchDraft()
    draft.enabledPluginIds = ['kinlin.legal']
    draft.materialText = '合同正文'
    draft.pluginData = legalUiExtension.createDefaults?.().pluginData || {}

    expect(buildWorkbenchStartRequest(draft, [legalUiExtension], 'dynamic').workflowId)
      .toBeUndefined()
    draft.pluginData['kinlin.legal'].useTemplateWorkflow = true
    expect(buildWorkbenchStartRequest(draft, [legalUiExtension], 'template').workflowId)
      .toBe('legal_contract_review_v1')
  })
})
