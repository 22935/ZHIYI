<template>
  <div class="federated-learning-view">
    <div class="ambient-layer">
      <div class="ambient-orb orb-1"></div>
      <div class="ambient-orb orb-2"></div>
      <div class="ambient-orb orb-3"></div>
      <div class="grid-pattern"></div>
    </div>

    <div class="view-container">
      <header class="view-header">
        <div class="header-left">
          <div class="brand-icon">
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
              <circle cx="18" cy="18" r="16" stroke="#6366f1" stroke-width="1.5" />
              <circle cx="18" cy="18" r="8" fill="#6366f1" opacity="0.2" />
              <circle cx="18" cy="18" r="4" fill="#6366f1" />
              <circle cx="10" cy="10" r="2.5" fill="#22d3ee" />
              <circle cx="26" cy="10" r="2.5" fill="#22d3ee" />
              <circle cx="10" cy="26" r="2.5" fill="#22d3ee" />
              <circle cx="26" cy="26" r="2.5" fill="#22d3ee" />
              <line x1="18" y1="18" x2="10" y2="10" stroke="#6366f1" stroke-width="0.8" opacity="0.4" />
              <line x1="18" y1="18" x2="26" y2="10" stroke="#6366f1" stroke-width="0.8" opacity="0.4" />
              <line x1="18" y1="18" x2="10" y2="26" stroke="#6366f1" stroke-width="0.8" opacity="0.4" />
              <line x1="18" y1="18" x2="26" y2="26" stroke="#6366f1" stroke-width="0.8" opacity="0.4" />
            </svg>
          </div>
          <div class="brand-text">
            <h1>联邦学习系统</h1>
            <p>Federated Learning · 分布式智能协作平台</p>
          </div>
        </div>
        <div class="header-right">
          <div class="system-status-bar">
            <span class="status-indicator" :class="systemStatus">
              <span class="indicator-dot"></span>
              {{ systemStatusText }}
            </span>
            <span class="round-badge">Round {{ currentRound }}</span>
          </div>
          <div class="header-actions">
            <button class="action-btn" @click="startDemo" :disabled="demoRunning">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <polygon points="3,1 12,7 3,13" fill="currentColor" />
              </svg>
              演示
            </button>
            <button class="action-btn" @click="resetSystem">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 7a5 5 0 0 1 9-3M12 7a5 5 0 0 1-9 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
                <path d="M11 1v3h-3M3 13v-3h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
              重置
            </button>
          </div>
        </div>
      </header>

      <div class="stats-row">
        <div v-for="stat in systemStats" :key="stat.label" class="stat-card">
          <div class="stat-icon-wrap" :style="{ background: stat.bgColor }">
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" v-html="stat.svgPath"></svg>
          </div>
          <div class="stat-body">
            <span class="stat-value">{{ stat.value }}</span>
            <span class="stat-label">{{ stat.label }}</span>
          </div>
          <div class="stat-trend" :class="stat.trend > 0 ? 'up' : 'down'" v-if="stat.trend">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path v-if="stat.trend > 0" d="M6 2L10 7H2L6 2Z" fill="currentColor" />
              <path v-else d="M6 10L2 5H10L6 10Z" fill="currentColor" />
            </svg>
            {{ Math.abs(stat.trend) }}%
          </div>
        </div>
      </div>

      <div class="viz-row">
        <div class="panel-card topology-panel">
          <div class="panel-card-header">
            <div class="panel-title-group">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7" stroke="#6366f1" stroke-width="1.2" />
                <circle cx="9" cy="9" r="3" fill="#6366f1" opacity="0.3" />
                <circle cx="9" cy="9" r="1.5" fill="#6366f1" />
                <circle cx="5" cy="5" r="1.5" fill="#22d3ee" />
                <circle cx="13" cy="5" r="1.5" fill="#22d3ee" />
                <circle cx="5" cy="13" r="1.5" fill="#22d3ee" />
                <circle cx="13" cy="13" r="1.5" fill="#22d3ee" />
              </svg>
              <h2>联邦网络拓扑</h2>
            </div>
            <div class="panel-actions">
              <button class="icon-btn" @click="refreshNetwork" title="刷新">
                <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                  <path d="M2 7a5 5 0 0 1 9-3M12 7a5 5 0 0 1-9 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
                  <path d="M11 1v3h-3M3 13v-3h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
              </button>
            </div>
          </div>
          <FederatedTopologyGraph
            :clients="topologyClients"
            :global-version="globalVersion"
            :aggregating="aggregating"
          />
        </div>

        <div class="panel-card training-panel">
          <div class="panel-card-header">
            <div class="panel-title-group">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M2 14L6 8L10 11L16 3" stroke="#22d3ee" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
                <circle cx="16" cy="3" r="2" fill="#22d3ee" opacity="0.3" />
              </svg>
              <h2>训练曲线</h2>
            </div>
            <div class="training-controls">
              <button class="ctrl-btn" :class="{ active: trainingRunning }" @click="toggleTraining">
                {{ trainingRunning ? '⏸ 暂停' : '▶ 继续' }}
              </button>
              <button class="ctrl-btn" @click="resetTraining">↺ 重置</button>
            </div>
          </div>
          <TrainingCurveChart
            :accuracy-data="accuracyHistory"
            :loss-data="lossHistory"
            :rounds="roundHistory"
          />
          <div class="training-metrics-row">
            <div class="mini-metric">
              <span class="mini-metric-label">准确率</span>
              <span class="mini-metric-value cyan">{{ currentAccuracy }}%</span>
            </div>
            <div class="mini-metric">
              <span class="mini-metric-label">损失值</span>
              <span class="mini-metric-value pink">{{ currentLoss }}</span>
            </div>
            <div class="mini-metric">
              <span class="mini-metric-label">训练耗时</span>
              <span class="mini-metric-value purple">{{ trainingTime }}</span>
            </div>
            <div class="mini-metric">
              <span class="mini-metric-label">收敛速度</span>
              <span class="mini-metric-value green">{{ convergenceSpeed }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="detail-row">
        <div class="panel-card aggregation-panel">
          <div class="panel-card-header">
            <div class="panel-title-group">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="4" r="2" fill="#6366f1" />
                <circle cx="4" cy="13" r="2" fill="#22d3ee" />
                <circle cx="14" cy="13" r="2" fill="#a78bfa" />
                <line x1="9" y1="6" x2="4" y2="11" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
                <line x1="9" y1="6" x2="14" y2="11" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
              </svg>
              <h2>模型聚合</h2>
            </div>
          </div>
          <ModelAggregationCard
            :clients="aggClients"
            :aggregating="aggregating"
            :min-clients="3"
            @aggregate="handleAggregate"
            @refresh="fetchAggregationStatus"
          />
        </div>

        <div class="panel-card privacy-panel">
          <div class="panel-card-header">
            <div class="panel-title-group">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <rect x="4" y="8" width="10" height="7" rx="1.5" stroke="#34d399" stroke-width="1.2" />
                <path d="M6 8V6a3 3 0 0 1 6 0v2" stroke="#34d399" stroke-width="1.2" stroke-linecap="round" />
                <circle cx="9" cy="11.5" r="1" fill="#34d399" />
              </svg>
              <h2>隐私保护</h2>
            </div>
          </div>
          <div class="privacy-content">
            <div class="privacy-visual">
              <svg width="100%" height="80" viewBox="0 0 280 80" class="privacy-svg">
                <defs>
                  <linearGradient id="privGrad" x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stop-color="#6366f1" stop-opacity="0.2" />
                    <stop offset="50%" stop-color="#22d3ee" stop-opacity="0.1" />
                    <stop offset="100%" stop-color="#34d399" stop-opacity="0.2" />
                  </linearGradient>
                </defs>
                <rect x="0" y="0" width="280" height="80" rx="8" fill="url(#privGrad)" />
                <g transform="translate(30, 20)">
                  <rect x="0" y="0" width="40" height="40" rx="4" fill="#6366f1" opacity="0.15" stroke="#6366f1" stroke-width="0.5" />
                  <text x="20" y="24" text-anchor="middle" fill="#6366f1" font-size="8">∇x</text>
                </g>
                <g transform="translate(90, 20)">
                  <rect x="0" y="0" width="40" height="40" rx="4" fill="#22d3ee" opacity="0.15" stroke="#22d3ee" stroke-width="0.5" />
                  <text x="20" y="24" text-anchor="middle" fill="#22d3ee" font-size="8">ε-δ</text>
                </g>
                <g transform="translate(150, 20)">
                  <rect x="0" y="0" width="40" height="40" rx="4" fill="#a78bfa" opacity="0.15" stroke="#a78bfa" stroke-width="0.5" />
                  <text x="20" y="24" text-anchor="middle" fill="#a78bfa" font-size="8">E[·]</text>
                </g>
                <g transform="translate(210, 20)">
                  <rect x="0" y="0" width="40" height="40" rx="4" fill="#34d399" opacity="0.15" stroke="#34d399" stroke-width="0.5" />
                  <text x="20" y="24" text-anchor="middle" fill="#34d399" font-size="8">||g||</text>
                </g>
                <line x1="70" y1="40" x2="90" y2="40" stroke="#64748b" stroke-width="0.8" marker-end="url(#arrowhead)" />
                <line x1="130" y1="40" x2="150" y2="40" stroke="#64748b" stroke-width="0.8" />
                <line x1="190" y1="40" x2="210" y2="40" stroke="#64748b" stroke-width="0.8" />
              </svg>
            </div>
            <div class="privacy-items">
              <div class="privacy-item" v-for="item in privacyMechanisms" :key="item.label">
                <span class="privacy-dot" :class="{ active: item.enabled }"></span>
                <span class="privacy-label">{{ item.label }}</span>
                <span class="privacy-status" :class="{ on: item.enabled }">{{ item.enabled ? '已启用' : '未启用' }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-card models-panel">
          <div class="panel-card-header">
            <div class="panel-title-group">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path d="M9 2L16 6v6l-7 4-7-4V6l7-4z" stroke="#6366f1" stroke-width="1.2" />
                <path d="M9 2v8m0 0l7-4m-7 4l-7-4m7 4v8" stroke="#6366f1" stroke-width="0.6" opacity="0.4" />
              </svg>
              <h2>模型管理</h2>
            </div>
          </div>
          <div class="models-list">
            <div v-for="model in models" :key="model.id" class="model-item" :class="model.status">
              <div class="model-head">
                <div class="model-icon-box" :style="{ borderColor: model.color }">
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M8 1L14 4.5v7L8 15 2 11.5v-7L8 1z" :stroke="model.color" stroke-width="1" />
                  </svg>
                </div>
                <div class="model-info">
                  <span class="model-name">{{ model.name }}</span>
                  <span class="model-version">v{{ model.version }}</span>
                </div>
                <span class="model-badge" :class="model.status">{{ model.statusText }}</span>
              </div>
              <div class="model-perf">
                <div class="perf-row">
                  <span class="perf-label">准确率</span>
                  <div class="perf-bar"><div class="perf-fill" :style="{ width: model.accuracy + '%', background: model.color }"></div></div>
                  <span class="perf-val">{{ model.accuracy }}%</span>
                </div>
                <div class="perf-row">
                  <span class="perf-label">效率</span>
                  <div class="perf-bar"><div class="perf-fill" :style="{ width: model.efficiency + '%', background: model.color, opacity: 0.6 }"></div></div>
                  <span class="perf-val">{{ model.efficiency }}%</span>
                </div>
              </div>
              <div class="model-btns">
                <button class="model-btn" @click="evaluateModel(model)">评估</button>
                <button class="model-btn primary" @click="optimizeModel(model)">优化</button>
              </div>
            </div>
          </div>
        </div>

        <div class="panel-card version-panel">
          <div class="panel-card-header">
            <div class="panel-title-group">
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <circle cx="9" cy="9" r="7" stroke="#6366f1" stroke-width="1.2" />
                <path d="M9 5v4l2.5 1.5" stroke="#6366f1" stroke-width="1" stroke-linecap="round" />
              </svg>
              <h2>版本历史</h2>
            </div>
          </div>
          <div class="version-list">
            <div v-for="ver in versionHistory" :key="ver.version" class="version-item" :class="{ latest: ver.isLatest }">
              <div class="version-dot"></div>
              <div class="version-body">
                <div class="version-top">
                  <span class="version-tag">v{{ ver.version }}</span>
                  <span v-if="ver.isLatest" class="latest-badge">最新</span>
                </div>
                <div class="version-meta">
                  <span>准确率 {{ ver.accuracy }}%</span>
                  <span>·</span>
                  <span>{{ ver.clients }} 节点</span>
                  <span>·</span>
                  <span>{{ ver.time }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="demoRunning" class="demo-overlay">
        <div class="demo-card">
          <div class="demo-card-header">
            <h3>联邦学习交互演示</h3>
            <button class="close-btn" @click="stopDemo">✕</button>
          </div>
          <div class="demo-steps">
            <div class="demo-step" v-for="(step, idx) in demoSteps" :key="idx">
              <div class="step-num">{{ idx + 1 }}</div>
              <div class="step-body">
                <span class="step-text">{{ step.label }}</span>
                <div class="step-progress">
                  <div class="step-fill" :style="{ width: step.progress + '%' }"></div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import FederatedTopologyGraph from '@/components/federated/FederatedTopologyGraph.vue'
import TrainingCurveChart from '@/components/federated/TrainingCurveChart.vue'
import ModelAggregationCard from '@/components/federated/ModelAggregationCard.vue'
import { federatedModelApi } from '@/services/api/federatedModel'

const demoRunning = ref(false)
const trainingRunning = ref(true)
const aggregating = ref(false)
const globalVersion = ref('3.2')
const currentRound = ref(32)
const trainingTime = ref('12m 34s')
const convergenceSpeed = ref('0.82/round')

const systemStats = ref([
  {
    label: '活跃节点',
    value: '5',
    trend: 25,
    bgColor: 'rgba(99, 102, 241, 0.1)',
    svgPath: '<circle cx="10" cy="10" r="7" stroke="#6366f1" stroke-width="1.2"/><circle cx="10" cy="10" r="3" fill="#6366f1" opacity="0.3"/><circle cx="10" cy="10" r="1.5" fill="#6366f1"/>'
  },
  {
    label: '模型版本',
    value: '8',
    trend: 12,
    bgColor: 'rgba(34, 211, 238, 0.1)',
    svgPath: '<path d="M10 2L18 6v8l-8 4-8-4V6l8-4z" stroke="#22d3ee" stroke-width="1.2"/>'
  },
  {
    label: '训练轮次',
    value: '32',
    trend: 8,
    bgColor: 'rgba(167, 139, 250, 0.1)',
    svgPath: '<circle cx="10" cy="10" r="7" stroke="#a78bfa" stroke-width="1.2"/><path d="M10 6v4l2.5 1.5" stroke="#a78bfa" stroke-width="1" stroke-linecap="round"/>'
  },
  {
    label: '全局准确率',
    value: '93.2%',
    trend: 3,
    bgColor: 'rgba(52, 211, 153, 0.1)',
    svgPath: '<path d="M3 14L7 8L11 11L17 3" stroke="#34d399" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
  }
])

const topologyClients = ref([
  { id: 'c1', label: '律师节点', active: true, accuracy: 92.5, dataSize: 245 },
  { id: 'c2', label: '教师节点', active: true, accuracy: 88.7, dataSize: 187 },
  { id: 'c3', label: '程序员节点', active: true, accuracy: 91.3, dataSize: 312 },
  { id: 'c4', label: '作家节点', active: true, accuracy: 89.1, dataSize: 156 },
  { id: 'c5', label: '风控节点', active: false, accuracy: 85.2, dataSize: 0 },
  { id: 'c6', label: 'NLP节点', active: true, accuracy: 90.4, dataSize: 278 }
])

const accuracyHistory = ref([72.3, 78.5, 83.1, 86.4, 88.9, 90.2, 91.5, 92.1, 92.8, 93.2])
const lossHistory = ref([0.68, 0.55, 0.44, 0.36, 0.29, 0.24, 0.20, 0.17, 0.15, 0.13])
const roundHistory = ref([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

const aggClients = ref([
  { id: 'c1', label: '律师节点', weight: 0.25, uploaded: true },
  { id: 'c2', label: '教师节点', weight: 0.20, uploaded: true },
  { id: 'c3', label: '程序员节点', weight: 0.25, uploaded: true },
  { id: 'c4', label: '作家节点', weight: 0.15, uploaded: true },
  { id: 'c5', label: '风控节点', weight: 0.15, uploaded: false }
])

const privacyMechanisms = ref([
  { label: '差分隐私 (DP-SGD)', enabled: true },
  { label: '同态加密 (HE)', enabled: true },
  { label: '安全聚合 (SecAgg)', enabled: true },
  { label: '梯度裁剪 (Clip)', enabled: true },
  { label: '噪声注入 (Noise)', enabled: false }
])

const versionHistory = ref([
  { version: '3.2', accuracy: 93.2, clients: 6, time: '刚刚', isLatest: true },
  { version: '3.1', accuracy: 92.1, clients: 5, time: '2小时前', isLatest: false },
  { version: '3.0', accuracy: 91.5, clients: 5, time: '1天前', isLatest: false },
  { version: '2.8', accuracy: 90.2, clients: 4, time: '3天前', isLatest: false },
  { version: '2.5', accuracy: 88.9, clients: 4, time: '1周前', isLatest: false }
])

const models = ref([
  { id: 'lawyer', name: '法学认知增强模型', version: '3.2', status: 'online', statusText: '在线', accuracy: 98, efficiency: 92, color: '#3b82f6' },
  { id: 'teacher', name: '教育逻辑协同模型', version: '2.8', status: 'online', statusText: '在线', accuracy: 94, efficiency: 88, color: '#10b981' },
  { id: 'programmer', name: '工程代码优化模型', version: '4.1', status: 'training', statusText: '训练中', accuracy: 91, efficiency: 98, color: '#8b5cf6' },
  { id: 'writer', name: '创意写作增强模型', version: '2.3', status: 'ready', statusText: '就绪', accuracy: 89, efficiency: 85, color: '#f59e0b' }
])

const demoSteps = ref([
  { label: '模拟客户端连接和数据上传', progress: 0 },
  { label: '本地模型训练和参数更新', progress: 0 },
  { label: '全局模型聚合和版本发布', progress: 0 }
])

const systemStatus = computed(() => aggregating.value ? 'aggregating' : trainingRunning.value ? 'training' : 'paused')
const systemStatusText = computed(() => aggregating.value ? '聚合中' : trainingRunning.value ? '训练中' : '已暂停')
const currentAccuracy = computed(() => accuracyHistory.value.length ? accuracyHistory.value[accuracyHistory.value.length - 1].toFixed(1) : '--')
const currentLoss = computed(() => lossHistory.value.length ? lossHistory.value[lossHistory.value.length - 1].toFixed(3) : '--')

function toggleTraining() {
  trainingRunning.value = !trainingRunning.value
}

function resetTraining() {
  accuracyHistory.value = [72.3, 78.5, 83.1, 86.4, 88.9, 90.2, 91.5, 92.1, 92.8, 93.2]
  lossHistory.value = [0.68, 0.55, 0.44, 0.36, 0.29, 0.24, 0.20, 0.17, 0.15, 0.13]
  roundHistory.value = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  trainingRunning.value = true
}

function refreshNetwork() {
  ElMessage.success('网络拓扑已刷新')
}

async function handleAggregate() {
  aggregating.value = true
  ElMessage.info('开始联邦聚合...')
  try {
    const result = await federatedModelApi.optimizeModel('advanced', 'federated', 'quality', 1)
    if (result.success) {
      ElMessage.success('联邦聚合完成！模型已更新')
      globalVersion.value = (parseFloat(globalVersion.value) + 0.1).toFixed(1)
      currentRound.value++
      versionHistory.value.unshift({
        version: globalVersion.value,
        accuracy: parseFloat(currentAccuracy.value),
        clients: topologyClients.value.filter(c => c.active).length,
        time: '刚刚',
        isLatest: true
      })
      if (versionHistory.value.length > 1) versionHistory.value[1].isLatest = false
    }
  } catch {
    ElMessage.warning('聚合服务暂不可用，使用本地模拟')
    setTimeout(() => {
      globalVersion.value = (parseFloat(globalVersion.value) + 0.1).toFixed(1)
      currentRound.value++
      ElMessage.success('本地模拟聚合完成')
    }, 2000)
  } finally {
    aggregating.value = false
  }
}

async function fetchAggregationStatus() {
  try {
    const result = await federatedModelApi.getOptimizationStatus()
    if (result.success) ElMessage.success('聚合状态已刷新')
  } catch {
    ElMessage.info('使用本地缓存数据')
  }
}

async function evaluateModel(model: any) {
  ElMessage.info(`正在评估 ${model.name}...`)
  try {
    const result = await federatedModelApi.evaluateModel(model.id)
    if (result.success) ElMessage.success(`${model.name} 评估完成`)
  } catch {
    ElMessage.warning('评估服务暂不可用')
  }
}

async function optimizeModel(model: any) {
  ElMessage.info(`正在优化 ${model.name}...`)
  try {
    const result = await federatedModelApi.optimizeModel(model.id, 'federated', 'quality', 5)
    if (result.success) ElMessage.success(`${model.name} 优化完成`)
  } catch {
    ElMessage.warning('优化服务暂不可用')
  }
}

function startDemo() {
  demoRunning.value = true
  demoSteps.value = [
    { label: '模拟客户端连接和数据上传', progress: 0 },
    { label: '本地模型训练和参数更新', progress: 0 },
    { label: '全局模型聚合和版本发布', progress: 0 }
  ]
  const interval = setInterval(() => {
    const steps = demoSteps.value
    if (steps[0].progress < 100) {
      steps[0].progress += 10
    } else if (steps[1].progress < 100) {
      steps[1].progress += 10
    } else if (steps[2].progress < 100) {
      steps[2].progress += 10
    } else {
      clearInterval(interval)
      ElMessage.success('演示完成！')
    }
  }, 800)
}

function stopDemo() {
  demoRunning.value = false
  ElMessage.info('演示已停止')
}

async function resetSystem() {
  try {
    await ElMessageBox.confirm('确定要重置系统吗？', '确认重置', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    })
    stopDemo()
    resetTraining()
    globalVersion.value = '3.2'
    currentRound.value = 32
    ElMessage.success('系统已重置')
  } catch {}
}

onMounted(async () => {
  try {
    const result = await federatedModelApi.listModels()
    if (result.success && result.data) {
      const remoteModels: any[] = []
      Object.entries(result.data || {}).forEach(([, groupModels]) => {
        Object.entries(groupModels || {}).forEach(([modelKey, model]: [string, any]) => {
          remoteModels.push({
            id: modelKey,
            name: model.name || modelKey,
            version: model.version || '1.0.0',
            status: model.status === 'active' ? 'online' : 'ready',
            statusText: model.status === 'active' ? '在线' : '就绪',
            accuracy: Math.round((model.performance?.accuracy || 0.85) * 100),
            efficiency: Math.round((model.performance?.efficiency || 0.80) * 100),
            color: '#6366f1'
          })
        })
      })
      if (remoteModels.length > 0) models.value = remoteModels
    }
  } catch {}
})
</script>

<style scoped>
.federated-learning-view {
  min-height: 100vh;
  background: #f8fafc;
  position: relative;
  overflow-x: hidden;
}

.ambient-layer {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}

.ambient-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.4;
}

.orb-1 {
  width: 400px;
  height: 400px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.15), transparent);
  top: -100px;
  left: -100px;
  animation: orbFloat 20s ease-in-out infinite;
}

.orb-2 {
  width: 300px;
  height: 300px;
  background: radial-gradient(circle, rgba(34, 211, 238, 0.12), transparent);
  bottom: -50px;
  right: -50px;
  animation: orbFloat 25s ease-in-out infinite reverse;
}

.orb-3 {
  width: 200px;
  height: 200px;
  background: radial-gradient(circle, rgba(167, 139, 250, 0.1), transparent);
  top: 40%;
  left: 50%;
  animation: orbFloat 18s ease-in-out infinite 5s;
}

@keyframes orbFloat {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(30px, -20px) scale(1.05); }
  66% { transform: translate(-20px, 30px) scale(0.95); }
}

