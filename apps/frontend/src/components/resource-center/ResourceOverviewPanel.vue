<template>
  <section class="resource-overview-panel" aria-label="系统资源">
    <!-- <div class="resource-summary" aria-label="资源摘要">
       <div class="resource-summary__intro">
        <span class="resource-summary__eyebrow">RESOURCE OVERVIEW</span>
        <strong>您的资源</strong>
        <span>设备、模型与工具的连接状态和使用情况</span>
      </div> -->
      <!-- <div class="resource-summary__metrics">
        <div v-for="tier in tierStats" :key="tier.id" class="resource-summary__metric resource-summary__metric--tier" :class="`is-tier-${tier.id}`">
          <span>{{ tier.label }}</span>
          <strong>{{ tier.count }}</strong>
          <small>资源</small>
        </div>
        <div class="resource-summary__metric resource-summary__metric--compute">
          <span>总算力</span>
          <strong>{{ computeTotals.hasCapacity ? (computeTotals.cpu > 0 ? `${computeTotals.cpu}核` : 'CPU 未登记') : '未观测' }}</strong>
          <small v-if="computeTotals.hasCapacity">{{ computeTotals.memory > 0 ? `${computeTotals.memory}G 内存` : '内存未登记' }}<template v-if="computeTotals.gpu > 0"> · {{ computeTotals.gpu }}G GPU</template></small>
          <small v-else>未登记算力</small>
        </div>
        <div class="resource-summary__metric resource-summary__metric--health">
          <span>健康分布</span>
          <strong>{{ healthyResourceCount }}</strong>
          <small>在线 · {{ degradedResourceCount }} 降级 · {{ offlineResourceCount }} 离线 · {{ unknownResourceCount }} 未知</small>
        </div>
      </div>
    </div> -->

    <div class="resource-toolbar" aria-label="资源筛选">
      <label class="resource-search" :class="{ 'has-query': searchText }">
        <span class="resource-search__icon" aria-hidden="true"><el-icon><Search /></el-icon></span>
        <span class="resource-search__copy">
        <span class="resource-search__label">查找资源</span>
          <input ref="searchInput" v-model="searchText" type="search" placeholder="搜索名称、能力或位置" />
        </span>
        <kbd>/</kbd>
      </label>
      <div class="resource-toolbar__meta">
        <span class="resource-toolbar__count"><b>{{ filteredResources.length }}</b> / {{ resources.length }} 个资源</span>
        <span class="resource-toolbar__mode"><i aria-hidden="true"></i> 已连接资源</span>
      </div>
    </div>

    <div class="resource-catalog-filters" aria-label="资源目录筛选">
      <label><span>类型</span><select v-model="selectedType"><option value="">全部</option><option value="device">设备</option><option value="model">模型</option><option value="tool">工具</option></select></label>
      <label><span>位置</span><select v-model="selectedTier"><option value="">全部位置</option><option value="device">本地</option><option value="edge">边缘</option><option value="cloud">云端</option><option v-for="tier in otherTierOptions" :key="tier" :value="tier">{{ tier }}</option></select></label>
      <label><span>状态</span><select v-model="selectedHealth"><option value="">全部状态</option><option value="online">可用</option><option value="degraded">需关注</option><option value="offline">离线</option><option value="unknown">待检测</option></select></label>
      <label><span>数据区域</span><select v-model="selectedDataZone"><option value="">全部区域</option><option v-for="zone in dataZoneOptions" :key="zone" :value="zone">{{ zone }}</option></select></label>
      <label><span>来源</span><select v-model="selectedSource"><option value="">全部来源</option><option v-for="source in sourceOptions" :key="source" :value="source">{{ source }}</option></select></label>
      <label><span>提供方</span><select v-model="selectedProvider"><option value="">全部提供方</option><option v-for="provider in providerOptions" :key="provider" :value="provider">{{ provider }}</option></select></label>
    </div>

    <div v-if="domainOptions.length" class="resource-domain-filter" role="group" aria-label="按领域筛选">
      <button type="button" :class="{ active: !selectedDomain }" @click="selectedDomain = ''">全部</button>
      <button
        v-for="domain in domainOptions"
        :key="domain.name"
        type="button"
        :class="{ active: selectedDomain === domain.name }"
        @click="selectedDomain = selectedDomain === domain.name ? '' : domain.name"
      >{{ domain.name }}<small>{{ domain.count }}</small></button>
    </div>

    <ResourceTopologyPanel :items="filteredResources" :nodes="filteredNodes" :nodes-error="nodesError" :pending-nodes="pendingNodes" @open="openDetail" @toggle-node="toggleNode" />
    <section v-if="loading && !resources.length" class="resource-state" role="status">
      <BrandLoader title="正在读取 ResourceService" subtitle="只读加载系统 Resource profile…" />
    </section>
    <section v-else-if="errorMessage" class="resource-state resource-state--error" role="alert">
      <strong>资源中心暂时不可用</strong>
      <span>{{ errorMessage }}</span>
      <button type="button" @click="loadResources">重新加载</button>
    </section>
    <section v-else-if="!filteredResources.length" class="resource-state" role="status">
      <strong>{{ hasFilters ? '没有匹配的资源' : '还没有接入资源' }}</strong>
      <span>{{ hasFilters ? '调整筛选条件，或清除筛选查看全部资源。' : '接入设备、模型或工具后，它们会显示在这里。' }}</span>
    </section>
    <div v-else class="resource-groups" aria-label="系统资源">
      <section v-for="group in groupedResources" :key="group.tier" class="resource-tier-group" :class="`is-tier-${group.tier}`">
        <header class="resource-tier-group__header">
          <span class="resource-tier-group__dot" aria-hidden="true"></span>
          <strong>{{ group.label }}</strong>
          <span class="resource-tier-group__count">{{ group.items.length }} 个资源</span>
        </header>
        <div class="resource-list">
          <article v-for="item in group.items" :key="item.profile.resourceId" class="resource-row" @click="openDetail(item)">
            <div class="resource-row__identity">
              <span class="resource-row__icon" aria-hidden="true" :style="{ '--tile-tone': resourceTypeMeta(item.profile.resourceType).tone }">
                <el-icon><component :is="resourceTypeIcon(item.profile.resourceType)" /></el-icon>
                <i :class="`resource-row__health-dot is-${item.snapshot.healthStatus}`"></i>
              </span>
              <div>
                <strong>{{ item.profile.displayName || item.profile.resourceId }}</strong>
              <span class="resource-row__meta">{{ customerResourceType(item.profile.runtimeKind || item.profile.resourceType) }}<template v-if="item.profile.provider"> · {{ item.profile.provider }}</template><template v-if="item.profile.sourceType"> · {{ item.profile.sourceType }}</template></span>
              </div>
            </div>
            <div class="resource-row__capabilities">
              <span v-for="capability in item.profile.capabilities" :key="capability">{{ capability }}</span>
            </div>
            <dl class="resource-row__facts">
              <div><dt>连接状态</dt><dd :class="`is-${item.snapshot.healthStatus}`"><i class="resource-status-dot" aria-hidden="true"></i>{{ customerHealthLabel(item.snapshot.healthStatus) }}</dd></div>
              <div><dt>算力</dt><dd class="resource-row__capacity">{{ formatCapacity(item.profile.computeCapacity) }}</dd></div>
              <div><dt>利用率</dt><dd class="resource-row__util"><span class="resource-row__util-track"><i :style="{ width: utilizationPercent(item.snapshot.utilization) }"></i></span><em>{{ formatPercent(item.snapshot.utilization) }}</em></dd></div>
              <div><dt>延迟</dt><dd>{{ formatMetric(item.snapshot.latencyMs, 'ms') }}</dd></div>
            </dl>
            <div class="resource-row__extra">
              <span class="resource-row__privacy">{{ customerPrivacyLabel(item.profile.privacyLevel) }}</span>
              <span v-if="item.profile.dataZone" class="resource-row__zone">{{ item.profile.dataZone }}</span>
              <button type="button" class="resource-row__open" :aria-label="`查看 ${item.profile.displayName || '资源'}详情`" @click.stop="openDetail(item)">详情</button>
            </div>
          </article>
        </div>
      </section>
    </div>
  </section>

  <el-drawer v-model="drawerOpen" :title="selectedResource ? selectedResource.profile.resourceId : '资源详情'" size="440px" append-to-body class="resource-detail-drawer">
    <ResourceDetailPanel v-if="selectedResource" :item="selectedResource" @enabled-changed="handleEnabledChanged" />
  </el-drawer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { agentosApi, type RuntimeResourceItem, type NodeCatalogItem } from '@/services/api/agentos'
