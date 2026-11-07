<template>
  <div
    v-if="platform.platform === 'desktop'"
    ref="rootEl"
    class="workspace-trust"
    :class="{
      'is-trusted': isTrusted,
      'is-pending': Boolean(candidate),
      'is-open': open,
      'is-loading': loading
    }"
    role="group"
    aria-label="本机工作区授权"
  >
    <button
      ref="triggerRef"
      type="button"
      class="workspace-trust__trigger"
      :aria-expanded="open"
      aria-haspopup="dialog"
      aria-controls="workspace-trust-panel"
      :title="triggerTitle"
      :disabled="loading"
      @click="toggle"
    >
      <svg class="workspace-trust__shield" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <path
          d="M8 1.6 13 3.6v4.1c0 3-2.1 5.6-5 6.7-2.9-1.1-5-3.7-5-6.7V3.6L8 1.6Z"
          fill="none"
          stroke="currentColor"
          stroke-width="1.25"
          stroke-linejoin="round"
        />
        <path
          v-if="isTrusted && !candidate"
          d="m5.4 7.7 1.7 1.7 3.5-3.5"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
      <span class="workspace-trust__label">{{ triggerLabel }}</span>
      <svg class="workspace-trust__chevron" viewBox="0 0 12 12" aria-hidden="true" focusable="false">
        <path
          d="m2.5 4.5 3.5 3 3.5-3"
          fill="none"
          stroke="currentColor"
          stroke-width="1.4"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </button>

    <Teleport to="body">
      <Transition name="workspace-pop">
        <section
          v-if="open"
          id="workspace-trust-panel"
          ref="panelRef"
          class="workspace-trust__panel"
          :style="panelStyle"
          role="dialog"
          aria-modal="false"
          aria-label="本机工作区授权"
          tabindex="-1"
        >
          <header class="workspace-trust__panel-head">
            <span class="workspace-trust__panel-title">
              <svg class="workspace-trust__shield" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                <path
                  d="M8 1.6 13 3.6v4.1c0 3-2.1 5.6-5 6.7-2.9-1.1-5-3.7-5-6.7V3.6L8 1.6Z"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.25"
                  stroke-linejoin="round"
                />
                <path
                  v-if="isTrusted && !candidate"
                  d="m5.4 7.7 1.7 1.7 3.5-3.5"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.5"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              本机工作区
            </span>
            <span
              class="workspace-trust__state"
              :class="{
                'is-trusted': isTrusted && !candidate,
                'is-pending': Boolean(candidate)
              }"
            >{{ stateLabel }}</span>
          </header>

          <div class="workspace-trust__path-block">
            <span class="workspace-trust__path-label">{{ pathLabel }}</span>
            <code class="workspace-trust__path" :title="displayPath">{{ displayPath }}</code>
          </div>

          <p v-if="candidate && isTrusted" class="workspace-trust__hint">
            信任新目录后，新 Run 将使用新工作区；当前授权在新 Run 前仍然有效。
          </p>

          <p class="workspace-trust__risk-copy">
            项目命令将以当前用户权限运行（非 OS 沙箱）；新 Run 冻结当前授权。
          </p>

          <p v-if="loadError" class="workspace-trust__load-error" role="alert">
            <span>{{ loadError }}</span>
            <button type="button" class="workspace-trust__retry" @click="load">重试</button>
          </p>

          <div class="workspace-trust__panel-actions">
            <button
              type="button"
              class="workspace-trust__action"
              :disabled="busy"
              title="选择一个本机项目目录"
              @click="choose"
            >选择工作区</button>
            <button
              type="button"
              class="workspace-trust__action is-primary"
              :disabled="busy || (isTrusted && !candidate)"
              :title="candidate
                ? `信任并授权 ${candidate}`
                : isTrusted
                  ? '当前工作区已信任'
                  : '选择并信任一个本机工作区'"
              @click="trust"
            >信任工作区</button>
          </div>

          <div v-if="candidate || (isTrusted && !candidate)" class="workspace-trust__panel-footer">
            <button
              v-if="candidate"
              type="button"
              class="workspace-trust__revoke"
              :disabled="busy"
              title="清除待信任目录，保留当前授权"
              @click="clearCandidate"
            >取消选择</button>
            <button
              v-else
              type="button"
              class="workspace-trust__revoke"
              :disabled="busy"
              @click="revoke"
            >撤销信任</button>
          </div>

          <p v-if="error" class="workspace-trust__error" role="alert">{{ error }}</p>
        </section>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { localFetch } from '@/platform/api'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { apiUrl, platform } from '@/platform'
