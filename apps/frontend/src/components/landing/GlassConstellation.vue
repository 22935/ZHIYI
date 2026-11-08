<template>
  <div
    ref="root"
    class="agent-constellation"
    :class="{ 'is-controls-open': controlsExpanded, 'is-hovered': isHovered }"
    :style="agentThemeStyle"
    data-testid="glass-constellation"
    :data-voice-state="voiceState"
    role="group"
    aria-label="知弈 Agent 角色控制"
    @pointerenter="isHovered = true"
    @pointerleave="handlePointerLeave"
    @keydown.esc="controlsExpanded = false"
  >
    <div class="agent-stage" :class="{ 'agent-stage--listening': isListening, 'agent-stage--awake': isAwake }">
      <div class="agent-stage__halo" aria-hidden="true"></div>
      <div class="agent-stage__orbit-light" aria-hidden="true"></div>

      <button
        class="agent-avatar-trigger"
        data-testid="agent-avatar-trigger"
        type="button"
        :aria-expanded="controlsExpanded"
        aria-controls="agent-control-dock"
        :aria-label="controlsExpanded ? '收起 Agent 控制台' : '打开 Agent 控制台'"
        @click="toggleControls"
      >
        <svg
          ref="avatarSvg"
          class="agent-avatar"
          data-testid="agent-avatar"
          role="img"
          :aria-label="`知弈 Agent，${colorLabel}${shapeLabel}，当前${statusLabel}`"
        ></svg>
      </button>

      <div class="agent-stage__prompt" aria-hidden="true">{{ controlsExpanded ? '控制台已展开' : '点击唤醒控制台' }}</div>
      <div class="agent-stage__status" aria-live="polite">
        <span class="agent-stage__status-dot"></span>
        <span>{{ shownLabel }}</span>
      </div>

      <div
        v-if="conversationReply || conversationPending || conversationError"
        class="agent-conversation"
        data-testid="agent-conversation"
        aria-live="polite"
      >
        <span class="agent-conversation__label">JUSTIN</span>
        <p>{{ conversationPending && !conversationReply ? '正在连接智能协作者…' : conversationReply || conversationError }}</p>
      </div>
    </div>

    <div id="agent-control-dock" data-testid="agent-controls" class="agent-controls" :class="{ 'is-open': controlsExpanded }" :aria-hidden="!controlsExpanded" aria-label="Agent 动效控制" @click.stop>
      <div class="agent-controls__head">
        <div>
          <span class="agent-controls__eyebrow">AGENT CONSOLE</span>
          <strong>调节协作者</strong>
        </div>
        <div class="agent-controls__summary">
          <span class="agent-controls__summary-dot"></span>
          <span>{{ shownLabel }}</span>
          <span class="agent-controls__summary-divider">·</span>
          <span>{{ shapeLabel }}</span>
        </div>
        <button class="agent-controls__close" type="button" aria-label="关闭 Agent 控制台" @click="controlsExpanded = false">×</button>
      </div>

      <div class="agent-controls__tabs" role="tablist" aria-label="Agent 控制类别">
        <button
          v-for="panel in controlPanels"
          :key="panel.id"
          class="agent-controls__tab"
          :class="{ 'is-active': activePanel === panel.id }"
          :data-testid="`agent-control-tab-${panel.id}`"
          type="button"
          role="tab"
          :aria-selected="activePanel === panel.id"
          :aria-controls="`agent-control-panel-${panel.id}`"
          @click="activePanel = panel.id"
        >
          <span>{{ panel.label }}</span>
          <small>{{ panel.meta }}</small>
        </button>
      </div>

      <section id="agent-control-panel-shape" class="agent-controls__panel" :class="{ 'is-current': activePanel === 'shape' }" role="tabpanel" aria-labelledby="agent-control-tab-shape" :aria-hidden="activePanel !== 'shape'">
        <div class="agent-controls__panel-intro">
          <span>角色轮廓</span>
          <strong>{{ shapeLabel }}</strong>
        </div>
        <div class="agent-controls__choice-grid agent-controls__choice-grid--shapes">
          <button
            v-for="item in shapeOptions"
            :key="item.id"
            class="agent-control"
            data-testid="agent-shape-option"
            type="button"
            :aria-label="`切换为${item.label}`"
            :aria-pressed="shapeLabel === item.label"
            @click="applyShape(item.id)"
          >{{ item.label }}</button>
        </div>
      </section>

      <section id="agent-control-panel-state" class="agent-controls__panel" :class="{ 'is-current': activePanel === 'state' }" role="tabpanel" aria-labelledby="agent-control-tab-state" :aria-hidden="activePanel !== 'state'">
        <div class="agent-controls__panel-intro">
          <span>当前心境</span>
          <strong>{{ shownLabel }}</strong>
        </div>
        <div class="agent-controls__states">
          <div v-for="group in stateGroups" :key="group.label" class="agent-controls__line agent-controls__line--states">
            <span class="agent-controls__label">{{ group.label }}</span>
            <button
              v-for="item in group.options"
              :key="item.id"
              class="agent-control"
              data-testid="agent-action-option"
              type="button"
              :aria-label="`切换到${item.label}`"
              :aria-pressed="currentState === item.id"
              @click="applyState(item.id)"
            >{{ item.label }}</button>
          </div>
        </div>
      </section>

      <section id="agent-control-panel-actions" class="agent-controls__panel" :class="{ 'is-current': activePanel === 'actions' }" role="tabpanel" aria-labelledby="agent-control-tab-actions" :aria-hidden="activePanel !== 'actions'">
        <div class="agent-controls__panel-intro">
          <span>即时动作</span>
          <strong>让它动起来</strong>
        </div>
        <div class="agent-controls__line agent-controls__line--actions">
          <button class="agent-control agent-control--featured" data-testid="agent-action-option" type="button" aria-label="转一圈" @click="applyOneShot('spin')">转一圈</button>
          <button class="agent-control agent-control--featured" data-testid="agent-action-option" type="button" aria-label="跳一下" @click="applyOneShot('bounce')">跳一下</button>
          <button class="agent-control agent-control--featured" data-testid="agent-action-option" type="button" aria-label="撒粒子" @click="applyOneShot('burst')">粒子</button>
          <button class="agent-control" type="button" aria-label="登录轮换" :aria-pressed="mode === 'onboarding'" @click="resumeOnboarding">登录轮换</button>
          <button class="agent-control" type="button" aria-label="跟随指针" :aria-pressed="followOn" @click="toggleFollow">跟随指针</button>
          <button
            class="agent-control agent-control--voice"
            data-testid="agent-voice-toggle"
            type="button"
            :class="{ 'is-listening': isListening }"
            :aria-pressed="isListening"
            :aria-label="isListening ? '停止语音交互' : '开始语音交互'"
            @click="toggleVoice"
          >
            <Microphone aria-hidden="true" />
            <span>{{ isListening ? (isAwake ? '已唤醒' : '守候中') : '语音' }}</span>
          </button>
        </div>
        <p class="agent-controls__hint agent-controls__hint--block">{{ voiceStatus }}</p>
      </section>

      <section id="agent-control-panel-color" class="agent-controls__panel" :class="{ 'is-current': activePanel === 'color' }" role="tabpanel" aria-labelledby="agent-control-tab-color" :aria-hidden="activePanel !== 'color'">
        <div class="agent-controls__panel-intro">
          <span>视觉色彩</span>
          <strong>{{ colorLabel }}</strong>
        </div>
        <div class="agent-controls__color-grid">
          <button
            v-for="item in colorOptions"
            :key="item.id"
            class="agent-color"
            data-testid="agent-color-option"
            type="button"
            :style="{ '--swatch': item.main, '--swatch-deep': item.deep }"
            :aria-label="`切换为${item.label}`"
            :aria-pressed="colorLabel === item.label"
            :title="item.label"
            @click="applyColor(item.id)"
          ><span>{{ item.label }}</span></button>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Microphone } from '@element-plus/icons-vue'
