<template>
  <details v-if="isPrimitive && collapsible && isLongText" class="structured-value__disclosure" :open="expanded">
    <summary @click.stop.prevent="expanded = !expanded">
      <span v-if="!expanded" class="structured-value__preview">{{ previewText }}</span>
      <span class="structured-value__disclosure-action">{{ expanded ? '收起结论' : '展开完整结论' }}</span>
      <span class="structured-value__disclosure-count">{{ primitiveText.length }} 字符</span>
    </summary>
    <template v-if="expanded">
      <div v-if="markdown" class="structured-value__markdown markdown-body is-long" v-html="renderedMarkdown" />
      <span v-else class="structured-value__text" :class="[primitiveKindClass, { 'is-long': isLongText }]">{{ primitiveText }}</span>
    </template>
  </details>
  <div v-else-if="isPrimitive && markdown" class="structured-value__markdown markdown-body" v-html="renderedMarkdown" />
  <span
    v-else-if="isPrimitive"
    class="structured-value__text"
    :class="[primitiveKindClass, { 'is-long': isLongText }]"
  >{{ primitiveText }}</span>
  <div v-else-if="Array.isArray(value)" class="structured-value__list">
    <article v-for="(item, index) in value" :key="`${depth}-${index}`" class="structured-value__item">
      <span class="structured-value__index">{{ String(index + 1).padStart(2, '0') }}</span>
      <div class="structured-value__item-value">
        <StructuredValue :value="item" :depth="depth + 1" :collapsible="collapsible" />
      </div>
    </article>
  </div>
  <dl v-else class="structured-value__object">
    <div v-for="[key, item] in objectEntries" :key="key" class="structured-value__field" :class="{ 'is-narrative': isRichTextKey(key) || isLongValue(item) }">
      <dt>
        <span>{{ labelForKey(key) }}</span>
      </dt>
      <dd><StructuredValue :value="item" :depth="depth + 1" :markdown="isRichTextKey(key)" :collapsible="collapsible" /></dd>
    </div>
  </dl>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { renderMarkdown } from '@/utils/markdown'
import { documentEntries } from '@/workbench/runtime/documentContent'

defineOptions({ name: 'StructuredValue' })

const props = withDefaults(defineProps<{
  value: unknown
  depth?: number
  markdown?: boolean
  collapsible?: boolean
}>(), {
  depth: 0,
  markdown: false,
  collapsible: false
})

const expanded = ref(false)
watch(() => props.value, () => { expanded.value = false })

const isRecord = (value: unknown): value is Record<string, unknown> => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)
const isPrimitive = computed(() => !Array.isArray(props.value) && !isRecord(props.value))
const primitiveText = computed(() => {
  if (props.value == null) return '—'
  if (typeof props.value === 'boolean') return props.value ? 'true' : 'false'
  if (typeof props.value === 'string') return props.value
  return String(props.value)
})
const primitiveKindClass = computed(() => {
  if (props.value == null) return 'is-null'
  if (typeof props.value === 'boolean') return 'is-boolean'
  if (typeof props.value === 'number') return 'is-number'
  return 'is-text'
})
const isLongValue = (value: unknown) => typeof value === 'string' && (value.length > 180 || value.includes('\n'))
const isLongText = computed(() => typeof props.value === 'string' && (props.value.length > 180 || props.value.includes('\n')))
const previewText = computed(() => {
  const normalized = primitiveText.value.replace(/\s+/g, ' ').trim()
  return normalized.length > 180 ? `${normalized.slice(0, 180)}…` : normalized
})
const narrativeSource = computed(() => {
  if (!isLongText.value || primitiveText.value.includes('\n')) return primitiveText.value
  return primitiveText.value.replace(/([。！？；;])\s*/g, '$1\n')
})
const renderedMarkdown = computed(() => renderMarkdown(narrativeSource.value))
const objectEntries = computed(() => isRecord(props.value) ? documentEntries(props.value) : [])
const labels: Record<string, string> = {
  overview: '\u6982\u8981',
  objective: '\u76ee\u6807',
  summary: '\u6458\u8981',
  phases: '\u9636\u6bb5',
  deliverables: '\u4ea4\u4ed8\u7269',
  dependencies: '\u4f9d\u8d56',
  milestones: '\u91cc\u7a0b\u7891',
  acceptance_criteria: '\u9a8c\u6536\u6807\u51c6',
  constraints: '\u7ea6\u675f',
  assumptions: '\u5047\u8bbe',
  risks: '\u98ce\u9669',
  content: '\u5185\u5bb9',
  architecture: '\u67b6\u6784\u65b9\u6848',
  deployment: '\u90e8\u7f72\u65b9\u6848',
  rationale: '\u8bbe\u8ba1\u4f9d\u636e',
  style: '\u65b9\u6848\u98ce\u683c',
  components: '\u7cfb\u7edf\u7ec4\u4ef6',
  interfaces: '\u63a5\u53e3\u8bbe\u8ba1',
  data_flow: '\u6570\u636e\u6d41',
  dataFlow: '\u6570\u636e\u6d41',
  name: '\u540d\u79f0',
  status: '\u72b6\u6001',
  source: '\u6765\u6e90'
}
const labelForKey = (key: string) => labels[key] || key.split('_').join(' ')
const isRichTextKey = (key: string) => ['content', 'overview', 'description', 'summary', 'final_answer', 'report', 'report_markdown'].includes(key)
</script>

