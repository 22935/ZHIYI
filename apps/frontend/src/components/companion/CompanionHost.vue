<template>
  <Teleport to="body">
    <div
      class="companion-root"
      :class="{ 'is-expanded': expanded, 'is-dragging': dragging }"
      :style="rootStyle"
      :data-state="state"
      :data-speaking="speaking ? '1' : '0'"
      :data-listening="listening ? '1' : '0'"
      data-testid="companion-root"
    >
      <section v-if="expanded" class="companion-panel" aria-label="虚拟伙伴面板">
        <header class="companion-header">
          <div>
            <span class="companion-name" data-testid="companion-name">{{ personaName }}</span>
            <span class="companion-state" data-testid="companion-state">{{ stateLabel }}</span>
          </div>
          <button type="button" data-testid="companion-collapse" @click="toggleExpanded">收起</button>
        </header>

        <!-- 工坊是编辑模式：与养成区互斥，避免两层滚动把「保存形象」藏起来。
             关闭后互动状态、消息与养成数值都原样保留。 -->
        <template v-if="!customizerOpen">
          <CompanionPetBar
            :level="level"
            :title="title"
            :affinity-percent="affinityPercent"
            :energy="pet.energy"
            :mood-label="moodLabel"
            :streak-days="pet.streakDays"
            :achievement-labels="achievementLabels"
            :achievement-count="pet.achievements.length"
            @interact="interact"
          />

          <CompanionDialogue
            :messages="messages"
            :pending="pending"
            :card="card"
            :phase="voicePhase"
            :interim="interim"
            :hint="hint"
            :muted="muted"
            :level="voiceLevel"
            @send="onQuickSend"
            @dismiss-card="card = null"
            @toggle-voice="toggleVoice"
            @toggle-mute="toggleMute"
          />
        </template>
        <CompanionCustomizer
          v-else
          :value="customization"
          :voices="voiceOptions"
          @preview="onCustomizationPreview"
          @apply="onCustomizationApply"
          @audition="onAudition"
          @close="closeCustomizer"
        />

        <footer class="companion-footer">
          <label class="companion-toggle" title="切换后复用既有对话流，默认关闭">
            <input v-model="streamEnabled" type="checkbox" data-testid="companion-model-toggle" @change="onModelToggle" />
            模型回复
          </label>
          <label class="companion-toggle" title="免打扰时停止闲时搭话、朗读与桌面通知">
            <input v-model="quiet" type="checkbox" data-testid="companion-quiet" @change="onQuietChange" />
            免打扰
          </label>
          <select v-model="skinId" data-testid="companion-skin" aria-label="切换形象" @change="onSkinChange">
            <option v-for="skin in skins" :key="skin.id" :value="skin.id">{{ skin.label }}</option>
          </select>
          <button
            type="button"
            class="companion-diy-btn"
            data-testid="companion-diy-open"
            @click="customizerOpen ? closeCustomizer() : openCustomizer()"
          >{{ customizerOpen ? '完成' : 'DIY' }}</button>
        </footer>
        <button
          v-if="position"
          type="button"
          class="companion-reset"
          data-testid="companion-reset-position"
          @click="resetPosition"
        >回到右下角</button>
      </section>

      <CompanionBubble :text="bubble?.text ?? ''" :tone="bubble?.tone ?? 'chat'" />

      <div
        ref="stageRef"
        class="companion-avatar"
        data-testid="companion-avatar"
        role="button"
        tabindex="0"
        :aria-label="expanded ? `收起${personaName}` : `展开${personaName}`"
        :aria-expanded="expanded"
        title="点一下叫我，拖动可以挪位置"
        @click="onAvatarClick"
        @keydown.enter="onAvatarClick"
        @keydown.space.prevent="onAvatarClick"
        @pointerdown="onPointerDown"
      >
        <span v-if="state === 'sleeping'" class="companion-zzz" aria-hidden="true">z z Z</span>
        <span
          v-for="fx in effects"
          :key="fx.id"
          class="companion-fx"
          :style="{ left: `${fx.left}%`, animationDelay: `${fx.delay}ms` }"
          aria-hidden="true"
        >{{ fx.glyph }}</span>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import CompanionBubble from './CompanionBubble.vue'
import CompanionCustomizer from './CompanionCustomizer.vue'
import CompanionDialogue from './CompanionDialogue.vue'
import CompanionPetBar from './CompanionPetBar.vue'
import { createDesktopPort, type TrayAction } from '@/features/companion/adapters/desktop'
import {
  buildDiySkin, DIY_SKIN_ID, loadCustomization, saveCustomization
} from '@/features/companion/customization'
import { IdleChoreographer } from '@/features/companion/idleBehavior'
import {
  IdleFallback, ProactivityQueue, STATE_LABEL, resolveState, stateFromRuntimeEvent
} from '@/features/companion/companionState'
import { CompanionService, createDefaultPorts } from '@/features/companion/companionService'
import {
  ACHIEVEMENTS, MOOD_LABEL, levelOf, levelProgress, loadPetProfile, moodOf,
  savePetProfile, titleOf, applyPetAction, type PetAction, type PetProfile, type PetStorage
} from '@/features/companion/pet'
import {
  COMPANION_POSITION_KEY, clampCompanionPosition, clampExpandedPosition,
  companionPositionFromDrag, loadCompanionPosition, type CompanionPosition
} from '@/features/companion/position'
import { createRenderer } from '@/features/companion/renderers'
import { COMPANION_SKIN_STORAGE_KEY, defaultSkinRegistry } from '@/features/companion/skins'
import { createSwitchGuard } from '@/features/companion/switchGuard'
import { matchCompanionCommand, type CommandMatch } from '@/features/companion/speechCommands'
import { VoiceEngine, voiceHint, type VoiceOption, type VoicePhase } from '@/features/companion/voice'
import type {
  AvatarRenderer, CompanionCustomization, CompanionMessage, CompanionState, SkinManifest,
  TaskIntentCard
} from '@/features/companion/types'

