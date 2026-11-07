import { localFetch } from '@/platform/api'
import { backendUrl } from './api'
import selectedAdapter from '@platform'
import type { PlatformAdapter, RuntimeStatus } from './types'

export const platform: PlatformAdapter = selectedAdapter

export const isDesktop = (): boolean => platform.platform === 'desktop'

export * from './api'
export * from './types'

/** Check the existing Backend readiness contract without starting or supervising Runtime processes. */
export async function checkRuntimeStatus(signal?: AbortSignal): Promise<RuntimeStatus> {
  try {
    const response = await localFetch(backendUrl('/health/ready'), {
      method: 'GET',
      headers: { Accept: 'application/json' },
      cache: 'no-store',
      signal
    })
    if (!response.ok) return 'offline'

    const body = await response.json().catch(() => null) as { status?: unknown } | null
    return body?.status === 'UP' ? 'online' : 'unknown'
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    return 'offline'
  }
}
