<!-- 知弈平台根布局组件 — 侧边栏导航（对话、职业工作台、ACG 引擎、RAG 知识库、联邦学习），含错误边界和沉浸/简洁模式 -->
<template>
  <ErrorBoundary>
    <div id="app">
      <el-container class="app-layout" :class="{ 'immersive-mode': isImmersive }">
        <!-- Sidebar Navigation -->
        <el-aside
          v-if="!isImmersive && !usesDrawerNavigation"
          :width="sidebarAsideWidth"
          class="app-sidebar"
          :class="{ collapsed: mainSidebarCompact, 'chat-panel-open': secondaryNavOpen, resizing: sidebarResizing || chatPanelResizing }"
        >
          <div class="primary-sidebar" :style="{ width: primarySidebarWidth }">
          <!-- Logo Section -->
          <div class="sidebar-header">
            <button class="sidebar-brand" type="button" aria-label="返回对话" @click="router.push('/chat')">
              <span class="logo-icon">
                <img src="/logo.png" alt="" aria-hidden="true" />
              </span>
              <span v-if="!mainSidebarCompact" class="logo-text">知弈</span>
            </button>
            <button
              class="sidebar-collapse-btn"
              type="button"
              :aria-label="secondaryNavOpen ? '关闭任务面板' : (sidebarCollapsed ? '展开侧边栏' : '收起侧边栏')"
              :title="secondaryNavOpen ? '关闭任务面板' : (sidebarCollapsed ? '展开侧边栏' : '收起侧边栏')"
              @click="toggleSidebar"
            >
              <el-icon><Expand v-if="mainSidebarCompact" /><Fold v-else /></el-icon>
            </button>
          </div>

          <!-- Main Navigation -->
          <div class="sidebar-nav" ref="sidebarNav">
            <el-menu
              :default-active="activeMenu"
              router
              class="sidebar-menu"
              :collapse="mainSidebarCompact"
              :collapse-transition="false"
              @wheel="handleSidebarWheel"
            >
              <div v-if="!mainSidebarCompact" class="menu-group-title">{{ $t('nav.main') }}</div>
              <div
                class="chat-nav-group"
                :class="{ active: route.path.startsWith('/chat'), open: chatNavOpen }"
              >
                <button
                  class="chat-nav-trigger"
                  type="button"
                  :aria-expanded="chatNavOpen"
                  aria-controls="chat-side-panel"
                  @click="handleChatNavToggle"
                >
                  <el-icon><ChatDotRound /></el-icon>
                  <span v-if="!mainSidebarCompact" class="chat-nav-label">{{ $t('nav.chat') }}</span>
                  <el-icon v-if="!mainSidebarCompact" class="chat-nav-chevron">
                    <ArrowDown v-if="chatNavOpen" />
                    <ArrowRight v-else />
                  </el-icon>
                </button>

              </div>
              <div
                class="chat-nav-group acg-nav-group"
                :class="{ active: route.path.startsWith('/agentos/acg'), open: acgNavOpen }"
              >
                <button
                  class="chat-nav-trigger"
                  type="button"
                  :aria-expanded="acgNavOpen"
                  aria-controls="acg-side-panel"
                  @click="handleAcgNavToggle"
                >
                  <img class="acg-nav-logo" src="/acglogo.png" alt="" aria-hidden="true" />
                  <span v-if="!mainSidebarCompact" class="chat-nav-label">ACG 动态群体智能引擎</span>
                  <el-icon v-if="!mainSidebarCompact" class="chat-nav-chevron">
                    <ArrowDown v-if="acgNavOpen" />
                    <ArrowRight v-else />
                  </el-icon>
                </button>
              </div>

              <div v-if="!mainSidebarCompact" class="menu-group-title">{{ $t('nav.knowledge') }}</div>
              <el-menu-item index="/rag">
                <el-icon><Search /></el-icon>
                <span>{{ $t('nav.rag') }}</span>
              </el-menu-item>
              <el-menu-item index="/history">
                <el-icon><Clock /></el-icon>
                <span>{{ $t('nav.history') }}</span>
              </el-menu-item>

              <div v-if="!mainSidebarCompact" class="menu-group-title">{{ $t('nav.system') }}</div>
              <el-menu-item index="/agentos-console">
                <el-icon><Monitor /></el-icon>
                <span>ACG 历史记录</span>
              </el-menu-item>
              <el-menu-item index="/roles">
                <el-icon><User /></el-icon>
                <span>{{ $t('nav.roles') }}</span>
              </el-menu-item>
              <el-menu-item index="/federated-learning">
                <el-icon><Connection /></el-icon>
                <span>联邦管理</span>
              </el-menu-item>
              <el-menu-item index="/federated-models">
                <el-icon><Box /></el-icon>
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
            <div class="user-profile">
              <button class="user-identity" type="button" aria-label="打开用户中心" @click="router.push('/user')">
              <el-avatar :size="28" class="user-avatar">{{ sidebarUserInitial }}</el-avatar>
              <div v-if="!mainSidebarCompact" class="user-info">
                <span class="user-name">{{ sidebarUserName }}</span>
                <span class="user-status">{{ sidebarUserMeta }}</span>
              </div>
              </button>
              <button v-if="!mainSidebarCompact" class="user-logout" type="button" aria-label="退出登录" title="退出登录" @click="handleLogout">
                <el-icon><SwitchButton /></el-icon>
              </button>
            </div>
          </div>
          </div>

          <Transition name="chat-panel">
            <section
              v-if="chatNavOpen"
              id="chat-side-panel"
              class="chat-side-panel"
              :style="{ width: `${chatPanelWidth}px` }"
              aria-label="聊天项目"
            >
              <div class="chat-panel-content">
                <div class="workspace-switch" role="tablist" aria-label="对话模式">
                  <button
                    class="workspace-switch-btn"
                    :class="{ active: workspaceMode === 'agent' }"
                    type="button"
                    role="tab"
                    :aria-selected="workspaceMode === 'agent'"
                    @click="selectWorkspaceMode('agent')"
                  >
                    <el-icon><Monitor /></el-icon>
                    <span>Agent</span>
                  </button>
                  <button
                    class="workspace-switch-btn"
                    :class="{ active: workspaceMode === 'chat' }"
                    type="button"
                    role="tab"
                    :aria-selected="workspaceMode === 'chat'"
                    @click="selectWorkspaceMode('chat')"
                  >
                    <el-icon><ChatDotRound /></el-icon>
                    <span>Chat</span>
                  </button>
                </div>

                <button class="chat-submenu-action new-chat-action" type="button" @click="startNewChat">
                  <el-icon><EditPen /></el-icon>
                  <span>新建对话</span>
                </button>

                <div class="chat-submenu-section-head">
                  <span>对话记录</span>
                  <span v-if="recentConversations.length" class="chat-project-count">{{ recentConversations.length }}</span>
                </div>

                <div v-if="conversationListLoading" class="chat-submenu-loading">正在加载…</div>
                <div v-else-if="recentConversations.length" class="chat-project-list" role="list" aria-label="对话记录">
                  <div
                    v-for="conversation in recentConversations"
                    :key="conversation.id"
                    class="chat-project-row"
                    :class="{ active: route.query.contextId === (conversation.contextId || conversation.id) }"
                    role="listitem"
                  >
                    <button
                      class="chat-project-item"
                      type="button"
                      :title="conversation.title || '未命名对话'"
                      @click="openConversation(conversation)"
                    >
                      <span class="chat-project-icon" aria-hidden="true">
                        <el-icon><ChatLineRound /></el-icon>
                      </span>
                      <span class="chat-project-copy">
                        <span class="chat-project-title">{{ conversation.title || '未命名对话' }}</span>
                        <span class="chat-project-time">{{ formatConversationTime(conversation.updatedAt || conversation.createdAt) }}</span>
                      </span>
                      <el-icon class="chat-project-arrow" aria-hidden="true"><ArrowRight /></el-icon>
                    </button>
                    <button
                      class="chat-project-delete"
                      type="button"
                      :aria-label="`删除对话：${conversation.title || '未命名对话'}`"
                      title="删除对话"
                      @click="deleteSidebarConversation(conversation)"
                    >
                      <el-icon><Delete /></el-icon>
                    </button>
                  </div>
                </div>
                <div v-else class="chat-submenu-empty">暂无历史对话</div>

                <button class="chat-submenu-action history-action" type="button" @click="router.push('/history')">
                  <span class="history-action__icon" aria-hidden="true">
                    <el-icon><Clock /></el-icon>
                  </span>
                  <span class="history-action__copy">
                    <strong>查找所有聊天记录</strong>
                    <small>搜索、编辑与管理</small>
                  </span>
                  <el-icon class="history-action__arrow" aria-hidden="true"><ArrowRight /></el-icon>
                </button>
              </div>
              <div
                class="chat-panel-resizer"
                role="separator"
                aria-label="调整聊天子栏宽度"
                aria-orientation="vertical"
                :aria-valuemin="CHAT_PANEL_MIN_WIDTH"
                :aria-valuemax="CHAT_PANEL_MAX_WIDTH"
                :aria-valuenow="chatPanelWidth"
                tabindex="0"
                title="拖动调整宽度，双击恢复默认"
                @pointerdown="startChatPanelResize"
                @keydown="handleChatPanelResizeKeydown"
                @dblclick="resetChatPanelWidth"
              ></div>
            </section>
          </Transition>

          <Transition name="chat-panel">
            <section
              v-if="acgNavOpen"
              id="acg-side-panel"
              class="chat-side-panel acg-side-panel"
              :style="{ width: `${chatPanelWidth}px` }"
              aria-label="ACG 运行管理器"
            >
              <AcgRunManager
                :active-run-id="typeof route.query.runId === 'string' ? route.query.runId : ''"
                @new="startNewAcg"
                @select="openAcgRun"
                @deleted="handleAcgRunDeleted"
                @manage="openAcgOperations"
              />

              <div
                class="chat-panel-resizer"
                role="separator"
                aria-label="调整 ACG 运行面板宽度"
                aria-orientation="vertical"
                :aria-valuemin="CHAT_PANEL_MIN_WIDTH"
                :aria-valuemax="CHAT_PANEL_MAX_WIDTH"
                :aria-valuenow="chatPanelWidth"
                tabindex="0"
                title="拖动调整宽度，双击恢复默认"
                @pointerdown="startChatPanelResize"
                @keydown="handleChatPanelResizeKeydown"
                @dblclick="resetChatPanelWidth"
              ></div>
            </section>
          </Transition>

          <div
            v-if="!sidebarCollapsed && !secondaryNavOpen"
            class="sidebar-resizer"
            role="separator"
            aria-label="调整侧边栏宽度"
            aria-orientation="vertical"
            :aria-valuemin="SIDEBAR_MIN_WIDTH"
            :aria-valuemax="SIDEBAR_MAX_WIDTH"
            :aria-valuenow="sidebarWidth"
            tabindex="0"
            title="拖动调整宽度，双击恢复默认"
            @pointerdown="startSidebarResize"
            @keydown="handleSidebarResizeKeydown"
            @dblclick="resetSidebarWidth"
          ></div>
        </el-aside>

        <button
          v-if="usesDrawerNavigation"
          class="simple-nav-toggle"
          type="button"
          aria-label="展开导航"
          @click="simpleNavOpen = true"
        >
          <el-icon><MenuIcon /></el-icon>
        </button>

        <el-drawer
          v-if="usesDrawerNavigation"
          v-model="simpleNavOpen"
          direction="ltr"
          :size="248"
          :with-header="false"
          class="simple-nav-drawer"
        >
          <div class="drawer-sidebar">
            <div class="sidebar-header drawer-header" @click="router.push('/chat'); simpleNavOpen = false">
              <div class="logo-icon">
                <img src="/logo.png" alt="" aria-hidden="true" />
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
              <el-menu-item index="/agentos/acg">
                <img class="acg-nav-logo" src="/acglogo.png" alt="" aria-hidden="true" />
                <span>ACG 动态群体智能引擎</span>
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
              <el-menu-item index="/agentos-console">
                <el-icon><Monitor /></el-icon>
                <span>ACG 历史记录</span>
              </el-menu-item>
              <el-menu-item index="/roles">
                <el-icon><User /></el-icon>
                <span>{{ $t('nav.roles') }}</span>
              </el-menu-item>
              <el-menu-item index="/federated-learning">
                <el-icon><Connection /></el-icon>
                <span>联邦管理</span>
              </el-menu-item>
              <el-menu-item index="/federated-models">
                <el-icon><Box /></el-icon>
                <span>模型管理</span>
              </el-menu-item>
              <el-menu-item index="/settings">
                <el-icon><Setting /></el-icon>
                <span>{{ $t('nav.settings') }}</span>
              </el-menu-item>
            </el-menu>

            <div class="sidebar-footer drawer-footer">
              <div class="user-profile">
                <button class="user-identity" type="button" aria-label="打开用户中心" @click="router.push('/user'); simpleNavOpen = false">
                <el-avatar :size="28" class="user-avatar">{{ sidebarUserInitial }}</el-avatar>
                <div class="user-info">
                  <span class="user-name">{{ sidebarUserName }}</span>
                  <span class="user-status">{{ sidebarUserMeta }}</span>
                </div>
                </button>
                <button class="user-logout" type="button" aria-label="退出登录" title="退出登录" @click="simpleNavOpen = false; handleLogout()">
                  <el-icon><SwitchButton /></el-icon>
                </button>
              </div>
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
  ArrowDown, ArrowRight, ChatDotRound, ChatLineRound, Delete, EditPen, User, Search,
  Clock, Setting, SwitchButton, Connection,
  Monitor, Cpu, Box,
  Menu as MenuIcon, Fold, Expand
} from '@element-plus/icons-vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import AcgRunManager from '@/components/agentos/AcgRunManager.vue'
import { authApi } from '@/services/api/auth'
import { conversationApi, type Conversation } from '@/services/api/conversation'
import { useChatStore } from '@/stores/chat'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
const workflowRunsStore = useWorkflowRunsStore()
const userStore = useUserStore()
const globalError = ref('')
const simpleNavOpen = ref(false)
type WorkspaceMode = 'agent' | 'chat'
const WORKSPACE_MODE_KEY = 'layout.workspace_mode'
const workspaceMode = ref<WorkspaceMode>(localStorage.getItem(WORKSPACE_MODE_KEY) === 'agent' ? 'agent' : 'chat')
const CHAT_NAV_OPEN_KEY = 'layout.chat_nav_open'
const chatNavOpen = ref(route.path.startsWith('/chat') && localStorage.getItem(CHAT_NAV_OPEN_KEY) === '1')
const ACG_NAV_OPEN_KEY = 'layout.acg_nav_open'
const acgNavOpen = ref(route.path.startsWith('/agentos/acg') && localStorage.getItem(ACG_NAV_OPEN_KEY) !== '0')
const CHAT_PANEL_WIDTH_KEY = 'layout.chat_panel_width'
const CHAT_PANEL_DEFAULT_WIDTH = 300
const CHAT_PANEL_MIN_WIDTH = 220
const CHAT_PANEL_MAX_WIDTH = 420
const storedChatPanelWidth = Number(localStorage.getItem(CHAT_PANEL_WIDTH_KEY))
const chatPanelWidth = ref(
  Number.isFinite(storedChatPanelWidth) && storedChatPanelWidth >= CHAT_PANEL_MIN_WIDTH && storedChatPanelWidth <= CHAT_PANEL_MAX_WIDTH
    ? storedChatPanelWidth
    : CHAT_PANEL_DEFAULT_WIDTH
)
const chatPanelResizing = ref(false)
const recentConversations = ref<Conversation[]>([])
const conversationListLoading = ref(false)
const SIDEBAR_COLLAPSED_KEY = 'layout.sidebar_collapsed'
const SIDEBAR_WIDTH_KEY = 'layout.sidebar_width'
const SIDEBAR_DEFAULT_WIDTH = 248
const SIDEBAR_MIN_WIDTH = 220
const SIDEBAR_MAX_WIDTH = 360
const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1')
const storedSidebarWidth = Number(localStorage.getItem(SIDEBAR_WIDTH_KEY))
const sidebarWidth = ref(
  Number.isFinite(storedSidebarWidth) && storedSidebarWidth >= SIDEBAR_MIN_WIDTH && storedSidebarWidth <= SIDEBAR_MAX_WIDTH
    ? storedSidebarWidth
    : SIDEBAR_DEFAULT_WIDTH
)
const sidebarResizing = ref(false)
const secondaryNavOpen = computed(() => chatNavOpen.value || acgNavOpen.value)
const mainSidebarCompact = computed(() => sidebarCollapsed.value || secondaryNavOpen.value)
const sidebarAsideWidth = computed(() => `${secondaryNavOpen.value ? 60 + chatPanelWidth.value : (sidebarCollapsed.value ? 60 : sidebarWidth.value)}px`)
const primarySidebarWidth = computed(() => `${mainSidebarCompact.value ? 60 : sidebarWidth.value}px`)
let sidebarResizeStartX = 0
let sidebarResizeStartWidth = SIDEBAR_DEFAULT_WIDTH
let chatPanelResizeStartX = 0
let chatPanelResizeStartWidth = CHAT_PANEL_DEFAULT_WIDTH
const mobileMediaQuery = window.matchMedia('(max-width: 760px)')
const isMobileViewport = ref(mobileMediaQuery.matches)
const sidebarUserName = computed(() => {
  const username = userStore.currentUser?.username?.trim()
  if (username) return username
  const userId = localStorage.getItem('userId')?.trim()
  return userId ? `用户 ${userId.slice(-4)}` : '当前用户'
})
const sidebarUserMeta = computed(() => userStore.currentUser?.email?.trim() || '已登录')
const sidebarUserInitial = computed(() => sidebarUserName.value.charAt(0).toUpperCase())

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

