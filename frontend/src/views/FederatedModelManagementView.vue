<template>
  <div class="model-management-view">
    <div class="ambient-glow top-left"></div>
    <div class="ambient-glow bottom-right"></div>

    <section class="page-header glass-panel">
      <div class="header-brand">
        <div class="brand-icon">
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
            <path d="M14 2L24 7v10l-10 5L4 17V7l10-5z" stroke="#6366f1" stroke-width="1.5" />
            <path d="M14 2v10m0 0l10-5m-10 5L4 7m10 5v13" stroke="#6366f1" stroke-width="0.8" opacity="0.4" />
          </svg>
        </div>
        <div>
          <h1>模型管理</h1>
          <p>统一查看联邦模型版本、状态和评估结果</p>
        </div>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="refreshModels">
          <el-icon><Refresh /></el-icon>
          刷新模型
        </el-button>
        <el-button type="primary" @click="createModel">
          <el-icon><Plus /></el-icon>
          新建模型
        </el-button>
      </div>
    </section>

    <section class="stats-grid">
      <div class="stat-card glass-panel" v-for="stat in statsConfig" :key="stat.label">
        <div class="stat-accent" :style="{ background: stat.gradient }"></div>
        <div class="stat-icon-wrap" :style="{ background: stat.iconBg }">
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none" v-html="stat.svgPath"></svg>
        </div>
        <div class="stat-body">
          <span class="stat-value">{{ stat.value }}</span>
          <span class="stat-label">{{ stat.label }}</span>
        </div>
      </div>
    </section>

    <section class="filter-bar glass-panel">
      <el-input v-model="keyword" placeholder="搜索模型名称、场景或负责人" clearable>
        <template #prefix>
          <el-icon><Search /></el-icon>
        </template>
      </el-input>
      <el-select v-model="statusFilter" placeholder="全部状态" clearable>
        <el-option label="草稿" value="draft" />
        <el-option label="训练中" value="training" />
        <el-option label="就绪" value="ready" />
        <el-option label="在线" value="online" />
        <el-option label="离线" value="offline" />
      </el-select>
    </section>

    <section class="content-grid">
      <div v-loading="loading" class="card-grid">
        <article
          v-for="model in filteredModels"
          :key="model.id"
          class="model-card glass-panel"
          :class="{ active: activeModel?.id === model.id }"
          @click="showDetails(model)"
        >
          <div class="card-accent" :style="{ background: getAccentGradient(model.status) }"></div>
          <div class="card-head">
            <div class="card-title-area">
              <h3>{{ model.name }}</h3>
              <p>{{ model.scene }} · v{{ model.version }}</p>
            </div>
            <el-tag :type="getStatusTag(model.status)" effect="dark" size="small">{{ getStatusText(model.status) }}</el-tag>
          </div>

          <div class="meta-row">
            <el-tag v-if="model.federated" size="small" type="primary" effect="plain">联邦</el-tag>
            <el-tag v-else size="small" type="info" effect="plain">本地</el-tag>
            <span class="meta-owner">{{ model.owner }}</span>
            <span class="meta-type">{{ model.modelType }}</span>
          </div>

          <p class="description">{{ model.description }}</p>

          <div class="metric-item">
            <div class="metric-line">
              <span>精度</span>
              <span class="metric-value">{{ model.accuracy.toFixed(1) }}%</span>
            </div>
            <div class="progress-track">
              <div class="progress-fill" :style="{ width: model.accuracy.toFixed(1) + '%', background: getProgressColor(model.accuracy) }"></div>
            </div>
          </div>

          <div class="metrics-row-compact">
            <div class="metric-chip">
              <span class="chip-label">延迟</span>
              <span class="chip-value">{{ model.latency }}ms</span>
            </div>
            <div class="metric-chip">
              <span class="chip-label">损失</span>
              <span class="chip-value">{{ model.loss.toFixed(2) }}</span>
            </div>
            <div class="metric-chip">
              <span class="chip-label">大小</span>
              <span class="chip-value">{{ model.modelSize }}</span>
            </div>
            <div class="metric-chip">
              <span class="chip-label">更新</span>
              <span class="chip-value">{{ formatTimeShort(model.updatedAt) }}</span>
            </div>
          </div>

          <div class="card-actions">
            <el-button size="small" @click.stop="showDetails(model)">
              <el-icon><View /></el-icon>
              详情
            </el-button>
            <el-button size="small" @click.stop="evaluateModel(model)">
              <el-icon><TrendCharts /></el-icon>
              评估
            </el-button>
            <el-button size="small" type="primary" @click.stop="deployModel(model)">
              <el-icon><Upload /></el-icon>
              部署
            </el-button>
          </div>
        </article>

        <el-empty v-if="!loading && filteredModels.length === 0" description="没有匹配的模型" />
      </div>

      <aside class="inline-panel glass-panel">
        <div class="panel-header-area">
          <h3 class="panel-title">信息面板</h3>
          <div class="panel-mode-tabs" v-if="activeModel">
            <button class="mode-tab" :class="{ active: panelMode === 'details' }" @click="panelMode = 'details'">详情</button>
            <button class="mode-tab" :class="{ active: panelMode === 'evaluation' }" @click="panelMode = 'evaluation'">评估</button>
          </div>
        </div>

        <div v-if="activeModel" class="panel-content">
          <div class="panel-head">
            <strong class="panel-model-name">{{ activeModel.name }}</strong>
            <el-tag :type="getStatusTag(activeModel.status)" effect="dark" size="small">{{ getStatusText(activeModel.status) }}</el-tag>
          </div>
          <div class="panel-grid">
            <div class="panel-item">
              <span>版本</span>
              <strong>v{{ activeModel.version }}</strong>
            </div>
            <div class="panel-item">
              <span>场景</span>
              <strong>{{ activeModel.scene }}</strong>
            </div>
            <div class="panel-item">
              <span>负责人</span>
              <strong>{{ activeModel.owner }}</strong>
            </div>
            <div class="panel-item">
              <span>模型类型</span>
              <strong>{{ activeModel.modelType }}</strong>
            </div>
            <div class="panel-item">
              <span>参数量</span>
              <strong>{{ activeModel.params }}</strong>
            </div>
            <div class="panel-item">
              <span>模型大小</span>
              <strong>{{ activeModel.modelSize }}</strong>
            </div>
            <div class="panel-item">
              <span>框架</span>
              <strong>{{ activeModel.framework }}</strong>
            </div>
            <div class="panel-item">
              <span>参与方</span>
              <strong>{{ activeModel.participants }} Agent</strong>
            </div>
            <div class="panel-item">
              <span>训练轮次</span>
              <strong>{{ activeModel.trainingRounds }}</strong>
            </div>
            <div class="panel-item">
              <span>最近更新</span>
              <strong>{{ formatTime(activeModel.updatedAt) }}</strong>
            </div>
          </div>

          <div v-if="panelMode === 'details'" class="panel-block">
            <h4>模型说明</h4>
            <p>{{ activeModel.description }}</p>
            <div class="detail-metrics">
              <div class="detail-metric-item">
                <span class="detail-metric-label">精度</span>
                <div class="detail-progress-track">
                  <div class="detail-progress-fill" :style="{ width: activeModel.accuracy.toFixed(1) + '%', background: getProgressColor(activeModel.accuracy) }"></div>
                </div>
                <span class="detail-metric-value">{{ activeModel.accuracy.toFixed(1) }}%</span>
              </div>
              <div class="detail-metric-item">
                <span class="detail-metric-label">损失值</span>
                <div class="detail-progress-track">
                  <div class="detail-progress-fill" :style="{ width: Math.min(100, activeModel.loss * 50) + '%', background: activeModel.loss > 0.8 ? 'linear-gradient(90deg, #ef4444, #f87171)' : activeModel.loss > 0.5 ? 'linear-gradient(90deg, #f59e0b, #fbbf24)' : 'linear-gradient(90deg, #22c55e, #4ade80)' }"></div>
                </div>
                <span class="detail-metric-value">{{ activeModel.loss.toFixed(2) }}</span>
              </div>
              <div class="detail-metric-item">
                <span class="detail-metric-label">延迟</span>
                <span class="detail-metric-value">{{ activeModel.latency }}ms</span>
              </div>
            </div>
          </div>

          <div v-if="panelMode === 'evaluation'" class="panel-block">
            <h4>评估结果</h4>
            <div class="eval-grid">
              <div class="eval-card">
                <span class="eval-label">综合评分</span>
                <span class="eval-value primary">{{ evaluation.score }}</span>
              </div>
              <div class="eval-card">
                <span class="eval-label">推理吞吐</span>
                <span class="eval-value">{{ evaluation.qps }} QPS</span>
              </div>
              <div class="eval-card">
                <span class="eval-label">稳定性</span>
                <span class="eval-value success">{{ evaluation.stability }}%</span>
              </div>
            </div>
            <div class="eval-advice">
              <span class="advice-label">建议</span>
              <span class="advice-text">{{ evaluation.advice }}</span>
            </div>
          </div>
        </div>

        <div v-else class="panel-empty">
          <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity="0.3">
            <path d="M24 4L42 14v20L24 44 6 34V14L24 4z" stroke="#6366f1" stroke-width="1.5" />
            <path d="M24 4v20m0 0l18-10m-18 10L6 14m18 10v20" stroke="#6366f1" stroke-width="0.8" opacity="0.4" />
          </svg>
          <p>点击左侧模型查看详情或评估</p>
        </div>
      </aside>
    </section>

    <section class="status-strip glass-panel">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ operationMessage }}</span>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Plus, Refresh, Search, TrendCharts, Upload, View, InfoFilled } from '@element-plus/icons-vue'
