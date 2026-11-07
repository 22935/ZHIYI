<template>
  <section
    v-show="terminalVisible"
    class="desktop-terminal"
    :class="{ 'is-compact': height < 240 }"
    :style="{ height: `${height}px` }"
    aria-label="内置终端"
  >
    <div
      class="desktop-terminal__resize"
      role="separator"
      aria-label="调整终端高度"
      aria-orientation="horizontal"
      :aria-valuemin="160"
      :aria-valuemax="maxHeight()"
      :aria-valuenow="height"
      tabindex="0"
      @pointerdown="beginResize"
      @keydown="resizeKey"
      @dblclick="setHeight(280)"
    >
      <span class="desktop-terminal__grip" aria-hidden="true"></span>
    </div>
    <header class="desktop-terminal__header">
      <div class="desktop-terminal__brand">
        <span class="desktop-terminal__brand-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="m4 17 6-6-6-6" />
            <path d="M12 19h8" />
          </svg>
        </span>
        <span class="desktop-terminal__heading">终端</span>
        <span v-if="sessions.length > 1" class="desktop-terminal__count" :title="`${sessions.length} 个终端会话`">{{ sessions.length }}</span>
      </div>
      <nav class="desktop-terminal__tabs" role="tablist" aria-label="终端会话">
        <div v-for="(session, index) in sessions" :key="session.id" class="desktop-terminal__tab" :class="{ active: terminalActiveId === session.id }">
          <button
            role="tab"
            :aria-selected="terminalActiveId === session.id"
            :title="[session.profileName, session.cwd].filter(Boolean).join(' · ')"
            @click="activate(session.id)"
          >
            <span class="desktop-terminal__tab-label">{{ session.profileName }}</span>
            <span v-if="index > 0" class="desktop-terminal__number">· {{ index + 1 }}</span>
            <span v-if="session.state === 'exited'" class="desktop-terminal__exit-dot" aria-label="已退出" title="会话已退出"></span>
          </button>
          <button class="desktop-terminal__tab-close" :aria-label="`关闭终端 ${index + 1}`" title="终止并关闭此终端" @click="closeSession(session.id)">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>
      </nav>
      <div class="desktop-terminal__actions">
        <label class="desktop-terminal__profile" title="新建终端使用的 Shell">
          <select v-model="profileId" aria-label="选择终端 Shell" :title="profiles.find(profile => profile.id === profileId)?.name || '选择终端 Shell'" :disabled="busy || !profiles.length">
            <option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option>
          </select>
          <svg class="desktop-terminal__profile-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m6 9 6 6 6-6" />
          </svg>
        </label>
        <button :disabled="busy || !profiles.length" aria-label="新建终端" title="新建终端（当前 Shell）" @click="newTerminal()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
        <button :disabled="busy || !profiles.length" aria-label="选择目录并新建终端" title="选择目录并新建终端" @click="chooseDirectory">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z" />
          </svg>
        </button>
        <button :disabled="!terminalActiveId" aria-label="清空终端显示" title="清空显示（保留 Shell 会话）" @click="terminal?.clear()">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m7 21-4.3-4.3c-1-1-1-2.5 0-3.4l9.6-9.6c1-1 2.5-1 3.4 0l5.6 5.6c1 1 1 2.5 0 3.4L13 21" />
            <path d="M22 21H7" />
            <path d="m5 11 9 9" />
          </svg>
        </button>
        <span class="desktop-terminal__divider" aria-hidden="true"></span>
        <button aria-label="关闭终端面板" title="收起面板，终端继续运行 · Ctrl+`" @click="terminalVisible = false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
            <path d="M5 12h14" />
          </svg>
        </button>
      </div>
    </header>
    <div v-if="error" class="desktop-terminal__error" role="alert">
      <span>{{ error }}</span><button :disabled="busy" @click="refresh">重试</button>
    </div>
    <div ref="container" class="desktop-terminal__canvas" :class="{ 'is-empty': !terminalActiveId }"></div>
    <div v-if="!terminalActiveId && !error" class="desktop-terminal__empty">
      <span class="desktop-terminal__empty-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="4" width="18" height="16" rx="2.5" />
          <path d="m7 9 3 3-3 3" />
          <path d="M13 16h4" />
        </svg>
      </span>
      <strong>{{ busy ? '正在连接本地终端…' : '在工作区中开始一个终端会话' }}</strong>
      <p v-if="!busy">为不同 Shell 保留独立标签，随时切回。</p>
      <button v-if="!busy && profiles.length" @click="newTerminal()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
          <path d="M12 5v14M5 12h14" />
        </svg>
        新建终端
      </button>
      <span v-if="!busy" class="desktop-terminal__empty-hint"><kbd>Ctrl</kbd><kbd>`</kbd> 收起或唤回</span>
    </div>
    <footer class="desktop-terminal__status">
      <span class="desktop-terminal__status-dot" :class="{ running: activeSession?.state === 'running' }"></span>
      <span>{{ activeSession?.state === 'exited' ? `已退出 · ${activeSession.exitCode ?? '—'}` : activeSession ? '本机终端' : '本地会话' }}</span>
      <span class="desktop-terminal__cwd" :title="`启动目录：${activeSession?.cwd || ''}`">{{ activeSession?.cwd || '当前工作区' }}</span>
      <span class="desktop-terminal__shortcut" aria-hidden="true"><kbd>Ctrl</kbd><kbd>`</kbd></span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { localFetch } from '@/platform/api'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Terminal } from '@xterm/xterm'
