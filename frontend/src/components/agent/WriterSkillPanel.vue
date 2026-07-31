<!-- 作家技能面板 — 作家 Agent 智能写作助手仪表盘，含技能追踪、联邦增强状态和 Tab 导航 -->
<template>
  <section class="skill-panel writer-panel">
    <div class="panel-header">
      <div class="header-left">
        <div class="agent-avatar">
          <el-icon><EditPen /></el-icon>
        </div>
        <div class="header-text">
          <h3>作家 Agent 工作台</h3>
          <span class="header-sub">智能写作助手</span>
        </div>
      </div>
      <div class="header-badges">
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
        <el-icon class="tab-icon"><component :is="tab.icon" /></el-icon>
        <span class="tab-label">{{ tab.label }}</span>
        <span v-if="tab.count > 0" class="tab-badge">{{ tab.count }}</span>
      </button>
    </div>

    <div class="panel-body">
      <div v-show="activeTab === 'skills'" class="tab-content">
        <div class="sub-section">
          <div class="sub-title">联邦增强状态</div>
          <div class="federated-row">
            <div class="federated-actions">
              <button class="federated-btn ghost" type="button" @click="emit('open-federated-console')">
                <el-icon><Monitor /></el-icon>
                联邦控制台
              </button>
              <button
                class="federated-btn"
                :class="{ active: Boolean(federated?.enabled) }"
                type="button"
                :aria-pressed="Boolean(federated?.enabled)"
                :disabled="!federated?.enabled"
                @click="emit('optimize-federated')"
              >
                <el-icon><MagicStick /></el-icon>
                联邦优化
              </button>
            </div>
          </div>
        </div>

        <div class="sub-section">
          <div class="sub-title">已调用技能</div>
          <div v-if="!skillVisuals.length" class="empty">
            <div class="empty-illustration">
              <el-icon><EditPen /></el-icon>
            </div>
            <span>暂无技能调用记录</span>
            <span class="empty-hint">发送写作需求后，作家 Agent 将自动调用相关技能</span>
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
              <el-icon class="skill-icon"><component :is="item.icon" /></el-icon>
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
            <el-icon><Connection /></el-icon>
          </div>
          <span>暂无执行轨迹</span>
          <span class="empty-hint">发送写作需求后，作家 Agent 将自动调用相关技能</span>
        </div>
        <div v-else class="trace-container">
          <TraceTimeline :trace="trace" />
        </div>
      </div>

      <div v-show="activeTab === 'results'" class="tab-content results-tab">
        <slot name="results">
          <div class="empty">
            <div class="empty-illustration">
              <el-icon><Document /></el-icon>
            </div>
            <span>暂无技能调用记录</span>
            <span class="empty-hint">技能执行完成后将展示结构化结果</span>
          </div>
        </slot>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, type Component } from 'vue'
import { Connection, Document, EditPen, MagicStick, Monitor, Notebook, Operation, Share } from '@element-plus/icons-vue'
import TraceTimeline, { type TraceStep } from './TraceTimeline.vue'
import { toSkillNameZh } from '@/utils/agentDisplay'

interface FederatedInfo {
  enabled?: boolean
  applied?: boolean
  risk_adjustment?: number
  confidence?: number
  federated_nodes_count?: number
}

interface SkillVisual {
  icon: Component
  tone: 'amber' | 'orange' | 'warm' | 'rose' | 'teal'
}

const props = defineProps<{
  skillsUsed: string[]
  trace: TraceStep[]
  federated?: FederatedInfo
  resultCount?: number
}>()

const emit = defineEmits<{
  (e: 'open-federated-console'): void
  (e: 'optimize-federated'): void
}>()
const activeTab = ref<'skills' | 'trace' | 'results'>('skills')

const tabs = computed(() => [
  { key: 'skills' as const, label: '活动', icon: Operation, count: props.skillsUsed?.length || 0 },
  { key: 'trace' as const, label: '轨迹', icon: Connection, count: props.trace?.length || 0 },
  { key: 'results' as const, label: '结果', icon: Document, count: props.resultCount || 0 }
])

