<template>
  <main class="contract-review-workbench ui-shell">
    <header class="workbench-header ui-hero">
      <div class="workbench-title">
        <span class="ui-icon-badge">
          <el-icon><DocumentChecked /></el-icon>
        </span>
        <div>
          <span class="ui-hero__eyebrow">Zhiyi AgentOS Legal</span>
          <h1 class="ui-hero__title">律师合同审查</h1>
          <p class="ui-hero__subtitle">基于 WorkflowRun、Trace、Artifacts 与 Human Review 的合同审查工作台。</p>
        </div>
      </div>
      <button class="header-action" type="button" :disabled="!selectedRun || loading.detail" @click="refreshSelectedRun">
        <el-icon><Refresh /></el-icon>
        <span>刷新</span>
      </button>
    </header>

    <section class="workbench-layout">
      <section class="workbench-main">
        <section class="contract-input-panel ui-surface ui-surface--pad">
          <div class="section-head">
            <div class="section-title">
              <el-icon><DocumentChecked /></el-icon>
              <h3>合同文本</h3>
            </div>
            <span>{{ selectedWorkflowId }}</span>
          </div>
          <label class="workflow-select">
            <span>Workflow</span>
            <select v-model="selectedWorkflowId" :disabled="loading.start">
              <option v-for="item in workflowOptions" :key="item.value" :value="item.value">
                {{ item.label }}
              </option>
            </select>
          </label>
          <textarea
            v-model="contractText"
            :disabled="loading.start"
            placeholder="粘贴待审查合同文本"
            rows="9"
          />
          <div class="input-actions">
            <button type="button" class="primary-action" :disabled="loading.start || !contractText.trim()" @click="startContractReview">
              <el-icon><Check /></el-icon>
              <span>{{ loading.start ? '启动中...' : '启动审查 Workflow' }}</span>
            </button>
            <span v-if="selectedRun">当前运行：{{ selectedRun.runId }}</span>
          </div>
        </section>

        <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>

        <WorkflowRunPanel
          :run="selectedRun"
          :metrics="metrics"
          :loading="loading.detail"
          @refresh="refreshSelectedRun"
          @export-trace="exportTrace"
        />

        <WorkflowStepList
          :steps="selectedRun?.steps || []"
          :current-step-id="selectedRun?.currentStepId"
        />

        <ContractRiskPanel :risks="contractArtifacts.risks" />
        <ContractEvidencePanel :evidences="contractArtifacts.evidences" />
        <ContractReportPreview :report-markdown="contractArtifacts.reportMarkdown" />
      </section>

      <aside class="workbench-side">
        <section class="artifact-path-panel ui-surface ui-surface--pad">
          <div class="section-head">
            <div class="section-title">
              <el-icon><DocumentChecked /></el-icon>
              <h3>Artifact 路径</h3>
            </div>
          </div>
          <dl>
            <div>
              <dt>risks</dt>
              <dd>{{ contractArtifacts.paths.risks }}</dd>
            </div>
            <div>
              <dt>evidences</dt>
              <dd>{{ contractArtifacts.paths.evidences }}</dd>
            </div>
            <div>
              <dt>report</dt>
              <dd>{{ contractArtifacts.paths.reportMarkdown }}</dd>
            </div>
          </dl>
        </section>

        <HumanReviewPanel
          :run="selectedRun"
          :reviews="reviews"
          :loading="loading.reviews"
          :submitting="loading.reviewSubmit"
          @submit="submitReview"
        />

        <CheckpointPanel
          :checkpoints="checkpoints"
          :loading="loading.checkpoints"
          @resume="resumeFromCheckpoint"
        />

        <TraceEventTimeline
          :events="traceEvents"
          :loading="loading.trace"
          @export-markdown="exportTrace"
        />
      </aside>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Check, DocumentChecked, Refresh } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import CheckpointPanel from '@/components/agentos/CheckpointPanel.vue'
import ContractEvidencePanel from '@/components/agentos/ContractEvidencePanel.vue'
import ContractReportPreview from '@/components/agentos/ContractReportPreview.vue'
import ContractRiskPanel from '@/components/agentos/ContractRiskPanel.vue'
import HumanReviewPanel from '@/components/agentos/HumanReviewPanel.vue'
import TraceEventTimeline from '@/components/agentos/TraceEventTimeline.vue'
import WorkflowRunPanel from '@/components/agentos/WorkflowRunPanel.vue'
import WorkflowStepList from '@/components/agentos/WorkflowStepList.vue'
import { workflowApi, type Checkpoint, type EvaluationRun, type ReviewRecord, type ReviewRequest, type TraceEvent, type WorkflowRun } from '@/services/api/workflow'
import { extractContractReviewArtifacts } from '@/utils/agentos/contractReviewArtifactExtractor'

