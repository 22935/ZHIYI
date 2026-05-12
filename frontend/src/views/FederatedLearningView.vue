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
        <div class="detail-col detail-col-left">
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
      </div>

      <div class="detail-col detail-col-right">
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
                  <span>{{ ver.clients }} Agent</span>
                  <span>·</span>
                  <span>{{ ver.time }}</span>
                </div>
              </div>
            </div>
          </div>
          </div>
        </div>
      </div>

      <div class="panel-card tasks-panel">
        <div class="panel-card-header">
          <div class="panel-title-group">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
              <rect x="2" y="3" width="14" height="12" rx="2" stroke="#6366f1" stroke-width="1.2" />
              <line x1="5" y1="7" x2="13" y2="7" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
              <line x1="5" y1="10" x2="10" y2="10" stroke="#6366f1" stroke-width="0.8" opacity="0.5" />
            </svg>
            <h2>联邦学习任务</h2>
          </div>
          <span class="task-count">{{ federatedTasks.length }} 个任务</span>
        </div>
        <div class="tasks-list">
          <div v-for="task in federatedTasks" :key="task.id" class="task-item" :class="task.status">
            <div class="task-head">
              <div class="task-id">{{ task.id }}</div>
              <span class="task-badge" :class="task.status">{{ task.statusText }}</span>
            </div>
            <div class="task-name">{{ task.name }}</div>
            <div class="task-desc">{{ task.description }}</div>
            <div class="task-progress-row">
              <div class="task-progress-track">
                <div class="task-progress-fill" :class="task.status" :style="{ width: task.progress + '%' }"></div>
              </div>
              <span class="task-progress-text">{{ task.progress }}%</span>
            </div>
            <div class="task-meta-row">
              <span class="task-meta-item">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1" /><circle cx="6" cy="6" r="1.5" fill="currentColor" /></svg>
                {{ task.participants }} 参与方
              </span>
              <span class="task-meta-item">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M6 1v5l3 2" stroke="currentColor" stroke-width="1" stroke-linecap="round" /><circle cx="6" cy="6" r="5" stroke="currentColor" stroke-width="1" /></svg>
                轮次 {{ task.currentRound }}/{{ task.totalRounds }}
              </span>
              <span class="task-meta-item">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 9l2-3 2 2 4-5" stroke="currentColor" stroke-width="1" stroke-linecap="round" stroke-linejoin="round" /></svg>
                {{ task.accuracy }}%
              </span>
              <span class="task-meta-item">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><rect x="1" y="3" width="10" height="6" rx="1" stroke="currentColor" stroke-width="1" /><line x1="4" y1="5" x2="4" y2="7" stroke="currentColor" stroke-width="0.8" /></svg>
                {{ task.createdAt }}
              </span>
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
    value: '4',
    trend: 0,
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
    value: '85.3%',
    trend: 2.1,
    bgColor: 'rgba(52, 211, 153, 0.1)',
    svgPath: '<path d="M3 14L7 8L11 11L17 3" stroke="#34d399" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>'
  }
])

const topologyClients = ref([
  { id: 'c1', label: '律师Agent', active: true, accuracy: 87.3, dataSize: 12450 },
  { id: 'c2', label: '教师Agent', active: true, accuracy: 84.6, dataSize: 8920 },
  { id: 'c3', label: '程序员Agent', active: true, accuracy: 86.1, dataSize: 15380 },
  { id: 'c4', label: '作家Agent', active: true, accuracy: 83.2, dataSize: 6740 }
])

const accuracyHistory = ref([52.3, 58.7, 63.9, 68.4, 72.1, 75.6, 78.3, 80.5, 82.1, 83.4, 84.2, 84.8, 85.3, 85.6, 85.8, 86.0, 86.2, 86.3, 86.4, 86.5])
const lossHistory = ref([1.82, 1.61, 1.43, 1.28, 1.14, 1.02, 0.91, 0.82, 0.74, 0.67, 0.61, 0.56, 0.51, 0.47, 0.44, 0.41, 0.39, 0.37, 0.36, 0.35])
const roundHistory = ref([13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32])