import ResourceDetailPanel from './ResourceDetailPanel.vue'
import ResourceTopologyPanel from './ResourceTopologyPanel.vue'
import BrandLoader from '@/components/common/BrandLoader.vue'
import { formatCapacity, formatMetric, formatPercent, healthLabel, resourceTypeMeta, resourcePlacement, tierLabel } from '@/utils/resourceFormat'
import { resourceTypeIcon } from '@/utils/resourceTypeIcons'
import { customerHealthLabel, customerPrivacyLabel, customerResourceType } from './resourceCenterPresentation'

const resources = ref<RuntimeResourceItem[]>([])
const nodes = ref<NodeCatalogItem[]>([])
const nodesError = ref('')
const pendingNodes = ref<string[]>([])
const searchText = ref('')
const selectedDomain = ref('')
const selectedType = ref('')
const selectedTier = ref('')
const selectedHealth = ref('')
const selectedDataZone = ref('')
const selectedSource = ref('')
const selectedProvider = ref('')
const loading = ref(false)
const errorMessage = ref('')
const selectedResource = ref<RuntimeResourceItem | null>(null)
const drawerOpen = ref(false)
const searchInput = ref<HTMLInputElement | null>(null)
let controller: AbortController | null = null

const TIER_ORDER: Array<{ id: string; label: string }> = [
  { id: 'device', label: '本机设备' },
  { id: 'edge', label: '边缘' },
  { id: 'cloud', label: '云端' }
]

