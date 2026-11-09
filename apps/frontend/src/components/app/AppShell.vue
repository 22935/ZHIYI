<!-- 工作区布局 — 侧边栏导航、沉浸/简洁模式和工作区事件 -->
<template>
  <el-container class="app-layout" :class="{ 'immersive-mode': isImmersive }">
        <AppTopBar
          v-if="showNavigation"
          @navigate="handleTopChromeNavigate"
        />

        <el-container class="app-shell-body" :class="{ 'docked-workspace-shell': isDockedWorkspaceRoute, 'is-chat-route': isChatRoute, 'has-dock-status': hasDockStatus }">
          <!-- Sidebar Navigation -->
          <el-aside
            v-if="showNavigation"
            :width="sidebarAsideWidth"
            class="app-sidebar collapsed"
            :class="{ 'chat-panel-open': secondaryNavOpen, resizing: chatPanelResizing }"
          >
          <div class="primary-sidebar">
          <!-- Main Navigation -->
          <div class="sidebar-nav" ref="sidebarNav">
            <el-menu
              :default-active="activeMenu"
              router
              class="sidebar-menu"
              collapse
              :collapse-transition="false"
              @wheel="handleSidebarWheel"
            >
              <div
                class="chat-nav-group"
                :class="{ active: route.path.startsWith('/chat'), open: chatNavOpen }"
              >
                <button
                  class="chat-nav-trigger"
                  type="button"
                  :aria-expanded="chatNavOpen"
                  aria-controls="chat-side-panel"
                  title="OScode"
                  aria-label="OScode"
                  @click="handleChatNavToggle"
                >
                  <el-icon><ChatDotRound /></el-icon>
                </button>

              </div>
              <div
                class="chat-nav-group acg-nav-group"
                :class="{ active: isAcgRoute, open: acgNavOpen }"
              >
                <button
                  class="chat-nav-trigger"
                  type="button"
                  :aria-current="isAcgRoute ? 'page' : undefined"
                  title="Workbench"
                  aria-label="Workbench"
                  @click="handleAcgNavToggle"
                >
                  <img class="acg-nav-logo" src="/acglogo.webp" alt="" aria-hidden="true" />
                </button>
              </div>
              <div v-if="isMissionWorkspacePath(route.path)" class="workbench-activity-views" role="group" aria-label="Workbench 左侧视图">
                <button v-for="(item, activityIndex) in workbenchActivities" :key="item.id" class="chat-nav-trigger workbench-activity-button"
                  type="button" :class="{
                    'is-selected': activeWorkbenchSidebar === item.id,
                    'is-dragging': draggingActivity === activityIndex
                  }"
                  :title="item.label" :aria-label="item.label" :aria-pressed="activeWorkbenchSidebar === item.id"
                  v-bind="activityDrag.itemProps(activityIndex)"
                  @click="selectWorkbenchSidebar(item.id)">
                  <el-icon><component :is="item.icon" /></el-icon>
                </button>
              </div>
            </el-menu>
          </div>

          <!-- User Profile / Bottom Section -->
          <div class="sidebar-footer">
            <div class="user-profile">
              <button
                class="user-identity"
                type="button"
                aria-haspopup="menu"
                :aria-expanded="accountMenuOpen"
                aria-controls="sidebar-account-menu"
                aria-label="打开账户目录"
                title="账户目录"
                @click="toggleAccountMenu"
                @keydown.esc="closeAccountMenu"
              >
              <UserAvatar :size="28" class="user-avatar" :fallback="sidebarUserInitial" />
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
                <WorkspaceModeSwitch active="oscode" :pending="surfaceSwitching" @select="switchWorkspaceSurface" />

                <div class="chat-submenu-section-head">
                    <span class="chat-submenu-section-title">对话记录</span>
                  <div class="chat-submenu-section-tools">
                    <span v-if="workspaceHistoryCount" class="chat-project-count" :aria-label="`${workspaceHistoryCount} 条对话`">
                      {{ workspaceHistoryCount }}
                    </span>
                  </div>
                  <span v-if="conversationListLoading && workspaceHistoryCount" class="chat-submenu-refreshing">更新中</span>
                  <button class="chat-submenu-action new-chat-action" type="button" @click="startNewChat">
                    <el-icon><EditPen /></el-icon>
                    <span>新建对话</span>
                  </button>
                </div>

                <div v-if="conversationListLoading && !workspaceHistoryCount" class="chat-submenu-loading">正在加载…</div>
                <div v-else-if="visibleRecentConversations.length" class="chat-project-list" role="list" aria-label="对话记录">
                  <div
                    v-for="conversation in visibleRecentConversations"
                    :key="conversation.id"
                    class="chat-project-row chat-project-row--chat"
                    :class="{ active: route.query.contextId === (conversation.contextId || conversation.id) }"
                    role="listitem"
                    @contextmenu.prevent.stop="openSidebarActionMenu($event, { conversation })"
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
                    </button>
                    <div class="chat-project-actions" aria-label="对话操作">
                      <button class="chat-project-action chat-project-action--edit" type="button" title="编辑标题" @click.stop="editSidebarConversation(conversation)">
                        <el-icon><Edit /></el-icon>
                      </button>
                      <button class="chat-project-action chat-project-action--delete" type="button" title="删除对话" @click.stop="deleteSidebarActionConversation(conversation)">
                        <el-icon><Delete /></el-icon>
                      </button>
                    </div>
                  </div>
                </div>
                <div v-else class="chat-submenu-empty">
                  暂无历史对话
                </div>

                <button class="chat-submenu-action history-action" type="button" @click="openWorkspaceHistory">
                  <span class="history-action__icon" aria-hidden="true">
                    <el-icon><Clock /></el-icon>
                  </span>
                  <span class="history-action__copy">
                    <strong>查找所有聊天记录</strong>
                    <small>搜索、编辑与管理</small>
                  </span>
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
          </el-aside>

          <!-- Main Content Area -->
          <el-container class="main-container">
            <DesktopRuntimeStatus />
            <el-main class="app-main" :class="{ 'route-scrollable': isRouteScrollable }">
              <Suspense>
                <template #default>
                  <router-view v-slot="{ Component, route: viewRoute }">
                    <WorkspaceViewHost v-if="Component" :view="Component" :view-route="viewRoute" />
                  </router-view>
                </template>
                <template #fallback>
                  <div class="route-loading" role="status" aria-live="polite">
                    <BrandLoader :size="52" title="页面加载中…" />
                  </div>
                </template>
              </Suspense>
            </el-main>
            <DesktopTerminalDock v-if="isDesktop()" />
          </el-container>
        </el-container>
      </el-container>
    <KeyboardShortcutsDialog v-model="shortcutsDialogVisible" />
    <Teleport to="body">
      <section
        v-if="accountMenuOpen"
        id="sidebar-account-menu"
        ref="accountMenuElement"
        class="sidebar-account-menu"
        role="menu"
        aria-label="账户目录"
        :style="accountMenuStyle"
        @keydown.esc="closeAccountMenu"
      >
        <div class="sidebar-account-menu__identity">
          <UserAvatar :size="34" class="sidebar-account-menu__avatar" :fallback="sidebarUserInitial" />
          <div class="sidebar-account-menu__user-copy">
            <strong>{{ sidebarUserName }}</strong>
            <span>{{ userStore.currentUser?.email || '知弈账户' }}</span>
          </div>
        </div>
        <div class="sidebar-account-menu__divider" role="separator"></div>
        <button type="button" role="menuitem" @click="openUserProfile">
          <el-icon aria-hidden="true"><User /></el-icon><span>个人资料</span>
        </button>
        <button type="button" role="menuitem" @click="openSettings">
          <el-icon aria-hidden="true"><Setting /></el-icon><span>设置</span>
        </button>
        <div class="sidebar-account-menu__divider" role="separator"></div>
        <button type="button" role="menuitem" @click="handleLogout">
          <el-icon aria-hidden="true"><SwitchButton /></el-icon><span>退出登录</span>
        </button>
      </section>
    </Teleport>
    <Teleport to="body">
      <div
        v-if="sidebarActionMenu.target"
        ref="sidebarActionMenuElement"
        id="sidebar-action-menu"
        class="sidebar-action-menu"
        role="menu"
        aria-label="对话项目操作"
        :style="{ left: `${sidebarActionMenu.x}px`, top: `${sidebarActionMenu.y}px` }"
        @keydown.esc="closeSidebarActionMenu"
      >
        <button type="button" role="menuitem" @click="() => editSidebarConversation()">
          <el-icon><Edit /></el-icon><span>编辑标题</span>
        </button>
        <button type="button" role="menuitem" class="is-danger" @click="() => deleteSidebarActionConversation()">
          <el-icon><Delete /></el-icon><span>删除对话</span>
        </button>
      </div>
    </Teleport>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onBeforeUnmount, onMounted, onUnmounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatDotRound, ChatLineRound, Delete, Edit, EditPen,
  Clock, Setting, SwitchButton, User,
  Monitor
} from '@element-plus/icons-vue'
import WorkspaceModeSwitch from '@/components/workspace/WorkspaceModeSwitch.vue'
import { workspaceShellKey, type WorkspaceSurface, type WorkbenchSidebar } from '@/features/workspace/shell'
import { useDragReorder } from '@/composables/useDragReorder'
import {
  applyWorkbenchActivityOrder,
  readWorkbenchActivityOrder,
  writeWorkbenchActivityOrder
} from './workbenchActivityOrder'
import { FolderOpened, Search, Share, Connection } from '@element-plus/icons-vue'
import AppTopBar from '@/components/app/AppTopBar.vue'
import DesktopRuntimeStatus from '@/components/platform/DesktopRuntimeStatus.vue'
const DesktopTerminalDock = defineAsyncComponent(() => import('@/components/terminal/DesktopTerminalDock.vue'))
import BrandLoader from '@/components/common/BrandLoader.vue'
import { conversationApi, type Conversation } from '@/services/api/conversation'
import { agentosApi } from '@/services/api/agentos'
import { useChatStore } from '@/stores/chat'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { useUserStore } from '@/stores/user'
import { AUTH_ROUTE, logout } from '@/features/auth/authService'
import UserAvatar from '@/components/UserAvatar.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getConversationWorkspace,
  removeConversationWorkspace
} from '@/utils/conversationWorkspace'
import { isDesktop } from '@/platform'
import { DOCK_LEFT_DEFAULT, useDockedWorkspaceGeometry } from '@/composables/useDockedWorkspaceGeometry'
import KeyboardShortcutsDialog from '@/components/app/KeyboardShortcutsDialog.vue'
import WorkspaceViewHost from '@/components/app/WorkspaceViewHost.vue'
import { conversationBindingKey, conversationWorkbenchTarget, isConversationForWorkbench, workbenchConversationTarget } from '@/features/workspace/navigation'
import { conversationBindings } from '@/features/workspace/session'
import { initAppKeyboardShortcuts } from '@/composables/useAppKeyboardShortcuts'

