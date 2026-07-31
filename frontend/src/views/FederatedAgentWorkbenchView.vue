<!-- 联邦智能体工作台页面 — 多专业体协同编排、任务规划、知识融合，支持演示/API 模式和普通/专业用户模式 -->
<template>
  <section class="agent-workbench">
    <header class="workbench-header">
      <div class="brand-area">
        <div class="brand-logo">
          <el-icon><Connection /></el-icon>
        </div>
        <div>
          <h1>联邦智能体工作台</h1>
          <p>多专业体协同编排 · 任务规划 · 知识融合</p>
        </div>
      </div>

      <div class="header-tools">
        <label class="mode-toggle" :class="{ api: !isDemoMode }">
          <span>演示</span>
          <button type="button" @click="toggleDemoMode">
            <span class="toggle-knob"></span>
          </button>
          <span>API</span>
        </label>
        <div class="mode-switch" aria-label="模式切换">
          <button type="button" :class="{ active: currentMode === 'normal' }" @click="toggleUserMode('normal')">普通用户模式</button>
          <button :class="{ active: currentMode === 'pro' }" type="button" @click="toggleUserMode('pro')">专业用户模式</button>
        </div>
        <div class="status-chip online">
          <span></span>
          联邦网络：已连接
        </div>
        <div class="status-chip">模型版本：v2.3.1</div>
        <button class="square-button" type="button" aria-label="通知">
          <el-icon><Bell /></el-icon>
        </button>
        <button class="profile-button" type="button">
          <span class="avatar"></span>
          <strong>张明</strong>
        </button>
      </div>
    </header>

    <div class="workspace-grid">
      <aside class="left-rail">
        <section class="panel profile-panel">
          <div class="panel-title">
            <span>我的专业体</span>
            <button type="button">管理</button>
          </div>
          <div
            v-for="expert in experts" :key="expert.id"
            class="expert-card"
            :class="{ active: activeExpert === expert.id }"
            @click="activeExpert = expert.id"
          >
            <div class="expert-avatar" :class="expert.cls">{{ expert.avatar }}</div>
            <div>
              <strong>{{ expert.label }}</strong>
              <span>{{ expert.sub }}</span>
            </div>
          </div>
        </section>

        <section class="panel">
          <div class="panel-title">
            <span>核心能力模块</span>
          </div>
          <div class="module-list">
            <div v-for="module in capabilityModules" :key="module.name" class="module-item">
              <div class="module-icon" :class="module.tone">{{ module.short }}</div>
              <div>
                <strong>{{ module.name }}</strong>
                <span>{{ module.desc }}</span>
              </div>
              <em>{{ module.score }}</em>
            </div>
          </div>
        </section>

        <section class="panel support-panel">
          <div class="panel-title">
            <span>平台支持</span>
          </div>
          <div class="support-grid">
            <div v-for="item in platformSupports" :key="item.label">
              <strong>{{ item.value }}</strong>
              <span>{{ item.label }}</span>
            </div>
          </div>
        </section>

        <section class="panel node-panel">
          <div class="panel-title">
            <span>联邦节点状态</span>
          </div>
          <div class="node-row" v-for="node in nodes" :key="node.name">
            <span class="node-dot" :class="node.state"></span>
            <div>
              <strong>{{ node.name }}</strong>
              <small>{{ node.desc }}</small>
            </div>
            <em>{{ node.latency }}</em>
          </div>
        </section>
      </aside>

      <main class="task-board">
        <section class="task-hero panel">
          <div class="task-copy">
            <span class="eyebrow">当前任务</span>
            <h2>起草一份软件开发合同</h2>
            <p>由法律顾问、需求分析师、文档专家共同完成条款骨架生成与风险校验。</p>
            <div class="task-tags">
              <span>民商事领域</span>
              <span>合同法务</span>
              <span>合同审查</span>
              <span>交付物：正式合同草案</span>
            </div>
          </div>
          <div class="progress-card">
            <span>任务进度</span>
            <strong>{{ currentProgress }}%</strong>
            <div class="progress-track">
              <div :style="{ width: currentProgress + '%' }"></div>
            </div>
            <small>{{ currentProgress >= 100 ? '任务已完成' : '预计 ' + Math.max(1, Math.ceil((100 - currentProgress) / 2)) + ' 分钟后完成' }}</small>
          </div>
        </section>

        <section class="panel flow-panel">
          <div class="toolbar">
            <nav class="view-tabs">
              <button :class="{ active: activeFlowTab === 'flow' }" type="button" @click="activeFlowTab = 'flow'">流程视图</button>
              <button :class="{ active: activeFlowTab === 'chain' }" type="button" @click="activeFlowTab = 'chain'">思维链视图</button>
              <button :class="{ active: activeFlowTab === 'gantt' }" type="button" @click="activeFlowTab = 'gantt'">甘特视图</button>
              <button :class="{ active: activeFlowTab === 'compare' }" type="button" @click="activeFlowTab = 'compare'">对比视图</button>
            </nav>
            <button class="outline-button" type="button" @click="handleExportReport">导出报告</button>
          </div>

          <div class="flow-lane">
            <article
              v-for="step in flowSteps"
              :key="step.no"
              class="flow-step"
              :class="[step.state, { active: step.no === selectedStepNo }]"
              @click="selectFlowStep(step.no)"
            >
              <span class="step-no">{{ step.no }}</span>
              <strong>{{ step.title }}</strong>
              <small>{{ step.desc }}</small>
            </article>
          </div>

          <div class="flow-insight-board">
            <article class="flow-insight-card is-primary">
              <span class="insight-label">{{ flowTabSummary.label }}</span>
              <h3>{{ flowTabSummary.title }}</h3>
              <p>{{ flowTabSummary.desc }}</p>
              <div class="insight-meta-row">
                <span>Step {{ selectedStepNo }}</span>
                <strong>{{ selectedStepInfo.title }}</strong>
              </div>
            </article>

            <article class="flow-insight-card">
              <span class="insight-label">质量闸门</span>
              <div class="gate-list">
                <div v-for="gate in qualityGates" :key="gate.label" class="gate-item" :class="gate.tone">
                  <span>{{ gate.label }}</span>
                  <strong>{{ gate.value }}</strong>
                </div>
              </div>
            </article>

            <article class="flow-insight-card">
              <span class="insight-label">交付清单</span>
              <div class="delivery-list">
                <div v-for="item in deliveryItems" :key="item.title">
                  <strong>{{ item.title }}</strong>
                  <span>{{ item.desc }}</span>
                </div>
              </div>
            </article>
          </div>
        </section>

        <section class="detail-grid">
          <article class="panel detail-card">
            <div class="section-head">
              <div>
                <span class="eyebrow">Step {{ selectedStepNo }}</span>
                <h3>当前步骤详情：{{ selectedStepInfo.title }}</h3>
              </div>
              <span class="status-badge" :class="selectedStepInfo.state">{{ selectedStepInfo.state === 'running' ? '执行中' : selectedStepInfo.state === 'done' ? '已完成' : '等待中' }}</span>
            </div>
            <dl class="detail-meta">
              <div>
                <dt>执行体</dt>
                <dd>{{ activeExpert === 'lawyer' ? '法律顾问' : activeExpert === 'analyst' ? '需求分析师' : '文档专家' }} + 文档专家</dd>
              </div>
              <div>
                <dt>置信度</dt>
                <dd>{{ currentProgress }}%</dd>
              </div>
              <div>
                <dt>风险扫描</dt>
                <dd>{{ selectedStepInfo.state === 'done' ? '已通过' : selectedStepInfo.state === 'running' ? '已发现 3 项待确认条款' : '待执行' }}</dd>
              </div>
            </dl>
            <div class="cot-list">
              <div v-for="item in reasoningItems" :key="item.title">
                <span></span>
                <div>
                  <strong>{{ item.title }}</strong>
                  <p>{{ item.desc }}</p>
                </div>
              </div>
            </div>
          </article>

          <article class="panel preview-card">
            <div class="section-head compact">
              <h3>生成内容预览</h3>
              <span>草案 v0.7</span>
            </div>
            <div class="document-preview">
              <h4>软件开发合同</h4>
              <p v-for="(line, i) in documentPreview" :key="i">{{ line }}</p>
            </div>
          </article>
        </section>

        <section class="panel timeline-panel">
          <div class="section-head compact">
            <h3>执行时间线</h3>
            <span>自动记录</span>
          </div>
          <div class="timeline">
            <div v-for="item in timelineItems" :key="item.time" class="timeline-item">
              <time>{{ item.time }}</time>
              <div>
                <strong>{{ item.title }}</strong>
                <span>{{ item.desc }}</span>
              </div>
            </div>
          </div>
        </section>

      <section class="command-bar panel">
          <span class="plus-sign">
            <el-icon><Plus /></el-icon>
          </span>
          <input
            id="workbench-command"
            name="workbench-command"
            v-model="commandText"
            :disabled="isGenerating"
            aria-label="任务指令"
            @keyup.enter="handleSend"
          />
          <button type="button" :disabled="isGenerating" @click="handleSend">
            {{ isGenerating ? '执行中...' : '发送' }}
          </button>
        </section>
      </main>

      <aside v-if="false" class="right-rail">
        <section class="panel assistant-panel">
          <div class="section-head compact">
            <h3>数字人助手</h3>
            <span class="status-badge online">在线</span>
          </div>
          <div class="assistant-avatar-stage">
            <DigitalHuman
              v-if="digitalHumanRoleId"
              :role-id="digitalHumanRoleId"
              :style="'realistic'"
              transparent
            />
            <div v-else class="digital-human-preparing">正在连接数字人...</div>
          </div>
          <strong class="assistant-name">{{ digitalHumanRoleName }} · 张明</strong>
          <p>正在协助梳理合同关键条款，重点关注付款节点、知识产权与违约责任。</p>
          <div class="voice-wave" aria-hidden="true">
            <span v-for="bar in 12" :key="bar"></span>
          </div>
          <button class="assistant-action" type="button" @click="goToVoiceChat">语音说明</button>
        </section>

        <section class="panel source-panel">
          <div class="section-head compact">
            <h3>相关数据源</h3>
            <span>6 个</span>
          </div>
          <div class="source-list">
            <div v-for="source in dataSources" :key="source.name">
              <span class="source-icon">{{ source.type }}</span>
              <div>
                <strong>{{ source.name }}</strong>
                <small>{{ source.meta }}</small>
              </div>
              <em>{{ source.score }}</em>
            </div>
          </div>
        </section>

        <section class="panel recommendation-panel">
          <div class="section-head compact">
            <h3>智能推荐</h3>
            <span>实时</span>
          </div>
          <nav class="mini-tabs">
            <button :class="{ active: activeRecommendTab === 'clause' }" type="button" @click="selectRecommendTab('clause')">条款</button>
            <button :class="{ active: activeRecommendTab === 'risk' }" type="button" @click="selectRecommendTab('risk')">风险</button>
            <button :class="{ active: activeRecommendTab === 'case' }" type="button" @click="selectRecommendTab('case')">案例</button>
          </nav>
          <RecommendationPanel
            title="工作流建议"
            subtitle="基于当前任务和标签生成"
            :items="recommendations"
            :loading="recommendationLoading"
            refreshable
            @refresh="loadWorkbenchRecommendations"
            @select="applyWorkbenchRecommendation"
          />
        </section>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Bell, Connection, Plus } from '@element-plus/icons-vue'
