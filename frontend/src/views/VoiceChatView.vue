<!-- 语音对话页面 — 数字皮套人展示、角色选择、语音录制与交互 -->
<template>
  <div class="voice-view">
    <header class="voice-header">
      <div class="header-left">
        <el-button class="back-button" text @click="handleBack">
          <el-icon><ArrowLeft /></el-icon>
          返回对话
        </el-button>
        <div class="title-block">
          <h1>语音对话</h1>
          <p>保留数字皮套人，语音对话流程与主界面交互风格保持一致</p>
        </div>
      </div>
      <div class="header-right">
        <el-select
          v-model="selectedRoleId"
          class="role-select"
          placeholder="选择角色"
          size="small"
          :disabled="processing || isRecording"
          @change="handleRoleChange"
        >
          <el-option
            v-for="role in allRoles"
            :key="role.id"
            :label="role.name"
            :value="role.id"
          />
        </el-select>
      </div>
    </header>

    <div class="voice-main">
      <section class="left-column">
        <article class="panel-card avatar-card">
          <div class="card-header">
            <div class="header-title">
              <h2>数字皮套人</h2>
              <p>{{ currentRoleName }}</p>
            </div>
            <el-tag size="small" :type="statusTagType" effect="light">
              {{ statusText }}
            </el-tag>
          </div>

          <div class="avatar-stage" :class="{ speaking: isSpeaking, recording: isRecording }">
            <DigitalHuman
              class="digital-human"
              :role-id="roleStore.currentRole?.id"
              :is-speaking="isSpeaking"
              :audio-url="currentAudioUrl"
              :transparent="true"
            />
            <div class="stage-overlay">
              <span class="stage-chip" :class="{ active: isRecording }">录音</span>
              <span class="stage-chip" :class="{ active: isSpeaking }">播报</span>
              <span class="stage-chip" :class="{ active: processing }">处理中</span>
            </div>
          </div>
        </article>

        <article class="panel-card transcript-card">
          <div class="card-header">
            <div class="header-title">
              <h2>语音会话记录</h2>
              <p>每次录音会自动转文字并展示模型回复</p>
            </div>
            <el-button size="small" text @click="clearSession">清空会话</el-button>
          </div>

          <div ref="transcriptRef" class="transcript-list">
            <div v-if="!messages.length" class="empty-state">
              <el-icon><Microphone /></el-icon>
              <span>按住右侧麦克风开始语音对话</span>
            </div>

            <div
              v-for="msg in messages"
              :key="msg.id"
              class="message-item"
              :class="msg.role"
            >
              <template v-if="msg.role === 'system'">
                <div class="system-tip">{{ msg.text }}</div>
              </template>
              <template v-else>
                <div class="message-meta">
                  <span class="sender">{{ msg.role === 'assistant' ? currentRoleName : '你' }}</span>
                  <span class="time">{{ formatTime(msg.createdAt) }}</span>
                </div>
                <div class="message-bubble" v-html="renderMessageHtml(msg)" />
                <div v-if="msg.role === 'user' && msg.confidence !== undefined" class="confidence">
                  识别置信度 {{ (msg.confidence * 100).toFixed(1) }}%
                </div>
              </template>
            </div>
          </div>
        </article>
      </section>

      <aside class="right-column">
        <article class="panel-card control-card">
          <div class="card-header">
            <div class="header-title">
              <h2>语音输入</h2>
              <p>按住录音，松开发送</p>
            </div>
          </div>

          <div class="recorder-area">
            <VoiceRecorder
              :disabled="processing"
              :enable-realtime="false"
              @recorded="handleVoiceRecorded"
              @recording-start="handleRecordingStart"
              @recording-end="handleRecordingEnd"
              @realtime-text="handleRealtimeText"
            />
          </div>

          <el-alert
            :title="statusText"
            :type="statusTagType"
            :closable="false"
            show-icon
            class="status-alert"
          />

          <div v-if="recognizedText" class="recognized-preview">
            <span class="label">识别文本</span>
            <p>{{ recognizedText }}</p>
          </div>

          <div class="button-row">
            <el-button :disabled="!canReplay" @click="replayLastAudio">
              <el-icon><RefreshRight /></el-icon>
              重播回复
            </el-button>
            <el-button :disabled="!isSpeaking" @click="stopPlayback">
              <el-icon><VideoPause /></el-icon>
              停止播放
            </el-button>
          </div>
        </article>

        <article class="panel-card settings-card">
          <div class="card-header">
            <div class="header-title">
              <h2>语音设置</h2>
              <p>调整播报速度、音调和音色</p>
            </div>
          </div>

          <div class="settings-body">
            <div class="setting-item">
              <div class="setting-line">
                <span>语速</span>
                <strong>{{ voiceSpeed.toFixed(1) }}x</strong>
              </div>
              <el-slider v-model="voiceSpeed" :min="0.5" :max="2" :step="0.1" />
            </div>

            <div class="setting-item">
              <div class="setting-line">
                <span>音调</span>
                <strong>{{ voicePitch.toFixed(1) }}x</strong>
              </div>
              <el-slider v-model="voicePitch" :min="0.5" :max="2" :step="0.1" />
            </div>

            <div class="setting-item">
              <div class="setting-line">
                <span>音色</span>
              </div>
              <el-select v-model="voiceType" class="voice-type-select">
                <el-option label="默认" value="default" />
                <el-option label="女声" value="female" />
                <el-option label="男声" value="male" />
                <el-option label="温柔" value="gentle" />
                <el-option label="活力" value="lively" />
              </el-select>
            </div>

            <el-button :disabled="processing" type="primary" plain @click="handleTestVoice">
              <el-icon><VideoPlay /></el-icon>
              试听当前设置
            </el-button>
          </div>
        </article>

        <article class="panel-card tips-card">
          <div class="card-header">
            <div class="header-title">
              <h2>使用建议</h2>
            </div>
          </div>
          <ul>
            <li>尽量在安静环境中录音，提升识别准确率。</li>
            <li>长问题建议分段提问，回复会更稳定。</li>
            <li>如果播放失败，可点击“重播回复”。</li>
          </ul>
        </article>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  Microphone,
  RefreshRight,
  VideoPause,
  VideoPlay
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoleStore } from '@/stores/role'
import DigitalHuman from '@/components/DigitalHuman.vue'
import VoiceRecorder from '@/components/VoiceRecorder.vue'
import { voiceApi } from '@/services/api/voice'

