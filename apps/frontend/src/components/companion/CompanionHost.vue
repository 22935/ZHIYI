<template>
  <Teleport to="body">
    <div
      class="companion-root"
      :class="{ 'is-expanded': expanded }"
      data-testid="companion-root"
    >
      <section v-if="expanded" class="companion-panel" aria-label="虚拟伙伴面板">
        <header class="companion-header">
          <div>
            <span class="companion-name">知宝</span>
            <span class="companion-state" data-testid="companion-state">{{ stateLabel }}</span>
          </div>
          <button type="button" data-testid="companion-collapse" @click="toggleExpanded">收起</button>
        </header>

        <CompanionDialogue
          :messages="messages"
          :pending="pending"
          :card="card"
          @send="send"
          @dismiss-card="card = null"
        />

        <footer class="companion-footer">
          <label class="companion-toggle">
            <input v-model="streamEnabled" type="checkbox" data-testid="companion-model-toggle" @change="onModelToggle" />
            模型回复
          </label>
          <select v-model="skinId" data-testid="companion-skin" aria-label="切换形象" @change="onSkinChange">
            <option v-for="skin in skins" :key="skin.id" :value="skin.id">{{ skin.label }}</option>
          </select>
        </footer>
      </section>

      <div
        ref="stageRef"
        class="companion-avatar"
        data-testid="companion-avatar"
        role="button"
        tabindex="0"
        :aria-label="expanded ? '收起虚拟伙伴' : '展开虚拟伙伴'"
        :aria-expanded="expanded"
        @click="toggleExpanded"
        @keydown.enter="toggleExpanded"
      ></div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import CompanionDialogue from './CompanionDialogue.vue'
import {
  IdleFallback, ProactivityQueue, STATE_LABEL, resolveState, stateFromRuntimeEvent
} from '@/features/companion/companionState'
import { CompanionService, createDefaultPorts } from '@/features/companion/companionService'
import { createRenderer } from '@/features/companion/renderers'
import { COMPANION_SKIN_STORAGE_KEY, defaultSkinRegistry } from '@/features/companion/skins'
import type { AvatarRenderer, CompanionMessage, CompanionState, TaskIntentCard } from '@/features/companion/types'

const EXPANDED_KEY = 'companion.expanded.v1'

const readFlag = (key: string): boolean => {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}
const writeFlag = (key: string, value: boolean): void => {
  try { localStorage.setItem(key, value ? '1' : '0') } catch { /* storage is optional */ }
}
const readSkinId = (): string => {
  try { return localStorage.getItem(COMPANION_SKIN_STORAGE_KEY) || 'companion-static' } catch { return 'companion-static' }
}

const stageRef = ref<HTMLElement | null>(null)
const expanded = ref(readFlag(EXPANDED_KEY))
const skinId = ref(readSkinId())
const streamEnabled = ref(false)
const state = ref<CompanionState>('idle')
const messages = ref<CompanionMessage[]>([])
const pending = ref(false)
const card = ref<TaskIntentCard | null>(null)

const skins = defaultSkinRegistry.list()
const stateLabel = computed(() => STATE_LABEL[state.value])
const idleFallback = new IdleFallback(5000)
const queue = new ProactivityQueue(4000)

let renderer: AvatarRenderer | null = null
let service = new CompanionService(createDefaultPorts())
let abort: AbortController | null = null
let disposed = false
let messageSeq = 0

const pushMessage = (role: CompanionMessage['role'], content: string): void => {
  messages.value = [...messages.value, {
    id: `companion-${++messageSeq}`,
    role,
    content,
    createdAt: Date.now()
  }]
}

const applyState = (next: CompanionState): void => {
  state.value = resolveState(state.value, next)
  renderer?.setState(state.value)
  idleFallback.schedule(() => {
    if (disposed) return
    state.value = 'idle'
    renderer?.setState('idle')
  })
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
  if (notice) pushMessage('companion', notice.text)
}

