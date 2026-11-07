<template>
  <WorkbenchLayout :show-left="false" :show-right="false" storage-key="zhiyi.create-mission.layout.v1">
    <template #main>
      <main class="create-mission" aria-label="Create Mission">
        <div class="create-mission__workspace">
          <header class="create-mission__topbar">
            <button class="create-mission__back" type="button" @click="goBack">
              <span class="create-mission__back-icon" aria-hidden="true">←</span>
              <span>返回项目</span>
            </button>
            <div class="create-mission__topbar-title">
              <span class="create-mission__eyebrow">CREATE MISSION</span>
              <h1>新建任务</h1>
            </div>
            <span class="create-mission__topbar-mode">MISSION COMPOSER</span>
          </header>

          <form class="create-mission__form" @submit.prevent="submit">
          <div v-if="pendingLaunch" role="status">
            已恢复待确认提交；恢复时使用原始目标、材料及附件引用。
            <button type="button" :disabled="submitting" @click="resumePendingLaunch">核对并恢复原提交</button>
          </div>
          <div class="create-mission__workspace-body">
          <section class="mission-pane" aria-labelledby="mission-section-title">
            <div class="workspace-pane__heading">
              <span class="workspace-pane__eyebrow">MISSION</span>
              <h2 id="mission-section-title">Mission</h2>
            </div>
            <div class="mission-pane__scroll">
              <div class="mission-fields">
                <label class="field-block field-block--brief" for="mission-goal">
                  <div class="field-block__header">
                    <span class="field-block__label">Objective <small>必填</small></span>
                    <div class="brief-mode-switch" role="tablist" aria-label="Objective 显示模式">
                      <button type="button" role="tab" :aria-selected="objectiveMode === 'write'" :class="{ active: objectiveMode === 'write' }" @click="objectiveMode = 'write'">编写</button>
                      <button type="button" role="tab" :aria-selected="objectiveMode === 'preview'" :class="{ active: objectiveMode === 'preview' }" @click="objectiveMode = 'preview'">预览</button>
                    </div>
                  </div>
                  <textarea v-if="objectiveMode === 'write'" id="mission-goal" v-model="draft.taskGoal" rows="8" placeholder="描述需要完成什么、关键约束以及最终希望得到什么结果。支持 Markdown，切到「预览」查看渲染效果。" aria-required="true"></textarea>
                  <div v-else class="objective-preview markdown-body" role="tabpanel" aria-label="Objective 预览">
                    <div v-if="hasObjectiveContent" v-html="objectivePreviewHtml"></div>
                    <p v-else class="objective-preview__empty">暂无内容。切回「编写」输入任务简报，支持 Markdown 标题、列表与表格。</p>
                  </div>
                </label>
              </div>
            </div>
          </section>

          <aside class="create-mission__right-column" aria-label="Mission context and execution">
            <section class="context-panel" aria-labelledby="attachment-input-title">
              <div class="workspace-pane__heading workspace-pane__heading--row">
                <div>
                  <span class="workspace-pane__eyebrow">CONTEXT</span>
                  <h2 id="attachment-input-title">Context</h2>
                </div>
                <div class="context-panel__meta"><strong>{{ contextSummary }}</strong><label class="panel-action" for="mission-files">+ 添加上下文<input id="mission-files" type="file" accept=".pdf,.docx,.txt,.md" multiple @change="handleFiles" /></label></div>
              </div>
              <div class="context-panel__body">
                <div class="attachment-input__dropzone" :class="{ 'is-dragging': attachmentDragging }" role="region" aria-label="Context 文件区域" @dragenter.prevent="attachmentDragging = true" @dragover.prevent="attachmentDragging = true" @dragleave.prevent="attachmentDragging = false" @drop.prevent="handleDrop">
                  <div v-if="!attachments.length" class="context-empty">
                    <span class="context-empty__icon" aria-hidden="true">+</span>
                    <span class="context-empty__eyebrow">CONTEXT / READY TO ADD</span>
                    <p>为这次 Mission 提供 AgentOS 可以读取的参考材料。</p>
                    <div class="context-empty__actions"><label class="context-empty__action" for="mission-files">添加文件</label><span>支持 TXT、Markdown、PDF、DOCX · 也可直接拖入</span></div>
                  </div>
                  <article v-for="item in attachments" :key="item.localId" class="attachment-row">
                    <div class="attachment-row__file"><span class="attachment-row__file-mark" aria-hidden="true">▤</span><div><strong :title="item.file.name">{{ item.file.name }}</strong><small>{{ fileFormat(item.file.name) }} · {{ formatBytes(item.file.size) }}</small></div></div>
                    <div class="attachment-row__state" :class="`is-${item.status.toLowerCase()}`">
                      <span>{{ attachmentStatusLabel(item) }}</span>
                      <div v-if="item.status === 'UPLOADING'" class="attachment-row__progress" aria-hidden="true"><span :style="{ width: `${Math.max(0, item.progress)}%` }"></span></div>
                      <small v-if="item.error">{{ item.error }}</small>
                    </div>
                    <div class="attachment-row__actions"><button v-if="item.status === 'FAILED'" type="button" @click="retryAttachment(item)">重试</button><button class="attachment-row__remove" type="button" :disabled="item.status === 'UPLOADING' || item.status === 'PARSING'" :aria-label="`移除 ${item.file.name}`" @click="removeAttachment(item)">×</button></div>
                  </article>
                </div>
              </div>
            </section>

            <section class="execution-panel" aria-label="Execution settings">
            <div class="execution-overview">
            <div class="execution-settings">
              <div v-if="desktopWorkspaceRequired" class="config-line mission-workspace" aria-label="任务工作区">
                <div class="config-line__label"><strong>工作区</strong><small>选择本次任务读写文件的目录。</small></div>
                <div class="mission-workspace__selection">
                  <NativeWorkspacePicker @state-change="workspaceState = $event" />
                  <code aria-label="当前工作区目录">{{ workspaceState.pendingPath || workspaceState.workspaceRoot || '尚未选择工作区' }}</code>
                  <p class="mission-workspace__hint">{{ workspaceIssue || '新任务会由后端绑定当前已信任目录。' }}</p>
                </div>
              </div>
              <div class="config-line config-line--top">
                <div class="config-line__label"><strong>Capabilities</strong><small>基础能力始终启用，可选择一个能力包。</small></div>
                <div class="capability-choice">
                  <div class="capability-baseline"><span class="capability-baseline__mark">✓</span><div><strong>Native Core</strong><small>基础运行能力 · 始终启用</small></div></div>
                  <span class="config-sub-label">Additional capability pack</span>
                  <div class="config-options" role="radiogroup" aria-label="附加能力包">
                    <button class="config-option" :class="{ 'is-selected': !draft.enabledPluginIds.length }" type="button" role="radio" :aria-checked="!draft.enabledPluginIds.length" @click="clearPlugin">不添加</button>
                    <button v-for="plugin in plugins" :key="plugin.pluginId" class="config-option" :class="{ 'is-selected': draft.enabledPluginIds.includes(plugin.pluginId) }" type="button" role="radio" :aria-checked="draft.enabledPluginIds.includes(plugin.pluginId)" @click="togglePlugin(plugin.pluginId)">{{ plugin.displayName }}</button>
                  </div>
                </div>
              </div>
              <div class="config-line">
                <div class="config-line__label"><strong>Planning</strong><small>决定 TaskPlan 如何被生成。</small></div>
                <div class="planning-choice">
                <div class="config-options" role="radiogroup" aria-label="规划方式">
                  <button class="config-option" :class="{ 'is-selected': draft.planningMode === 'dynamic' }" type="button" role="radio" :aria-checked="draft.planningMode === 'dynamic'" @click="draft.planningMode = 'dynamic'">Dynamic</button>
                  <button class="config-option" :class="{ 'is-selected': draft.planningMode === 'template_preferred' }" type="button" role="radio" :aria-checked="draft.planningMode === 'template_preferred'" @click="draft.planningMode = 'template_preferred'">Template preferred</button>
                </div>
                <p class="planning-choice__hint"><strong>{{ planningModeLabel }}</strong><span>{{ planningModeDescription }}</span></p>
              </div>
            </div>
            <div class="config-line">
              <div class="config-line__label"><strong>Execution Control</strong><small>控制高风险步骤是否进入审核节点。</small></div>
              <div class="execution-control-choice">
                <div class="config-options" role="radiogroup" aria-label="执行控制">
                  <button class="config-option" :class="{ 'is-selected': draft.reviewMode === 'auto' }" type="button" role="radio" :aria-checked="draft.reviewMode === 'auto'" @click="draft.reviewMode = 'auto'">自动处理审核</button>
                  <button class="config-option" :class="{ 'is-selected': draft.reviewMode === 'human_in_loop' }" type="button" role="radio" :aria-checked="draft.reviewMode === 'human_in_loop'" @click="draft.reviewMode = 'human_in_loop'">人工审核</button>
                </div>
                <p class="planning-choice__hint"><strong>{{ executionControlLabel }}</strong><span>{{ executionControlDescription }}</span></p>
              </div>
            </div>
            </div>

            <details class="advanced-config" @toggle="syncAdvancedConfigState">
              <summary>
                <span class="advanced-config__summary"><strong>高级运行设置</strong><small>{{ advancedSettingsSummary }}</small></span>
                <span class="advanced-config__hint">{{ advancedConfigOpen ? '收起' : '展开' }}</span>
              </summary>
              <div class="advanced-config__body">
                <div class="advanced-config__presets">
                  <span class="config-line__label">快捷预设</span>
                  <div class="config-options">
                    <button class="config-option" :class="{ 'is-selected': advancedPreset === 'fast' }" type="button" @click="applyAdvancedPreset('fast')">快速</button>
                    <button class="config-option" :class="{ 'is-selected': advancedPreset === 'balanced' }" type="button" @click="applyAdvancedPreset('balanced')">均衡</button>
                    <button class="config-option" :class="{ 'is-selected': advancedPreset === 'deep' }" type="button" @click="applyAdvancedPreset('deep')">深入</button>
                  </div>
                </div>
                <p class="advanced-config__description">预设会同时调整推理强度、联网检索、规划多样性与能力覆盖范围；各项仍可单独修改。</p>
                <div class="advanced-config__grid">
                  <label class="advanced-field">
                    <span>推理强度<small>{{ activeModel }}<template v-if="usesEffortOptions"> · {{ effortOptions.join(' / ') }}</template></small></span>
                    <select v-model="thinkingSelection" aria-label="Thinking strength">
                      <option v-for="option in reasoningOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
                    </select>
                  </label>
                  <label class="advanced-field">
                    <span>规划多样性<small>决定规划时优先稳定，还是探索更多候选。</small></span>
                    <select v-model="draft.planningDiversity" aria-label="Planning diversity">
                      <option value="stable">稳定</option>
                      <option value="balanced">均衡</option>
                      <option value="exploratory">探索</option>
                    </select>
                  </label>
                  <label class="advanced-field">
                    <span>能力覆盖范围<small>在当前已启用的能力内，按任务复杂度选择覆盖范围。</small></span>
                    <select v-model="draft.capabilityProfile" aria-label="Capability profile">
                      <option value="auto">自动选择</option>
                      <option value="standard">标准</option>
                      <option value="full">完整</option>
                    </select>
                  </label>
                  <label class="advanced-field">
                    <span>规划随机种子<small>留空自动选择；固定种子便于对比规划，模型生成仍可能不同。</small></span>
                    <input v-model.number="draft.planningSeed" aria-label="Planning seed" type="number" min="0" max="9007199254740991" step="1" placeholder="自动" />
                  </label>
                  <label class="advanced-toggle">
                    <span><strong>联网检索</strong><small>允许执行时按需检索外部资料，实际可用性取决于已配置工具。</small></span>
                    <input v-model="draft.webSearchEnabled" type="checkbox" />
                  </label>
                </div>
                <p class="advanced-config__managed-note">运行诊断与来源追踪由运行服务管理，可在任务的运行详情中查看。</p>
              </div>
            </details>

              <PluginExtensionHost :extensions="draftExtensions" :draft="draft" @update:plugin-data="draft.pluginData = $event" />
            </div>
          </section>
        </aside>
      </div>
      <footer class="launch-bar">
        <div class="launch-bar__summary">
          <span class="launch-bar__eyebrow">LAUNCH PREVIEW</span>
          <strong>{{ planningModeSummary }} · {{ capabilitySummary }} · {{ contextSummary }} · {{ executionControlSummary }}</strong>
          <span v-if="runSummaryIssues.length" class="launch-bar__notice" role="status">{{ runSummaryIssues.join(' · ') }}</span>
          <span v-else class="launch-bar__ready">Ready to plan</span>
          <p v-if="errorMessage" class="create-mission__error" role="alert">{{ errorMessage }}</p>
        </div>
        <div class="launch-bar__actions">
          <button class="create-mission__cancel" type="button" @click="goBack">取消</button>
          <button class="create-mission__submit" type="submit" :disabled="!isReadyToRun" :aria-busy="submitting">
            <span>{{ submitting ? '正在创建 Run…' : '创建并运行' }}</span>
            <span aria-hidden="true">→</span>
          </button>
        </div>
      </footer>
      </form>
    </div>
      </main>
    </template>
  </WorkbenchLayout>
