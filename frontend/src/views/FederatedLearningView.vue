<template>
  <div class="federated-learning-view">
    <!-- 背景氛围元素 -->
    <div class="ambient-glow top-left"></div>
    <div class="ambient-glow bottom-right"></div>
    
    <!-- 页面标题区域 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <span class="icon">🌐</span>
          联邦学习系统
        </h1>
        <p class="page-subtitle">分布式智能模型训练与协作平台</p>
      </div>
      
      <!-- 全局控制面板 -->
      <div class="global-controls">
        <el-button type="primary" class="glass-btn" @click="startDemo" :disabled="demoRunning">
          <el-icon><VideoPlay /></el-icon>
          开始演示
        </el-button>
        <el-button class="glass-btn" @click="resetSystem">
          <el-icon><Refresh /></el-icon>
          重置系统
        </el-button>
        <el-button class="glass-btn" @click="exportReport">
          <el-icon><Document /></el-icon>
          导出报告
        </el-button>
      </div>
    </div>

    <!-- 系统概览卡片 -->
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

    <!-- 主要内容区域 -->
    <div class="main-content">
      <!-- 左侧：网络拓扑可视化 -->
      <div class="network-section glass-panel">
        <div class="section-header">
          <h2 class="section-title">
            <span class="icon">🕸️</span>
            联邦网络拓扑
          </h2>
          <div class="section-controls">
            <el-button size="small" class="glass-btn" @click="refreshNetwork">
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
        
        <div class="network-canvas-container">
          <!-- 网络控制工具栏 -->
          <div class="network-toolbar">
            <el-tooltip content="放大视图" placement="top">
              <el-button size="small" circle @click="zoomIn">
                <el-icon><ZoomIn /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="缩小视图" placement="top">
              <el-button size="small" circle @click="zoomOut">
                <el-icon><ZoomOut /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="重置视图" placement="top">
              <el-button size="small" circle @click="resetView">
                <el-icon><Refresh /></el-icon>
              </el-button>
            </el-tooltip>
            <el-tooltip content="全屏显示" placement="top">
              <el-button size="small" circle @click="toggleFullscreen">
                <el-icon><FullScreen /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
          
          <div ref="networkCanvas" class="network-canvas">
            <!-- 网络拓扑将通过JavaScript动态生成 -->
          </div>
          
          <!-- 网络状态指示器 -->
          <div class="network-status">
            <div class="status-item">
              <div class="status-dot active"></div>
              <span>活跃节点</span>
              <span class="status-count">{{ activeNodesCount }}</span>
            </div>
            <div class="status-item">
              <div class="status-dot inactive"></div>
              <span>待激活节点</span>
              <span class="status-count">{{ inactiveNodesCount }}</span>
            </div>
            <div class="status-item">
              <div class="status-dot data-flow"></div>
              <span>数据传输</span>
              <span class="status-count">{{ dataTransfers }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：详细信息面板 -->
      <div class="details-panel">
        <!-- 模型版本历史 -->
        <div class="detail-section glass-panel">
          <div class="section-header">
            <h3 class="section-title">
              <span class="icon">📊</span>
              模型版本历史
            </h3>
            <el-button size="small" class="glass-btn" @click="exportHistory">
              <el-icon><Download /></el-icon>
              导出
            </el-button>
          </div>
          
          <div class="timeline-container">
            <!-- 时间线控制 -->
            <div class="timeline-controls">
              <el-radio-group v-model="timelineView" size="small">
                <el-radio-button label="all">全部版本</el-radio-button>
                <el-radio-button label="latest">仅显示最新</el-radio-button>
                <el-radio-button label="significant">重要更新</el-radio-button>
              </el-radio-group>
              <el-button size="small" @click="compareVersions" :disabled="selectedVersions.length < 2">
                <el-icon><Scale /></el-icon>
                版本对比
              </el-button>
            </div>
            
            <el-timeline v-if="filteredModelHistory.length > 0">
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
                  <div class="version-header">
                    <span class="version-tag">v{{ version.version }}</span>
                    <span class="clients-badge">{{ version.clients_count }} 客户端</span>
                    <el-tag v-if="version.isLatest" type="success" size="small">最新</el-tag>
                    <el-tag v-if="version.significant" type="warning" size="small">重要</el-tag>
                  </div>
                  <div class="version-metrics">
                    <span class="metric">准确率: {{ version.accuracy }}%</span>
                    <span class="metric">损失: {{ version.loss }}</span>
                    <span class="metric">训练时长: {{ version.training_duration }}</span>
                  </div>
                  <!-- 性能趋势指示器 -->
                  <div class="performance-trend">
                    <el-icon v-if="version.accuracy_trend > 0" color="#52c41a"><Top /></el-icon>
                    <el-icon v-else-if="version.accuracy_trend < 0" color="#ff4d4f"><Bottom /></el-icon>
                    <span v-if="version.accuracy_trend !== 0" class="trend-value">
                      {{ Math.abs(version.accuracy_trend) }}%
                    </span>
                  </div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无模型历史记录">
              <template #description>
                <p>开始联邦学习训练后，模型版本历史将在此显示</p>
              </template>
            </el-empty>
          </div>
        </div>

        <!-- 客户端列表 -->
        <div class="detail-section glass-panel">
          <div class="section-header">
            <h3 class="section-title">
              <span class="icon">👥</span>
              客户端列表
            </h3>
            <el-input
              v-model="clientSearch"
              placeholder="搜索客户端..."
              size="small"
              style="width: 200px"
              clearable
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>
          
          <div class="clients-container">
            <!-- 客户端统计概览 -->
            <div class="clients-overview">
              <div class="overview-item">
                <span class="overview-label">总客户端数</span>
                <span class="overview-value">{{ clients.length }}</span>
              </div>
              <div class="overview-item">
                <span class="overview-label">活跃率</span>
                <span class="overview-value">{{ activeRate }}%</span>
              </div>
              <div class="overview-item">
                <span class="overview-label">总数据量</span>
                <span class="overview-value">{{ totalDataSize }} MB</span>
              </div>
            </div>
            
            <div
              v-for="client in filteredClients"
              :key="client.client_id"
              class="client-card"
              :class="{ 
                active: client.upload_count > 0, 
                selected: selectedClients.includes(client.client_id),
                online: client.is_online
              }"
              @click="toggleClientSelection(client)"
              @dblclick="showClientDetails(client)"
            >
              <div class="client-header">
                <div class="client-avatar">
                  <span class="avatar-icon">{{ getClientIcon(client.info?.name) }}</span>
                  <div class="online-indicator" v-if="client.is_online"></div>
                </div>
                <div class="client-info">
                  <div class="client-name">{{ client.info?.name || client.client_id }}</div>
                  <div class="client-status">
                    <span class="status-dot" :class="{ active: client.upload_count > 0 }"></span>
                    {{ client.upload_count > 0 ? '活跃' : '待激活' }}
                    <span v-if="client.is_online" class="online-badge">在线</span>
                  </div>
                </div>
                <div class="client-actions">
                  <el-tag
                    :type="client.upload_count > 0 ? 'success' : 'info'"
                    size="small"
                  >
                    {{ client.upload_count }} 次
                  </el-tag>
                  <el-button size="small" circle @click="sendMessageToClient(client)">
                    <el-icon><Message /></el-icon>
                  </el-button>
                </div>
              </div>
              
              <div class="client-stats">
                <div class="stat">
                  <span class="stat-label">最后上传:</span>
                  <span class="stat-value">{{ formatTime(client.last_upload) }}</span>
                </div>
                <div class="stat">
                  <span class="stat-label">数据量:</span>
                  <span class="stat-value">{{ client.data_size || '0' }} MB</span>
                </div>
                <div class="stat">
                  <span class="stat-label">贡献度:</span>
                  <div class="contribution-bar">
                    <div 
                      class="contribution-fill" 
                      :style="{ width: client.contribution + '%' }"
                    ></div>
                  </div>
                  <span class="stat-value">{{ client.contribution }}%</span>
                </div>
              </div>
              
              <!-- 客户端性能指标 -->
              <div class="client-performance">
                <div class="performance-metric">
                  <span class="metric-label">准确率</span>
                  <el-progress 
                    :percentage="client.accuracy || 0" 
                    :show-text="false"
                    :stroke-width="4"
                  />
                  <span class="metric-value">{{ client.accuracy || 0 }}%</span>
                </div>
                <div class="performance-metric">
                  <span class="metric-label">训练进度</span>
                  <el-progress 
                    :percentage="client.training_progress || 0" 
                    :show-text="false"
                    :stroke-width="4"
                  />
                  <span class="metric-value">{{ client.training_progress || 0 }}%</span>
                </div>
              </div>
            </div>
            
            <el-empty v-if="filteredClients.length === 0" description="未找到匹配的客户端">
              <template #description>
                <p>尝试调整搜索条件或等待客户端连接</p>
              </template>
            </el-empty>
          </div>
        </div>
      </div>
    </div>

    <!-- 演示控制面板 -->
    <div v-if="demoRunning" class="demo-controls glass-panel">
      <div class="demo-header">
        <h3>交互演示控制台</h3>
        <el-button size="small" @click="stopDemo">
          <el-icon><Close /></el-icon>
          停止演示
        </el-button>
      </div>
      
      <div class="demo-content">
        <div class="demo-step">
          <span class="step-number">1</span>
          <span class="step-text">模拟客户端连接和数据上传</span>
          <el-progress :percentage="demoProgress.clientConnect" />
        </div>
        
        <div class="demo-step">
          <span class="step-number">2</span>
          <span class="step-text">本地模型训练和参数更新</span>
          <el-progress :percentage="demoProgress.localTraining" />
        </div>
        
        <div class="demo-step">
          <span class="step-number">3</span>
          <span class="step-text">全局模型聚合和版本发布</span>
          <el-progress :percentage="demoProgress.globalAggregation" />
        </div>
      </div>
    </div>

    <!-- 客户端详情弹窗 -->
    <el-dialog
      v-model="clientDialog.visible"
      title="客户端详情"
      width="600px"
      class="client-detail-dialog"
    >
      <div v-if="clientDialog.data" class="client-detail-content">
        <div class="detail-header">
          <div class="client-avatar large">
            <span class="avatar-icon">{{ getClientIcon(clientDialog.data.info?.name) }}</span>
          </div>
          <div class="detail-info">
            <h3>{{ clientDialog.data.info?.name || clientDialog.data.client_id }}</h3>
            <p>客户端 ID: {{ clientDialog.data.client_id }}</p>
          </div>
        </div>
        
        <div class="detail-stats">
          <div class="stat-row">
            <span class="stat-label">上传次数:</span>
            <span class="stat-value">{{ clientDialog.data.upload_count }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">最后上传:</span>
            <span class="stat-value">{{ formatTime(clientDialog.data.last_upload) }}</span>
          </div>
          <div class="stat-row">
            <span class="stat-label">数据总量:</span>
            <span class="stat-value">{{ clientDialog.data.data_size || '0' }} MB</span>
          </div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  VideoPlay, Refresh, Top, Bottom, Download, Search, Close
} from '@element-plus/icons-vue'