import type { NativeWorkspaceState } from './workspaceState'

const emit = defineEmits<{ 'state-change': [state: NativeWorkspaceState] }>()

type Binding = {
  workspaceRoot: string
  workspaceId?: string
  grantId?: string
  revoked?: boolean
  risk?: string
}

const rootEl = ref<HTMLElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const panelStyle = ref<Record<string, string>>({})

const binding = ref<Binding | null>(null)
const candidate = ref('')
const loading = ref(true)
const busy = ref(false)
const error = ref('')
const loadError = ref('')
const open = ref(false)

const isTrusted = computed(() => Boolean(binding.value?.workspaceId && !binding.value.revoked))
const workspaceRoot = computed(() => binding.value?.workspaceRoot || '')
const workspaceName = computed(() => pathName(workspaceRoot.value))
const candidateName = computed(() => pathName(candidate.value))
const displayPath = computed(() => candidate.value || workspaceRoot.value || '尚未选择工作区')

const stateLabel = computed(() => {
  if (candidate.value) return '待信任'
  return isTrusted.value ? '已信任' : '未信任'
})

const pathLabel = computed(() => {
  if (candidate.value) return '待信任目录'
  return isTrusted.value ? '已授权目录' : '工作区目录'
})

const triggerLabel = computed(() => {
  if (loading.value) return '读取工作区…'
  if (loadError.value) return '工作区状态不可用'
  if (candidate.value) return `待信任 · ${candidateName.value}`
  if (isTrusted.value) return `已信任 · ${workspaceName.value}`
  return '工作区未信任'
})

const triggerTitle = computed(() => {
  if (loading.value) return '正在读取本机工作区授权状态'
  if (loadError.value) return `${loadError.value}\n点击查看并重试`
  const path = candidate.value || workspaceRoot.value
  if (path) return `工作区：${path}\n点击管理本机工作区授权`
  return '尚未信任本机工作区；点击选择并信任一个目录'
})

watch([binding, candidate, loading, busy, loadError, error], () => {
  emit('state-change', {
    loading: loading.value || busy.value,
    trusted: isTrusted.value && !candidate.value && !loadError.value,
    workspaceId: binding.value?.workspaceId || '', workspaceRoot: workspaceRoot.value,
    pendingPath: candidate.value, error: loadError.value || error.value
  })
}, { immediate: true })

const jsonHeaders = () => ({
  'Content-Type': 'application/json'
})

function pathName(path: string): string {
  const trimmed = path.replace(/[\\/]+$/, '')
  const parts = trimmed.split(/[\\/]/).filter(Boolean)
  return parts[parts.length - 1] || trimmed || '工作区'
}

function errorMessage(cause: unknown, fallback: string): string {
  return cause instanceof Error && cause.message ? cause.message : fallback
}

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const response = await localFetch(apiUrl('/api/agentos/v2/workspaces/current'), {
      headers: jsonHeaders()
    }).catch(() => null)
    if (!response) {
      loadError.value = '无法连接本地 Runtime'
      return
    }
    if (!response.ok) {
      loadError.value = response.status === 401
        ? '本机服务认证失败，无法读取工作区授权'
        : `读取工作区授权失败（${response.status}）`
      return
    }
    binding.value = await response.json()
  } catch (cause) {
    loadError.value = errorMessage(cause, '无法读取工作区授权状态')
  } finally {
    loading.value = false
    if (open.value) void nextTick(updatePosition)
  }
}

async function choose() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    const picked = await platform.openDirectory()
    if (picked) candidate.value = picked
  } catch (cause) {
    error.value = errorMessage(cause, '目录选择失败')
  } finally {
    busy.value = false
    if (open.value) void nextTick(updatePosition)
  }
}

function clearCandidate() {
  candidate.value = ''
  error.value = ''
  if (open.value) void nextTick(updatePosition)
}

async function trust() {
  if (busy.value || (isTrusted.value && !candidate.value)) return

  if (!candidate.value) {
    busy.value = true
    error.value = ''
    try {
      const picked = await platform.openDirectory()
      if (!picked) return
      candidate.value = picked
    } catch (cause) {
      error.value = errorMessage(cause, '目录选择失败')
      return
    } finally {
      busy.value = false
      if (open.value) void nextTick(updatePosition)
    }
  }

  busy.value = true
  error.value = ''
  try {
    const response = await localFetch(apiUrl('/api/agentos/v2/workspaces/select'), {
      method: 'POST',
      headers: jsonHeaders(),
      body: JSON.stringify({ path: candidate.value })
    })
    const data = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : '后端拒绝工作区授权')
    }
    binding.value = data
    loadError.value = ''
    candidate.value = ''
    window.dispatchEvent(new Event('workspace-authorization-changed'))
    close(true)
  } catch (cause) {
    error.value = errorMessage(cause, '信任工作区失败')
    if (open.value) void nextTick(updatePosition)
  } finally {
    busy.value = false
  }
}

