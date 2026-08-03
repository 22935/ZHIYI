<template>
  <section class="acg-inspector" aria-label="ACG 运行洞察">
    <header class="inspector-head">
      <span class="inspector-mark" aria-hidden="true">
        <el-icon><Cpu /></el-icon>
      </span>
      <div class="inspector-heading">
        <strong>ACG 运行洞察</strong>
        <span>{{ hasRun ? '通用 Agent 的实时运行投影' : '等待通用 Agent 任务' }}</span>
      </div>
      <span v-if="hasRun" class="status-chip" :class="statusTone">
        <i aria-hidden="true"></i>
        {{ statusLabel }}
      </span>
    </header>

    <div v-if="!hasRun" class="inspector-empty">
      <span class="empty-visual" aria-hidden="true">
        <el-icon><DataAnalysis /></el-icon>
      </span>
      <strong>暂无 ACG 运行数据</strong>
      <p>启动通用 Agent 任务后，这里会同步显示规划、节点、执行进度与低熵通信指标。</p>
      <dl class="empty-capabilities" aria-label="可展示的数据">
        <div><dt>规划</dt><dd>阶段与当前步骤</dd></div>
        <div><dt>拓扑</dt><dd>节点与关系</dd></div>
        <div><dt>通信</dt><dd>Token 节省与审计</dd></div>
      </dl>
    </div>

    <div v-else class="inspector-body">
      <section class="run-overview">
        <div class="run-line">
          <span>ACG 任务 ID</span>
          <code :title="runId">{{ shortRunId }}</code>
        </div>
        <strong class="run-message">{{ progressMessage }}</strong>
        <div class="progress-track" :aria-label="`执行进度 ${progressPercent}%`">
          <span :style="{ width: `${progressPercent}%` }"></span>
        </div>
        <div class="progress-meta">
          <span>{{ completedSteps }} / {{ totalSteps }} 步</span>
          <strong>{{ progressPercent }}%</strong>
        </div>
      </section>

      <section class="inspector-section">
        <div class="section-title">
          <span>执行态势</span>
          <span v-if="activeStepLabel" class="active-step" :title="activeStepLabel">{{ activeStepLabel }}</span>
        </div>
        <dl class="signal-list">
          <div>
            <dt>拓扑规模</dt>
            <dd>{{ nodeCount }} 节点 · {{ edgeCount }} 关系</dd>
          </div>
          <div>
            <dt>当前活动</dt>
            <dd>{{ runningSteps }} 运行 · {{ waitingSteps }} 待审</dd>
          </div>
          <div>
            <dt>运行变化</dt>
            <dd>{{ dynamicStepCount }} 新增 · {{ bindingSwitchCount }} 切换</dd>
          </div>
          <div>
            <dt>恢复 / 异常</dt>
            <dd :class="{ danger: recoveryCount > 0 || failedSteps > 0 }">{{ recoveryCount }} / {{ failedSteps }}</dd>
          </div>
        </dl>
      </section>

      <section class="inspector-section">
        <div class="section-title">
          <span>低熵通信</span>
          <span class="integrity" :class="{ warn: !integrityValid }">
            <i aria-hidden="true"></i>
            {{ integrityValid ? '审计通过' : '待校验' }}
          </span>
        </div>
        <div class="entropy-primary">
          <strong>{{ savingPercent }}</strong>
          <span>Token 节省率</span>
        </div>
        <dl class="entropy-details">
          <div><dt>累计节省</dt><dd>{{ formatNumber(tokensSaved) }}</dd></div>
          <div><dt>运行交互</dt><dd>{{ interactionCount }}</dd></div>
          <div><dt>契约异常</dt><dd :class="{ danger: contractViolationCount > 0 }">{{ contractViolationCount }}</dd></div>
        </dl>
      </section>

      <footer class="inspector-actions">
        <button type="button" @click="$emit('open-acg')">
          <el-icon><Share /></el-icon>
          <span>查看 ACG</span>
        </button>
        <button type="button" @click="$emit('open-console')">
          <el-icon><Monitor /></el-icon>
          <span>运行控制</span>
        </button>
      </footer>

    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Cpu, DataAnalysis, Monitor, Share } from '@element-plus/icons-vue'
import type { AcgBlueprint, AcgView, WorkflowProgress, WorkflowRun } from '@/services/api/agentos'

type InspectorProgress = Omit<WorkflowProgress, 'activeStepIds'> & {
  activeStepIds: readonly string[]
}

