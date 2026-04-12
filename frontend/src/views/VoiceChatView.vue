<template>
  <div class="voice-chat-view" :class="{ 'is-speaking': isSpeaking, 'is-recording': isRecording }">
    <div class="ambient-background">
      <div class="wave-layer wave-1"></div>
      <div class="wave-layer wave-2"></div>
      <div class="wave-layer wave-3"></div>
      <div class="particle-layer">
        <div class="particle" v-for="i in 30" :key="i" :style="getParticleStyle(i)"></div>
      </div>
      <div class="glow-orb orb-1" :class="{ 'active': isRecording || isSpeaking }"></div>
      <div class="glow-orb orb-2" :class="{ 'active': isRecording || isSpeaking }"></div>
      <div class="glow-orb orb-3" :class="{ 'active': isRecording || isSpeaking }"></div>
    </div>

    <div class="glass-header">
      <button class="back-button" @click="handleBack" title="返回">
        <el-icon><ArrowLeft /></el-icon>
      </button>
      <div class="header-info">
        <h1 class="header-title">语音对话</h1>
        <p class="header-subtitle">与 {{ roleStore.currentRole?.name || '智能助手' }} 对话</p>
      </div>
      <div class="header-spacer"></div>
    </div>

    <div class="main-content">
      <div class="digital-human-container">
        <div class="digital-human-wrapper" :class="{ 'speaking': isSpeaking, 'recording': isRecording }">
          <div class="digital-human-frame">
            <div class="frame-decoration top-left"></div>
            <div class="frame-decoration top-right"></div>
            <div class="frame-decoration bottom-left"></div>
            <div class="frame-decoration bottom-right"></div>
            <DigitalHuman
              :role-id="roleStore.currentRole?.id"
              :is-speaking="isSpeaking"
              :audio-url="currentAudioUrl"
              :transparent="true"
              class="digital-human-entity"
            />
          </div>
        </div>
        
        <transition name="fade-scale">
          <div class="status-indicator" v-if="processing || isRecording">
            <div class="status-dot" :class="{ 'pulse': isRecording, 'thinking': processing }"></div>
            <span class="status-text">
              {{ isRecording ? '聆听中...' : (processing ? '思考中...' : '') }}
            </span>
          </div>
        </transition>

        <transition name="fade-scale">
          <div class="audio-visualizer" v-if="isSpeaking || isRecording">
            <div class="wave-bar" v-for="i in 30" :key="i" :style="getWaveBarStyle(i)"></div>
          </div>
        </transition>
      </div>

      <transition name="slide-up-fade">
        <div class="transcription-area" v-if="recognizedText">
          <div class="transcription-bubble glass-panel">
            <div class="transcription-icon-wrapper">
              <el-icon class="transcription-icon"><Microphone /></el-icon>
            </div>
            <div class="transcription-text">{{ recognizedText }}</div>
          </div>
        </div>
      </transition>

      <div class="control-bar glass-panel" :class="{ 'settings-expanded': showSettings, 'pulse-glow': isRecording || isSpeaking }">
  <div class="control-core">
    <div class="recorder-wrapper">
      <div class="recorder-ring" :class="{ 'recording': isRecording }"></div>
      <div class="recorder-glow" :class="{ 'active': isRecording || isSpeaking }"></div>
      <VoiceRecorder
        @recorded="handleVoiceRecorded"
        @recording-start="handleRecordingStart"
        @recording-end="handleRecordingEnd"
        @realtime-text="handleRealtimeText"
        :disabled="processing"
        :enable-realtime="false"
        class="main-recorder-btn"
      />
    </div>
    
    <VoicePlayer
      v-if="responseAudioUrl"
      :audio-url="responseAudioUrl"
      @playing="handlePlaying"
      @stopped="handleStopped"
      v-show="false" 
    />
  </div>

  <button class="settings-toggle" @click="showSettings = !showSettings" :class="{ 'active': showSettings }">
    <el-icon class="toggle-icon" :class="{ 'rotated': showSettings }"><Setting /></el-icon>
    <span class="toggle-text">{{ showSettings ? '收起设置' : '语音设置' }}</span>
  </button>

        <transition name="expand">
          <div class="voice-params-panel" v-if="showSettings">
            <div class="panel-header">
              <div class="panel-icon">
                <el-icon><Microphone /></el-icon>
              </div>
              <div class="panel-title-group">
                <h3 class="panel-title">语音参数</h3>
                <p class="panel-subtitle">调整语音输出效果</p>
              </div>
            </div>
            
            <div class="params-content">
              <div class="param-item">
                <div class="param-header">
                  <div class="param-label-wrapper">
                    <el-icon class="param-icon"><VideoPlay /></el-icon>
                    <span class="param-label">语速</span>
                  </div>
                  <span class="param-value">{{ voiceSpeed.toFixed(1) }}x</span>
                </div>
                <el-slider
                  v-model="voiceSpeed"
                  :min="0.5"
                  :max="2.0"
                  :step="0.1"
                  size="small"
                  class="custom-slider"
                />
              </div>
              
              <div class="param-item">
                <div class="param-header">
                  <div class="param-label-wrapper">
                    <el-icon class="param-icon"><TrendCharts /></el-icon>
                    <span class="param-label">音调</span>
                  </div>
                  <span class="param-value">{{ voicePitch.toFixed(1) }}x</span>
                </div>
                <el-slider
                  v-model="voicePitch"
                  :min="0.5"
                  :max="2.0"
                  :step="0.1"
                  size="small"
                  class="custom-slider"
                />
              </div>

              <div class="param-item">
                <div class="param-header">
                  <div class="param-label-wrapper">
                    <el-icon class="param-icon"><User /></el-icon>
                    <span class="param-label">语音类型</span>
                  </div>
                </div>
                <el-select v-model="voiceType" size="small" class="voice-select">
                  <el-option label="默认" value="default" />
                  <el-option label="女声" value="female" />
                  <el-option label="男声" value="male" />
                  <el-option label="温柔" value="gentle" />
                  <el-option label="活泼" value="lively" />
                </el-select>
              </div>

              <button class="test-button" @click="handleTestVoice">
                <el-icon><VideoPlay /></el-icon>
                <span>试听效果</span>
              </button>
            </div>
          </div>
        </transition>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, onUnmounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Microphone, Setting, VideoPlay, ArrowLeft, User, TrendCharts } from '@element-plus/icons-vue'
