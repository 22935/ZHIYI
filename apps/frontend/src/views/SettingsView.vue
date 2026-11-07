<!-- 个人设置页面 — 延续 AgentOS 深色工作区，并采用侧栏分组 + 单列设置内容的结构。 -->
<template>
  <div class="settings-view">
    <aside class="settings-rail" aria-label="设置导航">
      <button class="back-to-app" type="button" @click="goBack">
        <el-icon><ArrowLeft /></el-icon>
        返回
      </button>
      <div class="settings-search">
        <el-icon aria-hidden="true"><Search /></el-icon>
        <input v-model="searchTerm" type="search" placeholder="搜索设置..." aria-label="搜索设置" />
      </div>

      <nav class="settings-nav">
        <section v-for="section in visibleSections" :key="section.label" class="settings-nav-section">
          <h2>{{ section.label }}</h2>
          <button
            v-for="item in section.items"
            :key="item.id"
            class="settings-nav-item"
            :class="{ active: activeTab === item.id && !item.route }"
            type="button"
            @click="selectSettingsItem(item)"
          >
            <el-icon><component :is="item.icon" /></el-icon>
            <span>{{ item.label }}</span>
            <el-icon v-if="item.route" class="item-arrow"><ArrowLeft /></el-icon>
          </button>
        </section>
        <p v-if="!visibleSections.length" class="settings-empty">没有匹配的设置</p>
      </nav>
    </aside>

    <main class="settings-content">
      <header class="settings-header">
        <div>
          <span class="settings-eyebrow">PERSONAL SETTINGS</span>
          <h1>{{ currentTab.label }}</h1>
          <p>{{ currentTab.description }}</p>
        </div>
        <div class="settings-header-actions">
          <span class="save-state" :class="{ saved: lastSaved }">
            <i aria-hidden="true"></i>
            {{ lastSaved ? `已保存 ${lastSavedText}` : '本地设置' }}
          </span>
          <el-button type="primary" class="header-save" @click="saveSettings">
            <el-icon><Check /></el-icon>
            保存设置
          </el-button>
        </div>
      </header>

      <section v-if="activeTab === 'general'" class="settings-section">
        <div class="section-label">权限</div>
        <div class="setting-card">
          <div class="setting-row">
            <div>
              <strong>默认权限</strong>
              <p>默认情况下，知弈可以读取和编辑当前工作空间中的文件。</p>
            </div>
            <el-switch v-model="settings.defaultPermission" aria-label="默认权限" />
          </div>
          <div class="setting-row">
            <div>
              <strong>完整访问权限</strong>
              <p>允许任务在需要时访问工作空间之外的文件，使用前请确认任务边界。</p>
            </div>
            <el-switch v-model="settings.fullAccess" aria-label="完整访问权限" />
          </div>
        </div>

        <div class="section-label">常规</div>
        <div class="setting-card">
          <div class="setting-row setting-row-control">
            <div>
              <strong>无项目任务文件夹</strong>
              <p>在项目外启动的任务默认存储数据的位置。</p>
            </div>
            <el-input v-model="settings.workspaceFolder" class="inline-input" aria-label="无项目任务文件夹" />
          </div>
          <div class="setting-row setting-row-control">
            <div>
              <strong>语言</strong>
              <p>应用界面使用的语言。</p>
            </div>
            <el-select v-model="settings.language" class="inline-select" @change="handleLanguageChange">
              <el-option label="简体中文" value="zh-CN" />
              <el-option label="English" value="en" />
            </el-select>
          </div>
          <div class="setting-row setting-row-control">
            <div>
              <strong>界面缩放</strong>
              <p>调整界面文字与控件的整体尺寸，等同 Ctrl+滚轮缩放。</p>
            </div>
            <div class="compact-slider">
              <el-slider v-model="uiZoomLevelModel" :min="UI_ZOOM_MIN_LEVEL" :max="UI_ZOOM_MAX_LEVEL" :step="0.01" aria-label="界面缩放" />
              <span>{{ uiZoomPercentage(uiZoomLevelModel) }}%</span>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'appearance'" class="settings-section">
        <div class="section-label theme-header-row">
          <span>主题</span>
          <el-select
            v-model="settings.colorScheme"
            class="theme-select"
            aria-label="选择主题"
            @change="applyTheme()"
          >
            <el-option v-for="theme in themeOptions" :key="theme.id" :value="theme.id" :label="theme.label">
              <div class="theme-select-option">
                <span class="theme-aa" :style="{ background: theme.accent }">Aa</span>
                <span class="theme-select-name">{{ theme.label }}</span>
                <span class="theme-select-en">{{ theme.nameEn }}</span>
                <el-icon v-if="settings.colorScheme === theme.id" class="theme-select-check"><Check /></el-icon>
              </div>
            </el-option>
          </el-select>
        </div>
        <div class="theme-grid">
          <button
            v-for="theme in themeOptions"
            :key="theme.id"
            class="theme-option"
            :class="[{ active: settings.colorScheme === theme.id }, `theme-${theme.tone}`]"
            type="button"
            @click="settings.colorScheme = theme.id; applyTheme()"
          >
            <span
              class="theme-preview"
              :style="{
                '--pv-bg': theme.bgApp,
                '--pv-side': theme.bgPanel,
                '--pv-card': theme.bgCard,
                '--pv-fg': theme.fg,
                '--pv-accent': theme.accent,
                '--pv-border': theme.border
              }"
            >
              <i></i><i></i><i></i>
              <b></b><b></b>
            </span>
            <span class="theme-option-footer">
              <strong>{{ theme.label }}</strong>
              <el-icon v-if="settings.colorScheme === theme.id"><Check /></el-icon>
            </span>
          </button>
        </div>

        <div class="section-label">主题色值</div>
        <div class="setting-card">
          <div v-for="row in themeDetailRows" :key="row.label" class="setting-row">
            <div>
              <strong>{{ row.label }}</strong>
              <p>{{ row.desc }}</p>
            </div>
            <span class="color-chip">
              <i :style="{ background: row.value }"></i>
              <code>{{ row.value }}</code>
            </span>
          </div>
        </div>

        <div class="section-label">界面</div>
        <div class="setting-card">
          <div class="setting-row">
            <div>
              <strong>紧凑侧边栏</strong>
              <p>减少导航留白，为工作区保留更多空间。</p>
            </div>
            <el-switch v-model="settings.compactSidebar" aria-label="紧凑侧边栏" />
          </div>
          <div class="setting-row">
            <div>
              <strong>显示底部状态栏</strong>
              <p>在编辑器底部显示当前工作区状态。</p>
            </div>
            <el-switch v-model="settings.showStatusBar" aria-label="显示底部状态栏" />
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'privacy'" class="settings-section">
        <div class="section-label">隐私与数据</div>
        <div class="setting-card">
          <div class="setting-row setting-row-control">
            <div>
              <strong>存储位置</strong>
              <p>对话记录和本地偏好设置保存的位置。</p>
            </div>
            <el-radio-group v-model="settings.storageLocation" class="segmented-control">
              <el-radio-button label="local">本地</el-radio-button>
              <el-radio-button label="cloud">云端</el-radio-button>
            </el-radio-group>
          </div>
          <div class="setting-row setting-row-control">
            <div>
              <strong>自动删除记录</strong>
              <p>自动清理旧对话，释放本地存储空间。</p>
            </div>
            <el-select v-model="settings.autoDelete" class="inline-select">
              <el-option label="永不删除" value="never" />
              <el-option label="7天后删除" value="7" />
              <el-option label="30天后删除" value="30" />
            </el-select>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'chat'" class="settings-section">
        <div class="section-label">对话体验</div>
        <div class="setting-card">
          <div class="setting-row">
            <div>
              <strong>自动发送</strong>
              <p>输入后按回车直接发送消息。</p>
            </div>
            <el-switch v-model="settings.autoSend" aria-label="自动发送" />
          </div>
          <div class="setting-row">
            <div>
              <strong>消息提示音</strong>
              <p>AI 回复完成后播放提示音。</p>
            </div>
            <el-switch v-model="settings.messageSound" aria-label="消息提示音" />
          </div>
          <div class="setting-row setting-row-control">
            <div>
              <strong>历史保留时长</strong>
              <p>控制本地历史对话的保留时间。</p>
            </div>
            <el-select v-model="settings.historyRetention" class="inline-select">
              <el-option label="1天" value="1" />
              <el-option label="7天" value="7" />
              <el-option label="30天" value="30" />
              <el-option label="永久" value="forever" />
            </el-select>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'model'" class="settings-section">
        <div class="section-label">模型服务</div>
        <div class="section-heading">
          <div>
            <h2>当前连接</h2>
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
        <div v-if="modelSettings.provider !== 'system'" class="connection-form setting-card">
          <el-form-item label="API 地址" required>
            <el-input v-model="modelSettings.baseUrl" placeholder="https://api.example.com/v1" />
          </el-form-item>
          <el-form-item label="API Key" required>
            <el-input v-model="modelSettings.apiKey" type="password" show-password autocomplete="off" placeholder="输入服务商 API Key" />
          </el-form-item>
          <el-form-item label="可用模型" required>
            <el-select v-model="modelSettings.models" multiple filterable allow-create default-first-option class="wide-control" placeholder="输入模型名称后按回车添加" @change="ensureSelectedModel">
              <el-option v-for="model in modelSettings.models" :key="model" :label="model" :value="model" />
            </el-select>
          </el-form-item>
          <el-form-item label="默认模型" required>
            <el-select v-model="modelSettings.selectedModel" filterable allow-create class="wide-control" placeholder="选择默认模型">
              <el-option v-for="model in modelSettings.models" :key="model" :label="model" :value="model" />
            </el-select>
          </el-form-item>
        </div>
        <div v-else class="server-provider-panel">
          <div class="system-provider-note">
            <el-icon><InfoFilled /></el-icon>
            <span>服务端供应商对新对话与新任务即时生效，无需重启；切换影响整个部署。</span>
          </div>
          <div class="server-profile-list" v-loading="serverProfilesLoading">
            <div
              v-for="profile in serverProfiles"
              :key="profile.name"
              class="server-profile-item"
              :class="{ active: profile.active, unusable: !profile.usable }"
              role="radio"
              :aria-checked="profile.active"
              @click="switchServerProfile(profile)"
            >
              <span class="provider-mark">{{ profile.name.slice(0, 1) }}</span>
              <span class="provider-copy">
                <strong>{{ profile.name }}</strong>
                <small>{{ profile.provider }} · {{ profile.model }} · {{ profileHost(profile.base_url) }}</small>
              </span>
              <span class="server-profile-state">
                <span v-if="serverTestResults[profile.name]" class="server-test-result" :class="{ ok: serverTestResults[profile.name].ok }">{{ serverTestResults[profile.name].text }}</span>
                <el-tag v-if="profile.active" size="small" type="success">当前</el-tag>
                <el-tag v-else-if="!profile.usable" size="small" type="info">缺密钥</el-tag>
                <el-button size="small" text :disabled="serverActionBusy" @click.stop="testServerProfile(profile)">测试</el-button>
              </span>
            </div>
          </div>
          <div class="server-profile-actions">
            <el-button size="small" @click="showAddServerProfile = !showAddServerProfile">新增供应商</el-button>
          </div>
          <div v-if="showAddServerProfile" class="connection-form setting-card">
            <el-form-item label="名称" required>
              <el-input v-model="serverProfileDraft.name" placeholder="例如 glm-payg" />
            </el-form-item>
            <el-form-item label="类型" required>
              <el-select v-model="serverProfileDraft.provider" class="wide-control">
                <el-option v-for="p in serverProviderTypes" :key="p.value" :label="p.label" :value="p.value" />
              </el-select>
            </el-form-item>
            <el-form-item label="API 地址" required>
              <el-input v-model="serverProfileDraft.base_url" placeholder="https://open.bigmodel.cn/api/paas/v4" />
            </el-form-item>
            <el-form-item label="模型" required>
              <el-input v-model="serverProfileDraft.model" placeholder="glm-5.3-flash" />
            </el-form-item>
            <el-form-item label="API Key" required>
              <el-input v-model="serverProfileDraft.api_key" type="password" show-password autocomplete="off" placeholder="留空则改用下方密钥环境变量名" />
            </el-form-item>
            <el-form-item label="密钥环境变量名">
              <el-input v-model="serverProfileDraft.api_key_env" placeholder="例如 GLM_API_KEY（支持 *_FILE 密钥文件）" />
            </el-form-item>
            <div class="server-profile-actions">
              <el-button size="small" type="primary" :loading="serverActionBusy" @click="addServerProfile">保存到服务端</el-button>
            </div>
          </div>
        </div>
      </section>

      <section v-else-if="activeTab === 'voice'" class="settings-section">
        <div class="section-label">语音输出</div>
        <div class="setting-card">
          <div class="setting-row setting-row-control">
            <div>
              <strong>语音类型</strong>
              <p>选择语音讲解时使用的声音。</p>
            </div>
            <el-select v-model="settings.voice" class="inline-select">
              <el-option label="默认助手" value="default" />
              <el-option label="女声A" value="female" />
              <el-option label="男声A" value="male" />
              <el-option label="女声B" value="gentle" />
              <el-option label="男声B" value="lively" />
            </el-select>
          </div>
          <div class="setting-row setting-row-control">
            <div>
              <strong>语速</strong>
              <p>调整语音播放的速度。</p>
            </div>
            <div class="compact-slider">
              <el-slider v-model="settings.speed" :min="0.5" :max="2.0" :step="0.1" aria-label="语速" />
              <span>{{ settings.speed.toFixed(1) }}x</span>
            </div>
          </div>
          <div class="setting-row setting-row-control">
            <div>
              <strong>音调</strong>
              <p>调整语音输出的音调。</p>
            </div>
            <div class="compact-slider">
              <el-slider v-model="settings.pitch" :min="0.5" :max="2.0" :step="0.1" aria-label="音调" />
              <span>{{ settings.pitch.toFixed(1) }}x</span>
            </div>
          </div>
        </div>
      </section>

      <footer class="settings-footer">
        <div class="hint"><el-icon><InfoFilled /></el-icon><span>{{ inlineHint }}</span></div>
        <div class="actions">
          <el-button @click="resetSettings">恢复默认</el-button>
          <el-button type="primary" @click="saveSettings">保存设置</el-button>
        </div>
      </footer>
    </main>
  </div>
