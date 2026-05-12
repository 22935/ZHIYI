<template>
  <section class="contract-planner">
    <header class="planner-header">
      <div class="title-block">
        <span class="crumb">联邦智能 / 法律顾问 / 合同起草</span>
        <h1>软件开发合同起草 - 关键条款骨架</h1>
      </div>
      <div class="header-actions">
        <label class="mode-toggle" :class="{ api: !isDemoMode }">
          <span>演示模式</span>
          <button type="button" @click="toggleDemoMode">
            <span class="toggle-knob"></span>
          </button>
          <span>API 模式</span>
        </label>
        <button type="button">共享</button>
        <button type="button">版本</button>
        <button class="primary" type="button">保存草案</button>
      </div>
    </header>

    <div class="planner-grid">
      <aside class="left-column">
        <section class="panel domain-panel">
          <div class="panel-head">
            <h2>职业领域</h2>
            <span>{{ parentCategories.find(c => c.id === activeParent)?.count || 0 }} 个细分</span>
          </div>
          <div class="domain-tabs">
            <button
              v-for="cat in parentCategories"
              :key="cat.id"
              class="domain-parent-tab"
              :class="{ active: activeParent === cat.id }"
              @click="selectParent(cat.id)"
            >
              <span class="parent-icon">{{ cat.icon }}</span>
              <span class="parent-label">{{ cat.name }}</span>
            </button>
          </div>
          <div class="domain-sub-chips">
            <button
              v-for="sub in activeSubCategories"
              :key="sub.id"
              class="domain-sub-chip"
              :class="{ active: activeDomain === sub.id }"
              @click="selectDomain(sub.id)"
            >
              {{ sub.label }}
            </button>
          </div>
        </section>

        <section class="panel skill-panel">
          <div class="panel-head">
            <h2>嫁接技能</h2>
            <span>已启用 4 项</span>
          </div>
          <div class="skill-list">
            <div v-for="skill in attachedSkills" :key="skill.name">
              <span class="skill-icon" :class="skill.tone">{{ skill.short }}</span>
              <div>
                <strong>{{ skill.name }}</strong>
                <small>{{ skill.desc }}</small>
              </div>
            </div>
          </div>
        </section>

        <section class="panel pool-panel">
          <div class="panel-head">
            <h2>通用技能池</h2>
            <button type="button">全部</button>
          </div>
          <div class="pool-tags">
            <span v-for="tag in poolTags" :key="tag">{{ tag }}</span>
          </div>
        </section>

        <section class="panel config-panel">
          <div class="panel-head">
            <h2>当前配置</h2>
          </div>
          <dl>
            <div>
              <dt>专业体</dt>
              <dd>法律顾问</dd>
            </div>
            <div>
              <dt>任务类型</dt>
              <dd>合同起草</dd>
            </div>
            <div>
              <dt>知识范围</dt>
              <dd>民法典合同编、软件开发案例库</dd>
            </div>
            <div>
              <dt>输出风格</dt>
              <dd>严谨版 + 客户友好版</dd>
            </div>
          </dl>
        </section>
      </aside>

      <main class="center-column">
        <section class="panel map-panel">
          <div class="map-toolbar">
            <nav class="map-tabs">
              <button :class="{ active: activeTab === 'tree' }" type="button" @click="selectMapTab('tree')">思维树</button>
              <button :class="{ active: activeTab === 'timeline' }" type="button" @click="selectMapTab('timeline')">时间线</button>
              <button :class="{ active: activeTab === 'compare' }" type="button" @click="selectMapTab('compare')">对比视图</button>
            </nav>
            <div class="zoom-tools">
              <button type="button" @click="zoomOut">-</button>
              <span>{{ zoomLevel }}%</span>
              <button type="button" @click="zoomIn">+</button>
            </div>
          </div>

          <div class="mind-map" aria-label="合同起草思维树">
            <!-- markmap 交互思维树 -->
            <div v-if="activeTab === 'tree'" ref="mindmapContainer" class="mindmap-wrap">
              <svg ref="mindmapSvgRef" class="mindmap-canvas" />
            </div>

            <!-- 时间线 / 对比视图（静态节点） -->
            <template v-else>
              <svg class="map-lines" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                <path d="M50 16 C50 23 28 21 28 28" />
                <path d="M50 16 C50 23 50 23 50 30" />
                <path d="M50 36 C50 44 32 43 32 51" />
                <path d="M50 36 C50 44 68 43 68 51" />
                <path d="M32 57 C38 65 45 63 50 70" />
                <path d="M68 57 C62 65 55 63 50 70" />
                <path d="M50 76 C50 81 50 83 50 88" />
              </svg>

              <article
                v-for="node in mapDisplayNodes"
                :key="node.id"
                class="mind-node"
                :class="[node.tone, { active: node.id === selectedNodeId || node.active }]"
                :style="{ left: node.x + '%', top: node.y + '%' }"
                @click="selectMindNode(node.id)"
              >
                <div class="confidence">{{ node.confidence }}</div>
                <strong>{{ node.title }}</strong>
                <span>{{ node.desc }}</span>
              </article>

              <div class="mini-map">
                <span></span>
                <span></span>
                <span class="active"></span>
              </div>
            </template>
          </div>
        </section>

        <section class="panel inspector-panel">
          <div class="inspector-tabs">
            <button :class="{ active: activeInspectorTab === 'detail' }" type="button" @click="activeInspectorTab = 'detail'">节点详情</button>
            <button :class="{ active: activeInspectorTab === 'thought' }" type="button" @click="activeInspectorTab = 'thought'">思考过程</button>
            <button :class="{ active: activeInspectorTab === 'refs' }" type="button" @click="activeInspectorTab = 'refs'">引用资料</button>
            <button :class="{ active: activeInspectorTab === 'alt' }" type="button" @click="activeInspectorTab = 'alt'">备选方案</button>
          </div>

          <!-- 节点详情 -->
          <div v-if="activeInspectorTab === 'detail'" class="node-detail">
            <div class="detail-title">
              <span class="node-number">{{ selectedNode.id.slice(0, 2) }}</span>
              <div>
                <h2>{{ selectedNode.title }}</h2>
                <p>{{ selectedNode.desc }}</p>
              </div>
              <span class="detail-status">{{ selectedNode.confidence }}</span>
            </div>
            <div class="evidence-grid">
              <article v-for="item in evidenceItems" :key="item.title">
                <strong>{{ item.title }}</strong>
                <p>{{ item.desc }}</p>
              </article>
            </div>
          </div>

          <!-- 思考过程 -->
          <div v-else-if="activeInspectorTab === 'thought'" class="node-detail">
            <div class="thought-list">
              <div v-for="(t, i) in thoughts" :key="i" class="thought-item">
                <span class="thought-num">{{ i + 1 }}</span>
                <p>{{ t }}</p>
              </div>
            </div>
          </div>

          <!-- 引用资料 -->
          <div v-else-if="activeInspectorTab === 'refs'" class="node-detail">
            <div class="reference-list-inline">
              <article v-for="ref in references" :key="ref.title">
                <div>
                  <strong>{{ ref.title }}</strong>
                  <p>{{ ref.source }}</p>
                </div>
                <em>{{ ref.score }}</em>
              </article>
            </div>
          </div>

          <!-- 备选方案 -->
          <div v-else class="node-detail">
            <div class="alt-list">
              <article v-for="opt in altOptions" :key="opt.title">
                <strong>{{ opt.title }}</strong>
                <p>{{ opt.desc }}</p>
              </article>
            </div>
          </div>
        </section>

        <section class="panel command-panel">
          <span class="add-icon">+</span>
          <input
            id="contract-command"
            name="contract-command"
            v-model="commandText"
            :disabled="isGenerating"
            aria-label="补充指令"
            @keyup.enter="handleGenerate"
          />
          <button type="button" :disabled="isGenerating" @click="handleGenerate">
            {{ isGenerating ? '生成中...' : '生成' }}
          </button>
        </section>
      </main>

      <aside class="right-column">
        <section class="panel assistant-panel">
          <div class="panel-head">
            <h2>数字人助手</h2>
            <span class="online-dot">在线</span>
          </div>
          <div class="assistant-card">
            <div class="assistant-avatar-stage">
              <DigitalHuman
                v-if="digitalHumanRoleId"
                :role-id="digitalHumanRoleId"
                :style="'realistic'"
                transparent
              />
              <div v-else class="digital-human-preparing">正在连接数字人...</div>
            </div>
            <strong>{{ digitalHumanRoleName }} - 张明</strong>
            <p>已定位合同核心风险：交付验收边界、需求变更成本、源代码权属与保密责任。</p>
          </div>
          <button class="voice-button" type="button" @click="goToVoiceChat">播放讲解</button>
        </section>

        <section class="panel context-panel">
          <div class="panel-head">
            <h2>当前上下文</h2>
            <span>已锁定</span>
          </div>
          <div class="context-list">
            <div v-for="item in contextItems" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <section class="panel reference-panel">
          <div class="panel-head">
            <h2>推荐资料</h2>
            <span>相关度</span>
          </div>
          <div class="reference-list">
            <article v-for="ref in references" :key="ref.title">
              <div>
                <strong>{{ ref.title }}</strong>
                <p>{{ ref.source }}</p>
              </div>
              <em>{{ ref.score }}</em>
            </article>
          </div>
        </section>

        <section class="panel suggestion-panel">
          <div class="panel-head">
            <h2>下一步建议</h2>
          </div>
          <ol>
            <li>确认付款节点是否与交付验收绑定。</li>
            <li>补充需求变更的审批与报价机制。</li>
            <li>明确源代码、部署文档、接口文档交付清单。</li>
          </ol>
        </section>
      </aside>
    </div>

    <footer class="status-footer">
      <span>联邦节点：北京 · 上海 · 深圳</span>
      <span>知识版本：law-contract-2026.05</span>
      <span>自动保存：{{ lastSaveTime }}</span>
      <span>{{ isDemoMode ? '演示模式' : 'API 模式' }} · 会话: {{ sessionId ? sessionId.slice(0, 8) + '...' : '未开始' }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Transformer } from 'markmap-lib'
