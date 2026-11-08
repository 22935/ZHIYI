<template>
  <Transition name="companion-bubble">
    <div
      v-if="text"
      class="companion-bubble"
      :class="`companion-bubble--${tone}`"
      data-testid="companion-bubble"
      role="status"
      aria-live="polite"
    >{{ text }}</div>
  </Transition>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  text: string
  tone?: 'chat' | 'effect' | 'achievement'
}>(), { tone: 'chat' })
</script>

<style scoped>
.companion-bubble {
  position: relative;
  max-width: min(280px, calc(100vw - 48px));
  box-sizing: border-box;
  padding: 8px 11px;
  font-size: 12px;
  line-height: 1.6;
  word-break: break-word;
  color: var(--text-primary);
  background: var(--bg-card);
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
  border-radius: 10px;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.08);
}
.companion-bubble::after {
  content: '';
  position: absolute;
  right: 26px;
  bottom: -6px;
  width: 10px;
  height: 10px;
  background: var(--bg-card);
  border-right: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
  border-bottom: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
  transform: rotate(45deg);
}
.companion-bubble--effect { color: var(--primary-color, #4c8dff); }
.companion-bubble--achievement {
  border-color: var(--primary-line, rgba(76, 141, 255, 0.5));
  background: var(--accent-fade, rgba(76, 141, 255, 0.08));
}
.companion-bubble--achievement::after { background: var(--bg-card); }
.companion-bubble-enter-active, .companion-bubble-leave-active { transition: opacity 180ms ease, transform 180ms ease; }
.companion-bubble-enter-from, .companion-bubble-leave-to { opacity: 0; transform: translateY(6px) scale(0.96); }
@media (prefers-reduced-motion: reduce) {
  .companion-bubble-enter-active, .companion-bubble-leave-active { transition: none; }
}
</style>
