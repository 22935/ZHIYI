<!-- ACG 低熵通信指标 — 展示平均 Token 节省率、累计节省/交付/可用 Token 数和自愈恢复次数 -->
<template>
  <section class="acg-metrics ui-surface">
    <header class="panel-head">
      <div class="head-left">
        <el-icon class="head-icon"><DataLine /></el-icon>
        <h4>低熵通信指标</h4>
      </div>
    </header>

    <div class="metric-grid">
      <div class="metric-card metric-card--primary">
        <span class="metric-value">{{ savingPercent }}</span>
        <span class="metric-label">平均 Token 节省率</span>
      </div>
      <div class="metric-card metric-card--saved">
        <span class="metric-value">{{ formatNum(metrics.tokensSaved) }}</span>
        <span class="metric-label">累计节省 Token</span>
      </div>
      <div class="metric-card metric-card--delivery">
        <span class="metric-value">{{ formatNum(metrics.tokensDelivered) }} / {{ formatNum(metrics.tokensAvailable) }}</span>
        <span class="metric-label">投递 / 可获取</span>
      </div>
    </div>

    <div class="signal-grid" aria-label="运行质量信号">
      <div class="signal-card" :class="{ warn: metrics.recoveryCount > 0 }">
        <span class="metric-value">{{ metrics.recoveryCount }}</span>
        <span class="metric-label">自愈恢复次数</span>
      </div>
      <div class="signal-card">
        <span class="metric-value">{{ metrics.interactionCount }}</span>
        <span class="metric-label">运行时交互</span>
      </div>
      <div class="signal-card" :class="{ danger: metrics.contractViolationCount > 0 }">
        <span class="metric-value">{{ metrics.contractViolationCount }}</span>
        <span class="metric-label">契约异常</span>
      </div>
    </div>

    <footer class="metrics-footer">
      <div class="ledger-status" :class="{ invalid: metrics.integrityStatus !== 'valid' }">
        <span class="ledger-dot" aria-hidden="true"></span>
        <span>审计账本</span>
        <strong>{{ metrics.integrityStatus === 'valid' ? '校验通过' : '旧版或校验异常' }}</strong>
      </div>

      <div class="bar-wrap" v-if="metrics.tokensAvailable > 0">
        <div class="bar-heading">
          <span>实际投递 {{ deliveredPercent }}</span>
          <strong>节省 {{ savingPercent }}</strong>
        </div>
        <div class="bar-track">
          <div class="bar-fill" :style="{ width: deliveredPercent }"></div>
        </div>
        <div class="bar-caption">引擎按需投递，减少无效上下文</div>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { DataLine } from '@element-plus/icons-vue'
import type { AcgLowEntropyMetrics } from '@/services/api/agentos'

const props = withDefaults(defineProps<{
  metrics?: AcgLowEntropyMetrics
}>(), {
  metrics: () => ({
    averageSavingRatio: 0,
    effectiveSavingRatio: 0,
    tokensAvailable: 0,
    tokensDelivered: 0,
    tokensSaved: 0,
    recoveryCount: 0,
    interactionCount: 0,
    contractViolationCount: 0,
    integrityStatus: 'valid'
  })
})

const savingPercent = computed(() => `${((props.metrics.effectiveSavingRatio ?? props.metrics.averageSavingRatio) * 100).toFixed(1)}%`)

const deliveredPercent = computed(() => {
  const { tokensAvailable, tokensDelivered } = props.metrics
  if (!tokensAvailable) return '0%'
  return `${Math.min(100, (tokensDelivered / tokensAvailable) * 100).toFixed(1)}%`
})

const formatNum = (n: number) => {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`
  return String(n ?? 0)
}
</script>

<style scoped>
.acg-metrics {
  box-sizing: border-box; display: flex; flex-direction: column; min-width: 0;
  padding: var(--space-lg); overflow: hidden;
}
.panel-head { display: flex; align-items: center; margin-bottom: 12px; }
.head-left { display: flex; align-items: center; gap: 6px; }
.head-icon { font-size: 15px; color: var(--primary-color); }
.panel-head h4 { margin: 0; font-size: 14px; font-weight: 700; color: var(--text-primary); }

.metric-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px;
}
.metric-card {
  min-width: 0; min-height: 78px; display: flex; flex-direction: column; justify-content: center; gap: 5px;
  padding: 12px 14px; border: 1px solid var(--border-light); border-radius: var(--radius-md);
  background: color-mix(in srgb, var(--bg-input) 78%, var(--bg-card));
}
.metric-card--primary {
  border-color: var(--primary-line);
  background: linear-gradient(145deg, var(--primary-fade), color-mix(in srgb, var(--bg-card) 88%, var(--primary-color)));
}
.metric-card--saved { background: color-mix(in srgb, var(--success-fade) 62%, var(--bg-card)); }
.metric-card--delivery { grid-column: 1 / -1; min-height: 68px; }
.metric-value {
  min-width: 0; color: var(--text-primary); font-size: 22px; font-weight: 780;
  line-height: 1.05; letter-spacing: -.025em; overflow-wrap: anywhere;
}
.metric-card--primary .metric-value { color: var(--primary-color); font-size: 26px; }
.metric-card--saved .metric-value { color: var(--success); }
.metric-label { color: var(--text-secondary); font-size: 11px; line-height: 1.3; }

.signal-grid {
  display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px;
  margin-top: 8px;
}
.signal-card {
  min-width: 0; display: flex; flex-direction: column; gap: 4px; padding: 9px 10px;
  border: 1px solid var(--border-light); border-radius: 8px; background: var(--bg-panel);
}
.signal-card .metric-value { font-size: 17px; }
.signal-card.warn { border-color: color-mix(in srgb, var(--warning) 45%, var(--border-light)); background: var(--warning-fade); }
.signal-card.warn .metric-value { color: var(--warning); }
.signal-card.danger { border-color: color-mix(in srgb, var(--danger) 45%, var(--border-light)); background: var(--danger-fade); }
.signal-card.danger .metric-value { color: var(--danger); }

.metrics-footer { display: grid; gap: 10px; margin-top: 12px; padding-top: 11px; border-top: 1px solid var(--border-light); }
.ledger-status { display: flex; align-items: center; gap: 6px; color: var(--text-secondary); font-size: 11px; }
.ledger-status strong { margin-left: auto; color: var(--success); font-weight: 700; }
.ledger-dot {
  width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: var(--success);
  box-shadow: 0 0 0 3px var(--success-fade);
}
.ledger-status.invalid strong { color: var(--warning); }
.ledger-status.invalid .ledger-dot { background: var(--warning); box-shadow: 0 0 0 3px var(--warning-fade); }
.bar-wrap { display: grid; gap: 6px; }
.bar-heading { display: flex; justify-content: space-between; gap: 10px; color: var(--text-secondary); font-size: 11px; }
.bar-heading strong { color: var(--success); font-weight: 700; }
.bar-track {
  height: 7px; overflow: hidden; border-radius: 999px;
  background: color-mix(in srgb, var(--primary-color) 9%, var(--bg-input));
}
.bar-fill {
  height: 100%; border-radius: inherit;
  background: linear-gradient(90deg, color-mix(in srgb, var(--bg-card) 30%, var(--primary-color)), var(--primary-color));
  transition: width .4s ease;
}
.bar-caption { color: var(--text-muted); font-size: 10px; }

@media (max-width: 360px) {
  .acg-metrics { padding: var(--space-md); }
  .signal-grid { grid-template-columns: 1fr; }
  .signal-card { flex-direction: row; align-items: center; justify-content: space-between; }
}
</style>
