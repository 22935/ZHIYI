<template>
  <section class="generic-artifacts ui-surface">
    <header class="delivery-head">
      <div>
        <div class="eyebrow">任务成果</div>
        <div class="title-line">
          <h4>最终交付说明</h4>
          <span v-if="hasFinalResult" class="ready-state">已生成</span>
        </div>
        <p>面向使用者汇总结论、依据与下一步；运行过程保留在下方供审计。</p>
      </div>
      <div v-if="hasFinalResult" class="delivery-actions">
        <button type="button" class="quiet-action" @click="copyDelivery">
          {{ copied ? '已复制' : '复制成果' }}
        </button>
        <button type="button" class="primary-action" @click="downloadDelivery">
          下载 Markdown
        </button>
      </div>
    </header>

    <div v-if="!hasFinalResult" class="delivery-empty" :class="{ syncing: status === 'completed' }">
      <strong>{{ status === 'completed' ? '正在整理最终成果' : '等待任务完成' }}</strong>
      <span>
        {{ status === 'completed'
          ? '执行已经结束，正在同步最后一个节点的交付内容。'
          : '任务完成后，这里将提供可直接阅读和下载的成果说明。' }}
      </span>
    </div>

    <div v-else class="delivery-body">
      <article class="delivery-overview">
        <span class="artifact-kind">{{ artifactTypeLabel }}</span>
        <h5>{{ deliveryTitle }}</h5>
        <p v-if="executiveSummary">{{ executiveSummary }}</p>
      </article>

      <div v-if="hasStructuredDelivery" class="delivery-facts" aria-label="成果内容统计">
        <div><strong>{{ sections.length }}</strong><span>方案章节</span></div>
        <div><strong>{{ calculations.length }}</strong><span>计算依据</span></div>
        <div><strong>{{ assumptions.length }}</strong><span>明确假设</span></div>
        <div><strong>{{ openQuestions.length }}</strong><span>待确认事项</span></div>
      </div>

      <nav v-if="hasStructuredDelivery" class="delivery-tabs" role="tablist" aria-label="交付说明视图">
        <button
          v-for="tab in tabs"
          :key="tab.id"
          type="button"
          role="tab"
          :class="{ active: activeTab === tab.id }"
          :aria-selected="activeTab === tab.id"
          @click="activeTab = tab.id"
        >
          {{ tab.label }}
          <span>{{ tab.count }}</span>
        </button>
      </nav>

      <section v-if="hasStructuredDelivery && activeTab === 'solution'" class="tab-panel solution-sections" role="tabpanel">
        <article v-for="(section, index) in sections" :key="`${index}-${section.title}`" class="solution-section">
          <span class="section-index">{{ String(index + 1).padStart(2, '0') }}</span>
          <div>
            <h6>{{ section.title }}</h6>
            <p>{{ section.content }}</p>
            <div v-if="section.sourceFields.length" class="source-fields">
              <span v-for="field in section.sourceFields" :key="field">{{ field }}</span>
            </div>
          </div>
        </article>
      </section>

      <section v-else-if="hasStructuredDelivery && activeTab === 'calculations'" class="tab-panel calculation-list" role="tabpanel">
        <article v-for="(item, index) in calculations" :key="`${index}-${item.name}`" class="calculation-card">
          <div class="calculation-head">
            <h6>{{ item.name }}</h6>
            <strong>{{ item.result }}</strong>
          </div>
          <code>{{ item.formula }}</code>
          <dl v-if="item.inputs.length || item.assumptions.length">
            <template v-if="item.inputs.length">
              <dt>输入</dt><dd>{{ item.inputs.join('；') }}</dd>
            </template>
            <template v-if="item.assumptions.length">
              <dt>口径</dt><dd>{{ item.assumptions.join('；') }}</dd>
            </template>
          </dl>
        </article>
      </section>

      <section v-else-if="hasStructuredDelivery && activeTab === 'decisions'" class="tab-panel decision-grid" role="tabpanel">
        <article>
          <div class="decision-title"><h6>方案假设</h6><span>{{ assumptions.length }}</span></div>
          <ol v-if="assumptions.length"><li v-for="item in assumptions" :key="item">{{ item }}</li></ol>
          <p v-else class="muted">没有额外假设。</p>
        </article>
        <article>
          <div class="decision-title"><h6>待确认事项</h6><span>{{ openQuestions.length }}</span></div>
          <ol v-if="openQuestions.length"><li v-for="item in openQuestions" :key="item">{{ item }}</li></ol>
          <p v-else class="muted">没有未决事项。</p>
        </article>
        <footer v-if="sourceRefs.length">
          <span>来源引用</span>
          <code v-for="source in sourceRefs" :key="source">{{ source }}</code>
        </footer>
      </section>

      <article v-else class="report-fallback markdown-body" v-html="renderedReportHtml">
      </article>
    </div>

    <section v-if="stepOutputs.length" class="step-output-section">
      <header>
        <div>
          <h5>过程产出</h5>
          <p>节点级结构化结果，仅在追溯推理过程时展开。</p>
        </div>
        <span>{{ stepOutputs.length }} 项</span>
      </header>
      <div class="artifact-list">
        <details v-for="item in stepOutputs" :key="item.stepId">
          <summary>
            <span>{{ item.name }}</span>
            <small>{{ statusLabel(item.status) }}</small>
          </summary>
          <pre>{{ JSON.stringify(item.output, null, 2) }}</pre>
        </details>
      </div>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { AcgDeliverable, AcgFinalArtifact } from '@/services/api/workflow'
