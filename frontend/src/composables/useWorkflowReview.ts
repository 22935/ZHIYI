import { readonly, ref } from 'vue'
import axios from 'axios'
import {
  workflowApi,
  type ReviewDecision,
  type ReviewRequest,
  type WorkflowRun
} from '@/services/api/workflow'

interface SubmitWorkflowReviewInput {
  runId: string
  stepId: string
  decision: Extract<ReviewDecision, 'approved' | 'rejected'>
  comment?: string
  expectedRunUpdatedAt?: string
}

interface UseWorkflowReviewOptions {
  onReviewed?: (run: WorkflowRun) => void | Promise<void>
  onConflict?: () => void | Promise<void>
}

const createOperationId = () => {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  return `review_${Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('')}`
}

export function useWorkflowReview(options: UseWorkflowReviewOptions = {}) {
  const isSubmitting = ref(false)
  const error = ref<string | null>(null)
  const conflict = ref(false)
  const lastDecision = ref<ReviewDecision | null>(null)
  let controller: AbortController | null = null
  let generation = 0
  let pendingKey = ''
  let pendingOperationId = ''

  const submit = async (input: SubmitWorkflowReviewInput): Promise<WorkflowRun | null> => {
    if (isSubmitting.value) return null
    const key = JSON.stringify([
      input.runId,
      input.stepId,
      input.decision,
      input.comment || '',
      input.expectedRunUpdatedAt || ''
    ])
    if (key !== pendingKey || !pendingOperationId) {
      pendingKey = key
      pendingOperationId = createOperationId()
    }

    const requestGeneration = ++generation
    controller?.abort()
    controller = new AbortController()
    isSubmitting.value = true
    error.value = null
    conflict.value = false
    const payload: ReviewRequest = {
      stepId: input.stepId,
      decision: input.decision,
      comment: input.comment || '',
      operationId: pendingOperationId,
      expectedRunUpdatedAt: input.expectedRunUpdatedAt,
      expectedStepStatus: 'waiting_review'
    }

    try {
      const run = await workflowApi.submitReview(input.runId, payload, { signal: controller.signal })
      if (requestGeneration !== generation) return null
      lastDecision.value = input.decision
      pendingKey = ''
      pendingOperationId = ''
      await options.onReviewed?.(run)
      return run
    } catch (requestError: unknown) {
      if (requestGeneration !== generation || axios.isCancel(requestError)) return null
      if (axios.isAxiosError(requestError) && requestError.response?.status === 409) {
        conflict.value = true
        error.value = '该审核状态已发生变化'
        pendingKey = ''
        pendingOperationId = ''
        await options.onConflict?.()
      } else if (axios.isAxiosError(requestError) && requestError.response?.status === 404) {
        error.value = '运行记录不存在或当前账户无权审核'
      } else {
        error.value = '审核提交暂时失败，请重试'
      }
      return null
    } finally {
      if (requestGeneration === generation) {
        controller = null
        isSubmitting.value = false
      }
    }
  }

  const reset = () => {
    generation += 1
    controller?.abort()
    controller = null
    isSubmitting.value = false
    error.value = null
    conflict.value = false
    lastDecision.value = null
    pendingKey = ''
    pendingOperationId = ''
  }

  return {
    isSubmitting: readonly(isSubmitting),
    error: readonly(error),
    conflict: readonly(conflict),
    lastDecision: readonly(lastDecision),
    submit,
    reset
  }
}