import DigitalHuman from '@/components/DigitalHuman.vue'
import RecommendationPanel from '@/components/RecommendationPanel.vue'
import { useDigitalHumanRole } from '@/composables/useDigitalHumanRole'
import { agentosApi, type WorkflowRun, type WorkflowStep } from '@/services/api/agentos'
import { federatedModelApi } from '@/services/api/federatedModel'
import { recommendationApi, type RecommendationItem } from '@/services/api/recommendation'
import { useDebounce } from '@/composables/useDebounce'

const { digitalHumanRoleId, digitalHumanRoleName } = useDigitalHumanRole()
const router = useRouter()

function goToVoiceChat() {
  router.push('/voice-chat')
}

// ---- 模式 ----
const isDemoMode = ref(true)
const isGenerating = ref(false)
const currentProgress = ref(75)
const currentStepNo = ref(3)

// ---- 用户模式 ----
const currentMode = ref<'normal' | 'pro'>('pro')

function toggleUserMode(mode: 'normal' | 'pro') {
  currentMode.value = mode
}

// ---- 专业体 ----
const activeExpert = ref<'lawyer' | 'analyst' | 'writer'>('lawyer')
const experts = [
  { id: 'lawyer' as const, label: '法律顾问', sub: '合同法务 · 在线', avatar: '律', cls: 'lawyer' },
  { id: 'analyst' as const, label: '需求分析师', sub: '业务建模 · 在线', avatar: '需', cls: 'pm' },
  { id: 'writer' as const, label: '文档专家', sub: '格式审校 · 待命', avatar: '文', cls: 'writer' }
]

