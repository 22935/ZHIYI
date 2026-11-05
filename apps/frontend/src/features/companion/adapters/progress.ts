import { workflowApi } from '@/services/api/workflow'
import { EMPTY_PROGRESS } from '../types'
import type { ProgressPort, ProgressSnapshot } from '../types'

export const COMPANION_RUN_STORAGE_KEY = 'companion.active_run_id.v1'

/** 从路由 query（Web search 或 Electron hash）或本地锚点解析当前 runId。 */
export function parseRunIdFromLocation(href: string): string | null {
  const queryIndex = href.indexOf('?')
  if (queryIndex === -1) return null
  const query = href.slice(queryIndex + 1).split('#')[0]
  const params = new URLSearchParams(query)
  return params.get('runId') || params.get('run_id') || null
}

export class WorkflowProgressPort implements ProgressPort {
  resolveRunId(): string | null {
    let fromLocation: string | null = null
    try {
      fromLocation = parseRunIdFromLocation(window.location.href)
      if (!fromLocation && window.location.hash) {
        fromLocation = parseRunIdFromLocation(window.location.hash)
      }
    } catch {
      fromLocation = null
    }
    if (fromLocation) return fromLocation
    try {
      return localStorage.getItem(COMPANION_RUN_STORAGE_KEY) || null
    } catch {
      return null
    }
  }

  async read(runId: string, signal?: AbortSignal): Promise<ProgressSnapshot> {
    try {
      const raw = await workflowApi.getWorkflowProgress(runId, signal ? { signal } : {}) as Record<string, unknown>
      const num = (key: string, fallback = 0): number => {
        const value = raw[key]
        return typeof value === 'number' && Number.isFinite(value) ? value : fallback
      }
      const str = (key: string): string => typeof raw[key] === 'string' ? raw[key] as string : ''
      const arr = (key: string): string[] => Array.isArray(raw[key])
        ? (raw[key] as unknown[]).filter((item): item is string => typeof item === 'string')
        : []
      return {
        runId,
        status: str('status'),
        phase: str('phase'),
        percent: num('percent', num('percentage')),
        completedSteps: num('completedSteps'),
        totalSteps: num('totalSteps'),
        activeStepIds: arr('activeStepIds'),
        waitingReviewSteps: num('waitingReviewSteps'),
        failedSteps: num('failedSteps'),
        message: str('message'),
        available: true
      }
    } catch {
      return { ...EMPTY_PROGRESS, runId }
    }
  }
}