import { renderMarkdown } from '@/utils/markdown'

type DeliveryTab = 'solution' | 'calculations' | 'decisions'

interface DeliverySection {
  title: string
  content: string
  sourceFields: string[]
}

interface DeliveryCalculation {
  name: string
  formula: string
  result: string
  inputs: string[]
  assumptions: string[]
}

const props = withDefaults(defineProps<{
  stepOutputs: AcgDeliverable[]
  finalArtifacts: AcgFinalArtifact[]
  finalReport: string | null
  status?: string
}>(), {
  status: ''
})

const activeTab = ref<DeliveryTab>('solution')
const copied = ref(false)
let copiedTimer: ReturnType<typeof setTimeout> | null = null

onBeforeUnmount(() => {
  if (copiedTimer !== null) window.clearTimeout(copiedTimer)
})

const asRecord = (value: unknown): Record<string, any> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, any>
    : {}
)

const asText = (value: unknown): string => typeof value === 'string' ? value.trim() : ''
const asTextList = (value: unknown): string[] => Array.isArray(value)
  ? value.map(asText).filter(Boolean)
  : []

const primaryArtifact = computed(() => props.finalArtifacts[0] || null)
const structuredData = computed(() => asRecord(primaryArtifact.value?.structuredData))
const executiveSummary = computed(() => asText(structuredData.value.executiveSummary))
const reportContent = computed(() => (
  asText(primaryArtifact.value?.content)
  || asText(props.finalReport)
))
const reportHeading = computed(() => reportContent.value.match(/^#\s+(.+)$/m)?.[1]?.trim() || '')
const deliveryTitle = computed(() => {
  const artifactTitle = asText(primaryArtifact.value?.title)
  const isGenericTitle = /^workflow final report$/i.test(artifactTitle)
  return asText(structuredData.value.title)
    || (isGenericTitle ? reportHeading.value : artifactTitle)
    || reportHeading.value
    || '任务最终成果'
})
const renderedReportHtml = computed(() => renderMarkdown(reportContent.value))
const artifactTypeLabel = computed(() => {
  const type = asText(primaryArtifact.value?.type).toLowerCase()
  if (type === 'report') return '实施方案'
  return type || '最终成果'
})

const sections = computed<DeliverySection[]>(() => {
  if (!Array.isArray(structuredData.value.sections)) return []
  return structuredData.value.sections
    .map((value: unknown) => {
      const item = asRecord(value)
      return {
        title: asText(item.title) || '未命名章节',
        content: asText(item.content),
        sourceFields: asTextList(item.sourceFields)
      }
    })
    .filter((item: DeliverySection) => item.content)
})

const calculations = computed<DeliveryCalculation[]>(() => {
  if (!Array.isArray(structuredData.value.calculations)) return []
  return structuredData.value.calculations
    .map((value: unknown) => {
      const item = asRecord(value)
      return {
        name: asText(item.name) || '计算项',
        formula: asText(item.formula),
        result: asText(item.result),
        inputs: asTextList(item.inputs),
        assumptions: asTextList(item.assumptions)
      }
    })
    .filter((item: DeliveryCalculation) => item.formula || item.result)
})

const assumptions = computed(() => asTextList(structuredData.value.assumptions))
const openQuestions = computed(() => asTextList(structuredData.value.openQuestions))
const sourceRefs = computed(() => asTextList(structuredData.value.sourceRefs))
const hasStructuredDelivery = computed(() => Boolean(
  executiveSummary.value
  || sections.value.length
  || calculations.value.length
  || assumptions.value.length
  || openQuestions.value.length
))
const hasFinalResult = computed(() => Boolean(
  props.finalArtifacts.length || asText(props.finalReport)
))

const tabs = computed(() => [
  { id: 'solution' as const, label: '完整方案', count: sections.value.length },
  { id: 'calculations' as const, label: '计算依据', count: calculations.value.length },
  {
    id: 'decisions' as const,
    label: '假设与待确认',
    count: assumptions.value.length + openQuestions.value.length
  }
])

watch(() => primaryArtifact.value?.artifactId, () => {
  activeTab.value = 'solution'
  copied.value = false
})

const statusLabel = (status: string) => ({
  completed: '已完成',
  failed: '失败',
  running: '执行中',
  waiting_review: '待审核',
  retrying: '重试中',
  cancelled: '已取消'
})[status] || status

const deliveryMarkdown = computed(() => {
  if (!hasStructuredDelivery.value) return reportContent.value
  const lines = [`# ${deliveryTitle.value}`]
  if (executiveSummary.value) lines.push('', '## 执行摘要', '', executiveSummary.value)
  sections.value.forEach((section, index) => {
    lines.push('', `## ${index + 1}. ${section.title}`, '', section.content)
    if (section.sourceFields.length) lines.push('', `依据字段：${section.sourceFields.join('、')}`)
  })
  if (calculations.value.length) {
    lines.push('', '## 计算依据')
    calculations.value.forEach(item => {
      lines.push('', `### ${item.name}`, '', `- 公式：${item.formula}`, `- 结果：${item.result}`)
      if (item.inputs.length) lines.push(`- 输入：${item.inputs.join('；')}`)
      if (item.assumptions.length) lines.push(`- 口径：${item.assumptions.join('；')}`)
    })
  }
  if (assumptions.value.length) {
    lines.push('', '## 方案假设', '', ...assumptions.value.map(item => `- ${item}`))
  }
  if (openQuestions.value.length) {
    lines.push('', '## 待确认事项', '', ...openQuestions.value.map(item => `- ${item}`))
  }
  if (sourceRefs.value.length) lines.push('', '## 来源引用', '', ...sourceRefs.value.map(item => `- ${item}`))
  return lines.join('\n')
})

const copyDelivery = async () => {
  if (!deliveryMarkdown.value) return
  await navigator.clipboard.writeText(deliveryMarkdown.value)
  copied.value = true
  if (copiedTimer) window.clearTimeout(copiedTimer)
  copiedTimer = window.setTimeout(() => { copied.value = false }, 1600)
}

const downloadDelivery = () => {
  if (!deliveryMarkdown.value) return
  const blob = new Blob([deliveryMarkdown.value], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `${deliveryTitle.value.replace(/[\\/:*?"<>|]/g, '-')}–交付说明.md`
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.generic-artifacts {
  container-type: inline-size;
  padding: 18px;
  color: var(--text-primary);
}

.delivery-head,
.title-line,
.delivery-actions,
.step-output-section > header,
.calculation-head,
.decision-title {
  display: flex;
  align-items: center;
}

.delivery-head {
  justify-content: space-between;
  gap: 24px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--border-light);
}

.eyebrow {
  margin-bottom: 4px;
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: .12em;
}

.title-line { gap: 10px; }
.title-line h4 { margin: 0; font-size: 18px; line-height: 1.35; }
.delivery-head p,
.step-output-section header p { margin: 5px 0 0; color: var(--text-secondary); font-size: 12px; }

.ready-state {
  padding: 3px 8px;
  border: 1px solid color-mix(in srgb, var(--success) 35%, var(--border-light));
  border-radius: 999px;
  color: var(--success);
  background: color-mix(in srgb, var(--success) 8%, transparent);
  font-size: 11px;
  font-weight: 700;
}

.delivery-actions { flex: none; gap: 8px; }
.delivery-actions button,
.delivery-tabs button {
  border: 1px solid var(--border-light);
  border-radius: 7px;
  font: inherit;
  cursor: pointer;
  transition: border-color .16s ease, background-color .16s ease, color .16s ease;
}
.delivery-actions button { min-height: 34px; padding: 0 12px; font-size: 12px; font-weight: 650; }
.quiet-action { color: var(--text-primary); background: var(--bg-panel); }
.primary-action { color: #fff; border-color: var(--primary-color) !important; background: var(--primary-color); }
.delivery-actions button:hover { border-color: var(--primary-color); }
.delivery-actions button:focus-visible,
.delivery-tabs button:focus-visible,
summary:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

.delivery-empty {
  display: grid;
  gap: 6px;
  margin-top: 16px;
  padding: 24px;
  border: 1px dashed var(--border-light);
  border-radius: 10px;
  background: var(--bg-input);
  text-align: center;
}
.delivery-empty strong { font-size: 14px; }
.delivery-empty span { color: var(--text-secondary); font-size: 12px; }
.delivery-empty.syncing { border-style: solid; }

.delivery-body { padding-top: 16px; }
.delivery-overview {
  padding: 20px;
  border-radius: 10px;
  background: color-mix(in srgb, var(--primary-color) 7%, var(--bg-panel));
}
.artifact-kind { color: var(--primary-color); font-size: 11px; font-weight: 700; }
.delivery-overview h5 { margin: 7px 0 8px; font-size: 20px; line-height: 1.4; text-wrap: pretty; }
.delivery-overview p { max-width: 1080px; margin: 0; color: var(--text-secondary); font-size: 14px; line-height: 1.8; white-space: pre-wrap; }

.delivery-facts {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 12px 0;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  overflow: hidden;
}
.delivery-facts div { display: grid; gap: 2px; padding: 12px 14px; border-right: 1px solid var(--border-light); }
.delivery-facts div:last-child { border-right: 0; }
.delivery-facts strong { font-size: 18px; }
.delivery-facts span { color: var(--text-secondary); font-size: 11px; }

.delivery-tabs { display: flex; gap: 6px; margin: 16px 0 12px; }
.delivery-tabs button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 11px;
  color: var(--text-secondary);
  background: var(--bg-panel);
  font-size: 12px;
}
.delivery-tabs button span { font-family: var(--font-mono, monospace); font-size: 10px; }
.delivery-tabs button.active { color: var(--primary-color); border-color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 8%, var(--bg-panel)); }

.tab-panel { min-height: 140px; }
.solution-sections { display: grid; gap: 8px; }
.solution-section {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  background: var(--bg-panel);
}
.section-index { color: var(--primary-color); font-family: var(--font-mono, monospace); font-size: 12px; font-weight: 700; }
.solution-section h6,
.calculation-card h6,
.decision-grid h6 { margin: 0; font-size: 13px; }
.solution-section p { margin: 6px 0 0; color: var(--text-secondary); font-size: 13px; line-height: 1.75; white-space: pre-wrap; }
.source-fields { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.source-fields span,
.decision-grid footer code {
  padding: 2px 6px;
  border-radius: 5px;
  color: var(--text-secondary);
  background: var(--bg-input);
  font-family: var(--font-mono, monospace);
  font-size: 10px;
}

.calculation-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 9px; }
.calculation-card { padding: 14px; border: 1px solid var(--border-light); border-radius: 9px; background: var(--bg-panel); }
.calculation-head { justify-content: space-between; gap: 12px; }
.calculation-head strong { color: var(--primary-color); font-size: 13px; text-align: right; }
.calculation-card > code { display: block; margin: 10px 0; color: var(--text-primary); font-size: 11px; white-space: normal; }
.calculation-card dl { display: grid; grid-template-columns: 42px 1fr; gap: 5px 8px; margin: 0; font-size: 11px; }
.calculation-card dt { color: var(--text-secondary); }
.calculation-card dd { margin: 0; line-height: 1.6; }

.decision-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.decision-grid > article { padding: 14px; border: 1px solid var(--border-light); border-radius: 9px; background: var(--bg-panel); }
.decision-title { justify-content: space-between; }
.decision-title span { color: var(--primary-color); font-family: var(--font-mono, monospace); font-size: 11px; }
.decision-grid ol { margin: 10px 0 0; padding-left: 22px; }
.decision-grid li { margin: 0 0 7px; padding-left: 3px; color: var(--text-secondary); font-size: 12px; line-height: 1.6; }
.decision-grid footer { grid-column: 1 / -1; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; color: var(--text-secondary); font-size: 11px; }
.muted { color: var(--text-secondary); font-size: 12px; }
.report-fallback {
  padding: 4px 2px 18px;
  color: var(--text-primary);
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.75;
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) { margin: 20px 0 9px; color: var(--text-primary); line-height: 1.4; }
.markdown-body :deep(h1) { margin-top: 0; padding-bottom: 10px; border-bottom: 1px solid var(--border-light); font-size: 22px; }
.markdown-body :deep(h2) { padding-bottom: 6px; border-bottom: 1px solid var(--border-light); font-size: 17px; }
.markdown-body :deep(h3) { font-size: 14px; }
.markdown-body :deep(p) { margin: 7px 0; color: var(--text-secondary); }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 8px 0 12px; padding-left: 24px; }
.markdown-body :deep(li) { margin: 5px 0; color: var(--text-secondary); }
.markdown-body :deep(strong) { color: var(--text-primary); font-weight: 750; }
.markdown-body :deep(code) { padding: 2px 5px; border-radius: 4px; background: var(--bg-input); font: 12px var(--font-mono, monospace); }
.markdown-body :deep(pre) { padding: 12px; overflow-x: auto; border: 1px solid var(--border-light); border-radius: 8px; background: var(--bg-input); }
.markdown-body :deep(pre code) { padding: 0; background: transparent; }
.markdown-body :deep(blockquote) { margin: 10px 0; padding: 8px 14px; border-left: 3px solid var(--primary-color); background: color-mix(in srgb, var(--primary-color) 5%, transparent); color: var(--text-secondary); }
.markdown-body :deep(a) { color: var(--primary-color); text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(.markdown-table-wrap) { margin: 12px 0 18px; overflow-x: auto; border: 1px solid var(--border-light); border-radius: 8px; }
.markdown-body :deep(table) { width: 100%; border-collapse: collapse; background: var(--bg-panel); font-size: 12px; }
.markdown-body :deep(th),
.markdown-body :deep(td) { min-width: 110px; padding: 9px 11px; border-right: 1px solid var(--border-light); border-bottom: 1px solid var(--border-light); text-align: left; vertical-align: top; }
.markdown-body :deep(th) { color: var(--text-primary); background: var(--bg-input); font-weight: 700; }
.markdown-body :deep(th:last-child),
.markdown-body :deep(td:last-child) { border-right: 0; }
.markdown-body :deep(tbody tr:last-child td) { border-bottom: 0; }

.step-output-section { margin-top: 20px; padding-top: 16px; border-top: 1px solid var(--border-light); }
.step-output-section > header { justify-content: space-between; margin-bottom: 9px; }
.step-output-section h5 { margin: 0; font-size: 14px; }
.step-output-section > header > span { color: var(--text-secondary); font-size: 12px; }
.artifact-list { display: flex; flex-direction: column; gap: 7px; }
details { border: 1px solid var(--border-light); border-radius: 8px; background: var(--bg-panel); }
summary { display: flex; justify-content: space-between; gap: 16px; padding: 10px 12px; cursor: pointer; font-size: 12px; font-weight: 650; }
summary small { color: var(--text-secondary); font-weight: 500; }
details pre { max-height: 360px; margin: 0; padding: 12px; overflow: auto; border-top: 1px solid var(--border-light); background: var(--bg-input); white-space: pre-wrap; overflow-wrap: anywhere; font: 11px/1.6 var(--font-mono, monospace); }

@container (max-width: 760px) {
  .delivery-head { align-items: flex-start; flex-direction: column; }
  .delivery-actions { width: 100%; }
  .delivery-actions button { flex: 1; }
  .delivery-facts { grid-template-columns: repeat(2, 1fr); }
  .delivery-facts div:nth-child(2) { border-right: 0; }
  .delivery-facts div:nth-child(-n+2) { border-bottom: 1px solid var(--border-light); }
  .calculation-list,
  .decision-grid { grid-template-columns: 1fr; }
  .decision-grid footer { grid-column: 1; }
  .delivery-tabs { overflow-x: auto; }
  .delivery-tabs button { flex: none; }
}

@media (prefers-reduced-motion: reduce) {
  .delivery-actions button,
  .delivery-tabs button { transition: none; }
}
</style>
