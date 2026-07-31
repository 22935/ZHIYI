<!-- 教案查看器 — 将 Markdown 格式个性化教案渲染展示，从年级、学科、主题属性计算标题 -->
<template>
  <section class="card lesson-card">
    <header class="card-head">
      <div class="head-left">
        <el-icon class="head-icon"><Notebook /></el-icon>
        <h4>个性化教案</h4>
      </div>
      <span class="meta">{{ titleText }}</span>
    </header>

    <div v-if="!lessonPlanMarkdown" class="empty">
      <div class="empty-illustration">
        <el-icon><Document /></el-icon>
      </div>
      <span>暂无教案内容</span>
    </div>
    <article v-else class="markdown-body" v-html="renderedHtml" />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Document, Notebook } from '@element-plus/icons-vue'

interface LessonPlanData {
  topic?: string
  subject?: string
  grade?: string
  duration?: string
  lesson_plan?: string
}

const props = defineProps<{ data?: LessonPlanData }>()

const lessonPlanMarkdown = computed(() => (props.data?.lesson_plan || '').trim())
const titleText = computed(() => {
  const grade = props.data?.grade || ''
  const subject = props.data?.subject || ''
  const topic = props.data?.topic || ''
  const assembled = `${grade}${subject}${topic ? `·${topic}` : ''}`.trim()
  return assembled || '未命名课题'
})

const escapeHtml = (raw: string) =>
  raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const toMarkdownHtml = (markdown: string) => {
  const escaped = escapeHtml(markdown)
  const lines = escaped.split(/\r?\n/)
  const output: string[] = []
  let inUl = false
  let inOl = false

  const closeLists = () => {
    if (inUl) {
      output.push('</ul>')
      inUl = false
    }
    if (inOl) {
      output.push('</ol>')
      inOl = false
    }
  }

  const inlineFormat = (value: string) =>
    value
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.+?)`/g, '<code>$1</code>')

  lines.forEach(line => {
    const trimmed = line.trim()
    if (!trimmed) {
      closeLists()
      output.push('<br />')
      return
    }

    const h3 = trimmed.match(/^###\s+(.+)$/)
    const h2 = trimmed.match(/^##\s+(.+)$/)
    const h1 = trimmed.match(/^#\s+(.+)$/)
    if (h3 || h2 || h1) {
      closeLists()
      const content = inlineFormat((h3 || h2 || h1)?.[1] || '')
      const tag = h3 ? 'h3' : h2 ? 'h2' : 'h1'
      output.push(`<${tag}>${content}</${tag}>`)
      return
    }

    const ul = trimmed.match(/^[-*]\s+(.+)$/)
    if (ul) {
      if (!inUl) {
        closeLists()
        output.push('<ul>')
        inUl = true
      }
      output.push(`<li>${inlineFormat(ul[1])}</li>`)
      return
    }

    const ol = trimmed.match(/^\d+\.\s+(.+)$/)
    if (ol) {
      if (!inOl) {
        closeLists()
        output.push('<ol>')
        inOl = true
      }
      output.push(`<li>${inlineFormat(ol[1])}</li>`)
      return
    }

    closeLists()
    output.push(`<p>${inlineFormat(trimmed)}</p>`)
  })

  closeLists()
  return output.join('\n')
}

const renderedHtml = computed(() => toMarkdownHtml(lessonPlanMarkdown.value))
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.head-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.head-icon {
  font-size: 16px;
}

.card-head h4 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
}

.meta {
  font-size: 12px;
  color: #059669;
  background: var(--success-fade);
  border: 1px solid #a7f3d0;
  border-radius: 999px;
  padding: 3px 10px;
  font-weight: 500;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 24px 16px;
  font-size: 13px;
  color: var(--text-secondary);
}

.empty-illustration {
  opacity: 0.6;
}

.markdown-body {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary);
  padding: 10px 12px;
  background: linear-gradient(135deg, var(--success-fade), var(--warning-fade));
  border-radius: 10px;
  border: 1px solid #d1fae5;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 10px 0 6px;
  line-height: 1.35;
  color: var(--text-primary);
}

.markdown-body :deep(h1) {
  font-size: 16px;
  padding-bottom: 6px;
  border-bottom: 1px solid #d1fae5;
}

.markdown-body :deep(h2) {
  font-size: 15px;
  color: #047857;
}

.markdown-body :deep(h3) {
  font-size: 14px;
  color: #059669;
}

.markdown-body :deep(p) {
  margin: 6px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.markdown-body :deep(li) {
  margin: 3px 0;
}

.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--success-fade);
  border-radius: 4px;
  padding: 1px 5px;
  font-size: 12px;
  color: #047857;
}
</style>