import { federatedModelApi, type ModelInfo } from '@/services/api/federatedModel'

type ModelStatus = 'draft' | 'training' | 'ready' | 'online' | 'offline'
type PanelMode = 'details' | 'evaluation'

interface ModelCard {
  id: string
  name: string
  scene: string
  version: string
  status: ModelStatus
  federated: boolean
  owner: string
  accuracy: number
  latency: number
  updatedAt: string
  description: string
  modelType: string
  modelSize: string
  loss: number
  params: string
  framework: string
  trainingRounds: number
  participants: number
}

interface EvaluationState {
  score: string
  qps: string
  stability: string
  advice: string
}

const makeDefaultModels = (): ModelCard[] => [
  {
    id: 'fed-lawyer-1',
    name: '律师Agent模型',
    scene: '法律咨询',
    version: '3.2',
    status: 'online',
    federated: true,
    owner: '联邦平台',
    accuracy: 87.3,
    latency: 156,
    updatedAt: new Date().toISOString(),
    description: '面向法律领域的联邦模型，支持案例检索、法规查询、证据分析等技能的联邦协同优化。',
    modelType: 'RAG-Enhanced LLM',
    modelSize: '2.4 GB',
    loss: 0.35,
    params: '7B',
    framework: 'FedAvg + DP-SGD',
    trainingRounds: 32,
    participants: 4
  },
  {
    id: 'fed-teacher-1',
    name: '教师Agent模型',
    scene: '教学辅导',
    version: '2.8',
    status: 'online',
    federated: true,
    owner: '联邦平台',
    accuracy: 84.6,
    latency: 142,
    updatedAt: new Date(Date.now() - 35 * 60 * 1000).toISOString(),
    description: '面向教育领域的联邦模型，支持学情诊断、教案生成、错题推送等技能的联邦协同优化。',
    modelType: 'RAG-Enhanced LLM',
    modelSize: '2.1 GB',
    loss: 0.42,
    params: '7B',
    framework: 'FedAvg + SecAgg',
    trainingRounds: 28,
    participants: 4
  },
  {
    id: 'fed-programmer-1',
    name: '程序员Agent模型',
    scene: '代码开发',
    version: '4.1',
    status: 'training',
    federated: true,
    owner: '联邦平台',
    accuracy: 86.1,
    latency: 118,
    updatedAt: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    description: '面向开发领域的联邦模型，支持需求分析、代码检索、代码生成等技能的联邦协同优化。',
    modelType: 'RAG-Enhanced LLM',
    modelSize: '2.8 GB',
    loss: 0.38,
    params: '7B',
    framework: 'FedAvg + HE',
    trainingRounds: 21,
    participants: 4
  },
  {
    id: 'fed-writer-1',
    name: '作家Agent模型',
    scene: '创意写作',
    version: '2.3',
    status: 'ready',
    federated: true,
    owner: '联邦平台',
    accuracy: 83.2,
    latency: 168,
    updatedAt: new Date(Date.now() - 8 * 60 * 60 * 1000).toISOString(),
    description: '面向写作领域的联邦模型，支持灵感拓展、大纲生成、内容撰写等技能的联邦协同优化。',
    modelType: 'RAG-Enhanced LLM',
    modelSize: '1.9 GB',
    loss: 0.48,
    params: '7B',
    framework: 'FedAvg + DP-SGD',
    trainingRounds: 16,
    participants: 3
  },
  {
    id: 'fed-cross-1',
    name: '跨领域融合模型',
    scene: '知识融合',
    version: '1.5',
    status: 'online',
    federated: true,
    owner: '联邦平台',
    accuracy: 81.7,
    latency: 195,
    updatedAt: new Date(Date.now() - 2 * 24 * 60 * 60 * 1000).toISOString(),
    description: '融合4个Agent领域知识的联邦模型，验证跨领域知识迁移与协同推理能力。',
    modelType: 'Multi-Domain LLM',
    modelSize: '3.2 GB',
    loss: 0.52,
    params: '13B',
    framework: 'FedAvg + HE + DP-SGD',
    trainingRounds: 40,
    participants: 4
  },
  {
    id: 'fed-privacy-1',
    name: '隐私保护基准模型',
    scene: '隐私评估',
    version: '1.2',
    status: 'offline',
    federated: true,
    owner: '安全团队',
    accuracy: 79.4,
    latency: 210,
    updatedAt: new Date(Date.now() - 5 * 24 * 60 * 60 * 1000).toISOString(),
    description: '用于评估差分隐私与同态加密机制对联邦训练精度影响的基准模型。',
    modelType: 'Privacy-Preserving LLM',
    modelSize: '2.0 GB',
    loss: 0.58,
    params: '7B',
    framework: 'FedAvg + DP-SGD + HE',
    trainingRounds: 20,
    participants: 4
  },
  {
    id: 'fed-comm-1',
    name: '通信效率优化模型',
    scene: '通信优化',
    version: '0.8',
    status: 'draft',
    federated: true,
    owner: '基础设施组',
    accuracy: 74.8,
    latency: 85,
    updatedAt: new Date(Date.now() - 12 * 60 * 60 * 1000).toISOString(),
    description: '测试梯度压缩与稀疏化策略对联邦训练通信效率的提升，当前处于实验阶段。',
    modelType: 'Compressed LLM',
    modelSize: '1.2 GB',
    loss: 0.86,
    params: '3B',
    framework: 'FedAvg + Gradient Sparsification',
    trainingRounds: 3,
    participants: 2
  },
  {
    id: 'local-lawyer-1',
    name: '律师本地基线模型',
    scene: '法律咨询',
    version: '1.0',
    status: 'ready',
    federated: false,
    owner: '律师Agent',
    accuracy: 78.6,
    latency: 98,
    updatedAt: new Date(Date.now() - 10 * 24 * 60 * 60 * 1000).toISOString(),
    description: '律师Agent的本地基线模型，未参与联邦训练，用于对比联邦优化效果。',
    modelType: 'Local LLM',
    modelSize: '1.8 GB',
    loss: 0.72,
    params: '7B',
    framework: 'Local Training',
    trainingRounds: 0,
    participants: 1
  }
]