const aggClients = ref([
  { id: 'c1', label: '律师Agent', weight: 0.30, uploaded: true },
  { id: 'c2', label: '教师Agent', weight: 0.22, uploaded: true },
  { id: 'c3', label: '程序员Agent', weight: 0.30, uploaded: true },
  { id: 'c4', label: '作家Agent', weight: 0.18, uploaded: true }
])

const privacyMechanisms = ref([
  { label: '差分隐私 (DP-SGD)', enabled: true },
  { label: '同态加密 (HE)', enabled: true },
  { label: '安全聚合 (SecAgg)', enabled: true },
  { label: '梯度裁剪 (Clip)', enabled: true },
  { label: '噪声注入 (Noise)', enabled: false }
])

const versionHistory = ref([
  { version: '3.2', accuracy: 85.3, clients: 4, time: '刚刚', isLatest: true },
  { version: '3.1', accuracy: 84.1, clients: 4, time: '2小时前', isLatest: false },
  { version: '3.0', accuracy: 82.7, clients: 4, time: '1天前', isLatest: false },
  { version: '2.8', accuracy: 80.5, clients: 4, time: '3天前', isLatest: false },
  { version: '2.5', accuracy: 77.8, clients: 4, time: '1周前', isLatest: false },
  { version: '2.2', accuracy: 74.2, clients: 4, time: '2周前', isLatest: false },
  { version: '2.0', accuracy: 71.5, clients: 3, time: '3周前', isLatest: false },
  { version: '1.5', accuracy: 65.8, clients: 3, time: '1月前', isLatest: false }
])

const models = ref([
  { id: 'lawyer', name: '律师Agent模型', version: '3.2', status: 'online', statusText: '在线', accuracy: 87.3, efficiency: 82, color: '#3b82f6' },
  { id: 'teacher', name: '教师Agent模型', version: '2.8', status: 'online', statusText: '在线', accuracy: 84.6, efficiency: 79, color: '#10b981' },
  { id: 'programmer', name: '程序员Agent模型', version: '4.1', status: 'training', statusText: '训练中', accuracy: 86.1, efficiency: 85, color: '#8b5cf6' },
  { id: 'writer', name: '作家Agent模型', version: '2.3', status: 'ready', statusText: '就绪', accuracy: 83.2, efficiency: 76, color: '#f59e0b' }
])

