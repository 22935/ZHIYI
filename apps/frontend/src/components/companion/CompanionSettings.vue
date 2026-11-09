<template>
  <div class="companion-settings" data-testid="companion-settings">
    <div class="settings-row">
      <span class="settings-label">形象</span>
      <select
        :value="skinId"
        data-testid="companion-skin"
        aria-label="切换形象"
        @change="onSkinChange"
      >
        <option v-for="skin in skins" :key="skin.id" :value="skin.id">{{ skin.label }}</option>
      </select>
    </div>
    <button
      type="button"
      class="settings-diy"
      data-testid="companion-diy-open"
      @click="emit('open-diy')"
    >DIY 我的形象</button>

    <div class="settings-row">
      <span class="settings-label">语音唤醒</span>
      <label class="settings-toggle" title="说唤醒词就能叫醒我，不用先点麦克风">
        <input
          type="checkbox"
          :checked="wakeEnabled"
          :disabled="!wakeSupported"
          data-testid="companion-wake"
          @change="onWakeToggle"
        />
        {{ wakeSupported ? (wakeEnabled ? '已开启' : '已关闭') : '不可用' }}
      </label>
    </div>
    <p class="settings-note" data-testid="companion-wake-note">{{ wakeNote }}</p>
    <p class="settings-note">回复默认走模型（轻量档），这里不用再手动开关。</p>

    <button
      type="button"
      class="settings-done"
      data-testid="companion-settings-close"
      @click="emit('close')"
    >完成</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  skins: ReadonlyArray<{ id: string; label: string }>
  skinId: string
  wakeSupported: boolean
  wakeEnabled: boolean
  wakeWords: readonly string[]
  wakeError?: string
}>()

const emit = defineEmits<{
  (event: 'skin-change', id: string): void
  (event: 'open-diy'): void
  (event: 'toggle-wake', enabled: boolean): void
  (event: 'close'): void
}>()

const wakeNote = computed(() => {
  if (props.wakeError) return props.wakeError
  if (!props.wakeSupported) return '这个环境没有麦克风权限，语音唤醒用不了。'
  const words = props.wakeWords.length ? props.wakeWords.join('」或「') : '我的名字'
  return `说「${words}」就能叫醒我，后面可以直接跟一句话。`
})

const onSkinChange = (event: Event): void => {
  emit('skin-change', (event.target as HTMLSelectElement).value)
}

const onWakeToggle = (event: Event): void => {
  emit('toggle-wake', (event.target as HTMLInputElement).checked)
}
</script>

<style scoped>
.companion-settings { display: flex; flex-direction: column; gap: 9px; }
.settings-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.settings-label { font-size: 12px; color: var(--text-regular, var(--text-primary)); }
.settings-row select {
  font: inherit; font-size: 12px; padding: 3px 7px; cursor: pointer; max-width: 170px;
  color: var(--text-regular, var(--text-primary)); background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
}
.settings-toggle {
  display: flex; align-items: center; gap: 4px; font-size: 11px; cursor: pointer;
  color: var(--text-secondary, var(--text-primary));
}
.settings-toggle input { margin: 0; }
.settings-toggle input:disabled { cursor: not-allowed; opacity: 0.5; }
.settings-diy, .settings-done {
  font: inherit; font-size: 12px; padding: 5px 8px; cursor: pointer; align-self: flex-start;
  color: var(--text-regular, var(--text-primary)); background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
  transition: background-color 180ms ease;
}
.settings-diy { color: var(--primary-color, #4c8dff); }
.settings-done { align-self: flex-end; }
.settings-diy:hover, .settings-done:hover { background: var(--surface-hover, var(--bg-panel)); }
.settings-note {
  margin: 0; font-size: 11px; line-height: 1.5;
  color: var(--text-muted, var(--text-secondary));
}
</style>