// 响应式数据
const demoRunning = ref(false)
const autoRefresh = ref(true)
const clientSearch = ref('')
const demoProgress = ref({
  clientConnect: 0,
  localTraining: 0,
  globalAggregation: 0
})

const clientDialog = ref({
  visible: false,
  data: null as any
})

// 系统统计数据
const systemStats = ref([
  { icon: '🌐', label: '活跃节点', value: '5', trend: 25 },
  { icon: '📊', label: '模型版本', value: '8', trend: 12 },
  { icon: '⚡', label: '训练轮次', value: '32', trend: 8 },
  { icon: '📈', label: '准确率', value: '92.5%', trend: 3 }
])

// 模拟数据
const modelHistory = ref([
  { version_id: 'v1.0.0', version: '1.0.0', created_at: new Date(Date.now() - 2592000000).toISOString(), clients_count: 3, accuracy: 85.2, loss: 0.45, isLatest: false },
  { version_id: 'v1.1.0', version: '1.1.0', created_at: new Date(Date.now() - 1728000000).toISOString(), clients_count: 5, accuracy: 88.7, loss: 0.38, isLatest: false },
  { version_id: 'v1.2.0', version: '1.2.0', created_at: new Date(Date.now() - 864000000).toISOString(), clients_count: 7, accuracy: 91.3, loss: 0.29, isLatest: false },
  { version_id: 'v1.3.0', version: '1.3.0', created_at: new Date().toISOString(), clients_count: 8, accuracy: 92.5, loss: 0.25, isLatest: true }
])

