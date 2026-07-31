<!-- 用户个人中心页面 — 头像上传、用户名/邮箱、注册日期及统计数据展示 -->
<template>
  <div class="user-view">
    <div class="user-container">
      <!-- 用户信息卡片 -->
      <div class="profile-header-card">
        <div class="profile-background"></div>
        <div class="profile-content">
          <div class="avatar-section">
            <div class="avatar-wrapper">
              <el-upload
                class="avatar-uploader"
                action="/api/upload/avatar"
                :show-file-list="false"
                :on-success="handleAvatarSuccess"
              >
                <el-avatar :src="userInfo.avatar" :size="120" class="user-avatar">
                  <el-icon :size="60"><User /></el-icon>
                </el-avatar>
                <div class="avatar-overlay">
                  <el-icon><Camera /></el-icon>
                </div>
              </el-upload>
            </div>
            <div class="user-basic-info">
              <h1 class="username">{{ userInfo.username }}</h1>
              <p class="user-email">{{ userInfo.email || '未设置邮箱' }}</p>
              <div class="user-meta">
                <span class="meta-item">
                  <el-icon><Calendar /></el-icon>
                  <span>注册于 {{ formatDate(userInfo.createdAt) }}</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 统计卡片 -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-icon conversations">
            <el-icon><ChatDotRound /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.conversations }}</div>
            <div class="stat-label">对话数</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon roles">
            <el-icon><UserFilled /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.roles }}</div>
            <div class="stat-label">角色数</div>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-icon messages">
            <el-icon><Message /></el-icon>
          </div>
          <div class="stat-content">
            <div class="stat-value">{{ stats.messages }}</div>
            <div class="stat-label">消息数</div>
          </div>
        </div>
      </div>

      <!-- 主要内容区域 -->
      <div class="content-grid">
        <!-- 个人信息编辑 -->
        <div class="content-card">
          <div class="card-header">
            <h2 class="card-title">个人信息</h2>
            <p class="card-subtitle">管理您的个人资料信息</p>
          </div>
          <div class="card-body">
            <el-form :model="userInfo" label-position="top" class="profile-form">
              <el-form-item label="用户名">
                <el-input 
                  v-model="userInfo.username" 
                  disabled
                  class="custom-input"
                />
                <div class="form-hint">用户名不可修改</div>
              </el-form-item>
              
              <el-form-item label="邮箱地址">
                <el-input 
                  v-model="userInfo.email" 
                  placeholder="请输入邮箱地址"
                  class="custom-input"
                />
                <div class="form-hint">用于接收重要通知和找回密码</div>
              </el-form-item>

              <el-form-item>
                <button class="save-button" @click="updateProfile">
                  <el-icon><Check /></el-icon>
                  <span>保存更改</span>
                </button>
              </el-form-item>
            </el-form>
          </div>
        </div>

        <!-- 账户安全 -->
        <div class="content-card">
          <div class="card-header">
            <h2 class="card-title">账户安全</h2>
            <p class="card-subtitle">修改密码和账户安全设置</p>
          </div>
          <div class="card-body">
            <el-form :model="accountForm" label-position="top" class="security-form">
              <el-form-item label="当前密码">
                <el-input 
                  v-model="accountForm.currentPassword" 
                  type="password"
                  placeholder="请输入当前密码"
                  show-password
                  class="custom-input"
                />
              </el-form-item>
              
              <el-form-item label="新密码">
                <el-input 
                  v-model="accountForm.newPassword" 
                  type="password"
                  placeholder="请输入新密码（至少8位）"
                  show-password
                  class="custom-input"
                />
                <div class="form-hint">密码长度至少8位，建议包含字母和数字</div>
              </el-form-item>
              
              <el-form-item label="确认新密码">
                <el-input 
                  v-model="accountForm.confirmPassword" 
                  type="password"
                  placeholder="请再次输入新密码"
                  show-password
                  class="custom-input"
                />
              </el-form-item>

              <el-form-item>
                <button class="save-button secondary" @click="changePassword">
                  <el-icon><Lock /></el-icon>
                  <span>修改密码</span>
                </button>
              </el-form-item>
            </el-form>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { User, Camera, Calendar, ChatDotRound, UserFilled, Message, Check, Lock } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useRoleStore } from '@/stores/role'
import { useChatStore } from '@/stores/chat'
import { userApi } from '@/services/api/user'

const userStore = useUserStore()
const roleStore = useRoleStore()
const chatStore = useChatStore()

