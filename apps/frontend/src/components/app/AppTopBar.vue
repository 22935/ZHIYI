<template>
  <header
    class="app-topbar is-rail-collapsed"
    :class="{ 'is-desktop-shell': desktopShell }"
    v-bind="dragRegionProps"
    aria-label="应用工作栏"
  >
    <!-- 拖动区判定只认被点中的元素：网格包裹层必须自身带 drag-region，
         否则顶栏空白处（含窗口控件两侧）按下去 target 落在包裹层上，窗口拖不动 -->
    <div class="app-topbar__left" v-bind="dragRegionProps">
      <div class="app-topbar__brand-zone" v-bind="dragRegionProps">
        <span class="app-topbar__logo" aria-hidden="true">
          <img src="/logo.webp" alt="" />
        </span>
      </div>

      <nav ref="menuLinksRef" class="app-topbar__menu-links" aria-label="工作台菜单" v-bind="dragRegionProps">
        <div ref="projectsMenuItem" class="app-topbar__menu-item" v-bind="dragRegionProps">
          <button
            type="button"
            data-menu-trigger
            aria-haspopup="menu"
            :aria-expanded="projectsMenuOpen"
            :class="{ 'is-open': projectsMenuOpen }"
            @click="toggleProjectsMenu"
          >项目</button>
          <div v-if="projectsMenuOpen" class="app-topbar__dropdown" role="menu" aria-label="项目操作">
            <button type="button" role="menuitem" @click="selectProjectsMenuItem('/agentos/missions/new')">
              <el-icon aria-hidden="true"><Plus /></el-icon>
              <span class="app-topbar__dropdown-label">新建 Mission</span>
              <span class="app-topbar__dropdown-hint">创建新的 Mission</span>
            </button>
            <button type="button" role="menuitem" @click="selectProjectsMenuItem('/agentos/acg')">
              <el-icon aria-hidden="true"><FolderOpened /></el-icon>
              <span class="app-topbar__dropdown-label">打开 Mission</span>
              <span class="app-topbar__dropdown-hint">浏览全部工程项目</span>
            </button>

            <div class="app-topbar__dropdown-rule" role="separator"></div>
            <div
              class="app-topbar__submenu-anchor"
              @mouseenter="openRecentSubmenu"
              @mouseleave="scheduleRecentSubmenuClose"
            >
              <button
                type="button"
                role="menuitem"
                data-menu-submenu-trigger
                aria-haspopup="menu"
                :aria-expanded="recentSubmenuOpen"
                @click="openRecentSubmenu"
              >
                <el-icon aria-hidden="true"><Clock /></el-icon>
                <span class="app-topbar__dropdown-label">最近 Mission</span>
                <el-icon class="app-topbar__submenu-chevron" aria-hidden="true"><ArrowRight /></el-icon>
              </button>
              <div
                v-if="recentSubmenuOpen"
                class="app-topbar__dropdown app-topbar__dropdown--sub"
                role="menu"
                aria-label="最近 Mission"
                @mouseenter="openRecentSubmenu"
                @mouseleave="scheduleRecentSubmenuClose"
              >
                <p v-if="recentMissionsLoading" class="app-topbar__dropdown-note">正在加载任务…</p>
                <p v-else-if="recentMissionsError" class="app-topbar__dropdown-note">任务列表不可用：{{ recentMissionsError }}</p>
                <p v-else-if="!recentMissions.length" class="app-topbar__dropdown-note">还没有 Mission，点「新建 Mission」开始。</p>
                <button
                  v-for="mission in recentMissions"
                  :key="mission.missionId"
                  type="button"
                  role="menuitem"
                  :title="missionTitle(mission)"
                  @click="openRecentMission(mission)"
                >
                  <el-icon aria-hidden="true"><Memo /></el-icon>
                  <span class="app-topbar__dropdown-label">{{ missionTitle(mission) }}</span>
                  <span class="app-topbar__dropdown-hint">{{ mission.runCount }} 次运行</span>
                </button>
                <div v-if="recentMissions.length" class="app-topbar__dropdown-rule" role="separator"></div>
                <button v-if="recentMissions.length" type="button" role="menuitem" @click="selectProjectsMenuItem('/agentos/acg')">
                  <el-icon aria-hidden="true"><FolderOpened /></el-icon>
                  <span class="app-topbar__dropdown-label">更多…</span>
                  <span class="app-topbar__dropdown-hint">浏览全部工程项目</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <button
          v-for="(item, index) in plainMenuItems"
          :key="item.path"
          type="button"
          data-menu-item
          :class="{ 'is-overflowed': index >= plainMenuItems.length - overflowCount }"
          @click="emit('navigate', item.path)"
        >{{ item.label }}</button>
        <div v-if="overflowCount > 0" ref="moreMenuItem" class="app-topbar__menu-item" v-bind="dragRegionProps">
          <button
            type="button"
            aria-haspopup="menu"
            :aria-expanded="moreOpen"
            :class="{ 'is-open': moreOpen }"
            aria-label="更多菜单"
            title="更多菜单"
            @click="moreOpen = !moreOpen"
          >
            <el-icon aria-hidden="true"><MoreFilled /></el-icon>
          </button>
          <div v-if="moreOpen" class="app-topbar__dropdown" role="menu" aria-label="更多导航">
            <button
              v-for="item in overflowedMenuItems"
              :key="item.path"
              type="button"
              role="menuitem"
              @click="selectMenuItem(item.path)"
            >
              <span class="app-topbar__dropdown-label">{{ item.label }}</span>
            </button>
          </div>
        </div>
      </nav>
    </div>

    <div class="app-topbar__command" v-bind="dragRegionProps">
      <div class="app-topbar__history" role="group" aria-label="历史导航" v-bind="dragRegionProps">
        <button
          type="button"
          class="app-topbar__history-button"
          :disabled="!canGoBack"
          aria-label="上一步"
          title="上一步"
          @click="goBack"
        >
          <el-icon aria-hidden="true"><ArrowLeft /></el-icon>
        </button>
        <button
          type="button"
          class="app-topbar__history-button"
          :disabled="!canGoForward"
          aria-label="下一步"
          title="下一步"
          @click="goForward"
        >
          <el-icon aria-hidden="true"><ArrowRight /></el-icon>
        </button>
      </div>
      <div
        class="app-command-center"
        :class="{ 'is-focused': commandFocused }"
        role="search"
        aria-label="应用导航"
      >
        <el-icon class="app-command-center__icon" aria-hidden="true"><Search /></el-icon>
        <input
          ref="commandInput"
          v-model="query"
          type="search"
          autocomplete="off"
          placeholder="搜索任务、步骤、运行或命令"
          aria-label="搜索任务、步骤、运行或命令"
          aria-keyshortcuts="Control+K Meta+K"
          aria-autocomplete="list"
          aria-controls="app-command-menu"
          :aria-expanded="commandFocused"
          @focus="openCommandMenu"
          @blur="commandFocused = false"
          @keydown="handleCommandKeydown"
          @keydown.esc="clearCommand"
        />
        <kbd aria-hidden="true">{{ commandShortcutLabel }}</kbd>
        <div
          v-if="commandFocused"
          id="app-command-menu"
          class="app-command-menu"
          role="listbox"
          aria-label="导航结果"
        >
          <button
            v-for="(command, index) in filteredCommands"
            :id="`app-command-option-${command.id}`"
            :key="command.id"
            class="app-command-option"
            :class="{ 'is-active': index === selectedCommandIndex }"
            type="button"
            role="option"
            :aria-selected="index === selectedCommandIndex"
            @mousedown.prevent
            @click="selectCommand(command)"
          >
            <span class="app-command-option__label">{{ command.label }}</span>
            <span class="app-command-option__description">{{ command.description }}</span>
          </button>
          <p v-if="!filteredCommands.length" class="app-command-empty">没有匹配的导航项</p>
          <div v-else class="app-command-menu__footer">
            <span>{{ query.trim() ? '匹配导航' : '快速导航' }}</span>
            <span class="app-command-menu__keys" aria-hidden="true">
              <kbd>↑</kbd><kbd>↓</kbd><span>选择</span>
              <kbd>Enter</kbd><span>打开</span>
              <kbd>Esc</kbd><span>关闭</span>
            </span>
          </div>
        </div>
      </div>
    </div>

    <div class="app-topbar__right" v-bind="dragRegionProps">
      <button
        v-if="desktopShell"
        class="app-topbar__terminal"
        :class="{ 'is-active': terminalVisible }"
        type="button"
        :aria-pressed="terminalVisible"
        aria-label="切换内置终端"
        title="切换内置终端 · Ctrl+`"
        @click="toggleDesktopTerminal"
      >
        <span class="app-topbar__terminal-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="m4 17 6-6-6-6" />
            <path d="M12 19h8" />
          </svg>
        </span>
        <span class="app-topbar__terminal-label">终端</span>
      </button>
      <DesktopWindowControls v-if="desktopShell" />
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArrowLeft,
  ArrowRight,
  Clock,
  FolderOpened,
  Memo,
  MoreFilled,
  Plus,
  Search
} from '@element-plus/icons-vue'
import DesktopWindowControls from '@window-controls'
import { isDesktop, platform } from '@/platform'
import { agentosApi, type MissionListItem } from '@/services/api/agentos'
import { plainMissionTitle } from '@/utils/missionTitle'
import { terminalVisible, toggleDesktopTerminal } from '@/composables/useDesktopTerminal'
import { commands as commandRegistry } from '@/workbench/core/commands'

