<!-- 设置中心页面 — Tab 切换管理配色、语言、隐私、对话与语音等偏好设置 -->
<template>
  <div class="settings-view">
    <section class="page-header glass-panel">
      <div>
        <h1>设置中心</h1>
        <p>在这里统一管理配色、隐私、对话与语音设置。</p>
      </div>
      <div class="status-chip">
        上次保存：{{ lastSavedText }}
      </div>
    </section>

    <section class="tabs-bar glass-panel">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="tab-btn"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
      >
        <el-icon><component :is="tab.icon" /></el-icon>
        <span>{{ tab.label }}</span>
      </button>
    </section>

    <section class="content-panel glass-panel">
      <div v-if="activeTab === 'general'" class="form-grid">
        <el-form-item label="语言">
          <el-select v-model="settings.language" @change="handleLanguageChange">
            <el-option label="简体中文" value="zh-CN" />
            <el-option label="English" value="en" />
          </el-select>
        </el-form-item>

        <el-form-item label="字体大小">
          <div class="slider-box">
            <el-slider v-model="settings.fontSize" :min="12" :max="20" />
            <span>{{ settings.fontSize }}px</span>
          </div>
        </el-form-item>

        <el-form-item label="配色方案">
          <div class="scheme-row">
            <button
              v-for="s in colorSchemes"
              :key="s.id"
              class="scheme-chip"
              :class="{ active: settings.colorScheme === s.id }"
              @click="settings.colorScheme = s.id; applyTheme()"
            >
              <span class="scheme-dot" :style="{ background: s.previewColor }"></span>
              <span>{{ s.name }}</span>
            </button>
          </div>
        </el-form-item>
      </div>

      <div v-if="activeTab === 'privacy'" class="form-grid">
        <el-form-item label="存储位置">
          <el-radio-group v-model="settings.storageLocation">
            <el-radio-button label="local">本地</el-radio-button>
            <el-radio-button label="cloud">云端</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <el-form-item label="自动删除记录">
          <el-select v-model="settings.autoDelete">
            <el-option label="永不删除" value="never" />
            <el-option label="7天后删除" value="7" />
            <el-option label="30天后删除" value="30" />
          </el-select>
        </el-form-item>

        <el-form-item label="隐私密码">
          <el-input
            v-model="settings.privacyPassword"
            type="password"
            show-password
            placeholder="可选，用于保护敏感设置"
          />
        </el-form-item>
      </div>

      <div v-if="activeTab === 'chat'" class="form-grid">
        <div class="switch-row">
          <div>
            <strong>自动发送</strong>
            <p>输入后回车直接发送消息。</p>
          </div>
          <el-switch v-model="settings.autoSend" />
        </div>

        <div class="switch-row">
          <div>
            <strong>消息提示音</strong>
            <p>AI 回复完成后播放提示音。</p>
          </div>
          <el-switch v-model="settings.messageSound" />
        </div>

        <el-form-item label="历史保留时长">
          <el-select v-model="settings.historyRetention">
            <el-option label="1天" value="1" />
            <el-option label="7天" value="7" />
            <el-option label="30天" value="30" />
            <el-option label="永久" value="forever" />
          </el-select>
        </el-form-item>
      </div>

      <div v-if="activeTab === 'model'" class="model-settings">
        <div class="section-heading">
          <div>
            <h2>模型服务</h2>
            <p>选择服务商并配置当前浏览器使用的模型连接。</p>
          </div>
          <span class="local-only-badge"><el-icon><Lock /></el-icon> 仅存本机</span>
        </div>

        <div class="provider-grid" role="radiogroup" aria-label="模型服务商">
          <button
            v-for="provider in modelProviderPresets"
            :key="provider.id"
            class="provider-option"
            :class="{ active: modelSettings.provider === provider.id }"
            type="button"
            role="radio"
            :aria-checked="modelSettings.provider === provider.id"
            @click="selectProvider(provider.id)"
          >
            <span class="provider-mark">{{ provider.name.slice(0, 1) }}</span>
            <span class="provider-copy">
              <strong>{{ provider.name }}</strong>
              <small>{{ provider.description }}</small>
            </span>
            <el-icon v-if="modelSettings.provider === provider.id" class="provider-check"><Check /></el-icon>
          </button>
        </div>

        <div v-if="modelSettings.provider !== 'system'" class="connection-form">
          <el-form-item label="API 地址" required>
            <el-input v-model="modelSettings.baseUrl" placeholder="https://api.example.com/v1" />
          </el-form-item>

          <el-form-item label="API Key" required>
            <el-input
              v-model="modelSettings.apiKey"
              type="password"
              show-password
              autocomplete="off"
              placeholder="输入服务商 API Key"
            />
          </el-form-item>

          <el-form-item label="可用模型" required>
            <el-select
              v-model="modelSettings.models"
              multiple
              filterable
              allow-create
              default-first-option
              placeholder="输入模型名称后按回车添加"
              @change="ensureSelectedModel"
            >
              <el-option v-for="model in modelSettings.models" :key="model" :label="model" :value="model" />
            </el-select>
          </el-form-item>

          <el-form-item label="默认模型" required>
            <el-select v-model="modelSettings.selectedModel" filterable allow-create placeholder="选择默认模型">
              <el-option v-for="model in modelSettings.models" :key="model" :label="model" :value="model" />
            </el-select>
          </el-form-item>
        </div>

        <div v-else class="system-provider-note">
          <el-icon><InfoFilled /></el-icon>
          <span>继续使用服务端配置的默认模型，无需在浏览器中填写 API Key。</span>
        </div>
      </div>

      <div v-if="activeTab === 'voice'" class="form-grid">
        <el-form-item label="语音类型">
          <el-select v-model="settings.voice">
            <el-option label="默认助手" value="default" />
            <el-option label="女声A" value="female" />
            <el-option label="男声A" value="male" />
            <el-option label="女声B" value="gentle" />
            <el-option label="男声B" value="lively" />
          </el-select>
        </el-form-item>

        <el-form-item label="语速">
          <div class="slider-box">
            <el-slider v-model="settings.speed" :min="0.5" :max="2.0" :step="0.1" />
            <span>{{ settings.speed.toFixed(1) }}x</span>
          </div>
        </el-form-item>

        <el-form-item label="音调">
          <div class="slider-box">
            <el-slider v-model="settings.pitch" :min="0.5" :max="2.0" :step="0.1" />
            <span>{{ settings.pitch.toFixed(1) }}x</span>
          </div>
        </el-form-item>
      </div>
    </section>

    <section class="footer-bar glass-panel">
      <div class="hint">
        <el-icon><InfoFilled /></el-icon>
        <span>{{ inlineHint }}</span>
      </div>
      <div class="actions">
        <el-button @click="resetSettings">重置</el-button>
        <el-button type="primary" @click="saveSettings">保存设置</el-button>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { Setting, Lock, ChatDotRound, Microphone, InfoFilled, Cpu, Check } from '@element-plus/icons-vue'
