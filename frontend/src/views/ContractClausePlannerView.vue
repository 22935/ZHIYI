<!-- 职业工作台页面 — 知弈 OS 职业智能体工作台，支持角色选择、模板应用和共享操作 -->
<template>
  <section class="career-workbench">
    <header class="career-header">
      <div class="title-block">
        <span class="crumb">知弈OS / 职业智能体 / 工作台</span>
        <h1>职业工作台</h1>
        <p>{{ activeRole.summary }}</p>
      </div>
      <div class="header-actions">
        <label class="mode-toggle" :class="{ api: !isDemoMode }">
          <span>演示</span>
          <button type="button" @click="isDemoMode = !isDemoMode">
            <span class="toggle-knob"></span>
          </button>
          <span>API</span>
        </label>
        <button type="button">共享</button>
        <button type="button">模板</button>
        <button class="primary" type="button" @click="applyPreset">应用配置</button>
      </div>
    </header>

    <div class="career-grid">
      <aside class="left-column">
        <section class="panel role-panel">
          <div class="panel-head">
            <h2>职业角色</h2>
            <span>4 个角色</span>
          </div>
          <div class="role-list">
            <button
              v-for="role in roles"
              :key="role.id"
              type="button"
              class="role-card"
              :class="{ active: activeRoleId === role.id }"
              @click="selectRole(role.id)"
            >
              <span class="role-avatar">{{ role.short }}</span>
              <span>
                <strong>{{ role.name }}</strong>
                <small>{{ role.position }}</small>
              </span>
              <em>{{ role.readiness }}</em>
            </button>
          </div>
        </section>

        <section class="panel domain-panel">
          <div class="panel-head">
            <h2>细分领域</h2>
            <span>{{ activeRole.domains.length }} 个方向</span>
          </div>
          <div class="domain-chips">
            <button
              v-for="domain in activeRole.domains"
              :key="domain.id"
              type="button"
              :class="{ active: activeDomainId === domain.id }"
              @click="selectDomain(domain.id)"
            >
              {{ domain.name }}
            </button>
          </div>
        </section>

        <section class="panel skill-panel">
          <div class="panel-head">
            <h2>已启用能力</h2>
            <span>{{ activeDomain.skills.length }} 项</span>
          </div>
          <div class="skill-list">
            <article v-for="skill in activeDomain.skills" :key="skill.name">
              <span :class="skill.tone">{{ skill.short }}</span>
              <div>
                <strong>{{ skill.name }}</strong>
                <small>{{ skill.desc }}</small>
              </div>
            </article>
          </div>
        </section>

        <section class="panel config-panel">
          <div class="panel-head">
            <h2>当前配置</h2>
          </div>
          <dl>
            <div>
              <dt>角色</dt>
              <dd>{{ activeRole.name }}</dd>
            </div>
            <div>
              <dt>领域</dt>
              <dd>{{ activeDomain.name }}</dd>
            </div>
            <div>
              <dt>输出</dt>
              <dd>{{ activeDomain.deliverable }}</dd>
            </div>
            <div>
              <dt>协作</dt>
              <dd>{{ activeDomain.collaboration }}</dd>
            </div>
          </dl>
        </section>
      </aside>

      <main class="center-column">
        <section class="panel hero-panel">
          <div>
            <span class="eyebrow">{{ activeRole.name }} / {{ activeDomain.name }}</span>
            <h2>{{ activeDomain.title }}</h2>
            <p>{{ activeDomain.description }}</p>
            <div class="tag-row">
              <span v-for="tag in activeDomain.tags" :key="tag">{{ tag }}</span>
            </div>
          </div>
          <div class="score-card">
            <span>就绪度</span>
            <strong>{{ activeDomain.score }}</strong>
            <div class="score-track">
              <i :style="{ width: activeDomain.score }"></i>
            </div>
            <small>{{ activeDomain.eta }}</small>
          </div>
        </section>

        <section class="panel workflow-panel">
          <div class="toolbar">
            <nav class="view-tabs">
              <button :class="{ active: activeView === 'flow' }" type="button" @click="activeView = 'flow'">流程</button>
              <button :class="{ active: activeView === 'knowledge' }" type="button" @click="activeView = 'knowledge'">知识</button>
              <button :class="{ active: activeView === 'deliverable' }" type="button" @click="activeView = 'deliverable'">交付</button>
            </nav>
            <span>{{ activeDomain.workflow.length }} 步</span>
          </div>

          <div v-if="activeView === 'flow'" class="flow-board">
            <article
              v-for="step in activeDomain.workflow"
              :key="step.id"
              class="flow-step"
              :class="{ active: selectedStepId === step.id }"
              @click="selectedStepId = step.id"
            >
              <span>{{ step.no }}</span>
              <strong>{{ step.title }}</strong>
              <small>{{ step.owner }}</small>
              <p>{{ step.desc }}</p>
            </article>
          </div>

          <div v-else-if="activeView === 'knowledge'" class="knowledge-board">
            <article v-for="source in activeDomain.references" :key="source.title">
              <div>
                <strong>{{ source.title }}</strong>
                <p>{{ source.source }}</p>
              </div>
              <em>{{ source.score }}</em>
            </article>
          </div>

          <div v-else class="deliverable-board">
            <article v-for="item in activeDomain.outputs" :key="item.title">
              <strong>{{ item.title }}</strong>
              <p>{{ item.desc }}</p>
            </article>
          </div>
        </section>

        <section class="detail-grid">
          <article class="panel detail-panel">
            <div class="panel-head">
              <h2>当前步骤</h2>
              <span>{{ selectedStep.no }}</span>
            </div>
            <h3>{{ selectedStep.title }}</h3>
            <p>{{ selectedStep.detail }}</p>
            <div class="metric-row">
              <span v-for="metric in activeDomain.metrics" :key="metric.label">
                <strong>{{ metric.value }}</strong>
                <small>{{ metric.label }}</small>
              </span>
            </div>
          </article>

          <article class="panel preview-panel">
            <div class="panel-head">
              <h2>工作预览</h2>
              <span>{{ activeDomain.previewVersion }}</span>
            </div>
            <div class="preview-doc">
              <h3>{{ activeDomain.previewTitle }}</h3>
              <p v-for="line in activeDomain.preview" :key="line">{{ line }}</p>
            </div>
          </article>
        </section>

        <section class="panel command-panel">
          <span class="add-icon">+</span>
          <input
            id="career-command"
            v-model="commandText"
            name="career-command"
            :disabled="isGenerating"
            aria-label="职业工作台指令"
            @keyup.enter="runWorkbench"
          />
          <button type="button" :disabled="isGenerating" @click="runWorkbench">
            {{ isGenerating ? '执行中...' : '执行' }}
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
            <strong>{{ digitalHumanRoleName }} - {{ activeRole.name }}</strong>
            <p>{{ activeDomain.assistantHint }}</p>
          </div>
          <button class="voice-button" type="button" @click="goToVoiceChat">语音说明</button>
        </section>

        <section class="panel context-panel">
          <div class="panel-head">
            <h2>上下文</h2>
            <span>随切换更新</span>
          </div>
          <div class="context-list">
            <div v-for="item in contextItems" :key="item.label">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </section>

        <section class="panel action-panel">
          <div class="panel-head">
            <h2>下一步</h2>
          </div>
          <ol>
            <li v-for="item in activeDomain.nextActions" :key="item">{{ item }}</li>
          </ol>
        </section>
      </aside>
    </div>

    <footer class="status-footer">
      <span>当前角色：{{ activeRole.name }}</span>
      <span>细分领域：{{ activeDomain.name }}</span>
      <span>自动保存：{{ lastSaveTime }}</span>
      <span>{{ isDemoMode ? '演示模式' : 'API 模式' }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import DigitalHuman from '@/components/DigitalHuman.vue'
import { useDigitalHumanRole } from '@/composables/useDigitalHumanRole'

type ViewMode = 'flow' | 'knowledge' | 'deliverable'

interface SkillItem {
  short: string
  name: string
  desc: string
  tone: string
}

interface WorkflowStep {
  id: string
  no: string
  title: string
  owner: string
  desc: string
  detail: string
}

interface DomainConfig {
  id: string
  name: string
  title: string
  description: string
  deliverable: string
  collaboration: string
  score: string
  eta: string
  tags: string[]
  skills: SkillItem[]
  workflow: WorkflowStep[]
  references: Array<{ title: string; source: string; score: string }>
  outputs: Array<{ title: string; desc: string }>
  metrics: Array<{ label: string; value: string }>
  previewTitle: string
  previewVersion: string
  preview: string[]
  assistantHint: string
  nextActions: string[]
  suggestedCommand: string
}

interface RoleConfig {
  id: string
  short: string
  name: string
  position: string
  readiness: string
  summary: string
  domains: DomainConfig[]
}

const router = useRouter()
const { digitalHumanRoleId, digitalHumanRoleName } = useDigitalHumanRole()

const makeWorkflow = (items: Array<[string, string, string, string]>): WorkflowStep[] => {
  return items.map((item, index) => ({
    id: item[0],
    no: String(index + 1).padStart(2, '0'),
    title: item[1],
    owner: item[2],
    desc: item[3],
    detail: `${item[1]}会把${item[3]}拆成可验证的任务片段，并同步到右侧上下文与交付预览。`
  }))
}

const roles: RoleConfig[] = [
  {
    id: 'lawyer',
    short: '法',
    name: '法律顾问',
    position: '合同、合规、争议解决',
    readiness: '96%',
    summary: '面向合同审查、条款起草、证据链整理与合规判断的法律职业工作台。',
    domains: [
      {
        id: 'contract',
        name: '合同法务',
        title: '合同条款审查与起草协同',
        description: '围绕交易背景、交付边界、付款节点、违约责任和知识产权归属形成可审核草案。',
        deliverable: '风险清单 + 条款建议 + 正式草案',
        collaboration: '法律顾问 + 文档专家',
        score: '95%',
        eta: '预计 8 分钟完成首轮分析',
        tags: ['民法典合同编', '软件开发合同', '风险审查', '人工确认'],
        skills: [
          { short: '审', name: '风险审查', desc: '识别付款、验收、权属与违约风险', tone: 'blue' },
          { short: '据', name: '依据匹配', desc: '匹配法规条文、案例与内部模板', tone: 'green' },
          { short: '写', name: '条款生成', desc: '输出严谨版和客户友好版条款', tone: 'purple' }
        ],
        workflow: makeWorkflow([
          ['scope', '任务理解', '法律顾问', '确认交易背景与交付物'],
          ['risk', '风险识别', '法律顾问', '定位核心法律风险'],
          ['clause', '条款生成', '文档专家', '生成可编辑条款建议'],
          ['review', '人工确认', '律师', '复核关键责任边界']
        ]),
        references: [
          { title: '民法典合同编', source: '国家法律法规数据库', score: '98' },
          { title: '软件开发合同模板库', source: '企业常用模板', score: '94' },
          { title: '交付验收争议案例', source: '近三年裁判摘要', score: '89' }
        ],
        outputs: [
          { title: '风险清单', desc: '按高、中、低风险归类并标注触发条件。' },
          { title: '条款建议', desc: '给出原文问题、修改建议与替代表述。' },
          { title: '审查报告', desc: '形成可导出的律师审查报告。' }
        ],
        metrics: [
          { label: '法规命中', value: '18' },
          { label: '风险点', value: '7' },
          { label: '置信度', value: '95%' }
        ],
        previewTitle: '合同审查摘要',
        previewVersion: 'v1.2',
        preview: [
          '已识别交付验收、付款节点和知识产权归属三个重点风险。',
          '建议将“无重大问题视为验收通过”替换为明确的验收材料、期限和异议流程。',
          '源代码权属应与定制开发成果、第三方组件和开源许可分层约定。'
        ],
        assistantHint: '当前建议优先确认验收标准和源代码交付范围，避免后续履约争议。',
        nextActions: ['补充验收材料清单', '确认源码交付边界', '生成律师友好版修改稿'],
        suggestedCommand: '请审查软件开发合同中的验收、付款和知识产权条款'
      },
      {
        id: 'compliance',
        name: '企业合规',
        title: '企业合规事项识别与整改规划',
        description: '把经营场景映射到合规义务、内部制度和整改任务，输出可追踪清单。',
        deliverable: '合规矩阵 + 整改计划',
        collaboration: '法律顾问 + 风控专员',
        score: '91%',
        eta: '预计 10 分钟形成整改路线',
        tags: ['数据合规', '劳动合规', '内控制度', '审计留痕'],
        skills: [
          { short: '规', name: '规则匹配', desc: '定位适用法律和监管口径', tone: 'blue' },
          { short: '控', name: '控制点设计', desc: '拆解制度、流程与留痕要求', tone: 'green' },
          { short: '改', name: '整改计划', desc: '生成责任人和完成节点', tone: 'orange' }
        ],
        workflow: makeWorkflow([
          ['scene', '场景归类', '法律顾问', '识别业务和监管场景'],
          ['gap', '差距分析', '合规专员', '比对现有制度缺口'],
          ['control', '控制设计', '风控专员', '制定控制点与证据要求'],
          ['plan', '整改排期', '项目经理', '生成可追踪任务清单']
        ]),
        references: [
          { title: '个人信息保护法', source: '国家法律法规数据库', score: '96' },
          { title: '企业合规管理指引', source: '内部制度库', score: '90' },
          { title: '数据处理活动记录模板', source: '合规模板库', score: '87' }
        ],
        outputs: [
          { title: '合规义务矩阵', desc: '按场景、义务、证据和责任人组织。' },
          { title: '整改路线图', desc: '列出 30/60/90 天整改计划。' },
          { title: '审计留痕包', desc: '整理制度、审批、培训和记录。' }
        ],
        metrics: [
          { label: '义务项', value: '24' },
          { label: '缺口', value: '6' },
          { label: '覆盖率', value: '91%' }
        ],
        previewTitle: '合规整改概要',
        previewVersion: 'v0.9',
        preview: [
          '客户数据采集、供应商共享和员工权限管理存在制度缺口。',
          '建议优先补齐数据处理台账、授权审批和培训记录。',
          '整改任务应绑定责任部门、证据材料和复核节点。'
        ],
        assistantHint: '合规模式下会优先把问题转成整改任务，而不是只给法律解释。',
        nextActions: ['导入现有制度', '生成合规义务矩阵', '安排整改复核节点'],
        suggestedCommand: '请为企业数据合规场景生成整改计划'
      },
      {
        id: 'ip',
        name: '知识产权',
        title: '知识产权归属、授权与保护策略',
        description: '面向软件、品牌、专利和商业秘密场景，梳理权利边界与保护路径。',
        deliverable: '权属图谱 + 保护策略',
        collaboration: '知识产权律师 + 技术专家',
        score: '93%',
        eta: '预计 7 分钟输出保护建议',
        tags: ['软件著作权', '商标', '商业秘密', '开源组件'],
        skills: [
          { short: '权', name: '权属梳理', desc: '区分自研、委托开发和第三方成果', tone: 'blue' },
          { short: '源', name: '开源识别', desc: '识别开源许可与传染风险', tone: 'green' },
          { short: '护', name: '保护策略', desc: '设计登记、保密和授权安排', tone: 'purple' }
        ],
        workflow: makeWorkflow([
          ['asset', '资产盘点', '知识产权律师', '列出软件、文档、品牌和数据资产'],
          ['ownership', '权属判断', '法律顾问', '判断权利归属和授权范围'],
          ['license', '许可校验', '技术专家', '识别第三方和开源依赖'],
          ['strategy', '保护策略', '律师', '形成登记、合同和保密方案']
        ]),
        references: [
          { title: '著作权法', source: '国家法律法规数据库', score: '97' },
          { title: '开源许可证速查', source: '技术合规库', score: '92' },
          { title: '软件著作权登记指南', source: '知识产权模板库', score: '90' }
        ],
        outputs: [
          { title: '权属图谱', desc: '呈现成果、权利人、授权范围与限制。' },
          { title: '许可风险', desc: '标记开源和第三方组件风险。' },
          { title: '保护方案', desc: '给出登记、合同、保密和取证建议。' }
        ],
        metrics: [
          { label: '资产项', value: '16' },
          { label: '许可风险', value: '3' },
          { label: '置信度', value: '93%' }
        ],
        previewTitle: '知识产权保护建议',
        previewVersion: 'v1.0',
        preview: [
          '定制开发成果应明确归属甲方，通用工具和第三方组件应排除。',
          '开源组件需保留许可证、版本号和再分发限制。',
          '核心算法和客户数据处理规则建议纳入商业秘密保护范围。'
        ],
        assistantHint: '知识产权模式会把“谁拥有、谁能用、怎么保护”分开处理。',
        nextActions: ['上传组件清单', '生成权属图谱', '输出保密条款'],
        suggestedCommand: '请梳理软件项目中的知识产权归属和开源风险'
      }
    ]
  },
  {
    id: 'analyst',
    short: '需',
    name: '需求分析师',
    position: '业务建模、验收、用户研究',
    readiness: '94%',
    summary: '把模糊业务目标转成可执行需求、验收标准和迭代计划。',
    domains: [
      {
        id: 'requirement',
        name: '需求建模',
        title: '业务需求拆解与边界建模',
        description: '从目标、角色、流程、约束和验收口径拆解业务需求。',
        deliverable: '需求规格 + 验收清单',
        collaboration: '需求分析师 + 产品负责人',
        score: '94%',
        eta: '预计 6 分钟完成需求骨架',
        tags: ['用户故事', '业务流程', '验收标准', '边界条件'],
        skills: [
          { short: '拆', name: '目标拆解', desc: '把业务目标转成任务树', tone: 'blue' },
          { short: '流', name: '流程建模', desc: '识别主流程和异常流程', tone: 'green' },
          { short: '验', name: '验收设计', desc: '形成可验证验收条件', tone: 'orange' }
        ],
        workflow: makeWorkflow([
          ['goal', '目标识别', '需求分析师', '确认业务目标和成功标准'],
          ['actor', '角色建模', '产品负责人', '定义用户和权限边界'],
          ['process', '流程拆解', '业务专家', '拆分主流程和异常流程'],
          ['acceptance', '验收条件', '测试负责人', '生成验收标准']
        ]),
        references: [
          { title: '用户故事模板', source: '产品方法库', score: '95' },
          { title: '验收标准样例', source: '项目知识库', score: '91' },
          { title: '异常流程清单', source: '交付经验库', score: '88' }
        ],
        outputs: [
          { title: '需求规格', desc: '包含目标、角色、流程和约束。' },
          { title: '验收清单', desc: '将每条需求转成可测试条件。' },
          { title: '范围边界', desc: '明确本期做什么和不做什么。' }
        ],
        metrics: [
          { label: '需求项', value: '32' },
          { label: '异常流', value: '9' },
          { label: '完整度', value: '94%' }
        ],
        previewTitle: '需求建模摘要',
        previewVersion: 'v1.1',
        preview: [
          '当前目标可拆成客户管理、销售跟进、报表分析三个模块。',
          '需补充角色权限、数据导入失败和客户重复合并规则。',
          '验收口径建议绑定字段、操作步骤和可观察结果。'
        ],
        assistantHint: '需求建模模式会优先问清“谁在什么场景下完成什么目标”。',
        nextActions: ['补充业务角色', '生成用户故事', '导出验收清单'],
        suggestedCommand: '请把 CRM 系统目标拆解成用户故事和验收标准'
      },
      {
        id: 'research',
        name: '用户研究',
        title: '访谈材料整理与洞察提炼',
        description: '把访谈记录、问卷结果和行为数据转成用户画像与机会点。',
        deliverable: '用户画像 + 机会点列表',
        collaboration: '研究员 + 产品经理',
        score: '90%',
        eta: '预计 9 分钟提炼洞察',
        tags: ['访谈', '问卷', '画像', '机会点'],
        skills: [
          { short: '访', name: '访谈编码', desc: '从原始话术抽取主题', tone: 'blue' },
          { short: '像', name: '画像生成', desc: '沉淀用户类型和动机', tone: 'green' },
          { short: '洞', name: '洞察归纳', desc: '归纳痛点和机会点', tone: 'purple' }
        ],
        workflow: makeWorkflow([
          ['data', '材料汇入', '研究员', '整理访谈和问卷材料'],
          ['code', '主题编码', '研究员', '标注高频痛点和动机'],
          ['persona', '画像归纳', '产品经理', '形成用户类型'],
          ['insight', '机会排序', '负责人', '确定优先机会点']
        ]),
        references: [
          { title: '访谈编码框架', source: '研究方法库', score: '93' },
          { title: 'B2B 用户画像模板', source: '产品资料库', score: '89' },
          { title: '机会点评估矩阵', source: '决策模板库', score: '87' }
        ],
        outputs: [
          { title: '访谈摘要', desc: '按主题归纳用户原话和证据。' },
          { title: '用户画像', desc: '呈现目标、阻碍、行为和需求。' },
          { title: '机会排序', desc: '按影响和成本排优先级。' }
        ],
        metrics: [
          { label: '访谈', value: '12' },
          { label: '主题', value: '8' },
          { label: '洞察', value: '14' }
        ],
        previewTitle: '用户研究洞察',
        previewVersion: 'v0.8',
        preview: [
          '销售主管关注线索质量和跟进可视化。',
          '一线销售最怕重复录入和移动端操作复杂。',
          '优先机会点是自动提醒、客户合并和报表模板。'
        ],
        assistantHint: '用户研究模式会保留证据来源，避免凭感觉下结论。',
        nextActions: ['导入访谈记录', '生成画像卡片', '排序机会点'],
        suggestedCommand: '请从销售团队访谈中提炼用户画像和机会点'
      },
      {
        id: 'acceptance',
        name: '验收设计',
        title: '验收标准、测试场景与交付检查',
        description: '把需求转成验收场景、测试步骤和交付检查表。',
        deliverable: '验收用例 + 交付清单',
        collaboration: '需求分析师 + 测试负责人',
        score: '92%',
        eta: '预计 5 分钟生成检查表',
        tags: ['验收用例', '测试步骤', '缺陷等级', '交付清单'],
        skills: [
          { short: '例', name: '用例生成', desc: '生成正向和异常场景', tone: 'blue' },
          { short: '测', name: '测试步骤', desc: '拆解输入、动作和结果', tone: 'green' },
          { short: '交', name: '交付检查', desc: '确认文档、权限和数据', tone: 'orange' }
        ],
        workflow: makeWorkflow([
          ['scope', '范围确认', '需求分析师', '锁定验收范围'],
          ['case', '用例设计', '测试负责人', '生成验收场景'],
          ['data', '测试数据', '业务专家', '准备数据和权限'],
          ['signoff', '签收规则', '项目经理', '明确通过和驳回规则']
        ]),
        references: [
          { title: '验收测试模板', source: '测试知识库', score: '94' },
          { title: '交付清单模板', source: '项目管理库', score: '90' },
          { title: '缺陷等级定义', source: '质量标准库', score: '88' }
        ],
        outputs: [
          { title: '验收用例', desc: '覆盖主流程、异常流程和边界条件。' },
          { title: '测试数据表', desc: '列出账号、权限、初始数据和期望结果。' },
          { title: '签收规则', desc: '明确通过标准和整改时限。' }
        ],
        metrics: [
          { label: '用例', value: '28' },
          { label: '边界项', value: '11' },
          { label: '覆盖率', value: '92%' }
        ],
        previewTitle: '验收设计摘要',
        previewVersion: 'v1.0',
        preview: [
          '建议把验收拆成权限、客户管理、销售跟进和报表四组。',
          '每组应包含操作步骤、输入数据、预期结果和失败处理。',
          '签收规则需约定严重缺陷、一般缺陷和优化项的处理差异。'
        ],
        assistantHint: '验收设计模式会把“满意”变成可测试、可签收的条件。',
        nextActions: ['生成验收用例', '补充测试数据', '导出交付检查表'],
        suggestedCommand: '请为 CRM 项目生成验收用例和交付检查表'
      }
    ]
  },
  {
    id: 'architect',
    short: '架',
    name: '技术架构师',
    position: '系统架构、数据、安全',
    readiness: '92%',
    summary: '面向技术方案、架构评审、数据治理和安全约束的技术职业工作台。',
    domains: [
      {
        id: 'system',
        name: '系统架构',
        title: '系统模块划分与集成架构设计',
        description: '把业务能力映射为模块、接口、部署单元和演进路线。',
        deliverable: '架构图 + 接口清单 + 风险评审',
        collaboration: '架构师 + 后端负责人',
        score: '92%',
        eta: '预计 12 分钟形成初稿',
        tags: ['模块划分', '接口设计', '部署拓扑', '扩展性'],
        skills: [
          { short: '模', name: '模块拆分', desc: '按业务能力划分系统边界', tone: 'blue' },
          { short: '接', name: '接口设计', desc: '定义核心 API 和事件契约', tone: 'green' },
          { short: '险', name: '架构风险', desc: '识别性能、依赖和扩展风险', tone: 'orange' }
        ],
        workflow: makeWorkflow([
          ['capability', '能力地图', '架构师', '映射业务能力'],
          ['module', '模块划分', '后端负责人', '拆分服务和边界'],
          ['integration', '集成设计', '架构师', '定义接口和消息流'],
          ['risk', '风险评审', '技术负责人', '识别架构风险']
        ]),
        references: [
          { title: '微服务边界模板', source: '架构知识库', score: '92' },
          { title: 'API 设计规范', source: '工程标准库', score: '91' },
          { title: '部署拓扑示例', source: 'DevOps 模板库', score: '87' }
        ],
        outputs: [
          { title: '模块图', desc: '展示模块职责和依赖关系。' },
          { title: '接口清单', desc: '列出核心 API、事件和数据对象。' },
          { title: '风险评审', desc: '识别性能、可用性和扩展风险。' }
        ],
        metrics: [
          { label: '模块', value: '9' },
          { label: '接口', value: '24' },
          { label: '风险', value: '5' }
        ],
        previewTitle: '架构设计摘要',
        previewVersion: 'v0.6',
        preview: [
          'CRM 可拆成客户、销售、任务、报表和权限五个核心模块。',
          '客户合并和报表查询是潜在性能热点。',
          '建议将审计日志和权限策略作为横切能力独立设计。'
        ],
        assistantHint: '架构模式会优先关注边界、依赖和未来演进成本。',
        nextActions: ['生成模块图', '梳理接口清单', '输出架构风险表'],
        suggestedCommand: '请为 CRM 系统设计模块架构和接口清单'
      },
      {
        id: 'data',
        name: '数据治理',
        title: '数据模型、质量规则与治理责任',
        description: '梳理数据对象、指标口径、质量规则和治理责任人。',
        deliverable: '数据字典 + 质量规则',
        collaboration: '数据架构师 + 业务负责人',
        score: '90%',
        eta: '预计 9 分钟完成模型草案',
        tags: ['数据字典', '指标口径', '质量规则', '权限分级'],
        skills: [
          { short: '模', name: '数据建模', desc: '抽取实体、关系和字段', tone: 'blue' },
          { short: '质', name: '质量规则', desc: '设置完整性和一致性校验', tone: 'green' },
          { short: '权', name: '权限分级', desc: '定义访问和脱敏策略', tone: 'purple' }
        ],
        workflow: makeWorkflow([
          ['entity', '实体识别', '数据架构师', '抽取核心数据对象'],
          ['field', '字段定义', '业务负责人', '统一字段含义和口径'],
          ['quality', '质量规则', '数据治理专员', '定义校验和修复规则'],
          ['access', '权限策略', '安全负责人', '分级分类和访问控制']
        ]),
        references: [
          { title: '数据字典模板', source: '数据治理库', score: '93' },
          { title: '指标口径规范', source: 'BI 标准库', score: '89' },
          { title: '数据分级分类指南', source: '安全合规库', score: '88' }
        ],
        outputs: [
          { title: '数据字典', desc: '定义实体、字段、类型和含义。' },
          { title: '质量规则', desc: '形成可执行的校验规则。' },
          { title: '权限矩阵', desc: '按角色和数据级别控制访问。' }
        ],
        metrics: [
          { label: '实体', value: '14' },
          { label: '字段', value: '126' },
          { label: '质量规则', value: '18' }
        ],
        previewTitle: '数据治理摘要',
        previewVersion: 'v0.7',
        preview: [
          '客户、联系人、商机、跟进记录是核心实体。',
          '客户来源、成交金额和销售阶段需要统一指标口径。',
          '手机号、邮箱和合同金额应设置访问控制与脱敏规则。'
        ],
        assistantHint: '数据治理模式会把字段含义、质量规则和权限责任绑定起来。',
        nextActions: ['生成数据字典', '定义质量校验', '输出权限矩阵'],
        suggestedCommand: '请为 CRM 系统整理数据字典和质量规则'
      },
      {
        id: 'security',
        name: '安全方案',
        title: '安全威胁识别与防护方案设计',
        description: '针对认证、授权、审计、数据保护和供应链风险形成安全方案。',
        deliverable: '威胁模型 + 防护清单',
        collaboration: '安全工程师 + 架构师',
        score: '89%',
        eta: '预计 11 分钟完成威胁模型',
        tags: ['认证授权', '审计日志', '数据保护', '供应链'],
        skills: [
          { short: '胁', name: '威胁建模', desc: '识别攻击面和滥用路径', tone: 'blue' },
          { short: '防', name: '防护设计', desc: '设计认证、授权和审计', tone: 'green' },
          { short: '测', name: '安全测试', desc: '生成测试项和验收门槛', tone: 'orange' }
        ],
        workflow: makeWorkflow([
          ['asset', '资产识别', '安全工程师', '确定保护对象'],
          ['threat', '威胁建模', '安全工程师', '识别威胁和攻击路径'],
          ['control', '控制措施', '架构师', '设计防护和审计策略'],
          ['test', '安全验收', '测试负责人', '定义安全测试门槛']
        ]),
        references: [
          { title: 'OWASP ASVS', source: '安全标准库', score: '95' },
          { title: '权限模型模板', source: '工程标准库', score: '89' },
          { title: '安全测试清单', source: '质量标准库', score: '88' }
        ],
        outputs: [
          { title: '威胁模型', desc: '列出资产、威胁和防护状态。' },
          { title: '安全控制清单', desc: '覆盖认证、授权、审计和加密。' },
          { title: '测试门槛', desc: '定义上线前必须通过的安全项。' }
        ],
        metrics: [
          { label: '资产', value: '11' },
          { label: '威胁', value: '17' },
          { label: '覆盖率', value: '89%' }
        ],
        previewTitle: '安全方案摘要',
        previewVersion: 'v0.5',
        preview: [
          '客户数据、销售金额和账号权限是核心保护对象。',
          '需重点防范越权访问、弱口令和敏感数据导出。',
          '建议上线前完成权限绕过、审计日志和数据脱敏测试。'
        ],
        assistantHint: '安全方案模式会优先把风险转成可验收的控制项。',
        nextActions: ['生成威胁模型', '补充安全控制', '导出测试清单'],
        suggestedCommand: '请为 CRM 系统生成安全威胁模型和防护清单'
      }
    ]
  },
  {
    id: 'writer',
    short: '文',
    name: '文档专家',
    position: '报告、方案、交付文档',
    readiness: '97%',
    summary: '把过程、证据、结论和交付物整理成结构清晰、可复核的正式文档。',
    domains: [
      {
        id: 'report',
        name: '审查报告',
        title: '审查结论、依据和整改建议成文',
        description: '将风险、证据和处理建议组织成正式报告，支持内部复核和客户沟通。',
        deliverable: '审查报告 + 摘要页',
        collaboration: '文档专家 + 法律顾问',
        score: '97%',
        eta: '预计 4 分钟完成报告初稿',
        tags: ['报告结构', '风险摘要', '依据链', '客户表达'],
        skills: [
          { short: '结', name: '结论归纳', desc: '把复杂信息压缩成摘要', tone: 'blue' },
          { short: '据', name: '证据组织', desc: '绑定依据和风险点', tone: 'green' },
          { short: '版', name: '版式整理', desc: '输出正式文档结构', tone: 'purple' }
        ],
        workflow: makeWorkflow([
          ['material', '材料整理', '文档专家', '聚合风险和依据'],
          ['outline', '报告大纲', '文档专家', '设计章节结构'],
          ['draft', '正文生成', '法律顾问', '生成结论和建议'],
          ['polish', '表达润色', '文档专家', '统一语气和格式']
        ]),
        references: [
          { title: '法律审查报告模板', source: '文档模板库', score: '96' },
          { title: '风险分级说明', source: '质量标准库', score: '91' },
          { title: '客户沟通摘要样例', source: '交付经验库', score: '88' }
        ],
        outputs: [
          { title: '报告正文', desc: '完整呈现风险、依据和建议。' },
          { title: '管理摘要', desc: '适合负责人快速阅读的摘要页。' },
          { title: '整改清单', desc: '按责任、优先级和时限组织。' }
        ],
        metrics: [
          { label: '章节', value: '6' },
          { label: '证据链', value: '12' },
          { label: '清晰度', value: '97%' }
        ],
        previewTitle: '审查报告预览',
        previewVersion: 'v1.3',
        preview: [
          '本报告聚焦合同履约、付款、验收和知识产权风险。',
          '高风险问题建议在签署前修改，中风险问题可通过补充附件解决。',
          '所有建议均已绑定对应合同原文和法律依据。'
        ],
        assistantHint: '文档专家会把复杂过程变成可以给客户或管理层阅读的文本。',
        nextActions: ['生成管理摘要', '插入风险表格', '导出正式报告'],
        suggestedCommand: '请把合同审查结果整理成正式报告'
      },
      {
        id: 'proposal',
        name: '解决方案',
        title: '业务方案、实施路径与资源计划',
        description: '把目标、范围、实施步骤、资源和风险整理成可执行方案。',
        deliverable: '解决方案 + 实施计划',
        collaboration: '文档专家 + 项目经理',
        score: '94%',
        eta: '预计 7 分钟完成方案初稿',
        tags: ['方案结构', '实施路径', '资源计划', '风险控制'],
        skills: [
          { short: '框', name: '框架搭建', desc: '形成方案章节结构', tone: 'blue' },
          { short: '路', name: '路径规划', desc: '拆解阶段和里程碑', tone: 'green' },
          { short: '险', name: '风险提示', desc: '补充风险和应对措施', tone: 'orange' }
        ],
        workflow: makeWorkflow([
          ['target', '目标确认', '项目经理', '明确业务目标和范围'],
          ['solution', '方案设计', '文档专家', '设计解决路径'],
          ['plan', '实施计划', '项目经理', '安排资源和里程碑'],
          ['risk', '风险控制', '负责人', '形成风险和应对方案']
        ]),
        references: [
          { title: '解决方案模板', source: '文档模板库', score: '94' },
          { title: '项目计划样例', source: '项目管理库', score: '90' },
          { title: '风险登记册', source: '交付经验库', score: '87' }
        ],
        outputs: [
          { title: '方案正文', desc: '清楚说明现状、目标、路径和收益。' },
          { title: '实施计划', desc: '按阶段列出任务、责任和里程碑。' },
          { title: '风险登记册', desc: '记录风险、概率、影响和应对。' }
        ],
        metrics: [
          { label: '阶段', value: '4' },
          { label: '任务', value: '21' },
          { label: '完整度', value: '94%' }
        ],
        previewTitle: '解决方案摘要',
        previewVersion: 'v0.9',
        preview: [
          '方案分为调研、设计、开发、上线四个阶段。',
          '关键成功因素包括业务负责人参与、数据质量和验收机制。',
          '建议在每个阶段设置可交付成果和决策门。'
        ],
        assistantHint: '解决方案模式会把想法整理成客户能批准、团队能执行的计划。',
        nextActions: ['生成方案目录', '补充实施计划', '输出风险登记册'],
        suggestedCommand: '请为 CRM 项目生成实施解决方案'
      },
      {
        id: 'handover',
        name: '交付说明',
        title: '交付材料、使用说明与运维边界',
        description: '为项目交付整理材料清单、使用说明、运维边界和签收说明。',
        deliverable: '交付包 + 使用说明',
        collaboration: '文档专家 + 运维负责人',
        score: '95%',
        eta: '预计 5 分钟完成交付包',
        tags: ['交付清单', '使用说明', '运维边界', '签收'],
        skills: [
          { short: '清', name: '清单整理', desc: '归档代码、文档和账号', tone: 'blue' },
          { short: '用', name: '使用说明', desc: '生成操作和常见问题', tone: 'green' },
          { short: '维', name: '运维边界', desc: '明确责任和支持范围', tone: 'purple' }
        ],
        workflow: makeWorkflow([
          ['inventory', '材料盘点', '文档专家', '整理交付物清单'],
          ['guide', '说明编写', '产品负责人', '生成使用说明'],
          ['ops', '运维边界', '运维负责人', '明确支持范围'],
          ['sign', '签收确认', '项目经理', '形成签收说明']
        ]),
        references: [
          { title: '项目交付清单模板', source: '交付模板库', score: '95' },
          { title: '用户手册样例', source: '文档资料库', score: '90' },
          { title: '运维 SLA 模板', source: '运维知识库', score: '88' }
        ],
        outputs: [
          { title: '交付清单', desc: '代码、部署包、文档、账号和数据。' },
          { title: '使用手册', desc: '按角色说明核心操作和注意事项。' },
          { title: '签收说明', desc: '确认范围、遗留项和支持边界。' }
        ],
        metrics: [
          { label: '材料', value: '19' },
          { label: '角色', value: '5' },
          { label: '完整度', value: '95%' }
        ],
        previewTitle: '交付说明预览',
        previewVersion: 'v1.0',
        preview: [
          '交付包应包含部署包、源代码、接口文档、用户手册和管理员账号。',
          '运维支持范围需区分故障修复、功能优化和新增需求。',
          '签收说明建议记录遗留项、处理人和完成时限。'
        ],
        assistantHint: '交付说明模式会尽量减少项目交接时的信息丢失。',
        nextActions: ['生成交付清单', '补充用户手册', '输出签收说明'],
        suggestedCommand: '请为 CRM 项目整理交付清单和使用说明'
      }
    ]
  }
]

const activeRoleId = ref(roles[0].id)
const activeDomainId = ref(roles[0].domains[0].id)
const activeView = ref<ViewMode>('flow')
const selectedStepId = ref(roles[0].domains[0].workflow[0].id)
const isDemoMode = ref(true)
const isGenerating = ref(false)
const commandText = ref(roles[0].domains[0].suggestedCommand)
const lastSaveTime = ref(new Date().toLocaleTimeString('zh-CN', { hour12: false }))

const activeRole = computed(() => roles.find(role => role.id === activeRoleId.value) || roles[0])
const activeDomain = computed(() => {
  return activeRole.value.domains.find(domain => domain.id === activeDomainId.value) || activeRole.value.domains[0]
})
const selectedStep = computed(() => {
  return activeDomain.value.workflow.find(step => step.id === selectedStepId.value) || activeDomain.value.workflow[0]
})
const contextItems = computed(() => [
  { label: '角色定位', value: activeRole.value.position },
  { label: '任务领域', value: activeDomain.value.name },
  { label: '协作方式', value: activeDomain.value.collaboration },
  { label: '交付物', value: activeDomain.value.deliverable }
])

function resetDomainState(domain: DomainConfig) {
  activeView.value = 'flow'
  selectedStepId.value = domain.workflow[0].id
  commandText.value = domain.suggestedCommand
  lastSaveTime.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

function selectRole(roleId: string) {
  const nextRole = roles.find(role => role.id === roleId)
  if (!nextRole || nextRole.id === activeRoleId.value) return
  activeRoleId.value = nextRole.id
  activeDomainId.value = nextRole.domains[0].id
  resetDomainState(nextRole.domains[0])
}

function selectDomain(domainId: string) {
  const nextDomain = activeRole.value.domains.find(domain => domain.id === domainId)
  if (!nextDomain || nextDomain.id === activeDomainId.value) return
  activeDomainId.value = nextDomain.id
  resetDomainState(nextDomain)
}

function applyPreset() {
  ElMessage.success(`已应用 ${activeRole.value.name} / ${activeDomain.value.name} 配置`)
}

async function runWorkbench() {
  if (!commandText.value.trim()) return
  isGenerating.value = true
  await new Promise(resolve => window.setTimeout(resolve, 650))
  lastSaveTime.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
  isGenerating.value = false
  ElMessage.success(`${activeDomain.value.name}任务已生成工作预览`)
}

function goToVoiceChat() {
  router.push('/voice-chat')
}
</script>

<style scoped>
.career-workbench {
  min-height: 100%;
  overflow: visible;
  color: var(--text-primary);
  padding: 20px 24px 28px;
}

button {
  font: inherit;
}

.career-header,
.panel {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 88%, transparent);
  box-shadow: var(--shadow-sm);
}

.career-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 18px;
  backdrop-filter: var(--backdrop-blur);
}