const healthyResourceCount = computed(() => resources.value.filter(item => item.snapshot.healthStatus === 'online').length)
const degradedResourceCount = computed(() => resources.value.filter(item => item.snapshot.healthStatus === 'degraded').length)
const offlineResourceCount = computed(() => resources.value.filter(item => item.snapshot.healthStatus === 'offline').length)
const unknownResourceCount = computed(() => resources.value.filter(item => !['online', 'degraded', 'offline'].includes(item.snapshot.healthStatus)).length)

const tierStats = computed(() => TIER_ORDER.map(tier => ({
  ...tier,
  count: resources.value.filter(item => resourcePlacement(item.profile.deploymentTier) === tier.id).length
})))

const computeTotals = computed(() => {
  let cpu = 0
  let memory = 0
  let gpu = 0
  let hasCapacity = false
  const seenNodes = new Set<string>()
  const entries = nodes.value.length ? nodes.value.map(n => ({ profile: { nodeId: n.profile.nodeId, computeCapacity: n.profile.computeCapacity, runtimeKind: 'node' } })) : resources.value
  for (const item of entries) {
    if (item.profile.runtimeKind === 'model_endpoint') continue
    if (item.profile.nodeId && seenNodes.has(item.profile.nodeId)) continue
    if (item.profile.nodeId) seenNodes.add(item.profile.nodeId)
    const capacity = item.profile.computeCapacity
    if (!capacity) continue
    if ((capacity.cpuCores ?? 0) > 0 || (capacity.memoryMb ?? 0) > 0 || (capacity.gpuMemoryMb ?? 0) > 0) hasCapacity = true
    cpu += capacity.cpuCores ?? 0
    memory += (capacity.memoryMb ?? 0) / 1024
    gpu += (capacity.gpuMemoryMb ?? 0) / 1024
  }
  return { cpu, memory: Number(memory.toFixed(1)), gpu: Number(gpu.toFixed(1)), hasCapacity }
})