const clients = ref([
  { client_id: 'client_001', upload_count: 12, last_upload: new Date().toISOString(), info: { name: '北京节点' }, data_size: 245 },
  { client_id: 'client_002', upload_count: 8, last_upload: new Date(Date.now() - 86400000).toISOString(), info: { name: '上海节点' }, data_size: 187 },
  { client_id: 'client_003', upload_count: 0, last_upload: null, info: { name: '广州节点' }, data_size: 0 },
  { client_id: 'client_004', upload_count: 15, last_upload: new Date().toISOString(), info: { name: '深圳节点' }, data_size: 312 },
  { client_id: 'client_005', upload_count: 6, last_upload: new Date(Date.now() - 172800000).toISOString(), info: { name: '杭州节点' }, data_size: 134 }
])

// 计算属性
const activeNodesCount = computed(() => 
  clients.value.filter(client => client.upload_count > 0).length
)

const inactiveNodesCount = computed(() => 
  clients.value.filter(client => client.upload_count === 0).length
)

const filteredClients = computed(() => {
  if (!clientSearch.value) return clients.value
  return clients.value.filter(client => 
    (client.info?.name || client.client_id).toLowerCase().includes(clientSearch.value.toLowerCase())
  )
})

const activeRate = computed(() => {
  if (!clients.value.length) return 0
  const activeClients = clients.value.filter(client => client.upload_count > 0)
  return Math.round((activeClients.length / clients.value.length) * 100)
})

