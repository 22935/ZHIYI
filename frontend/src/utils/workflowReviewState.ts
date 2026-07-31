interface WorkflowReviewProgressLike {
  phase?: string | null
  status?: string | null
  waitingReviewSteps?: number | null
}

interface WorkflowReviewRunLike {
  status?: string | null
  steps?: ReadonlyArray<{ status?: string | null }> | null
}

const TERMINAL_STATES = new Set(['completed', 'failed', 'cancelled'])

export const isWorkflowReviewPending = (
  progress?: WorkflowReviewProgressLike | null,
  run?: WorkflowReviewRunLike | null
): boolean => {
  if (
    (progress?.status && TERMINAL_STATES.has(progress.status))
    || (progress?.phase && TERMINAL_STATES.has(progress.phase))
    || (run?.status && TERMINAL_STATES.has(run.status))
  ) return false

  return Boolean(
    progress?.phase === 'review'
    || progress?.status === 'waiting_review'
    || (progress?.waitingReviewSteps || 0) > 0
    || run?.status === 'waiting_review'
    || run?.steps?.some(step => step.status === 'waiting_review')
  )
}
