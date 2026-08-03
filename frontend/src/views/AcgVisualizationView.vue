<!-- 知弈OS 原生 ACG 工作台 — 专业语义通过编译期 Plugin UI Extension 增量注入。 -->
<template>
  <div class="acg-view ui-shell" :class="{ 'has-progress': isSubmitting || progressTracker.progress.value || progressTracker.syncError.value, 'has-run': !!activeRunId, 'is-draft': !activeRunId }">
    <header class="ui-hero ui-hero--compact">
      <div class="hero-left">
        <div class="ui-icon-badge"><el-icon><Cpu /></el-icon></div>
        <h3>ACG 动态群体智能引擎</h3>
      </div>
      <div class="hero-right">
        <span class="hero-run-chip" :title="activeRunId || '尚未创建运行'">
          <span>RUN</span>
          <code>{{ activeRunId || '—' }}</code>
        </span>
        <button class="hero-icon-action" type="button" title="复制 Run ID" aria-label="复制 Run ID" :disabled="!activeRunId" @click="copyRunId">
          <el-icon><CopyDocument /></el-icon>
        </button>
        <button class="hero-operations" type="button" @click="openOperations">
          <el-icon><Monitor /></el-icon>
          <span>运维查看</span>
        </button>
        <el-tag :type="statusTagType" effect="plain">{{ statusLabel }}</el-tag>
        <el-tag class="hero-engine" effect="plain">engine: acg</el-tag>
      </div>
    </header>

    <!-- 控制台 -->
    <section class="ui-surface ui-surface--pad control-bar" :class="{ collapsed: inputPanelCompact }">
      <button
        class="input-panel-toggle"
        type="button"
        :title="inputPanelExpanded ? '收起任务配置' : '展开任务配置'"
        :aria-label="inputPanelExpanded ? '收起任务配置' : '展开任务配置'"
        :aria-expanded="inputPanelExpanded"
        @click="inputPanelExpanded = !inputPanelExpanded"
      >
        <el-icon><ArrowUp v-if="inputPanelExpanded" /><ArrowDown v-else /></el-icon>
      </button>
      <div v-if="inputPanelCompact" class="input-summary">
        <span class="input-summary__copy">
          <el-icon><Document /></el-icon>
          <strong>{{ taskName || '未命名 ACG 任务' }}</strong>
          <small>任务材料 · {{ contractText.length.toLocaleString('zh-CN') }} 字｜{{ planningModeSummary }}｜{{ activePluginSummary }}</small>
        </span>
      </div>
      <Transition
        :duration="380"
        @before-enter="beforeInputPanelEnter"
        @enter="enterInputPanel"
        @after-enter="afterInputPanelEnter"
        @before-leave="beforeInputPanelLeave"
        @leave="leaveInputPanel"
        @after-leave="afterInputPanelLeave"
      >
        <div v-show="inputPanelExpanded" class="input-panel-expandable">
      <div class="workbench-identity">
        <div><strong>知弈OS 原生任务工作台</strong><small>默认只使用 Native 能力；专业能力包按 Run 显式启用</small></div>
        <el-tag effect="plain">Native Core</el-tag>
      </div>
      <div class="input-fields">
        <div class="input-pane contract-pane">
          <span class="pane-heading">任务材料</span>
          <div class="ctrl-row">
            <label class="ctrl-label">文本材料（可选）</label>
            <el-input class="contract-textarea" v-model="contractText" type="textarea" :autosize="{ minRows: 6, maxRows: 14 }" placeholder="粘贴需求、背景资料、研究材料或其他任务上下文" />
          </div>
          <div class="contract-upload" :class="{ dragging: uploadDragging, populated: selectedContractFile, loading: loading.upload }" @dragenter.prevent="uploadDragging = true" @dragover.prevent="uploadDragging = true" @dragleave.prevent="uploadDragging = false" @drop.prevent="handleContractDrop">
            <input ref="contractFileInput" class="contract-file-input" type="file" accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown" @change="handleContractFileSelection" />
            <span class="contract-upload__icon" aria-hidden="true"><el-icon><Document v-if="selectedContractFile" /><UploadFilled v-else /></el-icon></span>
            <span class="contract-upload__copy">
              <strong>{{ selectedContractFile?.originalFilename || (uploadState === 'parsing' ? '正在解析任务文件' : loading.upload ? '正在上传任务文件' : '补充任务文件') }}</strong>
              <small v-if="selectedContractFile">{{ formatFileSize(selectedContractFile.size) }} · 已提取 {{ selectedContractFile.textLength.toLocaleString('zh-CN') }} 字</small>
              <small v-if="uploadError" class="contract-upload__error">{{ uploadError }}</small>
              <small v-else-if="!selectedContractFile">拖放到此处，或选择 PDF、DOCX、TXT、MD，最大 10MB</small>
            </span>
            <span class="contract-upload__actions">
              <el-button size="small" :loading="loading.upload" @click="openContractFilePicker"><el-icon><UploadFilled /></el-icon>{{ selectedContractFile ? '替换文件' : '选择文件' }}</el-button>
              <el-button v-if="selectedContractFile" circle size="small" title="移除任务文件" aria-label="移除任务文件" @click="clearContractFile"><el-icon><Delete /></el-icon></el-button>
            </span>
          </div>
        </div>
        <div class="input-pane definition-pane">
          <span class="pane-heading">任务定义</span>
          <label class="ctrl-label">任务名称</label>
          <el-input v-model="taskName" placeholder="为本次任务命名" />
          <div class="ctrl-row">
            <label class="ctrl-label">任务目标</label>
            <el-input class="intent-textarea" v-model="userIntent" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" placeholder="描述目标、范围和成功标准" />
          </div>
          <label class="ctrl-label">执行约束</label>
          <el-input v-model="constraintsText" placeholder="使用逗号分隔，例如：两周内完成、控制预算" />
          <label class="ctrl-label">预期交付物</label>
          <el-input v-model="expectedArtifactsText" placeholder="使用逗号分隔，例如：实施方案、风险清单" />
        </div>
      </div>
      <section class="plugin-selector" aria-label="专业能力扩展">
        <header><div><strong>专业能力扩展（单选）</strong><small>Native Core 始终启用；每个 Run 最多叠加一个专业能力包</small></div><span v-if="pluginsLoading">正在读取...</span></header>
        <div class="plugin-options">
          <button type="button" class="plugin-card native-card" :class="{ selected: !draft.enabledPluginIds.length }" :aria-pressed="!draft.enabledPluginIds.length" :disabled="scopeLocked" @click="clearPlugins">
            <strong>Native Core · 始终启用</strong><small>{{ draft.enabledPluginIds.length ? '作为专业能力包的运行基础' : '当前仅使用通用规划、分析与交付能力' }}</small><code>不叠加专业能力包</code>
          </button>
          <button v-for="plugin in installedPlugins" :key="plugin.pluginId" type="button" class="plugin-card" :class="{ selected: draft.enabledPluginIds[0] === plugin.pluginId }" :aria-pressed="draft.enabledPluginIds[0] === plugin.pluginId" :disabled="scopeLocked || !plugin.available" @click="togglePlugin(plugin.pluginId)">
            <strong>{{ plugin.displayName }}</strong><small>{{ plugin.description }}</small><code>{{ plugin.pluginId }} · v{{ plugin.version }}</code>
          </button>
        </div>
      </section>
      <PluginExtensionHost :extensions="draftExtensions" :draft="draft" :readonly="scopeLocked" @update:plugin-data="draft.pluginData = $event" />
      <div v-if="advancedSettingsExpanded" class="advanced-settings">
        <label class="advanced-item">
          <span>图规划多样性</span>
          <el-select v-model="draft.planningDiversity" aria-label="图规划多样性">
            <el-option label="稳定（可重复）" value="stable" />
            <el-option label="均衡（推荐）" value="balanced" />
            <el-option label="探索（变化更大）" value="exploratory" />
          </el-select>
        </label>
        <label class="advanced-item">
          <span>随机种子（可选）</span>
          <el-input-number v-model="draft.planningSeed" :min="0" :max="2147483647" :controls="false" placeholder="留空则自动生成" />
        </label>
        <label v-if="activeRunId && draft.planningDiversity !== 'stable'" class="advanced-item">
          <span>规划变体</span>
          <el-button @click="rerunWithNewPlanningSeed">换一种规划</el-button>
        </label>
        <label class="advanced-item"><span>调试开关</span><el-checkbox v-model="debugTraceEnabled">记录详细调试轨迹</el-checkbox></label>
        <label class="advanced-item advanced-item--wide">
          <span>低熵通信实验项</span>
          <el-checkbox-group v-model="lowEntropyOptions" class="advanced-checks">
            <el-checkbox label="trace_provenance">记录通信血缘</el-checkbox>
          </el-checkbox-group>
        </label>
      </div>
        </div>
      </Transition>
      <div class="ctrl-options">
        <div v-show="inputPanelExpanded" class="primary-config"><span class="ctrl-label">规划方式</span><el-radio-group v-model="planningMode" size="small"><el-radio-button label="dynamic">动态规划</el-radio-button><el-radio-button label="template_preferred">模板优先</el-radio-button></el-radio-group></div>
        <div v-show="inputPanelExpanded" class="primary-config"><span class="ctrl-label">思考强度</span><el-radio-group v-model="thinkingMode" size="small"><el-radio-button label="disabled">关闭</el-radio-button><el-radio-button label="standard">标准</el-radio-button><el-radio-button label="deep">深度</el-radio-button></el-radio-group></div>
        <div v-show="inputPanelExpanded" class="primary-config"><span class="ctrl-label">审核方式</span><el-radio-group v-model="draft.reviewMode" size="small"><el-radio-button label="auto">自动</el-radio-button><el-radio-button label="human_in_loop">人工介入</el-radio-button></el-radio-group></div>
        <button v-show="inputPanelExpanded" class="advanced-toggle" type="button" :aria-expanded="advancedSettingsExpanded" @click="advancedSettingsExpanded = !advancedSettingsExpanded"><span>高级设置</span><el-icon><ArrowUp v-if="advancedSettingsExpanded" /><ArrowDown v-else /></el-icon></button>
        <el-button :type="mainAction.type" :loading="mainAction.loading" :disabled="mainAction.disabled" @click="handleMainAction">{{ mainAction.label }}</el-button>
      </div>
    </section>

    <section v-if="activeRunId" class="run-scope ui-surface ui-surface--pad">
      <header><strong>本次 Run 的能力范围（已冻结）</strong><el-tag effect="plain" type="info">只读</el-tag></header>
      <p v-if="activeRun?.legacyPluginScope" class="scope-warning">该运行创建于插件快照功能之前，未伪造插件版本。</p>
      <p v-else-if="missingSnapshotPlugins.length" class="scope-warning">原插件当前不可用：{{ missingSnapshotPlugins.join('、') }}。历史图和输出仍可查看，不能扩大 Scope 后继续执行。</p>
      <div class="snapshot-list">
        <span v-if="!activeRun?.pluginSnapshot?.length">Native only</span>
        <span v-for="snapshot in activeRun?.pluginSnapshot || []" :key="snapshot.pluginId"><b>{{ snapshot.pluginId }}</b> v{{ snapshot.version }}</span>
        <code v-if="activeRun?.capabilityCatalogRevision">Catalog {{ activeRun.capabilityCatalogRevision.slice(0, 12) }}</code>
        <code v-if="activeRun?.planningDiversity && activeRun.planningDiversity !== 'stable'">
          {{ activeRun.planningDiversity === 'balanced' ? '均衡规划' : '探索规划' }} · Seed {{ activeRun.planningSeed }} · 候选 {{ activeRun.planningCandidateCount || 1 }} 选 1
        </code>
      </div>
      <div v-if="planningSelectionReasons.length" class="planning-selection-reasons">
        <strong>本次规划选择依据</strong>
        <span v-for="reason in planningSelectionReasons.slice(0, 4)" :key="reason">{{ reason }}</span>
      </div>
    </section>

    <WorkflowProgressBar
      v-if="isSubmitting || progressTracker.progress.value || progressTracker.syncError.value"
      :progress="progressTracker.progress.value"
      :loading="isSubmitting || progressTracker.isLoading.value"
      :sync-error="progressTracker.syncError.value"
    />
    <DynamicRunSummaryCard
      v-if="activeRunId"
      class="run-summary-card"
      :progress="progressTracker.progress.value"
      :run="activeRun"
      :view="acgView"
    />

    <p v-if="startError" class="run-error" role="alert">{{ startError }}</p>

    <WorkflowReviewPanel
      v-if="reviewPending"
      :run-id="activeRunId"
      :progress="progressTracker.progress.value"
      :run="activeRun"
      @reviewed="handleAcgReviewed"
      @conflict="handleAcgReviewConflict"
    />

    <!-- 主区：拓扑 + 指标/血缘 -->
    <div class="acg-grid" v-if="acgView">
      <div class="grid-main">
        <AcgTopologyGraph
          :blueprint="acgView.acgBlueprint"
          :completed-step-ids="acgView.completedStepIds"
          :step-states="acgView.stepStates"
        />
        <template v-if="artifactRenderers.length">
          <component v-for="renderer in artifactRenderers" :key="renderer.pluginId" :is="renderer.component" :deliverables="acgView.deliverables" :final-report="acgView.finalReport" />
        </template>
        <GenericArtifactPanel
          v-else
          :step-outputs="acgView.stepOutputs || acgView.deliverables"
          :final-artifacts="acgView.finalArtifacts || []"
          :final-report="acgView.finalReport"
          :status="acgView.status"
        />
        <div class="schedule-strip ui-surface" v-if="scheduleBatches.length">
          <h4>就绪集调度轨迹（动态拓扑）</h4>
          <div class="batch-row">
            <div v-for="b in scheduleBatches" :key="b.id" class="batch">
              <span class="batch-idx">第{{ b.round }}轮</span>
              <span v-for="sid in b.nodes" :key="sid" class="batch-node">{{ sid }}</span>
            </div>
          </div>
        </div>
      </div>
      <div class="grid-side">
        <AcgLowEntropyMetrics :metrics="acgView.lowEntropyMetrics" />
        <AcgProvenancePanel
          :consumptions="acgView.provenance.consumptions"
          :interactions="acgView.interactions"
          :recovery-trace="acgView.recoveryTrace"
          :contract-violations="acgView.contractViolations"
          @export-json="exportAudit('json')"
          @export-csv="exportAudit('csv')"
        />
        <RuntimeChangeTimeline
          :runtime-events="acgView.runtimeEvents"
          :applied-patches="acgView.appliedPatches"
          :branch-decisions="acgView.branchDecisions"
          :step-states="acgView.stepStates"
        />
      </div>
    </div>

    <div v-else class="ui-surface task-brief">
      <strong>ACG 动态智能体长程任务</strong>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch, type DeepReadonly } from 'vue'
