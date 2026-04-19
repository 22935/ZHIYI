<template>
  <section class="skill-panel lawyer-panel">
    <div class="panel-header">
      <div class="header-left">
        <div class="agent-avatar">⚖️</div>
        <div class="header-text">
          <h3>律师 Agent 工作台</h3>
          <span class="header-sub">智能法律助手</span>
        </div>
      </div>
      <div class="header-badges">
        <span class="risk-pill" :class="riskLevelClass">风险：{{ displayRiskLevel }}</span>
        <span class="skill-pill">
          <span class="pill-dot"></span>
          技能 {{ skillsUsed?.length || 0 }}
        </span>
      </div>
    </div>

    <div class="panel-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-btn"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        <span class="tab-icon">{{ tab.icon }}</span>
        <span class="tab-label">{{ tab.label }}</span>
        <span v-if="tab.count > 0" class="tab-badge">{{ tab.count }}</span>
      </button>
    </div>

    <div class="panel-body">
      <div v-show="activeTab === 'skills'" class="tab-content">
        <div class="sub-section">
          <div class="sub-title">联邦增强状态</div>
          <div class="federated-row">
            <span class="status-pill" :class="federatedStatusClass">{{ federatedStatusText }}</span>
            <span class="meta" v-if="federated?.applied">
              调整：{{ formatAdjustment(federated?.risk_adjustment) }} | 置信度：{{ formatPercent(federated?.confidence) }} |
              节点：{{ federated?.federated_nodes_count ?? 0 }}
            </span>
            <div class="federated-actions">
              <button class="federated-btn ghost" type="button" @click="emit('open-federated-console')">联邦控制台</button>
              <button
                class="federated-btn"
                type="button"
                :disabled="federated?.enabled === false"
                @click="emit('optimize-federated')"
              >
                联邦优化
              </button>
            </div>
          </div>
        </div>

        <div class="sub-section">
          <div class="sub-title">已调用技能</div>
          <div v-if="!skillVisuals.length" class="empty">
            <div class="empty-illustration">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="20" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4 3"/>
                <path d="M18 22h12M18 26h8" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span>暂无技能调用记录</span>
            <span class="empty-hint">发送消息后，律师 Agent 将自动调用相关技能</span>
          </div>
          <div v-else class="skill-list">
            <div
              v-for="(item, idx) in skillVisuals"
              :key="item.raw"
              class="skill-item"
              :class="item.tone"
              :style="{ animationDelay: `${idx * 0.06}s` }"
              :title="item.raw"
            >
              <span class="skill-icon">{{ item.icon }}</span>
              <span class="skill-name">{{ item.zh }}</span>
              <span class="skill-state">
                <span class="state-dot"></span>
                已执行
              </span>
            </div>
          </div>
        </div>
      </div>

      <div v-show="activeTab === 'trace'" class="tab-content">
        <div v-if="!trace.length" class="empty">
          <div class="empty-illustration">
            <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
              <circle cx="24" cy="24" r="20" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4 3"/>
              <path d="M16 20l6 6 10-10" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <span>暂无调用轨迹</span>
          <span class="empty-hint">技能执行后将展示完整调用链路</span>
        </div>
        <div v-else class="trace-container">
          <TraceTimeline :trace="trace" />
        </div>
      </div>

      <div v-show="activeTab === 'results'" class="tab-content results-tab">
        <slot name="results">
          <div class="empty">
            <div class="empty-illustration">
              <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
                <circle cx="24" cy="24" r="20" stroke="#d1d5db" stroke-width="1.5" stroke-dasharray="4 3"/>
                <rect x="16" y="16" width="16" height="16" rx="3" stroke="#9ca3af" stroke-width="1.5"/>
                <path d="M20 24h8M24 20v8" stroke="#9ca3af" stroke-width="1.5" stroke-linecap="round"/>
              </svg>
            </div>
            <span>暂无技能调用结果</span>
            <span class="empty-hint">技能执行完成后将展示详细结果</span>
          </div>
        </slot>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
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
  tone: 'blue' | 'sky' | 'indigo' | 'cyan' | 'slate'
}

const props = defineProps<{
  skillsUsed: string[]
  trace: TraceStep[]
  federated?: FederatedInfo
  riskLevel?: string
  resultCount?: number
}>()

const emit = defineEmits<{
  (e: 'open-federated-console'): void
  (e: 'optimize-federated'): void
}>()

const activeTab = ref<'skills' | 'trace' | 'results'>('skills')

const tabs = computed(() => [
  { key: 'skills' as const, label: '技能调用', icon: '⚡', count: props.skillsUsed?.length || 0 },
  { key: 'trace' as const, label: '调用轨迹', icon: '🔗', count: props.trace?.length || 0 },
  { key: 'results' as const, label: '调用结果', icon: '📊', count: props.resultCount || 0 }
])

const SKILL_VISUAL_MAP: Record<string, SkillVisual> = {
  case_understanding: { icon: '🧠', tone: 'indigo' },
  statute_retrieval: { icon: '📚', tone: 'blue' },
  case_retrieval: { icon: '⚖️', tone: 'sky' },
  evidence_analysis: { icon: '📋', tone: 'cyan' },
  limitation_calculation: { icon: '⏳', tone: 'slate' },
  jurisdiction_determination: { icon: '📍', tone: 'indigo' },
  hearing_outline_generation: { icon: '📝', tone: 'blue' },
  document_generation: { icon: '✍️', tone: 'sky' },
  risk_assessment: { icon: '🛡️', tone: 'cyan' }
}