import { useRouter } from 'vue-router'
import { useRoleStore } from '@/stores/role'
import DigitalHuman from '@/components/DigitalHuman.vue'
import VoiceRecorder from '@/components/VoiceRecorder.vue'
import VoicePlayer from '@/components/VoicePlayer.vue'
import { voiceApi } from '@/services/api/voice'

const router = useRouter()
const roleStore = useRoleStore()
const isSpeaking = ref(false)
const isRecording = ref(false)
const processing = ref(false)
const showSettings = ref(false)
const recognizedText = ref('')
const currentAudioUrl = ref<string>('')
const responseAudioUrl = ref<string>('')
const voiceSpeed = ref(1.0)
const voicePitch = ref(1.0)
const voiceType = ref('default')
const waveAnimationFrame = ref<number>()

onMounted(async () => {
  await roleStore.loadBuiltinRoles()
  if (roleStore.builtinRoles.length > 0 && !roleStore.currentRole) {
    roleStore.selectRole(roleStore.builtinRoles[0])
  }
  startWaveAnimation()
})

onUnmounted(() => {
  if (waveAnimationFrame.value) {
    cancelAnimationFrame(waveAnimationFrame.value)
  }
})

const handleRecordingStart = () => {
  isRecording.value = true
}

const handleRecordingEnd = () => {
  isRecording.value = false
}

const handleRealtimeText = (text: string) => {
  if (text) {
    recognizedText.value = text
  }
}