</template>

<script setup lang="ts">
import { localFetch } from '@/platform/api'
import { computed, onMounted, ref, watch, type Component } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { apiUrl } from '@/platform/api'
import { ArrowLeft, Brush, ChatDotRound, Check, Cpu, InfoFilled, Key, Lock, Microphone, Search, Setting } from '@element-plus/icons-vue'
import { useTheme } from '@/composables/useTheme'
import { UI_ZOOM_BASE, UI_ZOOM_MAX_LEVEL, UI_ZOOM_MIN_LEVEL, UI_ZOOM_STORAGE_KEY, setUiZoomLevel, uiZoomPercentage, uiZoomState } from '@/composables/useUiZoom'
import { colorSchemes, type ColorSchemeId } from '@/themes/presets'
import {
  applyProviderPreset,
  getDefaultModelSettings,
  loadModelSettings,
  modelProviderPresets,
  saveModelSettings,
  type ModelProviderId
} from '@/config/modelSettings'

type TabId = 'general' | 'appearance' | 'privacy' | 'chat' | 'model' | 'voice'
type NavigationItem = {
  id: TabId
  label: string
  icon: Component
  route?: string
}

interface AppSettings {
  colorScheme: ColorSchemeId
  language: 'zh-CN' | 'en'
  primaryColor: string
  defaultPermission: boolean
  fullAccess: boolean
  workspaceFolder: string
  compactSidebar: boolean
  showStatusBar: boolean
  storageLocation: 'local' | 'cloud'
  autoDelete: 'never' | '7' | '30'
  autoSend: boolean
  messageSound: boolean
  historyRetention: '1' | '7' | '30' | 'forever'
  voice: 'default' | 'female' | 'male' | 'gentle' | 'lively'
  speed: number
  pitch: number
}