const loading = ref(false)
const models = ref<ModelCard[]>(makeDefaultModels())
const keyword = ref('')
const statusFilter = ref<ModelStatus | ''>('')

const activeModel = ref<ModelCard | null>(null)
const panelMode = ref<PanelMode>('details')
const evaluation = ref<EvaluationState>({
  score: '--',
  qps: '--',
  stability: '--',
  advice: '--'
})
const operationMessage = ref('已进入模型管理页面，当前为同页交互模式。')

const filteredModels = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  return models.value.filter((item) => {
    const matchKeyword =
      !key ||
      item.name.toLowerCase().includes(key) ||
      item.scene.toLowerCase().includes(key) ||
      item.owner.toLowerCase().includes(key)
    const matchStatus = !statusFilter.value || item.status === statusFilter.value
    return matchKeyword && matchStatus
  })
})

const totalCount = computed(() => models.value.length)
const onlineCount = computed(() => models.value.filter((m) => m.status === 'online').length)
const trainingCount = computed(() => models.value.filter((m) => m.status === 'training').length)
const averageAccuracy = computed(() => {
  if (models.value.length === 0) return '0.0'
  const avg = models.value.reduce((sum, item) => sum + item.accuracy, 0) / models.value.length
  return avg.toFixed(1)
})

const statsConfig = computed(() => [
  {
    label: '模型总数',
    value: totalCount.value,
    gradient: 'linear-gradient(135deg, #6366f1, #818cf8)',
    iconBg: 'rgba(99, 102, 241, 0.1)',
    svgPath: '<path d="M10 2L18 6v8l-8 4-8-4V6l8-4z" stroke="#6366f1" stroke-width="1.3"/><path d="M10 2v8m0 0l8-4m-8 4L2 6m8 4v8" stroke="#6366f1" stroke-width="0.7" opacity="0.4"/>'
  },
  {
    label: '在线服务',
    value: onlineCount.value,
    gradient: 'linear-gradient(135deg, #22c55e, #4ade80)',
    iconBg: 'rgba(34, 197, 94, 0.1)',
    svgPath: '<circle cx="10" cy="10" r="7" stroke="#22c55e" stroke-width="1.3"/><path d="M7 10l2 2 4-4" stroke="#22c55e" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>'
  },
  {
    label: '训练中',
    value: trainingCount.value,
    gradient: 'linear-gradient(135deg, #f59e0b, #fbbf24)',
    iconBg: 'rgba(245, 158, 11, 0.1)',
    svgPath: '<path d="M10 3a7 7 0 0 1 0 14" stroke="#f59e0b" stroke-width="1.3" stroke-linecap="round"/><path d="M10 3a7 7 0 0 0 0 14" stroke="#f59e0b" stroke-width="1.3" stroke-linecap="round" stroke-dasharray="2 3" opacity="0.4"/>'
  },
  {
    label: '平均精度',
    value: averageAccuracy.value + '%',
    gradient: 'linear-gradient(135deg, #06b6d4, #22d3ee)',
    iconBg: 'rgba(6, 182, 212, 0.1)',
    svgPath: '<path d="M3 14l4-4 3 3 7-7" stroke="#06b6d4" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><circle cx="17" cy="6" r="1.5" fill="#06b6d4"/>'
  }
])

