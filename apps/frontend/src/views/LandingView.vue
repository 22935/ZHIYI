<template>
  <main ref="landingRoot" class="landing-view" :class="{ 'is-desktop-shell': desktopShell, 'is-theme-dark': isDarkTheme }" aria-label="知弈 AgentOS 公开首页" @wheel="handleWheel">
      <div class="landing-surface">
        <div class="landing-atmosphere" aria-hidden="true"></div>

    <header class="landing-header" v-bind="dragRegionProps" aria-label="应用窗口标题栏">
      <a class="landing-brand" href="/" aria-label="知弈 AgentOS 首页" @click.prevent="goHome">
        <span class="landing-brand__logo"><img src="/logo.webp" alt="" aria-hidden="true" /></span>
        <span>知弈 <strong>AgentOS</strong></span>
      </a>

      <nav class="landing-nav" aria-label="主导航">
        <a
          v-for="item in navigation"
          :key="item.id"
          :class="{ 'is-active': activeSection === item.id }"
          :href="`#${item.id}`"
          :aria-current="activeSection === item.id ? 'page' : undefined"
          @click.prevent="goToSection(item.id)"
        >{{ item.label }}</a>
      </nav>

      <div class="landing-header__actions">
        <span class="landing-header__note">More Agents <i aria-hidden="true">·</i> More Possibilities</span>
        <button
          class="landing-theme-toggle"
          data-testid="landing-theme-toggle"
          type="button"
          :aria-label="themeToggleLabel"
          :title="themeToggleLabel"
          @click="toggleTheme"
        >
          <el-icon aria-hidden="true"><Sunny v-if="isDarkTheme" /><Moon v-else /></el-icon>
          <span>{{ isDarkTheme ? '黑暗' : '明亮' }}</span>
        </button>
      </div>
      <DesktopWindowControls v-if="desktopShell" />
    </header>

    <div class="landing-track" :style="trackStyle">
      <section id="home" data-testid="landing-page-home" class="landing-page landing-page--hero" :class="{ 'is-active': activeSection === 'home', 'is-auth-open': authOpen }" :aria-hidden="activeSection !== 'home'" aria-labelledby="landing-title">
        <div class="landing-page__inner landing-page__inner--hero">
          <div class="landing-hero__copy landing-page__content">
            <p class="landing-eyebrow">COLLECTIVE INTELLIGENCE</p>
            <h1 id="landing-title">知弈 <span>AgentOS</span></h1>
            <h2>让智能体成为协作者</h2>
            <p class="landing-lead">一个目标，多个角色，一起完成。</p>
            <button class="landing-cta" type="button" data-testid="landing-cta" @click="goToLogin">
              探索知弈 AgentOS
              <el-icon aria-hidden="true"><ArrowRight /></el-icon>
            </button>
          </div>
          <div class="landing-agent-slot" data-testid="landing-agent-slot">
            <LoginView v-if="authOpen" embedded @back="closeAuth" />
            <GlassConstellation v-else />
          </div>
        </div>
      </section>

      <section id="features" data-testid="landing-page-features" class="landing-page landing-page--section" :class="{ 'is-active': activeSection === 'features' }" :aria-hidden="activeSection !== 'features'" aria-labelledby="features-title">
        <div class="landing-page__inner">
          <div class="landing-page__content landing-section__heading">
            <p class="landing-eyebrow">WORKFLOW</p>
            <h2 id="features-title">从目标，到结果</h2>
            <p class="landing-section__intro">理解、协作、交付。</p>
          </div>
          <div class="landing-info-grid landing-info-grid--three">
            <article v-for="item in workflowFeatures" :key="item.title" class="landing-info-card">
              <span class="landing-info-card__index">{{ item.index }}</span>
              <h3>{{ item.title }}</h3>
              <p>{{ item.description }}</p>
              <span class="landing-info-card__meta">{{ item.meta }}</span>
            </article>
          </div>
        </div>
      </section>

      <section id="ecosystem" data-testid="landing-page-ecosystem" class="landing-page landing-page--section" :class="{ 'is-active': activeSection === 'ecosystem' }" :aria-hidden="activeSection !== 'ecosystem'" aria-labelledby="ecosystem-title">
        <div class="landing-page__inner">
          <div class="landing-page__content landing-section__heading">
            <p class="landing-eyebrow">ECOSYSTEM</p>
            <h2 id="ecosystem-title">连接模型、知识与智能体</h2>
            <p class="landing-section__intro">需要什么，就调用什么。</p>
          </div>
          <div class="landing-info-grid landing-info-grid--two">
            <article v-for="item in ecosystemFeatures" :key="item.title" class="landing-info-card">
              <span class="landing-info-card__index">{{ item.index }}</span>
              <h3>{{ item.title }}</h3>
              <p>{{ item.description }}</p>
              <span class="landing-info-card__meta">{{ item.meta }}</span>
            </article>
          </div>
        </div>
      </section>

      <section id="about" data-testid="landing-page-about" class="landing-page landing-page--section landing-page--last" :class="{ 'is-active': activeSection === 'about' }" :aria-hidden="activeSection !== 'about'" aria-labelledby="about-title">
        <div class="landing-page__inner landing-page__inner--about">
          <div class="about-team__copy landing-page__content">
            <p class="landing-eyebrow">ABOUT THE TEAM</p>
            <h2 id="about-title">二龙山<br /><span>游击队</span></h2>
            <p class="about-team__lead">保持好奇，保持行动。</p>
            <p class="about-team__note">我们在想法、技术与作品之间穿行，寻找值得被看见的答案。</p>
          </div>
          <aside class="about-contact-card" aria-label="二龙山游击队联系方式">
            <div class="about-contact-card__top">
              <span>CONTACT</span>
              <span>01 / 01</span>
            </div>
            <div class="about-contact-card__item">
              <span class="about-contact-card__label">PHONE / 电话</span>
              <span class="about-contact-card__value">18703442157</span>
            </div>
            <div class="about-contact-card__item">
              <span class="about-contact-card__label">EMAIL / 邮箱</span>
              <span class="about-contact-card__value">2293581974@qq.com</span>
            </div>
            <p class="about-contact-card__hint">欢迎交流项目、合作与新的想法。</p>
            <button class="landing-cta landing-cta--small about-team__cta" type="button" @click="goToLogin">进入 AgentOS</button>
          </aside>
        </div>
      </section>
    </div>

        <footer class="landing-footer" aria-label="首页分页">
          <span class="landing-footer__status">0{{ activeIndex + 1 }} / 0{{ navigation.length }}</span>
          <div class="landing-footer__dots">
            <button
              v-for="(item, index) in navigation"
              :key="item.id"
              type="button"
              :class="{ 'is-active': activeIndex === index }"
              :aria-label="`前往${item.label}`"
              :aria-current="activeIndex === index ? 'page' : undefined"
              @click="goToSection(item.id)"
            ></button>
          </div>
          <span class="landing-footer__caption">SCROLL TO EXPLORE</span>
        </footer>
      </div>
  </main>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowRight, Moon, Sunny } from '@element-plus/icons-vue'