const { locale } = useI18n()
const { applyColorScheme } = useTheme()
const router = useRouter()
const route = useRoute()
const userStore = useUserStore()

const tabs = [
  { id: 'general' as TabId, label: '常规', description: '管理工作区权限、默认目录与基础偏好。', icon: Setting },
  { id: 'appearance' as TabId, label: '外观', description: '调整主题、密度与界面显示方式。', icon: Brush },
  { id: 'privacy' as TabId, label: '隐私', description: '控制数据存储、历史记录与敏感设置。', icon: Lock },
  { id: 'chat' as TabId, label: '对话', description: '管理消息发送与历史对话体验。', icon: ChatDotRound },
  { id: 'model' as TabId, label: '模型与 API', description: '配置当前浏览器使用的模型连接。', icon: Cpu },
  { id: 'voice' as TabId, label: '语音', description: '管理语音讲解的声音与播放参数。', icon: Microphone }
]

const settingsSections: Array<{ label: string; items: NavigationItem[] }> = [
  {
    label: '偏好',
    items: [
      { id: 'general', label: '常规', icon: Setting },
      { id: 'appearance', label: '外观', icon: Brush },
      { id: 'voice', label: '语音', icon: Microphone },
      { id: 'privacy', label: '隐私', icon: Key }
    ]
  },
  {
    label: '工作区',
    items: [
      { id: 'chat', label: '对话', icon: ChatDotRound },
      { id: 'model', label: '模型与 API', icon: Cpu }
    ]
  }
]

