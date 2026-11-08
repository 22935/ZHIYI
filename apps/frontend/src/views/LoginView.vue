<template>
    <main class="auth-view" :class="{ 'is-desktop-shell': desktopShell, 'is-register': activeTab === 'register', 'is-embedded': props.embedded, 'is-theme-dark': isDarkTheme }">
    <header v-if="!props.embedded" class="auth-topbar" v-bind="dragRegionProps" aria-label="应用窗口标题栏">
      <a class="auth-brand" href="/" aria-label="知弈 AgentOS 首页" @click.prevent="handleBrandClick">
        <span class="auth-brand__logo"><img src="/logo.webp" alt="" aria-hidden="true" /></span>
        <span class="auth-brand__wordmark">
          <span class="auth-brand__name">知弈</span>
          <strong>AgentOS</strong>
        </span>
      </a>
      <button
        class="auth-theme-toggle"
        data-testid="auth-theme-toggle"
        type="button"
        :aria-label="themeToggleLabel"
        :title="themeToggleLabel"
        @click="toggleTheme"
      >
        <el-icon aria-hidden="true"><Sunny v-if="isDarkTheme" /><Moon v-else /></el-icon>
        <span>{{ isDarkTheme ? '黑暗' : '明亮' }}</span>
      </button>
      <DesktopWindowControls v-if="desktopShell" />
    </header>

    <div class="auth-layout">
      <section v-if="!props.embedded" class="auth-intro" aria-labelledby="auth-title">
        <p class="auth-eyebrow">DYNAMIC HETEROGENEOUS AGENT SWARM</p>
        <h1 id="auth-title">让复杂工作<br /><span>在协作中涌现答案</span></h1>
        <p class="auth-intro__lead">连接知识、模型与智能体，让每一个专业任务从规划到交付持续推进。</p>
        <div class="auth-intro__features" aria-label="产品能力">
          <span><b>01</b> 多智能体协作</span>
          <span><b>02</b> 动态任务规划</span>
          <span><b>03</b> 异构资源调度</span>
          <span><b>04</b> 自进化学习</span>
        </div>
      </section>

      <section class="auth-card" data-testid="auth-card" aria-labelledby="auth-card-title">
        <button v-if="props.embedded" class="auth-card__close" data-testid="auth-dialog-close" type="button" aria-label="返回首页" @click="emit('back')">×</button>
        <div class="auth-card__mark" aria-hidden="true"><img src="/logo.webp" alt="" /></div>
        <div class="auth-card__heading">
          <p class="auth-card__eyebrow"><span aria-hidden="true"></span>{{ activeTab === 'login' ? 'WORKSPACE ACCESS' : 'NEW WORKSPACE' }}</p>
          <h2 id="auth-card-title">{{ activeTab === 'login' ? '登录知弈 AgentOS' : '创建知弈 AgentOS 账号' }}</h2>
          <p>{{ activeTab === 'login' ? '继续进入你的智能协作工作空间' : '连接模型、知识与智能体，开始构建你的工作流' }}</p>
        </div>

        <el-tabs v-model="activeTab" class="auth-tabs" stretch @tab-change="authError = ''">
          <el-tab-pane label="登录" name="login">
            <el-form ref="loginFormRef" :model="loginForm" :rules="loginRules" label-position="top" class="auth-form">
              <el-form-item label="登录账号" prop="username">
                <el-input v-model="loginForm.username" :prefix-icon="User" placeholder="用户名或邮箱" autocomplete="username" />
              </el-form-item>
              <el-form-item label="登录密码" prop="password">
                <el-input v-model="loginForm.password" type="password" :prefix-icon="Lock" placeholder="输入你的登录密码" autocomplete="current-password" show-password @keyup.enter="handleLogin" />
              </el-form-item>
              <p v-if="authError" class="auth-form__error" role="alert">{{ authError }}</p>
              <div class="auth-form__options">
                <el-checkbox v-model="loginForm.remember">记住我</el-checkbox>
                <button class="text-action" type="button" @click="showUnavailable('忘记密码')">忘记密码？</button>
              </div>
              <el-button type="primary" class="auth-submit" data-testid="auth-submit" :loading="loading" @click="handleLogin">登录</el-button>
            </el-form>
          </el-tab-pane>

          <el-tab-pane label="注册" name="register">
            <el-form ref="registerFormRef" :model="registerForm" :rules="registerRules" label-position="top" class="auth-form">
              <el-form-item label="用户名" prop="username">
                <el-input v-model="registerForm.username" :prefix-icon="User" placeholder="设置用户名" autocomplete="username" />
              </el-form-item>
              <el-form-item label="邮箱地址" prop="email">
                <el-input v-model="registerForm.email" :prefix-icon="Message" placeholder="用于接收账号通知" autocomplete="email" />
              </el-form-item>
              <el-form-item label="设置密码" prop="password">
                <el-input v-model="registerForm.password" type="password" :prefix-icon="Lock" placeholder="8–32 位，含字母和数字" autocomplete="new-password" show-password />
              </el-form-item>
              <el-form-item label="确认密码" prop="confirmPassword">
                <el-input v-model="registerForm.confirmPassword" type="password" :prefix-icon="Lock" placeholder="再次输入你的密码" autocomplete="new-password" show-password @keyup.enter="handleRegister" />
              </el-form-item>
              <p v-if="authError" class="auth-form__error" role="alert">{{ authError }}</p>
              <el-button type="primary" class="auth-submit" data-testid="auth-submit" :loading="loading" @click="handleRegister">立即注册</el-button>
            </el-form>
          </el-tab-pane>
        </el-tabs>

        <div v-if="!props.embedded" class="auth-divider"><span>或使用以下方式登录</span></div>
        <div v-if="!props.embedded" class="auth-providers" aria-label="第三方登录">
          <button type="button" aria-label="微信登录" @click="showUnavailable('微信登录')"><el-icon><ChatDotRound /></el-icon></button>
          <button type="button" aria-label="GitHub 登录" @click="showUnavailable('GitHub 登录')"><el-icon><Connection /></el-icon></button>
          <button type="button" aria-label="企业账号登录" @click="showUnavailable('企业账号登录')"><el-icon><OfficeBuilding /></el-icon></button>
        </div>
        <p v-if="!props.embedded" class="auth-switch">还没有账户？ <button type="button" @click="activeTab = 'register'">立即注册</button></p>
        <p v-if="!props.embedded" class="auth-legal">登录即表示你同意遵守平台使用规范与隐私政策。</p>
      </section>
    </div>

    <footer v-if="!props.embedded" class="auth-footer"><span>© 2026 知弈 AgentOS</span><span>智能协作 · 共创未来</span></footer>
  </main>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound, Connection, Lock, Message, Moon, OfficeBuilding, Sunny, User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { DEFAULT_REDIRECT, login as localLogin, register as localRegister } from '@/features/auth/authService'