</template>

<script setup lang="ts">
import { localFetch } from '@/platform/api'
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import NativeWorkspacePicker from '@/components/platform/NativeWorkspacePicker.vue'
import type { NativeWorkspaceState } from '@/components/platform/workspaceState'
import { presetReasoningOption, type RuntimePreset } from '@/features/mission/runtimePresets'
import PluginExtensionHost from '@/features/acg/PluginExtensionHost.vue'
import { workflowApi } from '@/services/api/workflow'
import type { InputAttachment } from '@/services/api/agentos'
import { createNativeWorkbenchDraft, restoreWorkbenchDraft, type WorkbenchDraft } from '@/features/acg/workbench'
import { workbenchLaunchCommand } from '@/features/mission/command'
import { createMissionLaunchAttempt } from '@/features/mission/launchAttempt'
import { pluginUiExtensions } from '@/plugins'
import { apiUrl, platform } from '@/platform'
import { renderMarkdown } from '@/utils/markdown'
import { plainMissionTitle } from '@/utils/missionTitle'
import {
  MODEL_SETTINGS_EVENT,
  capabilityFromPayload,
  defaultReasoningEffortFromCapability,
  effortValuesFromOptions,
  fetchModelCapability,
  isEffortKindOption,
  loadModelSettings,
  reasoningOptionsFromCapability,
  thinkingOptions,
  type ReasoningEffort,
  type ModelCapability,
  type ModelSettings,
  type ThinkingMode
} from '@/config/modelSettings'

