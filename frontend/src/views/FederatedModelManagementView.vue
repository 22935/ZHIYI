<template>
  <div class="model-management-view">
    <div class="ambient-glow top-left"></div>
    <div class="ambient-glow bottom-right"></div>

    <section class="page-header glass-panel">
      <div>
        <h1>模型管理</h1>
        <p>统一查看联邦模型版本、状态和评估结果，不再弹出新界面。</p>
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
      <div class="stat-card glass-panel">
        <div class="label">模型总数</div>
        <div class="value">{{ totalCount }}</div>
      </div>
      <div class="stat-card glass-panel">
        <div class="label">在线服务</div>
        <div class="value">{{ onlineCount }}</div>
      </div>
      <div class="stat-card glass-panel">
        <div class="label">训练中</div>
        <div class="value">{{ trainingCount }}</div>
      </div>
      <div class="stat-card glass-panel">
        <div class="label">平均精度</div>
        <div class="value">{{ averageAccuracy }}%</div>
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
        <article v-for="model in filteredModels" :key="model.id" class="model-card glass-panel">
          <div class="card-head">
            <div>
              <h3>{{ model.name }}</h3>
              <p>{{ model.scene }} · v{{ model.version }}</p>
            </div>
            <el-tag :type="getStatusTag(model.status)">{{ getStatusText(model.status) }}</el-tag>
          </div>

          <div class="meta-row">
            <el-tag v-if="model.federated" size="small" type="primary">联邦</el-tag>
            <span>负责人：{{ model.owner }}</span>
          </div>

          <p class="description">{{ model.description }}</p>

          <div class="metric-item">
            <div class="metric-line">
              <span>精度</span>
              <span>{{ model.accuracy.toFixed(1) }}%</span>
            </div>
            <el-progress :percentage="Number(model.accuracy.toFixed(1))" :stroke-width="8" />
          </div>

          <div class="metric-line">
            <span>平均延迟</span>
            <span>{{ model.latency }}ms</span>
          </div>
          <div class="metric-line">
            <span>最近更新时间</span>
            <span>{{ formatTime(model.updatedAt) }}</span>
          </div>

          <div class="card-actions">
            <el-button size="small" @click="showDetails(model)">
              <el-icon><View /></el-icon>
              详情
            </el-button>
            <el-button size="small" @click="evaluateModel(model)">
              <el-icon><TrendCharts /></el-icon>
              评估
            </el-button>
            <el-button size="small" type="primary" @click="deployModel(model)">
              <el-icon><Upload /></el-icon>
              部署
            </el-button>
          </div>
        </article>

        <el-empty v-if="!loading && filteredModels.length === 0" description="没有匹配的模型" />
      </div>

      <aside class="inline-panel glass-panel">
        <h3 class="panel-title">同页信息面板</h3>
        <p class="panel-subtitle">点击左侧模型的“详情/评估”在此处展示，不弹窗。</p>

        <div v-if="activeModel" class="panel-content">
          <div class="panel-head">
            <strong>{{ activeModel.name }}</strong>
            <el-tag :type="getStatusTag(activeModel.status)">{{ getStatusText(activeModel.status) }}</el-tag>
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
              <span>最近更新</span>
              <strong>{{ formatTime(activeModel.updatedAt) }}</strong>
            </div>
          </div>

          <div v-if="panelMode === 'details'" class="panel-block">
            <h4>模型说明</h4>
            <p>{{ activeModel.description }}</p>
          </div>

          <div v-if="panelMode === 'evaluation'" class="panel-block">
            <h4>评估结果</h4>
            <div class="eval-item">
              <span>综合评分</span>
              <strong>{{ evaluation.score }}</strong>
            </div>
            <div class="eval-item">
              <span>推理吞吐</span>
              <strong>{{ evaluation.qps }} QPS</strong>
            </div>
            <div class="eval-item">
              <span>稳定性</span>
              <strong>{{ evaluation.stability }}%</strong>
            </div>
            <div class="eval-item">
              <span>建议</span>
              <strong>{{ evaluation.advice }}</strong>
            </div>
          </div>
        </div>

        <el-empty v-else description="请选择模型查看详情或评估" />
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
}

interface EvaluationState {
  score: string
  qps: string
  stability: string
  advice: string
}