const federatedTasks = ref([
  {
    id: 'task-001',
    name: '法律知识图谱RAG优化',
    status: 'running',
    statusText: '运行中',
    participants: 4,
    progress: 78,
    currentRound: 32,
    totalRounds: 40,
    createdAt: '2026-04-18 09:30',
    description: '基于联邦学习优化法律领域RAG检索与生成质量',
    accuracy: 87.3,
    loss: 0.35,
    dataSize: 43490
  },
  {
    id: 'task-002',
    name: '教育学情诊断模型训练',
    status: 'running',
    statusText: '运行中',
    participants: 4,
    progress: 65,
    currentRound: 26,
    totalRounds: 40,
    createdAt: '2026-04-19 14:15',
    description: '联邦协同训练学情诊断与个性化推荐模型',
    accuracy: 84.6,
    loss: 0.42,
    dataSize: 43490
  },
  {
    id: 'task-003',
    name: '代码生成与审查模型迭代',
    status: 'running',
    statusText: '运行中',
    participants: 4,
    progress: 52,
    currentRound: 21,
    totalRounds: 40,
    createdAt: '2026-04-20 08:00',
    description: '多Agent联邦训练代码生成与安全审查模型',
    accuracy: 86.1,
    loss: 0.38,
    dataSize: 43490
  },
  {
    id: 'task-004',
    name: '创意写作风格迁移优化',
    status: 'paused',
    statusText: '已暂停',
    participants: 3,
    progress: 40,
    currentRound: 16,
    totalRounds: 40,
    createdAt: '2026-04-20 11:45',
    description: '联邦优化写作风格迁移与内容生成质量',
    accuracy: 83.2,
    loss: 0.48,
    dataSize: 34110
  },
  {
    id: 'task-005',
    name: '跨领域知识融合实验',
    status: 'completed',
    statusText: '已完成',
    participants: 4,
    progress: 100,
    currentRound: 40,
    totalRounds: 40,
    createdAt: '2026-04-15 10:00',
    description: '验证4个Agent领域知识联邦融合的可行性与效果',
    accuracy: 81.7,
    loss: 0.52,
    dataSize: 43490
  },
  {
    id: 'task-006',
    name: '隐私保护机制基准测试',
    status: 'completed',
    statusText: '已完成',
    participants: 4,
    progress: 100,
    currentRound: 20,
    totalRounds: 20,
    createdAt: '2026-04-12 16:30',
    description: '评估DP-SGD与同态加密对联邦训练精度的影响',
    accuracy: 79.4,
    loss: 0.58,
    dataSize: 43490
  },
  {
    id: 'task-007',
    name: '通信效率优化实验',
    status: 'failed',
    statusText: '失败',
    participants: 2,
    progress: 15,
    currentRound: 3,
    totalRounds: 20,
    createdAt: '2026-04-21 07:20',
    description: '测试梯度压缩与稀疏化对通信效率的提升',
    accuracy: 54.2,
    loss: 1.35,
    dataSize: 21740
  }
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
  accuracyHistory.value = [52.3, 58.7, 63.9, 68.4, 72.1, 75.6, 78.3, 80.5, 82.1, 83.4, 84.2, 84.8, 85.3, 85.6, 85.8, 86.0, 86.2, 86.3, 86.4, 86.5]
  lossHistory.value = [1.82, 1.61, 1.43, 1.28, 1.14, 1.02, 0.91, 0.82, 0.74, 0.67, 0.61, 0.56, 0.51, 0.47, 0.44, 0.41, 0.39, 0.37, 0.36, 0.35]
  roundHistory.value = [13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32]
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
  --primary: #6366f1;
  --primary-light: #818cf8;
  --primary-bg: rgba(99, 102, 241, 0.06);
  --primary-border: rgba(99, 102, 241, 0.12);
  --cyan: #22d3ee;
  --cyan-dark: #0891b2;
  --purple: #a78bfa;
  --green: #34d399;
  --green-dark: #059669;
  --pink: #f472b6;
  --amber: #f59e0b;
  --surface: #ffffff;
  --surface-alt: #f8fafc;
  --border: rgba(99, 102, 241, 0.06);
  --border-hover: rgba(99, 102, 241, 0.15);
  --text-primary: #1e293b;
  --text-secondary: #475569;
  --text-muted: #94a3b8;
  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-lg: 16px;
  --radius-xl: 20px;
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.04);
  --shadow-md: 0 4px 16px rgba(0, 0, 0, 0.06);
  --shadow-lg: 0 8px 32px rgba(0, 0, 0, 0.08);
  --shadow-primary: 0 4px 20px rgba(99, 102, 241, 0.12);
  --transition-fast: 0.15s ease;
  --transition-base: 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
  --transition-smooth: 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
  --gap-xs: 6px;
  --gap-sm: 10px;
  --gap-md: 16px;
  --gap-lg: 24px;
  --gap-xl: 32px;

  min-height: 100vh;
  background: var(--surface-alt);
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
  max-width: 1440px;
  margin: 0 auto;
  padding: var(--gap-lg) var(--gap-xl);
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--gap-lg);
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border);
}

.header-left {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
}

.brand-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-md);
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-primary);
  transition: transform var(--transition-base), box-shadow var(--transition-base);
}

.brand-icon:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 24px rgba(99, 102, 241, 0.4);
}

.brand-text h1 {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}

.brand-text p {
  margin: 0;
  font-size: 13px;
  color: var(--primary);
  font-weight: 500;
  letter-spacing: 0.5px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: var(--gap-md);
}

.system-status-bar {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.status-indicator {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-xl);
  font-size: 12px;
  font-weight: 600;
  transition: all var(--transition-base);
}

.status-indicator.training {
  background: rgba(34, 211, 238, 0.1);
  color: var(--cyan-dark);
  border: 1px solid rgba(34, 211, 238, 0.2);
}

.status-indicator.aggregating {
  background: var(--primary-bg);
  color: var(--primary);
  border: 1px solid var(--primary-border);
}

.status-indicator.paused {
  background: rgba(100, 116, 139, 0.08);
  color: var(--text-muted);
  border: 1px solid rgba(100, 116, 139, 0.15);
}

.indicator-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
  animation: blink 2s ease-in-out infinite;
}