const loadRecentConversations = async () => {
  if (conversationListLoading.value) return

  try {
    conversationListLoading.value = true
    const userId = localStorage.getItem('userId') || undefined
    const conversations = await conversationApi.getUserConversations(userId)
    recentConversations.value = [...conversations]
      .sort((a, b) => new Date(b.updatedAt || b.createdAt).getTime() - new Date(a.updatedAt || a.createdAt).getTime())
  } catch {
    recentConversations.value = []
  } finally {
    conversationListLoading.value = false
  }
}

const handleChatNavToggle = () => {
  if (acgNavOpen.value) closeAcgPanel()
  chatNavOpen.value = !chatNavOpen.value
  localStorage.setItem(CHAT_NAV_OPEN_KEY, chatNavOpen.value ? '1' : '0')
  if (chatNavOpen.value) void loadRecentConversations()
  if (!route.path.startsWith('/chat')) {
    void router.push({ path: '/chat', query: { workspace: workspaceMode.value } })
  }
}

const closeChatPanel = () => {
  chatNavOpen.value = false
  localStorage.setItem(CHAT_NAV_OPEN_KEY, '0')
}

const closeAcgPanel = () => {
  acgNavOpen.value = false
  localStorage.setItem(ACG_NAV_OPEN_KEY, '0')
}