async function revoke() {
  if (busy.value || !binding.value?.workspaceId) return
  busy.value = true
  error.value = ''
  try {
    const response = await localFetch(
      apiUrl(`/api/agentos/v2/workspaces/${encodeURIComponent(binding.value.workspaceId)}/revoke`),
      { method: 'POST', headers: jsonHeaders() }
    )
    if (!response.ok) throw new Error('撤销信任失败')
    binding.value = await response.json()
    loadError.value = ''
    candidate.value = ''
    window.dispatchEvent(new Event('workspace-authorization-changed'))
    close(true)
  } catch (cause) {
    error.value = errorMessage(cause, '撤销信任失败')
    if (open.value) void nextTick(updatePosition)
  } finally {
    busy.value = false
  }
}

function updatePosition() {
  if (!open.value) return
  const trigger = triggerRef.value
  if (!trigger) return
  const rect = trigger.getBoundingClientRect()
  const width = Math.min(340, window.innerWidth - 24)
  const left = Math.min(Math.max(12, rect.left), window.innerWidth - width - 12)
  const panelHeight = panelRef.value?.offsetHeight || 260
  const spaceAbove = rect.top - 12
  const spaceBelow = window.innerHeight - rect.bottom - 12
  const openAbove = spaceAbove >= panelHeight || spaceAbove >= spaceBelow
  panelStyle.value = openAbove
    ? {
        left: `${Math.round(left)}px`,
        bottom: `${Math.round(window.innerHeight - rect.top + 8)}px`,
        width: `${Math.round(width)}px`
      }
    : {
        left: `${Math.round(left)}px`,
        top: `${Math.round(rect.bottom + 8)}px`,
        width: `${Math.round(width)}px`
      }
}

function toggle() {
  if (loading.value) return
  open.value = !open.value
}

function close(restoreFocus = false) {
  open.value = false
  if (restoreFocus) void nextTick(() => triggerRef.value?.focus())
}

function onDocumentPointerDown(event: PointerEvent) {
  if (!open.value) return
  const target = event.target as Node | null
  if (!target) return
  if (rootEl.value?.contains(target) || panelRef.value?.contains(target)) return
  close()
}

function onDocumentKeydown(event: KeyboardEvent) {
  if (!open.value || event.key !== 'Escape') return
  event.stopPropagation()
  close(true)
}

function onWorkspaceAuthorizationChanged() {
  if (!busy.value) void load()
}

function addWindowListeners() {
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('keydown', onDocumentKeydown)
  window.addEventListener('resize', updatePosition)
  window.addEventListener('scroll', updatePosition, true)
}

function removeWindowListeners() {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('keydown', onDocumentKeydown)
  window.removeEventListener('resize', updatePosition)
  window.removeEventListener('scroll', updatePosition, true)
}

watch(open, async (value) => {
  if (value) {
    addWindowListeners()
    await nextTick()
    updatePosition()
    panelRef.value?.focus({ preventScroll: true })
  } else {
    removeWindowListeners()
  }
})

onMounted(() => {
  window.addEventListener('workspace-authorization-changed', onWorkspaceAuthorizationChanged)
  void load()
})

onUnmounted(() => {
  window.removeEventListener('workspace-authorization-changed', onWorkspaceAuthorizationChanged)
  removeWindowListeners()
})
</script>

<style scoped>
.workspace-trust {
  display: inline-flex;
  flex: 0 1 auto;
  min-width: 0;
  max-width: 100%;
}

.workspace-trust__trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  height: 30px;
  padding: 0 9px;
  border: 1px solid color-mix(in srgb, var(--text-primary) 18%, var(--border-light));
  border-radius: 9px;
  background: color-mix(in srgb, var(--text-secondary) 12%, transparent);
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 550;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.workspace-trust__trigger:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent-color) 40%, var(--border-hover));
  background: color-mix(in srgb, var(--text-secondary) 17%, transparent);
  color: var(--text-primary);
}

.workspace-trust.is-open .workspace-trust__trigger {
  border-color: color-mix(in srgb, var(--accent-color) 55%, var(--border-light));
  background: var(--accent-fade);
  color: var(--text-primary);
}

.workspace-trust__trigger:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent-color) 58%, transparent);
  outline-offset: 2px;
}