const THEME_TONES: Record<string, string> = {
  'codex-dark': 'dark',
  'one-dark-modern': 'dark',
  'claude-warm': 'light',
  'blue-purple': 'light',
  'tea-green': 'soft'
}

const themeOptions = colorSchemes.map((theme) => ({
  id: theme.id,
  label: theme.name,
  nameEn: theme.nameEn,
  tone: THEME_TONES[theme.id] || 'light',
  accent: theme.previewColor,
  bgApp: theme.variables['--bg-app'],
  bgPanel: theme.variables['--bg-sidebar'],
  bgCard: theme.variables['--bg-card'],
  fg: theme.variables['--text-primary'],
  border: theme.variables['--border-light']
}))

const activeThemeOption = computed(() => themeOptions.find((theme) => theme.id === settings.value.colorScheme) || themeOptions[0])

const themeDetailRows = computed(() => [
  { label: '强调色', desc: '按钮、选中态与高亮使用的主题色。', value: activeThemeOption.value.accent },
  { label: '背景', desc: '工作区与侧边栏的底色。', value: activeThemeOption.value.bgApp },
  { label: '前景', desc: '正文文字颜色。', value: activeThemeOption.value.fg }
])

const defaultSettings = (): AppSettings => ({
  colorScheme: 'codex-dark',
  language: 'zh-CN',
  primaryColor: '#4f46e5',
  defaultPermission: true,
  fullAccess: false,
  workspaceFolder: '',
  compactSidebar: false,
  showStatusBar: true,
  storageLocation: 'local',
  autoDelete: 'never',
  autoSend: false,
  messageSound: true,
  historyRetention: '7',
  voice: 'default',
  speed: 1.0,
  pitch: 1.0
})

const settings = ref<AppSettings>(defaultSettings())
const modelSettings = ref(getDefaultModelSettings())
const tabIds: TabId[] = ['general', 'appearance', 'privacy', 'chat', 'model', 'voice']
const isTabId = (value: unknown): value is TabId => typeof value === 'string' && tabIds.includes(value as TabId)
const activeTab = ref<TabId>(isTabId(route.query.tab) ? route.query.tab : 'general')
const searchTerm = ref('')
const lastSaved = ref<Date | null>(null)
const inlineHint = ref('修改后点击“保存设置”即可生效。')

const currentTab = computed(() => tabs.find((tab) => tab.id === activeTab.value) || tabs[0])
const visibleSections = computed(() => {
  const query = searchTerm.value.trim().toLowerCase()
  if (!query) return settingsSections
  return settingsSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => item.label.toLowerCase().includes(query))
    }))
    .filter((section) => section.items.length)
})
const lastSavedText = computed(() => {
  if (!lastSaved.value) return '尚未保存'
  return lastSaved.value.toLocaleTimeString('zh-CN', { hour12: false })
})

function applyTheme(): void {
  applyColorScheme(settings.value.colorScheme)
}

// 界面缩放：档位是唯一事实源（Ctrl+滚轮/快捷键与滑杆共用，持久化在独立键）。
const uiZoomLevelModel = computed({
  get: () => uiZoomState.level,
  set: (level: number) => setUiZoomLevel(level)
})

// 旧版「字体大小」(12–20px) 从未真正生效（只写了无人消费的 CSS 变量），
// 迁移为整体缩放档位：14px = 100%。直接写存储键——本组件挂载早于 App.vue
// 的缩放初始化，此时 setUiZoomLevel 还是空操作，由启动读取存储值生效。
const LEGACY_BASE_FONT_SIZE = 14

