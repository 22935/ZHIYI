<!-- 登录/注册页面 — 轻量双栏布局，右侧使用 ACG 动态群体智能拓扑作为品牌视觉 -->
<template>
  <main class="login-view ui-shell">
    <header class="brand-bar">
      <a class="brand" href="/" aria-label="知弈首页">
        <span class="logo-box"><img src="/logo.png" alt="" aria-hidden="true" /></span>
        <span class="brand-name">知弈</span>
      </a>
    </header>

    <div class="login-layout">
      <section class="auth-side" aria-labelledby="auth-title">
        <div class="auth-content">
          <div class="hero-text">
            <p class="eyebrow">KINLIN AGENT OS</p>
            <h1 id="auth-title"><span>让专业任务，</span><span>在协作中涌现答案</span></h1>
            <p class="subtitle">连接知识、模型与智能体，让复杂工作从规划到交付持续推进。</p>
          </div>

          <el-tabs v-model="activeTab" class="premium-tabs">
            <el-tab-pane label="登录" name="login">
              <div class="auth-header">
                <h2>继续你的工作</h2>
                <p>登录后进入知弈工作空间</p>
              </div>
              
              <el-form
                ref="loginFormRef"
                :model="loginForm"
                :rules="loginRules"
                label-width="0"
                class="auth-form"
              >
                <el-form-item prop="username">
                  <el-input
                    v-model="loginForm.username"
                    placeholder="用户名"
                    :prefix-icon="User"
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="password">
                  <el-input
                    v-model="loginForm.password"
                    type="password"
                    placeholder="密码"
                    :prefix-icon="Lock"
                    show-password
                    class="premium-input"
                    @keyup.enter="handleLogin"
                  />
                </el-form-item>
                
                <div class="form-options">
                  <el-checkbox v-model="loginForm.remember">记住我</el-checkbox>
                  <el-button link class="forgot-link">忘记密码？</el-button>
                </div>
                
                <el-button
                  type="primary"
                  class="submit-btn"
                  @click="handleLogin"
                  :loading="loading"
                >
                  登录
                </el-button>
                <p class="auth-note">登录即表示你同意遵守平台使用规范与隐私政策。</p>
              </el-form>
            </el-tab-pane>
            
            <el-tab-pane label="注册" name="register">
              <div class="auth-header">
                <h2>创建工作空间账户</h2>
                <p>开始构建你的专业智能体协作网络</p>
              </div>
              
              <el-form
                ref="registerFormRef"
                :model="registerForm"
                :rules="registerRules"
                label-width="0"
                class="auth-form"
              >
                <el-form-item prop="username">
                  <el-input
                    v-model="registerForm.username"
                    placeholder="用户名"
                    :prefix-icon="User"
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="email">
                  <el-input
                    v-model="registerForm.email"
                    placeholder="邮箱"
                    :prefix-icon="Message"
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="password">
                  <el-input
                    v-model="registerForm.password"
                    type="password"
                    placeholder="密码"
                    :prefix-icon="Lock"
                    show-password
                    class="premium-input"
                  />
                </el-form-item>
                
                <el-form-item prop="confirmPassword">
                  <el-input
                    v-model="registerForm.confirmPassword"
                    type="password"
                    placeholder="确认密码"
                    :prefix-icon="Lock"
                    show-password
                    class="premium-input"
                    @keyup.enter="handleRegister"
                  />
                </el-form-item>
                
                <el-button
                  type="primary"
                  class="submit-btn"
                  @click="handleRegister"
                  :loading="loading"
                >
                  立即注册
                </el-button>
                <p class="auth-note">注册即表示你同意遵守平台使用规范与隐私政策。</p>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </div>
      </section>

      <section class="acg-showcase" aria-label="ACG 动态群体智能拓扑示意">
        <LoginAcgDemo
          :blueprint="demoBlueprint"
          :completed-step-ids="demoCompletedStepIds"
          :step-states="demoStepStates"
        />
      </section>
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { User, Lock, Message } from '@element-plus/icons-vue'
import { ElMessage, FormInstance, FormRules } from 'element-plus'
import { authApi } from '@/services/api/auth'
// 登录页使用独立快照组件，避免业务 ACG 后续迭代改变登录页展示。
import LoginAcgDemo from '@/components/agentos/LoginAcgDemo.vue'
import type { AcgBlueprint, AcgStepState } from '@/services/api/agentos'

const router = useRouter()
const route = useRoute()

const activeTab = ref('login')
const loading = ref(false)
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()

