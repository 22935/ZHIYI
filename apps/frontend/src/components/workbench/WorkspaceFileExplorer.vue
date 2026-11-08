<template>
  <section class="workspace-file-explorer" aria-label="工作区文件">
    <div class="workspace-file-explorer__root" :title="workspaceRoot || '工作区不可用'">
      <span class="workspace-file-explorer__root-icon" aria-hidden="true">
        <el-icon><FolderOpened /></el-icon>
      </span>
      <span class="workspace-file-explorer__root-path">{{ workspaceRoot || '工作区不可用' }}</span>
    </div>

    <div class="workspace-file-explorer__tools">
      <button v-if="desktopWorkspace" type="button" class="workspace-file-explorer__open" @click="chooseFolder">打开文件夹</button>
      <label class="workspace-file-explorer__filter">
        <el-icon aria-hidden="true"><Search /></el-icon>
        <input v-model="filterText" type="search" aria-label="筛选文件名" placeholder="筛选文件..." />
        <button
          v-if="filterText"
          class="workspace-file-explorer__clear"
          type="button"
          aria-label="清除筛选"
          @click="filterText = ''"
        >×</button>
      </label>
      <button
        class="workspace-file-explorer__refresh"
        type="button"
        aria-label="刷新文件列表"
        title="刷新"
        :disabled="rootLoading || !props.missionId"
        @click="refresh"
      >
        <el-icon :class="{ 'is-spinning': rootLoading }"><Refresh /></el-icon>
      </button>
    </div>

    <div class="workspace-file-explorer__tree" role="tree" aria-label="工作区文件树">
      <div v-if="rootLoading && !nodes.length" class="workspace-file-explorer__message" role="status">
        正在读取工作区…
      </div>
      <div v-else-if="rootError" class="workspace-file-explorer__message is-error" role="alert">
        <span>{{ rootError }}</span>
        <button type="button" @click="refresh">重试</button>
      </div>
      <div v-else-if="visibleNodes.length === 0" class="workspace-file-explorer__message">
        {{ filterText ? '没有匹配的已加载文件' : '此目录为空' }}
      </div>
      <WorkspaceFileTreeNode
        v-for="node in visibleNodes"
        :key="node.path"
        :node="node"
        :selected-path="selectedPath"
        :filter-text="filterText"
        @toggle-directory="toggleDirectory"
        @select-file="selectFile"
        @retry-directory="loadDirectory"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { getElectronBridge } from '@/platform/electron/bridge'
import { FolderOpened, Refresh, Search } from '@element-plus/icons-vue'
import { agentosApi, type WorkspaceFileEntry, type WorkspaceFileOpenRequest } from '@/services/api/agentos'
import WorkspaceFileTreeNode from './WorkspaceFileTreeNode.vue'
import type { WorkspaceFileTreeItem, WorkspaceFileVisibleTreeItem } from './workspaceFileExplorer.types'

const props = defineProps<{ missionId: string }>()
const emit = defineEmits<{ 'open-file': [request: WorkspaceFileOpenRequest] }>()

const ignoredDirectories = new Set([
  '.git', 'node_modules', 'dist', 'target', '__pycache__', '.venv', 'coverage',
  '.pytest_cache', '.mypy_cache', '.ruff_cache', 'build', '.next', '.nuxt'
])

const desktopWorkspace = getElectronBridge()?.workspace
const desktopWorkspaceId = ref<string | null>(null)
async function chooseFolder() {
  try {
    const folder = await desktopWorkspace?.choose()
    if (!folder) return
    desktopWorkspaceId.value = folder.id
    workspaceRoot.value = folder.root
    selectedPath.value = ''; filterText.value = ''
    await refresh()
  } catch (error: any) { rootError.value = error?.message || '无法打开文件夹' }
}
const listFiles = (missionId: string, path: string) => desktopWorkspaceId.value && desktopWorkspace
  ? desktopWorkspace.list(desktopWorkspaceId.value, path) : agentosApi.listWorkspaceFiles(missionId, path)
const nodes = ref<WorkspaceFileTreeItem[]>([])
const workspaceRoot = ref('')
const selectedPath = ref('')
const filterText = ref('')
const rootLoading = ref(false)
const rootError = ref('')

const makeNodes = (entries: WorkspaceFileEntry[]): WorkspaceFileTreeItem[] => entries
  .filter(entry => desktopWorkspaceId.value || !(entry.type === 'directory' && ignoredDirectories.has(entry.name.toLowerCase())))
  .map(entry => ({
    ...entry,
    expanded: false,
    loaded: false,
    loading: false,
    error: '',
    children: [],
    visibleChildren: []
  }))
  .sort((left, right) => {
    if (left.type !== right.type) return left.type === 'directory' ? -1 : 1
    return left.name.localeCompare(right.name, undefined, { sensitivity: 'base' })
  })

