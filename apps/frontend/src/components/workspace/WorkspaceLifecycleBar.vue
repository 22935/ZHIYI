<template>
  <section class="lifecycle-bar" :data-tone="tone" aria-label="运行状态">
    <div class="lifecycle-bar__row">
      <div class="lifecycle-bar__status" role="status" aria-live="polite">
        <span class="lifecycle-bar__badge">
          <svg v-if="lifecycle.phase === 'COMPLETED'" viewBox="0 0 16 16" aria-hidden="true"><path d="m4 8 2.5 2.5L12 5" /></svg>
          <span v-else class="lifecycle-bar__dot" aria-hidden="true" />
          <strong>{{ lifecycleLabels[lifecycle.phase] }}</strong>
        </span>
        <span class="lifecycle-bar__message" :title="message">{{ message }}</span>
      </div>
      <div class="lifecycle-bar__actions">
        <button
          type="button"
          class="lifecycle-bar__follow"
          :aria-pressed="following"
          :title="following ? '已开启自动跟随；手动切换文件后暂停' : '根据运行状态自动展示进度、审核任务或交付物'"
          @click="$emit('follow')"
        >
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M12.8 6A5 5 0 0 0 4 4.8L2.5 6.5M3.2 10A5 5 0 0 0 12 11.2l1.5-1.7M2.5 3v3.5H6M10 9.5h3.5V13" /></svg>
          {{ following ? '自动跟随' : '恢复跟随' }}
        </button>
        <button type="button" class="lifecycle-bar__details-toggle" :aria-expanded="detailsOpen" @click="detailsOpen = !detailsOpen">
          运行详情
          <svg viewBox="0 0 16 16" aria-hidden="true" :class="{ 'is-open': detailsOpen }"><path d="m5 6.5 3 3 3-3" /></svg>
        </button>
      </div>
    </div>
    <dl v-if="detailsOpen" class="lifecycle-bar__details">
      <div><dt>当前查看</dt><dd>{{ lifecycle.runId || '未选择运行' }}</dd></div>
      <div><dt>最新创建</dt><dd>{{ lifecycle.latestRunId || '未观测' }}</dd></div>
      <div><dt>活跃运行</dt><dd>{{ activeRunIds.join('、') || '未观测到活跃运行' }}</dd></div>
      <div class="lifecycle-bar__reason"><dt>状态依据</dt><dd>{{ lifecycle.reason }}</dd></div>
    </dl>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { lifecycleLabels, type LifecyclePhase } from '@/features/workspace/runLifecycle'
import type { LifecycleProjection } from '@/workbench/runtime/lifecycleProjection'

const props = defineProps<{ lifecycle: LifecycleProjection; activeRunIds: string[]; following: boolean }>()
defineEmits<{ follow: [] }>()
const detailsOpen = ref(false)
const tone = computed(() => {
  const phase = props.lifecycle.phase
  if (phase === 'COMPLETED' && props.lifecycle.deliveryStatus !== 'MISSING') return 'success'
  if (phase === 'FAILED') return 'danger'
  if (props.lifecycle.deliveryStatus === 'MISSING' || ['WAITING_REVIEW', 'AWAITING_CONFIRMATION', 'READY_TO_DISPATCH', 'RECOVERING'].includes(phase)) return 'warning'
  if (['RUNNING', 'PLANNING', 'QUEUED', 'DISPATCHED'].includes(phase)) return 'active'
  return 'muted'
})
const messages: Record<LifecyclePhase, string> = {
  CREATED: '任务已就绪，等待创建运行', QUEUED: '等待调度执行', PLANNING: '正在理解需求并编排任务',
  AWAITING_CONFIRMATION: '请确认执行方案', ACTIVATED_PAUSED: '执行图已激活，等待继续',
  READY_TO_DISPATCH: '执行许可已就绪，等待派发', DISPATCHED: '已提交执行，等待运行反馈',
  RUNNING: '正在执行任务', WAITING_REVIEW: '有任务需要你审核', RECOVERING: '正在恢复执行',
  FAILED: '请查看失败原因与任务详情', COMPLETED: '交付物已就绪', CANCELLED: '本次执行已停止',
  SUPERSEDED: '已由后续运行接替，当前记录仅供查阅', UNKNOWN: '等待同步运行状态'
}
const message = computed(() => props.lifecycle.deliveryStatus === 'MISSING'
  ? '执行已完成，尚未找到最终交付物'
  : props.lifecycle.isHistorical ? '历史运行 · 当前记录仅供查阅' : messages[props.lifecycle.phase])
