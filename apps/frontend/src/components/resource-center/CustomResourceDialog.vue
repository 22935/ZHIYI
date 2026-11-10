<template>
  <el-dialog v-model="open" title="登记本地服务" width="min(520px, calc(100vw - 28px))" append-to-body>
    <form class="custom-resource-form" @submit.prevent="submit">
      <label><span>资源名称</span><input v-model.trim="form.displayName" required maxlength="120" placeholder="例如：我的本地模型" /></label>
      <label><span>资源类型</span><select v-model="form.kind"><option value="model_server">模型服务</option><option value="tool_service">工具服务</option><option value="execution_backend">执行服务</option></select></label>
      <label class="custom-resource-form__wide"><span>本地服务地址</span><input v-model.trim="form.address" required type="url" placeholder="http://127.0.0.1:11434" /><small>只允许 localhost 或本机回环地址</small></label>
      <label class="custom-resource-form__wide"><span>能力标识</span><input v-model.trim="form.capabilities" required placeholder="model.generate" /></label>
      <template v-if="form.kind === 'model_server'">
        <label><span>提供方</span><input v-model.trim="form.provider" required placeholder="Ollama" /></label>
        <label><span>模型 ID</span><input v-model.trim="form.modelIds" required placeholder="qwen3:4b" /></label>
      </template>
      <p v-if="validationError || error" class="custom-resource-form__error" role="alert">{{ validationError || error }}</p>
      <footer><button type="button" class="custom-resource-form__cancel" @click="open = false">取消</button><button type="submit" class="custom-resource-form__submit" :disabled="submitting">{{ submitting ? '正在登记…' : '检查并登记' }}</button></footer>
    </form>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { CustomLocalResourceRequest } from '@/services/api/agentos'

const props = defineProps<{ modelValue: boolean; submitting?: boolean; error?: string }>()
const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'submit', payload: CustomLocalResourceRequest): void
}>()
const open = computed({ get: () => props.modelValue, set: value => emit('update:modelValue', value) })
const form = reactive({ displayName: '', kind: 'model_server' as CustomLocalResourceRequest['kind'], address: 'http://127.0.0.1:11434', capabilities: 'model.generate', provider: '', modelIds: '' })
const validationError = ref('')
watch(() => form.kind, kind => {
  form.capabilities = kind === 'model_server' ? 'model.generate' : kind === 'tool_service' ? 'tool.invoke' : 'exec.task'
})
const submit = () => {
  validationError.value = ''
  let endpoint: URL
  try {
    endpoint = new URL(form.address)
  } catch {
    validationError.value = '请输入有效的 HTTP(S) 本地服务地址。'
    return
  }
  if (!['http:', 'https:'].includes(endpoint.protocol)) {
    validationError.value = '本地服务仅支持 HTTP 或 HTTPS。'
    return
  }
  if (!['127.0.0.1', 'localhost', '[::1]', '::1'].includes(endpoint.hostname)) {
    validationError.value = '仅允许 localhost 或本机回环地址。'
    return
  }
  emit('submit', {
    displayName: form.displayName,
    kind: form.kind,
    endpoint: { protocol: endpoint.protocol.slice(0, -1) as 'http' | 'https', address: form.address },
    capabilities: form.capabilities.split(',').map(value => value.trim()).filter(Boolean),
    ...(form.kind === 'model_server' ? {
      provider: form.provider,
      modelIds: form.modelIds.split(',').map(value => value.trim()).filter(Boolean),
      adapter: 'agentos_model_http'
    } : { adapter: 'agentos_http' })
  })
}
</script>

<style scoped>
.custom-resource-form { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 15px; }.custom-resource-form label { display: grid; gap: 6px; min-width: 0; }.custom-resource-form label > span { color: var(--text-secondary); font-size: 11px; }.custom-resource-form input, .custom-resource-form select { width: 100%; min-width: 0; min-height: 36px; padding: 0 10px; border: 1px solid var(--border-light); border-radius: 4px; color: var(--text-primary); background: var(--bg-input); font: inherit; font-size: 11px; }.custom-resource-form input:focus, .custom-resource-form select:focus { outline: 1px solid var(--primary-color); border-color: var(--primary-color); }.custom-resource-form small { color: var(--text-muted); font-size: 9px; }.custom-resource-form__wide { grid-column: 1 / -1; }.custom-resource-form__error { grid-column: 1 / -1; margin: 0; color: var(--danger); font-size: 11px; }.custom-resource-form footer { grid-column: 1 / -1; display: flex; justify-content: flex-end; gap: 8px; padding-top: 8px; }.custom-resource-form footer button { min-height: 34px; padding: 0 12px; border-radius: 4px; cursor: pointer; font: inherit; font-size: 11px; }.custom-resource-form__cancel { border: 1px solid var(--border-light); color: var(--text-secondary); background: transparent; }.custom-resource-form__submit { border: 1px solid var(--primary-color); color: #fff; background: var(--primary-color); }.custom-resource-form__submit:disabled { opacity: .6; cursor: wait; }
@media (max-width: 460px) { .custom-resource-form { grid-template-columns: 1fr; }.custom-resource-form__wide, .custom-resource-form__error, .custom-resource-form footer { grid-column: auto; } }
</style>
