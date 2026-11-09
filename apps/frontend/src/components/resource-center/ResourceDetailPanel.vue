<template>
  <div class="resource-detail">
    <header class="resource-detail__hero">
      <span class="resource-detail__icon" aria-hidden="true" :style="{ '--tile-tone': resourceTypeMeta(item.profile.resourceType).tone }"><el-icon><component :is="resourceTypeIcon(item.profile.resourceType)" /></el-icon></span>
      <div class="resource-detail__identity">
        <div class="resource-detail__title">
          <strong>{{ item.profile.resourceId }}</strong>
          <ResourceTypeBadge :type="item.profile.resourceType" />
        </div>
        <span>{{ tierLabel(item.profile.deploymentTier) }} · v{{ item.profile.version }}</span>
      </div>
      <span class="resource-detail__health" :class="`is-${item.snapshot.healthStatus}`">{{ healthLabel(item.snapshot.healthStatus) }}</span>
    </header>

    <section class="resource-detail__section">
      <h3>资源概览</h3>
      <dl class="resource-detail__kv">
        <div><dt>健康状态</dt><dd :class="`is-${item.snapshot.healthStatus}`">{{ healthLabel(item.snapshot.healthStatus) }}</dd></div>
        <template v-if="!isModelEndpoint">
          <div><dt>可用槽位</dt><dd>{{ item.snapshot.availableSlots ?? '未观测' }} / {{ item.profile.capacity }}</dd></div>
          <div><dt>利用率</dt><dd>{{ formatPercent(item.snapshot.utilization) }}</dd></div>
          <div><dt>延迟</dt><dd>{{ formatMetric(item.snapshot.latencyMs, 'ms') }}</dd></div>
          <div><dt>可靠性</dt><dd>{{ formatPercent(item.snapshot.reliability) }}</dd></div>
        </template>
      </dl>
    </section>

    <section v-if="healthEvents.length" class="resource-detail__section">
      <h3>健康趋势</h3>
      <div class="resource-detail__spark">
        <span class="resource-detail__spark-label">可靠性</span>
        <svg viewBox="0 0 100 24" preserveAspectRatio="none" role="img" aria-label="可靠性历史曲线">
          <polyline :points="reliabilityPoints" fill="none" stroke="currentColor" stroke-width="1.6" vector-effect="non-scaling-stroke" />
        </svg>
      </div>
      <div v-if="latencyPoints" class="resource-detail__spark">
        <span class="resource-detail__spark-label">延迟</span>
        <svg viewBox="0 0 100 24" preserveAspectRatio="none" role="img" aria-label="延迟历史曲线">
          <polyline :points="latencyPoints" fill="none" stroke="currentColor" stroke-width="1.6" vector-effect="non-scaling-stroke" />
        </svg>
      </div>
      <p class="resource-detail__spark-meta">最近 {{ healthEvents.length }} 次观测 · 最早 {{ formatDate(healthEvents[healthEvents.length - 1]?.observedAt) }}</p>
    </section>

    <section class="resource-detail__section">
      <div class="resource-detail__section-head">
        <h3>最近参与任务</h3>
        <span v-if="usageTotal !== null">{{ usageTotal }} 条绑定记录</span>
      </div>
      <ul v-if="usageRecords.length" class="resource-detail__usage">
        <li v-for="record in usageRecords" :key="record.bindingId">
          <div class="resource-detail__usage-main">
            <strong>{{ record.taskTitle || record.semanticTaskKey || record.taskId }}</strong>
            <span>{{ record.runId }} · 第 {{ record.attemptNumber }} 次 · {{ usageStatusLabel(record.attemptStatus) }}</span>
          </div>
          <div class="resource-detail__usage-side">
            <span>{{ formatMetric(relativeMinutes(record.startedAt), '分钟前') }}</span>
            <em>{{ record.modelId }}</em>
          </div>
        </li>
      </ul>
      <p v-else class="resource-detail__empty">{{ usageError || '暂无运行绑定记录' }}</p>
      <router-link class="resource-detail__history-link" :to="{ path: '/history', query: { tab: 'acg' } }">在运行记忆中查看 →</router-link>
    </section>

    <section v-if="isModelEndpoint" class="resource-detail__section">
      <h3>模型概况</h3>
      <dl class="resource-detail__kv">
        <div><dt>供应商</dt><dd>{{ item.profile.provider || '未登记' }}</dd></div>
        <div><dt>模型</dt><dd>{{ item.profile.model || item.profile.modelIds?.[0] || '未登记' }}</dd></div>
        <div><dt>上下文窗口</dt><dd>{{ formatMetric(item.profile.contextWindowTokens, 'tokens') }}</dd></div>
        <div><dt>最大输出</dt><dd>{{ formatMetric(item.profile.maxOutputTokens, 'tokens') }}</dd></div>
      </dl>
    </section>

    <details v-if="!isModelEndpoint" class="resource-detail__advanced">
      <summary>高级设置</summary>
      <p>停止后不会删除资源或历史记录；新的任务将不再使用此资源。</p>
      <section v-if="item.profile.computeCapacity" class="resource-detail__section">
      <h3>算力画像</h3>
      <dl class="resource-detail__kv">
        <div><dt>登记算力</dt><dd>{{ formatCapacity(item.profile.computeCapacity) }}</dd></div>
      </dl>
      </section>

      <section class="resource-detail__section">
      <h3>部署与归属</h3>
      <dl class="resource-detail__kv">
        <div><dt>资源类型</dt><dd>{{ resourceTypeMeta(item.profile.runtimeKind || item.profile.resourceType).label }}</dd></div>
        <div v-if="item.profile.nodeId"><dt>宿主节点</dt><dd>{{ item.profile.nodeId }}</dd></div>
        <div v-if="item.profile.hostRuntimeId"><dt>宿主服务</dt><dd>{{ item.profile.hostRuntimeId }}</dd></div>
        <div v-if="item.profile.trust"><dt>信任等级</dt><dd>{{ item.profile.trust }}</dd></div>
        <div><dt>部署层级</dt><dd>{{ tierLabel(item.profile.deploymentTier) }}</dd></div>
        <div><dt>隐私级别</dt><dd>{{ item.profile.privacyLevel || '未标注' }}</dd></div>
        <div><dt>数据域</dt><dd>{{ item.profile.dataZone || '未标注' }}</dd></div>
        <div><dt>位置</dt><dd>{{ item.profile.location || '未标注' }}</dd></div>
        <div><dt>归属</dt><dd>{{ item.profile.ownerScope || '未标注' }}</dd></div>
        <div><dt>资源来源</dt><dd>{{ item.profile.sourceType || '未标注' }}</dd></div>
        <div><dt>厂家 / 提供方</dt><dd>{{ item.profile.provider || '未标注' }}</dd></div>
        <div><dt>接入适配器</dt><dd>{{ item.profile.adapter || '未标注' }}</dd></div>
        <!-- 执行端点与凭据引用已随 N1.2 投影迁移从资源目录移除（任务书：资源目录无 endpoint/credential）。 -->
      </dl>
      </section>

      <section v-if="item.profile.capabilities.length" class="resource-detail__section">
      <h3>能力</h3>
      <div class="resource-detail__chips">
        <span v-for="capability in item.profile.capabilities" :key="capability">{{ capability }}</span>
      </div>
      </section>

      <section v-if="item.profile.domains.length" class="resource-detail__section">
      <h3>领域</h3>
      <div class="resource-detail__chips">
        <span v-for="domain in item.profile.domains" :key="domain">{{ domain }}</span>
      </div>
      </section>

      <section v-if="item.profile.modelIds?.length" class="resource-detail__section">
      <h3>挂载模型</h3>
      <div class="resource-detail__chips">
        <span v-for="modelId in item.profile.modelIds" :key="modelId">{{ modelId }}</span>
      </div>
      </section>

      <section v-if="item.profile.labels?.length" class="resource-detail__section">
      <h3>标签</h3>
      <dl class="resource-detail__kv">
        <div v-for="label in item.profile.labels" :key="label.key"><dt>{{ label.key }}</dt><dd>{{ label.value }}</dd></div>
      </dl>
      </section>

      <section v-if="item.profile.costMetadata?.length" class="resource-detail__section">
      <h3>成本元数据</h3>
      <dl class="resource-detail__kv">
        <div v-for="cost in item.profile.costMetadata" :key="cost.key"><dt>{{ cost.key }}</dt><dd>{{ cost.value }}</dd></div>
      </dl>
      </section>

      <section v-if="credential" class="resource-detail__section">
      <h3>凭据</h3>
      <dl class="resource-detail__kv">
        <div><dt>凭据 ID</dt><dd class="resource-detail__mono">{{ credential.credentialId }}</dd></div>
        <div><dt>创建于</dt><dd>{{ formatDate(credential.createdAt) }}</dd></div>
      </dl>
      <div class="resource-detail__probe">
        <button type="button" :disabled="rotatePending" @click="onRotate">
          {{ rotatePending ? '轮换中…' : '轮换凭据' }}
        </button>
      </div>
      </section>

      <section class="resource-detail__section">
      <h3>观测信息</h3>
      <dl class="resource-detail__kv">
        <div><dt>观测时间</dt><dd>{{ formatDate(item.snapshot.observedAt) }}</dd></div>
        <div><dt>快照版本</dt><dd>v{{ item.snapshotVersion }}</dd></div>
      </dl>
      </section>
      <div v-if="!isModelEndpoint" class="resource-detail__toggle">
        <span>参与调度</span>
        <el-switch
          :model-value="item.profile.enabled"
          :loading="enabledPending"
          size="small"
          aria-label="切换该资源是否参与调度"
          @change="onToggleEnabled"
        />
        <span :class="{ 'is-off': !item.profile.enabled }">{{ item.profile.enabled ? '已启用' : '已停用' }}</span>
      </div>
      <div v-if="canProbe" class="resource-detail__probe">
        <button type="button" :disabled="probePending" @click="onProbe">
          {{ probePending ? '检测中…' : '检测连接' }}
        </button>
        <span v-if="probeResult" :class="{ 'is-offline': !probeResult.healthy }">
          {{ probeResult.healthy ? '连接正常' : '连接失败' }} · {{ formatMetric(probeResult.latencyMs, 'ms') }}
        </span>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { agentosApi, type ResourceCredentialMetadata, type ResourceHealthEvent, type ResourceUsageRecord, type RuntimeResourceItem } from '@/services/api/agentos'