@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.round-badge {
  padding: 6px 14px;
  border-radius: var(--radius-xl);
  font-size: 12px;
  font-weight: 600;
  background: var(--primary-bg);
  color: var(--primary);
  border: 1px solid var(--primary-border);
}

.header-actions {
  display: flex;
  gap: var(--gap-xs);
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  border: 1px solid var(--primary-border);
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
}

.action-btn:hover:not(:disabled) {
  background: var(--primary-bg);
  color: var(--primary);
  border-color: rgba(99, 102, 241, 0.3);
  box-shadow: var(--shadow-primary);
  transform: translateY(-1px);
}

.action-btn:active:not(:disabled) {
  transform: translateY(0);
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gap-md);
  margin-bottom: var(--gap-lg);
}

.stat-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 18px 20px;
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  transition: all var(--transition-base);
  position: relative;
  overflow: hidden;
}

.stat-card::after {
  content: '';
  position: absolute;
  top: 0;
  right: 0;
  width: 80px;
  height: 80px;
  border-radius: 50%;
  opacity: 0.04;
  transform: translate(20px, -20px);
}

.stat-card:nth-child(1)::after { background: var(--primary); }
.stat-card:nth-child(2)::after { background: var(--cyan); }
.stat-card:nth-child(3)::after { background: var(--purple); }
.stat-card:nth-child(4)::after { background: var(--green); }

.stat-card:hover {
  box-shadow: var(--shadow-primary);
  transform: translateY(-2px);
  border-color: var(--border-hover);
}

.stat-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
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
  font-size: 22px;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1;
  letter-spacing: -0.3px;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 3px;
  font-weight: 500;
}

.stat-trend {
  display: flex;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 8px;
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
  margin-bottom: var(--gap-lg);
}

.detail-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  align-items: stretch;
}

.detail-col {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.panel-card {
  background: var(--surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-sm);
  overflow: hidden;
  transition: all var(--transition-base);
  display: flex;
  flex-direction: column;
  height: 100%;
}

.panel-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-hover);
}

.panel-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--gap-md) 20px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.02), rgba(34, 211, 238, 0.01));
  flex-shrink: 0;
}

.panel-title-group {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.panel-title-group h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.2px;
}

.panel-actions {
  display: flex;
  gap: 6px;
}

.icon-btn {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--primary-border);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-base);
}

.icon-btn:hover {
  background: var(--primary-bg);
  color: var(--primary);
  border-color: rgba(99, 102, 241, 0.2);
}

.icon-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.topology-panel {
  padding-bottom: 12px;
}

.topology-panel :deep(.topology-graph) {
  padding: 0 16px;
}

.training-panel {
  padding-bottom: 12px;
}

.training-panel :deep(.training-curve) {
  padding: 0 16px;
}

.training-controls {
  display: flex;
  gap: 6px;
}

.ctrl-btn {
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  border: 1px solid var(--primary-border);
  background: var(--primary-bg);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
  font-weight: 500;
}

.ctrl-btn:hover {
  background: rgba(99, 102, 241, 0.08);
  color: var(--text-primary);
}

.ctrl-btn.active {
  background: rgba(99, 102, 241, 0.1);
  color: var(--primary);
  border-color: rgba(99, 102, 241, 0.25);
}

.ctrl-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.training-metrics-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gap-sm);
  padding: 0 var(--gap-md);
  margin-top: var(--gap-sm);
}

.mini-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 10px 6px;
  background: var(--primary-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  transition: all var(--transition-base);
}

.mini-metric:hover {
  background: rgba(99, 102, 241, 0.06);
  border-color: var(--border-hover);
}