const skillVisuals = computed(() => {
  return (props.skillsUsed || []).map(raw => {
    const key = (raw || '').trim().toLowerCase()
    const visual = SKILL_VISUAL_MAP[key] || { icon: '🧩', tone: 'blue' as const }
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
.skill-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  overflow: hidden;
  height: 100%;
}

.lawyer-panel {
  border-top: 3px solid #2563eb;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 40%, #eef2ff 100%);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.agent-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  background: linear-gradient(135deg, #2563eb, #3b82f6);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.25);
}

.header-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.panel-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}

.header-sub {
  font-size: 11px;
  color: #2563eb;
  font-weight: 500;
}

.header-badges {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.risk-pill {
  font-size: 11px;
  border-radius: 999px;
  padding: 3px 10px;
  background: #eef2ff;
  color: #4338ca;
  white-space: nowrap;
  font-weight: 600;
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

.skill-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  border-radius: 999px;
  padding: 3px 10px;
  background: #eff6ff;
  color: #2563eb;
  white-space: nowrap;
  font-weight: 600;
  border: 1px solid #bfdbfe;
}

.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #2563eb;
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-light);
  background: #fafbfc;
}

.tab-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 10px 8px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  transition: all 0.2s ease;
  border-bottom: 2px solid transparent;
  position: relative;
}

.tab-btn:hover {
  background: rgba(37, 99, 235, 0.05);
  color: var(--text-primary);
}

.tab-btn.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
  background: rgba(37, 99, 235, 0.06);
}

.tab-icon {
  font-size: 14px;
}

.tab-label {
  white-space: nowrap;
}

.tab-badge {
  font-size: 10px;
  min-width: 16px;
  height: 16px;
  line-height: 16px;
  text-align: center;
  border-radius: 999px;
  background: #dbeafe;
  color: #1e40af;
  padding: 0 4px;
  font-weight: 700;
}

.tab-btn.active .tab-badge {
  background: #2563eb;
  color: #fff;
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.tab-content {
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 14px 16px;
}

.tab-content::-webkit-scrollbar {
  width: 5px;
}

.tab-content::-webkit-scrollbar-track {
  background: transparent;
}

.tab-content::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 999px;
}

.tab-content::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

.sub-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.sub-title {
  font-size: 11px;
  font-weight: 700;
  color: #2563eb;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.federated-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.federated-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.federated-btn {
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.federated-btn:hover:not(:disabled) {
  border-color: #2563eb;
  background: #dbeafe;
}

.federated-btn.ghost {
  border-color: #dbeafe;
  background: #fff;
  color: #2563eb;
}

.federated-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.status-pill {
  width: fit-content;
  border-radius: 999px;
  padding: 3px 10px;
  font-size: 12px;
  font-weight: 500;
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
  background: #eef2ff;
  color: #3730a3;
}

.meta {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.45;
  word-break: break-word;
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skill-item {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  border: 1px solid;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 12px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
  animation: skill-slide-in 0.3s ease-out both;
}

@keyframes skill-slide-in {
  from {
    opacity: 0;
    transform: translateX(-6px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.skill-item:hover {
  transform: translateX(3px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.skill-item.blue {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border-color: #93c5fd;
  color: #1d4ed8;
}

.skill-item.sky {
  background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
  border-color: #7dd3fc;
  color: #0369a1;
}

.skill-item.indigo {
  background: linear-gradient(135deg, #eef2ff, #e0e7ff);
  border-color: #a5b4fc;
  color: #4338ca;
}

.skill-item.cyan {
  background: linear-gradient(135deg, #ecfeff, #cffafe);
  border-color: #67e8f9;
  color: #0e7490;
}

.skill-item.slate {
  background: linear-gradient(135deg, #f8fafc, #f1f5f9);
  border-color: #cbd5e1;
  color: #334155;
}

.skill-icon {
  text-align: center;
  font-size: 16px;
}

.skill-name {
  font-weight: 600;
  min-width: 0;
  word-break: break-word;
}

.skill-state {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  opacity: 0.85;
  white-space: nowrap;
}

.state-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.6;
}

.empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.empty-illustration {
  margin-bottom: 4px;
  opacity: 0.7;
}

.empty-hint {
  font-size: 11px;
  color: #9ca3af;
  text-align: center;
  line-height: 1.4;
}

.trace-container {
  padding: 4px 0;
}

.results-tab :deep(.el-collapse) {
  border-top: none;
  border-bottom: none;
}

.results-tab :deep(.el-collapse-item__header) {
  min-height: 40px;
  height: auto;
  line-height: 1.45;
  padding: 8px 0;
  align-items: flex-start;
  font-size: 13px;
  font-weight: 600;
  white-space: normal;
}

.results-tab :deep(.el-collapse-item__arrow) {
  margin-top: 2px;
}

.results-tab :deep(.el-collapse-item__wrap) {
  overflow: hidden;
}

.results-tab :deep(.el-collapse-item__content) {
  padding-bottom: 10px;
  word-break: break-word;
}
</style>