import { applyFontSize, useTheme } from '@/composables/useTheme'
import { colorSchemes, type ColorSchemeId } from '@/themes/presets'
import {
  applyProviderPreset,
  getDefaultModelSettings,
  loadModelSettings,
  modelProviderPresets,
  saveModelSettings,
  type ModelProviderId
} from '@/config/modelSettings'

type TabId = 'general' | 'privacy' | 'chat' | 'model' | 'voice'

interface AppSettings {
  colorScheme: ColorSchemeId
  language: 'zh-CN' | 'en'
  fontSize: number
  primaryColor: string
  storageLocation: 'local' | 'cloud'
  autoDelete: 'never' | '7' | '30'
  privacyPassword: string
  autoSend: boolean
  messageSound: boolean
  historyRetention: '1' | '7' | '30' | 'forever'
  voice: 'default' | 'female' | 'male' | 'gentle' | 'lively'
  speed: number
  pitch: number
}

const { locale } = useI18n()
const { applyColorScheme } = useTheme()

const tabs = [
  { id: 'general' as TabId, label: '通用', icon: Setting },
  { id: 'privacy' as TabId, label: '隐私', icon: Lock },
  { id: 'chat' as TabId, label: '对话', icon: ChatDotRound },
  { id: 'model' as TabId, label: '模型与 API', icon: Cpu },
  { id: 'voice' as TabId, label: '语音', icon: Microphone }
]

