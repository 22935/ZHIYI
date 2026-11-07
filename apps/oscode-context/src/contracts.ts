/** OScode-owned contracts, independent of Cordis, DSH Session and any Provider. */
export type Message = Record<string, any>
export const VERSION = 'oscode-context.v1'
export const SUMMARY_FIELDS = ['goals', 'facts', 'constraints', 'completed', 'decisions', 'unresolved', 'references', 'tool_results'] as const
export type Summary = Record<typeof SUMMARY_FIELDS[number], string[]>
export type Summarize = (text: string, maxTokens: number, instruction: string) => Promise<{ text: string; totalTokens?: number }>

export interface Budget {
  contextWindow: number
  outputReserve: number
  safetyMargin: number
}
export interface Config {
  triggerRatio: number
  targetRatio: number
  retainTurns: number
  retainRatio: number
  summaryMaxTokens: number
  maxSummaryCalls: number
  thresholdChars: number
  headChars: number
  tailChars: number
}
export const DEFAULTS: Readonly<Config> = Object.freeze({
  triggerRatio: .85, targetRatio: .65, retainTurns: 2, retainRatio: .20,
  summaryMaxTokens: 2048, maxSummaryCalls: 16,
  thresholdChars: 8192, headChars: 4096, tailChars: 1024,
})
export interface ProjectionRequest {
  /** Explicit /compact request; still respects protected turns and hard limits. */
  force?: boolean
  contextId: string
  provider: string
  model: string
  messages: Message[]
  instructions: string
  tools: Record<string, unknown>[]
  budget: Budget
}
export interface Projection {
  messages: Message[]
  status: 'unchanged' | 'pruned' | 'summarized' | 'no_safe_range' | 'failed_passthrough'
  metrics: Record<string, number | string | boolean>
  snapshot?: Record<string, unknown>
}
export class CompactionError extends Error {}

/** DSH model-window/output-reserve budgeting, with a separate safety margin. */
export function inputLimit(budget: Budget): number {
  const { contextWindow, outputReserve, safetyMargin } = budget
  if (![contextWindow, outputReserve, safetyMargin].every(Number.isSafeInteger)
    || contextWindow < 1 || outputReserve < 1 || safetyMargin < 0
    || outputReserve + safetyMargin >= contextWindow) throw new CompactionError('Invalid context budget')
  return contextWindow - outputReserve - safetyMargin
}
export function resolveConfig(overrides: Partial<Config> = {}): Config {
  for (const key of Object.keys(overrides)) if (!(key in DEFAULTS)) throw new CompactionError(`Unknown compaction config ${key}`)
  const config = { ...DEFAULTS, ...overrides }
  if (!(config.targetRatio > 0 && config.targetRatio < config.triggerRatio && config.triggerRatio < 1)
    || !(config.retainRatio >= 0 && config.retainRatio < config.targetRatio)) throw new CompactionError('Invalid hysteresis/retention ratios')
  for (const key of ['retainTurns', 'summaryMaxTokens', 'maxSummaryCalls', 'thresholdChars'] as const) {
    if (!Number.isSafeInteger(config[key]) || config[key] < 1) throw new CompactionError(`Invalid ${key}`)
  }
  for (const key of ['headChars', 'tailChars'] as const) if (!Number.isSafeInteger(config[key]) || config[key] < 0) throw new CompactionError(`Invalid ${key}`)
  if (config.headChars + config.tailChars + 50 > config.thresholdChars) throw new CompactionError('Pruning replacement exceeds threshold')
  return config
}
