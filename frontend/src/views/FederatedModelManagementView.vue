<!-- 联邦模型管理页面 — 统一查看模型版本、状态和评估结果，支持新建和刷新模型 -->
<template>
  <div class="model-management-view">
    <div class="ambient-glow top-left"></div>
    <div class="ambient-glow bottom-right"></div>

    <section class="page-header glass-panel">
      <div class="header-brand">
        <div class="brand-icon">
          <el-icon><Box /></el-icon>
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
      <div class="stat-card glass-panel" v-for="(stat, index) in statsConfig" :key="stat.label">
        <div class="stat-accent" :style="{ background: stat.gradient }"></div>
        <div class="stat-icon-wrap" :style="{ background: stat.iconBg }">
          <el-icon><component :is="statsIcons[index]" /></el-icon>
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
                  <div class="detail-progress-fill" :style="{ width: Math.min(100, activeModel.loss * 50) + '%', background: activeModel.loss > 0.8 ? 'linear-gradient(90deg, var(--danger), var(--danger))' : activeModel.loss > 0.5 ? 'linear-gradient(90deg, var(--warning), var(--warning))' : 'linear-gradient(90deg, var(--success), var(--success))' }"></div>
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
          <div class="runtime-block">
            <div class="runtime-block-head">
              <h4>ACG 运行编排</h4>
              <span class="runtime-badge">{{ getRuntimeMode(activeModel) }}</span>
            </div>

            <div class="runtime-graph" aria-label="模型运行图">
              <div
                v-for="node in getRuntimeNodes(activeModel)"
                :key="node.key"
                class="runtime-node"
                :class="node.state"
              >
                <span class="node-dot"></span>
                <div>
                  <strong>{{ node.label }}</strong>
                  <span>{{ node.description }}</span>
                </div>
              </div>
            </div>

            <div class="runtime-insights">
              <div
                v-for="item in getRuntimeInsights(activeModel)"
                :key="item.label"
                class="runtime-insight"
                :class="item.tone"
              >
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>

            <div class="trace-card">
              <div class="trace-head">
                <span>Trace 快照</span>
                <strong>{{ getTraceStatus(activeModel) }}</strong>
              </div>
              <div class="trace-list">
                <div class="trace-row">
                  <span>ACG</span>
                  <strong>{{ activeModel.federated ? 'federated_model_graph' : 'local_model_graph' }}</strong>
                </div>
                <div class="trace-row">
                  <span>Checkpoint</span>
                  <strong>round-{{ activeModel.trainingRounds }} / v{{ activeModel.version }}</strong>
                </div>
                <div class="trace-row">
                  <span>Guardrail</span>
                  <strong>{{ getGuardrailText(activeModel) }}</strong>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-else class="panel-empty">
          <el-icon><Box /></el-icon>
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
import { Box, Finished, InfoFilled, Plus, Refresh, Search, Timer, TrendCharts, Upload, View } from '@element-plus/icons-vue'
import { federatedModelApi, type ModelInfo } from '@/services/api/federatedModel'

type ModelStatus = 'draft' | 'training' | 'ready' | 'online' | 'offline'
type PanelMode = 'details' | 'evaluation'
type RuntimeNodeState = 'done' | 'running' | 'pending' | 'blocked'
type RuntimeInsightTone = 'primary' | 'success' | 'warning'

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

interface RuntimeNode {
  key: string
  label: string
  description: string
  state: RuntimeNodeState
}

