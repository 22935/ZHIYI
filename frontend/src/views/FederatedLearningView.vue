<template>
  <div class="federated-learning-view">
    <div class="page-header glass-panel">
      <div>
        <h1>联邦学习中心</h1>
        <p>分布式模型协同训练与版本管理</p>
      </div>
      <div class="header-actions">
        <el-button type="primary" @click="startDemo" :disabled="demoRunning">
          <el-icon><VideoPlay /></el-icon>
          开始演示
        </el-button>
        <el-button @click="resetSystem">
          <el-icon><Refresh /></el-icon>
          重置系统
        </el-button>
        <el-button @click="exportReport">
          <el-icon><Document /></el-icon>
          导出报告
        </el-button>
      </div>
    </div>

    <div class="overview-cards">
      <div class="overview-card glass-panel" v-for="stat in systemStats" :key="stat.label">
        <div class="stat-icon">{{ stat.icon }}</div>
        <div class="stat-content">
          <div class="stat-value">{{ stat.value }}</div>
          <div class="stat-label">{{ stat.label }}</div>
        </div>
        <div class="stat-trend" :class="{ positive: stat.trend > 0, negative: stat.trend < 0 }">
          <el-icon v-if="stat.trend > 0"><Top /></el-icon>
          <el-icon v-else-if="stat.trend < 0"><Bottom /></el-icon>
          {{ Math.abs(stat.trend) }}%
        </div>
      </div>
    </div>

    <div class="main-content">
      <div class="network-section glass-panel">
        <div class="section-header">
          <h2>联邦网络拓扑</h2>
          <div class="section-actions">
            <el-button size="small" @click="refreshNetwork">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
            <el-switch
              v-model="autoRefresh"
              active-text="自动刷新"
              inactive-text="手动刷新"
            />
          </div>
        </div>

        <div class="network-toolbar">
          <el-button size="small" circle @click="zoomIn"><el-icon><ZoomIn /></el-icon></el-button>
          <el-button size="small" circle @click="zoomOut"><el-icon><ZoomOut /></el-icon></el-button>
          <el-button size="small" circle @click="resetView"><el-icon><Refresh /></el-icon></el-button>
          <el-button size="small" circle @click="toggleFullscreen"><el-icon><FullScreen /></el-icon></el-button>
        </div>

        <div ref="networkCanvas" class="network-canvas"></div>

        <div class="network-status">
          <div class="item">活跃节点：<strong>{{ activeNodesCount }}</strong></div>
          <div class="item">待激活节点：<strong>{{ inactiveNodesCount }}</strong></div>
          <div class="item">数据传输：<strong>{{ dataTransfers }}</strong></div>
        </div>
      </div>

      <div class="details-section">
        <div class="detail-card glass-panel">
          <div class="section-header">
            <h3>模型版本历史</h3>
            <div class="section-actions">
              <el-radio-group v-model="timelineView" size="small">
                <el-radio-button label="all">全部</el-radio-button>
                <el-radio-button label="latest">最新</el-radio-button>
                <el-radio-button label="significant">重点</el-radio-button>
              </el-radio-group>
              <el-button size="small" @click="compareVersions" :disabled="selectedVersions.length < 2">
                <el-icon><ScaleToOriginal /></el-icon>
                版本对比
              </el-button>
              <el-button size="small" @click="exportHistory">
                <el-icon><Download /></el-icon>
                导出
              </el-button>
            </div>
          </div>

          <div class="timeline-wrap">
            <el-timeline v-if="filteredModelHistory.length">
              <el-timeline-item
                v-for="version in filteredModelHistory"
                :key="version.version_id"
                :timestamp="formatTime(version.created_at)"
                :type="version.isLatest ? 'primary' : version.significant ? 'warning' : 'info'"
              >
                <div
                  class="version-card"
                  :class="{ selected: selectedVersions.includes(version.version_id) }"
                  @click="toggleVersionSelection(version)"
                  @dblclick="showVersionDetails(version)"
                >
                  <div class="version-top">
                    <el-tag size="small">v{{ version.version }}</el-tag>
                    <el-tag v-if="version.isLatest" size="small" type="success">最新</el-tag>
                    <el-tag v-if="version.significant" size="small" type="warning">重点</el-tag>
                  </div>
                  <div class="version-metrics">
                    <span>客户端：{{ version.clients_count }}</span>
                    <span>准确率：{{ version.accuracy }}%</span>
                    <span>损失：{{ version.loss }}</span>
                    <span>训练时长：{{ version.training_duration }}</span>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无模型历史数据" />
          </div>
        </div>

        <div class="detail-card glass-panel">
          <div class="section-header">
            <h3>客户端列表</h3>
            <el-input
              v-model="clientSearch"
              size="small"
              placeholder="搜索客户端"
              clearable
              style="width: 220px"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>

          <div class="clients-overview">
            <span>总数：{{ clients.length }}</span>
            <span>活跃率：{{ activeRate }}%</span>
            <span>数据量：{{ totalDataSize }} MB</span>
          </div>

          <div class="clients-wrap">
            <div
              v-for="client in filteredClients"
              :key="client.client_id"
              class="client-card"
              :class="{ selected: selectedClients.includes(client.client_id), active: client.upload_count > 0 }"
              @click="toggleClientSelection(client)"
              @dblclick="showClientDetails(client)"
            >
              <div class="client-top">
                <div>
                  <div class="name">{{ client.info?.name || client.client_id }}</div>
                  <div class="meta">
                    <span>上传 {{ client.upload_count }} 次</span>
                    <span v-if="client.is_online" class="online">在线</span>
                    <span v-else class="offline">离线</span>
                  </div>
                </div>
                <el-button size="small" circle @click.stop="sendMessageToClient(client)">
                  <el-icon><Message /></el-icon>
                </el-button>
              </div>

              <div class="client-stats">
                <div>最后上传：{{ formatTime(client.last_upload) }}</div>
                <div>数据量：{{ client.data_size }} MB</div>
                <div>贡献度：{{ client.contribution }}%</div>
              </div>

              <div class="progress-row">
                <span>准确率</span>
                <el-progress :percentage="client.accuracy" :show-text="false" :stroke-width="4" />
                <span>{{ client.accuracy }}%</span>
              </div>
              <div class="progress-row">
                <span>训练进度</span>
                <el-progress :percentage="client.training_progress" :show-text="false" :stroke-width="4" />
                <span>{{ client.training_progress }}%</span>
              </div>
            </div>

            <el-empty v-if="filteredClients.length === 0" description="未找到匹配客户端" />
          </div>
        </div>
      </div>
    </div>

    <div v-if="demoRunning" class="demo-box glass-panel">
      <div class="section-header compact">
        <h3>演示进行中</h3>
        <el-button size="small" @click="stopDemo">
          <el-icon><Close /></el-icon>
          停止
        </el-button>
      </div>
      <div class="demo-steps">
        <div class="step">
          <span>1. 客户端接入</span>
          <el-progress :percentage="demoProgress.clientConnect" />
        </div>
        <div class="step">
          <span>2. 本地训练</span>
          <el-progress :percentage="demoProgress.localTraining" />
        </div>
        <div class="step">
          <span>3. 全局聚合</span>
          <el-progress :percentage="demoProgress.globalAggregation" />
        </div>
      </div>
    </div>

    <el-dialog v-model="clientDialog.visible" title="客户端详情" width="560px">
      <div v-if="clientDialog.data" class="client-dialog-content">
        <p><strong>名称：</strong>{{ clientDialog.data.info?.name || clientDialog.data.client_id }}</p>
        <p><strong>ID：</strong>{{ clientDialog.data.client_id }}</p>
        <p><strong>上传次数：</strong>{{ clientDialog.data.upload_count }}</p>
        <p><strong>最后上传：</strong>{{ formatTime(clientDialog.data.last_upload) }}</p>
        <p><strong>数据量：</strong>{{ clientDialog.data.data_size }} MB</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoPlay,
  Refresh,
  Top,
  Bottom,
  Download,
  Search,
  Close,
  Document,
  ZoomIn,
  ZoomOut,
  FullScreen,
  ScaleToOriginal,
  Message
} from '@element-plus/icons-vue'

