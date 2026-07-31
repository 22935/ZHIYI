<!-- 语音设置组件 — TTS 语音引擎、语速滑块和音调频率设置表单 -->
<template>
  <div class="voice-settings-art">
    <el-form label-position="top">
      <div class="voice-grid">
        <!-- 语音选择 -->
        <el-form-item label="语音引擎" class="grid-item">
          <el-select v-model="voice" @change="handleChange" class="art-select">
            <el-option label="默认助手机器人" value="default" />
            <el-option label="温柔治愈女声" value="female" />
            <el-option label="成熟稳重男声" value="male" />
            <el-option label="甜美亲切女声" value="gentle" />
            <el-option label="活力阳光男声" value="lively" />
          </el-select>
        </el-form-item>

        <!-- 语速控制 -->
        <el-form-item label="语速调节" class="grid-item full-width">
          <div class="slider-container">
            <el-slider
              v-model="speed"
              :min="0.5"
              :max="2.0"
              :step="0.1"
              class="art-slider"
              @change="handleChange"
            />
            <span class="val-tag">{{ speed.toFixed(1) }}x</span>
          </div>
        </el-form-item>
        
        <!-- 音调控制 -->
        <el-form-item label="音调频率" class="grid-item full-width">
          <div class="slider-container">
            <el-slider
              v-model="pitch"
              :min="0.5"
              :max="2.0"
              :step="0.1"
              class="art-slider"
              @change="handleChange"
            />
            <span class="val-tag">{{ pitch.toFixed(1) }}x</span>
          </div>
        </el-form-item>
      </div>

      <!-- 试听区域 -->
      <div class="test-area">
        <div class="test-info">
          <span class="label">测试当前配置</span>
          <span class="desc">点击下方按钮试听合成语音效果</span>
        </div>
        <div class="test-actions">
          <button class="test-pill" @click.prevent="handleTest">
            <el-icon><VideoPlay /></el-icon>
            <span>开始试听</span>
          </button>
          <button class="reset-pill" @click.prevent="handleReset">
            <span>重置为默认</span>
          </button>
        </div>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { VideoPlay } from '@element-plus/icons-vue'
import { voiceApi } from '@/services/api/voice'

const props = defineProps({
  initialVoice: { type: String, default: 'default' },
  initialSpeed: { type: Number, default: 1.0 },
  initialPitch: { type: Number, default: 1.0 }
})

const emit = defineEmits<{
  change: [settings: { voice: string; speed: number; pitch: number }]
}>()

const voice = ref(props.initialVoice)
const speed = ref(props.initialSpeed)
const pitch = ref(props.initialPitch)

// 同步初始值
watch(() => props.initialVoice, (val) => voice.value = val)
watch(() => props.initialSpeed, (val) => speed.value = val)
watch(() => props.initialPitch, (val) => pitch.value = val)

const handleChange = () => {
  emit('change', {
    voice: voice.value,
    speed: speed.value,
    pitch: pitch.value
  })
}

const handleTest = async () => {
  try {
    const testText = '您好，这是当前语音配置的试听效果。'
    const audioBlob = await voiceApi.textToSpeech(testText, voice.value, speed.value, pitch.value)
    const audioUrl = URL.createObjectURL(audioBlob)
    const audio = new Audio(audioUrl)
    audio.play()
    
    audio.onended = () => {
      URL.revokeObjectURL(audioUrl)
    }
    ElMessage.success('正在试听...')
  } catch (error: any) {
    ElMessage.error('试听失败: ' + (error.message || '未知错误'))
  }
}

const handleReset = () => {
  voice.value = 'default'
  speed.value = 1.0
  pitch.value = 1.0
  handleChange()
  ElMessage.success('语音设置已重置')
}
</script>

<style scoped lang="scss">
.voice-settings-art {
  background: var(--card-bg);
  border: 1px solid var(--border);
  border-radius: 32px;
  padding: 40px;
  backdrop-filter: blur(20px);
}

.voice-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 32px;
  margin-bottom: 40px;
}

.slider-container {
  display: flex;
  align-items: center;
  gap: 24px;
  .art-slider { flex: 1; }
  .val-tag { font-size: 13px; font-weight: 800; font-family: 'JetBrains Mono', monospace; min-width: 40px; color: var(--accent); }
}

.test-area {
  padding-top: 32px;
  border-top: 1px solid var(--border);
  display: flex;
  justify-content: space-between;
  align-items: center;

  .test-info {
    display: flex;
    flex-direction: column;
    gap: 4px;
    .label { font-size: 14px; font-weight: 700; }
    .desc { font-size: 12px; color: var(--text-dim); }
  }

  .test-actions {
    display: flex;
    gap: 16px;
  }

  .test-pill {
    height: 44px;
    padding: 0 24px;
    background: var(--accent);
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 800;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: all 0.3s;
    &:hover { transform: translateY(-2px); opacity: 0.9; }
  }

  .reset-pill {
    height: 44px;
    padding: 0 20px;
    background: transparent;
    border: 1px solid var(--border);
    color: var(--text-dim);
    border-radius: 12px;
    font-size: 12px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.3s;
    &:hover { border-color: var(--text); color: var(--text); }
  }
}

:deep(.el-form-item__label) {
  font-size: 12px;
  font-weight: 800;
  color: var(--text-dim) !important;
  text-transform: uppercase;
  letter-spacing: 1px;
}
</style>
