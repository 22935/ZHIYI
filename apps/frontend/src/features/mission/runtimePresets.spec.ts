import { describe, expect, it } from 'vitest'
import { presetReasoningOption } from './runtimePresets'
import { reasoningOptionsFromCapability, type ModelCapability } from '@/config/modelSettings'

const capability = (reasoningEfforts: string[]): ModelCapability => ({
  thinkingModes: ['standard', 'deep'], alwaysThinking: true,
  supportsReasoningEffort: true, reasoningEfforts, defaultReasoningEffort: 'high'
})
describe('model-aware Mission presets', () => {
  it('maps the declared low/high/max levels to the corresponding presets', () => {
    const caps = capability(['low', 'high', 'max']), options = reasoningOptionsFromCapability(caps)
    expect(['fast', 'balanced', 'deep'].map(preset => presetReasoningOption(options, preset as 'fast' | 'balanced' | 'deep', caps)?.value))
      .toEqual(['low', 'high', 'max'])
  })
  it('uses the lowest supported effort for fast when low is not offered', () => {
    const caps = capability(['medium', 'high']), options = reasoningOptionsFromCapability(caps)
    expect(presetReasoningOption(options, 'fast', caps)?.value).toBe('medium')
    expect(presetReasoningOption(options, 'deep', caps)?.value).toBe('high')
  })
  it('supports future provider effort names without making up unsupported levels', () => {
    const caps = capability(['economy', 'normal', 'turbo']), options = reasoningOptionsFromCapability(caps)
    expect(presetReasoningOption(options, 'fast', caps)?.value).toBe('economy')
    expect(presetReasoningOption(options, 'balanced', caps)?.value).toBe('normal')
    expect(presetReasoningOption(options, 'deep', caps)?.value).toBe('turbo')
  })
  it('uses thinking modes when the provider does not expose effort levels', () => {
    const options = reasoningOptionsFromCapability(null)
    expect(presetReasoningOption(options, 'fast', null)?.value).toBe('disabled')
    expect(presetReasoningOption(options, 'balanced', null)?.value).toBe('standard')
    expect(presetReasoningOption(options, 'deep', null)?.value).toBe('deep')
  })
})