.grid-pattern {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(99, 102, 241, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(99, 102, 241, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
}

.view-container {
  position: relative;
  z-index: 1;
  max-width: 1400px;
  margin: 0 auto;
  padding: 24px;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.25);
}

.brand-text h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 800;
  color: #1e1b4b;
  letter-spacing: -0.5px;
}

.brand-text p {
  margin: 0;
  font-size: 12px;
  color: #6366f1;
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.system-status-bar {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
}

.status-indicator.training {
  background: rgba(34, 211, 238, 0.1);
  color: #0891b2;
  border: 1px solid rgba(34, 211, 238, 0.2);
}

.status-indicator.aggregating {
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.status-indicator.paused {
  background: rgba(100, 116, 139, 0.08);
  color: #64748b;
  border: 1px solid rgba(100, 116, 139, 0.15);
}

.indicator-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: blink 2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.round-badge {
  padding: 5px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 600;
  background: rgba(99, 102, 241, 0.06);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.1);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
  border: 1px solid rgba(99, 102, 241, 0.15);
  background: white;
  color: #475569;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.06);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.3);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
  margin-bottom: 24px;
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: white;
  border-radius: 14px;
  border: 1px solid rgba(99, 102, 241, 0.06);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  transition: all 0.2s ease;
}

.stat-card:hover {
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.08);
  transform: translateY(-1px);
}