// Desktop 构建下本栏即窗口标题栏（decorations:false）：
// 空白区域承担拖拽与双击最大化，右侧挂窗口控制；
// Web 构建通过 @window-controls 别名拿到空占位，不含任何桌面 API。
const desktopShell = isDesktop()
const dragRegionProps = platform.dragRegionProps

const emit = defineEmits<{
  home: []
  navigate: [path: string]
}>()

// 「项目」按 VS Code 菜单模式工作：单击打开下拉，同时主界面落到预加载屏；
// 实际内容（新建/打开 Mission）从菜单项进入。
const projectsMenuOpen = ref(false)
const projectsMenuItem = ref<HTMLElement | null>(null)

const toggleProjectsMenu = () => {
  if (projectsMenuOpen.value) {
    projectsMenuOpen.value = false
    return
  }
  projectsMenuOpen.value = true
  emit('navigate', '/agentos/projects')
}

const selectProjectsMenuItem = (path: string) => {
  projectsMenuOpen.value = false
  emit('navigate', path)
}

const handleGlobalPointerdown = (event: PointerEvent) => {
  if (!projectsMenuOpen.value && !moreOpen.value) return
  const target = event.target
  if (target instanceof Node) {
    if (projectsMenuOpen.value && projectsMenuItem.value?.contains(target)) return
    if (moreOpen.value && moreMenuItem.value?.contains(target)) return
  }
  projectsMenuOpen.value = false
  moreOpen.value = false
  recentSubmenuOpen.value = false
}