function migrateLegacyFontSize(legacy: unknown): void {
  const px = Number(legacy)
  if (!Number.isFinite(px) || px === LEGACY_BASE_FONT_SIZE) return
  if (localStorage.getItem(UI_ZOOM_STORAGE_KEY) !== null) return
  const level = Math.log(px / LEGACY_BASE_FONT_SIZE) / Math.log(UI_ZOOM_BASE)
  localStorage.setItem(UI_ZOOM_STORAGE_KEY, String(level))
  setUiZoomLevel(level)
}

function handleLanguageChange(newLang: 'zh-CN' | 'en'): void {
  locale.value = newLang
  inlineHint.value = `语言已切换为 ${newLang === 'zh-CN' ? '简体中文' : 'English'}，记得保存设置。`
}

function goBack(): void {
  if (window.history.length > 1) {
    router.back()
    return
  }
  void router.push('/chat')
}

function selectSettingsItem(item: NavigationItem): void {
  if (item.route) {
    router.push(item.route)
    return
  }
  activeTab.value = item.id as TabId
  if (route.query.tab) {
    void router.replace({ path: '/settings', query: {} })
  }
}

watch(() => route.query.tab, value => {
  if (isTabId(value) && value !== activeTab.value) {
    activeTab.value = value
  }
})

function loadSettings(): void {
  const saved = localStorage.getItem('appSettings')
  if (!saved) return
  try {
    const parsed = JSON.parse(saved) as Partial<AppSettings> & { theme?: unknown; fontSize?: unknown }
    const { theme: _legacyTheme, fontSize: _legacyFontSize, ...savedSettings } = parsed
    migrateLegacyFontSize(parsed.fontSize)
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
  localStorage.removeItem(UI_ZOOM_STORAGE_KEY)
  setUiZoomLevel(0)
  saveModelSettings(modelSettings.value)
  applyTheme()
  lastSaved.value = new Date()
  inlineHint.value = '已恢复默认设置。'
}

onMounted(() => {
  loadSettings()
  modelSettings.value = loadModelSettings()
  void userStore.loadCurrentUser()
  if (activeTab.value === 'model') void loadServerProfiles()
})

function selectProvider(provider: ModelProviderId): void {
  modelSettings.value = applyProviderPreset(modelSettings.value, provider)
  inlineHint.value = provider === 'system' ? '已选择服务端默认模型。' : '请检查 API Key 后保存设置。'
  if (provider === 'system' && !serverProfiles.value.length) void loadServerProfiles()
}

// ---- 服务端供应商档案（热切换，无需重启） ----

interface ServerProfile {
  name: string
  provider: string
  base_url: string
  model: string
  key_source: string
  usable: boolean
  active: boolean
}

const serverProfiles = ref<ServerProfile[]>([])
const serverProfilesLoading = ref(false)
const serverActionBusy = ref(false)
const showAddServerProfile = ref(false)
const serverTestResults = ref<Record<string, { ok: boolean; text: string }>>({})
const serverProviderTypes = [
  { value: 'glm', label: '智谱 GLM' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'qwen', label: '通义千问' },
  { value: 'openai-compatible', label: 'OpenAI 兼容' }
]
const serverProfileDraft = ref({ name: '', provider: 'openai-compatible', base_url: '', model: '', api_key: '', api_key_env: '' })

function profileHost(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url
  }
}

async function serverFetch(path: string, init?: RequestInit): Promise<Response> {

  return localFetch(apiUrl(path), {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init?.headers
    }
  })
}

async function loadServerProfiles(): Promise<void> {
  serverProfilesLoading.value = true
  try {
    const response = await serverFetch('/ai/llm/profiles')
    if (!response.ok) return
    const data = await response.json() as { profiles?: ServerProfile[] }
    serverProfiles.value = Array.isArray(data.profiles) ? data.profiles : []
  } catch {
    // 服务端不可达时保持空列表，提示交给 el-loading 消失后的空态
  } finally {
    serverProfilesLoading.value = false
  }
}

async function switchServerProfile(profile: ServerProfile): Promise<void> {
  if (profile.active || !profile.usable || serverActionBusy.value) return
  serverActionBusy.value = true
  try {
    const response = await serverFetch('/ai/llm/profiles/active', {
      method: 'POST',
      body: JSON.stringify({ name: profile.name })
    })
    const data = await response.json().catch(() => ({})) as { profiles?: ServerProfile[]; detail?: string }
    if (!response.ok) {
      inlineHint.value = data.detail || '切换失败，请稍后再试。'
      return
    }
    serverProfiles.value = Array.isArray(data.profiles) ? data.profiles : []
    serverTestResults.value = {}
    inlineHint.value = `已切换到 ${profile.name}，新对话与新任务立即生效。`
  } catch {
    inlineHint.value = '切换失败，服务端不可达。'
  } finally {
    serverActionBusy.value = false
  }
}

