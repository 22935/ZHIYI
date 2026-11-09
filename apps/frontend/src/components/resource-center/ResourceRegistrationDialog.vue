<template>
  <el-dialog :model-value="modelValue" width="760px" class="resource-registration" align-center
    :show-close="!issued" :close-on-click-modal="false" :close-on-press-escape="!issued"
    @update:model-value="emit('update:modelValue', $event)" @closed="resetForm">
    <template #header><div class="rr-header"><span class="rr-header__icon"><el-icon><Connection /></el-icon></span>
      <div class="rr-header__copy"><strong>接入您的资源</strong><span>连接设备、模型和工具服务，供任务在授权范围内使用</span></div></div></template>
    <div v-if="issued" class="rr-body" role="status">
      <h3>接入信息已创建，请保存凭据</h3>
      <p>密钥仅在本次显示。完成设备连接后，返回资源中心执行“检测连接”确认可用状态。</p>
      <label class="rr-field"><span>凭据 ID</span><input :value="issued.credentialId" readonly /></label>
      <label class="rr-field"><span>接入密钥</span><textarea :value="issued.secret" readonly aria-label="一次性接入密钥" /></label>
    </div>
    <div v-else class="rr-body">
      <section class="rr-section"><h3 class="rr-section__title">选择接入类型</h3>
        <div class="rr-type-grid">
          <button v-for="option in registrationTypes" :key="option.value" type="button" class="rr-type"
            :class="{ 'is-active': form.kind === option.value }" @click="selectRegistrationKind(option.value)">
            <strong>{{ option.label }}</strong><small>{{ option.description }}</small></button>
        </div>
      </section>
      <section class="rr-section"><h3 class="rr-section__title">基础信息</h3><div class="rr-form">
        <div class="rr-grid rr-grid--2">
          <label class="rr-field"><span>{{ isDevice ? '设备 ID' : '服务 ID' }} *</span><input v-model="form.id" placeholder="例如 device:edge:research / service:research" /></label>
          <label class="rr-field"><span>显示名称</span><input v-model="form.name" placeholder="便于识别的名称" /></label>
        </div>
        <template v-if="isDevice">
          <div class="rr-grid rr-grid--3">
            <label class="rr-field"><span>部署位置</span><select v-model="form.placement"><option value="device">端侧设备</option><option value="edge">边缘节点</option><option value="cloud">云端节点</option></select></label>
            <label class="rr-field"><span>信任等级</span><select v-model="form.trust"><option value="trusted">Trusted</option><option value="sandboxed">Sandboxed</option><option value="untrusted">Untrusted</option></select></label>
            <label class="rr-field"><span>归属范围 *</span><input v-model="form.ownerScope" placeholder="该节点所属的操作范围" /></label>
          </div>
          <div class="rr-grid rr-grid--3">
            <label class="rr-field"><span>资源来源</span><input v-model="form.sourceType" placeholder="如 kubernetes、vendor_agent" /></label>
            <label class="rr-field"><span>厂家 / 提供方</span><input v-model="form.provider" placeholder="如 NVIDIA、华为、AWS" /></label>
            <label class="rr-field"><span>接入适配器</span><input v-model="form.adapter" placeholder="如 k8s-agentos、vendor-sdk" /></label>
          </div>
          <div class="rr-grid rr-grid--3">
            <label class="rr-field"><span>CPU 核数</span><input v-model.number="form.cpuCores" type="number" min="0" /></label>
            <label class="rr-field"><span>内存 MB</span><input v-model.number="form.memoryMb" type="number" min="0" /></label>
            <label class="rr-field"><span>GPU 显存 MB</span><input v-model.number="form.gpuMemoryMb" type="number" min="0" /></label>
          </div>
          <label class="rr-field"><span>GPU 型号</span><input v-model="form.gpuType" placeholder="未登记可留空" /></label>
        </template>
        <template v-else>
          <label class="rr-field"><span>宿主节点 *</span><select v-model="form.nodeId" :disabled="nodesLoading">
            <option value="">{{ nodesLoading ? '正在读取节点…' : '选择已登记的远程节点' }}</option>
            <option v-for="node in remoteNodes" :key="node.profile.nodeId" :value="node.profile.nodeId">{{ node.profile.displayName || node.profile.nodeId }} · {{ node.profile.placement }}</option>
          </select></label>
          <p v-if="!nodesLoading && !remoteNodes.length" class="rr-hint">暂无可用设备，请先完成“接入设备”。</p>
          <p v-if="selectedNode" class="rr-hint">归属：{{ selectedNode.profile.ownerScope }} · 信任：{{ selectedNode.profile.trust }}</p>
          <div class="rr-grid rr-grid--3">
            <label class="rr-field"><span>资源来源</span><input v-model="form.sourceType" placeholder="如 openai_compatible、mcp" /></label>
            <label class="rr-field"><span>厂家 / 提供方{{ form.kind === 'model' ? ' *' : '' }}</span><input v-model="form.provider" placeholder="如 vLLM、火山引擎" /></label>
            <label class="rr-field"><span>执行协议适配器</span><select v-model="form.adapter"><option value="agentos_http">AgentOS HTTP</option></select></label>
          </div>
          <div class="rr-grid rr-grid--2">
            <label class="rr-field"><span>能力 *</span><el-select v-model="form.capabilities" multiple filterable allow-create default-first-option placeholder="输入能力后回车" /></label>
            <label class="rr-field"><span>领域</span><el-select v-model="form.domains" multiple filterable allow-create default-first-option placeholder="例如 general" /></label>
          </div>
          <div class="rr-grid rr-grid--2">
            <label class="rr-field"><span>端点协议</span><select v-model="form.protocol"><option value="https">HTTPS</option><option value="http">HTTP</option></select></label>
            <label class="rr-field"><span>服务地址 *</span><input v-model="form.address" placeholder="例如 https://worker.example.com" /></label>
          </div>
          <label class="rr-field rr-field--capacity"><span>并发容量</span><input v-model.number="form.capacity" type="number" min="1" step="1" /></label>
          <label v-if="form.kind === 'model'" class="rr-field"><span>模型标识 *</span><el-select v-model="form.modelIds" multiple filterable allow-create default-first-option placeholder="输入模型名称后回车" /></label>
        </template>
      </div></section>
      <p v-if="errorMessage" class="rr-error" role="alert">{{ errorMessage }}</p>
    </div>
    <template #footer><div class="rr-footer">
      <button v-if="!issued" type="button" class="rr-cancel" :disabled="submitting" @click="emit('update:modelValue', false)">取消</button>
      <button type="button" class="rr-submit" :disabled="submitting" @click="issued ? finish() : submit()">{{ issued ? '已保存，完成' : submitting ? '接入中…' : '接入资源' }}</button>
    </div></template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Connection } from '@element-plus/icons-vue'