// 左侧菜单溢出收纳：命令中心恒居中后，左列空间不足时把尾部菜单项收进「···」。
// 溢出项 absolute+visibility:hidden 留在 DOM 里，offsetWidth 仍可测，避免测量与显隐互相打架。
const plainMenuItems = [
  { label: '资源', path: '/agentos/resources' },
  { label: '知识库', path: '/rag' },
  { label: '历史记录', path: '/history' },
  { label: '运行记忆', path: '/agentos/memory' }
]
const menuLinksRef = ref<HTMLElement | null>(null)
const moreMenuItem = ref<HTMLElement | null>(null)
const moreOpen = ref(false)
const overflowCount = ref(0)
const overflowedMenuItems = computed(() => plainMenuItems.slice(plainMenuItems.length - overflowCount.value))

const MENU_GAP_PX = 1
const MORE_RESERVE_PX = 40
const measureMenuOverflow = () => {
  const nav = menuLinksRef.value
  if (!nav) return
  const available = nav.clientWidth
  if (available <= 0) return
  const trigger = nav.querySelector<HTMLElement>('[data-menu-trigger]')
  const els = Array.from(nav.querySelectorAll<HTMLElement>('[data-menu-item]'))
  if (!els.length) return
  let used = trigger?.offsetWidth ?? 0
  let fit = 0
  for (let i = 0; i < els.length; i++) {
    const next = used + MENU_GAP_PX + els[i].offsetWidth
    const limit = i < els.length - 1 ? next + MENU_GAP_PX + MORE_RESERVE_PX : next
    if (limit <= available) {
      used = next
      fit = i + 1
    } else break
  }
  const nextCount = els.length - fit
  if (nextCount !== overflowCount.value) overflowCount.value = nextCount
}
const selectMenuItem = (path: string) => {
  moreOpen.value = false
  emit('navigate', path)
}

// 「项目」下拉的任务区：最近 Mission 平铺直列（参考编辑器「打开最近的文件」形式），
// 点一条直接进工作区（带最近 Run）。
// 读取速度：顶栏挂载后空闲预取 + 30s 缓存；展开时先渲染缓存再后台静默刷新，
// 仅首次无缓存才显示加载行。
const RECENT_MISSION_LIMIT = 10
const MISSIONS_CACHE_TTL_MS = 30_000
let missionsCache: MissionListItem[] = []
let missionsCacheAt = 0
let missionsInflight: Promise<void> | null = null
let topBarDisposed = false
const recentMissions = ref<MissionListItem[]>([])
const recentMissionsLoading = ref(false)
const recentMissionsError = ref('')
let recentMissionsController: AbortController | null = null

const missionTitle = (mission: MissionListItem) => plainMissionTitle(mission.title)
const missionWorkspacePath = (mission: MissionListItem) =>
  mission.latestRunId
    ? `/agentos/missions/${mission.missionId}/workspace?runId=${mission.latestRunId}`
    : `/agentos/missions/${mission.missionId}/workspace`