const workflowOptions = [
  { label: 'StateGraph Runtime', value: 'legal_contract_review_stategraph_v1' },
  { label: 'AgentOS Native Migration', value: 'legal_contract_review_langgraph_v1' }
]

const defaultContractText = `甲方委托乙方开发 CRM 系统，合同约定签署后支付 30%，系统上线后支付 70%。
如无重大问题视为验收通过，项目源代码归双方共同所有。`

const contractText = ref(defaultContractText)
const selectedWorkflowId = ref(workflowOptions[0].value)
const selectedRun = ref<WorkflowRun | null>(null)
const traceEvents = ref<TraceEvent[]>([])
const checkpoints = ref<Checkpoint[]>([])
const reviews = ref<ReviewRecord[]>([])
const metrics = ref<EvaluationRun | null>(null)
const errorMessage = ref('')

const loading = reactive({
  start: false,
  detail: false,
  trace: false,
  checkpoints: false,
  reviews: false,
  reviewSubmit: false
})

const contractArtifacts = computed(() => extractContractReviewArtifacts(selectedRun.value))

const loadRunAuxiliaryData = async (run: WorkflowRun) => {
  await Promise.allSettled([
    loadTrace(run.runId),
    loadCheckpoints(run.runId),
    loadReviews(run.runId),
    loadMetrics(run)
  ])
}

const refreshRunUntilStable = async (runId: string) => {
  let latest = await workflowApi.getRun(runId)
  selectedRun.value = latest

  for (let index = 0; index < 4 && ['pending', 'planning', 'running'].includes(latest.status); index += 1) {
    await new Promise(resolve => window.setTimeout(resolve, 800))
    latest = await workflowApi.getRun(runId)
    selectedRun.value = latest
  }

  await loadRunAuxiliaryData(latest)
}

const startContractReview = async () => {
  if (!contractText.value.trim()) return
  loading.start = true
  errorMessage.value = ''
  try {
    const response = await workflowApi.startWorkflow({
      title: '律师合同审查',
      domain: 'legal',
      intent: selectedWorkflowId.value === 'legal_contract_review_stategraph_v1'
        ? 'contract_review_stategraph'
        : 'contract_review_langgraph',
      workflowId: selectedWorkflowId.value,
      reviewMode: 'human_in_loop',
      input: {
        source: 'workbench',
        contractText: contractText.value.trim()
      }
    })
    selectedRun.value = response.run
    await refreshRunUntilStable(response.run.runId)
    if (selectedRun.value?.status === 'waiting_review' && selectedRun.value.currentStepId === 'human_review') {
      ElMessage.success('Workflow 已执行到 human_review:waiting_review')
    }
  } catch (error: any) {
    errorMessage.value = error?.message || '启动合同审查 Workflow 失败'
  } finally {
    loading.start = false
  }
}

const refreshSelectedRun = async () => {
  if (!selectedRun.value) return
  loading.detail = true
  errorMessage.value = ''
  try {
    await refreshRunUntilStable(selectedRun.value.runId)
  } catch (error: any) {
    errorMessage.value = error?.message || '刷新 WorkflowRun 失败'
  } finally {
    loading.detail = false
  }
}

const loadTrace = async (runId: string) => {
  loading.trace = true
  try {
    const payload = await workflowApi.getTrace(runId)
    traceEvents.value = payload.events || []
  } finally {
    loading.trace = false
  }
}

const loadCheckpoints = async (runId: string) => {
  loading.checkpoints = true
  try {
    const payload = await workflowApi.listCheckpoints(runId)
    checkpoints.value = payload.items || []
  } finally {
    loading.checkpoints = false
  }
}

const loadReviews = async (runId: string) => {
  loading.reviews = true
  try {
    const payload = await workflowApi.listReviews(runId)
    reviews.value = payload.items || []
  } finally {
    loading.reviews = false
  }
}