const capabilityModules = ref([
  { short: '需', name: '需求理解', desc: '识别业务目标与边界条件', score: '98%', tone: 'blue' },
  { short: '法', name: '法律适配', desc: '匹配合同法规与行业惯例', score: '92%', tone: 'green' },
  { short: '风', name: '风险审查', desc: '定位履约、付款与权属风险', score: '89%', tone: 'orange' },
  { short: '文', name: '文档生成', desc: '输出结构化合同文本', score: '96%', tone: 'purple' }
])

const platformSupports = [
  { value: '12', label: '在线专业体' },
  { value: '43', label: '知识库' },
  { value: '8.7k', label: '法规条目' },
  { value: '99.8%', label: '服务可用性' }
]

const nodes = ref([
  { name: '北京节点', desc: '法律知识增强', latency: '22ms', state: 'online' },
  { name: '上海节点', desc: '合同模板索引', latency: '31ms', state: 'online' },
  { name: '深圳节点', desc: '企业案例检索', latency: '46ms', state: 'busy' }
])

// ---- 流程步骤 ----
type FlowState = 'done' | 'running' | 'waiting'
interface FlowStep { no: string; title: string; desc: string; state: FlowState }
const initialFlowSteps: FlowStep[] = [
  { no: '01', title: '任务理解', desc: '解析目标与交付物', state: 'done' },
  { no: '02', title: '资料检索', desc: '抽取法规与模板', state: 'done' },
  { no: '03', title: '条款结构生成', desc: '生成合同骨架', state: 'running' },
  { no: '04', title: '风险审校', desc: '补充约束与例外', state: 'waiting' },
  { no: '05', title: '正式草案输出', desc: '合并与格式化', state: 'waiting' }
]
const flowSteps = ref<FlowStep[]>(structuredClone(initialFlowSteps))
const selectedStepNo = ref('03')

// ---- 思维链 ----
type FlowTab = 'flow' | 'chain' | 'gantt' | 'compare'
const activeFlowTab = ref<FlowTab>('flow')

const flowTabSummary = computed(() => {
  const map: Record<FlowTab, { label: string; title: string; desc: string }> = {
    flow: {
      label: '协同编排',
      title: '法律顾问、需求分析师、文档专家并行推进',
      desc: '当前流程聚焦条款骨架生成，正在把需求边界、法规依据和合同文本结构同步到同一份草案。'
    },
    chain: {
      label: '思维链摘要',
      title: '从交付物定义到风险校验逐层收敛',
      desc: '系统先确认任务目标，再检索法规与模板，随后生成条款结构并进入风险审核，避免直接生成失控文本。'
    },
    gantt: {
      label: '节奏规划',
      title: '核心生成阶段已进入中后段',
      desc: '资料检索已完成，条款结构生成正在执行；后续风险审核和正式草案输出会承接当前结果。'
    },
    compare: {
      label: '对比视图',
      title: '严谨版与客户友好版并行保留差异',
      desc: '系统会保留法律严谨表述，同时准备客户可读版本，便于后续合并、解释和人工确认。'
    }
  }
  return map[activeFlowTab.value]
})

const qualityGates = [
  { label: '验收标准', value: '待补强', tone: 'warning' },
  { label: '知识产权', value: '已定位', tone: 'success' },
  { label: '付款边界', value: '复核中', tone: 'info' },
  { label: '违约责任', value: '待确认', tone: 'warning' }
]

const deliveryItems = [
  { title: '条款骨架', desc: '5 个核心模块已成型' },
  { title: '风险标注', desc: '付款、验收、权属重点校验' },
  { title: '草案预览', desc: '同步生成正式合同文本' }
]

const reasoningItems = ref([
  { title: '提取合同主体与交易背景', desc: '识别甲乙双方、开发范围、交付方式与付款结构。' },
  { title: '匹配软件开发合同常用条款', desc: '引用项目范围、验收标准、知识产权、保密与违约责任模块。' },
  { title: '生成双版本条款骨架', desc: '同时输出律师严谨版与客户友好版，供下一步对比合并。' }
])

const timelineItems = ref([
  { time: '10:21', title: '任务创建', desc: '用户发起软件开发合同起草任务。' },
  { time: '10:24', title: '完成资料检索', desc: '命中 21 条法规、8 份模板、5 个相似项目。' },
  { time: '10:28', title: '进入条款结构生成', desc: '法律顾问与文档专家正在并行生成。' }
])

const documentPreview = ref([
  '一、项目范围：乙方根据甲方需求完成系统设计、开发、测试及交付。',
  '二、交付节点：需求确认、原型评审、阶段验收、最终上线。',
  '三、知识产权：除双方另有约定，定制开发成果归甲方所有。',
  '四、保密义务：双方对技术资料、业务数据及交易信息承担保密责任。'
])

// ---- 右侧面板 ----
const dataSources = ref([
  { type: '法', name: '民法典合同编', meta: '国家法律法规数据库', score: '98' },
  { type: '模', name: '软件开发合同模板库', meta: '企业常用模板 128 份', score: '94' },
  { type: '例', name: '交付验收争议案例', meta: '近三年相关裁判摘要', score: '87' },
  { type: '库', name: '知识产权条款库', meta: '源代码与著作权专题', score: '91' }
])

type RecommendTab = 'clause' | 'risk' | 'case'
const activeRecommendTab = ref<RecommendTab>('clause')
const recommendations = ref<RecommendationItem[]>([])
const recommendationLoading = ref(false)

function selectRecommendTab(tab: RecommendTab) {
  activeRecommendTab.value = tab
  void loadWorkbenchRecommendations()
}

function applyWorkbenchRecommendation(item: RecommendationItem) {
  commandText.value = item.text
}

async function loadWorkbenchRecommendations() {
  recommendationLoading.value = true
  try {
    recommendations.value = await recommendationApi.getContextualRecommendations({
      roleName: activeExpert.value === 'lawyer' ? '律师' : activeExpert.value === 'analyst' ? '需求分析师' : '文档专家',
      scope: 'workbench',
      scene: activeRecommendTab.value,
      currentInput: commandText.value,
      currentOutput: documentPreview.value.join('\n'),
      conversationHistory: commandHistory.value.slice(0, 5)
    })
  } catch (error) {
    console.warn('加载工作台推荐失败', error)
    recommendations.value = []
  } finally {
    recommendationLoading.value = false
  }
}