.title-block {
  min-width: 0;
}

.crumb,
.eyebrow {
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 800;
}

h1,
h2,
h3,
p,
dl,
dd {
  margin: 0;
}

h1 {
  margin-top: 6px;
  font-size: 26px;
  line-height: 1.2;
}

.title-block p,
.hero-panel p,
.preview-doc p,
.flow-step p,
.assistant-card p,
.skill-list small,
.role-card small,
.knowledge-board p,
.deliverable-board p,
dt,
dd,
.status-footer,
.detail-panel p {
  color: var(--text-secondary);
}

.title-block p {
  margin-top: 6px;
  max-width: 760px;
  line-height: 1.6;
}

.header-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.header-actions button,
.voice-button,
.command-panel button {
  height: 36px;
  padding: 0 13px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--surface-solid);
  color: var(--text-primary);
  cursor: pointer;
  transition: var(--transition);
}

.header-actions button:hover,
.voice-button:hover,
.command-panel button:hover:not(:disabled) {
  border-color: var(--border-hover);
  color: var(--primary-color);
  transform: translateY(-1px);
}

.header-actions .primary,
.command-panel button {
  border-color: transparent;
  background: var(--primary-color);
  color: #fff;
  font-weight: 800;
}

.header-actions .primary:hover,
.command-panel button:hover:not(:disabled) {
  background: var(--primary-hover);
  color: #fff;
}