const EXPANDED_KEY = 'companion.expanded.v1'
const QUIET_KEY = 'companion.quiet.v1'
const IDLE_TICK_MS = 15_000
const BUBBLE_TTL_MS = 3600
const PREVIEW_DEBOUNCE_MS = 180

const storage = ((): PetStorage | null => {
  try { return typeof localStorage === 'undefined' ? null : localStorage } catch { return null }
})()
const readFlag = (key: string): boolean => {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}
const writeFlag = (key: string, value: boolean): void => {
  try { localStorage.setItem(key, value ? '1' : '0') } catch { /* storage is optional */ }
}
const readSkinId = (): string => {
  try { return localStorage.getItem(COMPANION_SKIN_STORAGE_KEY) || 'companion-static' } catch { return 'companion-static' }
}
const viewport = (): { width: number; height: number } => ({
  width: typeof window === 'undefined' ? 1280 : window.innerWidth,
  height: typeof window === 'undefined' ? 800 : window.innerHeight
})
const reduceMotion = (): boolean => {
  try {
    return typeof window.matchMedia === 'function'
      && window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch { return false }
}

const stageRef = ref<HTMLElement | null>(null)
const expanded = ref(readFlag(EXPANDED_KEY))
const quiet = ref(readFlag(QUIET_KEY))
const skinId = ref(readSkinId())
const streamEnabled = ref(false)
const state = ref<CompanionState>('idle')
const messages = ref<CompanionMessage[]>([])
const pending = ref(false)
const card = ref<TaskIntentCard | null>(null)
const pet = ref<PetProfile>(loadPetProfile(storage, Date.now()))
const position = ref<CompanionPosition | null>(null)
const dragging = ref(false)
const restingBecauseIdle = ref(false)
const bubble = ref<{ text: string; tone: 'chat' | 'effect' | 'achievement' } | null>(null)

const customization = ref<CompanionCustomization>(loadCustomization(storage))
const customizerOpen = ref(false)
const skins = ref(defaultSkinRegistry.list())
const muted = ref(customization.value.voice.muted)
const voicePhase = ref<VoicePhase>('idle')
const interim = ref('')
const voiceError = ref('')
const speaking = ref(false)
const listening = ref(false)
const effects = ref<{ id: number; glyph: string; left: number; delay: number }[]>([])

const savedPosition = loadCompanionPosition(storage)
if (savedPosition) position.value = clampCompanionPosition(savedPosition, viewport())

defaultSkinRegistry.upsert(buildDiySkin(customization.value))
skins.value = defaultSkinRegistry.list()

const voice = new VoiceEngine()
const voiceCaps = ref(voice.capabilities)
/** 系统声线列表：首次往往是空的，等 voiceschanged 再填。 */
const voiceOptions = ref<VoiceOption[]>(voice.listVoices())
const personaName = computed(() => customization.value.name)
const stateLabel = computed(() => STATE_LABEL[state.value])
const level = computed(() => levelOf(pet.value.affinity))
const title = computed(() => titleOf(level.value))
const affinityPercent = computed(() => levelProgress(pet.value.affinity))
const moodLabel = computed(() => MOOD_LABEL[moodOf(pet.value, Date.now(), state.value)])
const achievementLabels = computed(() =>
  pet.value.achievements
    .map(id => ACHIEVEMENTS.find(item => item.id === id)?.label)
    .filter((label): label is string => Boolean(label))
    .slice(-3)
)
const hint = computed(() => voiceHint(voiceCaps.value, voicePhase.value, voiceError.value))
const voiceLevel = computed(() => 0.36 + Math.min(0.5, interim.value.length / 48))

// 面板在角色上方：按 right/bottom 锚定，展开时向上生长。
// 同时把 bottom 传给 CSS，让面板的最大高度按「角色离屏幕底部的距离」收缩，
// 否则窗口变矮或角色被拖到上方时，展开的面板会从视口顶部溢出。
const rootStyle = computed<Record<string, string>>(() => position.value
  ? {
      right: `${position.value.right}px`,
      bottom: `${position.value.bottom}px`,
      left: 'auto',
      top: 'auto',
      '--companion-bottom': `${position.value.bottom}px`
    }
  : {})

const idleFallback = new IdleFallback(5000)
const queue = new ProactivityQueue(4000)
const choreographer = new IdleChoreographer()
const desktop = createDesktopPort()

let renderer: AvatarRenderer | null = null
let service = new CompanionService(createDefaultPorts(customization.value.lines))
let abort: AbortController | null = null
let disposed = false
let messageSeq = 0
let fxSeq = 0
let bubbleTimer: ReturnType<typeof setTimeout> | null = null
let clickSuppressTimer: ReturnType<typeof setTimeout> | null = null
let idleTimer: ReturnType<typeof setInterval> | null = null
let previewTimer: ReturnType<typeof setTimeout> | null = null
let hiddenAt = 0
let unsubscribeTray: (() => void) | null = null
let unsubscribeVoices: (() => void) | null = null
let skinBeforeDiy: string | null = null
let diyCommitted = false
const effectTimers = new Set<ReturnType<typeof setTimeout>>()

const drag = {
  active: false, moved: false, startX: 0, startY: 0,
  offsetX: 0, offsetY: 0, avatarWidth: 0, avatarHeight: 0
}
let suppressClick = false

const pushMessage = (role: CompanionMessage['role'], content: string): void => {
  messages.value = [...messages.value, {
    id: `companion-${++messageSeq}`,
    role,
    content,
    createdAt: Date.now()
  }]
}

const showBubble = (text: string, tone: 'chat' | 'effect' | 'achievement' = 'chat'): void => {
  bubble.value = { text, tone }
  if (bubbleTimer !== null) clearTimeout(bubbleTimer)
  bubbleTimer = setTimeout(() => { bubble.value = null }, BUBBLE_TTL_MS)
}

const spawnEffects = (glyph: string, count = 3): void => {
  if (!customization.value.motion || reduceMotion()) return
  for (let i = 0; i < count; i += 1) {
    const id = ++fxSeq
    effects.value = [...effects.value, {
      id, glyph, left: 14 + Math.random() * 54, delay: i * 90
    }]
    const timer = setTimeout(() => {
      effects.value = effects.value.filter(item => item.id !== id)
      effectTimers.delete(timer)
    }, 1700)
    effectTimers.add(timer)
  }
}

const setSpeaking = (on: boolean): void => {
  speaking.value = on
  renderer?.setSpeaking?.(on)
}
const setListening = (on: boolean): void => {
  listening.value = on
  renderer?.setListening?.(on)
}

/**
 * 打断朗读是切换声线、静音、免打扰共用的收尾动作：
 * 取消合成之外还要复位口型与语音相位，否则脸会停在「正在说」。
 */
const stopSpeaking = (): void => {
  voice.cancelSpeak()
  setSpeaking(false)
  if (voicePhase.value === 'speaking') voicePhase.value = 'idle'
}

/** 朗读只发生在用户主动互动后；闲时搭话与免打扰状态一律不出声。 */
const speakText = (text: string, settings: CompanionCustomization['voice']): boolean => {
  if (quiet.value || muted.value || !voiceCaps.value.synthesis) return false
  return voice.speak(text, { ...settings, muted: false }, () => {
    voicePhase.value = 'speaking'
    setSpeaking(true)
  }, () => {
    setSpeaking(false)
    if (voicePhase.value === 'speaking') voicePhase.value = 'idle'
  })
}

const speakReply = (text: string): void => {
  speakText(text, customization.value.voice)
}

/** 试听用工坊里的草稿声线说话，不写入配置；保存后才成为默认声音。 */
const onAudition = (settings: CompanionCustomization['voice']): void => {
  stopSpeaking()
  if (!speakText(`你好，我是${personaName.value}，这是我现在的声音。`, settings)) {
    showBubble('这个环境暂时不能试听声音。')
  }
}

const trayVoicePhase = (): 'idle' | 'listening' | 'speaking' =>
  voicePhase.value === 'listening' || voicePhase.value === 'recognizing' ? 'listening'
    : voicePhase.value === 'speaking' ? 'speaking' : 'idle'

const publishDesktopState = (): void => {
  desktop.publishState({
    state: state.value,
    label: STATE_LABEL[state.value],
    level: level.value,
    affinity: pet.value.affinity,
    quiet: quiet.value,
    name: personaName.value,
    voice: trayVoicePhase()
  })
}

// 托盘 tooltip 要跟着朗读/聆听和 DIY 改名走，但不新建任何 IPC 通道。
watch(voicePhase, () => publishDesktopState())
watch(personaName, () => publishDesktopState())

const scheduleFallback = (): void => {
  idleFallback.schedule(() => {
    if (disposed) return
    state.value = restingBecauseIdle.value ? 'sleeping' : 'idle'
    renderer?.setState(state.value)
  })
}

/**
 * 主干把 happy 提权为完成态（run.completed 需要压过 thinking/working）。
 * 但本地点头像/摸头等互动也借用 happy 做表情，若不显式接管，用户新一轮的
 * 「聆听 / 思考中」会被上一次互动的开心表情挡住。运行时事件仍走优先级仲裁。
 */
const applyState = (next: CompanionState, overrideInteractiveHappy = false): void => {
  state.value = overrideInteractiveHappy && state.value === 'happy'
    ? next
    : resolveState(state.value, next)
  renderer?.setState(state.value)
  scheduleFallback()
  publishDesktopState()
}

/** 互动的开心表情不覆盖告警/思考/跟进中：宠物再活泼也不打断正事。 */
const NO_INTERRUPT: CompanionState[] = ['error', 'alert', 'working', 'thinking']
const flashPetState = (next: CompanionState): void => {
  if (NO_INTERRUPT.includes(state.value)) return
  state.value = next
  renderer?.setState(next)
  scheduleFallback()
  publishDesktopState()
}

const recordAchievements = (names: string): void => {
  if (!names) return
  showBubble(`解锁成就：${names}`, 'achievement')
  spawnEffects('★', 5)
  if (!quiet.value) desktop.notifyIfBackground(`${personaName.value} · 解锁成就`, names)
}

/** speak=false 用于页面加载 / 长时间离开后的自动问候：没有用户手势时不自动出声。 */
const interact = (action: PetAction, speak = true): void => {
  const result = applyPetAction(pet.value, action, Date.now())
  pet.value = result.profile
  savePetProfile(storage, pet.value)
  restingBecauseIdle.value = false
  const names = result.unlocked.map(item => item.label).join('、')
  if (names) recordAchievements(names)
  else {
    showBubble(result.message, result.tone === 'cooldown' ? 'chat' : 'effect')
    if (result.tone !== 'cooldown') spawnEffects('✦')
  }
  if (result.state) flashPetState(result.state)
  if (speak) speakReply(result.message)
  publishDesktopState()
}

/** 对话带来的成长只记数、不弹气泡，避免盖掉真正的回复。 */
const trackAction = (action: PetAction): void => {
  const result = applyPetAction(pet.value, action, Date.now())
  pet.value = result.profile
  savePetProfile(storage, pet.value)
  restingBecauseIdle.value = false
  recordAchievements(result.unlocked.map(item => item.label).join('、'))
  publishDesktopState()
}

/** 只消费上游已订阅的运行时事件，不新建长连接；无 webhook 也不新建推送协议。 */
const handleRuntimeEvent = (event: Event): void => {
  const detail = (event as CustomEvent<{ eventType?: string; runId?: string }>).detail || {}
  const mapped = stateFromRuntimeEvent(detail.eventType || '')
  if (!mapped) return
  applyState(mapped)
  if (mapped !== 'error' && mapped !== 'alert') return
  const notice = queue.enqueue({
    id: `${detail.eventType || 'event'}:${detail.runId || ''}`,
    priority: mapped === 'error' ? 5 : 4,
    text: mapped === 'error'
      ? '有个运行出问题了，去工作台看看 Trace 吧。'
      : '有个运行等待人工复核，抽空看一眼？',
    state: mapped,
    at: Date.now()
  })
  if (!notice) return
  pushMessage('companion', notice.text)
  if (!quiet.value) desktop.notifyIfBackground(`${personaName.value} · ${STATE_LABEL[mapped]}`, notice.text)
}

/**
 * 切换形象是一次事务，而不是两步赋值。
 *
 * 1. 先挂载新渲染器，成功之后才销毁旧的：grok 皮肤要等动态 import，
 *    期间旧形象仍在屏幕上，不会闪白，也不会出现 renderer 为 null 的空窗。
 * 2. 用 SwitchGuard 丢弃过期结果：连续切换（下拉连点、语音命令、工坊预览）
 *    时只认最后一次，避免慢的旧挂载覆盖快的新挂载。
 * 3. 新渲染器就位后重放当前 8 态与口型/收音状态，说话中换皮不会「僵脸」。
 * 4. 失败走同一套流程降级到 companion-static，并把降级结果写回持久化，
 *    否则刷新后会再次尝试那个注定失败的形象。
 */
const skinSwitch = createSwitchGuard()

const applySkin = async (id: string): Promise<void> => {
  const stage = stageRef.value
  if (!stage || disposed) return
  const isLatest = skinSwitch.begin()

  const commit = (candidate: AvatarRenderer, manifest: SkinManifest): void => {
    const previous = renderer
    renderer = candidate
    renderer.setState(state.value)
    renderer.setSpeaking?.(speaking.value)
    renderer.setListening?.(listening.value)
    previous?.destroy()
    if (manifest.id !== skinId.value) skinId.value = manifest.id
    try { localStorage.setItem(COMPANION_SKIN_STORAGE_KEY, manifest.id) } catch { /* optional */ }
  }

  const skin = defaultSkinRegistry.resolve(id)
  const next = createRenderer(skin)
  try {
    await next.mount(stage, skin)
    if (disposed || !isLatest()) { next.destroy(); return }
    commit(next, skin)
  } catch {
    next.destroy()
    if (disposed || !isLatest()) return
    const fallback = defaultSkinRegistry.resolve(null)
    const plain = createRenderer(fallback)
    try {
      await plain.mount(stage, fallback)
      if (disposed || !isLatest()) { plain.destroy(); return }
      commit(plain, fallback)
    } catch {
      plain.destroy()
    }
  }
}

const writePosition = (): void => {
  if (!position.value) return
  try { localStorage.setItem(COMPANION_POSITION_KEY, JSON.stringify(position.value)) } catch { /* optional */ }
}

/**
 * 面板在角色上方、向左生长，展开后根节点比角色宽得多。
 * 若角色被拖到屏幕左侧，展开前把它平移回仍有完整面板空间的位置；
 * 收起态不做限制，拖拽依旧自由。
 */
const ensurePanelVisible = (): boolean => {
  if (!position.value) return false
  const adjusted = clampExpandedPosition(position.value, viewport())
  if (adjusted.right === position.value.right && adjusted.bottom === position.value.bottom) return false
  position.value = adjusted
  writePosition()
  return true
}

watch(expanded, (isOpen) => { if (isOpen) ensurePanelVisible() })

const toggleExpanded = (): boolean => {
  expanded.value = !expanded.value
  writeFlag(EXPANDED_KEY, expanded.value)
  if (!expanded.value) return false
  applyState('listening')
  return ensurePanelVisible()
}

/**
 * 点头像是「叫它过来/让它退下」，不是摸头，因此不占用摸头冷却：
 * 用户展开面板后立刻点「摸摸头」不该被判成刷数值。
 */
const onAvatarClick = (): void => {
  if (suppressClick) return
  const moved = toggleExpanded()
  if (expanded.value) {
    flashPetState('happy')
    showBubble(moved ? '我往里挪了挪，这样面板能看全～' : '我来啦，想说什么直接说就好。')
    speakReply(moved ? '我往里挪了挪，这样面板能看全。' : '我来啦，想说什么直接说就好。')
    spawnEffects('✦', 2)
  } else {
    showBubble('我先退到角落，拖动可以挪位置。')
  }
}

const onSkinChange = (): void => { void applySkin(skinId.value) }

const cycleSkin = (): void => {
  const list = skins.value
  const index = list.findIndex(item => item.id === skinId.value)
  const next = list[(index + 1 + list.length) % list.length]
  if (next) { skinId.value = next.id; void applySkin(next.id) }
}

/** 打开工坊先看 DIY 皮肤；未保存就收起时还原到原来的形象。 */
const openCustomizer = (): void => {
  if (!customizerOpen.value) {
    skinBeforeDiy = skinId.value
    diyCommitted = false
  }
  customizerOpen.value = true
  expanded.value = true
  writeFlag(EXPANDED_KEY, true)
  ensurePanelVisible()
  if (skinId.value !== DIY_SKIN_ID) void applySkin(DIY_SKIN_ID)
}

const closeCustomizer = (): void => {
  customizerOpen.value = false
  if (!diyCommitted && skinBeforeDiy && skinBeforeDiy !== DIY_SKIN_ID) {
    skinId.value = skinBeforeDiy
    void applySkin(skinBeforeDiy)
  }
  skinBeforeDiy = null
}

const onCustomizationPreview = (value: CompanionCustomization): void => {
  const voiceChanged = value.voice.voiceURI !== customization.value.voice.voiceURI
  customization.value = value
  // 声线一换，正在念的那句会变成前后两种嗓子：立刻打断，下一次开口直接用新声线。
  if (voiceChanged) stopSpeaking()
  defaultSkinRegistry.upsert(buildDiySkin(value))
  skins.value = defaultSkinRegistry.list()
  service = new CompanionService(createDefaultPorts(value.lines))
  if (previewTimer !== null) clearTimeout(previewTimer)
  previewTimer = setTimeout(() => {
    if (!disposed && skinId.value === DIY_SKIN_ID) void applySkin(DIY_SKIN_ID)
  }, PREVIEW_DEBOUNCE_MS)
}

const onCustomizationApply = (value: CompanionCustomization): void => {
  customization.value = value
  saveCustomization(storage, value)
  defaultSkinRegistry.upsert(buildDiySkin(value))
  skins.value = defaultSkinRegistry.list()
  service = new CompanionService(createDefaultPorts(value.lines))
  diyCommitted = true
  if (skinId.value !== DIY_SKIN_ID) skinId.value = DIY_SKIN_ID
  void applySkin(DIY_SKIN_ID)
  spawnEffects('★', 4)
  showBubble(`好，以后我就是${value.name}啦。`, 'effect')
  speakReply(`好，以后我就是${value.name}啦。`)
}

const onQuietChange = (): void => {
  writeFlag(QUIET_KEY, quiet.value)
  showBubble(quiet.value ? '好，我先安静待着。' : '我回来啦，有事叫我。')
  if (quiet.value) {
    choreographer.reset()
    stopSpeaking()
  }
  publishDesktopState()
}

const toggleMute = (): void => {
  muted.value = !muted.value
  customization.value = {
    ...customization.value,
    voice: { ...customization.value.voice, muted: muted.value }
  }
  saveCustomization(storage, customization.value)
  if (muted.value) stopSpeaking()
  showBubble(muted.value ? '好，我只用气泡回答你。' : '声音打开啦。')
}

const resetPosition = (): void => {
  position.value = null
  try { localStorage.removeItem(COMPANION_POSITION_KEY) } catch { /* optional */ }
  showBubble('回到老位置啦。')
}

const onModelToggle = async (): Promise<void> => {
  if (!streamEnabled.value) {
    service = new CompanionService(createDefaultPorts(customization.value.lines))
    pushMessage('companion', '已切回本地回复，不会发起模型请求。')
    return
  }
  try {
    const { StreamChatPort } = await import('@/features/companion/adapters/chatStream')
    if (disposed || !streamEnabled.value) return
    const ports = createDefaultPorts(customization.value.lines)
    ports.chat = new StreamChatPort()
    service = new CompanionService(ports)
    pushMessage('companion', '已切换到模型回复，我会复用现有对话流回答你。')
  } catch {
    streamEnabled.value = false
    pushMessage('companion', '模型通道暂时不可用，先继续用本地回复陪你。')
  }
}

const toggleVoice = (): void => {
  if (voicePhase.value === 'speaking') {
    stopSpeaking()
    showBubble('好，我不说啦。')
    return
  }
  if (voicePhase.value === 'listening' || voicePhase.value === 'recognizing') {
    voice.stop()
    setListening(false)
    voicePhase.value = 'idle'
    return
  }
  voiceError.value = ''
  interim.value = ''
  voice.start({
    onPhase(phase) {
      voicePhase.value = phase
      setListening(phase === 'listening' || phase === 'recognizing')
      setSpeaking(phase === 'speaking')
      if (phase === 'speaking') voicePhase.value = 'speaking'
    },
    onInterim(text) { interim.value = text },
    onFinal(text) { interim.value = ''; handleUtterance(text) },
    onError(message) {
      voiceError.value = message
      showBubble(message, 'chat')
      setListening(false)
    }
  })
  if (!voiceCaps.value.recognition) {
    voicePhase.value = 'unsupported'
    voiceError.value = '这个环境暂时不能语音输入，点上面的指令或用系统语音输入（Win+H）也行。'
  }
}

const toggleVoiceMuteFromCommand = (on: boolean): void => {
  if (muted.value !== on) toggleMute()
}

const runCommand = (match: CommandMatch): void => {
  switch (match.id) {
    case 'collapse':
      expanded.value = false
      writeFlag(EXPANDED_KEY, false)
      break
    case 'summon':
      expanded.value = true
      writeFlag(EXPANDED_KEY, true)
      applyState('listening', true)
      break
    case 'quiet-on': quiet.value = true; onQuietChange(); break
    case 'quiet-off': quiet.value = false; onQuietChange(); break
    case 'mute-on': toggleVoiceMuteFromCommand(true); break
    case 'mute-off': toggleVoiceMuteFromCommand(false); break
    case 'stop-speaking':
      stopSpeaking()
      break
    case 'reset-position': resetPosition(); break
    case 'open-customizer': openCustomizer(); break
    case 'close-customizer': closeCustomizer(); break
    case 'next-skin': cycleSkin(); break
    case 'interact-pat': interact('pat'); break
    case 'interact-feed': interact('feed'); break
    case 'interact-play': interact('play'); break
  }
  pushMessage('companion', match.reply)
  showBubble(match.reply, 'effect')
  if (match.id !== 'stop-speaking') speakReply(match.reply)
}

/** 语音识别结果先过控制命令，再进入既有意图编排，不改执行链路。 */
const handleUtterance = (text: string): void => {
  const value = text.trim()
  if (!value) return
  pushMessage('user', value)
  const command = matchCompanionCommand(value)
  if (command) { runCommand(command); return }
  void send(value)
}

const onQuickSend = (text: string): void => { void send(text) }

const send = async (text: string): Promise<void> => {
  const value = text.trim()
  if (!value || pending.value) return
  if (!messages.value.length || messages.value[messages.value.length - 1]?.content !== value) {
    pushMessage('user', value)
  }
  pending.value = true
  applyState('thinking', true)
  abort?.abort()
  const controller = new AbortController()
  abort = controller
  try {
    const turn = await service.handle(
      value,
      { messages: messages.value, progress: null, personaName: personaName.value },
      controller.signal
    )
    if (disposed) return
    pushMessage('companion', turn.reply)
    card.value = turn.card
    applyState(turn.state)
    speakReply(turn.reply)
    trackAction(turn.intent === 'progress_query' ? 'progress' : turn.intent === 'task_dispatch' ? 'task' : 'chat')
  } catch {
    if (disposed) return
    pushMessage('companion', '刚才没能拿到回复，稍后再问我一次吧。')
    applyState('error')
  } finally {
    pending.value = false
  }
}

const handleTrayAction = (action: TrayAction): void => {
  switch (action) {
    case 'toggle': toggleExpanded(); break
    case 'summon':
      expanded.value = true
      writeFlag(EXPANDED_KEY, true)
      applyState('listening', true)
      showBubble('我在，叫我做什么？')
      speakReply('我在，叫我做什么？')
      break
    case 'progress':
      expanded.value = true
      writeFlag(EXPANDED_KEY, true)
      void send('现在的任务进度怎么样了？')
      break
    case 'quiet':
      quiet.value = !quiet.value
      onQuietChange()
      break
    case 'focus':
      expanded.value = true
      writeFlag(EXPANDED_KEY, true)
      break
    case 'voice':
      expanded.value = true
      writeFlag(EXPANDED_KEY, true)
      ensurePanelVisible()
      toggleVoice()
      break
  }
}

const handleKeydown = (event: KeyboardEvent): void => {
  const target = event.target as HTMLElement | null
  const typing = Boolean(target && (
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName) || target.isContentEditable
  ))
  if (event.key === 'Escape' && expanded.value) {
    expanded.value = false
    writeFlag(EXPANDED_KEY, false)
    return
  }
  if (typing) return
  if ((event.ctrlKey || event.metaKey) && event.shiftKey && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    toggleExpanded()
  }
  // R 兜底：只在面板展开、无修饰键时接管，避免吞掉页面其它输入。
  if (expanded.value && event.key.toLowerCase() === 'r' && !event.repeat
    && !event.ctrlKey && !event.metaKey && !event.altKey && voicePhase.value === 'idle') {
    event.preventDefault()
    toggleVoice()
  }
}

