<template>
  <section class="workspace-git" aria-label="源代码管理">
    <header class="workspace-git__head">
      <span class="workspace-git__branch">{{ status?.branch || '—' }}</span>
      <span v-if="status && (status.ahead || status.behind)" class="workspace-git__ahead">↑{{ status.ahead }} ↓{{ status.behind }}</span>
      <button class="workspace-git__refresh" type="button" :disabled="loading" @click="refresh">{{ loading ? '…' : '刷新' }}</button>
    </header>

    <p v-if="hint" class="workspace-git__hint">{{ hint }}</p>
    <p v-else-if="error" class="workspace-git__error" role="alert">{{ error }}</p>

    <div v-else-if="notRepo" class="workspace-git__init">
      <svg class="workspace-git__init-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        <circle cx="4.5" cy="3.5" r="1.7" />
        <circle cx="4.5" cy="12.5" r="1.7" />
        <circle cx="11.5" cy="4.5" r="1.7" />
        <path d="M4.5 5.2v5.6" />
        <path d="M11.5 6.2c0 2.3-1.9 3.2-4.2 3.6-1 .18-2 .5-2.8 1" />
      </svg>
      <strong>此文件夹还不是 Git 仓库</strong>
      <span class="workspace-git__init-path" :title="root">{{ root }}</span>
      <p class="workspace-git__init-copy">初始化后即可在这里查看改动、暂存与提交。</p>
      <div class="workspace-git__init-actions">
        <button type="button" class="workspace-git__init-btn" :disabled="initting" @click="initRepo">{{ initting ? '初始化中…' : '初始化仓库' }}</button>
        <button type="button" class="workspace-git__switch-btn" :disabled="initting" @click="switchFolder">打开其他文件夹</button>
      </div>
    </div>

    <template v-else>
      <div v-if="!status || !status.files.length" class="workspace-git__clean">工作区干净</div>
      <ul v-else class="workspace-git__files" role="list">
        <li v-for="file in status.files" :key="file.path">
          <button
            class="workspace-git__file"
            :class="{ 'is-active': selected?.path === file.path }"
            type="button"
            :title="file.path"
            @click="select(file)"
          >
            <span class="workspace-git__letters">{{ letters(file) }}</span>
            <span class="workspace-git__path">{{ file.path }}</span>
          </button>
          <div class="workspace-git__actions">
            <button v-if="isStaged(file)" type="button" :disabled="busy" @click="unstage(file)">取消暂存</button>
            <button v-else type="button" :disabled="busy" @click="stage(file)">暂存</button>
            <button type="button" @click="openDiff(file)">对比</button>
            <button type="button" @click="openFile(file)">打开</button>
          </div>
        </li>
      </ul>

      <section v-if="selected" class="workspace-git__diff">
        <header class="workspace-git__diff-head">diff · {{ selected.path }}</header>
        <pre v-if="diff !== null" class="workspace-git__diff-body"><span v-for="(line, index) in diffLines" :key="index" class="workspace-git__diff-line" :class="line.tone">{{ line.text }}</span></pre>
        <p v-else-if="diffLoading" class="workspace-git__diff-empty">正在加载 diff…</p>
        <p v-else class="workspace-git__diff-empty">没有可显示的差异</p>
      </section>

      <footer class="workspace-git__commit">
        <textarea v-model="message" rows="3" placeholder="提交信息…" aria-label="提交信息" />
        <button type="button" :disabled="!canCommit" @click="commit">{{ committing ? '提交中…' : '提交' }}</button>
      </footer>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { agentosApi } from '@/services/api/agentos'
import { gitCommit, gitDiff, gitInit, gitStage, gitStatus, gitUnstage, isNotRepositoryError, type GitFileChange, type GitStatusResult } from '@/services/workspaceGit'
import { getElectronBridge } from '@/platform/electron/bridge'
import { requestDiff } from '@/workbench/core/diffRequest'

const props = defineProps<{ missionId: string }>()
const emit = defineEmits<{ (event: 'open-file', request: Record<string, unknown>): void }>()

const status = ref<GitStatusResult | null>(null)
const loading = ref(false)
const busy = ref(false)
const committing = ref(false)
const error = ref('')
const root = ref('')
const workspaceId = ref<string | null>(null)
const selected = ref<GitFileChange | null>(null)
const diff = ref<string | null>(null)
const diffLoading = ref(false)
const message = ref('')
const notRepo = ref(false)
const initting = ref(false)

const bridgeReady = Boolean(getElectronBridge()?.workspace?.gitStatus)
const hint = computed(() => bridgeReady ? (root.value ? '' : '正在定位工作区…') : 'Git 仅在桌面端可用')

const isStaged = (file: GitFileChange): boolean => file.index !== ' ' && file.index !== '?'
const letters = (file: GitFileChange): string => `${file.index}${file.worktree}`.replace(/ /g, '·')
const canCommit = computed(() => Boolean(message.value.trim()) && Boolean(status.value?.files.some(isStaged)) && !committing.value)