</script>

<style scoped>
.lifecycle-bar { --lifecycle-tone: var(--wb-text-muted); flex: 0 0 auto; min-width: 0; border-bottom: 1px solid var(--wb-border-soft); background: var(--wb-surface-shell); color: var(--wb-text-secondary); font-size: 10px; }
.lifecycle-bar[data-tone="success"] { --lifecycle-tone: var(--wb-success); }
.lifecycle-bar[data-tone="danger"] { --lifecycle-tone: var(--wb-danger); }
.lifecycle-bar[data-tone="warning"] { --lifecycle-tone: var(--wb-warning); }
.lifecycle-bar[data-tone="active"] { --lifecycle-tone: var(--wb-accent); }
.lifecycle-bar__row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 16px; min-height: 46px; padding: 6px 14px; box-sizing: border-box; }
.lifecycle-bar__status { display: flex; flex: 1 1 180px; align-items: center; gap: 10px; min-width: 0; }
.lifecycle-bar__badge { display: inline-flex; flex-shrink: 0; align-items: center; gap: 6px; min-height: 28px; padding: 0 8px; border-radius: var(--wb-radius-sm); color: var(--lifecycle-tone); background: color-mix(in srgb, var(--lifecycle-tone) 10%, transparent); }
.lifecycle-bar__badge strong { font-size: 10px; font-weight: 600; }
.lifecycle-bar svg { width: 16px; height: 16px; flex-shrink: 0; fill: none; stroke: currentColor; stroke-width: 1.6; stroke-linecap: round; stroke-linejoin: round; }
.lifecycle-bar__dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.lifecycle-bar__message { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lifecycle-bar__actions { display: flex; flex-shrink: 0; align-items: center; gap: 6px; margin-left: auto; }
.lifecycle-bar button { display: inline-flex; align-items: center; justify-content: center; gap: 5px; min-height: 32px; padding: 0 8px; border: 1px solid transparent; border-radius: var(--wb-radius-sm); background: transparent; color: var(--wb-text-secondary); font: inherit; cursor: pointer; transition: background 120ms ease, color 120ms ease; }
.lifecycle-bar button:hover { background: var(--wb-hover); color: var(--wb-text); }
.lifecycle-bar button:focus-visible { outline: 2px solid var(--wb-accent); outline-offset: 2px; }
.lifecycle-bar__follow[aria-pressed="true"] { color: var(--wb-accent); background: var(--wb-accent-soft); }
.lifecycle-bar__details-toggle svg { transition: transform 120ms ease; }
.lifecycle-bar__details-toggle svg.is-open { transform: rotate(180deg); }
.lifecycle-bar__details { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); gap: 12px 20px; margin: 0; padding: 12px 16px 14px; border-top: 1px solid var(--wb-border-soft); background: var(--wb-surface-pane); }
.lifecycle-bar__details div { min-width: 0; }
.lifecycle-bar__details dt { margin-bottom: 5px; color: var(--wb-text-muted); font-size: 10px; }
.lifecycle-bar__details dd { margin: 0; color: var(--wb-text-secondary); font-family: var(--font-mono, monospace); font-size: 10px; line-height: 1.6; overflow-wrap: anywhere; user-select: text; }
.lifecycle-bar__reason { grid-column: 1 / -1; }
@media (prefers-reduced-motion: reduce) { .lifecycle-bar button, .lifecycle-bar__details-toggle svg { transition: none; } }
</style>