const totalDataSize = computed(() => {
  return clients.value.reduce((total, client) => total + (client.data_size || 0), 0)
})

// 方法
const startDemo = async () => {
  demoRunning.value = true
  ElMessage.success('开始联邦学习交互演示')
  
  // 模拟演示进度
  const interval = setInterval(() => {
    if (demoProgress.value.clientConnect < 100) {
      demoProgress.value.clientConnect += 10
    } else if (demoProgress.value.localTraining < 100) {
      demoProgress.value.localTraining += 10
    } else if (demoProgress.value.globalAggregation < 100) {
      demoProgress.value.globalAggregation += 10
    } else {
      clearInterval(interval)
      ElMessage.success('演示完成！')
    }
  }, 1000)
}

const stopDemo = () => {
  demoRunning.value = false
  demoProgress.value = { clientConnect: 0, localTraining: 0, globalAggregation: 0 }
  ElMessage.info('演示已停止')
}

const resetSystem = async () => {
  try {
    await ElMessageBox.confirm('确定要重置系统吗？这将清除所有演示数据。', '确认重置', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    stopDemo()
    // 重置数据到初始状态
    ElMessage.success('系统已重置')
  } catch {
    // 用户取消操作
  }
}

const refreshNetwork = () => {
  ElMessage.info('网络拓扑已刷新')
  renderNetwork()
}

const exportHistory = () => {
  ElMessage.success('模型历史数据导出成功')
}

const showVersionDetails = (version: any) => {
  ElMessage.info(`查看版本 ${version.version} 的详细信息`)
}

const showClientDetails = (client: any) => {
  clientDialog.value.data = client
  clientDialog.value.visible = true
}

const getClientIcon = (name: string) => {
  if (!name) return '💻'
  if (name.includes('北京')) return '🏛️'
  if (name.includes('上海')) return '🏙️'
  if (name.includes('广州')) return '🌉'
  if (name.includes('深圳')) return '🏢'
  if (name.includes('杭州')) return '🏞️'
  return '💻'
}

const formatTime = (time: string) => {
  if (!time) return '从未上传'
  const date = new Date(time)
  return date.toLocaleString('zh-CN')
}

// 网络拓扑渲染
const networkCanvas = ref<HTMLElement | null>(null)

const renderNetwork = () => {
  if (!networkCanvas.value) return
  
  const canvas = networkCanvas.value
  canvas.innerHTML = ''
  
  // 创建中心节点
  const centerNode = document.createElement('div')
  centerNode.className = 'network-node center-node'
  centerNode.innerHTML = `
    <div class="node-pulse"></div>
    <div class="node-content">
      <span class="node-icon">🌐</span>
      <span class="node-label">云端服务器</span>
    </div>
  `
  canvas.appendChild(centerNode)
  
  // 创建客户端节点
  clients.value.forEach((client, index) => {
    const angle = (index / clients.value.length) * 2 * Math.PI
    const radius = 180
    const isActive = client.upload_count > 0
    
    const clientNode = document.createElement('div')
    clientNode.className = `network-node client-node ${isActive ? 'active' : ''}`
    clientNode.style.left = `calc(50% + ${radius * Math.cos(angle)}px)`
    clientNode.style.top = `calc(50% + ${radius * Math.sin(angle)}px)`
    clientNode.innerHTML = `
      <div class="node-content">
        <span class="node-icon">${getClientIcon(client.info?.name)}</span>
        <span class="node-label">${client.info?.name || client.client_id}</span>
      </div>
      ${isActive ? '<div class="node-status active"></div>' : '<div class="node-status"></div>'}
    `
    
    // 创建连接线
    const line = document.createElement('div')
    line.className = `network-line ${isActive ? 'active' : ''}`
    line.style.width = `${radius}px`
    line.style.left = '50%'
    line.style.top = '50%'
    line.style.transform = `rotate(${angle}rad)`
    
    if (isActive) {
      line.innerHTML = '<div class="data-flow"></div>'
    }
    
    canvas.appendChild(line)
    canvas.appendChild(clientNode)
  })
}

// 生命周期
onMounted(() => {
  renderNetwork()
  
  // 自动刷新定时器
  const refreshInterval = setInterval(() => {
    if (autoRefresh.value) {
      renderNetwork()
    }
  }, 5000)
  
  onUnmounted(() => {
    clearInterval(refreshInterval)
  })
})
</script>

<style scoped>
.federated-learning-view {
  min-height: 100vh;
  padding: 24px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  position: relative;
  overflow-x: hidden;
  font-family: var(--font-sans);
}

/* 背景氛围效果 */
.ambient-glow {
  position: absolute;
  width: 300px;
  height: 300px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.1) 0%, transparent 70%);
  filter: blur(40px);
  z-index: 0;
}