import ResourceTypeBadge from './ResourceTypeBadge.vue'
import { formatDate, formatMetric, formatPercent, healthLabel, resourceTypeMeta, tierLabel, formatCapacity } from '@/utils/resourceFormat'
import { resourceTypeIcon } from '@/utils/resourceTypeIcons'

const props = defineProps<{ item: RuntimeResourceItem }>()
const emit = defineEmits<{ (event: 'enabled-changed', payload: { resourceId: string; enabled: boolean }): void }>()

const enabledPending = ref(false)
const probePending = ref(false)
const probeResult = ref<{ healthy: boolean; latencyMs: number | null } | null>(null)
const usageRecords = ref<ResourceUsageRecord[]>([])
const usageTotal = ref<number | null>(null)
const usageError = ref('')
const healthEvents = ref<ResourceHealthEvent[]>([])
const credential = ref<ResourceCredentialMetadata | null>(null)
const rotatePending = ref(false)
const isModelEndpoint = computed(() => props.item.profile.runtimeKind === 'model_endpoint')

const canProbe = computed(() => !isModelEndpoint.value && props.item.profile.deploymentTier !== 'device' && props.item.profile.deploymentTier !== 'local' && props.item.profile.resourceType === 'worker')

const loadDetailData = async () => {
  const resourceId = props.item.profile.resourceId
  usageRecords.value = []
  usageTotal.value = null
  usageError.value = ''
  healthEvents.value = []
  credential.value = null
  probeResult.value = null
  if (isModelEndpoint.value) return
  const [usage, history, credentialResult] = await Promise.allSettled([
    agentosApi.listResourceUsage(resourceId, { limit: 12 }),
    agentosApi.getResourceHealthHistory(resourceId, { limit: 40 }),
    agentosApi.getResourceCredential(resourceId)
  ])
  if (props.item.profile.resourceId !== resourceId) return
  if (usage.status === 'fulfilled') {
    usageRecords.value = usage.value.items
    usageTotal.value = usage.value.total
  } else {
    usageError.value = '运行绑定记录读取失败'
  }
  if (history.status === 'fulfilled') {
    // 上游按最新在前返回；曲线按时间正序绘制。
    healthEvents.value = [...history.value.items].reverse()
  }
  if (credentialResult.status === 'fulfilled') {
    credential.value = credentialResult.value
  }
}