async function testServerProfile(profile: ServerProfile): Promise<void> {
  if (serverActionBusy.value) return
  serverActionBusy.value = true
  serverTestResults.value = { ...serverTestResults.value, [profile.name]: { ok: true, text: '测试中…' } }
  try {
    const response = await serverFetch('/ai/llm/profiles/test', {
      method: 'POST',
      body: JSON.stringify({ name: profile.name })
    })
    const data = await response.json().catch(() => ({})) as { ok?: boolean; error?: string; latency_ms?: number | null; detail?: string }
    if (!response.ok) {
      serverTestResults.value = { ...serverTestResults.value, [profile.name]: { ok: false, text: data.detail || '测试失败' } }
      return
    }
    serverTestResults.value = {
      ...serverTestResults.value,
      [profile.name]: data.ok
        ? { ok: true, text: `连通 ${data.latency_ms ?? '?'}ms` }
        : { ok: false, text: data.error || '连通失败' }
    }
  } catch {
    serverTestResults.value = { ...serverTestResults.value, [profile.name]: { ok: false, text: '服务端不可达' } }
  } finally {
    serverActionBusy.value = false
  }
}

async function addServerProfile(): Promise<void> {
  const draft = serverProfileDraft.value
  if (!draft.name.trim() || !draft.base_url.trim() || !draft.model.trim()) {
    inlineHint.value = '请完整填写名称、API 地址和模型。'
    return
  }
  if (!draft.api_key.trim() && !draft.api_key_env.trim()) {
    inlineHint.value = '请填写 API Key，或指定服务端已有的密钥环境变量名。'
    return
  }
  serverActionBusy.value = true
  try {
    const response = await serverFetch('/ai/llm/profiles', {
      method: 'POST',
      body: JSON.stringify({ ...draft, name: draft.name.trim() })
    })
    const data = await response.json().catch(() => ({})) as { profiles?: ServerProfile[]; detail?: string }
    if (!response.ok) {
      inlineHint.value = data.detail || '保存失败，请检查填写内容。'
      return
    }
    serverProfiles.value = Array.isArray(data.profiles) ? data.profiles : []
    serverProfileDraft.value = { name: '', provider: 'openai-compatible', base_url: '', model: '', api_key: '', api_key_env: '' }
    showAddServerProfile.value = false
    inlineHint.value = '供应商已保存，点击对应卡片即可切换。'
  } catch {
    inlineHint.value = '保存失败，服务端不可达。'
  } finally {
    serverActionBusy.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'model' && !serverProfiles.value.length) void loadServerProfiles()
})

function ensureSelectedModel(models: string[]): void {
  if (!models.includes(modelSettings.value.selectedModel)) {
    modelSettings.value.selectedModel = models[0] || ''
  }
}
</script>


<style scoped>
/* 个人设置视觉层：窄侧栏承载定位，主区域保持安静的纵向阅读节奏。 */
.settings-view {
  width: 100%;
  height: 100%;
  min-height: 0;
  padding: 0;
  display: grid;
  grid-template-columns: minmax(210px, 250px) minmax(0, 1fr);
  overflow: hidden;
  background: var(--bg-app);
  color: var(--text-primary);
}

.settings-rail {
  min-width: 0;
  min-height: 0;
  padding: 22px 12px 14px;
  display: flex;
  flex-direction: column;
  background: color-mix(in srgb, var(--bg-sidebar) 78%, var(--bg-app));
}

.back-to-app,
.settings-nav-item {
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  cursor: pointer;
  transition: var(--transition);
}

.back-to-app {
  min-height: 34px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  align-self: flex-start;
  border-radius: var(--radius-control);
  font-size: 12px;
}

.back-to-app:hover,
.back-to-app:focus-visible {
  color: var(--text-primary);
  background: var(--bg-input);
}

.back-to-app .el-icon {
  font-size: 15px;
}

.settings-search {
  height: 36px;
  margin: 18px 0 14px;
  padding: 0 11px;
  display: flex;
  align-items: center;
  gap: 8px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg-input) 88%, transparent);
  color: var(--text-muted);
}

.settings-search:focus-within {
  box-shadow: 0 0 0 1px var(--primary-color) inset;
  color: var(--primary-color);
}

.settings-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  font-size: 12px;
}

.settings-search input::placeholder {
  color: var(--text-muted);
}

.settings-nav {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 0 1px 12px;
}

.settings-nav-section {
  margin-bottom: 20px;
}

.settings-nav-section h2 {
  padding: 0 10px;
  margin: 0 0 7px;
  color: var(--text-muted);
  font: 600 11px/1.4 var(--font-sans);
  letter-spacing: .04em;
}

.settings-nav-item {
  width: 100%;
  min-height: 35px;
  padding: 0 10px;
  display: flex;
  align-items: center;
  gap: 9px;
  border-radius: 9px;
  text-align: left;
  font-size: 12px;
}

.settings-nav-item .el-icon {
  flex: 0 0 16px;
  color: var(--text-muted);
  font-size: 15px;
}

.settings-nav-item:hover,
.settings-nav-item:focus-visible {
  color: var(--text-primary);
  background: var(--bg-input);
}

.settings-nav-item:hover .el-icon,
.settings-nav-item:focus-visible .el-icon {
  color: var(--primary-color);
}

/* 选中态 = VS Code 列表选中式：柔和中性圆角底 + 文字提亮，无强调色、无竖条 */
.settings-nav-item.active {
  color: var(--text-primary);
  font-weight: 500;
  background: color-mix(in srgb, var(--text-primary) 9%, transparent);
  box-shadow: none;
}

.settings-nav-item.active .el-icon {
  color: var(--text-primary);
}

.settings-nav-item .item-arrow {
  margin-left: auto;
  color: var(--text-muted);
  font-size: 12px;
  transform: rotate(180deg);
}