function getStatusTag(status: ModelStatus): 'info' | 'success' | 'warning' | 'primary' | 'danger' {
  if (status === 'online') return 'success'
  if (status === 'training') return 'warning'
  if (status === 'ready') return 'primary'
  if (status === 'offline') return 'danger'
  return 'info'
}

function getStatusText(status: ModelStatus): string {
  if (status === 'online') return '在线'
  if (status === 'training') return '训练中'
  if (status === 'ready') return '就绪'
  if (status === 'offline') return '离线'
  return '草稿'
}

function normalizeStatus(raw: string | undefined): ModelStatus {
  const value = (raw || '').toLowerCase()
  if (value.includes('online') || value.includes('published') || value.includes('active')) return 'online'
  if (value.includes('training') || value.includes('running')) return 'training'
  if (value.includes('ready') || value.includes('optimized')) return 'ready'
  if (value.includes('offline') || value.includes('disabled')) return 'offline'
  return 'draft'
}

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

function formatTimeShort(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}小时前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function getAccentGradient(status: ModelStatus): string {
  if (status === 'online') return 'linear-gradient(135deg, #22c55e, #4ade80)'
  if (status === 'training') return 'linear-gradient(135deg, #f59e0b, #fbbf24)'
  if (status === 'ready') return 'linear-gradient(135deg, #6366f1, #818cf8)'
  if (status === 'offline') return 'linear-gradient(135deg, #ef4444, #f87171)'
  return 'linear-gradient(135deg, #94a3b8, #cbd5e1)'
}

