<!-- 模型聚合卡片 — 展示各客户端模型聚合状态、加权进度条、上传状态和聚合算法（FedAvg） -->
<template>
  <div class="aggregation-card">
    <div class="aggregation-header">
      <div class="header-left">
        <div class="header-icon">
          <el-icon><Share /></el-icon>
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
          <el-icon v-if="client.uploaded"><Select /></el-icon>
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
        <el-icon><Share /></el-icon>
        执行聚合
      </button>
      <button class="agg-btn" @click="$emit('refresh')">
        <el-icon><Refresh /></el-icon>
        刷新
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Refresh, Select, Share } from '@element-plus/icons-vue'

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
  --primary: var(--primary-color, #3f6b63);
  --primary-bg: var(--primary-fade, rgba(63, 107, 99, 0.1));
  --primary-border: var(--border-light, #e3e6df);
  --cyan: var(--accent-color, #6f668f);
  --green: var(--success, #3d7656);
  --surface: var(--bg-card);
  --surface-alt: var(--bg-input, #f1f3ef);
  --text-primary: var(--text-primary, #1d2422);
  --text-secondary: var(--text-secondary, #727c76);
  --text-muted: var(--text-disabled, #a6aca8);
  --radius-sm: 8px;
  --radius-md: 8px;
  --transition-fast: 0.15s ease;
  --transition-base: 0.25s cubic-bezier(0.2, 0.8, 0.2, 1);

  background: var(--surface);
  border: 1px solid var(--primary-border);
  border-radius: var(--radius-md);
  padding: 14px;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(29, 36, 34, 0.04));
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
  border: 1px solid var(--primary-border);
  background: var(--surface-solid);
  color: var(--primary);
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
  background: rgba(61, 118, 86, 0.1);
  color: var(--green);
  border: 1px solid rgba(61, 118, 86, 0.2);
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
  background: var(--surface-alt);
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
  border: 1px solid var(--primary-border);
  transition: all var(--transition-fast);
}

.upload-status.uploaded {
  background: rgba(61, 118, 86, 0.1);
  border-color: rgba(61, 118, 86, 0.2);
  color: var(--green);
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
  border-top: 1px solid var(--primary-border);
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
  border: 1px solid var(--primary-border);
  background: var(--surface);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.agg-btn:hover:not(:disabled) {
  background: var(--surface-alt);
  color: var(--text-primary);
  border-color: var(--border-hover, #cfd6cd);
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