const handleVoiceRecorded = async (audioBlob: Blob) => {
  isRecording.value = false
  processing.value = true
  recognizedText.value = ''

  try {
    const audioFile = new File([audioBlob], 'recording.wav', { type: 'audio/wav' })
    
    const response = await voiceApi.sendVoiceMessage({
      audio: audioFile,
      roleId: roleStore.currentRole?.id || ''
    })

    recognizedText.value = response.recognizedText || response.text

    if (response.text) {
      try {
        console.log('开始TTS合成，文本:', response.text)
        const audioBlob = await voiceApi.textToSpeech(
          response.text, 
          voiceType.value,
          voiceSpeed.value, 
          voicePitch.value
        )
        
        console.log('TTS合成成功，音频大小:', audioBlob.size, 'bytes')
        
        if (!audioBlob || audioBlob.size === 0) {
          throw new Error('TTS返回的音频为空')
        }
        
        const audioUrl = URL.createObjectURL(audioBlob)
        responseAudioUrl.value = audioUrl
        currentAudioUrl.value = audioUrl
        
        console.log('创建音频URL:', audioUrl)
        
        const audio = new Audio(audioUrl)
        audio.preload = 'auto'
        audio.volume = 1.0
        
        audio.addEventListener('loadedmetadata', () => {
          console.log('音频元数据加载完成，时长:', audio.duration, '秒')
        })
        
        audio.addEventListener('canplay', () => {
          console.log('音频可以播放')
          audio.play().then(() => {
            console.log('音频播放成功')
            isSpeaking.value = true
          }).catch((playError) => {
            console.error('播放失败:', playError)
            if (playError.name === 'NotAllowedError' || playError.name === 'NotSupportedError') {
              ElMessage.warning('请点击页面后重试播放音频')
            } else {
              ElMessage.error('音频播放失败: ' + (playError.message || '未知错误'))
            }
            isSpeaking.value = false
          })
        })
        
        audio.addEventListener('play', () => {
          console.log('音频开始播放')
          isSpeaking.value = true
        })
        
        audio.addEventListener('ended', () => {
          console.log('音频播放结束')
          isSpeaking.value = false
          URL.revokeObjectURL(audioUrl)
          responseAudioUrl.value = ''
          currentAudioUrl.value = ''
        })
        
        audio.addEventListener('error', (error) => {
          console.error('音频加载/播放失败:', error, audio.error)
          isSpeaking.value = false
          
          if (audio.error) {
            const errorMessages: Record<number, string> = {
              1: '音频加载被中止',
              2: '网络错误',
              3: '音频解码失败',
              4: '不支持的音频格式'
            }
            const errorMsg = errorMessages[audio.error.code] || '未知错误'
            ElMessage.error(`音频播放失败: ${errorMsg}`)
          } else {
            ElMessage.error('音频播放失败: ' + (error.message || '未知错误'))
          }
          
          URL.revokeObjectURL(audioUrl)
          responseAudioUrl.value = ''
          currentAudioUrl.value = ''
        })
        
        audio.load()
      } catch (ttsError: any) {
        console.error('语音合成失败:', ttsError)
        ElMessage.error('语音合成失败: ' + (ttsError.message || '未知错误'))
      }
    }
  } catch (error: any) {
    console.error('语音处理失败:', error)
    ElMessage.error('语音处理失败: ' + (error.message || '未知错误'))
  } finally {
    processing.value = false
    setTimeout(() => {
      recognizedText.value = ''
    }, 3000)
  }
}

const handlePlaying = () => {
  isSpeaking.value = true
}

const handleStopped = () => {
  isSpeaking.value = false
}

const handleTestVoice = async () => {
  try {
    const testText = '这是语音测试，请听效果。'
    const audioBlob = await voiceApi.textToSpeech(
      testText, 
      voiceType.value,
      voiceSpeed.value, 
      voicePitch.value
    )
    const audioUrl = URL.createObjectURL(audioBlob)
    const audio = new Audio(audioUrl)
    audio.play()
    
    audio.onended = () => {
      URL.revokeObjectURL(audioUrl)
    }
    ElMessage.success('正在播放试听')
  } catch (error: any) {
    ElMessage.error('试听失败: ' + (error.message || '未知错误'))
  }
}