.stat-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-body {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.stat-value {
  font-size: 20px;
  font-weight: 800;
  color: #1e293b;
  line-height: 1;
}

.stat-label {
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.stat-trend {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 6px;
}

.stat-trend.up {
  color: #059669;
  background: rgba(16, 185, 129, 0.08);
}

.stat-trend.down {
  color: #dc2626;
  background: rgba(239, 68, 68, 0.08);
}

.viz-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  margin-bottom: 20px;
}

.detail-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  align-items: stretch;
}

.panel-card {
  background: white;
  border-radius: 14px;
  border: 1px solid rgba(99, 102, 241, 0.06);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  overflow: hidden;
  transition: box-shadow 0.2s ease;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-card:hover {
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.06);
}

.panel-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.06);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.02), rgba(34, 211, 238, 0.01));
  flex-shrink: 0;
}

.panel-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.panel-title-group h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #1e1b4b;
}

.panel-actions {
  display: flex;
  gap: 6px;
}

.icon-btn {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  border: 1px solid rgba(99, 102, 241, 0.1);
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.icon-btn:hover {
  background: rgba(99, 102, 241, 0.06);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.2);
}

.topology-panel {
  padding-bottom: 12px;
}

.topology-panel :deep(.topology-graph) {
  padding: 0 12px;
}

