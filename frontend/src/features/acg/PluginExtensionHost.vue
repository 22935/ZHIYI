<template>
  <div class="extension-host">
    <template v-for="extension in extensions" :key="extension.pluginId">
      <component
        :is="extension.taskInputComponent"
        v-if="extension.taskInputComponent"
        :model-value="pluginValue(extension.pluginId)"
        :readonly="readonly"
        @update:model-value="updatePluginValue(extension.pluginId, $event)"
      />
      <component
        :is="extension.strategyComponent"
        v-if="extension.strategyComponent"
        :model-value="pluginValue(extension.pluginId)"
        :readonly="readonly"
        @update:model-value="updatePluginValue(extension.pluginId, $event)"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import type { PluginUiExtension, WorkbenchDraft } from './workbench'

const props = defineProps<{
  extensions: PluginUiExtension[]
  draft: WorkbenchDraft
  readonly?: boolean
}>()
const emit = defineEmits<{ 'update:pluginData': [value: Record<string, Record<string, unknown>>] }>()

const pluginValue = (pluginId: string) => props.draft.pluginData[pluginId] || {}
const updatePluginValue = (pluginId: string, value: Record<string, unknown>) => {
  if (props.readonly) return
  emit('update:pluginData', { ...props.draft.pluginData, [pluginId]: value })
}
</script>

<style scoped>
.extension-host { display:flex; flex-direction:column; gap:10px; }
</style>
