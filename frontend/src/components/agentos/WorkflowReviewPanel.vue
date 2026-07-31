<template>
  <section class="workflow-review" :class="{ compact }" aria-labelledby="workflow-review-title">
    <header class="workflow-review__head">
      <div>
        <span class="workflow-review__state" aria-hidden="true"></span>
        <strong id="workflow-review-title">人工审核</strong>
      </div>
      <span>{{ canReview ? '等待处理' : '当前无需审核' }}</span>
    </header>

    <template v-if="canReview">
      <div class="workflow-review__summary" aria-live="polite">
        <span>当前步骤</span>
        <strong>{{ reviewStep?.name || reviewStepId }}</strong>
        <p>{{ reviewReason }}</p>
      </div>

      <label class="workflow-review__comment">
        <span>审核说明（可选）</span>
        <textarea
          v-model="comment"
          rows="3"
          maxlength="500"
          :disabled="review.isSubmitting.value"
          placeholder="记录批准依据或驳回原因"
        ></textarea>
      </label>

      <div class="workflow-review__actions">
        <button
          class="approve"
          type="button"
          :disabled="review.isSubmitting.value"
          @click="submit('approved')"
        >
          <el-icon><Check /></el-icon>
          <span>{{ review.isSubmitting.value ? '提交中' : '通过并继续' }}</span>
        </button>
        <button
          class="reject"
          type="button"
          :disabled="review.isSubmitting.value"
          @click="submit('rejected')"
        >
          <el-icon><Close /></el-icon>
          <span>驳回</span>
        </button>
      </div>
    </template>

    <p v-if="review.error.value" class="workflow-review__error" role="alert">
      {{ review.error.value }}
    </p>

    <div v-if="!compact && reviews.length" class="workflow-review__history">
      <strong>最近审核</strong>
      <ol>
        <li v-for="item in reviews.slice(-5).reverse()" :key="item.reviewId">
          <span>{{ decisionLabel(item.decision) }} · {{ item.stepId }}</span>
          <time>{{ formatTime(item.createdAt) }}</time>
          <p v-if="item.comment">{{ item.comment }}</p>
        </li>
      </ol>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch, type DeepReadonly } from 'vue'
import { Check, Close } from '@element-plus/icons-vue'
import {
  type ReviewDecision,
  type ReviewRecord,
  type WorkflowProgress,
  type WorkflowRun
} from '@/services/api/workflow'
import { useWorkflowReview } from '@/composables/useWorkflowReview'
import { isWorkflowReviewPending } from '@/utils/workflowReviewState'

const props = withDefaults(defineProps<{
  runId: string
  progress: DeepReadonly<WorkflowProgress> | null
  run?: DeepReadonly<WorkflowRun> | null
  reviews?: ReviewRecord[]
  compact?: boolean
}>(), {
  run: null,
  reviews: () => [],
  compact: false
})

const emit = defineEmits<{
  reviewed: [run: WorkflowRun]
  conflict: []
  error: [message: string]
}>()

const comment = ref('')
const review = useWorkflowReview({
  onReviewed: run => {
    comment.value = ''
    emit('reviewed', run)
  },
  onConflict: () => emit('conflict')
})

const reviewStep = computed(() => props.run?.steps.find(step => step.status === 'waiting_review')
  || props.run?.steps.find(step => step.stepId === props.progress?.currentStepId))
const reviewStepId = computed(() => reviewStep.value?.stepId
  || props.progress?.currentStepId
  || props.progress?.activeStepIds[0]
  || '')
const canReview = computed(() => Boolean(
  props.runId
  && reviewStepId.value
  && isWorkflowReviewPending(props.progress, props.run)
))
const reviewReason = computed(() => {
  if (props.run && typeof props.run.error === 'string' && props.run.error.trim()) return props.run.error
  return props.progress?.message || '该节点需要人工确认后才能继续执行。'
})

