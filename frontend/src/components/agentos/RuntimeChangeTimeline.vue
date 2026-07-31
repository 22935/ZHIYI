<template>
  <section class="runtime-timeline ui-surface" aria-label="运行时变化时间线">
    <header>
      <div><span class="eyebrow">Runtime Audit</span><strong>运行时变化时间线</strong></div>
      <span>{{ items.length }} 条</span>
    </header>
    <p v-if="!items.length" class="empty">本次运行尚未发生动态图变化</p>
    <ol v-else>
      <li v-for="item in items" :key="item.id" :class="`kind-${item.kind}`">
        <span class="marker" aria-hidden="true"></span>
        <div class="content">
          <div class="item-head">
            <strong>{{ typeLabel(item.type) }}</strong>
            <time v-if="item.time">{{ formatTime(item.time) }}</time>
          </div>
          <p>{{ item.description }}</p>
          <div class="meta">
            <code v-if="item.graphVersionBefore !== undefined && item.graphVersionAfter !== undefined">v{{ item.graphVersionBefore }} → v{{ item.graphVersionAfter }}</code>
            <code v-else-if="item.graphVersionAfter !== undefined">v{{ item.graphVersionAfter }}</code>
            <span v-if="item.runtimeNodeId">节点 {{ item.runtimeNodeId }}</span>
            <span v-if="item.reasonCode">原因 {{ item.reasonCode }}</span>
          </div>
          <details>
            <summary>查看结构化详情</summary>
            <pre>{{ formatRuntimeDetail(item.detail) }}</pre>
          </details>
        </div>
      </li>
    </ol>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AcgStepState, AppliedPatchProjection, BranchDecision, RuntimeEventProjection } from '@/services/api/agentos'
import { buildRuntimeTimeline, formatRuntimeDetail } from '@/utils/runtimePresentation'

const props = withDefaults(defineProps<{
  runtimeEvents?: RuntimeEventProjection[]
  appliedPatches?: AppliedPatchProjection[]
  branchDecisions?: BranchDecision[]
  stepStates?: AcgStepState[]
}>(), {
  runtimeEvents: () => [], appliedPatches: () => [], branchDecisions: () => [], stepStates: () => []
})

const items = computed(() => buildRuntimeTimeline(props.runtimeEvents, props.appliedPatches, props.branchDecisions, props.stepStates))
const typeLabel = (type: string) => ({
  ADD_SUBGRAPH: '补救子图已应用', RETRY_ALTERNATE_BINDING: '备用执行绑定已启用',
  ACTIVATE_CONDITIONAL_BRANCH: '条件分支已激活', CONDITIONAL_DECISION: '条件分支决策',
  BINDING_SWITCH: '执行绑定切换', EVIDENCE_MISSING: '检测到证据缺口',
  BINDING_UNAVAILABLE: '执行绑定不可用', INPUT_CONTRACT_VIOLATION: '输入契约不满足',
  OUTPUT_CONTRACT_VIOLATION: '输出契约不满足', LOW_CONFIDENCE: '结果置信度较低',
  STEP_EXECUTION_FAILED: '步骤执行失败'
}[type] || type)
const formatTime = (value: string) => {
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString('zh-CN', { hour12: false }) : value
}
</script>

<style scoped>
.runtime-timeline { padding: 14px; }
header, header > div, .item-head, .meta { display: flex; align-items: center; }
header { justify-content: space-between; gap: 12px; }
header > div { gap: 9px; }
header > span, .eyebrow, time, .meta { color: var(--text-secondary); font-size: 11px; }
header strong { color: var(--text-primary); font-size: 13px; }
.eyebrow { letter-spacing: .04em; text-transform: uppercase; }
.empty { margin: 14px 0 0; color: var(--text-secondary); font-size: 12px; }
ol { margin: 14px 0 0; padding: 0; list-style: none; }
li { position: relative; display: grid; grid-template-columns: 13px minmax(0, 1fr); gap: 9px; padding-bottom: 14px; }
li:not(:last-child)::before { content: ''; position: absolute; left: 5px; top: 13px; bottom: 0; width: 1px; background: var(--border-light); }
.marker { position: relative; z-index: 1; width: 9px; height: 9px; margin-top: 4px; border: 2px solid var(--bg-card); border-radius: 50%; background: var(--text-muted); box-shadow: 0 0 0 1px var(--border-light); }
.kind-patch .marker { background: var(--primary-color); }
.kind-event .marker { background: var(--warning); }
.kind-decision .marker { background: var(--success); }
.kind-binding .marker { background: var(--info); }
.content { min-width: 0; }
.item-head { justify-content: space-between; gap: 8px; }
.item-head strong { color: var(--text-primary); font-size: 12px; }
.content p { margin: 4px 0 6px; color: var(--text-regular); font-size: 12px; line-height: 1.55; overflow-wrap: anywhere; }
.meta { flex-wrap: wrap; gap: 6px 10px; }
.meta code { color: var(--primary-color); }
details { margin-top: 7px; }
summary { color: var(--text-secondary); cursor: pointer; font-size: 11px; }
pre { max-height: 240px; margin: 7px 0 0; padding: 9px; overflow: auto; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-input); color: var(--text-regular); font: 11px/1.5 ui-monospace, SFMono-Regular, Consolas, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
