<template>
  <div class="companion-voice" data-testid="companion-voice">
    <button
      type="button"
      class="voice-mic"
      :class="{ 'is-active': listening, 'is-speaking': speaking }"
      :aria-label="listening ? '停止聆听' : '点击说话'"
      :aria-pressed="listening"
      data-testid="companion-mic"
      @click="emit('toggle')"
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
        <path d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3z" fill="currentColor" />
        <path d="M6 11a6 6 0 0 0 12 0M12 17v4m-4 0h8" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
      </svg>
      <span class="voice-mic-pulse" aria-hidden="true"></span>
    </button>

    <div class="voice-body">
      <div class="voice-wave" :class="{ 'is-active': listening || speaking }" data-testid="companion-wave" aria-hidden="true">
        <span
          v-for="(bar, index) in bars"
          :key="index"
          class="voice-wave-bar"
          :style="{ '--i': String(index), '--amp': String(bar) }"
        ></span>
      </div>
      <p class="voice-subtitle" data-testid="companion-voice-subtitle">
        <span v-if="interim" class="voice-interim">{{ interim }}</span>
        <span v-else>{{ hint }}</span>
      </p>
    </div>

    <button
      type="button"
      class="voice-mute"
      :class="{ 'is-muted': muted }"
      :aria-label="muted ? '打开朗读' : '关闭朗读'"
      data-testid="companion-mute"
      @click="emit('toggle-mute')"
    >{{ muted ? '静音' : '有声' }}</button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { VoicePhase } from '@/features/companion/voice'

const props = withDefaults(defineProps<{
  phase: VoicePhase
  interim?: string
  hint: string
  muted?: boolean
  level?: number
}>(), { interim: '', muted: false, level: 0.35 })

const emit = defineEmits<{
  (event: 'toggle'): void
  (event: 'toggle-mute'): void
}>()

const listening = computed(() => props.phase === 'listening' || props.phase === 'recognizing')
const speaking = computed(() => props.phase === 'speaking')
const bars = computed(() => {
  const amplitude = Math.min(1, Math.max(0.1, props.level))
  return Array.from({ length: 11 }, (_, index) => {
    const wave = Math.abs(Math.sin(index * 1.13 + 0.7))
    return Math.round(4 + 16 * amplitude * (0.35 + 0.65 * wave))
  })
})
</script>

<style scoped>
.companion-voice {
  display: flex; align-items: center; gap: 8px;
  padding: 7px; border-radius: 9px;
  background: var(--bg-input, var(--bg-app));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
}
.voice-mic {
  position: relative; flex: 0 0 auto;
  width: 40px; height: 40px; border-radius: 50%;
  display: grid; place-items: center; cursor: pointer;
  color: var(--text-primary);
  background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
  transition: transform 160ms ease, color 160ms ease, background-color 160ms ease;
}
.voice-mic:hover { transform: scale(1.06); }
.voice-mic:active { transform: scale(0.94); }
.voice-mic.is-active { color: #fff; background: var(--primary-color, #4c8dff); border-color: transparent; }
.voice-mic.is-speaking { color: var(--primary-color, #4c8dff); }
.voice-mic-pulse {
  position: absolute; inset: -4px; border-radius: 50%; pointer-events: none;
  border: 2px solid var(--primary-color, #4c8dff); opacity: 0;
}
.voice-mic.is-active .voice-mic-pulse { animation: voice-pulse 1.5s ease-out infinite; }
.voice-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
.voice-wave { display: flex; align-items: center; gap: 2px; height: 18px; }
.voice-wave-bar {
  flex: 1; min-width: 2px; border-radius: 2px;
  height: 4px; background: var(--border-color-base, rgba(128, 128, 128, 0.4));
  transition: height 180ms ease, background-color 180ms ease;
}
.voice-wave.is-active .voice-wave-bar {
  height: calc(var(--amp) * 1px);
  background: var(--primary-color, #4c8dff);
  animation: voice-bounce 760ms ease-in-out infinite alternate;
  animation-delay: calc(var(--i) * -72ms);
}
.voice-subtitle {
  margin: 0; font-size: 11px; line-height: 1.4; min-height: 15px;
  color: var(--text-muted, var(--text-secondary));
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.voice-interim { color: var(--text-primary); }
.voice-mute {
  flex: 0 0 auto; font: inherit; font-size: 11px; padding: 4px 7px; cursor: pointer;
  color: var(--text-regular, var(--text-primary));
  background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3)); border-radius: 6px;
}
.voice-mute.is-muted { opacity: 0.6; }
@keyframes voice-pulse {
  0% { transform: scale(0.9); opacity: 0.65; }
  100% { transform: scale(1.5); opacity: 0; }
}
@keyframes voice-bounce {
  from { transform: scaleY(0.45); }
  to { transform: scaleY(1); }
}
@media (prefers-reduced-motion: reduce) {
  .voice-mic, .voice-wave-bar { transition: none; }
  .voice-mic-pulse, .voice-wave.is-active .voice-wave-bar { animation: none; }
}
</style>
