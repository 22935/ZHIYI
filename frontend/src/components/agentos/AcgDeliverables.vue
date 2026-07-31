<!-- ACG 交付物面板 — 双 Tab 展示合同审查交付物：Markdown 最终报告和按步骤拆分的结构化产物 -->
<template>
  <section class="acg-deliverables ui-surface">
    <header class="panel-head">
      <div class="head-left">
        <el-icon class="head-icon"><Document /></el-icon>
        <h4>审查交付物</h4>
      </div>
      <div class="tabs" v-if="hasReport">
        <button :class="{ active: tab === 'report' }" @click="tab = 'report'">审查报告</button>
        <button :class="{ active: tab === 'detail' }" @click="tab = 'detail'">分步结论</button>
      </div>
    </header>

    <div v-if="!deliverables.length" class="empty">暂无交付物，请先运行 ACG 引擎</div>

    <!-- 最终报告（Markdown 渲染） -->
    <div v-else-if="tab === 'report' && hasReport" class="report-body">
      <article class="report-md markdown-body" v-html="renderedReportHtml" />
    </div>

    <!-- 分步结论：风险 / 证据 / 建议 等结构化产出 -->
    <div v-else class="detail-body">
      <div v-for="d in structuredDeliverables" :key="d.stepId" class="deliverable-block">
        <div class="block-head">
          <span class="block-name">{{ d.name }}</span>
          <span class="block-step">{{ d.stepId }}</span>
        </div>

        <!-- 风险项 -->
        <ul v-if="d.risks.length" class="risk-list">
          <li v-for="(r, i) in d.risks" :key="i" class="risk-item">
            <span class="risk-level" :class="riskClass(r)">{{ riskLabel(r) }}</span>
            <div class="risk-body">
              <div class="risk-title">{{ r.title || r.name || r.clause || ('风险 ' + (i + 1)) }}</div>
              <div class="risk-desc" v-if="r.description || r.reason">{{ r.description || r.reason }}</div>
              <div class="risk-sug" v-if="r.suggestion">建议：{{ r.suggestion }}</div>
            </div>
          </li>
        </ul>

        <!-- 证据 / 依据 -->
        <ul v-if="d.evidences.length" class="evidence-list">
          <li v-for="(e, i) in d.evidences" :key="i" class="evidence-item">
            <span class="ev-source">{{ e.sourceName || e.source || e.sourceType || '依据' }}</span>
            <span class="ev-text">{{ e.citationText || e.content || e.title || '' }}</span>
          </li>
        </ul>

        <!-- 修改建议 -->
        <ul v-if="d.suggestions.length" class="suggest-list">
          <li v-for="(s, i) in d.suggestions" :key="i">{{ typeof s === 'string' ? s : (s.suggestion || s.content || JSON.stringify(s)) }}</li>
        </ul>

        <!-- 其他纯文本/标量字段 -->
        <div v-if="d.summary" class="block-summary">{{ d.summary }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Document } from '@element-plus/icons-vue'
import type { AcgDeliverable } from '@/services/api/workflow'

const props = withDefaults(defineProps<{
  deliverables?: AcgDeliverable[]
  finalReport?: string | null
}>(), {
  deliverables: () => [],
  finalReport: null
})

const hasReport = computed(() => !!props.finalReport && props.finalReport.trim().length > 0)
const tab = ref<'report' | 'detail'>('detail')

watch(hasReport, (v) => { if (v) tab.value = 'report' }, { immediate: true })

const asArray = (v: any): any[] => (Array.isArray(v) ? v : [])

const escapeHtml = (raw: string) =>
  raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')

const escapeAttr = (raw: string) => escapeHtml(raw).replace(/"/g, '&quot;')
const isSafeUrl = (url: string) => /^(https?:\/\/|mailto:|\/)/i.test(url)

const applyInlineMarkdown = (value: string) => {
  let text = value
  text = text.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_all, label, url) => {
    const safe = String(url || '').trim()
    if (!isSafeUrl(safe)) return label
    return `<a href="${escapeAttr(safe)}" target="_blank" rel="noopener noreferrer">${label}</a>`
  })
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  text = text.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>')
  return text
}