.mode-toggle {
  min-height: 36px;
  padding: 4px 7px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-input);
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 800;
}

.mode-toggle button {
  width: 42px;
  height: 22px;
  padding: 2px;
  border: 0;
  border-radius: 999px;
  background: var(--primary-color);
}

.mode-toggle.api button {
  background: var(--info);
}

.toggle-knob {
  display: block;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--surface-solid);
  transition: var(--transition);
}

.mode-toggle.api .toggle-knob {
  transform: translateX(18px);
}

.career-grid {
  margin-top: 16px;
  display: grid;
  grid-template-columns: minmax(248px, 280px) minmax(0, 1fr) minmax(300px, 340px);
  gap: 16px;
  align-items: stretch;
  min-height: min(820px, calc(100vh - 188px));
}

.left-column,
.center-column,
.right-column {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  height: 100%;
}

.panel {
  min-width: 0;
  padding: 16px;
}

.panel-head,
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 12px;
}

.panel-head h2 {
  font-size: 15px;
}

.panel-head span,
.toolbar span {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}

.role-list,
.skill-list,
.domain-chips,
.context-list,
.action-panel ol,
.knowledge-board,
.deliverable-board {
  display: grid;
  gap: 10px;
}

.role-card {
  width: 100%;
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
  text-align: left;
  cursor: pointer;
  transition: var(--transition);
}