// The filter only inspects directories already fetched by expanding them. It never triggers a tree scan.
const filterNodes = (items: WorkspaceFileTreeItem[], query: string): WorkspaceFileVisibleTreeItem[] => {
  const normalized = query.trim().toLocaleLowerCase()
  return items.flatMap(node => {
    const visibleChildren = filterNodes(node.children, query)
    if (!normalized || node.name.toLocaleLowerCase().includes(normalized) || visibleChildren.length) {
      return [{ ...node, source: node, visibleChildren }]
    }
    return []
  })
}

const visibleNodes = computed(() => filterNodes(nodes.value, filterText.value))

const errorMessage = (error: unknown) => {
  const responseData = (error as { response?: { data?: { detail?: unknown; message?: unknown } } })?.response?.data
  return typeof responseData?.detail === 'string' ? responseData.detail
    : typeof responseData?.message === 'string' ? responseData.message : (error as Error)?.message || '无法读取工作区目录'
}

const refresh = async () => {
  const missionId = props.missionId
  const selectedWorkspace = desktopWorkspaceId.value
  if (!missionId && !desktopWorkspaceId.value) {
    workspaceRoot.value = ''
    nodes.value = []
    rootError.value = '当前没有可用的工作区'
    return
  }
  rootLoading.value = true
  rootError.value = ''
  try {
    const listing = await listFiles(missionId, '.')
    if (missionId !== props.missionId || selectedWorkspace !== desktopWorkspaceId.value) return
    workspaceRoot.value = listing.workspaceRoot
    nodes.value = makeNodes(listing.entries)
  } catch (error) {
    if (missionId !== props.missionId || selectedWorkspace !== desktopWorkspaceId.value) return
    rootError.value = errorMessage(error)
    nodes.value = []
  } finally {
    if (missionId === props.missionId && selectedWorkspace === desktopWorkspaceId.value) rootLoading.value = false
  }
}

const loadDirectory = async (node: WorkspaceFileTreeItem) => {
  if (node.loading || (node.loaded && !node.error)) return
  const missionId = props.missionId
  const selectedWorkspace = desktopWorkspaceId.value
  node.loading = true
  node.error = ''
  try {
    const listing = await listFiles(missionId, node.path)
    if (missionId !== props.missionId || selectedWorkspace !== desktopWorkspaceId.value) return
    workspaceRoot.value = listing.workspaceRoot
    node.children = makeNodes(listing.entries)
    node.loaded = true
  } catch (error) {
    if (missionId === props.missionId && selectedWorkspace === desktopWorkspaceId.value) node.error = errorMessage(error)
  } finally {
    node.loading = false
  }
}

const toggleDirectory = async (node: WorkspaceFileTreeItem) => {
  node.expanded = !node.expanded
  if (node.expanded) await loadDirectory(node)
}

const selectFile = (node: WorkspaceFileTreeItem) => {
  selectedPath.value = node.path
  emit('open-file', {
    missionId: props.missionId,
    workspaceRoot: workspaceRoot.value,
    relativePath: node.path,
    name: node.name,
    ...(desktopWorkspaceId.value ? {desktopWorkspaceId: desktopWorkspaceId.value} : {})
  })
}

watch(() => props.missionId, () => {
  selectedPath.value = ''
  workspaceRoot.value = ''
  nodes.value = []
  void refresh()
})

// Git 面板「打开其他文件夹」切换目录后广播此事件，两侧面板保持同一工作文件夹。
const onFolderChanged = (event: Event) => {
  const detail = (event as CustomEvent<{ id?: string; root?: string }>).detail
  if (!detail?.root) return
  desktopWorkspaceId.value = typeof detail.id === 'string' ? detail.id : null
  workspaceRoot.value = detail.root
  selectedPath.value = ''
  filterText.value = ''
  nodes.value = []
  void refresh()
}

onMounted(async () => {
  window.addEventListener('workspace-folder-changed', onFolderChanged)
  try { const folder = await desktopWorkspace?.current(); if (folder) { desktopWorkspaceId.value = folder.id; workspaceRoot.value = folder.root } }
  catch { /* The native folder picker remains available. */ }
  await refresh()
})

onUnmounted(() => {
  window.removeEventListener('workspace-folder-changed', onFolderChanged)
})
</script>

