<!-- 已认证工作区布局 — 侧边栏导航、沉浸/简洁模式和工作区事件 -->
<template>
  <el-container class="app-layout" :class="{ 'immersive-mode': isImmersive }">
        <AppTopBar
          v-if="showNavigation"
          :navigation-state="usesDrawerNavigation ? 'drawer' : (mainSidebarCompact ? 'collapsed' : 'expanded')"
          @menu="handleTopChromeMenu"
          @navigate="handleTopChromeNavigate"
        />

        <el-container class="app-shell-body" :class="{ 'docked-workspace-shell': isDockedWorkspaceRoute, 'is-chat-route': isChatRoute, 'has-dock-status': hasDockStatus }">
          <!-- Sidebar Navigation -->
          <el-aside
            v-if="showNavigation && !usesDrawerNavigation"
            :width="sidebarAsideWidth"
            class="app-sidebar"
            :class="{ collapsed: mainSidebarCompact, 'chat-panel-open': secondaryNavOpen, resizing: sidebarResizing || chatPanelResizing }"
          >
          <div class="primary-sidebar" :style="{ width: primarySidebarWidth }">
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
                  @click="handleAcgNavToggle"
                >
                  <img class="acg-nav-logo" src="/acglogo.webp" alt="" aria-hidden="true" />
                  <span v-if="!mainSidebarCompact" class="chat-nav-label">ACG 动态群体智能引擎</span>
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
                :aria-label="userIdentityActionLabel"
                :title="userIdentityActionLabel"
                @click="handleUserIdentityClick"
              >
              <UserAvatar :size="28" class="user-avatar" :fallback="sidebarUserInitial" />
              <div v-if="!mainSidebarCompact" class="user-info">
                <span class="user-name">{{ sidebarUserName }}</span>
                <span class="user-status">{{ sidebarUserMeta }}</span>
              </div>
              </button>
              <button v-if="!mainSidebarCompact" class="user-logout" type="button" aria-label="退出登录" title="退出登录" @click="handleLogout">
                <el-icon><SwitchButton /></el-icon>
              </button>
            </div>
            <el-menu
              :default-active="activeMenu"
              router
              class="sidebar-menu sidebar-settings-menu"
              :collapse="mainSidebarCompact"
              :collapse-transition="false"
            >
              <el-menu-item index="/settings">
                <el-icon><Setting /></el-icon>
                <span>{{ $t('nav.settings') }}</span>
              </el-menu-item>
            </el-menu>
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

                <div class="chat-submenu-section-head">
                    <span class="chat-submenu-section-title">{{ workspaceMode === 'agent' ? '工程项目' : '对话记录' }}</span>
                  <div class="chat-submenu-section-tools">
                    <span v-if="workspaceHistoryCount" class="chat-project-count" :aria-label="`${workspaceHistoryCount} 个项目`">
                      {{ workspaceHistoryCount }}
                    </span>
                  </div>
                  <span v-if="conversationListLoading && workspaceHistoryCount" class="chat-submenu-refreshing">更新中</span>
                  <button class="chat-submenu-action new-chat-action" type="button" @click="startNewChat">
                    <el-icon><EditPen /></el-icon>
                    <span>{{ workspaceMode === 'agent' ? '新建 Agent 任务' : '新建对话' }}</span>
                  </button>
                </div>

                <div v-if="conversationListLoading && !workspaceHistoryCount" class="chat-submenu-loading">正在加载…</div>
                <div v-else-if="workspaceMode === 'agent' && recentAgentProjects.length" class="chat-project-list" role="list" aria-label="Agent 工程项目">
                  <div
                    v-for="mission in recentAgentProjects"
                    :key="mission.missionId"
                    class="chat-project-row"
                    :class="{ active: String(route.params.missionId || '') === mission.missionId }"
                    role="listitem"
                    @contextmenu.prevent.stop="openSidebarActionMenu($event, { kind: 'agent', project: mission })"
                  >
                    <button
                      class="chat-project-item"
                      type="button"
                      :title="plainMissionTitle(mission.title)"
                      @click="openAgentProject(mission)"
                    >
                      <span class="chat-project-icon" aria-hidden="true">
                        <el-icon><Cpu /></el-icon>
                      </span>
                      <span class="chat-project-copy">
                        <span class="chat-project-title">{{ plainMissionTitle(mission.title) }}</span>
                        <span class="chat-project-time">
                          {{ agentProjectState(mission) }} · {{ formatConversationTime(mission.updatedAt || mission.createdAt) }}
                        </span>
                      </span>
                    </button>
                    <button
                      class="chat-project-action-trigger"
                      :class="{ 'is-open': isAgentSidebarActionOpen(mission.missionId) }"
                      type="button"
                      aria-haspopup="menu"
                      aria-controls="sidebar-action-menu"
                      :aria-expanded="isAgentSidebarActionOpen(mission.missionId)"
                      :aria-label="`打开项目操作：${mission.title || '未命名工程'}`"
                      title="更多操作"
                      @click.stop="openSidebarActionMenu($event, { kind: 'agent', project: mission })"
                    >
                      <el-icon><MoreFilled /></el-icon>
                    </button>
                  </div>
                </div>
                <div v-else-if="workspaceMode === 'chat' && visibleRecentConversations.length" class="chat-project-list" role="list" aria-label="对话记录">
                  <div
                    v-for="conversation in visibleRecentConversations"
                    :key="conversation.id"
                    class="chat-project-row chat-project-row--chat"
                    :class="{ active: route.query.contextId === (conversation.contextId || conversation.id) }"
                    role="listitem"
                    @contextmenu.prevent.stop="openSidebarActionMenu($event, { kind: 'chat', conversation })"
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
                    <div class="chat-project-actions" aria-label="瀵硅瘽鎿嶄綔">
                      <button class="chat-project-action chat-project-action--edit" type="button" title="缂栬緫鏍囬" @click.stop="editSidebarConversation(conversation)">
                        <el-icon><Edit /></el-icon>
                      </button>
                      <button class="chat-project-action chat-project-action--delete" type="button" title="鍒犻櫎瀵硅瘽" @click.stop="deleteSidebarActionConversation(conversation)">
                        <el-icon><Delete /></el-icon>
                      </button>
                    </div>
                  </div>
                </div>
                <div v-else class="chat-submenu-empty">
                  {{ workspaceMode === 'agent' ? '暂无 Agent 工程项目' : '暂无历史对话' }}
                </div>

                <button class="chat-submenu-action history-action" type="button" @click="openWorkspaceHistory">
                  <span class="history-action__icon" aria-hidden="true">
                    <el-icon><Clock /></el-icon>
                  </span>
                  <span class="history-action__copy">
                    <strong>{{ workspaceMode === 'agent' ? '查看所有 ACG 记录' : '查找所有聊天记录' }}</strong>
                    <small>{{ workspaceMode === 'agent' ? '搜索、审计与任务管理' : '搜索、编辑与管理' }}</small>
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

        <el-drawer
          v-if="showNavigation && usesDrawerNavigation"
          v-model="simpleNavOpen"
          direction="ltr"
          :size="248"
          :with-header="false"
          class="simple-nav-drawer"
        >
          <div class="drawer-sidebar">
            <div class="sidebar-header drawer-header">
              <button class="drawer-close" type="button" aria-label="关闭导航" title="关闭导航" @click="simpleNavOpen = false">
                <el-icon><Fold /></el-icon>
                <span>导航</span>
              </button>
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
                <img class="acg-nav-logo" src="/acglogo.webp" alt="" aria-hidden="true" />
                <span>ACG 动态群体智能引擎</span>
              </el-menu-item>
            </el-menu>

            <div class="sidebar-footer drawer-footer">
              <div class="user-profile">
                <button
                  class="user-identity"
                  type="button"
                  :aria-label="userIdentityActionLabel"
                  :title="userIdentityActionLabel"
                  @click="handleUserIdentityClick"
                >
                  <UserAvatar :size="28" class="user-avatar" :fallback="sidebarUserInitial" />
                  <div class="user-info">
                    <span class="user-name">{{ sidebarUserName }}</span>
                    <span class="user-status">{{ sidebarUserMeta }}</span>
                  </div>
                </button>
                <button class="user-logout" type="button" aria-label="退出登录" title="退出登录" @click="handleLogout">
                  <el-icon><SwitchButton /></el-icon>
                </button>
              </div>
              <el-menu
                :default-active="activeMenu"
                router
                class="sidebar-menu sidebar-settings-menu"
                @select="simpleNavOpen = false"
              >
                <el-menu-item index="/settings">
                  <el-icon><Setting /></el-icon>
                  <span>{{ $t('nav.settings') }}</span>
                </el-menu-item>
              </el-menu>
            </div>
          </div>
        </el-drawer>

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
        <template v-if="sidebarActionMenu.target.kind === 'agent'">
          <button type="button" role="menuitem" @click="openSidebarActionTarget">
            <span>打开项目</span>
          </button>
          <button
            type="button"
            role="menuitem"
            :disabled="!canMutateSidebarProject"
            :title="canMutateSidebarProject ? '' : '运行中的任务不能归档或删除'"
            @click="archiveSidebarProject"
          >
            <el-icon><FolderAdd /></el-icon><span>归档项目</span>
          </button>
          <button
            type="button"
            role="menuitem"
            class="is-danger"
            :disabled="!canMutateSidebarProject"
            :title="canMutateSidebarProject ? '' : '运行中的任务不能归档或删除'"
            @click="deleteSidebarProject"
          >
            <el-icon><Delete /></el-icon><span>删除项目</span>
          </button>
        </template>
        <template v-else>
          <button type="button" role="menuitem" @click="() => editSidebarConversation()">
            <el-icon><Edit /></el-icon><span>编辑标题</span>
          </button>
          <button type="button" role="menuitem" class="is-danger" @click="() => deleteSidebarActionConversation()">
            <el-icon><Delete /></el-icon><span>删除对话</span>
          </button>
        </template>
      </div>
    </Teleport>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, provide, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ChatDotRound, ChatLineRound, Delete, Edit, EditPen, FolderAdd, MoreFilled,
  Clock, Setting, SwitchButton,
  Monitor, Cpu,
  Fold
} from '@element-plus/icons-vue'
import AppTopBar from '@/components/app/AppTopBar.vue'
import DesktopRuntimeStatus from '@/components/platform/DesktopRuntimeStatus.vue'
const DesktopTerminalDock = defineAsyncComponent(() => import('@/components/terminal/DesktopTerminalDock.vue'))
import { authApi } from '@/services/api/auth'
import BrandLoader from '@/components/common/BrandLoader.vue'
import { conversationApi, type Conversation } from '@/services/api/conversation'
import { agentosApi, type MissionListItem } from '@/services/api/agentos'
import { useChatStore } from '@/stores/chat'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { useUserStore } from '@/stores/user'
import UserAvatar from '@/components/UserAvatar.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  getConversationWorkspace,
  removeConversationWorkspace
} from '@/utils/conversationWorkspace'
import { isDesktop } from '@/platform'
import { plainMissionTitle } from '@/utils/missionTitle'
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
const simpleNavOpen = ref(false)
const shortcutsDialogVisible = ref(false)
let disposeAppKeyboardShortcuts: (() => void) | null = null
type WorkspaceMode = 'agent' | 'chat'
const WORKSPACE_MODE_KEY = 'layout.workspace_mode'
const workspaceMode = ref<WorkspaceMode>(localStorage.getItem(WORKSPACE_MODE_KEY) === 'agent' ? 'agent' : 'chat')
const CHAT_NAV_OPEN_KEY = 'layout.chat_nav_open'
const chatNavOpen = ref(route.path.startsWith('/chat') && localStorage.getItem(CHAT_NAV_OPEN_KEY) === '1')
const ACG_NAV_OPEN_KEY = 'layout.acg_nav_open'
const isMissionWorkspacePath = (path: string) => path.startsWith('/agentos/missions/') && path.endsWith('/workspace')
const isDockedWorkspaceRoute = computed(() => route.path.startsWith('/chat') || isMissionWorkspacePath(route.path))
const isChatRoute = computed(() => route.path.startsWith('/chat'))
const hasDockStatus = computed(() => isMissionWorkspacePath(route.path) || (route.path.startsWith('/chat') && workspaceMode.value === 'chat'))
const lastMissionWorkspacePath = ref(isMissionWorkspacePath(route.path) ? route.fullPath : '')
const lastChatRoute = ref(route.path.startsWith('/chat') ? route.fullPath : `/chat?workspace=${workspaceMode.value}`)
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
const recentAgentProjects = ref<MissionListItem[]>([])
type SidebarActionTarget =
  | { kind: 'agent'; project: MissionListItem }
  | { kind: 'chat'; conversation: Conversation }