.role-card:hover,
.role-card.active {
  border-color: var(--primary-line);
  background: var(--surface-solid);
  box-shadow: var(--shadow-sm);
}

.role-avatar,
.skill-list span {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-weight: 900;
}

.role-card strong,
.role-card small,
.skill-list strong,
.skill-list small {
  display: block;
  overflow-wrap: anywhere;
}

.role-card em {
  color: var(--success);
  font-size: 12px;
  font-style: normal;
  font-weight: 900;
}

.domain-chips {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.domain-chips button,
.view-tabs button {
  min-height: 34px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
  font-weight: 750;
}

.domain-chips button.active,
.view-tabs button.active {
  border-color: var(--primary-line);
  background: var(--primary-fade);
  color: var(--primary-color);
}

.skill-list article {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr);
  gap: 10px;
  align-items: center;
}

.skill-list span.green { color: var(--success); background: rgba(83, 129, 114, 0.12); }
.skill-list span.orange { color: var(--warning); background: rgba(173, 117, 56, 0.12); }
.skill-list span.purple { color: var(--info); background: rgba(73, 107, 143, 0.12); }

.config-panel dl {
  display: grid;
  gap: 9px;
}

.config-panel dl > div {
  padding: 9px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

dt {
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 800;
}

dd {
  font-size: 13px;
  overflow-wrap: anywhere;
}

.hero-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(190px, 240px);
  gap: 16px;
  align-items: center;
}