.ambient-glow.top-left {
  top: -100px;
  left: -100px;
}

.ambient-glow.bottom-right {
  bottom: -100px;
  right: -100px;
}

/* 玻璃态面板样式 */
.glass-panel {
  background: rgba(255, 255, 255, 0.1);
  backdrop-filter: blur(20px);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
}

.glass-btn {
  background: rgba(255, 255, 255, 0.1) !important;
  backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 255, 255, 0.2) !important;
  color: white !important;
}

.glass-btn:hover {
  background: rgba(255, 255, 255, 0.2) !important;
  transform: translateY(-1px);
}

/* 页面标题 */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 32px;
  position: relative;
  z-index: 1;
}

.header-content {
  color: white;
}

.page-title {
  font-size: 36px;
  font-weight: 700;
  margin: 0 0 8px 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.page-subtitle {
  font-size: 16px;
  opacity: 0.9;
  margin: 0;
}

.global-controls {
  display: flex;
  gap: 12px;
}

/* 概览卡片 */
.overview-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 32px;
  position: relative;
  z-index: 1;
}

.overview-card {
  padding: 20px;
  color: white;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: transform 0.3s ease;
}

.overview-card:hover {
  transform: translateY(-2px);
}

.stat-icon {
  font-size: 32px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
}

.stat-label {
  font-size: 14px;
  opacity: 0.8;
  margin-top: 4px;
}