import { Markmap } from 'markmap-view'
import DigitalHuman from '@/components/DigitalHuman.vue'
import { useDigitalHumanRole } from '@/composables/useDigitalHumanRole'
import { agentLawyerApi } from '@/services/api/agentLawyer'
import type { LawyerAgentResponse } from '@/services/api/agentLawyer'

const { digitalHumanRoleId, digitalHumanRoleName } = useDigitalHumanRole()
const router = useRouter()

type MapTab = 'tree' | 'timeline' | 'compare'
type MindNode = {
  id: string
  title: string
  desc: string
  confidence: string
  x: number
  y: number
  tone: string
  active?: boolean
}

const activeTab = ref<MapTab>('tree')

function goToVoiceChat() {
  router.push('/voice-chat')
}

// ---- markmap 交互思维树 ----
const mindmapSvgRef = ref<SVGSVGElement | null>(null)
const transformer = new Transformer()
let markmap: Markmap | null = null
let clickBound = false

const nodesToMarkdown = (nodes: MindNode[]): string => {
  const root = nodes.find(n => n.tone === 'root')
  if (!root) return '# 合同起草\n\n- 无数据'
  const children = nodes.filter(n => n.tone !== 'root')
  const lines = [`# ${root.title}`]
  for (const c of children) {
    lines.push(`## ${c.title}`)
    const sublines = c.desc.split(/[,，、]/).filter(Boolean).map(s => s.trim())
    for (const sl of sublines.slice(0, 2)) {
      lines.push(`### ${sl}`)
    }
  }
  return lines.join('\n')
}

async function renderMarkmap() {
  await nextTick()
  if (!mindmapSvgRef.value || activeTab.value !== 'tree') return
  try {
    const md = nodesToMarkdown(mindNodes.value)
    const { root } = transformer.transform(md)

    if (!markmap) {
      markmap = Markmap.create(mindmapSvgRef.value, {
        autoFit: true,
        duration: 300
      })
    }
    markmap.setData(root)
    await nextTick()
    markmap.fit()

    // 节点点击 → 同步 Inspector（只绑定一次）
    if (!clickBound && mindmapSvgRef.value) {
      clickBound = true
      mindmapSvgRef.value.addEventListener('click', (e: Event) => {
        const target = e.target as HTMLElement
        const g = target.closest('.markmap-node') as SVGElement | null
        if (g) {
          const textEl = g.querySelector('.markmap-node-text') as HTMLElement | null
          const nodeLabel = textEl?.textContent?.trim() || ''
          if (nodeLabel) {
            const match = mindNodes.value.find(n => nodeLabel.startsWith(n.title))
            if (match) {
              selectedNodeId.value = match.id
              activeInspectorTab.value = 'detail'
            }
          }
        }
      })
    }
  } catch (_) {
    // markmap 渲染失败时静默降级
  }
}

function destroyMarkmap() {
  if (markmap) {
    try { markmap.destroy() } catch (_) { /* noop */ }
    markmap = null
  }
  clickBound = false
}

watch(activeTab, (tab) => {
  if (tab === 'tree') {
    destroyMarkmap()
    nextTick(() => renderMarkmap())
  } else {
    destroyMarkmap()
  }
})

onMounted(() => {
  if (activeTab.value === 'tree') {
    nextTick(() => renderMarkmap())
  }
})

onBeforeUnmount(() => {
  destroyMarkmap()
})

// 缩放（使用 CSS transform）
const zoomLevel = ref(100)
const mindmapContainer = ref<HTMLElement | null>(null)

