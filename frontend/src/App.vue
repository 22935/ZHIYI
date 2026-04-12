<template>
  <ErrorBoundary>
    <div id="app">
      <el-container class="app-layout" :class="{ 'immersive-mode': isImmersive }">
        <!-- Sidebar Navigation -->
        <el-aside width="260px" class="app-sidebar" v-if="!isImmersive">
          <!-- Logo Section -->
          <div class="sidebar-header" @click="router.push('/chat')">
            <div class="logo-icon">K</div>
            <span class="logo-text">Kinlin AI</span>
          </div>

          <!-- Main Navigation -->
          <div class="sidebar-nav" ref="sidebarNav">
            <el-menu
              :default-active="activeMenu"
              router
              class="sidebar-menu"
              @wheel="handleSidebarWheel"
            >
              <div class="menu-group-title">{{ $t('nav.main') }}</div>
              <el-menu-item index="/chat">
                <el-icon><ChatDotRound /></el-icon>
                <span>{{ $t('nav.chat') }}</span>
              </el-menu-item>
              <el-menu-item index="/digital-human">
                <el-icon><UserFilled /></el-icon>
                <span>{{ $t('nav.digitalHuman') }}</span>
              </el-menu-item>
              <el-menu-item index="/voice">
                <el-icon><Microphone /></el-icon>
                <span>{{ $t('nav.voice') }}</span>
              </el-menu-item>

              <div class="menu-group-title">{{ $t('nav.knowledge') }}</div>
              <el-menu-item index="/rag">
                <el-icon><Search /></el-icon>
                <span>{{ $t('nav.rag') }}</span>
              </el-menu-item>
              <el-menu-item index="/history">
                <el-icon><Clock /></el-icon>
                <span>{{ $t('nav.history') }}</span>
              </el-menu-item>

              <div class="menu-group-title">{{ $t('nav.system') }}</div>
              <el-menu-item index="/roles">
                <el-icon><User /></el-icon>
                <span>{{ $t('nav.roles') }}</span>
              </el-menu-item>
              <!-- <el-menu-item index="/federated-models">
                <el-icon><DataAnalysis /></el-icon>
                <span>模型管理</span>
              </el-menu-item> -->
              <el-menu-item index="/settings">
                <el-icon><Setting /></el-icon>
                <span>{{ $t('nav.settings') }}</span>
              </el-menu-item>
            </el-menu>
          </div>

          <!-- Digital Human Widget -->
          <div class="sidebar-digital-human">
            <DigitalHuman
              :role-id="currentRoleId"
              :is-speaking="isSpeaking"
              :audio-url="currentAudioUrl"
            />
          </div>

          <!-- User Profile / Bottom Section -->
          <div class="sidebar-footer">
            <div class="user-profile" @click="router.push('/user')">
              <el-avatar :size="32" class="user-avatar">U</el-avatar>
              <div class="user-info">
                <span class="user-name">User</span>
                <span class="user-status">Online</span>
              </div>
            </div>
            <div class="logout-section">
              <el-button 
                class="logout-btn" 
                type="danger" 
                size="small" 
                @click="handleLogout"
                :icon="SwitchButton"
              >
                退出登录
              </el-button>
            </div>
          </div>
        </el-aside>

        <!-- Main Content Area -->
        <el-container class="main-container">
          <!-- Global Error Banner (Floating) -->
          <transition name="fade">
            <div v-if="globalError" class="global-error-banner">
              <el-alert
                :title="globalError"
                type="error"
                show-icon
                @close="clearGlobalError"
              />
            </div>
          </transition>

          <el-main class="app-main">
            <router-view v-slot="{ Component }">
              <transition name="fade" mode="out-in">
                <component :is="Component" />
              </transition>
            </router-view>
          </el-main>
        </el-container>
      </el-container>
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { 
  ChatDotRound, User, UserFilled, Microphone, Search, 
  Clock, Setting, SwitchButton
} from '@element-plus/icons-vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import DigitalHuman from '@/components/DigitalHuman.vue'
import { useRoleStore } from '@/stores/role'
import { authApi } from '@/services/api/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const globalError = ref('')

// 获取角色和聊天状态
const roleStore = useRoleStore()

// 计算当前角色ID和状态
const currentRoleId = computed(() => roleStore.currentRole?.id || null)
const isSpeaking = computed(() => false) // 可以从chatStore获取
const currentAudioUrl = computed(() => '') // 可以从chatStore获取

// 导航栏滚动相关
const sidebarNav = ref<HTMLElement | null>(null)

// 处理导航栏滚动
const handleSidebarWheel = (event: WheelEvent) => {
  if (!sidebarNav.value) return
  
  // 阻止默认滚动行为
  event.preventDefault()
  
  // 计算滚动距离（平滑滚动）
  const scrollAmount = event.deltaY * 0.5
  
  // 平滑滚动导航栏
  sidebarNav.value.scrollBy({
    top: scrollAmount,
    behavior: 'smooth'
  })
}