const loadRecentMissions = async (options: { force?: boolean } = {}) => {
  if (missionsInflight) return missionsInflight
  const cacheFresh = missionsCacheAt > 0 && Date.now() - missionsCacheAt < MISSIONS_CACHE_TTL_MS
  if (!options.force && cacheFresh) return
  const controller = new AbortController()
  recentMissionsController = controller
  const request = (async () => {
    if (!recentMissions.value.length) recentMissionsLoading.value = true
    recentMissionsError.value = ''
    try {
      const response = await agentosApi.listMissions(
        { page: 1, pageSize: RECENT_MISSION_LIMIT },
        { signal: controller.signal }
      )
      if (controller.signal.aborted) return
      missionsCache = response.items
      missionsCacheAt = Date.now()
      recentMissions.value = response.items
    } catch (error: any) {
      if (controller.signal.aborted || error?.name === 'CanceledError' || error?.name === 'AbortError') return
      recentMissionsError.value = error?.response?.data?.detail || error?.message || '请稍后重试。'
    } finally {
      if (recentMissionsController === controller && !controller.signal.aborted) {
        recentMissionsLoading.value = false
      }
    }
  })()
  missionsInflight = request.finally(() => {
    missionsInflight = null
  })
  return missionsInflight
}

watch(projectsMenuOpen, open => {
  if (!open) {
    recentSubmenuOpen.value = false
    return
  }
  if (missionsCache.length) recentMissions.value = missionsCache
  void loadRecentMissions()
})

const openRecentMission = (mission: MissionListItem) => {
  projectsMenuOpen.value = false
  emit('navigate', missionWorkspacePath(mission))
}

// 「最近 Mission」二级飞出框：VS Code 子菜单式，悬停即开、移出延迟关、点击也可开
const recentSubmenuOpen = ref(false)
let submenuCloseTimer: number | null = null

const openRecentSubmenu = () => {
  if (submenuCloseTimer !== null) {
    window.clearTimeout(submenuCloseTimer)
    submenuCloseTimer = null
  }
  recentSubmenuOpen.value = true
  void loadRecentMissions()
}

const scheduleRecentSubmenuClose = () => {
  if (submenuCloseTimer !== null) window.clearTimeout(submenuCloseTimer)
  submenuCloseTimer = window.setTimeout(() => {
    submenuCloseTimer = null
    recentSubmenuOpen.value = false
  }, 160)
}

const query = ref('')
const commandFocused = ref(false)
const commandInput = ref<HTMLInputElement | null>(null)
const selectedCommandIndex = ref(0)
const commandShortcutLabel = typeof navigator !== 'undefined' && /Mac|iPhone|iPad|iPod/.test(navigator.platform)
  ? '⌘ K'
  : 'Ctrl K'

type CommandItem = {
  id: string
  label: string
  description: string
  path: string
  keywords: string
}

const commands: CommandItem[] = [
  { id: 'projects', label: '项目', description: 'Agent 项目入口（预加载屏）', path: '/agentos/projects', keywords: '项目 任务 mission agent acg' },
  { id: 'new-mission', label: '新建任务', description: '创建一个新的 Mission', path: '/agentos/missions/new', keywords: '新建 任务 mission create' },
  { id: 'open-mission', label: '打开 Mission', description: '浏览全部工程项目', path: '/agentos/acg', keywords: '打开 mission 项目 工程 列表 open project' },
  { id: 'history', label: '历史记录', description: '查看对话、文件与 ACG 运行记录', path: '/history', keywords: '历史 记录 运行 history run' },
  { id: 'resources', label: '资源中心', description: '管理模型、角色与知识资源', path: '/agentos/resources', keywords: '资源 模型 角色 知识 resource' },
  { id: 'rag', label: '知识库', description: '智能检索与文档管理', path: '/rag', keywords: '知识库 rag 检索 文档 knowledge' },
  { id: 'memory', label: '运行记忆', description: '查看执行过程中的运行记忆', path: '/agentos/memory', keywords: '记忆 memory 执行' },
  { id: 'chat', label: '对话', description: '打开 Chat 工作台', path: '/chat', keywords: '对话 chat 聊天' },
  { id: 'settings', label: '设置', description: '管理应用设置', path: '/settings', keywords: '设置 配置 settings' }
]

const filteredCommands = computed(() => {
  const terms = query.value.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean)
  if (!terms.length) return commands

  return commands.filter(command => {
    const searchable = `${command.label} ${command.description} ${command.keywords}`.toLocaleLowerCase()
    return terms.every(term => searchable.includes(term))
  })
})

const selectedCommand = computed(() => filteredCommands.value[selectedCommandIndex.value])