function zoomIn() {
  if (activeTab.value !== 'tree') selectMapTab('tree')
  zoomLevel.value = Math.min(200, zoomLevel.value + 20)
  if (mindmapContainer.value) {
    mindmapContainer.value.style.transform = `scale(${zoomLevel.value / 100})`
  }
}

function zoomOut() {
  if (activeTab.value !== 'tree') selectMapTab('tree')
  zoomLevel.value = Math.max(40, zoomLevel.value - 20)
  if (mindmapContainer.value) {
    mindmapContainer.value.style.transform = `scale(${zoomLevel.value / 100})`
  }
}

// ---- 模式 ----
const isDemoMode = ref(true)
const isGenerating = ref(false)
const currentStep = ref(0)

// ---- 职业领域标签栏 ----
interface SubCategory {
  id: string
  label: string
}
interface ParentCategory {
  id: string
  name: string
  icon: string
  count: number
  subs: SubCategory[]
}

const parentCategories: ParentCategory[] = [
  {
    id: 'law', name: '法律', icon: '⚖', count: 7,
    subs: [
      { id: '合同法务', label: '合同法务' }, { id: '公司法务', label: '公司法务' },
      { id: '知识产权', label: '知识产权' }, { id: '劳动法务', label: '劳动法务' },
      { id: '民商事', label: '民商事诉讼' }, { id: '刑事', label: '刑事辩护' },
      { id: '行政', label: '行政法务' }
    ]
  },
  {
    id: 'tech', name: '技术', icon: '💻', count: 6,
    subs: [
      { id: '软件开发', label: '软件开发' }, { id: '系统架构', label: '系统架构' },
      { id: '数据科学', label: '数据科学' }, { id: '网络安全', label: '网络安全' },
      { id: 'AI-ML', label: 'AI/ML' }, { id: 'DevOps', label: 'DevOps' }
    ]
  },
  {
    id: 'finance', name: '财务', icon: '📊', count: 6,
    subs: [
      { id: '审计', label: '审计' }, { id: '税务', label: '税务筹划' },
      { id: '财务分析', label: '财务分析' }, { id: '投融资', label: '投融资' },
      { id: '风控', label: '风控合规' }, { id: '资产评估', label: '资产评估' }
    ]
  },
  {
    id: 'medical', name: '医疗', icon: '🏥', count: 6,
    subs: [
      { id: '临床', label: '临床医学' }, { id: '药学', label: '药学研发' },
      { id: '公卫', label: '公共卫生' }, { id: '医保', label: '医疗保险' },
      { id: '器械', label: '医疗器械' }, { id: '数字医疗', label: '数字医疗' }
    ]
  },
  {
    id: 'edu', name: '教育', icon: '📚', count: 6,
    subs: [
      { id: '课程设计', label: '课程设计' }, { id: '教学评估', label: '教学评估' },
      { id: '教育科技', label: '教育科技' }, { id: '学术研究', label: '学术研究' },
      { id: '职业培训', label: '职业培训' }, { id: '特殊教育', label: '特殊教育' }
    ]
  }
]

const activeParent = ref('law')

const activeSubCategories = computed(() => {
  return parentCategories.find(c => c.id === activeParent.value)?.subs || []
})

const activeDomain = ref('合同法务')

// 每个子领域的技能数据
const allSkills: Record<string, { short: string; name: string; desc: string; tone: string }[]> = {
  '合同法务': [
    { short: '法', name: '法规检索', desc: '定位民法典、著作权与数据安全条款', tone: 'blue' },
    { short: '审', name: '风险审查', desc: '识别责任边界与异常履约风险', tone: 'orange' },
    { short: '写', name: '条款生成', desc: '生成可编辑合同文本', tone: 'green' },
    { short: '比', name: '版本对比', desc: '并列输出专业版与友好版', tone: 'purple' }
  ],
  '公司法务': [
    { short: '章', name: '章程审查', desc: '审核公司章程与治理结构', tone: 'blue' },
    { short: '股', name: '股权设计', desc: '设计股权架构与退出机制', tone: 'orange' },
    { short: '审', name: '合规审计', desc: '企业合规风险评估与整改', tone: 'green' },
    { short: '并', name: '并购尽调', desc: '并购法律尽职调查与协议', tone: 'purple' }
  ],
  '知识产权': [
    { short: '专', name: '专利检索', desc: '专利数据库检索与分析', tone: 'blue' },
    { short: '著', name: '著作权登记', desc: '软件著作权申请与保护', tone: 'orange' },
    { short: '商', name: '商标管理', desc: '商标注册、异议与维权', tone: 'green' },
    { short: '秘', name: '商业秘密', desc: '保密协议与竞业限制', tone: 'purple' }
  ],
  '劳动法务': [
    { short: '合', name: '合同管理', desc: '劳动合同起草与审核', tone: 'blue' },
    { short: '争', name: '争议处理', desc: '劳动仲裁与诉讼代理', tone: 'orange' },
    { short: '规', name: '制度合规', desc: '企业规章制度合规审查', tone: 'green' },
    { short: '裁', name: '裁员方案', desc: '经济性裁员方案设计', tone: 'purple' }
  ],
  '民商事': [
    { short: '诉', name: '诉讼策略', desc: '民商事诉讼方案设计', tone: 'blue' },
    { short: '证', name: '证据梳理', desc: '证据链组织与质证预案', tone: 'orange' },
    { short: '调', name: '调解谈判', desc: '商事调解与和解方案', tone: 'green' },
    { short: '执', name: '执行代理', desc: '生效判决执行与财产查控', tone: 'purple' }
  ],
  '刑事': [
    { short: '辩', name: '辩护策略', desc: '刑事辩护方案与庭审策略', tone: 'blue' },
    { short: '取', name: '证据审查', desc: '非法证据排除与质证', tone: 'orange' },
    { short: '减', name: '量刑协商', desc: '认罪认罚与量刑建议', tone: 'green' },
    { short: '申', name: '申诉代理', desc: '再审申诉与减刑假释', tone: 'purple' }
  ],
  '行政': [
    { short: '议', name: '行政复议', desc: '行政行为审查与复议申请', tone: 'blue' },
    { short: '诉', name: '行政诉讼', desc: '行政案件起诉与代理', tone: 'orange' },
    { short: '赔', name: '国家赔偿', desc: '国家赔偿申请与诉讼', tone: 'green' },
    { short: '规', name: '规范性审查', desc: '规范性文件合法性审查', tone: 'purple' }
  ]
}

