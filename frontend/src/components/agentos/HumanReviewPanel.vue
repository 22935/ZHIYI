<!-- 人工审核面板 — 提交审批/驳回/需补充信息的表单，含审核人名称和评论 -->
<template>
  <section class="human-review-panel ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><EditPen /></el-icon>
        <h3>人工审核</h3>
      </div>
      <span :class="{ active: canReview }">{{ canReview ? '可处理' : '无待审节点' }}</span>
    </div>

    <div v-if="!run" class="empty">选择运行记录后提交审核</div>

    <template v-else>
      <form class="review-form" @submit.prevent="submit">
        <label>
          <span>步骤</span>
          <select v-model="stepId" :disabled="!run.steps.length">
            <option v-for="step in run.steps" :key="step.stepId" :value="step.stepId">
              {{ step.name }} · {{ step.stepId }}
            </option>
          </select>
        </label>

        <label>
          <span>决定</span>
          <select v-model="decision">
            <option value="approved">通过</option>
            <option value="rejected">驳回</option>
            <option value="need_more_info">补充信息</option>
          </select>
        </label>

        <label>
          <span>审核人</span>
          <input v-model="reviewer" placeholder="reviewer" />
        </label>

        <label>
          <span>意见</span>
          <textarea v-model="comment" rows="3" placeholder="填写审核意见" />
        </label>

        <button type="submit" :disabled="submitting || !stepId">
          <el-icon><Check /></el-icon>
          {{ submitting ? '提交中...' : '提交审核' }}
        </button>
      </form>

      <div class="review-history">
        <div class="history-head">
          <strong>审核记录</strong>
          <span>{{ reviews.length }} 条</span>
        </div>
        <div v-if="loading" class="empty">正在加载审核记录...</div>
        <div v-else-if="!reviews.length" class="empty">暂无审核记录</div>
        <template v-else>
          <article v-for="record in reviews" :key="record.reviewId" class="review-record">
            <div>
              <strong>{{ decisionLabel(record.decision) }}</strong>
              <span>{{ record.stepId }} · {{ record.reviewer }}</span>
            </div>
            <time>{{ formatTime(record.createdAt) }}</time>
            <p v-if="record.comment">{{ record.comment }}</p>
          </article>
        </template>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Check, EditPen } from '@element-plus/icons-vue'
import type { ReviewDecision, ReviewRecord, ReviewRequest, WorkflowRun } from '@/services/api/workflow'

const props = defineProps<{
  run: WorkflowRun | null
  reviews: ReviewRecord[]
  loading?: boolean
  submitting?: boolean
}>()

const emit = defineEmits<{
  submit: [payload: ReviewRequest]
}>()

const stepId = ref('')
const decision = ref<ReviewDecision>('approved')
const reviewer = ref(localStorage.getItem('userId') || 'console_reviewer')
const comment = ref('')

const canReview = computed(() => props.run?.status === 'waiting_review')

watch(
  () => props.run,
  run => {
    const preferred = run?.steps.find(step => step.status === 'waiting_review') || run?.steps.find(step => step.stepId === run.currentStepId)
    stepId.value = preferred?.stepId || run?.currentStepId || run?.steps[0]?.stepId || ''
    decision.value = 'approved'
    comment.value = ''
  },
  { immediate: true }
)

const submit = () => {
  if (!stepId.value) return
  emit('submit', {
    stepId: stepId.value,
    decision: decision.value,
    reviewer: reviewer.value || 'console_reviewer',
    comment: comment.value
  })
}

const decisionLabel = (value: ReviewDecision) => {
  const labels: Record<ReviewDecision, string> = {
    approved: '通过',
    rejected: '驳回',
    need_more_info: '补充信息',
    rerun: '重跑',
    cancelled: '取消'
  }
  return labels[value] || value
}

const formatTime = (value?: string) => {
  if (!value) return ''
  return new Date(value).toLocaleString()
}
</script>

<style scoped>
.human-review-panel {
  min-width: 0;
}

.section-head,
.history-head,
.review-record > div:first-child {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.section-head {
  margin-bottom: 12px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
}

h3,
p {
  margin: 0;
}

h3 {
  color: var(--text-primary);
  font-size: 15px;
}

.section-head span,
.history-head span,
.empty,
time,
p {
  color: var(--text-secondary);
  font-size: 12px;
}

.section-head span.active {
  color: var(--warning);
  font-weight: 700;
}

.review-form {
  display: grid;
  gap: 10px;
}

label {
  display: grid;
  gap: 5px;
}

label span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

select,
input,
textarea {
  width: 100%;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: var(--transition);
}

select,
input {
  height: 34px;
  padding: 0 9px;
}

textarea {
  min-height: 72px;
  padding: 9px;
  resize: vertical;
}

select:focus,
input:focus,
textarea:focus {
  background: var(--surface-solid);
  border-color: var(--primary-line);
  box-shadow: 0 0 0 3px var(--primary-fade);
}

button {
  height: 34px;
  border: 0;
  border-radius: 8px;
  background: var(--primary-color);
  color: #fff;
  cursor: pointer;
  font-weight: 700;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: var(--transition);
}

button:hover:not(:disabled) {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.review-history {
  display: grid;
  gap: 8px;
  margin-top: 16px;
}

.history-head strong,
.review-record strong {
  color: var(--text-primary);
  font-size: 13px;
}

.review-record {
  display: grid;
  gap: 6px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.review-record span {
  color: var(--text-secondary);
  font-size: 12px;
}

p {
  overflow-wrap: anywhere;
}
</style>