type VoiceMessageRole = 'user' | 'assistant' | 'system'

interface VoiceMessage {
  id: string
  role: VoiceMessageRole
  text: string
  createdAt: number
  confidence?: number
}

const router = useRouter()
const roleStore = useRoleStore()

const selectedRoleId = ref<string>('')
const isRecording = ref(false)
const isSpeaking = ref(false)
const processing = ref(false)
const recognizedText = ref('')
const voiceSpeed = ref(1.0)
const voicePitch = ref(1.0)
const voiceType = ref('default')
const contextId = ref('')
const currentAudioUrl = ref('')
const messages = ref<VoiceMessage[]>([])
const transcriptRef = ref<HTMLElement | null>(null)
const lastResponseAudioBlob = ref<Blob | null>(null)

let playbackAudio: HTMLAudioElement | null = null
let recognizedTextTimer: number | null = null

const allRoles = computed(() => roleStore.roles)
const currentRoleName = computed(() => roleStore.currentRole?.name || '智能助手')
const canReplay = computed(() => Boolean(lastResponseAudioBlob.value) && !processing.value)

const statusText = computed(() => {
  if (isRecording.value) return '正在录音，松开发送'
  if (processing.value) return '语音处理中，请稍候'
  if (isSpeaking.value) return '数字人正在播报回复'
  return '准备就绪，可以开始语音对话'
})

