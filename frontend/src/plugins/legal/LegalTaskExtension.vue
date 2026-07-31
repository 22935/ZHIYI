<template>
  <section class="legal-extension ui-surface ui-surface--pad">
    <header>
      <div><strong>法律任务扩展</strong><small>仅对当前新 Run 生效</small></div>
      <el-tag effect="plain" type="warning">kinlin.legal</el-tag>
    </header>
    <div class="legal-grid">
      <label class="wide"><span>合同文本</span><el-input v-model="draft.contractText" :disabled="readonly" type="textarea" :rows="5" placeholder="粘贴合同正文；也可以在通用任务材料区上传合同文件" /></label>
      <label><span>合同审查目标</span><el-input v-model="draft.reviewGoal" :disabled="readonly" placeholder="例如：识别风险并给出修改建议" /></label>
      <label><span>合同类型（可选）</span><el-input v-model="draft.contractType" :disabled="readonly" placeholder="采购、服务、软件开发等" /></label>
    </div>
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
.legal-extension { border-color: color-mix(in srgb, var(--el-color-warning) 36%, var(--border-color)); }
header { display:flex; justify-content:space-between; gap:12px; margin-bottom:12px; }
header div { display:flex; flex-direction:column; gap:3px; }
header small, label span { color:var(--text-secondary); font-size:12px; }
.legal-grid { display:grid; grid-template-columns:1fr 1fr; gap:12px; }
label { display:flex; flex-direction:column; gap:6px; }
.wide { grid-column:1 / -1; }
@media (max-width: 760px) { .legal-grid { grid-template-columns:1fr; } .wide { grid-column:auto; } }
</style>