// 判断是否为沉浸式模式（如语音交互界面、登录页面、联邦学习管理中心、设置页面等）
const isImmersive = computed(() => {
  const path = route.path
  return path.startsWith('/voice') || 
         path.startsWith('/login') || 
         path.startsWith('/federated-models') ||
         path.startsWith('/settings')
})

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/chat' || path.startsWith('/chat')) return '/chat'
  if (path === '/digital-human' || path.startsWith('/digital-human')) return '/digital-human'
  if (path === '/voice' || path.startsWith('/voice')) return '/voice'
  if (path === '/roles' || path.startsWith('/roles')) return '/roles'
  if (path === '/rag' || path.startsWith('/rag')) return '/rag'
  if (path === '/settings' || path.startsWith('/settings')) return '/settings'
  if (path.startsWith('/history')) return '/history'
  if (path.startsWith('/federated-models')) return '/federated-models'
  if (path.startsWith('/user')) return '/settings' // User goes to settings
  return path
})

const clearGlobalError = () => {
  globalError.value = ''
}

const handleGlobalError = (event: CustomEvent) => {
  const detail = event.detail
  if (detail.clear) {
    globalError.value = ''
    return
  }
  
  if (detail.message) {
    globalError.value = detail.message
    const duration = detail.duration || 5000
    setTimeout(() => {
      clearGlobalError()
    }, duration)
  }
}

// 退出登录处理
const handleLogout = async () => {
  try {
    // 确认退出
    await ElMessageBox.confirm(
      '确定要退出登录吗？退出后将需要重新登录。',
      '确认退出',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'logout-confirm'
      }
    )
    
    // 执行退出登录
    const result = await authApi.logout()
    
    if (result.success) {
      ElMessage.success(result.message || '退出登录成功')
      
      // 跳转到登录页面
      router.push('/login')
    } else {
      ElMessage.error(result.message || '退出登录失败')
    }
  } catch (error) {
    // 用户取消退出
    if (error === 'cancel') {
      return
    }
    
    // 其他错误
    console.error('退出登录失败:', error)
    ElMessage.error('退出登录失败，请重试')
  }
}

onMounted(() => {
  window.addEventListener('global-error', handleGlobalError as EventListener)
})

onUnmounted(() => {
  window.removeEventListener('global-error', handleGlobalError as EventListener)
})
</script>

<style scoped>
.app-layout {
  height: 100%;
  width: 100%;
  background-color: var(--bg-app);
  overflow: hidden;
  display: flex;
}

/* Sidebar Styles */
.app-sidebar {
  background-color: var(--bg-sidebar);
  border-right: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
}

.sidebar-header {
  height: 64px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  cursor: pointer;
  gap: 12px;
}

.logo-icon {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, var(--primary-color), var(--primary-active));
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-weight: bold;
  font-family: var(--font-serif);
  font-size: 18px;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.3);
}

.logo-text {
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.sidebar-nav {
  flex: 1;
  padding: 16px 8px;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
  max-height: calc(100vh - 480px); /* 限制最大高度，确保可以滚动 */
}

/* 导航栏滚动条样式 */
.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.sidebar-nav::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.3);
}

.menu-group-title {
  padding: 12px 16px 8px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-disabled);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.sidebar-menu {
  border: none;
  background: transparent;
}

.sidebar-digital-human {
  padding: 16px;
  border-top: 1px solid var(--border-light);
  border-bottom: 1px solid var(--border-light);
  height: 320px; /* 增加高度以更好地显示数字人 */
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden; /* 确保内容不溢出 */
}

.sidebar-digital-human :deep(.digital-human-container) {
  width: 100%;
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.sidebar-digital-human :deep(.digital-human-canvas) {
  width: 100% !important;
  height: 100% !important;
  display: block;
}

.sidebar-footer {
  padding: 16px;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color 0.2s;
}

.user-profile:hover {
  background-color: rgba(255, 255, 255, 0.05);
}

.user-avatar {
  background-color: var(--primary-color);
  color: white;
  font-weight: 600;
}

.user-info {
  display: flex;
  flex-direction: column;
}

.user-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.user-status {
  font-size: 12px;
  color: var(--success);
}

/* 退出登录按钮样式 */
.logout-section {
  margin-top: 12px;
  padding: 0 12px;
}

.logout-btn {
  width: 100%;
  background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%);
  border: none;
  border-radius: 8px;
  color: white;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 8px rgba(239, 68, 68, 0.3);
}

.logout-btn:hover {
  background: linear-gradient(135deg, #f87171 0%, #ef4444 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(239, 68, 68, 0.4);
}

.logout-btn:active {
  transform: translateY(0);
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.3);
}

.logout-btn:deep(.el-icon) {
  font-size: 14px;
}

/* Main Content Styles */
.main-container {
  background-color: var(--bg-app);
  position: relative;
  display: flex;
  flex-direction: column;
}

.app-main {
  padding: 0;
  overflow: hidden;
  height: 100%;
  width: 100%;
  position: relative;
}

.global-error-banner {
  position: absolute;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  min-width: 300px;
}

/* Transitions */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Immersive Mode Overrides */
.immersive-mode .main-container {
  background-color: #0f1115; /* Match VoiceChatView background */
}

.immersive-mode .app-main {
  overflow-y: auto;
}

/* 艺术感自定义滚动条 */
.app-main::-webkit-scrollbar {
  width: 6px;
}

.app-main::-webkit-scrollbar-track {
  background: transparent;
}

.app-main::-webkit-scrollbar-thumb {
  background: rgba(99, 102, 241, 0.1);
  border-radius: 10px;
}

.app-main::-webkit-scrollbar-thumb:hover {
  background: rgba(99, 102, 241, 0.2);
}
</style>