const props = withDefaults(defineProps<{
  runId?: string
  status?: string
  statusLabel?: string
  run?: WorkflowRun | null
  view?: AcgView | null
  progress?: Readonly<InspectorProgress> | null
  blueprint?: AcgBlueprint | null
  loading?: boolean
}>(), {
  runId: '',
  status: 'pending',
  statusLabel: '等待任务',
  run: null,
  view: null,
  progress: null,
  blueprint: null,
  loading: false
})

defineEmits<{
  'open-acg': []
  'open-console': []
}>()

const hasRun = computed(() => Boolean(props.runId))
const shortRunId = computed(() => {
  if (props.runId.length <= 18) return props.runId
  return `${props.runId.slice(0, 10)}…${props.runId.slice(-6)}`
})
const statusTone = computed(() => {
  if (props.status === 'completed') return 'success'
  if (props.status === 'failed' || props.status === 'cancelled') return 'danger'
  if (props.status === 'waiting_review' || props.status === 'retrying') return 'warning'
  return 'active'
})
const progressPercent = computed(() => {
  const raw = props.progress?.percent ?? props.progress?.percentage ?? props.progress?.progress
  if (typeof raw === 'number' && Number.isFinite(raw)) {
    return Math.max(0, Math.min(100, Math.round(raw)))
  }
  const total = totalSteps.value
  return total > 0 ? Math.round((completedSteps.value / total) * 100) : 0
})
const totalSteps = computed(() => props.progress?.totalSteps ?? props.run?.steps?.length ?? 0)
const completedSteps = computed(() => props.progress?.completedSteps ?? props.view?.completedStepIds?.length ?? props.run?.steps?.filter(step => step.status === 'completed').length ?? 0)
const runningSteps = computed(() => props.progress?.runningSteps ?? props.run?.steps?.filter(step => step.status === 'running').length ?? 0)
const waitingSteps = computed(() => props.progress?.waitingReviewSteps ?? props.run?.steps?.filter(step => step.status === 'waiting_review').length ?? 0)
const failedSteps = computed(() => props.progress?.failedSteps ?? props.run?.steps?.filter(step => step.status === 'failed').length ?? 0)
const recoveryCount = computed(() => props.view?.lowEntropyMetrics?.recoveryCount ?? props.progress?.recoveryCount ?? props.run?.recoveryCount ?? 0)
const progressMessage = computed(() => props.progress?.message || props.run?.title || props.blueprint?.objective || (props.loading ? '正在同步运行数据…' : props.statusLabel))
const activeStepLabel = computed(() => props.progress?.currentStepId || props.run?.currentStepId || props.view?.activeStepIds?.[0] || '')
const nodeCount = computed(() => props.blueprint?.nodes?.length ?? 0)
const edgeCount = computed(() => props.blueprint?.edges?.length ?? 0)
const dynamicStepCount = computed(() => props.view?.dynamicStepCount ?? props.progress?.dynamicStepCount ?? props.run?.dynamicStepCount ?? 0)
const bindingSwitchCount = computed(() => props.view?.bindingSwitchCount ?? props.progress?.bindingSwitchCount ?? props.run?.bindingSwitchCount ?? 0)
const savingRatio = computed(() => props.view?.lowEntropyMetrics?.effectiveSavingRatio ?? props.view?.lowEntropyMetrics?.averageSavingRatio ?? 0)
const savingPercent = computed(() => `${(savingRatio.value * 100).toFixed(1)}%`)
const tokensSaved = computed(() => props.view?.lowEntropyMetrics?.tokensSaved ?? 0)
const interactionCount = computed(() => props.view?.lowEntropyMetrics?.interactionCount ?? props.view?.interactions?.length ?? 0)
const contractViolationCount = computed(() => props.view?.lowEntropyMetrics?.contractViolationCount ?? props.view?.contractViolations?.length ?? 0)
const integrityValid = computed(() => !props.view || props.view.lowEntropyMetrics?.integrityStatus === 'valid')

const formatNumber = (value: number) => {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return String(value)
}
</script>

<style scoped>
.acg-inspector {
  min-height: 100%;
  color: var(--text-primary);
  background: var(--bg-sidebar);
}

.inspector-head {
  min-height: 64px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 46px 10px 14px;
  border-bottom: 1px solid var(--border-light);
}

.inspector-mark,
.empty-visual {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  color: var(--primary-color);
  background: var(--primary-fade);
}

