<template>
  <section class="companion-pet" data-testid="companion-pet-bar" aria-label="伙伴养成状态">
    <div class="pet-line">
      <span class="pet-level" data-testid="companion-pet-level">Lv.{{ level }}</span>
      <span class="pet-title">{{ title }}</span>
      <span class="pet-mood" data-testid="companion-pet-mood">{{ moodLabel }}</span>
      <span class="pet-streak" data-testid="companion-pet-streak">连续 {{ streakDays }} 天</span>
    </div>

    <div class="pet-meter" :aria-label="`好感度 ${Math.round(affinityPercent * 100)}%`">
      <span class="pet-meter-label">好感</span>
      <div class="pet-meter-track">
        <div
          class="pet-meter-fill"
          data-testid="companion-pet-affinity"
          :style="{ width: `${Math.round(affinityPercent * 100)}%` }"
        ></div>
      </div>
      <span class="pet-meter-value">{{ Math.round(affinityPercent * 100) }}%</span>
    </div>

    <div class="pet-meter" :aria-label="`精力 ${energy}%`">
      <span class="pet-meter-label">精力</span>
      <div class="pet-meter-track">
        <div class="pet-meter-fill pet-meter-fill--energy" :style="{ width: `${energy}%` }"></div>
      </div>
      <span class="pet-meter-value">{{ energy }}</span>
    </div>

    <div class="pet-actions">
      <button type="button" data-testid="companion-pet-pat" @click="emit('interact', 'pat')">摸摸头</button>
      <button type="button" data-testid="companion-pet-feed" @click="emit('interact', 'feed')">喂点心</button>
      <button type="button" data-testid="companion-pet-play" @click="emit('interact', 'play')">玩一会儿</button>
    </div>

    <div v-if="achievementLabels.length" class="pet-badges" data-testid="companion-pet-badges">
      <span class="pet-badges-label">成就 {{ achievementCount }}</span>
      <span v-for="label in achievementLabels" :key="label" class="pet-badge">{{ label }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import type { PetAction } from '@/features/companion/pet'

withDefaults(defineProps<{
  level: number
  title: string
  affinityPercent: number
  energy: number
  moodLabel: string
  streakDays: number
  achievementLabels: string[]
  achievementCount: number
}>(), { achievementLabels: () => [], achievementCount: 0 })

const emit = defineEmits<{
  (event: 'interact', action: Extract<PetAction, 'pat' | 'feed' | 'play'>): void
}>()
</script>

<style scoped>
.companion-pet {
  display: flex; flex-direction: column; gap: 7px;
  padding: 9px; border-radius: 9px;
  background: var(--bg-input, var(--bg-app));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
}
.pet-line { display: flex; align-items: baseline; flex-wrap: wrap; gap: 6px; font-size: 12px; }
.pet-level { font-weight: 600; color: var(--primary-color, #4c8dff); }
.pet-title { color: var(--text-primary); }
.pet-mood, .pet-streak { font-size: 11px; color: var(--text-muted, var(--text-secondary)); }
.pet-streak { margin-left: auto; }
.pet-meter { display: flex; align-items: center; gap: 6px; }
.pet-meter-label, .pet-meter-value { font-size: 10px; color: var(--text-muted, var(--text-secondary)); min-width: 26px; }
.pet-meter-value { text-align: right; min-width: 30px; }
.pet-meter-track { flex: 1; height: 5px; border-radius: 3px; overflow: hidden; background: var(--border-color-base, rgba(128, 128, 128, 0.22)); }
.pet-meter-fill {
  height: 100%; border-radius: 3px;
  background: var(--primary-color, #4c8dff);
  transition: width 320ms ease;
}
.pet-meter-fill--energy { background: var(--success-color, #67c23a); }
.pet-actions { display: flex; gap: 5px; }
.pet-actions button {
  flex: 1; font: inherit; font-size: 11px; padding: 5px 4px; cursor: pointer;
  color: var(--text-regular, var(--text-primary));
  background: var(--bg-panel, var(--bg-card));
  border: 1px solid var(--border-color-base, rgba(128, 128, 128, 0.3));
  border-radius: 6px;
  transition: transform 140ms ease, background-color 140ms ease;
}
.pet-actions button:hover { background: var(--surface-hover, var(--bg-panel)); }
.pet-actions button:active { transform: scale(0.94); }
.pet-badges { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.pet-badges-label { font-size: 10px; color: var(--text-muted, var(--text-secondary)); }
.pet-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  color: var(--primary-color, #4c8dff);
  background: var(--accent-fade, rgba(76, 141, 255, 0.08));
}
@media (prefers-reduced-motion: reduce) {
  .pet-meter-fill, .pet-actions button { transition: none; }
}
</style>