const domainOptions = computed(() => {
  const counts = new Map<string, number>()
  for (const item of resources.value) {
    for (const domain of item.profile.domains || []) {
      counts.set(domain, (counts.get(domain) || 0) + 1)
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .map(([name, count]) => ({ name, count }))
})

const dataZoneOptions = computed(() => [...new Set(resources.value.map(item => item.profile.dataZone).filter((zone): zone is string => Boolean(zone)))].sort())
const sourceOptions = computed(() => [...new Set(resources.value.map(item => item.profile.sourceType).filter((value): value is string => Boolean(value)))].sort())
const providerOptions = computed(() => [...new Set(resources.value.map(item => item.profile.provider).filter((value): value is string => Boolean(value)))].sort())
const otherTierOptions = computed(() => [...new Set(resources.value.map(item => resourcePlacement(item.profile.deploymentTier)))].filter(tier => !['device', 'edge', 'cloud'].includes(tier)).sort())
const hasFilters = computed(() => Boolean(searchText.value || selectedDomain.value || selectedType.value || selectedTier.value || selectedHealth.value || selectedDataZone.value || selectedSource.value || selectedProvider.value))
const filteredNodes = computed(() => nodes.value.filter(node => {
  if (selectedType.value && selectedType.value !== 'device') return false
  if (selectedTier.value && resourcePlacement(node.profile.placement) !== selectedTier.value) return false
  if (selectedHealth.value && node.healthStatus !== selectedHealth.value) return false
  if (selectedDataZone.value) return false
  const query = searchText.value.trim().toLocaleLowerCase()
  return !query || [node.profile.displayName || '', node.profile.nodeId, node.profile.placement].some(value => value.toLocaleLowerCase().includes(query))
}))

const filteredResources = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase()
  const domain = selectedDomain.value
  return resources.value.filter(item => {
    const runtimeKind = item.profile.runtimeKind || item.profile.resourceType
    const type = runtimeKind === 'model_endpoint' || runtimeKind === 'model_server' || item.profile.resourceType === 'model' ? 'model'
      : runtimeKind === 'tool_service' || item.profile.resourceType === 'tool' || item.profile.resourceType === 'mcp' ? 'tool' : 'device'
    if (selectedType.value && type !== selectedType.value) return false
    if (selectedTier.value && resourcePlacement(item.profile.deploymentTier) !== selectedTier.value) return false
    if (selectedHealth.value && item.snapshot.healthStatus !== selectedHealth.value) return false
    if (selectedDataZone.value && item.profile.dataZone !== selectedDataZone.value) return false
    if (selectedSource.value && item.profile.sourceType !== selectedSource.value) return false
    if (selectedProvider.value && item.profile.provider !== selectedProvider.value) return false
    if (domain && !(item.profile.domains || []).includes(domain)) return false
    if (!query) return true
    return [
      item.profile.resourceId,
      item.profile.resourceType,
      item.profile.displayName || '', item.profile.nodeId || '', item.profile.runtimeKind || '',
      ...item.profile.capabilities,
      item.profile.deploymentTier || ''
      , item.profile.provider || '', item.profile.sourceType || '', item.profile.adapter || ''
    ].some(value => (value || '').toLocaleLowerCase().includes(query))
  })
})

const groupedResources = computed(() => {
  const groups = new Map<string, RuntimeResourceItem[]>()
  for (const item of filteredResources.value) {
    const tier = resourcePlacement(item.profile.deploymentTier)
    if (!groups.has(tier)) groups.set(tier, [])
    groups.get(tier)!.push(item)
  }
  const tiers = [...TIER_ORDER, ...[...groups.keys()].filter(id => !TIER_ORDER.some(t => t.id === id)).map(id => ({ id, label: `其他位置 · ${id}` }))]
  return tiers
    .filter(tier => groups.has(tier.id))
    .map(tier => ({ tier: tier.id, label: tier.label, items: groups.get(tier.id)! }))
})

const utilizationPercent = (value: number | null | undefined) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return 0
  return Math.max(0, Math.min(100, Math.round(value * 100)))
}

const openDetail = (item: RuntimeResourceItem) => {
  selectedResource.value = item
  drawerOpen.value = true
}