import { agentosApi, type NodeCatalogItem, type ResourceRegistrationResult } from '@/services/api/agentos'
const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', value: boolean): void; (e: 'registered'): void }>()
const registrationTypes = [
  { value: 'device', label: '接入设备', description: '本地或边缘设备，用于承载任务' },
  { value: 'model', label: '接入模型', description: '连接自有模型服务或登记云端模型' },
  { value: 'tool', label: '接入工具', description: '接入 AgentOS HTTP 执行服务' }
] as const
const defaults = () => ({ kind: 'device' as 'device' | 'model' | 'tool',
  id: '', name: '', placement: 'edge' as 'device' | 'edge' | 'cloud', trust: 'trusted', ownerScope: '', nodeId: '',
  sourceType: '', provider: '', adapter: '',
  capabilities: [] as string[], domains: [] as string[], modelIds: [] as string[],
  protocol: 'https', address: '', capacity: 1, cpuCores: 0, memoryMb: 0, gpuMemoryMb: 0, gpuType: '' })
const form = reactive(defaults())
const nodes = ref<NodeCatalogItem[]>([])
const nodesLoading = ref(false)
const submitting = ref(false)
const errorMessage = ref('')
const issued = ref<ResourceRegistrationResult | null>(null)
const isDevice = computed(() => form.kind === 'device')
const isModel = computed(() => form.kind === 'model')
const selectRegistrationKind = (kind: typeof form.kind) => {
  form.kind = kind
  if (kind !== 'device' && !form.adapter) form.adapter = 'agentos_http'
}
const remoteNodes = computed(() => nodes.value.filter(n => n.profile.enabled && ['device', 'edge', 'cloud'].includes(n.profile.placement) && n.profile.ownerScope))
const selectedNode = computed(() => remoteNodes.value.find(n => n.profile.nodeId === form.nodeId))
let nodeLoad = 0
watch(() => props.modelValue, async open => {
  if (!open) { nodeLoad++; return }
  const request = ++nodeLoad
  nodesLoading.value = true
  try { const result = await agentosApi.listNodes(); if (request === nodeLoad) nodes.value = result.items }
  catch { if (request === nodeLoad) errorMessage.value = '节点目录读取失败，可先登记节点或关闭后重试。' }
  finally { if (request === nodeLoad) nodesLoading.value = false }
}, { immediate: true })
const submit = async () => {
  if (submitting.value) return
  errorMessage.value = ''
  if (!form.id.trim() || (isDevice.value ? !form.ownerScope.trim() : !selectedNode.value || !form.capabilities.length || !form.address.trim()
    || (isModel.value && (!form.provider.trim() || !form.modelIds.length)))) {
    errorMessage.value = isDevice.value ? '请填写设备 ID 和归属范围。'
      : isModel.value ? '请填写模型服务 ID，选择承载设备，并提供厂家、模型标识、能力及服务地址。'
        : '请填写服务 ID，选择承载设备，并提供能力及服务地址。'
    return
  }
  if (!isDevice.value && (!Number.isInteger(form.capacity) || form.capacity < 1)) { errorMessage.value = '并发容量必须是正整数。'; return }
  submitting.value = true
  try {
    if (isDevice.value) {
      issued.value = await agentosApi.registerNode({ profile: { nodeId: form.id.trim(), displayName: form.name.trim(),
        placement: form.placement, trust: form.trust, ownerScope: form.ownerScope.trim(),
        sourceType: form.sourceType.trim() || undefined, provider: form.provider.trim() || undefined,
        adapter: form.adapter || undefined,
        computeCapacity: { cpuCores: form.cpuCores, memoryMb: form.memoryMb, gpuMemoryMb: form.gpuMemoryMb, gpuType: form.gpuType.trim() || null, bandwidthMbps: 0 } },
        snapshot: { nodeId: form.id.trim(), healthStatus: 'offline' } })
    } else {
      const node = selectedNode.value!.profile
      issued.value = await agentosApi.registerResource({ profile: { runtimeId: form.id.trim(), displayName: form.name.trim(),
        kind: form.kind === 'model' ? 'model_server' : 'tool_service', nodeId: node.nodeId,
        placement: node.placement as 'device' | 'edge' | 'cloud', trust: node.trust, ownerScope: node.ownerScope!,
        sourceType: form.sourceType.trim() || undefined, provider: form.provider.trim() || undefined,
        adapter: form.adapter.trim() || 'agentos_http',
        capabilities: [...form.capabilities], domains: [...form.domains], modelIds: form.kind === 'model' ? [...form.modelIds] : [],
        capacity: form.capacity, enabled: true, endpoint: { protocol: form.protocol, address: form.address.trim() } },
        snapshot: { runtimeId: form.id.trim(), availableSlots: form.capacity, utilization: 0, healthStatus: 'unknown' } })
    }
  } catch (error: unknown) {
    const data = (error as { response?: { data?: { detail?: unknown; message?: unknown } } })?.response?.data
    const detail = data?.detail || data?.message
    errorMessage.value = typeof detail === 'string' ? detail : '注册失败，请检查标识、权限及宿主节点约束。'
  } finally { submitting.value = false }
}
const finish = () => { issued.value = null; emit('registered'); emit('update:modelValue', false) }
const resetForm = () => { Object.assign(form, defaults()); issued.value = null; errorMessage.value = ''; nodes.value = []; nodesLoading.value = false }
</script>