// ---- 命令栏 ----
const commandText = ref('请重点补充验收标准、违约责任和源代码交付约定')
const commandHistory = ref<string[]>([])
const sessionId = ref('')
const workflowRunId = ref('')
const debouncedCommandText = useDebounce(commandText, 400)

function addToHistory(text: string) {
  commandHistory.value.unshift(text)
  if (commandHistory.value.length > 10) commandHistory.value.pop()
}

function selectFlowStep(no: string) {
  selectedStepNo.value = no
}

const selectedStepInfo = computed(() => {
  return flowSteps.value.find(s => s.no === selectedStepNo.value) || flowSteps.value[0]
})

// ---- Demo 模式 ----
async function runDemoMode() {
  isGenerating.value = true
  addToHistory(commandText.value)
  flowSteps.value = structuredClone(initialFlowSteps)
  currentProgress.value = 75
  currentStepNo.value = 3

  // Step 03 running → done
  await new Promise(r => setTimeout(r, 1200))
  currentProgress.value = 84
  flowSteps.value[2].state = 'done'
  // Step 04 waiting → running
  flowSteps.value[3].state = 'running'
  selectedStepNo.value = '04'
  currentStepNo.value = 4
  reasoningItems.value = [
    { title: '扫描合同骨架风险点', desc: '已识别付款节点、验收标准、知识产权归属 3 项潜在风险条款。' },
    { title: '对比行业惯例与裁判规则', desc: '引用近三年软件开发合同争议裁判摘要，定位高频争议焦点。' },
    { title: '生成约束建议与例外条款', desc: '为每一步骤补充违约边界、宽限期与免责条件。' }
  ]

  await new Promise(r => setTimeout(r, 1000))
  currentProgress.value = 91
  flowSteps.value[3].state = 'done'
  // Step 05 waiting → running
  flowSteps.value[4].state = 'running'
  selectedStepNo.value = '05'
  currentStepNo.value = 5
  reasoningItems.value = [
    { title: '合并律师版与客户版差异', desc: '同步合并语义相同的条款，保留双版本中差异化的表述。' },
    { title: '应用格式模板', desc: '按正式合同格式排版，添加页眉、页脚、签署栏。' },
    { title: '生成最终草案', desc: '输出完整合同草案，标记待确认条款 3 项。' }
  ]
  documentPreview.value = [
    '一、项目范围：乙方根据甲方需求完成系统设计、开发、测试及交付，具体需求以附件一《需求规格说明书》为准。',
    '二、交付节点：需求确认（签约后 5 日）、原型评审（签约后 20 日）、阶段验收（签约后 45 日）、最终上线（签约后 90 日）。',
    '三、知识产权：定制开发成果（含源代码、文档、接口设计）的知识产权归甲方所有。',
    '四、保密义务：双方对技术资料、业务数据及交易信息承担保密责任，保密期限为合同终止后 3 年。',
    '五、违约责任：逾期交付每日按合同总价 0.05% 计收违约金，上限不超过合同总价 20%。'
  ]
  timelineItems.value.push({ time: new Date().toLocaleTimeString('zh-CN', { hour12: false }), title: '进入风险审校', desc: '已完成 3 项风险条款扫描。' })

  await new Promise(r => setTimeout(r, 800))
  currentProgress.value = 100
  flowSteps.value[4].state = 'done'
  selectedStepNo.value = '05'
  timelineItems.value.push({ time: new Date().toLocaleTimeString('zh-CN', { hour12: false }), title: '正式草案输出完成', desc: '合同草案已生成，含 5 大条款模块。' })
  nodes.value[2].state = 'online'
  nodes.value[2].latency = '28ms'

  isGenerating.value = false
  ElMessage.success('Demo 联邦任务执行完成')
}

// ---- API 模式 ----
function toFlowState(status: WorkflowStep['status']): FlowState {
  if (status === 'completed') return 'done'
  if (status === 'running' || status === 'retrying') return 'running'
  if (status === 'failed' || status === 'cancelled') return 'waiting'
  return 'waiting'
}

function updateWorkbenchFromRun(run: WorkflowRun) {
  workflowRunId.value = run.runId
  sessionId.value = run.runId
  flowSteps.value = run.steps.map((step, index) => ({
    no: String(index + 1).padStart(2, '0'),
    title: step.name || step.stepId,
    desc: step.error || step.capability || step.agentName,
    state: toFlowState(step.status)
  }))

  const activeIndex = run.currentStepId
    ? run.steps.findIndex(step => step.stepId === run.currentStepId)
    : run.steps.findIndex(step => step.status !== 'completed')
  const selectedIndex = activeIndex >= 0 ? activeIndex : Math.max(run.steps.length - 1, 0)
  selectedStepNo.value = String(selectedIndex + 1).padStart(2, '0')
  currentStepNo.value = selectedIndex + 1

  const completedCount = run.steps.filter(step => step.status === 'completed').length
  currentProgress.value = run.steps.length
    ? Math.round((completedCount / run.steps.length) * 100)
    : 0

  reasoningItems.value = run.trace.slice(-5).map(event => ({
    title: event.eventType,
    desc: event.observation || event.agentName || event.stepId || ''
  }))
  timelineItems.value = run.trace.slice(-6).map(event => ({
    time: event.createdAt ? new Date(event.createdAt).toLocaleTimeString('zh-CN', { hour12: false }) : '',
    title: event.eventType,
    desc: event.observation || ''
  }))

  const finalAnswer = run.output?.final_answer
  if (finalAnswer) {
    documentPreview.value = String(finalAnswer).split('\n').filter(line => line.trim())
  } else {
    const stepSummaries = run.steps
      .map(step => step.output?.summary || step.output?.case_summary || step.output?.risk_summary || step.output?.legal_basis)
      .filter(Boolean)
      .map(String)
    if (stepSummaries.length > 0) {
      documentPreview.value = stepSummaries
    }
  }
}