.stat-trend {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 14px;
  font-weight: 600;
}

.stat-trend.positive {
  color: #52c41a;
}

.stat-trend.negative {
  color: #f5222d;
}

/* 主要内容区域 */
.main-content {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 24px;
  position: relative;
  z-index: 1;
}

.network-section {
  min-height: 600px;
}

.details-panel {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.detail-section {
  flex: 1;
}

/* 区域标题 */
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 20px 0;
  margin-bottom: 16px;
}

.section-title {
  color: white;
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-controls {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* 网络拓扑容器 */
.network-canvas-container {
  padding: 20px;
  position: relative;
}

/* 网络控制工具栏 */
.network-toolbar {
  position: absolute;
  top: 10px;
  right: 10px;
  z-index: 10;
  display: flex;
  gap: 8px;
  background: rgba(255, 255, 255, 0.9);
  backdrop-filter: blur(10px);
  border-radius: var(--radius-md);
  padding: 8px;
  box-shadow: var(--shadow-md);
}

.network-toolbar .el-button {
  background: transparent !important;
  border: 1px solid var(--border-light) !important;
}

.network-canvas {
  position: relative;
  width: 100%;
  height: 400px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 12px;
  overflow: hidden;
  transition: all 0.3s ease;
}

/* 网络节点样式 */
.network-node {
  position: absolute;
  width: 100px;
  height: 100px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transform: translate(-50%, -50%);
  transition: all 0.3s ease;
  cursor: pointer;
}

.network-node.center-node {
  background: radial-gradient(circle at 30% 30%, #ff6b6b, #ee5a52);
  color: white;
  box-shadow: 0 8px 32px rgba(255, 107, 107, 0.4);
  left: 50%;
  top: 50%;
  z-index: 10;
}

.network-node.client-node {
  background: rgba(255, 255, 255, 0.1);
  border: 2px solid rgba(255, 255, 255, 0.3);
  color: white;
}

.network-node.client-node.active {
  background: rgba(82, 196, 26, 0.2);
  border-color: #52c41a;
  box-shadow: 0 4px 16px rgba(82, 196, 26, 0.3);
}

.node-content {
  text-align: center;
  z-index: 2;
}

.node-icon {
  font-size: 24px;
  display: block;
  margin-bottom: 4px;
}

.node-label {
  font-size: 12px;
  font-weight: 600;
}

.node-pulse {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  background: rgba(255, 107, 107, 0.3);
  animation: pulse 2s ease-in-out infinite;
}

.node-status {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
}

.node-status.active {
  background: #52c41a;
  animation: blink 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.2); opacity: 0.7; }
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* 网络连接线 */
.network-line {
  position: absolute;
  height: 2px;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.3), transparent);
  transform-origin: left center;
  z-index: 1;
}