const router = useRouter()
const draft = ref<WorkbenchDraft>(createNativeWorkbenchDraft())
const submitting = ref(false)
const errorMessage = ref('')
type AttachmentDraft = { localId: string; file: File; status: 'UPLOADING' | 'PARSING' | 'READY' | 'FAILED'; progress: number; attachment?: InputAttachment; error?: string }
const attachments = ref<AttachmentDraft[]>([])
const attachmentDragging = ref(false)
const attachmentsCommitted = ref(false)
const attachmentsPending = computed(() => attachments.value.some(item => item.status !== 'READY'))
const desktopWorkspaceRequired = platform.platform === 'desktop'
const workspaceState = ref<NativeWorkspaceState>({ loading: true, trusted: false,
  workspaceId: '', workspaceRoot: '', pendingPath: '', error: '' })
const workspaceIssue = computed(() => {
  if (!desktopWorkspaceRequired) return ''
  if (workspaceState.value.loading) return '正在确认工作区授权状态'
  if (workspaceState.value.pendingPath) return '请先信任所选工作区'
  if (!workspaceState.value.trusted) return workspaceState.value.error || '请选择并信任工作区后再创建任务'
  return ''
})
const runtimeSettingsIssue = computed(() => {
  const seed: unknown = draft.value.planningSeed
  return seed !== null && seed !== '' && (typeof seed !== 'number' || !Number.isSafeInteger(seed) || seed < 0)
    ? '规划种子需为 0 到 9007199254740991 之间的整数' : ''
})
let controller: AbortController | null = null
const modelSettings = ref<ModelSettings>(loadModelSettings())
const serverSystemModel = ref('')
let systemModelsRequest = 0
const activeModel = computed(() => (
  modelSettings.value.provider === 'system' && serverSystemModel.value
    ? serverSystemModel.value
    : modelSettings.value.selectedModel
))
const modelCapability = ref<ModelCapability | null>(null)
const reasoningOptions = computed(() => reasoningOptionsFromCapability(modelCapability.value))
const usesEffortOptions = computed(() => isEffortKindOption(reasoningOptions.value))
const effortOptions = computed(() => effortValuesFromOptions(reasoningOptions.value))
const thinkingSelection = computed<ReasoningEffort | ThinkingMode>({
  get: () => {
    if (usesEffortOptions.value) {
      const stored = draft.value.reasoningEffort
      if (stored && effortOptions.value.includes(stored)) return stored as ReasoningEffort
      if (draft.value.thinkingMode === 'disabled' && reasoningOptions.value.some(option => option.value === 'disabled')) {
        return 'disabled'
      }
      if (draft.value.thinkingMode === 'standard' && effortOptions.value.includes('low')) return 'low'
      if (draft.value.thinkingMode === 'deep' && effortOptions.value.includes('max')) return 'max'
      return defaultReasoningEffortFromCapability(modelCapability.value, reasoningOptions.value) as ReasoningEffort
    }
    return draft.value.thinkingMode
  },
  set: value => {
    const selected = reasoningOptions.value.find(option => option.value === value)
    if (selected?.kind === 'effort') {
      const effort = value as ReasoningEffort
      draft.value.reasoningEffort = effort
      draft.value.thinkingMode = effort === 'low' ? 'standard' : 'deep'
      return
    }
    draft.value.reasoningEffort = undefined
    draft.value.thinkingMode = value as ThinkingMode
  }
})

type AdvancedPreset = RuntimePreset | 'custom'
const advancedPreset = computed<AdvancedPreset>(() => {
  return (['fast', 'balanced', 'deep'] as const).find(preset =>
    thinkingSelection.value === presetReasoningOption(reasoningOptions.value, preset, modelCapability.value)?.value
    && draft.value.webSearchEnabled === (preset !== 'fast')
    && draft.value.capabilityProfile === (preset === 'fast' ? 'standard' : preset === 'deep' ? 'full' : 'auto')
    && draft.value.planningDiversity === (preset === 'fast' ? 'stable' : preset === 'balanced' ? 'balanced' : 'exploratory')) || 'custom'
})
const advancedConfigOpen = ref(false)
const planningModeLabel = computed(() => draft.value.planningMode === 'dynamic' ? '动态规划' : '模板优先')
const planningModeDescription = computed(() => draft.value.planningMode === 'dynamic'
  ? '根据任务目标动态拆解，并选择当前可用能力。'
  : '优先复用已验证模板，未命中时自动切换动态规划。')
const advancedSettingsSummary = computed(() => [
  reasoningOptions.value.find(option => option.value === thinkingSelection.value)?.label || '模型默认',
  draft.value.webSearchEnabled ? '联网检索' : '不检索网络',
  draft.value.planningDiversity === 'stable' ? '稳定规划' : draft.value.planningDiversity === 'balanced' ? '均衡规划' : '探索规划'
].join(' · '))
const plugins = computed(() => pluginUiExtensions.all())
const draftExtensions = computed(() => pluginUiExtensions.resolve(draft.value.enabledPluginIds))
const planningModeSummary = computed(() => draft.value.planningMode === 'dynamic' ? 'Dynamic' : 'Template preferred')
const executionControlLabel = computed(() => draft.value.reviewMode === 'auto' ? '自动处理审核' : '人工审核')
const executionControlSummary = computed(() => draft.value.reviewMode === 'auto' ? 'Auto Review' : 'Human Review')
const executionControlDescription = computed(() => draft.value.reviewMode === 'auto'
  ? '正式任务先接受规划；签发许可后仍需明确点击执行。运行中自动处理审核。'
  : '每个执行步骤完成后暂停，等待人工审核；最终交付须经批准。')
