<template>
  <div class="resource-page">
    <WorkbenchLayout :show-left="false" :show-right="false" storage-key="zhiyi.resources.overview.v2">
      <template #main>
        <main class="resource-page__main" aria-label="资源概览">
          <WorkspacePageHero eyebrow="RESOURCE PLANE / 01" title="资源概览">
            <template #actions>
              <RouterLink class="resource-button resource-button--primary" to="/agentos/resources/store">浏览资源商店</RouterLink>
            </template>
          </WorkspacePageHero>
          <ResourceCenterNav active="overview" />

          <section class="resource-pulse" aria-label="资源运行摘要" :aria-busy="loading">
            <div class="resource-pulse__lead">
              <span class="resource-kicker">LIVE RESOURCE FIELD</span>
              <strong>{{ totals.runtime }}</strong>
              <span>已登记运行时</span>
              <i class="resource-pulse__rule" aria-hidden="true"></i>
              <small>{{ totals.online }} 可调度 · {{ totals.attention }} 需关注</small>
            </div>
            <div class="resource-pulse__tiers">
              <div v-for="tier in tiers" :key="tier.id" class="tier-readout" :class="`is-${tier.id}`">
                <span class="tier-readout__index">{{ tier.index }}</span>
                <div><small>{{ tier.label }}</small><strong>{{ tier.count }}</strong><span>项资源</span></div>
                <i aria-hidden="true"></i>
              </div>
            </div>
          </section>

          <section class="resource-overview-grid">
            <div class="resource-overview-grid__heading">
              <div><span class="resource-kicker">CONNECTED CAPABILITIES</span><h2>正在运行</h2></div>
              <RouterLink to="/agentos/resources/manage">打开资源管理 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink>
            </div>
            <div v-if="loading" class="resource-loading" role="status">正在读取资源状态…</div>
            <div v-else-if="error" class="resource-loading is-error" role="alert">
              <span>{{ error }}</span><button type="button" @click="load">重试</button>
            </div>
            <div v-else-if="!resources.length" class="resource-empty">
              <span class="resource-empty__mark" aria-hidden="true">+</span>
              <strong>资源网络尚未建立</strong>
              <span>从本地目录安装一个模型服务，或登记已部署的本地能力。</span>
              <RouterLink to="/agentos/resources/store">前往资源商店</RouterLink>
            </div>
            <div v-else class="resource-recent-list">
              <article v-for="item in recentResources" :key="item.profile.resourceId" class="resource-recent-row">
                <span class="resource-recent-row__signal" :class="`is-${item.snapshot.healthStatus}`" aria-hidden="true"></span>
                <div class="resource-recent-row__name"><strong>{{ item.profile.displayName || item.profile.resourceId }}</strong><span>{{ kindLabel(item.profile.runtimeKind || item.profile.resourceType) }}<template v-if="item.profile.provider"> · {{ item.profile.provider }}</template></span></div>
                <span class="resource-recent-row__tier">{{ tierLabel(item.profile.deploymentTier) }}</span>
                <span class="resource-recent-row__health">{{ healthLabel(item.snapshot.healthStatus) }}</span>
              </article>
            </div>
          </section>

          <footer class="resource-overview-footer">
            <span>资源目录与运行资源分离管理</span>
            <RouterLink to="/agentos/resources/manage">查看端边云拓扑 <el-icon aria-hidden="true"><ArrowRight /></el-icon></RouterLink>
          </footer>
        </main>
      </template>
    </WorkbenchLayout>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ArrowRight } from '@element-plus/icons-vue'
import { agentosApi } from '@/services/api/agentos'
import type { RuntimeResourceItem } from '@/services/api/agentos'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import WorkspacePageHero from '@/components/app/WorkspacePageHero.vue'
import ResourceCenterNav from '@/components/resource-center/ResourceCenterNav.vue'