type TimelineView = 'all' | 'latest' | 'significant'

interface ModelVersion {
  version_id: string
  version: string
  created_at: string
  clients_count: number
  accuracy: number
  loss: number
  isLatest: boolean
  significant: boolean
  accuracy_trend: number
  training_duration: string
}

interface ClientNode {
  client_id: string
  upload_count: number
  last_upload: string | null
  info: { name: string }
  data_size: number
  is_online: boolean
  contribution: number
  accuracy: number
  training_progress: number
}

const demoRunning = ref(false)
const autoRefresh = ref(true)
const clientSearch = ref('')
const timelineView = ref<TimelineView>('all')
const selectedVersions = ref<string[]>([])
const selectedClients = ref<string[]>([])
const zoomLevel = ref(1)
let refreshInterval: ReturnType<typeof setInterval> | null = null
let demoInterval: ReturnType<typeof setInterval> | null = null

const demoProgress = ref({
  clientConnect: 0,
  localTraining: 0,
  globalAggregation: 0
})

const clientDialog = ref<{ visible: boolean; data: ClientNode | null }>({
  visible: false,
  data: null
})

const systemStats = ref([
  { icon: '节点', label: '活跃节点', value: '5', trend: 25 },
  { icon: '版本', label: '模型版本', value: '8', trend: 12 },
  { icon: '轮次', label: '训练轮次', value: '32', trend: 8 },
  { icon: '精度', label: '平均准确率', value: '92.5%', trend: 3 }
])