const loadMetrics = async (run: WorkflowRun) => {
  metrics.value = await workflowApi.getMetrics({
    domain: 'legal',
    workflowId: run.workflowId,
    source: 'workbench'
  })
}

const submitReview = async (payload: ReviewRequest) => {
  if (!selectedRun.value) return
  loading.reviewSubmit = true
  errorMessage.value = ''
  try {
    const reviewed = await workflowApi.submitReview(selectedRun.value.runId, payload)
    selectedRun.value = reviewed
    await refreshRunUntilStable(reviewed.runId)
    if (contractArtifacts.value.reportMarkdown) {
      ElMessage.success('审核已提交，报告已生成')
    }
  } catch (error: any) {
    errorMessage.value = error?.message || '提交人工审核失败'
  } finally {
    loading.reviewSubmit = false
  }
}

const resumeFromCheckpoint = async (checkpointId: string) => {
  if (!selectedRun.value) return
  loading.detail = true
  errorMessage.value = ''
  try {
    const resumed = await workflowApi.resumeFromCheckpoint(selectedRun.value.runId, checkpointId)
    selectedRun.value = resumed
    await refreshRunUntilStable(resumed.runId)
  } catch (error: any) {
    errorMessage.value = error?.message || '恢复 WorkflowRun 失败'
  } finally {
    loading.detail = false
  }
}

const exportTrace = async () => {
  if (!selectedRun.value) return
  const markdown = await workflowApi.exportTraceMarkdown(selectedRun.value.runId)
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `contract-review-trace-${selectedRun.value.runId}.md`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.contract-review-workbench {
  min-height: 100%;
  color: var(--text-primary);
  overflow: auto;
}

.workbench-header {
  flex-shrink: 0;
}

.workbench-title {
  display: flex;
  align-items: flex-start;
  gap: 14px;
}

h1,
h3,
p,
dl,
dd {
  margin: 0;
}

.header-action,
.primary-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 8px;
  cursor: pointer;
  transition: var(--transition);
}

.header-action {
  height: 36px;
  padding: 0 14px;
  border: 1px solid var(--border-light);
  background: #fff;
  color: var(--text-primary);
}

.header-action:hover:not(:disabled) {
  border-color: var(--border-hover);
  color: var(--primary-color);
  transform: translateY(-1px);
}

.header-action:disabled,
.primary-action:disabled {
  cursor: not-allowed;
  opacity: 0.56;
}

.workbench-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 390px);
  gap: 16px;
  align-items: start;
}

.workbench-main,
.workbench-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.workbench-side {
  position: sticky;
  top: 16px;
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.section-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
}

h3 {
  color: var(--text-primary);
  font-size: 15px;
}

.section-head span,
.input-actions span,
dt,
dd {
  color: var(--text-secondary);
  font-size: 12px;
}

textarea {
  width: 100%;
  min-height: 190px;
  padding: 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
  outline: none;
  resize: vertical;
  transition: var(--transition);
}

select {
  width: 100%;
  height: 34px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: var(--transition);
}

.workflow-select {
  display: grid;
  gap: 5px;
  margin-bottom: 12px;
}

.workflow-select span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

textarea:focus {
  background: #fff;
  border-color: var(--primary-line);
  box-shadow: 0 0 0 3px var(--primary-fade);
}

select:focus {
  background: #fff;
  border-color: var(--primary-line);
  box-shadow: 0 0 0 3px var(--primary-fade);
}

.input-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 12px;
}

.primary-action {
  min-height: 36px;
  padding: 0 14px;
  border: 0;
  background: var(--primary-color);
  color: #fff;
  font-weight: 700;
}

.primary-action:hover:not(:disabled) {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

.error-message {
  padding: 10px;
  border: 1px solid rgba(178, 74, 74, 0.18);
  border-radius: 8px;
  color: var(--danger);
  background: rgba(178, 74, 74, 0.08);
  font-size: 13px;
}

.artifact-path-panel dl {
  display: grid;
  gap: 8px;
}

.artifact-path-panel div {
  display: grid;
  gap: 4px;
  padding: 9px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

dt {
  font-weight: 800;
}

dd {
  overflow-wrap: anywhere;
}

@media (max-width: 1160px) {
  .workbench-layout {
    grid-template-columns: 1fr;
  }

  .workbench-side {
    position: static;
  }
}

@media (max-width: 720px) {
  .contract-review-workbench {
    padding: 14px;
  }

  .workbench-header {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>