const handleAcgNavToggle = () => {
  if (chatNavOpen.value) closeChatPanel()
  acgNavOpen.value = !acgNavOpen.value
  localStorage.setItem(ACG_NAV_OPEN_KEY, acgNavOpen.value ? '1' : '0')
  if (!route.path.startsWith('/agentos/acg')) {
    acgNavOpen.value = true
    localStorage.setItem(ACG_NAV_OPEN_KEY, '1')
    void router.push('/agentos/acg')
  }
}

const startNewAcg = async () => {
  await router.push('/agentos/acg')
  window.dispatchEvent(new Event('acg-new-task'))
}

const openAcgRun = async (runId: string) => {
  await router.push({ path: '/agentos/acg', query: { runId } })
}

const handleAcgRunDeleted = async (runId: string) => {
  if (route.query.runId !== runId) return
  await startNewAcg()
}

const openAcgOperations = async () => {
  await router.push({ path: '/agentos-console', query: { tab: 'runs', source: 'acg' } })
}

const startNewChat = async () => {
  chatStore.clearMessages()
  await router.push({ path: '/chat', query: { workspace: workspaceMode.value } })
}

const openConversation = async (conversation: Conversation) => {
  const contextId = conversation.contextId || conversation.id
  await router.push({ path: '/chat', query: { contextId, workspace: workspaceMode.value } })
}