onMounted(() => { void loadDetailData() })
watch(() => props.item.profile.resourceId, () => { void loadDetailData() })

const onToggleEnabled = async (value: string | number | boolean) => {
  const enabled = Boolean(value)
  const resourceId = props.item.profile.resourceId
  if (!enabled) {
    try {
      await ElMessageBox.confirm(
        '停止后，新的任务不会再使用此资源；资源配置和历史记录会保留。继续？',
        '停止使用资源',
        { confirmButtonText: '停止使用', cancelButtonText: '取消', type: 'warning' }
      )
    } catch {
      return
    }
  }
  enabledPending.value = true
  try {
    const result = await agentosApi.setResourceEnabled(resourceId, enabled)
    emit('enabled-changed', { resourceId, enabled: result.enabled })
    ElMessage.success(result.enabled ? '已恢复参与调度' : '已停用调度')
  } catch {
    ElMessage.error('启停切换失败，请稍后重试')
  } finally {
    enabledPending.value = false
  }
}

const onProbe = async () => {
  probePending.value = true
  probeResult.value = null
  try {
    const result = await agentosApi.probeResource(props.item.profile.resourceId)
    probeResult.value = { healthy: result.healthy, latencyMs: result.latencyMs }
  } catch {
    ElMessage.error('该资源不支持主动探测')
  } finally {
    probePending.value = false
  }
}

