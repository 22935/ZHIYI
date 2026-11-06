import { createRouter, createWebHashHistory, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { authApi } from '@/services/api/auth'
import { isDesktop } from '@/platform'
import { ensureDesktopSession } from '@/platform/electron/session'

const normalizeRedirect = (redirect?: string) => {
  if (!redirect) return '/chat'
  if (!redirect.startsWith('/') || redirect.startsWith('//')) return '/chat'
  return redirect
}

const stringQuery = (value: unknown) => typeof value === 'string' ? value : undefined

const landingAuthQuery = (redirect?: unknown, from?: unknown) => ({
  auth: '1',
  redirect: normalizeRedirect(stringQuery(redirect)),
  ...(typeof from === 'string' ? { from } : {})
})

// Unauthenticated access to a protected route: web falls back to landing
// embedded auth, the desktop shell returns to the standalone login page.
const unauthRedirect = (fullPath: string) => isDesktop()
  ? `/login?redirect=${encodeURIComponent(fullPath)}`
  : { path: '/', query: landingAuthQuery(fullPath) }

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Landing',
    component: () => import('@/views/LandingView.vue'),
    meta: {
      title: '首页',
      requiresAuth: false
    }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    // Web presents auth embedded on the landing page; the desktop shell keeps
    // the standalone login surface with its own title-bar chrome.
    beforeEnter: to => (isDesktop()
      ? true
      : { path: '/', query: landingAuthQuery(to.query.redirect, to.query.from) }),
    meta: {
      title: '登录',
      requiresAuth: false
    }
  },
  {
    path: '/user',
    name: 'User',
    component: () => import('@/views/UserView.vue'),
    meta: {
      title: '用户中心',
      requiresAuth: true,
      hideNavigation: true
    }
  },
  {
    path: '/info',
    name: 'Info',
    component: () => import('@/views/InfoView.vue'),
    meta: {
      title: '信息入口',
      requiresAuth: true
    }
  },
  {
    path: '/history',
    name: 'History',
    // These workspace surfaces pull in graph and visualization libraries.
    // Load them only after navigation so the login shell does not ask Vite to
    // transform the entire authenticated workspace at startup. Chunk failures
    // remain covered by the one-shot router recovery below.
    component: () => import('@/views/HistoryView.vue'),
    meta: {
      title: '历史记录',
      requiresAuth: true
    }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: {
      title: '对话',
      requiresAuth: true
    }
  },
  {
    path: '/roles',
    name: 'Roles',
    redirect: to => ({ path: '/agentos/resources', query: to.query })
  },
  {
    path: '/settings',
    name: 'Settings',
    // Settings is the main route used to recover identity and client state.
    // It should remain available even when a deployed lazy chunk is stale.
    // 不挂 hideNavigation：设置页公用 AppTopBar（无边框窗口的拖拽区与窗口控件都在顶栏），
    // 页面内自建拖拽区实测无效，顶栏是唯一可靠拖拽面。
    component: () => import('@/views/SettingsView.vue'),
    meta: {
      title: '设置',
      requiresAuth: true
    }
  },
  {
    path: '/rag',
    name: 'RAG',
    component: () => import('@/views/RagView.vue'),
    meta: {
      title: '知识库查询',
      requiresAuth: true
    }
  },
  {
    path: '/federated-models',
    name: 'FederatedModelManagement',
    redirect: to => ({ path: '/agentos/resources', query: { ...to.query, tab: 'models' } })
  },
  {
    path: '/federated-learning',
    name: 'FederatedLearning',
    redirect: to => ({ path: '/agentos/resources', query: { ...to.query, tab: 'federated' } })
  },
  {
    path: '/federated-agent-workbench',
    name: 'FederatedAgentWorkbench',
    redirect: { path: '/chat', query: { workspace: 'agent' } }
  },
  {
    path: '/agentos-console',
    name: 'AgentOsConsole',
    redirect: to => ({ path: '/history', query: { ...to.query, tab: 'acg' } })
  },
  {
    path: '/agentos/acg',
    name: 'AcgVisualization',
    component: () => import('@/views/AcgEntryView.vue'),
    meta: {
      title: 'ACG 动态群体智能引擎',
      requiresAuth: true
    }
  },
  {
    path: '/agentos/projects',
    name: 'ProjectsHub',
    component: () => import('@/views/ProjectsHubView.vue'),
    meta: {
      title: '项目',
      requiresAuth: true
    }
  },
  {
    path: '/agentos/resources',
    name: 'ResourceCenter',
    component: () => import('@/views/ResourceCenterView.vue'),
    meta: {
      title: 'Resource Center',
      requiresAuth: true
    }
  },
  {
    path: '/agentos/memory',
    name: 'MemoryCenter',
    component: () => import('@/views/MemoryView.vue'),
    meta: {
      title: 'Run Memory',
      requiresAuth: true
    }
  },
  {
    path: '/agentos/missions/new',
    name: 'CreateMission',
    component: () => import('@/views/CreateMissionView.vue'),
    meta: {
      title: '新建任务',
      requiresAuth: true
    }
  },
  {
    path: '/agentos/missions/:missionId/workspace',
    name: 'MissionWorkspace',
    component: () => import('@/views/MissionWorkspaceView.vue'),
    meta: {
      title: 'Mission Project Workspace',
      requiresAuth: true
    }
  },
  {
    path: '/contract-clause-planner',
    name: 'ContractClausePlanner',
    redirect: {
      path: '/chat',
      query: { workspace: 'agent' }
    }
  }
]

