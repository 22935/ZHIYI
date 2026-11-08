<template>
  <section class="file-editor" :aria-label="request.relativePath">
    <header class="file-editor__toolbar">
      <span class="file-editor__path" :title="request.workspaceRoot + '/' + request.relativePath">{{ request.relativePath }}</span>
      <span v-if="dirty" class="file-editor__dirty">未保存</span>
      <button v-if="isTextKind" type="button" :disabled="!doc || diffLoading" :title="diffMode ? '返回编辑' : '与 HEAD 对比（行内 diff）'" @click="toggleDiff">{{ diffLoading ? '对比中…' : diffMode ? '编辑' : '对比' }}</button>
      <button type="button" :disabled="loading || saving" @click="reload">重新读取</button>
      <button v-if="isTextKind" type="button" :disabled="!dirty || !version || loading || saving" title="保存到工作区（Ctrl+S）" @click="save">{{ saving ? '保存中…' : '保存' }}</button>
    </header>
    <p v-if="loading" role="status">正在读取文件…</p>
    <div v-if="error" class="file-editor__error" role="alert">{{ error }} <button v-if="!doc" type="button" @click="load">重试</button></div>
    <p v-if="notice" class="file-editor__notice">{{ notice }}</p>
    <p v-if="diffError" class="file-editor__error">{{ diffError }}</p>
    <div v-if="previewKind === 'unsupported'" class="file-editor__unsupported" role="alert">
      <p>{{ meta?.reason || '该文件类型暂不支持预览' }}</p>
      <button type="button" @click="reload">重新读取</button>
    </div>
    <div v-else-if="doc" class="file-editor__body">
      <img v-if="previewKind === 'image'" class="file-editor__image" :src="currentText" :alt="request.name">
      <WorkspaceDiffView
        v-else-if="diffMode"
        :base="baseText"
        :current="currentText"
        :file-name="request.name"
      />
      <WorkspaceCodeEditor
        v-else
        :key="editorKey"
        :document="doc"
        :file-name="request.name"
        :file-path="request.relativePath"
        :workspace-root="request.workspaceRoot"
        :read-only="!version"
        @save="save"
        @cursor="cursor = $event"
        @definition="openDefinition"
      />
    </div>
  </section>
</template>
<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { DocumentConflictError, workspaceDocuments, type DocumentMeta, type TextDocument } from '@/workbench/core/documents'
import { workspaceDiagnostics } from '@/workbench/core/diagnostics'
import { registerDiff } from '@/workbench/core/diffRequest'
import { requestOpenFile } from '@/workbench/core/openFileRequest'
import { requestReveal } from '@/workbench/core/reveal'
import { gitShow } from '@/services/workspaceGit'
import type { WorkspaceFileOpenRequest } from '@/services/api/agentos'

// 文件元信息不在编辑器内占一行，而是上报给窗口底部状态栏（VS Code 式）显示。
export interface WorkspaceFileEditorStatus {
  /** 后端是否支持版本保护保存；false 时状态栏展示只读标记。 */
  editable: boolean
  language: string
  /** 真实解码编码（UTF-8/GB18030/UTF-16LE…），状态栏展示。 */
  encoding: string
  lines: number
  cursor: string
}

// CodeMirror 体积较大且只在打开文件时用得到：异步加载，避免拖慢工作台首屏。
const WorkspaceCodeEditor = defineAsyncComponent(() => import('./WorkspaceCodeEditor.vue'))
const WorkspaceDiffView = defineAsyncComponent(() => import('./WorkspaceDiffView.vue'))

const props = defineProps<{request: WorkspaceFileOpenRequest}>()
const emit = defineEmits<{'dirty-change': [dirty: boolean], 'status-change': [status: WorkspaceFileEditorStatus]}>()
const doc = shallowRef<TextDocument | null>(null)
const meta = ref<DocumentMeta | null>(null)
const error = ref(''), loading = ref(false), saving = ref(false)
const cursor = ref({ line: 1, column: 1 })
const revision = ref(0)
const editorGeneration = ref(0)
const diffMode = ref(props.request.diff === true)
const baseText = ref('')
const baseLoaded = ref(false)
const diffLoading = ref(false)
const diffError = ref('')
const currentText = computed(() => {
  revision.value
  return doc.value?.getText() ?? ''
})

const version = computed(() => doc.value?.versionToken ?? null)
const dirty = computed(() => {
  revision.value // 文档内部变化不是响应式的，用它触发重算
  return doc.value?.dirty ?? false
})
const lines = computed(() => {
  revision.value
  return doc.value?.lineCount ?? 0
})
const language = computed(() => props.request.name.split('.').pop()?.toUpperCase() || 'TEXT')
const previewKind = computed(() => meta.value?.kind ?? 'text')
const isTextKind = computed(() => previewKind.value === 'text')
const formatLabel = computed(() => (meta.value?.format || props.request.name.split('.').pop() || '文档').toUpperCase())
const notice = computed(() => {
  const value = meta.value
  if (!value) return ''
  if (value.kind === 'extracted') return `${formatLabel.value} 文本提取预览（只读）${value.reason ? '：' + value.reason : ''}`
  if (value.kind === 'text' && value.reason) return value.reason
  return ''
})
const status = computed<WorkspaceFileEditorStatus>(() => ({
  editable: Boolean(version.value),
  language: language.value,
  encoding: meta.value?.encoding ? meta.value.encoding.toUpperCase() : 'UTF-8',
  lines: lines.value,
  cursor: `行 ${cursor.value.line}，列 ${cursor.value.column}`
}))
// 重新读取时换 key 让编辑器用新内容重建；平时编辑不重建（否则会打断输入）。
const editorKey = computed(() => `${doc.value?.uri || props.request.relativePath}:${editorGeneration.value}`)

