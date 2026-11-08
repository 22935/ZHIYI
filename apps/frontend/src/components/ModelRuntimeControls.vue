<template>
  <el-popover
    v-if="composer"
    placement="top-end"
    trigger="click"
    :width="336"
    :offset="10"
    :show-arrow="false"
    popper-class="composer-model-popover"
    @show="handleComposerOpen"
    @hide="providerMenuOpen = false"
  >
    <template #reference>
      <button
        class="composer-model-trigger"
        type="button"
        :style="{ '--effort-color': activeReasoningColor }"
        :aria-label="triggerTitle"
        aria-haspopup="dialog"
        :title="triggerTitle"
      >
        <span class="composer-model-name">{{ settings.selectedModel || '选择模型' }}</span>
        <span v-if="settings.selectedModel" class="composer-model-effort">{{ activeReasoningShortLabel }}</span>
        <el-icon><ArrowDown /></el-icon>
      </button>
    </template>

    <div class="model-menu" role="dialog" aria-label="模型与思考强度" :style="{ '--effort-color': activeReasoningColor }">
      <div class="model-menu__head">
        <span class="model-menu__label">模型</span>
        <div class="model-menu__provider">
          <button
            class="model-menu__provider-trigger"
            type="button"
            :title="providerTitle"
            aria-haspopup="listbox"
            :aria-expanded="providerMenuOpen"
            @click="providerMenuOpen = !providerMenuOpen"
          >
            {{ compactProviderLabel(settings.provider) }}
            <el-icon><ArrowDown /></el-icon>
          </button>
          <Transition name="model-menu-pop">
            <div v-if="providerMenuOpen" class="model-menu__provider-list" role="listbox" aria-label="模型服务商">
              <button
                v-for="provider in modelProviderPresets"
                :key="provider.id"
                class="model-menu__provider-option"
                :class="{ 'is-selected': provider.id === settings.provider }"
                type="button"
                role="option"
                :aria-selected="provider.id === settings.provider"
                @click="chooseProvider(provider.id)"
              >
                <span>{{ provider.name }}</span>
                <el-icon v-if="provider.id === settings.provider"><Check /></el-icon>
              </button>
            </div>
          </Transition>
        </div>
      </div>

      <div class="model-menu__list" role="listbox" aria-label="选择模型">
        <button
          v-for="model in availableModels"
          :key="model"
          class="model-menu__model"
          :class="{ 'is-selected': model === settings.selectedModel }"
          type="button"
          role="option"
          :aria-selected="model === settings.selectedModel"
          @click="selectModel(model)"
        >
          <span class="model-menu__model-name">{{ model }}</span>
          <el-icon v-if="model === settings.selectedModel" class="model-menu__check"><Check /></el-icon>
        </button>
        <p v-if="modelsLoading" class="model-menu__empty">正在加载模型…</p>
        <p v-else-if="!availableModels.length" class="model-menu__empty">暂无可用模型</p>
      </div>

      <div class="model-menu__divider" role="separator"></div>

      <div class="model-menu__effort">
        <span class="model-menu__label">思考强度</span>
        <div
          class="model-menu__segments"
          role="radiogroup"
          aria-label="思考强度"
          :style="{
            '--segment-index': String(reasoningIndex),
            '--segment-count': String(Math.max(reasoningOptions.length, 1))
          }"
        >
          <span class="model-menu__segment-thumb" aria-hidden="true"></span>
          <button
            v-for="option in reasoningOptions"
            :key="option.value"
            class="model-menu__segment"
            :class="{ 'is-selected': isSelectedReasoningOption(option) }"
            :style="{ '--segment-color': reasoningColor(option.value) }"
            type="button"
            role="radio"
            :aria-checked="isSelectedReasoningOption(option)"
            @click="selectReasoningOption(option.value)"
          >
            <span class="model-menu__segment-dot" aria-hidden="true"></span>
            {{ reasoningShortLabel(option) }}
          </button>
        </div>
        <div class="model-menu__hint-slot">
          <Transition name="model-menu-hint" mode="out-in">
            <p class="model-menu__hint" :key="String(selectedReasoningOption?.value)">
              <span class="model-menu__hint-dot" aria-hidden="true"></span>
              {{ reasoningHint }}
            </p>
          </Transition>
        </div>
      </div>
    </div>
  </el-popover>
  <div v-else class="model-runtime-controls" :class="{ compact }" aria-label="模型运行设置">
    <el-select
      :model-value="settings.provider"
      class="provider-select"
      :title="providerTitle"
      aria-label="选择模型服务商"
      @change="selectProvider"
    >
      <template #prefix><el-icon><Connection /></el-icon></template>
      <el-option
        v-for="provider in modelProviderPresets"
        :key="provider.id"
        :label="compact ? compactProviderLabel(provider.id) : provider.name"
        :value="provider.id"
      />
    </el-select>

    <el-select
      v-model="settings.selectedModel"
      class="model-select"
      :loading="modelsLoading"
      placeholder="默认模型"
      aria-label="选择模型"
      @change="persistSettings"
    >
      <template #prefix><el-icon><Cpu /></el-icon></template>
      <el-option
        v-for="model in availableModels"
        :key="model"
        :label="model"
        :value="model"
      />
    </el-select>

    <el-select
      v-model="reasoningSelection"
      class="reasoning-select"
      aria-label="选择思考程度"
      @change="persistSettings"
    >
      <template #prefix><el-icon><Opportunity /></el-icon></template>
      <el-option
        v-for="option in reasoningOptions"
        :key="option.value"
        :label="compact ? option.shortLabel : option.label"
        :value="option.value"
      />
    </el-select>
  </div>
