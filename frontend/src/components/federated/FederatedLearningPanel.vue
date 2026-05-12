<template>
  <section class="federated-panel">
    <div class="panel-header">
      <div class="header-left">
        <div class="agent-avatar">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <circle cx="14" cy="14" r="12" stroke="#6366f1" stroke-width="1.5" />
            <circle cx="14" cy="14" r="6" fill="#6366f1" opacity="0.3" />
            <circle cx="14" cy="14" r="3" fill="#6366f1" />
            <circle cx="8" cy="8" r="2" fill="#22d3ee" />
            <circle cx="20" cy="8" r="2" fill="#22d3ee" />
            <circle cx="8" cy="20" r="2" fill="#22d3ee" />
            <circle cx="20" cy="20" r="2" fill="#22d3ee" />
            <line x1="14" y1="14" x2="8" y2="8" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
            <line x1="14" y1="14" x2="20" y2="8" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
            <line x1="14" y1="14" x2="8" y2="20" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
            <line x1="14" y1="14" x2="20" y2="20" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
          </svg>
        </div>
        <div class="header-text">
          <h3>联邦学习控制台</h3>
          <span class="header-sub">Federated Learning Console</span>
        </div>
      </div>
      <div class="header-badges">
        <span class="status-pill" :class="systemStatusClass">
          <span class="pill-dot"></span>
          {{ systemStatusText }}
        </span>
        <span class="round-pill">Round {{ currentRound }}</span>
      </div>
    </div>

    <div class="panel-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <svg v-if="tab.key === 'topology'" class="tab-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.2" />
          <circle cx="7" cy="7" r="2" fill="currentColor" opacity="0.3" />
          <circle cx="4" cy="4" r="1" fill="currentColor" />
          <circle cx="10" cy="4" r="1" fill="currentColor" />
          <circle cx="4" cy="10" r="1" fill="currentColor" />
          <circle cx="10" cy="10" r="1" fill="currentColor" />
        </svg>
        <svg v-else-if="tab.key === 'training'" class="tab-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M2 11L5 7L8 9L12 3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
          <circle cx="12" cy="3" r="1.5" fill="currentColor" opacity="0.3" />
        </svg>
        <svg v-else-if="tab.key === 'aggregation'" class="tab-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
          <circle cx="7" cy="3" r="1.5" fill="currentColor" />
          <circle cx="3" cy="10" r="1.5" fill="currentColor" />
          <circle cx="11" cy="10" r="1.5" fill="currentColor" />
          <line x1="7" y1="4.5" x2="3" y2="8.5" stroke="currentColor" stroke-width="0.8" opacity="0.5" />
          <line x1="7" y1="4.5" x2="11" y2="8.5" stroke="currentColor" stroke-width="0.8" opacity="0.5" />
        </svg>
        <svg v-else-if="tab.key === 'models'" class="tab-icon" width="14" height="14" viewBox="0 0 14 14" fill="none">
          <path d="M7 1L13 4v6l-6 3-6-3V4l6-3z" stroke="currentColor" stroke-width="1.2" />
          <path d="M7 1v6m0 0l6-3m-6 3l-6-3m6 3v6" stroke="currentColor" stroke-width="0.6" opacity="0.4" />
        </svg>
        <span class="tab-label">{{ tab.label }}</span>
      </button>
    </div>

    <div class="panel-body">
      <div v-show="activeTab === 'topology'" class="tab-content">
        <FederatedTopologyGraph
          :clients="topologyClients"
          :global-version="globalVersion"
          :aggregating="aggregating"
        />
        <div class="topology-stats">
          <div class="mini-stat">
            <span class="mini-label">活跃节点</span>
            <span class="mini-value accent">{{ activeClientsCount }}/{{ topologyClients.length }}</span>
          </div>
          <div class="mini-stat">
            <span class="mini-label">数据传输</span>
            <span class="mini-value">{{ dataTransferRate }} MB/s</span>
          </div>
          <div class="mini-stat">
            <span class="mini-label">通信开销</span>
            <span class="mini-value">{{ commOverhead }}%</span>
          </div>
        </div>
      </div>

      <div v-show="activeTab === 'training'" class="tab-content">
        <div class="training-header">
          <span class="training-title">训练曲线</span>
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
        <div class="training-metrics">
          <div class="metric-card">
            <div class="metric-icon">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 14L6 8L10 11L14 2" stroke="#22d3ee" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>
            <div class="metric-info">
              <span class="metric-label">当前准确率</span>
              <span class="metric-value cyan">{{ currentAccuracy }}%</span>
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M2 2L6 8L10 5L14 14" stroke="#f472b6" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
              </svg>
            </div>
            <div class="metric-info">
              <span class="metric-label">当前损失</span>
              <span class="metric-value pink">{{ currentLoss }}</span>
            </div>
          </div>
          <div class="metric-card">
            <div class="metric-icon">
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="6" stroke="#a78bfa" stroke-width="1.5" />
                <path d="M8 4v4l3 2" stroke="#a78bfa" stroke-width="1.2" stroke-linecap="round" />
              </svg>
            </div>
            <div class="metric-info">
              <span class="metric-label">训练耗时</span>
              <span class="metric-value purple">{{ trainingTime }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-show="activeTab === 'aggregation'" class="tab-content">
        <ModelAggregationCard
          :clients="aggClients"
          :aggregating="aggregating"
          :min-clients="3"
          @aggregate="handleAggregate"
          @refresh="fetchAggregationStatus"
        />

        <div class="privacy-section">
          <div class="privacy-header">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <rect x="3" y="7" width="10" height="7" rx="1.5" stroke="#34d399" stroke-width="1.2" />
              <path d="M5 7V5a3 3 0 0 1 6 0v2" stroke="#34d399" stroke-width="1.2" stroke-linecap="round" />
              <circle cx="8" cy="10.5" r="1" fill="#34d399" />
            </svg>
            <span>隐私保护机制</span>
          </div>
          <div class="privacy-items">
            <div class="privacy-item" v-for="item in privacyMechanisms" :key="item.label">
              <span class="privacy-dot" :class="{ active: item.enabled }"></span>
              <span class="privacy-label">{{ item.label }}</span>
              <span class="privacy-status">{{ item.enabled ? '已启用' : '未启用' }}</span>
            </div>
          </div>
        </div>
      </div>

      <div v-show="activeTab === 'models'" class="tab-content models-tab">
        <div class="models-grid">
          <div v-for="model in models" :key="model.id" class="model-item" :class="model.status">
            <div class="model-head">
              <div class="model-icon-wrap">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 2L18 6v8l-8 4-8-4V6l8-4z" :stroke="model.color" stroke-width="1.2" />
                  <path d="M10 2v8m0 0l8-4m-8 4l-8-4m8 4v8" :stroke="model.color" stroke-width="0.8" opacity="0.5" />
                </svg>
              </div>
              <div class="model-info">
                <span class="model-name">{{ model.name }}</span>
                <span class="model-version">v{{ model.version }}</span>
              </div>
              <span class="model-status-badge" :class="model.status">{{ model.statusText }}</span>
            </div>
            <div class="model-perf">
              <div class="perf-row">
                <span class="perf-label">准确率</span>
                <div class="perf-bar">
                  <div class="perf-fill" :style="{ width: model.accuracy + '%', background: model.color }"></div>
                </div>
                <span class="perf-value">{{ model.accuracy }}%</span>
              </div>
              <div class="perf-row">
                <span class="perf-label">效率</span>
                <div class="perf-bar">
                  <div class="perf-fill" :style="{ width: model.efficiency + '%', background: model.color }" style="opacity: 0.6"></div>
                </div>
                <span class="perf-value">{{ model.efficiency }}%</span>
              </div>
            </div>
            <div class="model-actions">
              <button class="model-btn" @click="evaluateModel(model)">评估</button>
              <button class="model-btn primary" @click="optimizeModel(model)">优化</button>
            </div>
          </div>
        </div>

        <div class="version-timeline">
          <div class="timeline-header">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="6" stroke="#6366f1" stroke-width="1.2" />
              <path d="M8 5v3l2 1.5" stroke="#6366f1" stroke-width="1" stroke-linecap="round" />
            </svg>
            <span>版本历史</span>
          </div>
          <div class="timeline-list">
            <div v-for="ver in versionHistory" :key="ver.version" class="timeline-item" :class="{ latest: ver.isLatest }">
              <div class="timeline-dot"></div>
              <div class="timeline-content">
                <div class="timeline-version">v{{ ver.version }}</div>
                <div class="timeline-meta">
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
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import FederatedTopologyGraph from './FederatedTopologyGraph.vue'
import TrainingCurveChart from './TrainingCurveChart.vue'
import ModelAggregationCard from './ModelAggregationCard.vue'
import { federatedModelApi } from '@/services/api/federatedModel'

const activeTab = ref('topology')
const aggregating = ref(false)
const trainingRunning = ref(true)
const globalVersion = ref('3.2')
const currentRound = ref(32)
const dataTransferRate = ref('12.4')
const commOverhead = ref('8.2')

const tabs = [
  { key: 'topology', label: '网络拓扑' },
  { key: 'training', label: '训练监控' },
  { key: 'aggregation', label: '聚合与隐私' },
  { key: 'models', label: '模型与版本' }
]

const topologyClients = ref([
  { id: 'c1', label: '律师Agent', active: true, accuracy: 87.3, dataSize: 12450 },
  { id: 'c2', label: '教师Agent', active: true, accuracy: 84.6, dataSize: 8920 },
  { id: 'c3', label: '程序员Agent', active: true, accuracy: 86.1, dataSize: 15380 },
  { id: 'c4', label: '作家Agent', active: true, accuracy: 83.2, dataSize: 6740 }
])

const accuracyHistory = ref([62.1, 68.4, 73.7, 77.9, 81.2, 83.5, 85.1, 86.3, 87.0, 87.3])
const lossHistory = ref([1.24, 1.05, 0.89, 0.76, 0.64, 0.55, 0.48, 0.42, 0.38, 0.35])
const roundHistory = ref([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

const aggClients = ref([
  { id: 'c1', label: '律师Agent', weight: 0.30, uploaded: true },
  { id: 'c2', label: '教师Agent', weight: 0.22, uploaded: true },
  { id: 'c3', label: '程序员Agent', weight: 0.30, uploaded: true },
  { id: 'c4', label: '作家Agent', weight: 0.18, uploaded: true }
])

const privacyMechanisms = ref([
  { label: '差分隐私 (DP)', enabled: true },
  { label: '同态加密 (HE)', enabled: true },
  { label: '安全聚合 (SA)', enabled: true },
  { label: '梯度裁剪', enabled: true },
  { label: '噪声注入', enabled: false }
])

const versionHistory = ref([
  { version: '3.2', accuracy: 85.3, clients: 4, time: '刚刚', isLatest: true },
  { version: '3.1', accuracy: 84.1, clients: 4, time: '2小时前', isLatest: false },
  { version: '3.0', accuracy: 82.7, clients: 4, time: '1天前', isLatest: false },
  { version: '2.8', accuracy: 80.5, clients: 4, time: '3天前', isLatest: false }
])

const models = ref([
  { id: 'lawyer', name: '律师Agent模型', version: '3.2', status: 'online', statusText: '在线', accuracy: 87.3, efficiency: 82, color: '#3b82f6' },
  { id: 'teacher', name: '教师Agent模型', version: '2.8', status: 'online', statusText: '在线', accuracy: 84.6, efficiency: 79, color: '#10b981' },
  { id: 'programmer', name: '程序员Agent模型', version: '4.1', status: 'training', statusText: '训练中', accuracy: 86.1, efficiency: 85, color: '#8b5cf6' },
  { id: 'writer', name: '作家Agent模型', version: '2.3', status: 'ready', statusText: '就绪', accuracy: 83.2, efficiency: 76, color: '#f59e0b' }
])

const activeClientsCount = computed(() => topologyClients.value.filter(c => c.active).length)

const currentAccuracy = computed(() => {
  const data = accuracyHistory.value
  return data.length ? data[data.length - 1].toFixed(1) : '--'
})

const currentLoss = computed(() => {
  const data = lossHistory.value
  return data.length ? data[data.length - 1].toFixed(3) : '--'
})

const trainingTime = computed(() => '12m 34s')

const systemStatusText = computed(() => {
  if (aggregating.value) return '聚合中'
  return trainingRunning.value ? '训练中' : '已暂停'
})

const systemStatusClass = computed(() => {
  if (aggregating.value) return 'aggregating'
  return trainingRunning.value ? 'training' : 'paused'
})

function toggleTraining() {
  trainingRunning.value = !trainingRunning.value
}

function resetTraining() {
  accuracyHistory.value = [62.1, 68.4, 73.7, 77.9, 81.2, 83.5, 85.1, 86.3, 87.0, 87.3]
  lossHistory.value = [1.24, 1.05, 0.89, 0.76, 0.64, 0.55, 0.48, 0.42, 0.38, 0.35]
  roundHistory.value = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
  trainingRunning.value = true
}

async function handleAggregate() {
  aggregating.value = true
  ElMessage.info('开始联邦聚合...')
  try {
    const result = await federatedModelApi.optimizeModel('advanced', 'federated', 'quality', 1)
    if (result.success) {
      ElMessage.success('联邦聚合完成！模型已更新')
      const newVersion = parseFloat(globalVersion.value) + 0.1
      globalVersion.value = newVersion.toFixed(1)
      currentRound.value++
      versionHistory.value.unshift({
        version: globalVersion.value,
        accuracy: parseFloat(currentAccuracy.value),
        clients: activeClientsCount.value,
        time: '刚刚',
        isLatest: true
      })
      if (versionHistory.value.length > 1) {
        versionHistory.value[1].isLatest = false
      }
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
    if (result.success && result.data) {
      ElMessage.success('聚合状态已刷新')
    }
  } catch {
    ElMessage.info('使用本地缓存数据')
  }
}

async function evaluateModel(model: any) {
  ElMessage.info(`正在评估 ${model.name}...`)
  try {
    const result = await federatedModelApi.evaluateModel(model.id)
    if (result.success) {
      ElMessage.success(`${model.name} 评估完成`)
    }
  } catch {
    ElMessage.warning('评估服务暂不可用')
  }
}

async function optimizeModel(model: any) {
  ElMessage.info(`正在优化 ${model.name}...`)
  try {
    const result = await federatedModelApi.optimizeModel(model.id, 'federated', 'quality', 5)
    if (result.success) {
      ElMessage.success(`${model.name} 优化完成`)
    }
  } catch {
    ElMessage.warning('优化服务暂不可用')
  }
}

onMounted(async () => {
  try {
    const result = await federatedModelApi.listModels()
    if (result.success && result.data) {
      const remoteModels: any[] = []
      Object.entries(result.data || {}).forEach(([groupKey, groupModels]) => {
        Object.entries(groupModels || {}).forEach(([modelKey, model]) => {
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
      if (remoteModels.length > 0) {
        models.value = remoteModels
      }
    }
  } catch {
    // use default models
  }
})
</script>

<style scoped>
.federated-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.97);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(15, 23, 42, 0.08);
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(99, 102, 241, 0.08);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.03), rgba(34, 211, 238, 0.02));
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
}

.header-text h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #1e1b4b;
}

.header-sub {
  font-size: 11px;
  color: #6366f1;
  font-weight: 500;
}

.header-badges {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
}

.status-pill.training {
  background: rgba(34, 211, 238, 0.1);
  color: #0891b2;
  border: 1px solid rgba(34, 211, 238, 0.2);
}

.status-pill.aggregating {
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.2);
}

.status-pill.paused {
  background: rgba(100, 116, 139, 0.1);
  color: #64748b;
  border: 1px solid rgba(100, 116, 139, 0.2);
}

.pill-dot {
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

.round-pill {
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(99, 102, 241, 0.06);
  color: #6366f1;
  border: 1px solid rgba(99, 102, 241, 0.12);
}

.panel-tabs {
  display: flex;
  gap: 2px;
  padding: 8px 12px;
  background: rgba(99, 102, 241, 0.02);
  border-bottom: 1px solid rgba(99, 102, 241, 0.06);
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 7px 8px;
  border: none;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 500;
  color: #64748b;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-btn:hover {
  background: rgba(99, 102, 241, 0.06);
  color: #475569;
}

.tab-btn.active {
  background: rgba(99, 102, 241, 0.1);
  color: #6366f1;
  font-weight: 600;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.1);
}

.tab-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
}

.tab-content {
  animation: fadeIn 0.3s ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.topology-stats {
  display: flex;
  gap: 12px;
  margin-top: 12px;
}

.mini-stat {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px;
  background: rgba(99, 102, 241, 0.04);
  border-radius: 8px;
  border: 1px solid rgba(99, 102, 241, 0.06);
}

.mini-label {
  font-size: 10px;
  color: #94a3b8;
}

.mini-value {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.mini-value.accent {
  color: #6366f1;
}

.training-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.training-title {
  font-size: 13px;
  font-weight: 600;
  color: #1e293b;
}

.training-controls {
  display: flex;
  gap: 6px;
}

.ctrl-btn {
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 11px;
  border: 1px solid rgba(99, 102, 241, 0.15);
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
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.3);
}

.training-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  margin-top: 12px;
}

.metric-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  background: rgba(15, 23, 42, 0.03);
  border-radius: 10px;
  border: 1px solid rgba(99, 102, 241, 0.06);
}

