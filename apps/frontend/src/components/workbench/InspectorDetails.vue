<template>
  <details class="inspector-details" :open="open || undefined">
    <summary><span>{{ title }}</span><span v-if="count != null" class="inspector-details__count">{{ count }}</span></summary>
    <div class="inspector-details__body"><p v-if="description" class="inspector-details__description">{{ description }}</p><slot /></div>
  </details>
</template>

<script setup lang="ts">
defineProps<{ title: string; description?: string; count?: number; open?: boolean }>()
</script>

<style scoped>
.inspector-details { min-width: 0; margin-top: 12px; border-top: 1px solid var(--wb-border-soft); }
.inspector-details > summary { display: flex; align-items: center; gap: 8px; min-height: 38px; color: var(--wb-text-secondary); cursor: pointer; list-style: none; font: 500 12px/1.5 var(--font-sans, sans-serif); }
.inspector-details > summary::-webkit-details-marker { display: none; }
.inspector-details > summary::before { content: ''; width: 6px; height: 6px; flex: none; border-right: 1.5px solid currentColor; border-bottom: 1.5px solid currentColor; transform: rotate(-45deg); transition: transform 140ms ease; }
.inspector-details[open] > summary::before { transform: rotate(45deg); }
.inspector-details > summary:hover { color: var(--wb-text); }
.inspector-details > summary:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: 2px; border-radius: 4px; }
.inspector-details__count { margin-left: auto; color: var(--wb-text-muted); font-variant-numeric: tabular-nums; }
.inspector-details__body { min-width: 0; padding: 0 0 8px 14px; }
.inspector-details__description { margin: 0 0 10px; color: var(--wb-text-muted); font-size: 12px; line-height: 1.65; }
</style>