const tickIdle = (): void => {
  if (disposed) return
  const now = Date.now()
  const decision = choreographer.observe({
    now,
    lastInteractionAt: pet.value.lastInteractionAt,
    state: state.value,
    mood: moodOf(pet.value, now, state.value),
    quiet: quiet.value,
    hidden: typeof document === 'undefined' ? false : document.hidden
  })
  restingBecauseIdle.value = decision.sleep
  if (decision.sleep && state.value !== 'sleeping' && !NO_INTERRUPT.includes(state.value)) {
    state.value = 'sleeping'
    renderer?.setState('sleeping')
    publishDesktopState()
  }
  if (decision.line) showBubble(decision.line)
}

const handleVisibility = (): void => {
  if (document.hidden) {
    hiddenAt = Date.now()
    return
  }
  if (hiddenAt > 0 && Date.now() - hiddenAt > 30 * 60_000) {
    interact('visit', false)
    showBubble('你回来啦，我一直在这儿。')
  }
  hiddenAt = 0
}

const onPointerDown = (event: PointerEvent): void => {
  if (event.button !== 0) return
  // 以「角色」而不是根节点为拖拽参照：根节点的高度会随面板展开变化。
  const rect = stageRef.value?.getBoundingClientRect()
  if (!rect) return
  drag.active = true
  drag.moved = false
  drag.startX = event.clientX
  drag.startY = event.clientY
  drag.offsetX = event.clientX - rect.left
  drag.offsetY = event.clientY - rect.top
  drag.avatarWidth = rect.width
  drag.avatarHeight = rect.height
  window.addEventListener('pointermove', onPointerMove)
  window.addEventListener('pointerup', onPointerUp)
}