const router = createRouter({
  // The desktop shell has no server fallback for deep links. Keep the
  // browser URL contract unchanged and use hashes only inside the desktop shell.
  history: isDesktop() ? createWebHashHistory() : createWebHistory(),
  routes
})

const ROUTE_CHUNK_RELOAD_KEY = 'kinlin:route-chunk-reload'
const isRouteChunkError = (error: unknown) => {
  const message = error instanceof Error ? error.message : String(error)
  return /Failed to fetch dynamically imported module|Importing a module script failed|Loading chunk .* failed|ChunkLoadError/i.test(message)
}

// A long-lived tab can keep an old index while a deployment replaces hashed
// route chunks. Retry the failed navigation once so a normal click recovers
// without asking the user to refresh manually, while avoiding a reload loop
// when the chunk is genuinely unavailable.
router.onError((error, to, from) => {
  if (!isRouteChunkError(error)) return

  if (sessionStorage.getItem(ROUTE_CHUNK_RELOAD_KEY) === to.fullPath) {
    sessionStorage.removeItem(ROUTE_CHUNK_RELOAD_KEY)
    if (from.fullPath !== to.fullPath) {
      void router.replace(from.fullPath)
    }
    window.dispatchEvent(new CustomEvent('global-error', {
      detail: { message: '页面资源加载失败，已返回上一页，请稍后重试。' }
    }))
    return
  }

  sessionStorage.setItem(ROUTE_CHUNK_RELOAD_KEY, to.fullPath)
  window.location.reload()
})

router.afterEach((to) => {
  if (sessionStorage.getItem(ROUTE_CHUNK_RELOAD_KEY) === to.fullPath) {
    sessionStorage.removeItem(ROUTE_CHUNK_RELOAD_KEY)
  }
})

const clearAuthState = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('userId')
}

const isAuthorizationFailure = (error: unknown) => {
  const status = (error as { response?: { status?: number } } | null)?.response?.status
  return status === 401 || status === 403
}

// Global route guard
router.beforeEach(async (to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - 知弈AgentOS` : '知弈AgentOS'

  // 内部发行版：桌面壳启动即建立本地会话（账号由启动器首启自动注册），
  // 因此登录页不会出现在界面上；拿不到会话时回落到原有登录流程。
  if (isDesktop() && !localStorage.getItem('token')) {
    await ensureDesktopSession()
  }

  const token = localStorage.getItem('token')
  const requiresAuth = Boolean(to.meta.requiresAuth)

  // The desktop shell never shows the public landing page: unauthenticated
  // sessions open the standalone login surface instead.
  if (to.path === '/' && isDesktop()) {
    next({ path: '/login', replace: true })
    return
  }

  // Validate login state for protected routes
  if (requiresAuth) {
    if (!token) {
      next(unauthRedirect(to.fullPath))
      return
    }

    try {
      const result = await authApi.verifyToken()
      if (!result.valid) {
        clearAuthState()
        next(unauthRedirect(to.fullPath))
        return
      }
    } catch (error) {
      if (isAuthorizationFailure(error)) {
        clearAuthState()
        next(unauthRedirect(to.fullPath))
      } else {
        // A temporary backend/dev-server interruption is not an authentication
        // decision. Keep the session and route so recovery does not force login.
        next()
      }
      return
    }
  }

  // 已登录时访问登录页，回到来源页（如果有）或默认聊天页。
  if (to.path === '/login' && token) {
    try {
      const result = await authApi.verifyToken()
      if (result.valid) {
        const redirect = normalizeRedirect(typeof to.query.redirect === 'string' ? to.query.redirect : undefined)
        next(redirect)
        return
      }
      clearAuthState()
    } catch (error) {
      if (isAuthorizationFailure(error)) clearAuthState()
    }
  }

  // 已登录时打开首页内嵌认证入口，回到来源页（如果有）或默认聊天页。
  if (to.path === '/' && to.query.auth === '1' && token) {
    try {
      const result = await authApi.verifyToken()
      if (result.valid) {
        const redirect = normalizeRedirect(typeof to.query.redirect === 'string' ? to.query.redirect : undefined)
        next(redirect)
        return
      }
      clearAuthState()
    } catch (error) {
      if (isAuthorizationFailure(error)) clearAuthState()
    }
  }

  next()
})

export default router