<style scoped>
.workspace-file-explorer__open { flex:none; border:1px solid var(--wb-border-strong); border-radius:4px; background:var(--wb-surface-1); color:var(--wb-text-secondary); padding:4px 8px; font:inherit; cursor:pointer; }
.workspace-file-explorer__open:hover { color:var(--wb-text); background:var(--wb-hover); }
.workspace-file-explorer__open:focus-visible { outline:2px solid var(--wb-accent); outline-offset:2px; }
.workspace-file-explorer {
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  color: var(--wb-text);
  font: 12px/1.45 var(--font-sans, sans-serif);
}
.workspace-file-explorer__root {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 7px;
  padding: 3px 10px 8px;
  color: var(--wb-text-secondary);
}
.workspace-file-explorer__root-icon { flex: 0 0 auto; color: var(--wb-accent, #579dff); }
.workspace-file-explorer__root-path { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workspace-file-explorer__tools { display: flex; align-items: center; gap: 5px; padding: 0 8px 7px; }
.workspace-file-explorer__filter {
  display: flex;
  height: 26px;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 6px;
  padding: 0 7px;
  color: var(--wb-text-muted, #818999);
  background: var(--wb-surface-2, rgba(255, 255, 255, 0.035));
  border: 1px solid var(--wb-border-subtle, rgba(135, 148, 169, 0.16));
  border-radius: 5px;
}
.workspace-file-explorer__filter:focus-within { border-color: var(--wb-border-focus, rgba(87, 157, 255, 0.5)); }
.workspace-file-explorer__filter input { width: 100%; min-width: 0; padding: 0; color: var(--wb-text); font: inherit; background: transparent; border: 0; outline: 0; }
.workspace-file-explorer__filter input::placeholder { color: var(--wb-text-muted, #818999); }
.workspace-file-explorer__filter input::-webkit-search-cancel-button { display: none; }
.workspace-file-explorer__clear,
.workspace-file-explorer__refresh {
  display: grid;
  width: 25px;
  height: 25px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--wb-text-secondary);
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 4px;
}
.workspace-file-explorer__clear { width: 18px; height: 20px; font-size: 16px; }
.workspace-file-explorer__clear:hover,
.workspace-file-explorer__refresh:hover:not(:disabled) { color: var(--wb-text); background: var(--wb-surface-hover, rgba(255, 255, 255, 0.07)); }
.workspace-file-explorer__refresh:disabled { cursor: default; opacity: 0.45; }
.workspace-file-explorer__tree { min-height: 0; flex: 1; overflow: auto; padding: 0 4px 8px; }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__branch) { min-width: 0; }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__row) {
  display: flex;
  width: 100%;
  height: 25px;
  min-width: 0;
  align-items: center;
  gap: 5px;
  padding: 0 5px 0 2px;
  overflow: hidden;
  color: var(--wb-text-secondary);
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  background: transparent;
  border: 0;
  border-radius: 4px;
}
.workspace-file-explorer__tree :deep(.workspace-file-explorer__row:hover) { color: var(--wb-text); background: var(--wb-surface-hover, rgba(255, 255, 255, 0.055)); }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__row.is-selected) { color: var(--wb-text); background: var(--wb-selection, rgba(87, 157, 255, 0.18)); }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__chevron) {
  display: grid;
  width: 12px;
  height: 16px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--wb-text-muted, #818999);
  transition: transform 100ms ease;
}
.workspace-file-explorer__tree :deep(.workspace-file-explorer__chevron.is-expanded) { transform: rotate(90deg); }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__file-icon) { display: grid; width: 15px; flex: 0 0 auto; place-items: center; color: var(--wb-text-muted, #818999); }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__row.is-directory .workspace-file-explorer__file-icon) { color: var(--wb-icon-folder, #c5a86c); }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__row.is-selected .workspace-file-explorer__file-icon) { color: var(--wb-accent, #579dff); }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__name) { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__inline-status) { margin-left: auto; color: var(--wb-text-muted, #818999); font-size: 11px; }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__children) { padding-left: 13px; }
.workspace-file-explorer__message { display: flex; min-height: 28px; align-items: center; gap: 7px; padding: 3px 8px; color: var(--wb-text-muted, #818999); font-size: 11px; }
.workspace-file-explorer__message.is-error { color: var(--wb-danger, #e58b8b); }
.workspace-file-explorer__message button { padding: 0; color: var(--wb-accent, #579dff); cursor: pointer; background: none; border: 0; font: inherit; }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__message.is-error) { color: var(--wb-danger, #e58b8b); }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__message button) { padding: 0; color: var(--wb-accent, #579dff); cursor: pointer; background: none; border: 0; font: inherit; }
.workspace-file-explorer__tree :deep(.workspace-file-explorer__message--nested) { padding-left: 18px; }
.is-spinning { animation: workspace-file-explorer-spin 900ms linear infinite; }
@keyframes workspace-file-explorer-spin { to { transform: rotate(360deg); } }
</style>
