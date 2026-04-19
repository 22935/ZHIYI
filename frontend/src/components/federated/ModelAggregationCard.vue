<template>
  <div class="aggregation-card">
    <div class="aggregation-header">
      <div class="header-icon">
        <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="4" r="2.5" fill="#6366f1" />
          <circle cx="4" cy="14" r="2.5" fill="#22d3ee" />
          <circle cx="16" cy="14" r="2.5" fill="#a78bfa" />
          <line x1="10" y1="6.5" x2="4" y2="11.5" stroke="#6366f1" stroke-width="1" opacity="0.5" />
          <line x1="10" y1="6.5" x2="16" y2="11.5" stroke="#6366f1" stroke-width="1" opacity="0.5" />
          <line x1="4" y1="14" x2="16" y2="14" stroke="#22d3ee" stroke-width="1" stroke-dasharray="2 2" opacity="0.4" />
        </svg>
      </div>
      <span class="header-title">模型聚合</span>
      <span class="header-badge" :class="statusClass">{{ statusText }}</span>
    </div>

    <div class="aggregation-visual">
      <svg width="100%" height="100" viewBox="0 0 280 100" class="agg-svg">
        <defs>
          <linearGradient id="aggBarGrad" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#6366f1" />
            <stop offset="100%" stop-color="#22d3ee" />
          </linearGradient>
          <filter id="aggGlow">
            <feGaussianBlur stdDeviation="2" result="blur" />
            <feMerge>
              <feMerge in="blur" />
              <feMerge in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g v-for="(client, idx) in clients" :key="`agg-${idx}`" :transform="`translate(20, ${8 + idx * 16})`">
          <text x="0" y="9" fill="#94a3b8" font-size="8">{{ client.label }}</text>
          <rect x="55" y="1" width="165" height="10" rx="2" fill="#1e293b" />
          <rect
            x="55" y="1"
            :width="client.weight * 165"
            height="10"
            rx="2"
            fill="url(#aggBarGrad)"
            :opacity="0.6 + client.weight * 0.4"
            class="weight-bar"
            :style="{ animationDelay: `${idx * 0.15}s` }"
          />
          <text :x="55 + client.weight * 165 + 5" y="9" fill="#e2e8f0" font-size="7" font-weight="500">
            {{ (client.weight * 100).toFixed(0) }}%
          </text>
          <g :transform="`translate(225, 1)`">
            <rect width="30" height="10" rx="2" :fill="client.uploaded ? '#064e3b' : '#1e293b'" />
            <text x="15" y="8" text-anchor="middle" :fill="client.uploaded ? '#34d399' : '#475569'" font-size="6">
              {{ client.uploaded ? '✓' : '...' }}
            </text>
          </g>
        </g>

        <g transform="translate(20, 88)">
          <line x1="0" y1="0" x2="280" y2="0" stroke="#334155" stroke-width="0.5" />
          <text x="0" y="9" fill="#64748b" font-size="7">聚合方法: FedAvg | 最小客户端: {{ minClients }}</text>
          <g v-if="aggregating" transform="translate(200, 2)">
            <circle r="2.5" fill="#6366f1" class="agg-pulse" />
            <text x="6" y="2" fill="#a78bfa" font-size="7">聚合中...</text>
          </g>
        </g>
      </svg>
    </div>

    <div class="aggregation-actions">
      <button class="agg-btn primary" @click="$emit('aggregate')" :disabled="!canAggregate">
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
          <path d="M7 1v4M7 9v4M1 7h4M9 7h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          <circle cx="7" cy="7" r="3" stroke="currentColor" stroke-width="1" opacity="0.5" />
        </svg>
        执行聚合
      </button>
      <button class="agg-btn" @click="$emit('refresh')">
        <svg width="12" height="12" viewBox="0 0 14 14" fill="none">
          <path d="M2 7a5 5 0 0 1 9-3M12 7a5 5 0 0 1-9 3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
          <path d="M11 1v3h-3M3 13v-3h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        刷新状态
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
    { id: 'c1', label: '律师节点', weight: 0.25, uploaded: true },
    { id: 'c2', label: '教师节点', weight: 0.20, uploaded: true },
    { id: 'c3', label: '程序员节点', weight: 0.25, uploaded: true },
    { id: 'c4', label: '作家节点', weight: 0.15, uploaded: true },
    { id: 'c5', label: '风控节点', weight: 0.15, uploaded: false }
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
  background: rgba(15, 23, 42, 0.6);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: 8px;
  padding: 6px;
  backdrop-filter: blur(12px);
}

.aggregation-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
}

.header-icon {
  display: flex;
  align-items: center;
}

.header-title {
  font-size: 11px;
  font-weight: 600;
  color: #e2e8f0;
  flex: 1;
}

.header-badge {
  font-size: 8px;
  padding: 2px 6px;
  border-radius: 6px;
  font-weight: 500;
}

.header-badge.ready {
  background: rgba(16, 185, 129, 0.15);
  color: #34d399;
  border: 1px solid rgba(16, 185, 129, 0.3);
}

.header-badge.running {
  background: rgba(99, 102, 241, 0.15);
  color: #a78bfa;
  border: 1px solid rgba(99, 102, 241, 0.3);
}

.header-badge.waiting {
  background: rgba(100, 116, 139, 0.15);
  color: #94a3b8;
  border: 1px solid rgba(100, 116, 139, 0.3);
}

.agg-svg {
  display: block;
}

.weight-bar {
  animation: barGrow 0.8s ease-out forwards;
  transform-origin: left;
}

@keyframes barGrow {
  from { transform: scaleX(0); }
  to { transform: scaleX(1); }
}

.agg-pulse {
  animation: aggPulse 1.5s ease-in-out infinite;
}

@keyframes aggPulse {
  0%, 100% { opacity: 1; r: 2.5; }
  50% { opacity: 0.4; r: 4; }
}

.aggregation-actions {
  display: flex;
  gap: 6px;
  margin-top: 6px;
}

.agg-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 10px;
  font-weight: 500;
  border: 1px solid rgba(99, 102, 241, 0.2);
  background: rgba(30, 41, 59, 0.6);
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.2s ease;
}

.agg-btn:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.1);
  color: #e2e8f0;
  border-color: rgba(99, 102, 241, 0.4);
}

.agg-btn.primary {
  background: rgba(99, 102, 241, 0.15);
  color: #a78bfa;
  border-color: rgba(99, 102, 241, 0.3);
}

.agg-btn.primary:hover:not(:disabled) {
  background: rgba(99, 102, 241, 0.25);
  color: #c4b5fd;
}

.agg-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
