<!-- 数字人形象设置抽屉面板 — 调整头像主色、辅色、强调色等外观参数 -->
<template>
  <el-drawer
    v-model="visible"
    title="形象设置"
    :size="400"
    direction="rtl"
    class="avatar-settings-drawer"
  >
    <template #header>
      <div class="drawer-header">
        <h3 class="drawer-title">形象设置</h3>
        <p class="drawer-subtitle">{{ avatarName || '当前形象' }}</p>
      </div>
    </template>

    <div class="settings-content" v-if="avatarId">
      <!-- 颜色调整 -->
      <div class="settings-section">
        <div class="section-title">颜色调整</div>
        <div class="color-controls">
          <div class="control-item">
            <label class="control-label">主色调</label>
            <el-color-picker 
              v-model="settings.colors.primary" 
              show-alpha
              @change="handleColorChange"
            />
            <div class="color-preview" :style="{ background: settings.colors.primary }"></div>
          </div>
          <div class="control-item">
            <label class="control-label">辅助色</label>
            <el-color-picker 
              v-model="settings.colors.secondary" 
              show-alpha
              @change="handleColorChange"
            />
            <div class="color-preview" :style="{ background: settings.colors.secondary }"></div>
          </div>
          <div class="control-item">
            <label class="control-label">强调色</label>
            <el-color-picker 
              v-model="settings.colors.accent" 
              show-alpha
              @change="handleColorChange"
            />
            <div class="color-preview" :style="{ background: settings.colors.accent }"></div>
          </div>
        </div>
      </div>

      <!-- 大小调整 -->
      <div class="settings-section">
        <div class="section-title">大小调整</div>
        <div class="control-item">
          <label class="control-label">缩放比例</label>
          <el-slider 
            v-model="settings.scale" 
            :min="50" 
            :max="150" 
            :step="5"
            show-input
            @change="handleScaleChange"
          />
          <span class="control-value">{{ settings.scale }}%</span>
        </div>
      </div>

      <!-- 背景设置 -->
      <div class="settings-section">
        <div class="section-title">背景设置</div>
        <div class="control-item">
          <label class="control-label">背景颜色</label>
          <el-color-picker 
            v-model="settings.background.color" 
            show-alpha
            @change="handleBackgroundChange"
          />
          <div class="color-preview" :style="{ background: settings.background.color }"></div>
        </div>
        <div class="control-item">
          <label class="control-label">背景透明度</label>
          <el-slider 
            v-model="settings.background.opacity" 
            :min="0" 
            :max="100" 
            :step="5"
            @change="handleBackgroundChange"
          />
          <span class="control-value">{{ settings.background.opacity }}%</span>
        </div>
        <div class="control-item">
          <label class="control-label">预设背景</label>
          <div class="preset-backgrounds">
            <div 
              v-for="preset in backgroundPresets" 
              :key="preset.name"
              class="preset-item"
              :class="{ active: settings.background.color === preset.color }"
              :style="{ background: preset.color }"
              @click="selectPresetBackground(preset)"
            >
              <span class="preset-name">{{ preset.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 显示位置 -->
      <div class="settings-section">
        <div class="section-title">显示位置</div>
        <div class="control-item">
          <label class="control-label">水平位置</label>
          <el-slider 
            v-model="settings.position.x" 
            :min="-50" 
            :max="50" 
            :step="5"
            show-input
            @change="handlePositionChange"
          />
          <span class="control-value">{{ settings.position.x }}%</span>
        </div>
        <div class="control-item">
          <label class="control-label">垂直位置</label>
          <el-slider 
            v-model="settings.position.y" 
            :min="-50" 
            :max="50" 
            :step="5"
            show-input
            @change="handlePositionChange"
          />
          <span class="control-value">{{ settings.position.y }}%</span>
        </div>
        <div class="control-item">
          <label class="control-label">预设位置</label>
          <div class="preset-positions">
            <el-button 
              v-for="preset in positionPresets" 
              :key="preset.name"
              size="small"
              :type="isPositionActive(preset) ? 'primary' : 'default'"
              @click="selectPresetPosition(preset)"
            >
              {{ preset.name }}
            </el-button>
          </div>
        </div>
      </div>

      <!-- 其他设置 -->
      <div class="settings-section">
        <div class="section-title">其他设置</div>
        <div class="control-item">
          <label class="control-label">旋转角度</label>
          <el-slider 
            v-model="settings.rotation" 
            :min="-180" 
            :max="180" 
            :step="5"
            show-input
            @change="handleRotationChange"
          />
          <span class="control-value">{{ settings.rotation }}°</span>
        </div>
        <div class="control-item">
          <label class="control-label">透明度</label>
          <el-slider 
            v-model="settings.opacity" 
            :min="0" 
            :max="100" 
            :step="5"
            @change="handleOpacityChange"
          />
          <span class="control-value">{{ settings.opacity }}%</span>
        </div>
      </div>

      <!-- 操作按钮 -->
      <div class="settings-actions">
        <el-button @click="handleReset">重置</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存设置</el-button>
      </div>
    </div>

    <div v-else class="empty-state">
      <el-icon :size="48"><Picture /></el-icon>
      <p>请先选择一个形象</p>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { Picture } from '@element-plus/icons-vue'

interface Props {
  modelValue: boolean
  avatarId?: string | null
  avatarName?: string
  initialSettings?: any
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'settings-changed', settings: any): void
  (e: 'save', settings: any): void
}

const props = withDefaults(defineProps<Props>(), {
  avatarId: null,
  avatarName: '',
  initialSettings: () => ({
    colors: {
      primary: '#409EFF',
      secondary: '#79bbff',
      accent: '#95d475'
    },
    scale: 100,
    background: {
      color: '#f8fafc',
      opacity: 100
    },
    position: {
      x: 0,
      y: 0
    },
    rotation: 0,
    opacity: 100
  })
})

const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const saving = ref(false)

const settings = reactive({
  colors: {
    primary: props.initialSettings?.colors?.primary || '#409EFF',
    secondary: props.initialSettings?.colors?.secondary || '#79bbff',
    accent: props.initialSettings?.colors?.accent || '#95d475'
  },
  scale: props.initialSettings?.scale || 100,
  background: {
    color: props.initialSettings?.background?.color || '#f8fafc',
    opacity: props.initialSettings?.background?.opacity || 100
  },
  position: {
    x: props.initialSettings?.position?.x || 0,
    y: props.initialSettings?.position?.y || 0
  },
  rotation: props.initialSettings?.rotation || 0,
  opacity: props.initialSettings?.opacity || 100
})

const backgroundPresets = [
  { name: '白色', color: '#ffffff' },
  { name: '浅灰', color: '#f8fafc' },
  { name: '灰白', color: '#f1f5f9' },
  { name: '米白', color: '#fafafa' },
  { name: '浅蓝', color: '#eff6ff' },
  { name: '浅绿', color: '#f0fdf4' }
]

const positionPresets = [
  { name: '居中', x: 0, y: 0 },
  { name: '左上', x: -30, y: -30 },
  { name: '右上', x: 30, y: -30 },
  { name: '左下', x: -30, y: 30 },
  { name: '右下', x: 30, y: 30 }
]

watch(() => props.initialSettings, (newSettings) => {
  if (newSettings) {
    Object.assign(settings, newSettings)
  }
}, { deep: true })

const handleColorChange = () => {
  emit('settings-changed', { ...settings })
}

const handleScaleChange = () => {
  emit('settings-changed', { ...settings })
}

const handleBackgroundChange = () => {
  emit('settings-changed', { ...settings })
}

const handlePositionChange = () => {
  emit('settings-changed', { ...settings })
}

const handleRotationChange = () => {
  emit('settings-changed', { ...settings })
}

const handleOpacityChange = () => {
  emit('settings-changed', { ...settings })
}

const selectPresetBackground = (preset: any) => {
  settings.background.color = preset.color
  handleBackgroundChange()
}

const selectPresetPosition = (preset: any) => {
  settings.position.x = preset.x
  settings.position.y = preset.y
  handlePositionChange()
}

const isPositionActive = (preset: any) => {
  return settings.position.x === preset.x && settings.position.y === preset.y
}

const handleReset = () => {
  Object.assign(settings, props.initialSettings || {
    colors: {
      primary: '#409EFF',
      secondary: '#79bbff',
      accent: '#95d475'
    },
    scale: 100,
    background: {
      color: '#f8fafc',
      opacity: 100
    },
    position: {
      x: 0,
      y: 0
    },
    rotation: 0,
    opacity: 100
  })
  emit('settings-changed', { ...settings })
  ElMessage.info('已重置为默认设置')
}

const handleSave = async () => {
  saving.value = true
  try {
    // 这里可以调用API保存设置
    emit('save', { ...settings })
    ElMessage.success('设置已保存')
  } catch (error) {
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped lang="scss">
.avatar-settings-drawer {
  :deep(.el-drawer__header) {
    margin-bottom: 0;
    padding: 24px 24px 16px;
    border-bottom: 1px solid var(--border-light);
  }

  :deep(.el-drawer__body) {
    padding: 0;
  }
}

.drawer-header {
  .drawer-title {
    font-size: 18px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 4px 0;
  }

  .drawer-subtitle {
    font-size: 13px;
    color: var(--text-secondary);
    margin: 0;
  }
}

.settings-content {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 24px;
  overflow-y: auto;
  max-height: calc(100vh - 120px);
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.control-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.control-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.control-value {
  font-size: 12px;
  color: var(--text-secondary);
  text-align: right;
  margin-top: 4px;
}

.color-controls {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.color-preview {
  width: 100%;
  height: 32px;
  border-radius: 6px;
  margin-top: 8px;
  border: 1px solid var(--border-light);
}

.preset-backgrounds {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 8px;
}

.preset-item {
  aspect-ratio: 1;
  border-radius: 8px;
  border: 2px solid transparent;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;

  &:hover {
    transform: scale(1.05);
  }

  &.active {
    border-color: var(--primary-color);
  }

  .preset-name {
    font-size: 11px;
    font-weight: 500;
    color: rgba(0, 0, 0, 0.6);
    background: color-mix(in srgb, var(--bg-card) 80%, transparent);
    padding: 2px 6px;
    border-radius: 4px;
  }
}

.preset-positions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.settings-actions {
  display: flex;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid var(--border-light);
  margin-top: 8px;
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 24px;
  color: var(--text-secondary);
  text-align: center;

  p {
    margin-top: 16px;
    font-size: 14px;
  }
}
</style>