const submit = async (decision: 'approved' | 'rejected') => {
  if (!canReview.value || !reviewStepId.value) return
  const result = await review.submit({
    runId: props.runId,
    stepId: reviewStepId.value,
    decision,
    comment: comment.value.trim(),
    expectedRunUpdatedAt: props.run?.updatedAt || props.progress?.updatedAt || undefined
  })
  if (!result && review.error.value) emit('error', review.error.value)
}

watch(() => props.runId, () => {
  comment.value = ''
  review.reset()
})

const decisionLabel = (decision: ReviewDecision) => decision === 'approved'
  ? '通过'
  : decision === 'rejected' ? '驳回' : decision
const formatTime = (value?: string) => value ? new Date(value).toLocaleString('zh-CN') : ''

onBeforeUnmount(review.reset)
</script>

<style scoped>
.workflow-review {
  display: grid;
  gap: 12px;
  min-width: 0;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-primary);
}

.workflow-review.compact { gap: 9px; padding: 10px 12px; border-radius: 6px; }
.workflow-review__head,
.workflow-review__head > div,
.workflow-review__actions,
.workflow-review__history li > span:first-child {
  display: flex;
  align-items: center;
}
.workflow-review__head { justify-content: space-between; gap: 12px; }
.workflow-review__head > div { gap: 7px; }
.workflow-review__head strong { font-size: 14px; }
.workflow-review__head > span { color: var(--warning); font-size: 12px; font-weight: 700; }
.workflow-review__state { width: 7px; height: 7px; border-radius: 50%; background: var(--warning); }

.workflow-review__summary { display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 3px 10px; }
.workflow-review__summary > span,
.workflow-review__comment > span { color: var(--text-secondary); font-size: 12px; font-weight: 650; }
.workflow-review__summary strong { overflow-wrap: anywhere; font-size: 13px; }
.workflow-review__summary p { grid-column: 1 / -1; margin: 3px 0 0; color: var(--text-secondary); font-size: 12px; overflow-wrap: anywhere; }

.workflow-review__comment { display: grid; gap: 5px; }
.workflow-review__comment textarea {
  width: 100%; min-height: 68px; padding: 9px 10px; resize: vertical;
  border: 1px solid transparent; border-radius: 6px; outline: none;
  background: var(--bg-input); color: var(--text-primary); font: inherit; font-size: 13px;
}
.workflow-review__comment textarea:focus { border-color: var(--primary-line); box-shadow: 0 0 0 3px var(--primary-fade); }
.workflow-review__actions { gap: 8px; flex-wrap: wrap; }
.workflow-review__actions button {
  min-height: 34px; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  padding: 0 12px; border: 1px solid transparent; border-radius: 6px; cursor: pointer;
  font-weight: 700; transition: var(--transition);
}
.workflow-review__actions .approve { background: var(--primary-color); color: #fff; }
.workflow-review__actions .reject { border-color: var(--border-light); background: var(--surface-solid); color: var(--danger); }
.workflow-review__actions button:hover:not(:disabled) { transform: translateY(-1px); }
.workflow-review__actions button:disabled { cursor: not-allowed; opacity: 0.55; }
.workflow-review__error { margin: 0; color: var(--danger); font-size: 12px; }

.workflow-review__history { display: grid; gap: 8px; padding-top: 10px; border-top: 1px solid var(--border-light); }
.workflow-review__history > strong { font-size: 13px; }
.workflow-review__history ol { display: grid; gap: 7px; margin: 0; padding: 0; list-style: none; }
.workflow-review__history li { display: grid; grid-template-columns: 1fr auto; gap: 3px 8px; font-size: 12px; }
.workflow-review__history time { color: var(--text-secondary); }
.workflow-review__history p { grid-column: 1 / -1; margin: 0; color: var(--text-secondary); overflow-wrap: anywhere; }

@media (max-width: 520px) {
  .workflow-review__actions button { flex: 1 1 140px; }
  .workflow-review__history li { grid-template-columns: 1fr; }
}
</style>