.settings-empty {
  padding: 12px 10px;
  color: var(--text-muted);
  font-size: 12px;
}

.settings-content {
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 42px clamp(24px, 5vw, 76px) 56px;
}

.settings-header,
.settings-section,
.settings-footer {
  width: min(100%, 1400px);
  margin: 0 auto;
}

.settings-header {
  min-height: 84px;
  padding-bottom: 24px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid var(--border-light);
}

.settings-eyebrow {
  display: block;
  margin-bottom: 8px;
  color: var(--primary-color);
  font: 10px/1 var(--font-mono);
  letter-spacing: .12em;
}

.settings-header h1 {
  margin: 0;
  color: var(--text-primary);
  font-size: clamp(23px, 2.2vw, 30px);
  line-height: 1.15;
}

.settings-header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
}

.settings-header-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  flex-shrink: 0;
}

.save-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
}

.save-state i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-muted);
}

.save-state.saved i { background: var(--success); }

.header-save {
  height: 34px;
  padding: 0 13px;
  border-radius: 8px;
  font-size: 12px;
}

.settings-section {
  padding-top: 30px;
}

.section-label {
  margin: 0 0 10px;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 650;
}

.settings-section > .section-label:not(:first-child) {
  margin-top: 30px;
}

.setting-card {
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 13px;
  background: color-mix(in srgb, var(--surface-solid) 92%, transparent);
}

.setting-row {
  min-height: 78px;
  padding: 15px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-light) 82%, transparent);
}

.setting-row:last-child { border-bottom: 0; }

.setting-row > div:first-child {
  min-width: 0;
}

.setting-row strong {
  display: block;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 650;
}

.setting-row p {
  max-width: 620px;
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.45;
  text-wrap: pretty;
}

.setting-row-control { min-height: 72px; }

.inline-input,
.inline-select {
  width: min(100%, 280px);
  flex: 0 0 280px;
}

.compact-slider {
  width: min(100%, 250px);
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 0 0 250px;
}

.compact-slider .el-slider { flex: 1; }

.compact-slider > span {
  width: 40px;
  color: var(--text-secondary);
  font: 11px var(--font-mono);
  text-align: right;
}

.theme-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
  gap: 12px;
}

.theme-option {
  padding: 0;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  text-align: left;
  transition: var(--transition);
}

.theme-option:hover,
.theme-option:focus-visible {
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

.theme-option.active {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 1px var(--primary-color);
}

.theme-preview {
  position: relative;
  height: 116px;
  padding: 14px 14px 12px 50px;
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: 8px 8px 1fr;
  gap: 8px;
  overflow: hidden;
  background: var(--pv-bg, #242536);
}

.theme-preview::before {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 38px;
  background: var(--pv-side, color-mix(in srgb, #ffffff 7%, transparent));
  border-right: 1px solid var(--pv-border, transparent);
}

.theme-preview i,
.theme-preview b {
  position: relative;
  z-index: 1;
  display: block;
  border-radius: 999px;
  background: color-mix(in srgb, var(--pv-fg, #ffffff) 30%, transparent);
}

.theme-preview i:nth-child(1) { display: none; }
.theme-preview i:nth-child(2) { width: 84px; }
.theme-preview i:nth-child(3) { width: 58px; opacity: .6; }
.theme-preview b:nth-of-type(1) {
  height: 42px;
  border-radius: 7px;
  background: var(--pv-card, color-mix(in srgb, #ffffff 86%, transparent));
  border: 1px solid var(--pv-border, transparent);
}
.theme-preview b:nth-of-type(2) { position: absolute; z-index: 2; right: 15px; bottom: 15px; width: 28px; height: 5px; background: var(--pv-accent); }

.theme-option-footer {
  min-height: 42px;
  padding: 0 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--surface-solid);
  font-size: 12px;
}

.theme-option-footer strong { color: var(--text-primary); font-weight: 600; }
.theme-option-footer .el-icon { color: var(--primary-color); }

.theme-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.theme-select {
  width: 240px;
}

.theme-select-option {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 0;
}

.theme-aa {
  flex: none;
  width: 24px;
  height: 24px;
  display: grid;
  place-items: center;
  border-radius: 6px;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.18);
}

.theme-select-name {
  color: var(--text-primary);
  font-weight: 600;
  white-space: nowrap;
}

.theme-select-en {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-muted);
  font-size: 11px;
  white-space: nowrap;
}

.theme-select-check { margin-left: auto; color: var(--primary-color); }

.color-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px 5px 6px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-input);
}

.color-chip i {
  width: 16px;
  height: 16px;
  border-radius: 5px;
  box-shadow: inset 0 0 0 1px rgba(127, 127, 127, 0.35);
}

.color-chip code {
  color: var(--text-regular);
  font-size: 11px;
  text-transform: uppercase;
}

.section-heading {
  margin-bottom: 14px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.section-heading h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
}

.section-heading p {
  margin: 5px 0 0;
  color: var(--text-secondary);
  font-size: 11px;
}

.local-only-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 8px;
  border: 1px solid var(--border-light);
  border-radius: 7px;
  color: var(--text-secondary);
  font-size: 10px;
  white-space: nowrap;
}

.provider-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 14px;
}

.provider-option {
  position: relative;
  min-height: 92px;
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: var(--surface-solid);
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
  transition: var(--transition);
}

.provider-option:hover,
.provider-option:focus-visible {
  border-color: var(--border-hover);
  transform: translateY(-1px);
}

.provider-option.active {
  border-color: var(--primary-color);
  background: var(--primary-fade);
  box-shadow: 0 0 0 1px var(--primary-line);
}

.provider-mark {
  width: 25px;
  height: 25px;
  margin-bottom: 8px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  background: var(--primary-color);
  color: var(--on-primary);
  font-size: 11px;
  font-weight: 700;
}

.provider-copy { display: grid; gap: 3px; }
.provider-copy strong { font-size: 12px; }
.provider-copy small { color: var(--text-secondary); font-size: 10px; line-height: 1.35; }
.provider-check { position: absolute; top: 10px; right: 10px; color: var(--primary-color); }

.connection-form {
  padding: 18px 16px 2px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 2px 18px;
}

.connection-form :deep(.el-form-item) { margin-bottom: 14px; }
.connection-form :deep(.el-form-item__label) { color: var(--text-primary); font-size: 11px; font-weight: 600; }
.connection-form :deep(.el-select) { width: 100%; }
.wide-control { width: 100%; }

.system-provider-note {
  padding: 13px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: var(--primary-fade);
  color: var(--text-secondary);
  font-size: 11px;
}

.server-provider-panel {
  display: grid;
  gap: 12px;
}

.server-profile-list {
  display: grid;
  gap: 8px;
  min-height: 64px;
}

.server-profile-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: var(--surface-solid);
  cursor: pointer;
  transition: var(--transition);
}