import axios from 'axios'
import { ArrowDown, ArrowUp, CopyDocument, Cpu, Delete, Document, Monitor, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  workflowApi,
  type AcgDeliverable,
  type AcgFinalArtifact,
  type AcgView,
  type InstalledPlugin,
  type WorkflowRun,
  type WorkflowProgress
} from '@/services/api/workflow'
import AcgTopologyGraph from '@/components/agentos/AcgTopologyGraph.vue'
import AcgLowEntropyMetrics from '@/components/agentos/AcgLowEntropyMetrics.vue'
import AcgProvenancePanel from '@/components/agentos/AcgProvenancePanel.vue'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import DynamicRunSummaryCard from '@/components/agentos/DynamicRunSummaryCard.vue'
import RuntimeChangeTimeline from '@/components/agentos/RuntimeChangeTimeline.vue'
import WorkflowReviewPanel from '@/components/agentos/WorkflowReviewPanel.vue'
import { useWorkflowProgress } from '@/composables/useWorkflowProgress'
import { graphVersionChanged, runtimeProjectionChanged } from '@/utils/runtimePresentation'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import type { ThinkingMode } from '@/config/modelSettings'
import { fileApi, type TaskMaterial } from '@/services/api/file'
import { buildAcgAuditCsv, buildAcgAuditExport } from '@/utils/acgAuditExport'
import { isWorkflowReviewPending } from '@/utils/workflowReviewState'
import { resolveAcgTaskTitle } from '@/utils/acgTaskTitle'
import PluginExtensionHost from '@/features/acg/PluginExtensionHost.vue'
import GenericArtifactPanel from '@/features/acg/GenericArtifactPanel.vue'
import {
  buildWorkbenchStartRequest,
  createNativeWorkbenchDraft,
  type WorkbenchDraft
} from '@/features/acg/workbench'
import { pluginUiExtensions } from '@/plugins'