const handleBack = () => {
  router.push('/chat')
}

const getParticleStyle = (index: number) => {
  const delay = (index * 0.08) % 3
  const duration = 4 + (index % 4)
  const size = 2 + (index % 4)
  const left = (index * 3.5) % 100
  return {
    left: `${left}%`,
    width: `${size}px`,
    height: `${size}px`,
    animationDelay: `${delay}s`,
    animationDuration: `${duration}s`
  }
}

const getWaveBarStyle = (index: number) => {
  const delay = index * 0.03
  const height = 25 + Math.sin(index * 0.6) * 20
  return {
    animationDelay: `${delay}s`,
    height: `${height}%`
  }
}

const startWaveAnimation = () => {
  const animate = () => {
    waveAnimationFrame.value = requestAnimationFrame(animate)
  }
  animate()
}
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

.voice-chat-view {
  position: relative;
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  background: linear-gradient(135deg, #0a0d14 0%, #111827 50%, #0f172a 100%);
  color: #ffffff;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.1);
}

.glass-header {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 24px;
  background: rgba(10, 13, 20, 0.6);
  backdrop-filter: blur(24px);
  -webkit-backdrop-filter: blur(24px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.back-button {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.15);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.back-button:hover {
  background: rgba(255, 255, 255, 0.15);
  border-color: rgba(255, 255, 255, 0.25);
  transform: translateX(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
}

.back-button:active {
  transform: scale(0.95);
}

.header-info {
  text-align: center;
  flex: 1;
}

.header-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 2px 0;
  background: linear-gradient(135deg, #ffffff 0%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-subtitle {
  font-size: 12px;
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
}

.header-spacer {
  width: 44px;
}

.ambient-background {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  z-index: 0;
  overflow: hidden;
}

.wave-layer {
  position: absolute;
  width: 200%;
  height: 100%;
  opacity: 0.12;
  background: linear-gradient(90deg, transparent, rgba(129, 140, 248, 0.4), transparent);
  animation: wave-flow 20s linear infinite;
}

.wave-1 {
  top: 15%;
  animation-duration: 22s;
  animation-delay: 0s;
}

.wave-2 {
  top: 45%;
  animation-duration: 28s;
  animation-delay: -8s;
  opacity: 0.08;
}

.wave-3 {
  top: 75%;
  animation-duration: 32s;
  animation-delay: -4s;
  opacity: 0.06;
}

@keyframes wave-flow {
  0% { transform: translateX(-50%) translateY(0); }
  100% { transform: translateX(0) translateY(0); }
}

.particle-layer {
  position: absolute;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.particle {
  position: absolute;
  background: rgba(255, 255, 255, 0.7);
  border-radius: 50%;
  animation: particle-float linear infinite;
  box-shadow: 0 0 8px rgba(255, 255, 255, 0.3);
}

@keyframes particle-float {
  0% {
    transform: translateY(100vh) translateX(0) rotate(0deg);
    opacity: 0;
  }
  10% {
    opacity: 1;
  }
  90% {
    opacity: 1;
  }
  100% {
    transform: translateY(-15vh) translateX(150px) rotate(360deg);
    opacity: 0;
  }
}

.glow-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.15;
  transition: opacity 0.8s ease, transform 0.8s ease;
}

.orb-1 {
  top: -20%;
  left: -15%;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(64, 158, 255, 0.5) 0%, transparent 70%);
  animation: orb-float-1 18s ease-in-out infinite;
}

.orb-2 {
  bottom: -20%;
  right: -15%;
  width: 550px;
  height: 550px;
  background: radial-gradient(circle, rgba(168, 85, 247, 0.4) 0%, transparent 70%);
  animation: orb-float-2 20s ease-in-out infinite;
  animation-delay: -6s;
}

.orb-3 {
  top: 40%;
  right: -5%;
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(34, 197, 94, 0.3) 0%, transparent 70%);
  animation: orb-float-3 22s ease-in-out infinite;
  animation-delay: -10s;
}

.glow-orb.active {
  opacity: 0.3;
  transform: scale(1.15);
}

@keyframes orb-float-1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(40px, 50px) scale(1.08); }
  66% { transform: translate(-30px, 30px) scale(0.92); }
}