import type { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { getElectronBridge, type TerminalBridge, type TerminalProfile, type TerminalSession } from '@/platform/electron/bridge'
import { apiUrl } from '@/platform'
import { terminalVisible, terminalActiveId, toggleDesktopTerminal } from '@/composables/useDesktopTerminal'
import { commands } from '@/workbench/core/commands'

const container = ref<HTMLElement | null>(null)
const sessions = ref<TerminalSession[]>([])
const profiles = ref<TerminalProfile[]>([])
const profileId = ref('')
const busy = ref(false)
const error = ref('')
const height = ref(280)
const activeSession = computed(() => sessions.value.find(session => session.id === terminalActiveId.value))
let terminal: Terminal | null = null
let fit: FitAddon | null = null
let renderedId: string | null = null
let generation = 0
let cursor = 0
let timer: ReturnType<typeof setTimeout> | undefined
let observer: ResizeObserver | undefined
let frame = 0
const inputQueues = new Map<string, Promise<void>>()
let finishResize: (() => void) | undefined

function bridge(): TerminalBridge {
  const value = getElectronBridge()?.terminal
  if (!value) throw new Error('终端桥接尚未加载，请通过桌面图标重新打开知弈')
  return value
}
function fail(cause: unknown) { error.value = cause instanceof Error ? cause.message.replace(/^Error invoking remote method '[^']+': Error: /, '') : '终端操作失败' }
function maxHeight() { return Math.max(160, Math.min(720, Math.floor(window.innerHeight * 0.7))) }
function setHeight(value: number) {
  height.value = Math.max(160, Math.min(maxHeight(), value))
  try { localStorage.setItem('zhiyi.terminal.height', String(height.value)) } catch { /* Optional layout persistence. */ }
}
function beginResize(event: PointerEvent) {
  if (event.button !== 0) return
  event.preventDefault()
  finishResize?.()
  const start = event.clientY, original = height.value
  const previous = document.body.style.cursor
  document.body.style.cursor = 'row-resize'
  const move = (current: PointerEvent) => setHeight(original + start - current.clientY)
  finishResize = () => {
    window.removeEventListener('pointermove', move); window.removeEventListener('pointerup', finish)
    document.body.style.cursor = previous; finishResize = undefined
  }
  const finish = () => finishResize?.()
  window.addEventListener('pointermove', move); window.addEventListener('pointerup', finish, { once: true })
}
function resizeKey(event: KeyboardEvent) {
  if (!['ArrowUp', 'ArrowDown', 'Home'].includes(event.key)) return
  event.preventDefault(); setHeight(event.key === 'Home' ? 280 : height.value + (event.key === 'ArrowUp' ? 20 : -20))
}
// Ctrl+` 走工作台命令表（见 onMounted 注册），xterm 仍需放行该组合，避免被终端吞掉。
let disposeToggleCommand: (() => void) | null = null
function fitTerminal() {
  cancelAnimationFrame(frame)
  frame = requestAnimationFrame(() => {
    if (!terminalVisible.value || !terminal || !fit || !renderedId || !container.value?.clientWidth) return
    fit.fit()
    const session = sessions.value.find(item => item.id === renderedId)
    if (session?.state === 'running' && (session.cols !== terminal.cols || session.rows !== terminal.rows)) {
      session.cols = terminal.cols; session.rows = terminal.rows
      const id = session.id
      void bridge().resize(id, terminal.cols, terminal.rows).catch(cause => { if (renderedId === id && !busy.value) fail(cause) })
    }
  })
}
async function poll(currentGeneration: number, id: string) {
  if (currentGeneration !== generation || !terminalVisible.value || renderedId !== id) return
  try {
    const result = await bridge().read(id, cursor)
    if (currentGeneration !== generation || renderedId !== id || !terminal) return
    if (result.truncated) terminal.write('\r\n\x1b[33m[较早的输出已截断]\x1b[0m\r\n')
    for (const chunk of result.chunks) terminal.write(chunk.data)
    cursor = result.cursor
    sessions.value = sessions.value.map(session => session.id === id ? result.session : session)
    if (result.session.state === 'running' && terminalVisible.value) timer = setTimeout(() => void poll(currentGeneration, id), 180)
  } catch (cause) { if (currentGeneration === generation) fail(cause) }
}
async function renderSession(id: string | null) {
  const currentGeneration = ++generation
  clearTimeout(timer)
  if (!terminalVisible.value) return
  await nextTick()
  if (currentGeneration !== generation || !container.value) return
  if (!id) { terminal?.dispose(); terminal = null; fit = null; renderedId = null; cursor = 0; container.value.replaceChildren(); return }
  if (renderedId !== id || !terminal) {
    terminal?.dispose(); terminal = null; fit = null; renderedId = null; cursor = 0
    const [{ Terminal: TerminalClass }, { FitAddon: FitClass }] = await Promise.all([import('@xterm/xterm'), import('@xterm/addon-fit')])
    if (currentGeneration !== generation || !container.value) return
    container.value.replaceChildren()
    const instance = new TerminalClass({ cursorBlink: true, fontSize: 13, lineHeight: 1.24, scrollback: 5000,
      fontFamily: 'Cascadia Code, Consolas, Microsoft YaHei, monospace', allowProposedApi: false, cursorStyle: 'bar',
      theme: { background: '#161619', foreground: '#d7dae0', cursor: '#e8e8ee', cursorAccent: '#161619', selectionBackground: '#334051',
        black: '#27272a', red: '#f07178', green: '#8bcb78', yellow: '#d9b86c', blue: '#82aaff', magenta: '#c099e8', cyan: '#7cc8cf', white: '#d7dae0' } })
    const addon = new FitClass(); instance.loadAddon(addon); instance.open(container.value)
    instance.onData(data => {
      if (terminal !== instance || renderedId !== id) return
      const queued = inputQueues.get(id) || Promise.resolve()
      inputQueues.set(id, queued.then(async () => {
        if (sessions.value.some(session => session.id === id)) await bridge().write(id, data)
      }).catch(cause => { if (renderedId === id && !busy.value) fail(cause) }))
    })
    instance.attachCustomKeyEventHandler(event => !((event.ctrlKey || event.metaKey) && event.code === 'Backquote'))
    terminal = instance; fit = addon; renderedId = id
  }
  terminal.focus(); fitTerminal(); void poll(currentGeneration, id)
}
function activate(id: string) { terminalActiveId.value = id; terminal?.focus() }
async function selectedDirectory(): Promise<string | undefined> {
  try {

    const response = await localFetch(apiUrl('/api/agentos/v2/workspaces/current'), { signal: AbortSignal.timeout(2000) })
    if (response.ok) { const data = await response.json(); if (data.workspaceRoot) return data.workspaceRoot }
    return (await getElectronBridge()?.workspace?.current())?.root
  } catch { return undefined }
}
async function newTerminal(directory?: string) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try {
    const session = await bridge().create({ profileId: profileId.value || undefined, cwd: directory || await selectedDirectory(), cols: 100, rows: 20 })
    sessions.value.push(session); terminalActiveId.value = session.id
  } catch (cause) { fail(cause) } finally { busy.value = false }
}
async function chooseDirectory() {
  try { const selected = await getElectronBridge()?.dialog.openDirectory(); if (selected) await newTerminal(selected) } catch (cause) { fail(cause) }
}
async function closeSession(id: string) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  if (terminalActiveId.value === id) { ++generation; clearTimeout(timer) }
  try {
    await bridge().close(id)
    inputQueues.delete(id)
    sessions.value = sessions.value.filter(session => session.id !== id)
    if (terminalActiveId.value === id) {
      terminalActiveId.value = sessions.value[sessions.value.length - 1]?.id || null
      if (!terminalActiveId.value) { ++generation; clearTimeout(timer); terminal?.dispose(); terminal = null; fit = null; renderedId = null }
    }
  } catch (cause) { fail(cause) } finally { busy.value = false }
}
async function refresh() {
  if (busy.value) return
  busy.value = true; error.value = ''
  ++generation; clearTimeout(timer)
  terminal?.dispose(); terminal = null; fit = null; renderedId = null; cursor = 0
  try {
    const [available, existing] = await Promise.all([bridge().profiles(), bridge().list()])
    profiles.value = available.profiles; sessions.value = existing.sessions
    if (!profiles.value.some(profile => profile.id === profileId.value)) profileId.value = profiles.value[0]?.id || ''
    if (!sessions.value.some(session => session.id === terminalActiveId.value)) terminalActiveId.value = sessions.value[0]?.id || null
  } catch (cause) { fail(cause) } finally { busy.value = false }
  if (!error.value && !sessions.value.length && profiles.value.length) await newTerminal()
  else if (!error.value) await renderSession(terminalActiveId.value)
}
watch(terminalActiveId, id => { if (terminalVisible.value) void renderSession(id) })
watch(terminalVisible, visible => {
  if (visible) void refresh()
  else { ++generation; clearTimeout(timer) }
})
onMounted(() => {
  try { const saved = Number(localStorage.getItem('zhiyi.terminal.height')); if (saved >= 160) setHeight(saved) } catch { /* Default height. */ }
  disposeToggleCommand = commands.register({
    id: 'terminal.toggle',
    title: '终端面板',
    category: '桌面',
    order: 70,
    keys: ['mod+backquote'],
    // 焦点本来就在终端里也必须能收起面板，因此不让位给 shell。
    terminalSafe: true,
    editableSafe: true,
    run: toggleDesktopTerminal
  })
  if (typeof ResizeObserver !== 'undefined') {
    observer = new ResizeObserver(fitTerminal)
    if (container.value) observer.observe(container.value)
  }
  if (terminalVisible.value) void refresh()
})
onBeforeUnmount(() => {
  ++generation; clearTimeout(timer); cancelAnimationFrame(frame); finishResize?.(); observer?.disconnect()
  terminal?.dispose(); disposeToggleCommand?.(); disposeToggleCommand = null
})
</script>