.hero-panel h2 {
  margin-top: 6px;
  font-size: 22px;
  line-height: 1.25;
}

.hero-panel p {
  margin-top: 8px;
  line-height: 1.65;
}

.tag-row {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-row span {
  padding: 6px 10px;
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-input);
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 800;
}

.score-card {
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.score-card span,
.score-card small {
  color: var(--text-secondary);
  font-size: 12px;
}

.score-card strong {
  display: block;
  margin: 8px 0;
  color: var(--primary-color);
  font-size: 34px;
  line-height: 1;
}

.score-track {
  height: 8px;
  margin-bottom: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: var(--primary-fade);
}

.score-track i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--primary-color);
}

.workflow-panel {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.view-tabs {
  display: inline-grid;
  grid-template-columns: repeat(3, minmax(74px, 1fr));
  gap: 4px;
  padding: 4px;
  border-radius: 8px;
  background: var(--bg-input);
}

.view-tabs button {
  border: 0;
  min-height: 32px;
}

.flow-board {
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  align-content: start;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.flow-step {
  min-width: 0;
  min-height: 170px;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
  cursor: pointer;
  transition: var(--transition);
}

.flow-step:hover,
.flow-step.active {
  border-color: var(--primary-line);
  background: var(--surface-solid);
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}

.flow-step span {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 12px;
  font-weight: 900;
}

.flow-step strong,
.flow-step small {
  display: block;
}

.flow-step strong {
  margin-top: 16px;
}

.flow-step small {
  margin-top: 6px;
  color: var(--primary-color);
  font-weight: 800;
}

.flow-step p {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.55;
}

.knowledge-board,
.deliverable-board {
  flex: 1 1 auto;
  max-height: clamp(240px, 36vh, 440px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.knowledge-board article,
.deliverable-board article {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  padding: 13px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.deliverable-board article {
  grid-template-columns: 1fr;
}

.knowledge-board em {
  color: var(--primary-color);
  font-style: normal;
  font-weight: 900;
}

.detail-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.95fr) minmax(0, 1.05fr);
  gap: 14px;
}

.detail-panel,
.preview-panel {
  min-height: 260px;
}

.detail-panel h3 {
  font-size: 18px;
}

.detail-panel p {
  margin-top: 10px;
  line-height: 1.7;
}

.metric-row {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}

.metric-row span {
  padding: 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.metric-row strong,
.metric-row small {
  display: block;
}

.metric-row strong {
  color: var(--primary-color);
  font-size: 20px;
}

.metric-row small {
  margin-top: 4px;
  color: var(--text-secondary);
}

.preview-doc {
  padding: 16px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-input);
  max-height: clamp(180px, 28vh, 320px);
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.preview-doc h3 {
  text-align: center;
  font-size: 17px;
}

.preview-doc p {
  margin-top: 12px;
  line-height: 1.75;
}

.command-panel {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr) auto;
  gap: 10px;
  align-items: center;
}

.add-icon {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--bg-input);
  color: var(--primary-color);
  font-size: 22px;
  font-weight: 300;
}

.command-panel input {
  width: 100%;
  min-width: 0;
  height: 40px;
  padding: 0 12px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: var(--bg-input);
  color: var(--text-primary);
  outline: none;
}

.command-panel input:focus {
  border-color: var(--primary-line);
  background: var(--surface-solid);
  box-shadow: 0 0 0 3px var(--primary-fade);
}

.assistant-panel,
.context-panel,
.action-panel {
  min-height: 0;
}

.assistant-panel {
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
}

.assistant-card {
  flex: 1 1 auto;
  text-align: center;
}

.assistant-avatar-stage {
  width: 100%;
  aspect-ratio: 4 / 3;
  margin-bottom: 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
  background: var(--bg-panel);
}

.assistant-avatar-stage :deep(.digital-human-container) {
  border-radius: 8px;
  background: transparent;
}

.digital-human-preparing {
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.assistant-card p {
  margin-top: 10px;
  line-height: 1.6;
  font-size: 13px;
}

.voice-button {
  width: 100%;
  margin-top: 12px;
  background: var(--primary-color);
  color: #fff;
  font-weight: 800;
}

.online-dot {
  color: var(--success);
}

.context-list div {
  display: grid;
  gap: 4px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-panel);
}

.context-list span {
  color: var(--text-secondary);
  font-size: 12px;
}

.context-list strong {
  overflow-wrap: anywhere;
}

.action-panel ol {
  margin: 0;
  padding-left: 20px;
  color: var(--text-secondary);
  line-height: 1.75;
}

.status-footer {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.status-footer span {
  padding: 7px 10px;
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-card) 78%, transparent);
}

@media (max-width: 1280px) {
  .career-grid {
    grid-template-columns: minmax(230px, 260px) minmax(0, 1fr);
  }

  .right-column {
    grid-column: 1 / -1;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 1040px) {
  .career-header,
  .hero-panel {
    grid-template-columns: 1fr;
    flex-direction: column;
    align-items: flex-start;
  }

  .career-grid,
  .detail-grid {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .left-column,
  .right-column {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .flow-board {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .career-workbench {
    padding: 14px;
  }

  .header-actions,
  .left-column,
  .right-column,
  .flow-board,
  .domain-chips,
  .metric-row {
    grid-template-columns: 1fr;
    width: 100%;
  }

  .command-panel {
    grid-template-columns: 36px 1fr;
  }

  .command-panel button {
    grid-column: 1 / -1;
  }
}
</style>
