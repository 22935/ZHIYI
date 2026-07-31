<!-- ACG 数据血缘面板 — 双 Tab 展示生产者→消费者步骤数据流（消费字段）和故障恢复追踪 -->
<template>
  <section class="acg-provenance ui-surface">
    <header class="panel-head">
      <div class="head-left">
        <el-icon class="head-icon"><Connection /></el-icon>
        <h4>数据血缘与恢复轨迹</h4>
      </div>
      <div class="export-actions">
        <button type="button" title="导出 ACG 审计 JSON" @click="emit('export-json')">
          <el-icon><Download /></el-icon>
          JSON
        </button>
        <button type="button" title="导出 ACG 审计 CSV" @click="emit('export-csv')">
          <el-icon><Download /></el-icon>
          CSV
        </button>
      </div>
    </header>
    <div class="tabs">
      <button :class="{ active: tab === 'lineage' }" @click="tab = 'lineage'">数据血缘</button>
      <button :class="{ active: tab === 'interaction' }" @click="tab = 'interaction'">运行交互</button>
      <button :class="{ active: tab === 'recovery' }" @click="tab = 'recovery'">恢复轨迹</button>
    </div>

    <!-- 数据血缘 -->
    <div v-if="tab === 'lineage'" class="tab-body">
      <div v-if="!consumptions.length" class="empty">暂无数据流转记录</div>
      <ul v-else class="lineage-list">
        <li v-for="(c, i) in consumptions" :key="c.eventId || i" class="lineage-item">
          <div class="flow">
            <span class="node-tag producer" v-for="p in c.producerStepIds" :key="p">{{ p }}</span>
            <el-icon class="arrow"><Right /></el-icon>
            <span class="node-tag consumer">{{ c.consumerStepId }}</span>
          </div>
          <div class="fields" v-if="c.consumedFields && c.consumedFields.length">
            <span class="fields__label">消费字段</span>
            <span class="fields__chips">
              <code v-for="f in c.consumedFields" :key="f">{{ f }}</code>
            </span>
          </div>
        </li>
      </ul>
    </div>

    <!-- 恢复轨迹 -->
    <div v-else-if="tab === 'interaction'" class="tab-body">
      <div v-if="!interactions.length" class="empty">暂无运行时交互记录</div>
      <ul v-else class="interaction-list">
        <li v-for="item in interactions" :key="item.interactionId" class="interaction-item">
          <div class="flow">
            <span class="node-tag producer">{{ agentNames(item.producerAgentNames, item.producerStepIds) }}</span>
            <el-icon class="arrow"><Right /></el-icon>
            <span class="node-tag consumer">{{ item.consumerAgentName || item.consumerStepId }}</span>
          </div>
          <div class="interaction-meta">
            <span>{{ item.tokensDelivered }} / {{ item.tokensAvailable }} Token</span>
            <span>节省 {{ (item.savingRatio * 100).toFixed(1) }}%</span>
            <span class="contract-state" :class="item.contractStatus">{{ item.contractStatus }}</span>
          </div>
          <div class="fields" v-if="interactionFields(item).length">
            <span class="fields__label">投递字段</span>
            <span class="fields__chips">
              <code v-for="field in interactionFields(item)" :key="field">{{ field }}</code>
            </span>
          </div>
        </li>
      </ul>
    </div>

    <!-- 恢复与契约异常 -->
    <div v-else class="tab-body">
      <div v-if="!runtimeEvents.length" class="empty">本次运行未发生恢复或契约异常</div>
      <ul v-else class="recovery-list">
        <li v-for="(e, i) in runtimeEvents" :key="e.eventId || i" class="recovery-item" :class="e.eventType">
          <div class="rec-head">
            <span class="rec-type">{{ recoveryLabel(e.eventType) }}</span>
            <span class="rec-step" v-if="e.stepId">{{ e.stepId }}</span>
          </div>
          <div class="rec-obs">{{ e.observation }}</div>
          <div class="rec-meta" v-if="e.payload?.strategy">
            策略：<strong>{{ e.payload.strategy }}</strong>
            <span v-if="e.payload.faultType"> · 故障类型：{{ e.payload.faultType }}</span>
          </div>
        </li>
      </ul>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Connection, Download, Right } from '@element-plus/icons-vue'
import type { ProvenanceConsumption, RuntimeInteraction, TraceEvent } from '@/services/api/agentos'

const props = withDefaults(defineProps<{
  consumptions?: ProvenanceConsumption[]
  interactions?: RuntimeInteraction[]
  recoveryTrace?: TraceEvent[]
  contractViolations?: TraceEvent[]
}>(), {
  consumptions: () => [],
  interactions: () => [],
  recoveryTrace: () => [],
  contractViolations: () => []
})

const emit = defineEmits<{
  'export-json': []
  'export-csv': []
}>()

const tab = ref<'lineage' | 'interaction' | 'recovery'>('lineage')

const runtimeEvents = computed(() => {
  return [...props.recoveryTrace, ...props.contractViolations].sort((a, b) =>
    String(a.createdAt || '').localeCompare(String(b.createdAt || ''))
  )
})

const interactionFields = (item: RuntimeInteraction) => {
  return Array.from(new Set(Object.values(item.fieldsByProducer || {}).flat()))
}

