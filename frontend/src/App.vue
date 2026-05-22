<template>
  <ErrorBoundary>
    <div id="app">
      <el-container class="app-layout" :class="{ 'immersive-mode': isImmersive, 'simple-chat-shell': isSimpleChatMode }">
        <!-- Sidebar Navigation -->
        <el-aside width="248px" class="app-sidebar" v-if="!isImmersive && !isSimpleChatMode">
          <!-- Logo Section -->
          <div class="sidebar-header" @click="router.push('/chat')">
            <div class="logo-icon">
              <el-icon><Connection /></el-icon>
            </div>
            <span class="logo-text">知弈</span>
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
                <el-icon><Operation /></el-icon>
                <span>智能体工作台</span>
              </el-menu-item>
              <el-menu-item index="/agentos-console">
                <el-icon><Monitor /></el-icon>
                <span>AgentOS 控制台</span>
              </el-menu-item>
              <el-menu-item index="/agentos/legal/contract-review">
                <el-icon><DocumentChecked /></el-icon>
                <span>律师合同审查</span>
              </el-menu-item>
              <el-menu-item index="/contract-clause-planner">
                <el-icon><DocumentChecked /></el-icon>
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
                <el-icon><Connection /></el-icon>
                <span>联邦管理</span>
              </el-menu-item>
              <el-menu-item index="/federated-models">
                <el-icon><Cpu /></el-icon>
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

        <button
          v-if="isSimpleChatMode"
          class="simple-nav-toggle"
          type="button"
          aria-label="展开导航"
          @click="simpleNavOpen = true"
        >
          <el-icon><MenuIcon /></el-icon>
          <span>导航</span>
        </button>

        <el-drawer
          v-if="isSimpleChatMode"
          v-model="simpleNavOpen"
          direction="ltr"
          :size="268"
          :with-header="false"
          class="simple-nav-drawer"
        >
          <div class="drawer-sidebar">
            <div class="sidebar-header drawer-header" @click="router.push('/chat'); simpleNavOpen = false">
              <div class="logo-icon">
                <el-icon><Connection /></el-icon>
              </div>
              <span class="logo-text">知弈</span>
            </div>

            <el-menu
              :default-active="activeMenu"
              router
              class="sidebar-menu drawer-menu"
              @select="simpleNavOpen = false"
            >
              <div class="menu-group-title">{{ $t('nav.main') }}</div>
              <el-menu-item index="/chat">
                <el-icon><ChatDotRound /></el-icon>
                <span>{{ $t('nav.chat') }}</span>
              </el-menu-item>
              <el-menu-item index="/federated-agent-workbench">
                <el-icon><Operation /></el-icon>
                <span>智能体工作台</span>
              </el-menu-item>
              <el-menu-item index="/agentos-console">
                <el-icon><Monitor /></el-icon>
                <span>AgentOS 控制台</span>
              </el-menu-item>
              <el-menu-item index="/agentos/legal/contract-review">
                <el-icon><DocumentChecked /></el-icon>
                <span>律师合同审查</span>
              </el-menu-item>
              <el-menu-item index="/contract-clause-planner">
                <el-icon><DocumentChecked /></el-icon>
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
                <el-icon><Connection /></el-icon>
                <span>联邦管理</span>
              </el-menu-item>
              <el-menu-item index="/federated-models">
                <el-icon><Cpu /></el-icon>
                <span>模型管理</span>
              </el-menu-item>
              <el-menu-item index="/settings">
                <el-icon><Setting /></el-icon>
                <span>{{ $t('nav.settings') }}</span>
              </el-menu-item>
            </el-menu>

            <div class="sidebar-footer drawer-footer">
              <div class="user-profile" @click="router.push('/user'); simpleNavOpen = false">
                <el-avatar :size="32" class="user-avatar">U</el-avatar>
                <div class="user-info">
                  <span class="user-name">User</span>
                  <span class="user-status">Online</span>
                </div>
              </div>
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
        </el-drawer>

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
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { 
  ChatDotRound, User, Search, 
  Clock, Setting, SwitchButton, Connection,
  Operation, Monitor, DocumentChecked, Cpu,
  Menu as MenuIcon
} from '@element-plus/icons-vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import { authApi } from '@/services/api/auth'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const globalError = ref('')
type ChatInterfaceMode = 'simple' | 'detail'
const CHAT_INTERFACE_MODE_KEY = 'chat.interface_mode'
const CHAT_INTERFACE_MODE_EVENT = 'chat-interface-mode-change'
const getStoredChatInterfaceMode = (): ChatInterfaceMode => {
  return localStorage.getItem(CHAT_INTERFACE_MODE_KEY) === 'detail' ? 'detail' : 'simple'
}
const chatInterfaceMode = ref<ChatInterfaceMode>(getStoredChatInterfaceMode())
const simpleNavOpen = ref(false)

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

const isSimpleChatMode = computed(() => {
  return route.path.startsWith('/chat') && chatInterfaceMode.value === 'simple' && !isImmersive.value
})

const isRouteScrollable = computed(() => {
  const path = route.path
  return (
    path.startsWith('/federated-learning') ||
    path.startsWith('/federated-models') ||
    path.startsWith('/federated-agent-workbench') ||
    path.startsWith('/agentos-console') ||
    path.startsWith('/agentos/legal/contract-review') ||
    path.startsWith('/contract-clause-planner')
  )
})

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/chat' || path.startsWith('/chat')) return '/chat'
  if (path.startsWith('/federated-agent-workbench')) return '/federated-agent-workbench'
  if (path.startsWith('/agentos-console')) return '/agentos-console'
  if (path.startsWith('/agentos/legal/contract-review')) return '/agentos/legal/contract-review'
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