const statusTagType = computed<'success' | 'warning' | 'danger' | 'info'>(() => {
  if (isRecording.value) return 'danger'
  if (processing.value) return 'warning'
  if (isSpeaking.value) return 'success'
  return 'info'
})

const handleBack = () => {
  router.push('/chat')
}

const pushMessage = (role: VoiceMessageRole, text: string, confidence?: number) => {
  const payload: VoiceMessage = {
    id: `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`,
    role,
    text,
    createdAt: Date.now(),
    confidence
  }
  messages.value.push(payload)
}

const handleRoleChange = async (roleId: string) => {
  const target = allRoles.value.find(role => role.id === roleId)
  if (!target) return

  await roleStore.setCurrentRole(target)
  contextId.value = ''
  pushMessage('system', `已切换到角色「${target.name}」，会话上下文已重置。`)
}

const handleRecordingStart = () => {
  isRecording.value = true
  recognizedText.value = ''
  clearRecognizedTimer()
}

const handleRecordingEnd = () => {
  isRecording.value = false
}

const handleRealtimeText = (text: string) => {
  if (!text) return
  recognizedText.value = text
}

const handleVoiceRecorded = async (audioBlob: Blob) => {
  isRecording.value = false
  processing.value = true
  clearRecognizedTimer()

  try {
    const audioFile = new File([audioBlob], `voice-${Date.now()}.webm`, {
      type: audioBlob.type || 'audio/webm'
    })

    const response = await voiceApi.sendVoiceMessage({
      audio: audioFile,
      roleId: roleStore.currentRole?.id || '',
      contextId: contextId.value || undefined
    })

    if (response.contextId) {
      contextId.value = response.contextId
    }

    const userText = (response.recognizedText || recognizedText.value || '已发送语音消息').trim()
    const assistantText = (response.text || '').trim()

    pushMessage('user', userText, response.confidence)
    recognizedText.value = userText

    if (assistantText) {
      pushMessage('assistant', assistantText)
      await synthesizeAndPlay(assistantText)
    } else {
      pushMessage('system', '模型未返回文本回复，请稍后重试。')
    }
  } catch (error: any) {
    const message =
      error?.response?.data?.message ||
      error?.message ||
      '语音处理失败，请检查后端服务状态。'
    pushMessage('system', `请求失败：${message}`)
    ElMessage.error(message)
  } finally {
    processing.value = false
    recognizedTextTimer = window.setTimeout(() => {
      recognizedText.value = ''
    }, 6000)
  }
}

const synthesizeAndPlay = async (text: string) => {
  try {
    const audioBlob = await voiceApi.textToSpeech(
      text,
      voiceType.value,
      voiceSpeed.value,
      voicePitch.value
    )
    lastResponseAudioBlob.value = audioBlob
    await playAudioBlob(audioBlob)
  } catch (error: any) {
    const message = error?.message || '语音合成失败'
    ElMessage.warning(`文本已返回，但语音播放失败：${message}`)
  }
}

const playAudioBlob = async (audioBlob: Blob) => {
  stopPlayback()
  releaseCurrentAudioUrl()

  const audioUrl = URL.createObjectURL(audioBlob)
  currentAudioUrl.value = audioUrl
  playbackAudio = new Audio(audioUrl)
  playbackAudio.preload = 'auto'

  playbackAudio.onplay = () => {
    isSpeaking.value = true
  }

  playbackAudio.onpause = () => {
    isSpeaking.value = false
  }

  playbackAudio.onended = () => {
    isSpeaking.value = false
    releaseCurrentAudioUrl()
    if (playbackAudio) {
      playbackAudio.src = ''
      playbackAudio = null
    }
  }

  playbackAudio.onerror = () => {
    isSpeaking.value = false
    ElMessage.error('音频播放失败，请点击“重播回复”重试。')
  }

  try {
    await playbackAudio.play()
  } catch (error: any) {
    isSpeaking.value = false
    releaseCurrentAudioUrl()
    if (playbackAudio) {
      playbackAudio.src = ''
      playbackAudio = null
    }
    throw error
  }
}