function getProgressColor(accuracy: number): string {
  if (accuracy >= 90) return 'linear-gradient(90deg, #22c55e, #4ade80)'
  if (accuracy >= 85) return 'linear-gradient(90deg, #06b6d4, #22d3ee)'
  if (accuracy >= 80) return 'linear-gradient(90deg, #6366f1, #818cf8)'
  return 'linear-gradient(90deg, #f59e0b, #fbbf24)'
}

function normalizeAccuracyPercent(accuracy: number | undefined, fallback = 85): number {
  if (typeof accuracy !== 'number' || Number.isNaN(accuracy)) {
    return fallback
  }

  const normalized = accuracy <= 1 ? accuracy * 100 : accuracy
  return Math.max(0, Math.min(99.9, normalized))
}

function normalizeLatency(speedOrLatency: number | undefined, fallback = 120): number {
  if (typeof speedOrLatency !== 'number' || Number.isNaN(speedOrLatency)) {
    return fallback
  }

  if (speedOrLatency > 1) {
    return Math.round(speedOrLatency)
  }

  return Math.round(245 - speedOrLatency * 110)
}

function flattenApiModels(data: Record<string, Record<string, ModelInfo>>): ModelCard[] {
  const flattened: ModelCard[] = []
  Object.entries(data || {}).forEach(([groupKey, groupModels]) => {
    Object.entries(groupModels || {}).forEach(([modelKey, model]) => {
      const perf = model.performance
      flattened.push({
        id: `${groupKey}-${modelKey}`,
        name: model.name || modelKey,
        scene: groupKey,
        version: model.version || '1.0.0',
        status: normalizeStatus(model.status),
        federated: true,
        owner: '联邦平台',
        accuracy: normalizeAccuracyPercent(perf?.accuracy, 85),
        latency: normalizeLatency(perf?.speed, 120),
        updatedAt: new Date().toISOString(),
        description: `来自 ${groupKey} 组的联邦模型。`,
        modelType: 'RAG-Enhanced LLM',
        modelSize: '2.0 GB',
        loss: 0.45,
        params: '7B',
        framework: 'FedAvg',
        trainingRounds: 10,
        participants: 4
      })
    })
  })
  return flattened
}

