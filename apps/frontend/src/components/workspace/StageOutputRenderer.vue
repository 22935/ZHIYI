<template>
  <div class="stage-output-viewer" data-testid="task-stage-output">
    <article v-if="reportText" class="stage-output-viewer__document markdown-body" v-html="renderedReport" />
    <template v-else-if="isStructured">
      <div class="stage-output-viewer__sections">
        <section v-for="section in sections" :key="section.key" class="stage-output-viewer__section">
          <button
            type="button"
            class="stage-output-viewer__section-head"
            :aria-expanded="isSectionOpen(section.key)"
            @click="toggleSection(section.key)"
          >
            <span class="stage-output-viewer__section-title">
              <span class="stage-output-viewer__fold" aria-hidden="true">{{ isSectionOpen(section.key) ? '▾' : '▸' }}</span>
              <span>{{ labelForKey(section.key) }}</span>
              <span v-if="sectionCount(section.value) !== null" class="stage-output-viewer__section-count">
                · {{ sectionCount(section.value) }}
              </span>
            </span>
          </button>

          <div v-if="isSectionOpen(section.key)" class="stage-output-viewer__section-body">
            <div v-if="Array.isArray(section.value)" class="stage-output-viewer__list">
              <EditorObjectRow
                v-for="(item, index) in section.value"
                :key="`${section.key}-${index}`"
                tag="article"
                :index="padIndex(index)"
                :selected="selectedId === selectionId(section.key, index)"
                :interactive="true"
                class="stage-output-viewer__item"
                role="button"
                tabindex="0"
                @click="emit('select', selectionFor(section.key, index, item))"
                @keydown.enter.prevent="emit('select', selectionFor(section.key, index, item))"
                @keydown.space.prevent="emit('select', selectionFor(section.key, index, item))"
              >
                <div class="stage-output-viewer__item-content">
                  <template v-if="isRecord(item)">
                    <StructuredValue
                      v-if="primaryEntry(item)"
                      :value="primaryEntry(item)?.[1]"
                      :markdown="isRichTextKey(primaryEntry(item)?.[0] || '')"
                      :collapsible="true"
                    />
                    <div v-if="metadataEntries(item).length" class="stage-output-viewer__metadata">
                      <template v-for="[fieldKey, fieldValue] in metadataEntries(item)" :key="fieldKey">
                        <button
                          v-if="isReferenceKey(fieldKey)"
                          type="button"
                          class="stage-output-viewer__meta stage-output-viewer__meta--reference"
                          @click.stop="emit('reference', selectionFor(section.key, index, item))"
                        >{{ displayMetadata(fieldKey, fieldValue) }}</button>
                        <span v-else class="stage-output-viewer__meta" :class="metadataClass(fieldKey, fieldValue)">
                          {{ displayMetadata(fieldKey, fieldValue) }}
                        </span>
                      </template>
                    </div>
                    <dl v-if="secondaryEntries(item).length" class="stage-output-viewer__fields">
                      <div v-for="[fieldKey, fieldValue] in secondaryEntries(item)" :key="fieldKey" :class="fieldToneClass(fieldKey, fieldValue)">
                        <dt>{{ labelForKey(fieldKey) }}</dt>
                        <dd :class="valueClass(fieldValue)"><StructuredValue :value="fieldValue" :markdown="isRichTextKey(fieldKey)" :collapsible="true" /></dd>
                      </div>
                    </dl>
                  </template>
                  <p v-else class="stage-output-viewer__semantic">{{ displayValue(item) }}</p>
                </div>
              </EditorObjectRow>
            </div>

            <dl v-else-if="isRecord(section.value)" class="stage-output-viewer__fields stage-output-viewer__fields--record">
              <div
                v-for="[fieldKey, fieldValue] in recordEntries(section.value)"
                :key="fieldKey"
                :class="{ ...fieldClass(fieldKey, fieldValue), ...fieldToneClass(fieldKey, fieldValue) }"
              >
                <dt class="stage-output-viewer__field-label">
                  <span>{{ labelForKey(fieldKey) }}</span>
                </dt>
                <dd :class="valueClass(fieldValue)"><StructuredValue :value="fieldValue" :markdown="isRichTextKey(fieldKey)" :collapsible="true" /></dd>
              </div>
            </dl>
            <p v-else class="stage-output-viewer__semantic">{{ displayValue(section.value) }}</p>
          </div>
        </section>
      </div>

    </template>

    <article v-else class="stage-output-viewer__document markdown-body" v-html="renderedText" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import EditorObjectRow from './EditorObjectRow.vue'
