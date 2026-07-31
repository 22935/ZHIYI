<!-- 语音录制器组件 — 按住录音按钮，含录制状态指示、实时 ASR 文字识别和松开后 Blob 输出 -->
<template>
  <div class="voice-recorder">
    <el-button
      :type="isRecording ? 'danger' : 'primary'"
      :icon="Microphone"
      circle
      size="large"
      class="voice-recorder-btn"
      @mousedown="startRecording"
      @mouseup="stopRecording"
      @mouseleave="stopRecording"
      :loading="processing"
    >
    </el-button>
    <div v-if="isRecording" class="recording-indicator">
      <span class="pulse"></span>
      <span>正在录音...</span>
    </div>
    <div v-if="realtimeText" class="realtime-text">
      {{ realtimeText }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onUnmounted } from 'vue'
import { Microphone } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { RealtimeASRService } from '@/services/api/realtimeAsr'

interface Props {
  disabled?: boolean
  enableRealtime?: boolean  // 是否启用实时识别
}

interface Emits {
  (e: 'recorded', audioBlob: Blob): void
  (e: 'recording-start'): void
  (e: 'recording-end'): void
  (e: 'realtime-text', text: string): void  // 实时识别文本
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  enableRealtime: false
})

const emit = defineEmits<Emits>()

const isRecording = ref(false)
const processing = ref(false)
const realtimeText = ref('')
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []
let audioStream: MediaStream | null = null
let realtimeASR: RealtimeASRService | null = null
let audioContext: AudioContext | null = null
let audioWorkletNode: AudioWorkletNode | null = null

// 清理资源
onUnmounted(() => {
  stopRecording()
  if (realtimeASR) {
    realtimeASR.close()
  }
  if (audioStream) {
    audioStream.getTracks().forEach(track => track.stop())
  }
  if (audioContext) {
    audioContext.close()
  }
})

const startRecording = async () => {
  if (props.disabled || isRecording.value) return
  
  try {
    audioStream = await navigator.mediaDevices.getUserMedia({ 
      audio: {
        sampleRate: 16000,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true
      }
    })
    
    // 禁用实时识别（有bug，暂时不使用）
    // if (props.enableRealtime) {
    //   await startRealtimeASR()
    // }
    
    mediaRecorder = new MediaRecorder(audioStream, {
      mimeType: 'audio/webm;codecs=opus'
    })
    audioChunks = []

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        audioChunks.push(event.data)
        // 禁用实时识别
        // if (props.enableRealtime && realtimeASR) {
        //   realtimeASR.sendAudio(event.data)
        // }
      }
    }

    mediaRecorder.onstop = () => {
      if (audioChunks.length > 0) {
        const audioBlob = new Blob(audioChunks, { type: 'audio/webm' })
        emit('recorded', audioBlob)
      }
      if (audioStream) {
        audioStream.getTracks().forEach(track => track.stop())
        audioStream = null
      }
      // 结束实时识别
      // if (props.enableRealtime && realtimeASR) {
      //   realtimeASR.endSession()
      // }
    }

    // 正常录音，不使用时间片
    mediaRecorder.start()
    isRecording.value = true
    emit('recording-start')
  } catch (error: any) {
    ElMessage.error('无法访问麦克风: ' + (error.message || '未知错误'))
    console.error('录音失败:', error)
    emit('recording-end')
  }
}

const stopRecording = () => {
  if (mediaRecorder && isRecording.value) {
    mediaRecorder.stop()
    isRecording.value = false
    emit('recording-end')
    realtimeText.value = ''
  }
}

/**
 * 启动实时ASR
 */
const startRealtimeASR = async () => {
  try {
    realtimeASR = new RealtimeASRService()
    await realtimeASR.startSession({
      language: 'zh-CN',
      sampleRate: 16000,
      onPartialResult: (text, confidence) => {
        realtimeText.value = text
        emit('realtime-text', text)
      },
      onFinalResult: (text, confidence) => {
        realtimeText.value = text
        emit('realtime-text', text)
      },
      onError: (error) => {
        console.error('实时识别错误:', error)
        ElMessage.warning('实时识别错误: ' + error)
      }
    })
  } catch (error: any) {
    console.error('启动实时识别失败:', error)
    ElMessage.warning('实时识别功能不可用，将使用普通录音模式')
  }
}
</script>

<style scoped>
.voice-recorder {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.recording-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #f56c6c;
  font-size: 14px;
}

.pulse {
  width: 10px;
  height: 10px;
  background: #f56c6c;
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
</style>

