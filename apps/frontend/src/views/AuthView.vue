<!--
  单一认证路由：登录与注册共用一个页面（页内切换），由 router 守卫统一跳转到此。

  边界：账号库保存在浏览器本机存储，用于本机入口的身份校验；后端 N03 仍是
  单用户 LocalIdentity，不读取这里的账号，也不签发服务端会话。
-->
<template>
  <main class="auth-view" data-testid="auth-view">
    <div class="auth-view__aurora" aria-hidden="true" />
    <div class="auth-view__grid" aria-hidden="true" />

    <section class="auth-shell">
      <aside class="auth-brand">
        <div class="auth-brand__mark" aria-hidden="true">
          <BrandLoader :size="58" />
        </div>
        <p class="auth-brand__eyebrow">ZHIYI · LOCAL WORKSPACE</p>
        <h1>知弈 AgentOS</h1>
        <p class="auth-brand__lead">把复杂任务交给可追溯的执行闭环，<br />把上下文留在你自己的机器上。</p>

        <ul class="auth-brand__features">
          <li><span>01</span>本机身份与数据隔离</li>
          <li><span>02</span>任务规划 · 执行 · 恢复</li>
          <li><span>03</span>常驻虚拟伙伴与语音交互</li>
        </ul>

        <p class="auth-brand__foot">账号仅保存在本机浏览器 · 不上传云端</p>
      </aside>

      <section class="auth-panel">
        <header class="auth-panel__head">
          <h2>{{ mode === 'login' ? '欢迎回来' : '创建本机账号' }}</h2>
          <p>{{ mode === 'login' ? '登录后继续使用你的工作空间' : '只需几步，即可开始使用' }}</p>
        </header>

        <div class="auth-tabs" role="tablist" aria-label="登录或注册">
          <button
            type="button"
            role="tab"
            data-testid="auth-tab-login"
            :aria-selected="mode === 'login'"
            :class="{ active: mode === 'login' }"
            @click="switchMode('login')"
          >登录</button>
          <button
            type="button"
            role="tab"
            data-testid="auth-tab-register"
            :aria-selected="mode === 'register'"
            :class="{ active: mode === 'register' }"
            @click="switchMode('register')"
          >注册</button>
        </div>

        <form class="auth-form" novalidate @submit.prevent="submit">
          <template v-if="mode === 'login'">
            <label class="auth-field">
              <span>用户名或邮箱</span>
              <input
                v-model.trim="identifier"
                data-testid="auth-identifier"
                type="text"
                autocomplete="username"
                placeholder="请输入用户名或邮箱"
                :aria-invalid="Boolean(fieldErrors.identifier)"
              />
              <small v-if="fieldErrors.identifier">{{ fieldErrors.identifier }}</small>
            </label>
          </template>

          <template v-else>
            <label class="auth-field">
              <span>用户名</span>
              <input
                v-model.trim="username"
                data-testid="auth-username"
                type="text"
                autocomplete="username"
                placeholder="3–20 位字母、数字、下划线或中文"
                :aria-invalid="Boolean(fieldErrors.username)"
              />
              <small v-if="fieldErrors.username">{{ fieldErrors.username }}</small>
            </label>
            <label class="auth-field">
              <span>邮箱</span>
              <input
                v-model.trim="email"
                data-testid="auth-email"
                type="email"
                autocomplete="email"
                placeholder="you@example.com"
                :aria-invalid="Boolean(fieldErrors.email)"
              />
              <small v-if="fieldErrors.email">{{ fieldErrors.email }}</small>
            </label>
          </template>

          <label class="auth-field">
            <span>密码</span>
            <input
              v-model="password"
              data-testid="auth-password"
              type="password"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              placeholder="8–32 位，含字母和数字"
              :aria-invalid="Boolean(fieldErrors.password)"
            />
            <small v-if="fieldErrors.password">{{ fieldErrors.password }}</small>
          </label>

          <label v-if="mode === 'register'" class="auth-field">
            <span>确认密码</span>
            <input
              v-model="confirmPassword"
              data-testid="auth-confirm"
              type="password"
              autocomplete="new-password"
              placeholder="再次输入密码"
              :aria-invalid="Boolean(fieldErrors.confirmPassword)"
            />
            <small v-if="fieldErrors.confirmPassword">{{ fieldErrors.confirmPassword }}</small>
          </label>

          <label v-else class="auth-remember">
            <input v-model="remember" data-testid="auth-remember" type="checkbox" />
            <span>记住登录（30 天）</span>
          </label>

          <p
            v-if="message"
            class="auth-message"
            :class="`auth-message--${messageType}`"
            data-testid="auth-message"
            role="status"
            aria-live="polite"
          >{{ message }}</p>

          <button
            class="auth-submit"
            data-testid="auth-submit"
            type="submit"
            :disabled="busy"
          >
            {{ busy ? '正在验证…' : (mode === 'login' ? '登录并进入工作台' : '注册并进入工作台') }}
          </button>
        </form>

        <p class="auth-switch" data-testid="auth-switch">
          {{ mode === 'login' ? '还没有账号？' : '已经有账号了？' }}
          <button type="button" @click="switchMode(mode === 'login' ? 'register' : 'login')">
            {{ mode === 'login' ? '立即注册' : '返回登录' }}
          </button>
        </p>

        <p class="auth-note">连续 5 次密码错误将锁定 30 秒 · 口令经 PBKDF2 加盐派生后保存</p>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import BrandLoader from '@/components/common/BrandLoader.vue'
