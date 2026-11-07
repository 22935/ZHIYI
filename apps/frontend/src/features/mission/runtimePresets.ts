import type { ModelCapability, ReasoningOption } from '@/config/modelSettings'

export type RuntimePreset = 'fast' | 'balanced' | 'deep'

/** Resolve against the current model's declared options, never invent a level. */
export function presetReasoningOption(options: ReasoningOption[], preset: RuntimePreset, capability: ModelCapability | null): ReasoningOption | undefined {
  const efforts = options.filter(option => option.kind === 'effort')
  const available = efforts.length ? efforts : options
  if (!available.length) return
  const preferred = preset === 'fast' ? ['low', 'minimal', 'disabled', 'standard']
    : preset === 'balanced' ? ['high', 'medium', 'standard'] : ['max', 'deep', 'high']
  for (const value of preferred) {
    const option = available.find(item => item.value === value)
    if (option) return option
  }
  if (preset === 'fast') return available[0]
  if (preset === 'deep') return available[available.length - 1]
  return available.find(item => item.value === capability?.defaultReasoningEffort)
    || available[Math.floor(available.length / 2)]
}
