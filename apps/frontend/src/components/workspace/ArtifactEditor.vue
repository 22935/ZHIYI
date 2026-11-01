<template>
  <section class="artifact-editor" aria-label="Artifact editor">
    <header class="artifact-editor__header">
      <div class="artifact-editor__title">
        <strong>{{ entry.name }}</strong>
      </div>
      <div class="artifact-editor__actions">
        <button type="button" :disabled="!canLocateGraph" @click="emit('locateGraph')">在图中定位</button>
        <button type="button" :disabled="!contentRef || loading" @click="download">下载</button>
        <button type="button" :disabled="!contentRef || loading" @click="openExternal">打开</button>
      </div>
    </header>

    <div v-if="!available" class="artifact-editor__state artifact-editor__state--missing">
      <strong>Not available in this Run</strong>
      <span>该稳定文件槽位在 {{ runId || '当前 Run' }} 中没有对应 Artifact。</span>
    </div>
    <div v-else-if="loading" class="artifact-editor__state">正在读取 sealed ContentManifest…</div>
    <div v-else-if="errorMessage" class="artifact-editor__state artifact-editor__state--error" role="alert">
      <strong>Artifact content unavailable</strong>
      <span>{{ errorMessage }}</span>
    </div>
    <template v-else-if="content">
      <article v-if="renderer === 'markdown'" class="artifact-editor__body markdown-body" v-html="renderedMarkdown" />
      <pre v-else-if="renderer === 'json'" class="artifact-editor__body json-body"><code>{{ formattedJson }}</code></pre>
      <pre v-else-if="renderer === 'text'" class="artifact-editor__body text-body">{{ content.content }}</pre>
      <div v-else class="artifact-editor__body generic-preview">
        <div class="generic-preview__icon" aria-hidden="true">FILE</div>
        <strong>Generic Artifact Preview</strong>
        <span>{{ content.mediaType }} · {{ content.byteLength ?? 'unknown size' }} bytes</span>
        <p>该媒体类型保留在 Artifact 中；可下载或在新窗口打开原始内容。</p>
      </div>
    </template>
    <div v-else class="artifact-editor__state">Artifact 尚未读取。</div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { agentosApi, type ArtifactContentResponse, type WorkspaceEntry } from '@/services/api/agentos'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  entry: WorkspaceEntry
  runId: string | null
  available: boolean
}>()

const emit = defineEmits<{ locateGraph: []; contentReady: [runId: string | null] }>()

const content = ref<ArtifactContentResponse | null>(null)
const loading = ref(false)
const errorMessage = ref('')
let controller: AbortController | null = null

const normalizeMediaType = (value: string) => value.toLowerCase().split(';', 1)[0].trim()
const contentRef = computed(() => props.entry.contentRef || props.entry.artifactId || '')
const mediaType = computed(() => normalizeMediaType(content.value?.mediaType || props.entry.mediaType || ''))
const renderer = computed<'markdown' | 'text' | 'json' | 'generic'>(() => {
  if (mediaType.value === 'text/markdown' || mediaType.value.endsWith('+markdown')) return 'markdown'
  if (mediaType.value === 'text/plain') return 'text'
  if (mediaType.value === 'application/json' || mediaType.value.endsWith('+json')) return 'json'
  if (mediaType.value.startsWith('text/')) return 'text'
  return 'generic'
})
const renderedMarkdown = computed(() => renderMarkdown(content.value?.content || ''))
const formattedJson = computed(() => {
  const raw = content.value?.content || ''
  try { return JSON.stringify(JSON.parse(raw), null, 2) }
  catch { return raw }
})
const canLocateGraph = computed(() => props.available && props.entry.identityQuality !== 'legacy' && Boolean(props.entry.semanticTaskKey))
const bodyReadable = (value: string) => {
  const normalized = normalizeMediaType(value)
  return normalized.startsWith('text/') || normalized === 'application/json' || normalized.endsWith('+markdown') || normalized.endsWith('+json')
}
const inlineContent = () => {
  if (typeof props.entry.content !== 'string') return null
  return {
    manifestId: props.entry.contentRef || props.entry.artifactId || props.entry.entryId,
    mediaType: normalizeMediaType(props.entry.mediaType || 'text/plain') || 'text/plain',
    content: props.entry.content
  } as ArtifactContentResponse
}