const clearCommand = () => {
  query.value = ''
  commandFocused.value = false
  commandInput.value?.blur()
}

const focusCommand = () => {
  selectedCommandIndex.value = 0
  commandInput.value?.focus()
  commandInput.value?.select()
}

const openCommandMenu = () => {
  commandFocused.value = true
  selectedCommandIndex.value = 0
}

const selectCommand = (command: CommandItem) => {
  query.value = ''
  commandFocused.value = false
  commandInput.value?.blur()
  emit('navigate', command.path)
}

const handleCommandKeydown = (event: KeyboardEvent) => {
  if (!filteredCommands.value.length) return

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    selectedCommandIndex.value = (selectedCommandIndex.value + 1) % filteredCommands.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    selectedCommandIndex.value = (selectedCommandIndex.value - 1 + filteredCommands.value.length) % filteredCommands.value.length
  } else if (event.key === 'Enter' && selectedCommand.value) {
    event.preventDefault()
    selectCommand(selectedCommand.value)
  }
}

const handleGlobalKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && (projectsMenuOpen.value || moreOpen.value || recentSubmenuOpen.value)) {
    projectsMenuOpen.value = false
    moreOpen.value = false
    recentSubmenuOpen.value = false
  }
}

// Ctrl/Cmd+K 注册为工作台命令：派发、速查浮层与后续命令面板共用同一份定义。
const toggleCommandPalette = () => {
  if (commandFocused.value) {
    clearCommand()
  } else {
    focusCommand()
  }
}
let disposeCommandPalette: (() => void) | null = null

watch(query, () => {
  selectedCommandIndex.value = 0
})

// 历史导航：vue-router 不暴露 canGoBack/canGoForward，用写入 history.state 的
// position 对账——current 为当前栈位，furthest 记录本次会话到过的最深处。
const router = useRouter()
const currentPosition = ref(0)
const furthestPosition = ref(0)

const syncHistoryPosition = () => {
  const state = router.options.history.state as { position?: number } | null
  const position = Number(state?.position ?? 0)
  currentPosition.value = position
  furthestPosition.value = Math.max(furthestPosition.value, position)
}

const canGoBack = computed(() => currentPosition.value > 0)
const canGoForward = computed(() => currentPosition.value < furthestPosition.value)
const goBack = () => router.back()
const goForward = () => router.forward()

let menuResizeObserver: ResizeObserver | null = null
const stopTrackingHistory = router.afterEach((to) => {
  // 「项目」单击=开菜单+跳预加载屏：抵达 hub 的这次导航不收回刚打开的菜单，
  // 其余任何路由变化都收起全部下拉。
  if (!projectsMenuOpen.value || to.path !== '/agentos/projects') {
    projectsMenuOpen.value = false
  }
  moreOpen.value = false
  recentSubmenuOpen.value = false
  syncHistoryPosition()
})
onMounted(() => {
  syncHistoryPosition()
  measureMenuOverflow()
  if (typeof ResizeObserver !== 'undefined' && menuLinksRef.value) {
    menuResizeObserver = new ResizeObserver(measureMenuOverflow)
    menuResizeObserver.observe(menuLinksRef.value)
  }
  void document.fonts?.ready.then(() => measureMenuOverflow())
  // 空闲预取最近 Mission：用户点开「项目」前缓存已就绪
  topBarDisposed = false
  if (typeof window.requestIdleCallback === 'function') {
    window.requestIdleCallback(() => {
      if (!topBarDisposed) void loadRecentMissions()
    })
  } else {
    window.setTimeout(() => {
      if (!topBarDisposed) void loadRecentMissions()
    }, 500)
  }
  window.addEventListener('keydown', handleGlobalKeydown, { capture: true })
  window.addEventListener('pointerdown', handleGlobalPointerdown, { capture: true })
  disposeCommandPalette = commandRegistry.register({
    id: 'app.commandPalette.toggle',
    title: '命令中心',
    category: '通用',
    order: 10,
    keys: ['mod+k'],
    // 顶栏有自己的输入框：命令中心在输入焦点下仍可切换，浏览器里也一样。
    editableSafe: true,
    // 终端聚焦时仍允许切到命令中心（与旧实现一致：旧监听没有终端让位）。
    terminalSafe: true,
    run: toggleCommandPalette
  })
})
onBeforeUnmount(() => {
  topBarDisposed = true
  stopTrackingHistory()
  disposeCommandPalette?.()
  disposeCommandPalette = null
  menuResizeObserver?.disconnect()
  menuResizeObserver = null
  recentMissionsController?.abort()
  recentMissionsController = null
  if (submenuCloseTimer !== null) {
    window.clearTimeout(submenuCloseTimer)
    submenuCloseTimer = null
  }
  window.removeEventListener('keydown', handleGlobalKeydown, { capture: true })
  window.removeEventListener('pointerdown', handleGlobalPointerdown, { capture: true })
})
</script>