@keyframes orb-float-2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-40px, -50px) scale(1.08); }
  66% { transform: translate(30px, -30px) scale(0.92); }
}

@keyframes orb-float-3 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(-20px, 30px) scale(1.05); }
  66% { transform: translate(25px, -25px) scale(0.95); }
}

.main-content {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 100px 24px 140px;
}

.digital-human-container {
  flex: 1;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  min-height: 450px;
}

.digital-human-wrapper {
  position: relative;
  transition: transform 0.4s ease;
}

.digital-human-frame {
  position: relative;
  padding: 20px;
}

.frame-decoration {
  position: absolute;
  width: 40px;
  height: 40px;
  border: 2px solid;
  opacity: 0.3;
  transition: all 0.3s ease;
}

.frame-decoration.top-left {
  top: 0;
  left: 0;
  border-right: none;
  border-bottom: none;
  border-color: rgba(129, 140, 248, 0.5);
  border-radius: 12px 0 0 0;
}

.frame-decoration.top-right {
  top: 0;
  right: 0;
  border-left: none;
  border-bottom: none;
  border-color: rgba(129, 140, 248, 0.5);
  border-radius: 0 12px 0 0;
}

.frame-decoration.bottom-left {
  bottom: 0;
  left: 0;
  border-right: none;
  border-top: none;
  border-color: rgba(129, 140, 248, 0.5);
  border-radius: 0 0 0 12px;
}

.frame-decoration.bottom-right {
  bottom: 0;
  right: 0;
  border-left: none;
  border-top: none;
  border-color: rgba(129, 140, 248, 0.5);
  border-radius: 0 0 12px 0;
}

.digital-human-wrapper.speaking .frame-decoration {
  opacity: 0.6;
  border-color: rgba(34, 197, 94, 0.7);
  animation: frame-glow 1.5s ease-in-out infinite;
}

.digital-human-wrapper.recording .frame-decoration {
  opacity: 0.6;
  border-color: rgba(239, 68, 68, 0.7);
  animation: frame-glow 1.2s ease-in-out infinite;
}

@keyframes frame-glow {
  0%, 100% { transform: scale(1); opacity: 0.6; }
  50% { transform: scale(1.1); opacity: 0.8; }
}

.digital-human-wrapper.speaking {
  animation: speaking-pulse 2s ease-in-out infinite;
}

.digital-human-wrapper.recording {
  animation: recording-pulse 1.5s ease-in-out infinite;
}

@keyframes speaking-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.03); }
}

@keyframes recording-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.04); }
}

.digital-human-entity {
  max-height: 65vh;
  transition: opacity 0.3s ease;
}

.status-indicator {
  position: absolute;
  top: 12%;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  z-index: 10;
}

.status-dot {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #ffffff;
  box-shadow: 0 0 20px rgba(255, 255, 255, 0.5);
}

.status-dot.pulse {
  background: #ef4444;
  box-shadow: 0 0 20px rgba(239, 68, 68, 0.6);
  animation: pulse-red 1.5s ease-in-out infinite;
}

.status-dot.thinking {
  background: #3b82f6;
  box-shadow: 0 0 20px rgba(59, 130, 246, 0.6);
  animation: thinking-bounce 1.2s ease-in-out infinite;
}

.status-text {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
  letter-spacing: 0.5px;
  text-transform: uppercase;
}

@keyframes pulse-red {
  0%, 100% { 
    transform: scale(1);
    opacity: 1;
    box-shadow: 0 0 20px rgba(239, 68, 68, 0.6);
  }
  50% { 
    transform: scale(1.4);
    opacity: 0.7;
    box-shadow: 0 0 40px rgba(239, 68, 68, 0.8);
  }
}