const handleChatInterfaceModeChange = (event: Event) => {
  const mode = (event as CustomEvent<{ mode?: ChatInterfaceMode }>).detail?.mode
  chatInterfaceMode.value = mode === 'detail' ? 'detail' : 'simple'
  if (chatInterfaceMode.value !== 'simple') {
    simpleNavOpen.value = false
  }
}

const handleStorage = (event: StorageEvent) => {
  if (event.key !== CHAT_INTERFACE_MODE_KEY) return
  chatInterfaceMode.value = event.newValue === 'detail' ? 'detail' : 'simple'
  if (chatInterfaceMode.value !== 'simple') {
    simpleNavOpen.value = false
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
  window.addEventListener(CHAT_INTERFACE_MODE_EVENT, handleChatInterfaceModeChange as EventListener)
  window.addEventListener('storage', handleStorage)
})

onUnmounted(() => {
  window.removeEventListener('global-error', handleGlobalError as EventListener)
  window.removeEventListener(CHAT_INTERFACE_MODE_EVENT, handleChatInterfaceModeChange as EventListener)
  window.removeEventListener('storage', handleStorage)
})

watch(isSimpleChatMode, active => {
  if (!active) {
    simpleNavOpen.value = false
  }
})
</script>

<style scoped>
.app-layout {
  height: 100%;
  width: 100%;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.66), rgba(246, 247, 244, 0.98)),
    var(--bg-app);
  overflow: hidden;
  display: flex;
}

/* Sidebar Styles */
.app-sidebar {
  background-color: rgba(251, 251, 248, 0.92);
  border-right: 1px solid var(--border-light);
  backdrop-filter: blur(18px);
  display: flex;
  flex-direction: column;
  transition: width 0.24s var(--ease-out);
}

.sidebar-header {
  height: 72px;
  display: flex;
  align-items: center;
  padding: 0 22px;
  cursor: pointer;
  gap: 10px;
  border-bottom: 1px solid rgba(227, 230, 223, 0.72);
}

.logo-icon {
  width: 34px;
  height: 34px;
  background: #fff;
  border: 1px solid var(--primary-line);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
  font-weight: bold;
  font-size: 18px;
  box-shadow: var(--shadow-sm);
}

.logo-text {
  font-family: var(--font-serif);
  font-size: 19px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: 0;
}

.sidebar-nav {
  flex: 1;
  padding: 18px 8px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
  max-height: calc(100vh - 196px);
}

/* Sidebar menu scrolling */
.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: rgba(63, 107, 99, 0.16);
  border-radius: 999px;
}

.sidebar-nav::-webkit-scrollbar-thumb:hover {
  background: rgba(63, 107, 99, 0.24);
}

.menu-group-title {
  padding: 14px 16px 7px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-disabled);
  letter-spacing: 0;
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
  padding: 14px;
  margin-top: auto;
  border-top: 1px solid rgba(227, 230, 223, 0.72);
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px;
  border-radius: var(--radius-md);
  cursor: pointer;
  border: 1px solid transparent;
  transition: var(--transition);
}

.user-profile:hover {
  background-color: #fff;
  border-color: var(--border-light);
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
  margin-top: 10px;
  padding: 0;
}

.logout-btn {
  width: 100%;
  background: #fff !important;
  border: 1px solid rgba(178, 74, 74, 0.22) !important;
  border-radius: 8px;
  color: var(--danger) !important;
  font-weight: 500;
  transition: var(--transition);
  box-shadow: none;
}

.logout-btn:hover {
  background: rgba(178, 74, 74, 0.08) !important;
  transform: translateY(-1px);
  box-shadow: none;
}

.logout-btn:active {
  transform: translateY(0);
  box-shadow: 0 2px 6px rgba(239, 68, 68, 0.3);
}

.logout-btn:deep(.el-icon) {
  font-size: 14px;
}

.simple-chat-shell .main-container {
  width: 100%;
}

.simple-nav-toggle {
  position: fixed;
  top: 16px;
  left: 16px;
  z-index: 2100;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 12px;
  border: 1px solid rgba(47, 143, 131, 0.22);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.9);
  color: var(--primary-color);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(24, 39, 35, 0.08);
  backdrop-filter: blur(14px);
  transition: border-color 0.18s ease, background-color 0.18s ease, transform 0.18s ease;
}

.simple-nav-toggle:hover {
  border-color: rgba(47, 143, 131, 0.42);
  background: #fff;
  transform: translateY(-1px);
}

.simple-nav-drawer :deep(.el-drawer__body),
:global(.simple-nav-drawer .el-drawer__body) {
  padding: 0;
  background: rgba(251, 251, 248, 0.96);
}

.drawer-sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.72), rgba(246, 247, 244, 0.96)),
    var(--bg-app);
}

.drawer-header {
  flex-shrink: 0;
}

.drawer-menu {
  flex: 1;
  min-height: 0;
  padding: 14px 8px 10px;
  overflow-y: auto;
}

.drawer-menu::-webkit-scrollbar {
  width: 4px;
}

.drawer-menu::-webkit-scrollbar-track {
  background: transparent;
}

.drawer-menu::-webkit-scrollbar-thumb {
  background: rgba(63, 107, 99, 0.18);
  border-radius: 999px;
}

.drawer-footer {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Main Content Styles */
.main-container {
  background-color: transparent;
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
  transition: opacity 0.18s var(--ease-out), transform 0.18s var(--ease-out);
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
  transform: translateY(4px);
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

@media (max-width: 620px) {
  .simple-nav-toggle {
    top: 10px;
    left: 10px;
    width: 36px;
    padding: 0;
    justify-content: center;
  }

  .simple-nav-toggle span {
    display: none;
  }
}
</style>