<style scoped>
.app-topbar {
  position: relative;
  z-index: 20;
  flex: 0 0 36px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  grid-template-areas: 'left center right';
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 36px;
  padding: 0 8px;
  color: var(--app-topbar-text);
  background: var(--app-topbar-bg);
  border-bottom: 0;
}

/* 角落细化：紧凑图标栏那一列上方不画下缘线，线从图标栏右缘（COLLAPSED_SIDEBAR_WIDTH=48，App.vue）开始，对齐 VS Code 标题栏。 */
.app-topbar.is-rail-collapsed {
  border-bottom-color: transparent;
}
.app-topbar.is-rail-collapsed::after {
  content: '';
  position: absolute;
  left: 48px;
  right: 0;
  bottom: 0;
  height: 1px;
  background: transparent;
}

/* Desktop 无边框窗口：关闭按钮必须贴住窗口右缘（Fitts's Law）。 */
.app-topbar.is-desktop-shell {
  padding-right: 0;
}

.app-topbar__brand-zone,
.app-topbar__menu-links {
  display: flex;
  align-items: center;
}

.app-topbar__brand-zone {
  min-width: 0;
}

/* 对称三列：左右 1fr 等宽，中列（历史导航+命令中心）恒居窗口正中；
   左列放不下时菜单项收进「···」而不是挤压中列。 */