async function runApiMode() {
  isGenerating.value = true
  addToHistory(commandText.value)
  flowSteps.value = structuredClone(initialFlowSteps)

  try {
    const [workflowRes, modelStatusRes] = await Promise.allSettled([
      agentosApi.startWorkflow({
        title: `Workbench任务：${commandText.value.slice(0, 24)}`,
        domain: 'legal',
        intent: 'contract_review',
        reviewMode: 'human_in_loop',
        input: {
          source: 'workbench',
          activeExpert: activeExpert.value,
          caseText: commandText.value
        }
      }),
      federatedModelApi.getOptimizationStatus()
    ])

    if (workflowRes.status === 'fulfilled') {
      updateWorkbenchFromRun(workflowRes.value.run)
      ElMessage.success('Workflow 已发起')
    } else {
      ElMessage.warning('Workflow 发起失败，请检查 AgentOS Core 服务')
    }

    if (modelStatusRes.status === 'fulfilled' && modelStatusRes.value?.success) {
      const statusData = modelStatusRes.value.data || modelStatusRes.value
      if (statusData?.nodes) {
        nodes.value = statusData.nodes.map((n: any, i: number) => ({
          name: n.name || `节点 ${i + 1}`,
          desc: n.description || n.desc || '',
          latency: n.latency || `${20 + i * 10}ms`,
          state: n.state || n.status || 'online'
        }))
      }
    }
  } catch {
    ElMessage.warning('API 调用失败，请检查后端服务是否可用')
  } finally {
    isGenerating.value = false
  }
}

async function handleSend() {
  if (!commandText.value.trim()) return
  if (isDemoMode.value) {
    await runDemoMode()
  } else {
    await runApiMode()
  }
  void loadWorkbenchRecommendations()
}

async function handleExportReport() {
  if (isDemoMode.value) {
    ElMessage.info('演示模式下导出功能暂不可用，请切换到 API 模式')
  } else {
    ElMessage.info('报告导出功能开发中')
  }
}

function toggleDemoMode() {
  isDemoMode.value = !isDemoMode.value
}

// ---- 时间 ----
const now = ref(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
setInterval(() => { now.value = new Date().toLocaleTimeString('zh-CN', { hour12: false }) }, 30000)

watch([activeRecommendTab, activeExpert, debouncedCommandText], () => {
  void loadWorkbenchRecommendations()
})

onMounted(() => {
  void loadWorkbenchRecommendations()
})
</script>

<style scoped>
.agent-workbench {
  min-height: 100%;
  overflow: visible;
  padding: var(--page-padding-y) var(--page-padding-x);
  background: var(--primary-fade);
  color: #17233c;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
  box-sizing: border-box;
}

button {
  font: inherit;
}

.workbench-header {
  min-height: 72px;
  padding: 14px 18px;
  border: 1px solid #dce7f3;
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 94%, transparent);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  box-shadow: 0 14px 36px rgba(35, 77, 128, 0.06);
}

.brand-area {
  display: flex;
  align-items: center;
  gap: 14px;
}

.brand-logo {
  width: 44px;
  height: 44px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  color: var(--on-primary);
  background: var(--primary-color);
  font-weight: 800;
  box-shadow: 0 12px 24px rgba(45, 127, 249, 0.2);
}

.brand-area h1 {
  margin: 0;
  font-size: 20px;
  line-height: 1.25;
  letter-spacing: 0;
}

.brand-area p {
  margin: 4px 0 0;
  color: #6d7e99;
  font-size: 13px;
}

.header-tools {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.mode-switch {
  display: flex;
  padding: 3px;
  border-radius: 8px;
  background: var(--primary-fade);
  border: 1px solid #dce7f3;
}

.mode-switch button {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #60718c;
  padding: 7px 12px;
  cursor: pointer;
}

.mode-switch button.active {
  color: var(--primary-color);
  background: var(--surface-solid);
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.12);
}

.status-chip {
  min-height: 34px;
  padding: 0 12px;
  border: 1px solid #dbe8f5;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  background: var(--surface-solid);
  color: #53657f;
  font-size: 12px;
}

.status-chip.online span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--success);
  box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.12);
}

.square-button,
.profile-button {
  border: 1px solid #dbe8f5;
  background: var(--surface-solid);
  cursor: pointer;
}

.square-button {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: grid;
  place-items: center;
}

.profile-button {
  min-height: 36px;
  padding: 3px 10px 3px 4px;
  border-radius: 18px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #213657;
}

.avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--primary-fade);
}

.workspace-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: minmax(248px, 272px) minmax(0, 1fr);
  gap: 16px;
  align-items: stretch;
  min-height: min(820px, calc(100vh - 188px));
}

.left-rail,
.right-rail {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
}

.task-board {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
}

.node-panel,
.flow-panel,
.recommendation-panel {
  flex: 1 1 auto;
}

.node-panel,
.flow-panel,
.detail-card,
.preview-card,
.timeline-panel,
.recommendation-panel {
  min-height: 0;
}

.flow-panel,
.detail-card,
.preview-card,
.timeline-panel,
.recommendation-panel {
  display: flex;
  flex-direction: column;
}

.panel {
  border: 1px solid #dce7f3;
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 96%, transparent);
  box-shadow: 0 12px 30px rgba(36, 74, 121, 0.05);
}

.panel-title,
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.panel-title {
  padding: 14px 16px 10px;
  color: #192b49;
  font-weight: 700;
}

.panel-title button {
  border: 0;
  background: transparent;
  color: #2874ef;
  cursor: pointer;
}

.expert-card {
  margin: 0 12px 10px;
  padding: 12px;
  border: 1px solid #e4edf7;
  border-radius: 8px;
  background: var(--primary-fade);
  display: flex;
  align-items: center;
  gap: 10px;
}

.expert-card.active {
  border-color: #b8d3ff;
  background: var(--primary-fade);
}

.expert-avatar {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  display: grid;
  place-items: center;
  color: var(--on-primary);
  font-weight: 800;
  flex: 0 0 auto;
}

.expert-avatar.lawyer {
  background: var(--info);
}

.expert-avatar.pm {
  background: var(--success);
}

.expert-avatar.writer {
  background: var(--accent-color);
}

.expert-card strong,
.module-item strong,
.node-row strong,
.source-list strong {
  display: block;
  font-size: 13px;
  color: #1a2d4d;
}

.expert-card span,
.module-item span,
.node-row small,
.source-list small {
  display: block;
  margin-top: 3px;
  color: #70819b;
  font-size: 12px;
}