const route = useRoute()
const router = useRouter()
const chatStore = useChatStore()
provide(conversationBindingKey, (contextId, missionId, runId) =>
  isConversationForWorkbench(chatStore.workflowBindings, contextId, missionId, runId))
const workflowRunsStore = useWorkflowRunsStore()
const userStore = useUserStore()
const accountMenuOpen = ref(false)
const accountMenuElement = ref<HTMLElement | null>(null)
const accountMenuStyle = ref<Record<string, string>>({})
const shortcutsDialogVisible = ref(false)
let disposeAppKeyboardShortcuts: (() => void) | null = null
type WorkspaceMode = 'agent' | 'chat'
const workspaceMode = computed<WorkspaceMode>(() => isAcgPath(route.path) ? 'agent' : 'chat')
// 对话子栏只在 OScode（/chat）存在：ACG 工程页只有中心列表，子栏不再于该页弹出。
const CHAT_NAV_OPEN_KEY = 'layout.chat_nav_open'
const chatNavOpen = ref(route.path.startsWith('/chat') && localStorage.getItem(CHAT_NAV_OPEN_KEY) === '1')
const ACG_NAV_OPEN_KEY = 'layout.acg_nav_open'
const isMissionWorkspacePath = (path: string) => path.startsWith('/agentos/missions/') && path.endsWith('/workspace')
const isDockedWorkspaceRoute = computed(() => route.path.startsWith('/chat') || isMissionWorkspacePath(route.path))
const isChatRoute = computed(() => route.path.startsWith('/chat'))
const hasDockStatus = computed(() => isMissionWorkspacePath(route.path) || (route.path.startsWith('/chat') && workspaceMode.value === 'chat'))
const lastMissionWorkspacePath = ref(isMissionWorkspacePath(route.path) ? route.fullPath : '')
const lastChatRoute = ref(route.path.startsWith('/chat') ? route.fullPath : '/chat?workspace=chat')
const isAcgPath = (path: string) => path.startsWith('/agentos/acg') || isMissionWorkspacePath(path)
const acgNavOpen = ref(isAcgPath(route.path) && localStorage.getItem(ACG_NAV_OPEN_KEY) !== '0')
const CHAT_PANEL_WIDTH_KEY = 'layout.chat_panel_width'
const CHAT_PANEL_DEFAULT_WIDTH = DOCK_LEFT_DEFAULT
const CHAT_PANEL_MIN_WIDTH = 240
const CHAT_PANEL_MAX_WIDTH = 520
const dockGeometry = useDockedWorkspaceGeometry()
const chatPanelWidth = dockGeometry.leftWidth
const chatPanelResizing = ref(false)
const recentConversations = ref<Conversation[]>([])
type SidebarActionTarget = { conversation: Conversation }
const sidebarActionMenu = reactive<{ target: SidebarActionTarget | null; x: number; y: number }>({ target: null, x: 0, y: 0 })
const sidebarActionMenuElement = ref<HTMLElement | null>(null)
let conversationLoadGeneration = 0
let conversationLoadController: AbortController | null = null
let conversationLoadPromise: Promise<void> | null = null
let conversationLoadWorkspace: WorkspaceMode | null = null
const conversationWorkspaceVersion = ref(0)
const agentConversationIds = computed(() => new Set(
  Object.entries(chatStore.workflowBindings)
    .filter(([, bindings]) => bindings.some(binding => !binding.invalidAt))
    .map(([conversationId]) => conversationId)
))
const visibleRecentConversations = computed(() => {
  // Make local workspace index updates reactive without duplicating it in App state.
  void conversationWorkspaceVersion.value
  return recentConversations.value.filter(conversation => {
    const contextId = conversation.contextId || conversation.id
    const resolvedMode = conversation.workspaceMode
      || getConversationWorkspace(contextId, agentConversationIds.value)
    return resolvedMode === workspaceMode.value
  })
})
const workspaceHistoryCount = computed(() => visibleRecentConversations.value.length)
const conversationListLoading = ref(false)
const isAcgRoute = computed(() => isAcgPath(route.path))
const secondaryNavOpen = computed(() => chatNavOpen.value)
// 侧边栏固定为图标窄栏：展开宽栏与移动端抽屉已退役，唯一可变宽度是对话子栏。
const COLLAPSED_SIDEBAR_WIDTH = 48
const sidebarAsideWidth = computed(() => `${secondaryNavOpen.value ? COLLAPSED_SIDEBAR_WIDTH + chatPanelWidth.value : COLLAPSED_SIDEBAR_WIDTH}px`)
let chatPanelResizeStartX = 0
let chatPanelResizeStartWidth = CHAT_PANEL_DEFAULT_WIDTH
const sidebarUserName = computed(() => {
  const username = userStore.currentUser?.username?.trim()
  if (username) return username
  const userId = localStorage.getItem('userId')?.trim()
  return userId ? `用户 ${userId.slice(-4)}` : '当前用户'
})
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

