<template>
  <section class="contract-report-preview ui-surface ui-surface--pad">
    <div class="section-head">
      <div class="section-title">
        <el-icon><Document /></el-icon>
        <h3>报告预览</h3>
      </div>
      <span>{{ reportMarkdown ? 'report_markdown' : '等待生成' }}</span>
    </div>

    <div v-if="!reportMarkdown" class="empty">人工审核通过后生成报告。</div>
    <pre v-else>{{ reportMarkdown }}</pre>
  </section>
</template>

<script setup lang="ts">
import { Document } from '@element-plus/icons-vue'

defineProps<{
  reportMarkdown: string
}>()
</script>

<style scoped>
.contract-report-preview {
  min-width: 0;
}

.section-head,
.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-head {
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  color: var(--primary-color);
}

h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 15px;
}

.section-head span,
.empty {
  color: var(--text-secondary);
  font-size: 12px;
}

pre {
  max-height: 520px;
  margin: 0;
  padding: 14px;
  overflow: auto;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: #fff;
  color: var(--text-primary);
  font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
  font-size: 12px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
</style>