async function refreshModels(): Promise<void> {
  loading.value = true
  try {
    const response = await federatedModelApi.listModels()
    const remote = flattenApiModels(response.data || {})
    if (remote.length > 0) {
      models.value = remote
      operationMessage.value = '模型列表已同步远端数据。'
    } else {
      operationMessage.value = '未获取到远端模型，已保留本地占位数据。'
    }
  } catch {
    operationMessage.value = '模型服务暂不可用，当前展示本地占位数据。'
  } finally {
    loading.value = false
  }
}

function createModel(): void {
  panelMode.value = 'details'
  activeModel.value = null
  operationMessage.value = '新建模型功能可在此处接入，目前保持同页交互。'
}

function showDetails(model: ModelCard): void {
  activeModel.value = model
  panelMode.value = 'details'
  operationMessage.value = `已在右侧面板展示 ${model.name} 的详细信息。`
}

function deployModel(model: ModelCard): void {
  if (model.status === 'training') {
    operationMessage.value = `${model.name} 仍在训练中，暂不可部署。`
    return
  }
  operationMessage.value = `已提交 ${model.name} 的部署任务（同页状态提示）。`
}

function evaluateModel(model: ModelCard): void {
  activeModel.value = model
  panelMode.value = 'evaluation'
  evaluation.value = {
    score: `${Math.round(model.accuracy * 10 + 20)}`,
    qps: `${Math.max(30, Math.round(1200 / Math.max(model.latency, 30)))}`,
    stability: `${Math.min(99, Math.round(model.accuracy + 5))}`,
    advice: model.status === 'training' ? '建议训练完成后再进入生产。' : '可进入灰度发布阶段。'
  }
  operationMessage.value = `已在右侧面板展示 ${model.name} 的评估结果。`
}

