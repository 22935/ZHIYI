<template>
  <div class="resource-page">
    <WorkbenchLayout :show-left="false" :show-right="false" storage-key="zhiyi.resources.store.v2">
      <template #main>
        <main class="resource-page__main" aria-label="资源商店">
          <WorkspacePageHero eyebrow="RESOURCE PLANE / STORE" title="资源商店">
            <template #actions><button class="store-custom-action" type="button" @click="customOpen = true"><el-icon aria-hidden="true"><Plus /></el-icon><span>登记本地服务</span></button></template>
          </WorkspacePageHero>
          <ResourceCenterNav active="store" />

          <section class="store-context" aria-label="资源商店说明">
            <span class="store-context__mark" aria-hidden="true"><el-icon><Box /></el-icon></span>
            <p><strong>平台本地目录</strong><span>目录包由平台维护并校验。安装完成且健康检查通过后，资源才进入端边云调度。</span></p>
            <span class="store-context__count">{{ catalog.length }} 项内容</span>
          </section>

          <div class="store-toolbar">
            <div class="store-tabs" role="tablist" aria-label="商店内容">
              <button type="button" role="tab" :aria-selected="activeTab === 'catalog'" :class="{ active: activeTab === 'catalog' }" @click="activeTab = 'catalog'">平台目录 <small>{{ catalog.length }}</small></button>
              <button type="button" role="tab" :aria-selected="activeTab === 'installed'" :class="{ active: activeTab === 'installed' }" @click="activeTab = 'installed'">已安装 <small>{{ installations.length }}</small></button>
            </div>
            <button type="button" class="store-refresh" title="刷新目录和安装状态" aria-label="刷新目录和安装状态" :disabled="loading" @click="loadAll"><el-icon><Refresh /></el-icon></button>
          </div>

          <MarketplaceCatalogPanel v-if="activeTab === 'catalog'" :items="catalog" :installations="installations" :loading="loading" :busy="Boolean(busyJob)" @install="installItem" />
          <MarketplaceInstalledPanel v-else :items="installations" :loading="loading" :busy-job="busyJob" @stop="stopJob" @uninstall="uninstallJob" @use="toolJob = $event" />
          <p v-if="error" class="store-error" role="alert">{{ error }}</p>
          <p class="store-footnote">自定义资源仅接受本机回环地址，不会执行用户提交的命令。</p>
        </main>
      </template>
    </WorkbenchLayout>
    <CustomResourceDialog v-model="customOpen" :submitting="customSubmitting" :error="customError" @submit="registerCustom" />
    <MarketplaceToolDialog :job="toolJob" @close="toolJob = null" />
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Box, Plus, Refresh } from '@element-plus/icons-vue'
import { agentosApi } from '@/services/api/agentos'
import type { CustomLocalResourceRequest, MarketplaceCatalogItem, MarketplaceInstallation } from '@/services/api/agentos'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import WorkspacePageHero from '@/components/app/WorkspacePageHero.vue'
import ResourceCenterNav from '@/components/resource-center/ResourceCenterNav.vue'
import MarketplaceCatalogPanel from '@/components/resource-center/MarketplaceCatalogPanel.vue'
import MarketplaceInstalledPanel from '@/components/resource-center/MarketplaceInstalledPanel.vue'
import CustomResourceDialog from '@/components/resource-center/CustomResourceDialog.vue'
import MarketplaceToolDialog from '@/components/resource-center/MarketplaceToolDialog.vue'

const catalog = ref<MarketplaceCatalogItem[]>([])
const installations = ref<MarketplaceInstallation[]>([])
const loading = ref(true)
const error = ref('')
const activeTab = ref<'catalog' | 'installed'>('catalog')
const customOpen = ref(false)
const customSubmitting = ref(false)
const customError = ref('')
const busyJob = ref('')
const toolJob = ref<MarketplaceInstallation | null>(null)
let pollTimer: ReturnType<typeof setInterval> | undefined
let disposed = false