const allTags: Record<string, string[]> = {
  '合同法务': ['摘要生成', '问答检索', '表格提取', '引用校验', '格式排版', '合同归档', '术语解释', '风险评级'],
  '公司法务': ['章程审查', '股权设计', '合规审计', '并购尽调', '尽职调查', '文件归档', '风险预警', '谈判支持'],
  '知识产权': ['专利检索', '侵权分析', '著作权登记', '商标监控', '技术交底', '权利图谱', '许可谈判', '估值测算'],
  '劳动法务': ['合同审核', '争议预判', '仲裁代理', '合规检查', '制度审查', '培训材料', '风险评级', '裁审模拟'],
  '民商事': ['诉讼评估', '证据分析', '判例检索', '调解方案', '庭审模拟', '文书撰写', '保全申请', '执行跟踪'],
  '刑事': ['罪名分析', '证据审查', '量刑预测', '辩护要点', '程序审查', '强制措施', '和解协商', '庭审实训'],
  '行政': ['规范性审查', '程序审查', '证据整理', '诉讼评估', '赔偿测算', '文书撰写', '案例检索', '法规追踪']
}

const allContexts: Record<string, { label: string; value: string }[]> = {
  '合同法务': [
    { label: '甲方角色', value: '委托开发方' },
    { label: '乙方角色', value: '软件服务供应商' },
    { label: '项目周期', value: '3 个月' },
    { label: '交付方式', value: '源码 + 部署文档 + 测试报告' },
    { label: '当前焦点', value: '关键条款骨架' }
  ],
  '公司法务': [
    { label: '企业类型', value: '有限责任公司' },
    { label: '注册资本', value: '500 万元' },
    { label: '股东构成', value: '3 名自然人股东' },
    { label: '经营范围', value: '软件开发与技术服务' },
    { label: '当前焦点', value: '公司章程修订' }
  ],
  '知识产权': [
    { label: '权利类型', value: '软件著作权' },
    { label: '技术领域', value: 'AI 算法与数据平台' },
    { label: '保护范围', value: '源代码、接口文档、架构设计' },
    { label: '申请阶段', value: '初审待补正' },
    { label: '当前焦点', value: '权利要求的布局策略' }
  ],
  '劳动法务': [
    { label: '企业规模', value: '200 人' },
    { label: '合同类型', value: '固定期限劳动合同' },
    { label: '争议焦点', value: '加班工资与绩效奖金' },
    { label: '涉及部门', value: '研发中心' },
    { label: '当前焦点', value: '批量续签合规审查' }
  ],
  '民商事': [
    { label: '案件类型', value: '合同纠纷' },
    { label: '标的金额', value: '人民币 860 万元' },
    { label: '管辖法院', value: '北京知识产权法院' },
    { label: '审理阶段', value: '一审' },
    { label: '当前焦点', value: '证据链补强与质证准备' }
  ],
  '刑事': [
    { label: '罪名', value: '侵犯商业秘密' },
    { label: '涉案金额', value: '人民币 1200 万元' },
    { label: '程序阶段', value: '审查起诉' },
    { label: '嫌疑人', value: '2 名自然人' },
    { label: '当前焦点', value: '罪轻辩护与量刑协商' }
  ],
  '行政': [
    { label: '行政行为', value: '行政处罚决定' },
    { label: '复议机关', value: '省市场监督管理局' },
    { label: '复议期限', value: '60 日（剩余 42 天）' },
    { label: '涉及部门', value: '市场监管局、税务局' },
    { label: '当前焦点', value: '复议申请书撰写' }
  ]
}

const attachedSkills = ref(allSkills['合同法务'] || [])
const poolTags = ref(allTags['合同法务'] || [])
const contextItems = ref(allContexts['合同法务'] || [])

function selectParent(parentId: string) {
  activeParent.value = parentId
  const firstSub = parentCategories.find(c => c.id === parentId)?.subs[0]
  if (firstSub) selectDomain(firstSub.id)
}

function selectDomain(domainId: string) {
  activeDomain.value = domainId
  attachedSkills.value = allSkills[domainId] || [
    { short: domainId.slice(0, 1), name: domainId, desc: '自定义技能配置', tone: 'blue' }
  ]
  poolTags.value = allTags[domainId] || ['分析', '检索', '生成', '评估', '审查', '报告', '优化', '归档']
  contextItems.value = allContexts[domainId] || [
    { label: '专业体', value: domainId },
    { label: '任务类型', value: '标准任务' },
    { label: '当前焦点', value: '任务规划' }
  ]
}

// ---- 思维树 / 时间线 / 对比视图 ----
const initialMindNodes: MindNode[] = [
  { id: 'task', title: '任务理解', desc: '软件开发合同起草', confidence: '98%', x: 50, y: 12, tone: 'root' },
  { id: 'keyword', title: '关键词提取', desc: '软件开发、验收、交付', confidence: '94%', x: 28, y: 30, tone: 'blue' },
  { id: 'law', title: '法律适用选择', desc: '民法典合同编 + 著作权法', confidence: '92%', x: 50, y: 32, tone: 'orange' },
  { id: 'lawyer', title: '骨架生成（律师视角）', desc: '强调责任、证据与违约', confidence: '89%', x: 32, y: 53, tone: 'green' },
  { id: 'client', title: '骨架生成（客户友好版）', desc: '强调可读性与交付清单', confidence: '87%', x: 68, y: 53, tone: 'green' },
  { id: 'merge', title: '对比与合并', desc: '合并差异条款与语气', confidence: '84%', x: 50, y: 72, tone: 'blue' },
  { id: 'final', title: '最终版本生成', desc: '输出正式合同草案', confidence: '待执行', x: 50, y: 90, tone: 'muted' }
]
const mindNodes = ref<MindNode[]>(structuredClone(initialMindNodes))
const selectedNodeId = ref('law')

const timelineNodes: MindNode[] = [
  { id: 't1', title: '第 1 步', desc: '10:15 接收合同起草指令，解析甲方需求和项目背景', confidence: '完成', x: 18, y: 40, tone: 'root' },
  { id: 't2', title: '第 2 步', desc: '10:18 检索民法典合同编、著作权法、数据安全法相关条款', confidence: '完成', x: 50, y: 40, tone: 'blue' },
  { id: 't3', title: '第 3 步', desc: '10:24 提取关键词：软件开发、验收、交付、知识产权、保密', confidence: '92%', x: 82, y: 40, tone: 'orange' }
]

const compareNodes: MindNode[] = [
  { id: 'c1', title: '律师版', desc: '强调违约责任、证据保留、法律适用', confidence: '严谨', x: 25, y: 40, tone: 'blue' },
  { id: 'c2', title: '客户版', desc: '强调可读性、交付清单、通俗表述', confidence: '友好', x: 75, y: 40, tone: 'green' }
]

const mapDisplayNodes = computed<MindNode[]>(() => {
  switch (activeTab.value) {
    case 'timeline': return timelineNodes
    case 'compare': return compareNodes
    default: return mindNodes.value
  }
})

function selectMapTab(tab: MapTab) {
  activeTab.value = tab
  if (tab === 'compare') selectedNodeId.value = 'c1'
  else if (tab === 'timeline') selectedNodeId.value = 't1'
  else selectedNodeId.value = 'law'
}