import {
  AUTH_ROUTE,
  DEFAULT_REDIRECT,
  login,
  register
} from '@/features/auth/authService'
import type { AuthField, AuthMode } from '@/features/auth/types'
import { validateLogin, validateRegister } from '@/features/auth/validation'

const route = useRoute()
const router = useRouter()

const mode = ref<AuthMode>(route.query.mode === 'register' ? 'register' : 'login')
const identifier = ref('')
const username = ref('')
const email = ref('')
const password = ref('')
const confirmPassword = ref('')
const remember = ref(false)
const busy = ref(false)
const message = ref('')
const messageType = ref<'error' | 'success'>('error')
const fieldErrors = ref<Partial<Record<AuthField, string>>>({})

/** 只接受站内绝对路径，避免 ?redirect= 变成开放重定向。 */
const safeRedirect = (value: unknown): string => {
  if (typeof value !== 'string' || !value.startsWith('/') || value.startsWith('//')) {
    return DEFAULT_REDIRECT
  }
  return value === AUTH_ROUTE ? DEFAULT_REDIRECT : value
}

const switchMode = (next: AuthMode): void => {
  if (busy.value || mode.value === next) return
  mode.value = next
  message.value = ''
  fieldErrors.value = {}
  password.value = ''
  confirmPassword.value = ''
}