const draft = reactive<WorkbenchDraft>(createNativeWorkbenchDraft())
const taskName = computed({ get: () => draft.title, set: value => { draft.title = value } })
const contractText = computed({ get: () => draft.materialText, set: value => { draft.materialText = value } })
const userIntent = computed({ get: () => draft.taskGoal, set: value => { draft.taskGoal = value } })
const planningMode = computed({ get: () => draft.planningMode, set: value => { draft.planningMode = value } })
const thinkingMode = computed<ThinkingMode>({ get: () => draft.thinkingMode, set: value => { draft.thinkingMode = value } })
const constraintsText = computed({
  get: () => draft.constraints.join('，'),
  set: value => { draft.constraints = value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean) }
})
const expectedArtifactsText = computed({
  get: () => draft.expectedArtifacts.join('，'),
  set: value => { draft.expectedArtifacts = value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean) }
})
const advancedSettingsExpanded = ref(false)
const debugTraceEnabled = ref(false)
const lowEntropyOptions = ref(['trace_provenance'])

watch(userIntent, value => {
  if (!activeRunId.value) taskName.value = resolveAcgTaskTitle({ title: value })
})

const acgView = ref<AcgView | null>(null)
const activeRun = ref<WorkflowRun | null>(null)
const loading = reactive({ upload: false })
const isSubmitting = ref(false)
const isAcgLoading = ref(false)
const startError = ref<string | null>(null)
const route = useRoute()
const router = useRouter()
const workflowRunsStore = useWorkflowRunsStore()
const activeRunId = ref('')
const installedPlugins = ref<InstalledPlugin[]>([])
const pluginsLoading = ref(false)
const scopeLocked = computed(() => Boolean(activeRunId.value))
const draftExtensions = computed(() => pluginUiExtensions.resolve(draft.enabledPluginIds))
const activePluginIds = computed(() => (
  activeRun.value?.resolvedEnabledPluginIds
  || activeRun.value?.enabledPluginIds
  || draft.enabledPluginIds
))
const activeExtensions = computed(() => pluginUiExtensions.resolve(activePluginIds.value))
const artifactRenderers = computed(() => activeExtensions.value
  .filter(item => item.artifactRenderer)
  .map(item => ({ pluginId: item.pluginId, component: item.artifactRenderer! })))
const activePluginSummary = computed(() => activePluginIds.value.length
  ? activePluginIds.value.join('、')
  : 'Native only')
const missingSnapshotPlugins = computed(() => {
  const available = new Set(installedPlugins.value.filter(item => item.available).map(item => item.pluginId))
  return (activeRun.value?.pluginSnapshot || [])
    .map(item => item.pluginId)
    .filter(pluginId => !available.has(pluginId))
})
const inputPanelExpanded = ref(true)
const inputPanelCompact = ref(false)
const loadedRunId = ref('')
const contractFileInput = ref<HTMLInputElement | null>(null)
const uploadDragging = ref(false)
type SelectedMaterial = Omit<TaskMaterial, 'extractedText'> & { extractedText?: string }
const selectedContractFile = ref<SelectedMaterial | null>(null)
const uploadState = ref<'idle' | 'uploading' | 'parsing' | 'ready' | 'error'>('idle')
const uploadError = ref('')

const resetDraftContent = () => {
  Object.assign(draft, createNativeWorkbenchDraft())
  selectedContractFile.value = null
  uploadState.value = 'idle'
  uploadError.value = ''
}

const applyExtensionDefaults = (pluginId: string) => {
  const defaults = pluginUiExtensions.get(pluginId)?.createDefaults?.()
  if (!defaults) return
  const nativeDefaults = createNativeWorkbenchDraft()
  if (defaults.title && draft.title === nativeDefaults.title) draft.title = defaults.title
  if (defaults.taskGoal && draft.taskGoal === nativeDefaults.taskGoal) draft.taskGoal = defaults.taskGoal
  if (defaults.reviewMode) draft.reviewMode = defaults.reviewMode
  if (defaults.pluginData) draft.pluginData = { ...draft.pluginData, ...defaults.pluginData }
}

const removeExtensionDefaults = (pluginId: string) => {
  const defaults = pluginUiExtensions.get(pluginId)?.createDefaults?.()
  const nativeDefaults = createNativeWorkbenchDraft()
  if (defaults?.title && draft.title === defaults.title) draft.title = nativeDefaults.title
  if (defaults?.taskGoal && draft.taskGoal === defaults.taskGoal) draft.taskGoal = nativeDefaults.taskGoal
}

const togglePlugin = (pluginId: string) => {
  if (scopeLocked.value) return
  if (draft.enabledPluginIds[0] === pluginId) {
    clearPlugins()
    return
  }
  for (const selectedPluginId of draft.enabledPluginIds) removeExtensionDefaults(selectedPluginId)
  draft.enabledPluginIds = [pluginId]
  draft.pluginData = {}
  draft.reviewMode = 'auto'
  applyExtensionDefaults(pluginId)
}

const clearPlugins = () => {
  if (scopeLocked.value) return
  for (const pluginId of draft.enabledPluginIds) removeExtensionDefaults(pluginId)
  draft.enabledPluginIds = []
  draft.pluginData = {}
  draft.reviewMode = 'auto'
}

const loadInstalledPlugins = async () => {
  pluginsLoading.value = true
  try {
    installedPlugins.value = await workflowApi.listInstalledPlugins()
  } catch {
    installedPlugins.value = []
    ElMessage.warning('专业能力包列表暂时无法加载，仍可使用 Native 能力')
  } finally {
    pluginsLoading.value = false
  }
}

const progressTracker = useWorkflowProgress({
  intervalMs: 2000,
  onProgressChanged: value => workflowRunsStore.updateObservedState(
    value.runId,
    value.status,
    value.phase,
    value.updatedAt
  ),
  onTerminal: handleTerminal
})
const reviewPending = computed(() => Boolean(
  activeRunId.value && isWorkflowReviewPending(progressTracker.progress.value, activeRun.value)
))

const CONTRACT_FILE_MAX_SIZE = 10 * 1024 * 1024
const CONTRACT_FILE_EXTENSIONS = ['pdf', 'docx', 'txt', 'md']

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const openContractFilePicker = () => {
  if (!loading.upload) contractFileInput.value?.click()
}