const loadContent = async () => {
  controller?.abort()
  content.value = null
  errorMessage.value = ''
  loading.value = false
  if (!props.available || !props.runId || !contentRef.value) return
  controller = new AbortController()
  const requestController = controller
  const requestedRunId = props.runId
  const requestedRef = contentRef.value
  loading.value = true
  try {
    const requestedMediaType = normalizeMediaType(props.entry.mediaType || '')
    const typeHint = requestedMediaType || normalizeMediaType(props.entry.artifactType || '')
    if (bodyReadable(typeHint) || !typeHint) {
      const result = await agentosApi.getArtifactContent(requestedRunId, requestedRef, { signal: requestController.signal })
      if (controller === requestController && !requestController.signal.aborted
        && props.runId === requestedRunId && contentRef.value === requestedRef) content.value = result
    } else {
      const detail = await agentosApi.getArtifactDetail(requestedRunId, requestedRef, { signal: requestController.signal })
      const detailContent = (detail as ArtifactContentResponse).content
      if (controller === requestController && !requestController.signal.aborted
        && props.runId === requestedRunId && contentRef.value === requestedRef) {
        content.value = { ...detail, content: typeof detailContent === 'string' ? detailContent : '' }
      }
    }
  } catch (error: unknown) {
    if (controller !== requestController || requestController.signal.aborted) return
    if ((error as { name?: string }).name === 'CanceledError' || (error as { name?: string }).name === 'AbortError') return
    const fallback = inlineContent()
    if (fallback) content.value = fallback
    else errorMessage.value = '无法读取当前 Run 的 sealed ContentManifest。'
  } finally {
    if (controller === requestController && !requestController.signal.aborted) {
      loading.value = false
      emit('contentReady', props.runId)
    }
  }
}

const download = async () => {
  if (!props.runId || !contentRef.value) return
  const blob = await agentosApi.downloadArtifact(props.runId, contentRef.value)
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = props.entry.name || contentRef.value
  anchor.click()
  URL.revokeObjectURL(url)
}

const openExternal = async () => {
  if (!props.runId || !contentRef.value || typeof window === 'undefined' || typeof window.open !== 'function') return
  const blob = await agentosApi.downloadArtifact(props.runId, contentRef.value)
  const url = URL.createObjectURL(blob)
  window.open(url, '_blank', 'noopener,noreferrer')
  window.setTimeout(() => URL.revokeObjectURL(url), 30_000)
}

watch([() => props.entry.entryId, () => props.runId, () => props.available, contentRef], loadContent, { immediate: true })
onBeforeUnmount(() => controller?.abort())
</script>