const markdownToHtml = (raw: string) => {
  if (!raw) return ''

  const codeBlocks: string[] = []
  const stripped = raw.replace(/```([a-zA-Z0-9_-]+)?\n?([\s\S]*?)```/g, (_m, lang, code) => {
    const language = (lang || '').trim()
    const escapedCode = escapeHtml(String(code || '').replace(/\n$/, ''))
    const className = language ? ` class="language-${escapeAttr(language)}"` : ''
    const token = `@@CODE_BLOCK_${codeBlocks.length}@@`
    codeBlocks.push(`<pre><code${className}>${escapedCode}</code></pre>`)
    return token
  })

  const lines = stripped.split(/\r?\n/)
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

  lines.forEach((line) => {
    const trimmed = line.trim()
    if (!trimmed) {
      closeLists()
      return
    }

    if (/^@@CODE_BLOCK_\d+@@$/.test(trimmed)) {
      closeLists()
      output.push(trimmed)
      return
    }

    const escaped = escapeHtml(trimmed)
    const heading = escaped.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      closeLists()
      const level = Math.min(6, heading[1].length)
      output.push(`<h${level}>${applyInlineMarkdown(heading[2])}</h${level}>`)
      return
    }

    const ul = escaped.match(/^[-*]\s+(.+)$/)
    if (ul) {
      if (!inUl) {
        closeLists()
        output.push('<ul>')
        inUl = true
      }
      output.push(`<li>${applyInlineMarkdown(ul[1])}</li>`)
      return
    }

    const ol = escaped.match(/^\d+\.\s+(.+)$/)
    if (ol) {
      if (!inOl) {
        closeLists()
        output.push('<ol>')
        inOl = true
      }
      output.push(`<li>${applyInlineMarkdown(ol[1])}</li>`)
      return
    }

    closeLists()
    output.push(`<p>${applyInlineMarkdown(escaped)}</p>`)
  })

  closeLists()
  let html = output.join('\n')
  codeBlocks.forEach((block, index) => {
    html = html.replace(`@@CODE_BLOCK_${index}@@`, block)
  })
  return html
}

const renderedReportHtml = computed(() => markdownToHtml(props.finalReport || ''))

// 从各步骤 output 中提取结构化结论（风险/证据/建议/摘要）
const structuredDeliverables = computed(() => {
  return props.deliverables
    .map((d) => {
      const o = d.output || {}
      return {
        stepId: d.stepId,
        name: d.name,
        risks: asArray(o.risks),
        evidences: asArray(o.evidences || o.citations),
        suggestions: asArray(o.revision_suggestions || o.suggestions),
        summary: o.risk_summary || o.contract_summary || o.summary || ''
      }
    })
    .filter((d) => d.risks.length || d.evidences.length || d.suggestions.length || d.summary)
})

const riskLevel = (r: any): string => (r.level || r.risk_level || r.severity || '').toString().toLowerCase()
const riskLabel = (r: any) => {
  const l = riskLevel(r)
  if (l.includes('high') || l.includes('高')) return '高'
  if (l.includes('mid') || l.includes('medium') || l.includes('中')) return '中'
  if (l.includes('low') || l.includes('低')) return '低'
  return '风险'
}
const riskClass = (r: any) => {
  const l = riskLevel(r)
  if (l.includes('high') || l.includes('高')) return 'high'
  if (l.includes('mid') || l.includes('medium') || l.includes('中')) return 'mid'
  return 'low'
}
</script>