const capabilitySummary = computed(() => {
  const selected = draft.value.enabledPluginIds
    .map(pluginId => plugins.value.find(plugin => plugin.pluginId === pluginId)?.displayName)
    .filter((name): name is string => Boolean(name))
  return selected.length ? `Native Core · ${selected.join(' · ')}` : 'Native Core'
})
const contextSummary = computed(() => {
  if (!attachments.value.length) return 'No context files'
  const readyCount = attachments.value.filter(item => item.status === 'READY').length
  return readyCount === attachments.value.length
    ? `${readyCount} ${readyCount === 1 ? 'file' : 'files'} ready`
    : `${readyCount}/${attachments.value.length} files ready`
})
const extensionValidationMessage = computed(() => {
  for (const extension of draftExtensions.value) {
    const validation = extension.validateDraft?.(draft.value)
    if (validation && !validation.valid) return validation.message || `${extension.displayName} 配置不完整`
  }
  return ''
})
const runSummaryIssues = computed(() => {
  const issues: string[] = []
  if (!draft.value.taskGoal.trim()) issues.push('补充 Objective')
  const processingCount = attachments.value.filter(item => item.status === 'UPLOADING' || item.status === 'PARSING').length
  const failedCount = attachments.value.filter(item => item.status === 'FAILED').length
  if (processingCount) issues.push(`${processingCount} 个 Context 文件仍在处理中`)
  if (failedCount) issues.push(`${failedCount} 个 Context 文件失败，请重试或移除`)
  if (extensionValidationMessage.value) issues.push(extensionValidationMessage.value)
  if (workspaceIssue.value) issues.push(workspaceIssue.value)
  if (runtimeSettingsIssue.value) issues.push(runtimeSettingsIssue.value)
  return issues
})
const isReadyToRun = computed(() => !submitting.value && runSummaryIssues.value.length === 0)

const automaticMissionTitle = (objective: string) => plainMissionTitle(objective, 'AI Mission').slice(0, 80)

const objectiveMode = ref<'write' | 'preview'>('write')
const hasObjectiveContent = computed(() => Boolean(draft.value.taskGoal.trim()))
const objectivePreviewHtml = computed(() => renderMarkdown(draft.value.taskGoal || ''))

const applyAdvancedPreset = (preset: RuntimePreset) => {
  draft.value.capabilityProfile = preset === 'fast' ? 'standard' : preset === 'deep' ? 'full' : 'auto'
  const option = presetReasoningOption(reasoningOptions.value, preset, modelCapability.value)
  if (option) thinkingSelection.value = option.value
  draft.value.webSearchEnabled = preset !== 'fast'
  draft.value.planningDiversity = preset === 'fast' ? 'stable' : preset === 'balanced' ? 'balanced' : 'exploratory'
}

const syncAdvancedConfigState = (event: Event) => {
  const details = event.currentTarget as HTMLDetailsElement
  advancedConfigOpen.value = details.open
}

const syncDraftRuntimeSelection = () => {
  if (usesEffortOptions.value) {
    const hasDisabledOption = reasoningOptions.value.some(option => option.value === 'disabled')
    const storedEffort = draft.value.reasoningEffort || modelSettings.value.reasoningEffort
    if (!storedEffort && hasDisabledOption && draft.value.thinkingMode === 'disabled') {
      draft.value.reasoningEffort = undefined
      return
    }
    const effort = (storedEffort && effortOptions.value.includes(storedEffort) ? storedEffort
      : defaultReasoningEffortFromCapability(modelCapability.value, reasoningOptions.value)) as ReasoningEffort
    draft.value.reasoningEffort = effort
    draft.value.thinkingMode = effort === 'low' ? 'standard' : 'deep'
  } else if (draft.value.reasoningEffort) {
    draft.value.reasoningEffort = undefined
  }
}

const loadSystemModel = async (): Promise<void> => {
  if (modelSettings.value.provider !== 'system' || typeof fetch !== 'function') return
  const requestId = ++systemModelsRequest
  try {

    const response = await localFetch(apiUrl('/ai/chat/models'), {
    })
    if (!response.ok || requestId !== systemModelsRequest || modelSettings.value.provider !== 'system') return
    const data = await response.json() as { models?: unknown; default_model?: unknown; capabilities?: unknown }
    const models = Array.isArray(data.models)
      ? data.models.filter((model): model is string => typeof model === 'string' && Boolean(model.trim()))
      : []
    const defaultModel = typeof data.default_model === 'string' && models.includes(data.default_model)
      ? data.default_model
      : models[0]
    if (defaultModel && requestId === systemModelsRequest && modelSettings.value.provider === 'system') {
      serverSystemModel.value = defaultModel
      const entry = data.capabilities && typeof data.capabilities === 'object'
        ? (data.capabilities as Record<string, unknown>)[defaultModel]
        : undefined
      modelCapability.value = capabilityFromPayload(entry)
      syncDraftRuntimeSelection()
    }
  } catch {
    // Keep local model settings as the fallback when the catalog is unavailable.
  }
}

const syncModelSettings = (event: Event) => {
  const detail = (event as CustomEvent<ModelSettings>).detail
  modelSettings.value = detail
    ? { ...detail, models: [...detail.models] }
    : loadModelSettings()
  serverSystemModel.value = ''
  modelCapability.value = null
  syncDraftRuntimeSelection()
  if (modelSettings.value.provider === 'system') void loadSystemModel()
}

let capabilityRequest = 0
watch([activeModel, () => modelSettings.value.provider, () => modelSettings.value.baseUrl], ([model, provider, baseUrl]) => {
  const requestId = ++capabilityRequest
  if (provider !== 'system') modelCapability.value = null
  syncDraftRuntimeSelection()
  if (model && provider !== 'system') {
    // 非系统供应商：按需单查模型能力（system 由 loadSystemModel 的目录带回）。
    void fetchModelCapability(model, baseUrl).then(capability => {
      if (requestId === capabilityRequest) {
        modelCapability.value = capability
        syncDraftRuntimeSelection()
      }
    })
  }
}, { immediate: true })
onMounted(() => {
  window.addEventListener(MODEL_SETTINGS_EVENT, syncModelSettings)
  void loadSystemModel()
})

