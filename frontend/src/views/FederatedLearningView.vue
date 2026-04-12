<template>
  <div class="federated-learning-view">
    <!-- 页面标题 -->
    <div class="page-header">
      <div class="header-content">
        <h1 class="page-title">
          <span class="icon">🌐</span>
          联邦学习全局最优模型
        </h1>
        <p class="page-subtitle">数据不动模型动 · 参数可用不可见</p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">🖥️</div>
        <div class="stat-content">
          <div class="stat-value">{{ statistics.totalClients }}</div>
          <div class="stat-label">总客户端数</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">✅</div>
        <div class="stat-content">
          <div class="stat-value">{{ statistics.activeClients }}</div>
          <div class="stat-label">活跃客户端</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">🔄</div>
        <div class="stat-content">
          <div class="stat-value">{{ statistics.modelVersion }}</div>
          <div class="stat-label">当前模型版本</div>
        </div>
      </div>

      <div class="stat-card">
        <div class="stat-icon">📊</div>
        <div class="stat-content">
          <div class="stat-value">{{ statistics.trainingRounds }}</div>
          <div class="stat-label">训练轮次</div>
        </div>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="content-grid">
      <!-- 左侧：联邦网络可视化 -->
      <div class="content-card network-card">
        <div class="card-header">
          <h2 class="card-title">联邦网络拓扑</h2>
          <el-button size="small" @click="refreshNetwork">
            <span class="icon">🔄</span> 刷新
          </el-button>
        </div>
        <div class="card-body">
          <div ref="networkCanvas" class="network-canvas"></div>
        </div>
      </div>

      <!-- 右侧：模型历史和客户端列表 -->
      <div class="right-panel">
        <!-- 模型版本历史 -->
        <div class="content-card">
          <div class="card-header">
            <h2 class="card-title">模型版本历史</h2>
          </div>
          <div class="card-body">
            <el-timeline v-if="modelHistory.length > 0">
              <el-timeline-item
                v-for="version in modelHistory"
                :key="version.version_id"
                :timestamp="formatTime(version.created_at)"
              >
                <div class="version-item">
                  <div class="version-header">
                    <span class="version-tag">{{ version.version }}</span>
                    <span class="clients-badge">{{ version.clients_count }} 客户端</span>
                  </div>
                  <div class="version-id">ID: {{ version.version_id }}</div>
                </div>
              </el-timeline-item>
            </el-timeline>
            <el-empty v-else description="暂无模型历史"></el-empty>
          </div>
        </div>

        <!-- 客户端列表 -->
        <div class="content-card">
          <div class="card-header">
            <h2 class="card-title">客户端列表</h2>
          </div>
          <div class="card-body">
            <div class="client-list">
              <div
                v-for="client in clients"
                :key="client.client_id"
                class="client-item"
              >
                <div class="client-header">
                  <div class="client-name">{{ client.info?.name || client.client_id }}</div>
                  <el-tag
                    :type="client.upload_count > 0 ? 'success' : 'info'"
                    size="small"
                  >
                    {{ client.upload_count > 0 ? '活跃' : '待激活' }}
                  </el-tag>
                </div>
                <div class="client-stats">
                  <span class="stat-item">
                    <span class="stat-label">上传次数:</span>
                    <span class="stat-value">{{ client.upload_count }}</span>
                  </span>
                  <span class="stat-item" v-if="client.last_upload">
                    <span class="stat-label">最后上传:</span>
                    <span class="stat-value">{{ formatTime(client.last_upload) }}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- RAG优化面板 -->
    <div class="content-card rag-optimization-card">
      <div class="card-header">
        <h2 class="card-title">🎯 RAG联邦优化</h2>
        <div class="header-actions">
          <el-button size="small" @click="analyzeRAGPatterns">
            <span class="icon">📊</span> 分析模式
          </el-button>
          <el-select
            v-model="ragOptimizationStrategy"
            size="small"
            style="width: 150px; margin-left: 10px"
          >
            <el-option label="平衡策略" value="balanced"></el-option>
            <el-option label="精确率优先" value="precision"></el-option>
            <el-option label="召回率优先" value="recall"></el-option>
            <el-option label="速度优先" value="speed"></el-option>
          </el-select>
          <el-button
            type="primary"
            size="small"
            @click="optimizeRAGParams"
            style="margin-left: 10px"
          >
            <span class="icon">⚡</span> 优化参数
          </el-button>
        </div>
      </div>
      <div class="card-body">
        <div v-if="ragAnalysis" class="rag-analysis">
          <div class="analysis-grid">
            <div class="analysis-item">
              <div class="analysis-label">总查询数</div>
              <div class="analysis-value">{{ ragAnalysis.total_queries }}</div>
            </div>
            <div class="analysis-item">
              <div class="analysis-label">平均检索时间</div>
              <div class="analysis-value">{{ ragAnalysis.avg_retrieval_time?.toFixed(2) }}s</div>
            </div>
            <div class="analysis-item">
              <div class="analysis-label">平均成功率</div>
              <div class="analysis-value">{{ (ragAnalysis.avg_success_rate * 100).toFixed(1) }}%</div>
            </div>
            <div class="analysis-item">
              <div class="analysis-label">最优Top-K</div>
              <div class="analysis-value">{{ ragAnalysis.top_k_distribution?.median }}</div>
            </div>
          </div>

          <!-- 优化建议 -->
          <div v-if="ragAnalysis.insights && ragAnalysis.insights.length > 0" class="insights">
            <h3 class="insights-title">💡 优化建议</h3>
            <ul class="insights-list">
              <li v-for="(insight, index) in ragAnalysis.insights" :key="index">
                {{ insight }}
              </li>
            </ul>
          </div>
        </div>
        <el-empty v-else description="点击“分析模式”开始RAG优化"></el-empty>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

