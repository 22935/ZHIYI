<!-- 庭审提纲查看器 — 将 Markdown 格式庭审提纲渲染为 HTML 展示 -->
<template>
  <section class="card">
    <header class="card-head">
      <h4>庭审提纲</h4>
      <span class="hint">Markdown 展示</span>
    </header>

    <div v-if="!outlineMarkdown" class="empty">暂无庭审提纲内容</div>
    <article v-else class="markdown-body" v-html="renderedHtml" />
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface HearingOutlineResult {
  outline_markdown?: string
  outline?: string
}

const props = defineProps<{
  data?: HearingOutlineResult
}>()

const outlineMarkdown = computed(() => (props.data?.outline_markdown || props.data?.outline || '').trim())

const escapeHtml = (raw: string) => {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

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

const renderedHtml = computed(() => toMarkdownHtml(outlineMarkdown.value))
</script>

<style scoped>
.card {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--surface-solid);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-head h4 {
  margin: 0;
  font-size: 14px;
  color: var(--text-primary);
}

.hint {
  font-size: 12px;
  color: #1d4ed8;
  background: var(--primary-fade);
  border: 1px solid #bfdbfe;
  border-radius: 999px;
  padding: 2px 8px;
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
}

.markdown-body {
  font-size: 13px;
  line-height: 1.65;
  color: var(--text-primary);
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3) {
  margin: 8px 0;
  line-height: 1.35;
  color: var(--text-primary);
}

.markdown-body :deep(h1) {
  font-size: 16px;
}

.markdown-body :deep(h2) {
  font-size: 15px;
}

.markdown-body :deep(h3) {
  font-size: 14px;
}

.markdown-body :deep(p) {
  margin: 6px 0;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 6px 0;
  padding-left: 20px;
}

.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  background: var(--bg-input);
  border-radius: 4px;
  padding: 0 4px;
}
</style>