const togglePlugin = (pluginId: string) => {
  if (draft.value.enabledPluginIds.includes(pluginId)) {
    clearPlugin()
    return
  }
  draft.value.enabledPluginIds = [pluginId]
  const defaults = pluginUiExtensions.get(pluginId)?.createDefaults?.()
  if (!defaults) return
  const nativeDefaults = createNativeWorkbenchDraft()
  if (!draft.value.title && defaults.title) draft.value.title = defaults.title
  if (!draft.value.taskGoal && defaults.taskGoal) draft.value.taskGoal = defaults.taskGoal
  if (!draft.value.expectedArtifacts.length && defaults.expectedArtifacts) draft.value.expectedArtifacts = [...defaults.expectedArtifacts]
  if (defaults.reviewMode) draft.value.reviewMode = defaults.reviewMode
  if (defaults.capabilityProfile && draft.value.capabilityProfile === nativeDefaults.capabilityProfile) draft.value.capabilityProfile = defaults.capabilityProfile
  if (defaults.planningDiversity && draft.value.planningDiversity === nativeDefaults.planningDiversity) draft.value.planningDiversity = defaults.planningDiversity
  if (typeof defaults.webSearchEnabled === 'boolean' && draft.value.webSearchEnabled === nativeDefaults.webSearchEnabled) draft.value.webSearchEnabled = defaults.webSearchEnabled
  if (defaults.thinkingMode && draft.value.thinkingMode === nativeDefaults.thinkingMode) draft.value.thinkingMode = defaults.thinkingMode
  if (defaults.reasoningEffort && !draft.value.reasoningEffort) draft.value.reasoningEffort = defaults.reasoningEffort
  if (defaults.pluginData) draft.value.pluginData = { ...draft.value.pluginData, ...defaults.pluginData }
}

const clearPlugin = () => {
  draft.value.enabledPluginIds = []
  draft.value.pluginData = {}
  draft.value.reviewMode = 'auto'
}

const createClientRequestId = () => typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`

const extensionOf = (filename: string) => filename.includes('.') ? filename.slice(filename.lastIndexOf('.')).toLowerCase() : 'file'
const formatBytes = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`
const fileFormat = (filename: string) => extensionOf(filename).replace('.', '').toUpperCase()
const attachmentStatusLabel = (item: AttachmentDraft) => {
  if (item.status === 'UPLOADING') return item.progress > 0 ? `正在上传 ${item.progress}%` : '正在上传'
  if (item.status === 'PARSING') return '正在解析…'
  if (item.status === 'READY') return '✓ 已就绪'
  return '失败'
}
const uploadAttachment = async (item: AttachmentDraft) => {
  item.status = 'UPLOADING'; item.progress = 0; item.error = undefined
  try {
    item.attachment = await workflowApi.uploadAttachment(item.file, { onProgress: value => { item.progress = value; if (value >= 100) item.status = 'PARSING' } })
    item.status = item.attachment.status === 'READY' ? 'READY' : 'FAILED'
    if (item.status === 'FAILED') item.error = item.attachment.parseError || '文件解析失败'
  } catch (error: any) {
    item.status = 'FAILED'
    const detail = error?.response?.data?.detail
    item.error = detail?.message || error?.response?.data?.message || error?.message || '文件上传失败'
  }
}
const addFiles = (files: File[]) => {
  const accepted = new Set(['.txt', '.md', '.pdf', '.docx'])
  for (const file of files) {
    if (!accepted.has(extensionOf(file.name))) { errorMessage.value = `不支持的文件类型：${file.name}`; continue }
    // 必须 reactive 包裹后入队：uploadAttachment 若拿到原生对象，status/progress 赋值
    // 不触发响应式更新，行状态会永远停在"上传中…"并锁死提交按钮。
    const item = reactive<AttachmentDraft>({ localId: createClientRequestId(), file, status: 'UPLOADING', progress: 0 })
    attachments.value.push(item); void uploadAttachment(item)
  }
}
const handleFiles = (event: Event) => { const input = event.currentTarget as HTMLInputElement; addFiles(Array.from(input.files || [])); input.value = '' }
const handleDrop = (event: DragEvent) => { attachmentDragging.value = false; addFiles(Array.from(event.dataTransfer?.files || [])) }
const retryAttachment = async (item: AttachmentDraft) => { if (item.attachment) { try { await workflowApi.deleteAttachment(item.attachment.attachmentId) } catch {} item.attachment = undefined }; await uploadAttachment(item) }
const removeAttachment = async (item: AttachmentDraft) => { attachments.value = attachments.value.filter(candidate => candidate.localId !== item.localId); if (item.attachment) { try { await workflowApi.deleteAttachment(item.attachment.attachmentId) } catch { ElMessage.error('附件删除失败') } } }

const launchAttempt = createMissionLaunchAttempt({ slot: 'workbench' })
const restoredLaunch = launchAttempt.pending()
const pendingLaunch = ref(restoredLaunch)
if (restoredLaunch) restoreWorkbenchDraft(draft.value, {
  runId: '', title: restoredLaunch.commandSnapshot.title,
  reviewMode: restoredLaunch.commandSnapshot.reviewMode,
  enabledPluginIds: restoredLaunch.commandSnapshot.enabledPluginIds || [],
  input: restoredLaunch.commandSnapshot.input
}, [])
const resumePendingLaunch = async () => {
  if (submitting.value || !pendingLaunch.value) return
  submitting.value = true
  try {
    const result = await launchAttempt.resume(pendingLaunch.value.operationId)
    await router.replace({ name: 'MissionWorkspace', params: { missionId: result.missionId }, query: { runId: result.runId } })
    launchAttempt.complete(result.clientRequestId)
    pendingLaunch.value = null
  } catch (error: any) { errorMessage.value = error?.message || '原提交核对失败，身份已保留。' }
  finally { submitting.value = false }
}
const submit = async () => {
  if (submitting.value) return
  if (!draft.value.taskGoal.trim()) { errorMessage.value = '请输入 Objective'; return }
  if (workspaceIssue.value || runtimeSettingsIssue.value) {
    errorMessage.value = workspaceIssue.value || runtimeSettingsIssue.value
    return
  }
  if (attachmentsPending.value) { errorMessage.value = '请等待所有附件解析完成，或移除失败的附件。'; return }
  for (const extension of draftExtensions.value) {
    const validation = extension.validateDraft?.(draft.value)
    if (validation && !validation.valid) {
      errorMessage.value = validation.message || `${extension.displayName}配置不完整`
      return
    }
  }
  submitting.value = true
  errorMessage.value = ''
  controller?.abort()
  controller = new AbortController()
  try {
    if (desktopWorkspaceRequired) {
      const expected = { ...workspaceState.value }
      const response = await localFetch(apiUrl('/api/agentos/v2/workspaces/current'), {
        signal: controller.signal, cache: 'no-store'
      })
      if (!response.ok) throw new Error('无法复核工作区授权，请重新选择并信任工作区。')
      const current = await response.json()
      if (current.revoked || current.selected === false || !current.workspaceId
        || current.workspaceId !== expected.workspaceId || current.workspaceRoot !== expected.workspaceRoot) {
        window.dispatchEvent(new Event('workspace-authorization-changed'))
        throw new Error('工作区授权已变化，请确认当前目录后重新创建任务。')
      }
    }
    const command = workbenchLaunchCommand(
      { ...draft.value, title: draft.value.title.trim() || automaticMissionTitle(draft.value.taskGoal) },
      draftExtensions.value,
      {
        attachmentIds: [...(restoredLaunch?.commandSnapshot.attachmentIds || []), ...attachments.value.map(item => item.attachment?.attachmentId).filter((item): item is string => Boolean(item))],
      }
    )
    // Once sent, a failed response can still mean the Mission owns these files.
    attachmentsCommitted.value = true
    const run = await launchAttempt.launch(command, { signal: controller.signal })
    await router.replace({ name: 'MissionWorkspace', params: { missionId: run.missionId }, query: { runId: run.runId } })
    launchAttempt.complete(run.clientRequestId)
  } catch (error: any) {
    if (error?.name === 'CanceledError' || error?.name === 'AbortError') return
    const detail = error?.response?.data?.detail
    pendingLaunch.value = launchAttempt.pending()
    errorMessage.value = (typeof detail === 'string' ? detail : error?.response?.data?.message) || error?.message || 'Mission 创建失败，请稍后重试。'
    ElMessage.error(errorMessage.value)
  } finally {
    submitting.value = false
  }
}