import { useChatStore } from '@/stores/chat'
import { GROK_GEO, GROK_META, GrokCharacter, type GrokCharacterInstance } from '@/lib/grok-character'

type OneShotId = 'spin' | 'bounce' | 'burst'

// 引擎符号是源码混淆名，这里统一挂中文标签；语音关键词同时收中英文。
const SHAPE_ZH: Record<string, string> = {
  blob: '流体', pebble: '卵石', bean: '豆形', egg: '蛋形', squircle: '方圆', tablet: '平板',
  capsule: '胶囊', cylinder: '圆柱', hex: '六边', gem: '宝石', crystal: '晶体', wedge: '楔形',
  shield: '盾形', dome: '穹顶', arch: '拱形', cloud: '云朵', teardrop: '水滴', leaf: '叶形'
}
const STATE_ZH: Record<string, string> = {
  sleeping: '睡着了', waking: '苏醒', idle: '待机', listening: '聆听', thinking: '思考中', searching: '搜索中', working: '工作中',
  excited: '兴奋', surprised: '惊讶', suspicious: '狐疑', angry: '生气', drowsy: '困倦', happy: '开心', curious: '好奇',
  confused: '困惑', bored: '无聊', proud: '自豪', shy: '害羞', sad: '难过', laughing: '大笑', scared: '害怕', playful: '俏皮', celebrate: '庆祝',
  orbit: '环绕', radar: '雷达', progress: '进度',
  spawning: '生成', humming: '哼歌', loading: '加载中', dictating: '听写', writing: '书写', sending: '发送',
  receiving: '接收', uploading: '上传', notifying: '通知', alerting: '警报', dragging: '拖拽', bouncing: '弹跳', 'powering-down': '关机'
}
const COLOR_ZH: Record<string, string> = {
  black: '黑曜', brown: '棕褐', red: '赤焰', orange: '炽橙', yellow: '金橙', green: '薄荷',
  cyan: '澄蓝', blue: '蓝曜', violet: '紫晶', magenta: '品红', gray: '岩灰'
}

const shapeOptions = Object.keys(GROK_GEO.shapes).map(id => ({ id, label: SHAPE_ZH[id] ?? GROK_GEO.shapes[id].label }))
const colorOptions = Object.keys(GROK_GEO.palette).map(id => ({
  id,
  label: COLOR_ZH[id] ?? id,
  main: GROK_GEO.palette[id].light,
  deep: GROK_GEO.palette[id].dark
}))
const stateGroups = GROK_META.groups.map(group => ({
  label: group.label,
  options: group.states.map(id => ({ id, label: STATE_ZH[id] ?? id }))
}))

const controlPanels = [
  { id: 'shape', label: '形态', meta: `${shapeOptions.length}` },
  { id: 'state', label: '状态', meta: `${stateGroups.reduce((total, group) => total + group.options.length, 0)}` },
  { id: 'actions', label: '动作', meta: '3+' },
  { id: 'color', label: '颜色', meta: `${colorOptions.length}` }
] as const
type ControlPanelId = typeof controlPanels[number]['id']

const root = ref<HTMLElement | null>(null)
const avatarSvg = ref<SVGSVGElement | null>(null)
const emit = defineEmits<{
  (event: 'voice-message', text: string): void
}>()
const chatStore = useChatStore()

