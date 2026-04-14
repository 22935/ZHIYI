<template>
  <section class="lawyer-panel">
    <div class="panel-header">
      <h3>律师 Agent 面板</h3>
      <span class="risk-pill" :class="riskLevelClass">风险: {{ displayRiskLevel }}</span>
    </div>

    <div class="section">
      <div class="section-title">联邦增强开关</div>
      <div class="federated-row">
        <span class="status-pill" :class="federatedStatusClass">{{ federatedStatusText }}</span>
        <span class="meta" v-if="federated?.applied">
          调整: {{ formatAdjustment(federated?.risk_adjustment) }} |
          置信度: {{ formatPercent(federated?.confidence) }} |
          节点: {{ federated?.federated_nodes_count ?? 0 }}
        </span>
      </div>
    </div>

    <div class="section">
      <div class="section-title">Skills 调用</div>
      <div v-if="!skillsUsed.length" class="empty">当前暂无技能调用记录</div>
      <div v-else class="skill-tags">
        <span v-for="name in skillsUsed" :key="name" class="skill-tag">{{ name }}</span>
      </div>
    </div>

    <div class="section">
      <div class="section-title">ReAct 轨迹</div>
      <TraceTimeline :trace="trace" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import TraceTimeline, { type TraceStep } from './TraceTimeline.vue'

interface FederatedInfo {
  enabled?: boolean
  applied?: boolean
  risk_adjustment?: number
  confidence?: number
  federated_nodes_count?: number
}

const props = defineProps<{
  skillsUsed: string[]
  trace: TraceStep[]
  federated?: FederatedInfo
  riskLevel?: string
}>()

const displayRiskLevel = computed(() => {
  if (!props.riskLevel) return 'unknown'
  return props.riskLevel
})

const riskLevelClass = computed(() => {
  const level = (props.riskLevel || '').toLowerCase()
  if (level === 'high') return 'high'
  if (level === 'medium') return 'medium'
  if (level === 'low') return 'low'
  return ''
})

const federatedStatusText = computed(() => {
  if (!props.federated?.enabled) return '关闭'
  return props.federated?.applied ? '已启用' : '已开启(本轮未命中)'
})

const federatedStatusClass = computed(() => {
  if (!props.federated?.enabled) return 'off'
  return props.federated?.applied ? 'on' : 'idle'
})

const formatPercent = (v?: number) => `${Math.max(0, Math.round((v || 0) * 100))}%`
const formatAdjustment = (v?: number) => {
  const value = v || 0
  return `${value >= 0 ? '+' : ''}${(value * 100).toFixed(1)}`
}
</script>

<style scoped>
.lawyer-panel {
  height: 100%;
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
  letter-spacing: .02em;
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

.skill-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.skill-tag {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 8px;
  border: 1px solid #dbeafe;
  background: #eff6ff;
  color: #1d4ed8;
}

.empty {
  font-size: 12px;
  color: var(--text-secondary);
}
</style>