function selectMindNode(id: string) {
  selectedNodeId.value = id
}

const selectedNode = computed(() => {
  return mapDisplayNodes.value.find(n => n.id === selectedNodeId.value) || mapDisplayNodes.value[0]
})

// ---- Inspector ----
type InspectorTab = 'detail' | 'thought' | 'refs' | 'alt'
const activeInspectorTab = ref<InspectorTab>('detail')

const evidenceItems = ref([
  { title: '合同性质', desc: '开发服务与成果交付并存，需要同时覆盖服务过程、验收和成果权属。' },
  { title: '核心条款', desc: '付款节点、验收标准、知识产权、保密义务、违约责任为主干结构。' },
  { title: '输出策略', desc: '先生成关键条款骨架，再由风险审查节点补充边界条件与例外情形。' }
])

const thoughts = ref([
  '本任务的核心是将用户需求映射到合同法的规范框架中，确保每个条款都有法律依据。',
  '关键词"验收"需要展开为具体的验收标准、验收方式和验收期限，这直接对应民法典第 600 条。',
  '交付物清单必须明确区分"成果交付"和"服务过程"，否则容易在履约阶段产生争议。',
  '知识产权条款是软件合同区别于普通买卖合同的关键特征，需要引用著作权法第 17 条。'
])

const references = ref([
  { title: '民法典合同编相关条款', source: '国家法律法规数据库', score: '98%' },
  { title: '计算机软件著作权登记办法', source: '知识产权专题库', score: '93%' },
  { title: '软件开发合同争议裁判摘要', source: '案例库 · 近三年', score: '88%' },
  { title: '企业数据处理安全约定模板', source: '企业合规模板库', score: '84%' }
])

const altOptions = ref([
  { title: '方案 A：民法典为主', desc: '以合同编为核心框架，著作权法辅助，适用大多数通用合同场景。' },
  { title: '方案 B：行业模板驱动', desc: '基于软件开发行业标准模板，补充合规条款，适用成熟外包场景。' },
  { title: '方案 C：自主定制', desc: '从零起草，灵活度最高，但风险覆盖依赖律师经验判断。' }
])

// ---- 命令栏 ----
const commandText = ref('请将知识产权、验收标准、违约责任展开为可直接放入合同的条款')
const commandHistory = ref<string[]>([])
const sessionId = ref('')

function addToHistory(text: string) {
  commandHistory.value.unshift(text)
  if (commandHistory.value.length > 10) commandHistory.value.pop()
}

const demoChainSteps = [
  { nodeId: 'task', delay: 300, newActive: 'keyword', newTitle: '关键词提取', newDesc: '软件开发、验收、交付、知识产权', confidence: '94%' },
  { nodeId: 'keyword', delay: 800, newActive: 'law', newTitle: '法律适用选择', newDesc: '民法典合同编 + 著作权法第 17 条', confidence: '92%' },
  { nodeId: 'law', delay: 1000, newActive: 'lawyer', newTitle: '骨架生成（律师视角）', newDesc: '强调违约责任与风险分配', confidence: '89%' },
  { nodeId: 'lawyer', delay: 800, newActive: 'client', newTitle: '骨架生成（客户友好版）', newDesc: '强调可读性与交付清单', confidence: '87%' },
  { nodeId: 'client', delay: 900, newActive: 'merge', newTitle: '对比与合并', newDesc: '合并差异条款与语气表述', confidence: '84%' },
  { nodeId: 'merge', delay: 700, newActive: 'final', newTitle: '最终版本生成', newDesc: '输出正式合同草案 v1.0', confidence: '已完成' }
]

async function runDemoMode() {
  isGenerating.value = true
  currentStep.value = 0
  addToHistory(commandText.value)

  mindNodes.value = structuredClone(initialMindNodes)
  mindNodes.value.forEach(n => (n.active = false))
  const first = mindNodes.value.find(n => n.id === 'task')
  if (first) first.active = true
  selectedNodeId.value = 'task'

  for (let i = 0; i < demoChainSteps.length; i++) {
    const step = demoChainSteps[i]
    await new Promise(r => setTimeout(r, step.delay))
    currentStep.value = i + 1
    mindNodes.value.forEach(n => (n.active = false))
    const target = mindNodes.value.find(n => n.id === step.newActive)
    if (target) {
      target.active = true
      target.confidence = step.confidence
      target.title = step.newTitle
      target.desc = step.newDesc
    }
    selectedNodeId.value = step.newActive
    await renderMarkmap()
  }

  isGenerating.value = false
  ElMessage.success('Demo 合同条款骨架生成完成')
}

async function runApiMode() {
  isGenerating.value = true
  addToHistory(commandText.value)
  mindNodes.value = structuredClone(initialMindNodes)
  mindNodes.value.forEach(n => (n.active = false))
  const first = mindNodes.value.find(n => n.id === 'task')
  if (first) first.active = true
  selectedNodeId.value = 'task'

  try {
    const res: LawyerAgentResponse = await agentLawyerApi.chat({
      text: commandText.value,
      sessionId: sessionId.value || undefined
    })

    if (res.success) {
      sessionId.value = res.sessionId || ''
      if (res.trace && res.trace.length > 0) {
        mindNodes.value = res.trace.slice(0, 7).map((t, i) => {
          const positions = [
            { x: 50, y: 12 }, { x: 28, y: 30 }, { x: 50, y: 32 }, { x: 32, y: 53 }, { x: 68, y: 53 }, { x: 50, y: 72 }, { x: 50, y: 90 }
          ]
          const tones = ['root', 'blue', 'orange', 'green', 'green', 'blue', 'muted']
          return {
            id: `api-${i}`,
            title: t.action || `步骤 ${i + 1}`,
            desc: t.observation || t.thought || '',
            confidence: i < res.trace.length - 1 ? `${85 + i * 2}%` : '已完成',
            x: positions[i]?.x ?? 50,
            y: positions[i]?.y ?? 50,
            tone: tones[i] || 'blue'
          }
        })
        if (mindNodes.value.length > 0) {
          mindNodes.value[mindNodes.value.length - 1].active = true
          selectedNodeId.value = mindNodes.value[mindNodes.value.length - 1].id
        }
      }
      if (res.evidenceAnalysis || res.evidence_analysis) {
        const ea = res.evidenceAnalysis || res.evidence_analysis
        evidenceItems.value = (ea?.evidence_items || []).map((ei: any) => ({
          title: ei.name || ei.type || '',
          desc: ei.notes || ei.strength || ''
        })).slice(0, 3)
      }
      ElMessage.success('API 返回成功')
      await renderMarkmap()
    } else {
      ElMessage.error(res.error || res.message || 'API 返回失败')
    }
  } catch {
    ElMessage.warning('API 调用失败，请检查后端服务是否可用')
  } finally {
    isGenerating.value = false
  }
}

