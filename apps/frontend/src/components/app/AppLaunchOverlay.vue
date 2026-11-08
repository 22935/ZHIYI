<!--
  启动/过渡页：纯视觉入口，不参与鉴权。

  N03 是本机单用户形态（无账号密码、身份由本机 home 自动就绪），因此这里
  刻意不做登录表单、不写 token、不请求后端健康接口、也不改变路由。它只负责
  在冷启动时盖住异步加载的应用壳，提供品牌感与「进入工作台」的可控入口：
  到时自动收起、可点击/按 Esc 立即跳过、每个浏览器会话只出现一次。
-->
<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="launch-overlay"
      data-testid="app-launch-overlay"
      role="status"
      aria-live="polite"
      aria-label="知弈 AgentOS 启动页"
      :style="{ '--launch-duration': `${durationMs}ms` }"
    >
      <div class="launch-overlay__glow" aria-hidden="true" />
      <!-- 背景立即不透明：冷启动瞬间就盖住未加载完的界面；只有卡片淡入。 -->
      <Transition name="launch-card-fade" appear>
        <section class="launch-card">
          <p class="launch-card__eyebrow">ZHIYI · LOCAL WORKSPACE</p>
          <BrandLoader :size="76" />
          <h1 class="launch-card__title">知弈 AgentOS</h1>
          <p class="launch-card__subtitle">本机工作空间 · 无需账号密码</p>

          <div class="launch-card__chips" aria-hidden="true">
            <span>本机身份</span>
            <span>执行闭环</span>
            <span>虚拟伙伴</span>
          </div>

          <div class="launch-progress" aria-hidden="true"><i /></div>
          <p class="launch-card__status">正在准备界面，马上就好…</p>

          <button
            type="button"
            class="launch-enter"
            data-testid="app-launch-enter"
            @click="dismiss"
          >
            进入工作台
          </button>
          <p class="launch-card__hint">按 Esc 跳过 · 稍后自动进入</p>
        </section>
      </Transition>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import BrandLoader from '@/components/common/BrandLoader.vue'

/** 每个浏览器会话只显示一次；`?splash=1` 可强制重现，便于验收与演示。 */
const SESSION_KEY = 'kinlin.launchOverlay.v1'
const DEFAULT_MS = 2600
const REDUCED_MS = 700

const visible = ref(false)
const durationMs = ref(DEFAULT_MS)
let timer: number | null = null

const prefersReducedMotion = (): boolean =>
  typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false

const forceShow = (): boolean => {
  try {
    return new URLSearchParams(window.location.search).get('splash') === '1'
  } catch {
    return false
  }
}

const alreadyShown = (): boolean => {
  try {
    return window.sessionStorage.getItem(SESSION_KEY) !== null
  } catch {
    return false
  }
}

const markShown = (): void => {
  try {
    window.sessionStorage.setItem(SESSION_KEY, '1')
  } catch {
    // 隐私模式或存储被禁用时不影响启动，只退化为每次都显示。
  }
}

const dismiss = (): void => {
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
  visible.value = false
  window.removeEventListener('keydown', onKeydown)
}

const onKeydown = (event: KeyboardEvent): void => {
  if (event.key === 'Escape') dismiss()
}

onMounted(() => {
  if (!forceShow() && alreadyShown()) return
  durationMs.value = prefersReducedMotion() ? REDUCED_MS : DEFAULT_MS
  visible.value = true
  markShown()
  window.addEventListener('keydown', onKeydown)
  timer = window.setTimeout(dismiss, durationMs.value)
})

onUnmounted(() => {
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
  window.removeEventListener('keydown', onKeydown)
})
</script>

<style scoped>
.launch-overlay {
  position: fixed;
  inset: 0;
  z-index: 4000;
  display: grid;
  place-items: center;
  padding: 24px;
  color: var(--text-primary);
  /* 接近全不透明：冷启动时背后的 Offline 提示/未加载完的界面不应透出来，
     否则启动页会像「盖在故障界面上的一层灰」，破坏独立入口的观感。 */
  background: color-mix(in srgb, var(--bg-app, #181818) 97%, transparent);
  backdrop-filter: blur(24px);
  -webkit-app-region: no-drag;
}

.launch-overlay__glow {
  position: absolute;
  width: min(760px, 92vw);
  height: min(760px, 92vw);
  border-radius: 50%;
  background: radial-gradient(circle, var(--accent-fade, rgba(79, 193, 255, .14)), transparent 68%);
  animation: launch-glow 6s ease-in-out infinite;
  pointer-events: none;
}

.launch-card {
  position: relative;
  display: grid;
  justify-items: center;
  width: min(440px, 100%);
  padding: 38px 40px 30px;
  border: 1px solid var(--border-light, #3c3c3c);
  border-radius: 20px;
  background: color-mix(in srgb, var(--bg-card, #252526) 92%, transparent);
  box-shadow: 0 24px 70px rgba(0, 0, 0, .32);
  text-align: center;
}

.launch-card__eyebrow {
  margin: 0 0 18px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: .22em;
  color: var(--text-muted, #858585);
}

.launch-card__title {
  margin: 18px 0 6px;
  font-size: 26px;
  font-weight: 600;
  letter-spacing: .04em;
  color: var(--text-primary);
}

.launch-card__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary, #a6a6a6);
}

.launch-card__chips {
  display: flex;
  gap: 8px;
  margin: 22px 0 24px;
}

.launch-card__chips span {
  padding: 4px 10px;
  border: 1px solid var(--border-light, #3c3c3c);
  border-radius: 999px;
  font-size: 11px;
  color: var(--text-secondary, #a6a6a6);
}

.launch-progress {
  width: 220px;
  max-width: 100%;
  height: 3px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--border-light, #3c3c3c);
}

.launch-progress i {
  display: block;
  width: 100%;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--primary-color, #0e639c), var(--accent-color, #4fc1ff));
  transform-origin: left center;
  animation: launch-progress var(--launch-duration, 2600ms) linear forwards;
}

.launch-card__status {
  margin: 12px 0 22px;
  font-size: 12px;
  color: var(--text-muted, #858585);
}

.launch-enter {
  min-width: 168px;
  padding: 10px 22px;
  border: 1px solid color-mix(in srgb, var(--accent-color, #4fc1ff) 42%, transparent);
  border-radius: 10px;
  background: linear-gradient(135deg, var(--primary-color, #0e639c), var(--primary-hover, #1177bb));
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: transform .18s ease, filter .18s ease;
  -webkit-app-region: no-drag;
}

.launch-enter:hover { filter: brightness(1.12); transform: translateY(-1px); }
.launch-enter:focus-visible { outline: 2px solid var(--border-focus, rgba(79, 193, 255, .68)); outline-offset: 3px; }

.launch-card__hint {
  margin: 14px 0 0;
  font-size: 11px;
  color: var(--text-disabled, #5a5a5a);
}

.launch-card-fade-enter-active { transition: opacity .38s ease, transform .38s ease; }
.launch-card-fade-enter-from { opacity: 0; transform: translateY(10px); }

@keyframes launch-progress {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}

@keyframes launch-glow {
  0%, 100% { opacity: .55; transform: scale(.94); }
  50% { opacity: 1; transform: scale(1.06); }
}

@media (prefers-reduced-motion: reduce) {
  .launch-overlay__glow { animation: none; }
  .launch-progress i { animation-duration: 1ms; }
  .launch-enter { transition: none; }
  .launch-card-fade-enter-active { transition-duration: 1ms; }
}
</style>