const hasActiveJobs = () => installations.value.some(job => ['queued', 'installing', 'registering', 'uninstalling'].includes(job.status))
const updatePolling = () => {
  if (hasActiveJobs() && !pollTimer) pollTimer = setInterval(() => { void loadInstallations(false) }, 3000)
  if (!hasActiveJobs() && pollTimer) { clearInterval(pollTimer); pollTimer = undefined }
}
async function loadInstallations(showLoading = true) {
  if (showLoading) loading.value = true
  try {
    const response = await agentosApi.listMarketplaceInstallations()
    if (!disposed) installations.value = response.items
  } catch {
    if (!disposed) error.value = '安装任务暂时无法读取。'
  } finally {
    if (!disposed && showLoading) loading.value = false
    updatePolling()
  }
}
async function loadAll() {
  loading.value = true
  error.value = ''
  try {
    const [catalogResponse, installResponse] = await Promise.all([
      agentosApi.listMarketplaceCatalog(), agentosApi.listMarketplaceInstallations()
    ])
    if (disposed) return
    catalog.value = catalogResponse.items
    installations.value = installResponse.items
  } catch {
    if (!disposed) error.value = '商店数据暂时不可用，请稍后重试。'
  } finally {
    if (!disposed) loading.value = false
    updatePolling()
  }
}
async function installItem(item: MarketplaceCatalogItem) {
  busyJob.value = item.catalogId
  error.value = ''
  try {
    await agentosApi.installMarketplaceItem({ catalogId: item.catalogId })
    activeTab.value = 'installed'
    ElMessage.success('安装任务已创建')
    await loadAll()
  } catch {
    error.value = '安装任务创建失败，请检查目录包和本地环境。'
  } finally { busyJob.value = '' }
}
async function registerCustom(request: CustomLocalResourceRequest) {
  customSubmitting.value = true
  customError.value = ''
  try {
    const job = await agentosApi.createCustomMarketplaceResource(request)
    customOpen.value = false
    activeTab.value = 'installed'
    ElMessage.success(job.status === 'running' ? '本地服务已接入' : '服务检查未通过，可在任务中查看状态')
    await loadAll()
  } catch (cause) {
    customError.value = (cause as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '服务登记失败，请确认本地地址可访问。'
  } finally { customSubmitting.value = false }
}
async function stopJob(job: MarketplaceInstallation) {
  busyJob.value = job.jobId
  try { await agentosApi.stopMarketplaceInstallation(job.jobId); await loadAll(); ElMessage.success('资源已停止') }
  catch { error.value = '停止资源失败。' }
  finally { busyJob.value = '' }
}
async function uninstallJob(job: MarketplaceInstallation) {
  try { await ElMessageBox.confirm(`卸载“${job.displayName || job.catalogId || '本地资源'}”并从资源管理中移除？`, '卸载资源', { confirmButtonText: '卸载', cancelButtonText: '取消', type: 'warning' }) }
  catch { return }
  busyJob.value = job.jobId
  try { await agentosApi.uninstallMarketplaceInstallation(job.jobId); await loadAll(); ElMessage.success('资源已卸载') }
  catch { error.value = '卸载失败，资源状态未被隐藏。' }
  finally { busyJob.value = '' }
}

onMounted(() => { disposed = false; void loadAll() })
onBeforeUnmount(() => { disposed = true; if (pollTimer) clearInterval(pollTimer) })
</script>

<style scoped>
.resource-page { width: 100%; height: 100%; min-height: 0; overflow: hidden; background: var(--bg-app); }.resource-page__main { width: min(100%, 1400px); height: 100%; overflow: auto; margin: 0 auto; padding: 0 clamp(18px, 4vw, 58px) 36px; color: var(--text-primary); }
.store-custom-action { display: inline-flex; align-items: center; gap: 7px; min-height: 36px; padding: 0 13px; border: 1px solid var(--primary-line); color: var(--primary-color); background: var(--primary-fade); cursor: pointer; font: inherit; font-size: 11px; }.store-context { display: flex; align-items: center; gap: 13px; margin: 18px 0 20px; padding: 13px 15px; border-left: 2px solid var(--primary-color); background: color-mix(in srgb, var(--primary-color) 5%, var(--bg-card)); }.store-context__mark { display: grid; place-items: center; width: 34px; aspect-ratio: 1; color: var(--primary-color); border: 1px solid var(--primary-line); font-size: 16px; }.store-context p { display: grid; gap: 3px; min-width: 0; margin: 0; }.store-context p strong { font-size: 11px; font-weight: 600; }.store-context p span { color: var(--text-secondary); font-size: 10px; line-height: 1.5; }.store-context__count { flex: 0 0 auto; margin-left: auto; color: var(--text-muted); font: 10px var(--font-mono, monospace); }.store-toolbar { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--border-light); }.store-tabs { display: flex; gap: 19px; }.store-tabs button { position: relative; display: inline-flex; align-items: center; gap: 6px; min-height: 42px; border: 0; color: var(--text-secondary); background: transparent; cursor: pointer; font: inherit; font-size: 11px; }.store-tabs button.active { color: var(--primary-color); }.store-tabs button.active::after { position: absolute; right: 0; bottom: -1px; left: 0; height: 2px; background: var(--primary-color); content: ''; }.store-tabs small { color: var(--text-muted); font: 9px var(--font-mono, monospace); }.store-refresh { display: grid; place-items: center; width: 32px; aspect-ratio: 1; border: 1px solid var(--border-light); color: var(--text-secondary); background: transparent; cursor: pointer; }.store-refresh:hover:not(:disabled) { color: var(--primary-color); border-color: var(--primary-line); }.store-refresh:disabled { opacity: .5; cursor: wait; }.store-error { padding: 9px 11px; border-left: 2px solid var(--danger); color: var(--danger); background: color-mix(in srgb, var(--danger) 6%, var(--bg-card)); font-size: 11px; }.store-footnote { margin: 10px 0 0; color: var(--text-muted); font-size: 9px; }
@media (max-width: 600px) { .resource-page__main { padding-right: 14px; padding-left: 14px; }.store-context { align-items: flex-start; }.store-context__count { padding-top: 4px; }.store-context p span { max-width: 36ch; } }
</style>