const currentShape = ref('blob')
const currentColor = ref('violet')
const currentState = ref('idle')
const mode = ref<'onboarding' | 'hold'>('onboarding')
const followOn = ref(true)
const statusLabel = ref('好奇')
const labelOverride = ref('')
const controlsExpanded = ref(false)
const activePanel = ref<ControlPanelId>('state')
const isHovered = ref(false)
const isListening = ref(false)
const isAwake = ref(false)
const transcript = ref('')
const conversationReply = ref('')
const conversationError = ref('')
const conversationPending = ref(false)
let bot: GrokCharacterInstance | null = null
let labelTimer: number | undefined
let resumeTimer: number | undefined
let voiceRestartTimer: number | undefined

const shapeLabel = computed(() => SHAPE_ZH[currentShape.value] ?? currentShape.value)
const colorLabel = computed(() => COLOR_ZH[currentColor.value] ?? currentColor.value)
const shownLabel = computed(() => labelOverride.value || statusLabel.value)
const agentThemeStyle = computed(() => {
  const palette = GROK_GEO.palette[currentColor.value] ?? GROK_GEO.palette.violet
  return {
    '--agent-main': palette.light,
    '--agent-deep': palette.dark,
    '--agent-light': `color-mix(in srgb, ${palette.light} 18%, white)`,
    '--agent-glow': `color-mix(in srgb, ${palette.light} 44%, white)`
  }
})
const voiceStatus = computed(() => {
  if (isListening.value && !isAwake.value) return '语音守候中 · 说 “Justin” 唤醒对话'
  if (isListening.value && isAwake.value) return 'Justin 已唤醒 · 请说出颜色、形状或动作'
  if (transcript.value) return `识别：${transcript.value}`
  return '点击语音，或说 “Justin” 开始对话'
})
const voiceState = computed(() => isAwake.value ? 'awake' : isListening.value ? 'waiting' : 'idle')

const flashLabel = (text: string, duration = 1500) => {
  labelOverride.value = text
  window.clearTimeout(labelTimer)
  labelTimer = window.setTimeout(() => { labelOverride.value = '' }, duration)
}

const applyShape = (id: string) => {
  if (!bot || !GROK_GEO.shapes[id] || currentShape.value === id) return
  mode.value = 'hold'
  bot.setMode('hold')
  currentShape.value = id
  bot.setShape(id)
}

const applyColor = (id: string) => {
  if (!GROK_GEO.palette[id]) return
  currentColor.value = id
  bot?.setColor(id, 'light')
}

const applyState = (id: string) => {
  if (!bot) return
  mode.value = 'hold'
  bot.setMode('hold')
  bot.setState(id)
}

const applyOneShot = (id: OneShotId) => {
  if (!bot) return
  if (id === 'spin') { bot.spinOnce(1); flashLabel('旋转中') }
  else if (id === 'bounce') { bot.bounceOnce(); flashLabel('弹跳中') }
  else { bot.burstOnce(); flashLabel('粒子') }
}

const resumeOnboarding = () => {
  if (!bot) return
  mode.value = 'onboarding'
  bot.setMode('onboarding')
}

const toggleFollow = () => {
  followOn.value = !followOn.value
  bot?.setFollowPointer(followOn.value)
}

const resumeOnboardingLater = (delay = 4200) => {
  window.clearTimeout(resumeTimer)
  resumeTimer = window.setTimeout(() => {
    if (!isListening.value) resumeOnboarding()
  }, delay)
}

const handlePointerLeave = () => {
  isHovered.value = false
}

const toggleControls = () => {
  controlsExpanded.value = !controlsExpanded.value
  if (controlsExpanded.value) {
    activePanel.value = 'state'
    applyState('curious')
  }
}

interface SpeechResultEvent { resultIndex?: number; results: ArrayLike<ArrayLike<{ transcript: string; isFinal?: boolean }>> }
interface SpeechRecognitionLike {
  lang: string
  continuous: boolean
  interimResults: boolean
  onresult: ((event: SpeechResultEvent) => void) | null
  onerror: (() => void) | null
  onend: (() => void) | null
  start: () => void
  stop: () => void
}
type SpeechRecognitionConstructor = new () => SpeechRecognitionLike

const submitConversation = async (text: string) => {
  const message = text.trim()
  if (!message || conversationPending.value) return

  emit('voice-message', message)
  if (!localStorage.getItem('token')) {
    conversationError.value = '请先登录，再开始 Justin 对话'
    return
  }

  conversationReply.value = ''
  conversationError.value = ''
  conversationPending.value = true
  const streamStart = chatStore.messages.length
  const stopWatching = watch(
    () => chatStore.messages.slice(streamStart).map(item => ({ role: item.role, content: item.content })),
    (items) => {
      const latest = [...items].reverse().find(item => item.role === 'assistant')
      if (latest?.content) conversationReply.value = latest.content
    },
    { deep: true }
  )

  applyState('thinking')
  try {
    await chatStore.sendMessageStream(message, 'default', undefined, 'agent')
    const latest = chatStore.messages.slice(streamStart).reverse().find(item => item.role === 'assistant')
    if (latest?.content) {
      conversationReply.value = latest.content
      applyState('happy')
    } else if (!conversationReply.value) {
      conversationError.value = '没有收到有效回复，请稍后再试'
      applyState('surprised')
    }
  } catch (error) {
    conversationError.value = error instanceof Error ? error.message : '对话请求失败，请稍后再试'
    applyState('surprised')
  } finally {
    stopWatching()
    conversationPending.value = false
    resumeOnboardingLater()
  }
}

// “思考中”这类标签要能被“思考”唤醒：剥掉状态后缀再参与匹配。
const matchKey = (label: string) => label.replace(/(中|了)$/, '')
const COLOR_KEYS: Record<string, string[]> = {
  black: ['黑'], brown: ['棕'], red: ['红', '赤'], orange: ['橙'], yellow: ['黄', '金'],
  green: ['绿', '薄荷'], cyan: ['青', '澄'], blue: ['蓝'], violet: ['紫'],
  magenta: ['品红', '粉', '洋红'], gray: ['灰', '岩']
}