const formatConversationTime = (value?: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  const now = new Date()
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const startOfDate = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime()
  const dayDifference = Math.round((startOfToday - startOfDate) / 86_400_000)

  if (dayDifference === 0) {
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }
  if (dayDifference === 1) return '昨天'
  if (date.getFullYear() === now.getFullYear()) {
    return date.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
  }
  return date.toLocaleDateString('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric' })
}

const deleteSidebarConversation = async (conversation: Conversation) => {
  try {
    await ElMessageBox.confirm(
      `确定删除对话“${conversation.title || '未命名对话'}”吗？此操作不可恢复。`,
      '删除聊天记录',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    await conversationApi.deleteConversation(conversation.id)
    recentConversations.value = recentConversations.value.filter(item => item.id !== conversation.id)

    const deletedContextId = conversation.contextId || conversation.id
    if (route.query.contextId === deletedContextId) {
      chatStore.clearMessages()
      await router.replace({ path: '/chat', query: { workspace: workspaceMode.value } })
    }

    window.dispatchEvent(new Event('history-refresh'))
    ElMessage.success('聊天记录已删除')
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error?.message || '删除聊天记录失败')
    }
  }
}

const handleHistoryRefresh = () => {
  if (chatNavOpen.value) void loadRecentConversations()
}

watch(
  () => route.path,
  path => {
    if (!path.startsWith('/chat') && chatNavOpen.value) closeChatPanel()
    if (path.startsWith('/agentos/acg')) {
      if (localStorage.getItem(ACG_NAV_OPEN_KEY) !== '0') acgNavOpen.value = true
    } else {
      acgNavOpen.value = false
    }
  }
)

watch(
  () => route.query.workspace,
  workspace => {
    if (workspace !== 'agent' && workspace !== 'chat') return
    workspaceMode.value = workspace
    localStorage.setItem(WORKSPACE_MODE_KEY, workspace)
  },
  { immediate: true }
)