const sidebarActionMenu = reactive<{ target: SidebarActionTarget | null; x: number; y: number }>({ target: null, x: 0, y: 0 })
const sidebarActionMenuElement = ref<HTMLElement | null>(null)
let conversationLoadGeneration = 0
let conversationLoadController: AbortController | null = null
let conversationLoadPromise: Promise<void> | null = null
let conversationLoadWorkspace: WorkspaceMode | null = null
const SIDEBAR_PROJECT_PAGE_SIZE = 100
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
const workspaceHistoryCount = computed(() => workspaceMode.value === 'agent'
  ? recentAgentProjects.value.length
  : visibleRecentConversations.value.length
)
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
const isAcgRoute = computed(() => isAcgPath(route.path))
const secondaryNavOpen = computed(() => chatNavOpen.value)
const mainSidebarCompact = computed(() => sidebarCollapsed.value || secondaryNavOpen.value || isMissionWorkspacePath(route.path))
const COLLAPSED_SIDEBAR_WIDTH = 48
const sidebarAsideWidth = computed(() => `${secondaryNavOpen.value ? COLLAPSED_SIDEBAR_WIDTH + chatPanelWidth.value : (mainSidebarCompact.value ? COLLAPSED_SIDEBAR_WIDTH : sidebarWidth.value)}px`)
const primarySidebarWidth = computed(() => `${mainSidebarCompact.value ? COLLAPSED_SIDEBAR_WIDTH : sidebarWidth.value}px`)
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
      if (requestedWorkspace === 'agent') {
        const missionPage = await agentosApi.listMissions(
          { page: 1, pageSize: SIDEBAR_PROJECT_PAGE_SIZE },
          { signal: controller.signal }
        )
        if (requestGeneration !== conversationLoadGeneration || requestedWorkspace !== workspaceMode.value) return
        const projects = missionPage.items || []
        if (requestGeneration !== conversationLoadGeneration || requestedWorkspace !== workspaceMode.value) return
        recentAgentProjects.value = projects
        return
      }

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
    const associatedBefore = Object.values(index).flat().some(item => !item.invalidAt
      && item.missionId === String(route.params.missionId || '') && item.runId === route.query.runId)
    const target = isMissionWorkspacePath(route.path) ? await workbenchConversationTarget({
      index: chatStore.workflowBindings,
      missionId: String(route.params.missionId || ''),
      runId: typeof route.query.runId === 'string' ? route.query.runId : '',
      draftId: localStorage.getItem('chat.workflow_draft_conversation_id'),
      currentContextId: chatStore.contextId,
      readRun: id => agentosApi.getWorkflowRun(id),
      readConversation: id => conversationApi.getConversation(id)
    }) : null
    if (generation !== navigationGeneration || source !== route.fullPath || index !== chatStore.workflowBindings
      || contextIdBefore !== chatStore.contextId) return
    if (!target && isMissionWorkspacePath(route.path)) {
      ElMessage.warning('当前没有可恢复的关联对话')
      const associated = Object.values(chatStore.workflowBindings).flat().some(item => !item.invalidAt
        && item.missionId === String(route.params.missionId || '') && item.runId === route.query.runId)
      if (associatedBefore || associated) return // a denied/mismatched association must never fall back to the same cached history
      const fallback = router.resolve(lastChatRoute.value)
      const { runId: _run, missionId: _mission, ...query } = fallback.query
      const contextId = typeof query.contextId === 'string' ? query.contextId : chatStore.contextId
      if (contextId) {
        try {
          const conversation = await conversationApi.getConversation(contextId)
          if (generation !== navigationGeneration || source !== route.fullPath || conversation.contextId !== contextId) return
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
      ElMessage.warning('当前对话没有可验证的关联任务')
      if (conversationBindings(chatStore.workflowBindings, conversationId).some(item => !item.invalidAt)) return
    }
    await router.push(target || lastMissionWorkspacePath.value || '/agentos/acg')
  }
}

