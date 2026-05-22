import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import ChatView from '@/views/ChatView.vue'
import RoleView from '@/views/RoleView.vue'
import SettingsView from '@/views/SettingsView.vue'
import LoginView from '@/views/LoginView.vue'
import RagView from '@/views/RagView.vue'
import { authApi } from '@/services/api/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    redirect: '/chat'
  },
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
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
      requiresAuth: true
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
    component: () => import('@/views/HistoryView.vue'),
    meta: {
      title: '历史记录',
      requiresAuth: true
    }
  },
  {
    path: '/chat',
    name: 'Chat',
    component: ChatView,
    meta: {
      title: '对话',
      requiresAuth: true
    }
  },
  {
    path: '/roles',
    name: 'Roles',
    component: RoleView,
    meta: {
      title: '角色管理',
      requiresAuth: true
    }
  },
  {
    path: '/create-role',
    name: 'CreateRole',
    component: () => import('@/views/CreateRoleView.vue'),
    meta: {
      title: '创建角色',
      requiresAuth: true
    }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: SettingsView,
    meta: {
      title: '设置',
      requiresAuth: true
    }
  },
  {
    path: '/rag',
    name: 'RAG',
    component: RagView,
    meta: {
      title: '知识库查询',
      requiresAuth: true
    }
  },
  {
    path: '/federated-models',
    name: 'FederatedModelManagement',
    component: () => import('@/views/FederatedModelManagementView.vue'),
    meta: {
      title: '联邦模型管理',
      requiresAuth: true
    }
  },
  {
    path: '/federated-learning',
    name: 'FederatedLearning',
    component: () => import('@/views/FederatedLearningView.vue'),
    meta: {
      title: '联邦学习管理',
      requiresAuth: true
    }
  },
  {
    path: '/federated-agent-workbench',
    name: 'FederatedAgentWorkbench',
    component: () => import('@/views/FederatedAgentWorkbenchView.vue'),
    meta: {
      title: '联邦智能体工作台',
      requiresAuth: true
    }
  },
  {
    path: '/agentos-console',
    name: 'AgentOsConsole',
    component: () => import('@/views/AgentOsConsoleView.vue'),
    meta: {
      title: 'AgentOS 控制台',
      requiresAuth: true
    }
  },
  {
    path: '/agentos/legal/contract-review',
    name: 'LawyerContractReviewWorkbench',
    component: () => import('@/views/LawyerContractReviewWorkbenchView.vue'),
    meta: {
      title: '律师合同审查',
      requiresAuth: true
    }
  },
  {
    path: '/contract-clause-planner',
    name: 'ContractClausePlanner',
    component: () => import('@/views/ContractClausePlannerView.vue'),
    meta: {
      title: '软件开发合同起草',
      requiresAuth: true
    }
  },
  {
    path: '/voice-chat',
    name: 'VoiceChat',
    component: () => import('@/views/VoiceChatView.vue'),
    meta: {
      title: '语音讲解',
      requiresAuth: true
    }
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

const clearAuthState = () => {
  localStorage.removeItem('token')
  localStorage.removeItem('userId')
}

const normalizeRedirect = (redirect?: string) => {
  if (!redirect) return '/chat'
  if (!redirect.startsWith('/') || redirect.startsWith('//')) return '/chat'
  return redirect
}

// Global route guard
router.beforeEach(async (to, _from, next) => {
  document.title = to.meta.title ? `${to.meta.title} - 联邦智能枢` : '联邦智能枢'

  const token = localStorage.getItem('token')
  const requiresAuth = Boolean(to.meta.requiresAuth)

  // Validate login state for protected routes
  if (requiresAuth) {
    if (!token) {
      next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
      return
    }

    try {
      const result = await authApi.verifyToken()
      if (!result.valid) {
        clearAuthState()
        next(`/login?redirect=${encodeURIComponent(to.fullPath)}`)
        return
      }
    } catch {
      clearAuthState()
      next('/login')
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
    } catch {
      clearAuthState()
    }
  }

  next()
})

export default router


