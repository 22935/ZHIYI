<template>
  <section class="lawyer-panel">
    <div class="panel-header">
      <h3>律师 Agent 面板</h3>
      <span class="risk-pill" :class="riskLevelClass">风险：{{ displayRiskLevel }}</span>
    </div>

    <div class="section">
      <div class="section-title">联邦增强状态</div>
      <div class="federated-row">
        <span class="status-pill" :class="federatedStatusClass">{{ federatedStatusText }}</span>
        <span class="meta" v-if="federated?.applied">
          调整：{{ formatAdjustment(federated?.risk_adjustment) }} |
          置信度：{{ formatPercent(federated?.confidence) }} |
          节点：{{ federated?.federated_nodes_count ?? 0 }}
        </span>
      </div>
    </div>

    <div class="section">
      <div class="section-title">技能调用</div>
      <div v-if="!skillVisuals.length" class="empty">当前暂无技能调用记录</div>
      <div v-else class="skill-list">
        <div
          v-for="item in skillVisuals"
          :key="item.raw"
          class="skill-item"
          :class="item.tone"
          :title="item.raw"
        >
          <span class="skill-icon">{{ item.icon }}</span>
          <span class="skill-name">{{ item.zh }}</span>
          <span class="skill-state">已调用</span>
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">调用轨迹</div>
      <TraceTimeline :trace="trace" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TraceTimeline, { type TraceStep } from './TraceTimeline.vue'
import { toRiskLevelZh, toSkillNameZh } from '@/utils/agentDisplay'

interface FederatedInfo {
  enabled?: boolean
  applied?: boolean
  risk_adjustment?: number
  confidence?: number
  federated_nodes_count?: number
}

interface SkillVisual {
  icon: string
  tone: 'blue' | 'green' | 'orange' | 'purple' | 'indigo'
}

const props = defineProps<{
  skillsUsed: string[]
  trace: TraceStep[]
  federated?: FederatedInfo
  riskLevel?: string
}>()

const SKILL_VISUAL_MAP: Record<string, SkillVisual> = {
  case_understanding: { icon: '🧠', tone: 'indigo' },
  statute_retrieval: { icon: '📚', tone: 'blue' },
  case_retrieval: { icon: '⚖️', tone: 'blue' },
  evidence_analysis: { icon: '🔍', tone: 'green' },
  limitation_calculation: { icon: '⏳', tone: 'orange' },
  jurisdiction_determination: { icon: '📍', tone: 'purple' },
  hearing_outline_generation: { icon: '📝', tone: 'green' },
  document_generation: { icon: '✍️', tone: 'indigo' },
  risk_assessment: { icon: '🛡️', tone: 'orange' }
}

const skillVisuals = computed(() => {
  return (props.skillsUsed || []).map(raw => {
    const key = (raw || '').trim().toLowerCase()
    const visual = SKILL_VISUAL_MAP[key] || { icon: '⚙️', tone: 'blue' as const }
    return {
      raw,
      zh: toSkillNameZh(raw),
      icon: visual.icon,
      tone: visual.tone
    }
  })
})

const displayRiskLevel = computed(() => toRiskLevelZh(props.riskLevel))

const riskLevelClass = computed(() => {
  const level = (props.riskLevel || '').toLowerCase()
  if (level === 'high') return 'high'
  if (level === 'medium') return 'medium'
  if (level === 'low') return 'low'
  return ''
})

const federatedStatusText = computed(() => {
  if (!props.federated?.enabled) return '已关闭'
  return props.federated?.applied ? '已启用（本轮生效）' : '已开启（本轮未生效）'
})

const federatedStatusClass = computed(() => {
  if (!props.federated?.enabled) return 'off'
  return props.federated?.applied ? 'on' : 'idle'
})

const formatPercent = (v?: number) => `${Math.max(0, Math.round((v || 0) * 100))}%`
const formatAdjustment = (v?: number) => {
  const value = v || 0
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}
</script>

<style scoped>
.lawyer-panel {
  height: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: rgba(255, 255, 255, 0.85);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  backdrop-filter: blur(6px);
  overflow: auto;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}

.risk-pill {
  font-size: 12px;
  border-radius: 999px;
  padding: 4px 10px;
  background: #eef2ff;
  color: #4338ca;
}

.risk-pill.high {
  background: #fee2e2;
  color: #b91c1c;
}

.risk-pill.medium {
  background: #fef3c7;
  color: #92400e;
}

.risk-pill.low {
  background: #dcfce7;
  color: #166534;
}

.section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.section-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  letter-spacing: 0.02em;
}

.federated-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.status-pill {
  width: fit-content;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
}

.status-pill.on {
  background: #dcfce7;
  color: #166534;
}

.status-pill.off {
  background: #f3f4f6;
  color: #374151;
}

.status-pill.idle {
  background: #e0e7ff;
  color: #3730a3;
}

.meta {
  font-size: 12px;
  color: var(--text-secondary);
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.skill-item {
  display: grid;
  grid-template-columns: 24px 1fr auto;
  align-items: center;
  gap: 8px;
  border: 1px solid;
  border-radius: 10px;
  padding: 6px 8px;
  font-size: 12px;
}

.skill-item.blue {
  background: #eff6ff;
  border-color: #bfdbfe;
  color: #1d4ed8;
}

.skill-item.green {
  background: #ecfdf5;
  border-color: #a7f3d0;
  color: #047857;
}

.skill-item.orange {
  background: #fff7ed;
  border-color: #fed7aa;
  color: #c2410c;
}

.skill-item.purple {
  background: #f5f3ff;
  border-color: #ddd6fe;
  color: #6d28d9;
}

.skill-item.indigo {
  background: #eef2ff;
  border-color: #c7d2fe;
  color: #4338ca;
}

.skill-icon {
  text-align: center;
}

.skill-name {
  font-weight: 600;
}

.skill-state {
  font-size: 11px;
  opacity: 0.9;
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