const modelHistory = ref<ModelVersion[]>([
  {
    version_id: 'v1.0.0',
    version: '1.0.0',
    created_at: new Date(Date.now() - 2592000000).toISOString(),
    clients_count: 3,
    accuracy: 85.2,
    loss: 0.45,
    isLatest: false,
    significant: false,
    accuracy_trend: 0,
    training_duration: '34m'
  },
  {
    version_id: 'v1.1.0',
    version: '1.1.0',
    created_at: new Date(Date.now() - 1728000000).toISOString(),
    clients_count: 5,
    accuracy: 88.7,
    loss: 0.38,
    isLatest: false,
    significant: true,
    accuracy_trend: 3.5,
    training_duration: '29m'
  },
  {
    version_id: 'v1.2.0',
    version: '1.2.0',
    created_at: new Date(Date.now() - 864000000).toISOString(),
    clients_count: 7,
    accuracy: 91.3,
    loss: 0.29,
    isLatest: false,
    significant: true,
    accuracy_trend: 2.6,
    training_duration: '24m'
  },
  {
    version_id: 'v1.3.0',
    version: '1.3.0',
    created_at: new Date().toISOString(),
    clients_count: 8,
    accuracy: 92.5,
    loss: 0.25,
    isLatest: true,
    significant: true,
    accuracy_trend: 1.2,
    training_duration: '22m'
  }
])

const clients = ref<ClientNode[]>([
  {
    client_id: 'client_001',
    upload_count: 12,
    last_upload: new Date().toISOString(),
    info: { name: '北京节点' },
    data_size: 245,
    is_online: true,
    contribution: 24,
    accuracy: 93,
    training_progress: 100
  },
  {
    client_id: 'client_002',
    upload_count: 8,
    last_upload: new Date(Date.now() - 86400000).toISOString(),
    info: { name: '上海节点' },
    data_size: 187,
    is_online: true,
    contribution: 18,
    accuracy: 90,
    training_progress: 86
  },
  {
    client_id: 'client_003',
    upload_count: 0,
    last_upload: null,
    info: { name: '广州节点' },
    data_size: 0,
    is_online: false,
    contribution: 0,
    accuracy: 0,
    training_progress: 0
  },
  {
    client_id: 'client_004',
    upload_count: 15,
    last_upload: new Date().toISOString(),
    info: { name: '深圳节点' },
    data_size: 312,
    is_online: true,
    contribution: 32,
    accuracy: 95,
    training_progress: 100
  },
  {
    client_id: 'client_005',
    upload_count: 6,
    last_upload: new Date(Date.now() - 172800000).toISOString(),
    info: { name: '杭州节点' },
    data_size: 134,
    is_online: false,
    contribution: 12,
    accuracy: 88,
    training_progress: 72
  }
])

