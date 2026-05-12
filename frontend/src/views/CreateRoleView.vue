<template>
  <div class="create-role-view">
    <el-container class="view-layout">
      <!-- Header -->
      <el-header class="header">
        <div class="header-content">
          <div class="left-section">
            <button class="back-btn" @click="handleBack">
              <el-icon><ArrowLeft /></el-icon>
            </button>
            <div class="header-text">
              <h1 class="page-title">创建新角色</h1>
              <p class="page-subtitle">定制你的专属数字人助手</p>
            </div>
          </div>
          <div class="header-actions">
            <el-button @click="handleBack" class="cancel-btn" size="large">取消</el-button>
            <el-button 
              type="primary" 
              @click="handleSubmit" 
              :loading="loading" 
              class="create-btn"
              size="large"
            >
              {{ loading ? '创建中...' : '创建角色' }}
            </el-button>
          </div>
        </div>
      </el-header>

      <el-main class="main-content">
        <div class="content-container">
          <!-- Progress Indicator -->
          <div class="progress-indicator">
            <div class="progress-step" :class="{ active: currentStep >= 1, completed: currentStep > 1 }">
              <div class="step-number">1</div>
              <div class="step-label">基本信息</div>
            </div>
            <div class="progress-line" :class="{ active: currentStep > 1 }"></div>
            <div class="progress-step" :class="{ active: currentStep >= 2, completed: currentStep > 2 }">
              <div class="step-number">2</div>
              <div class="step-label">形象风格</div>
            </div>
            <div class="progress-line" :class="{ active: currentStep > 2 }"></div>
            <div class="progress-step" :class="{ active: currentStep >= 3, completed: currentStep > 3 }">
              <div class="step-number">3</div>
              <div class="step-label">个性设定</div>
            </div>
          </div>

          <!-- Step Content -->
          <div class="form-content">
            <!-- Step 1: Basic Info -->
            <div v-show="currentStep === 1" class="step-content">
              <div class="step-header">
                <h2 class="step-title">基本信息</h2>
                <p class="step-desc">设定角色的基础身份信息</p>
              </div>

              <el-form
                ref="formRef"
                :model="form"
                :rules="rules"
                label-position="top"
                class="role-form"
              >
                <el-form-item label="角色名称" prop="name">
                  <el-input 
                    v-model="form.name" 
                    placeholder="例如：Python 专家、心理咨询师、销售顾问" 
                    maxlength="50"
                    show-word-limit
                    size="large"
                  />
                </el-form-item>

                <el-form-item label="角色描述" prop="description">
                  <el-input
                    v-model="form.description"
                    type="textarea"
                    :rows="3"
                    placeholder="简短描述这个角色的主要功能和特点，帮助用户快速了解"
                    maxlength="200"
                    show-word-limit
                  />
                </el-form-item>

                <el-form-item prop="systemPrompt">
                  <template #label>
                    <div class="label-with-helper">
                      <span>系统提示词</span>
                      <el-tag size="small" type="info">核心设定</el-tag>
                    </div>
                  </template>
                  <el-input
                    v-model="form.systemPrompt"
                    type="textarea"
                    :rows="12"
                    placeholder="这是核心设定，决定了角色的行为方式。请详细描述角色的身份背景、专业技能、对话风格、语言禁忌等。&#10;&#10;示例：你是一个拥有20年经验的Python开发专家，精通后端开发、数据科学和机器学习。你的回答应该专业、准确，并提供实用的代码示例。避免使用过于复杂的术语，确保初学者也能理解。"
                    class="prompt-input"
                  />
                </el-form-item>
              </el-form>

              <div class="step-actions">
                <el-button type="primary" @click="goToStep(2)" size="large">
                  下一步：选择形象风格
                </el-button>
              </div>
            </div>

            <!-- Step 2: Digital Human Style -->
            <div v-show="currentStep === 2" class="step-content">
              <div class="step-header">
                <h2 class="step-title">数字人形象风格</h2>
                <p class="step-desc">选择数字人的视觉呈现风格</p>
              </div>

              <div class="style-selector">
                <div 
                  v-for="style in digitalHumanStyles" 
                  :key="style.id"
                  class="style-card"
                  :class="{ active: form.digitalHumanStyle === style.id }"
                  @click="form.digitalHumanStyle = style.id"
                >
                  <div class="style-header">
                    <div class="style-icon">{{ style.icon }}</div>
                    <div class="style-check" v-if="form.digitalHumanStyle === style.id">
                      <el-icon><Check /></el-icon>
                    </div>
                  </div>
                  <h3 class="style-title">{{ style.name }}</h3>
                  <p class="style-description">{{ style.description }}</p>
                  <div class="style-features">
                    <div class="feature-tag" v-for="feature in style.features" :key="feature">
                      {{ feature }}
                    </div>
                  </div>
                </div>
              </div>

              <!-- Avatar Name & Description -->
              <div class="avatar-config-section">
                <h3 class="section-subtitle">首个形象设置</h3>
                <p class="section-hint">为角色创建第一个数字人形象</p>
                
                <el-form :model="form" label-position="top" class="role-form">
                  <div class="form-row">
                    <el-form-item label="形象名称" class="half-width">
                      <el-input 
                        v-model="form.avatarName" 
                        placeholder="例如：正式场合、休闲装扮" 
                        maxlength="30"
                      />
                    </el-form-item>
                    <el-form-item label="职业设定" class="half-width">
                      <el-input 
                        v-model="form.profession" 
                        placeholder="例如：教师、医生、设计师" 
                      />
                    </el-form-item>
                  </div>
                  <el-form-item label="个性特征">
                    <el-input 
                      v-model="form.personality" 
                      placeholder="例如：温柔、专业、活泼" 
                    />
                  </el-form-item>
                </el-form>
              </div>

              <div class="step-actions">
                <el-button @click="goToStep(1)" size="large">上一步</el-button>
                <el-button type="primary" @click="goToStep(3)" size="large">
                  下一步：个性化设定
                </el-button>
              </div>
            </div>

            <!-- Step 3: Personality & Advanced -->
            <div v-show="currentStep === 3" class="step-content">
              <div class="step-header">
                <h2 class="step-title">个性化设定</h2>
                <p class="step-desc">设定角色的对话风格和性格特点（可选）</p>
              </div>

              <div class="advanced-config">
                <div class="config-card">
                  <div class="card-header">
                    <div class="card-icon">💬</div>
                    <div class="card-title">对话风格</div>
                  </div>
                  <div class="card-content">
                    <p class="card-hint">设定角色的对话语气和风格偏好</p>
                    <el-input
                      v-model="form.dialogueStyleText"
                      type="textarea"
                      :rows="4"
                      placeholder='可选配置，JSON格式：&#10;{&#10;  "tone": "warm",&#10;  "formality": "medium",&#10;  "humor": "low"&#10;}'
                    />
                  </div>
                </div>

                <div class="config-card">
                  <div class="card-header">
                    <div class="card-icon">🎭</div>
                    <div class="card-title">性格特点</div>
                  </div>
                  <div class="card-content">
                    <p class="card-hint">定义角色的核心性格特质</p>
                    <el-input
                      v-model="form.personalityText"
                      type="textarea"
                      :rows="4"
                      placeholder='可选配置，JSON格式：&#10;{&#10;  "traits": ["patient", "empathetic"],&#10;  "values": ["honesty", "professionalism"]&#10;}'
                    />
                  </div>
                </div>
              </div>

              <!-- Preview Summary -->
              <div class="creation-summary">
                <div class="summary-header">
                  <h3 class="summary-title">创建预览</h3>
                  <p class="summary-hint">确认信息后点击创建</p>
                </div>
                <div class="summary-content">
                  <div class="summary-item">
                    <span class="summary-label">角色名称</span>
                    <span class="summary-value">{{ form.name || '未设置' }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">角色描述</span>
                    <span class="summary-value">{{ form.description || '未设置' }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">形象风格</span>
                    <span class="summary-value">{{ getStyleName(form.digitalHumanStyle) }}</span>
                  </div>
                  <div class="summary-item">
                    <span class="summary-label">形象名称</span>
                    <span class="summary-value">{{ form.avatarName || '默认形象' }}</span>
                  </div>
                  <div class="summary-item" v-if="form.profession">
                    <span class="summary-label">职业</span>
                    <span class="summary-value">{{ form.profession }}</span>
                  </div>
                  <div class="summary-item" v-if="form.personality">
                    <span class="summary-label">个性</span>
                    <span class="summary-value">{{ form.personality }}</span>
                  </div>
                </div>
              </div>

              <div class="step-actions">
                <el-button @click="goToStep(2)" size="large">上一步</el-button>
                <el-button 
                  type="primary" 
                  @click="handleSubmit" 
                  :loading="loading" 
                  size="large"
                  class="final-create-btn"
                >
                  {{ loading ? '创建中...' : '完成创建' }}
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { ArrowLeft, Check } from '@element-plus/icons-vue'
import { useRoleStore } from '@/stores/role'
import { digitalHumanApi } from '@/services/api/digitalHuman'
import type { RoleCreateRequest } from '@/services/api/role'

const router = useRouter()
const roleStore = useRoleStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const currentStep = ref(1)

const form = reactive({
  name: '',
  description: '',
  systemPrompt: '',
  dialogueStyleText: '',
  personalityText: '',
  digitalHumanStyle: 'realistic',
  avatarName: '',
  profession: '',
  personality: '',
  colors: {
    primary: '#4F46E5',
    secondary: '#818CF8',
    accent: '#10B981'
  }
})

const digitalHumanStyles = [
  {
    id: 'realistic',
    name: '写实风格',
    icon: '🎭',
    description: '极其写实，如同真实人类一般',
    features: ['逼真', '专业', '正式']
  },
  {
    id: 'cartoon',
    name: '卡通风格',
    icon: '🎨',
    description: '清新可爱，适合日常交流',
    features: ['亲和', '活泼', '轻松']
  },
  {
    id: 'anime',
    name: '二次元风格',
    icon: '✨',
    description: '充满艺术感，深受年轻用户喜爱',
    features: ['时尚', '个性', '年轻']
  }
]

const rules: FormRules = {
  name: [
    { required: true, message: '请输入角色名称', trigger: 'blur' },
    { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
  ],
  description: [
    { required: true, message: '请输入角色描述', trigger: 'blur' }
  ],
  systemPrompt: [
    { required: true, message: '请输入系统提示词', trigger: 'blur' },
    { min: 20, message: '提示词至少需要20个字符', trigger: 'blur' }
  ]
}

const goToStep = async (step: number) => {
  // 验证当前步骤
  if (step > currentStep.value) {
    if (currentStep.value === 1 && formRef.value) {
      const valid = await formRef.value.validate().catch(() => false)
      if (!valid) {
        ElMessage.warning('请完善基本信息')
        return
      }
    }
    if (currentStep.value === 2 && !form.digitalHumanStyle) {
      ElMessage.warning('请选择数字人形象风格')
      return
    }
  }
  
  currentStep.value = step
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

const handleBack = () => {
  if (currentStep.value > 1) {
    goToStep(currentStep.value - 1)
  } else {
    router.back()
  }
}

const parseJson = (text: string, fieldName: string = ''): any => {
  if (!text || !text.trim()) return undefined
  try {
    return JSON.parse(text)
  } catch (error) {
    if (text.trim()) {
      ElMessage.warning(`${fieldName || 'JSON'}格式错误，将忽略该配置`)
    }
    return undefined
  }
}

const getStyleName = (styleId: string) => {
  const style = digitalHumanStyles.find(s => s.id === styleId)
  return style?.name || styleId
}

const handleSubmit = async () => {
  if (!formRef.value) return

  await formRef.value.validate(async (valid) => {
    if (valid) {
      loading.value = true
      try {
        // 1. 创建角色
        const roleRequest: RoleCreateRequest = {
          name: form.name.trim(),
          description: form.description.trim() || undefined,
          systemPrompt: form.systemPrompt.trim(),
          dialogueStyle: parseJson(form.dialogueStyleText, '对话风格'),
          personality: parseJson(form.personalityText, '性格特点'),
          avatarConfig: {
            colors: form.colors,
            style: form.digitalHumanStyle
          }
        }

        const role = await roleStore.createRole(roleRequest)
        
        // 2. 为角色创建首个数字人形象
        try {
          console.log('创建数字人形象，角色ID:', role.id)
          const avatarResponse = await digitalHumanApi.createDigitalHuman({
            roleId: role.id,
            name: form.avatarName || '默认形象',
            description: form.description,
            style: form.digitalHumanStyle,
            personality: form.personality || undefined,
            profession: form.profession || undefined
          })
          
          console.log('数字人形象创建响应:', avatarResponse)
          
          if (avatarResponse && avatarResponse.success) {
            ElMessage.success({
              message: '角色和形象创建成功！',
              duration: 2000
            })
          } else {
            ElMessage.warning('角色创建成功，但形象生成失败')
          }
        } catch (avatarError: any) {
          console.error('创建数字人形象失败:', avatarError)
          console.error('错误详情:', avatarError.response?.data || avatarError.message)
          ElMessage.warning('角色创建成功，但形象生成可能需要时间')
        }
        
        // 3. 刷新角色列表（通过事件通知）
        window.dispatchEvent(new CustomEvent('role-created', { detail: { role } }))
        
        // 4. 返回角色管理页面
        setTimeout(() => {
          router.push('/roles')
        }, 500)
        
      } catch (error: any) {
        console.error('创建角色失败:', error)
        ElMessage.error(error.message || '创建角色失败')
      } finally {
        loading.value = false
      }
    } else {
      ElMessage.warning('请完善所有必填信息')
    }
  })
}
</script>

<style scoped lang="scss">
.create-role-view {
  height: 100vh;
  width: 100%;
  background: #fafafa;
  overflow: hidden;
}

.view-layout {
  height: 100%;
}

/* Header */
.header {
  background: #ffffff;
  border-bottom: 1px solid #e5e7eb;
  height: 80px !important;
  display: flex;
  align-items: center;
  padding: 0;
}

.header-content {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding: 0 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.left-section {
  display: flex;
  align-items: center;
  gap: 20px;
}

.back-btn {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  border: 1px solid #e5e7eb;
  cursor: pointer;
  transition: all 0.2s;
  color: #6b7280;

  &:hover {
    color: var(--primary-color);
    background: rgba(79, 70, 229, 0.05);
    border-color: rgba(79, 70, 229, 0.2);
  }
}

.header-text {
  .page-title {
    font-size: 22px;
    font-weight: 600;
    color: #111827;
    margin: 0 0 2px 0;
    letter-spacing: -0.02em;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  }

  .page-subtitle {
    font-size: 13px;
    color: #6b7280;
    margin: 0;
  }
}

.header-actions {
  display: flex;
  gap: 12px;
}

.cancel-btn {
  border-radius: 10px;
  font-weight: 500;
}

.create-btn {
  border-radius: 10px;
  font-weight: 600;
  min-width: 120px;
}

/* Main Content */
.main-content {
  padding: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.content-container {
  max-width: 900px;
  margin: 0 auto;
  padding: 40px 32px 60px;
}

/* Progress Indicator */
.progress-indicator {
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 48px;
  padding: 32px;
  background: white;
  border-radius: 16px;
  border: 1px solid #e5e7eb;
}

.progress-step {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  position: relative;
}

.step-number {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  border: 2px solid #e5e7eb;
  background: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 600;
  color: #9ca3af;
  transition: all 0.3s;
}

.progress-step.active .step-number {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: white;
}

.progress-step.completed .step-number {
  border-color: var(--primary-color);
  background: var(--primary-color);
  color: white;
}

.step-label {
  font-size: 13px;
  font-weight: 500;
  color: #9ca3af;
  transition: color 0.3s;
}

.progress-step.active .step-label,
.progress-step.completed .step-label {
  color: var(--primary-color);
}

.progress-line {
  width: 100px;
  height: 2px;
  background: #e5e7eb;
  margin: 0 16px;
  margin-bottom: 28px;
  transition: background 0.3s;
}

.progress-line.active {
  background: var(--primary-color);
}

/* Form Content */
.form-content {
  background: white;
  border-radius: 16px;
  border: 1px solid #e5e7eb;
  padding: 40px;
}

.step-content {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.step-header {
  margin-bottom: 32px;
  padding-bottom: 24px;
  border-bottom: 1px solid #f3f4f6;
}

.step-title {
  font-size: 20px;
  font-weight: 600;
  color: #111827;
  margin: 0 0 8px 0;
  letter-spacing: -0.01em;
}

.step-desc {
  font-size: 14px;
  color: #6b7280;
  margin: 0;
  line-height: 1.5;
}

/* Role Form */
.role-form {
  :deep(.el-form-item__label) {
    font-weight: 500;
    font-size: 14px;
    color: #374151;
    padding-bottom: 8px;
    line-height: 1.5;
  }

  :deep(.el-input__wrapper) {
    background-color: #f9fafb;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid transparent;
    transition: all 0.2s;

    &:hover {
      background-color: #ffffff;
      border-color: #e5e7eb;
    }

    &.is-focus {
      background-color: #ffffff;
      border-color: var(--primary-color);
    }
  }

  :deep(.el-textarea__inner) {
    background-color: #f9fafb;
    border-radius: 10px;
    padding: 12px 16px;
    border: 1px solid transparent;
    transition: all 0.2s;
    line-height: 1.6;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;

    &:hover {
      background-color: #ffffff;
      border-color: #e5e7eb;
    }

    &:focus {
      background-color: #ffffff;
      border-color: var(--primary-color);
    }
  }
}

.prompt-input {
  :deep(.el-textarea__inner) {
    font-size: 13px;
    line-height: 1.8;
  }
}

.label-with-helper {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.half-width {
  margin-bottom: 0;
}

/* Style Selector */
.style-selector {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 32px;
}

.style-card {
  padding: 24px;
  border: 2px solid #e5e7eb;
  border-radius: 12px;
  cursor: pointer;
  transition: all 0.2s;
  background: white;
  position: relative;

  &:hover {
    border-color: var(--primary-color);
    background: rgba(79, 70, 229, 0.02);
  }

  &.active {
    border-color: var(--primary-color);
    background: rgba(79, 70, 229, 0.05);
  }
}

.style-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.style-icon {
  font-size: 48px;
  line-height: 1;
}

.style-check {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--primary-color);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
}

.style-title {
  font-size: 17px;
  font-weight: 600;
  color: #111827;
  margin: 0 0 8px 0;
}

.style-description {
  font-size: 13px;
  color: #6b7280;
  line-height: 1.5;
  margin: 0 0 16px 0;
}

.style-features {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.feature-tag {
  padding: 4px 10px;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 6px;
  font-size: 11px;
  font-weight: 500;
  color: #6b7280;
}

.style-card.active .feature-tag {
  background: rgba(79, 70, 229, 0.1);
  color: var(--primary-color);
}

/* Avatar Config Section */
.avatar-config-section {
  padding: 24px;
  background: #f9fafb;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
  margin-bottom: 32px;
}

.section-subtitle {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin: 0 0 4px 0;
}

.section-hint {
  font-size: 13px;
  color: #6b7280;
  margin: 0 0 20px 0;
}

/* Advanced Config */
.advanced-config {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 32px;
}

.config-card {
  padding: 24px;
  background: #f9fafb;
  border-radius: 12px;
  border: 1px solid #e5e7eb;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.card-icon {
  font-size: 28px;
  line-height: 1;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #111827;
}

.card-hint {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.5;
  margin: 0 0 12px 0;
}

.card-content {
  :deep(.el-textarea__inner) {
    font-size: 12px;
    line-height: 1.6;
  }
}

/* Creation Summary */
.creation-summary {
  padding: 24px;
  background: rgba(79, 70, 229, 0.03);
  border-radius: 12px;
  border: 1px solid rgba(79, 70, 229, 0.1);
  margin-bottom: 32px;
}

.summary-header {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(79, 70, 229, 0.1);
}

.summary-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin: 0 0 4px 0;
}

.summary-hint {
  font-size: 12px;
  color: #6b7280;
  margin: 0;
}

.summary-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.summary-item {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 10px 0;
  font-size: 14px;
}

.summary-item:not(:last-child) {
  border-bottom: 1px solid rgba(0, 0, 0, 0.05);
}

.summary-label {
  color: #6b7280;
  font-weight: 500;
  min-width: 100px;
}

.summary-value {
  color: #111827;
  font-weight: 500;
  text-align: right;
  flex: 1;
}

/* Step Actions */
.step-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 24px;
  border-top: 1px solid #f3f4f6;
}

.final-create-btn {
  min-width: 140px;
}

/* Responsive */
@media (max-width: 1024px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .style-selector {
    grid-template-columns: 1fr;
  }

  .advanced-config {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .progress-indicator {
    padding: 20px;
  }

  .progress-line {
    width: 60px;
    margin: 0 8px;
  }

  .form-content {
    padding: 24px;
  }

  .header-content {
    padding: 0 16px;
  }

  .content-container {
    padding: 24px 16px;
  }

  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
