<template>
  <ErrorBoundary>
    <div id="app">
      <el-container class="app-layout" :class="{ 'immersive-mode': isImmersive }">
        <!-- Sidebar Navigation -->
        <el-aside width="260px" class="app-sidebar" v-if="!isImmersive">
          <!-- Logo Section -->
          <div class="sidebar-header" @click="router.push('/chat')">
            <div class="logo-icon">
              <svg viewBox="0 0 32 32" width="22" height="22" fill="none" xmlns="http://www.w3.org/2000/svg">
                <circle cx="16" cy="16" r="14" stroke="white" stroke-width="1.8" fill="none"/>
                <circle cx="16" cy="11" r="4" fill="white"/>
                <circle cx="9" cy="22" r="3.2" fill="white" opacity="0.7"/>
                <circle cx="23" cy="22" r="3.2" fill="white" opacity="0.7"/>
                <line x1="16" y1="15" x2="9" y2="19" stroke="white" stroke-width="1.2" opacity="0.6"/>
                <line x1="16" y1="15" x2="23" y2="19" stroke="white" stroke-width="1.2" opacity="0.6"/>
                <line x1="9" y1="22" x2="23" y2="22" stroke="white" stroke-width="1.2" opacity="0.4"/>
              </svg>
            </div>
            <span class="logo-text">联邦智枢</span>
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
              <el-menu-item index="/federated-agent-workbench">
                <el-icon><DataAnalysis /></el-icon>
                <span>智能体工作台</span>
              </el-menu-item>
              <el-menu-item index="/contract-clause-planner">
                <el-icon><DataAnalysis /></el-icon>
                <span>合同起草规划</span>
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
              <el-menu-item index="/federated-learning">
                <el-icon><DataAnalysis /></el-icon>
                <span>联邦管理</span>
              </el-menu-item>
              <el-menu-item index="/federated-models">
                <el-icon><DataAnalysis /></el-icon>
                <span>模型管理</span>
              </el-menu-item>
              <el-menu-item index="/settings">
                <el-icon><Setting /></el-icon>
                <span>{{ $t('nav.settings') }}</span>
              </el-menu-item>
            </el-menu>
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

          <el-main class="app-main" :class="{ 'route-scrollable': isRouteScrollable }">
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
  ChatDotRound, User, Search, 
  Clock, Setting, SwitchButton, DataAnalysis
} from '@element-plus/icons-vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { authApi } from '@/services/api/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const globalError = ref('')

// Sidebar navigation state

// Sidebar scroll container reference
const sidebarNav = ref<HTMLElement | null>(null)

// Handle mouse-wheel scrolling inside sidebar
const handleSidebarWheel = (event: WheelEvent) => {
  if (!sidebarNav.value) return
  
  // Prevent page-level scrolling when pointer is on sidebar
  event.preventDefault()
  
  // Slow down scroll speed for smoother navigation
  const scrollAmount = event.deltaY * 0.5
  
  // Scroll only the sidebar container
  sidebarNav.value.scrollBy({
    top: scrollAmount,
    behavior: 'smooth'
  })
}

// Immersive mode: only keep login page immersive
const isImmersive = computed(() => {
  const path = route.path
  return path.startsWith('/login')
})

const isRouteScrollable = computed(() => {
  const path = route.path
  return (
    path.startsWith('/federated-learning') ||
    path.startsWith('/federated-models') ||
    path.startsWith('/federated-agent-workbench') ||
    path.startsWith('/contract-clause-planner')
  )
})

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/chat' || path.startsWith('/chat')) return '/chat'
  if (path.startsWith('/federated-agent-workbench')) return '/federated-agent-workbench'
  if (path.startsWith('/contract-clause-planner')) return '/contract-clause-planner'
  if (path === '/roles' || path.startsWith('/roles')) return '/roles'
  if (path === '/rag' || path.startsWith('/rag')) return '/rag'
  if (path === '/settings' || path.startsWith('/settings')) return '/settings'
  if (path.startsWith('/history')) return '/history'
  if (path.startsWith('/federated-models')) return '/federated-models'
  if (path.startsWith('/federated-learning')) return '/federated-learning'
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

// Logout with confirmation dialog
const handleLogout = async () => {
  try {
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

    const result = await authApi.logout()
    if (result.success) {
      ElMessage.success(result.message || '退出登录成功')
      router.push('/login')
    } else {
      ElMessage.error(result.message || '退出登录失败')
    }
  } catch (error) {
    if (error === 'cancel') return
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
  max-height: calc(100vh - 200px); /* 减少底部空白，优化高度 */
}

/* Sidebar menu scrolling */
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
  height: 320px; /* Keep a stable user card height */
  min-height: 320px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.02);
  overflow: hidden; /* Prevent overflow artifacts */
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
  margin-top: auto; /* 确保底部区域始终在底部 */
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

/* Footer layout */
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

.app-main.route-scrollable {
  overflow-y: auto;
  overflow-x: hidden;
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
  background-color: #0f1115;
}

.immersive-mode .app-main {
  overflow-y: auto;
}

/* Responsive optimization */
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

''