const goBack = () => { void router.replace({ name: 'AcgVisualization', query: {} }) }
onBeforeUnmount(() => {
  controller?.abort()
  systemModelsRequest += 1
  window.removeEventListener(MODEL_SETTINGS_EVENT, syncModelSettings)
  if (!attachmentsCommitted.value) for (const item of attachments.value) if (item.attachment) void workflowApi.deleteAttachment(item.attachment.attachmentId).catch(() => undefined)
})
</script>

<style scoped>
/* One layout layer: clear input hierarchy, bounded panes, and a non-overlapping launch bar. */
.create-mission {
  --mission-surface: color-mix(in srgb, var(--bg-card) 92%, var(--bg-app));
  --mission-surface-raised: color-mix(in srgb, var(--bg-card) 72%, var(--bg-app));
  --mission-border: color-mix(in srgb, var(--border-light) 88%, transparent);
  display: block;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  color: var(--text-primary);
  background: var(--bg-app);
}

.create-mission__workspace,
.create-mission__form {
  display: grid;
  min-width: 0;
  min-height: 0;
}

.create-mission__workspace {
  grid-template-rows: 62px minmax(0, 1fr);
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.create-mission__topbar {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) auto minmax(180px, 1fr);
  align-items: center;
  gap: 24px;
  min-width: 0;
  padding: 0 clamp(20px, 3vw, 44px);
  border-bottom: 1px solid var(--mission-border);
  background: color-mix(in srgb, var(--bg-app) 88%, var(--bg-sidebar));
}

.create-mission__back {
  justify-self: start;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  padding: 0;
  border: 0;
  color: var(--text-secondary);
  background: transparent;
  cursor: pointer;
  font: inherit;
  font-size: 12px;
  transition: color 160ms var(--ease-out), transform 160ms var(--ease-out);
}

.create-mission__back:hover { color: var(--text-primary); transform: translateX(-2px); }
.create-mission__back-icon { color: var(--text-muted); font-size: 18px; line-height: 1; }
.create-mission__topbar-title { display: grid; justify-items: center; gap: 3px; min-width: 0; }
.create-mission__eyebrow,
.workspace-pane__eyebrow,
.launch-bar__eyebrow,
.context-empty__eyebrow { color: var(--primary-color); font: 10px var(--font-mono, monospace); letter-spacing: .14em; }
.create-mission__topbar-title h1 { margin: 0; color: var(--text-primary); font-family: var(--font-sans); font-size: 14px; font-weight: 650; line-height: 1.2; }
.create-mission__topbar-mode { justify-self: end; color: var(--text-muted); font: 9px var(--font-mono, monospace); letter-spacing: .14em; }

.create-mission__form { grid-template-rows: minmax(0, 1fr) auto; width: 100%; height: 100%; }
.create-mission__workspace-body { display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, .62fr); min-width: 0; min-height: 0; overflow: hidden; }
.create-mission__right-column { display: grid; grid-template-rows: minmax(320px, 1.05fr) minmax(300px, .95fr); min-width: 0; min-height: 0; overflow: hidden; }

.mission-pane,
.context-panel,
.execution-panel { min-width: 0; min-height: 0; background: color-mix(in srgb, var(--bg-app) 96%, var(--bg-card)); }

.mission-pane { display: grid; grid-template-rows: auto minmax(0, 1fr); padding: clamp(28px, 4.5vh, 52px) clamp(26px, 5vw, 76px); }
.context-panel,
.execution-panel { display: grid; grid-template-rows: auto minmax(0, 1fr); padding: clamp(24px, 3.5vh, 36px) clamp(24px, 3vw, 40px); background: color-mix(in srgb, var(--bg-sidebar) 72%, var(--bg-app)); }
.context-panel { border-bottom: 1px solid var(--mission-border); }

.workspace-pane__heading { min-width: 0; margin-bottom: 28px; }
.workspace-pane__heading--row { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.workspace-pane__eyebrow { display: block; margin-bottom: 8px; }
.workspace-pane__heading h2 { margin: 0; color: var(--text-primary); font-family: var(--font-sans); font-size: 17px; font-weight: 650; line-height: 1.2; }
.mission-pane__scroll { display: grid; grid-template-rows: minmax(0, 1fr); min-width: 0; min-height: 0; overflow: auto; padding: 2px 18px 18px 0; scrollbar-color: var(--scrollbar-thumb, var(--border-hover)) transparent; scrollbar-width: thin; }
.mission-fields { display: grid; grid-template-rows: minmax(0, 1fr); gap: 28px; max-width: none; min-height: 0; padding-bottom: 12px; }

.field-block { display: grid !important; gap: 9px; min-width: 0; margin: 0 !important; color: var(--text-primary); }
.field-block__label { display: inline-flex; align-items: center; gap: 7px; color: var(--text-primary); font-size: 12px; font-weight: 650; }
.field-block__label small { color: var(--text-muted); font-size: 10px; font-weight: 450; }
.field-block__header { display: flex; align-items: baseline; justify-content: space-between; gap: 16px; }
.field-block__header em { color: var(--text-muted); font: 9px var(--font-mono, monospace); font-style: normal; letter-spacing: .1em; }
.field-block--brief { grid-template-rows: auto minmax(0, 1fr); min-height: 0; padding: 0; }

.brief-mode-switch { display: inline-flex; align-items: center; gap: 2px; padding: 2px; border: 1px solid var(--mission-border); border-radius: 7px; background: var(--mission-surface); }
.brief-mode-switch button { min-width: 44px; padding: 3px 10px; border: 0; border-radius: 5px; background: transparent; color: var(--text-secondary); font: inherit; font-size: 11px; cursor: pointer; transition: background-color 140ms var(--ease-out), color 140ms var(--ease-out); }
.brief-mode-switch button:hover { color: var(--text-primary); }
.brief-mode-switch button.active { background: var(--primary-fade); color: var(--primary-color); font-weight: 600; }

.objective-preview {
  height: 100%;
  min-height: 320px;
  padding: 16px;
  overflow-y: auto;
  border: 1px solid var(--mission-border);
  border-radius: 9px;
  outline: 0;
  color: var(--text-primary);
  background: var(--mission-surface);
  font-size: 13px;
  line-height: 1.7;
}
.objective-preview :deep(> div > *:first-child) { margin-top: 0; }
.objective-preview__empty { margin: 0; color: var(--text-muted); font-size: 12.5px; }

#mission-goal,
.advanced-field select,
.advanced-field input { width: 100%; border: 1px solid var(--mission-border); border-radius: 9px; outline: 0; color: var(--text-primary); background: var(--mission-surface); font: inherit; font-size: 13px; transition: border-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out), background-color 160ms var(--ease-out); }
#mission-goal { height: 100%; min-height: 320px; padding: 16px; resize: vertical; line-height: 1.7; }
#mission-goal::placeholder { color: var(--text-muted); opacity: .9; }
#mission-goal:hover,
.advanced-field select:hover,
.advanced-field input:hover { border-color: var(--border-hover); background: var(--mission-surface-raised); }
#mission-goal:focus,
.advanced-field select:focus,
.advanced-field input:focus { border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-fade); }