</template>

<script setup lang="ts">
import { localFetch } from '@/platform/api'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowDown, Check, Connection, Cpu, Opportunity } from '@element-plus/icons-vue'
import { apiUrl } from '@/platform'
import {
  MODEL_SETTINGS_EVENT,
  applyProviderPreset,
  capabilityFromPayload,
  defaultReasoningEffortFromCapability,
  effortValuesFromOptions,
  fetchModelCapability,
  isEffortKindOption,
  loadModelSettings,
  modelProviderPresets,
  reasoningOptionsFromCapability,
  saveModelSettings,
  type ReasoningEffort,
  type ModelCapability,
  type ModelProviderId,
  type ModelSettings,
  type ThinkingMode
} from '@/config/modelSettings'

withDefaults(defineProps<{ compact?: boolean; composer?: boolean }>(), { compact: false, composer: false })

const settings = ref(loadModelSettings())
const modelsLoading = ref(false)
const providerMenuOpen = ref(false)
let systemModelsRequest = 0
const availableModels = computed(() => settings.value.models)
const modelCapability = ref<ModelCapability | null>(null)
const reasoningOptions = computed(() => reasoningOptionsFromCapability(modelCapability.value))
const usesEffortOptions = computed(() => isEffortKindOption(reasoningOptions.value))
const reasoningSelection = computed<ThinkingMode | ReasoningEffort>({
  get: () => {
    if (usesEffortOptions.value) {
      const stored = settings.value.reasoningEffort
      const effortOptions = effortValuesFromOptions(reasoningOptions.value)
      if (stored && effortOptions.includes(stored)) return stored as ReasoningEffort
      if (settings.value.thinkingMode === 'disabled' && reasoningOptions.value.some(option => option.value === 'disabled')) {
        return 'disabled'
      }
      if (settings.value.thinkingMode === 'standard' && effortOptions.includes('low')) return 'low'
      if (settings.value.thinkingMode === 'deep' && effortOptions.includes('max')) return 'max'
      return defaultReasoningEffortFromCapability(modelCapability.value, reasoningOptions.value) as ReasoningEffort
    }
    return settings.value.thinkingMode
  },
  set: value => {
    const selected = reasoningOptions.value.find(option => option.value === value)
    if (selected?.kind === 'effort') {
      const effort = value as ReasoningEffort
      settings.value.reasoningEffort = effort
      settings.value.thinkingMode = effort === 'low' ? 'standard' : 'deep'
      return
    }
    settings.value.thinkingMode = value as ThinkingMode
    settings.value.reasoningEffort = undefined
  }
})
const selectedReasoningOption = computed(() => {
  const selected = reasoningOptions.value.find(option => String(option.value) === String(reasoningSelection.value))
  return selected || reasoningOptions.value[0]
})
const reasoningHint = computed(() => {
  const option = selectedReasoningOption.value
  return option ? reasoningDescription(option.value) : '按模型能力调整推理深度'
})
const reasoningIndex = computed(() => {
  const option = selectedReasoningOption.value
  if (!option) return 0
  const index = reasoningOptions.value.findIndex(item => String(item.value) === String(option.value))
  return Math.max(0, index)
})
const REASONING_LABELS: Record<string, string> = {
  disabled: '关闭',
  low: '轻度',
  standard: '标准',
  medium: '中度',
  high: '高强度',
  deep: '深度',
  xhigh: '极高',
  max: '极致'
}
const REASONING_SHORT_LABELS: Record<string, string> = {
  disabled: '关',
  low: '轻度',
  standard: '标准',
  medium: '中度',
  high: '高',
  deep: '深度',
  xhigh: '极高',
  max: '极致'
}
const REASONING_DESCRIPTIONS: Record<string, string> = {
  disabled: '快速响应，不额外推理',
  low: '轻量推理，响应更快',
  standard: '平衡速度与分析深度',
  medium: '平衡速度与分析深度',
  high: '更充分地分析复杂任务',
  deep: '深入拆解问题与步骤',
  xhigh: '为复杂任务保留更多推理',
  max: '适合最复杂的任务'
}
// 档位颜色沿用语义色板：越往上越“重”，关档保持中性。
const REASONING_COLORS: Record<string, string> = {
  disabled: 'var(--text-secondary)',
  low: 'var(--sem-flow)',
  standard: 'var(--sem-running)',
  medium: 'var(--sem-running)',
  high: 'var(--sem-waiting)',
  deep: 'var(--sem-artifact)',
  xhigh: 'var(--sem-artifact)',
  max: 'var(--sem-artifact)'
}
const activeReasoningLabel = computed(() => {
  const option = selectedReasoningOption.value
  return option ? reasoningLabel(option.value) : '标准'
})
const activeReasoningShortLabel = computed(() => {
  const option = selectedReasoningOption.value
  return option ? reasoningShortLabel(option) : '标准'
})
const activeReasoningColor = computed(() => {
  const option = selectedReasoningOption.value
  return reasoningColor(option ? option.value : 'standard')
})
const triggerTitle = computed(() => {
  const model = settings.value.selectedModel || '选择模型'
  return `${model} · 思考强度：${activeReasoningLabel.value}`
})
const providerTitle = computed(() => {
  const provider = modelProviderPresets.find(item => item.id === settings.value.provider)
  return provider ? `${provider.name} · ${provider.description}` : '选择模型服务商'
})