const agentNames = (names: string[], stepIds: string[]) => {
  const values = names?.length ? names : stepIds
  return values.join(' + ')
}

const recoveryLabel = (t: string) => {
  if (t === 'step_failed') return '故障注入'
  if (t === 'run_recovered') return '检查点恢复'
  if (t === 'contract_violation') return '契约异常'
  return t
}
</script>

<style scoped>
.acg-provenance { display: flex; flex-direction: column; min-width: 0; overflow: hidden; }
.panel-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: var(--space-sm); }
.head-left { display: flex; align-items: center; gap: 6px; min-width: 0; }
.head-icon { font-size: 15px; color: var(--primary-color); }
.panel-head h4 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); text-wrap: pretty; }
.export-actions { display: flex; flex: 0 0 auto; gap: 4px; }
.export-actions button {
  min-height: 30px; display: inline-flex; align-items: center; gap: 4px; padding: 4px 9px;
  border: 1px solid var(--border-light); border-radius: 6px;
  background: var(--surface-solid); color: var(--text-secondary); font-size: 10px; cursor: pointer;
  transition: border-color .18s ease, color .18s ease, background-color .18s ease;
}
.export-actions button:hover { color: var(--primary-color); border-color: var(--primary-line); background: var(--primary-fade); }
.tabs {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 3px;
  margin-bottom: var(--space-sm); padding: 3px;
  border: 1px solid var(--border-light); border-radius: 8px; background: var(--bg-input);
}
.tabs button {
  min-width: 0; min-height: 30px; padding: 4px 8px; border: 0; border-radius: 6px;
  background: transparent; color: var(--text-secondary); font-size: 12px; cursor: pointer;
  transition: background-color .18s ease, color .18s ease, box-shadow .18s ease;
}
.tabs button:hover:not(.active) { color: var(--text-primary); background: var(--surface-solid); }
.tabs button.active { background: var(--primary-color); color: var(--on-primary); box-shadow: var(--shadow-sm); }

.tab-body {
  flex: 1 1 320px; min-width: 0; min-height: 320px;
  box-sizing: border-box; overflow-x: hidden; overflow-y: auto;
  padding: 2px 8px 10px; scrollbar-gutter: stable;
}
.empty {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 12px;
  text-align: center;
  color: var(--text-secondary);
  font-size: 13px;
}

.lineage-list, .interaction-list, .recovery-list {
  min-width: 0; list-style: none; margin: 0; padding: 0;
  display: flex; flex-direction: column; gap: var(--space-sm);
}
.lineage-item, .interaction-item {
  box-sizing: border-box; width: 100%; min-width: 0; padding: 11px 12px;
  border: 1px solid var(--border-light); border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--bg-panel) 76%, var(--bg-card));
  transition: border-color .18s ease, background-color .18s ease;
}
.lineage-item:hover, .interaction-item:hover { border-color: var(--border-hover); background: var(--bg-panel); }
.flow { min-width: 0; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.node-tag {
  min-width: 0; max-width: 100%; display: inline-flex; align-items: center;
  padding: 3px 9px; border-radius: 999px; font-size: 11px; font-weight: 650;
  line-height: 1.35; overflow-wrap: anywhere; white-space: normal;
}
.node-tag.producer { background: var(--bg-input); color: var(--text-secondary); border: 1px solid var(--border-light); }
.node-tag.consumer { background: var(--primary-fade); color: var(--primary-color); }
.arrow { flex: 0 0 auto; color: var(--text-disabled); font-size: 13px; }
.fields {
  min-width: 0; display: grid; gap: 5px; margin-top: 9px; padding-top: 8px;
  border-top: 1px solid var(--border-light); color: var(--text-secondary);
}
.fields__label { font-size: 10px; font-weight: 650; color: var(--text-muted); }
.fields__chips { min-width: 0; display: flex; flex-wrap: wrap; gap: 4px; }
.fields code {
  min-width: 0; max-width: 100%; display: inline-flex; padding: 2px 6px;
  border: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent);
  border-radius: 5px; background: var(--bg-input); color: var(--text-secondary);
  font-size: 10px; line-height: 1.25; overflow-wrap: anywhere; white-space: normal;
}
.interaction-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; font-size: 11px; color: var(--text-secondary); }
.contract-state { font-weight: 700; color: var(--success); }
.contract-state.invalid { color: var(--danger); }

.recovery-item { padding: var(--space-sm); border-radius: var(--radius-md); border-left: 3px solid var(--border-light); background: var(--bg-panel); }
.recovery-item.step_failed { border-left-color: var(--warning); }
.recovery-item.run_recovered { border-left-color: var(--success); }
.recovery-item.contract_violation { border-left-color: var(--danger); }
.rec-head { display: flex; justify-content: space-between; align-items: center; }
.rec-type { font-size: 12px; font-weight: 700; color: var(--text-primary); }
.rec-step { font-size: 11px; color: var(--text-secondary); font-family: monospace; }
.rec-obs { font-size: 12px; color: var(--text-secondary); margin-top: 2px; }
.rec-meta { font-size: 11px; color: var(--text-secondary); margin-top: 4px; }
.rec-meta strong { color: var(--success); }

@media (max-width: 520px) {
  .panel-head { align-items: flex-start; }
  .export-actions { flex-wrap: wrap; justify-content: flex-end; }
}
</style>