.network-line.active {
  background: linear-gradient(90deg, #52c41a, transparent);
  height: 3px;
}

.data-flow {
  position: absolute;
  width: 20px;
  height: 100%;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0.8), transparent);
  animation: dataFlow 2s linear infinite;
}

@keyframes dataFlow {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(1000%); }
}

/* 网络状态指示器 */
.network-status {
  display: flex;
  gap: 20px;
  margin-top: 16px;
  justify-content: center;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: white;
  font-size: 14px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
}

.status-dot.active {
  background: #52c41a;
  animation: blink 2s ease-in-out infinite;
}

.status-count {
  font-weight: 600;
  margin-left: 4px;
}

/* 时间线容器 */
.timeline-container {
  padding: 0 20px 20px;
  max-height: 300px;
  overflow-y: auto;
}

.version-card {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 12px;
  margin: 8px 0;
  cursor: pointer;
  transition: background 0.3s ease;
}

.version-card:hover {
  background: rgba(255, 255, 255, 0.1);
}

.version-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.version-tag {
  background: rgba(24, 144, 255, 0.2);
  color: #1890ff;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.clients-badge {
  color: rgba(255, 255, 255, 0.7);
  font-size: 12px;
}

.version-metrics {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

/* 客户端列表 */
.clients-container {
  padding: 0 20px 20px;
  max-height: 300px;
  overflow-y: auto;
}

.client-card {
  background: rgba(255, 255, 255, 0.05);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.3s ease;
  border: 1px solid transparent;
}

.client-card:hover {
  background: rgba(255, 255, 255, 0.1);
  transform: translateY(-1px);
}

.client-card.active {
  border-color: rgba(82, 196, 26, 0.3);
}

.client-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.client-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  display: flex;
  align-items: center;
  justify-content: center;
}

.client-avatar.large {
  width: 60px;
  height: 60px;
}

.avatar-icon {
  font-size: 18px;
}

.client-avatar.large .avatar-icon {
  font-size: 24px;
}

.client-info {
  flex: 1;
}

.client-name {
  color: white;
  font-weight: 600;
  margin-bottom: 4px;
}

.client-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.7);
}

.client-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.stat {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}

.stat-label {
  color: rgba(255, 255, 255, 0.6);
}

.stat-value {
  color: white;
  font-weight: 600;
}

/* 演示控制面板 */
.demo-controls {
  position: fixed;
  bottom: 24px;
  right: 24px;
  width: 400px;
  z-index: 1000;
  color: white;
}

.demo-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.demo-content {
  padding: 20px;
}

.demo-step {
  margin-bottom: 16px;
}

.demo-step:last-child {
  margin-bottom: 0;
}

.step-number {
  display: inline-block;
  width: 24px;
  height: 24px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 50%;
  text-align: center;
  line-height: 24px;
  margin-right: 12px;
  font-weight: 600;
}

.step-text {
  font-size: 14px;
  margin-bottom: 8px;
  display: inline-block;
}

/* 弹窗样式 */
.client-detail-dialog {
  --el-dialog-bg-color: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(20px);
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
}

.detail-info h3 {
  margin: 0 0 8px 0;
  color: #1a1a1a;
}

.detail-info p {
  margin: 0;
  color: #666;
  font-size: 14px;
}

.detail-stats {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 16px;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #e8e8e8;
}

.stat-row:last-child {
  border-bottom: none;
}

.stat-row .stat-label {
  color: #666;
}

.stat-row .stat-value {
  color: #1a1a1a;
  font-weight: 600;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .main-content {
    grid-template-columns: 1fr;
  }
  
  .demo-controls {
    width: calc(100% - 48px);
    left: 24px;
    right: 24px;
  }
}

@media (max-width: 768px) {
  .page-header {
    flex-direction: column;
    gap: 16px;
  }
  
  .overview-cards {
    grid-template-columns: 1fr 1fr;
  }
  
  .page-title {
    font-size: 28px;
  }
}
</style>