const startNewChat = async () => {
  await router.push({ path: '/chat', query: { workspace: workspaceMode.value, newConversation: '1' } })
}

const openWorkspaceHistory = () => {
  if (workspaceMode.value === 'agent') {
    void router.push({ path: '/history', query: { tab: 'acg', source: 'agent' } })
    return
  }
  void router.push({ path: '/history', query: { workspace: 'chat' } })
}

const agentProjectState = (project: MissionListItem) => {
  const status = project.latestRunStatus || project.status
  if (status === 'completed' || status === 'succeeded') return '已完成'
  if (status === 'failed') return '执行失败'
  if (status === 'cancelled') return '已取消'
  if (status === 'waiting_review') return '等待审核'
  return '运行中'
}

const openAgentProject = async (project: MissionListItem) => {
  chatStore.clearMessages()
  await router.push({
    path: `/agentos/missions/${encodeURIComponent(project.missionId)}/workspace`,
    query: project.latestRunId ? { runId: project.latestRunId } : undefined
  })
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

const isTerminalSidebarProject = (project: MissionListItem) => {
  if (project.runCount === 0) return true
  const status = project.latestRunStatus || project.status
  return ['completed', 'succeeded', 'failed', 'cancelled', 'superseded'].includes(status)
}

const canMutateSidebarProject = computed(() => {
  const target = sidebarActionMenu.target
  return target?.kind === 'agent' && isTerminalSidebarProject(target.project)
})

const closeSidebarActionMenu = () => {
  sidebarActionMenu.target = null
}

const isAgentSidebarActionOpen = (missionId: string) => (
  sidebarActionMenu.target?.kind === 'agent' && sidebarActionMenu.target.project.missionId === missionId
)

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

const openSidebarActionTarget = () => {
  const target = sidebarActionMenu.target
  if (!target) return
  closeSidebarActionMenu()
  if (target.kind === 'agent') void openAgentProject(target.project)
  else void openConversation(target.conversation)
}

const sidebarMissionMutationError = (error: unknown, action: string) => {
  const response = (error as { response?: { status?: number; data?: { detail?: unknown; message?: unknown } } })?.response
  const detail = [response?.data?.message, response?.data?.detail]
    .find(value => typeof value === 'string' && value.trim())
  if (response?.status === 409 && detail === 'mission has active runs') return `项目仍在运行，暂时不能${action}`
  if (response?.status === 404) return '项目不存在或当前账户无权操作'
  return typeof detail === 'string' ? `${action}失败：${detail.slice(0, 160)}` : `项目${action}失败，请稍后重试`
}

const archiveSidebarProject = async () => {
  const target = sidebarActionMenu.target
  if (!target || target.kind !== 'agent' || !isTerminalSidebarProject(target.project)) return
  const project = target.project
  try {
    await agentosApi.archiveMission(project.missionId)
    recentAgentProjects.value = recentAgentProjects.value.filter(item => item.missionId !== project.missionId)
    closeSidebarActionMenu()
    ElMessage.success('项目已归档')
    window.dispatchEvent(new Event('history-refresh'))
    if (String(route.params.missionId || '') === project.missionId) {
      await router.replace({ path: '/chat', query: { workspace: 'agent' } })
    }
  } catch (error: unknown) {
    ElMessage.error(sidebarMissionMutationError(error, '归档'))
  }
}

const deleteSidebarProject = async () => {
  const target = sidebarActionMenu.target
  if (!target || target.kind !== 'agent' || !isTerminalSidebarProject(target.project)) return
  const project = target.project
  try {
    await ElMessageBox.confirm(
      `确定删除项目“${project.title || '未命名工程'}”吗？此操作不可恢复。`,
      '删除项目',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning',
        customClass: 'destructive-confirm'
      }
    )
  } catch {
    return
  }
  try {
    await agentosApi.deleteMission(project.missionId)
    recentAgentProjects.value = recentAgentProjects.value.filter(item => item.missionId !== project.missionId)
    closeSidebarActionMenu()
    ElMessage.success('项目已删除')
    window.dispatchEvent(new Event('history-refresh'))
    if (String(route.params.missionId || '') === project.missionId) {
      await router.replace({ path: '/chat', query: { workspace: 'agent' } })
    }
  } catch (error: unknown) {
    ElMessage.error(sidebarMissionMutationError(error, '删除'))
  }
}

