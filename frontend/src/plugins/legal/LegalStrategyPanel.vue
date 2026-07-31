<template>
  <section class="legal-strategy">
    <strong>法律执行策略</strong>
    <el-checkbox v-model="draft.evidenceFirst" :disabled="readonly">Evidence 优先</el-checkbox>
    <el-checkbox v-model="draft.riskParallel" :disabled="readonly">风险并行分析</el-checkbox>
    <el-checkbox v-model="draft.conservativeReview" :disabled="readonly">保守人工审核</el-checkbox>
    <el-checkbox v-model="draft.useTemplateWorkflow" :disabled="readonly">固定合同审查 Workflow</el-checkbox>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { LegalPluginDraft } from './index'

const props = defineProps<{ modelValue: Record<string, unknown>; readonly?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()
const draft = computed<LegalPluginDraft>({
  get: () => props.modelValue as unknown as LegalPluginDraft,
  set: value => emit('update:modelValue', value as unknown as Record<string, unknown>)
})
</script>

<style scoped>
.legal-strategy { display:flex; align-items:center; flex-wrap:wrap; gap:10px 18px; padding:10px 12px; border-left:3px solid var(--el-color-warning); background:var(--surface-muted, rgba(127,127,127,.06)); }
.legal-strategy strong { margin-right:4px; }
</style>