import { useRoute, useRouter } from 'vue-router'
import DesktopWindowControls from '@window-controls'
import { isDesktop, platform } from '@/platform'
import { usePublicTheme } from '@/composables/usePublicTheme'
import { AUTH_ROUTE, DEFAULT_REDIRECT, isAuthenticated } from '@/features/auth/authService'
const GlassConstellation = defineAsyncComponent(() => import('@/components/landing/GlassConstellation.vue').then(module => module.default))
const LoginView = defineAsyncComponent(() => import('@/views/LoginView.vue').then(module => module.default))

const router = useRouter()
const route = useRoute()
const { isDarkTheme, themeToggleLabel, toggleTheme } = usePublicTheme()
const desktopShell = isDesktop()
const dragRegionProps = platform.dragRegionProps
const landingRoot = ref<HTMLElement | null>(null)
const navigation = [
  { id: 'home', label: '首页' },
  { id: 'features', label: '功能' },
  { id: 'ecosystem', label: '生态' },
  { id: 'about', label: '关于' }
] as const
const sectionIndex = (hash: string | undefined) => {
  const id = (hash || '').replace(/^#/, '')
  const index = navigation.findIndex(item => item.id === id)
  return index >= 0 ? index : 0
}
const activeIndex = ref(sectionIndex(route.hash))
const activeSection = computed(() => navigation[activeIndex.value].id)
const trackStyle = computed(() => ({ transform: `translate3d(0px, -${activeIndex.value * 25}%, 0px)` }))
const authOpen = ref(route.query.auth === '1')

const workflowFeatures = [
  { index: '01 / UNDERSTAND', title: '理解与规划', description: '拆解目标，建立路径。', meta: 'Context → Plan' },
  { index: '02 / COLLABORATE', title: '协作与执行', description: '明确分工，并行推进。', meta: 'Roles → Actions' },
  { index: '03 / DELIVER', title: '复核与交付', description: '保留依据，交付结果。', meta: 'Evidence → Outcome' }
]

const ecosystemFeatures = [
  { index: 'MODEL LAYER', title: '模型与资源', description: '统一管理模型与工具。', meta: 'One place' },
  { index: 'KNOWLEDGE LAYER', title: '知识与工作流', description: '让知识进入工作流。', meta: 'Knowledge → Action' }
]

let wheelLocked = false
let wheelUnlockTimer: number | undefined

const setPage = (index: number) => {
  if (index < 0 || index >= navigation.length || index === activeIndex.value) return
  activeIndex.value = index
  const hash = `#${navigation[index].id}`
  if (route.hash !== hash) void router.replace({ path: '/', hash })
}

const goToSection = (id: string) => {
  const index = navigation.findIndex(item => item.id === id)
  if (index >= 0) setPage(index)
}

const handleWheel = (event: WheelEvent) => {
  if (Math.abs(event.deltaY) < 8) return
  event.preventDefault()
  if (wheelLocked) return

  const nextIndex = activeIndex.value + (event.deltaY > 0 ? 1 : -1)
  if (nextIndex < 0 || nextIndex >= navigation.length) return

  wheelLocked = true
  setPage(nextIndex)
  window.clearTimeout(wheelUnlockTimer)
  wheelUnlockTimer = window.setTimeout(() => { wheelLocked = false }, 980)
}

const handleKeydown = (event: KeyboardEvent) => {
  const direction = event.key === 'ArrowDown' || event.key === 'PageDown' ? 1 : event.key === 'ArrowUp' || event.key === 'PageUp' ? -1 : 0
  if (!direction) return
  event.preventDefault()
  setPage(activeIndex.value + direction)
}

onMounted(() => window.addEventListener('keydown', handleKeydown))

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
  window.clearTimeout(wheelUnlockTimer)
})

