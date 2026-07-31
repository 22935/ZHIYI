<!-- 文件上传组件 — 基于 Element Plus 的单文件上传按钮，含图片预览和删除 -->
<template>
  <div class="file-upload">
    <el-upload
      :action="uploadUrl"
      :headers="uploadHeaders"
      :on-success="handleSuccess"
      :on-error="handleError"
      :before-upload="beforeUpload"
      :show-file-list="false"
      :disabled="disabled"
    >
      <el-button :icon="Upload" :disabled="disabled">
        {{ buttonText }}
      </el-button>
    </el-upload>
    <div v-if="fileUrl" class="file-preview">
      <el-image
        v-if="isImage"
        :src="fileUrl"
        fit="cover"
        style="width: 100px; height: 100px"
        :preview-src-list="[fileUrl]"
      />
      <div v-else class="file-info">
        <el-icon><Document /></el-icon>
        <span>{{ fileName }}</span>
        <el-button
          type="danger"
          size="small"
          text
          @click="removeFile"
        >
          删除
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Upload, Document } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'

interface Props {
  type?: string
  disabled?: boolean
  buttonText?: string
}

interface Emits {
  (e: 'uploaded', fileUrl: string, fileName: string): void
  (e: 'removed'): void
}

const props = withDefaults(defineProps<Props>(), {
  type: 'general',
  disabled: false,
  buttonText: '上传文件'
})

const emit = defineEmits<Emits>()

const fileUrl = ref<string>('')
const fileName = ref<string>('')

const uploadUrl = computed(() => `/api/files/upload?type=${props.type}`)

const uploadHeaders = {
  // 可以添加认证头
}

const isImage = computed(() => {
  if (!fileUrl.value) return false
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
  return imageExtensions.some(ext => fileUrl.value.toLowerCase().endsWith(ext))
})

const beforeUpload = (file: File) => {
  const maxSize = 10 * 1024 * 1024 // 10MB
  if (file.size > maxSize) {
    ElMessage.error('文件大小不能超过10MB')
    return false
  }
  return true
}

const handleSuccess = (response: any) => {
  if (response.data && response.data.filePath) {
    fileUrl.value = `/api/files/download/${response.data.filePath}`
    fileName.value = response.data.originalFilename || '文件'
    emit('uploaded', fileUrl.value, fileName.value)
    ElMessage.success('上传成功')
  }
}

const handleError = () => {
  ElMessage.error('上传失败')
}

const removeFile = () => {
  fileUrl.value = ''
  fileName.value = ''
  emit('removed')
}
</script>

<style scoped>
.file-upload {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.file-preview {
  margin-top: 10px;
}

.file-info {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: var(--bg-input);
  border-radius: 4px;
}
</style>