<style scoped>
.acg-deliverables { display: flex; flex-direction: column; }
.panel-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-sm); }
.head-left { display: flex; align-items: center; gap: 6px; }
.head-icon { font-size: 15px; color: var(--primary-color); }
.panel-head h4 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); }
.tabs { display: flex; gap: 4px; }
.tabs button {
  padding: 4px 10px; font-size: 12px; border: 1px solid var(--border-light);
  background: var(--bg-input); color: var(--text-secondary); border-radius: 6px; cursor: pointer;
}
.tabs button.active { background: var(--primary-color); color: #fff; border-color: var(--primary-color); }

.empty { padding: 32px 12px; text-align: center; color: var(--text-secondary); font-size: 13px; }

.report-body { max-height: 460px; overflow-y: auto; }
.report-md {
  word-break: break-word; font-size: 13px; line-height: 1.7;
  color: var(--text-primary); margin: 0; font-family: inherit;
  background: var(--bg-panel); padding: var(--space-md); border-radius: var(--radius-md);
  border: 1px solid var(--border-light);
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
  margin: 14px 0 8px;
  font-weight: 800;
  line-height: 1.35;
  color: var(--text-primary);
}
.markdown-body :deep(h1) { font-size: 20px; margin-top: 0; padding-bottom: 8px; border-bottom: 1px solid var(--border-light); }
.markdown-body :deep(h2) { font-size: 16px; margin-top: 18px; }
.markdown-body :deep(h3) { font-size: 14px; }
.markdown-body :deep(p) { margin: 6px 0; color: var(--text-primary); }
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 6px 0 10px 18px;
  padding: 0;
}
.markdown-body :deep(li) {
  margin: 4px 0;
  padding-left: 2px;
}
.markdown-body :deep(strong) { font-weight: 800; color: var(--text-primary); }
.markdown-body :deep(em) { color: var(--text-secondary); }
.markdown-body :deep(code) {
  padding: 1px 5px;
  border-radius: 4px;
  background: var(--bg-input);
  color: var(--primary-color);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
}
.markdown-body :deep(pre) {
  margin: 8px 0;
  padding: 10px;
  overflow-x: auto;
  border-radius: 6px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
}
.markdown-body :deep(pre code) {
  padding: 0;
  background: transparent;
  color: var(--text-primary);
}
.markdown-body :deep(a) {
  color: var(--primary-color);
  text-decoration: none;
}
.markdown-body :deep(a:hover) { text-decoration: underline; }

.detail-body { max-height: 460px; overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-md); }
.deliverable-block { border: 1px solid var(--border-light); border-radius: var(--radius-md); padding: var(--space-sm); background: var(--bg-panel); }
.block-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.block-name { font-size: 13px; font-weight: 700; color: var(--text-primary); }
.block-step { font-size: 11px; color: var(--text-secondary); font-family: monospace; }

.risk-list, .evidence-list, .suggest-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.risk-item { display: flex; gap: 8px; padding: 6px; background: var(--bg-input); border-radius: 6px; }
.risk-level { flex: 0 0 auto; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; border-radius: 50%; font-size: 11px; font-weight: 700; color: #fff; }
.risk-level.high { background: var(--danger); }
.risk-level.mid { background: var(--warning); }
.risk-level.low { background: var(--info); }
.risk-body { flex: 1; }
.risk-title { font-size: 12px; font-weight: 600; color: var(--text-primary); }
.risk-desc { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.risk-sug { font-size: 12px; color: var(--success); margin-top: 2px; }

.evidence-item { display: flex; flex-direction: column; gap: 2px; padding: 6px; background: var(--bg-input); border-radius: 6px; }
.ev-source { font-size: 11px; font-weight: 600; color: var(--primary-color); }
.ev-text { font-size: 12px; color: var(--text-secondary); }

.suggest-list li { font-size: 12px; color: var(--text-primary); padding: 6px 8px; background: var(--bg-input); border-radius: 6px; }
.block-summary { font-size: 12px; color: var(--text-secondary); margin-top: 6px; line-height: 1.6; }
</style>