.metric-icon {
  display: flex;
  align-items: center;
}

.metric-info {
  display: flex;
  flex-direction: column;
}

.metric-label {
  font-size: 10px;
  color: #94a3b8;
}

.metric-value {
  font-size: 14px;
  font-weight: 700;
}

.metric-value.cyan { color: #0891b2; }
.metric-value.pink { color: #db2777; }
.metric-value.purple { color: #7c3aed; }

.privacy-section {
  margin-top: 14px;
  background: rgba(15, 23, 42, 0.03);
  border-radius: 10px;
  padding: 12px;
  border: 1px solid rgba(52, 211, 153, 0.1);
}

.privacy-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 10px;
}

.privacy-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.privacy-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.privacy-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #94a3b8;
}

.privacy-dot.active {
  background: #10b981;
  box-shadow: 0 0 6px rgba(16, 185, 129, 0.4);
}

.privacy-label {
  flex: 1;
  color: #475569;
}

.privacy-status {
  font-size: 10px;
  color: #94a3b8;
}

.version-timeline {
  margin-top: 14px;
}

.timeline-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
  margin-bottom: 10px;
}

.timeline-list {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.timeline-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 8px 0;
  border-left: 2px solid #e2e8f0;
  padding-left: 14px;
  position: relative;
}

.timeline-item::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  border: 2px solid white;
}