onMounted(() => {
  void refreshModels()
})
</script>

<style scoped>
.model-management-view {
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

  position: relative;
  min-height: 100vh;
  padding: var(--gap-lg) 28px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  color: var(--text-primary);
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
  background: var(--surface-alt);
}

.ambient-glow {
  position: fixed;
  width: 400px;
  height: 400px;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.12;
  pointer-events: none;
  z-index: 0;
}

.ambient-glow.top-left {
  top: -140px;
  left: -140px;
  background: var(--primary);
}

.ambient-glow.bottom-right {
  right: -140px;
  bottom: -160px;
  background: #06b6d4;
}

.glass-panel {
  position: relative;
  z-index: 1;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition: box-shadow var(--transition-base), transform var(--transition-base);
}

.page-header {
  padding: 20px var(--gap-lg);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap-md);
}

.header-brand {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: var(--primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: var(--text-primary);
}

.page-header p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.header-actions {
  display: flex;
  gap: var(--gap-sm);
}

.stats-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 14px;
}

.stat-card {
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 14px;
  overflow: hidden;
}

.stat-accent {
  position: absolute;
  top: 0;
  left: 0;
  width: 3px;
  height: 100%;
  border-radius: 0 2px 2px 0;
}

.stat-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.stat-label {
  font-size: 12px;
  color: var(--text-muted);
  font-weight: 500;
}

.filter-bar {
  position: relative;
  z-index: 1;
  padding: 14px var(--gap-md);
  display: grid;
  grid-template-columns: 1fr 200px;
  gap: var(--gap-md);
  align-items: center;
}

.content-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 18px;
  align-items: start;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
  align-content: start;
}

.model-card {
  padding: 18px;
  cursor: pointer;
  overflow: hidden;
  transition: all var(--transition-base);
}

.model-card:hover {
  box-shadow: var(--shadow-primary);
  transform: translateY(-2px);
}

.model-card.active {
  border-color: rgba(99, 102, 241, 0.25);
  box-shadow: 0 4px 16px rgba(99, 102, 241, 0.12);
}

.card-accent {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  border-radius: var(--radius-lg) var(--radius-lg) 0 0;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--gap-sm);
}

.card-title-area h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-title-area p {
  margin: 4px 0 0;
  color: var(--text-muted);
  font-size: 12px;
}

.meta-row {
  margin-top: var(--gap-sm);
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
  font-size: 12px;
}

.meta-owner {
  color: var(--text-muted);
}

.meta-type {
  color: var(--text-muted);
  font-size: 11px;
  padding: 1px 6px;
  background: var(--primary-bg);
  border-radius: 4px;
}

.description {
  margin: var(--gap-sm) 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.metric-item {
  margin-top: 14px;
}

.metric-line {
  display: flex;
  justify-content: space-between;
  gap: var(--gap-md);
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

.metric-value {
  font-weight: 600;
  color: var(--text-primary);
}

.progress-track {
  width: 100%;
  height: 6px;
  background: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.metrics-row-compact {
  margin-top: var(--gap-md);
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gap-xs);
}

.metric-chip {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 8px;
  background: var(--surface-alt);
  border-radius: var(--radius-sm);
  border: 1px solid #f1f5f9;
}

.chip-label {
  font-size: 10px;
  color: var(--text-muted);
}

.chip-value {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.card-actions {
  margin-top: 14px;
  display: flex;
  gap: var(--gap-xs);
  flex-wrap: wrap;
}

.inline-panel {
  padding: 20px;
  min-height: 480px;
  max-height: calc(100vh - 240px);
  overflow-y: auto;
  overflow-x: hidden;
  position: sticky;
  top: var(--gap-lg);
}

.panel-header-area {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap-md);
  margin-bottom: var(--gap-md);
}

.panel-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-mode-tabs {
  display: flex;
  gap: 2px;
  background: #f1f5f9;
  border-radius: var(--radius-sm);
  padding: 2px;
}

.mode-tab {
  padding: 5px 14px;
  border: none;
  background: transparent;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.mode-tab.active {
  background: var(--surface);
  color: var(--primary);
  box-shadow: var(--shadow-sm);
}

.mode-tab:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

.panel-content {
  animation: panelFadeIn 0.3s ease;
}

@keyframes panelFadeIn {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--gap-xs);
  padding-bottom: 14px;
  border-bottom: 1px solid #f1f5f9;
}

.panel-model-name {
  font-size: 15px;
  color: var(--text-primary);
}

.panel-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--gap-sm);
}