.workspace-trust__trigger:disabled {
  cursor: default;
  opacity: 0.66;
}

.workspace-trust__shield {
  flex: 0 0 15px;
  width: 15px;
  height: 15px;
  color: var(--warning);
}

.workspace-trust.is-trusted .workspace-trust__shield {
  color: var(--success);
}

.workspace-trust.is-pending .workspace-trust__shield {
  color: var(--warning);
}

.workspace-trust__label {
  overflow: hidden;
  max-width: 142px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workspace-trust__chevron {
  flex: 0 0 10px;
  width: 10px;
  height: 10px;
  color: var(--text-secondary);
  transition: transform 0.16s ease;
}

.workspace-trust.is-open .workspace-trust__chevron {
  transform: rotate(180deg);
}

.workspace-trust__panel {
  position: fixed;
  z-index: 3000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: min(70vh, 420px);
  overflow-y: auto;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: var(--bg-card);
  box-shadow: var(--shadow-lg);
  color: var(--text-primary);
  font-size: 12px;
  outline: none;
  scrollbar-width: thin;
}

.workspace-trust__panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.workspace-trust__panel-title {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12.5px;
  font-weight: 650;
  letter-spacing: 0.01em;
}

.workspace-trust__state {
  flex: 0 0 auto;
  padding: 1px 7px;
  border: 1px solid var(--border-light);
  border-radius: 999px;
  color: var(--text-muted);
  font-size: 10.5px;
  font-weight: 500;
  line-height: 17px;
}

.workspace-trust__state.is-trusted {
  border-color: color-mix(in srgb, var(--success) 34%, var(--border-light));
  background: var(--success-fade);
  color: var(--success);
}

.workspace-trust__state.is-pending {
  border-color: color-mix(in srgb, var(--warning) 34%, var(--border-light));
  background: var(--warning-fade);
  color: var(--warning);
}

.workspace-trust__path-block {
  display: grid;
  gap: 4px;
  padding: 9px 10px;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  background: var(--bg-input);
}

.workspace-trust__path-label {
  color: var(--text-muted);
  font-size: 10.5px;
  letter-spacing: 0.02em;
}

.workspace-trust__path {
  overflow-wrap: anywhere;
  color: var(--text-primary);
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  line-height: 1.5;
}

.workspace-trust__hint,
.workspace-trust__risk-copy {
  margin: 0;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.55;
}

.workspace-trust__hint {
  color: var(--text-secondary);
}

.workspace-trust__load-error {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  color: var(--danger);
  font-size: 11px;
  line-height: 1.45;
}

.workspace-trust__retry {
  flex: 0 0 auto;
  border: 0;
  background: transparent;
  color: var(--accent-color);
  font: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.workspace-trust__panel-actions {
  display: flex;
  gap: 8px;
  margin-top: 2px;
}

.workspace-trust__action {
  flex: 1 1 0;
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border-hover);
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 550;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease;
}

.workspace-trust__action:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent-color) 50%, var(--border-hover));
  background: color-mix(in srgb, var(--text-secondary) 9%, transparent);
  color: var(--text-primary);
}

.workspace-trust__action.is-primary {
  border-color: color-mix(in srgb, var(--accent-color) 42%, var(--border-light));
  background: var(--accent-fade);
  color: var(--accent-color);
}

.workspace-trust__action.is-primary:hover:not(:disabled) {
  border-color: color-mix(in srgb, var(--accent-color) 68%, var(--border-light));
  background: color-mix(in srgb, var(--accent-color) 20%, transparent);
  color: var(--accent-color);
}

.workspace-trust__action:focus-visible,
.workspace-trust__revoke:focus-visible,
.workspace-trust__retry:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--accent-color) 58%, transparent);
  outline-offset: 2px;
}

.workspace-trust__action:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.workspace-trust__panel-footer {
  display: flex;
  justify-content: flex-end;
  margin-top: -2px;
}

.workspace-trust__revoke {
  padding: 2px 4px;
  border: 0;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.workspace-trust__revoke:hover:not(:disabled) {
  color: var(--danger);
}

.workspace-trust__revoke:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.workspace-trust__error {
  margin: 0;
  color: var(--danger);
  font-size: 11px;
  line-height: 1.5;
}

.workspace-pop-enter-active,
.workspace-pop-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}

.workspace-pop-enter-from,
.workspace-pop-leave-to {
  opacity: 0;
  transform: translateY(4px);
}

@media (max-width: 1100px) {
  .workspace-trust__label {
    max-width: 112px;
  }
}
</style>