.context-panel__meta { display: grid; justify-items: end; gap: 9px; min-width: 0; }
.context-panel__meta > strong { color: var(--text-secondary); font: 10px var(--font-mono, monospace); white-space: nowrap; }
.panel-action,
.context-empty__action { display: inline-flex !important; align-items: center; min-height: 30px; margin: 0 !important; padding: 0 10px; border: 1px solid color-mix(in srgb, var(--primary-color) 45%, var(--border-light)); border-radius: 7px; color: var(--primary-color) !important; background: var(--primary-fade); cursor: pointer; font-size: 11px !important; font-weight: 650 !important; white-space: nowrap; transition: background-color 160ms var(--ease-out), border-color 160ms var(--ease-out), color 160ms var(--ease-out); }
.panel-action:hover,
.context-empty__action:hover { border-color: var(--primary-color); color: var(--primary-hover) !important; background: var(--accent-fade); }
.panel-action input { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); clip-path: inset(50%); white-space: nowrap; }

.context-panel__body { min-width: 0; min-height: 0; overflow: hidden; }
.attachment-input__dropzone { display: grid; align-content: start; width: 100%; height: 100%; min-height: 200px; overflow: auto; padding: 16px; border: 1.5px dashed color-mix(in srgb, var(--primary-color) 42%, var(--border-hover)); border-radius: 10px; background: color-mix(in srgb, var(--primary-color) 5%, var(--mission-surface)); scrollbar-color: var(--scrollbar-thumb, var(--border-hover)) transparent; scrollbar-width: thin; transition: border-color 160ms var(--ease-out), background-color 160ms var(--ease-out); }
.attachment-input__dropzone:hover { border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 8%, var(--mission-surface)); }
.attachment-input__dropzone.is-dragging { border-color: var(--primary-color); background: var(--primary-fade); }
.context-empty { display: grid; align-content: center; justify-items: center; gap: 12px; min-height: 170px; }
.context-empty__icon { display: grid; place-items: center; width: 36px; height: 36px; border: 1.5px dashed color-mix(in srgb, var(--primary-color) 55%, var(--border-hover)); border-radius: 50%; color: var(--primary-color); font-size: 20px; line-height: 1; }
.context-empty p { max-width: 380px; margin: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.65; }
.context-empty__actions { display: flex; align-items: center; flex-wrap: wrap; justify-content: center; gap: 10px; color: var(--text-muted); font-size: 11px; line-height: 1.45; }
.context-empty__action { min-height: 29px; }
.attachment-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 14px; min-height: 62px; padding: 0 4px; }
.attachment-row + .attachment-row { border-top: 1px solid color-mix(in srgb, var(--border-light) 65%, transparent); }
.attachment-row__file,
.attachment-row__state { display: grid; gap: 3px; min-width: 0; }
.attachment-row__file { display: flex; align-items: center; gap: 10px; }
.attachment-row__file-mark { color: var(--primary-color); font-size: 15px; }
.attachment-row__file > div { display: grid; gap: 3px; min-width: 0; }
.attachment-row__file strong { overflow: hidden; color: var(--text-primary); font-size: 11px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.attachment-row__file small,
.attachment-row__state small { color: var(--text-muted); font-size: 10px; }
.attachment-row__state { color: var(--text-secondary); font: 10px var(--font-mono, monospace); white-space: nowrap; }
.attachment-row__state.is-ready { color: var(--success); }
.attachment-row__state.is-failed,
.attachment-row__state.is-failed small { color: var(--danger); }
.attachment-row__progress { width: 100%; height: 3px; overflow: hidden; background: color-mix(in srgb, var(--border-light) 70%, transparent); }
.attachment-row__progress span { display: block; height: 100%; background: var(--primary-color); transition: width 160ms var(--ease-out); }
.attachment-row__actions { display: flex; justify-content: flex-end; gap: 8px; }
.attachment-row__actions button { min-width: 26px; padding: 4px 2px; border: 0; color: var(--text-muted); background: transparent; cursor: pointer; font-size: 10px; }
.attachment-row__actions button:hover { color: var(--text-primary); }
.attachment-row__actions button:disabled { cursor: default; opacity: .45; }
.attachment-row__remove { font-size: 18px !important; line-height: 1; }

.execution-panel { display: grid; grid-template-rows: minmax(0, 1fr); }
.execution-overview { min-width: 0; min-height: 0; overflow: auto; padding-right: 8px; scrollbar-color: var(--scrollbar-thumb, var(--border-hover)) transparent; scrollbar-width: thin; }
.execution-settings { display: grid; gap: 20px; }
.config-line { display: grid; grid-template-columns: minmax(105px, .72fr) minmax(0, 1.28fr); align-items: start; gap: 16px; min-width: 0; }
.config-line__label { display: grid; gap: 4px; min-width: 0; color: var(--text-primary); font-size: 11px; }
.config-line__label strong { color: var(--text-primary); font-size: 11px; font-weight: 650; }
.config-line__label small,
.config-sub-label { color: var(--text-muted); font-size: 10px; line-height: 1.45; }
.capability-choice,
.planning-choice,
.execution-control-choice { display: grid; gap: 10px; min-width: 0; }
.capability-baseline { display: flex; align-items: center; gap: 9px; min-height: 34px; }
.capability-baseline__mark { color: var(--success); font-size: 13px; }
.capability-baseline div { display: grid; gap: 2px; }
.capability-baseline strong { color: var(--text-primary); font-size: 11px; font-weight: 650; }
.capability-baseline small { color: var(--text-muted); font-size: 10px; }
.config-sub-label { margin-top: 2px; }
.config-options { display: flex; flex-wrap: wrap; gap: 7px; }
.config-option { min-height: 32px; padding: 6px 10px; border: 1px solid var(--mission-border); border-radius: 7px; color: var(--text-secondary); background: transparent; cursor: pointer; font: inherit; font-size: 11px; transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out), background-color 160ms var(--ease-out); }
.config-option:hover { border-color: var(--border-hover); color: var(--text-primary); background: var(--mission-surface-raised); }
.config-option.is-selected { border-color: color-mix(in srgb, var(--primary-color) 56%, var(--border-light)); color: var(--primary-color); background: var(--primary-fade); }
.planning-choice__hint { display: grid; gap: 3px; margin: 0; color: var(--text-muted); font-size: 10px; line-height: 1.45; }
.planning-choice__hint strong { color: var(--text-secondary); font-size: 11px; font-weight: 650; }