const activeNodesCount = computed(() => clients.value.filter(client => client.upload_count > 0).length)
const inactiveNodesCount = computed(() => clients.value.filter(client => client.upload_count === 0).length)

const dataTransfers = computed(() => {
  const base = clients.value.reduce((sum, client) => sum + Math.min(client.upload_count, 3), 0)
  if (!demoRunning.value) return base
  return base + Math.round((demoProgress.value.clientConnect + demoProgress.value.localTraining) / 20)
})

const filteredModelHistory = computed(() => {
  if (timelineView.value === 'latest') {
    return modelHistory.value.filter(version => version.isLatest)
  }
  if (timelineView.value === 'significant') {
    return modelHistory.value.filter(version => version.significant)
  }
  return modelHistory.value
})

const filteredClients = computed(() => {
  if (!clientSearch.value.trim()) return clients.value
  const keyword = clientSearch.value.trim().toLowerCase()
  return clients.value.filter(client => {
    const name = client.info?.name || client.client_id
    return name.toLowerCase().includes(keyword) || client.client_id.toLowerCase().includes(keyword)
  })
})

const activeRate = computed(() => {
  if (!clients.value.length) return 0
  return Math.round((activeNodesCount.value / clients.value.length) * 100)
})

const totalDataSize = computed(() => clients.value.reduce((total, client) => total + (client.data_size || 0), 0))

const networkCanvas = ref<HTMLElement | null>(null)

const applyCanvasZoom = () => {
  if (!networkCanvas.value) return
  networkCanvas.value.style.transform = `scale(${zoomLevel.value})`
  networkCanvas.value.style.transformOrigin = 'center center'
}

const renderNetwork = () => {
  if (!networkCanvas.value) return

  const canvas = networkCanvas.value
  canvas.innerHTML = ''

  const centerNode = document.createElement('div')
  centerNode.className = 'network-node center-node'
  centerNode.innerHTML = `
    <div class="node-pulse"></div>
    <div class="node-content">
      <span class="node-icon">AI</span>
      <span class="node-label">联邦中心</span>
    </div>
  `
  canvas.appendChild(centerNode)

  clients.value.forEach((client, index) => {
    const angle = (index / clients.value.length) * 2 * Math.PI
    const radius = 180
    const isActive = client.upload_count > 0

    const line = document.createElement('div')
    line.className = `network-line ${isActive ? 'active' : ''}`
    line.style.width = `${radius}px`
    line.style.left = '50%'
    line.style.top = '50%'
    line.style.transform = `rotate(${angle}rad)`
    if (isActive) line.innerHTML = '<div class="data-flow"></div>'

    const clientNode = document.createElement('div')
    clientNode.className = `network-node client-node ${isActive ? 'active' : ''}`
    clientNode.style.left = `calc(50% + ${radius * Math.cos(angle)}px)`
    clientNode.style.top = `calc(50% + ${radius * Math.sin(angle)}px)`
    clientNode.innerHTML = `
      <div class="node-content">
        <span class="node-icon">${getClientIcon(client.info?.name)}</span>
        <span class="node-label">${client.info?.name || client.client_id}</span>
      </div>
      <div class="node-status ${isActive ? 'active' : ''}"></div>
    `

    canvas.appendChild(line)
    canvas.appendChild(clientNode)
  })

  applyCanvasZoom()
}

const startDemo = async () => {
  demoRunning.value = true
  ElMessage.success('演示已启动')

  if (demoInterval) clearInterval(demoInterval)
  demoProgress.value = { clientConnect: 0, localTraining: 0, globalAggregation: 0 }

  demoInterval = setInterval(() => {
    if (demoProgress.value.clientConnect < 100) {
      demoProgress.value.clientConnect += 10
      return
    }
    if (demoProgress.value.localTraining < 100) {
      demoProgress.value.localTraining += 10
      return
    }
    if (demoProgress.value.globalAggregation < 100) {
      demoProgress.value.globalAggregation += 10
      return
    }

    stopDemo()
    ElMessage.success('演示完成')
  }, 800)
}

const stopDemo = () => {
  demoRunning.value = false
  demoProgress.value = { clientConnect: 0, localTraining: 0, globalAggregation: 0 }
  if (demoInterval) {
    clearInterval(demoInterval)
    demoInterval = null
  }
}