interface RuntimeInsight {
  label: string
  value: string
  tone: RuntimeInsightTone
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

const statsIcons = [Box, Finished, Timer, TrendCharts]

const statsConfig = computed(() => [
  {
    label: '模型总数',
    value: totalCount.value,
    gradient: 'linear-gradient(180deg, var(--primary-color), var(--primary-fade))',
    iconBg: 'var(--primary-fade)'
  },
  {
    label: '在线服务',
    value: onlineCount.value,
    gradient: 'linear-gradient(180deg, var(--success), var(--success-fade))',
    iconBg: 'var(--success-fade)'
  },
  {
    label: '训练中',
    value: trainingCount.value,
    gradient: 'linear-gradient(180deg, var(--warning), var(--warning-fade))',
    iconBg: 'var(--warning-fade)'
  },
  {
    label: '平均精度',
    value: averageAccuracy.value + '%',
    gradient: 'linear-gradient(180deg, var(--primary-hover), var(--primary-fade))',
    iconBg: 'var(--primary-fade)'
  }
])

function getStatusTag(status: ModelStatus): 'info' | 'success' | 'warning' | 'primary' | 'danger' {
  if (status === 'online') return 'primary'
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
  if (status === 'online' || status === 'ready') return 'linear-gradient(180deg, var(--primary-color), var(--primary-fade))'
  if (status === 'training') return 'linear-gradient(180deg, var(--warning), var(--warning-fade))'
  if (status === 'offline') return 'linear-gradient(180deg, var(--danger), var(--danger-fade))'
  return 'linear-gradient(180deg, var(--primary-color), var(--primary-fade))'
}

function getProgressColor(_accuracy: number): string {
  return 'linear-gradient(90deg, var(--primary-color), var(--primary-hover))'
}

function getRuntimeMode(model: ModelCard): string {
  if (model.status === 'training') return 'ACG / 训练中'
  if (model.federated) return 'ACG / 联邦聚合'
  return 'ACG / 本地适配'
}

function getRuntimeNodes(model: ModelCard): RuntimeNode[] {
  const paused = model.status === 'draft' || model.status === 'offline'
  const needsReview = model.loss > 0.7 || model.accuracy < 80

  return [
    {
      key: 'input',
      label: '输入归一',
      description: 'Schema 与 Prompt 版本锁定',
      state: 'done'
    },
    {
      key: 'context',
      label: model.federated ? '联邦上下文' : '本地上下文',
      description: model.federated ? `${model.participants} 个 Agent 聚合` : '本地 Adapter 直连',
      state: paused ? 'pending' : 'done'
    },
    {
      key: 'router',
      label: '模型路由',
      description: model.latency <= 140 ? '低延迟执行路径' : '质量优先执行路径',
      state: model.status === 'training' ? 'running' : paused ? 'pending' : 'done'
    },
    {
      key: 'gate',
      label: '评估门控',
      description: needsReview ? '进入人工复核阈值' : '自动通过质量阈值',
      state: needsReview ? 'blocked' : model.status === 'training' ? 'pending' : 'done'
    },
    {
      key: 'publish',
      label: '发布检查点',
      description: `round-${model.trainingRounds} / v${model.version}`,
      state: model.status === 'online' ? 'running' : model.status === 'ready' ? 'pending' : paused ? 'blocked' : 'pending'
    }
  ]
}

function getRuntimeInsights(model: ModelCard): RuntimeInsight[] {
  const checkpointSpan = Math.max(4, Math.ceil(Math.max(model.trainingRounds, 1) / 8))
  return [
    {
      label: '路由策略',
      value: model.accuracy >= 85 ? '质量优先' : model.latency <= 120 ? '速度优先' : '观察模式',
      tone: model.accuracy >= 85 ? 'success' : 'warning'
    },
    {
      label: '失败回退',
      value: model.federated ? '本地基线' : 'Mock Provider',
      tone: 'primary'
    },
    {
      label: '检查点',
      value: `每 ${checkpointSpan} 轮`,
      tone: model.status === 'training' ? 'warning' : 'success'
    }
  ]
}

function getTraceStatus(model: ModelCard): string {
  if (model.status === 'online') return '实时观测'
  if (model.status === 'training') return '训练追踪'
  if (model.status === 'ready') return '待发布'
  return '暂停'
}

function getGuardrailText(model: ModelCard): string {
  if (model.loss > 0.7) return 'Human Review'
  if (model.accuracy >= 85) return 'Auto Pass'
  return 'Evidence Check'
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
  --primary: var(--primary-color, #3f6b63);
  --primary-light: var(--primary-hover);
  --primary-bg: var(--primary-fade, rgba(63, 107, 99, 0.1));
  --primary-border: var(--border-light, #e3e6df);
  --cyan: var(--accent-color, #6f668f);
  --cyan-dark: var(--accent-color, #6f668f);
  --purple: var(--accent-color, #6f668f);
  --green: var(--success, #3d7656);
  --green-dark: var(--success, #3d7656);
  --pink: var(--warning, #9a7432);
  --amber: var(--warning, #9a7432);
  --surface: var(--bg-card);
  --surface-alt: var(--bg-input, #f1f3ef);
  --border: var(--border-light, #e3e6df);
  --border-hover: var(--border-hover, #cfd6cd);
  --text-primary: var(--text-primary, #1d2422);
  --text-secondary: var(--text-regular, #3d4642);
  --text-muted: var(--text-secondary, #727c76);
  --radius-sm: 8px;
  --radius-md: 8px;
  --radius-lg: 8px;
  --radius-xl: 8px;
  --shadow-sm: var(--shadow-sm, 0 1px 2px rgba(29, 36, 34, 0.04));
  --shadow-md: var(--shadow-md, 0 8px 24px rgba(29, 36, 34, 0.06));
  --shadow-lg: var(--shadow-lg, 0 18px 48px rgba(29, 36, 34, 0.08));
  --shadow-primary: var(--shadow-glow, 0 12px 28px rgba(63, 107, 99, 0.14));
  --transition-fast: 0.15s ease;
  --transition-base: 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);
  --transition-smooth: 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
  --gap-xs: 6px;
  --gap-sm: 10px;
  --gap-md: 16px;
  --gap-lg: 24px;
  --gap-xl: 32px;

  position: relative;
  height: 100%;
  padding: var(--page-padding-y) var(--page-padding-x);
  display: flex;
  flex-direction: column;
  gap: var(--page-gap);
  color: var(--text-primary);
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
  background: transparent;
}

.ambient-glow {
  display: none;
}

.ambient-glow.top-left {
  top: -140px;
  left: -140px;
  background: var(--primary);
}

.ambient-glow.bottom-right {
  right: -140px;
  bottom: -160px;
  background: var(--accent-color);
}

.glass-panel {
  position: relative;
  z-index: 1;
  background: color-mix(in srgb, var(--bg-card) 86%, transparent);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  backdrop-filter: var(--backdrop-blur, blur(20px));
  transition: var(--transition);
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
  border: 1px solid var(--border);
  background: var(--surface-solid);
  color: var(--primary);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.page-header h1 {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 0;
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
  min-height: 86px;
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
  color: var(--primary);
  border: 1px solid var(--border);
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
  align-items: stretch;
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
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.model-card.active {
  border-color: var(--primary-line, rgba(63, 107, 99, 0.22));
  box-shadow: inset 0 0 0 1px var(--primary-line, rgba(63, 107, 99, 0.22));
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
  background: var(--surface-alt);
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
  border: 1px solid var(--border);
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
  height: 100%;
  max-height: none;
  overflow-y: visible;
  overflow-x: hidden;
  position: sticky;
  top: var(--gap-lg);
  align-self: stretch;
  display: flex;
  flex-direction: column;
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
  background: var(--surface-alt);
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
  flex: 1;
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
  border-bottom: 1px solid var(--border);
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
  border: 1px solid var(--border);
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
  border-top: 1px solid var(--border);
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
  background: var(--surface-alt);
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
  border: 1px solid var(--border);
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
  color: var(--success);
}

.eval-advice {
  margin-top: 14px;
  padding: var(--gap-md);
  background: var(--primary-bg);
  border-radius: var(--radius-md);
  border: 1px solid var(--primary-line, rgba(63, 107, 99, 0.22));
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

.runtime-block {
  margin-top: var(--gap-md);
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.runtime-block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap-sm);
  margin-bottom: var(--gap-sm);
}

.runtime-block-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.runtime-badge {
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  background: var(--primary-bg);
  color: var(--primary);
  border: 1px solid var(--primary-line, rgba(63, 107, 99, 0.22));
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.runtime-graph {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--gap-xs);
}

.runtime-node {
  position: relative;
  min-height: 94px;
  padding: 10px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-alt);
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
}

.runtime-node:not(:last-child)::after {
  content: '';
  position: absolute;
  top: 19px;
  right: -7px;
  width: 12px;
  height: 1px;
  background: var(--border-hover);
  z-index: 2;
}

.node-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 2px solid var(--border-hover);
  background: var(--surface);
}

.runtime-node strong {
  display: block;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.3;
}

.runtime-node span:not(.node-dot) {
  display: block;
  margin-top: 4px;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.35;
}

.runtime-node.done .node-dot,
.runtime-node.running .node-dot {
  border-color: var(--green);
  background: var(--green);
}

.runtime-node.running {
  border-color: var(--primary-line, rgba(63, 107, 99, 0.22));
  background: color-mix(in srgb, var(--primary-color) 8%, transparent);
}

.runtime-node.pending .node-dot {
  border-color: var(--amber);
}

.runtime-node.blocked {
  background: rgba(178, 74, 74, 0.08);
  border-color: rgba(178, 74, 74, 0.22);
}

.runtime-node.blocked .node-dot {
  border-color: var(--danger);
  background: var(--danger);
}

.runtime-insights {
  margin-top: var(--gap-sm);
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--gap-xs);
}

.runtime-insight {
  padding: 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--surface-alt);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.runtime-insight span {
  color: var(--text-muted);
  font-size: 11px;
}

.runtime-insight strong {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 700;
}

.runtime-insight.success {
  border-color: rgba(61, 118, 86, 0.24);
}

.runtime-insight.warning {
  border-color: rgba(154, 116, 50, 0.26);
}

.runtime-insight.primary {
  border-color: var(--primary-line, rgba(63, 107, 99, 0.22));
}

.trace-card {
  margin-top: var(--gap-sm);
  padding: var(--gap-md);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--surface-solid);
}

.trace-head,
.trace-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap-sm);
}

.trace-head {
  padding-bottom: 10px;
  border-bottom: 1px solid var(--border);
}

.trace-head span,
.trace-row span {
  color: var(--text-muted);
  font-size: 12px;
}

.trace-head strong {
  color: var(--primary);
  font-size: 12px;
}

.trace-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.trace-row strong {
  color: var(--text-primary);
  font-size: 12px;
  font-weight: 600;
  text-align: right;
}

.panel-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--gap-md);
  padding: 48px 20px;
  color: var(--text-muted);
}

.panel-empty .el-icon {
  width: 48px;
  height: 48px;
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--primary);
  background: var(--surface-solid);
  font-size: 24px;
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

  .runtime-graph {
    grid-template-columns: 1fr;
  }

  .runtime-node {
    min-height: auto;
  }

  .runtime-node:not(:last-child)::after {
    display: none;
  }

  .runtime-insights {
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