.advanced-config { margin-top: 18px; border-top: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent); }
.advanced-config summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 0 10px; cursor: pointer; }
.advanced-config__summary { display: grid; gap: 6px; min-width: 0; }
.advanced-config summary strong { font-size: 14px; font-weight: 650; }
.advanced-config__summary small { color: var(--text-muted); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.advanced-config__hint { flex: 0 0 auto; color: var(--text-muted); font-size: 12px; }
.advanced-config__description,
.advanced-config__managed-note,
.mission-workspace__hint { margin: 0; color: var(--text-muted); font-size: 12px; line-height: 1.6; }
.mission-workspace__selection { display: grid; justify-items: start; gap: 9px; min-width: 0; }
.mission-workspace__selection > code { max-width: 100%; color: var(--text-secondary); overflow-wrap: anywhere; font-size: 12px; line-height: 1.6; }
.advanced-config__body { display: grid; gap: 16px; padding: 4px 0 2px; }
.advanced-config__presets { display: grid; grid-template-columns: minmax(105px, .72fr) minmax(0, 1.28fr); align-items: center; gap: 16px; }
.advanced-config__grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.advanced-field,
.advanced-toggle { display: grid !important; gap: 7px; min-width: 0; margin: 0 !important; }
.advanced-field > span,
.advanced-toggle strong { color: var(--text-primary); font-size: 13px; font-weight: 650; }
.advanced-field > span small,
.advanced-toggle small { display: block; margin-top: 5px; color: var(--text-muted); font-size: 12px; font-weight: 400; line-height: 1.5; }
.advanced-field select,
.advanced-field input { height: 42px; padding: 0 12px; border-radius: 8px; font-size: 14px; }
.advanced-toggle { grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 12px; }
.advanced-toggle span { display: grid; gap: 2px; }
.advanced-toggle input { width: 32px; height: 18px; margin: 0; accent-color: var(--primary-color); cursor: pointer; }

.launch-bar { display: flex; align-items: center; justify-content: space-between; gap: 24px; min-width: 0; min-height: 56px; padding: 8px clamp(20px, 3vw, 44px); border-top: 1px solid var(--mission-border); background: color-mix(in srgb, var(--bg-app) 92%, var(--bg-sidebar)); }
.launch-bar__summary { display: grid; gap: 3px; min-width: 0; }
.launch-bar__eyebrow { color: var(--text-muted); font-size: 9px; }
.launch-bar__summary strong { overflow: hidden; color: var(--text-primary); font-size: 11px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.launch-bar__ready,
.launch-bar__notice { overflow: hidden; font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.launch-bar__ready { color: var(--success); }
.launch-bar__notice { color: var(--warning); }
.launch-bar__actions { display: flex; flex: 0 0 auto; gap: 10px; }
.create-mission__cancel,
.create-mission__submit { min-width: 88px; min-height: 34px; padding: 0 16px; border-radius: 8px; cursor: pointer; font: inherit; font-size: 12px; transition: border-color 160ms var(--ease-out), color 160ms var(--ease-out), background-color 160ms var(--ease-out), transform 160ms var(--ease-out); }
.create-mission__cancel { border: 1px solid var(--mission-border); color: var(--text-secondary); background: transparent; }
.create-mission__cancel:hover { border-color: var(--border-hover); color: var(--text-primary); background: var(--mission-surface-raised); }
.create-mission__submit { display: inline-flex; align-items: center; justify-content: center; gap: 12px; min-width: 146px; border: 1px solid var(--primary-color); color: var(--on-primary, #fff); background: var(--primary-color); font-weight: 700; }
.create-mission__submit:hover:not(:disabled) { border-color: var(--primary-hover); background: var(--primary-hover); transform: translateY(-1px); }
.create-mission__submit:active:not(:disabled) { transform: translateY(1px); }
.create-mission__submit:disabled { cursor: not-allowed; opacity: .46; }
.create-mission button:focus-visible,
.create-mission input:focus-visible,
.create-mission textarea:focus-visible,
.create-mission select:focus-visible,
.create-mission summary:focus-visible { outline: 2px solid var(--border-focus); outline-offset: 2px; }

@media (max-width: 1020px) {
  .create-mission__workspace-body { grid-template-columns: 1fr; grid-template-rows: auto auto; overflow: auto; }
  .mission-pane { min-height: 460px; border-bottom: 1px solid var(--mission-border); }
  .create-mission__right-column { grid-template-rows: minmax(320px, auto) minmax(420px, auto); min-height: 740px; }
}

@media (max-width: 640px) {
  .create-mission__workspace { grid-template-rows: 58px minmax(0, 1fr); }
  .create-mission__topbar { grid-template-columns: auto 1fr; gap: 14px; padding: 0 16px; }
  .create-mission__topbar-title { justify-items: start; }
  .create-mission__topbar-mode { display: none; }
  .mission-pane,
  .context-panel,
  .execution-panel { padding: 24px 18px; }
  .workspace-pane__heading--row { flex-wrap: wrap; }
  .context-panel__meta { justify-items: start; }
  .attachment-row { grid-template-columns: minmax(0, 1fr) auto; gap: 8px 12px; padding: 10px 4px; }
  .attachment-row__state { grid-column: 1; grid-row: 2; }
  .attachment-row__actions { grid-column: 2; grid-row: 1 / span 2; }
  .config-line,
  .advanced-config__presets { grid-template-columns: 1fr; gap: 9px; }
  .advanced-config__grid { grid-template-columns: 1fr; }
  .launch-bar { align-items: stretch; flex-direction: column; gap: 12px; padding: 12px 16px; }
  .launch-bar__actions { width: 100%; }
  .launch-bar__actions button { flex: 1; }
}
</style>