const resetSystem = async () => {
  try {
    await ElMessageBox.confirm('确定要重置联邦学习面板吗？', '确认重置', {
      confirmButtonText: '重置',
      cancelButtonText: '取消',
      type: 'warning'
    })
    stopDemo()
    selectedVersions.value = []
    selectedClients.value = []
    zoomLevel.value = 1
    renderNetwork()
    ElMessage.success('系统已重置')
  } catch {
    // ignore cancel
  }
}

const refreshNetwork = () => {
  renderNetwork()
  ElMessage.success('拓扑已刷新')
}

const exportReport = () => {
  ElMessage.success('报告导出成功')
}

const exportHistory = () => {
  ElMessage.success('模型历史导出成功')
}

const zoomIn = () => {
  zoomLevel.value = Math.min(1.8, Number((zoomLevel.value + 0.1).toFixed(2)))
  applyCanvasZoom()
}

const zoomOut = () => {
  zoomLevel.value = Math.max(0.6, Number((zoomLevel.value - 0.1).toFixed(2)))
  applyCanvasZoom()
}

const resetView = () => {
  zoomLevel.value = 1
  applyCanvasZoom()
}

const toggleFullscreen = async () => {
  if (!networkCanvas.value) return
  try {
    if (!document.fullscreenElement) {
      await networkCanvas.value.requestFullscreen()
    } else {
      await document.exitFullscreen()
    }
  } catch {
    ElMessage.warning('当前环境不支持全屏')
  }
}

const toggleVersionSelection = (version: ModelVersion) => {
  const id = version.version_id
  if (selectedVersions.value.includes(id)) {
    selectedVersions.value = selectedVersions.value.filter(item => item !== id)
    return
  }
  if (selectedVersions.value.length >= 2) {
    selectedVersions.value = [selectedVersions.value[1], id]
    return
  }
  selectedVersions.value = [...selectedVersions.value, id]
}

const compareVersions = () => {
  if (selectedVersions.value.length < 2) {
    ElMessage.warning('请先选择两个版本')
    return
  }

  const [aId, bId] = selectedVersions.value
  const a = modelHistory.value.find(item => item.version_id === aId)
  const b = modelHistory.value.find(item => item.version_id === bId)

  if (!a || !b) {
    ElMessage.warning('版本数据不存在')
    return
  }

  const acc = (b.accuracy - a.accuracy).toFixed(2)
  const loss = (b.loss - a.loss).toFixed(3)
  ElMessage.info(`v${a.version} -> v${b.version}，准确率变化 ${acc}%，损失变化 ${loss}`)
}

const showVersionDetails = (version: ModelVersion) => {
  ElMessage.info(`版本 v${version.version}，客户端 ${version.clients_count}，准确率 ${version.accuracy}%`)
}

const toggleClientSelection = (client: ClientNode) => {
  const id = client.client_id
  if (selectedClients.value.includes(id)) {
    selectedClients.value = selectedClients.value.filter(item => item !== id)
    return
  }
  selectedClients.value = [...selectedClients.value, id]
}

const sendMessageToClient = (client: ClientNode) => {
  ElMessage.success(`已向 ${client.info?.name || client.client_id} 下发指令`)
}

const showClientDetails = (client: ClientNode) => {
  clientDialog.value = { visible: true, data: client }
}

const getClientIcon = (name: string) => {
  if (!name) return 'N'
  if (name.includes('北京')) return '京'
  if (name.includes('上海')) return '沪'
  if (name.includes('广州')) return '穗'
  if (name.includes('深圳')) return '深'
  if (name.includes('杭州')) return '杭'
  return 'N'
}

const formatTime = (time: string | null) => {
  if (!time) return '从未上传'
  return new Date(time).toLocaleString('zh-CN')
}

onMounted(() => {
  renderNetwork()
  refreshInterval = setInterval(() => {
    if (autoRefresh.value) renderNetwork()
  }, 5000)
})

onUnmounted(() => {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
  if (demoInterval) {
    clearInterval(demoInterval)
    demoInterval = null
  }
})
</script>

