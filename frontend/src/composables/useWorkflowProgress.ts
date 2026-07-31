import { computed, onScopeDispose, readonly, ref } from 'vue'
import { workflowApi, type WorkflowProgress } from '@/services/api/workflow'

type PollingState =
  | 'idle'
  | 'starting'
  | 'polling'
  | 'temporarily_disconnected'
  | 'terminal'
  | 'stopped'

interface StartOptions {
  fresh?: boolean
}

export interface UseWorkflowProgressOptions {
  intervalMs?: number
  maxConsecutiveErrors?: number
  onTerminal?: (progress: WorkflowProgress) => void | Promise<void>
  onProgressChanged?: (
    current: WorkflowProgress,
    previous: WorkflowProgress | null
  ) => void
  request?: (
    runId: string,
    options?: { signal?: AbortSignal }
  ) => Promise<WorkflowProgress>
}

const TERMINAL_PHASES = new Set(['completed', 'failed', 'cancelled'])
const TERMINAL_STATUSES = new Set(['completed', 'failed', 'cancelled'])

const httpStatusOf = (error: unknown): number | undefined => {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const response = (error as { response?: { status?: unknown } }).response
  return typeof response?.status === 'number' ? response.status : undefined
}

export function useWorkflowProgress(options: UseWorkflowProgressOptions = {}) {
  const intervalMs = Math.max(1000, options.intervalMs ?? 2000)
  const maxConsecutiveErrors = Math.max(1, options.maxConsecutiveErrors ?? 6)
  const request = options.request ?? workflowApi.getWorkflowProgress

  const progress = ref<WorkflowProgress | null>(null)
  const state = ref<PollingState>('idle')
  const isLoading = ref(false)
  const isRefreshing = ref(false)
  const syncError = ref<string | null>(null)
  const consecutiveErrors = ref(0)
  const runId = ref<string | null>(null)

  let timer: ReturnType<typeof setTimeout> | null = null
  let controller: AbortController | null = null
  let requestInFlight = false
  let generation = 0
  let terminalNotifiedGeneration = -1
  let remainingFreshNotFoundRetries = 0

  const clearTimer = () => {
    if (timer !== null) {
      clearTimeout(timer)
      timer = null
    }
  }

  const invalidateRequest = () => {
    generation += 1
    controller?.abort()
    controller = null
    requestInFlight = false
  }

  const isTerminalProgress = (value: WorkflowProgress) =>
    TERMINAL_PHASES.has(value.phase) || TERMINAL_STATUSES.has(value.status)

  const schedule = (delayMs: number, expectedGeneration: number) => {
    clearTimer()
    if (expectedGeneration !== generation || state.value === 'terminal' || state.value === 'stopped') return
    timer = setTimeout(() => {
      timer = null
      void refresh()
    }, delayMs)
  }

  const notifyTerminal = (value: WorkflowProgress, expectedGeneration: number) => {
    if (!options.onTerminal || terminalNotifiedGeneration === expectedGeneration) return
    terminalNotifiedGeneration = expectedGeneration
    void Promise.resolve(options.onTerminal(value)).catch(() => undefined)
  }

  const refresh = async (): Promise<void> => {
    const requestedRunId = runId.value
    if (!requestedRunId || requestInFlight || state.value === 'terminal' || state.value === 'stopped') return

    const requestGeneration = generation
    requestInFlight = true
    controller = new AbortController()
    isLoading.value = progress.value === null
    isRefreshing.value = progress.value !== null

    try {
      const response = await request(requestedRunId, { signal: controller.signal })
      if (requestGeneration !== generation || requestedRunId !== runId.value) return

      const previous = progress.value
      progress.value = response
      try {
        options.onProgressChanged?.(response, previous)
      } catch {
        // UI projection callbacks must not break successful progress synchronization.
      }
      syncError.value = null
      consecutiveErrors.value = 0
      state.value = isTerminalProgress(response) ? 'terminal' : 'polling'

      if (state.value === 'terminal') {
        clearTimer()
        notifyTerminal(response, requestGeneration)
      } else {
        schedule(intervalMs, requestGeneration)
      }
    } catch (error: unknown) {
      if (requestGeneration !== generation || requestedRunId !== runId.value) return

      const status = httpStatusOf(error)
      if (status === 404) {
        if (remainingFreshNotFoundRetries > 0) {
          remainingFreshNotFoundRetries -= 1
          syncError.value = '运行记录尚未可见，正在短暂重试'
          consecutiveErrors.value += 1
          state.value = 'temporarily_disconnected'
          schedule(1000, requestGeneration)
        } else {
          syncError.value = '该运行记录不存在或当前账户无权访问'
          consecutiveErrors.value += 1
          state.value = 'stopped'
          clearTimer()
        }
      } else {
        consecutiveErrors.value += 1
        syncError.value = '进度同步暂时中断，正在重试'
        state.value = 'temporarily_disconnected'
        const cappedErrors = Math.min(consecutiveErrors.value, maxConsecutiveErrors)
        schedule(cappedErrors >= 3 ? 4500 : intervalMs, requestGeneration)
      }
    } finally {
      if (requestGeneration === generation) {
        requestInFlight = false
        controller = null
        isLoading.value = false
        isRefreshing.value = false
      }
    }
  }

  const start = async (nextRunId: string, startOptions: StartOptions = {}): Promise<void> => {
    clearTimer()
    invalidateRequest()
    progress.value = null
    syncError.value = null
    consecutiveErrors.value = 0
    runId.value = nextRunId
    state.value = 'starting'
    remainingFreshNotFoundRetries = startOptions.fresh ? 2 : 0
    terminalNotifiedGeneration = -1
    await refresh()
  }

  const stop = () => {
    clearTimer()
    invalidateRequest()
    state.value = 'stopped'
    isLoading.value = false
    isRefreshing.value = false
  }

  const reset = () => {
    stop()
    progress.value = null
    syncError.value = null
    consecutiveErrors.value = 0
    runId.value = null
    state.value = 'idle'
  }

  const phase = computed(() => progress.value?.phase ?? null)
  const percent = computed(() => progress.value?.percent ?? null)
  const isIndeterminate = computed(() => progress.value !== null && progress.value.percent === null)
  const isTerminal = computed(() => state.value === 'terminal')
  const isRunning = computed(() =>
    state.value === 'starting' || state.value === 'polling' || state.value === 'temporarily_disconnected'
  )
  const isWaitingReview = computed(() =>
    progress.value?.phase === 'review' || progress.value?.status === 'waiting_review'
  )
  const isRecovering = computed(() => progress.value?.phase === 'recovery')

  onScopeDispose(() => reset())

  return {
    progress: readonly(progress),
    phase,
    percent,
    isIndeterminate,
    isRunning,
    isTerminal,
    isWaitingReview,
    isRecovering,
    isLoading: readonly(isLoading),
    isRefreshing: readonly(isRefreshing),
    syncError: readonly(syncError),
    consecutiveErrors: readonly(consecutiveErrors),
    runId: readonly(runId),
    start,
    stop,
    refresh,
    reset
  }
}