const demoBlueprint: AcgBlueprint = {
  graphId: 'login-acg-demo',
  objective: '协同完成一份软件服务合同的风险审查与修订建议',
  complexityLevel: 'complex',
  nodes: [
    { nodeId: 'intake', nodeType: 'step', name: '材料理解', description: '解析合同材料并识别审查范围。', agentName: '任务理解 Agent', capability: '文档理解' },
    { nodeId: 'knowledge', nodeType: 'memory', name: '法规与案例库', description: '提供法规、案例与内部审查规则。' },
    { nodeId: 'risk', nodeType: 'agent', name: '风险识别 Agent', description: '识别责任、履约、数据和知识产权风险。', capability: '合同风险识别' },
    { nodeId: 'clause', nodeType: 'agent', name: '条款分析 Agent', description: '分析关键条款的完整性与可执行性。', capability: '条款分析' },
    { nodeId: 'evidence', nodeType: 'evidence', name: '审查证据', description: '记录法规依据和原文定位。' },
    { nodeId: 'review', nodeType: 'control', name: '交叉复核', description: '汇总多智能体结论并解决冲突。', controlType: 'join' },
    { nodeId: 'rewrite', nodeType: 'step', name: '修订建议', description: '生成可直接采用的条款修改方案。', agentName: '法律顾问 Agent', capability: '合同修订' },
    { nodeId: 'report', nodeType: 'step', name: '审查报告', description: '形成结构化风险清单与最终报告。', agentName: '报告生成 Agent', capability: '专业报告生成' }
  ],
  edges: [
    { edgeId: 'e1', sourceId: 'intake', targetId: 'risk', edgeType: 'dependency' },
    { edgeId: 'e2', sourceId: 'intake', targetId: 'clause', edgeType: 'dependency' },
    { edgeId: 'e3', sourceId: 'knowledge', targetId: 'risk', edgeType: 'read' },
    { edgeId: 'e4', sourceId: 'knowledge', targetId: 'clause', edgeType: 'read' },
    { edgeId: 'e5', sourceId: 'risk', targetId: 'evidence', edgeType: 'write' },
    { edgeId: 'e6', sourceId: 'clause', targetId: 'evidence', edgeType: 'write' },
    { edgeId: 'e7', sourceId: 'risk', targetId: 'review', edgeType: 'communication' },
    { edgeId: 'e8', sourceId: 'clause', targetId: 'review', edgeType: 'communication' },
    { edgeId: 'e9', sourceId: 'evidence', targetId: 'review', edgeType: 'support' },
    { edgeId: 'e10', sourceId: 'review', targetId: 'rewrite', edgeType: 'control_flow' },
    { edgeId: 'e11', sourceId: 'rewrite', targetId: 'report', edgeType: 'execution' }
  ]
}

const demoCompletedStepIds = ['intake', 'risk', 'clause']
const demoStepStates: AcgStepState[] = [
  { stepId: 'intake', status: 'completed', agentName: '任务理解 Agent', attempt: 1, retryCount: 0, outputSummary: '已识别 28 个待审条款与 4 类重点风险。' },
  { stepId: 'risk', status: 'completed', agentName: '风险识别 Agent', attempt: 1, retryCount: 0, outputSummary: '已完成责任限制、数据合规与知识产权风险识别。' },
  { stepId: 'clause', status: 'completed', agentName: '条款分析 Agent', attempt: 1, retryCount: 0, outputSummary: '已完成关键条款完整性检查。' },
  { stepId: 'review', status: 'running', agentName: '复核协调 Agent', attempt: 1, retryCount: 0, outputSummary: '正在合并风险结论与审查证据。' },
  { stepId: 'rewrite', status: 'pending', agentName: '法律顾问 Agent', attempt: 0, retryCount: 0 },
  { stepId: 'report', status: 'pending', agentName: '报告生成 Agent', attempt: 0, retryCount: 0 }
]

const loginForm = reactive({
  username: '',
  password: '',
  remember: false
})

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const loginRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ]
}

const registerRules: FormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, message: '用户名长度不能少于3位', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入正确的邮箱格式', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value, callback) => {
        if (value !== registerForm.password) {
          callback(new Error('两次输入密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur'
    }
  ]
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const response = await authApi.login({
        username: loginForm.username,
        password: loginForm.password
      })
      
      // 如果请求成功（没有抛出异常），说明登录成功
      if (response.token) {
        localStorage.setItem('token', response.token)
        localStorage.setItem('userId', response.userId?.toString() || '')
        ElMessage.success(response.message || '登录成功')

        const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/chat'
        const safeRedirect = redirect.startsWith('/') && !redirect.startsWith('//') ? redirect : '/chat'
        router.push(safeRedirect)
      } else {
        ElMessage.error(response.message || '登录失败')
      }
    } catch (error: any) {
      // 错误已经在request.ts的拦截器中处理，这里只显示具体错误信息
      const errorMessage = error.response?.data?.message || error.message || '登录失败'
      ElMessage.error(errorMessage)
    } finally {
      loading.value = false
    }
  })
}

