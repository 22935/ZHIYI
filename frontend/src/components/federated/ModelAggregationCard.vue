<template>
  <div class="aggregation-card">
    <div class="aggregation-header">
      <div class="header-left">
        <div class="header-icon">
          <svg width="14" height="14" viewBox="0 0 20 20" fill="none">
            <circle cx="10" cy="4" r="2.5" fill="#6366f1" />
            <circle cx="4" cy="14" r="2.5" fill="#22d3ee" />
            <circle cx="16" cy="14" r="2.5" fill="#a78bfa" />
            <line x1="10" y1="6.5" x2="4" y2="11.5" stroke="#6366f1" stroke-width="1" opacity="0.4" />
            <line x1="10" y1="6.5" x2="16" y2="11.5" stroke="#6366f1" stroke-width="1" opacity="0.4" />
          </svg>
        </div>
        <span class="header-title">模型聚合</span>
      </div>
      <span class="header-badge" :class="statusClass">{{ statusText }}</span>
    </div>

    <div class="client-list">
      <div v-for="(client, idx) in clients" :key="client.id" class="client-row">
        <div class="client-info">
          <span class="client-label">{{ client.label }}</span>
          <span class="client-weight">{{ (client.weight * 100).toFixed(0) }}%</span>
        </div>
        <div class="weight-track">
          <div
            class="weight-fill"
            :style="{ width: (client.weight * 100).toFixed(0) + '%' }"
          ></div>
        </div>
        <div class="upload-status" :class="{ uploaded: client.uploaded }">
          <svg v-if="client.uploaded" width="10" height="10" viewBox="0 0 10 10" fill="none">
            <path d="M2 5l2.5 2.5L8 3" stroke="#10b981" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
          <span v-else class="upload-waiting">...</span>
        </div>
      </div>
    </div>

    <div class="aggregation-meta">
      <span class="meta-item">FedAvg</span>
      <span class="meta-divider">·</span>
      <span class="meta-item">最少 {{ minClients }} 客户端</span>
      <div v-if="aggregating" class="aggregating-indicator">
        <span class="pulse-dot"></span>
        <span>聚合中</span>
      </div>
    </div>

    <div class="aggregation-actions">
      <button class="agg-btn primary" @click="$emit('aggregate')" :disabled="!canAggregate">
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
          <path d="M7 1v4M7 9v4M1 7h4M9 7h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          <circle cx="7" cy="7" r="3" stroke="currentColor" stroke-width="1" opacity="0.4" />
        </svg>
        执行聚合
      </button>
      <button class="agg-btn" @click="$emit('refresh')">
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
          <path d="M2 7a5 5 0 0 1 9-3M12 7a5 5 0 0 1-9 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
          <path d="M11 1v3h-3M3 13v-3h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        刷新
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface AggClient {
  id: string
  label: string
  weight: number
  uploaded: boolean
}

const props = withDefaults(defineProps<{
  clients?: AggClient[]
  aggregating?: boolean
  minClients?: number
}>(), {
  clients: () => [
    { id: 'c1', label: '律师Agent', weight: 0.30, uploaded: true },
    { id: 'c2', label: '教师Agent', weight: 0.22, uploaded: true },
    { id: 'c3', label: '程序员Agent', weight: 0.30, uploaded: true },
    { id: 'c4', label: '作家Agent', weight: 0.18, uploaded: true }
  ],
  aggregating: false,
  minClients: 3
})

defineEmits(['aggregate', 'refresh'])

const canAggregate = computed(() => {
  return props.clients.filter(c => c.uploaded).length >= props.minClients
})

const statusText = computed(() => {
  if (props.aggregating) return '聚合中'
  const uploaded = props.clients.filter(c => c.uploaded).length
  if (uploaded >= props.minClients) return '就绪'
  return `等待 (${uploaded}/${props.minClients})`
})

const statusClass = computed(() => {
  if (props.aggregating) return 'running'
  if (canAggregate.value) return 'ready'
  return 'waiting'
})
</script>

<style scoped>
.aggregation-card {
  --primary: #6366f1;
  --primary-bg: rgba(99, 102, 241, 0.06);
  --primary-border: rgba(99, 102, 241, 0.12);
  --cyan: #22d3ee;
  --green: #34d399;
  --surface: #ffffff;
  --surface-alt: #f8fafc;
  --text-primary: #1e293b;
  --text-secondary: #475569;
  --text-muted: #94a3b8;
  --radius-sm: 8px;
  --radius-md: 12px;
  --transition-fast: 0.15s ease;
  --transition-base: 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);

  background: var(--surface);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-md);
  padding: 14px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.03);
}

.aggregation-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--gap-xs, 8px);
  margin-bottom: var(--gap-md, 12px);
}

.header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.header-icon {
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  background: var(--primary-bg);
  display: flex;
  align-items: center;
  justify-content: center;
}

.header-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.header-badge {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-weight: 500;
}

.header-badge.ready {
  background: rgba(16, 185, 129, 0.08);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.15);
}

.header-badge.running {
  background: var(--primary-bg);
  color: var(--primary);
  border: 1px solid rgba(99, 102, 241, 0.15);
}

.header-badge.waiting {
  background: var(--surface-alt);
  color: var(--text-muted);
  border: 1px solid #f1f5f9;
}

.client-list {
  display: flex;
  flex-direction: column;
  gap: var(--gap-xs, 8px);
}

.client-row {
  display: flex;
  align-items: center;
  gap: var(--gap-xs, 8px);
}

.client-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-width: 90px;
}

.client-label {
  font-size: 11px;
  color: var(--text-secondary);
}

.client-weight {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
}

.weight-track {
  flex: 1;
  height: 6px;
  background: #f1f5f9;
  border-radius: 3px;
  overflow: hidden;
}

.weight-fill {
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--primary), var(--cyan));
  transition: width 0.6s cubic-bezier(0.2, 0.8, 0.2, 1);
}

.upload-status {
  width: 20px;
  height: 20px;
  border-radius: 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-alt);
  border: 1px solid #f1f5f9;
  transition: all var(--transition-fast);
}

.upload-status.uploaded {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.15);
}

.upload-waiting {
  font-size: 8px;
  color: var(--text-muted);
  letter-spacing: 1px;
}

.aggregation-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: var(--gap-sm, 10px);
  padding-top: var(--gap-sm, 10px);
  border-top: 1px solid #f1f5f9;
  font-size: 10px;
  color: var(--text-muted);
}

.meta-divider {
  color: #e2e8f0;
}

.aggregating-indicator {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
  color: var(--primary);
  font-weight: 500;
}

.pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary);
  animation: pulseDot 1.5s ease-in-out infinite;
}

@keyframes pulseDot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.4; transform: scale(1.3); }
}

.aggregation-actions {
  display: flex;
  gap: 6px;
  margin-top: var(--gap-md, 12px);
}

.agg-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 500;
  border: 1px solid #e2e8f0;
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.agg-btn:hover:not(:disabled) {
  background: var(--surface-alt);
  color: var(--text-primary);
  border-color: #cbd5e1;
}

.agg-btn.primary {
  background: var(--primary-bg);
  color: var(--primary);
  border-color: rgba(99, 102, 241, 0.15);
}

.agg-btn.primary:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.1);
  border-color: rgba(99, 102, 241, 0.25);
}

.agg-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.agg-btn:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}
</style>