const loadRecentConversations = (): Promise<void> => {
  const requestedWorkspace = workspaceMode.value
  if (conversationLoadPromise && conversationLoadWorkspace === requestedWorkspace) {
    return conversationLoadPromise
  }

  conversationLoadController?.abort()
  const controller = new AbortController()
  conversationLoadController = controller
  conversationLoadWorkspace = requestedWorkspace
  const requestGeneration = ++conversationLoadGeneration
  conversationListLoading.value = true

  const pending = (async () => {
    try {
      const userId = localStorage.getItem('userId') || undefined
      const conversations = await conversationApi.getUserConversations(userId, 'chat', { signal: controller.signal })
      if (requestGeneration !== conversationLoadGeneration || requestedWorkspace !== workspaceMode.value) return
      recentConversations.value = [...conversations]
        .sort((a, b) => new Date(b.updatedAt || b.createdAt).getTime() - new Date(a.updatedAt || a.createdAt).getTime())
    } catch {
      // Keep the last successful list visible during transient failures and cancelled refreshes.
      if (controller.signal.aborted) return
    } finally {
      if (requestGeneration === conversationLoadGeneration) {
        conversationListLoading.value = false
        conversationLoadController = null
        conversationLoadPromise = null
        conversationLoadWorkspace = null
      }
    }
  })()
  conversationLoadPromise = pending
  return pending
}