const diffLines = computed(() => (diff.value || '').split('\n').map(text => ({
  text,
  tone: text.startsWith('+') && !text.startsWith('+++') ? 'is-add'
    : text.startsWith('-') && !text.startsWith('---') ? 'is-del'
      : text.startsWith('@@') ? 'is-hunk' : ''
})))

const messageOf = (cause: any) => cause?.message || 'Git 操作失败'

async function resolveRoot(): Promise<void> {
  try {
    const folder = await getElectronBridge()?.workspace?.current?.()
    if (folder) {
      root.value = folder.root
      workspaceId.value = folder.id
      return
    }
    if (props.missionId) {
      const listing = await agentosApi.listWorkspaceFiles(props.missionId, '.')
      root.value = listing.workspaceRoot
    }
  } catch (cause) {
    error.value = messageOf(cause)
  }
}

async function refresh(): Promise<void> {
  if (!root.value || !bridgeReady) return
  loading.value = true
  error.value = ''
  try {
    status.value = await gitStatus(root.value)
    notRepo.value = false
    if (selected.value && !status.value.files.some(file => file.path === selected.value?.path)) {
      selected.value = null
      diff.value = null
    }
  } catch (cause) {
    status.value = null
    selected.value = null
    diff.value = null
    if (isNotRepositoryError(cause)) {
      notRepo.value = true
      error.value = ''
      return
    }
    notRepo.value = false
    error.value = messageOf(cause)
  } finally {
    loading.value = false
  }
}

/** 引导主操作：在当前工作文件夹执行 git init，成功后回到正常面板。 */
async function initRepo(): Promise<void> {
  if (initting.value || !root.value) return
  initting.value = true
  error.value = ''
  try {
    await gitInit(root.value)
    notRepo.value = false
    await refresh()
  } catch (cause) {
    error.value = messageOf(cause)
  } finally {
    initting.value = false
  }
}

/** 引导次操作：换一个工作文件夹；广播事件让文件浏览器同步刷新列表。 */
async function switchFolder(): Promise<void> {
  if (initting.value) return
  error.value = ''
  try {
    const folder = await getElectronBridge()?.workspace?.choose()
    if (!folder) return
    root.value = folder.root
    workspaceId.value = folder.id
    notRepo.value = false
    status.value = null
    selected.value = null
    diff.value = null
    window.dispatchEvent(new CustomEvent('workspace-folder-changed', { detail: { id: folder.id, root: folder.root } }))
    await refresh()
  } catch (cause) {
    error.value = messageOf(cause)
  }
}

async function select(file: GitFileChange): Promise<void> {
  selected.value = file
  diff.value = null
  diffLoading.value = true
  try {
    diff.value = await gitDiff(root.value, file.path, isStaged(file))
  } catch (cause) {
    error.value = messageOf(cause)
  } finally {
    diffLoading.value = false
  }
}

async function stage(file: GitFileChange): Promise<void> {
  busy.value = true
  try {
    await gitStage(root.value, [file.path])
    await refresh()
  } catch (cause) {
    error.value = messageOf(cause)
  } finally {
    busy.value = false
  }
}

async function unstage(file: GitFileChange): Promise<void> {
  busy.value = true
  try {
    await gitUnstage(root.value, [file.path])
    await refresh()
  } catch (cause) {
    error.value = messageOf(cause)
  } finally {
    busy.value = false
  }
}

async function commit(): Promise<void> {
  if (!canCommit.value) return
  committing.value = true
  error.value = ''
  try {
    const result = await gitCommit(root.value, message.value.trim())
    if (!result.committed) error.value = result.output.trim() || '提交未完成'
    else message.value = ''
    await refresh()
  } catch (cause) {
    error.value = messageOf(cause)
  } finally {
    committing.value = false
  }
}

function openFile(file: GitFileChange): void {
  emit('open-file', {
    missionId: props.missionId,
    workspaceRoot: root.value,
    relativePath: file.path,
    name: file.path.split('/').pop() || file.path,
    ...(workspaceId.value ? { desktopWorkspaceId: workspaceId.value } : {})
  })
}

/** 「对比」= 打开文件 + 行内 diff（文件已打开时由 diffRequest 直接切换）。 */
function openDiff(file: GitFileChange): void {
  requestDiff(file.path)
  emit('open-file', {
    missionId: props.missionId,
    workspaceRoot: root.value,
    relativePath: file.path,
    name: file.path.split('/').pop() || file.path,
    diff: true,
    ...(workspaceId.value ? { desktopWorkspaceId: workspaceId.value } : {})
  })
}

onMounted(async () => {
  await resolveRoot()
  await refresh()
})
</script>