.mini-metric-label {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.mini-metric-value {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.3px;
}

.mini-metric-value.cyan { color: var(--cyan-dark); }
.mini-metric-value.pink { color: #db2777; }
.mini-metric-value.purple { color: #7c3aed; }
.mini-metric-value.green { color: var(--green-dark); }

.aggregation-panel :deep(.aggregation-card) {
  border: none;
  border-radius: 0;
  background: transparent;
  padding: 8px 12px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.privacy-panel .privacy-content {
  padding: 8px 16px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.privacy-visual {
  margin-bottom: 8px;
  flex-shrink: 0;
}

.privacy-svg {
  display: block;
}

.privacy-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  padding-top: 6px;
}

.privacy-item {
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
  font-size: 12px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  transition: background var(--transition-fast);
}

.privacy-item:hover {
  background: var(--primary-bg);
}

.privacy-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #cbd5e1;
  flex-shrink: 0;
  transition: all var(--transition-base);
}

.privacy-dot.active {
  background: var(--green);
  box-shadow: 0 0 8px rgba(52, 211, 153, 0.5);
}

.privacy-label {
  flex: 1;
  color: var(--text-secondary);
  font-weight: 500;
}

.privacy-status {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
}

.privacy-status.on {
  color: var(--green-dark);
}

.models-panel .models-list {
  padding: 8px 12px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  align-content: start;
}

.model-item {
  padding: 12px;
  background: var(--primary-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  transition: all var(--transition-base);
  flex-shrink: 0;
}

.model-item:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-sm);
  background: rgba(99, 102, 241, 0.04);
}

.model-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.model-icon-box {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  border: 1.5px solid;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--primary-bg);
  flex-shrink: 0;
}

.model-icon-box svg {
  width: 14px;
  height: 14px;
}

.model-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.model-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.model-version {
  font-size: 10px;
  color: var(--text-muted);
}

.model-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 8px;
  font-weight: 600;
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
  gap: 5px;
  margin-bottom: 8px;
}

.perf-row {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
}

.perf-label {
  width: 32px;
  color: #94a3b8;
  font-size: 10px;
  flex-shrink: 0;
  font-weight: 500;
}

.perf-bar {
  flex: 1;
  height: 4px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
}

.perf-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.8s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.perf-val {
  width: 30px;
  text-align: right;
  font-weight: 600;
  color: #475569;
  font-size: 10px;
  flex-shrink: 0;
}

.model-btns {
  display: flex;
  gap: 6px;
}

.model-btn {
  flex: 1;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  border: 1px solid var(--primary-border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-base);
  font-weight: 500;
}

.model-btn:hover {
  background: var(--primary-bg);
  color: var(--text-primary);
  border-color: rgba(99, 102, 241, 0.2);
}

.model-btn.primary {
  background: var(--primary-bg);
  color: var(--primary);
  border-color: rgba(99, 102, 241, 0.15);
}

.model-btn.primary:hover {
  background: rgba(99, 102, 241, 0.12);
  border-color: rgba(99, 102, 241, 0.3);
}

.model-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.version-panel .version-list {
  padding: 8px 16px;
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  gap: 2px;
}

.version-item {
  display: flex;
  align-items: flex-start;
  gap: var(--gap-md);
  padding: 8px 0 8px 16px;
  border-left: 2px solid #e2e8f0;
  position: relative;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.version-item::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  border: 2px solid var(--surface);
  transition: all var(--transition-base);
}

.version-item:hover {
  background: var(--primary-bg);
}

.version-item.latest {
  border-left-color: var(--primary);
}

.version-item.latest::before {
  background: var(--primary);
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.5);
}

.version-top {
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
  margin-bottom: 3px;
}

.version-tag {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.version-item.latest .version-tag {
  color: var(--primary);
}

.latest-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  background: var(--primary-bg);
  color: var(--primary);
  font-weight: 600;
}

.version-meta {
  display: flex;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
  flex-wrap: wrap;
}

.demo-overlay {
  position: fixed;
  bottom: var(--gap-lg);
  right: var(--gap-lg);
  z-index: 1000;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.demo-card {
  width: 380px;
  background: var(--surface);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  border: 1px solid var(--primary-border);
  overflow: hidden;
}

.demo-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--gap-md) 20px;
  background: linear-gradient(135deg, var(--primary), var(--primary-light));
  color: white;
}

.demo-card-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.close-btn {
  background: rgba(255, 255, 255, 0.2);
  border: none;
  color: white;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  transition: background var(--transition-fast);
}

.close-btn:hover {
  background: rgba(255, 255, 255, 0.3);
}

.close-btn:focus-visible {
  outline: 2px solid white;
  outline-offset: 2px;
}

.demo-steps {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: var(--gap-md);
}

.demo-step {
  display: flex;
  gap: var(--gap-md);
  align-items: flex-start;
}