const validateContractFile = (file: File) => {
  const extension = file.name.split('.').pop()?.toLowerCase() || ''
  if (!CONTRACT_FILE_EXTENSIONS.includes(extension)) {
    throw new Error('仅支持 PDF、DOCX、TXT、MD 格式')
  }
  if (file.size <= 0) throw new Error('文件内容为空')
  if (file.size > CONTRACT_FILE_MAX_SIZE) throw new Error('文件不能超过 10MB')
}

const processContractFile = async (file: File) => {
  if (loading.upload) return

  try {
    validateContractFile(file)
    loading.upload = true
    uploadState.value = 'uploading'
    uploadError.value = ''
    const previous = selectedContractFile.value
    const result = await fileApi.uploadTaskMaterial(file, () => { uploadState.value = 'parsing' })
    const extractedText = (result.extractedText || '').trim()
    if (!extractedText) throw new Error('未能从文件中提取到文本，请确认文档包含可复制文字')

    contractText.value = extractedText
    draft.materialIds = [result.materialId]
    selectedContractFile.value = { ...result, extractedText }
    uploadState.value = 'ready'
    if (previous?.state === 'ready' && previous.materialId !== result.materialId) {
      void fileApi.deleteTaskMaterial(previous.materialId).catch(() => undefined)
    }
    ElMessage.success(`已载入任务文件：${file.name}`)
  } catch (error: any) {
    const message = materialErrorMessage(error)
    uploadState.value = 'error'
    uploadError.value = message
    ElMessage.error(message)
  } finally {
    loading.upload = false
    uploadDragging.value = false
    if (contractFileInput.value) contractFileInput.value.value = ''
  }
}

const handleContractFileSelection = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) void processContractFile(file)
}

const handleContractDrop = (event: DragEvent) => {
  uploadDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void processContractFile(file)
}

const clearContractFile = () => {
  const selected = selectedContractFile.value
  if (selected?.state === 'ready') {
    void fileApi.deleteTaskMaterial(selected.materialId).catch(() => undefined)
  }
  if (selected?.extractedText && contractText.value === selected.extractedText) contractText.value = ''
  draft.materialIds = []
  selectedContractFile.value = null
  uploadState.value = 'idle'
  uploadError.value = ''
  if (contractFileInput.value) contractFileInput.value.value = ''
}

const materialErrorMessage = (error: any): string => {
  const data = error?.response?.data
  const detail = typeof data?.detail === 'string' ? data.detail : data?.detail?.message
  return data?.message || detail || error?.message || '任务文件上传失败'
}

const sha256Text = async (value: string): Promise<string> => {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value))
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('')
}

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    completed: '已完成', failed: '失败', running: '执行中',
    waiting_review: '待审核', cancelled: '已取消', retrying: '重试中', planning: '规划中', pending: '待启动'
  }
  const status = progressTracker.progress.value?.status || acgView.value?.status
  return status ? (map[status] || status) : '准备中'
})
const statusTagType = computed(() => {
  const phase = progressTracker.progress.value?.phase
  const s = progressTracker.progress.value?.status || acgView.value?.status
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'waiting_review' || phase === 'review' || phase === 'recovery') return 'warning'
  return 'info'
})
const effectiveStatus = computed(() => progressTracker.progress.value?.status || acgView.value?.status || '')
const effectivePhase = computed(() => progressTracker.progress.value?.phase || '')
const planningModeSummary = computed(() => ({
  template_preferred: '模板优先',
  dynamic: '动态规划'
})[planningMode.value])
const thinkingModeSummary = computed(() => ({ disabled: '关闭', standard: '标准', deep: '深度' })[thinkingMode.value])
const mainAction = computed<{
  action: 'start' | 'planning' | 'view' | 'review' | 'rerun' | 'retry'
  label: string
  type: 'primary' | 'warning' | 'danger' | 'info'
  loading: boolean
  disabled: boolean
}>(() => {
  const status = effectiveStatus.value
  const phase = effectivePhase.value
  if (isSubmitting.value || (activeRunId.value && ['understanding', 'planning', 'graph_building'].includes(phase))) {
    return { action: 'planning', label: '正在生成编排', type: 'info', loading: true, disabled: true }
  }
  if (loading.upload) return { action: 'planning', label: '正在解析文件', type: 'info', loading: true, disabled: true }
  if (!activeRunId.value) return { action: 'start', label: '启动 ACG', type: 'primary', loading: false, disabled: false }
  if (status === 'waiting_review' || phase === 'review') return { action: 'review', label: '进入人工审核', type: 'warning', loading: false, disabled: false }
  if (status === 'completed' || phase === 'completed') return { action: 'rerun', label: '基于当前配置重新运行', type: 'primary', loading: false, disabled: false }
  if (status === 'failed' || phase === 'failed') return { action: 'retry', label: '修改配置并重试', type: 'danger', loading: false, disabled: false }
  if (status === 'cancelled' || phase === 'cancelled') return { action: 'retry', label: '重新运行', type: 'primary', loading: false, disabled: false }
  if (status === 'pending' || status === 'planning') return { action: 'planning', label: '正在生成编排', type: 'info', loading: true, disabled: true }
  return { action: 'view', label: '查看运行', type: 'primary', loading: false, disabled: false }
})
// 从调度 trace 还原"每轮就绪集批次"，可视化并行调度
const scheduleBatches = computed(() => {
  const events = acgView.value?.scheduleTrace || []
  const batches = new Map<string, { id: string; round: number; nodes: string[] }>()
  for (const e of events) {
    const batch = (e.payload?.batch as string[]) || (e.stepId ? [e.stepId] : [])
    const round = Number(e.payload?.round || batches.size + 1)
    const id = String(e.payload?.batchId || `${round}:${e.eventId}`)
    if (batch.length && !batches.has(id)) {
      batches.set(id, { id, round, nodes: batch })
    }
  }
  return Array.from(batches.values()).sort((a, b) => a.round - b.round)
})

const hasStepOutput = (output?: Record<string, any>) => {
  return !!output && Object.keys(output).length > 0
}

const deliverablesFromRun = (run: WorkflowRun): AcgDeliverable[] => {
  return (run.steps || [])
    .filter((step) => hasStepOutput(step.output))
    .map((step) => ({
      stepId: step.stepId,
      name: step.name,
      status: step.status,
      output: step.output || {}
    }))
}

const asMarkdown = (value: unknown): string | null => {
  return typeof value === 'string' && value.trim().length > 0 ? value : null
}

const finalReportFromRun = (run: WorkflowRun): string | null => {
  let finalReport: string | null = null
  for (const step of run.steps || []) {
    const output = step.output || {}
    const markdown = asMarkdown(output.final_answer) || asMarkdown(output.report_markdown) || asMarkdown(output.report) || asMarkdown(output.final_report)
    if (markdown) finalReport = markdown
  }

  if (finalReport) return finalReport

  const runOutput = run.output || {}
  const direct = asMarkdown(runOutput.final_answer) || asMarkdown(runOutput.report_markdown) || asMarkdown(runOutput.report) || asMarkdown(runOutput.final_report)
  if (direct) return direct

  const artifacts = runOutput.artifacts
  if (artifacts && typeof artifacts === 'object') {
    for (const artifact of Object.values(artifacts as Record<string, any>)) {
      if (!artifact || typeof artifact !== 'object') continue
      const markdown = asMarkdown(artifact.final_answer) || asMarkdown(artifact.report_markdown) || asMarkdown(artifact.report) || asMarkdown(artifact.final_report)
      if (markdown) finalReport = markdown
    }
  }

  return finalReport
}