watch(() => route.hash, (hash) => {
  const nextIndex = sectionIndex(hash)
  if (nextIndex !== activeIndex.value) activeIndex.value = nextIndex
})

watch(() => route.query.auth, (value) => {
  authOpen.value = value === '1'
  if (authOpen.value && activeIndex.value !== 0) activeIndex.value = 0
})

const goHome = () => router.replace({ path: '/', hash: '' })
/**
 * 登录注册统一收敛到单一 /login 路由：已登录直接回工作台，未登录带上原目标。
 * 介绍页本身保持纯展示；/?auth=1 的嵌入式登录卡仍作为原设计的深链接保留。
 */
const openAuth = (redirect = DEFAULT_REDIRECT) => {
  if (isAuthenticated()) {
    void router.push(redirect)
    return
  }
  void router.push({ path: AUTH_ROUTE, query: { redirect } })
}
const closeAuth = () => {
  authOpen.value = false
  const { auth: _auth, redirect: _redirect, from: _from, ...query } = route.query
  void router.replace({ path: '/', query, hash: route.hash })
}
const goToLogin = () => openAuth()
</script>

<style scoped lang="scss">
.landing-view {
  --ink: #173963;
  --soft-ink: #55749e;
  --muted-ink: #6b85ad;
  --blue: #248ff0;
  --cyan: #38bdeb;
  --purple: #6655f4;
  position: relative;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
  color: var(--ink);
  background: #dcecff url('/bg.webp') center / cover no-repeat;
  isolation: isolate;
}

.landing-surface { position: absolute; inset: 0; width: 100%; height: 100%; overflow: hidden; }