function persistSettings(): void {
  saveModelSettings(settings.value)
}

function reasoningLabel(value: ThinkingMode | ReasoningEffort): string {
  return REASONING_LABELS[String(value)] || String(value)
}

function reasoningShortLabel(option: { value: ThinkingMode | ReasoningEffort; shortLabel: string }): string {
  return REASONING_SHORT_LABELS[String(option.value)] || option.shortLabel
}

function reasoningDescription(value: ThinkingMode | ReasoningEffort): string {
  return REASONING_DESCRIPTIONS[String(value)] || '按模型能力调整推理深度'
}

function reasoningColor(value: ThinkingMode | ReasoningEffort): string {
  return REASONING_COLORS[String(value)] || 'var(--text-secondary)'
}

function selectReasoningOption(value: ThinkingMode | ReasoningEffort): void {
  providerMenuOpen.value = false
  reasoningSelection.value = value
  persistSettings()
}

function isSelectedReasoningOption(option: { value: ThinkingMode | ReasoningEffort }): boolean {
  return String(option.value) === String(selectedReasoningOption.value?.value)
}

function selectModel(model: string): void {
  providerMenuOpen.value = false
  if (model === settings.value.selectedModel) return
  settings.value.selectedModel = model
  persistSettings()
}

function chooseProvider(provider: ModelProviderId): void {
  providerMenuOpen.value = false
  if (provider !== settings.value.provider) selectProvider(provider)
}

function compactProviderLabel(provider: ModelProviderId): string {
  const labels: Partial<Record<ModelProviderId, string>> = {
    system: '服务端',
    deepseek: 'DeepSeek',
    glm: 'GLM',
    qwen: 'Qwen',
    openai: 'OpenAI',
    custom: '自定义'
  }
  return labels[provider] || provider
}

function selectProvider(provider: ModelProviderId): void {
  if (!modelProviderPresets.some(item => item.id === provider)) return
  settings.value = applyProviderPreset(settings.value, provider)
  persistSettings()
  if (provider === 'system') void loadSystemModels()
}

function syncSettings(event: Event): void {
  const detail = (event as CustomEvent<ModelSettings>).detail
  const previousProvider = settings.value.provider
  settings.value = detail ? { ...detail, models: [...detail.models] } : loadModelSettings()
  if (settings.value.provider === 'system' && previousProvider !== 'system') void loadSystemModels(true)
}