const handleRegister = async () => {
  if (!registerFormRef.value) return
  
  await registerFormRef.value.validate(async (valid) => {
    if (!valid) return
    
    loading.value = true
    try {
      const response = await authApi.register({
        username: registerForm.username,
        email: registerForm.email,
        password: registerForm.password
      })
      
      // 如果请求成功（没有抛出异常），说明注册成功
      if (response.token || response.message) {
        ElMessage.success(response.message || '注册成功，请登录')
        activeTab.value = 'login'
        loginForm.username = registerForm.username
      } else {
        ElMessage.error(response.message || '注册失败')
      }
    } catch (error: any) {
      // 错误已经在request.ts的拦截器中处理，这里只显示具体错误信息
      const errorMessage = error.response?.data?.message || error.message || '注册失败'
      ElMessage.error(errorMessage)
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped lang="scss">
.login-view {
  --login-line: color-mix(in srgb, var(--border-light) 78%, transparent);
  --login-surface: color-mix(in srgb, var(--bg-card) 42%, transparent);
  width: 100%;
  height: 100vh;
  height: 100dvh;
  position: relative;
  overflow: hidden;
  color: var(--text-primary);
  background:
    radial-gradient(circle at 74% 46%, var(--primary-fade), transparent 32%),
    var(--bg-app);
}

.brand-bar {
  position: absolute;
  z-index: 5;
  top: 28px;
  left: 32px;
  display: flex;
  align-items: center;
}

.brand {
  color: inherit;
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 11px;
}

.logo-box {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  overflow: hidden;
}

.logo-box img {
  width: 100%;
  height: 100%;
  display: block;
  object-fit: cover;
}

.brand-name {
  font-family: var(--font-serif);
  font-size: 22px;
  font-weight: 650;
  letter-spacing: .04em;
}

.login-layout {
  position: absolute;
  top: 50%;
  left: calc(50% + 100px);
  width: min(1180px, calc(100% - 96px));
  max-height: calc(100vh - 120px);
  max-height: calc(100dvh - 120px);
  padding: 0;
  box-sizing: border-box;
  display: grid;
  grid-template-columns: minmax(360px, 430px) minmax(500px, 650px);
  justify-content: space-between;
  align-items: center;
  gap: clamp(64px, 7vw, 100px);
  transform: translate(-50%, -50%);
}

.auth-side {
  width: 100%;
  max-width: 430px;
  justify-self: end;
}

.hero-text { margin-bottom: 38px; }
.eyebrow {
  margin: 0 0 18px;
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 750;
  letter-spacing: .18em;
}

.hero-text h1 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: clamp(40px, 3.35vw, 52px);
  font-weight: 520;
  line-height: 1.08;
  letter-spacing: -.035em;
  text-wrap: balance;
}

.hero-text h1 span { display: block; white-space: nowrap; }

.subtitle {
  max-width: 440px;
  margin: 22px 0 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.75;
  text-wrap: pretty;
}

.premium-tabs { width: 100%; }
.premium-tabs :deep(.el-tabs__header) {
  margin: 0 0 27px;
}

.premium-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: var(--login-line);
}

.premium-tabs :deep(.el-tabs__item) {
  height: 44px;
  padding: 0 24px;
  color: var(--text-muted, var(--text-secondary));
  font-size: 14px;
  font-weight: 600;
}

.premium-tabs :deep(.el-tabs__item:first-child) { padding-left: 0; }
.premium-tabs :deep(.el-tabs__item.is-active) { color: var(--text-primary); }
.premium-tabs :deep(.el-tabs__active-bar) {
  height: 1px;
  background: var(--primary-color);
}

.auth-header { margin-bottom: 22px; }
.auth-header h2 {
  margin: 0 0 7px;
  font-size: 18px;
  font-weight: 650;
}
.auth-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.auth-form { display: flex; flex-direction: column; gap: 13px; }
.auth-form :deep(.el-form-item) { margin-bottom: 0; }
.premium-input :deep(.el-input__wrapper) {
  height: 50px;
  padding: 0 15px;
  border: 1px solid var(--login-line);
  border-radius: 10px;
  background: var(--login-surface) !important;
  box-shadow: none !important;
  transition: border-color 180ms ease, background-color 180ms ease;
}
.premium-input :deep(.el-input__wrapper:hover) { border-color: var(--border-hover); }
.premium-input :deep(.el-input__wrapper.is-focus) {
  border-color: var(--primary-color);
  background: var(--bg-card) !important;
}
.premium-input :deep(.el-input__inner) { color: var(--text-primary); font-size: 14px; }
.premium-input :deep(.el-input__prefix) { color: var(--text-muted, var(--text-secondary)); }

.form-options {
  min-height: 30px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.form-options :deep(.el-checkbox__label), .forgot-link { font-size: 12px; }
.forgot-link { color: var(--primary-color); }

.submit-btn {
  width: 100%;
  height: 50px;
  margin-top: 3px;
  border: 0;
  border-radius: 10px;
  background: var(--primary-color);
  color: var(--on-primary, #fff);
  box-shadow: none;
  font-size: 14px;
  font-weight: 700;
  letter-spacing: .04em;
  transition: background-color 180ms ease, transform 180ms ease;
}
.submit-btn:hover { background: var(--primary-hover); transform: translateY(-1px); }
.submit-btn:active { transform: translateY(0); }
.auth-note {
  margin: 3px 0 0;
  color: var(--text-disabled);
  font-size: 11px;
  line-height: 1.6;
  text-align: center;
}

.acg-showcase {
  position: relative;
  width: 100%;
  aspect-ratio: 1 / 1;
  max-height: min(72vh, 720px);
  justify-self: end;
  overflow: hidden;
  border: 1px solid var(--login-line);
  border-radius: 22px;
  background:
    radial-gradient(circle at 50% 42%, var(--primary-fade), transparent 48%),
    color-mix(in srgb, var(--bg-panel) 64%, transparent);
  box-shadow: inset 0 0 80px color-mix(in srgb, var(--bg-app) 62%, transparent);
}

.acg-showcase :deep(.acg-topology) {
  width: 100%;
  height: 100%;
  box-sizing: border-box;
  padding: 18px 20px 14px;
  border: 0;
  border-radius: inherit;
  background: transparent;
  box-shadow: none;
}

.acg-showcase :deep(.graph-stage) { flex: 1; min-height: 0; }
.acg-showcase :deep(.graph-canvas) { height: 100%; min-height: 320px; }
.acg-showcase :deep(.node-detail) { height: 100%; }
.acg-showcase :deep(.legend) { gap: 7px 10px; }
.acg-showcase :deep(.legend-item) { font-size: 9px; }

@media (max-width: 1080px) {
  .login-layout { width: min(900px, calc(100% - 56px)); grid-template-columns: minmax(350px, .9fr) minmax(390px, 1fr); gap: 48px; }
  .hero-text h1 { font-size: clamp(38px, 4.5vw, 46px); }
}

@media (max-width: 820px) {
  .brand-bar { top: 20px; left: 20px; }
  .login-view { min-height: 100vh; min-height: 100dvh; height: auto; overflow-y: auto; }
  .login-layout { position: relative; top: auto; left: auto; width: min(480px, calc(100% - 40px)); height: auto; min-height: 100vh; min-height: 100dvh; max-height: none; margin: 0 auto; padding: 92px 0 48px; display: block; transform: none; }
  .auth-side { max-width: none; }
  .hero-text { margin-bottom: 30px; }
  .hero-text h1 { font-size: clamp(38px, 10vw, 50px); }
  .acg-showcase { display: none; }
}

@media (max-width: 480px) {
  .brand-bar, .login-layout { width: calc(100% - 32px); }
  .login-layout { padding-top: 22px; }
  .hero-text h1 { font-size: 36px; }
  .subtitle { margin-top: 16px; font-size: 14px; }
  .hero-text { margin-bottom: 24px; }
}

@media (min-width: 821px) and (max-height: 760px) {
  .brand-bar { top: 18px; left: 24px; }
  .login-layout { max-height: calc(100vh - 72px); max-height: calc(100dvh - 72px); }
  .hero-text { margin-bottom: 22px; }
  .hero-text h1 { font-size: clamp(36px, 3.2vw, 46px); }
  .subtitle { margin-top: 14px; }
  .premium-tabs :deep(.el-tabs__header) { margin-bottom: 18px; }
  .auth-header { margin-bottom: 16px; }
  .auth-form { gap: 9px; }
  .premium-input :deep(.el-input__wrapper), .submit-btn { height: 46px; }
}

@media (prefers-reduced-motion: reduce) {
  .premium-input :deep(.el-input__wrapper), .submit-btn { transition: none; }
}
</style>