const replayLastAudio = async () => {
  if (!lastResponseAudioBlob.value) {
    ElMessage.info('当前没有可重播音频。')
    return
  }

  try {
    await playAudioBlob(lastResponseAudioBlob.value)
  } catch (error: any) {
    ElMessage.warning(error?.message || '重播失败，请稍后重试。')
  }
}

const stopPlayback = () => {
  if (!playbackAudio) return
  playbackAudio.pause()
  playbackAudio.currentTime = 0
  playbackAudio.src = ''
  playbackAudio = null
  isSpeaking.value = false
  releaseCurrentAudioUrl()
}

const handleTestVoice = async () => {
  if (processing.value) return
  processing.value = true

  try {
    const sampleText = '你好，这是语音设置试听。'
    const sampleAudio = await voiceApi.textToSpeech(
      sampleText,
      voiceType.value,
      voiceSpeed.value,
      voicePitch.value
    )
    await playAudioBlob(sampleAudio)
    ElMessage.success('正在试听当前语音设置。')
  } catch (error: any) {
    ElMessage.error(error?.message || '试听失败，请检查语音服务。')
  } finally {
    processing.value = false
  }
}

const clearSession = () => {
  messages.value = []
  contextId.value = ''
  recognizedText.value = ''
  stopPlayback()
  pushMessage('system', '语音会话已清空。')
}

const releaseCurrentAudioUrl = () => {
  if (!currentAudioUrl.value) return
  URL.revokeObjectURL(currentAudioUrl.value)
  currentAudioUrl.value = ''
}

const clearRecognizedTimer = () => {
  if (recognizedTextTimer === null) return
  window.clearTimeout(recognizedTextTimer)
  recognizedTextTimer = null
}

const formatTime = (timestamp: number) => {
  return new Date(timestamp).toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}

const escapeHtml = (raw: string) =>
  raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const escapeAttr = (raw: string) => raw.replace(/"/g, '&quot;')

const isSafeUrl = (url: string) => /^(https?:\/\/|mailto:|\/)/i.test(url)

const applyInlineMarkdown = (value: string) => {
  let text = value
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_all, label, url) => {
    const safe = String(url || '').trim()
    if (!isSafeUrl(safe)) return label
    return `<a href="${escapeAttr(safe)}" target="_blank" rel="noopener noreferrer">${label}</a>`
  })
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  return text
}

const markdownToHtml = (raw: string) => {
  if (!raw) return ''

  const codeBlocks: string[] = []
  const stripped = raw.replace(/```([a-zA-Z0-9_-]+)?\n?([\s\S]*?)```/g, (_m, lang, code) => {
    const language = (lang || '').trim()
    const escapedCode = escapeHtml(String(code || '').replace(/\n$/, ''))
    const className = language ? ` class="language-${escapeAttr(language)}"` : ''
    const token = `@@CODE_BLOCK_${codeBlocks.length}@@`
    codeBlocks.push(`<pre><code${className}>${escapedCode}</code></pre>`)
    return token
  })

  const lines = stripped.split(/\r?\n/)
  const output: string[] = []
  let inUl = false
  let inOl = false

  const closeLists = () => {
    if (inUl) {
      output.push('</ul>')
      inUl = false
    }
    if (inOl) {
      output.push('</ol>')
      inOl = false
    }
  }

  lines.forEach(line => {
    const trimmed = line.trim()
    if (!trimmed) {
      closeLists()
      return
    }

    if (/^@@CODE_BLOCK_\d+@@$/.test(trimmed)) {
      closeLists()
      output.push(trimmed)
      return
    }

    const escaped = escapeHtml(trimmed)
    const heading = escaped.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      closeLists()
      const level = Math.min(6, heading[1].length)
      output.push(`<h${level}>${applyInlineMarkdown(heading[2])}</h${level}>`)
      return
    }

    const ul = escaped.match(/^[-*]\s+(.+)$/)
    if (ul) {
      if (!inUl) {
        closeLists()
        output.push('<ul>')
        inUl = true
      }
      output.push(`<li>${applyInlineMarkdown(ul[1])}</li>`)
      return
    }

    const ol = escaped.match(/^\d+\.\s+(.+)$/)
    if (ol) {
      if (!inOl) {
        closeLists()
        output.push('<ol>')
        inOl = true
      }
      output.push(`<li>${applyInlineMarkdown(ol[1])}</li>`)
      return
    }

    closeLists()
    output.push(`<p>${applyInlineMarkdown(escaped)}</p>`)
  })

  closeLists()
  let html = output.join('\n')
  codeBlocks.forEach((block, index) => {
    html = html.replace(`@@CODE_BLOCK_${index}@@`, block)
  })
  return html
}

