<template>
  <InspectorSection title="相关文件" :badge="String(artifacts.length)">
    <div v-if="artifacts.length" class="related-files">
      <button v-for="artifact in artifacts" :key="artifact.entryId" type="button" @click="emit('openArtifact', artifact)">
        <span class="related-files__icon" aria-hidden="true">md</span>
        <span class="related-files__copy">
          <strong>{{ artifact.name }}</strong>
          <small>{{ artifact.artifactKey || artifact.contentRef || 'artifact' }}</small>
        </span>
        <span class="related-files__arrow" aria-hidden="true">↗</span>
      </button>
    </div>
    <p v-else class="related-files__empty">当前步骤没有可打开的相关产物。</p>
  </InspectorSection>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { WorkspaceEntry } from '@/services/api/agentos'
import InspectorSection from '@/components/workbench/InspectorSection.vue'

const props = defineProps<{
  entry: WorkspaceEntry
  entries: WorkspaceEntry[]
}>()

const emit = defineEmits<{
  openArtifact: [entry: WorkspaceEntry]
}>()

const artifacts = computed(() => props.entries
  .filter(item => item.kind === 'artifact' && (
    (props.entry.semanticTaskKey && item.semanticTaskKey === props.entry.semanticTaskKey)
    || (props.entry.entryId && item.parentEntryId === props.entry.entryId)
  ))
  .sort((left, right) => left.displayOrder - right.displayOrder || left.entryId.localeCompare(right.entryId)))
</script>

<style scoped>
.related-files { display: grid; gap: 2px; }
.related-files button { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; gap: 9px; align-items: center; width: 100%; min-height: 42px; padding: 5px 0; border: 0; border-bottom: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: transparent; cursor: pointer; text-align: left; }
.related-files button:hover { color: var(--wb-accent); }
.related-files button:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: -2px; }
.related-files__icon { display: grid; place-items: center; width: 24px; height: 20px; border: 1px solid color-mix(in srgb, var(--wb-accent) 36%, var(--wb-border)); border-radius: 4px; color: var(--wb-accent); font: 9px var(--font-mono, monospace); text-transform: uppercase; }
.related-files__copy { display: grid; gap: 2px; min-width: 0; }
.related-files__copy strong { overflow: hidden; color: inherit; font-size: 11px; font-weight: 550; text-overflow: ellipsis; white-space: nowrap; }
.related-files__copy small { overflow: hidden; color: var(--wb-text-muted); font: 9px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.related-files__arrow { color: var(--wb-text-muted); font: 12px var(--font-mono, monospace); }
.related-files__empty { margin: 0; color: var(--wb-text-muted); font-size: 11px; line-height: 1.6; }
</style>