.timeline-item.latest {
  border-left-color: #6366f1;
}

.timeline-item.latest::before {
  background: #6366f1;
  box-shadow: 0 0 6px rgba(99, 102, 241, 0.4);
}

.timeline-version {
  font-size: 12px;
  font-weight: 600;
  color: #1e293b;
}

.timeline-item.latest .timeline-version {
  color: #6366f1;
}

.timeline-meta {
  display: flex;
  gap: 4px;
  font-size: 10px;
  color: #94a3b8;
  margin-top: 2px;
}

.models-tab {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.models-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.model-item {
  padding: 10px;
  background: rgba(15, 23, 42, 0.03);
  border-radius: 10px;
  border: 1px solid rgba(99, 102, 241, 0.08);
  transition: all 0.2s ease;
}

.model-item:hover {
  border-color: rgba(99, 102, 241, 0.2);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.08);
}

.model-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.model-icon-wrap {
  display: flex;
  align-items: center;
}

.model-info {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.model-name {
  font-size: 11px;
  font-weight: 600;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-version {
  font-size: 9px;
  color: #94a3b8;
}

.model-status-badge {
  font-size: 9px;
  padding: 2px 6px;
  border-radius: 8px;
  font-weight: 500;
  flex-shrink: 0;
}

.model-status-badge.online {
  background: rgba(16, 185, 129, 0.1);
  color: #059669;
}

.model-status-badge.training {
  background: rgba(139, 92, 246, 0.1);
  color: #7c3aed;
}

.model-status-badge.ready {
  background: rgba(245, 158, 11, 0.1);
  color: #d97706;
}

.model-perf {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 8px;
}

.perf-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
}

.perf-label {
  width: 32px;
  color: #94a3b8;
  font-size: 9px;
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

.perf-value {
  width: 32px;
  text-align: right;
  font-weight: 600;
  color: #475569;
  font-size: 9px;
}

.model-actions {
  display: flex;
  gap: 6px;
}

.model-btn {
  flex: 1;
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 10px;
  border: 1px solid rgba(99, 102, 241, 0.12);
  background: transparent;
  color: #64748b;
  cursor: pointer;
  transition: all 0.2s ease;
}

.model-btn:hover {
  background: rgba(99, 102, 241, 0.06);
  color: #475569;
}

.model-btn.primary {
  background: rgba(99, 102, 241, 0.08);
  color: #6366f1;
  border-color: rgba(99, 102, 241, 0.2);
}

.model-btn.primary:hover {
  background: rgba(99, 102, 241, 0.15);
}

@media (max-width: 768px) {
  .models-grid {
    grid-template-columns: 1fr;
  }
}
</style>
