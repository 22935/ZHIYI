<template>
  <div ref="root" class="permission-selector" @keydown.esc.stop.prevent="close" @keydown="navigate">
    <button ref="trigger" type="button" class="permission-trigger" :class="`permission-tone--${selected}`" aria-haspopup="menu" :aria-expanded="open" aria-label="访问权限" @click="open = !open" @keydown.down.prevent="show">
      <el-icon><component :is="current.icon" /></el-icon>
      <span>{{ current.label }}</span>
    </button>
    <div v-if="open" class="permission-menu" role="menu" aria-label="访问权限选项">
      <div class="permission-heading">应如何批准 OScode 操作？</div>
      <button v-for="option in options" :key="option.id" type="button" role="menuitemradio" :aria-checked="selected === option.id" class="permission-option" :class="[`permission-tone--${option.id}`, { 'is-selected': selected === option.id }]" @click="select(option.id)">
        <el-icon class="permission-option-icon"><component :is="option.icon" /></el-icon>
        <span class="permission-copy"><strong>{{ option.title }}</strong><span>{{ option.description }}</span></span>
        <el-icon v-if="selected === option.id" class="permission-check"><Check /></el-icon>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import { Check, Lock, MagicStick, Warning } from '@element-plus/icons-vue'

import type { ChatApprovalMode } from '@/config/chatApproval'
const props = withDefaults(defineProps<{ modelValue?: ChatApprovalMode }>(), { modelValue: 'ask' })
const emit = defineEmits<{ 'update:modelValue': [value: ChatApprovalMode] }>()
const options = [
  { id: 'ask' as const, label: '请求批准', title: '请求批准', description: '读取工作区文件无需确认；修改文件和运行命令前询问', icon: Lock },
  { id: 'auto' as const, label: '帮我批准', title: '帮我批准', description: '自动批准工作区文件修改；运行终端命令前询问', icon: MagicStick },
  { id: 'full' as const, label: '完全访问', title: '完全访问权限', description: '自动批准文件修改和终端命令；命令可按当前用户权限访问工作区外资源', icon: Warning }
]
const selected = computed(() => props.modelValue)
const current = computed(() => options.find(option => option.id === selected.value)!)
const open = ref(false)
const root = ref<HTMLElement>()
const trigger = ref<HTMLButtonElement>()
function close() { open.value = false; trigger.value?.focus() }
function select(value: ChatApprovalMode) { emit('update:modelValue', value); close() }
async function show() {
  open.value = true
  await nextTick()
  root.value?.querySelector<HTMLButtonElement>('[aria-checked="true"]')?.focus()
}
function navigate(event: KeyboardEvent) {
  if (!open.value || !['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key) || event.target === trigger.value) return
  const items = Array.from(root.value?.querySelectorAll<HTMLButtonElement>('[role="menuitemradio"]') || [])
  const index = items.indexOf(document.activeElement as HTMLButtonElement)
  const next = event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
  event.preventDefault()
  items[next]?.focus()
}
function outside(event: PointerEvent) { if (!root.value?.contains(event.target as Node)) open.value = false }
onMounted(() => document.addEventListener('pointerdown', outside))
onUnmounted(() => document.removeEventListener('pointerdown', outside))
</script>

<style scoped>
.permission-selector { position: relative; }
.permission-tone--ask { --permission-tone: color-mix(in srgb, #719fce 78%, var(--text-primary)); }
.permission-tone--auto { --permission-tone: color-mix(in srgb, #65aa98 78%, var(--text-primary)); }
.permission-tone--full { --permission-tone: color-mix(in srgb, #be943b 82%, var(--text-primary)); }
.permission-selector .permission-trigger { display: inline-flex; align-items: center; gap: 6px; min-height: 28px; padding: 4px 9px; border: 0; box-shadow: none; border-radius: 20px; background: transparent; color: var(--permission-tone); font: inherit; font-size: 12px; cursor: pointer; transition: background 160ms ease; }
.permission-selector .permission-trigger:hover, .permission-selector .permission-trigger[aria-expanded='true'] { background: color-mix(in srgb, var(--permission-tone) 10%, var(--bg-card)); }
.permission-menu { position: absolute; bottom: calc(100% + 12px); left: 0; z-index: 40; width: min(420px, calc(100vw - 100px)); padding: 12px 8px 8px; border: 1px solid var(--border-color); border-radius: 18px; background: var(--bg-card); box-shadow: 0 16px 48px rgba(0,0,0,.28); }
.permission-heading { padding: 3px 12px 10px; font-size: 13px; color: var(--text-muted); }
.permission-option { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 12px; border: 0; border-radius: 10px; text-align: left; color: var(--text-secondary); background: transparent; font: inherit; cursor: pointer; }
.permission-option:hover, .permission-option:focus-visible { background: color-mix(in srgb, var(--text-primary) 7%, var(--bg-card)); }
.permission-option-icon { flex-shrink: 0; font-size: 19px; }
.permission-copy { display: flex; flex: 1; flex-direction: column; gap: 3px; min-width: 0; }
.permission-copy strong { font-size: 14px; font-weight: 600; }
.permission-copy > span { font-size: 12px; line-height: 1.5; color: var(--text-muted); }
.permission-option { color: var(--permission-tone); }
.permission-option.is-selected { background: color-mix(in srgb, var(--permission-tone) 10%, var(--bg-card)); }
.permission-option:hover, .permission-option:focus-visible { background: color-mix(in srgb, var(--permission-tone) 14%, var(--bg-card)); }
.permission-option.is-selected .permission-copy > span { color: color-mix(in srgb, var(--permission-tone) 48%, var(--text-secondary)); }
.permission-check { flex-shrink: 0; font-size: 18px; }
button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
</style>