const selectWorkspaceMode = (mode: WorkspaceMode) => {
  workspaceMode.value = mode
  localStorage.setItem(WORKSPACE_MODE_KEY, mode)
  window.dispatchEvent(new CustomEvent('workspace-mode-change', { detail: { mode } }))
  void router.replace({
    path: '/chat',
    query: { ...route.query, workspace: mode }
  })
}

// Immersive mode: only keep login page immersive
const isImmersive = computed(() => {
  const path = route.path
  return path.startsWith('/login')
})

const usesDrawerNavigation = computed(() => {
  return !isImmersive.value && isMobileViewport.value
})

const toggleSidebar = () => {
  if (secondaryNavOpen.value) {
    closeChatPanel()
    closeAcgPanel()
    return
  }
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed.value ? '1' : '0')
}

const clampSidebarWidth = (width: number) => {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(width)))
}

const persistSidebarWidth = () => {
  localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth.value))
}

const handleSidebarResizeMove = (event: PointerEvent) => {
  if (!sidebarResizing.value) return
  sidebarWidth.value = clampSidebarWidth(sidebarResizeStartWidth + event.clientX - sidebarResizeStartX)
}

const stopSidebarResize = () => {
  if (!sidebarResizing.value) return
  sidebarResizing.value = false
  persistSidebarWidth()
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleSidebarResizeMove)
  window.removeEventListener('pointerup', stopSidebarResize)
  window.removeEventListener('pointercancel', stopSidebarResize)
}

const startSidebarResize = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  sidebarResizeStartX = event.clientX
  sidebarResizeStartWidth = sidebarWidth.value
  sidebarResizing.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleSidebarResizeMove)
  window.addEventListener('pointerup', stopSidebarResize)
  window.addEventListener('pointercancel', stopSidebarResize)
}

const resetSidebarWidth = () => {
  sidebarWidth.value = SIDEBAR_DEFAULT_WIDTH
  persistSidebarWidth()
}

const handleSidebarResizeKeydown = (event: KeyboardEvent) => {
  const increments: Record<string, number> = {
    ArrowLeft: -8,
    ArrowRight: 8
  }

  if (event.key === 'Home') {
    sidebarWidth.value = SIDEBAR_MIN_WIDTH
  } else if (event.key === 'End') {
    sidebarWidth.value = SIDEBAR_MAX_WIDTH
  } else if (increments[event.key]) {
    sidebarWidth.value = clampSidebarWidth(sidebarWidth.value + increments[event.key])
  } else {
    return
  }

  event.preventDefault()
  persistSidebarWidth()
}

const clampChatPanelWidth = (width: number) => {
  return Math.min(CHAT_PANEL_MAX_WIDTH, Math.max(CHAT_PANEL_MIN_WIDTH, Math.round(width)))
}

const persistChatPanelWidth = () => {
  localStorage.setItem(CHAT_PANEL_WIDTH_KEY, String(chatPanelWidth.value))
}

const handleChatPanelResizeMove = (event: PointerEvent) => {
  if (!chatPanelResizing.value) return
  chatPanelWidth.value = clampChatPanelWidth(chatPanelResizeStartWidth + event.clientX - chatPanelResizeStartX)
}

const stopChatPanelResize = () => {
  if (!chatPanelResizing.value) return
  chatPanelResizing.value = false
  persistChatPanelWidth()
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleChatPanelResizeMove)
  window.removeEventListener('pointerup', stopChatPanelResize)
  window.removeEventListener('pointercancel', stopChatPanelResize)
}

const startChatPanelResize = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  chatPanelResizeStartX = event.clientX
  chatPanelResizeStartWidth = chatPanelWidth.value
  chatPanelResizing.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleChatPanelResizeMove)
  window.addEventListener('pointerup', stopChatPanelResize)
  window.addEventListener('pointercancel', stopChatPanelResize)
}

const resetChatPanelWidth = () => {
  chatPanelWidth.value = CHAT_PANEL_DEFAULT_WIDTH
  persistChatPanelWidth()
}

const handleChatPanelResizeKeydown = (event: KeyboardEvent) => {
  const step = event.shiftKey ? 24 : 8

  if (event.key === 'Home') {
    chatPanelWidth.value = CHAT_PANEL_MIN_WIDTH
  } else if (event.key === 'End') {
    chatPanelWidth.value = CHAT_PANEL_MAX_WIDTH
  } else if (event.key === 'ArrowLeft') {
    chatPanelWidth.value = clampChatPanelWidth(chatPanelWidth.value - step)
  } else if (event.key === 'ArrowRight') {
    chatPanelWidth.value = clampChatPanelWidth(chatPanelWidth.value + step)
  } else {
    return
  }

  event.preventDefault()
  persistChatPanelWidth()
}

const handleViewportChange = (event: MediaQueryListEvent) => {
  isMobileViewport.value = event.matches
  if (!event.matches) simpleNavOpen.value = false
}

const isRouteScrollable = computed(() => {
  const path = route.path
  return (
    path.startsWith('/federated-learning') ||
    path.startsWith('/federated-models') ||
    path.startsWith('/agentos-console') ||
    path.startsWith('/agentos/acg') ||
    path.startsWith('/rag') ||
    path.startsWith('/voice-chat')
  )
})

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/chat' || path.startsWith('/chat')) return '/chat'
  if (path.startsWith('/agentos-console')) return '/agentos-console'
  if (path.startsWith('/agentos/acg')) return '/agentos/acg'
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
      userStore.setCurrentUser(null)
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
  window.addEventListener('history-refresh', handleHistoryRefresh)
  mobileMediaQuery.addEventListener('change', handleViewportChange)
  if (chatNavOpen.value) void loadRecentConversations()
  if (localStorage.getItem('userId')) void userStore.loadCurrentUser()
  void workflowRunsStore.bootstrap()
})

