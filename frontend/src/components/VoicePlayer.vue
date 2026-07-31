<!-- 语音播放器组件 — 音频播放/暂停按钮和时长显示，支持 URL 或 Blob 音频源 -->
<template>
  <div class="voice-player">
    <el-button
      :type="isPlaying ? 'warning' : 'primary'"
      :icon="isPlaying ? VideoPause : VideoPlay"
      circle
      size="small"
      @click="togglePlay"
      :loading="loading"
    />
    <span v-if="duration" class="duration">{{ formatDuration(duration) }}</span>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted, computed, watch } from 'vue'
import { VideoPlay, VideoPause } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

interface Props {
  audioUrl?: string | Blob
}

const props = defineProps<Props>()

interface Emits {
  (e: 'playing'): void
  (e: 'stopped'): void
}

const emit = defineEmits<Emits>()

const isPlaying = ref(false)
const loading = ref(false)
const duration = ref<number | null>(null)
let audio: HTMLAudioElement | null = null

const togglePlay = async () => {
  if (!props.audioUrl) {
    ElMessage.warning('没有可播放的音频')
    return
  }
  
  if (!audio) {
    initAudio()
    // 等待音频加载完成
    await new Promise((resolve) => {
      if (audio) {
        audio.onloadedmetadata = () => {
          resolve(null)
        }
      } else {
        resolve(null)
      }
    })
  }
  
  if (isPlaying.value) {
    audio?.pause()
  } else {
    audio?.play().catch((error) => {
      console.error('播放音频失败:', error)
      ElMessage.error('播放音频失败')
    })
  }
}

const initAudio = () => {
  loading.value = true
  audio = new Audio()
  
  if (props.audioUrl instanceof Blob) {
    audio.src = URL.createObjectURL(props.audioUrl)
  } else {
    audio.src = props.audioUrl
  }
  
  audio.onloadedmetadata = () => {
    duration.value = audio!.duration
    loading.value = false
  }
  
  audio.onplay = () => {
    isPlaying.value = true
    emit('playing')
  }
  
  audio.onpause = () => {
    isPlaying.value = false
    emit('stopped')
  }
  
  audio.onended = () => {
    isPlaying.value = false
    emit('stopped')
  }
  
  audio.onerror = () => {
    loading.value = false
    isPlaying.value = false
  }
}

const formatDuration = (seconds: number) => {
  const mins = Math.floor(seconds / 60)
  const secs = Math.floor(seconds % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

// 监听 audioUrl 变化，重新初始化音频
watch(() => props.audioUrl, (newUrl) => {
  if (newUrl && audio) {
    audio.pause()
    audio = null
    isPlaying.value = false
  }
})

onUnmounted(() => {
  if (audio) {
    audio.pause()
    audio.src = ''
    audio = null
  }
})
</script>

<style scoped>
.voice-player {
  display: flex;
  align-items: center;
  gap: 10px;
}

.duration {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>