const applyVoiceCommand = (rawCommand: string) => {
  const command = rawCommand.toLowerCase()
  let restyled = false
  let motion = false

  const nextColor = colorOptions.find(item => (COLOR_KEYS[item.id] ?? []).some(key => command.includes(key)))
  if (nextColor) {
    applyColor(nextColor.id)
    restyled = true
  }

  const nextShape = shapeOptions.find(item => command.includes(matchKey(item.label)) || command.includes(item.id))
  if (nextShape) {
    applyShape(nextShape.id)
    restyled = true
  }

  if (/旋转|转一圈|spin/.test(command)) { applyOneShot('spin'); motion = true }
  else if (/弹跳|跳起来|蹦|bounce|jump/.test(command)) { applyOneShot('bounce'); motion = true }
  else if (/粒子|撒花|burst/.test(command)) { applyOneShot('burst'); motion = true }

  if (!motion) {
    const nextState = stateGroups
      .flatMap(group => group.options)
      .find(item => command.includes(matchKey(item.label)) || command.includes(item.id))
    if (nextState) {
      applyState(nextState.id)
      motion = true
    } else if (/待机|停止|idle/.test(command)) {
      resumeOnboarding()
      motion = true
    }
  }

  // 换色/换形本身不是表情，补一记好奇让反馈更明显；不得覆盖刚点名的状态。
  if (restyled && !motion) applyState('curious')
  return restyled || motion
}

const wakeWordPattern = /justin|贾斯汀/i
const handleVoiceTranscript = (rawTranscript: string) => {
  const command = rawTranscript.trim()
  if (!command) return

  if (!isAwake.value) {
    const wakeMatch = command.match(wakeWordPattern)
    if (!wakeMatch) {
      transcript.value = command
      return
    }

    isAwake.value = true
    applyState('curious')
    const afterWakeWord = command.slice((wakeMatch.index ?? 0) + wakeMatch[0].length).replace(/^[\s,，。.!！?？]+/, '')
    transcript.value = afterWakeWord ? `Justin · ${afterWakeWord}` : 'Justin 已唤醒'
    if (afterWakeWord && !applyVoiceCommand(afterWakeWord)) void submitConversation(afterWakeWord)
    return
  }

  transcript.value = command
  if (!applyVoiceCommand(command)) void submitConversation(command)
}

const stopVoice = () => {
  window.clearTimeout(voiceRestartTimer)
  recognition?.stop()
  recognition = null
  isListening.value = false
  isAwake.value = false
  resumeOnboarding()
}

let recognition: SpeechRecognitionLike | null = null
const startVoice = () => {
  const Constructor = recognitionConstructor()
  if (!Constructor) {
    transcript.value = '当前浏览器不支持语音识别'
    return
  }

  recognition = new Constructor()
  recognition.lang = 'zh-CN'
  recognition.continuous = true
  recognition.interimResults = true
  recognition.onresult = (event) => {
    const result = event.results[event.resultIndex ?? 0]?.[0]
    if (!result || result.isFinal === false) return
    handleVoiceTranscript(result.transcript)
  }
  recognition.onerror = () => { transcript.value = '没有听清，请再试一次' }
  recognition.onend = () => {
    if (!isListening.value || !recognition) return
    window.clearTimeout(voiceRestartTimer)
    voiceRestartTimer = window.setTimeout(() => {
      if (!isListening.value || !recognition) return
      try { recognition.start() } catch { transcript.value = '语音权限尚未开启' }
    }, 280)
  }
  try {
    recognition.start()
    isListening.value = true
    isAwake.value = false
    applyState('listening')
  } catch {
    transcript.value = '语音权限尚未开启'
    stopVoice()
  }
}

const toggleVoice = () => { if (isListening.value) stopVoice(); else startVoice() }

const recognitionConstructor = () => {
  const speechWindow = window as Window & { SpeechRecognition?: SpeechRecognitionConstructor; webkitSpeechRecognition?: SpeechRecognitionConstructor }
  return speechWindow.SpeechRecognition || speechWindow.webkitSpeechRecognition
}

onMounted(() => {
  if (!avatarSvg.value) return
  bot = new GrokCharacter(avatarSvg.value, {
    shape: 'blob',
    color: 'violet',
    scheme: 'light',
    mode: 'onboarding',
    state: 'idle',
    loginWrap: true,
    followPointer: true,
    badgeColor: GROK_GEO.palette.violet.light,
    onChange(snapshot) {
      currentState.value = snapshot.state
      statusLabel.value = STATE_ZH[snapshot.state] ?? snapshot.state
    }
  })
  // 与登录页一致：首拍从 curious 起播，让角色一上来就有表情。
  bot.moodN = 1
  bot.setState('curious', { resetEyes: true })
})

onBeforeUnmount(() => {
  window.clearTimeout(labelTimer)
  window.clearTimeout(resumeTimer)
  window.clearTimeout(voiceRestartTimer)
  stopVoice()
  bot?.destroy()
  bot = null
  if (conversationPending.value) chatStore.cancelMessageStream()
})
</script>

<script lang="ts">
export default { name: 'GlassConstellation' }
</script>