<style scoped>
.federated-learning-view {
  min-height: 100%;
  padding: 16px;
  background: var(--bg-app);
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.glass-panel {
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid var(--border-light);
  border-radius: 12px;
}

.page-header {
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
}

.page-header p {
  margin: 6px 0 0;
  color: var(--text-secondary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.overview-cards {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.overview-card {
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.stat-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--primary-fade);
  display: grid;
  place-items: center;
  color: var(--primary-color);
  font-weight: 700;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 18px;
  font-weight: 700;
}

.stat-label {
  color: var(--text-secondary);
  font-size: 12px;
}

.stat-trend {
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.stat-trend.positive {
  color: #16a34a;
}

.stat-trend.negative {
  color: #dc2626;
}

.main-content {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 12px;
  min-height: 0;
}

.network-section,
.detail-card {
  padding: 12px;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.section-header h2,
.section-header h3 {
  margin: 0;
}

.section-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.network-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.network-canvas {
  height: 360px;
  background: #f8fafc;
  border-radius: 10px;
  position: relative;
  overflow: hidden;
}

.network-status {
  margin-top: 10px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  color: var(--text-secondary);
}

.details-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
}

.timeline-wrap,
.clients-wrap {
  max-height: 280px;
  overflow-y: auto;
}

.version-card {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 8px;
  cursor: pointer;
  background: #fff;
}

.version-card.selected {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}

.version-top,
.version-metrics {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.version-metrics {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.clients-overview {
  display: flex;
  gap: 12px;
  margin-bottom: 10px;
  color: var(--text-secondary);
  font-size: 12px;
}

.client-card {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 10px;
  background: #fff;
  margin-bottom: 8px;
}

.client-card.active {
  border-color: #86efac;
}

.client-card.selected {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}

.client-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.name {
  font-weight: 600;
}

.meta {
  color: var(--text-secondary);
  font-size: 12px;
  display: flex;
  gap: 8px;
}

.online {
  color: #16a34a;
}

.offline {
  color: #6b7280;
}

.client-stats {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
  display: grid;
  gap: 4px;
}

.progress-row {
  margin-top: 6px;
  display: grid;
  grid-template-columns: 52px 1fr 42px;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.demo-box {
  padding: 12px;
}

.section-header.compact {
  margin-bottom: 8px;
}

.demo-steps {
  display: grid;
  gap: 10px;
}

.step {
  display: grid;
  gap: 6px;
}

.client-dialog-content p {
  margin: 8px 0;
}

.network-node {
  position: absolute;
  width: 96px;
  height: 96px;
  border-radius: 999px;
  transform: translate(-50%, -50%);
  display: grid;
  place-items: center;
  text-align: center;
  font-size: 12px;
}

.network-node.center-node {
  left: 50%;
  top: 50%;
  background: #e0f2fe;
  border: 1px solid #7dd3fc;
  z-index: 2;
}

.network-node.client-node {
  background: #fff;
  border: 1px solid #dbeafe;
  z-index: 2;
}

.network-node.client-node.active {
  border-color: #86efac;
}

.node-status {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #9ca3af;
}

.node-status.active {
  background: #22c55e;
}

.node-icon {
  font-weight: 700;
  color: var(--primary-color);
}

.node-label {
  display: block;
  margin-top: 4px;
  color: var(--text-secondary);
}

.network-line {
  position: absolute;
  left: 50%;
  top: 50%;
  height: 1px;
  background: #cbd5e1;
  transform-origin: left center;
}

.network-line.active {
  background: #22c55e;
}

.data-flow {
  width: 18px;
  height: 100%;
  background: linear-gradient(90deg, rgba(34, 197, 94, 0.9), transparent);
  animation: flow 1.8s linear infinite;
}

.node-pulse {
  position: absolute;
  inset: 0;
  border-radius: 999px;
  border: 1px solid rgba(14, 165, 233, 0.4);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes flow {
  from { transform: translateX(-100%); }
  to { transform: translateX(900%); }
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.15); opacity: 0.5; }
}

@media (max-width: 1200px) {
  .overview-cards {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .main-content {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    flex-wrap: wrap;
  }

  .overview-cards {
    grid-template-columns: 1fr;
  }
}
</style>