const userInfo = ref({
  username: '',
  email: '',
  avatar: '',
  createdAt: new Date()
})

const accountForm = ref({
  currentPassword: '',
  newPassword: '',
  confirmPassword: ''
})

const stats = computed(() => {
  return {
    conversations: chatStore.contextId ? 1 : 0,
    roles: roleStore.roles?.length || 0,
    messages: chatStore.messages?.length || 0
  }
})

const formatDate = (date: Date | string | undefined) => {
  if (!date) return '未知'
  const d = new Date(date)
  return d.toLocaleDateString('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' })
}

const handleAvatarSuccess = (response: any) => {
  if (response && response.url) {
    userInfo.value.avatar = response.url
    ElMessage.success('头像上传成功')
  }
}

const updateProfile = async () => {
  if (!userInfo.value.email) {
    ElMessage.warning('请输入邮箱地址')
    return
  }
  
  if (!userStore.currentUser?.id) {
    ElMessage.error('用户信息不存在，请重新登录')
    return
  }
  
  try {
    await userApi.updateUser(userStore.currentUser.id, {
      username: userInfo.value.username,
      email: userInfo.value.email
    })
    // 更新store中的用户信息
    await userStore.loadCurrentUser()
    ElMessage.success('个人信息已更新')
  } catch (error: any) {
    ElMessage.error('更新失败: ' + (error.message || '未知错误'))
  }
}

const changePassword = async () => {
  if (!accountForm.value.currentPassword || !accountForm.value.newPassword) {
    ElMessage.warning('请填写完整的密码信息')
    return
  }
  
  if (accountForm.value.newPassword !== accountForm.value.confirmPassword) {
    ElMessage.warning('两次输入的密码不一致')
    return
  }
  
  if (accountForm.value.newPassword.length < 8) {
    ElMessage.warning('密码长度至少8位')
    return
  }
  
  if (!userStore.currentUser?.id) {
    ElMessage.error('用户信息不存在，请重新登录')
    return
  }
  
  try {
    await userApi.changePassword(userStore.currentUser.id, {
      currentPassword: accountForm.value.currentPassword,
      newPassword: accountForm.value.newPassword
    })
    accountForm.value = {
      currentPassword: '',
      newPassword: '',
      confirmPassword: ''
    }
    ElMessage.success('密码已修改')
  } catch (error: any) {
    const errorMessage = error.response?.data?.message || error.message || '未知错误'
    if (error.response?.status === 400) {
      ElMessage.error('当前密码错误，请重新输入')
    } else {
      ElMessage.error('修改失败: ' + errorMessage)
    }
  }
}

onMounted(async () => {
  await userStore.loadCurrentUser()
  if (userStore.currentUser) {
    userInfo.value = {
      username: userStore.currentUser.username || '',
      email: userStore.currentUser.email || '',
      avatar: '',
      createdAt: userStore.currentUser.createdAt || new Date()
    }
  }
})
</script>

<style scoped lang="scss">
.user-view {
  height: 100%;
  overflow-y: auto;
  background: var(--bg-app);
  padding: var(--page-padding-y) var(--page-padding-x);
}

.user-container {
  max-width: var(--page-content-max-width);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
}

/* 用户信息头部卡片 */
.profile-header-card {
  position: relative;
  background: var(--surface-solid);
  border-radius: 20px;
  border: 1px solid var(--border-light);
  overflow: hidden;
  transition: all 0.3s ease;
}

.profile-background {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 120px;
  background: linear-gradient(135deg, rgba(79, 70, 229, 0.08) 0%, rgba(99, 102, 241, 0.05) 100%);
  z-index: 0;
}

.profile-content {
  position: relative;
  z-index: 1;
  padding: 32px;
}

.avatar-section {
  display: flex;
  align-items: center;
  gap: 24px;
}

.avatar-wrapper {
  position: relative;
  flex-shrink: 0;
}

.avatar-uploader {
  position: relative;
  cursor: pointer;
  
  :deep(.el-upload) {
    border: none;
    background: transparent;
  }
}

.user-avatar {
  border: 4px solid var(--surface-solid);
  transition: transform 0.3s ease;
}

.avatar-overlay {
  position: absolute;
  bottom: 0;
  right: 0;
  width: 36px;
  height: 36px;
  background: var(--primary-color);
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #ffffff;
  border: 3px solid var(--surface-solid);
  opacity: 0;
  transition: opacity 0.3s ease;
  cursor: pointer;
}

.avatar-wrapper:hover .avatar-overlay {
  opacity: 1;
}