const renderMessageHtml = (msg: VoiceMessage) => {
  if (msg.role === 'assistant') return markdownToHtml(msg.text)
  return escapeHtml(msg.text).replace(/\n/g, '<br />')
}

watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    if (!transcriptRef.value) return
    transcriptRef.value.scrollTo({
      top: transcriptRef.value.scrollHeight,
      behavior: 'smooth'
    })
  }
)

onMounted(async () => {
  await roleStore.loadRoles()
  if (roleStore.currentRole) {
    selectedRoleId.value = roleStore.currentRole.id
  } else if (allRoles.value.length > 0) {
    const defaultRole = allRoles.value[0]
    await roleStore.setCurrentRole(defaultRole)
    selectedRoleId.value = defaultRole.id
  }

  pushMessage('system', '语音会话已就绪，按住麦克风即可开始。')
})

onUnmounted(() => {
  clearRecognizedTimer()
  stopPlayback()
  releaseCurrentAudioUrl()
})
</script>

<style scoped>
.voice-view {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-app);
  position: relative;
  overflow-x: hidden;
  overflow-y: auto;
}

.voice-view::before,
.voice-view::after {
  content: '';
  position: absolute;
  width: min(500px, 100%);
  height: 500px;
  border-radius: 50%;
  filter: blur(120px);
  opacity: 0.25;
  pointer-events: none;
  z-index: 0;
}

.voice-view::before {
  top: 0;
  left: 0;
  background: radial-gradient(circle, rgba(79, 70, 229, 0.35), transparent 60%);
}

.voice-view::after {
  bottom: 0;
  right: 0;
  background: radial-gradient(circle, rgba(16, 185, 129, 0.25), transparent 60%);
}

.voice-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--bg-card) 88%, transparent);
  backdrop-filter: blur(12px);
  position: relative;
  z-index: 10;
  box-shadow: 0 1px 0 rgba(0, 0, 0, 0.02);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.back-button {
  padding-left: 0;
  transition: all 0.2s ease;
}

.back-button:hover {
  color: var(--primary-color);
  transform: translateX(-2px);
}

.title-block {
  min-width: 0;
}

.title-block h1 {
  font-size: 18px;
  margin: 0;
  color: var(--text-primary);
  font-weight: 700;
  letter-spacing: -0.2px;
}

.title-block p {
  margin: 3px 0 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.role-select {
  width: 220px;
}

.voice-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 370px;
  gap: 16px;
  padding: 16px;
  position: relative;
  z-index: 1;
}

.left-column {
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(300px, 1.1fr) minmax(280px, 0.9fr);
  gap: 16px;
}

.right-column {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 16px;
  overflow-y: auto;
  padding-right: 2px;
}

.right-column::-webkit-scrollbar {
  width: 6px;
}

.right-column::-webkit-scrollbar-track {
  background: transparent;
}

.right-column::-webkit-scrollbar-thumb {
  background: var(--border-hover);
  border-radius: 3px;
}

.panel-card {
  background: var(--bg-card);
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: box-shadow 0.3s ease, transform 0.3s ease;
}

.panel-card:hover {
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 1));
}