const defaultSettings = (): AppSettings => ({
  colorScheme: 'codex-dark',
  language: 'zh-CN',
  fontSize: 14,
  primaryColor: '#4f46e5',
  storageLocation: 'local',
  autoDelete: 'never',
  privacyPassword: '',
  autoSend: false,
  messageSound: true,
  historyRetention: '7',
  voice: 'default',
  speed: 1.0,
  pitch: 1.0
})

const settings = ref<AppSettings>(defaultSettings())
const modelSettings = ref(getDefaultModelSettings())
const activeTab = ref<TabId>('general')
const lastSaved = ref<Date | null>(null)
const inlineHint = ref('修改后点击“保存设置”即可生效。')

const lastSavedText = computed(() => {
  if (!lastSaved.value) return '尚未保存'
  return lastSaved.value.toLocaleTimeString('zh-CN', { hour12: false })
})

function applyTheme(): void {
  applyColorScheme(settings.value.colorScheme)
  applyFontSize(settings.value.fontSize)
}

watch(() => settings.value.fontSize, (fontSize) => {
  applyFontSize(fontSize)
})

function handleLanguageChange(newLang: 'zh-CN' | 'en'): void {
  locale.value = newLang
  inlineHint.value = `语言已切换为 ${newLang === 'zh-CN' ? '简体中文' : 'English'}，记得保存设置。`
}

function loadSettings(): void {
  const saved = localStorage.getItem('appSettings')
  if (!saved) return
  try {
    const parsed = JSON.parse(saved) as Partial<AppSettings> & { theme?: unknown }
    const { theme: _legacyTheme, ...savedSettings } = parsed
    settings.value = { ...defaultSettings(), ...savedSettings }
    locale.value = settings.value.language
    applyTheme()
    inlineHint.value = '已读取本地设置。'
  } catch {
    settings.value = defaultSettings()
    inlineHint.value = '本地设置解析失败，已使用默认配置。'
  }
}

function saveSettings(): void {
  if (modelSettings.value.provider !== 'system') {
    if (!modelSettings.value.baseUrl.trim() || !modelSettings.value.apiKey.trim() || !modelSettings.value.selectedModel.trim()) {
      activeTab.value = 'model'
      inlineHint.value = '请完整填写 API 地址、API Key 和默认模型。'
      return
    }
    if (!/^https?:\/\//i.test(modelSettings.value.baseUrl.trim())) {
      activeTab.value = 'model'
      inlineHint.value = 'API 地址必须以 http:// 或 https:// 开头。'
      return
    }
  }
  localStorage.setItem('appSettings', JSON.stringify(settings.value))
  saveModelSettings(modelSettings.value)
  applyTheme()
  lastSaved.value = new Date()
  inlineHint.value = '设置已保存。'
}

function resetSettings(): void {
  settings.value = defaultSettings()
  modelSettings.value = getDefaultModelSettings()
  locale.value = 'zh-CN'
  localStorage.removeItem('appSettings')
  saveModelSettings(modelSettings.value)
  applyTheme()
  lastSaved.value = new Date()
  inlineHint.value = '已恢复默认设置。'
}

onMounted(() => {
  loadSettings()
  modelSettings.value = loadModelSettings()
})

function selectProvider(provider: ModelProviderId): void {
  modelSettings.value = applyProviderPreset(modelSettings.value, provider)
  inlineHint.value = provider === 'system' ? '已选择服务端默认模型。' : '请检查 API Key 后保存设置。'
}

