<template>
  <dl class="property-list">
    <div v-for="row in rows" :key="row.label" class="property-row">
      <dt>{{ inspectorLabel(row.label) }}</dt>
      <dd
        :title="row.value == null || row.value === '' ? undefined : String(row.value)"
        :class="{ 'is-code': row.code, 'is-empty': row.value == null || row.value === '' }"
      >{{ row.value == null || row.value === '' ? (row.emptyLabel || '暂未提供') : row.code ? row.value : inspectorValue(row.value) }}</dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
import { inspectorLabel, inspectorValue } from '@/workbench/runtime/inspectorPresentation'
export interface InspectorProperty {
  label: string
  value?: string | number | null
  code?: boolean
  emptyLabel?: string
}

defineProps<{
  rows: InspectorProperty[]
}>()
</script>

<style scoped>
.property-list { margin: 0; }
.property-list { container-type: inline-size; }
.property-row { display: grid; grid-template-columns: minmax(76px, .32fr) minmax(0, 1fr); gap: 12px; min-height: 32px; padding: 6px 0; font-size: 12px; line-height: 1.65; }
.property-row + .property-row { border-top: 0; }
.property-row dt { min-width: 0; color: var(--wb-text-secondary); overflow-wrap: anywhere; }
.property-row dd { min-width: 0; margin: 0; overflow-wrap: anywhere; color: var(--wb-text); text-align: left; }
.property-row dd.is-code { user-select: text; color: var(--wb-text-secondary); font: 11px/1.65 var(--font-mono, monospace); }
.property-row dd.is-empty { color: var(--wb-text-muted); }
@container (max-width: 260px) { .property-row { grid-template-columns: 1fr; gap: 2px; padding: 8px 0; } }
</style>