const editSidebarConversation = async (conversationOverride?: Conversation) => {
  const target = sidebarActionMenu.target
  const conversation = conversationOverride || (target?.kind === 'chat' ? target.conversation : null)
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
  const conversation = conversationOverride || (target?.kind === 'chat' ? target.conversation : null)
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

const handleSidebarActionMenuOutside = (event: MouseEvent) => {
  const target = event.target as Node | null
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
    if (route.path.startsWith('/chat')) lastChatRoute.value = fullPath
    else if (!isMissionWorkspacePath(route.path) && chatNavOpen.value) closeChatPanel()
    if (isAcgPath(route.path)) {
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
    const workspaceChanged = workspaceMode.value !== workspace
    workspaceMode.value = workspace
    localStorage.setItem(WORKSPACE_MODE_KEY, workspace)
    if (workspaceChanged && chatNavOpen.value) void loadRecentConversations()
  },
  { immediate: true }
)

const selectWorkspaceMode = (mode: WorkspaceMode) => {
  if (workspaceMode.value === mode) return
  closeSidebarActionMenu()
  workspaceMode.value = mode
  localStorage.setItem(WORKSPACE_MODE_KEY, mode)
  window.dispatchEvent(new CustomEvent('workspace-mode-change', { detail: { mode } }))
  void loadRecentConversations()
  void router.replace({
    path: '/chat',
    query: { workspace: mode, newConversation: '1' }
  })
}

// Immersive mode: keep landing auth immersive without a standalone login page.
const isImmersive = computed(() => {
  const path = route.path
  return path === '/' && route.query.auth === '1'
})

const showNavigation = computed(() => !isImmersive.value && !route.meta.hideNavigation)

const usesDrawerNavigation = computed(() => {
  return showNavigation.value && isMobileViewport.value
})

const userIdentityActionLabel = computed(() => {
  if (mainSidebarCompact.value) return '展开侧边栏'
  return '打开用户中心'
})

const openUserProfile = () => {
  void router.push('/user')
}

const expandPrimarySidebar = () => {
  // If the chat sub-panel is occupying the extra sidebar width, close it first
  // so the primary navigation can expand back to its normal width.
  if (secondaryNavOpen.value) closeChatPanel()
  if (!sidebarCollapsed.value) return

  sidebarCollapsed.value = false
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, '0')
}

