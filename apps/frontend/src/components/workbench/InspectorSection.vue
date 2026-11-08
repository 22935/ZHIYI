<template>
  <section class="inspector-section">
    <div class="inspector-section__heading">
      <h3>{{ inspectorLabel(title) }}</h3>
      <span v-if="badge" class="inspector-section__badge" :class="badgeClass">{{ inspectorValue(badge) }}</span>
    </div>
    <slot />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { statusToneClass, type SemanticTone } from '@/utils/statusSemantic'
import { inspectorLabel, inspectorValue } from '@/workbench/runtime/inspectorPresentation'

const props = defineProps<{
  title: string
  badge?: string | null
  /** 'status' derives the tone from the badge text; any SemanticTone pins it; 'accent' keeps the workbench accent. */
  badgeTone?: 'status' | 'accent' | SemanticTone
}>()

const badgeClass = computed(() => {
  const tone = props.badgeTone
  if (!tone || tone === 'accent') return ''
  if (tone === 'status') return statusToneClass(props.badge)
  return `tone-${tone}`
})
</script>

<style scoped>
.inspector-section { min-width: 0; min-height: 0; padding: 16px 2px; border: 0; border-radius: 0; background: transparent; box-shadow: none; font: 13px/1.65 var(--font-sans, system-ui, sans-serif); overflow-wrap: anywhere; }
.inspector-section__heading { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 12px; }
.inspector-section__heading h3 { min-width: 0; margin: 0; color: var(--wb-text); font: 600 13px/1.5 var(--font-sans, system-ui, sans-serif); }
.inspector-section :deep(p) { margin: 8px 0; line-height: 1.65; }
.inspector-section :deep(pre) { max-width: 100%; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
.inspector-section__badge, .inspector-section__heading span { display: inline-flex; align-items: center; min-height: 20px; padding: 2px 6px; border: 1px solid color-mix(in srgb, var(--wb-accent) 20%, var(--wb-border-soft)); border-radius: var(--wb-radius-sm); color: var(--wb-accent); background: color-mix(in srgb, var(--wb-accent-soft) 44%, transparent); font: 10px var(--font-mono, monospace); letter-spacing: .04em; text-transform: uppercase; }
.inspector-section__heading span.inspector-section__badge { flex-shrink: 0; max-width: 55%; text-align: center; text-transform: none; letter-spacing: 0; font: 11px/1.4 var(--font-sans, sans-serif); color: var(--tone, var(--wb-accent)); border-color: color-mix(in srgb, var(--tone, var(--wb-accent)) 26%, var(--wb-border-soft)); background: color-mix(in srgb, var(--tone, var(--wb-accent)) 8%, transparent); }
</style>