async function handleGenerate() {
  if (!commandText.value.trim()) return
  if (isDemoMode.value) {
    await runDemoMode()
  } else {
    await runApiMode()
  }
}

function toggleDemoMode() {
  isDemoMode.value = !isDemoMode.value
}

// ---- 自动保存时间 ----
const lastSaveTime = ref(new Date().toLocaleTimeString('zh-CN', { hour12: false }))
setInterval(() => { lastSaveTime.value = new Date().toLocaleTimeString('zh-CN', { hour12: false }) }, 30000)
</script>

<style scoped>
.contract-planner {
  min-height: 100%;
  padding: 20px;
  box-sizing: border-box;
  color: #17233c;
  background: linear-gradient(165deg, #f0f5ff 0%, #f8fafc 40%, #faf9fb 100%);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}

button {
  font: inherit;
}

.planner-header {
  padding: 16px 24px;
  border: 1px solid #bfdbfe;
  border-radius: 12px;
  background: linear-gradient(180deg, rgba(37, 99, 235, 0.04), rgba(255, 255, 255, 0.96));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  box-shadow: 0 4px 24px rgba(37, 99, 235, 0.06);
}

.crumb {
  display: block;
  margin-bottom: 4px;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
}

.title-block h1 {
  margin: 0;
  font-size: 21px;
  line-height: 1.3;
  letter-spacing: 0;
}

.mode-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border: 1px solid #dbe8f5;
  border-radius: 20px;
  background: #eef5ff;
  font-size: 11px;
  color: #2b72ec;
  cursor: pointer;
  user-select: none;
  height: 32px;
}
.mode-toggle.api {
  background: #fef3c7;
  border-color: #fcd34d;
  color: #92400e;
}
.mode-toggle button {
  width: 30px;
  height: 18px;
  border: 0;
  border-radius: 9px;
  background: #195ee4;
  cursor: pointer;
  position: relative;
}
.mode-toggle.api button {
  background: #f59e0b;
}
.toggle-knob {
  position: absolute;
  left: 2px;
  top: 2px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #ffffff;
  transition: left 0.2s;
}
.mode-toggle.api .toggle-knob {
  left: 14px;
}
.header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  flex-shrink: 0;
}

.header-actions button,
.panel-head button,
.zoom-tools button,
.command-panel button,
.voice-button {
  border: 1px solid #bdd2ef;
  border-radius: 8px;
  background: #ffffff;
  color: #1f65d7;
  cursor: pointer;
  font-size: 13px;
  transition: box-shadow 0.15s, border-color 0.15s;
}

.header-actions button:hover,
.panel-head button:hover {
  border-color: #2d7ff9;
  box-shadow: 0 2px 8px rgba(45, 127, 249, 0.1);
}

.header-actions button {
  height: 34px;
  padding: 0 14px;
}

.header-actions .primary,
.command-panel button,
.voice-button {
  border-color: transparent;
  color: #ffffff;
  background: linear-gradient(135deg, #2d7ff9, #1d5fd8);
}

.header-actions .primary:hover,
.command-panel button:hover,
.voice-button:hover {
  box-shadow: 0 4px 14px rgba(45, 127, 249, 0.25);
}

.planner-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: 268px minmax(0, 1fr) 288px;
  gap: 16px;
  align-items: start;
}

.left-column,
.right-column,
.center-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel {
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 2px 16px rgba(0, 0, 0, 0.03);
}

.panel-head {
  padding: 14px 16px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-bottom: 1px solid #f1f5f9;
}

.panel-head h2 {
  margin: 0;
  color: #1e293b;
  font-size: 14px;
  font-weight: 700;
}

.panel-head span,
.panel-head button {
  font-size: 12px;
}

.panel-head span {
  color: #94a3b8;
}

.panel-head button {
  padding: 5px 10px;
}

/* -- 领域标签栏 -- Lawyer Blue -- */
.domain-tabs {
  padding: 8px 14px 0;
  display: flex;
  gap: 4px;
  overflow-x: auto;
}
.domain-parent-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 8px 8px 0 0;
  background: transparent;
  color: #64748b;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  flex-shrink: 0;
}
.domain-parent-tab:hover {
  color: #2563eb;
  background: #eff6ff;
}
.domain-parent-tab.active {
  color: #2563eb;
  background: #ffffff;
  border-color: #bfdbfe;
  border-bottom-color: #ffffff;
  font-weight: 700;
  box-shadow: 0 -2px 8px rgba(37, 99, 235, 0.06);
}
.parent-icon {
  font-size: 16px;
}
.parent-label {
  font-size: 13px;
}

.domain-sub-chips {
  padding: 10px 14px 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  border-top: 1px solid #bfdbfe;
  background: #f8faff;
  border-radius: 0 0 8px 8px;
}
.domain-sub-chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 16px;
  background: #ffffff;
  color: #475569;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.domain-sub-chip:hover {
  border-color: #2563eb;
  color: #2563eb;
  background: #eff6ff;
}
.domain-sub-chip.active {
  border-color: #2563eb;
  color: #ffffff;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  font-weight: 700;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.22);
}