const handleUserIdentityClick = () => {
  if (usesDrawerNavigation.value) {
    simpleNavOpen.value = false
    openUserProfile()
    return
  }

  if (mainSidebarCompact.value) {
    expandPrimarySidebar()
    return
  }

  openUserProfile()
}

const toggleSidebar = () => {
  if (secondaryNavOpen.value) {
    closeChatPanel()
    closeAcgPanel()
    return
  }
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed.value ? '1' : '0')
}

const handleTopChromeMenu = () => {
  if (usesDrawerNavigation.value) {
    simpleNavOpen.value = true
    return
  }
  toggleSidebar()
}

const handleTopChromeNavigate = (path: string) => {
  void router.push(path)
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

const handleViewportChange = (event: MediaQueryListEvent) => {
  isMobileViewport.value = event.matches
  if (!event.matches) simpleNavOpen.value = false
}

const isRouteScrollable = computed(() => {
  const path = route.path
  return (
    path.startsWith('/history') ||
    path.startsWith('/agentos/resources') ||
    path.startsWith('/rag') ||
    path.startsWith('/voice-chat')
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
      // 服务端撤销未确认时不得用成功样式显示"已退出"
      if (result.serverRevoked) {
        ElMessage.success(result.message || '退出登录成功')
      } else {
        ElMessage.warning(result.message || '本机已退出，服务端撤销未确认')
      }
      await router.replace(isDesktop() ? { path: '/login' } : { path: '/', query: { auth: '1', redirect: '/chat' } })
    } else {
      ElMessage.error(result.message || '退出登录失败')
    }
  } catch (error) {
    if (error === 'cancel') return
    console.error('退出登录失败:', error)
    ElMessage.error('退出登录失败，请重试')
  }
}

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
  mobileMediaQuery.addEventListener('change', handleViewportChange)
  // 应用级全局快捷键（Ctrl+B / Ctrl+R / Alt+方向 / F1），窗口级 F11/F12 在 Electron Main。
  disposeAppKeyboardShortcuts = initAppKeyboardShortcuts({
    desktop: isDesktop(),
    toggleSidebar,
    historyBack: () => router.back(),
    historyForward: () => router.forward(),
    onShowShortcuts: () => { shortcutsDialogVisible.value = true }
  })
  if (chatNavOpen.value) void loadRecentConversations()
  if (localStorage.getItem('userId')) void userStore.loadCurrentUser()
  void workflowRunsStore.bootstrap()
})