.step-num {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--primary-bg);
  color: var(--primary);
  font-size: 12px;
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
  font-size: 13px;
  color: var(--text-secondary);
  display: block;
  margin-bottom: var(--gap-xs);
  font-weight: 500;
}

.step-progress {
  height: 5px;
  background: #e2e8f0;
  border-radius: 3px;
  overflow: hidden;
}

.step-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--primary), var(--cyan));
  border-radius: 3px;
  transition: width 0.5s ease;
}

@media (max-width: 1280px) {
  .viz-row {
    grid-template-columns: 1fr;
  }

  .detail-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1024px) {
  .view-container {
    padding: var(--gap-lg) var(--gap-md);
  }

  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .training-metrics-row {
    grid-template-columns: repeat(2, 1fr);
  }

  .models-panel .models-list {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .view-container {
    padding: var(--gap-md);
  }

  .view-header {
    flex-direction: column;
    gap: var(--gap-md);
    align-items: flex-start;
  }

  .header-right {
    flex-wrap: wrap;
    gap: var(--gap-sm);
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

  .models-panel .models-list {
    grid-template-columns: 1fr;
  }

  .demo-overlay {
    left: var(--gap-md);
    right: var(--gap-md);
    bottom: var(--gap-md);
  }

  .demo-card {
    width: 100%;
  }
}

@media (max-width: 480px) {
  .view-container {
    padding: var(--gap-sm);
  }

  .brand-text h1 {
    font-size: 20px;
  }

  .stat-card {
    padding: 14px var(--gap-md);
  }

  .stat-value {
    font-size: 18px;
  }

  .training-metrics-row {
    grid-template-columns: 1fr 1fr;
    gap: var(--gap-xs);
  }

  .mini-metric {
    padding: 8px 4px;
  }

  .mini-metric-value {
    font-size: 13px;
  }
}

.tasks-panel {
  margin-top: 20px;
}

.task-count {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
  padding: 3px 10px;
  background: var(--primary-bg);
  border-radius: var(--radius-sm);
}

.tasks-list {
  padding: var(--gap-md);
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 520px;
  overflow-y: auto;
}

.tasks-list::-webkit-scrollbar {
  width: 4px;
}

.tasks-list::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}

.task-item {
  padding: 14px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface);
  transition: all var(--transition-base);
}

.task-item:hover {
  border-color: var(--border-hover);
  box-shadow: var(--shadow-sm);
}

.task-item.running {
  border-left: 3px solid var(--cyan);
}

.task-item.paused {
  border-left: 3px solid var(--amber);
}

.task-item.completed {
  border-left: 3px solid var(--green);
}

.task-item.failed {
  border-left: 3px solid #ef4444;
}

.task-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.task-id {
  font-size: 11px;
  color: var(--text-muted);
  font-weight: 500;
  font-family: monospace;
}

.task-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-weight: 600;
}

.task-badge.running {
  background: rgba(34, 211, 238, 0.1);
  color: var(--cyan-dark);
}

.task-badge.paused {
  background: rgba(245, 158, 11, 0.1);
  color: #b45309;
}

.task-badge.completed {
  background: rgba(52, 211, 153, 0.1);
  color: var(--green-dark);
}

.task-badge.failed {
  background: rgba(239, 68, 68, 0.1);
  color: #dc2626;
}

.task-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.task-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 10px;
  line-height: 1.4;
}

.task-progress-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.task-progress-track {
  flex: 1;
  height: 6px;
  background: rgba(99, 102, 241, 0.08);
  border-radius: 3px;
  overflow: hidden;
}

.task-progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.5s ease;
}

.task-progress-fill.running {
  background: linear-gradient(90deg, var(--cyan), var(--primary));
}

.task-progress-fill.paused {
  background: linear-gradient(90deg, var(--amber), #fbbf24);
}

.task-progress-fill.completed {
  background: linear-gradient(90deg, var(--green), #6ee7b7);
}

.task-progress-fill.failed {
  background: linear-gradient(90deg, #ef4444, #fca5a5);
}

.task-progress-text {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  min-width: 36px;
  text-align: right;
}

.task-meta-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.task-meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
}

.task-meta-item svg {
  color: var(--primary);
  opacity: 0.6;
}
</style>