<style scoped>
.workspace-git { display:flex; flex-direction:column; width:100%; min-width:0; min-height:0; color:var(--wb-text); font:12px/1.45 var(--font-sans, sans-serif); }
.workspace-git__head { display:flex; align-items:center; gap:8px; padding:8px 10px 6px; }
.workspace-git__branch { flex:1; min-width:0; overflow:hidden; color:var(--wb-text); font:11.5px var(--font-mono, monospace); text-overflow:ellipsis; white-space:nowrap; }
.workspace-git__ahead { color:var(--wb-text-muted); font:10px var(--font-mono, monospace); }
.workspace-git__refresh { padding:2px 8px; border:1px solid var(--wb-border-strong); border-radius:4px; background:transparent; color:var(--wb-text-secondary); font-size:10.5px; cursor:pointer; }
.workspace-git__refresh:disabled { opacity:.5; cursor:default; }
.workspace-git__hint, .workspace-git__error { margin:8px 12px; font-size:11px; }
.workspace-git__hint { color:var(--wb-text-muted); }
.workspace-git__error { color:var(--wb-danger); }
.workspace-git__clean { padding:14px 12px; color:var(--wb-text-muted); font-size:11px; }
.workspace-git__init { display:flex; flex-direction:column; align-items:flex-start; gap:5px; margin:12px; padding:14px 12px; border:1px solid var(--wb-border); border-radius:8px; background:var(--wb-surface-inset, transparent); }
.workspace-git__init-icon { width:18px; height:18px; margin-bottom:2px; fill:none; stroke:var(--wb-accent); stroke-width:1.2; stroke-linecap:round; }
.workspace-git__init strong { color:var(--wb-text); font-size:12px; }
.workspace-git__init-path { max-width:100%; overflow:hidden; color:var(--wb-text-secondary); font:10.5px var(--font-mono, monospace); text-overflow:ellipsis; white-space:nowrap; }
.workspace-git__init-copy { margin:0; color:var(--wb-text-muted); font-size:11px; line-height:1.5; }
.workspace-git__init-actions { display:flex; gap:6px; margin-top:6px; }
.workspace-git__init-btn { padding:4px 10px; border:1px solid color-mix(in srgb, var(--wb-accent) 55%, var(--wb-border-strong)); border-radius:4px; background:transparent; color:var(--wb-accent); font-size:11px; cursor:pointer; }
.workspace-git__init-btn:hover:not(:disabled) { background:var(--wb-hover); }
.workspace-git__init-btn:disabled { opacity:.5; cursor:default; }
.workspace-git__switch-btn { padding:4px 10px; border:1px solid var(--wb-border-strong); border-radius:4px; background:transparent; color:var(--wb-text-secondary); font-size:11px; cursor:pointer; }
.workspace-git__switch-btn:hover:not(:disabled) { color:var(--wb-text); background:var(--wb-hover); }
.workspace-git__files { flex:1; min-height:0; margin:0; padding:0 0 8px; overflow:auto; list-style:none; }
.workspace-git__files li { display:flex; flex-direction:column; }
.workspace-git__file { display:flex; align-items:center; gap:7px; width:100%; padding:4px 12px; border:0; background:transparent; color:inherit; text-align:left; cursor:pointer; }
.workspace-git__file:hover, .workspace-git__file.is-active { background:var(--wb-hover); }
.workspace-git__letters { width:18px; color:var(--wb-warning); font:10px var(--font-mono, monospace); }
.workspace-git__path { min-width:0; overflow:hidden; font-size:11.5px; text-overflow:ellipsis; white-space:nowrap; }
.workspace-git__actions { display:none; gap:6px; padding:0 12px 5px 37px; }
.workspace-git__files li:hover .workspace-git__actions { display:flex; }
.workspace-git__actions button { padding:1px 7px; border:1px solid var(--wb-border-strong); border-radius:4px; background:transparent; color:var(--wb-text-secondary); font-size:10px; cursor:pointer; }
.workspace-git__actions button:hover { color:var(--wb-text); background:var(--wb-hover); }
.workspace-git__diff { flex:0 0 auto; max-height:40%; display:flex; flex-direction:column; border-top:1px solid var(--wb-border); }
.workspace-git__diff-head { padding:5px 12px; color:var(--wb-text-muted); font:10px var(--font-mono, monospace); }
.workspace-git__diff-body { margin:0; padding:0 0 8px; overflow:auto; font:11px/1.5 var(--font-mono, Consolas, monospace); }
.workspace-git__diff-line { display:block; padding:0 12px; white-space:pre; }
.workspace-git__diff-line.is-add { color:var(--sem-success); background:color-mix(in srgb, var(--sem-success) 8%, transparent); }
.workspace-git__diff-line.is-del { color:var(--sem-failed); background:color-mix(in srgb, var(--sem-failed) 8%, transparent); }
.workspace-git__diff-line.is-hunk { color:var(--wb-accent); }
.workspace-git__diff-empty { margin:6px 12px; color:var(--wb-text-muted); font-size:11px; }
.workspace-git__commit { flex:none; display:flex; gap:6px; padding:8px 10px; border-top:1px solid var(--wb-border); }
.workspace-git__commit textarea { flex:1; min-width:0; padding:4px 6px; border:1px solid var(--wb-border-strong); border-radius:4px; background:var(--wb-surface-inset, #161616); color:var(--wb-text); font:11.5px/1.4 inherit; resize:vertical; }
.workspace-git__commit button { align-self:flex-start; padding:4px 10px; border:1px solid var(--wb-border-strong); border-radius:4px; background:var(--wb-surface-1); color:var(--wb-text); font-size:11px; cursor:pointer; }
.workspace-git__commit button:disabled { opacity:.45; cursor:default; }
</style>