async function loadSystemModels(preferServerDefault = false): Promise<void> {
  if (settings.value.provider !== 'system') return
  const requestId = ++systemModelsRequest
  modelsLoading.value = true
  try {

    const response = await localFetch(apiUrl('/ai/chat/models'), {
    })
    if (!response.ok || requestId !== systemModelsRequest || settings.value.provider !== 'system') return
    const data = await response.json() as { models?: unknown; default_model?: unknown; capabilities?: unknown }
    const models = Array.isArray(data.models)
      ? data.models.filter((model): model is string => typeof model === 'string' && Boolean(model.trim()))
      : []
    if (!models.length || requestId !== systemModelsRequest || settings.value.provider !== 'system') return

    const defaultModel = typeof data.default_model === 'string' && models.includes(data.default_model)
      ? data.default_model
      : models[0]
    settings.value = {
      ...settings.value,
      models,
      selectedModel: preferServerDefault || !models.includes(settings.value.selectedModel)
        ? defaultModel
        : settings.value.selectedModel
    }
    saveModelSettings(settings.value)
    syncCapabilityFromCatalog(data.capabilities, settings.value.selectedModel)
  } catch {
    // Keep the system-default fallback when the model catalog is unavailable.
  } finally {
    if (requestId === systemModelsRequest) modelsLoading.value = false
  }
}

function syncCapabilityFromCatalog(catalog: unknown, model: string): void {
  const entry = catalog && typeof catalog === 'object'
    ? (catalog as Record<string, unknown>)[model]
    : undefined
  modelCapability.value = capabilityFromPayload(entry)
}

// 档位选择器随服务端能力元数据变化：system 供应商的目录响应已携带 capabilities，
// 其余供应商（自定义 base_url）按需走 /ai/chat/model-capabilities 单查。
watch(
  () => [settings.value.provider, settings.value.selectedModel, settings.value.baseUrl] as const,
  ([provider, model, baseUrl]) => {
    if (provider === 'system') {
      // 目录尚未拉取时不主动清空已有能力；loadSystemModels 会带目录回填。
      if (!modelCapability.value && model) void refreshCapability(model)
      return
    }
    modelCapability.value = null
    if (model) void refreshCapability(model, baseUrl)
  },
  { immediate: true }
)

async function refreshCapability(model: string, baseUrl = ''): Promise<void> {
  const capability = await fetchModelCapability(model, baseUrl)
  if (model === settings.value.selectedModel && (settings.value.provider === 'system' || baseUrl === settings.value.baseUrl)) {
    modelCapability.value = capability
  }
}

onMounted(() => {
  window.addEventListener(MODEL_SETTINGS_EVENT, syncSettings)
  void loadSystemModels()
})
onUnmounted(() => window.removeEventListener(MODEL_SETTINGS_EVENT, syncSettings))

function handleComposerOpen(): void {
  providerMenuOpen.value = false
  if (settings.value.provider === 'system' && !availableModels.value.length) void loadSystemModels()
}
</script>

<style scoped>
.composer-model-trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 240px;
  min-height: 28px;
  padding: 4px 7px 4px 9px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease;
}
.composer-model-trigger:hover { background: color-mix(in srgb, var(--text-primary) 6%, transparent); color: var(--text-primary); }
.composer-model-trigger:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.composer-model-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.composer-model-effort { flex: 0 0 auto; color: color-mix(in srgb, var(--effort-color) 66%, var(--text-secondary)); font-size: 11px; transition: color 200ms ease; }
.composer-model-trigger:hover .composer-model-effort { color: color-mix(in srgb, var(--effort-color) 72%, var(--text-primary)); }
.composer-model-trigger .el-icon { flex: 0 0 auto; font-size: 10px; color: var(--text-muted); }
.model-menu { display: grid; gap: 2px; }
.model-menu__head { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 8px 2px; }
.model-menu__label { color: var(--text-muted); font-size: 11px; font-weight: 600; letter-spacing: .02em; line-height: 16px; }
.model-menu__provider { position: relative; }
.model-menu__provider-trigger {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 24px;
  padding: 0 6px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}
.model-menu__provider-trigger:hover { background: color-mix(in srgb, var(--text-primary) 6%, transparent); color: var(--text-primary); }
.model-menu__provider-trigger:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }
.model-menu__provider-trigger .el-icon { font-size: 9px; transition: transform 140ms ease; }
.model-menu__provider-trigger[aria-expanded="true"] .el-icon { transform: rotate(180deg); }
.model-menu__provider-list {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 3;
  display: grid;
  gap: 1px;
  width: 172px;
  padding: 4px;
  border: 1px solid color-mix(in srgb, var(--border-light) 80%, transparent);
  border-radius: 10px;
  background: var(--bg-panel);
  box-shadow: var(--shadow-md);
}
.model-menu__provider-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  height: 30px;
  padding: 0 8px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}