@keyframes thinking-bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-10px); }
}

.audio-visualizer {
  position: absolute;
  bottom: 15%;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  height: 50px;
  z-index: 5;
}

.wave-bar {
  width: 4px;
  background: linear-gradient(180deg, #818cf8 0%, #4f46e5 100%);
  border-radius: 4px;
  animation: wave-animate 1.2s ease-in-out infinite;
  box-shadow: 0 0 10px rgba(129, 140, 248, 0.5);
}

@keyframes wave-animate {
  0%, 100% { transform: scaleY(0.2); }
  50% { transform: scaleY(1); }
}

.transcription-area {
  margin-bottom: 40px;
  width: 90%;
  max-width: 700px;
  text-align: center;
  min-height: 80px;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}

.transcription-bubble {
  padding: 20px 28px;
  border-radius: 20px;
  font-size: 16px;
  line-height: 1.7;
  color: #ffffff;
  display: flex;
  align-items: center;
  gap: 16px;
  max-width: 100%;
  word-wrap: break-word;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}

.transcription-icon-wrapper {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.2) 0%, rgba(129, 140, 248, 0.2) 100%);
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.transcription-icon {
  color: #818cf8;
  font-size: 20px;
}

.transcription-text {
  flex: 1;
  text-align: left;
  font-weight: 400;
}

.control-bar {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  width: 92%;
  max-width: 600px;
  border-radius: 28px;
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 24px;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  z-index: 100;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, rgba(255, 255, 255, 0.04) 100%);
  backdrop-filter: blur(24px) saturate(180%);
  -webkit-backdrop-filter: blur(24px) saturate(180%);
  border: 1px solid rgba(255, 255, 255, 0.12);
  box-shadow: 
    0 25px 80px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(255, 255, 255, 0.05) inset,
    0 1px 0 0 rgba(255, 255, 255, 0.1) inset;
  animation: control-bar-float 6s ease-in-out infinite;
}

.control-bar.settings-expanded {
  padding-bottom: 32px;
  animation: control-bar-expanded 0.4s ease-out;
}

@keyframes control-bar-float {
  0%, 100% { transform: translateX(-50%) translateY(0); }
  50% { transform: translateX(-50%) translateY(-4px); }
}

@keyframes control-bar-expanded {
  0% { transform: translateX(-50%) scale(0.98); opacity: 0.8; }
  100% { transform: translateX(-50%) scale(1); opacity: 1; }
}

.control-core {
  display: flex;
  justify-content: center;
  width: 100%;
  position: relative;
}

.recorder-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.recorder-ring {
  position: absolute;
  width: 120px;
  height: 120px;
  border-radius: 50%;
  border: 3px solid transparent;
  border-top-color: rgba(129, 140, 248, 0.6);
  border-right-color: rgba(129, 140, 248, 0.3);
  animation: ring-spin 1.8s linear infinite;
  opacity: 0;
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  filter: drop-shadow(0 0 8px rgba(129, 140, 248, 0.3));
}

.recorder-ring.recording {
  opacity: 1;
  border-top-color: rgba(239, 68, 68, 0.8);
  border-right-color: rgba(239, 68, 68, 0.4);
  filter: drop-shadow(0 0 12px rgba(239, 68, 68, 0.5));
  animation: ring-spin-recording 1.2s linear infinite;
}

@keyframes ring-spin {
  to { transform: rotate(360deg); }
}

@keyframes ring-spin-recording {
  to { transform: rotate(360deg); }
}

.recorder-glow {
  position: absolute;
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(129, 140, 248, 0.2) 0%, transparent 70%);
  opacity: 0;
  transition: opacity 0.4s ease;
  filter: blur(20px);
}

.recorder-glow.active {
  opacity: 0.6;
  animation: glow-pulse 2s ease-in-out infinite;
}