.module-list {
  padding: 0 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 9px;
  max-height: clamp(230px, 28vh, 350px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.module-item {
  min-height: 54px;
  padding: 10px;
  border-radius: 8px;
  background: var(--primary-fade);
  border: 1px solid #e7eef8;
  display: grid;
  grid-template-columns: 34px 1fr auto;
  align-items: center;
  gap: 10px;
}

.module-icon {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: var(--on-primary);
  font-weight: 800;
}

.module-icon.blue {
  background: var(--primary-color);
}

.module-icon.green {
  background: var(--success);
}

.module-icon.orange {
  background: var(--warning);
}

.module-icon.purple {
  background: var(--accent-color);
}

.module-item em,
.node-row em,
.source-list em {
  font-style: normal;
  color: #236be8;
  font-size: 12px;
  font-weight: 700;
}

.support-grid {
  padding: 0 12px 14px;
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}

.support-grid div {
  padding: 12px 10px;
  border-radius: 8px;
  background: var(--primary-fade);
  border: 1px solid #e5eef8;
}

.support-grid strong {
  display: block;
  color: #1f65d7;
  font-size: 20px;
}

.support-grid span {
  display: block;
  margin-top: 2px;
  color: #7888a0;
  font-size: 12px;
}

.node-panel {
  padding-bottom: 10px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.node-panel .panel-title {
  flex: 0 0 auto;
}

.node-row {
  margin: 0 12px;
  padding: 10px 0;
  border-top: 1px solid #edf2f8;
  display: grid;
  grid-template-columns: 10px 1fr auto;
  gap: 10px;
  align-items: center;
}

.node-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--border-light);
}

.node-dot.online {
  background: var(--success);
}

.node-dot.busy {
  background: var(--warning);
}

.task-hero {
  padding: 22px;
  display: grid;
  grid-template-columns: 1fr 220px;
  gap: 24px;
  align-items: center;
}

.eyebrow {
  display: inline-block;
  margin-bottom: 8px;
  color: #2c73ef;
  font-size: 12px;
  font-weight: 800;
}

.task-copy h2 {
  margin: 0;
  font-size: 26px;
  line-height: 1.25;
  letter-spacing: 0;
  color: #142847;
}

.task-copy p {
  margin: 10px 0 0;
  color: #64758f;
  font-size: 14px;
}

.task-tags {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.task-tags span {
  padding: 6px 10px;
  border-radius: 7px;
  background: var(--primary-fade);
  border: 1px solid #d9e8ff;
  color: #236be8;
  font-size: 12px;
}

.progress-card {
  padding: 16px;
  border-radius: 8px;
  background: var(--primary-fade);
  border: 1px solid #dfeaf6;
}

.progress-card span,
.progress-card small {
  color: #70819a;
  font-size: 12px;
}

.progress-card strong {
  display: block;
  margin: 8px 0;
  color: var(--info);
  font-size: 34px;
  line-height: 1;
}

.progress-track {
  height: 8px;
  border-radius: 4px;
  background: var(--primary-fade);
  overflow: hidden;
}

.progress-track div {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--info), var(--info));
}

.flow-panel {
  padding: 16px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
  min-width: 0;
}

.view-tabs {
  display: flex;
  gap: 6px;
  padding: 4px;
  border-radius: 8px;
  background: var(--primary-fade);
  min-width: 0;
  overflow-x: auto;
}

.view-tabs button,
.mini-tabs button {
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: #60718c;
  cursor: pointer;
}

.view-tabs button {
  padding: 8px 12px;
  white-space: nowrap;
}

.view-tabs button.active,
.mini-tabs button.active {
  color: var(--info);
  background: var(--surface-solid);
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(30, 90, 180, 0.1);
}

.outline-button {
  border: 1px solid #bcd2ef;
  border-radius: 7px;
  padding: 8px 14px;
  color: #1f65d7;
  background: var(--surface-solid);
  cursor: pointer;
}

.flow-lane {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(128px, 1fr));
  gap: 12px;
  max-height: clamp(260px, 34vh, 460px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.flow-insight-board {
  flex: 1 1 auto;
  min-height: 0;
  margin-top: 14px;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(210px, 0.9fr) minmax(220px, 0.9fr);
  gap: 12px;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.flow-insight-card {
  min-width: 0;
  padding: 16px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-input);
}

.flow-insight-card.is-primary {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.82), var(--bg-input));
  border-color: var(--primary-line);
}

.insight-label {
  display: inline-flex;
  width: fit-content;
  margin-bottom: 10px;
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 800;
}

.flow-insight-card h3 {
  margin: 0;
  color: var(--text-primary);
  font-size: 17px;
  line-height: 1.35;
}

.flow-insight-card p {
  margin: 10px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.65;
}

.insight-meta-row {
  margin-top: 18px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.insight-meta-row span,
.insight-meta-row strong {
  padding: 8px 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 72%, transparent);
}

.insight-meta-row span {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 800;
}

.insight-meta-row strong {
  min-width: 0;
  color: var(--text-primary);
  font-size: 13px;
  overflow-wrap: anywhere;
}

.gate-list,
.delivery-list {
  display: grid;
  gap: 8px;
}

.gate-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 72%, transparent);
}

.gate-item span,
.delivery-list span {
  color: var(--text-secondary);
  font-size: 12px;
}

.gate-item strong,
.delivery-list strong {
  color: var(--text-primary);
  font-size: 13px;
}

.gate-item.success strong {
  color: var(--success);
}

.gate-item.warning strong {
  color: var(--warning);
}

.gate-item.info strong {
  color: var(--info);
}

.delivery-list > div {
  padding: 11px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 72%, transparent);
}

.delivery-list strong,
.delivery-list span {
  display: block;
}

.delivery-list span {
  margin-top: 4px;
  line-height: 1.45;
}

.flow-step {
  min-width: 0;
  min-height: 116px;
  padding: 14px;
  border-radius: 8px;
  border: 1px solid #dce7f3;
  background: var(--primary-fade);
  position: relative;
}

.flow-step::after {
  content: "";
  position: absolute;
  top: 36px;
  right: -13px;
  width: 13px;
  height: 2px;
  background: var(--primary-fade);
}

.flow-step:last-child::after {
  display: none;
}

.flow-step .step-no {
  display: inline-grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--primary-fade);
  color: #236be8;
  font-size: 12px;
  font-weight: 800;
}

.flow-step strong {
  display: block;
  margin-top: 12px;
  color: #1c3152;
  line-height: 1.35;
}

.flow-step small {
  display: block;
  margin-top: 6px;
  color: #6f8098;
}

.flow-step.done {
  background: var(--success-fade);
  border-color: #bdebd5;
}

.flow-step.done .step-no {
  color: #047857;
  background: var(--success-fade);
}

.flow-step.running,
.flow-step.active {
  border-color: #f5bf70;
  background: var(--warning-fade);
  box-shadow: inset 0 0 0 1px rgba(245, 158, 11, 0.12);
}