<style scoped>
.artifact-editor { display: flex; flex: 1 1 auto; flex-direction: column; height: 100%; min-height: 0; overflow: hidden; border: 1px solid var(--wb-border-soft); border-radius: var(--wb-radius-section); background: var(--wb-surface-section); color: var(--wb-text); box-shadow: var(--wb-shadow-section); }
.artifact-editor__header { display: flex; align-items: center; justify-content: space-between; gap: 18px; min-height: 40px; padding: 5px 14px; border-bottom: 1px solid var(--wb-border-soft); background: var(--wb-surface-section); }
.artifact-editor__title { min-width: 0; }
.artifact-editor__eyebrow { display: block; color: var(--wb-accent); font: 10px var(--font-mono, monospace); letter-spacing: .1em; }
.artifact-editor__title strong { display: block; margin: 1px 0; overflow: hidden; color: var(--wb-text); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.artifact-editor__title small { color: var(--wb-text-muted); font: 10px var(--font-mono, monospace); }
.artifact-editor__actions { display: flex; gap: 6px; flex: 0 0 auto; }
.artifact-editor__actions button { min-height: 28px; padding: 0 9px; border: 1px solid var(--wb-border); border-radius: var(--wb-radius-sm); color: var(--wb-text-secondary); background: transparent; cursor: pointer; font-size: 11px; }
.artifact-editor__actions button:hover:not(:disabled) { color: var(--wb-accent); border-color: color-mix(in srgb, var(--wb-accent) 42%, var(--wb-border)); background: var(--wb-accent-soft); }
.artifact-editor__actions button:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: 1px; }
.artifact-editor__actions button:disabled { color: var(--text-disabled); cursor: not-allowed; }
.artifact-editor__state { display: grid; place-items: center; gap: 7px; min-height: 220px; padding: 24px; color: var(--text-secondary); text-align: center; font-size: 12px; }
.artifact-editor__state strong { color: var(--text-primary); }
.artifact-editor__state--missing { background: color-mix(in srgb, var(--info) 4%, transparent); }
.artifact-editor__state--error { color: var(--danger); }
.artifact-editor__body { flex: 1 1 auto; min-height: 0; max-width: 920px; width: min(100% - 44px, 920px); margin: 0 auto; overflow-y: auto; overflow-x: hidden; scrollbar-gutter: stable; }
.markdown-body { padding: 24px 0 52px; color: var(--wb-text-secondary); }
.markdown-body :deep(h1), .markdown-body :deep(h2), .markdown-body :deep(h3) { color: var(--wb-text); line-height: 1.35; text-wrap: pretty; }
.markdown-body :deep(h1) { margin: 0 0 18px; padding-bottom: 10px; border-bottom: 1px solid var(--wb-border); font-size: 26px; }
.markdown-body :deep(h2) { margin: 26px 0 10px; font-size: 18px; }
.markdown-body :deep(h3) { margin: 20px 0 8px; font-size: 14px; }
.markdown-body :deep(p), .markdown-body :deep(li) { font-size: 13px; line-height: 1.8; }
.markdown-body :deep(ul), .markdown-body :deep(ol) { padding-left: 24px; }
.markdown-body :deep(code) { padding: 2px 4px; background: var(--wb-surface-inset); font: 11px var(--font-mono, monospace); }
.markdown-body :deep(pre) { overflow: auto; padding: 12px; border: 1px solid var(--wb-border); background: var(--wb-surface-inset); }
.markdown-body :deep(pre code) { padding: 0; background: transparent; }
.markdown-body :deep(blockquote) { margin: 12px 0; padding-left: 12px; border-left: 2px solid var(--primary-color); }
/* Markdown 表格样式收敛到 global.css 的全局三线表 */
.text-body, .json-body { box-sizing: border-box; margin-top: 24px; padding: 18px; overflow: auto; border: 1px solid var(--wb-border); color: var(--wb-text-secondary); background: var(--wb-surface-inset); font: 12px/1.7 var(--font-mono, monospace); white-space: pre-wrap; }
.json-body { color: var(--wb-text); }
.generic-preview { display: grid; place-items: center; gap: 9px; min-height: 300px; color: var(--wb-text-secondary); text-align: center; }
.generic-preview strong { color: var(--wb-text); font-size: 15px; }
.generic-preview span { color: var(--wb-text-muted); font: 11px var(--font-mono, monospace); }
.generic-preview p { max-width: 360px; margin: 0; font-size: 12px; line-height: 1.6; }
.generic-preview__icon { display: grid; place-items: center; width: 52px; height: 52px; border: 1px solid var(--wb-border); border-radius: var(--wb-radius-md); color: var(--wb-accent); background: var(--wb-accent-soft); font: 11px var(--font-mono, monospace); }

@media (max-width: 640px) {
  .artifact-editor__header { align-items: flex-start; flex-direction: column; }
  .artifact-editor__actions { width: 100%; }
  .artifact-editor__actions button { flex: 1; }
  .artifact-editor__body { width: min(100% - 28px, 920px); }
}
</style>