@keyframes glow-pulse {
  0%, 100% { 
    transform: scale(1);
    opacity: 0.4;
  }
  50% { 
    transform: scale(1.1);
    opacity: 0.8;
  }
}

.control-bar.pulse-glow {
  animation: control-bar-pulse 3s ease-in-out infinite;
}

@keyframes control-bar-pulse {
  0%, 100% { 
    box-shadow: 
      0 25px 80px rgba(0, 0, 0, 0.5),
      0 0 0 1px rgba(255, 255, 255, 0.05) inset,
      0 1px 0 0 rgba(255, 255, 255, 0.1) inset;
  }
  50% { 
    box-shadow: 
      0 30px 100px rgba(0, 0, 0, 0.6),
      0 0 0 1px rgba(255, 255, 255, 0.1) inset,
      0 1px 0 0 rgba(255, 255, 255, 0.15) inset,
      0 0 0 0 rgba(129, 140, 248, 0.2);
  }
}

.settings-toggle.active {
  background: linear-gradient(135deg, rgba(129, 140, 248, 0.15) 0%, rgba(129, 140, 248, 0.08) 100%);
  border-color: rgba(129, 140, 248, 0.3);
  box-shadow: 
    0 8px 24px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(129, 140, 248, 0.2) inset;
}

:deep(.voice-recorder-btn) {
  width: 100px;
  height: 100px;
  border-radius: 50%;
  background: linear-gradient(135deg, #3b82f6 0%, #2563eb 50%, #1d4ed8 100%);
  border: 4px solid rgba(255, 255, 255, 0.2);
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 
    0 12px 32px rgba(59, 130, 246, 0.5),
    0 0 0 0 rgba(59, 130, 246, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  position: relative;
  overflow: hidden;
}

:deep(.voice-recorder-btn::before) {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.2), transparent);
  transition: left 0.6s ease;
}

:deep(.voice-recorder-btn:hover) {
  transform: scale(1.12);
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 50%, #2563eb 100%);
  box-shadow: 
    0 16px 40px rgba(59, 130, 246, 0.6),
    0 0 0 4px rgba(59, 130, 246, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.3);
}

:deep(.voice-recorder-btn:hover::before) {
  left: 100%;
}

:deep(.voice-recorder-btn:active) {
  transform: scale(0.96);
  box-shadow: 
    0 8px 24px rgba(59, 130, 246, 0.4),
    0 0 0 0 rgba(59, 130, 246, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.1);
}

.voice-chat-view.is-recording :deep(.voice-recorder-btn) {
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 50%, #b91c1c 100%);
  border-color: rgba(255, 255, 255, 0.3);
  animation: recording-pulse 1.2s ease-in-out infinite;
  box-shadow: 
    0 12px 32px rgba(239, 68, 68, 0.5),
    0 0 0 0 rgba(239, 68, 68, 0.4),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

@keyframes recording-pulse {
  0%, 100% { 
    transform: scale(1);
    box-shadow: 
      0 12px 32px rgba(239, 68, 68, 0.5),
      0 0 0 0 rgba(239, 68, 68, 0.4);
  }
  50% { 
    transform: scale(1.08);
    box-shadow: 
      0 16px 40px rgba(239, 68, 68, 0.6),
      0 0 0 12px rgba(239, 68, 68, 0);
  }
}

.settings-toggle {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.05) 0%, rgba(255, 255, 255, 0.02) 100%);
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 20px;
  border-radius: 16px;
  font-size: 15px;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 
    0 4px 16px rgba(0, 0, 0, 0.2),
    0 0 0 1px rgba(255, 255, 255, 0.05) inset;
  position: relative;
  overflow: hidden;
}

.settings-toggle::before {
  content: '';
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.1), transparent);
  transition: left 0.6s ease;
}

.settings-toggle:hover {
  color: #ffffff;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.06) 100%);
  border-color: rgba(255, 255, 255, 0.15);
  transform: translateY(-2px);
  box-shadow: 
    0 8px 24px rgba(0, 0, 0, 0.3),
    0 0 0 1px rgba(255, 255, 255, 0.1) inset;
}