const onPointerMove = (event: PointerEvent): void => {
  if (!drag.active) return
  if (!drag.moved && Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY) < 5) return
  drag.moved = true
  dragging.value = true
  position.value = companionPositionFromDrag(
    { width: drag.avatarWidth, height: drag.avatarHeight },
    { x: event.clientX, y: event.clientY },
    { x: drag.offsetX, y: drag.offsetY },
    viewport()
  )
}

const onPointerUp = (): void => {
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  if (!drag.active) return
  drag.active = false
  dragging.value = false
  if (!drag.moved) return
  suppressClick = true
  if (clickSuppressTimer !== null) clearTimeout(clickSuppressTimer)
  clickSuppressTimer = setTimeout(() => { suppressClick = false }, 0)
  writePosition()
  // 展开态下拖到屏幕左侧也会把面板挤出视口，松手时同样避让一次。
  if (expanded.value && ensurePanelVisible()) showBubble('这边有点挤，我挪回来一点～')
}

const handleResize = (): void => {
  if (!position.value) return
  const next = expanded.value
    ? clampExpandedPosition(position.value, viewport())
    : clampCompanionPosition(position.value, viewport())
  if (next.right === position.value.right && next.bottom === position.value.bottom) return
  position.value = next
  writePosition()
}

onMounted(() => {
  window.addEventListener('companion:run-event', handleRuntimeEvent)
  window.addEventListener('keydown', handleKeydown)
  window.addEventListener('resize', handleResize)
  document.addEventListener('visibilitychange', handleVisibility)
  unsubscribeTray = desktop.onTrayAction(handleTrayAction)
  // 声线列表是异步就绪的（Chrome 首次返回空数组），补齐后工坊才有得选。
  unsubscribeVoices = voice.onVoicesChanged(() => {
    voiceOptions.value = voice.listVoices()
  })
  voiceOptions.value = voice.listVoices()
  void applySkin(skinId.value)
  // 刷新后若记住的是「展开态 + 靠左位置」，watch 不会触发，这里补一次避让。
  if (expanded.value) ensurePanelVisible()
  interact('visit', false)
  publishDesktopState()
  idleTimer = setInterval(tickIdle, IDLE_TICK_MS)
})