.model-menu__provider-option:hover { background: color-mix(in srgb, var(--text-primary) 6%, transparent); color: var(--text-primary); }
.model-menu__provider-option.is-selected { color: var(--text-primary); }
.model-menu__provider-option .el-icon { flex: 0 0 auto; font-size: 12px; color: var(--text-secondary); }
.model-menu__list {
  display: grid;
  gap: 1px;
  max-height: 202px;
  padding: 2px 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.model-menu__list::-webkit-scrollbar { width: 4px; }
.model-menu__list::-webkit-scrollbar-thumb { border-radius: 999px; background: color-mix(in srgb, var(--text-primary) 16%, transparent); }
.model-menu__model {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 32px;
  padding: 0 8px 0 9px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-regular);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}
.model-menu__model:hover { background: color-mix(in srgb, var(--text-primary) 6%, transparent); color: var(--text-primary); }
.model-menu__model:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
.model-menu__model.is-selected { color: var(--text-primary); }
.model-menu__model-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.model-menu__check { flex: 0 0 auto; margin-left: auto; font-size: 12px; color: var(--text-secondary); }
.model-menu__empty { margin: 0; padding: 10px 8px; color: var(--text-muted); font-size: 11px; text-align: center; }
.model-menu__divider { height: 1px; margin: 6px 5px; background: color-mix(in srgb, var(--border-light) 62%, transparent); }
.model-menu__effort { display: grid; gap: 6px; padding: 2px 8px 6px; }
.model-menu__segments {
  position: relative;
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--text-primary) 5%, transparent);
  isolation: isolate;
}
.model-menu__segment-thumb {
  position: absolute;
  z-index: 0;
  top: 3px;
  bottom: 3px;
  left: 3px;
  width: calc((100% - 6px - (var(--segment-count) - 1) * 2px) / var(--segment-count));
  border-radius: 7px;
  background: color-mix(in srgb, var(--effort-color) 18%, transparent);
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--effort-color) 34%, transparent),
    0 2px 12px color-mix(in srgb, var(--effort-color) 16%, transparent);
  transform: translateX(calc(var(--segment-index) * (100% + 2px)));
  transition:
    transform 300ms cubic-bezier(.22, 1, .36, 1),
    background-color 240ms ease,
    box-shadow 240ms ease;
  pointer-events: none;
}
.model-menu__segment {
  position: relative;
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  flex: 1 1 0;
  min-width: 0;
  height: 28px;
  padding: 0 4px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 200ms ease, background-color 160ms ease, transform 160ms ease;
}
.model-menu__segment:hover {
  background: color-mix(in srgb, var(--segment-color) 9%, transparent);
  color: color-mix(in srgb, var(--segment-color) 70%, var(--text-primary));
}
.model-menu__segment:active { transform: scale(.97); }
.model-menu__segment.is-selected {
  color: var(--segment-color);
  font-weight: 600;
}
.model-menu__segment:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 0; }
.model-menu__segment-dot {
  position: relative;
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--segment-color) 52%, transparent);
  transition: background-color 200ms ease, box-shadow 200ms ease, transform 200ms ease;
}
.model-menu__segment.is-selected .model-menu__segment-dot {
  background: var(--segment-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--segment-color) 22%, transparent);
  transform: scale(1.12);
}
.model-menu__segment-dot::after {
  content: '';
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  background: color-mix(in srgb, var(--segment-color) 42%, transparent);
  opacity: 0;
  pointer-events: none;
}
.model-menu__segment.is-selected .model-menu__segment-dot::after {
  animation: model-menu-dot-ring 460ms cubic-bezier(.2, .8, .2, 1) both;
}
@keyframes model-menu-dot-ring {
  0% { opacity: .5; transform: scale(.45); }
  70% { opacity: .16; }
  100% { opacity: 0; transform: scale(1.75); }
}
.model-menu__hint-slot { display: flex; align-items: center; min-height: 16px; }
.model-menu__hint {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  overflow: hidden;
  color: color-mix(in srgb, var(--effort-color) 38%, var(--text-secondary));
  font-size: 11px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.model-menu__hint-dot {
  width: 4px;
  height: 4px;
  flex: 0 0 4px;
  border-radius: 50%;
  background: var(--effort-color);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--effort-color) 12%, transparent);
  transition: background-color 240ms ease, box-shadow 240ms ease;
  animation: model-menu-hint-dot-in 260ms cubic-bezier(.2, .8, .2, 1) both;
}
@keyframes model-menu-hint-dot-in {
  from { opacity: 0; transform: scale(.4); }
  to { opacity: 1; transform: scale(1); }
}
.model-menu__check { animation: model-menu-check-in 200ms cubic-bezier(.2, .9, .3, 1.35) both; }
@keyframes model-menu-check-in {
  from { opacity: 0; transform: scale(.55); }
  to { opacity: 1; transform: scale(1); }
}
.model-menu-hint-enter-active { transition: opacity 140ms ease, transform 140ms ease; }
.model-menu-hint-leave-active { transition: opacity 90ms ease, transform 90ms ease; }
.model-menu-hint-enter-from { opacity: 0; transform: translateY(3px); }
.model-menu-hint-leave-to { opacity: 0; transform: translateY(-3px); }
.model-menu-pop-enter-active,
.model-menu-pop-leave-active { transition: opacity 120ms ease, transform 120ms ease; }
.model-menu-pop-enter-from,
.model-menu-pop-leave-to { opacity: 0; transform: translateY(-3px) scale(.98); }