.header-title h2 {
  margin: 0;
  font-size: 15px;
  color: var(--text-primary);
  font-weight: 700;
  letter-spacing: -0.1px;
}

.header-title p {
  margin: 5px 0 0 0;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.avatar-card {
  display: flex;
  flex-direction: column;
}

.avatar-stage {
  position: relative;
  flex: 1;
  min-height: 0;
  background:
    radial-gradient(circle at 25% 15%, rgba(79, 70, 229, 0.18), transparent 50%),
    radial-gradient(circle at 75% 85%, rgba(37, 99, 235, 0.16), transparent 50%),
    radial-gradient(circle at 50% 50%, rgba(16, 185, 129, 0.08), transparent 60%),
    linear-gradient(145deg, #f8fafc, #eff6ff);
  overflow: hidden;
}

.avatar-stage::before {
  content: '';
  position: absolute;
  inset: 20px;
  border-radius: 16px;
  border: 1.5px dashed rgba(79, 70, 229, 0.25);
  pointer-events: none;
  transition: border-color 0.3s ease;
}

.avatar-stage.recording::before {
  border-color: rgba(220, 38, 38, 0.4);
  animation: border-pulse 1.5s ease-in-out infinite;
}

.avatar-stage.speaking::before {
  border-color: rgba(5, 150, 105, 0.4);
  animation: border-pulse 2s ease-in-out infinite;
}

@keyframes border-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.digital-human {
  position: absolute;
  inset: 0;
}

.stage-overlay {
  position: absolute;
  left: 20px;
  top: 20px;
  display: flex;
  gap: 8px;
  z-index: 5;
}

.stage-chip {
  padding: 5px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--bg-card) 85%, transparent);
  border: 1px solid rgba(226, 232, 240, 0.8);
  backdrop-filter: blur(4px);
  transition: all 0.3s ease;
}

.stage-chip.active {
  color: var(--primary-color);
  border-color: rgba(79, 70, 229, 0.4);
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
  transform: scale(1.02);
}

.avatar-stage.recording .stage-chip.active {
  color: var(--danger);
  border-color: rgba(220, 38, 38, 0.4);
  background: rgba(220, 38, 38, 0.08);
}

.avatar-stage.speaking .stage-chip.active {
  color: var(--success);
  border-color: rgba(5, 150, 105, 0.4);
  background: rgba(5, 150, 105, 0.08);
}

.transcript-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.transcript-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.transcript-list::-webkit-scrollbar {
  width: 6px;
}

.transcript-list::-webkit-scrollbar-track {
  background: transparent;
}

.transcript-list::-webkit-scrollbar-thumb {
  background: var(--border-hover);
  border-radius: 3px;
}

.empty-state {
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--text-secondary);
  padding: 40px 20px;
}

.empty-state .el-icon {
  font-size: 36px;
  opacity: 0.7;
  margin-bottom: 4px;
}

.empty-state span {
  font-size: 13px;
}

.message-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-width: 80%;
  animation: message-in 0.3s ease-out;
}

@keyframes message-in {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.message-item.user {
  align-self: flex-end;
  align-items: flex-end;
}

.message-item.assistant {
  align-self: flex-start;
}

.message-item.system {
  align-self: center;
  max-width: 100%;
}

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
}

.message-item.user .message-meta {
  flex-direction: row-reverse;
}

.message-bubble {
  border: 1px solid var(--border-light);
  background: var(--surface-solid);
  border-radius: 16px;
  padding: 12px 14px;
  line-height: 1.7;
  font-size: 14px;
  color: var(--text-primary);
  word-break: break-word;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  transition: box-shadow 0.2s ease;
}

.message-bubble:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.message-item.user .message-bubble {
  background: linear-gradient(135deg, var(--primary-color), var(--primary-active));
  color: #fff;
  border-color: transparent;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.25);
}

.confidence {
  font-size: 11px;
  color: var(--text-secondary);
  padding: 0 4px;
}

.system-tip {
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--text-secondary);
  background: var(--bg-input);
  border: 1px dashed var(--border-light);
  backdrop-filter: blur(4px);
}