.training-panel {
  padding-bottom: 12px;
}

.training-panel :deep(.training-curve) {
  padding: 0 12px;
}

.training-controls {
  display: flex;
  gap: 6px;
}

.ctrl-btn {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  border: 1px solid rgba(99, 102, 241, 0.12);
  background: rgba(99, 102, 241, 0.04);
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.ctrl-btn:hover {
  background: rgba(99, 102, 241, 0.08);
  color: #475569;
}

.ctrl-btn.active {
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.25);
}

.training-metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  padding: 0 12px;
  margin-top: 10px;
}

.mini-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 4px;
  background: rgba(99, 102, 241, 0.03);
  border-radius: 8px;
  border: 1px solid rgba(99, 102, 241, 0.05);
}

.mini-metric-label {
  font-size: 10px;
  color: #94a3b8;
}

.mini-metric-value {
  font-size: 14px;
  font-weight: 700;
}

.mini-metric-value.cyan { color: #0891b2; }
.mini-metric-value.pink { color: #db2777; }
.mini-metric-value.purple { color: #7c3aed; }
.mini-metric-value.green { color: #059669; }

.aggregation-panel :deep(.aggregation-card) {
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 4px 8px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.privacy-panel .privacy-content {
  padding: 4px 8px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.privacy-visual {
  margin-bottom: 4px;
  flex-shrink: 0;
}

.privacy-svg {
  display: block;
}

.privacy-items {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  padding-top: 4px;
}

.privacy-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  padding: 4px 0;
}

.privacy-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #cbd5e1;
  flex-shrink: 0;
}

.privacy-dot.active {
  background: #34d399;
  box-shadow: 0 0 4px rgba(52, 211, 153, 0.4);
}

.privacy-label {
  flex: 1;
  color: #475569;
}

.privacy-status {
  font-size: 9px;
  color: #94a3b8;
}

.privacy-status.on {
  color: #059669;
}

.models-panel .models-list {
  padding: 4px 8px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 6px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  align-content: start;
}

.model-item {
  padding: 6px;
  background: rgba(99, 102, 241, 0.02);
  border-radius: 6px;
  border: 1px solid rgba(99, 102, 241, 0.06);
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.model-item:hover {
  border-color: rgba(99, 102, 241, 0.15);
  box-shadow: 0 1px 3px rgba(99, 102, 241, 0.05);
}

.model-head {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 4px;
}

.model-icon-box {
  width: 22px;
  height: 22px;
  border-radius: 5px;
  border: 1.5px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(99, 102, 241, 0.04);
  flex-shrink: 0;
}

.model-icon-box svg {
  width: 11px;
  height: 11px;
}

.model-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.model-name {
  font-size: 10px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-version {
  font-size: 8px;
  color: #94a3b8;
}

.model-badge {
  font-size: 8px;
  padding: 1px 5px;
  border-radius: 6px;
  font-weight: 500;
  flex-shrink: 0;
}

.model-badge.online {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.model-badge.training {
  background: rgba(139, 92, 246, 0.1);
  color: #7c3aed;
}

.model-badge.ready {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.model-perf {
  display: flex;
  flex-direction: column;
  gap: 3px;
  margin-bottom: 4px;
}

.perf-row {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 9px;
}

.perf-label {
  width: 28px;
  color: #94a3b8;
  font-size: 8px;
  flex-shrink: 0;
}

.perf-bar {
  flex: 1;
  height: 3px;
  background: #e2e8f0;
  border-radius: 2px;
  overflow: hidden;
}

.perf-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.8s ease;
}

.perf-val {
  width: 26px;
  text-align: right;
  font-weight: 600;
  color: #475569;
  font-size: 8px;
  flex-shrink: 0;
}

.model-btns {
  display: flex;
  gap: 3px;
}

.model-btn {
  flex: 1;
  padding: 3px 6px;
  border-radius: 4px;
  font-size: 9px;
  border: 1px solid rgba(99, 102, 241, 0.1);
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.model-btn:hover {
  background: rgba(99, 102, 241, 0.04);
  color: #475569;
}

.model-btn.primary {
  background: rgba(99, 102, 241, 0.06);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.15);
}

.model-btn.primary:hover {
  background: rgba(99, 102, 241, 0.12);
}

.version-panel .version-list {
  padding: 4px 8px;
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  gap: 4px;
}

.version-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 0;
  border-left: 2px solid #e2e8f0;
  padding-left: 10px;
  position: relative;
  flex-shrink: 0;
}

.version-item::before {
  content: '';
  position: absolute;
  left: -4px;
  top: 8px;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #cbd5e1;
  border: 2px solid white;
}

.version-item.latest {
  border-left-color: #6366f1;
}

.version-item.latest::before {
  background: #6366f1;
  box-shadow: 0 0 4px rgba(99, 102, 241, 0.4);
}

.version-top {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 2px;
}

.version-tag {
  font-size: 10px;
  font-weight: 700;
  color: #1e293b;
}

.version-item.latest .version-tag {
  color: #6366f1;
}

.latest-badge {
  font-size: 8px;
  padding: 1px 5px;
  border-radius: 4px;
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  font-weight: 600;
}

.version-meta {
  display: flex;
  gap: 3px;
  font-size: 9px;
  color: #94a3b8;
  flex-wrap: wrap;
}

.demo-overlay {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.demo-card {
  width: 360px;
  background: white;
  border-radius: 14px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  border: 1px solid rgba(99, 102, 241, 0.1);
  overflow: hidden;
}

.demo-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 16px;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  color: white;
}

.demo-card-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.close-btn {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
}

.demo-steps {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.demo-step {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.step-num {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  font-size: 11px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.step-body {
  flex: 1;
}

.step-text {
  font-size: 12px;
  color: #475569;
  display: block;
  margin-bottom: 6px;
}

.step-progress {
  height: 4px;
  background: #e2e8f0;
  border-radius: 2px;
  overflow: hidden;
}

.step-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #22d3ee);
  border-radius: 2px;
  transition: width 0.5s ease;
}

@media (max-width: 1200px) {
  .viz-row {
    grid-template-columns: 1fr;
  }

  .detail-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .view-header {
    flex-direction: column;
    gap: 16px;
    align-items: flex-start;
  }

  .viz-row {
    grid-template-columns: 1fr;
  }

  .detail-row {
    grid-template-columns: 1fr;
  }

  .stats-row {
    grid-template-columns: 1fr;
  }

  .training-metrics-row {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
