<template>
  <section class="installed-panel" aria-label="安装任务">
    <div v-if="loading" class="installed-panel__state" role="status">正在同步安装任务…</div>
    <div v-else-if="!items.length" class="installed-panel__state">还没有安装内容</div>
    <div v-else class="installed-list">
      <article v-for="job in items" :key="job.jobId" class="installed-row">
        <span class="installed-row__state" :class="`is-${job.status}`" aria-hidden="true"></span>
        <div class="installed-row__identity"><strong>{{ job.displayName || job.catalogId || '自定义资源' }}</strong><span>{{ job.runtimeId || job.jobId }}</span></div>
        <div class="installed-row__timeline"><span>{{ statusLabel(job.status) }}</span><small>{{ timeLabel(job.updatedAt) }}</small></div>
        <p v-if="job.errorSummary" class="installed-row__error">{{ job.errorSummary }}</p>
        <div class="installed-row__actions">
          <button v-if="job.status === 'running' && ['tool.pdf-parser', 'tool.file-converter'].includes(job.catalogId || '')" type="button" title="使用工具" aria-label="使用工具" :disabled="Boolean(busyJob)" @click="$emit('use', job)"><el-icon><Tools /></el-icon></button>
          <button v-if="job.status === 'running'" type="button" title="停止资源" aria-label="停止资源" :disabled="busyJob === job.jobId" @click="$emit('stop', job)"><el-icon><VideoPause /></el-icon></button>
          <button v-if="['running', 'stopped', 'failed'].includes(job.status)" type="button" title="卸载资源" aria-label="卸载资源" :disabled="busyJob === job.jobId" @click="$emit('uninstall', job)"><el-icon><Delete /></el-icon></button>
          <span v-if="busyJob === job.jobId" class="installed-row__busy">处理中</span>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup lang="ts">
import { Delete, Tools, VideoPause } from '@element-plus/icons-vue'
import type { MarketplaceInstallation } from '@/services/api/agentos'

defineProps<{ items: MarketplaceInstallation[]; loading: boolean; busyJob: string }>()
defineEmits<{
  (event: 'use', item: MarketplaceInstallation): void
  (event: 'stop', item: MarketplaceInstallation): void
  (event: 'uninstall', item: MarketplaceInstallation): void
}>()
const statusLabel = (status: string) => ({ queued: '等待安装', installing: '正在安装', registering: '正在接入资源器', running: '运行中', failed: '安装失败', stopped: '已停止', uninstalling: '正在卸载', removed: '已卸载' }[status] || status)
const timeLabel = (value: string) => {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '' : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date)
}
</script>

<style scoped>
.installed-panel__state { display: grid; place-items: center; min-height: 240px; color: var(--text-muted); font-size: 12px; }.installed-list { border-top: 1px solid var(--border-light); }.installed-row { display: grid; grid-template-columns: 8px minmax(0, 1fr) 150px auto; align-items: center; gap: 14px; min-height: 74px; padding: 12px 6px; border-bottom: 1px solid var(--border-light); }.installed-row__state { width: 7px; height: 7px; border-radius: 50%; background: var(--text-muted); }.installed-row__state.is-running { background: var(--success); box-shadow: 0 0 0 4px color-mix(in srgb, var(--success) 12%, transparent); }.installed-row__state.is-failed { background: var(--danger); }.installed-row__state.is-installing, .installed-row__state.is-registering, .installed-row__state.is-queued, .installed-row__state.is-uninstalling { background: var(--warning); }.installed-row__identity { display: grid; gap: 4px; min-width: 0; }.installed-row__identity strong { overflow: hidden; color: var(--text-primary); text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 550; }.installed-row__identity span { overflow: hidden; color: var(--text-muted); text-overflow: ellipsis; white-space: nowrap; font: 9px var(--font-mono, monospace); }.installed-row__timeline { display: grid; gap: 4px; color: var(--text-secondary); font-size: 11px; }.installed-row__timeline small { color: var(--text-muted); font-size: 9px; }.installed-row__error { grid-column: 2 / 4; margin: -5px 0 2px; color: var(--danger); font-size: 10px; }.installed-row__actions { display: flex; gap: 5px; }.installed-row__actions button { display: grid; place-items: center; width: 30px; aspect-ratio: 1; border: 1px solid var(--border-light); color: var(--text-secondary); background: transparent; cursor: pointer; }.installed-row__actions button:hover:not(:disabled) { border-color: var(--danger); color: var(--danger); }.installed-row__actions button:disabled { opacity: .5; }.installed-row__busy { color: var(--text-muted); font-size: 9px; }
@media (max-width: 620px) { .installed-row { grid-template-columns: 8px minmax(0, 1fr) auto; gap: 9px; }.installed-row__timeline { grid-column: 2; grid-row: 2; display: flex; gap: 8px; }.installed-row__actions { grid-column: 3; grid-row: 1 / 3; }.installed-row__error { grid-column: 2 / 4; } }
</style>