.control-card,
.settings-card,
.tips-card {
  padding-bottom: 16px;
}

.recorder-area {
  display: flex;
  justify-content: center;
  padding: 20px 16px 12px;
}

.status-alert {
  margin: 0 18px;
  border-radius: 12px;
  font-size: 13px;
}

.recognized-preview {
  margin: 14px 18px 0;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: var(--bg-input);
  padding: 12px 14px;
  box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.02);
}

.recognized-preview .label {
  display: block;
  margin-bottom: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.3px;
}

.recognized-preview p {
  margin: 0;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.6;
}

.button-row {
  margin: 14px 18px 0;
  display: flex;
  gap: 10px;
}

.button-row .el-button {
  flex: 1;
  border-radius: 10px;
  height: 40px;
  font-weight: 500;
}

.settings-body {
  padding: 16px 18px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.setting-item {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border-light);
  background: linear-gradient(180deg, #fff, var(--bg-input));
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.setting-item:hover {
  border-color: var(--border-hover);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.setting-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--text-regular);
  font-weight: 500;
}

.setting-line strong {
  color: var(--text-primary);
  font-weight: 700;
}

.voice-type-select {
  width: 100%;
}

.tips-card ul {
  margin: 14px 18px 0;
  padding-left: 20px;
  color: var(--text-regular);
  line-height: 1.9;
  font-size: 13px;
}

.tips-card li {
  position: relative;
}

.tips-card li::marker {
  color: var(--primary-color);
}

.tips-card li + li {
  margin-top: 6px;
}

.message-bubble :deep(h1),
.message-bubble :deep(h2),
.message-bubble :deep(h3) {
  margin: 10px 0 6px;
  line-height: 1.4;
  font-weight: 700;
}

.message-bubble :deep(h1) {
  font-size: 18px;
}

.message-bubble :deep(h2) {
  font-size: 16px;
}

.message-bubble :deep(h3) {
  font-size: 15px;
}

.message-bubble :deep(p) {
  margin: 8px 0;
}

.message-bubble :deep(ul),
.message-bubble :deep(ol) {
  margin: 10px 0;
  padding-left: 20px;
}

.message-bubble :deep(li) {
  margin: 6px 0;
}

.message-bubble :deep(pre) {
  margin: 12px 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #0f172a;
  color: #e2e8f0;
  overflow-x: auto;
  font-size: 13px;
}

.message-bubble :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  padding: 2px 6px;
  border-radius: 6px;
  background: rgba(100, 116, 139, 0.12);
  font-size: 13px;
}

.message-bubble :deep(pre code) {
  background: transparent;
  padding: 0;
}

.message-bubble :deep(a) {
  color: #1d4ed8;
  text-decoration: underline;
  text-underline-offset: 2px;
  word-break: break-all;
}

:deep(.voice-recorder-btn) {
  width: 96px;
  height: 96px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

:deep(.voice-recorder-btn:hover) {
  transform: scale(1.05);
}

:deep(.voice-recorder .recording-indicator),
:deep(.voice-recorder .realtime-text) {
  display: none;
}

@media (max-width: 1280px) {
  .voice-main {
    grid-template-columns: minmax(0, 1fr) 330px;
  }
}

@media (max-width: 1024px) {
  .voice-view {
    height: auto;
    min-height: 100%;
  }

  .voice-header {
    flex-wrap: wrap;
    padding: 12px 16px;
  }

  .header-left {
    flex: 1 1 220px;
  }

  .role-select {
    width: min(100%, 320px);
    flex: 1 1 220px;
  }

  .voice-main {
    flex: none;
    grid-template-columns: minmax(0, 1fr);
    padding: 12px;
  }

  .left-column {
    grid-template-rows: auto;
  }

  .voice-main {
    grid-template-columns: 1fr;
  }

  .right-column {
    max-height: 52vh;
  }

  .title-block p {
    white-space: normal;
  }
}
</style>