const SKILL_VISUAL_MAP: Record<string, SkillVisual> = {
  inspiration_expand: { icon: Share, tone: 'amber' },
  outline_generate: { icon: Notebook, tone: 'orange' },
  content_write: { icon: EditPen, tone: 'warm' },
  character_relation_map: { icon: Connection, tone: 'rose' }
}

const skillVisuals = computed(() => {
  return (props.skillsUsed || []).map(raw => {
    const key = (raw || '').trim().toLowerCase()
    const visual = SKILL_VISUAL_MAP[key] || { icon: EditPen, tone: 'amber' as const }
    return {
      raw,
      zh: toSkillNameZh(raw),
      icon: visual.icon,
      tone: visual.tone
    }
  })
})

</script>

<style scoped>
.skill-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: color-mix(in srgb, var(--bg-card) 97%, transparent);
  border: 1px solid var(--border-light);
  border-radius: 14px;
  overflow: hidden;
  height: 100%;
}

.writer-panel {
  border-top: 3px solid #d97706;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border-light);
  background: linear-gradient(135deg, var(--warning-fade) 0%, var(--warning-fade) 40%, var(--warning-fade) 100%);
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
  background: linear-gradient(135deg, var(--warning), var(--warning));
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  box-shadow: 0 2px 8px rgba(217, 119, 6, 0.25);
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
  color: #d97706;
  font-weight: 500;
}

.header-badges {
  display: flex;
  align-items: center;
  gap: 6px;
}

.skill-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  border-radius: 999px;
  padding: 3px 10px;
  background: var(--warning-fade);
  color: #d97706;
  white-space: nowrap;
  font-weight: 600;
  border: 1px solid #fcd34d;
}

.pill-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--warning);
  animation: pulse-dot 2s ease-in-out infinite;
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border-light);
  background: var(--bg-input);
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
  background: rgba(217, 119, 6, 0.05);
  color: var(--text-primary);
}

.tab-btn.active {
  color: #d97706;
  border-bottom-color: #d97706;
  background: rgba(217, 119, 6, 0.06);
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
  background: var(--warning-fade);
  color: #92400e;
  padding: 0 4px;
  font-weight: 700;
}

.tab-btn.active .tab-badge {
  background: var(--warning);
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
  background: var(--border-light);
  border-radius: 999px;
}

.sub-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.sub-section:last-child { margin-bottom: 0; }
.sub-section + .sub-section {
  padding-top: 14px;
  border-top: 1px solid var(--border-light);
}

.sub-title {
  font-size: 11px;
  font-weight: 700;
  color: #d97706;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.federated-row {
  display: grid;
  gap: 9px;
  padding: 10px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-input) 72%, transparent);
}
.federated-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px;
}

.federated-btn {
  min-width: 0;
  height: 32px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid var(--border-light);
  background: var(--surface-solid);
  color: var(--text-secondary);
  border-radius: 7px;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.federated-btn .el-icon { flex: 0 0 auto; font-size: 13px; }

.federated-btn:hover:not(:disabled) {
  border-color: #d97706;
  background: var(--warning-fade);
}

.federated-btn.ghost {
  color: var(--text-primary);
}

.federated-btn.active {
  border-color: #fbbf24;
  background: var(--warning-fade);
  color: #b45309;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, #d97706 12%, transparent);
}

.federated-btn:disabled {
  cursor: not-allowed;
  background: var(--bg-input);
  color: var(--text-disabled);
  opacity: 1;
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
  from { opacity: 0; transform: translateX(-6px); }
  to { opacity: 1; transform: translateX(0); }
}

.skill-item:hover {
  transform: translateX(3px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.skill-item.amber {
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-color: #fcd34d;
  color: #b45309;
}

.skill-item.orange {
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-color: #fdba74;
  color: #c2410c;
}

.skill-item.warm {
  background: linear-gradient(135deg, var(--warning-fade), var(--warning-fade));
  border-color: #fed7aa;
  color: #9a3412;
}

.skill-item.rose {
  background: linear-gradient(135deg, var(--danger-fade), var(--danger-fade));
  border-color: #fda4af;
  color: #be123c;
}

.skill-item.teal {
  background: linear-gradient(135deg, var(--success-fade), var(--success-fade));
  border-color: #5eead4;
  color: #0f766e;
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
  color: var(--text-disabled);
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