import { validateEmail, validatePassword, validateUsername } from '@/features/auth/validation'
import DesktopWindowControls from '@window-controls'
import { isDesktop, platform } from '@/platform'
import { usePublicTheme } from '@/composables/usePublicTheme'

const props = withDefaults(defineProps<{ embedded?: boolean }>(), { embedded: false })
const emit = defineEmits<{ back: [] }>()

const desktopShell = isDesktop()
const dragRegionProps = platform.dragRegionProps

const router = useRouter()
const route = useRoute()
const { isDarkTheme, themeToggleLabel, toggleTheme } = usePublicTheme()

const landingReturnTarget = () => {
  const value = route.query.from
  return typeof value === 'string' && /^\/(?:#[a-z-]+)?$/.test(value) ? value : '/'
}

const handleBrandClick = () => {
  if (props.embedded) {
    emit('back')
    return
  }
  void router.push(landingReturnTarget())
}

const activeTab = ref<'login' | 'register'>(route.query.mode === 'register' ? 'register' : 'login')
const loading = ref(false)
const loginFormRef = ref<FormInstance>()
const registerFormRef = ref<FormInstance>()
const authError = ref('')
const loginForm = reactive({ username: '', password: '', remember: false })
const registerForm = reactive({ username: '', email: '', password: '', confirmPassword: '' })

const loginRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ]
}

/** 表单规则与 features/auth/validation 保持同源，避免页面放行后被服务层二次拒绝。 */
const fieldRule = (validate: (value: string) => string | null) => ({
  validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
    const message = validate(String(value ?? ''))
    if (message) callback(new Error(message))
    else callback()
  },
  trigger: 'blur'
})

const registerRules: FormRules = {
  username: [fieldRule(validateUsername)],
  email: [fieldRule(validateEmail)],
  password: [fieldRule(validatePassword)],
  confirmPassword: [
    fieldRule((value) => !value ? '请再次输入密码' : null),
    {
      validator: (_rule, value, callback) => {
        if (value !== registerForm.password) callback(new Error('两次输入的密码不一致'))
        else callback()
      },
      trigger: 'blur'
    }
  ]
}

const showUnavailable = (feature: string) => ElMessage.info(`${feature}功能即将开放`)

/** 只接受站内绝对路径，避免 ?redirect= 变成开放重定向。 */
const authRedirect = () => {
  const value = route.query.redirect
  return typeof value === 'string' && value.startsWith('/') && !value.startsWith('//') && value !== '/login'
    ? value
    : DEFAULT_REDIRECT
}

const handleLogin = async () => {
  if (!loginFormRef.value) return
  authError.value = ''
  await loginFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      const result = await localLogin({
        identifier: loginForm.username,
        password: loginForm.password,
        remember: loginForm.remember
      })
      if (!result.ok) {
        authError.value = result.message
        return
      }
      ElMessage.success(result.message)
      await router.push(authRedirect())
    } catch (error) {
      authError.value = error instanceof Error ? error.message : '登录失败，请稍后重试'
    } finally {
      loading.value = false
    }
  })
}