@media (max-width: 620px) {
  .composer-model-trigger { max-width: 168px; padding-inline: 5px; font-size: 11px; }
}
@media (prefers-reduced-motion: reduce) {
  .model-menu__segment-thumb,
  .model-menu__segment,
  .model-menu__segment-dot,
  .model-menu__hint-dot,
  .model-menu__check { animation: none; transition: none; }
  .model-menu__segment.is-selected .model-menu__segment-dot::after { animation: none; opacity: 0; }
  .model-menu-hint-enter-active,
  .model-menu-hint-leave-active,
  .model-menu-pop-enter-active,
  .model-menu-pop-leave-active { transition: none; }
}

.model-runtime-controls {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}

.model-select {
  width: 164px;
}

.provider-select {
  width: 138px;
}

.reasoning-select {
  width: 126px;
}

.model-runtime-controls.compact .provider-select {
  width: 88px;
}

.model-runtime-controls.compact .model-select {
  width: 112px;
}

.model-runtime-controls.compact .reasoning-select {
  width: 82px;
}

.model-runtime-controls :deep(.el-select__wrapper) {
  min-height: 28px;
  padding: 0 8px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--bg-card) 78%, transparent);
  box-shadow: 0 0 0 1px var(--border-light) inset;
}

.model-runtime-controls :deep(.el-select__selected-item),
.model-runtime-controls :deep(.el-select__placeholder) {
  font-size: 11px;
}

.model-runtime-controls :deep(.el-select__prefix),
.model-runtime-controls :deep(.el-select__suffix) {
  font-size: 12px;
}

.model-runtime-controls :deep(.el-select__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--border-hover) inset;
}

@media (max-width: 620px) {
  .model-runtime-controls,
  .model-runtime-controls.compact {
    width: 100%;
  }

  .model-runtime-controls .model-select,
  .model-runtime-controls.compact .model-select {
    width: auto;
    flex: 1 1 auto;
  }

  .model-runtime-controls .provider-select,
  .model-runtime-controls.compact .provider-select {
    width: 92px;
    flex: 0 0 92px;
  }

  .model-runtime-controls .reasoning-select,
  .model-runtime-controls.compact .reasoning-select {
    width: 92px;
    flex: 0 0 92px;
  }
}
</style>

<style>
.composer-model-popover.el-popover.el-popper {
  width: min(336px, calc(100vw - 24px)) !important;
  max-width: calc(100vw - 24px);
  padding: 6px;
  border: 1px solid color-mix(in srgb, var(--border-light) 74%, transparent);
  border-radius: 16px;
  background: color-mix(in srgb, var(--bg-card) 94%, var(--bg-panel));
  box-shadow: var(--shadow-lg), 0 0 0 1px color-mix(in srgb, var(--text-primary) 3%, transparent) inset;
  animation: composer-model-popover-in 140ms cubic-bezier(.2, .8, .2, 1);
}
.composer-model-popover .el-popper__arrow { display: none; }
@keyframes composer-model-popover-in {
  from { opacity: 0; transform: translateY(4px) scale(.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
@media (prefers-reduced-motion: reduce) {
  .composer-model-popover.el-popover.el-popper { animation: none; }
}
</style>
