<template>
  <div v-if="sources.length" class="observation-notice" role="status">
    <strong>部分运行数据加载失败</strong>
    <p>{{ sources.join('、') }}暂时无法读取；当前空白不代表没有记录。</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { RuntimeObservation } from '@/workbench/runtime/observation'
const props = defineProps<{ observation?: RuntimeObservation | null; runId: string | null }>()
const labels: Record<string, string> = {
  run: '运行状态', trace: '执行追踪', provenance: '来源关联', operational: '执行树',
  resource: '资源用量', review: '审核记录', context: '上下文数据'
}
const sources = computed(() => props.runId && props.observation?.runId === props.runId
  ? [...new Set(props.observation.unavailableSources || [])].map(key => labels[key] || '其他运行数据') : [])
</script>

<style scoped>
.observation-notice { flex: none; padding: 10px 14px; border-bottom: 1px solid var(--wb-border-soft); color: var(--wb-text-secondary); background: var(--wb-surface-inset); font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.observation-notice strong { color: var(--wb-warning); }
.observation-notice p { margin: 4px 0 0; }
</style>
