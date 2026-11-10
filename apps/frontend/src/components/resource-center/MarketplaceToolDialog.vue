<template>
  <el-dialog :model-value="Boolean(job)" :title="job?.displayName || '本地文档工具'" width="min(580px, 94vw)" :close-on-click-modal="!busy" :show-close="!busy" @update:model-value="close">
    <form class="tool-form" @submit.prevent="execute">
      <p class="tool-note">文件将在本机处理。最大 20 MiB；源文件保留，转换结果另存为独立副本。</p>
      <label class="tool-file">选择文档<input type="file" :accept="pdf ? '.pdf' : '.txt,.md,.html,.csv,.json,.docx,.xlsx,.pdf'" :disabled="busy" @change="selectFile" /></label>
      <template v-if="pdf">
        <label>起始页<input v-model.number="firstPage" type="number" min="1" max="200" :disabled="busy" /></label>
        <label>结束页（可选）<input v-model="lastPage" type="number" min="1" max="200" :disabled="busy" /></label>
        <p class="tool-note">支持含文字层的 PDF；扫描件暂不支持 OCR。</p>
      </template>
      <label v-else>目标格式<select v-model="target" :disabled="busy || !formats.length"><option v-for="format in formats" :key="format" :value="format">{{ format.toUpperCase() }}</option></select></label>
      <p v-if="file && !pdf && !formats.length" role="alert">该文件类型暂不支持转换。</p>
      <p v-if="error" class="tool-error" role="alert">{{ error }}</p>
      <pre v-if="text" class="tool-result" tabindex="0" aria-label="PDF 解析结果">{{ text }}</pre>
      <button v-if="outputPath" type="button" class="tool-action" :disabled="busy" @click="download">下载转换结果</button>
      <button class="tool-action is-primary" type="submit" :disabled="busy || !file || (!pdf && !formats.length)">{{ busy ? '正在本机处理…' : pdf ? '解析 PDF' : '开始转换' }}</button>
    </form>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { agentosApi } from '@/services/api/agentos'
import type { MarketplaceInstallation } from '@/services/api/agentos'

const props = defineProps<{ job: MarketplaceInstallation | null }>()
const emit = defineEmits<{ (event: 'close'): void }>()
const file = ref<File | null>(null)
const firstPage = ref(1)
const lastPage = ref('')
const target = ref('')
const busy = ref(false)
const error = ref('')
const text = ref('')
const outputPath = ref('')
const pdf = computed(() => props.job?.catalogId === 'tool.pdf-parser')
const pairs: Record<string, string[]> = { txt: ['md', 'html'], md: ['txt', 'html'], html: ['txt', 'md'], csv: ['json'], json: ['csv'], docx: ['txt', 'md', 'html'], xlsx: ['csv', 'json'], pdf: ['txt', 'md'] }
const formats = computed(() => pairs[file.value?.name.split('.').pop()?.toLowerCase() || ''] || [])
watch(formats, value => { target.value = value[0] || '' })
watch(() => props.job?.jobId, () => { file.value = null; text.value = ''; outputPath.value = ''; error.value = ''; firstPage.value = 1; lastPage.value = '' })
function selectFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null; text.value = ''; outputPath.value = ''; error.value = '' }
function close(value: boolean) { if (!value && !busy.value) emit('close') }
async function execute() {
  if (!file.value || !props.job || busy.value) return
  error.value = ''; text.value = ''; outputPath.value = ''
  if (file.value.size > 20 * 1024 ** 2 || !file.value.size) { error.value = '请选择非空且不超过 20 MiB 的文件。'; return }
  busy.value = true
  try {
    const uploaded = await agentosApi.uploadMarketplaceToolFile(props.job.jobId, file.value)
    const input = pdf.value ? { sourcePath: uploaded.sourcePath, firstPage: firstPage.value, ...(lastPage.value ? { lastPage: Number(lastPage.value) } : {}) } : { sourcePath: uploaded.sourcePath, targetFormat: target.value }
    const result = await agentosApi.executeMarketplaceTool(props.job.jobId, input)
    if (result.error) {
      const messages: Record<string, string> = { OCR_NOT_AVAILABLE: '此 PDF 包含无文字层页面，暂不支持 OCR。', FORMAT_NOT_SUPPORTED: '暂不支持该格式组合。', INVALID_PDF: 'PDF 文件无法解析。', PAGE_RANGE_INVALID: '页码超出文档范围。', ENCRYPTED_PDF_NOT_SUPPORTED: '暂不支持加密 PDF。', TOOL_TIMEOUT: '处理超过 30 秒，请使用更小的文档。' }
      error.value = messages[String(result.error)] || `处理失败：${result.error}`
    } else { text.value = String(result.text || ''); outputPath.value = String(result.outputPath || '') }
  } catch { error.value = '本地工具暂不可用，请检查安装状态后重试。' }
  finally { busy.value = false }
}
async function download() {
  if (!props.job || !outputPath.value || busy.value) return
  busy.value = true
  try {
    const blob = await agentosApi.downloadMarketplaceToolFile(props.job.jobId, outputPath.value)
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `converted.${outputPath.value.split('.').pop()}`; anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  } catch { error.value = '结果下载失败，请重试。' }
  finally { busy.value = false }
}
</script>

<style scoped>
.tool-form { display: grid; gap: 14px; }.tool-note { margin: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.7; }.tool-form label { display: grid; gap: 7px; color: var(--text-primary); font-size: 12px; }.tool-form input, .tool-form select { min-height: 36px; padding: 7px 10px; border: 1px solid var(--border-light); color: var(--text-primary); background: var(--bg-card); }.tool-file { padding: 18px; border: 1px dashed var(--primary-line); background: var(--primary-fade); }.tool-error { color: var(--danger); font-size: 12px; }.tool-result { max-height: 300px; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; padding: 14px; border: 1px solid var(--border-light); background: var(--bg-app); color: var(--text-primary); font-size: 12px; }.tool-action { min-height: 38px; padding: 8px 14px; border: 1px solid var(--primary-line); color: var(--primary-color); background: transparent; cursor: pointer; }.tool-action.is-primary { background: var(--primary-fade); }.tool-action:disabled { opacity: .5; cursor: default; }.tool-action:focus-visible, input:focus-visible, select:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 3px; }
</style>