const applySkin = async (id: string): Promise<void> => {
  if (!stageRef.value || disposed) return
  renderer?.destroy()
  renderer = null
  const skin = defaultSkinRegistry.resolve(id)
  const next = createRenderer(skin)
  try {
    await next.mount(stageRef.value, skin)
    if (disposed) { next.destroy(); return }
    renderer = next
    renderer.setState(state.value)
    if (skin.id !== skinId.value) skinId.value = skin.id
    try { localStorage.setItem(COMPANION_SKIN_STORAGE_KEY, skin.id) } catch { /* optional */ }
  } catch {
    next.destroy()
    const fallback = defaultSkinRegistry.resolve(null)
    skinId.value = fallback.id
    const plain = createRenderer(fallback)
    plain.mount(stageRef.value, fallback)
    renderer = plain
    renderer.setState(state.value)
  }
}

const toggleExpanded = (): void => {
  expanded.value = !expanded.value
  writeFlag(EXPANDED_KEY, expanded.value)
  if (expanded.value) applyState('listening')
}

const onSkinChange = (): void => { void applySkin(skinId.value) }

const onModelToggle = async (): Promise<void> => {
  if (!streamEnabled.value) {
    service = new CompanionService(createDefaultPorts())
    pushMessage('companion', '已切回本地回复，不会发起模型请求。')
    return
  }
  try {
    const { StreamChatPort } = await import('@/features/companion/adapters/chatStream')
    if (disposed || !streamEnabled.value) return
    const ports = createDefaultPorts()
    ports.chat = new StreamChatPort()
    service = new CompanionService(ports)
    pushMessage('companion', '已切换到模型回复，我会复用现有对话流回答你。')
  } catch {
    streamEnabled.value = false
    pushMessage('companion', '模型通道暂时不可用，先继续用本地回复陪你。')
  }
}

const send = async (text: string): Promise<void> => {
  const value = text.trim()
  if (!value || pending.value) return
  pushMessage('user', value)
  pending.value = true
  applyState('thinking')
  abort?.abort()
  const controller = new AbortController()
  abort = controller
  try {
    const turn = await service.handle(
      value,
      { messages: messages.value, progress: null, personaName: '知宝' },
      controller.signal
    )
    if (disposed) return
    pushMessage('companion', turn.reply)
    card.value = turn.card
    applyState(turn.state)
  } catch {
    if (disposed) return
    pushMessage('companion', '刚才没能拿到回复，稍后再问我一次吧。')
    applyState('error')
  } finally {
    pending.value = false
  }
}

onMounted(() => {
  window.addEventListener('companion:run-event', handleRuntimeEvent)
  void applySkin(skinId.value)
})

onBeforeUnmount(() => {
  disposed = true
  window.removeEventListener('companion:run-event', handleRuntimeEvent)
  idleFallback.clear()
  queue.reset()
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
  width: 64px; height: 64px; box-sizing: border-box; cursor: pointer;
  border-radius: 50%; overflow: hidden;
  background: var(--bg-card); border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
  transition: width 180ms ease, height 180ms ease;
}
.companion-root.is-expanded .companion-avatar { width: 76px; height: 76px; }
.companion-panel {
  width: min(320px, calc(100vw - 48px)); box-sizing: border-box; padding: 10px;
  display: flex; flex-direction: column; gap: 10px;
  background: var(--bg-glass, var(--bg-card)); color: var(--text-primary);
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 12px;
}
.companion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.companion-name { font-size: 13px; font-weight: 500; margin-right: 8px; }
.companion-state { font-size: 11px; color: var(--text-muted, var(--text-secondary)); }
.companion-header button, .companion-footer select {
  font: inherit; font-size: 12px; padding: 3px 7px; cursor: pointer;
  color: var(--text-regular, var(--text-primary)); background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
}
.companion-footer { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.companion-toggle { display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-secondary); cursor: pointer; }
@media (prefers-reduced-motion: reduce) { .companion-avatar { transition: none; } }
</style>