const resources = ref<RuntimeResourceItem[]>([])
const loading = ref(true)
const error = ref('')
let controller: AbortController | null = null
const totals = computed(() => ({
  runtime: resources.value.filter(item => item.profile.runtimeKind !== 'model_endpoint').length,
  online: resources.value.filter(item => item.snapshot.healthStatus === 'online' && item.profile.enabled).length,
  attention: resources.value.filter(item => item.snapshot.healthStatus !== 'online' || !item.profile.enabled).length
}))
const tiers = computed(() => [
  { id: 'device', index: '01', label: '本地设备', count: countTier('device') },
  { id: 'edge', index: '02', label: '边缘节点', count: countTier('edge') },
  { id: 'cloud', index: '03', label: '云端服务', count: countTier('cloud') }
])
const recentResources = computed(() => [...resources.value]
  .filter(item => item.profile.runtimeKind !== 'model_endpoint')
  .sort((a, b) => Number(b.snapshot.healthStatus === 'online') - Number(a.snapshot.healthStatus === 'online'))
  .slice(0, 5))

function countTier(tier: string) {
  return resources.value.filter(item => item.profile.deploymentTier === tier || (tier === 'device' && ['local', 'terminal'].includes(String(item.profile.deploymentTier || '')))).length
}
const tierLabel = (tier?: string | null) => ({ device: '本地', local: '本地', terminal: '本地', edge: '边缘', cloud: '云端' }[tier || ''] || '未分类')
const kindLabel = (kind?: string | null) => ({ model_server: '模型服务', tool_service: '工具服务', execution_backend: '执行服务', model_endpoint: '模型端点' }[kind || ''] || '资源')
const healthLabel = (health?: string | null) => ({ online: '可调度', degraded: '需关注', offline: '离线', unknown: '待检测' }[health || ''] || '状态未知')

async function load() {
  controller?.abort()
  controller = new AbortController()
  const current = controller
  loading.value = true
  error.value = ''
  try {
    const response = await agentosApi.listResources({ signal: current.signal })
    if (controller === current && !current.signal.aborted) resources.value = response.items
  } catch {
    if (!current.signal.aborted && controller === current) error.value = '暂时无法读取资源状态。'
  } finally {
    if (controller === current && !current.signal.aborted) loading.value = false
  }
}
onMounted(() => { void load() })
onBeforeUnmount(() => controller?.abort())
</script>