<style scoped>
.desktop-terminal {
  --term-bg:#161619;
  --term-line:rgba(255,255,255,.08);
  --term-line-soft:rgba(255,255,255,.045);
  --term-text:#d7dae0;
  --term-muted:#8b8b96;
  --term-accent:var(--sem-running,#6ea8fe);
  position:relative;
  flex:0 0 auto;
  min-height:160px;
  min-width:0;
  display:flex;
  flex-direction:column;
  overflow:visible;
  background:var(--term-bg);
  color:var(--term-text);
  border-top:1px solid var(--term-line);
  box-shadow:0 -14px 36px rgba(0,0,0,.2),inset 0 1px 0 rgba(255,255,255,.035);
  font-family:var(--font-sans,system-ui,sans-serif);
}
.desktop-terminal__resize { position:absolute; top:-5px; left:0; right:0; height:9px; z-index:5; display:flex; justify-content:center; cursor:row-resize; touch-action:none; }
.desktop-terminal__grip { width:28px; height:2px; margin-top:3px; border-radius:999px; background:rgba(255,255,255,.12); opacity:0; transition:opacity 160ms var(--ease-out,ease),width 160ms var(--ease-out,ease),background-color 160ms var(--ease-out,ease); }
.desktop-terminal:hover .desktop-terminal__grip { opacity:.35; }
.desktop-terminal__resize:hover .desktop-terminal__grip,
.desktop-terminal__resize:focus-visible .desktop-terminal__grip { width:36px; opacity:.9; background:rgba(255,255,255,.3); }
.desktop-terminal__resize:focus-visible .desktop-terminal__grip { background:var(--term-accent); }
.desktop-terminal__resize:focus-visible { outline:none; }
.desktop-terminal__header { position:relative; z-index:2; display:flex; flex:0 0 32px; min-width:0; align-items:center; gap:8px; padding:0 6px 0 10px; background:linear-gradient(180deg,#1c1c21 0%,#18181b 100%); border-bottom:1px solid var(--term-line-soft); }
.desktop-terminal__brand { display:flex; align-items:center; gap:6px; flex-shrink:0; min-width:0; height:18px; padding-right:9px; border-right:1px solid var(--term-line-soft); }
.desktop-terminal__brand-icon { display:grid; place-items:center; flex:0 0 18px; width:18px; height:18px; border-radius:5px; color:#aeb1bb; background:rgba(255,255,255,.045); border:1px solid rgba(255,255,255,.07); }
.desktop-terminal__brand-icon svg { width:11px; height:11px; }
.desktop-terminal__heading { flex-shrink:0; font-size:10.5px; font-weight:500; color:#b9b9c3; letter-spacing:.08em; white-space:nowrap; }
.desktop-terminal__count { display:inline-flex; align-items:center; justify-content:center; min-width:14px; height:14px; padding:0 3px; border-radius:999px; background:rgba(255,255,255,.05); color:#9d9da7; font:8px/1 var(--font-mono,Consolas,monospace); }
.desktop-terminal__tabs { display:flex; align-items:stretch; gap:1px; min-width:0; flex:1; overflow-x:auto; scrollbar-width:none; }
.desktop-terminal__tabs::-webkit-scrollbar { display:none; }
.desktop-terminal__tab { position:relative; display:flex; align-items:stretch; flex-shrink:0; }
.desktop-terminal__tab > button:first-child { position:relative; display:flex; align-items:center; gap:5px; padding:0 4px 0 9px; color:#7b7b86; font-size:10px; font-weight:500; letter-spacing:.08em; text-transform:uppercase; white-space:nowrap; transition:color 160ms var(--ease-out,ease); }
.desktop-terminal__tab:hover > button:first-child { color:#c5c5ce; }
.desktop-terminal__tab.active > button:first-child { color:#e8e8ee; }
.desktop-terminal__tab.active > button:first-child::after { content:''; position:absolute; left:9px; right:3px; bottom:0; height:1.5px; border-radius:1px; background:#dcdce2; opacity:.8; }
.desktop-terminal__tab-label { max-width:180px; overflow:hidden; text-overflow:ellipsis; }
.desktop-terminal__number { margin-left:-1px; color:#63636d; font:8px/1 var(--font-mono,Consolas,monospace); letter-spacing:0; }
.desktop-terminal__tab-close { display:grid; place-items:center; align-self:center; width:18px; height:18px; margin:0 2px 0 0; border-radius:3px; color:var(--term-muted); opacity:0; transition:opacity 140ms ease,background-color 140ms ease,color 140ms ease; }
.desktop-terminal__tab-close svg { width:8px; height:8px; }
.desktop-terminal__tab:hover .desktop-terminal__tab-close,
.desktop-terminal__tab.active .desktop-terminal__tab-close { opacity:.5; }
.desktop-terminal__tab-close:hover,.desktop-terminal__tab-close:focus-visible { opacity:1; background:rgba(255,255,255,.08); color:#ececf1; }
.desktop-terminal button { color:inherit; border:0; background:transparent; cursor:pointer; font:inherit; }
.desktop-terminal button:disabled { opacity:.3; cursor:default; }
.desktop-terminal button:focus-visible,.desktop-terminal select:focus-visible { outline:2px solid color-mix(in srgb,var(--term-accent) 55%,transparent); outline-offset:1px; }
.desktop-terminal__actions { display:flex; align-items:center; gap:1px; flex-shrink:0; margin-left:1px; }
.desktop-terminal__actions button { display:grid; place-items:center; width:22px; height:22px; border-radius:5px; color:#878792; transition:background-color 140ms ease,color 140ms ease; }
.desktop-terminal__actions button svg { width:12px; height:12px; }
.desktop-terminal__actions button:hover:not(:disabled) { background:rgba(255,255,255,.07); color:#e6e6eb; }
.desktop-terminal__actions button:active:not(:disabled) { background:rgba(255,255,255,.1); }
.desktop-terminal__profile { position:relative; display:flex; align-items:center; margin-right:2px; }
.desktop-terminal__profile select { appearance:none; -webkit-appearance:none; width:86px; height:20px; padding:0 17px 0 6px; border:1px solid transparent; border-radius:5px; background:transparent; color:#9696a1; font:9.5px var(--font-sans,system-ui,sans-serif); letter-spacing:.02em; text-overflow:ellipsis; cursor:pointer; outline:none; transition:background-color 140ms ease,border-color 140ms ease,color 140ms ease; }
.desktop-terminal__profile:hover select:not(:disabled),.desktop-terminal__profile select:focus-visible { background:rgba(255,255,255,.05); border-color:var(--term-line-soft); color:#dcdce2; }
.desktop-terminal__profile select:disabled { opacity:.45; cursor:default; }
.desktop-terminal__profile select option { background:#202024; color:#d4d4d8; }
.desktop-terminal__profile-chevron { position:absolute; right:5px; width:8px; height:8px; color:#6b6b75; pointer-events:none; }
.desktop-terminal__divider { width:1px; height:12px; margin:0 3px; background:var(--term-line-soft); }
.desktop-terminal__canvas { flex:1; min-height:0; min-width:0; padding:7px 8px 0 12px; overflow:hidden; background:var(--term-bg); }
.desktop-terminal__canvas :deep(.xterm) { height:100%; }
.desktop-terminal__canvas :deep(.xterm-viewport) { scrollbar-width:thin; scrollbar-color:rgba(255,255,255,.14) transparent; }
.desktop-terminal__canvas :deep(.xterm-viewport)::-webkit-scrollbar { width:9px; }
.desktop-terminal__canvas :deep(.xterm-viewport)::-webkit-scrollbar-thumb { background:rgba(255,255,255,.13); border:3px solid transparent; background-clip:padding-box; border-radius:999px; }
.desktop-terminal__canvas :deep(.xterm-viewport)::-webkit-scrollbar-thumb:hover { background:rgba(255,255,255,.24); border:3px solid transparent; background-clip:padding-box; }
.desktop-terminal__status { display:flex; align-items:center; gap:6px; height:22px; flex:0 0 22px; padding:0 9px 0 12px; color:#777781; background:rgba(0,0,0,.16); border-top:1px solid var(--term-line-soft); font:9.5px var(--font-sans,system-ui,sans-serif); }
.desktop-terminal__status-dot,.desktop-terminal__exit-dot { width:5px; height:5px; border-radius:50%; background:#5f5f69; flex-shrink:0; }
.desktop-terminal__status-dot { transition:background-color 200ms ease,box-shadow 200ms ease; }
.desktop-terminal__status-dot.running { background:#8bcb78; box-shadow:0 0 0 3px rgba(139,203,120,.1),0 0 9px rgba(139,203,120,.35); }
.desktop-terminal__cwd { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; margin-left:3px; padding-left:8px; border-left:1px solid var(--term-line-soft); color:#62626c; font:9.5px var(--font-mono,Consolas,monospace); }
.desktop-terminal__shortcut { display:flex; align-items:center; gap:3px; margin-left:auto; }
.desktop-terminal__shortcut kbd,.desktop-terminal__empty-hint kbd { display:inline-flex; align-items:center; justify-content:center; min-width:12px; height:13px; padding:0 3px; border:1px solid rgba(255,255,255,.07); border-radius:3px; background:rgba(255,255,255,.04); color:#82828c; font:8px/1 var(--font-mono,Consolas,monospace); }
.desktop-terminal__error { display:flex; align-items:center; justify-content:space-between; gap:10px; padding:7px 12px; background:color-mix(in srgb,var(--sem-failed,#e06c75) 11%,var(--term-bg)); border-bottom:1px solid color-mix(in srgb,var(--sem-failed,#e06c75) 22%,transparent); color:#e8b5ae; font-size:10.5px; }
.desktop-terminal__error button { padding:2px 0; color:#f0c4be; text-decoration:underline; text-underline-offset:2px; white-space:nowrap; }
.desktop-terminal__empty { position:absolute; inset:38px 10px 22px; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:6px; color:#777781; font-size:11.5px; text-align:center; pointer-events:none; }
.desktop-terminal__empty-icon { display:grid; place-items:center; width:36px; height:36px; margin-bottom:1px; border-radius:10px; color:#b0b0bb; background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,.02)); border:1px solid rgba(255,255,255,.08); box-shadow:0 10px 24px rgba(0,0,0,.24),inset 0 1px 0 rgba(255,255,255,.06); }
.desktop-terminal__empty-icon svg { width:18px; height:18px; }
.desktop-terminal__empty strong { font-size:12px; font-weight:500; color:#c9c9d2; letter-spacing:.01em; }
.desktop-terminal__empty p { margin:0; font-size:10.5px; color:#6d6d77; }
.desktop-terminal__empty button { pointer-events:auto; display:inline-flex; align-items:center; gap:5px; height:26px; margin-top:2px; padding:0 10px; border:1px solid rgba(255,255,255,.12); border-radius:5px; background:rgba(255,255,255,.05); color:#dedee4; font-size:10.5px; transition:background-color 140ms ease,border-color 140ms ease; }
.desktop-terminal__empty button svg { width:11px; height:11px; }
.desktop-terminal__empty button:hover { background:rgba(255,255,255,.09); border-color:rgba(255,255,255,.2); }
.desktop-terminal__empty-hint { display:flex; align-items:center; gap:3px; color:#5f5f69; font:8.5px var(--font-mono,Consolas,monospace); }
.desktop-terminal.is-compact .desktop-terminal__empty { inset:36px 10px 20px; gap:5px; }
.desktop-terminal.is-compact .desktop-terminal__empty p,
.desktop-terminal.is-compact .desktop-terminal__empty-hint { display:none; }
.desktop-terminal.is-compact .desktop-terminal__empty-icon { width:30px; height:30px; border-radius:8px; }
.desktop-terminal.is-compact .desktop-terminal__empty-icon svg { width:16px; height:16px; }
.desktop-terminal.is-compact .desktop-terminal__empty button { height:24px; margin-top:0; }
@media(max-width:760px) {
  .desktop-terminal__header { gap:6px; padding-left:8px; }
  .desktop-terminal__heading { display:none; }
  .desktop-terminal__brand { padding-right:8px; }
  .desktop-terminal__shortcut { display:none; }
}
@media(max-width:560px) {
  .desktop-terminal__profile { display:none; }
  .desktop-terminal__cwd { display:none; }
}
@media(prefers-reduced-motion:reduce) {
  .desktop-terminal__grip,.desktop-terminal__tab > button:first-child,.desktop-terminal__tab-close,.desktop-terminal__actions button,.desktop-terminal__profile select,.desktop-terminal__empty button,.desktop-terminal__status-dot { transition:none; }
}
</style>