.flow-step.running .step-no {
  color: #b45309;
  background: var(--warning-fade);
}

.detail-grid {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: 14px;
}

.detail-card,
.preview-card,
.timeline-panel {
  padding: 18px;
}

.detail-card .section-head,
.preview-card .section-head,
.timeline-panel .section-head,
.recommendation-panel .section-head {
  flex: 0 0 auto;
}

.section-head h3,
.section-head compact h3 {
  margin: 0;
}

.section-head h3 {
  font-size: 17px;
  color: #1a2e4f;
}

.section-head.compact h3 {
  margin: 0;
  font-size: 15px;
}

.section-head.compact span {
  color: #7c8ca3;
  font-size: 12px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 0 8px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 700;
}

.status-badge.running {
  color: #b45309;
  background: var(--warning-fade);
}

.status-badge.online {
  color: #047857;
  background: var(--success-fade);
}

.detail-meta {
  margin: 16px 0;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.detail-meta div {
  padding: 10px;
  border-radius: 8px;
  background: var(--primary-fade);
  border: 1px solid #e3edf8;
}

.detail-meta dt {
  color: #7c8ca3;
  font-size: 12px;
}

.detail-meta dd {
  margin: 5px 0 0;
  color: #1b2e4c;
  font-size: 13px;
  font-weight: 700;
}

.cot-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: clamp(210px, 28vh, 360px);
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.cot-list > div {
  display: grid;
  grid-template-columns: 10px 1fr;
  gap: 10px;
}

.cot-list > div > div {
  min-width: 0;
}

.cot-list span {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--primary-color);
  margin-top: 5px;
}

.cot-list strong {
  color: #1a2e4f;
}

.cot-list p {
  margin: 4px 0 0;
  color: #64758f;
  font-size: 13px;
  line-height: 1.55;
}

.document-preview {
  margin-top: 14px;
  padding: 16px;
  min-height: 220px;
  max-height: clamp(260px, 34vh, 440px);
  overflow-y: auto;
  scrollbar-gutter: stable;
  border-radius: 8px;
  background: linear-gradient(180deg, var(--bg-card), var(--primary-fade));
  border: 1px solid #e1ebf6;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.8);
}

.document-preview h4 {
  margin: 0 0 12px;
  text-align: center;
  color: #182b49;
}

.document-preview p {
  margin: 0 0 10px;
  color: #344761;
  font-size: 13px;
  line-height: 1.72;
}

.timeline {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
  max-height: clamp(190px, 24vh, 320px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.timeline-item {
  padding: 12px;
  border-radius: 8px;
  background: var(--primary-fade);
  border: 1px solid #e4edf8;
}

.timeline-item time {
  color: #236be8;
  font-weight: 800;
  font-size: 12px;
}

.timeline-item strong {
  display: block;
  margin-top: 7px;
  color: #1b2f50;
  font-size: 13px;
}

.timeline-item span {
  display: block;
  margin-top: 4px;
  color: #6e7f98;
  font-size: 12px;
  line-height: 1.45;
}

.command-bar {
  padding: 10px;
  display: grid;
  grid-template-columns: 36px 1fr 82px;
  align-items: center;
  gap: 10px;
}

.plus-sign {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: var(--primary-fade);
  color: #236be8;
  display: grid;
  place-items: center;
  font-size: 22px;
}

.command-bar input {
  height: 38px;
  border: 0;
  outline: 0;
  color: #1e314f;
  background: transparent;
  font-size: 14px;
}

.mode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 8px;
  border: 1px solid #dbe8f5;
  border-radius: 20px;
  background: var(--primary-fade);
  font-size: 11px;
  color: #2b72ec;
  cursor: pointer;
  user-select: none;
}
.mode-toggle.api {
  background: var(--warning-fade);
  border-color: #fcd34d;
  color: #92400e;
}
.mode-toggle button {
  width: 34px;
  height: 20px;
  border: 0;
  border-radius: 10px;
  background: var(--info);
  cursor: pointer;
  position: relative;
}
.mode-toggle.api button {
  background: var(--warning);
}
.toggle-knob {
  position: absolute;
  left: 3px;
  top: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--surface-solid);
  transition: left 0.2s;
}
.mode-toggle.api .toggle-knob {
  left: 17px;
}

.flow-step {
  cursor: pointer;
  transition: box-shadow 0.15s;
}
.flow-step:hover {
  box-shadow: 0 12px 28px rgba(36, 74, 121, 0.1);
}

.expert-card {
  cursor: pointer;
  transition: border-color 0.15s;
}
.expert-card:hover {
  border-color: #b8d3ff;
}

.command-bar button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.recommendation-list button:hover {
  border-color: #b8d3ff;
  background: var(--primary-fade);
}

.status-badge.done {
  color: #047857;
  background: var(--success-fade);
}

.command-bar button,
.assistant-action {
  border: 0;
  border-radius: 8px;
  color: var(--on-primary);
  background: var(--primary-color);
  cursor: pointer;
}

.command-bar button {
  height: 38px;
}

.assistant-panel {
  padding: 16px;
  text-align: center;
}

.assistant-avatar-stage {
  width: 100%;
  height: 190px;
  margin: 16px auto 12px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #dbeafe;
  background: linear-gradient(180deg, var(--primary-fade), var(--primary-fade));
}

.assistant-avatar-stage :deep(.digital-human-container) {
  border-radius: 8px;
  background: transparent;
}

.assistant-avatar-stage :deep(.loading-overlay),
.assistant-avatar-stage :deep(.error-overlay),
.assistant-avatar-stage :deep(.empty-overlay) {
  background: rgba(247, 250, 255, 0.82);
  backdrop-filter: blur(4px);
}

.digital-human-preparing {
  height: 100%;
  display: grid;
  place-items: center;
  color: #667790;
  font-size: 13px;
}

.assistant-name {
  display: block;
  color: #1b2f50;
}

.assistant-panel p {
  margin: 9px 0 14px;
  color: #667790;
  font-size: 13px;
  line-height: 1.6;
}

.voice-wave {
  height: 34px;
  margin: 0 auto 12px;
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 4px;
}

.voice-wave span {
  width: 4px;
  height: 12px;
  border-radius: 3px;
  background: var(--primary-color);
}

.voice-wave span:nth-child(2n) {
  height: 24px;
  background: var(--info);
}

.voice-wave span:nth-child(3n) {
  height: 18px;
  background: var(--info-fade);
}

.assistant-action {
  width: 100%;
  height: 38px;
}