.settings-toggle:hover::before {
  left: 100%;
}

.settings-toggle:active {
  transform: translateY(0) scale(0.98);
}

.toggle-icon {
  font-size: 20px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  filter: drop-shadow(0 0 4px rgba(129, 140, 248, 0.3));
}

.settings-toggle:hover .toggle-icon {
  filter: drop-shadow(0 0 8px rgba(129, 140, 248, 0.5));
  transform: rotate(15deg);
}

.toggle-icon.rotated {
  transform: rotate(180deg);
}

.settings-toggle:hover .toggle-icon.rotated {
  transform: rotate(195deg);
}

.toggle-text {
  font-size: 15px;
  font-weight: 500;
  letter-spacing: 0.3px;
  background: linear-gradient(135deg, #ffffff 0%, #a5b4fc 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.voice-params-panel {
  width: 100%;
  background: rgba(0, 0, 0, 0.2);
  border-radius: 16px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  border: 1px solid rgba(255, 255, 255, 0.08);
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 4px;
}

.panel-icon {
  width: 48px;
  height: 48px;
  background: linear-gradient(135deg, rgba(129, 140, 248, 0.2) 0%, rgba(79, 70, 229, 0.2) 100%);
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  color: #818cf8;
}

.panel-title-group {
  flex: 1;
}

.panel-title {
  font-size: 16px;
  font-weight: 600;
  color: #ffffff;
  margin: 0 0 4px 0;
  letter-spacing: -0.01em;
}

.panel-subtitle {
  font-size: 13px;
  color: rgba(255, 255, 255, 0.5);
  margin: 0;
}

.params-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.param-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.param-label-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
}

.param-icon {
  color: rgba(129, 140, 248, 0.8);
  font-size: 16px;
}

.param-label {
  font-size: 14px;
  font-weight: 500;
  color: rgba(255, 255, 255, 0.9);
}

.param-value {
  font-size: 14px;
  font-weight: 600;
  color: #818cf8;
  min-width: 45px;
  text-align: right;
}

.custom-slider {
  --el-slider-main-bg-color: linear-gradient(90deg, #818cf8 0%, #6366f1 100%);
  --el-slider-runway-bg-color: rgba(255, 255, 255, 0.12);
  --el-slider-button-size: 18px;
}

.voice-select {
  width: 100%;
}

.test-button {
  width: 100%;
  padding: 14px;
  background: linear-gradient(135deg, rgba(129, 140, 248, 0.2) 0%, rgba(79, 70, 229, 0.2) 100%);
  border: 1px solid rgba(129, 140, 248, 0.35);
  border-radius: 12px;
  color: #818cf8;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  transition: all 0.2s ease;
  margin-top: 4px;
}

.test-button:hover {
  background: linear-gradient(135deg, rgba(129, 140, 248, 0.3) 0%, rgba(79, 70, 229, 0.3) 100%);
  border-color: rgba(129, 140, 248, 0.5);
  transform: translateY(-2px);
  box-shadow: 0 8px 20px rgba(129, 140, 248, 0.2);
}

.test-button:active {
  transform: translateY(0);
}

.fade-scale-enter-active,
.fade-scale-leave-active {
  transition: all 0.3s ease;
}

.fade-scale-enter-from,
.fade-scale-leave-to {
  opacity: 0;
  transform: scale(0.85);
}

.slide-up-fade-enter-active,
.slide-up-fade-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.slide-up-fade-enter-from,
.slide-up-fade-leave-to {
  opacity: 0;
  transform: translateY(25px);
}

.expand-enter-active,
.expand-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.expand-enter-from,
.expand-leave-to {
  max-height: 0;
  opacity: 0;
  margin-top: 0;
  padding-top: 0;
  padding-bottom: 0;
}

.expand-enter-to,
.expand-leave-from {
  max-height: 550px;
  opacity: 1;
}
</style>