.app-topbar__left {
  grid-area: left;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.app-topbar__right {
  grid-area: right;
  /* 窗口控制按钮内部依赖 height:100% 吃满顶栏行高，
     包装层必须 align-self:stretch 提供确定的 36px 参照，否则按钮塌成图标高。 */
  align-self: stretch;
  display: flex;
  align-items: stretch;
  justify-content: flex-end;
  min-width: 0;
}

/* 品牌标是纯识别物不承接点击（侧边栏固定图标窄栏，无导航开合动作）；
   点击语义退役后此区域完全交还窗口拖拽。 */
.app-command-center:focus-within {
  outline: 2px solid var(--app-topbar-focus-ring);
  outline-offset: 1px;
}

.app-topbar__logo {
  position: relative;
  display: grid;
  flex: 0 0 24px;
  place-items: center;
  width: 24px;
  height: 24px;
  overflow: visible;
  background: var(--app-topbar-logo-bg);
  border: 1px solid var(--app-topbar-border);
  border-radius: 7px;
  box-shadow: 0 1px 2px color-mix(in srgb, var(--app-topbar-text) 8%, transparent), 0 0 0 1px color-mix(in srgb, var(--app-topbar-text) 18%, transparent) inset;
  transition: border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

.app-topbar__logo img {
  width: 18px;
  height: 18px;
  object-fit: contain;
}

.app-topbar__menu-links {
  gap: 1px;
  min-width: 0;
}

/* 溢出收纳的菜单项：移出排版流但保留可测宽度（visibility 不参与布局） */
.app-topbar__menu-links button.is-overflowed {
  position: absolute;
  visibility: hidden;
  pointer-events: none;
}

.app-topbar__menu-links button {
  height: 28px;
  padding: 0 8px;
  color: var(--app-topbar-muted);
  font: inherit;
  font-family: var(--font-serif);
  font-size: 13px;
  font-weight: 520;
  letter-spacing: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}

.app-topbar__menu-links button:hover,
.app-topbar__menu-links button:focus-visible {
  color: var(--app-topbar-text);
  background: var(--app-topbar-hover);
}

.app-topbar__menu-links button:active {
  transform: scale(0.98);
}

.app-topbar__menu-links button:focus-visible {
  outline: 2px solid var(--app-topbar-focus-ring);
  outline-offset: 1px;
}

.app-topbar__menu-links button.is-open {
  color: var(--app-topbar-text);
  background: var(--app-topbar-hover);
}

/* 「项目」VS Code 式下拉：与右侧命令面板同一套面板配色 */
.app-topbar__menu-item {
  position: relative;
  display: flex;
  align-items: center;
}

.app-topbar__dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  z-index: 60;
  display: grid;
  gap: 2px;
  min-width: 236px;
  padding: 5px;
  color: var(--app-topbar-text);
  background: var(--app-topbar-input-bg-hover);
  border: 1px solid var(--app-topbar-input-border);
  border-radius: 9px;
  box-shadow: 0 12px 28px color-mix(in srgb, var(--app-topbar-text) 18%, transparent);
}

/* 二级飞出框：挂在「最近 Mission」行右侧；overflow 不裁剪父面板才能完整浮出 */
.app-topbar__submenu-anchor {
  position: relative;
  display: block;
}

.app-topbar__dropdown--sub {
  left: calc(100% + 6px);
  top: -6px;
  min-width: 264px;
  max-height: min(430px, calc(100vh - 96px));
  overflow-y: auto;
}

.app-topbar__submenu-chevron {
  color: var(--app-topbar-muted);
  font-size: 12px;
}

.app-topbar__dropdown-rule {
  height: 1px;
  margin: 4px 3px;
  background: var(--app-topbar-border);
}

.app-topbar__dropdown-section {
  margin: 2px 9px 1px;
  color: var(--app-topbar-muted);
  font-size: 10px;
  letter-spacing: .08em;
}

.app-topbar__dropdown-note {
  margin: 0;
  padding: 7px 9px 5px;
  color: var(--app-topbar-muted);
  font-size: 11px;
}

.app-topbar__dropdown button {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  min-height: 32px;
  padding: 5px 9px;
  color: inherit;
  font: inherit;
  font-size: 12px;
  text-align: left;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
}

.app-topbar__dropdown button:hover,
.app-topbar__dropdown button:focus-visible {
  background: var(--app-topbar-active);
}

.app-topbar__dropdown button:focus-visible {
  outline: 2px solid var(--app-topbar-focus-ring);
  outline-offset: -2px;
}

.app-topbar__dropdown .el-icon {
  color: var(--app-topbar-muted);
  font-size: 14px;
}

.app-topbar__dropdown-label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-topbar__dropdown-hint {
  overflow: hidden;
  color: var(--app-topbar-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-topbar__command {
  grid-area: center;
  justify-self: center;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
}

.app-topbar__history {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 2px;
}

.app-topbar__history-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  padding: 0;
  color: var(--app-topbar-muted);
  font-size: 15px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  transition: background-color 140ms ease, color 140ms ease;
}

.app-topbar__history-button:hover:not(:disabled),
.app-topbar__history-button:focus-visible:not(:disabled) {
  color: var(--app-topbar-text);
  background: var(--app-topbar-hover);
}

.app-topbar__history-button:focus-visible {
  outline: 2px solid var(--app-topbar-focus-ring);
  outline-offset: 1px;
}

.app-topbar__history-button:active:not(:disabled) {
  transform: scale(0.96);
}

.app-topbar__history-button:disabled {
  opacity: 0.38;
  cursor: default;
}

.app-command-center {
  position: relative;
  display: flex;
  align-items: center;
  width: clamp(200px, 24vw, 360px);
  height: 26px;
  flex: 0 1 auto;
  min-width: 0;
  padding: 0 8px;
  color: var(--app-topbar-text);
  background: var(--app-topbar-input-bg);
  border: 1px solid var(--app-topbar-input-border);
  border-radius: 9px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.22);
  transition: border-color 160ms ease, background-color 160ms ease, box-shadow 160ms ease;
}

.app-command-center:hover,
.app-command-center.is-focused {
  background: var(--app-topbar-input-bg-hover);
  border-color: var(--app-topbar-focus-border);
}

.app-command-center.is-focused {
  box-shadow: 0 2px 6px color-mix(in srgb, var(--app-topbar-text) 8%, transparent), 0 0 0 3px var(--app-topbar-focus-ring), 0 0 0 1px color-mix(in srgb, var(--app-topbar-text) 16%, transparent) inset;
}

.app-command-center__icon {
  flex: 0 0 auto;
  margin-right: 6px;
  font-size: 14px;
}

.app-command-center input {
  min-width: 0;
  flex: 1;
  height: 100%;
  color: var(--app-topbar-text);
  font: inherit;
  font-size: 13px;
  background: transparent;
  border: 0;
  outline: 0;
}

.app-command-center input::placeholder {
  color: var(--app-topbar-muted);
  opacity: 0.84;
}

.app-command-center kbd {
  flex: 0 0 auto;
  min-width: 28px;
  padding: 2px 5px;
  color: var(--app-topbar-muted);
  font-family: var(--font-mono);
  font-size: 9px;
  line-height: 1.2;
  text-align: center;
  background: var(--app-topbar-kbd-bg);
  border: 1px solid var(--app-topbar-border);
  border-radius: 6px;
  box-shadow: 0 1px 1px color-mix(in srgb, var(--app-topbar-text) 5%, transparent);
}

.app-command-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: -1px;
  left: -1px;
  z-index: 50;
  display: grid;
  gap: 2px;
  max-height: min(360px, calc(100vh - 64px));
  overflow-y: auto;
  padding: 5px;
  color: var(--app-topbar-text);
  background: var(--app-topbar-input-bg-hover);
  border: 1px solid var(--app-topbar-input-border);
  border-radius: 8px;
  box-shadow: 0 12px 28px color-mix(in srgb, var(--app-topbar-text) 18%, transparent);
}