const onRotate = async () => {
  try {
    await ElMessageBox.confirm(
      '轮换后旧凭据立即失效，远端资源需使用新密钥重新接入。继续？',
      '轮换资源凭据',
      { confirmButtonText: '轮换', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return
  }
  rotatePending.value = true
  try {
    const result = await agentosApi.rotateResourceCredential(props.item.profile.resourceId)
    await ElMessageBox.alert(
      `新凭据仅本次显示，请立即复制保存：\n${result.secret}`,
      '凭据已轮换',
      { confirmButtonText: '已保存' }
    )
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error('凭据轮换失败（需要 operator 权限）')
    }
  } finally {
    rotatePending.value = false
  }
}

const usageStatusLabel = (status: string) => ({
  succeeded: '成功',
  failed: '失败',
  running: '运行中',
  pending: '等待中'
}[status] || status)

const relativeMinutes = (iso?: string | null) => {
  if (!iso) return null
  const started = new Date(iso).getTime()
  if (!Number.isFinite(started)) return null
  return Math.max(0, Math.round((Date.now() - started) / 60000))
}

const sparklinePoints = (values: Array<number | null | undefined>): string => {
  const finite = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (finite.length < 2) return ''
  const min = Math.min(...finite)
  const max = Math.max(...finite)
  const span = max - min || 1
  return values
    .map((value, index) => {
      if (typeof value !== 'number' || !Number.isFinite(value)) return null
      const x = values.length > 1 ? (index / (values.length - 1)) * 100 : 50
      const y = 22 - ((value - min) / span) * 20
      return `${x.toFixed(2)},${y.toFixed(2)}`
    })
    .filter((point): point is string => point !== null)
    .join(' ')
}

const reliabilityPoints = computed(() => sparklinePoints(healthEvents.value.map(event => event.reliability)))
const latencyPoints = computed(() => {
  const points = sparklinePoints(healthEvents.value.map(event => event.latencyMs))
  return points
})
</script>

<style scoped>
.resource-detail { display: grid; gap: 18px; padding: 4px 2px 24px; color: var(--text-primary); }
.resource-detail__hero { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border: 1px solid var(--border-light); border-radius: var(--radius-card, 9px); background: var(--bg-card); }
.resource-detail__icon { display: inline-grid; place-items: center; flex: 0 0 auto; width: 40px; height: 40px; border-radius: 11px; color: color-mix(in srgb, var(--tile-tone, var(--primary-color)) 40%, #e9f5ff); background: linear-gradient(145deg, color-mix(in srgb, var(--tile-tone, var(--primary-color)) 34%, transparent), color-mix(in srgb, var(--tile-tone, var(--primary-color)) 10%, transparent) 55%, color-mix(in srgb, var(--tile-tone, var(--primary-color)) 24%, transparent)), var(--bg-input); border: 1px solid color-mix(in srgb, var(--tile-tone, var(--primary-color)) 46%, transparent); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.09), 0 0 12px color-mix(in srgb, var(--tile-tone, var(--primary-color)) 16%, transparent); }
.resource-detail__icon .el-icon { font-size: 20px; filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.35)); }
.resource-detail__identity { display: grid; gap: 3px; min-width: 0; flex: 1; }
.resource-detail__title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.resource-detail__title strong { min-width: 0; }
.resource-detail__identity strong { overflow: hidden; color: var(--text-primary); font: 600 13px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.resource-detail__identity span:not(.resource-detail__icon) { color: var(--text-muted); font: 10px var(--font-mono, monospace); }
.resource-detail__health { flex: 0 0 auto; padding: 3px 9px; border-radius: 999px; color: var(--text-secondary); background: var(--bg-input); font-size: 11px; }
.resource-detail__health.is-online { color: var(--success); }
.resource-detail__health.is-degraded { color: var(--warning); }
.resource-detail__health.is-offline { color: var(--danger); }
.resource-detail__section { display: grid; gap: 8px; }
.resource-detail__section h3 { margin: 0; color: var(--text-secondary); font-size: 11px; font-weight: 650; letter-spacing: .02em; }
.resource-detail__kv { display: grid; margin: 0; border: 1px solid var(--border-light); border-radius: var(--radius-card, 9px); overflow: hidden; }
.resource-detail__kv > div { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 9px 14px; border-bottom: 1px solid var(--border-light); background: var(--bg-card); }
.resource-detail__kv > div:last-child { border-bottom: 0; }
.resource-detail__kv dt { color: var(--text-muted); font-size: 11px; }
.resource-detail__kv dd { margin: 0; color: var(--text-secondary); font: 11px var(--font-mono, monospace); text-align: right; word-break: break-all; }
.resource-detail__kv dd.is-online { color: var(--success); }
.resource-detail__kv dd.is-degraded { color: var(--warning); }
.resource-detail__kv dd.is-offline { color: var(--danger); }
.resource-detail__code { font-size: 10px !important; }
.resource-detail__chips { display: flex; gap: 6px; flex-wrap: wrap; }
.resource-detail__chips span { padding: 4px 9px; border: 1px solid var(--border-light); border-radius: 4px; color: var(--text-secondary); background: var(--bg-input); font: 10px var(--font-mono, monospace); }
.resource-detail__section-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.resource-detail__section-head span { color: var(--text-muted); font-size: 10px; }
.resource-detail__toggle { display: inline-flex; align-items: center; gap: 8px; justify-content: flex-end; }
.resource-detail__advanced { display: grid; gap: 10px; padding: 12px 14px; border: 1px solid var(--border-light); border-radius: var(--radius-card, 9px); background: var(--bg-card); }
.resource-detail__advanced summary { color: var(--text-secondary); cursor: pointer; font-size: 11px; font-weight: 650; }
.resource-detail__advanced p { margin: 0; color: var(--text-muted); font-size: 11px; line-height: 1.6; }
.resource-detail__toggle span.is-off { color: var(--text-muted); }
.resource-detail__probe { display: flex; align-items: center; gap: 10px; }
.resource-detail__probe button { padding: 4px 12px; border: 1px solid var(--primary-line); border-radius: 5px; color: var(--primary-color); background: var(--primary-fade); cursor: pointer; font: inherit; font-size: 11px; transition: var(--transition); }
.resource-detail__probe button:hover:not(:disabled) { border-color: var(--primary-color); }
.resource-detail__probe button:disabled { cursor: default; opacity: .55; }
.resource-detail__probe span { color: var(--text-muted); font: 10px var(--font-mono, monospace); }
.resource-detail__probe span.is-offline { color: var(--danger); }
.resource-detail__spark { display: grid; grid-template-columns: 44px 1fr; align-items: center; gap: 8px; color: var(--primary-color); }
.resource-detail__spark-label { color: var(--text-muted); font-size: 10px; }
.resource-detail__spark svg { width: 100%; height: 24px; display: block; }
.resource-detail__spark-meta { margin: 0; color: var(--text-muted); font-size: 10px; }
.resource-detail__usage { display: grid; gap: 6px; margin: 0; padding: 0; list-style: none; }
.resource-detail__usage li { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 11px; border: 1px solid var(--border-light); border-radius: var(--radius-card, 9px); background: var(--bg-card); }
.resource-detail__usage-main { display: grid; gap: 3px; min-width: 0; }
.resource-detail__usage-main strong { overflow: hidden; color: var(--text-primary); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.resource-detail__usage-main span { overflow: hidden; color: var(--text-muted); font: 10px var(--font-mono, monospace); text-overflow: ellipsis; white-space: nowrap; }
.resource-detail__usage-side { display: grid; gap: 3px; flex: 0 0 auto; justify-items: end; }
.resource-detail__usage-side span { color: var(--text-muted); font: 10px var(--font-mono, monospace); }
.resource-detail__usage-side em { color: var(--text-secondary); font: 9px var(--font-mono, monospace); font-style: normal; }
.resource-detail__empty { margin: 0; color: var(--text-muted); font-size: 11px; }
.resource-detail__history-link { color: var(--primary-color); font-size: 11px; text-decoration: none; }
.resource-detail__history-link:hover { text-decoration: underline; }
.resource-detail__mono { font-family: var(--font-mono, monospace); }
</style>

