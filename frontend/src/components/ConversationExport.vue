<!-- 对话导出对话框 — 支持将对话导出为 JSON / TXT / CSV / Markdown 格式 -->
<template>
  <el-dialog
    v-model="visible"
    title="导出对话"
    width="400px"
  >
    <el-form>
      <el-form-item label="导出格式">
        <el-radio-group v-model="exportFormat">
          <el-radio label="json">JSON</el-radio>
          <el-radio label="txt">TXT</el-radio>
          <el-radio label="csv">CSV</el-radio>
          <el-radio label="md">Markdown</el-radio>
        </el-radio-group>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="handleExport">导出</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { 
  exportConversationToJson, 
  exportConversationToTxt, 
  exportConversationToCsv,
  exportConversationToMarkdown,
  downloadFile 
} from '@/utils/export'
import type { ConversationExport } from '@/utils/export'

interface Props {
  modelValue: boolean
  conversation: ConversationExport
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const exportFormat = ref<'json' | 'txt' | 'csv' | 'md'>('txt')

const handleExport = () => {
  try {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')
    let content: string
    let filename: string
    let mimeType: string

    if (exportFormat.value === 'json') {
      content = exportConversationToJson(props.conversation)
      filename = `conversation-${timestamp}.json`
      mimeType = 'application/json'
    } else if (exportFormat.value === 'csv') {
      content = exportConversationToCsv(props.conversation)
      filename = `conversation-${timestamp}.csv`
      mimeType = 'text/csv;charset=utf-8'
    } else if (exportFormat.value === 'md') {
      content = exportConversationToMarkdown(props.conversation)
      filename = `conversation-${timestamp}.md`
      mimeType = 'text/markdown'
    } else {
      content = exportConversationToTxt(props.conversation)
      filename = `conversation-${timestamp}.txt`
      mimeType = 'text/plain'
    }

    downloadFile(content, filename, mimeType)
    ElMessage.success('导出成功')
    visible.value = false
  } catch (error) {
    ElMessage.error('导出失败')
  }
}
</script>