const submit = async (): Promise<void> => {
  if (busy.value) return
  message.value = ''
  fieldErrors.value = {}

  const payload = mode.value === 'login'
    ? { identifier: identifier.value, password: password.value, remember: remember.value }
    : {
      username: username.value,
      email: email.value,
      password: password.value,
      confirmPassword: confirmPassword.value
    }
  const issues = mode.value === 'login' ? validateLogin(payload) : validateRegister(payload)
  if (issues.length) {
    fieldErrors.value = Object.fromEntries(issues.map(issue => [issue.field, issue.message]))
    message.value = issues[0].message
    messageType.value = 'error'
    return
  }

  busy.value = true
  try {
    const result = mode.value === 'login' ? await login(payload) : await register(payload)
    if (!result.ok) {
      message.value = result.message
      messageType.value = 'error'
      return
    }
    message.value = result.message
    messageType.value = 'success'
    await router.replace(safeRedirect(route.query.redirect))
  } catch (error) {
    message.value = error instanceof Error ? error.message : '验证失败，请稍后重试'
    messageType.value = 'error'
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.auth-view {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 100vh;
  padding: 32px 20px;
  overflow: hidden;
  color: #e8edf5;
  background: radial-gradient(circle at 18% 18%, #16283a 0%, transparent 46%),
    radial-gradient(circle at 82% 82%, #241d3a 0%, transparent 48%), #0d1117;
  font-family: var(--font-family, "Inter", "PingFang SC", "Microsoft YaHei", sans-serif);
}

.auth-view__aurora {
  position: absolute;
  top: -30%;
  left: 50%;
  width: 900px;
  height: 900px;
  transform: translateX(-50%);
  border-radius: 50%;
  background: radial-gradient(circle, rgba(79, 193, 255, .13), transparent 65%);
  filter: blur(20px);
  pointer-events: none;
}

.auth-view__grid {
  position: absolute;
  inset: 0;
  background-image: linear-gradient(rgba(255, 255, 255, .022) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, .022) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(circle at center, #000 20%, transparent 78%);
  pointer-events: none;
}

.auth-shell {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 400px) minmax(0, 440px);
  width: min(900px, 100%);
  border: 1px solid rgba(255, 255, 255, .09);
  border-radius: 22px;
  overflow: hidden;
  background: rgba(20, 25, 34, .82);
  box-shadow: 0 32px 90px rgba(0, 0, 0, .48);
  backdrop-filter: blur(18px);
}

.auth-brand {
  display: flex;
  flex-direction: column;
  padding: 44px 38px;
  background: linear-gradient(155deg, rgba(79, 193, 255, .1), rgba(139, 108, 255, .08) 58%, transparent);
  border-right: 1px solid rgba(255, 255, 255, .07);
}

.auth-brand__mark { margin-bottom: 30px; }
.auth-brand__eyebrow {
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .2em;
  color: #79c9f5;
}
.auth-brand h1 { margin: 0 0 14px; font-size: 30px; font-weight: 650; letter-spacing: .01em; }
.auth-brand__lead { margin: 0; font-size: 13px; line-height: 1.9; color: #a9b6c8; }

.auth-brand__features {
  display: grid;
  gap: 14px;
  margin: 42px 0 0;
  padding: 0;
  list-style: none;
}
.auth-brand__features li {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: #c4cfdd;
}
.auth-brand__features span {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  color: #4fc1ff;
}
.auth-brand__foot { margin: auto 0 0; padding-top: 34px; font-size: 11px; color: #74839a; }

.auth-panel { padding: 40px 38px 32px; }
.auth-panel__head h2 { margin: 0 0 6px; font-size: 23px; font-weight: 650; }
.auth-panel__head p { margin: 0 0 24px; font-size: 12.5px; color: #8e9bb0; }

.auth-tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
  margin-bottom: 24px;
  padding: 4px;
  border-radius: 11px;
  background: rgba(255, 255, 255, .045);
}
.auth-tabs button {
  padding: 9px 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: #8e9bb0;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background .18s ease, color .18s ease;
}
.auth-tabs button.active { background: rgba(79, 193, 255, .15); color: #8fd7ff; }
.auth-tabs button:hover:not(.active) { color: #d5dfeb; }

.auth-form { display: grid; gap: 15px; }
.auth-field { display: grid; gap: 7px; }
.auth-field > span { font-size: 12px; font-weight: 600; color: #b8c4d4; }
.auth-field input {
  width: 100%;
  box-sizing: border-box;
  padding: 11px 13px;
  border: 1px solid rgba(255, 255, 255, .11);
  border-radius: 9px;
  outline: none;
  background: rgba(9, 13, 20, .62);
  color: #e8edf5;
  font-size: 13px;
  transition: border-color .18s ease, box-shadow .18s ease;
}
.auth-field input::placeholder { color: #5f6c7e; }
.auth-field input:focus {
  border-color: rgba(79, 193, 255, .65);
  box-shadow: 0 0 0 3px rgba(79, 193, 255, .12);
}
.auth-field input[aria-invalid="true"] { border-color: rgba(255, 116, 116, .7); }
.auth-field small { font-size: 11px; color: #ff8e8e; }

.auth-remember { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #9aa8bb; cursor: pointer; }
.auth-remember input { accent-color: #4fc1ff; }

.auth-message {
  margin: 0;
  padding: 9px 12px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.6;
}
.auth-message--error { background: rgba(255, 99, 99, .1); color: #ff9d9d; }
.auth-message--success { background: rgba(76, 209, 148, .12); color: #8ce0b8; }

.auth-submit {
  margin-top: 4px;
  padding: 12px 0;
  border: 0;
  border-radius: 9px;
  background: linear-gradient(100deg, #3aa9ee, #6a7cf0);
  color: #fff;
  font-size: 13.5px;
  font-weight: 650;
  letter-spacing: .02em;
  cursor: pointer;
  transition: filter .18s ease, transform .18s ease;
}
.auth-submit:hover:not(:disabled) { filter: brightness(1.1); transform: translateY(-1px); }
.auth-submit:disabled { opacity: .62; cursor: progress; }

.auth-switch { margin: 20px 0 0; text-align: center; font-size: 12px; color: #8e9bb0; }
.auth-switch button {
  border: 0;
  background: none;
  padding: 0 2px;
  color: #79c9f5;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.auth-switch button:hover { text-decoration: underline; }
.auth-note { margin: 22px 0 0; text-align: center; font-size: 10.5px; line-height: 1.7; color: #63728a; }

@media (max-width: 820px) {
  .auth-shell { grid-template-columns: 1fr; width: min(450px, 100%); }
  .auth-brand { display: none; }
  .auth-panel { padding: 34px 28px 28px; }
}
@media (prefers-reduced-motion: reduce) {
  .auth-submit, .auth-tabs button, .auth-field input { transition: none; }
}
</style>