<style scoped>
.rr-header { display: flex; align-items: center; gap: 12px; }
.rr-header__icon { display: inline-grid; place-items: center; width: 40px; height: 40px; border-radius: 12px; color: var(--primary-color); background: var(--primary-fade); }
.rr-header__copy { display: grid; gap: 4px; }
.rr-header__copy strong { color: var(--text-primary); font-size: 15px; }
.rr-header__copy span, .rr-hint { color: var(--text-muted); font-size: 11px; }
.rr-body { display: grid; gap: 22px; max-height: 62vh; overflow-y: auto; padding-right: 4px; }
.rr-body > p { font-size: 12px; color: var(--text-secondary); line-height: 1.7; }
.rr-section, .rr-form { display: grid; gap: 14px; }
.rr-section__title { margin: 0; color: var(--text-secondary); font-size: 12px; }
.rr-type-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }
.rr-type { display: grid; gap: 6px; padding: 14px 12px; border: 1px solid var(--border-light); border-radius: 10px; color: var(--text-secondary); background: var(--bg-card); cursor: pointer; text-align: left; }
.rr-type.is-active { border-color: var(--primary-color); color: var(--primary-color); background: var(--primary-fade); }
.rr-type small { color: var(--text-muted); font-size: 10px; }
.rr-grid { display: grid; gap: 14px; }
.rr-grid--2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.rr-grid--3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.rr-field { display: grid; gap: 6px; min-width: 0; }
.rr-field > span { color: var(--text-muted); font-size: 11px; }
.rr-field input, .rr-field select, .rr-field textarea { width: 100%; min-height: 38px; box-sizing: border-box; padding: 8px 11px; border: 1px solid var(--border-light); border-radius: 8px; color: var(--text-primary); background: var(--bg-input); font: inherit; font-size: 12px; outline: 0; }
.rr-field input:focus, .rr-field select:focus, .rr-field textarea:focus { border-color: var(--primary-color); }
.rr-field textarea { min-height: 80px; resize: vertical; overflow-wrap: anywhere; }
.rr-field--capacity { max-width: 160px; }
.rr-error { margin: 0; padding: 10px 12px; border-radius: 8px; color: var(--danger, #b64d55); background: var(--bg-input); font-size: 12px; }
.rr-footer { display: flex; justify-content: flex-end; gap: 10px; }
.rr-cancel, .rr-submit { min-height: 36px; padding: 0 18px; border: 1px solid var(--border-light); border-radius: 8px; color: var(--text-secondary); background: transparent; cursor: pointer; font: inherit; font-size: 12px; }
.rr-submit { border-color: var(--primary-color); color: #fff; background: var(--primary-color); }
.rr-footer button:disabled { opacity: .55; cursor: not-allowed; }
@media (max-width: 640px) { .rr-type-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .rr-grid--2, .rr-grid--3 { grid-template-columns: 1fr; } }
</style>