<style scoped>
.structured-value__text { display: block; min-width: 0; color: var(--wb-text-secondary); font-weight: 450; line-height: 1.65; white-space: pre-wrap; overflow-wrap: anywhere; text-wrap: pretty; }
.structured-value__text.is-long { padding: 11px 14px; border-left: 2px solid color-mix(in srgb, var(--wb-accent) 52%, var(--wb-border)); border-radius: 0 var(--wb-radius-sm) var(--wb-radius-sm) 0; background: color-mix(in srgb, var(--wb-surface-inset) 82%, transparent); color: var(--wb-text); font-size: 12px; font-weight: 480; line-height: 1.85; }
.structured-value__text.is-number, .structured-value__text.is-boolean { color: var(--wb-accent); font-family: var(--font-mono, monospace); font-weight: 650; }
.structured-value__text.is-null { color: var(--wb-text-muted); }
.structured-value__disclosure { min-width: 0; }
.structured-value__disclosure > summary { display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; align-items: baseline; gap: 8px; padding: 9px 11px; border-left: 2px solid var(--wb-accent); border-radius: 0 var(--wb-radius-sm) var(--wb-radius-sm) 0; color: var(--wb-text-secondary); background: color-mix(in srgb, var(--wb-surface-inset) 74%, transparent); cursor: pointer; list-style: none; }
.structured-value__disclosure > summary::-webkit-details-marker { display: none; }
.structured-value__disclosure > summary::before { content: '▸'; color: var(--wb-accent); font: 11px var(--font-mono, monospace); }
.structured-value__disclosure[open] > summary::before { content: '▾'; }
.structured-value__preview { min-width: 0; overflow: hidden; color: var(--wb-text-secondary); font-size: 11px; line-height: 1.6; text-overflow: ellipsis; white-space: nowrap; }
.structured-value__disclosure-action { flex: 0 0 auto; color: var(--wb-accent); font-size: 10px; font-weight: 650; }
.structured-value__disclosure-count { flex: 0 0 auto; color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.structured-value__disclosure > .structured-value__text.is-long, .structured-value__disclosure > .structured-value__markdown.is-long { margin-top: 6px; }
.structured-value__markdown { min-width: 0; color: var(--wb-text-secondary); line-height: 1.75; overflow-wrap: anywhere; text-wrap: pretty; }
.structured-value__markdown :deep(h1), .structured-value__markdown :deep(h2), .structured-value__markdown :deep(h3) { margin: 0 0 7px; color: var(--wb-text); line-height: 1.35; }
.structured-value__markdown :deep(h1) { font-size: 16px; }
.structured-value__markdown :deep(h2) { font-size: 14px; }
.structured-value__markdown :deep(h3) { font-size: 13px; }
.structured-value__markdown :deep(p), .structured-value__markdown :deep(li) { margin: 0 0 7px; }
.structured-value__markdown :deep(ul), .structured-value__markdown :deep(ol) { margin: 0 0 5px; padding-left: 18px; }
.structured-value__markdown :deep(pre) { max-width: 100%; overflow: auto; padding: 6px 8px; background: var(--wb-surface-inset); font: 10px/1.5 var(--font-mono, monospace); }
.structured-value__list { display: grid; gap: 6px; min-width: 0; }
.structured-value__item { display: grid; grid-template-columns: 24px minmax(0, 1fr); gap: 8px; min-width: 0; padding: 8px 0; border-bottom: 1px solid color-mix(in srgb, var(--wb-border-soft) 72%, transparent); }
.structured-value__item:last-child { border-bottom: 0; }
.structured-value__index { color: var(--wb-accent); font: 650 10px/1.6 var(--font-mono, monospace); text-align: right; }
.structured-value__item-value { min-width: 0; }
.structured-value__object { display: grid; gap: 0; min-width: 0; margin: 0; }
.structured-value__field { display: grid; grid-template-columns: minmax(104px, 24%) minmax(0, 1fr); gap: 12px; min-width: 0; padding: 6px 0; border-bottom: 1px solid color-mix(in srgb, var(--wb-border-soft) 58%, transparent); }
.structured-value__field:last-child { border-bottom: 0; }
.structured-value__field.is-narrative { grid-template-columns: 1fr; gap: 5px; }
.structured-value__field dt { display: flex; align-items: baseline; gap: 6px; color: var(--wb-text-secondary); font-size: 11px; font-weight: 650; }
.structured-value__field.is-narrative dt { color: var(--wb-accent); font-weight: 700; }
.structured-value__field dt code { color: var(--wb-text-muted); font: 500 9px var(--font-mono, monospace); opacity: .72; }
.structured-value__field dd { min-width: 0; margin: 0; }
</style>
