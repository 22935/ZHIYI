<template>
  <section class="catalog-panel" aria-label="平台资源目录">
    <div v-if="loading" class="catalog-panel__state" role="status">正在读取平台资源目录…</div>
    <div v-else-if="!items.length" class="catalog-panel__state">
      <strong>目录正在准备中</strong>
      <span>平台目录包由本机管理员维护，接入已部署的本地服务可使用“自定义资源”。</span>
    </div>
    <div v-else class="catalog-grid">
      <article v-for="item in items" :key="item.catalogId" class="catalog-item">
        <header class="catalog-item__topline"><span>{{ kindLabel(item.kind) }}</span><span>v{{ item.version }}</span></header>
        <div class="catalog-item__symbol" :class="`is-${item.kind}`" aria-hidden="true"><el-icon><component :is="kindIcon(item.kind)" /></el-icon></div>
        <h3>{{ item.displayName || item.catalogId }}</h3>
        <p>{{ item.description }}</p>
        <ul v-if="item.capabilities?.length" class="catalog-capabilities" aria-label="资源能力"><li v-for="capability in item.capabilities.filter(value => value !== 'tool.invoke')" :key="capability">{{ capability }}</li></ul>
        <p v-if="Array.isArray(item.requirements.formats)" class="catalog-formats">{{ item.requirements.formats.join(' · ') }}</p>
        <dl><div><dt>包体</dt><dd>{{ sizeLabel(item.sizeBytes) }}</dd></div><div><dt>要求</dt><dd>{{ requirementLabel(item.requirements) }}</dd></div></dl>
        <button class="catalog-item__install" type="button" :disabled="busy || installedIds.has(item.catalogId)" :data-testid="`install-${item.catalogId}`" @click="$emit('install', item)">
          <el-icon aria-hidden="true"><component :is="installedIds.has(item.catalogId) ? CircleCheck : Download" /></el-icon>
          <span>{{ installedIds.has(item.catalogId) ? '已安装' : busy ? '处理中…' : '安装到本机' }}</span>
        </button>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheck, Cpu, Download, Tools } from '@element-plus/icons-vue'
import type { MarketplaceCatalogItem, MarketplaceInstallation } from '@/services/api/agentos'

const props = defineProps<{
  items: MarketplaceCatalogItem[]
  installations: MarketplaceInstallation[]
  loading: boolean
  busy: boolean
}>()
defineEmits<{ (event: 'install', item: MarketplaceCatalogItem): void }>()
const kindLabel = (kind: string) => ({ model_server: '模型服务', tool_service: '工具服务', execution_backend: '执行服务' }[kind] || '本地能力')
const kindIcon = (kind: string) => kind === 'model_server' ? Cpu : Tools
const sizeLabel = (size: number) => size >= 1024 ** 3 ? `${(size / 1024 ** 3).toFixed(1)} GB` : size >= 1024 ** 2 ? `${(size / 1024 ** 2).toFixed(1)} MB` : size > 0 ? `${(size / 1024).toFixed(1)} KB` : '本地包'
const requirementLabel = (requirements: Record<string, unknown>) => {
  const parts = []
  if (requirements.gpu) parts.push(String(requirements.gpu))
  if (requirements.memoryGb) parts.push(`${requirements.memoryGb} GB 内存`)
  if (requirements.python) parts.push(`Python ${requirements.python}`)
  if (requirements.offline) parts.push('离线运行')
  return parts.join(' · ') || '通用设备'
}
const installedIds = computed(() => new Set(props.installations.filter(job => !['failed', 'removed'].includes(job.status)).map(job => job.catalogId).filter((id): id is string => Boolean(id))))
</script>

<style scoped>
.catalog-capabilities { display: flex; flex-wrap: wrap; gap: 6px; padding: 0; margin: 10px 0 4px; list-style: none; }.catalog-capabilities li { padding: 3px 7px; color: var(--primary-color); border: 1px solid var(--primary-line); font: 10px var(--font-mono, monospace); }.catalog-formats { padding-top: 6px; overflow-wrap: anywhere; }
.catalog-panel__state { display: grid; justify-items: center; align-content: center; gap: 8px; min-height: 270px; color: var(--text-secondary); font-size: 12px; text-align: center; }.catalog-panel__state strong { color: var(--text-primary); font-size: 14px; }.catalog-panel__state span { max-width: 440px; line-height: 1.6; }
.catalog-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, 248px), 1fr)); gap: 14px; padding: 18px 0; }.catalog-item { display: grid; grid-template-rows: auto auto auto minmax(40px, 1fr) auto auto; min-width: 0; padding: 16px; border: 1px solid var(--border-light); background: var(--bg-card); transition: border-color .18s ease, transform .18s ease; }.catalog-item:hover { border-color: var(--primary-line); transform: translateY(-2px); }.catalog-item__topline { display: flex; justify-content: space-between; color: var(--text-muted); font: 10px var(--font-mono, monospace); }.catalog-item__symbol { display: grid; place-items: center; width: 42px; aspect-ratio: 1; margin-top: 19px; border: 1px solid color-mix(in srgb, var(--primary-color) 32%, var(--border-light)); color: var(--primary-color); background: color-mix(in srgb, var(--primary-color) 7%, var(--bg-card)); font-size: 19px; }.catalog-item__symbol.is-tool_service { color: var(--success); border-color: color-mix(in srgb, var(--success) 30%, var(--border-light)); }.catalog-item h3 { margin: 14px 0 5px; font-size: 14px; }.catalog-item p { min-height: 38px; margin: 0; color: var(--text-secondary); font-size: 11px; line-height: 1.6; }.catalog-item dl { display: flex; gap: 18px; margin: 16px 0; }.catalog-item dl div { display: grid; gap: 4px; }.catalog-item dt { color: var(--text-muted); font-size: 9px; }.catalog-item dd { margin: 0; color: var(--text-secondary); font-size: 10px; }.catalog-item__install { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 34px; border: 1px solid var(--primary-line); color: var(--primary-color); background: transparent; cursor: pointer; font: inherit; font-size: 11px; }.catalog-item__install:hover:not(:disabled) { background: var(--primary-fade); }.catalog-item__install:disabled { cursor: default; opacity: .65; }
</style>
