import { describe, expect, it } from 'vitest'
import { ACG_PROMPT_PRESETS, DEFAULT_ACG_PROMPT_PRESET } from './acgPromptPresets'

describe('ACG test prompt presets', () => {
  it('provides a stable default and unique editable preset records', () => {
    expect(ACG_PROMPT_PRESETS.length).toBeGreaterThan(0)
    expect(ACG_PROMPT_PRESETS[0]).toBe(DEFAULT_ACG_PROMPT_PRESET)
    expect(new Set(ACG_PROMPT_PRESETS.map(preset => preset.id)).size).toBe(ACG_PROMPT_PRESETS.length)
    expect(ACG_PROMPT_PRESETS.every(preset => preset.contractText.trim() && preset.userIntent.trim())).toBe(true)
  })
})