let navigationGeneration = 0
const handleChatNavToggle = async () => {
  if (acgNavOpen.value) closeAcgPanel()
  chatNavOpen.value = route.path.startsWith('/chat') ? !chatNavOpen.value : true
  localStorage.setItem(CHAT_NAV_OPEN_KEY, chatNavOpen.value ? '1' : '0')
  if (chatNavOpen.value) void loadRecentConversations()
  if (!route.path.startsWith('/chat')) {
    const generation = ++navigationGeneration
    const source = route.fullPath
    const index = chatStore.workflowBindings
    const contextIdBefore = chatStore.contextId
    const missionId = String(route.params.missionId || '')
    const selectedRunId = typeof route.query.runId === 'string' ? route.query.runId : ''
    // Detect in-place binding mutations as well as replacement of the index object.
    const runBindingSnapshot = () => Object.values(chatStore.workflowBindings).flat()
      .filter(item => item.missionId === missionId && item.runId === selectedRunId)
      .map(item => JSON.stringify(item) ?? '').sort().join('\n')
    const runBindingsBefore = runBindingSnapshot()
    const associatedBefore = Object.values(index).flat().some(item => !item.invalidAt
      && item.missionId === missionId && item.runId === selectedRunId)
    const target = isMissionWorkspacePath(route.path) ? await workbenchConversationTarget({
      index,
      missionId,
      runId: selectedRunId,
      draftId: localStorage.getItem('chat.workflow_draft_conversation_id'),
      currentContextId: chatStore.contextId,
      readRun: id => agentosApi.getWorkflowRun(id),
      readConversation: id => conversationApi.getConversation(id)
    }) : null
    if (generation !== navigationGeneration || source !== route.fullPath || index !== chatStore.workflowBindings
      || contextIdBefore !== chatStore.contextId || runBindingsBefore !== runBindingSnapshot()) return
    if (!target && isMissionWorkspacePath(route.path)) {
      const associated = Object.values(chatStore.workflowBindings).flat().some(item => !item.invalidAt
        && item.missionId === missionId && item.runId === selectedRunId)
      if (associatedBefore || associated) { ElMessage.warning('关联对话暂时无法核实'); return } // a denied/mismatched association must never fall back to the same cached history
      const fallback = router.resolve(lastChatRoute.value)
      const { runId: _run, missionId: _mission, ...query } = fallback.query
      const contextId = typeof query.contextId === 'string' ? query.contextId : chatStore.contextId
      if (contextId) {
        try {
          const conversation = await conversationApi.getConversation(contextId)
          if (generation !== navigationGeneration || source !== route.fullPath || index !== chatStore.workflowBindings
            || contextIdBefore !== chatStore.contextId || runBindingsBefore !== runBindingSnapshot()
            || conversation.contextId !== contextId) return
          query.contextId = contextId
        } catch { return }
      }
      await router.push({ path: '/chat', query })
      return
    }
    await router.push(target || lastChatRoute.value)
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

// Ctrl+B：只在 OScode 对话页开合对话记录子栏；不导航，其他页面为 no-op。
const toggleChatPanelShortcut = () => {
  if (!isChatRoute.value) return
  chatNavOpen.value = !chatNavOpen.value
  localStorage.setItem(CHAT_NAV_OPEN_KEY, chatNavOpen.value ? '1' : '0')
  if (chatNavOpen.value) void loadRecentConversations()
}

const handleAcgNavToggle = async () => {
  if (chatNavOpen.value) closeChatPanel()
  acgNavOpen.value = !acgNavOpen.value
  localStorage.setItem(ACG_NAV_OPEN_KEY, acgNavOpen.value ? '1' : '0')
  if (!isAcgPath(route.path)) {
    acgNavOpen.value = true
    localStorage.setItem(ACG_NAV_OPEN_KEY, '1')
    const generation = ++navigationGeneration
    const source = route.fullPath
    const conversationId = typeof route.query.contextId === 'string' ? route.query.contextId
      : chatStore.contextId || localStorage.getItem('chat.workflow_draft_conversation_id') || ''
    const index = chatStore.workflowBindings
    const contextIdBefore = chatStore.contextId
    const target = isChatRoute.value ? await conversationWorkbenchTarget(index, conversationId,
      typeof route.query.runId === 'string' ? route.query.runId : undefined,
      id => agentosApi.getWorkflowRun(id)) : null
    if (generation !== navigationGeneration || source !== route.fullPath || index !== chatStore.workflowBindings
      || contextIdBefore !== chatStore.contextId) return
    if (!target && isChatRoute.value) {
      if (conversationBindings(chatStore.workflowBindings, conversationId).some(item => !item.invalidAt)) {
        ElMessage.warning('当前对话的关联任务暂时无法核实')
        return
      }
    }
    await router.push(target || lastMissionWorkspacePath.value || '/agentos/acg')
  }
}

const startNewChat = async () => {
  await router.push({ path: '/chat', query: { workspace: 'chat', newConversation: '1' } })
}

const openWorkspaceHistory = () => {
  void router.push({ path: '/history', query: { workspace: 'chat' } })
}

const openConversation = async (conversation: Conversation) => {
  const contextId = conversation.contextId || conversation.id
  await router.push({ path: '/chat', query: { contextId, workspace: 'chat' } })
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

const closeSidebarActionMenu = () => {
  sidebarActionMenu.target = null
}

const openSidebarActionMenu = async (event: MouseEvent, target: SidebarActionTarget) => {
  sidebarActionMenu.target = target
  const trigger = event.currentTarget as HTMLElement | null
  const rect = trigger?.getBoundingClientRect()
  sidebarActionMenu.x = event.clientX || (rect ? rect.right - 176 : 8)
  sidebarActionMenu.y = event.clientY || (rect ? rect.bottom + 6 : 8)
  await nextTick()
  const menu = sidebarActionMenuElement.value
  if (!menu) return
  sidebarActionMenu.x = Math.max(8, Math.min(sidebarActionMenu.x, window.innerWidth - menu.offsetWidth - 8))
  sidebarActionMenu.y = Math.max(8, Math.min(sidebarActionMenu.y, window.innerHeight - menu.offsetHeight - 8))
}

const editSidebarConversation = async (conversationOverride?: Conversation) => {
  const target = sidebarActionMenu.target
  const conversation = conversationOverride || target?.conversation || null
  if (!conversation) return
  closeSidebarActionMenu()
  try {
    const { value: newTitle } = await ElMessageBox.prompt(
      '请输入新的对话标题',
      '编辑标题',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: conversation.title || '',
        inputValidator: (value) => {
          if (!value || value.trim().length === 0) return '标题不能为空'
          if (value.length > 50) return '标题不能超过50个字符'
          return true
        }
      }
    )
    if (!newTitle?.trim()) return
    const title = newTitle.trim()
    await conversationApi.updateTitle(conversation.id, title)
    recentConversations.value = recentConversations.value.map(item => item.id === conversation.id ? { ...item, title } : item)
    ElMessage.success('标题更新成功')
    window.dispatchEvent(new Event('history-refresh'))
  } catch (error: any) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(error?.message || '更新标题失败')
  }
}

const deleteSidebarActionConversation = (conversationOverride?: Conversation) => {
  const target = sidebarActionMenu.target
  const conversation = conversationOverride || target?.conversation || null
  if (!conversation) return
  closeSidebarActionMenu()
  void deleteSidebarConversation(conversation)
}

const deleteSidebarConversation = async (conversation: Conversation) => {
  closeSidebarActionMenu()
  try {
    await ElMessageBox.confirm(
      `确定删除对话“${conversation.title || '未命名对话'}”吗？此操作不可恢复。`,
      '删除聊天记录',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'destructive-confirm'
      }
    )

    await conversationApi.deleteConversation(conversation.id)
    recentConversations.value = recentConversations.value.filter(item => item.id !== conversation.id)

    const deletedContextId = conversation.contextId || conversation.id
    removeConversationWorkspace(deletedContextId)
    if (route.query.contextId === deletedContextId) {
      chatStore.clearMessages()
      await router.replace({ path: '/chat', query: { workspace: 'chat' } })
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

const handleSidebarActionMenuOutside = (event: MouseEvent) => {
  const target = event.target as Node | null
  if (accountMenuOpen.value && target && !accountMenuElement.value?.contains(target)
    && !(target instanceof Element && target.closest('.user-identity'))) {
    closeAccountMenu()
  }
  if (sidebarActionMenu.target && target && !sidebarActionMenuElement.value?.contains(target)) {
    closeSidebarActionMenu()
  }
}

const handleConversationWorkspaceChange = () => {
  conversationWorkspaceVersion.value += 1
  if (chatNavOpen.value) void loadRecentConversations()
}

watch(
  () => route.fullPath,
  fullPath => {
    closeSidebarActionMenu()
    if (isMissionWorkspacePath(route.path)) lastMissionWorkspacePath.value = fullPath
    // 子栏只在 /chat 存在：离开对话页（含进入 ACG hub）一律收起，不得在别页弹出。
    if (route.path.startsWith('/chat')) lastChatRoute.value = fullPath
    else if (chatNavOpen.value) closeChatPanel()
    if (isAcgPath(route.path)) {
      if (localStorage.getItem(ACG_NAV_OPEN_KEY) !== '0') acgNavOpen.value = true
    } else {
      acgNavOpen.value = false
    }
  }
)

const surfaceSwitching = ref(false)
const sidebarKey = 'workbench.primary_sidebar.v1'
const storedSidebar = localStorage.getItem(sidebarKey)
const activeWorkbenchSidebar = ref<WorkbenchSidebar>(['files', 'search', 'git'].includes(storedSidebar || '') ? storedSidebar as WorkbenchSidebar : 'thought')
const sidebarActivation = ref(0)
// 图标顺序可拖拽调整（仅显示偏好，全局记忆）；描述符固定，顺序存 id 数组。
const workbenchActivityDescriptors: Record<WorkbenchSidebar, { id: WorkbenchSidebar; label: string; icon: typeof FolderOpened }> = {
  files: { id: 'files', label: '文件', icon: FolderOpened },
  search: { id: 'search', label: '搜索文件', icon: Search },
  git: { id: 'git', label: 'Git', icon: Share },
  thought: { id: 'thought', label: '思维链', icon: Connection }
}
const activityOrder = ref<WorkbenchSidebar[]>(applyWorkbenchActivityOrder(readWorkbenchActivityOrder()))
const workbenchActivities = computed(() => activityOrder.value.map(id => workbenchActivityDescriptors[id]))

const reorderWorkbenchActivities = (from: number, to: number) => {
  const next = [...activityOrder.value]
  const [moved] = next.splice(from, 1)
  if (!moved) return
  next.splice(to, 0, moved)
  activityOrder.value = next
  writeWorkbenchActivityOrder(next)
}

// 活动栏小图标拖拽排序：隐藏原生快照（会叠在真实图标上显得杂乱），只留淡化 + 落点线。
const activityDrag = useDragReorder({ group: 'workbench-activities', ghost: 'none', onReorder: reorderWorkbenchActivities })
// 活动栏不画落点指示线：按钮圆角会把 2px 插入线弯成半圆，且边界处上下两条同显；松手即重排，视觉只留源项淡化。
const { draggingIndex: draggingActivity } = activityDrag
onBeforeUnmount(() => activityDrag.resetDrag())
const selectWorkbenchSidebar = (view: WorkbenchSidebar) => {
  activeWorkbenchSidebar.value = view
  sidebarActivation.value++
  localStorage.setItem(sidebarKey, view)
}
const switchWorkspaceSurface = async (surface: WorkspaceSurface) => {
  if (surfaceSwitching.value || (surface === 'oscode' ? isChatRoute.value : isAcgRoute.value)) return
  surfaceSwitching.value = true
  try {
    if (surface === 'oscode') await handleChatNavToggle()
    else await handleAcgNavToggle()
  } finally { surfaceSwitching.value = false }
}
provide(workspaceShellKey, {
  activeSidebar: activeWorkbenchSidebar, sidebarActivation, switching: surfaceSwitching,
  switchSurface: switchWorkspaceSurface
})

const isImmersive = computed(() => false)

const showNavigation = computed(() => !isImmersive.value && !route.meta.hideNavigation)

const closeAccountMenu = () => {
  accountMenuOpen.value = false
}

const toggleAccountMenu = async (event: MouseEvent) => {
  if (accountMenuOpen.value) {
    closeAccountMenu()
    return
  }
  const trigger = event.currentTarget as HTMLElement
  const rect = trigger.getBoundingClientRect()
  accountMenuStyle.value = {
    left: `${Math.round(rect.right + 10)}px`,
    bottom: `${Math.max(12, Math.round(window.innerHeight - rect.bottom))}px`
  }
  accountMenuOpen.value = true
  await nextTick()
  const menu = accountMenuElement.value
  if (!menu) return
  accountMenuStyle.value = {
    left: `${Math.max(8, Math.min(rect.right + 10, window.innerWidth - menu.offsetWidth - 8))}px`,
    bottom: `${Math.max(12, Math.round(window.innerHeight - rect.bottom))}px`
  }
}

const openUserProfile = () => {
  closeAccountMenu()
  void router.push('/user')
}

const openSettings = () => {
  closeAccountMenu()
  void router.push('/settings')
}

const handleLogout = () => {
  closeAccountMenu()
  logout()
  void router.replace(AUTH_ROUTE)
}

const handleTopChromeNavigate = (path: string) => {
  void router.push(path)
}

const clampChatPanelWidth = (width: number) => {
  return Math.min(CHAT_PANEL_MAX_WIDTH, Math.max(CHAT_PANEL_MIN_WIDTH, Math.round(width)))
}

const persistChatPanelWidth = () => {
  localStorage.setItem(CHAT_PANEL_WIDTH_KEY, String(chatPanelWidth.value))
  dockGeometry.persist({ leftWidth: chatPanelWidth.value })
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

const isRouteScrollable = computed(() => {
  const path = route.path
  return (
    path.startsWith('/history') ||
    path.startsWith('/agentos/resources') ||
    path.startsWith('/rag')
  )
})

const activeMenu = computed(() => {
  const path = route.path
  if (path === '/chat' || path.startsWith('/chat')) return '/chat'
  if (path.startsWith('/agentos/acg') || isMissionWorkspacePath(path)) return '/agentos/acg'
  if (path === '/settings' || path.startsWith('/settings')) return '/settings'
  if (path.startsWith('/user')) return '/user'
  return path
})

// 拖拽落到页面里无拖放承接的区域时，阻止 WebView2/浏览器默认的"导航到所拖文件"。
// 各拖拽区（如新建工程附件）在自己的 dragover/drop 里 preventDefault 不受影响。
const guardNativeFileDrop = (event: DragEvent): void => {
  if (event.dataTransfer?.types.includes('Files')) event.preventDefault()
}

onMounted(() => {
  window.addEventListener('history-refresh', handleHistoryRefresh)
  window.addEventListener('acg-runs-refresh', handleHistoryRefresh)
  window.addEventListener('conversation-workspace-change', handleConversationWorkspaceChange)
  window.addEventListener('dragover', guardNativeFileDrop)
  window.addEventListener('drop', guardNativeFileDrop)
  document.addEventListener('mousedown', handleSidebarActionMenuOutside)
  // 应用级全局快捷键（Ctrl+B / Ctrl+R / Alt+方向 / F1），窗口级 F11/F12 在 Electron Main。
  disposeAppKeyboardShortcuts = initAppKeyboardShortcuts({
    desktop: isDesktop(),
    toggleChatPanel: toggleChatPanelShortcut,
    historyBack: () => router.back(),
    historyForward: () => router.forward(),
    onShowShortcuts: () => { shortcutsDialogVisible.value = true }
  })
  if (chatNavOpen.value) void loadRecentConversations()
  void userStore.loadCurrentUser()
  void workflowRunsStore.bootstrap()
})

onUnmounted(() => {
  conversationLoadController?.abort()
  stopChatPanelResize()
  disposeAppKeyboardShortcuts?.()
  disposeAppKeyboardShortcuts = null
  window.removeEventListener('history-refresh', handleHistoryRefresh)
  window.removeEventListener('acg-runs-refresh', handleHistoryRefresh)
  window.removeEventListener('conversation-workspace-change', handleConversationWorkspaceChange)
  window.removeEventListener('dragover', guardNativeFileDrop)
  window.removeEventListener('drop', guardNativeFileDrop)
  document.removeEventListener('mousedown', handleSidebarActionMenuOutside)
})
</script>

<style scoped>
.app-layout {
  height: 100%;
  width: 100%;
  background: var(--app-layout-bg);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.app-shell-body {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  width: 100%;
  overflow: hidden;
}

/* Sidebar Styles */
.app-sidebar {
  position: relative;
  background-color: transparent;
  border-right: 0;
  backdrop-filter: blur(18px);
  display: flex;
  flex-direction: row;
  overflow: hidden;
  transition: width 0.22s var(--ease-out);
}

.primary-sidebar {
  /* 图标窄栏固定宽度（与 AppTopBar 的 is-rail-collapsed::after left:48px 同口径）。 */
  width: 48px;
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
  background: var(--app-topbar-bg);
}

.app-sidebar.chat-panel-open .primary-sidebar {
  border-right: 0;
}

.app-sidebar.resizing {
  transition: none;
}

.app-sidebar.resizing .primary-sidebar {
  transition: none;
}

.sidebar-nav {
  flex: 1;
  min-height: 0;
  padding: 10px 8px 12px;
  overflow-y: auto;
  overflow-x: hidden;
  scroll-behavior: smooth;
}

.app-sidebar.collapsed .sidebar-nav {
  padding: 12px 6px 10px;
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
  background: var(--app-topbar-bg);
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

.sidebar-menu {
  --el-menu-item-font-size: 13px;
  font-family: var(--font-sans);
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
  font-family: var(--font-serif);
  font-size: 13px;
  font-weight: 500;
  letter-spacing: -0.012em;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, box-shadow 160ms ease;
}

.chat-nav-trigger > .el-icon:first-child {
  flex: 0 0 auto;
  margin-right: 17px;
  font-size: 18px;
}

.acg-nav-logo {
  width: 35px;
  height: 35px;
  flex: 0 0 35px;
  display: block;
  border-radius: 4px;
  object-fit: cover;
  /* The raster artwork has built-in side padding; align its visible mark with the line icons. */
  transform: translateX(-6px);
}

.chat-nav-trigger:hover {
  border-color: transparent;
  background: color-mix(in srgb, var(--text-primary) 4%, transparent);
  color: var(--text-primary);
  box-shadow: none;
}

.chat-nav-group.active > .chat-nav-trigger {
  border-color: transparent;
  background: transparent;
  color: var(--text-primary);
  font-weight: 500;
  box-shadow: none;
}

/* VS Code 简约选中态：左缘细竖条指示，无底色无描边 */
.chat-nav-group.active > .chat-nav-trigger::before {
  content: '';
  position: absolute;
  top: 50%;
  left: -8px;
  width: 2px;
  height: 18px;
  border-radius: 1px;
  background: var(--text-primary);
  transform: translateY(-50%);
}

.chat-nav-trigger:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.app-sidebar.collapsed .chat-nav-trigger {
  justify-content: center;
  padding: 0;
}

.app-sidebar.collapsed .chat-nav-group.active > .chat-nav-trigger::before {
  left: -6px;
}

.app-sidebar.collapsed .chat-nav-trigger > .el-icon:first-child {
  margin-right: 0;
}

.app-sidebar.collapsed .acg-nav-logo {
  width: 28px;
  height: 28px;
  flex-basis: 28px;
  transform: none;
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
  width: auto;
  flex: 0 0 auto;
  min-height: 26px;
  justify-content: flex-start;
  padding: 0 8px;
  border: 0;
  background: transparent;
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 550;
  box-shadow: none;
}

.new-chat-action:hover {
  background: var(--bg-panel);
  color: var(--primary-color);
}

.chat-submenu-section-head {
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 6px 5px 8px;
  color: var(--text-disabled);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.035em;
}

.chat-submenu-section-title {
  min-width: 0;
  flex: 1 1 auto;
  white-space: nowrap;
}

.chat-submenu-section-tools {
  min-width: 0;
  flex: 0 1 auto;
  display: flex;
  align-items: center;
  gap: 6px;
}

.chat-project-count {
  min-width: 20px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 4px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-disabled);
  font-size: 11px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.chat-submenu-refreshing {
  margin-left: auto;
  color: var(--primary-color);
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0;
}

.chat-submenu-action .el-icon {
  flex: 0 0 auto;
  font-size: 13px;
}

.chat-project-list {
  min-height: 0;
  flex: 1 1 auto;
  display: grid;
  /* 行高按内容计：容器高度不足时溢出滚动，而不是把行轨道压扁叠在一起 */
  grid-auto-rows: max-content;
  align-content: start;
  gap: 6px;
  padding: 2px 2px 8px;
  overflow-y: auto;
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
  position: relative;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: stretch;
  gap: 2px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  overflow: hidden;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.chat-project-item {
  min-width: 0;
  min-height: 32px;
  gap: 8px;
  padding: 5px 8px;
  border-radius: 8px;
  color: inherit;
  font-size: 12.5px;
  font-weight: 450;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.chat-project-row:hover {
  background: var(--bg-panel);
  color: var(--text-primary);
}

.chat-project-item:hover {
  background: transparent;
  color: inherit;
}

.chat-project-icon {
  display: none;
}

.chat-project-icon .el-icon {
  font-size: 14px;
}

.chat-project-copy {
  min-width: 0;
  flex: 1 1 auto;
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

.chat-project-title,
.chat-project-time {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-project-title {
  min-width: 0;
  flex: 0 1 auto;
  color: inherit;
  line-height: 1.35;
}

.chat-project-time {
  position: absolute;
  top: 50%;
  right: 10px;
  transform: translateY(-50%);
  color: var(--text-disabled);
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  line-height: 1.2;
}

.chat-project-row.active {
  background: var(--primary-fade);
  color: var(--primary-color);
  font-weight: 550;
}

.chat-project-row.active .chat-project-icon {
  background: color-mix(in srgb, var(--primary-color) 14%, var(--bg-card));
  color: var(--primary-color);
}

.chat-project-action-trigger {
  width: 30px;
  min-height: 32px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-left: 1px solid transparent;
  background: transparent;
  color: var(--text-disabled);
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.16s ease, color 0.16s ease, background-color 0.16s ease;
}

.chat-project-action-trigger .el-icon {
  font-size: 14px;
}

.chat-project-row:hover .chat-project-action-trigger,
.chat-project-action-trigger:focus-visible {
  border-left-color: transparent;
  opacity: 0.7;
}

.chat-project-action-trigger.is-open {
  opacity: 1;
}

.chat-project-action-trigger:hover,
.chat-project-action-trigger:focus-visible {
  background: color-mix(in srgb, var(--primary-color) 9%, transparent);
  color: var(--primary-color);
  outline: none;
}

.chat-project-actions {
  position: absolute;
  top: 50%;
  right: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
  opacity: 0;
  pointer-events: none;
  transform: translate(10px, -50%);
  transition: opacity 220ms var(--ease-out, ease) 35ms, transform 220ms var(--ease-out, ease) 35ms;
}

.chat-project-row--chat {
  position: relative;
  display: block;
}

.chat-project-row--chat:hover .chat-project-actions,
.chat-project-row--chat:focus-within .chat-project-actions {
  opacity: 1;
  pointer-events: auto;
  transform: translate(0, -50%);
}

.chat-project-action {
  width: 24px;
  height: 24px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background-color 160ms ease, color 160ms ease;
}

.chat-project-action .el-icon {
  font-size: 15px;
}

.chat-project-action:hover,
.chat-project-action:focus-visible {
  background: color-mix(in srgb, var(--primary-color) 9%, transparent);
  color: var(--primary-color);
  outline: none;
}

.chat-project-action--delete:hover,
.chat-project-action--delete:focus-visible {
  background: var(--danger-fade);
  color: var(--danger);
}

.chat-project-action:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 45%, transparent);
  outline-offset: 2px;
}

.sidebar-action-menu {
  position: fixed;
  z-index: 3000;
  min-width: 148px;
  display: grid;
  gap: 2px;
  padding: 5px;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  background: var(--surface-solid);
  box-shadow: var(--shadow-lg, 0 12px 30px rgba(0, 0, 0, .18));
}

.sidebar-action-menu button {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  min-height: 30px;
  padding: 0 9px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.sidebar-action-menu button:hover,
.sidebar-action-menu button:focus-visible {
  outline: none;
  background: var(--bg-panel);
  color: var(--text-primary);
}

.sidebar-action-menu button.is-danger:hover,
.sidebar-action-menu button.is-danger:focus-visible {
  background: var(--danger-fade);
  color: var(--danger);
}

.sidebar-action-menu button:disabled {
  color: var(--text-disabled);
  cursor: not-allowed;
  opacity: .6;
}

.sidebar-action-menu button .el-icon {
  flex: 0 0 auto;
  font-size: 14px;
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
  height: 34px;
  min-height: 34px;
  flex: 0 0 34px;
  gap: 7px;
  margin-top: 5px;
  padding: 0 9px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
}

.history-action:hover {
  background: var(--bg-panel);
  color: var(--text-primary);
}

.history-action__icon {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
  display: inline-grid;
  place-items: center;
  border-radius: 5px;
  background: transparent;
}

.history-action__copy {
  min-width: 0;
  flex: 1 1 0;
  display: flex;
  align-items: center;
}

.history-action__copy strong,
.history-action__copy small {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.history-action__copy strong {
  color: inherit;
  font-size: 12px;
  font-weight: 500;
  line-height: 1.2;
}

.history-action__copy small {
  display: none;
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

/* 简约选中态：图标/文字提亮，选中指示条见 .is-active::before */
.sidebar-menu :deep(.el-menu-item) {
  height: 44px;
  margin: 0 0 2px;
  padding: 0 var(--sidebar-item-icon-inset) !important;
  gap: 10px;
  border: 1px solid transparent;
  border-radius: 10px;
  color: var(--text-secondary);
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: -0.012em;
  transition: background-color 160ms ease, border-color 160ms ease, color 160ms ease, box-shadow 160ms ease;
  position: relative;
}

.sidebar-menu :deep(.el-menu-item .el-icon) {
  flex: 0 0 18px;
  width: 18px;
  margin-right: 17px;
  font-size: 18px;
}

.sidebar-menu :deep(.el-menu-item > span) {
  font-size: 13px !important;
  line-height: 1.35;
}

.sidebar-menu :deep(.el-menu-item:hover) {
  border-color: transparent;
  /* global.css 对 el-menu-item hover/active 有 ！important 强制（蓝底蓝字），此处同级覆盖回简约样式 */
  background-color: color-mix(in srgb, var(--text-primary) 4%, transparent) !important;
  color: var(--text-primary) !important;
  box-shadow: none;
}

.sidebar-menu :deep(.el-menu-item.is-active) {
  border-color: transparent;
  background-color: transparent !important;
  color: var(--text-primary) !important;
  box-shadow: none;
}

/* VS Code 简约选中态：左缘细竖条指示，无底色无描边 */
.sidebar-menu :deep(.el-menu-item.is-active::before) {
  content: '';
  position: absolute;
  top: 50%;
  left: -8px;
  width: 2px;
  height: 18px;
  border-radius: 1px;
  background: var(--text-primary);
  transform: translateY(-50%);
}

.app-sidebar.collapsed .sidebar-menu :deep(.el-menu-item.is-active::before) {
  left: -6px;
}

.sidebar-menu :deep(.el-menu-item:focus-visible) {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.sidebar-footer {
  flex-shrink: 0;
  padding: 10px 10px 12px;
  margin-top: auto;
  border-top: 0;
  background: color-mix(in srgb, var(--bg-sidebar) 86%, var(--bg-app));
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
  gap: 6px;
  min-width: 0;
  padding: 3px;
}

.user-identity {
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.user-identity {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 6px;
  border-radius: 7px;
  text-align: left;
}

.user-identity:hover { background: var(--bg-input); }
.user-avatar {
  flex: 0 0 32px;
  width: 32px !important;
  height: 32px !important;
  background-color: var(--primary-color);
  color: white;
  font-size: 14px;
  font-weight: 700;
}

.user-identity:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.sidebar-account-menu {
  position: fixed;
  z-index: 4000;
  width: 248px;
  max-height: calc(100vh - 24px);
  overflow-y: auto;
  padding: 8px;
  border: 1px solid color-mix(in srgb, var(--border-color) 70%, transparent);
  border-radius: 16px;
  background: var(--bg-sidebar);
  color: var(--text-primary);
  box-shadow: 0 16px 42px rgba(0, 0, 0, 0.32);
  backdrop-filter: blur(18px);
}

.sidebar-account-menu__identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 8px 7px 10px;
}

.sidebar-account-menu__avatar { flex: 0 0 auto; }

.sidebar-account-menu__user-copy {
  display: grid;
  min-width: 0;
  gap: 2px;
}

.sidebar-account-menu__user-copy strong,
.sidebar-account-menu__user-copy span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-account-menu__user-copy strong { font-size: 14px; font-weight: 600; }
.sidebar-account-menu__user-copy span { color: var(--text-secondary); font-size: 12px; }

.sidebar-account-menu__divider {
  height: 1px;
  margin: 2px 4px 6px;
  background: var(--border-color);
}

.sidebar-account-menu > button {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: 38px;
  padding: 0 8px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.sidebar-account-menu > button:hover { background: var(--bg-input); }
.sidebar-account-menu > button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 1px; }

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

.route-loading {
  display: grid;
  min-height: 100%;
  place-items: center;
  color: var(--text-secondary);
  font-size: 13px;
}

/* Keep the application chrome still while dock contents change. */
.docked-workspace-shell { background: var(--wb-surface-shell); }
.docked-workspace-shell.has-dock-status { padding-bottom: var(--workbench-status-bar-height, 22px); }
.docked-workspace-shell .app-sidebar,
.docked-workspace-shell .primary-sidebar { transition: none; }
.docked-workspace-shell .chat-side-panel {
  box-sizing: border-box;
  background: var(--wb-surface-pane);
  box-shadow: none;
}
.docked-workspace-shell .docked-workspace-shell .chat-panel-enter-active,
.docked-workspace-shell .chat-panel-leave-active { transition: opacity 160ms ease, transform 180ms var(--ease-out); }
.docked-workspace-shell .chat-panel-enter-from,
.docked-workspace-shell .chat-panel-leave-to { opacity: 0; transform: translateX(-14px); }
.docked-workspace-shell .dock-column-enter-active,
.docked-workspace-shell .dock-column-leave-active {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  transition: opacity 180ms ease, transform 220ms var(--ease-out);
}
.docked-workspace-shell .dock-column-leave-active { pointer-events: none; }
.docked-workspace-shell .dock-column-enter-from { opacity: 0; transform: translateX(var(--dock-column-enter-x)); }
.docked-workspace-shell .dock-column-leave-to { opacity: 0; transform: translateX(var(--dock-column-leave-x)); }
.docked-workspace-shell.is-chat-route { --dock-column-enter-x: -26px; --dock-column-leave-x: 26px; }
.docked-workspace-shell:not(.is-chat-route) { --dock-column-enter-x: 26px; --dock-column-leave-x: -26px; }
.docked-workspace-shell :deep(.message-list),
.docked-workspace-shell :deep(.editor-document__body) { animation: dock-content-enter 140ms ease-out; }
@keyframes dock-content-enter { from { opacity: .7; } to { opacity: 1; } }
@media (prefers-reduced-motion: reduce) {
  .docked-workspace-shell .dock-column-enter-active,
  .docked-workspace-shell .dock-column-leave-active,
  .docked-workspace-shell :deep(.message-list),
  .docked-workspace-shell :deep(.editor-document__body) { animation: none; }
}

/* Immersive Mode Overrides */
.immersive-mode .main-container {
  background-color: var(--bg-app);
}

.immersive-mode .app-main {
  overflow-y: auto;
}

/* Responsive optimization */
.app-main::-webkit-scrollbar {
  width: 4px;
}

.app-main::-webkit-scrollbar-track {
  background: transparent;
}

.app-main::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 10px;
}

.app-main::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-thumb-hover);
}

/* Screenshot refinement: make the shell read as one calm, layered workbench. */
.app-sidebar {
  border-right-color: transparent;
}

.primary-sidebar,
.chat-side-panel {
  background: var(--app-topbar-bg);
}

.chat-side-panel {
  box-shadow: 14px 0 28px rgba(0, 0, 0, 0.14);
}

.chat-panel-content {
  padding: 12px 10px 12px;
}



.chat-submenu-section-head {
  min-height: 36px;
  padding: 4px 8px 6px;
  color: var(--text-muted);
}

.chat-project-list {
  gap: 3px;
  padding: 2px 2px 8px;
}

.chat-project-row {
  border-radius: 8px;
}

.chat-project-row:hover {
  background: var(--bg-panel);
}

.chat-project-row.active {
  background: color-mix(in srgb, var(--primary-fade) 55%, var(--bg-card));
  color: var(--text-primary);
}

.chat-project-item {
  min-height: 34px;
  padding: 6px 148px 6px 9px;
}

.chat-project-row--chat .chat-project-item {
  padding-right: 108px;
}

.chat-project-row--chat .chat-project-time {
  max-width: 46px;
}

.chat-project-row--chat .chat-project-actions {
  right: 50px;
}

.chat-project-time {
  color: var(--text-muted);
}

.chat-project-row:not(.chat-project-row--chat) .chat-project-time {
  width: 96px;
  text-align: right;
}

.chat-project-row:not(.chat-project-row--chat) .chat-project-action-trigger {
  position: absolute;
  top: 50%;
  right: 112px;
  transform: translateY(-50%);
}

.history-action {
  color: var(--text-muted);
}

.history-action:hover {
  background: var(--bg-panel);
  color: var(--text-primary);
}

.workbench-activity-views { display: flex; flex-direction: column; gap: 3px; margin-top: 8px; }
.workbench-activity-button { position: relative; }
.workbench-activity-button.is-selected { color: var(--primary-color); }
.workbench-activity-button > .el-icon:first-child { margin-right: 0; }
/* —— 图标拖拽排序：拖起半透明，落点上/下缘画指示线 —— */
.workbench-activity-button { cursor: grab; }
.workbench-activity-button:active { cursor: grabbing; }
.workbench-activity-button.is-dragging { opacity: .45; }
</style>