onBeforeUnmount(() => {
  disposed = true
  window.removeEventListener('companion:run-event', handleRuntimeEvent)
  window.removeEventListener('keydown', handleKeydown)
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('pointermove', onPointerMove)
  window.removeEventListener('pointerup', onPointerUp)
  document.removeEventListener('visibilitychange', handleVisibility)
  unsubscribeTray?.()
  unsubscribeTray = null
  unsubscribeVoices?.()
  unsubscribeVoices = null
  idleFallback.clear()
  choreographer.reset()
  queue.reset()
  if (bubbleTimer !== null) clearTimeout(bubbleTimer)
  if (clickSuppressTimer !== null) clearTimeout(clickSuppressTimer)
  if (idleTimer !== null) clearInterval(idleTimer)
  if (previewTimer !== null) clearTimeout(previewTimer)
  effectTimers.forEach(timer => clearTimeout(timer))
  effectTimers.clear()
  voice.dispose()
  abort?.abort()
  abort = null
  renderer?.destroy()
  renderer = null
})
</script>

<style scoped>
.companion-root {
  position: fixed; right: 24px; bottom: 24px; z-index: 2100;
  display: flex; flex-direction: column; align-items: flex-end; gap: 8px;
}
.companion-avatar {
  position: relative;
  width: 64px; height: 64px; box-sizing: border-box;
  border-radius: 50%; overflow: hidden;
  background: var(--bg-card); border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
  cursor: grab; touch-action: none; user-select: none;
  transition: width 180ms ease, height 180ms ease, box-shadow 180ms ease;
  animation: companion-bob 3.6s ease-in-out infinite;
}
.companion-root.is-expanded .companion-avatar { width: 76px; height: 76px; }
.companion-root.is-dragging .companion-avatar { cursor: grabbing; animation: none; box-shadow: 0 10px 26px rgba(0, 0, 0, 0.16); }
.companion-root[data-state="error"] .companion-avatar,
.companion-root[data-state="alert"] .companion-avatar {
  box-shadow: 0 0 0 3px var(--accent-fade, rgba(76, 141, 255, 0.16));
  animation: companion-wiggle 620ms ease-in-out infinite;
}
.companion-root[data-state="sleeping"] .companion-avatar { animation-duration: 6s; }
.companion-root[data-state="happy"] .companion-avatar { animation-duration: 1.5s; }
.companion-root[data-speaking="1"] .companion-avatar {
  box-shadow: 0 0 0 2px var(--accent-fade, rgba(76, 141, 255, 0.2)), 0 0 24px var(--primary-color, #4c8dff);
  animation-duration: 1.1s;
}
.companion-root[data-listening="1"] .companion-avatar { animation-duration: 1.8s; }
.companion-zzz {
  position: absolute; top: 4px; right: 6px; font-size: 10px; letter-spacing: 1px;
  color: var(--text-muted, var(--text-secondary)); pointer-events: none;
}
.companion-fx {
  position: absolute; bottom: 30%; font-size: 13px; line-height: 1; pointer-events: none;
  color: var(--primary-color, #4c8dff);
  animation: companion-float 1.6s ease-out forwards;
}
.companion-panel {
  width: min(320px, calc(100vw - 48px)); box-sizing: border-box; padding: 10px;
  display: flex; flex-direction: column; gap: 9px;
  /* 预留角色 76px、气泡与间距；小窗口/被拖到屏幕上方时面板内部滚动，整体不越界。 */
  max-height: max(240px, calc(100vh - var(--companion-bottom, 24px) - 132px));
  overflow-y: auto; overscroll-behavior: contain;
  background: var(--bg-glass, var(--bg-card)); color: var(--text-primary);
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 12px;
  box-shadow: 0 12px 36px rgba(0, 0, 0, 0.12);
  animation: companion-panel-in 220ms ease-out;
}
.companion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.companion-name { font-size: 13px; font-weight: 500; margin-right: 8px; }
.companion-state { font-size: 11px; color: var(--text-muted, var(--text-secondary)); }
.companion-header button, .companion-footer select, .companion-diy-btn {
  font: inherit; font-size: 12px; padding: 3px 7px; cursor: pointer;
  color: var(--text-regular, var(--text-primary)); background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
}
.companion-diy-btn { color: var(--primary-color, #4c8dff); }
.companion-footer { display: flex; align-items: center; justify-content: space-between; gap: 5px; flex-wrap: wrap; }
.companion-toggle { display: flex; align-items: center; gap: 3px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
.companion-toggle input { margin: 0; }
.companion-reset {
  align-self: flex-start; font: inherit; font-size: 11px; padding: 2px 0; cursor: pointer;
  color: var(--text-muted, var(--text-secondary)); background: none; border: none;
}
.companion-reset:hover { color: var(--primary-color, #4c8dff); }
/* 表情层的光晕由渲染器动态创建，需要 :deep 才能命中。 */
.companion-avatar :deep(.companion-face-ring) { transform-origin: 100px 100px; }
.companion-avatar :deep(svg[data-companion-listening="1"] .companion-face-ring) {
  animation: companion-ring 1.4s ease-out infinite;
}
.companion-avatar :deep(svg[data-companion-speaking="1"] .companion-face-ring) {
  animation: companion-ring 900ms ease-out infinite;
  opacity: 0.3;
}
@keyframes companion-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}
@keyframes companion-wiggle {
  0%, 100% { transform: rotate(0); }
  25% { transform: rotate(-4deg); }
  75% { transform: rotate(4deg); }
}
@keyframes companion-ring {
  0% { opacity: 0.55; transform: scale(0.94); }
  100% { opacity: 0; transform: scale(1.12); }
}
@keyframes companion-float {
  0% { opacity: 0; transform: translateY(6px) scale(0.7); }
  25% { opacity: 1; }
  100% { opacity: 0; transform: translateY(-38px) scale(1.15); }
}
@keyframes companion-panel-in {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .companion-avatar, .companion-panel, .companion-fx { animation: none; transition: none; }
  .companion-fx { display: none; }
  .companion-avatar :deep(svg[data-companion-listening="1"] .companion-face-ring),
  .companion-avatar :deep(svg[data-companion-speaking="1"] .companion-face-ring) { animation: none; opacity: 0.25; }
}
</style>