const handleEnabledChanged = (payload: { resourceId: string; enabled: boolean }) => {
  for (const item of resources.value) {
    if (item.profile.resourceId === payload.resourceId) {
      item.profile.enabled = payload.enabled
    }
  }
  if (selectedResource.value?.profile.resourceId === payload.resourceId) {
    selectedResource.value = {
      ...selectedResource.value,
      profile: { ...selectedResource.value.profile, enabled: payload.enabled }
    }
  }
}

const toggleNode = async (payload: { nodeId: string; enabled: boolean }) => {
  if (pendingNodes.value.includes(payload.nodeId)) return
  if (!payload.enabled) {
    try {
      await ElMessageBox.confirm(
        '停用后，该设备上的新任务将暂停；设备配置和历史记录会保留。继续？',
        '停用设备',
        { confirmButtonText: '停用设备', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
  }
  pendingNodes.value = [...pendingNodes.value, payload.nodeId]
  try {
    const result = await agentosApi.setNodeEnabled(payload.nodeId, payload.enabled)
    nodes.value = nodes.value.map(node => node.profile.nodeId === result.nodeId
      ? { ...node, profile: { ...node.profile, enabled: result.enabled } }
      : node)
    ElMessage.success(result.enabled ? '设备已启用' : '设备已停用')
  } catch (error: unknown) {
    const status = (error as { response?: { status?: number } })?.response?.status
    ElMessage.error(status === 403 ? '无权管理此设备' : '设备状态更新失败，请稍后重试')
  } finally {
    pendingNodes.value = pendingNodes.value.filter(nodeId => nodeId !== payload.nodeId)
  }
}

const loadResources = async () => {
  controller?.abort()
  controller = new AbortController()
  const requestController = controller
  loading.value = true
  errorMessage.value = ''
  nodesError.value = ''
  void agentosApi.listNodes({ signal: requestController.signal }).then(response => {
    if (!requestController.signal.aborted && controller === requestController) nodes.value = response.items
  }).catch(() => {
    if (!requestController.signal.aborted && controller === requestController) nodesError.value = '节点目录暂时不可用，服务目录仍可单独查看。'
  })
  try {
    const response = await agentosApi.listResources({ signal: requestController.signal })
    if (requestController.signal.aborted || controller !== requestController) return
    resources.value = response.items
  } catch (error: unknown) {
    if ((error as { name?: string })?.name === 'CanceledError' || (error as { name?: string })?.name === 'AbortError') return
    errorMessage.value = '无法读取 ResourceService 的真实数据。'
  } finally {
    if (controller === requestController && !requestController.signal.aborted) loading.value = false
  }
}

defineExpose({ loadResources })

const focusSearch = (event: KeyboardEvent) => {
  if (event.key !== '/') return
  const target = event.target as HTMLElement | null
  const tag = target?.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || target?.isContentEditable) return
  event.preventDefault()
  searchInput.value?.focus()
}

onMounted(() => { void loadResources(); window.addEventListener('keydown', focusSearch) })
onBeforeUnmount(() => { controller?.abort(); window.removeEventListener('keydown', focusSearch) })
</script>

<style scoped>
.resource-overview-panel {
  --resource-surface: color-mix(in srgb, var(--bg-card) 92%, var(--bg-panel));
  --resource-inset: color-mix(in srgb, var(--bg-input) 78%, var(--bg-card));
  --resource-grid: minmax(180px, 0.9fr) minmax(140px, 0.7fr) minmax(360px, 1.6fr) auto;
  min-width: 0;
  color: var(--text-primary);
}
.resource-summary {
  display: flex;
  align-items: stretch;
  justify-content: space-between;
  gap: 24px;
  margin: 20px 0 12px;
  padding: 16px 18px;
  border: 1px solid color-mix(in srgb, var(--primary-color) 15%, var(--border-light));
  border-radius: var(--radius-card, 9px);
  background: linear-gradient(105deg, color-mix(in srgb, var(--primary-color) 9%, var(--bg-card)), var(--resource-surface) 48%);
  box-shadow: var(--shadow-sm);
}
.resource-summary__intro { display: grid; align-content: center; gap: 3px; min-width: 190px; }
.resource-summary__intro strong { color: var(--text-primary); font-size: 14px; font-weight: 650; }
.resource-summary__intro > span:last-child { color: var(--text-muted); font-size: 10px; }
.resource-summary__eyebrow { color: var(--primary-color); font: 9px var(--font-mono, monospace); letter-spacing: .12em; }
.resource-summary__metrics { display: grid; grid-template-columns: repeat(5, minmax(96px, 1fr)); min-width: min(600px, 62%); }
.resource-summary__metric { display: grid; align-content: center; gap: 1px; padding: 0 18px; border-left: 1px solid var(--border-light); }
.resource-summary__metric span, .resource-summary__metric small { color: var(--text-muted); font-size: 10px; }
.resource-summary__metric strong { color: var(--text-primary); font: 650 20px/1.2 var(--font-mono, monospace); }
.resource-summary__metric small { color: var(--text-secondary); font: 9px var(--font-mono, monospace); white-space: nowrap; }
.resource-summary__metric--health strong { color: var(--success); }
.resource-summary__metric--compute strong { color: var(--primary-color); }
.resource-summary__metric--tier strong { color: var(--text-secondary); }
.resource-summary__metric--tier.is-tier-cloud strong { color: var(--primary-color); }
.resource-summary__metric--tier.is-tier-edge strong { color: var(--success); }
.resource-summary__metric--tier.is-tier-device strong { color: var(--text-secondary); }
.resource-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 14px 0 12px; color: var(--text-muted); font-size: 11px; }
.resource-domain-filter { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 0 12px; }
.resource-domain-filter button { display: inline-flex; align-items: center; gap: 5px; padding: 3px 10px; border: 1px solid var(--border-light); border-radius: 999px; color: var(--text-secondary); background: var(--bg-input); cursor: pointer; font: inherit; font-size: 10px; transition: var(--transition); }
.resource-domain-filter button:hover { border-color: var(--primary-line); color: var(--primary-color); }
.resource-domain-filter button.active { border-color: color-mix(in srgb, var(--primary-color) 62%, transparent); color: var(--primary-color); background: var(--primary-fade); }
.resource-domain-filter button small { color: var(--text-muted); font-size: 9px; }
.resource-domain-filter button.active small { color: var(--primary-color); }
.resource-search { display: flex; align-items: center; gap: 9px; width: min(500px, 100%); min-height: 42px; padding: 0 11px; border: 1px solid var(--border-light); border-radius: var(--radius-control, 6px); color: var(--text-muted); background: var(--resource-inset); transition: var(--transition); }
.resource-search:hover, .resource-search:focus-within, .resource-search.has-query { border-color: var(--primary-line); background: var(--bg-input); }
.resource-search__icon { display: inline-grid; place-items: center; color: var(--primary-color); }
.resource-search__copy { display: grid; min-width: 0; flex: 1; gap: 0; }
.resource-search__label { color: var(--text-muted); font-size: 9px; line-height: 1.1; }
.resource-search input { width: 100%; min-width: 0; border: 0; outline: 0; color: var(--text-primary); background: transparent; font: 11px/1.4 var(--font-sans); }
.resource-search input::placeholder { color: var(--text-secondary); }
.resource-search kbd { min-width: 18px; padding: 2px 5px; border: 1px solid var(--border-light); border-radius: 4px; color: var(--text-muted); background: var(--bg-card); font: 10px var(--font-mono, monospace); text-align: center; }
.resource-toolbar__meta { display: flex; align-items: center; gap: 14px; white-space: nowrap; }
.resource-catalog-filters { display: flex; flex-wrap: wrap; gap: 8px; padding: 0 0 12px; }
.resource-catalog-filters label { display: inline-flex; align-items: center; gap: 7px; min-height: 32px; padding: 0 9px; border: 1px solid var(--border-light); border-radius: 5px; background: var(--bg-card); }
.resource-catalog-filters label > span { color: var(--text-muted); font-size: 10px; }
.resource-catalog-filters select { max-width: 150px; border: 0; outline: 0; color: var(--text-secondary); background: transparent; font: inherit; font-size: 11px; }
.resource-toolbar__count b { color: var(--text-primary); font: 650 12px var(--font-mono, monospace); }
.resource-toolbar__mode { display: inline-flex; align-items: center; gap: 5px; color: var(--text-muted); font: 9px var(--font-mono, monospace); text-transform: uppercase; letter-spacing: .05em; }
.resource-toolbar__mode i { width: 5px; height: 5px; border-radius: 50%; background: var(--success); box-shadow: 0 0 0 3px var(--success-fade); }
.resource-groups { display: grid; gap: 16px; }
.resource-tier-group { display: grid; gap: 8px; }
.resource-tier-group__header { display: flex; align-items: center; gap: 8px; padding: 2px 2px 6px; color: var(--text-secondary); }
.resource-tier-group__header strong { font-size: 12px; font-weight: 650; }
.resource-tier-group__count { margin-left: auto; color: var(--text-muted); font: 10px var(--font-mono, monospace); }
.resource-tier-group__dot { width: 8px; height: 8px; border-radius: 50%; background: var(--primary-color); }
.is-tier-device .resource-tier-group__dot { background: var(--text-secondary); }
.is-tier-edge .resource-tier-group__dot { background: var(--success); }
.is-tier-cloud .resource-tier-group__dot { background: var(--primary-color); }
.resource-list { overflow: hidden; border: 1px solid var(--border-light); border-radius: var(--radius-card, 9px); background: var(--resource-surface); box-shadow: var(--shadow-sm); }
.resource-row { display: grid; grid-template-columns: var(--resource-grid); align-items: center; gap: 24px; min-height: 88px; padding: 15px 16px; border-bottom: 1px solid var(--border-light); background: var(--resource-surface); transition: var(--transition); cursor: pointer; }
.resource-row:last-child { border-bottom: 0; }
.resource-row:hover { background: var(--surface-hover); box-shadow: inset 2px 0 0 var(--primary-color); }
.resource-row__identity { display: flex; align-items: center; gap: 10px; min-width: 0; }
.resource-row__icon { position: relative; display: inline-grid; place-items: center; flex: 0 0 auto; width: 36px; height: 36px; border-radius: 10px; color: color-mix(in srgb, var(--tile-tone, var(--primary-color)) 40%, #e9f5ff); background: linear-gradient(145deg, color-mix(in srgb, var(--tile-tone, var(--primary-color)) 34%, transparent), color-mix(in srgb, var(--tile-tone, var(--primary-color)) 10%, transparent) 55%, color-mix(in srgb, var(--tile-tone, var(--primary-color)) 24%, transparent)), var(--bg-input); border: 1px solid color-mix(in srgb, var(--tile-tone, var(--primary-color)) 46%, transparent); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.09), 0 0 12px color-mix(in srgb, var(--tile-tone, var(--primary-color)) 16%, transparent); transition: box-shadow var(--transition), border-color var(--transition); }
.resource-row__icon .el-icon { font-size: 18px; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35)); }
.resource-row:hover .resource-row__icon { border-color: color-mix(in srgb, var(--tile-tone, var(--primary-color)) 70%, transparent); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12), 0 0 18px color-mix(in srgb, var(--tile-tone, var(--primary-color)) 30%, transparent); }
.resource-row__health-dot { position: absolute; right: -3px; bottom: -3px; width: 8px; height: 8px; border: 2px solid var(--resource-surface); border-radius: 50%; background: var(--warning); }
.resource-row__health-dot.is-online { background: var(--success); }
.resource-row__health-dot.is-degraded { background: var(--warning); }
.resource-row__health-dot.is-offline { background: var(--danger); }
.resource-row__identity div { min-width: 0; }
.resource-row__identity strong, .resource-row__identity span:not(.resource-row__icon) { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.resource-row__identity strong { color: var(--text-primary); font: 600 11px var(--font-mono, monospace); }
.resource-row__identity span:not(.resource-row__icon) { margin-top: 4px; color: var(--text-muted); font: 10px var(--font-mono, monospace); }
.resource-row__identity .resource-row__meta { display: inline-flex; align-items: center; gap: 5px; }
.resource-row__capabilities { display: flex; gap: 5px; min-width: 0; flex-wrap: wrap; }
.resource-row__capabilities span { padding: 4px 7px; border: 1px solid color-mix(in srgb, var(--border-light) 82%, var(--primary-color)); border-radius: 4px; color: var(--text-secondary); background: color-mix(in srgb, var(--bg-input) 76%, transparent); font: 10px var(--font-mono, monospace); }
.resource-row__facts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 0; }
.resource-row__facts div { min-width: 0; }
.resource-row__facts dt { display: none; color: var(--text-muted); font-size: 10px; }
.resource-row__facts dd { display: flex; align-items: center; gap: 5px; margin: 0; overflow: hidden; color: var(--text-secondary); font: 11px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.resource-row__facts dd.is-unknown { color: var(--warning); }
.resource-row__facts dd.is-online { color: var(--success); }
.resource-row__facts dd.is-degraded { color: var(--warning); }
.resource-row__facts dd.is-offline, .resource-row__facts dd.is-disabled { color: var(--danger); }
.resource-row__facts dd.is-enabled { color: var(--text-secondary); }
.resource-status-dot { width: 5px; height: 5px; flex: 0 0 auto; border-radius: 50%; background: currentColor; }
.resource-row__capacity { font-size: 9px !important; }
.resource-row__util { display: flex; align-items: center; gap: 6px; }
.resource-row__util-track { position: relative; display: inline-block; flex: 0 0 auto; width: 46px; height: 4px; border-radius: 2px; background: var(--border-light); overflow: hidden; }
.resource-row__util-track i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 2px; background: var(--primary-color); }
.resource-row__util em { font-style: normal; }
.resource-row__extra { display: flex; align-items: center; gap: 6px; justify-content: flex-end; }
.resource-row__privacy { padding: 2px 7px; border: 1px solid var(--border-light); border-radius: 999px; color: var(--text-muted); font: 9px var(--font-mono, monospace); white-space: nowrap; }
.resource-row__zone { color: var(--text-muted); font: 9px var(--font-mono, monospace); white-space: nowrap; }
.resource-row__open { min-height: 26px; padding: 0 10px; border: 1px solid var(--primary-line); border-radius: 5px; color: var(--primary-color); background: transparent; cursor: pointer; font-size: 10px; }
.resource-row__open:hover { background: var(--primary-fade); }
.resource-state { display: grid; place-items: center; align-content: center; gap: 8px; min-height: 280px; color: var(--text-secondary); font-size: 12px; text-align: center; }
.resource-state strong { color: var(--text-primary); font-size: 14px; }
.resource-state span { line-height: 1.6; }
.resource-state--error { color: var(--danger, #b64d55); }
.resource-state button { min-height: 32px; padding: 0 12px; border: 1px solid var(--primary-line); border-radius: 5px; color: var(--primary-color); background: var(--primary-fade); cursor: pointer; font: inherit; font-size: 11px; }
@media (max-width: 900px) {
  .resource-summary { flex-direction: column; gap: 16px; }
  .resource-summary__metrics { min-width: 0; }
  .resource-row { grid-template-columns: 1fr; gap: 12px; min-height: 0; padding: 16px; }
  .resource-row__facts { gap: 10px; }
  .resource-row__facts dt { display: block; }
  .resource-row__facts dd { margin-top: 3px; }
}
@media (max-width: 560px) {
  .resource-summary { margin-top: 14px; padding: 14px; }
  .resource-summary__metrics { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .resource-summary__metric { padding: 0 9px; }
  .resource-summary__metric strong { font-size: 17px; }
  .resource-summary__metric small { overflow: hidden; text-overflow: ellipsis; }
  .resource-toolbar { align-items: stretch; flex-direction: column; gap: 9px; }
  .resource-toolbar__meta { justify-content: space-between; }
  .resource-row__facts { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