watch(dirty, value => emit('dirty-change', value), { immediate: true })
watch(status, value => emit('status-change', value), { immediate: true })

let controller: AbortController | undefined
let unsubscribe: (() => void) | null = null
const message = (cause: any) => cause?.response?.data?.detail || cause?.response?.data?.message || cause?.message || '操作失败，请检查工作区服务'

function attach(next: TextDocument): void {
  unsubscribe?.()
  doc.value = next
  meta.value = workspaceDocuments.meta(next.uri) ?? { kind: 'text' }
  unsubscribe = next.onDidChange(() => { revision.value += 1 })
}

async function load(): Promise<void> {
  controller?.abort()
  const pending = new AbortController()
  controller = pending
  loading.value = true
  error.value = ''
  try {
    const next = await workspaceDocuments.open(props.request, pending.signal)
    if (controller !== pending || pending.signal.aborted) return
    if (next !== doc.value) {
      attach(next)
      editorGeneration.value += 1
      if (diffMode.value) void loadBase()
    }
  } catch (cause) {
    if (!pending.signal.aborted) error.value = message(cause)
  } finally {
    if (controller === pending) loading.value = false
  }
}

async function reload(): Promise<void> {
  if (dirty.value && !window.confirm('重新读取将放弃尚未保存的修改，是否继续？')) return
  loading.value = true
  error.value = ''
  try {
    attach(await workspaceDocuments.reload(props.request))
    editorGeneration.value += 1
  } catch (cause) {
    error.value = message(cause)
  } finally {
    loading.value = false
  }
}

async function save(): Promise<void> {
  if (!doc.value || !version.value || loading.value || saving.value || !dirty.value) return
  saving.value = true
  error.value = ''
  try {
    await workspaceDocuments.save(doc.value)
    revision.value += 1
    // 保存成功后自动跑一次静态检查；Problems 面板与角标共用同一份结果。
    workspaceDiagnostics.schedule(props.request.workspaceRoot)
  } catch (cause: any) {
    error.value = cause instanceof DocumentConflictError
      ? cause.message
      : `${message(cause)}。未自动重试；请重新读取磁盘确认保存结果。`
  } finally {
    saving.value = false
  }
}

function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || saving.value) { event.preventDefault(); event.returnValue = '' } }
window.addEventListener('beforeunload', beforeUnload)

// 行内 diff：对比 HEAD 与当前内容；原始版本只为展示，不参与保存。
async function loadBase(): Promise<void> {
  if (baseLoaded.value || diffLoading.value) return
  diffLoading.value = true
  diffError.value = ''
  try {
    baseText.value = (await gitShow(props.request.workspaceRoot, props.request.relativePath)) ?? ''
    baseLoaded.value = true
  } catch (cause: any) {
    diffError.value = cause?.message || '无法读取原始版本（需要 Git 仓库）'
    diffMode.value = false
  } finally {
    diffLoading.value = false
  }
}

function toggleDiff(): void {
  if (!doc.value || !isTextKind.value) return
  diffMode.value = !diffMode.value
  if (diffMode.value) void loadBase()
}

/** LSP 跳转定义：先投递行号再打开目标文件，跨文件也能定位。 */
function openDefinition(location: { path: string; line: number }): void {
  if (!location?.path) return
  requestReveal(location.path, location.line)
  requestOpenFile({
    missionId: props.request.missionId,
    workspaceRoot: props.request.workspaceRoot,
    relativePath: location.path,
    name: location.path.split('/').pop() || location.path,
    ...(props.request.desktopWorkspaceId ? { desktopWorkspaceId: props.request.desktopWorkspaceId } : {})
  })
}

let unregisterDiff: (() => void) | null = null
onMounted(() => {
  unregisterDiff = registerDiff(props.request.relativePath, () => {
    if (!isTextKind.value) return
    diffMode.value = true
    void loadBase()
  })
})

watch(() => [props.request.missionId, props.request.desktopWorkspaceId, props.request.relativePath], () => void load(), { immediate: true })

onBeforeUnmount(() => {
  controller?.abort()
  unsubscribe?.()
  unsubscribe = null
  unregisterDiff?.()
  unregisterDiff = null
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>
<style scoped>
.file-editor { display:flex; flex-direction:column; width:100%; height:100%; min-height:0; color:var(--wb-text); background:var(--wb-surface-shell); }
.file-editor__toolbar { display:flex; align-items:center; gap:12px; padding:8px 16px; font-size:12px; color:var(--wb-text-secondary); }
.file-editor__path { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.file-editor button { color:var(--wb-text); background:var(--wb-surface-1); border:1px solid var(--wb-border-strong); border-radius:4px; padding:4px 10px; cursor:pointer; }
.file-editor button:disabled { opacity:.45; cursor:default; }
.file-editor__dirty { color:var(--wb-warning); }
.file-editor__body { flex:1; min-height:0; display:flex; overflow:hidden; }
.file-editor__error { padding:10px 16px; color:var(--wb-danger); }
.file-editor__notice { margin:0; padding:6px 16px; font-size:12px; color:var(--wb-text-secondary); background:var(--wb-surface-1); border-top:1px solid var(--wb-border); border-bottom:1px solid var(--wb-border); }
.file-editor__unsupported { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:12px; color:var(--wb-text-secondary); }
.file-editor__image { flex:1; min-width:0; height:100%; object-fit:contain; background:var(--wb-surface-1); }
</style>