// 统计数据
const statistics = ref({
  totalClients: 0,
  activeClients: 0,
  modelVersion: '-',
  trainingRounds: 0
})

// 模型历史
const modelHistory = ref<any[]>([])

// 客户端列表
const clients = ref<any[]>([])

// RAG优化
const ragOptimizationStrategy = ref('balanced')
const ragAnalysis = ref<any>(null)

// 网络画布
const networkCanvas = ref<HTMLElement | null>(null)

// 加载数据
const loadData = async () => {
  try {
    // 加载客户端统计
    const clientsRes = await axios.get('/ai/global-model/clients')
    if (clientsRes.data.success) {
      const stats = clientsRes.data.statistics
      statistics.value.totalClients = stats.total_clients
      statistics.value.activeClients = stats.active_clients
      clients.value = stats.clients || []
    }

    // 加载模型历史
    const historyRes = await axios.get('/ai/global-model/history')
    if (historyRes.data.success) {
      modelHistory.value = historyRes.data.history || []
      if (modelHistory.value.length > 0) {
        statistics.value.modelVersion = modelHistory.value[modelHistory.value.length - 1].version
        statistics.value.trainingRounds = modelHistory.value.length
      }
    }
  } catch (error: any) {
    console.error('加载数据失败:', error)
    ElMessage.error('加载数据失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 刷新网络
const refreshNetwork = () => {
  loadData()
  renderNetwork()
  ElMessage.success('网络已刷新')
}

// 渲染网络拓扑
const renderNetwork = () => {
  if (!networkCanvas.value) return

  // 简化实现：使用CSS绘制网络拓扑
  // 实际应该使用D3.js或Three.js
  const canvas = networkCanvas.value
  canvas.innerHTML = ''

  // 创建中心节点（云端服务器）
  const centerNode = document.createElement('div')
  centerNode.className = 'network-node center-node'
  centerNode.innerHTML = '<div class="node-label">云端服务器</div>'
  canvas.appendChild(centerNode)

  // 创建客户端节点
  clients.value.forEach((client, index) => {
    const angle = (index / clients.value.length) * 2 * Math.PI
    const radius = 150

    const clientNode = document.createElement('div')
    clientNode.className = `network-node client-node ${client.upload_count > 0 ? 'active' : ''}`
    clientNode.style.left = `calc(50% + ${radius * Math.cos(angle)}px)`
    clientNode.style.top = `calc(50% + ${radius * Math.sin(angle)}px)`
    clientNode.innerHTML = `<div class="node-label">${client.info?.name || client.client_id}</div>`

    // 创建连接线
    const line = document.createElement('div')
    line.className = 'network-line'
    line.style.width = `${radius}px`
    line.style.left = '50%'
    line.style.top = '50%'
    line.style.transform = `rotate(${angle}rad)`

    canvas.appendChild(line)
    canvas.appendChild(clientNode)
  })
}

// 分析RAG模式
const analyzeRAGPatterns = async () => {
  try {
    const res = await axios.get('/ai/federated-rag/analyze-patterns')
    if (res.data.success) {
      ragAnalysis.value = res.data.analysis
      ElMessage.success('RAG模式分析完成')
    }
  } catch (error: any) {
    console.error('分析失败:', error)
    ElMessage.error('分析失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 优化RAG参数
const optimizeRAGParams = async () => {
  try {
    const res = await axios.post('/ai/federated-rag/optimize-params', {
      strategy: ragOptimizationStrategy.value
    })
    if (res.data.success) {
      ElMessage.success('RAG参数优化完成')
      // 更新分析数据
      ragAnalysis.value = res.data.analysis
    }
  } catch (error: any) {
    console.error('优化失败:', error)
    ElMessage.error('优化失败: ' + (error.response?.data?.detail || error.message))
  }
}

// 格式化时间
const formatTime = (time: string) => {
  if (!time) return '-'
  const date = new Date(time)
  return date.toLocaleString('zh-CN')
}

// 初始化
onMounted(() => {
  loadData()
  renderNetwork()
})
</script>

<style scoped>
.federated-learning-view {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
}

/* 页面标题 */
.page-header {
  margin-bottom: 24px;
}

.header-content {
  text-align: center;
}

.page-title {
  font-size: 32px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0 0 8px 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}

.page-title .icon {
  font-size: 36px;
}

.page-subtitle {
  font-size: 16px;
  color: #666;
  margin: 0;
}

/* 统计卡片 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  transition: all 0.3s ease;
}

.stat-card:hover {
  border-color: #9333ea;
  box-shadow: 0 2px 8px rgba(147, 51, 234, 0.1);
}

.stat-icon {
  font-size: 40px;
  width: 60px;
  height: 60px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f5f5;
  border-radius: 8px;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 28px;
  font-weight: 600;
  color: #1a1a1a;
  margin-bottom: 4px;
}

.stat-label {
  font-size: 14px;
  color: #666;
}

/* 内容网格 */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 24px;
  margin-bottom: 24px;
}

.right-panel {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 卡片 */
.content-card {
  background: white;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  overflow: hidden;
}

.network-card {
  min-height: 500px;
}

.card-header {
  padding: 16px 20px;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
  color: #1a1a1a;
  margin: 0;
}

.card-body {
  padding: 20px;
}

/* 网络可视化 */
.network-canvas {
  position: relative;
  width: 100%;
  height: 440px;
  background: #fafafa;
  border-radius: 4px;
}

.network-node {
  position: absolute;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transform: translate(-50%, -50%);
  transition: all 0.3s ease;
}

.center-node {
  background: linear-gradient(135deg, #9333ea 0%, #7c3aed 100%);
  color: white;
  font-weight: 600;
  box-shadow: 0 4px 12px rgba(147, 51, 234, 0.3);
  left: 50%;
  top: 50%;
}

.client-node {
  background: white;
  border: 2px solid #e8e8e8;
  color: #666;
  font-size: 12px;
}

.client-node.active {
  border-color: #22c55e;
  box-shadow: 0 2px 8px rgba(34, 197, 94, 0.2);
}

.node-label {
  text-align: center;
  padding: 0 8px;
  line-height: 1.2;
}

.network-line {
  position: absolute;
  height: 2px;
  background: linear-gradient(to right, #9333ea, transparent);
  transform-origin: left center;
}

/* 版本历史 */
.version-item {
  padding: 4px 0;
}

.version-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.version-tag {
  background: #9333ea;
  color: white;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}

.clients-badge {
  background: #f5f5f5;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 12px;
  color: #666;
}

.version-id {
  font-size: 12px;
  color: #999;
  font-family: monospace;
}

/* 客户端列表 */
.client-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.client-item {
  padding: 12px;
  background: #fafafa;
  border-radius: 4px;
  border: 1px solid #e8e8e8;
  transition: all 0.3s ease;
}

.client-item:hover {
  border-color: #9333ea;
  background: white;
}

.client-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.client-name {
  font-weight: 600;
  color: #1a1a1a;
}

.client-stats {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #666;
}

.stat-item {
  display: flex;
  gap: 4px;
}

.stat-label {
  color: #999;
}

/* RAG优化 */
.rag-optimization-card {
  margin-top: 24px;
}

.header-actions {
  display: flex;
  align-items: center;
}

.rag-analysis {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
}

.analysis-item {
  padding: 16px;
  background: #fafafa;
  border-radius: 4px;
  text-align: center;
}

.analysis-label {
  font-size: 12px;
  color: #666;
  margin-bottom: 8px;
}

.analysis-value {
  font-size: 24px;
  font-weight: 600;
  color: #9333ea;
}

.insights {
  padding: 16px;
  background: #f0fdf4;
  border: 1px solid #86efac;
  border-radius: 4px;
}

.insights-title {
  font-size: 14px;
  font-weight: 600;
  color: #166534;
  margin: 0 0 12px 0;
}

.insights-list {
  margin: 0;
  padding-left: 20px;
}

.insights-list li {
  color: #166534;
  font-size: 14px;
  line-height: 1.6;
  margin-bottom: 8px;
}

.insights-list li:last-child {
  margin-bottom: 0;
}

/* 响应式 */
@media (max-width: 1200px) {
  .content-grid {
    grid-template-columns: 1fr;
  }

  .right-panel {
    flex-direction: row;
  }
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }

  .right-panel {
    flex-direction: column;
  }

  .page-title {
    font-size: 24px;
  }
}
</style>