const handleRegister = async () => {
  if (!registerFormRef.value) return
  authError.value = ''
  await registerFormRef.value.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      // 保留原设计交互：注册成功后回到登录 tab，由用户再完成一次密码验证。
      const result = await localRegister({
        username: registerForm.username,
        email: registerForm.email,
        password: registerForm.password,
        confirmPassword: registerForm.confirmPassword
      }, { signIn: false })
      if (!result.ok) {
        authError.value = result.message
        return
      }
      ElMessage.success('注册成功，请登录')
      activeTab.value = 'login'
      loginForm.username = registerForm.username
      registerForm.password = ''
      registerForm.confirmPassword = ''
    } catch (error) {
      authError.value = error instanceof Error ? error.message : '注册失败，请稍后重试'
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped lang="scss">
.auth-view {
  --auth-ink: #102a56;
  --auth-muted: #6c85ad;
  --auth-blue: #249ef0;
  --auth-purple: #6654f4;
  position: relative;
  min-height: 100vh;
  min-height: 100dvh;
  overflow-x: hidden;
  overflow-y: auto;
  scrollbar-gutter: stable;
  color: var(--auth-ink);
  background: #dcecff url('/bg.webp') center / cover fixed no-repeat;
}
.auth-view::before { content: ''; position: fixed; inset: 0; pointer-events: none; background: linear-gradient(90deg, rgba(246,251,255,.9) 0%, rgba(246,251,255,.6) 37%, rgba(236,246,255,.08) 77%), linear-gradient(180deg, rgba(255,255,255,.25), transparent 50%); }
.auth-topbar, .auth-layout, .auth-footer { position: relative; z-index: 1; }
.auth-topbar { width: min(100% - 96px, 1920px); min-height: 88px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; }
.auth-brand { display: inline-flex; align-items: center; gap: 13px; color: var(--auth-ink); font-family: var(--font-sans); font-size: 22px; font-weight: 600; letter-spacing: -.035em; line-height: 1; text-decoration: none; }
.auth-brand__wordmark { display: inline-flex; align-items: baseline; gap: 5px; }
.auth-brand__name { font-family: var(--font-serif); font-weight: 700; letter-spacing: -.055em; }
.auth-brand strong { color: #23477d; font-family: var(--font-sans); font-size: .93em; font-weight: 650; letter-spacing: -.045em; }
.auth-brand__logo { width: 36px; height: 36px; display: block; }
.auth-brand__logo img { width: 100%; height: 100%; display: block; object-fit: contain; }
.auth-theme-toggle { min-height: 34px; margin-left: 18px; padding: 0 12px; display: inline-flex; align-items: center; gap: 6px; border: 1px solid rgba(36, 143, 240, .2); border-radius: 999px; color: #557cae; background: rgba(255, 255, 255, .28); cursor: pointer; font: inherit; font-size: 12px; font-weight: 650; white-space: nowrap; transition: border-color 180ms ease, background-color 180ms ease, color 180ms ease, transform 180ms ease; }
.auth-theme-toggle:hover { border-color: rgba(36, 143, 240, .5); color: var(--auth-ink); background: rgba(255, 255, 255, .62); transform: translateY(-1px); }
.auth-layout { width: min(100% - 96px, 1420px); min-height: calc(100vh - 130px); min-height: calc(100dvh - 130px); margin: 0 auto; display: grid; grid-template-columns: minmax(360px, 1fr) minmax(420px, 520px); align-items: center; gap: clamp(70px, 11vw, 190px); padding-bottom: 44px; box-sizing: border-box; }
.auth-intro { margin-top: -5vh; }
.auth-eyebrow { margin: 0 0 22px; color: #6c8fbe; font-size: 11px; font-weight: 700; letter-spacing: .25em; }
.auth-intro h1 { margin: 0; color: var(--auth-ink); font-size: clamp(46px, 4.5vw, 75px); font-weight: 520; line-height: 1.05; letter-spacing: -.065em; }
.auth-intro h1 span { color: #23508d; font-weight: 450; }
.auth-intro__lead { max-width: 520px; margin: 24px 0 0; color: var(--auth-muted); font-size: 16px; line-height: 1.8; }
.auth-intro__features { max-width: 510px; margin-top: 48px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px 30px; color: #53729e; font-size: 13px; }
.auth-intro__features b { margin-right: 10px; color: var(--auth-blue); font-size: 10px; letter-spacing: .08em; }
.auth-card { width: 100%; box-sizing: border-box; padding: 36px 44px 28px; border: 1px solid rgba(255,255,255,.78); border-radius: 24px; background: rgba(249,252,255,.72); box-shadow: 0 24px 70px rgba(68,111,181,.16), inset 0 1px 0 rgba(255,255,255,.86); backdrop-filter: blur(18px); }
.auth-card__mark { width: 44px; height: 44px; margin-bottom: 22px; display: grid; place-items: center; border-radius: 50%; background: linear-gradient(145deg, #d9f1ff, #b8dcff); box-shadow: 0 8px 18px rgba(36,143,240,.14); }
.auth-card__mark img { width: 29px; height: 29px; object-fit: contain; }
.auth-card__heading h2 { margin: 0; color: var(--auth-ink); font-size: 30px; font-weight: 650; letter-spacing: -.04em; }
.auth-card__heading p { margin: 8px 0 26px; color: var(--auth-muted); font-size: 13px; }
.auth-tabs :deep(.el-tabs__header) { margin-bottom: 24px; }
.auth-tabs :deep(.el-tabs__nav-wrap::after) { background: rgba(114,149,194,.2); }
.auth-tabs :deep(.el-tabs__item) { min-height: 44px; color: #7891b5; font-size: 14px; font-weight: 650; }
.auth-tabs :deep(.el-tabs__item.is-active) { color: var(--auth-ink); }
.auth-tabs :deep(.el-tabs__active-bar) { height: 3px; border-radius: 999px; background: linear-gradient(90deg, var(--auth-blue), var(--auth-purple)); }
.auth-form :deep(.el-form-item) { margin-bottom: 28px; }
.auth-form :deep(.el-form-item__label) { padding-bottom: 6px; color: #55739f; font-size: 12px; line-height: 1.2; }
.auth-form :deep(.el-input__wrapper) { min-height: 48px; padding: 0 15px; border: 1px solid rgba(150,180,220,.42) !important; border-radius: 12px; background: rgba(255,255,255,.62) !important; box-shadow: 0 1px 2px rgba(68,111,181,.06) inset !important; transition: border-color 180ms ease, box-shadow 180ms ease, background-color 180ms ease; }
.auth-form :deep(.el-input__wrapper:hover) { border-color: rgba(36,143,240,.58) !important; background: rgba(255,255,255,.76) !important; }
.auth-form :deep(.el-input__wrapper.is-focus) { border-color: var(--auth-blue) !important; background: rgba(255,255,255,.88) !important; box-shadow: 0 0 0 3px rgba(36,143,240,.12) !important; }
.auth-form :deep(.el-input__inner) { color: var(--auth-ink) !important; font-size: 13px; }
.auth-form :deep(.el-input__inner::placeholder) { color: #7e98bb !important; }
.auth-form :deep(.el-input__prefix), .auth-form :deep(.el-input__suffix) { color: #557cae !important; }
.auth-form__options { min-height: 34px; display: flex; align-items: center; justify-content: space-between; }
.auth-form__error { margin: -2px 0 8px; color: #ff9da9; font-size: 12px; line-height: 1.5; }
.auth-form__options :deep(.el-checkbox__label) { color: #6884ac; font-size: 12px; }
.auth-form__options :deep(.el-checkbox__inner) { border-color: rgba(105,145,194,.52); background: rgba(255,255,255,.7); }
.auth-form__options :deep(.el-checkbox__input.is-checked .el-checkbox__inner) { border-color: var(--auth-blue); background: var(--auth-blue); }
.text-action, .auth-switch button { border: 0; color: #256ef1; background: transparent; font: inherit; cursor: pointer; }
.text-action { padding: 8px 0; font-size: 12px; }
.auth-submit { width: 100%; min-height: 50px; margin-top: 10px; border: 0; border-radius: 999px; color: white; background: linear-gradient(105deg, var(--auth-blue), var(--auth-purple)); box-shadow: 0 12px 25px rgba(74,107,237,.28); font-size: 14px; font-weight: 700; letter-spacing: .08em; transition: transform 180ms ease, box-shadow 180ms ease; }
.auth-submit:hover { transform: translateY(-1px); box-shadow: 0 16px 30px rgba(74,107,237,.36); }
.auth-divider { display: flex; align-items: center; gap: 12px; margin: 25px 0 18px; color: #8da3c1; font-size: 11px; }
.auth-divider::before, .auth-divider::after { content: ''; height: 1px; flex: 1; background: rgba(114,149,194,.2); }
.auth-providers { display: flex; justify-content: center; gap: 20px; }
.auth-providers button { width: 44px; height: 44px; display: grid; place-items: center; border: 1px solid rgba(255,255,255,.8); border-radius: 50%; color: #2e75dd; background: rgba(255,255,255,.48); font-size: 19px; cursor: pointer; transition: transform 180ms ease, background-color 180ms ease; }
.auth-providers button:hover { transform: translateY(-2px); background: rgba(255,255,255,.82); }
.auth-switch { margin: 21px 0 0; color: #7790b2; font-size: 12px; text-align: center; }
.auth-switch button { padding: 4px; font-weight: 700; }
.auth-legal { margin: 19px 0 0; color: #a1b2c9; font-size: 10px; line-height: 1.6; text-align: center; }
.auth-footer { width: min(100% - 96px, 1920px); margin: -2px auto 0; padding-bottom: 20px; display: flex; justify-content: space-between; color: #6f8bae; font-size: 10px; letter-spacing: .05em; }
.auth-brand:focus-visible, .auth-theme-toggle:focus-visible, .text-action:focus-visible, .auth-switch button:focus-visible, .auth-providers button:focus-visible, .auth-submit:focus-visible { outline: 3px solid rgba(36,143,240,.42); outline-offset: 3px; }
@media (max-width: 940px) { .auth-layout { width: min(100% - 56px, 680px); display: block; padding-top: 7vh; } .auth-intro { display: none; } .auth-card { max-width: 520px; margin: 0 auto; } }
@media (max-width: 560px) { .auth-view { overflow-y: auto; } .auth-topbar { width: calc(100% - 40px); min-height: 72px; } .auth-brand { font-size: 18px; } .auth-brand__logo { width: 32px; height: 32px; } .auth-theme-toggle span { display: none; } .auth-theme-toggle { margin-left: 8px; padding: 0 9px; } .auth-layout { width: calc(100% - 32px); min-height: auto; padding-top: 4vh; padding-bottom: 28px; } .auth-card { padding: 28px 22px 24px; border-radius: 20px; } .auth-card__heading h2 { font-size: 27px; } .auth-footer { width: calc(100% - 32px); padding-bottom: 16px; font-size: 9px; } }
@media (prefers-reduced-motion: reduce) { .auth-form :deep(.el-input__wrapper), .auth-submit, .auth-providers button { transition: none; } }

/* Tauri 隐藏了原生标题栏，桌面 shell 下由登录页顶栏兼任窗口拖拽区，
   右上角承载窗口控制按钮（纯 Web 版不渲染桌面 shell）。 */
.auth-view.is-desktop-shell { overflow-y: auto; scrollbar-gutter: stable; }
.auth-view.is-desktop-shell .auth-topbar { width: 100%; min-height: 52px; padding-left: 18px; box-sizing: border-box; }
.auth-view.is-desktop-shell :deep(.desktop-window-controls) { flex: 0 0 auto; height: 52px; align-self: center; margin-left: auto; }

/* Desktop windows can be as small as 1100x700. Keep the registration form,
   providers and legal copy available in one viewport while retaining scrolling
   as a safe fallback for the minimum window size. */
.auth-view.is-desktop-shell .auth-layout { min-height: calc(100dvh - 88px); padding-top: 16px; padding-bottom: 24px; }
.auth-view.is-desktop-shell .auth-card { padding: 28px 36px 22px; }
.auth-view.is-desktop-shell .auth-card__mark { width: 38px; height: 38px; margin-bottom: 15px; }
.auth-view.is-desktop-shell .auth-card__mark img { width: 25px; height: 25px; }
.auth-view.is-desktop-shell .auth-card__heading h2 { font-size: 27px; }
.auth-view.is-desktop-shell .auth-card__heading p { margin-bottom: 17px; }
.auth-view.is-desktop-shell .auth-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
.auth-view.is-desktop-shell .auth-tabs :deep(.el-tabs__item) { min-height: 38px; }
.auth-view.is-desktop-shell .auth-form :deep(.el-form-item) { margin-bottom: 20px; }
.auth-view.is-desktop-shell .auth-form :deep(.el-input__wrapper) { min-height: 43px; }
.auth-view.is-desktop-shell .auth-form__options { min-height: 28px; }
.auth-view.is-desktop-shell .auth-submit { min-height: 45px; margin-top: 5px; }
.auth-view.is-desktop-shell .auth-divider { margin: 17px 0 12px; }
.auth-view.is-desktop-shell .auth-providers { gap: 16px; }
.auth-view.is-desktop-shell .auth-providers button { width: 40px; height: 40px; }
.auth-view.is-desktop-shell .auth-switch { margin-top: 14px; }
.auth-view.is-desktop-shell .auth-legal { margin-top: 12px; }

/* 注册态收紧两栏构图：两侧各向中心移动一点，卡片整体上提，
   登录态保留原有的宽松节奏。 */
@media (min-width: 941px) {
  .auth-view.is-register .auth-layout {
    transform: none;
  }
  .auth-view .auth-card {
    position: relative;
    left: clamp(-72px, -3.4vw, -36px);
  }
  .auth-view.is-register .auth-intro {
    transform: translateY(-6px);
  }
  .auth-view.is-register .auth-card {
    transform: translateY(-24px);
  }
}

/* A browser can expose the same wide layout with a shorter viewport. Apply
   the same compact rhythm there so registration does not hide its lower
   actions behind the fold; overflow-y above remains the final fallback. */
@media (min-width: 941px) and (max-height: 980px) {
  .auth-layout { min-height: calc(100dvh - 88px); padding-top: 16px; padding-bottom: 24px; }
  .auth-card { padding: 28px 36px 22px; }
  .auth-card__mark { width: 38px; height: 38px; margin-bottom: 15px; }
  .auth-card__mark img { width: 25px; height: 25px; }
  .auth-card__heading h2 { font-size: 27px; }
  .auth-card__heading p { margin-bottom: 17px; }
  .auth-tabs :deep(.el-tabs__header) { margin-bottom: 16px; }
  .auth-tabs :deep(.el-tabs__item) { min-height: 38px; }
  .auth-form :deep(.el-form-item) { margin-bottom: 20px; }
  .auth-form :deep(.el-input__wrapper) { min-height: 43px; }
  .auth-form__options { min-height: 28px; }
  .auth-submit { min-height: 45px; margin-top: 5px; }
  .auth-divider { margin: 17px 0 12px; }
  .auth-providers { gap: 16px; }
  .auth-providers button { width: 40px; height: 40px; }
  .auth-switch { margin-top: 14px; }
  .auth-legal { margin-top: 12px; }
}

/* 窗口控件的取色变量指向登录页自己的 auth 色系——各页面的配色体系各自保留，
   不借用工作台顶栏的灰。 */
.auth-view.is-desktop-shell {
  --app-topbar-muted: var(--auth-muted);
  --app-topbar-hover: rgba(36, 158, 240, .08);
  --app-topbar-active: rgba(36, 158, 240, .13);
  --app-topbar-focus-ring: rgba(36, 158, 240, .45);
}

/* Shared dark login scene for web and desktop. The landing page and workbench
   keep their own visual systems; only the auth surface follows darkbg.webp. */
.auth-view.is-theme-dark {
  --auth-ink: #f1f6ff;
  --auth-muted: #a6b8d0;
  --auth-primary: var(--primary-color, #168bd4);
  --auth-accent: var(--accent-color, #55bcff);
  --auth-blue: var(--auth-accent);
  --auth-purple: var(--auth-primary);
  --auth-line: color-mix(in srgb, var(--auth-accent) 30%, transparent);
  --auth-field: rgba(3, 10, 21, .76);
  color-scheme: dark;
  background: #050914 url('/darkbg.webp') center / cover fixed no-repeat;

  &::before {
    background:
      radial-gradient(circle at 70% 42%, color-mix(in srgb, var(--auth-accent) 16%, transparent), transparent 38%),
      linear-gradient(90deg, rgba(3, 7, 15, .94) 0%, rgba(3, 10, 22, .76) 44%, rgba(3, 7, 15, .48) 100%),
      linear-gradient(180deg, rgba(1, 4, 10, .16), rgba(1, 4, 10, .72));
  }
  .auth-brand { color: #f1f6ff; }
  .auth-brand strong { color: color-mix(in srgb, var(--auth-accent) 42%, #f1f6ff); }
  .auth-theme-toggle { border-color: rgba(109, 189, 255, .3); color: #b7cbe4; background: rgba(9, 24, 46, .48); }
  .auth-theme-toggle:hover { border-color: rgba(109, 189, 255, .68); color: #f1f6ff; background: rgba(18, 44, 77, .76); }
  .auth-intro h1 { color: #f1f6ff; }
  .auth-intro h1 span { color: color-mix(in srgb, var(--auth-accent) 64%, #f1f6ff); }
  .auth-eyebrow { color: color-mix(in srgb, var(--auth-accent) 78%, #f1f6ff); }
  .auth-intro__lead { color: #afc2dc; }
  .auth-intro__features { color: #a7bdd8; }
  .auth-intro__features b { color: var(--auth-blue); }
  .auth-card {
    border-color: color-mix(in srgb, var(--auth-accent) 28%, transparent);
    background: linear-gradient(145deg, rgba(13, 29, 53, .86), rgba(4, 12, 25, .80));
    box-shadow: 0 26px 80px rgba(0, 0, 0, .46), inset 0 1px 0 rgba(220, 239, 255, .16);
  }
  .auth-card__mark {
    background: linear-gradient(145deg, color-mix(in srgb, var(--auth-accent) 40%, #17365d), color-mix(in srgb, var(--auth-primary) 48%, #101b3b));
    box-shadow: 0 8px 24px color-mix(in srgb, var(--auth-accent) 25%, transparent), inset 0 1px 0 rgba(255, 255, 255, .22);
  }
  .auth-card__heading h2 { color: #f1f6ff; }
  .auth-card__heading p { color: var(--auth-muted); }
  .auth-tabs :deep(.el-tabs__nav-wrap::after) { background: var(--auth-line); }
  .auth-tabs :deep(.el-tabs__item) { color: #8ea8c8; }
  .auth-tabs :deep(.el-tabs__item.is-active) { color: #f1f6ff; }
  .auth-form :deep(.el-form-item__label) { color: #a5beda; }
  .auth-form :deep(.el-input__wrapper) {
    border-color: rgba(135, 188, 241, .28) !important;
    background: var(--auth-field) !important;
    box-shadow: 0 1px 3px rgba(0, 0, 0, .42) inset !important;
  }
  .auth-form :deep(.el-input__wrapper:hover) {
    border-color: color-mix(in srgb, var(--auth-accent) 72%, transparent) !important;
    background: rgba(7, 20, 38, .88) !important;
  }
  .auth-form :deep(.el-input__wrapper.is-focus) {
    border-color: var(--auth-blue) !important;
    background: rgba(7, 20, 38, .94) !important;
    box-shadow: 0 0 0 3px color-mix(in srgb, var(--auth-accent) 20%, transparent) !important;
  }
  .auth-form :deep(.el-input__inner) { color: #eff6ff !important; }
  .auth-form :deep(.el-input__inner::placeholder) { color: #8ca6c5 !important; }
  .auth-form :deep(.el-input__prefix), .auth-form :deep(.el-input__suffix) { color: #7fcaff !important; }
  .auth-form__options :deep(.el-checkbox__label) { color: #a1b6d0; }
  .auth-form__options :deep(.el-checkbox__inner) {
    border-color: rgba(137, 187, 237, .42);
    background: rgba(5, 14, 28, .78);
  }
  .auth-form__options :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
    border-color: var(--auth-blue);
    background: var(--auth-blue);
  }
  .text-action, .auth-switch button { color: color-mix(in srgb, var(--auth-accent) 86%, #f1f6ff); }
  .auth-submit {
    background: linear-gradient(105deg, color-mix(in srgb, var(--auth-primary) 78%, #ffffff), color-mix(in srgb, var(--auth-accent) 72%, var(--auth-primary)));
    box-shadow: 0 12px 28px color-mix(in srgb, var(--auth-primary) 42%, transparent);
  }
  .auth-submit:hover { box-shadow: 0 16px 34px color-mix(in srgb, var(--auth-primary) 54%, transparent); }
  .auth-divider { color: #8da7c5; }
  .auth-divider::before, .auth-divider::after { background: var(--auth-line); }
  .auth-providers button {
    border-color: color-mix(in srgb, var(--auth-accent) 30%, transparent);
    color: color-mix(in srgb, var(--auth-accent) 82%, #f1f6ff);
    background: rgba(9, 24, 44, .62);
  }
  .auth-providers button:hover { background: color-mix(in srgb, var(--auth-primary) 30%, rgba(22, 52, 87, .86)); }
  .auth-switch { color: #9ab0ca; }
  .auth-legal { color: #8298b3; }
  .auth-footer { color: #8da7c4; }
  &.is-desktop-shell {
    --app-topbar-muted: #9eb4d0;
    --app-topbar-hover: color-mix(in srgb, var(--auth-accent) 12%, transparent);
    --app-topbar-active: color-mix(in srgb, var(--auth-accent) 20%, transparent);
    --app-topbar-focus-ring: color-mix(in srgb, var(--auth-accent) 55%, transparent);
  }
}

/* Embedded auth is a single replacement dialog for the landing agent slot.
   The standalone page keeps its full introduction and window chrome. */
.auth-view.is-embedded {
  width: 100%;
  min-width: 0;
  min-height: 100%;
  overflow: visible;
  display: grid;
  place-items: center;
  background: transparent;
  color-scheme: light;
}
.auth-view.is-embedded::before { display: none; }
.auth-view.is-embedded .auth-layout {
  width: 100%;
  min-height: 100%;
  margin: 0;
  padding: 0;
  display: block;
}
.auth-view.is-embedded .auth-card {
  position: relative;
  left: 0;
  transform: translateY(clamp(-16px, -1.4vh, -6px));
  width: min(100%, 520px);
  max-width: 100%;
  margin: 0 auto;
  padding: 38px 56px 40px;
  overflow: hidden;
  border-color: rgba(255, 255, 255, .78);
  border-radius: 28px;
  background: linear-gradient(145deg, rgba(255, 255, 255, .78), rgba(241, 248, 255, .64));
  -webkit-backdrop-filter: blur(24px) saturate(138%);
  backdrop-filter: blur(24px) saturate(138%);
  box-shadow: 0 24px 64px rgba(65, 105, 164, .2), inset 0 1px 0 rgba(255, 255, 255, .9);
}
.auth-view.is-embedded .auth-card::before {
  display: none;
}
.auth-view.is-embedded .auth-card::after {
  display: none;
}
.auth-view.is-embedded .auth-card > *:not(.auth-card__close) { position: relative; z-index: 1; }
.auth-card__eyebrow {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: #55789d;
  font-size: 10px;
  font-weight: 750;
  letter-spacing: .18em;
}
.auth-card__eyebrow span {
  width: 6px;
  height: 6px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #38b9e8;
  box-shadow: 0 0 0 4px rgba(56, 185, 232, .14), 0 0 14px rgba(56, 185, 232, .72);
}
.auth-card__close {
  position: absolute;
  top: 15px;
  right: 17px;
  width: 30px;
  height: 30px;
  padding: 0;
  border: 1px solid rgba(96, 143, 190, .28);
  border-radius: 50%;
  color: #4b6d91;
  background: rgba(255, 255, 255, .46);
  font-size: 21px;
  font-weight: 300;
  line-height: 1;
  cursor: pointer;
  z-index: 2;
  transition: border-color 180ms ease, color 180ms ease, background-color 180ms ease, transform 180ms ease;
}
.auth-card__close:hover { border-color: #4a9ed4; color: #23486f; background: rgba(255, 255, 255, .82); transform: translateY(-1px); }
.auth-view.is-embedded .auth-card__mark { width: 40px; height: 40px; margin-bottom: 20px; border: 1px solid rgba(91, 137, 185, .18); background: rgba(255, 255, 255, .44); box-shadow: none; }
.auth-view.is-embedded .auth-card__mark img { width: 26px; height: 26px; }
.auth-view.is-embedded .auth-card__eyebrow { display: none; }
.auth-view.is-embedded .auth-card__eyebrow span { display: none; }
.auth-view.is-embedded .auth-card__heading h2 { color: #173a63; font-size: 31px; letter-spacing: -.05em; text-shadow: none; }
.auth-view.is-embedded .auth-card__heading > p:not(.auth-card__eyebrow) { max-width: none; margin: 9px 0 24px; color: #5f7d9e; font-size: 13px; line-height: 1.65; }
.auth-view.is-embedded .auth-tabs :deep(.el-tabs__header) { margin-bottom: 20px; }
.auth-view.is-embedded .auth-tabs :deep(.el-tabs__nav-wrap::after) { background: rgba(89, 137, 185, .26); }
.auth-view.is-embedded .auth-tabs :deep(.el-tabs__item) { min-height: 40px; color: #7894b2; font-size: 13px; }
.auth-view.is-embedded .auth-tabs :deep(.el-tabs__item.is-active) { color: #244b73; }
.auth-view.is-embedded .auth-tabs :deep(.el-tabs__active-bar) { height: 2px; background: #3f8fd2; }
.auth-view.is-embedded .auth-form :deep(.el-form-item) { margin-bottom: 22px; }
.auth-view.is-embedded .auth-form :deep(.el-form-item__label) { color: #527397; }
.auth-view.is-embedded .auth-form :deep(.el-input__wrapper) { min-height: 50px; border-radius: 14px; border-color: rgba(91, 137, 185, .32) !important; background: rgba(255, 255, 255, .56) !important; box-shadow: 0 1px 2px rgba(59, 106, 158, .07) inset !important; }
.auth-view.is-embedded .auth-form :deep(.el-input__wrapper:hover) { border-color: rgba(53, 157, 214, .62) !important; background: rgba(255, 255, 255, .72) !important; }
.auth-view.is-embedded .auth-form :deep(.el-input__wrapper.is-focus) { border-color: #4aa9dc !important; background: rgba(255, 255, 255, .86) !important; box-shadow: 0 0 0 3px rgba(62, 169, 223, .14) !important; }
.auth-view.is-embedded .auth-form :deep(.el-input__inner) { color: #24496f !important; }
.auth-view.is-embedded .auth-form :deep(.el-input__inner::placeholder) { color: #7b96b3 !important; }
.auth-view.is-embedded .auth-form :deep(.el-input__prefix), .auth-view.is-embedded .auth-form :deep(.el-input__suffix) { color: #4d94c4 !important; }
.auth-view.is-embedded .auth-form__error { color: #c45a66; }
.auth-view.is-embedded .auth-form__options :deep(.el-checkbox__label) { color: #6683a1; }
.auth-view.is-embedded .auth-form__options :deep(.el-checkbox__inner) { border-color: rgba(87, 137, 187, .48); background: rgba(255, 255, 255, .58); }
.auth-view.is-embedded .auth-form__options :deep(.el-checkbox__input.is-checked .el-checkbox__inner) { border-color: #4b9ed5; background: #4b9ed5; }
.auth-view.is-embedded .text-action { color: #277ec0; }
.auth-view.is-embedded .auth-form__options { min-height: 32px; }
.auth-view.is-embedded .auth-submit { min-height: 50px; margin-top: 10px; background: #5d61d8; box-shadow: 0 12px 24px rgba(70, 88, 190, .24); }
.auth-view.is-embedded .auth-submit:hover { box-shadow: 0 15px 28px rgba(70, 88, 190, .3); }
.auth-view.is-embedded .auth-card__close:focus-visible { outline: 3px solid rgba(67, 158, 215, .38); outline-offset: 3px; }
@media (max-width: 940px) {
  .auth-view.is-embedded .auth-card { transform: none; }
}
@media (max-width: 560px) {
  .auth-view.is-embedded .auth-card {
    width: min(100%, 420px);
    padding: 32px 24px 34px;
    border-radius: 24px;
  }
}
</style>
