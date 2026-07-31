<!-- 大纲查看器 — 展示文章大纲，支持 Markdown 渲染或嵌套节点树（含层级标记、标题、描述和子节点） -->
<template>
  <section class="card outline-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Notebook /></el-icon>
        <h4>文章大纲</h4>
      </div>
      <span class="meta" v-if="titleText">{{ titleText }}</span>
    </header>

    <div v-if="!outline?.length && !outlineMarkdown" class="empty">
      <div class="empty-illustration">
        <el-icon><Document /></el-icon>
      </div>
      <span>暂无大纲内容</span>
    </div>

    <template v-else>
      <div v-if="outlineMarkdown" class="markdown-body" v-html="renderedHtml" />

      <div v-else-if="outline?.length" class="outline-tree">
        <div
          v-for="(node, idx) in outline"
          :key="idx"
          class="outline-node"
          :class="`level-${node.level || 1}`"
        >
          <span class="node-marker">{{ nodeMarker(node.level) }}</span>
          <span class="node-title">{{ node.title }}</span>
          <p v-if="node.summary || node.description" class="node-desc">{{ node.summary || node.description }}</p>
          <div v-if="node.children?.length" class="node-children">
            <div
              v-for="(child, cidx) in node.children"
              :key="cidx"
              class="outline-node"
              :class="`level-${child.level || 2}`"
            >
              <span class="node-marker">{{ nodeMarker(child.level) }}</span>
              <span class="node-title">{{ child.title }}</span>
              <p v-if="child.summary || child.description" class="node-desc">{{ child.summary || child.description }}</p>
            </div>
          </div>
        </div>
      </div>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document, Notebook } from '@element-plus/icons-vue'

interface OutlineNode {
  title: string
  level?: number
  summary?: string
  description?: string
  children?: OutlineNode[]
}

const props = defineProps<{
  data?: {
    title?: string
    outline?: OutlineNode[]
    outline_markdown?: string
    outlineMarkdown?: string
  }
}>()

const titleText = computed(() => props.data?.title)
const outline = computed(() => props.data?.outline)
const outlineMarkdown = computed(() => props.data?.outline_markdown || props.data?.outlineMarkdown)

const renderedHtml = computed(() => {
  const md = outlineMarkdown.value
  if (!md) return ''
  return md
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br/>')
})

const nodeMarker = (level?: number) => {
  switch (level) {
    case 1: return '1'
    case 2: return '2'
    case 3: return '3'
    default: return '•'
  }
}
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
  overflow: hidden;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
}

.head-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.head-icon {
  font-size: 14px;
}

.card-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.meta {
  font-size: 11px;
  color: #92400e;
  font-weight: 500;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 24px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-illustration {
  opacity: 0.7;
  margin-bottom: 4px;
}

.markdown-body {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  padding: 10px 12px;
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-radius: 0;
}

.markdown-body :deep(h1) {
  font-size: 16px;
  color: #92400e;
  margin: 8px 0 4px;
  padding-bottom: 4px;
  border-bottom: 1px solid #fcd34d;
}

.markdown-body :deep(h2) {
  font-size: 14px;
  color: #b45309;
  margin: 6px 0 3px;
}

.markdown-body :deep(h3) {
  font-size: 13px;
  color: #d97706;
  margin: 4px 0 2px;
}

.outline-tree {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.outline-node {
  padding-left: 4px;
}

.outline-node.level-1 {
  padding-left: 0;
}

.outline-node.level-2 {
  padding-left: 16px;
  border-left: 2px solid #fcd34d;
  margin-left: 8px;
}

.outline-node.level-3 {
  padding-left: 28px;
  border-left: 2px solid #fde68a;
  margin-left: 8px;
}

.node-marker {
  margin-right: 6px;
  font-size: 12px;
}

.node-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.node-desc {
  margin: 2px 0 0 22px;
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.4;
}

.node-children {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}
</style>