.avatar-wrapper:hover .user-avatar {
  transform: scale(1.05);
}

.user-basic-info {
  flex: 1;
}

.username {
  font-size: 28px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px 0;
  letter-spacing: -0.02em;
}

.user-email {
  font-size: 15px;
  color: var(--text-secondary);
  margin: 0 0 16px 0;
  font-weight: 400;
}

.user-meta {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-secondary);
  
  .el-icon {
    font-size: 14px;
  }
}

/* 统计卡片网格 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: var(--page-gap);
}

.stat-card {
  background: var(--surface-solid);
  border: 1px solid var(--border-light);
  border-radius: 16px;
  padding: 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.3s ease;
}

.stat-card:hover {
  border-color: var(--primary-color);
  transform: translateY(-2px);
}

.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
  flex-shrink: 0;
  
  &.conversations {
    background: color-mix(in srgb, var(--primary-color) 10%, transparent);
    color: var(--primary-color);
  }
  
  &.roles {
    background: rgba(16, 185, 129, 0.1);
    color: #10b981;
  }
  
  &.messages {
    background: rgba(59, 130, 246, 0.1);
    color: #3b82f6;
  }
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
  margin-bottom: 4px;
  letter-spacing: -0.01em;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 500;
}

/* 内容网格 */
.content-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
  gap: var(--page-gap);
}

.content-card {
  background: var(--surface-solid);
  border: 1px solid var(--border-light);
  border-radius: 20px;
  overflow: hidden;
  transition: all 0.3s ease;
}

.content-card:hover {
  border-color: var(--border-hover);
}

.card-header {
  padding: var(--space-xl) var(--space-xl) 0;
  border-bottom: 1px solid var(--border-light);
  margin-bottom: var(--space-xl);
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0 0 4px 0;
  letter-spacing: -0.01em;
}

.card-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
  margin: 0 0 var(--space-lg) 0;
  font-weight: 400;
}

.card-body {
  padding: 0 var(--space-xl) var(--space-xl);
}

/* 表单样式 */
.profile-form,
.security-form {
  .el-form-item {
    margin-bottom: 24px;
  }
  
  :deep(.el-form-item__label) {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-primary);
    margin-bottom: 8px;
    padding: 0;
  }
}

.custom-input {
  :deep(.el-input__wrapper) {
    border-radius: 10px;
    border: 1px solid var(--border-light);
    background: var(--bg-input);
    transition: all 0.2s ease;
    box-shadow: none;
  }
  
  :deep(.el-input__wrapper:hover) {
    border-color: var(--border-hover);
    background: var(--surface-solid);
  }
  
  :deep(.el-input__wrapper.is-focus) {
    border-color: var(--primary-color);
    background: var(--surface-solid);
    box-shadow: 0 0 0 3px var(--primary-fade);
  }
}

.form-hint {
  font-size: 12px;
  color: var(--text-disabled);
  margin-top: 6px;
  line-height: 1.4;
}

/* 按钮样式 */
.save-button {
  width: 100%;
  padding: 12px 24px;
  background: var(--primary-color);
  color: #ffffff;
  border: none;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.2s ease;
  font-family: inherit;
}

.save-button:hover {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

.save-button:active {
  transform: translateY(0);
}

.save-button.secondary {
  background: var(--surface-solid);
  color: var(--primary-color);
  border: 1px solid var(--primary-color);
}

.save-button.secondary:hover {
  background: var(--primary-fade);
  border-color: var(--primary-hover);
}

/* 响应式设计 */
@media (max-width: 768px) {
  .user-view {
    padding: var(--space-lg) var(--space-md);
  }

  .profile-content {
    padding: var(--space-xl);
  }

  .avatar-section {
    flex-direction: column;
    align-items: center;
    text-align: center;
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}

/* 去除深层次阴影和渐变 */
:deep(.el-card) {
  box-shadow: none !important;
  border: 1px solid var(--border-light) !important;
}

:deep(.el-card__header) {
  border-bottom: 1px solid var(--border-light) !important;
  padding: 20px 24px !important;
}

:deep(.el-tabs__header) {
  border-bottom: 1px solid var(--border-light) !important;
  margin: 0 0 24px 0 !important;
}

:deep(.el-tabs__item) {
  font-weight: 500 !important;
  color: var(--text-secondary) !important;
  padding: 0 20px !important;
  
  &.is-active {
    color: var(--primary-color) !important;
    font-weight: 600 !important;
  }
}

:deep(.el-upload) {
  border: none !important;
}
</style>