onUnmounted(() => {
  stopSidebarResize()
  stopChatPanelResize()
  window.removeEventListener('global-error', handleGlobalError as EventListener)
  window.removeEventListener('history-refresh', handleHistoryRefresh)
  mobileMediaQuery.removeEventListener('change', handleViewportChange)
})
</script>

<style scoped>
.app-layout {
  height: 100%;
  width: 100%;
  background: var(--app-layout-bg);
  overflow: hidden;
  display: flex;
}

/* Sidebar Styles */
.app-sidebar {
  position: relative;
  background-color: transparent;
  border-right: 1px solid var(--border-light);
  backdrop-filter: blur(18px);
  display: flex;
  flex-direction: row;
  overflow: hidden;
  transition: width 0.22s var(--ease-out);
}

.primary-sidebar {
  --sidebar-icon-axis: 30px;
  --sidebar-item-icon-inset: 13px;
  --sidebar-collapsed-menu-icon-offset: 6px;
  position: relative;
  z-index: 2;
  flex: 0 0 auto;
  height: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--sidebar-bg);
  transition: width 0.22s var(--ease-out);
}

.app-sidebar.chat-panel-open .primary-sidebar {
  border-right: 1px solid var(--sidebar-border);
}

.app-sidebar.resizing {
  transition: none;
}

.app-sidebar.resizing .primary-sidebar {
  transition: none;
}

.sidebar-resizer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 12;
  width: 8px;
  cursor: col-resize;
  touch-action: none;
  outline: none;
}

.sidebar-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 2px;
  background: var(--primary-color);
  opacity: 0;
  transform: scaleY(0.96);
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.sidebar-resizer:hover::after,
.sidebar-resizer:focus-visible::after,
.app-sidebar.resizing .sidebar-resizer::after {
  opacity: 0.8;
  transform: scaleY(1);
}

.sidebar-header {
  flex-shrink: 0;
  height: 54px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 10px;
  gap: 6px;
  border-bottom: 1px solid var(--sidebar-border);
}

.sidebar-brand,
.sidebar-collapse-btn {
  display: inline-flex;
  align-items: center;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.sidebar-brand {
  min-width: 0;
  gap: 10px;
  padding: 0;
}

.sidebar-collapse-btn {
  flex: 0 0 auto;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 9px;
  color: var(--text-secondary);
  font-size: 17px;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.sidebar-collapse-btn:hover {
  background: var(--primary-fade);
  color: var(--primary-color);
}

.sidebar-brand:focus-visible,
.sidebar-collapse-btn:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.app-sidebar.collapsed .sidebar-header {
  justify-content: center;
  padding: 0;
}

.app-sidebar.collapsed .sidebar-brand {
  display: none;
}

.logo-icon {
  width: 34px;
  height: 34px;
  background: var(--primary-fade);
  border: none;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--primary-color);
  font-weight: bold;
  font-size: 18px;
  overflow: hidden;
}

.logo-icon img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
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
  min-height: 0;
  padding: 0 8px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

.app-sidebar.collapsed .sidebar-nav {
  padding: 18px 6px 10px;
}

.workspace-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 3px;
  margin: 0 4px 8px;
  padding: 3px;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  background: var(--bg-input);
}

.workspace-switch-btn {
  width: 100%;
  height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 9px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.workspace-switch-btn:hover {
  color: var(--text-primary);
}

.workspace-switch-btn.active {
  background: var(--bg-card);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.workspace-switch-btn:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: -2px;
}

.workspace-switch-btn .el-icon {
  font-size: 12px;
}

.chat-side-panel {
  position: relative;
  z-index: 1;
  flex: 0 0 auto;
  min-width: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--sidebar-bg);
  box-shadow: 10px 0 24px rgba(16, 18, 33, 0.04);
}

.chat-panel-resizer {
  position: absolute;
  z-index: 4;
  top: 0;
  right: -3px;
  bottom: 0;
  width: 7px;
  cursor: col-resize;
  touch-action: none;
  outline: none;
}

.chat-panel-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  right: 3px;
  bottom: 0;
  width: 1px;
  background: transparent;
  transition: background-color 0.16s ease, box-shadow 0.16s ease;
}

.chat-panel-resizer:hover::after,
.chat-panel-resizer:focus-visible::after,
.app-sidebar.resizing .chat-panel-resizer::after {
  background: var(--primary-color);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 18%, transparent);
}

.chat-panel-content {
  min-width: 160px;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 8px 10px;
  overflow: hidden;
}

.chat-panel-enter-active {
  transition: opacity 0.18s ease 0.04s, transform 0.22s var(--ease-out);
}

.chat-panel-leave-active {
  transition: opacity 0.14s ease, transform 0.18s ease;
}

.chat-panel-enter-from,
.chat-panel-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}

.chat-panel-enter-to,
.chat-panel-leave-from {
  opacity: 1;
  transform: translateX(0);
}

/* Sidebar menu scrolling */
.sidebar-nav::-webkit-scrollbar {
  width: 4px;
}

.sidebar-nav::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-nav::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 999px;
}

.sidebar-nav::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover);
}

.menu-group-title {
  box-sizing: border-box;
  height: 33px;
  padding: 14px 16px 6px;
  font-size: 11px;
  font-weight: 500;
  color: var(--text-disabled);
  letter-spacing: 0;
  text-transform: none;
}

.sidebar-menu {
  --el-menu-item-font-size: 13px;
  border: none;
  background: transparent;
}

.sidebar-menu.el-menu--collapse {
  width: 100%;
}

.chat-nav-group {
  position: relative;
  margin-bottom: 2px;
}