const finalArtifactsFromRun = (run: WorkflowRun): AcgFinalArtifact[] => {
  const artifacts: AcgFinalArtifact[] = []
  for (const step of run.steps || []) {
    const candidate = step.output?.artifact
    if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) continue
    const content = asMarkdown(candidate.content)
    if (!content) continue
    artifacts.push({
      artifactId: String(candidate.artifactId || `artifact_${run.runId}_${step.stepId}`),
      type: String(candidate.type || 'report'),
      title: String(candidate.title || step.name),
      mediaType: String(candidate.mediaType || 'text/markdown'),
      content,
      structuredData: candidate.structuredData && typeof candidate.structuredData === 'object'
        ? candidate.structuredData as Record<string, any>
        : {},
      stepId: step.stepId
    })
  }
  return artifacts
}

const hydrateAcgView = (view: AcgView, run: WorkflowRun): AcgView => {
  const fallbackOutputs = deliverablesFromRun(run)
  const fallbackFinalArtifacts = finalArtifactsFromRun(run)
  return {
    ...view,
    deliverables: view.deliverables.length ? view.deliverables : fallbackOutputs,
    stepOutputs: view.stepOutputs?.length ? view.stepOutputs : fallbackOutputs,
    finalArtifacts: view.finalArtifacts?.length ? view.finalArtifacts : fallbackFinalArtifacts,
    finalReport: view.finalReport || finalReportFromRun(run)
  }
}

const ACTIVE_TOPOLOGY_PHASES = new Set(['executing', 'recovery', 'review'])
const TOPOLOGY_REFRESH_MS = 8000
let topologyController: AbortController | null = null
let topologyTimer: ReturnType<typeof setTimeout> | null = null
let topologyGeneration = 0
let lastTopologyRefreshAt = 0
let lastTopologyUpdatedAt: string | null = null
let submitController: AbortController | null = null
let inputCollapseTimer: ReturnType<typeof setTimeout> | null = null
let inputPanelCompactTimer: ReturnType<typeof setTimeout> | null = null
let terminalNotificationRunId: string | null = null

const clearInputCollapseTimer = () => {
  if (inputCollapseTimer !== null) window.clearTimeout(inputCollapseTimer)
  inputCollapseTimer = null
}

const clearInputPanelCompactTimer = () => {
  if (inputPanelCompactTimer !== null) window.clearTimeout(inputPanelCompactTimer)
  inputPanelCompactTimer = null
}

const inputPanelElement = (element: Element) => element as HTMLElement

const beforeInputPanelEnter = (element: Element) => {
  const panel = inputPanelElement(element)
  inputPanelCompact.value = false
  panel.style.height = '0'
  panel.style.opacity = '0'
  panel.style.transform = 'translateY(-8px)'
}

const enterInputPanel = (element: Element) => {
  const panel = inputPanelElement(element)
  window.requestAnimationFrame(() => {
    panel.style.height = `${panel.scrollHeight}px`
    panel.style.opacity = '1'
    panel.style.transform = 'translateY(0)'
  })
}

const afterInputPanelEnter = (element: Element) => {
  clearInputPanelCompactTimer()
  const panel = inputPanelElement(element)
  panel.style.height = 'auto'
  panel.style.opacity = ''
  panel.style.transform = ''
}

const beforeInputPanelLeave = (element: Element) => {
  const panel = inputPanelElement(element)
  panel.style.height = `${panel.scrollHeight}px`
  panel.style.opacity = '1'
  panel.style.transform = 'translateY(0)'
}

const leaveInputPanel = (element: Element) => {
  const panel = inputPanelElement(element)
  void panel.offsetHeight
  window.requestAnimationFrame(() => {
    panel.style.height = '0'
    panel.style.opacity = '0'
    panel.style.transform = 'translateY(-8px)'
  })
}

const afterInputPanelLeave = (element: Element) => {
  clearInputPanelCompactTimer()
  const panel = inputPanelElement(element)
  panel.style.height = ''
  panel.style.opacity = ''
  panel.style.transform = ''
  if (!inputPanelExpanded.value) inputPanelCompact.value = true
}

const scheduleInputCollapse = (delayMs = 1400) => {
  clearInputCollapseTimer()
  inputCollapseTimer = window.setTimeout(() => {
    inputCollapseTimer = null
    inputPanelExpanded.value = false
  }, delayMs)
}

const clearTopologyTimer = () => {
  if (topologyTimer !== null) {
    window.clearTimeout(topologyTimer)
    topologyTimer = null
  }
}

const clearRunData = () => {
  clearTopologyTimer()
  topologyGeneration += 1
  topologyController?.abort()
  topologyController = null
  acgView.value = null
  activeRun.value = null
  loadedRunId.value = ''
  isAcgLoading.value = false
  lastTopologyRefreshAt = 0
  lastTopologyUpdatedAt = null
}

const enterNewAcgDraft = () => {
  submitController?.abort()
  progressTracker.reset()
  clearRunData()
  clearInputCollapseTimer()
  clearInputPanelCompactTimer()
  activeRunId.value = ''
  startError.value = null
  inputPanelExpanded.value = true
  inputPanelCompact.value = false
  advancedSettingsExpanded.value = false
  resetDraftContent()
}

async function refreshAcgForRun(runId: string, force = false): Promise<void> {
  if (!runId || runId !== activeRunId.value) return
  if (!force && progressTracker.progress.value?.updatedAt === lastTopologyUpdatedAt) return

  const requestGeneration = ++topologyGeneration
  topologyController?.abort()
  topologyController = new AbortController()
  const signal = topologyController.signal
  isAcgLoading.value = true
  try {
    const [runResult, viewResult] = await Promise.allSettled([
      workflowApi.getRun(runId, { signal }),
      workflowApi.getAcgView(runId, { signal })
    ])
    if (requestGeneration !== topologyGeneration || runId !== activeRunId.value) return
    if (viewResult.status === 'rejected') throw viewResult.reason

    const view = viewResult.value
    if (runResult.status === 'rejected') {
      acgView.value = view
      loadedRunId.value = runId
      lastTopologyRefreshAt = Date.now()
      lastTopologyUpdatedAt = progressTracker.progress.value?.updatedAt ?? null
      return
    }

    const run = runResult.value
    acgView.value = hydrateAcgView(view, run)
    activeRun.value = run
    if (run.planningDiversity) draft.planningDiversity = run.planningDiversity
    draft.planningSeed = run.planningSeed ?? null
    draft.enabledPluginIds = [...(run.resolvedEnabledPluginIds || run.enabledPluginIds || [])]
    draft.pluginData = (
      run.input?.pluginData && typeof run.input.pluginData === 'object'
        ? JSON.parse(JSON.stringify(run.input.pluginData)) as Record<string, Record<string, unknown>>
        : {}
    )
    taskName.value = resolveAcgTaskTitle(run)
    if (typeof run.input?.materialText === 'string') contractText.value = run.input.materialText
    for (const extension of draftExtensions.value) {
      const current = draft.pluginData[extension.pluginId] || {}
      draft.pluginData[extension.pluginId] = extension.hydratePluginData?.(run.input || {}, current) || current
    }
    if (typeof run.input?.userIntent === 'string') userIntent.value = run.input.userIntent
    const material = Array.isArray(run.input?.sourceMaterials) ? run.input.sourceMaterials[0] : null
    if (material?.materialId) {
      selectedContractFile.value = { ...material, state: 'bound' }
      uploadState.value = 'ready'
      uploadError.value = ''
    }
    loadedRunId.value = runId
    lastTopologyRefreshAt = Date.now()
    lastTopologyUpdatedAt = progressTracker.progress.value?.updatedAt ?? null
  } catch (error: unknown) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      await removeMissingAcgRun(runId)
    } else if (!axios.isCancel(error) && requestGeneration === topologyGeneration && force) {
      ElMessage.warning('最终 ACG 数据暂时未能加载，请稍后刷新')
    }
  } finally {
    if (requestGeneration === topologyGeneration) {
      topologyController = null
      isAcgLoading.value = false
    }
  }
}