function ensureSelectedModel(models: string[]): void {
  if (!models.includes(modelSettings.value.selectedModel)) {
    modelSettings.value.selectedModel = models[0] || ''
  }
}
</script>

<style scoped>
.settings-view {
  position: relative;
  width: 100%;
  height: 100%;
  padding: var(--page-padding-y) var(--page-padding-x);
  display: flex;
  flex-direction: column;
  gap: var(--page-gap);
  color: var(--text-primary);
  overflow-y: auto;
  overflow-x: hidden;
}

.glass-panel {
  position: relative;
  z-index: 1;
  background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  box-shadow: var(--shadow-sm);
}

.page-header {
  padding: 16px 18px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
}

.page-header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.status-chip {
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--primary-color);
  padding: 6px 12px;
  font-size: 12px;
  white-space: nowrap;
}

.tabs-bar {
  padding: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.tab-btn {
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  color: var(--text-secondary);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
}

.tab-btn.active {
  background: var(--primary-fade);
  border-color: var(--primary-line);
  color: var(--primary-color);
}

.content-panel {
  padding: 16px;
}

.form-grid {
  display: grid;
  gap: 16px;
}

.model-settings {
  display: grid;
  gap: 20px;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.section-heading h2 {
  margin: 0;
  font-size: 18px;
}

.section-heading p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.local-only-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  padding: 5px 9px;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  color: var(--text-secondary);
  font-size: 12px;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
}

.provider-option {
  position: relative;
  min-height: 90px;
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition: var(--transition);
}

.provider-option:hover {
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

.provider-option.active {
  border-color: var(--primary-color);
  background: var(--primary-fade);
  box-shadow: 0 0 0 1px var(--primary-line);
}

.provider-mark {
  display: grid;
  width: 26px;
  height: 26px;
  margin-bottom: 9px;
  place-items: center;
  border-radius: 6px;
  background: var(--primary-color);
  color: #fff;
  font-size: 12px;
  font-weight: 700;
}

.provider-copy {
  display: grid;
  gap: 3px;
}

.provider-copy strong {
  font-size: 13px;
}

.provider-copy small {
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.35;
}

.provider-check {
  position: absolute;
  top: 10px;
  right: 10px;
  color: var(--primary-color);
}

.connection-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px 18px;
  padding-top: 18px;
  border-top: 1px solid var(--border-light);
}

.connection-form :deep(.el-select) {
  width: 100%;
}

.system-provider-note {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--primary-fade);
  color: var(--text-secondary);
  font-size: 13px;
}

.slider-box {
  display: flex;
  align-items: center;
  gap: 10px;
}

.slider-box span {
  width: 58px;
  color: var(--text-secondary);
  font-size: 12px;
}

.switch-row {
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.switch-row strong {
  display: block;
}

.switch-row p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.footer-bar {
  padding: 12px 14px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.hint {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.actions {
  display: flex;
  gap: 8px;
}

.scheme-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.scheme-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: var(--bg-card);
  color: var(--text-regular);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
}

.scheme-chip:hover {
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

.scheme-chip.active {
  border-color: var(--primary-line);
  background: var(--primary-fade);
  color: var(--primary-color);
  box-shadow: 0 0 0 1px var(--primary-line);
}

.scheme-dot {
  width: 18px;
  height: 18px;
  border-radius: 6px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  flex-shrink: 0;
}

@media (max-width: 760px) {
  .settings-view {
    padding: var(--space-md);
    gap: var(--space-md);
  }

  .page-header {
    flex-direction: column;
  }

  .footer-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .actions {
    justify-content: flex-end;
  }

  .provider-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .connection-form {
    grid-template-columns: 1fr;
  }

  .section-heading {
    flex-direction: column;
  }
}

@media (min-width: 761px) and (max-width: 1100px) {
  .provider-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
