import { createRouter, createWebHashHistory, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { isDesktop } from '@/platform'
import { AUTH_ROUTE, DEFAULT_REDIRECT, isAuthenticated } from '@/features/auth/authService'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'Landing',
    component: () => import('@/views/LandingView.vue'),
    meta: { title: '介绍', public: true }
  },
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { title: '登录', public: true }
  },
  {
    path: '/user',
    name: 'User',
    component: () => import('@/views/UserView.vue'),
    meta: {
      title: '用户中心'
    }
  },
  {
    path: '/info',
    name: 'Info',
    component: () => import('@/views/InfoView.vue'),
    meta: {
      title: '信息入口'
    }
  },
  {
    path: '/history',
    name: 'History',
    // These workspace surfaces pull in graph and visualization libraries.
    // Load them only after navigation so initial rendering does not ask Vite to
    // transform the entire workspace at startup. Chunk failures
    // remain covered by the one-shot router recovery below.
    component: () => import('@/views/HistoryView.vue'),
    meta: {
      title: '历史记录'
    }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: () => import('@/views/ChatView.vue'),
    meta: {
      title: '对话'
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
      title: '设置'
    }
  },
  {
    path: '/rag',
    name: 'RAG',
    component: () => import('@/views/RagView.vue'),
    meta: {
      title: '知识库查询'
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
      title: 'ACG 动态群体智能引擎'
    }
  },
  {
    path: '/agentos/projects',
    name: 'ProjectsHub',
    component: () => import('@/views/ProjectsHubView.vue'),
    meta: {
      title: '项目'
    }
  },
  {
    path: '/agentos/resources',
    name: 'ResourceCenter',
    component: () => import('@/views/ResourceCenterView.vue'),
    meta: {
      title: 'Resource Center'
    }
  },
  {
    path: '/agentos/memory',
    name: 'MemoryCenter',
    component: () => import('@/views/MemoryView.vue'),
    meta: {
      title: 'Run Memory'
    }
  },
  {
    path: '/agentos/missions/new',
    name: 'CreateMission',
    component: () => import('@/views/CreateMissionView.vue'),
    meta: {
      title: '新建任务'
    }
  },
  {
    path: '/agentos/missions/:missionId/workspace',
    name: 'MissionWorkspace',
    component: () => import('@/views/MissionWorkspaceView.vue'),
    meta: {
      title: 'Mission Project Workspace'
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

/** 只接受站内绝对路径，防止 ?redirect= 变成开放重定向。 */
const normalizeAuthRedirect = (value: unknown): string => {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//') || value === AUTH_ROUTE) {
    return DEFAULT_REDIRECT
  }
  return value
}

// 单一认证路由：未登录统一跳 /login 并带上原目标；已登录访问登录页则回到工作台。
// 后端 N03 仍是本机单用户 LocalIdentity，这里的会话只控制前端入口。
router.beforeEach((to) => {
  document.title = to.meta.title ? `${to.meta.title} - 知弈AgentOS` : '知弈AgentOS'

  const authenticated = isAuthenticated()
  if (to.meta.public) {
    if (authenticated && to.path === AUTH_ROUTE) return normalizeAuthRedirect(to.query.redirect)
    return true
  }
  if (!authenticated) return { path: AUTH_ROUTE, query: { redirect: to.fullPath } }
  return true
})

export default router