onUnmounted(() => {
  conversationLoadController?.abort()
  stopSidebarResize()
  stopChatPanelResize()
  disposeAppKeyboardShortcuts?.()
  disposeAppKeyboardShortcuts = null
  window.removeEventListener('history-refresh', handleHistoryRefresh)
  window.removeEventListener('acg-runs-refresh', handleHistoryRefresh)
  window.removeEventListener('conversation-workspace-change', handleConversationWorkspaceChange)
  window.removeEventListener('dragover', guardNativeFileDrop)
  window.removeEventListener('drop', guardNativeFileDrop)
  document.removeEventListener('mousedown', handleSidebarActionMenuOutside)
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
  transition: width 0.22s var(--ease-out);
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
  box-sizing: border-box;
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
  gap: 6px;
  border-bottom: 1px solid var(--sidebar-border);
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

.menu-group-title {
  box-sizing: border-box;
  height: 33px;
  padding: 14px 16px 6px;
  font-family: var(--font-sans);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-disabled);
  letter-spacing: 0.04em;
  text-transform: none;
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

.chat-nav-label {
  min-width: 0;
  flex: 1;
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
  padding: 10px 10px 12px;
  margin-top: auto;
  border-top: 0;
  background: color-mix(in srgb, var(--bg-sidebar) 86%, var(--bg-app));
}

.sidebar-settings-menu {
  flex: 0 0 auto;
  margin-top: 4px;
}

.sidebar-settings-menu :deep(.el-menu-item) {
  margin-bottom: 0;
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

.user-identity,
.user-logout {
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

.user-info {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.user-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}

.user-status {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 10px;
  color: var(--text-secondary);
  line-height: 1.2;
}

.user-status::before {
  content: '●';
  margin-right: 4px;
  color: var(--success);
  font-size: 7px;
  vertical-align: 1px;
}

.user-logout {
  width: 32px;
  height: 32px;
  flex: 0 0 32px;
  display: grid;
  place-items: center;
  border: 1px solid transparent;
  border-radius: 7px;
  color: var(--text-secondary);
  font-size: 16px;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease;
}

.user-identity:hover .user-name,
.user-logout:hover {
  color: var(--danger);
}

.user-logout:hover { border-color: color-mix(in srgb, var(--danger) 32%, var(--sidebar-border)); background: var(--danger-fade); }

.user-identity:focus-visible,
.user-logout:focus-visible {
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
  justify-content: flex-start;
}

.drawer-close {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 30px;
  padding: 0 8px;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  border: 0;
  border-radius: 5px;
  background: transparent;
  cursor: pointer;
}

.drawer-close:hover {
  color: var(--primary-color);
  background: var(--primary-fade);
}

.drawer-close:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 1px;
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
.docked-workspace-shell .workspace-switch { border: 0; box-shadow: none; }
.docked-workspace-shell .chat-panel-enter-active,
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
  width: 6px;
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

.workspace-switch {
  margin: 0 2px 10px;
  border-color: var(--border-light);
  background: color-mix(in srgb, var(--bg-app) 76%, var(--bg-sidebar));
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--text-primary) 5%, transparent);
}

.workspace-switch-btn.active {
  background: var(--bg-panel);
  color: var(--text-primary);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3), inset 0 1px 0 color-mix(in srgb, var(--text-primary) 6%, transparent);
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

</style>