.chat-nav-trigger,
.chat-submenu-action,
.chat-project-item {
  width: 100%;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.chat-nav-trigger {
  position: relative;
  height: 44px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 var(--sidebar-item-icon-inset);
  border: 1px solid transparent;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 450;
  letter-spacing: -0.01em;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

.chat-nav-trigger > .el-icon:first-child {
  flex: 0 0 auto;
  font-size: 18px;
}

.acg-nav-logo {
  width: 35px;
  height: 35px;
  flex: 0 0 35px;
  display: block;
  border-radius: 4px;
  object-fit: cover;
}

.chat-nav-label {
  min-width: 0;
  flex: 1;
}

.chat-nav-chevron {
  flex: 0 0 auto;
  margin-left: auto;
  font-size: 13px;
  color: var(--text-disabled);
}

.chat-nav-trigger:hover {
  border-color: var(--border-light);
  background: color-mix(in srgb, var(--surface-solid) 72%, transparent);
  color: var(--text-primary);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-solid) 82%, transparent);
}

.chat-nav-group.active > .chat-nav-trigger {
  border-color: var(--primary-line);
  background: color-mix(in srgb, var(--primary-fade) 74%, var(--surface-solid));
  color: var(--primary-color);
  font-weight: 550;
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-solid) 76%, transparent), var(--shadow-sm);
}

.chat-nav-group.active > .chat-nav-trigger::before {
  content: none;
}

.chat-nav-trigger:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.app-sidebar.collapsed .chat-nav-trigger {
  justify-content: center;
  padding: 0;
}

.chat-submenu-action,
.chat-project-item {
  min-height: 32px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 9px;
  border-radius: 7px;
  font-size: 12px;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.chat-submenu-action:hover,
.chat-project-item:hover,
.chat-project-item.active {
  background: var(--bg-panel);
  color: var(--text-primary);
}

.chat-nav-trigger:focus-visible,
.chat-submenu-action:focus-visible,
.chat-project-item:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: -2px;
}

.new-chat-action {
  min-height: 38px;
  margin-bottom: 8px;
  padding: 0 10px 0 calc(var(--sidebar-icon-axis) - 17px);
  border: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--bg-card) 84%, transparent);
  color: var(--text-primary);
  font-weight: 650;
  box-shadow: var(--shadow-sm);
}

.new-chat-action:hover {
  border-color: var(--primary-line);
  background: var(--bg-card);
  color: var(--primary-color);
}

.chat-submenu-section-head {
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 5px 8px 6px;
  color: var(--text-disabled);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.035em;
}

.chat-project-count {
  min-width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 10px;
}

.chat-submenu-action .el-icon {
  flex: 0 0 auto;
  font-size: 13px;
}

.chat-project-list {
  min-height: 0;
  flex: 1 1 auto;
  display: grid;
  align-content: start;
  gap: 6px;
  padding: 2px 2px 8px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--scrollbar-thumb) transparent;
}

.chat-project-list::-webkit-scrollbar {
  width: 4px;
}

.chat-project-list::-webkit-scrollbar-track {
  background: transparent;
}

.chat-project-list::-webkit-scrollbar-thumb {
  border-radius: 999px;
  background: var(--scrollbar-thumb);
}