const removeMissingAcgRun = async (runId: string) => {
  workflowRunsStore.removeReference(runId)
  if (activeRunId.value !== runId) return
  progressTracker.reset()
  clearRunData()
  activeRunId.value = ''
  const query = { ...route.query }
  delete query.runId
  await router.replace({ query })
  ElMessage.warning('该运行记录已不存在。')
}

const scheduleTopologyRefresh = (value: DeepReadonly<WorkflowProgress>) => {
  if (!ACTIVE_TOPOLOGY_PHASES.has(value.phase) || value.runId !== activeRunId.value) return
  if (value.updatedAt === lastTopologyUpdatedAt) return
  clearTopologyTimer()
  const remaining = Math.max(0, TOPOLOGY_REFRESH_MS - (Date.now() - lastTopologyRefreshAt))
  topologyTimer = window.setTimeout(() => {
    topologyTimer = null
    void refreshAcgForRun(value.runId)
  }, remaining)
}

async function handleTerminal(value: WorkflowProgress): Promise<void> {
  const shouldNotify = terminalNotificationRunId === value.runId
  if (shouldNotify) terminalNotificationRunId = null
  clearTopologyTimer()
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await refreshAcgForRun(value.runId, true)
    const projectedStepCount = acgView.value?.stepOutputs?.length || 0
    const hasFinalResult = Boolean(
      acgView.value?.finalArtifacts?.length || acgView.value?.finalReport
    )
    const projectionComplete = projectedStepCount >= value.completedSteps
      && (value.phase !== 'completed' || hasFinalResult)
    if (projectionComplete) break
    await new Promise(resolve => window.setTimeout(resolve, 300))
  }
  if (!shouldNotify) return
  if (value.phase === 'completed') ElMessage.success('ACG 引擎执行完成')
  if (value.phase === 'failed') ElMessage.error('ACG 工作流执行失败')
  if (value.phase === 'cancelled') ElMessage.info('ACG 工作流已取消')
}

watch(
  () => progressTracker.progress.value,
  (value, previous) => {
    if (!value) return
    const stateChanged = value.status !== previous?.status || value.phase !== previous?.phase
    if (value.status === 'failed' || value.phase === 'failed') {
      clearInputCollapseTimer()
      inputPanelExpanded.value = true
    } else if (stateChanged && (value.status === 'waiting_review' || ['review', 'completed', 'cancelled'].includes(value.phase))) {
      scheduleInputCollapse(0)
    }
    if (graphVersionChanged(value, previous) && !['completed', 'failed', 'cancelled'].includes(value.status)) {
      clearTopologyTimer()
      void refreshAcgForRun(value.runId, true)
      return
    }
    if (runtimeProjectionChanged(value, previous)) scheduleTopologyRefresh(value)
    if (isWorkflowReviewPending(value, activeRun.value) && !isWorkflowReviewPending(previous, activeRun.value)) {
      clearTopologyTimer()
      void refreshAcgForRun(value.runId, true)
      return
    }
    scheduleTopologyRefresh(value)
  }
)

watch(() => progressTracker.syncError.value, error => {
  if (error === '该运行记录不存在或当前账户无权访问' && activeRunId.value) {
    void removeMissingAcgRun(activeRunId.value)
  }
})
const planningSelectionReasons = computed<string[]>(() => {
  const reasons = activeRun.value?.executionState?.planningSelectionReasons
  return Array.isArray(reasons) ? reasons.filter(item => typeof item === 'string') : []
})

watch(inputPanelExpanded, value => {
  clearInputPanelCompactTimer()
  if (value) {
    inputPanelCompact.value = false
    return
  }
  advancedSettingsExpanded.value = false
  inputPanelCompactTimer = window.setTimeout(() => {
    inputPanelCompactTimer = null
    if (!inputPanelExpanded.value) inputPanelCompact.value = true
  }, 380)
})

watch(
  () => route.query.runId,
  (value) => {
    if (typeof value !== 'string' || !value.trim()) return
    const runId = value.trim()
    if (runId === activeRunId.value && progressTracker.runId.value === runId) return
    terminalNotificationRunId = null
    progressTracker.reset()
    clearRunData()
    startError.value = null
    activeRunId.value = runId
    inputPanelExpanded.value = false
    inputPanelCompact.value = true
    advancedSettingsExpanded.value = false
    workflowRunsStore.register({ runId, source: 'restored' })
    void progressTracker.start(runId, { fresh: false })
  },
  { immediate: true }
)

const copyRunId = async () => {
  if (!activeRunId.value) return
  try {
    await navigator.clipboard.writeText(activeRunId.value)
    ElMessage.success('Run ID 已复制')
  } catch {
    ElMessage.warning('浏览器未授权剪贴板，请直接选择 Run ID')
  }
}

const openOperations = () => {
  void router.push({
    path: '/agentos-console',
    query: activeRunId.value ? { runId: activeRunId.value, source: 'acg' } : { source: 'acg' }
  })
}

const scrollToSection = (selector: string) => {
  const target = document.querySelector<HTMLElement>(selector)
  if (!target) return
  const top = target.getBoundingClientRect().top + window.scrollY - 16
  window.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
}

const rerunWithNewPlanningSeed = () => {
  const values = new Uint32Array(1)
  crypto.getRandomValues(values)
  draft.planningSeed = values[0] & 0x7fffffff
  void startRun()
}

const handleMainAction = () => {
  if (mainAction.value.action === 'start' || mainAction.value.action === 'rerun' || mainAction.value.action === 'retry') {
    void startRun()
    return
  }
  if (mainAction.value.action === 'review') {
    scrollToSection('.workflow-review')
    return
  }
  if (mainAction.value.action === 'view') scrollToSection('.workflow-progress')
}

const handleAcgReviewed = async (run: WorkflowRun) => {
  if (run.runId !== activeRunId.value) return
  activeRun.value = run
  await progressTracker.refresh()
  await refreshAcgForRun(run.runId, true)
}

const handleAcgReviewConflict = async () => {
  await progressTracker.refresh()
  if (activeRunId.value) await refreshAcgForRun(activeRunId.value, true)
}

