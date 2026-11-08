<template>
  <InspectorSection title="Identity" :badge="entry.identityQuality || 'unproven'">
    <div class="identity-overview">
      <div class="identity-overview__row">
        <span>角色</span>
        <strong>{{ inspectorLabel(entry.logicalRole || '未定义') }}</strong>
      </div>

    </div>
    <button
      type="button"
      class="inspector-disclosure"
      :aria-expanded="idsExpanded"
      @click="idsExpanded = !idsExpanded"
    >
      <span>任务技术编号</span>
      <span class="inspector-disclosure__action">{{ idsExpanded ? '收起' : '展开' }}</span>
    </button>
    <div v-if="idsExpanded" class="identity-details">
      <InspectorPropertyList :rows="[
        { label: '任务标识', value: entry.semanticTaskKey, code: true },
        { label: 'Task ID', value: entry.taskId, code: true },
        { label: 'ACG Node', value: entry.acgNodeId, code: true }
      ]" />
    </div>
  </InspectorSection>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { WorkspaceEntry } from '@/services/api/agentos'
import InspectorPropertyList from '@/components/workbench/InspectorPropertyList.vue'
import { inspectorLabel } from '@/workbench/runtime/inspectorPresentation'
import InspectorSection from '@/components/workbench/InspectorSection.vue'

defineProps<{ entry: WorkspaceEntry }>()
const idsExpanded = ref(false)
</script>

<style scoped>
.identity-overview { display: grid; gap: 8px; padding: 1px 0 3px; }
.identity-overview__row { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 12px; align-items: center; min-width: 0; }
.identity-overview__row > span { color: var(--wb-text-muted); font-size: 12px; }
.identity-overview__row strong { color: var(--wb-text-secondary); font-size: 12px; font-weight: 500; }
.identity-overview__row code { min-width: 0; overflow: hidden; color: var(--wb-text); font: 11px/1.4 var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.inspector-disclosure { display: flex; align-items: center; justify-content: space-between; width: 100%; margin-top: 10px; padding: 8px 0; border: 0; border-top: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: transparent; cursor: pointer; font-size: 11px; text-align: left; }
.inspector-disclosure:hover { color: var(--wb-text); }
.inspector-disclosure__action { color: var(--wb-accent); font: 10px var(--font-mono, monospace); }
.identity-details { padding-top: 1px; }
</style>