.server-profile-item:hover,
.server-profile-item:focus-visible {
  border-color: var(--border-hover);
}

.server-profile-item.active {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}

.server-profile-item.unusable {
  opacity: 0.55;
  cursor: not-allowed;
}

.server-profile-state {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 10px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.server-test-result { font-size: 10px; }
.server-test-result.ok { color: var(--success-color, #3aa66a); }

.server-profile-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.settings-footer {
  padding-top: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.hint {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 7px;
  color: var(--text-muted);
  font-size: 11px;
}

.hint span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hint .el-icon { color: var(--text-secondary); }
.actions { display: flex; gap: 8px; flex-shrink: 0; }
.actions :deep(.el-button) { height: 34px; padding: 0 13px; border-radius: 8px; font-size: 12px; }

.setting-row :deep(.el-input__wrapper),
.connection-form :deep(.el-input__wrapper),
.setting-row :deep(.el-select .el-input__wrapper) {
  min-height: 34px;
  border: 1px solid var(--border-light) !important;
  border-radius: 8px !important;
  background: var(--bg-input) !important;
}

.setting-row :deep(.el-input__inner),
.connection-form :deep(.el-input__inner) {
  color: var(--text-primary);
  font-size: 11px;
}

.setting-row :deep(.el-input__inner::placeholder),
.connection-form :deep(.el-input__inner::placeholder) { color: var(--text-disabled); }

.setting-row :deep(.el-radio-button__inner) {
  padding: 8px 11px;
  border-color: var(--border-light);
  background: var(--bg-input);
  color: var(--text-secondary);
  font-size: 11px;
  box-shadow: none;
}

.setting-row :deep(.el-radio-button:first-child .el-radio-button__inner) { border-radius: 7px 0 0 7px; }
.setting-row :deep(.el-radio-button:last-child .el-radio-button__inner) { border-radius: 0 7px 7px 0; }
.setting-row :deep(.el-radio-button__original-radio:checked + .el-radio-button__inner) { color: var(--on-primary); background: var(--primary-color); border-color: var(--primary-color); box-shadow: none; }
.setting-row :deep(.el-switch.is-checked .el-switch__core) { border-color: var(--primary-color); background: var(--primary-color); }

@media (max-width: 980px) {
  .settings-view { grid-template-columns: 190px minmax(0, 1fr); }
  .settings-content { padding-right: 28px; padding-left: 28px; }
  .provider-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}

@media (max-width: 700px) {
  .settings-view { display: block; overflow: auto; }
  .settings-rail { min-height: auto; padding: 12px; border-right: 0; border-bottom: 1px solid var(--border-light); }
  .settings-nav { display: flex; gap: 12px; overflow-x: auto; padding-bottom: 2px; }
  .settings-nav-section { min-width: max-content; margin: 0; }
  .settings-nav-section h2 { display: none; }
  .settings-nav-item { width: auto; min-height: 32px; padding: 0 9px; white-space: nowrap; }
  .settings-nav-item .item-arrow { display: none; }
  .settings-search { margin: 12px 0 10px; }
  .settings-content { height: auto; overflow: visible; padding: 26px 16px 36px; }
  .settings-header { align-items: flex-start; flex-direction: column; gap: 18px; }
  .settings-header-actions { width: 100%; justify-content: space-between; }
  .theme-grid { grid-template-columns: 1fr; }
  .theme-preview { height: 94px; }
  .setting-row,
  .setting-row-control { align-items: flex-start; flex-direction: column; gap: 12px; }
  .inline-input, .inline-select, .compact-slider { width: 100%; flex-basis: auto; }
  .compact-slider { max-width: none; }
  .provider-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .connection-form { grid-template-columns: 1fr; }
  .settings-footer { align-items: stretch; flex-direction: column; }
  .actions { justify-content: flex-end; }
}

@media (prefers-reduced-motion: reduce) {
  .settings-view *, .settings-view *::before, .settings-view *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
</style>