.source-panel,
.recommendation-panel {
  padding: 16px;
}

.source-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: clamp(250px, 32vh, 420px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.source-list > div {
  display: grid;
  grid-template-columns: 32px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border-radius: 8px;
  background: var(--primary-fade);
  border: 1px solid #e4edf8;
}

.source-icon {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: var(--primary-color);
  background: var(--primary-fade);
  font-weight: 800;
}

.mini-tabs {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
  padding: 4px;
  border-radius: 8px;
  background: var(--primary-fade);
}

.mini-tabs button {
  height: 30px;
}

.recommendation-list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.recommendation-panel :deep(.recommendation-list) {
  max-height: clamp(260px, 34vh, 450px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.recommendation-list button {
  padding: 10px 12px;
  border: 1px solid #e0eaf6;
  border-radius: 8px;
  background: var(--surface-solid);
  color: #334865;
  text-align: left;
  cursor: pointer;
  line-height: 1.45;
}

@media (max-width: 1280px) {
  .workspace-grid {
    grid-template-columns: 250px minmax(520px, 1fr);
  }

  .flow-step::after {
    display: none;
  }
}

@media (max-width: 1160px) {
  .workspace-grid {
    grid-template-columns: 250px minmax(0, 1fr);
  }
}

@media (max-width: 1040px) {
  .workbench-header,
  .task-hero {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: flex-start;
  }

  .workspace-grid {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .left-rail {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
  }

  .flow-lane,
  .flow-insight-board,
  .timeline {
    grid-template-columns: repeat(2, 1fr);
  }

  .flow-step::after {
    display: none;
  }

  .detail-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .agent-workbench {
    padding: 12px;
  }

  .workspace-grid {
    min-height: 0;
  }

  .left-rail,
  .flow-lane,
  .flow-insight-board,
  .timeline,
  .detail-meta {
    grid-template-columns: 1fr;
  }

  .toolbar,
  .header-tools {
    align-items: stretch;
    flex-direction: column;
    width: 100%;
  }

  .view-tabs {
    overflow-x: auto;
  }

  .command-bar {
    grid-template-columns: 34px 1fr;
  }

  .command-bar button {
    grid-column: 1 / -1;
  }
}

/* Gallery minimal pass */
.agent-workbench {
  background: transparent;
  color: var(--text-primary);
  font-family: var(--font-sans);
  padding: 20px 24px 28px;
}

.workbench-header,
.panel {
  border-color: var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 86%, transparent);
  box-shadow: var(--shadow-sm);
}

.workbench-header {
  backdrop-filter: var(--backdrop-blur);
}

.brand-logo,
.expert-avatar,
.module-icon,
.source-icon,
.plus-sign {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--surface-solid);
  color: var(--primary-color);
  box-shadow: var(--shadow-sm);
}

.brand-logo {
  font-size: 22px;
}

.brand-area h1,
.panel-title,
.section-head h3,
.task-copy h2,
.expert-card strong,
.module-item strong,
.node-row strong,
.source-list strong,
.assistant-name,
.document-preview h4 {
  color: var(--text-primary);
  letter-spacing: 0;
}

.brand-area p,
.expert-card span,
.module-item span,
.node-row small,
.source-list small,
.task-copy p,
.assistant-panel p,
.cot-list p,
.timeline-item span,
.document-preview p {
  color: var(--text-secondary);
}

.mode-switch,
.view-tabs,
.mini-tabs,
.mode-toggle,
.status-chip,
.expert-card,
.module-item,
.support-grid div,
.task-tags span,
.progress-card,
.flow-step,
.detail-meta div,
.document-preview,
.timeline-item,
.command-bar,
.assistant-avatar-stage,
.source-list > div,
.recommendation-list button,
.source-panel,
.recommendation-panel {
  border-color: var(--border-light);
  border-radius: 8px;
  background: var(--bg-input);
}

.mode-switch button.active,
.view-tabs button.active,
.mini-tabs button.active,
.expert-card.active,
.flow-step.active,
.flow-step.running,
.task-tags span {
  background: var(--primary-fade);
  border-color: var(--primary-line);
  color: var(--primary-color);
  box-shadow: none;
}

.panel-title button,
.eyebrow,
.module-item em,
.node-row em,
.source-list em,
.support-grid strong,
.progress-card strong,
.timeline-item time {
  color: var(--primary-color);
}

.status-chip.online span,
.node-dot.online,
.cot-list span,
.progress-track div {
  background: var(--primary-color);
  box-shadow: none;
}

.node-dot.busy {
  background: var(--warning);
}

.flow-step.done {
  background: rgba(61, 118, 86, 0.1);
  border-color: rgba(61, 118, 86, 0.2);
}

.flow-step.done .step-no,
.status-badge.done,
.status-badge.online {
  color: var(--success);
  background: rgba(61, 118, 86, 0.1);
}

.flow-step.running .step-no,
.status-badge.running {
  color: var(--warning);
  background: rgba(154, 116, 50, 0.1);
}

.command-bar button,
.assistant-action {
  border: 1px solid rgba(255, 255, 255, 0.34);
  background: linear-gradient(135deg, var(--primary-color), var(--primary-hover));
  color: #fff;
  font-weight: 750;
  letter-spacing: 0;
  text-shadow: 0 1px 1px rgba(23, 36, 34, 0.18);
  box-shadow: 0 10px 22px rgba(63, 107, 99, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.command-bar button:hover:not(:disabled),
.assistant-action:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 28px rgba(63, 107, 99, 0.24), inset 0 1px 0 rgba(255, 255, 255, 0.2);
}

.command-bar button:disabled {
  border-color: rgba(255, 255, 255, 0.34);
  background: linear-gradient(135deg, var(--accent-color), var(--primary-color));
  color: rgba(255, 255, 255, 0.96);
  cursor: not-allowed;
  opacity: 1;
  box-shadow: 0 8px 18px rgba(95, 104, 201, 0.18), inset 0 1px 0 rgba(255, 255, 255, 0.18);
}

.voice-wave span,
.voice-wave span:nth-child(2n),
.voice-wave span:nth-child(3n) {
  background: var(--primary-color);
  opacity: 0.7;
}

.square-button,
.profile-button,
.outline-button {
  border-color: var(--border-light);
  border-radius: 8px;
  background: var(--surface-solid);
  color: var(--text-secondary);
}

.square-button:hover,
.outline-button:hover,
.profile-button:hover {
  color: var(--primary-color);
  border-color: var(--border-hover);
}
</style>