<style scoped lang="scss">
.agent-constellation { position: relative; width: min(46vw, 680px); height: min(50vw, 720px); min-width: 420px; min-height: 470px; margin-left: auto; transform: translateX(clamp(0px, 1.8vw, 28px)); isolation: isolate; color: #426286; }
.agent-stage { position: absolute; inset: 0; display: grid; place-items: center; }
.agent-stage::before { content: ''; position: absolute; width: 58%; height: 15%; bottom: 13%; border-radius: 50%; background: radial-gradient(ellipse, color-mix(in srgb, var(--agent-deep, #5c39a1) 22%, transparent), transparent 72%); filter: blur(20px); opacity: .72; }
.agent-stage__halo { position: absolute; inset: 11%; border-radius: 50%; background: radial-gradient(circle, color-mix(in srgb, var(--agent-glow, #cdb6ff) 36%, transparent), color-mix(in srgb, var(--agent-main, #a97efe) 12%, transparent) 38%, transparent 72%); filter: blur(32px); animation: agent-halo 5s ease-in-out infinite; }
.agent-stage__orbit-light { position: absolute; top: 14%; right: 17%; width: 9px; height: 9px; border: 1px solid rgba(255,255,255,.8); border-radius: 50%; background: var(--agent-glow, #cdb6ff); box-shadow: 0 0 16px 3px color-mix(in srgb, var(--agent-glow, #cdb6ff) 66%, transparent); animation: orbit-light 4.8s ease-in-out infinite; }
.agent-avatar-trigger { position: relative; z-index: 2; width: 74%; height: 74%; padding: 0; border: 0; border-radius: 50%; background: transparent; cursor: pointer; transition: width 360ms cubic-bezier(.2, .8, .2, 1), height 360ms cubic-bezier(.2, .8, .2, 1), transform 360ms cubic-bezier(.2, .8, .2, 1), filter 360ms ease; }
.agent-constellation.is-controls-open .agent-stage { box-sizing: border-box; padding-bottom: clamp(250px, 31vh, 320px); }
.agent-constellation.is-controls-open .agent-avatar-trigger { width: 56%; height: 56%; transform: translateY(-8px); }
.agent-constellation.is-controls-open .agent-stage__halo { inset: 3% 16% 38%; }
.agent-avatar-trigger:hover { transform: translateY(-4px) scale(1.018); filter: drop-shadow(0 30px 26px color-mix(in srgb, var(--agent-deep, #5c39a1) 30%, transparent)); }
.agent-avatar-trigger:focus-visible { outline: 3px solid color-mix(in srgb, var(--agent-main, #a97efe) 62%, white); outline-offset: 8px; }
.agent-avatar { display: block; width: 100%; height: 100%; overflow: visible; color-scheme: light; }
/* 引擎把 fill 写成 presentation attribute（fill="var(--fg, #000)"）；
   部分内核对 attribute 里的 var() 不做替换，这里用 CSS 规则兜底（规则优先级恒高于 presentation attribute）。 */
.agent-avatar :deep([fill='var(--fg, #000)']) { fill: var(--fg, #000); }
.agent-avatar :deep([fill='var(--bg, #f3efe6)']) { fill: var(--bg, #f3efe6); }
.agent-stage__prompt { position: absolute; top: 12%; z-index: 3; padding: 6px 10px; border: 1px solid rgba(255,255,255,.5); border-radius: 999px; color: color-mix(in srgb, var(--agent-deep, #5c39a1) 66%, #587698); background: rgba(255,255,255,.26); opacity: 0; transform: translateY(5px); transition: opacity 240ms ease, transform 240ms ease; backdrop-filter: blur(10px); font-size: 10px; letter-spacing: .06em; pointer-events: none; }
.agent-constellation.is-hovered .agent-stage__prompt, .agent-constellation.is-controls-open .agent-stage__prompt { opacity: 1; transform: translateY(0); }
.agent-stage__status { position: absolute; bottom: 19%; z-index: 3; display: inline-flex; align-items: center; gap: 7px; padding: 7px 12px; border: 1px solid color-mix(in srgb, var(--agent-main, #a97efe) 22%, white); border-radius: 999px; color: #5d7ba1; background: rgba(255, 255, 255, .42); box-shadow: 0 8px 20px rgba(75, 129, 181, .08), inset 0 1px 0 rgba(255,255,255,.7); backdrop-filter: blur(12px); font-size: 10px; letter-spacing: .08em; }
.agent-stage__status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--agent-main, #a97efe); box-shadow: 0 0 10px var(--agent-glow, #cdb6ff); }
.agent-stage--awake .agent-stage__status { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 58%, white); color: color-mix(in srgb, var(--agent-deep, #5c39a1) 86%, #173963); box-shadow: 0 0 0 5px color-mix(in srgb, var(--agent-glow, #cdb6ff) 12%, transparent), 0 10px 24px rgba(75, 129, 181, .14), inset 0 1px 0 rgba(255,255,255,.8); }
.agent-stage--awake .agent-stage__status-dot { animation: awake-pulse 1s ease-in-out infinite; }
.agent-controls { position: absolute; bottom: 4%; left: 50%; z-index: 4; width: min(100%, 520px); max-height: min(44vh, 390px); box-sizing: border-box; display: grid; gap: 12px; padding: 15px; overflow: hidden; border: 1px solid color-mix(in srgb, var(--agent-main, #a97efe) 18%, white); border-radius: 22px; background: linear-gradient(145deg, rgba(255,255,255,.76), color-mix(in srgb, var(--agent-light, #f1e8ff) 34%, rgba(225,242,255,.62))); box-shadow: 0 26px 60px color-mix(in srgb, var(--agent-deep, #5c39a1) 18%, rgba(73,125,207,.16)), inset 0 1px 0 rgba(255,255,255,.96), inset 0 -1px 0 rgba(125,177,220,.14); opacity: 0; visibility: hidden; pointer-events: none; transform: translate(-50%, 14px) scale(.94); transition: opacity 300ms ease, transform 360ms cubic-bezier(.2, .8, .2, 1), visibility 300ms ease; backdrop-filter: blur(22px) saturate(135%); }
.agent-controls::before { content: ''; position: absolute; top: -7px; left: 50%; width: 13px; height: 13px; border-top: 1px solid rgba(255,255,255,.72); border-left: 1px solid rgba(255,255,255,.72); background: rgba(244,250,255,.7); transform: translateX(-50%) rotate(45deg); backdrop-filter: blur(12px); }
.agent-controls.is-open { opacity: 1; visibility: visible; pointer-events: auto; transform: translate(-50%, 0) scale(1); }
.agent-controls__head { display: flex; align-items: center; gap: 10px; min-width: 0; }
.agent-controls__head > div:first-child { display: grid; gap: 2px; min-width: 0; }
.agent-controls__eyebrow { color: color-mix(in srgb, var(--agent-deep, #5c39a1) 56%, #7290b4); font: 9px var(--font-mono, monospace); letter-spacing: .16em; }
.agent-controls__head strong { overflow: hidden; color: #294c76; font: 600 15px/1.25 var(--font-sans, sans-serif); text-overflow: ellipsis; white-space: nowrap; }
.agent-controls__summary { display: inline-flex; align-items: center; gap: 6px; min-width: 0; margin-left: auto; padding: 6px 9px; border: 1px solid color-mix(in srgb, var(--agent-main, #a97efe) 15%, white); border-radius: 999px; color: color-mix(in srgb, var(--agent-deep, #5c39a1) 72%, #55769c); background: rgba(255,255,255,.42); font-size: 10px; white-space: nowrap; }
.agent-controls__summary-dot { width: 6px; height: 6px; flex: 0 0 auto; border-radius: 50%; background: var(--agent-main, #a97efe); box-shadow: 0 0 0 4px color-mix(in srgb, var(--agent-glow, #cdb6ff) 24%, transparent), 0 0 10px var(--agent-glow, #cdb6ff); }
.agent-controls__summary-divider { color: color-mix(in srgb, var(--agent-main, #a97efe) 35%, #8ea6c2); }
.agent-controls__close { width: 26px; height: 26px; flex: 0 0 auto; padding: 0; border: 1px solid rgba(111,151,190,.18); border-radius: 50%; color: #6d89aa; background: rgba(255,255,255,.42); cursor: pointer; font-size: 18px; line-height: 1; transition: color 180ms ease, background-color 180ms ease, transform 180ms ease; }
.agent-controls__close:hover { color: color-mix(in srgb, var(--agent-deep, #5c39a1) 82%, #173963); background: rgba(255,255,255,.8); transform: rotate(90deg); }
.agent-controls__tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; padding: 4px; border: 1px solid rgba(111,151,190,.12); border-radius: 13px; background: rgba(255,255,255,.3); }
.agent-controls__tab { min-width: 0; padding: 7px 6px 6px; border: 1px solid transparent; border-radius: 10px; color: #7893b2; background: transparent; cursor: pointer; font: 600 11px/1.1 var(--font-sans, sans-serif); transition: border-color 180ms ease, color 180ms ease, background-color 180ms ease, transform 180ms ease; }
.agent-controls__tab small { display: block; margin-top: 3px; color: #9aafc7; font: 9px var(--font-mono, monospace); }
.agent-controls__tab:hover { color: color-mix(in srgb, var(--agent-deep, #5c39a1) 72%, #294c76); background: rgba(255,255,255,.48); }
.agent-controls__tab.is-active { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 24%, white); color: color-mix(in srgb, var(--agent-deep, #5c39a1) 84%, #173963); background: color-mix(in srgb, var(--agent-light, #f1e8ff) 66%, white); box-shadow: 0 4px 10px color-mix(in srgb, var(--agent-deep, #5c39a1) 8%, transparent), inset 0 1px 0 rgba(255,255,255,.86); transform: translateY(-1px); }
.agent-controls__tab.is-active small { color: color-mix(in srgb, var(--agent-main, #a97efe) 72%, #7390b1); }
.agent-controls__panel { display: none; min-height: 0; }
.agent-controls__panel.is-current { display: block; animation: agent-panel-in 240ms cubic-bezier(.2, .8, .2, 1) both; }
.agent-controls__panel-intro { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; margin-bottom: 9px; color: #89a1bd; font-size: 10px; }
.agent-controls__panel-intro strong { color: color-mix(in srgb, var(--agent-deep, #5c39a1) 76%, #294c76); font-size: 12px; }
.agent-controls__choice-grid { display: flex; flex-wrap: wrap; gap: 6px; max-height: 146px; overflow-y: auto; padding: 2px 3px 3px 0; }
.agent-controls__choice-grid--shapes .agent-control { min-width: 52px; }
.agent-controls__states { display: grid; max-height: 174px; gap: 7px; overflow-y: auto; padding-right: 3px; }
.agent-controls__line { display: flex; align-items: center; justify-content: flex-start; gap: 6px; min-height: 28px; }
.agent-controls__line--states { flex-wrap: wrap; }
.agent-controls__line--actions { flex-wrap: wrap; }
.agent-controls__label { min-width: 61px; color: #82a0c1; font: 9px var(--font-mono, monospace); letter-spacing: .08em; }
.agent-control { min-height: 30px; padding: 0 10px; border: 1px solid rgba(115,165,205,.2); border-radius: 999px; color: #5f7da1; background: rgba(255,255,255,.38); cursor: pointer; font: inherit; font-size: 10px; transition: border-color 180ms ease, color 180ms ease, background-color 180ms ease, transform 180ms ease, box-shadow 180ms ease; }
.agent-control:hover, .agent-control[aria-pressed='true'] { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 55%, white); color: color-mix(in srgb, var(--agent-deep, #5c39a1) 80%, #173963); background: color-mix(in srgb, var(--agent-light, #f1e8ff) 60%, white); transform: translateY(-1px); }
.agent-control:active { transform: translateY(0); }
.agent-control--featured { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 24%, white); background: color-mix(in srgb, var(--agent-light, #f1e8ff) 38%, white); }
.agent-control--voice { display: inline-flex; align-items: center; gap: 5px; margin-left: auto; }
.agent-control--voice svg { width: 13px; height: 13px; }
.agent-control--voice.is-listening { border-color: var(--agent-main, #a97efe); color: var(--agent-deep, #5c39a1); background: color-mix(in srgb, var(--agent-light, #f1e8ff) 70%, white); box-shadow: 0 0 0 4px color-mix(in srgb, var(--agent-glow, #cdb6ff) 18%, transparent); }
.agent-controls__hint { min-width: 0; margin: 9px 0 0; overflow: hidden; color: #88a1bd; font-size: 9px; line-height: 1.4; text-overflow: ellipsis; white-space: nowrap; }
.agent-controls__hint--block { padding-top: 8px; border-top: 1px solid rgba(111,151,190,.12); }
.agent-controls__color-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 7px; }
.agent-color { min-width: 0; height: 38px; display: flex; align-items: center; gap: 7px; padding: 0 8px; border: 1px solid rgba(115,165,205,.16); border-radius: 12px; color: #6381a4; background: color-mix(in srgb, var(--swatch) 7%, white); box-shadow: 0 3px 8px rgba(60, 111, 166, .08), inset 0 1px 0 rgba(255,255,255,.82); cursor: pointer; font: inherit; font-size: 10px; transition: border-color 180ms ease, color 180ms ease, background-color 180ms ease, transform 180ms ease, box-shadow 180ms ease; }
.agent-color::before { content: ''; width: 15px; height: 15px; flex: 0 0 auto; border: 2px solid rgba(255,255,255,.84); border-radius: 50%; background: linear-gradient(145deg, var(--swatch), var(--swatch-deep)); box-shadow: 0 2px 6px color-mix(in srgb, var(--swatch-deep) 22%, transparent); }
.agent-color span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.agent-color:hover, .agent-color[aria-pressed='true'] { border-color: color-mix(in srgb, var(--swatch) 58%, white); color: color-mix(in srgb, var(--swatch-deep) 78%, #294c76); background: color-mix(in srgb, var(--swatch) 14%, white); box-shadow: 0 5px 12px color-mix(in srgb, var(--swatch-deep) 13%, transparent), inset 0 1px 0 rgba(255,255,255,.92); transform: translateY(-1px); }
.agent-color[aria-pressed='true']::before { box-shadow: 0 0 0 3px color-mix(in srgb, var(--swatch) 18%, transparent), 0 2px 8px color-mix(in srgb, var(--swatch-deep) 28%, transparent); }
.agent-control:focus-visible, .agent-color:focus-visible { outline: 3px solid color-mix(in srgb, var(--agent-main, #a97efe) 48%, white); outline-offset: 3px; }
.agent-controls__close:focus-visible, .agent-controls__tab:focus-visible { outline: 3px solid color-mix(in srgb, var(--agent-main, #a97efe) 48%, white); outline-offset: 2px; }
.agent-constellation.is-controls-open .agent-stage__status { opacity: 0; transform: translateY(-4px); }
:global(.landing-view.is-theme-dark) .agent-controls { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 42%, #294768); background: linear-gradient(145deg, rgba(15, 30, 57, .94), color-mix(in srgb, var(--agent-deep, #5c39a1) 22%, rgba(7, 18, 36, .94))); box-shadow: 0 28px 62px rgba(0, 0, 0, .34), inset 0 1px 0 rgba(255,255,255,.14), inset 0 -1px 0 rgba(109,189,255,.1); }
:global(.landing-view.is-theme-dark) .agent-controls::before { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 35%, #294768); background: rgba(17, 38, 67, .94); }
:global(.landing-view.is-theme-dark) .agent-controls__eyebrow { color: color-mix(in srgb, var(--agent-glow, #cdb6ff) 76%, #a9c5e8); }
:global(.landing-view.is-theme-dark) .agent-controls__head strong { color: #eef5ff; }
:global(.landing-view.is-theme-dark) .agent-controls__summary { border-color: rgba(144,190,236,.22); color: #d2e2f6; background: rgba(6, 18, 37, .48); }
:global(.landing-view.is-theme-dark) .agent-controls__close { border-color: rgba(144,190,236,.24); color: #b9cde6; background: rgba(8, 25, 48, .58); }
:global(.landing-view.is-theme-dark) .agent-controls__close:hover { color: #fff; background: rgba(30, 67, 107, .8); }
:global(.landing-view.is-theme-dark) .agent-controls__tabs { border-color: rgba(144,190,236,.16); background: rgba(2, 11, 24, .3); }
:global(.landing-view.is-theme-dark) .agent-controls__tab { color: #9db5d2; }
:global(.landing-view.is-theme-dark) .agent-controls__tab small { color: #718cab; }
:global(.landing-view.is-theme-dark) .agent-controls__tab:hover { color: #eef5ff; background: rgba(34, 76, 119, .42); }
:global(.landing-view.is-theme-dark) .agent-controls__tab.is-active { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 52%, #547ca6); color: #fff; background: color-mix(in srgb, var(--agent-deep, #5c39a1) 54%, #193758); box-shadow: 0 5px 14px rgba(0,0,0,.2), inset 0 1px 0 rgba(255,255,255,.14); }
:global(.landing-view.is-theme-dark) .agent-controls__tab.is-active small { color: color-mix(in srgb, var(--agent-glow, #cdb6ff) 82%, #a9c5e8); }
:global(.landing-view.is-theme-dark) .agent-controls__panel-intro { color: #88a7c9; }
:global(.landing-view.is-theme-dark) .agent-controls__panel-intro strong { color: #f0f6ff; }
:global(.landing-view.is-theme-dark) .agent-controls__label { color: #87a6c8; }
:global(.landing-view.is-theme-dark) .agent-control { border-color: rgba(144,190,236,.18); color: #afc6df; background: rgba(13, 35, 63, .64); }
:global(.landing-view.is-theme-dark) .agent-control:hover, :global(.landing-view.is-theme-dark) .agent-control[aria-pressed='true'] { color: #fff; background: color-mix(in srgb, var(--agent-deep, #5c39a1) 44%, #163452); }
:global(.landing-view.is-theme-dark) .agent-control--featured { border-color: color-mix(in srgb, var(--agent-main, #a97efe) 45%, #3d628b); background: color-mix(in srgb, var(--agent-deep, #5c39a1) 22%, #102b4b); }
:global(.landing-view.is-theme-dark) .agent-controls__hint { color: #87a6c8; }
:global(.landing-view.is-theme-dark) .agent-controls__hint--block { border-color: rgba(144,190,236,.16); }
:global(.landing-view.is-theme-dark) .agent-color { border-color: rgba(144,190,236,.2); color: #b6cbe2; background: color-mix(in srgb, var(--swatch) 12%, #0b1d35); box-shadow: 0 4px 10px rgba(0,0,0,.18), inset 0 1px 0 rgba(255,255,255,.12); }
:global(.landing-view.is-theme-dark) .agent-color:hover, :global(.landing-view.is-theme-dark) .agent-color[aria-pressed='true'] { color: #fff; background: color-mix(in srgb, var(--swatch) 23%, #0c2440); }
:global(html[data-color-scheme='codex-dark'], html[data-color-scheme='one-dark-modern'] .agent-controls__head strong) { color: #eef5ff !important; }
:global(html[data-color-scheme='codex-dark'], html[data-color-scheme='one-dark-modern'] .agent-controls__eyebrow) { color: #b9cdef; }
:global(html[data-color-scheme='codex-dark'], html[data-color-scheme='one-dark-modern'] .agent-controls__panel-intro strong) { color: #f0f6ff; }
.agent-conversation { position: absolute; right: 6%; bottom: 7%; z-index: 5; width: min(90%, 360px); padding: 13px 16px 14px; border: 1px solid color-mix(in srgb, var(--agent-main, #a97efe) 24%, white); border-radius: 16px; color: #36577f; background: linear-gradient(145deg, rgba(255,255,255,.7), rgba(224,241,255,.42)); box-shadow: 0 18px 34px rgba(55,108,174,.14), inset 0 1px 0 rgba(255,255,255,.9); backdrop-filter: blur(18px) saturate(135%); animation: conversation-in 420ms cubic-bezier(.2, .8, .2, 1) both; }
.agent-conversation::before { content: ''; position: absolute; top: -5px; right: 28px; width: 10px; height: 10px; border-top: 1px solid color-mix(in srgb, var(--agent-main, #a97efe) 24%, white); border-left: 1px solid color-mix(in srgb, var(--agent-main, #a97efe) 24%, white); background: rgba(246,252,255,.72); transform: rotate(45deg); }
.agent-conversation__label { display: block; color: color-mix(in srgb, var(--agent-deep, #5c39a1) 76%, #6d8ab1); font: 9px var(--font-mono, monospace); letter-spacing: .16em; }
.agent-conversation p { margin: 7px 0 0; color: #55749b; font-size: 12px; line-height: 1.6; }
@keyframes agent-halo { 0%, 100% { opacity: .62; transform: scale(.96); } 50% { opacity: .9; transform: scale(1.04); } }
@keyframes conversation-in { from { opacity: 0; transform: translate3d(0, 10px, 0) scale(.96); } to { opacity: 1; transform: translate3d(0, 0, 0) scale(1); } }
@keyframes agent-panel-in { from { opacity: 0; transform: translateY(5px); } to { opacity: 1; transform: translateY(0); } }
@keyframes orbit-light { 0%, 100% { transform: translate(0, 0) scale(.85); opacity: .55; } 50% { transform: translate(-12px, 9px) scale(1.18); opacity: 1; } }
@keyframes awake-pulse { 0%, 100% { transform: scale(.8); box-shadow: 0 0 8px var(--agent-glow, #cdb6ff); } 50% { transform: scale(1.35); box-shadow: 0 0 16px var(--agent-glow, #cdb6ff); } }
@media (max-width: 760px) {
  .agent-constellation { width: min(100%, 560px); min-width: 0; height: min(118vw, 650px); min-height: 430px; margin-left: 0; transform: none; }
  .agent-avatar-trigger { width: 68%; height: 68%; }
  .agent-constellation.is-controls-open .agent-stage { padding-bottom: clamp(220px, 28vh, 280px); }
  .agent-constellation.is-controls-open .agent-avatar-trigger { width: 32%; height: 32%; transform: translate(50%, -45px); }
  .agent-controls { bottom: 1%; width: min(100%, 520px); padding: 12px; }
  .agent-controls__summary { max-width: 112px; overflow: hidden; text-overflow: ellipsis; }
  .agent-controls__color-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .agent-controls__line { flex-wrap: wrap; }
  .agent-controls__label { min-width: 42px; }
  .agent-controls__hint { text-align: left; }
}
@media (prefers-reduced-motion: reduce) {
  .agent-stage__halo, .agent-stage__orbit-light, .agent-stage--awake .agent-stage__status-dot { animation: none; }
  .agent-avatar-trigger, .agent-controls, .agent-controls__panel.is-current, .agent-stage__prompt { transition: none; animation: none; }
}
</style>