import StructuredValue from './StructuredValue.vue'
import { renderMarkdown } from '@/utils/markdown'
import { documentEntries, reportContent, withoutRepeatedTitle } from '@/workbench/runtime/documentContent'

type JsonRecord = Record<string, unknown>

export interface StageOutputSelection {
  id: string
  sectionKey: string
  index: number
  title: string
  value: unknown
  source?: string
}

const props = withDefaults(defineProps<{
  value: string
  selectedId?: string | null
  idPrefix?: string
  documentTitle?: string
}>(), {
  selectedId: null,
  idPrefix: 'result'
})

const emit = defineEmits<{
  select: [selection: StageOutputSelection]
  reference: [selection: StageOutputSelection]
}>()

const keyLabels: Record<string, string> = {
  assumptions: '\u5047\u8bbe',
  constraints: '\u7ea6\u675f',
  acceptance_criteria: '\u9a8c\u6536\u6807\u51c6',
  acceptanceCriteria: '\u9a8c\u6536\u6807\u51c6',
  summary: '\u6458\u8981',
  objective: '\u76ee\u6807',
  objectives: '\u76ee\u6807',
  findings: '\u53d1\u73b0',
  decisions: '\u51b3\u7b56',
  risks: '\u98ce\u9669',
  evidence: '\u8bc1\u636e',
  recommendations: '\u5efa\u8bae',
  expected_outcomes: '\u9884\u671f\u7ed3\u679c',
  unknowns: '\u672a\u77e5\u4e8b\u9879',
  architecture: '\u67b6\u6784\u65b9\u6848',
  deployment: '\u90e8\u7f72\u65b9\u6848',
  rationale: '\u8bbe\u8ba1\u4f9d\u636e',
  style: '\u65b9\u6848\u98ce\u683c',
  components: '\u7cfb\u7edf\u7ec4\u4ef6',
  interfaces: '\u63a5\u53e3\u8bbe\u8ba1',
  data_flow: '\u6570\u636e\u6d41',
  dataFlow: '\u6570\u636e\u6d41',
  source: '\u6765\u6e90',
  mandatory: '\u5f3a\u5236\u8981\u6c42',
  required: '\u5f3a\u5236\u8981\u6c42',
  constraint: '\u7ea6\u675f\u5185\u5bb9',
  validation: '\u9a8c\u8bc1\u72b6\u6001',
  status: '\u72b6\u6001'
}
const primaryKeys = ['constraint', 'criterion', 'acceptance_criteria', 'assumption', 'finding', 'decision', 'summary', 'overview', 'description', 'title', 'content', 'text']
const metadataKeys = new Set(['mandatory', 'required', 'source', 'sourceRef', 'source_ref', 'status', 'validation', 'validationStatus', 'validation_status', 'provenance'])
const referenceKeys = new Set(['source', 'sourceRef', 'source_ref', 'provenance'])