.app-command-option {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 16px;
  min-width: 0;
  min-height: 34px;
  padding: 6px 8px;
  color: inherit;
  text-align: left;
  border: 0;
  border-radius: 5px;
  background: transparent;
  cursor: pointer;
}

.app-command-option:hover,
.app-command-option:focus-visible,
.app-command-option.is-active {
  background: var(--app-topbar-active);
}

.app-command-option:focus-visible {
  outline: 2px solid var(--app-topbar-focus-ring);
  outline-offset: -2px;
}

.app-command-option__label {
  overflow: hidden;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-command-option__description {
  overflow: hidden;
  color: var(--app-topbar-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-command-empty {
  margin: 0;
  padding: 11px 8px;
  color: var(--app-topbar-muted);
  font-size: 11px;
  text-align: center;
}

.app-command-menu__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 4px 3px 0;
  padding: 7px 5px 2px;
  color: var(--app-topbar-muted);
  font-size: 10px;
  border-top: 1px solid var(--app-topbar-border);
}

.app-command-menu__keys {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.app-command-menu__keys kbd {
  min-width: 17px;
  padding: 2px 4px;
  color: var(--app-topbar-text);
  font-family: var(--font-mono);
  font-size: 9px;
  line-height: 1.1;
  text-align: center;
  background: var(--app-topbar-kbd-bg);
  border: 1px solid var(--app-topbar-border);
  border-radius: 3px;
}

@media (max-width: 860px) {
  .app-topbar__menu-links {
    display: none;
  }

  .app-topbar__command {
    width: min(calc(100vw - 210px), 320px);
  }
}

@media (max-width: 560px) {
  .app-topbar {
    padding: 0 7px;
  }

  .app-command-center {
    width: calc(100vw - 205px);
  }

  .app-command-center kbd {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .app-topbar__history-button,
  .app-command-center {
    transition: none;
  }
}

/* Screenshot refinement: keep the top chrome quiet and precise. */
.app-topbar__menu-links button {
  height: 26px;
  border-radius: 6px;
}

.app-command-center.is-focused {
  box-shadow: 0 0 0 3px var(--app-topbar-focus-ring), 0 2px 8px rgba(0, 0, 0, 0.26);
}
.app-topbar__terminal { display:inline-flex; align-self:center; align-items:center; gap:6px; flex:0 0 auto; height:26px; margin:0 8px 0 4px; padding:0 7px 0 5px; border:1px solid transparent; border-radius:6px; background:transparent; color:var(--app-topbar-muted,#858585); font:11px/1 var(--font-sans,system-ui,sans-serif); letter-spacing:.01em; white-space:nowrap; cursor:pointer; -webkit-app-region:no-drag; transition:background-color 160ms var(--ease-out,ease),border-color 160ms var(--ease-out,ease),color 160ms var(--ease-out,ease); }
.app-topbar__terminal-icon { display:grid; place-items:center; width:17px; height:17px; border:1px solid color-mix(in srgb,currentColor 9%,transparent); border-radius:5px; background:color-mix(in srgb,currentColor 7%,transparent); transition:background-color 160ms var(--ease-out,ease),border-color 160ms var(--ease-out,ease); }
.app-topbar__terminal-icon svg { width:10px; height:10px; }
.app-topbar__terminal-label { font-weight:500; }
.app-topbar__terminal:hover { color:var(--app-topbar-text,#ccc); background:var(--app-topbar-hover,#2a2d2e); border-color:color-mix(in srgb,var(--app-topbar-text,#ccc) 8%,transparent); }
.app-topbar__terminal:hover .app-topbar__terminal-icon { background:color-mix(in srgb,currentColor 11%,transparent); }
.app-topbar__terminal.is-active { color:var(--app-topbar-text,#ccc); background:color-mix(in srgb,var(--sem-running,#6ea8fe) 8%,transparent); border-color:color-mix(in srgb,var(--sem-running,#6ea8fe) 20%,transparent); }
.app-topbar__terminal.is-active .app-topbar__terminal-icon { color:var(--sem-running,#6ea8fe); background:color-mix(in srgb,var(--sem-running,#6ea8fe) 12%,transparent); border-color:color-mix(in srgb,var(--sem-running,#6ea8fe) 24%,transparent); }
.app-topbar__terminal:focus-visible { outline:2px solid var(--app-topbar-focus-ring,rgba(79,193,255,.34)); outline-offset:1px; }
@media(prefers-reduced-motion:reduce) { .app-topbar__terminal,.app-topbar__terminal-icon { transition:none; } }
</style>
