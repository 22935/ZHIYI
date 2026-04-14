<template>
  <div class="settings-view">
    <div class="ambient-glow top-left"></div>
    <div class="ambient-glow bottom-right"></div>

    <section class="page-header glass-panel">
      <div>
        <h1>设置中心</h1>
        <p>与其他页面一致：同页分区切换、同页保存反馈，不弹出新界面。</p>
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
        <el-form-item label="主题模式">
          <el-radio-group v-model="settings.theme">
            <el-radio-button label="light">明亮</el-radio-button>
            <el-radio-button label="dark">深色</el-radio-button>
            <el-radio-button label="auto">跟随系统</el-radio-button>
          </el-radio-group>
        </el-form-item>

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

        <el-form-item label="主色">
          <el-color-picker v-model="settings.primaryColor" @change="applyTheme" />
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
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Setting, Lock, ChatDotRound, Microphone, InfoFilled } from '@element-plus/icons-vue'

type TabId = 'general' | 'privacy' | 'chat' | 'voice'

interface AppSettings {
  theme: 'light' | 'dark' | 'auto'
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

const tabs = [
  { id: 'general' as TabId, label: '通用', icon: Setting },
  { id: 'privacy' as TabId, label: '隐私', icon: Lock },
  { id: 'chat' as TabId, label: '对话', icon: ChatDotRound },
  { id: 'voice' as TabId, label: '语音', icon: Microphone }
]

const defaultSettings = (): AppSettings => ({
  theme: 'light',
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
const activeTab = ref<TabId>('general')
const lastSaved = ref<Date | null>(null)
const inlineHint = ref('修改后点击“保存设置”即可生效，全程在当前页面完成。')

const lastSavedText = computed(() => {
  if (!lastSaved.value) return '尚未保存'
  return lastSaved.value.toLocaleTimeString('zh-CN', { hour12: false })
})

function applyTheme(): void {
  const root = document.documentElement
  root.style.setProperty('--primary-color', settings.value.primaryColor)
  root.style.setProperty('--font-size-base', `${settings.value.fontSize}px`)
}

function handleLanguageChange(newLang: 'zh-CN' | 'en'): void {
  locale.value = newLang
  inlineHint.value = `语言已切换为 ${newLang === 'zh-CN' ? '简体中文' : 'English'}，记得保存设置。`
}

function loadSettings(): void {
  const saved = localStorage.getItem('appSettings')
  if (!saved) return
  try {
    const parsed = JSON.parse(saved) as Partial<AppSettings>
    settings.value = { ...defaultSettings(), ...parsed }
    locale.value = settings.value.language
    applyTheme()
    inlineHint.value = '已读取本地设置。'
  } catch {
    settings.value = defaultSettings()
    inlineHint.value = '本地设置解析失败，已使用默认配置。'
  }
}

function saveSettings(): void {
  localStorage.setItem('appSettings', JSON.stringify(settings.value))
  applyTheme()
  lastSaved.value = new Date()
  inlineHint.value = '设置已保存。'
}

function resetSettings(): void {
  settings.value = defaultSettings()
  locale.value = 'zh-CN'
  localStorage.removeItem('appSettings')
  applyTheme()
  lastSaved.value = new Date()
  inlineHint.value = '已恢复默认设置。'
}

onMounted(() => {
  loadSettings()
})
</script>

<style scoped>
.settings-view {
  position: relative;
  min-height: 100%;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--text-primary);
  overflow: auto;
}

.ambient-glow {
  position: absolute;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  filter: blur(70px);
  opacity: 0.2;
  pointer-events: none;
}

.ambient-glow.top-left {
  top: -120px;
  left: -120px;
  background: #5b8ff9;
}

.ambient-glow.bottom-right {
  right: -120px;
  bottom: -140px;
  background: #36cfc9;
}

.glass-panel {
  position: relative;
  z-index: 1;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 14px;
  box-shadow: 0 10px 28px rgba(15, 35, 95, 0.06);
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
  background: rgba(91, 143, 249, 0.12);
  color: var(--text-secondary);
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
  background: rgba(91, 143, 249, 0.12);
  border-color: rgba(91, 143, 249, 0.28);
  color: var(--text-primary);
}

.content-panel {
  padding: 16px;
}

.form-grid {
  display: grid;
  gap: 16px;
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

@media (max-width: 760px) {
  .settings-view {
    padding: 12px;
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
}
</style>