/* -- 技能面板 -- Teacher Green -- */
.skill-list {
  padding: 4px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-list > div {
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 10px;
  align-items: center;
  padding: 10px;
  border: 1px solid #a7f3d0;
  border-radius: 8px;
  background: #f6fdf8;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.skill-list > div:hover {
  border-color: #6ee7b7;
  box-shadow: 0 2px 8px rgba(5, 150, 105, 0.08);
}

.skill-icon {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  display: grid;
  place-items: center;
  color: #ffffff;
  font-weight: 800;
  font-size: 13px;
  flex-shrink: 0;
}

.skill-icon.blue {
  background: linear-gradient(135deg, #2563eb, #1e40af);
}

.skill-icon.orange {
  background: linear-gradient(135deg, #f59e0b, #d97706);
}

.skill-icon.green {
  background: linear-gradient(135deg, #059669, #047857);
}

.skill-icon.purple {
  background: linear-gradient(135deg, #7c3aed, #6d28d9);
}

.skill-list strong {
  display: block;
  color: #064e3b;
  font-size: 13px;
}

.skill-list small {
  display: block;
  margin-top: 2px;
  color: #065f46;
  opacity: 0.7;
  font-size: 11px;
  line-height: 1.4;
}

.pool-tags {
  padding: 4px 14px 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.pool-tags span {
  padding: 6px 10px;
  border-radius: 7px;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  color: #047857;
  font-size: 12px;
  cursor: default;
  transition: background 0.15s;
}
.pool-tags span:hover {
  background: #d1fae5;
}

.config-panel dl {
  margin: 0;
  padding: 4px 14px 14px;
}

.config-panel div {
  padding: 10px 0;
  border-top: 1px solid #f1f5f9;
}
.config-panel div:first-child {
  border-top: 0;
}

.config-panel dt {
  color: #94a3b8;
  font-size: 12px;
}

.config-panel dd {
  margin: 4px 0 0;
  color: #0f172a;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.45;
}

.map-panel {
  padding: 16px;
}

.map-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

/* -- 思维树面板 -- Programmer Purple -- */
.map-tabs {
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: 8px;
  background: #f5f3ff;
  min-width: 0;
  overflow-x: auto;
}

.map-tabs button {
  border: 0;
  border-radius: 6px;
  padding: 7px 14px;
  background: transparent;
  color: #7c3aed;
  opacity: 0.65;
  white-space: nowrap;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.map-tabs button:hover {
  opacity: 0.9;
  background: rgba(124, 58, 237, 0.06);
}

.map-tabs button.active {
  color: #6d28d9;
  background: #ffffff;
  font-weight: 700;
  opacity: 1;
  box-shadow: 0 1px 6px rgba(124, 58, 237, 0.12);
}

.zoom-tools {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #60718c;
  font-size: 12px;
}

.zoom-tools button {
  width: 28px;
  height: 28px;
  border-radius: 6px;
}

.mind-map {
  position: relative;
  height: 520px;
  margin-top: 14px;
  border-radius: 8px;
  overflow: hidden;
  background:
    linear-gradient(#ede9fe 1px, transparent 1px),
    linear-gradient(90deg, #ede9fe 1px, transparent 1px),
    #faf9fe;
  background-size: 28px 28px;
  border: 1px solid #ddd6fe;
}

.mindmap-wrap {
  width: 100%;
  height: 100%;
  overflow: hidden;
}
.mindmap-canvas {
  width: 100%;
  height: 100%;
}

/* markmap 自定义主题 - Programmer Purple */
.mindmap-wrap :deep(.markmap-node) {
  cursor: pointer;
  transition: fill 0.2s;
}
.mindmap-wrap :deep(.markmap-node circle) {
  fill: #7c3aed;
  stroke: #6d28d9;
}
.mindmap-wrap :deep(.markmap-node .markmap-node-text) {
  fill: #1e1b4b;
  font-size: 13px;
  font-family: Inter, "PingFang SC", "Microsoft YaHei", sans-serif;
}
.mindmap-wrap :deep(.markmap-link) {
  stroke: #c4b5fd;
  stroke-width: 1.8;
  transition: stroke 0.2s;
}
.mindmap-wrap :deep(.markmap-node:hover circle) {
  fill: #8b5cf6;
  stroke: #7c3aed;
  filter: drop-shadow(0 2px 6px rgba(124, 58, 237, 0.3));
}
.mindmap-wrap :deep(.markmap-node:hover .markmap-node-text) {
  fill: #6d28d9;
  font-weight: 700;
}

.map-lines path {
  fill: none;
  stroke: #c4b5fd;
  stroke-width: 0.5;
  stroke-linecap: round;
}

.mind-node {
  position: absolute;
  width: 178px;
  min-height: 82px;
  padding: 10px 10px 10px 12px;
  border-radius: 8px;
  transform: translate(-50%, -50%);
  border: 1.5px solid #ddd6fe;
  background: #ffffff;
  box-shadow: 0 4px 20px rgba(124, 58, 237, 0.05);
  display: grid;
  grid-template-columns: minmax(0, 1fr) 38px;
  grid-template-areas:
    "title confidence"
    "desc desc";
  column-gap: 6px;
  row-gap: 5px;
  transition: border-color 0.2s, box-shadow 0.2s, background 0.2s;
}

.mind-node.active {
  border-color: #7c3aed;
  background: #faf5ff;
  box-shadow: 0 8px 28px rgba(124, 58, 237, 0.12);
}

.mind-node.root {
  border-color: #c4b5fd;
  background: #f5f3ff;
}

.mind-node.green {
  border-color: #a7f3d0;
  background: #f0fdf4;
}

.mind-node.blue {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.mind-node.muted {
  color: #94a3b8;
  background: #f8fafc;
  border-color: #e2e8f0;
}

.confidence {
  grid-area: confidence;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #059669;
  background: conic-gradient(#10b981 0 78%, #d1fae5 78% 100%);
  font-size: 10px;
  font-weight: 800;
}

.mind-node.active .confidence {
  color: #6d28d9;
  background: conic-gradient(#7c3aed 0 72%, #ede9fe 72% 100%);
}

.mind-node strong {
  grid-area: title;
  display: block;
  color: #1e1b4b;
  font-size: 13px;
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.mind-node span {
  grid-area: desc;
  display: block;
  color: #64748b;
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.mind-node:hover {
  box-shadow: 0 12px 32px rgba(124, 58, 237, 0.1);
  border-color: #7c3aed;
}

.mini-map {
  position: absolute;
  right: 16px;
  bottom: 16px;
  width: 116px;
  height: 78px;
  border-radius: 8px;
  border: 1px solid #dce7f3;
  background: rgba(255, 255, 255, 0.88);
}

.mini-map span {
  position: absolute;
  width: 18px;
  height: 12px;
  border-radius: 4px;
  background: #c7d7ea;
}

.mini-map span:nth-child(1) {
  left: 18px;
  top: 18px;
}

.mini-map span:nth-child(2) {
  left: 48px;
  top: 34px;
}

.mini-map span:nth-child(3) {
  left: 78px;
  top: 48px;
}

.mini-map span.active {
  background: #f59e0b;
}

.inspector-panel {
  padding: 16px;
}

.inspector-tabs {
  display: flex;
  gap: 4px;
  padding: 3px;
  border-radius: 8px;
  background: #f5f3ff;
  width: fit-content;
  max-width: 100%;
  overflow-x: auto;
}

.inspector-tabs button {
  border: 0;
  border-radius: 6px;
  padding: 7px 14px;
  background: transparent;
  color: #7c3aed;
  opacity: 0.65;
  white-space: nowrap;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.15s;
}

.inspector-tabs button:hover {
  opacity: 0.9;
  background: rgba(124, 58, 237, 0.06);
}

.inspector-tabs button.active {
  color: #6d28d9;
  background: #ffffff;
  font-weight: 700;
  opacity: 1;
  box-shadow: 0 1px 6px rgba(124, 58, 237, 0.12);
}

.node-detail {
  margin-top: 14px;
}

.detail-title {
  display: grid;
  grid-template-columns: 42px 1fr auto;
  gap: 12px;
  align-items: start;
}

.node-number {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #6d28d9;
  background: #ede9fe;
  font-weight: 800;
  font-size: 14px;
}

.detail-title h2 {
  margin: 0;
  color: #1e1b4b;
  font-size: 16px;
}

.detail-title p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 13px;
  line-height: 1.55;
}

.detail-status {
  padding: 5px 10px;
  border-radius: 14px;
  color: #059669;
  background: #d1fae5;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.evidence-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.evidence-grid article {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #ddd6fe;
  background: #faf9fe;
}

.evidence-grid strong {
  display: block;
  color: #3b0764;
  font-size: 13px;
}

.evidence-grid p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.command-panel {
  padding: 10px 12px;
  display: grid;
  grid-template-columns: 36px 1fr auto;
  align-items: center;
  gap: 10px;
  border-color: #bfdbfe;
  background: #f8faff;
}

.add-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
  color: #ffffff;
  display: grid;
  place-items: center;
  font-size: 20px;
}

.command-panel input {
  height: 38px;
  border: 0;
  outline: 0;
  color: #1e293b;
  background: transparent;
  font-size: 14px;
  width: 100%;
}

.command-panel button {
  height: 38px;
  padding: 0 18px;
  white-space: nowrap;
  background: linear-gradient(135deg, #2563eb, #1d4ed8);
}

.command-panel button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* -- 数字人助手 -- Writer Amber -- */
.assistant-panel {
  border-color: #fcd34d;
  padding-bottom: 16px;
}

.assistant-card {
  margin: 0 14px;
  padding: 16px;
  border-radius: 10px;
  border: 1px solid #fde68a;
  background: #fffdf5;
  text-align: center;
}

.assistant-avatar-stage {
  width: 100%;
  height: 180px;
  margin: 0 auto 12px;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid #fcd34d;
  background: linear-gradient(180deg, #fffdf5, #fffbeb);
}

.assistant-avatar-stage :deep(.digital-human-container) {
  border-radius: 10px;
  background: transparent;
}

.assistant-avatar-stage :deep(.loading-overlay),
.assistant-avatar-stage :deep(.error-overlay),
.assistant-avatar-stage :deep(.empty-overlay) {
  background: rgba(255, 253, 245, 0.85);
  backdrop-filter: blur(4px);
}

.digital-human-preparing {
  height: 100%;
  display: grid;
  place-items: center;
  color: #92400e;
  font-size: 13px;
}

.assistant-card strong {
  color: #78350f;
}

.assistant-card p {
  margin: 8px 0 0;
  color: #a16207;
  font-size: 13px;
  line-height: 1.6;
}

.online-dot {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #d97706;
}

.online-dot::before {
  content: "";
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #f59e0b;
}

.voice-button {
  width: calc(100% - 28px);
  height: 38px;
  margin: 12px 14px 0;
  border-radius: 8px;
  background: linear-gradient(135deg, #f59e0b, #d97706) !important;
}

/* -- 上下文面板 -- Writer warm -- */
.context-list {
  padding: 4px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.context-list div {
  padding: 10px 0;
  border-top: 1px solid #fef3c7;
  display: flex;
  justify-content: space-between;
  gap: 12px;
}
.context-list div:first-child {
  border-top: 0;
}

.context-list span {
  color: #a16207;
  font-size: 12px;
  flex-shrink: 0;
}

.context-list strong {
  color: #78350f;
  font-size: 13px;
  text-align: right;
}

.reference-list {
  padding: 4px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reference-list article {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  border: 1px solid #fde68a;
  background: #fffbeb;
  transition: border-color 0.15s;
}
.reference-list article:hover {
  border-color: #f59e0b;
}

.reference-list strong {
  color: #78350f;
  font-size: 13px;
  display: block;
}

.reference-list p {
  margin: 4px 0 0;
  color: #a16207;
  font-size: 12px;
}

.reference-list em {
  font-style: normal;
  color: #92400e;
  font-size: 12px;
  font-weight: 800;
  display: flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 12px;
  background: #fef3c7;
}

.suggestion-panel ol {
  margin: 0;
  padding: 4px 16px 14px 32px;
  color: #78350f;
  font-size: 13px;
  line-height: 1.9;
}
.suggestion-panel ol li {
  padding: 2px 0;
}
.suggestion-panel ol li::marker {
  color: #f59e0b;
  font-weight: 700;
}

.mind-node {
  cursor: pointer;
}
.mind-node:hover {
  box-shadow: 0 12px 32px rgba(124, 58, 237, 0.1);
  border-color: #7c3aed;
}

.thought-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.thought-item {
  display: grid;
  grid-template-columns: 28px 1fr;
  gap: 10px;
  align-items: flex-start;
  padding: 10px;
  border: 1px solid #ddd6fe;
  border-radius: 8px;
  background: #faf9fe;
}
.thought-num {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #ede9fe;
  color: #7c3aed;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 800;
}
.thought-item p {
  margin: 0;
  color: #3b0764;
  font-size: 13px;
  line-height: 1.6;
}

.reference-list-inline {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.reference-list-inline article {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 10px;
  padding: 11px;
  border-radius: 8px;
  border: 1px solid #ddd6fe;
  background: #faf9fe;
}
.reference-list-inline strong {
  color: #3b0764;
  font-size: 13px;
}
.reference-list-inline p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 12px;
}
.reference-list-inline em {
  font-style: normal;
  color: #7c3aed;
  font-size: 12px;
  font-weight: 800;
  padding: 2px 8px;
  border-radius: 12px;
  background: #ede9fe;
}

.alt-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.alt-list article {
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #ddd6fe;
  background: #faf9fe;
}
.alt-list strong {
  color: #3b0764;
  font-size: 13px;
}
.alt-list p {
  margin: 6px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.5;
}

.status-footer {
  margin-top: 16px;
  padding: 10px 18px;
  border: 1px solid #bfdbfe;
  border-radius: 10px;
  background: linear-gradient(90deg, rgba(37, 99, 235, 0.03), rgba(255, 255, 255, 0.92));
  color: #475569;
  display: flex;
  flex-wrap: wrap;
  gap: 20px;
  font-size: 12px;
}
.status-footer span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.status-footer span::before {
  content: "";
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #94a3b8;
  flex-shrink: 0;
}
.status-footer span:first-child::before {
  display: none;
}

@media (max-width: 1540px) {
  .planner-grid {
    grid-template-columns: 260px minmax(560px, 1fr);
  }

  .right-column {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: repeat(4, 1fr);
  }
}

@media (max-width: 1320px) {
  .planner-grid {
    grid-template-columns: 250px minmax(0, 1fr);
  }
}

@media (max-width: 1060px) {
  .planner-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .planner-grid {
    grid-template-columns: 1fr;
  }

  .left-column,
  .right-column {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
  }

  .evidence-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .contract-planner {
    padding: 12px;
  }

  .left-column,
  .right-column {
    grid-template-columns: 1fr;
  }

  .mind-map {
    height: auto;
    padding: 14px;
    display: grid;
    gap: 12px;
    overflow: visible;
  }

  .map-lines,
  .mini-map {
    display: none;
  }

  .mind-node {
    position: relative;
    left: auto !important;
    top: auto !important;
    width: auto;
    min-height: 0;
    transform: none;
  }

  .map-toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .detail-title,
  .command-panel {
    grid-template-columns: 1fr;
  }
}
</style>