const parsedValue = computed<unknown>(() => {
  const source = props.value.trim()
  if (!source) return null
  try { return JSON.parse(source) as unknown } catch { return null }
})
const isRecord = (value: unknown): value is JsonRecord => (
  typeof value === 'object' && value !== null && !Array.isArray(value)
)
const isStructured = computed(() => isRecord(parsedValue.value) || Array.isArray(parsedValue.value))
const reportText = computed(() => reportContent(parsedValue.value))
const renderedReport = computed(() => renderMarkdown(withoutRepeatedTitle(reportText.value, props.documentTitle)))
const renderedText = computed(() => renderMarkdown(withoutRepeatedTitle(typeof parsedValue.value === 'string' ? parsedValue.value : props.value, props.documentTitle)))
const sections = computed(() => {
  if (Array.isArray(parsedValue.value)) return [{ key: 'items', value: parsedValue.value }]
  if (isRecord(parsedValue.value)) return documentEntries(parsedValue.value).map(([key, value]) => ({ key, value }))
  return []
})
const collapsedSections = ref(new Set<string>())
const isSectionOpen = (key: string) => !collapsedSections.value.has(key)
const toggleSection = (key: string) => {
  const next = new Set(collapsedSections.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedSections.value = next
}
const isLargeSection = (value: unknown) => {
  if (Array.isArray(value) && value.length > 20) return true
  if (isRecord(value) && Object.keys(value).length > 14) return true
  if (typeof value === 'string') return value.length > 8000
  try { return JSON.stringify(value).length > 12000 } catch { return false }
}
watch(sections, (next) => {
  const autoCollapsed = next.filter(section => isLargeSection(section.value)).map(section => section.key)
  if (!autoCollapsed.length) return
  collapsedSections.value = new Set([...collapsedSections.value, ...autoCollapsed])
}, { immediate: true })
const recordEntries = (value: JsonRecord) => documentEntries(value)
const labelForKey = (key: string) => keyLabels[key] || key.split('_').join(' ')
const padIndex = (index: number) => String(index + 1).padStart(2, '0')
const sectionCount = (value: unknown) => {
  if (Array.isArray(value)) return value.length
  if (isRecord(value)) return Object.keys(value).length
  return null
}
const selectionId = (sectionKey: string, index: number) => `${props.idPrefix}:${sectionKey}:${index}`
const primaryEntry = (value: JsonRecord) => {
  for (const key of primaryKeys) {
    const entry = value[key]
    if (typeof entry === 'string' && entry.trim()) return [key, entry] as [string, unknown]
  }
  return recordEntries(value).find(([key, entry]) => !metadataKeys.has(key) && typeof entry === 'string' && entry.trim()) || null
}
const metadataEntries = (value: JsonRecord) => recordEntries(value).filter(([key]) => metadataKeys.has(key))
const secondaryEntries = (value: JsonRecord) => {
  const primaryKey = primaryEntry(value)?.[0]
  return recordEntries(value).filter(([key]) => key !== primaryKey && !metadataKeys.has(key))
}
const displayValue = (value: unknown) => {
  if (value === null) return 'null'
  if (typeof value === 'string') return value
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  try { return JSON.stringify(value) } catch { return String(value) }
}
const displayMetadata = (key: string, value: unknown) => {
  if (['mandatory', 'required'].includes(key)) return value === true ? '必须满足' : '建议满足'
  if (['validation', 'validationStatus', 'validation_status'].includes(key)) return displayValue(value).split('_').join(' ')
  return displayValue(value)
}
const isLongValue = (value: unknown) => typeof value === 'string' && (value.length > 180 || value.includes('\n'))
const fieldClass = (key: string, value: unknown) => ({
  'is-narrative': isRichTextKey(key) || isLongValue(value),
  'is-complex': Array.isArray(value) || isRecord(value)
})
const fieldToneClass = (key: string, value: unknown) => {
  const normalizedValue = typeof value === 'string' ? value.toLowerCase() : ''
  return {
    'is-constraint': ['constraint', 'constraints', 'mandatory', 'required'].includes(key),
    'is-validation': ['validation', 'validationStatus', 'validation_status'].includes(key),
    'is-reference': referenceKeys.has(key),
    'is-status': key === 'status',
    'is-success': ['completed', 'success', 'passed', 'valid', 'approved', 'online'].includes(normalizedValue),
    'is-warning': ['pending', 'unknown', 'advisory', 'degraded', 'review'].includes(normalizedValue),
    'is-danger': ['failed', 'error', 'offline', 'rejected'].includes(normalizedValue)
  }
}
const metadataClass = (key: string, value: unknown) => ({
  'is-hard': ['mandatory', 'required'].includes(key) && value === true,
  'is-validation': ['validation', 'validationStatus', 'validation_status', 'status'].includes(key)
})
const isReferenceKey = (key: string) => referenceKeys.has(key)
const valueClass = (value: unknown) => ({
  'is-code': typeof value !== 'string' || value === null,
  'is-boolean': typeof value === 'boolean'
})
const isRichTextKey = (key: string) => ['content', 'overview', 'description', 'summary', 'final_answer', 'report', 'report_markdown'].includes(key)
const selectionFor = (sectionKey: string, index: number, value: unknown): StageOutputSelection => {
  const title = isRecord(value)
    ? displayValue(primaryEntry(value)?.[1] || value.title || labelForKey(sectionKey))
    : displayValue(value)
  const source = isRecord(value)
    ? metadataEntries(value).find(([key]) => isReferenceKey(key))?.[1]
    : undefined
  return {
    id: selectionId(sectionKey, index),
    sectionKey,
    index,
    title,
    value,
    source: source == null ? undefined : displayValue(source)
  }
}
</script>

<style scoped>
.stage-output-viewer { min-width: 0; color: var(--wb-text); }
.stage-output-viewer__sections { min-width: 0; }
.stage-output-viewer__document { color: var(--wb-text-secondary); font-size: 14px; line-height: 1.85; }
.stage-output-viewer__document :deep(p), .stage-output-viewer__document :deep(li) { overflow-wrap: anywhere; }
.stage-output-viewer__document :deep(pre) { max-width: 100%; overflow: auto; }
.stage-output-viewer__section { border-bottom: 1px solid var(--wb-border-soft); }
.stage-output-viewer__section:last-child { border-bottom: 0; }
.stage-output-viewer__section-head { display: flex; align-items: center; justify-content: flex-start; width: 100%; min-height: 34px; padding: 0 2px; border: 0; color: var(--wb-text-secondary); background: transparent; cursor: pointer; font-size: 13px; font-weight: 700; text-align: left; }
.stage-output-viewer__section-head:hover { color: var(--wb-text); }
.stage-output-viewer__section-head:focus-visible { outline: 1px solid var(--wb-accent); outline-offset: -1px; }
.stage-output-viewer__section-title { display: inline-flex; align-items: center; gap: 6px; }
.stage-output-viewer__fold { width: 12px; color: var(--wb-accent); font: 11px var(--font-mono, monospace); }
.stage-output-viewer__section-count { margin-left: 2px; color: var(--wb-text-muted); font: 500 11px var(--font-mono, monospace); }
.stage-output-viewer__section-body { padding: 4px 0 6px 18px; }
.stage-output-viewer__list { display: grid; }
.stage-output-viewer__item { padding: 8px 4px 8px 0; border-radius: var(--wb-radius-sm); }
.stage-output-viewer__item + .stage-output-viewer__item { border-top: 1px solid color-mix(in srgb, var(--wb-border-soft) 72%, transparent); }
.stage-output-viewer__item-content { min-width: 0; }
.stage-output-viewer__semantic { margin: 0; color: var(--wb-text); font-size: 14px; font-weight: 500; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; text-wrap: pretty; }
.stage-output-viewer__metadata { display: flex; align-items: center; flex-wrap: wrap; gap: 3px 9px; margin-top: 6px; color: var(--wb-text-muted); font: 500 10px var(--font-mono, monospace); opacity: .9; }
.stage-output-viewer__meta { color: inherit; }
.stage-output-viewer__meta--reference { padding: 0; border: 0; background: transparent; cursor: pointer; font: inherit; text-decoration: underline dotted; text-underline-offset: 3px; }
.stage-output-viewer__meta--reference:hover { color: var(--wb-accent); }
.stage-output-viewer__meta.is-hard { color: var(--wb-warning); font-weight: 700; }
.stage-output-viewer__meta.is-validation { color: var(--wb-success); font-weight: 650; }
.stage-output-viewer__fields { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(340px, 100%), 1fr)); gap: 12px 24px; margin: 8px 0 0; }
.stage-output-viewer__fields > div { min-width: 0; }
.stage-output-viewer__fields dt { margin-bottom: 1px; color: var(--wb-text-muted); font-size: 11px; }
.stage-output-viewer__fields dd { min-width: 0; margin: 0; color: var(--wb-text-secondary); font-size: 11px; font-weight: 450; line-height: 1.55; overflow-wrap: anywhere; }
.stage-output-viewer__fields dd.is-code { color: var(--wb-text); font: 500 11px var(--font-mono, monospace); }
.stage-output-viewer__fields dd.is-boolean { color: var(--wb-accent); font-weight: 650; }
.stage-output-viewer__fields--record { gap: 0 28px; margin-top: 2px; }
.stage-output-viewer__fields--record > div { padding: 11px 0 13px; border-bottom: 1px solid color-mix(in srgb, var(--wb-border-soft) 76%, transparent); }
.stage-output-viewer__fields--record > div:last-child { border-bottom: 0; }
.stage-output-viewer__fields--record > div.is-narrative { grid-column: 1 / -1; }
.stage-output-viewer__field-label { display: flex; align-items: baseline; gap: 7px; }
.stage-output-viewer__field-label::before { content: ''; width: 3px; height: 12px; flex: 0 0 auto; border-radius: 2px; background: var(--wb-border-strong); }
.stage-output-viewer__field-label span { color: var(--wb-text-secondary); font-size: 12px; font-weight: 700; }
.stage-output-viewer__field-label code { color: var(--wb-text-muted); font: 500 10px var(--font-mono, monospace); opacity: .82; }
.stage-output-viewer__fields--record > div.is-narrative .stage-output-viewer__field-label::before { height: 16px; background: var(--wb-accent); }
.stage-output-viewer__fields--record > div.is-constraint .stage-output-viewer__field-label::before { background: var(--wb-warning); }
.stage-output-viewer__fields--record > div.is-validation .stage-output-viewer__field-label::before { background: var(--wb-success); }
.stage-output-viewer__fields--record > div.is-reference .stage-output-viewer__field-label::before { background: var(--wb-accent); }
.stage-output-viewer__fields--record > div.is-status .stage-output-viewer__field-label::before { background: var(--wb-success); }
.stage-output-viewer__fields--record > div.is-constraint .stage-output-viewer__field-label span { color: var(--wb-warning); }
.stage-output-viewer__fields--record > div.is-validation .stage-output-viewer__field-label span { color: var(--wb-success); }
.stage-output-viewer__fields--record > div.is-status.is-success dd { color: var(--wb-success); font-weight: 650; }
.stage-output-viewer__fields--record > div.is-status.is-warning dd { color: var(--wb-warning); font-weight: 650; }
.stage-output-viewer__fields--record > div.is-status.is-danger dd { color: var(--wb-danger); font-weight: 650; }
.stage-output-viewer__fields--record > div.is-complex .stage-output-viewer__field-label span { color: var(--wb-text); }
.stage-output-viewer__fields--record > div.is-narrative > dd { margin-top: 7px; }
@media (max-width: 720px) {
  .stage-output-viewer__section-body { padding-left: 12px; }
  .stage-output-viewer__fields { grid-template-columns: minmax(0, 1fr); }
  .stage-output-viewer__field-label { flex-wrap: wrap; gap: 2px 7px; }
}
</style>