const downloadText = (content: string, filename: string, type: string) => {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

const exportAudit = (format: 'json' | 'csv') => {
  if (!acgView.value) return
  const filename = `acg-audit-${acgView.value.runId}.${format}`
  if (format === 'json') {
    downloadText(
      JSON.stringify(buildAcgAuditExport(acgView.value), null, 2),
      filename,
      'application/json;charset=utf-8'
    )
  } else {
    downloadText(`\ufeff${buildAcgAuditCsv(acgView.value)}`, filename, 'text/csv;charset=utf-8')
  }
  ElMessage.success(`ACG 审计 ${format.toUpperCase()} 已导出`)
}

const startRun = async () => {
  if (isSubmitting.value) return
  if (!taskName.value.trim()) {
    ElMessage.warning('请输入任务名称')
    return
  }
  if (!userIntent.value.trim()) {
    ElMessage.warning('请输入任务目标')
    return
  }
  for (const extension of draftExtensions.value) {
    const validation = extension.validateDraft?.(draft)
    if (validation && !validation.valid) {
      ElMessage.warning(validation.message || `${extension.displayName}配置不完整`)
      return
    }
  }
  isSubmitting.value = true
  startError.value = null
  submitController?.abort()
  submitController = new AbortController()
  progressTracker.reset()
  clearRunData()
  activeRunId.value = ''
  terminalNotificationRunId = null
  try {
    const clientRequestId = createClientRequestId()
    const request = buildWorkbenchStartRequest(draft, draftExtensions.value, clientRequestId)
    const requestInput: Record<string, unknown> = {
      ...request.input,
      taskName: taskName.value.trim(),
      debugTrace: debugTraceEnabled.value,
      lowEntropyOptions: [...lowEntropyOptions.value]
    }
    request.input = requestInput
    if (selectedContractFile.value) {
      const workingTextSha256 = await sha256Text(contractText.value)
      requestInput.sourceMaterials = [{
        materialId: selectedContractFile.value.materialId,
        purpose: 'task_material',
        edited: workingTextSha256 !== selectedContractFile.value.extractedTextSha256,
        workingTextSha256
      }]
    }
    const res = await workflowApi.startWorkflowAsync(request, { signal: submitController.signal })
    if (selectedContractFile.value) selectedContractFile.value.state = 'bound'
    activeRunId.value = res.run.runId
    scheduleInputCollapse()
    advancedSettingsExpanded.value = false
    workflowRunsStore.register({
      runId: res.run.runId,
      taskId: res.task.taskId,
      workflowId: res.run.workflowId || request.workflowId || 'native_acg_runtime_v1',
      source: 'acg',
      status: res.run.status,
      phase: res.run.lifecyclePhase
    })
    window.dispatchEvent(new Event('acg-runs-refresh'))
    terminalNotificationRunId = res.run.runId
    void progressTracker.start(res.run.runId, { fresh: true })
    await router.replace({ query: { ...route.query, runId: res.run.runId } })
  } catch (error: unknown) {
    if (axios.isCancel(error)) return
    startError.value = startErrorMessage(error)
  } finally {
    isSubmitting.value = false
    submitController = null
  }
}

const createClientRequestId = (): string => {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'))
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`
}

const startErrorDetail = (data: unknown): string | null => {
  if (!data || typeof data !== 'object') return null
  const response = data as Record<string, unknown>
  const parts = [response.message, response.error, response.detail]
    .filter((value): value is string => typeof value === 'string' && Boolean(value.trim()))
    .map((value) => value.trim())
  const unique = [...new Set(parts)]
  return unique.length ? unique.join('：').slice(0, 240) : null
}

const startErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409) {
      return '相同请求标识已用于不同参数，请重新发起任务'
    }
    if (!error.response) return '任务未能启动：网络连接暂时不可用'
    const detail = startErrorDetail(error.response.data)
    if (detail) return `任务未能启动：${detail}`
  }
  return '任务未能启动'
}

onMounted(() => {
  window.addEventListener('acg-new-task', enterNewAcgDraft)
  void loadInstalledPlugins()
})

onBeforeUnmount(() => {
  submitController?.abort()
  clearTopologyTimer()
  topologyGeneration += 1
  topologyController?.abort()
  clearInputCollapseTimer()
  clearInputPanelCompactTimer()
  window.removeEventListener('acg-new-task', enterNewAcgDraft)
})
</script>

<style scoped>
.acg-view.ui-shell { display: flex; flex-direction: column; gap: 0; padding: var(--space-sm) var(--space-md); }
.acg-view.is-draft { min-height: calc(100dvh + 15px); }
.acg-view > .ui-hero { border-bottom: 0; border-radius: 8px 8px 0 0; }
.acg-view > .control-bar { border-top: 0; border-radius: 0 0 8px 8px; }
.acg-view.is-draft > .control-bar { flex: 1 1 auto; }
.acg-view.has-progress:not(.has-run) > .control-bar { border-bottom: 0; border-radius: 0; box-shadow: none; }
.acg-view.has-progress:not(.has-run) > :deep(.workflow-progress) { border-top: 0; border-radius: 0 0 8px 8px; }
.acg-view.has-run > .run-scope { margin-top: 12px; }
.acg-view.has-run > :deep(.workflow-progress) { margin-top: 16px; }
.run-summary-card { margin-top: 10px; }
.hero-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.ui-hero h3 { overflow: hidden; margin: 0; color: var(--text-primary); font-size: 18px; font-weight: 800; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
.hero-right { display: flex; gap: 8px; align-items: center; justify-content: flex-end; flex-wrap: nowrap; }
.hero-run-chip { min-width: 0; height: 30px; display: inline-flex; align-items: center; gap: 5px; padding: 0 9px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-input); color: var(--text-muted); font-size: 10px; }
.hero-run-chip code { overflow: hidden; max-width: 150px; color: var(--text-secondary); font-family: var(--font-mono, ui-monospace, SFMono-Regular, Consolas, monospace); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.hero-icon-action, .hero-operations { height: 32px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--border-light); background: var(--surface-solid); color: var(--text-secondary); cursor: pointer; transition: var(--transition); }
.hero-icon-action { width: 32px; padding: 0; border-radius: 50%; }
.hero-operations { gap: 5px; padding: 0 11px; border-radius: 7px; font: inherit; font-size: 11px; }
.hero-icon-action:hover:not(:disabled), .hero-operations:hover { border-color: var(--primary-line); background: var(--primary-fade); color: var(--primary-color); }
.hero-icon-action:disabled { cursor: not-allowed; opacity: .5; }
.hero-icon-action:focus-visible, .hero-operations:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.hero-engine { color: var(--primary-color); }

.control-bar { position: relative; display: flex; flex-direction: column; gap: var(--space-md); padding-right: 52px; padding-bottom: 10px; }
.control-bar.collapsed { flex-direction: row; align-items: center; gap: 12px; padding: 9px 52px 9px 14px; }
.control-bar.collapsed .input-summary { flex: 1 1 auto; }
.control-bar.collapsed .ctrl-options { flex: 0 0 auto; padding: 0; border: 0; }
.workbench-identity, .plugin-selector header, .run-scope header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.workbench-identity div, .plugin-selector header div { display:flex; flex-direction:column; gap:3px; }
.workbench-identity small, .plugin-selector small, .plugin-selector header span { color:var(--text-secondary); font-size:11px; }
.plugin-selector { display:flex; flex-direction:column; gap:10px; }
.plugin-options { display:grid; grid-template-columns:repeat(auto-fit, minmax(210px, 1fr)); gap:10px; }
.plugin-card { display:flex; flex-direction:column; align-items:flex-start; gap:5px; min-height:86px; padding:12px; border:1px solid var(--border-light); border-radius:8px; background:var(--surface-solid); color:var(--text-primary); text-align:left; cursor:pointer; }
.plugin-card:hover:not(:disabled), .plugin-card.selected { border-color:var(--primary-color); background:var(--primary-fade); }
.plugin-card:disabled { cursor:not-allowed; opacity:.72; }
.plugin-card small { min-height:30px; }
.plugin-card code { color:var(--text-muted); font-size:10px; }
.run-scope { display:flex; flex-direction:column; gap:8px; padding:18px 20px; }
.run-scope header strong { font-size:13px; }
.snapshot-list { display:flex; align-items:center; flex-wrap:wrap; gap:8px; color:var(--text-secondary); font-size:11px; }
.snapshot-list span, .snapshot-list code { padding:5px 8px; border-radius:6px; background:var(--bg-input); }
.planning-selection-reasons { display:flex; flex-wrap:wrap; gap:6px 10px; margin-top:10px; font-size:11px; color:var(--text-secondary); }
.planning-selection-reasons strong { width:100%; color:var(--text-primary); }
.planning-selection-reasons span { padding:4px 7px; border-radius:6px; background:var(--bg-input); }
.scope-warning { margin:0; padding:8px 10px; border-left:3px solid var(--el-color-warning); background:color-mix(in srgb, var(--el-color-warning) 8%, transparent); color:var(--text-secondary); font-size:12px; }
.input-panel-expandable {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  min-width: 0;
  overflow: hidden;
  transform-origin: top center;
  transition:
    height 380ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 220ms ease,
    transform 380ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: height, opacity, transform;
}
.input-panel-toggle {
  position: absolute; top: 10px; right: 12px; z-index: 1;
  width: 28px; height: 28px; display: inline-grid; place-items: center;
  padding: 0; border: 1px solid var(--border-light); border-radius: 6px;
  background: var(--surface-solid); color: var(--text-secondary); cursor: pointer;
  transition: var(--transition);
}
.input-panel-toggle:hover { border-color: var(--primary-line); color: var(--primary-color); background: var(--primary-fade); }
.input-panel-toggle:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--primary-fade); }
.input-fields { display: grid; grid-template-columns: minmax(0, 13fr) minmax(280px, 7fr); align-items: stretch; gap: 24px; min-width: 0; }
.input-pane { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.contract-pane .ctrl-row { flex: 1 1 auto; min-height: 0; }
.contract-pane .contract-textarea { flex: 1 1 auto; min-height: 0; }
.definition-pane { min-width: 0; gap: 12px; }
.pane-heading { color: var(--text-primary); font-size: 13px; font-weight: 750; }
.pane-heading small { margin-left: 4px; color: var(--text-disabled); font-size: 10px; font-weight: 600; }
.input-summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-width: 0; }
.input-summary__copy { display: flex; align-items: center; gap: 7px; min-width: 0; color: var(--text-secondary); }
.input-summary__copy .el-icon { flex: 0 0 auto; color: var(--primary-color); }
.input-summary__copy strong { flex: 0 1 auto; overflow: hidden; max-width: min(320px, 34vw); color: var(--text-primary); font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.input-summary__copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.run-error {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--danger) 38%, var(--border-light));
  border-radius: 6px;
  background: var(--danger-fade);
  color: var(--danger);
  font-size: 12px;
}
.ctrl-row { display: flex; flex-direction: column; gap: 6px; }
.ctrl-label { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.ctrl-options { order: 2; display: flex; align-items: center; gap: 18px; flex-wrap: wrap; padding-top: 4px; }
.primary-config { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.primary-config :deep(.el-radio-button__inner) { border-color: transparent; background: transparent; box-shadow: none; }
.primary-config :deep(.el-radio-button.is-active .el-radio-button__inner) { border-color: var(--primary-line); background: var(--primary-fade); color: var(--primary-color); }
.advanced-toggle {
  min-height: 30px; display: inline-flex; align-items: center; gap: 5px; padding: 0 9px;
  border: 1px solid var(--border-light); border-radius: 6px; background: var(--surface-solid);
  color: var(--text-secondary); cursor: pointer; transition: var(--transition);
}
.advanced-toggle:hover { border-color: var(--primary-line); color: var(--primary-color); }
.ctrl-options > :deep(.el-button:last-child) { margin-left: auto; }
.advanced-settings {
  order: 3;
  display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px;
  padding: 12px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-input);
}
.advanced-item { display: flex; flex-direction: column; gap: 7px; min-width: 0; }
.advanced-item > span { color: var(--text-secondary); font-size: 11px; font-weight: 700; }
.advanced-item--wide { grid-column: span 2; }
.advanced-checks { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.contract-textarea :deep(.el-textarea__inner),
.intent-textarea :deep(.el-textarea__inner) {
  line-height: 1.72;
  font-size: 14px;
  padding: 12px 14px;
  resize: vertical;
}
.contract-pane .contract-textarea :deep(.el-textarea__inner) { height: 100% !important; }
.acg-view.is-draft .input-panel-expandable,
.acg-view.is-draft .input-fields,
.acg-view.is-draft .definition-pane .ctrl-row,
.acg-view.is-draft .contract-textarea,
.acg-view.is-draft .intent-textarea { flex: 1 1 auto; min-height: 0; }
.acg-view.is-draft .contract-textarea :deep(.el-textarea__inner),
.acg-view.is-draft .intent-textarea :deep(.el-textarea__inner) { height: 100% !important; }
.acg-view.is-draft .ctrl-options { margin-top: auto; }
.contract-textarea :deep(.el-textarea__inner),
.intent-textarea :deep(.el-textarea__inner) { min-height: 150px !important; }

.contract-file-input { display: none; }
.contract-upload {
  min-height: 42px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border: 0;
  border-radius: 0;
  background: var(--bg-input);
  transition: border-color 0.16s ease, background-color 0.16s ease;
}
.contract-upload.dragging {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}
.contract-upload.loading { opacity: 0.72; }
.contract-upload__icon {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  display: inline-grid;
  place-items: center;
  border-radius: 5px;
  background: var(--surface-solid);
  color: var(--primary-color);
  box-shadow: 0 0 0 1px var(--border-light);
}
.contract-upload__copy {
  min-width: 0;
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.contract-upload__copy strong,
.contract-upload__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.contract-upload__copy strong { color: var(--text-primary); font-size: 11px; font-weight: 700; }
.contract-upload__copy small { color: var(--text-secondary); font-size: 10px; }
.contract-upload__copy .contract-upload__error { color: var(--el-color-danger); }
.contract-upload__actions { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 6px; }

.acg-view > :deep(.workflow-review) { margin-top: var(--space-lg); }
.acg-grid { display: grid; grid-template-columns: minmax(0, 1fr) 380px; gap: 11px; margin-top: 16px; align-items: stretch; min-width: 0; }
.grid-main { display: flex; flex-direction: column; gap: var(--space-lg); min-width: 0; }
.grid-side { display: flex; flex-direction: column; gap: var(--space-lg); min-width: 0; min-height: 0; }
.grid-side :deep(.acg-provenance) { flex: 1 1 auto; min-height: 0; }

.schedule-strip { padding: var(--space-md); }
.schedule-strip h4 { margin: 0 0 var(--space-sm); font-size: 13px; font-weight: 700; color: var(--text-primary); }
.batch-row { display: flex; gap: var(--space-md); flex-wrap: wrap; }
.batch { display: flex; align-items: center; gap: 4px; padding: 4px 8px; background: var(--bg-input); border-radius: var(--radius-md); }
.batch-idx { font-size: 11px; color: var(--text-secondary); font-weight: 600; margin-right: 4px; }
.batch-node { font-size: 11px; padding: 2px 8px; background: var(--primary-fade); color: var(--primary-color); border-radius: 10px; font-family: monospace; }

.task-brief {
  min-height: 62px;
  display: grid;
  place-items: center;
  margin-top: var(--space-md);
  padding: 12px 20px;
  border-radius: var(--radius-lg);
}
.acg-view.is-draft > .task-brief { flex: 0 0 62px; margin-bottom: var(--space-md); }
.task-brief strong { color: var(--text-secondary); font-size: 13px; font-weight: 700; letter-spacing: .02em; }

@keyframes restore-pulse {
  to { opacity: 1; }
}

@media (max-width: 1160px) {
  .acg-grid { grid-template-columns: minmax(0, 1fr); }
  .advanced-settings { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 720px) {
  .ui-hero { flex-wrap: wrap; align-items: flex-start; }
  .hero-left { width: 100%; }
  .hero-right { justify-content: flex-start; width: 100%; flex-wrap: wrap; }
  .hero-run-chip code { max-width: 120px; }
  .contract-upload { align-items: flex-start; flex-wrap: wrap; }
  .contract-upload__copy { width: calc(100% - 34px); }
  .contract-upload__actions { width: 100%; padding-left: 34px; }
  .input-fields { grid-template-columns: 1fr; }
  .definition-pane { padding-top: 14px; }
  .advanced-settings { grid-template-columns: 1fr; }
  .advanced-item--wide { grid-column: auto; }
  .ctrl-options > :deep(.el-button:last-child) { width: 100%; margin-left: 0; }
  .input-summary__copy { align-items: flex-start; flex-wrap: wrap; }
  .input-summary__copy small { width: 100%; white-space: normal; }
  .control-bar.collapsed { align-items: stretch; flex-direction: column; }
  .control-bar.collapsed .ctrl-options { width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .input-panel-expandable { transition-duration: 1ms; }
}
</style>