<style scoped>
.resource-page { width: 100%; height: 100%; min-height: 0; overflow: hidden; background: var(--bg-app); }
.resource-page__main { width: min(100%, 1400px); height: 100%; overflow: auto; margin: 0 auto; padding: 0 clamp(18px, 4vw, 58px) 36px; color: var(--text-primary); }
.resource-button { display: inline-flex; align-items: center; justify-content: center; min-height: 36px; padding: 0 14px; border: 1px solid var(--border-light); color: var(--text-secondary); text-decoration: none; font-size: 11px; }
.resource-button--primary { border-color: var(--primary-color); color: #fff; background: var(--primary-color); }
.resource-pulse { display: grid; grid-template-columns: minmax(190px, .65fr) minmax(0, 1.8fr); min-height: 206px; margin: 25px 0 38px; border: 1px solid var(--border-light); background: var(--bg-card); }
.resource-pulse__lead { display: grid; align-content: center; gap: 5px; padding: 24px 28px; border-right: 1px solid var(--border-light); background: color-mix(in srgb, var(--primary-color) 5%, var(--bg-card)); }
.resource-kicker { color: var(--primary-color); font: 9px var(--font-mono, monospace); letter-spacing: 0; }
.resource-pulse__lead > strong { font: 500 50px/1 var(--font-mono, monospace); }
.resource-pulse__lead > span:not(.resource-kicker), .resource-pulse__lead small { color: var(--text-secondary); font-size: 11px; }
.resource-pulse__rule { width: 38px; height: 1px; margin: 10px 0 4px; background: var(--primary-color); }
.resource-pulse__tiers { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
.tier-readout { position: relative; display: flex; align-items: center; gap: 14px; min-width: 0; padding: 20px; border-right: 1px solid var(--border-light); overflow: hidden; }
.tier-readout:last-child { border-right: 0; }
.tier-readout__index { align-self: flex-start; color: var(--text-muted); font: 10px var(--font-mono, monospace); }
.tier-readout > div { display: grid; gap: 4px; min-width: 0; }
.tier-readout small { color: var(--text-secondary); font-size: 11px; }
.tier-readout strong { font: 500 32px/1.1 var(--font-mono, monospace); }
.tier-readout > div > span { color: var(--text-muted); font-size: 10px; }
.tier-readout > i { position: absolute; right: -20px; bottom: -34px; width: 104px; height: 104px; border: 1px solid color-mix(in srgb, var(--primary-color) 24%, transparent); border-radius: 50%; }
.tier-readout > i::after { position: absolute; inset: 12px; border: 1px solid color-mix(in srgb, var(--primary-color) 20%, transparent); border-radius: 50%; content: ''; }
.tier-readout.is-edge > i { border-color: color-mix(in srgb, var(--success) 38%, transparent); }
.tier-readout.is-cloud > i { border-color: color-mix(in srgb, #55a8ce 35%, transparent); }
.resource-overview-grid { margin-top: 12px; }
.resource-overview-grid__heading { display: flex; align-items: end; justify-content: space-between; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border-light); }
.resource-overview-grid__heading h2 { margin: 5px 0 0; font-size: 16px; font-weight: 600; }
.resource-overview-grid__heading > a, .resource-overview-footer a { display: inline-flex; align-items: center; gap: 6px; color: var(--primary-color); text-decoration: none; font-size: 11px; }
.resource-loading, .resource-empty { display: grid; justify-items: center; gap: 9px; min-height: 190px; align-content: center; color: var(--text-secondary); font-size: 12px; }
.resource-loading.is-error { color: var(--danger); }
.resource-loading button, .resource-empty a { border: 0; color: var(--primary-color); background: transparent; text-decoration: underline; cursor: pointer; font: inherit; }
.resource-empty strong { color: var(--text-primary); font-size: 14px; }
.resource-empty__mark { display: grid; place-items: center; width: 38px; aspect-ratio: 1; border: 1px solid var(--primary-line); color: var(--primary-color); font-size: 22px; }
.resource-recent-row { display: grid; grid-template-columns: 8px minmax(0, 1fr) 90px 72px; align-items: center; gap: 13px; min-height: 66px; border-bottom: 1px solid var(--border-light); }
.resource-recent-row__signal { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); }
.resource-recent-row__signal.is-online { background: var(--success); box-shadow: 0 0 0 4px color-mix(in srgb, var(--success) 12%, transparent); }
.resource-recent-row__signal.is-degraded, .resource-recent-row__signal.is-unknown { background: var(--warning); }
.resource-recent-row__signal.is-offline { background: var(--danger); }
.resource-recent-row__name { display: grid; gap: 4px; min-width: 0; }
.resource-recent-row__name strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 550; }
.resource-recent-row__name span, .resource-recent-row__tier, .resource-recent-row__health { color: var(--text-muted); font-size: 10px; }
.resource-recent-row__health { text-align: right; }
.resource-overview-footer { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 28px; padding-top: 13px; border-top: 1px solid var(--border-light); color: var(--text-muted); font-size: 10px; }
@media (max-width: 760px) { .resource-pulse { grid-template-columns: 1fr; }.resource-pulse__lead { border-right: 0; border-bottom: 1px solid var(--border-light); }.resource-pulse__tiers { min-height: 128px; }.tier-readout { gap: 7px; padding: 12px 8px; }.tier-readout strong { font-size: 25px; }.tier-readout__index { display: none; } }
@media (max-width: 480px) { .resource-page__main { padding-right: 14px; padding-left: 14px; }.resource-pulse { margin-top: 18px; }.resource-recent-row { grid-template-columns: 8px minmax(0, 1fr) 58px; gap: 8px; }.resource-recent-row__health { display: none; }.resource-recent-row__tier { text-align: right; }.resource-overview-footer { align-items: flex-start; flex-direction: column; } }
</style>