.chat-project-row {
  min-height: 50px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 32px;
  align-items: stretch;
  gap: 2px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 72%, transparent);
  color: var(--text-muted);
  overflow: hidden;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.chat-project-item {
  min-width: 0;
  min-height: 48px;
  gap: 9px;
  padding: 7px 5px 7px 8px;
  border-radius: 7px 0 0 7px;
  color: inherit;
  font-size: 12px;
  font-weight: 450;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.chat-project-row:hover {
  border-color: var(--primary-line);
  background: var(--bg-card);
  color: var(--text-primary);
}

.chat-project-item:hover {
  background: transparent;
  color: inherit;
}

.chat-project-icon {
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  display: inline-grid;
  place-items: center;
  border-radius: 6px;
  background: var(--bg-panel);
  color: var(--text-secondary);
}

.chat-project-icon .el-icon {
  font-size: 14px;
}

.chat-project-copy {
  min-width: 0;
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.chat-project-title,
.chat-project-time {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-project-title {
  color: inherit;
  line-height: 1.25;
}

.chat-project-time {
  color: var(--text-disabled);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.chat-project-arrow {
  flex: 0 0 auto;
  color: var(--text-disabled);
  font-size: 12px;
  transition: color 0.16s ease, transform 0.16s ease;
}

.chat-project-item:hover .chat-project-arrow,
.chat-project-row.active .chat-project-arrow {
  color: var(--primary-color);
  transform: translateX(1px);
}

.chat-project-row.active {
  border-color: var(--primary-line);
  color: var(--primary-color);
  background: var(--primary-fade);
  font-weight: 650;
}

.chat-project-row.active .chat-project-icon {
  background: color-mix(in srgb, var(--primary-color) 14%, var(--bg-card));
  color: var(--primary-color);
}

.chat-project-delete {
  width: 32px;
  min-height: 48px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-left: 1px solid transparent;
  background: transparent;
  color: var(--text-disabled);
  cursor: pointer;
  opacity: 0.55;
  transition: opacity 0.16s ease, color 0.16s ease, background-color 0.16s ease, border-color 0.16s ease;
}

.chat-project-delete .el-icon {
  font-size: 14px;
}

.chat-project-row:hover .chat-project-delete,
.chat-project-delete:focus-visible {
  border-left-color: var(--border-light);
  opacity: 1;
}

.chat-project-delete:hover,
.chat-project-delete:focus-visible {
  background: color-mix(in srgb, var(--danger) 9%, transparent);
  color: var(--danger);
  outline: none;
}

.chat-submenu-loading,
.chat-submenu-empty {
  flex: 1 1 auto;
  padding: 8px 9px;
  color: var(--text-disabled);
  font-size: 11px;
}

.history-action {
  box-sizing: border-box;
  height: 38px;
  min-height: 38px;
  flex: 0 0 38px;
  gap: 7px;
  margin-top: 5px;
  padding: 0 8px;
  border: 1px solid var(--primary-line);
  border-radius: 7px;
  background: color-mix(in srgb, var(--primary-fade) 72%, var(--bg-card));
  color: var(--primary-color);
}

.history-action:hover {
  border-color: var(--primary-color);
  background: color-mix(in srgb, var(--primary-fade) 88%, var(--bg-card));
  color: var(--primary-color);
}

.history-action__icon {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  display: inline-grid;
  place-items: center;
  border-radius: 5px;
  background: var(--bg-card);
}

.history-action__copy {
  min-width: 0;
  flex: 1 1 0;
  display: block;
}

.history-action__copy strong,
.history-action__copy small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-action__copy strong {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 700;
  line-height: 1.2;
}

.history-action__copy small {
  display: none;
}

.history-action__arrow {
  flex: 0 0 auto;
  color: var(--primary-color);
  font-size: 13px;
  transition: transform 0.16s ease;
}

.history-action:hover .history-action__arrow {
  transform: translateX(2px);
}

.app-sidebar.collapsed .sidebar-menu :deep(.el-menu-item) {
  display: flex !important;
  justify-content: center;
  align-items: center;
  height: 44px;
  padding: 0 !important;
}

.app-sidebar.collapsed .sidebar-menu :deep(.el-menu-item .el-icon) {
  display: inline-flex !important;
  align-items: center;
  justify-content: center;
  margin: 0 !important;
  font-size: 18px;
  transform: translateX(var(--sidebar-collapsed-menu-icon-offset));
}

/* Apple 风格选中态：单层半透明表面，不叠加独立指示条 */
.sidebar-menu :deep(.el-menu-item) {
  height: 44px;
  margin: 0 0 2px;
  padding: 0 var(--sidebar-item-icon-inset) !important;
  gap: 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text-secondary);
  font-size: 14px;
  font-weight: 450;
  letter-spacing: -0.01em;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, box-shadow 160ms ease;
  position: relative;
}

.sidebar-menu :deep(.el-menu-item .el-icon) {
  flex: 0 0 18px;
  width: 18px;
  margin-right: 0;
  font-size: 18px;
}

.sidebar-menu :deep(.el-menu-item > span) {
  font-size: 13px !important;
  line-height: 1.35;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  border-color: var(--border-light);
  background: color-mix(in srgb, var(--surface-solid) 72%, transparent);
  color: var(--text-primary);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-solid) 82%, transparent);
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  border-color: var(--primary-line);
  background: color-mix(in srgb, var(--primary-fade) 74%, var(--surface-solid));
  color: var(--primary-color);
  font-weight: 550;
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-solid) 76%, transparent), var(--shadow-sm);
}

.sidebar-menu :deep(.el-menu-item.is-active::before) {
  content: none;
}

.sidebar-menu :deep(.el-menu-item:focus-visible) {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
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
  flex-shrink: 0;
  padding: 10px 12px;
  margin-top: auto;
  border-top: 1px solid var(--sidebar-border);
}

.app-sidebar.collapsed .sidebar-footer {
  padding: 8px 6px;
}

.app-sidebar.collapsed .user-profile {
  justify-content: center;
  padding: 4px 0;
}

@media (prefers-reduced-motion: reduce) {
  .app-sidebar,
  .primary-sidebar,
  .chat-side-panel {
    transition-duration: 0.01ms !important;
  }
}

.user-profile {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-width: 0;
  padding: 4px;
}

.user-identity,
.user-logout {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.user-identity {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 2px;
  text-align: left;
}

.user-avatar {
  background-color: var(--primary-color);
  color: white;
  font-size: 13px;
  font-weight: 650;
}

.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.user-name {
  font-size: 12px;
  font-weight: 650;
  color: var(--text-primary);
  line-height: 1.2;
}

.user-status {
  font-size: 10px;
  color: var(--success);
  line-height: 1.2;
}

.user-logout {
  width: 28px;
  height: 28px;
  flex: 0 0 28px;
  display: grid;
  place-items: center;
  border-radius: 7px;
  color: var(--text-secondary);
  transition: color 160ms ease, background-color 160ms ease;
}

.user-identity:hover .user-name,
.user-logout:hover {
  color: var(--danger);
}

.user-logout:hover { background: var(--danger-fade); }

.user-identity:focus-visible,
.user-logout:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.simple-nav-toggle {
  position: fixed;
  top: 9px;
  left: 12px;
  z-index: 2100;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 36px;
  padding: 0;
  border: 1px solid var(--primary-line);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  color: var(--primary-color);
  font: inherit;
  font-size: 15px;
  font-weight: 650;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(24, 39, 35, 0.08);
  backdrop-filter: blur(14px);
  transition: border-color 0.18s ease, background-color 0.18s ease, transform 0.18s ease;
}

.simple-nav-toggle:hover {
  border-color: var(--border-focus);
  background: var(--surface-solid);
  transform: translateY(-1px);
}

.simple-nav-toggle:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.simple-nav-drawer :deep(.el-drawer__body),
:global(.simple-nav-drawer .el-drawer__body) {
  padding: 0;
  background: var(--drawer-bg);
}

.drawer-sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--app-layout-bg);
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
  background: var(--scrollbar-thumb);
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
  flex: 1;
  min-width: 0;
  background-color: transparent;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-main {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: hidden;
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
    top: 9px;
    left: 10px;
    width: 34px;
  }
}
</style>