.inspector-mark {
  width: 30px;
  height: 30px;
  border-radius: 8px;
  font-size: 15px;
}

.inspector-heading {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.inspector-heading strong {
  overflow: hidden;
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.inspector-heading span {
  overflow: hidden;
  color: var(--text-disabled);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.status-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-left: auto;
  padding: 3px 7px;
  border-radius: 999px;
  color: var(--primary-color);
  background: var(--primary-fade);
  font-size: 10px;
  font-weight: 650;
  white-space: nowrap;
}

.status-chip i,
.integrity i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: currentColor;
}

.status-chip.success { color: var(--success); background: var(--success-fade); }
.status-chip.warning { color: var(--warning); background: var(--warning-fade); }
.status-chip.danger { color: var(--danger); background: var(--danger-fade); }

.inspector-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 54px 18px 24px;
  text-align: center;
}

.empty-visual {
  width: 42px;
  height: 42px;
  margin-bottom: 13px;
  border-radius: 11px;
  font-size: 21px;
}

.inspector-empty strong { font-size: 13px; }
.inspector-empty p {
  max-width: 250px;
  margin: 7px 0 24px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.65;
}

.empty-capabilities {
  width: 100%;
  margin: 0;
  border-top: 1px solid var(--border-light);
}

.empty-capabilities div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 2px;
  border-bottom: 1px solid var(--border-light);
  font-size: 11px;
}

.empty-capabilities dt { color: var(--text-primary); font-weight: 650; }
.empty-capabilities dd { margin: 0; color: var(--text-muted); }

.inspector-body { min-width: 0; }
.run-overview { padding: 15px 14px 14px; border-bottom: 1px solid var(--border-light); }
.run-line,
.progress-meta,
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.run-line { color: var(--text-muted); font-size: 10px; }
.run-line code {
  overflow: hidden;
  color: var(--text-secondary);
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Consolas, monospace);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.run-message {
  display: block;
  overflow: hidden;
  margin-top: 10px;
  font-size: 12px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-track {
  height: 5px;
  margin-top: 11px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--bg-input);
}

.progress-track span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--primary-color);
  transition: width .24s ease;
}

.progress-meta { margin-top: 6px; color: var(--text-muted); font-size: 10px; }
.progress-meta strong { color: var(--primary-color); }
.inspector-section { padding: 13px 14px; border-bottom: 1px solid var(--border-light); }
.section-title { margin-bottom: 10px; color: var(--text-primary); font-size: 11px; font-weight: 700; }
.active-step {
  max-width: 55%;
  overflow: hidden;
  color: var(--text-muted);
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Consolas, monospace);
  font-size: 9px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.signal-list { margin: 0; }
.signal-list div {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 0;
  border-bottom: 1px solid color-mix(in srgb, var(--border-light) 65%, transparent);
}
.signal-list div:last-child { border-bottom: 0; }
.signal-list dt { color: var(--text-muted); font-size: 10px; }
.signal-list dd { margin: 0; color: var(--text-primary); font-size: 11px; font-weight: 650; }
.danger { color: var(--danger) !important; }

.integrity {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--success);
  font-size: 9px;
  font-weight: 600;
}
.integrity.warn { color: var(--warning); }
.entropy-primary { display: flex; align-items: baseline; gap: 7px; }
.entropy-primary strong { color: var(--primary-color); font-size: 25px; line-height: 1; letter-spacing: -.025em; }
.entropy-primary span { color: var(--text-secondary); font-size: 10px; }
.entropy-details {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  margin: 13px 0 0;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--border-light);
}
.entropy-details div { min-width: 0; padding: 9px 8px; background: var(--bg-panel); }
.entropy-details dt { color: var(--text-muted); font-size: 9px; white-space: nowrap; }
.entropy-details dd { margin: 4px 0 0; color: var(--text-primary); font-size: 14px; font-weight: 700; }

.inspector-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
  padding: 12px 14px;
}
.inspector-actions button {
  min-width: 0;
  height: 31px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid var(--border-light);
  border-radius: 7px;
  color: var(--text-regular);
  background: transparent;
  font: inherit;
  font-size: 10px;
  font-weight: 650;
  cursor: pointer;
}
.inspector-actions button:hover {
  border-color: var(--primary-line);
  color: var(--primary-color);
  background: var(--primary-fade);
}
.inspector-actions button:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }

</style>