.landing-view::before,
.landing-view::after,
.landing-atmosphere { content: ''; position: absolute; inset: 0; pointer-events: none; }
.landing-view::before { z-index: -2; background: linear-gradient(112deg, rgba(249, 253, 255, .9) 0%, rgba(243, 250, 255, .66) 38%, rgba(225, 240, 255, .25) 72%, rgba(216, 232, 255, .42) 100%); }
.landing-view::after { z-index: -1; background: radial-gradient(circle at 72% 30%, rgba(94, 206, 255, .2), transparent 28%), radial-gradient(circle at 78% 78%, rgba(119, 105, 244, .14), transparent 30%), radial-gradient(circle at 8% 86%, rgba(72, 168, 237, .13), transparent 30%), repeating-linear-gradient(90deg, transparent 0, transparent 119px, rgba(73, 139, 200, .035) 120px), repeating-linear-gradient(0deg, transparent 0, transparent 119px, rgba(73, 139, 200, .025) 120px); }
.landing-atmosphere { z-index: 4; opacity: .08; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 180 180' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.86' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.2'/%3E%3C/svg%3E"); mix-blend-mode: multiply; }

.landing-header { position: absolute; top: 0; right: 0; left: 0; z-index: 8; width: min(100% - 96px, 1920px); min-height: 88px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 28px; }
.landing-brand { display: inline-flex; align-items: center; gap: 12px; color: var(--ink); font-size: 21px; font-weight: 650; letter-spacing: -.02em; text-decoration: none; white-space: nowrap; }
.landing-brand strong { color: #6d86ac; font-weight: 500; }
.landing-brand__logo { width: 36px; height: 36px; display: block; filter: drop-shadow(0 0 12px rgba(64, 167, 235, .3)); }
.landing-brand__logo img { width: 100%; height: 100%; display: block; object-fit: contain; }
.landing-nav { display: flex; align-items: center; gap: clamp(24px, 3vw, 52px); }
.landing-nav a { position: relative; min-width: 58px; min-height: 58px; padding: 0 14px; box-sizing: border-box; display: inline-flex; align-items: center; justify-content: center; border: 1px solid transparent; color: var(--muted-ink); font-size: 14px; text-decoration: none; transition: color 220ms ease, border-color 220ms ease, background-color 220ms ease, box-shadow 220ms ease; }
.landing-nav a::after { content: ''; position: absolute; right: 10px; bottom: 7px; left: 10px; height: 2px; border-radius: 99px; background: linear-gradient(90deg, var(--cyan), var(--purple)); opacity: 0; transform: scaleX(.35); transition: opacity 220ms ease, transform 220ms ease; }
.landing-nav a:hover, .landing-nav a.is-active { color: var(--ink); }
.landing-nav a.is-active { border-color: transparent; background: transparent; box-shadow: none; }
.landing-nav a:hover::after, .landing-nav a.is-active::after { opacity: 1; transform: scaleX(1); }
.landing-header__actions { display: flex; align-items: center; gap: 20px; margin-left: auto; }
.landing-header__note { color: #7b96bd; font-size: 11px; letter-spacing: .11em; white-space: nowrap; }
.landing-header__note i { padding: 0 10px; font-style: normal; color: var(--blue); }
.landing-theme-toggle { min-height: 34px; padding: 0 12px; display: inline-flex; align-items: center; gap: 6px; border: 1px solid rgba(36, 143, 240, .2); border-radius: 999px; color: var(--muted-ink); background: rgba(255, 255, 255, .28); cursor: pointer; font: inherit; font-size: 12px; font-weight: 650; white-space: nowrap; transition: border-color 180ms ease, background-color 180ms ease, color 180ms ease, transform 180ms ease; }
.landing-theme-toggle:hover { border-color: rgba(36, 143, 240, .5); color: var(--ink); background: rgba(255, 255, 255, .62); transform: translateY(-1px); }
.landing-header__login { min-height: 34px; padding: 0 15px; border: 1px solid rgba(36, 143, 240, .26); border-radius: 999px; color: var(--ink); background: rgba(255, 255, 255, .42); cursor: pointer; font: inherit; font-size: 12px; font-weight: 650; transition: border-color 180ms ease, background-color 180ms ease, transform 180ms ease; }
.landing-header__login:hover { border-color: rgba(36, 143, 240, .52); background: rgba(255, 255, 255, .72); transform: translateY(-1px); }

.landing-track { position: absolute; inset: 0; z-index: 2; height: 400%; transition: transform 960ms cubic-bezier(.16, 1, .3, 1); will-change: transform; }
.landing-page { position: relative; width: 100%; height: 25%; min-height: 100vh; min-height: 100dvh; box-sizing: border-box; overflow: hidden; }
.landing-page__inner { width: min(1180px, calc(100% - 96px)); height: 100%; margin: 0 auto; display: flex; flex-direction: column; justify-content: center; box-sizing: border-box; }
.landing-page__inner--hero { flex-direction: row; align-items: center; justify-content: space-between; gap: 48px; padding-top: 50px; }
.landing-agent-slot { position: relative; width: min(46vw, 680px); height: min(50vw, 720px); min-width: 420px; min-height: 470px; margin-left: auto; transform: translateX(clamp(0px, 1.8vw, 28px)); display: grid; place-items: center; }
.landing-agent-slot :deep(.agent-constellation) { width: 100%; height: 100%; min-width: 0; min-height: 0; margin-left: 0; transform: none; }
.landing-page__content { animation: landing-content-in 900ms cubic-bezier(.2, .8, .2, 1) both; animation-play-state: paused; }
.landing-page.is-active .landing-page__content { animation-play-state: running; }
.landing-hero__copy { width: min(570px, 48vw); margin-top: -3vh; }
.landing-eyebrow { margin: 0 0 21px; color: #6e8fc0; font-size: 11px; font-weight: 750; letter-spacing: .25em; }
.landing-page--hero h1 { margin: 0; color: var(--ink); font-size: clamp(54px, 5vw, 86px); font-weight: 520; line-height: .98; letter-spacing: -.065em; text-shadow: 0 0 25px rgba(66, 166, 236, .12); }
.landing-page--hero h1 span { color: #6283ad; font-weight: 450; }
.landing-page--hero h2 { margin: 23px 0 0; color: #183665; font-size: clamp(26px, 2.2vw, 39px); font-weight: 520; letter-spacing: -.04em; }
.landing-lead { margin: 20px 0 0; color: #5e7da9; font-size: 16px; line-height: 1.7; }
.landing-cta { min-height: 52px; margin-top: 42px; padding: 0 28px; display: inline-flex; align-items: center; gap: 20px; border: 0; border-radius: 999px; color: white; background: linear-gradient(105deg, #28a9f3, #6352f5); box-shadow: 0 15px 28px rgba(70, 116, 239, .24), inset 0 1px 0 rgba(255, 255, 255, .65); font: inherit; font-size: 14px; font-weight: 700; cursor: pointer; transition: transform 220ms ease, box-shadow 220ms ease, filter 220ms ease; }
.landing-cta:hover { filter: brightness(1.06); transform: translateY(-3px); box-shadow: 0 20px 36px rgba(70, 116, 239, .32), inset 0 1px 0 rgba(255, 255, 255, .72); }
.landing-cta:active { transform: translateY(0); }
.landing-cta .el-icon { font-size: 18px; }

.landing-page--section { text-align: center; }
.landing-section__heading { width: 100%; }
.landing-section__heading .landing-eyebrow { margin-bottom: 16px; }
.landing-section__heading h2 { margin: 0; color: var(--ink); font-size: clamp(34px, 4vw, 58px); font-weight: 520; letter-spacing: -.055em; text-shadow: 0 0 25px rgba(66, 166, 236, .1); }
.landing-section__intro { margin: 16px auto 0; color: #6884ad; font-size: 15px; line-height: 1.7; }
.landing-page__inner--about { flex-direction: row; align-items: center; justify-content: space-between; gap: clamp(52px, 10vw, 170px); padding-top: 48px; text-align: left; }
.about-team__copy { flex: 1 1 auto; max-width: 650px; }
.about-team__copy .landing-eyebrow { margin-bottom: 23px; }
.about-team__copy h2 { margin: 0; color: #173963; font-size: clamp(58px, 7.2vw, 112px); font-weight: 520; line-height: .91; letter-spacing: -.08em; text-shadow: 0 0 30px rgba(72, 166, 236, .13); }
.about-team__copy h2 span { color: #6383ad; font-weight: 430; }
.about-team__lead { margin: 28px 0 0; color: #315b88; font-size: clamp(18px, 1.5vw, 24px); font-weight: 560; letter-spacing: -.03em; }
.about-team__note { max-width: 390px; margin: 14px 0 0; color: #6a87ad; font-size: 14px; line-height: 1.85; }
.about-contact-card { position: relative; width: min(500px, 100%); min-height: 360px; flex: 0 0 auto; overflow: hidden; isolation: isolate; padding: 35px 38px 33px; box-sizing: border-box; border: 1px solid rgba(255, 255, 255, .76); border-radius: 30px; background: radial-gradient(circle at 12% 0%, rgba(255, 255, 255, .72), transparent 32%), radial-gradient(circle at 93% 88%, rgba(151, 211, 255, .22), transparent 42%), linear-gradient(145deg, rgba(255, 255, 255, .66), rgba(225, 241, 255, .34)); box-shadow: 0 32px 70px rgba(69, 122, 193, .17), 0 10px 26px rgba(122, 176, 225, .11), inset 0 1px 0 rgba(255, 255, 255, .96), inset 0 -1px 0 rgba(255, 255, 255, .28); backdrop-filter: blur(26px) saturate(142%); transition: transform 280ms cubic-bezier(.22, .78, .24, 1), box-shadow 280ms ease, border-color 280ms ease; }
.about-contact-card::before { content: ''; position: absolute; z-index: -1; top: -34%; left: -18%; width: 76%; height: 58%; border-radius: 50%; background: rgba(255, 255, 255, .42); filter: blur(24px); transform: rotate(-13deg); pointer-events: none; }
.about-contact-card::after { content: ''; position: absolute; z-index: -1; top: 0; right: 11%; left: 11%; height: 1px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .98), transparent); pointer-events: none; }
.about-contact-card:hover { border-color: rgba(255, 255, 255, .94); box-shadow: 0 38px 82px rgba(69, 122, 193, .21), 0 14px 30px rgba(122, 176, 225, .14), inset 0 1px 0 rgba(255, 255, 255, .98), inset 0 -1px 0 rgba(255, 255, 255, .3); transform: translateY(-5px); }
.about-contact-card__top { display: flex; align-items: center; justify-content: space-between; color: #6386b3; font-size: 11px; font-weight: 760; letter-spacing: .2em; }
.about-contact-card__top span:last-child { color: #91abc8; font-size: 10px; letter-spacing: .13em; }
.about-contact-card__item { display: flex; align-items: center; justify-content: space-between; gap: 24px; min-height: 82px; border-bottom: 1px solid rgba(107, 148, 194, .2); }
.about-contact-card__item:first-of-type { margin-top: 17px; border-top: 1px solid rgba(107, 148, 194, .2); }
.about-contact-card__label { color: #718eaf; font-size: 11px; font-weight: 720; letter-spacing: .1em; }
.about-contact-card__value { color: #1d4875; font-size: 18px; font-weight: 640; letter-spacing: -.02em; }
.about-contact-card__hint { margin: 21px 0 0; color: #718caf; font-size: 13px; line-height: 1.75; }
.about-team__cta { width: 100%; min-height: 50px; margin-top: 23px; padding: 0 24px; justify-content: center; gap: 13px; font-size: 13px; box-shadow: 0 13px 25px rgba(70, 116, 239, .2), inset 0 1px 0 rgba(255, 255, 255, .7); }
.about-team__cta:hover { box-shadow: 0 17px 32px rgba(70, 116, 239, .29), inset 0 1px 0 rgba(255, 255, 255, .78); }
.landing-info-grid { display: grid; width: 100%; gap: 14px; margin-top: 42px; text-align: left; animation: landing-grid-in 1000ms cubic-bezier(.2, .8, .2, 1) both; animation-play-state: paused; }
.landing-page.is-active .landing-info-grid { animation-play-state: running; }
.landing-info-grid--three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.landing-info-grid--two { grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 820px; margin-right: auto; margin-left: auto; }
.landing-info-card { position: relative; min-height: 190px; padding: 24px; box-sizing: border-box; border: 1px solid rgba(255, 255, 255, .78); border-radius: 18px; background: linear-gradient(140deg, rgba(255, 255, 255, .46), rgba(224, 241, 255, .26)); box-shadow: 0 18px 38px rgba(73, 125, 207, .1), inset 0 1px 0 rgba(255, 255, 255, .86); backdrop-filter: blur(16px) saturate(125%); transition: transform 220ms ease, border-color 220ms ease, background-color 220ms ease, box-shadow 220ms ease; animation: landing-card-in 850ms cubic-bezier(.2, .8, .2, 1) both; animation-play-state: paused; }
.landing-page.is-active .landing-info-card { animation-play-state: running; }
.landing-page.is-active .landing-info-card:nth-child(2) { animation-delay: 80ms; }
.landing-page.is-active .landing-info-card:nth-child(3) { animation-delay: 150ms; }
.landing-info-card::after { content: ''; position: absolute; top: 0; right: 16px; left: 16px; height: 1px; background: linear-gradient(90deg, transparent, rgba(255, 255, 255, .92), transparent); }
.landing-info-card:hover { border-color: rgba(84, 178, 239, .5); background: linear-gradient(140deg, rgba(255, 255, 255, .62), rgba(219, 238, 255, .38)); box-shadow: 0 22px 44px rgba(73, 125, 207, .15), inset 0 1px 0 rgba(255, 255, 255, .92); transform: translateY(-5px); }
.landing-info-card__index, .landing-info-card__meta { display: block; color: #6e91c0; font-size: 10px; font-weight: 750; letter-spacing: .14em; }
.landing-info-card h3 { margin: 28px 0 0; color: #173963; font-size: 21px; font-weight: 650; letter-spacing: -.03em; }
.landing-info-card p { max-width: 300px; margin: 12px 0 0; color: #6884ad; font-size: 13px; line-height: 1.75; }
.landing-info-card__meta { position: absolute; right: 24px; bottom: 21px; color: #8aa5c8; font-size: 9px; font-weight: 600; letter-spacing: .06em; }
.about-ribbon { max-width: 720px; margin: 42px auto 0; padding: 20px 24px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; border: 1px solid rgba(255, 255, 255, .76); border-radius: 18px; background: rgba(255, 255, 255, .4); box-shadow: 0 18px 38px rgba(73, 125, 207, .09), inset 0 1px 0 rgba(255, 255, 255, .86); backdrop-filter: blur(16px); }
.about-ribbon span { position: relative; }
.about-ribbon span + span::before { content: ''; position: absolute; top: 3px; bottom: 3px; left: -8px; width: 1px; background: rgba(115, 155, 204, .24); }
.about-ribbon b, .about-ribbon small { display: block; }
.about-ribbon b { color: #214572; font-size: 14px; }
.about-ribbon small { margin-top: 6px; color: #7792b8; font-size: 10px; }
.landing-cta--small { margin-top: 36px; }

.landing-footer { position: absolute; right: min(48px, 5vw); bottom: 31px; left: min(48px, 5vw); z-index: 8; display: flex; align-items: center; gap: 18px; color: #7893b7; font-size: 9px; font-weight: 750; letter-spacing: .18em; }
.landing-footer__status { color: #6c8fbd; }
.landing-footer__dots { display: flex; align-items: center; gap: 7px; }
.landing-footer__dots button { width: 20px; height: 3px; padding: 0; border: 0; border-radius: 99px; background: rgba(93, 139, 190, .28); cursor: pointer; transition: width 240ms ease, background-color 240ms ease, box-shadow 240ms ease; }
.landing-footer__dots button.is-active { width: 38px; background: linear-gradient(90deg, var(--cyan), var(--purple)); box-shadow: 0 0 12px rgba(54, 185, 239, .42); }
.landing-footer__caption { margin-left: auto; }

/* The public surface follows the same saved scheme as the workbench. The
   light scene remains the default presentation for non-dark schemes, while
   the dark scheme uses the matching space scene asset and contrast tokens. */
.landing-view.is-theme-dark {
  --ink: #f1f6ff;
  --soft-ink: #b2c5df;
  --muted-ink: #9aafd0;
  --blue: #52b8ff;
  --cyan: #39c4f1;
  --purple: #9b78ff;
  color-scheme: dark;
  background: #050914 url('/darkbg.webp') center / cover no-repeat;

  &::before {
    background: linear-gradient(112deg, rgba(3, 7, 15, .94) 0%, rgba(3, 10, 22, .78) 40%, rgba(3, 7, 15, .42) 100%);
  }
  &::after {
    background: radial-gradient(circle at 72% 30%, rgba(79, 183, 255, .17), transparent 30%), radial-gradient(circle at 78% 78%, rgba(141, 112, 255, .18), transparent 32%), repeating-linear-gradient(90deg, transparent 0, transparent 119px, rgba(113, 166, 237, .05) 120px), repeating-linear-gradient(0deg, transparent 0, transparent 119px, rgba(113, 166, 237, .035) 120px);
  }
  .landing-atmosphere { opacity: .11; mix-blend-mode: screen; }
  .landing-brand strong { color: #b9a3ff; }
  .landing-header__note { color: #9aacc7; }
  .landing-theme-toggle { border-color: rgba(109, 189, 255, .3); color: #b7cbe4; background: rgba(9, 24, 46, .48); }
  .landing-theme-toggle:hover { border-color: rgba(109, 189, 255, .68); color: #f1f6ff; background: rgba(18, 44, 77, .76); }
  .landing-header__login { border-color: rgba(109, 189, 255, .34); color: #eef5ff; background: rgba(9, 24, 46, .54); }
  .landing-header__login:hover { border-color: rgba(109, 189, 255, .72); background: rgba(18, 44, 77, .78); }
  .landing-eyebrow { color: #9f7dff; }
  .landing-page--hero h1 span { color: #b6a1ff; }
  .landing-page--hero h2 { color: #f1f6ff; }
  .landing-lead { color: #abc0dd; }
  .landing-section__heading h2 { color: #f1f6ff; }
  .landing-section__intro { color: #9fb4d1; }
  .landing-info-card {
    border-color: rgba(130, 184, 237, .26);
    background: linear-gradient(140deg, rgba(17, 38, 70, .68), rgba(5, 15, 30, .58));
    box-shadow: 0 18px 38px rgba(0, 0, 0, .22), inset 0 1px 0 rgba(220, 239, 255, .14);
  }
  .landing-info-card::after { background: linear-gradient(90deg, transparent, rgba(132, 197, 255, .42), transparent); }
  .landing-info-card:hover { border-color: rgba(100, 192, 255, .66); background: linear-gradient(140deg, rgba(22, 52, 91, .8), rgba(7, 20, 40, .7)); box-shadow: 0 22px 44px rgba(0, 0, 0, .3), inset 0 1px 0 rgba(220, 239, 255, .18); }
  .landing-info-card__index, .landing-info-card__meta { color: #8fc8ff; }
  .landing-info-card h3 { color: #edf5ff; }
  .landing-info-card p { color: #a8bdd8; }
  .landing-info-card__meta { color: #8ea9c8; }
  .about-team__copy h2 { color: #f1f6ff; }
  .about-team__copy h2 span { color: #b7a1ff; }
  .about-team__lead { color: #b8d0ed; }
  .about-team__note { color: #9db5d4; }
  .about-contact-card {
    border-color: rgba(130, 184, 237, .3);
    background: radial-gradient(circle at 12% 0%, rgba(71, 164, 235, .22), transparent 32%), radial-gradient(circle at 93% 88%, rgba(139, 108, 255, .2), transparent 42%), linear-gradient(145deg, rgba(18, 42, 76, .78), rgba(5, 15, 30, .66));
    box-shadow: 0 32px 70px rgba(0, 0, 0, .3), inset 0 1px 0 rgba(220, 239, 255, .16);
  }
  .about-contact-card::before { background: rgba(102, 190, 255, .14); }
  .about-contact-card::after { background: linear-gradient(90deg, transparent, rgba(164, 211, 255, .54), transparent); }
  .about-contact-card:hover { border-color: rgba(130, 201, 255, .68); box-shadow: 0 38px 82px rgba(0, 0, 0, .38), inset 0 1px 0 rgba(220, 239, 255, .2); }
  .about-contact-card__top { color: #9bc7ef; }
  .about-contact-card__top span:last-child { color: #789bc3; }
  .about-contact-card__item { border-color: rgba(107, 171, 230, .22); }
  .about-contact-card__label { color: #8faed0; }
  .about-contact-card__value { color: #e8f3ff; }
  .about-contact-card__hint { color: #9db8d7; }
  .landing-footer { color: #91a9c9; }
  .landing-footer__status { color: #9cc9f2; }
  .landing-footer__dots button { background: rgba(125, 177, 232, .3); }
  & :deep(.agent-stage__status) { border-color: rgba(133, 193, 244, .36); color: #b3c8e3; background: rgba(7, 20, 39, .6); box-shadow: 0 8px 20px rgba(0, 0, 0, .2), inset 0 1px 0 rgba(220, 239, 255, .12); }
  & :deep(.agent-stage__prompt) { border-color: rgba(133, 193, 244, .34); color: #b7cbe4; background: rgba(7, 20, 39, .56); }
  & :deep(.agent-controls) { border-color: rgba(133, 193, 244, .3); background: linear-gradient(145deg, rgba(16, 39, 72, .78), rgba(5, 15, 30, .68)); box-shadow: 0 24px 48px rgba(0, 0, 0, .28), inset 0 1px 0 rgba(220, 239, 255, .14); }
  & :deep(.agent-controls::before) { border-color: rgba(133, 193, 244, .3); background: rgba(14, 34, 62, .8); }
  & :deep(.agent-control) { border-color: rgba(133, 193, 244, .22); color: #a6bfdd; background: rgba(13, 32, 58, .62); }
  & :deep(.agent-control:hover), & :deep(.agent-control[aria-pressed='true']) { color: #eef6ff; background: rgba(34, 76, 121, .76); }
  & :deep(.agent-controls__label), & :deep(.agent-controls__hint) { color: #8eacce; }
  & :deep(.agent-conversation) { border-color: rgba(133, 193, 244, .34); color: #c5d9ef; background: linear-gradient(145deg, rgba(17, 43, 78, .82), rgba(5, 15, 30, .7)); box-shadow: 0 18px 34px rgba(0, 0, 0, .28), inset 0 1px 0 rgba(220, 239, 255, .14); }
  & :deep(.agent-conversation::before) { background: rgba(14, 34, 62, .82); }
  & :deep(.agent-conversation p) { color: #a9c0dc; }
}

.landing-view.is-desktop-shell { --app-topbar-muted: var(--muted-ink); --app-topbar-hover: rgba(36, 143, 240, .08); --app-topbar-active: rgba(36, 143, 240, .13); --app-topbar-focus-ring: rgba(36, 143, 240, .45); }
.landing-view.is-desktop-shell .landing-header { padding-right: 24px; padding-left: 24px; background: linear-gradient(180deg, rgba(246, 251, 255, .72), rgba(246, 251, 255, .34)); backdrop-filter: blur(14px); }
.landing-view.is-desktop-shell .landing-header :deep(.desktop-window-controls) { height: 52px; align-self: center; }
.landing-brand:focus-visible, .landing-nav a:focus-visible, .landing-theme-toggle:focus-visible, .landing-header__login:focus-visible, .landing-cta:focus-visible, .landing-footer button:focus-visible { outline: 2px solid rgba(36, 143, 240, .56); outline-offset: 5px; }

@media (max-width: 860px) {
  .landing-header { width: calc(100% - 32px); gap: 12px; }
  .landing-header__actions { gap: 8px; }
  .landing-theme-toggle span { display: none; }
  .landing-header__note { display: none; }
  .landing-nav { gap: 4px; }
  .landing-nav a { min-width: 46px; padding: 0 8px; }
  .landing-page__inner { width: calc(100% - 40px); }
  .landing-page__inner--hero { flex-direction: column; justify-content: center; gap: 8px; padding-top: 78px; }
  .landing-hero__copy { width: 100%; margin-top: 0; }
  .landing-agent-slot { width: min(78vw, 500px); height: min(47vh, 430px); min-width: 0; min-height: 0; margin: 0 auto; transform: none; }
  .landing-page__inner--about { flex-direction: column; align-items: flex-start; justify-content: center; gap: 32px; padding-top: 86px; }
  .about-team__copy { max-width: 100%; }
  .about-team__copy h2 { font-size: clamp(54px, 14vw, 88px); }
  .about-contact-card { width: min(100%, 500px); min-height: 0; align-self: center; }
}

@media (max-width: 520px) {
  .about-contact-card { padding: 29px 25px 27px; border-radius: 25px; }
  .about-contact-card__item { min-height: 72px; gap: 16px; }
  .about-contact-card__value { font-size: 16px; }
}

@keyframes landing-content-in { from { opacity: 0; transform: translate3d(0, 26px, 0) scale(.985); } to { opacity: 1; transform: translate3d(0, 0, 0) scale(1); } }
@keyframes landing-grid-in { from { opacity: 0; transform: translate3d(0, 20px, 0); } to { opacity: 1; transform: translate3d(0, 0, 0); } }
@keyframes landing-card-in { from { opacity: 0; transform: translate3d(0, 18px, 0) scale(.98); } to { opacity: 1; transform: translate3d(0, 0, 0) scale(1); } }

@media (prefers-reduced-motion: reduce) {
  .landing-track { transition: none; }
  .landing-page__content, .landing-info-grid, .landing-info-card, .landing-nav a, .landing-nav a::after, .landing-cta, .landing-footer__dots button { animation: none; transition: none; }
}
</style>