const makeDefaultModels = (): ModelCard[] => [
  {
    id: 'fed-chat-1',
    name: '联邦对话模型',
    scene: '智能问答',
    version: '1.3.2',
    status: 'online',
    federated: true,
    owner: '平台算法组',
    accuracy: 92.6,
    latency: 128,
    updatedAt: new Date().toISOString(),
    description: '面向业务知识问答的联邦模型，支持多节点增量更新。'
  },
  {
    id: 'fed-risk-1',
    name: '联邦风控模型',
    scene: '异常检测',
    version: '0.9.8',
    status: 'training',
    federated: true,
    owner: '风控数据组',
    accuracy: 88.2,
    latency: 96,
    updatedAt: new Date(Date.now() - 35 * 60 * 1000).toISOString(),
    description: '融合多方特征进行风险评分，当前处于新一轮联合训练阶段。'
  },
  {
    id: 'baseline-doc-1',
    name: '文档分类基线模型',
    scene: '文本分类',
    version: '2.1.0',
    status: 'ready',
    federated: false,
    owner: 'NLP 工程组',
    accuracy: 90.4,
    latency: 82,
    updatedAt: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
    description: '用于文档自动分类的基线版本，可作为联邦蒸馏教师模型。'
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
        accuracy: perf?.accuracy ?? 85,
        latency: perf?.speed ?? 120,
        updatedAt: new Date().toISOString(),
        description: `来自 ${groupKey} 组的联邦模型。`
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
  position: relative;
  height: 100%;
  min-height: 0;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: var(--text-primary);
  overflow-y: auto;
  overflow-x: hidden;
  box-sizing: border-box;
}

.ambient-glow {
  position: absolute;
  width: 320px;
  height: 320px;
  border-radius: 50%;
  filter: blur(74px);
  opacity: 0.18;
  pointer-events: none;
}

.ambient-glow.top-left {
  top: -120px;
  left: -120px;
  background: #5b8ff9;
}

.ambient-glow.bottom-right {
  right: -120px;
  bottom: -130px;
  background: #36cfc9;
}

.glass-panel {
  position: relative;
  z-index: 1;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.75);
  border-radius: 14px;
  box-shadow: 0 10px 28px rgba(15, 35, 95, 0.06);
}

.page-header {
  padding: 16px 18px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.page-header h1 {
  margin: 0;
  font-size: 24px;
}

.page-header p {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.stats-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  padding: 14px 16px;
}

.stat-card .label {
  font-size: 13px;
  color: var(--text-secondary);
}

.stat-card .value {
  margin-top: 6px;
  font-size: 22px;
  font-weight: 700;
}

.filter-bar {
  position: relative;
  z-index: 1;
  padding: 12px;
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 10px;
}

.content-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1.6fr 1fr;
  gap: 12px;
  align-items: start;
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  align-content: start;
}

.model-card {
  padding: 14px;
}

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.card-head h3 {
  margin: 0;
  font-size: 18px;
}

.card-head p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.meta-row {
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}

.description {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.metric-item {
  margin-top: 12px;
}

.metric-line {
  margin-top: 8px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 13px;
}

.card-actions {
  margin-top: 14px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.inline-panel {
  padding: 14px;
  min-height: 420px;
  max-height: calc(100vh - 220px);
  overflow-y: auto;
  overflow-x: hidden;
}

.panel-title {
  margin: 0;
}

.panel-subtitle {
  color: var(--text-secondary);
  font-size: 13px;
  margin: 8px 0 14px;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.panel-grid {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.panel-item {
  background: rgba(91, 143, 249, 0.08);
  border-radius: 10px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.panel-item span {
  color: var(--text-secondary);
}

.panel-block {
  margin-top: 14px;
}

.panel-block h4 {
  margin: 0 0 8px;
}

.panel-block p {
  margin: 0;
  color: var(--text-secondary);
  line-height: 1.6;
  font-size: 13px;
}

.eval-item {
  padding: 9px 0;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 13px;
}

.status-strip {
  position: relative;
  z-index: 1;
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

@media (max-width: 1200px) {
  .stats-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }

  .inline-panel {
    max-height: none;
    overflow: visible;
  }
}

@media (max-width: 760px) {
  .model-management-view {
    padding: 12px;
  }

  .page-header {
    flex-direction: column;
  }

  .header-actions {
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
}
</style>