.panel-item {
  background: var(--surface-alt);
  border-radius: var(--radius-md);
  padding: 10px var(--gap-md);
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  border: 1px solid #f1f5f9;
}

.panel-item span {
  color: var(--text-muted);
}

.panel-item strong {
  color: var(--text-primary);
  font-weight: 600;
}

.panel-block {
  margin-top: var(--gap-md);
  padding-top: 14px;
  border-top: 1px solid #f1f5f9;
}

.panel-block h4 {
  margin: 0 0 var(--gap-sm);
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.panel-block p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.7;
  font-size: 13px;
}

.detail-metrics {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: var(--gap-sm);
}

.detail-metric-item {
  display: flex;
  align-items: center;
  gap: var(--gap-sm);
}

.detail-metric-label {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 36px;
}

.detail-progress-track {
  flex: 1;
  height: 6px;
  background: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
}

.detail-progress-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.detail-metric-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  min-width: 52px;
  text-align: right;
}

.eval-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gap-sm);
  margin-top: var(--gap-sm);
}

.eval-card {
  background: var(--surface-alt);
  border-radius: var(--radius-md);
  padding: var(--gap-md);
  display: flex;
  flex-direction: column;
  gap: 6px;
  border: 1px solid #f1f5f9;
  text-align: center;
}

.eval-label {
  font-size: 11px;
  color: var(--text-muted);
}

.eval-value {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
}

.eval-value.primary {
  color: var(--primary);
}

.eval-value.success {
  color: #22c55e;
}

.eval-advice {
  margin-top: 14px;
  padding: var(--gap-md);
  background: var(--primary-bg);
  border-radius: var(--radius-md);
  border: 1px solid rgba(99, 102, 241, 0.08);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.advice-label {
  font-size: 11px;
  color: var(--primary);
  font-weight: 600;
}

.advice-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}

.panel-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gap-md);
  padding: 48px 20px;
  color: var(--text-muted);
}

.panel-empty p {
  margin: 0;
  font-size: 13px;
}

.status-strip {
  position: relative;
  z-index: 1;
  padding: 10px var(--gap-md);
  display: flex;
  align-items: center;
  gap: var(--gap-xs);
  color: var(--text-muted);
  font-size: 12px;
}

@media (max-width: 1280px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .inline-panel {
    max-height: none;
    overflow: visible;
    position: static;
  }
}

@media (max-width: 1024px) {
  .model-management-view {
    padding: var(--gap-lg) var(--gap-md);
  }

  .card-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .model-management-view {
    padding: var(--gap-md);
    gap: var(--gap-md);
  }

  .page-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .header-actions {
    width: 100%;
    flex-wrap: wrap;
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }

  .filter-bar {
    grid-template-columns: 1fr;
  }

  .card-grid {
    grid-template-columns: 1fr;
  }

  .panel-grid {
    grid-template-columns: 1fr;
  }

  .eval-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .model-management-view {
    padding: var(--gap-sm);
  }

  .page-header h1 {
    font-size: 18px;
  }

  .stat-value {
    font-size: 18px;
  }

  .stat-card {
    padding: 14px var(--gap-md);
  }
}
</style>
