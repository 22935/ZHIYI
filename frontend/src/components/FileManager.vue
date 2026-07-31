<!-- 文件管理对话框 — 弹窗式文件管理，含上传、搜索和文件表格列表 -->
<template>
  <el-dialog
    v-model="visible"
    title="文件管理"
    width="800px"
    @close="handleClose"
  >
    <div class="file-manager">
      <!-- 工具栏 -->
      <div class="toolbar">
        <el-upload
          :action="uploadUrl"
          :headers="uploadHeaders"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :before-upload="beforeUpload"
          :show-file-list="false"
        >
          <el-button type="primary" :icon="Upload">上传文件</el-button>
        </el-upload>
        
        <el-input
          v-model="searchKeyword"
          placeholder="搜索文件"
          :prefix-icon="Search"
          style="width: 300px"
          clearable
          @input="handleSearch"
        />
      </div>

      <!-- 文件列表 -->
      <div class="file-list">
        <el-table
          :data="filteredFiles"
          style="width: 100%"
          v-loading="loading"
        >
          <el-table-column prop="name" label="文件名" min-width="200">
            <template #default="{ row }">
              <div class="file-name-cell">
                <el-icon class="file-icon">
                  <Document v-if="isDocument(row.type)" />
                  <Picture v-else-if="isImage(row.type)" />
                  <VideoPlay v-else-if="isVideo(row.type)" />
                  <Folder v-else />
                </el-icon>
                <span>{{ row.name }}</span>
              </div>
            </template>
          </el-table-column>
          
          <el-table-column prop="size" label="大小" width="120">
            <template #default="{ row }">
              {{ formatFileSize(row.size) }}
            </template>
          </el-table-column>
          
          <el-table-column prop="type" label="类型" width="100" />
          
          <el-table-column prop="uploadTime" label="上传时间" width="180">
            <template #default="{ row }">
              {{ formatTime(row.uploadTime) }}
            </template>
          </el-table-column>
          
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="{ row }">
              <el-button
                type="primary"
                size="small"
                text
                @click="handleDownload(row)"
              >
                下载
              </el-button>
              <el-button
                type="danger"
                size="small"
                text
                @click="handleDelete(row)"
              >
                删除
              </el-button>
            </template>
          </el-table-column>
        </el-table>
        
        <el-empty v-if="!loading && filteredFiles.length === 0" description="暂无文件" />
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { Upload, Search, Document, Picture, VideoPlay, Folder } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { fileApi, type FileInfo } from '@/services/api/file'
import axios from 'axios'

interface Props {
  modelValue: boolean
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'fileSelected', file: FileInfo): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const files = ref<FileInfo[]>([])
const loading = ref(false)
const searchKeyword = ref('')

const uploadUrl = computed(() => '/api/files/upload')
const uploadHeaders = {
  Authorization: `Bearer ${localStorage.getItem('token') || ''}`
}

const filteredFiles = computed(() => {
  if (!searchKeyword.value) return files.value
  
  const keyword = searchKeyword.value.toLowerCase()
  return files.value.filter(file =>
    file.name.toLowerCase().includes(keyword) ||
    file.type.toLowerCase().includes(keyword)
  )
})

const isDocument = (type: string) => {
  return ['application/pdf', 'application/msword', 'application/vnd.openxmlformats-officedocument'].some(t => type.includes(t))
}

const isImage = (type: string) => {
  return type.startsWith('image/')
}

const isVideo = (type: string) => {
  return type.startsWith('video/')
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

const formatTime = (time: string) => {
  const date = new Date(time)
  return date.toLocaleString('zh-CN')
}

const beforeUpload = (file: File) => {
  const maxSize = 10 * 1024 * 1024 // 10MB
  if (file.size > maxSize) {
    ElMessage.error('文件大小不能超过10MB')
    return false
  }
  return true
}

const handleUploadSuccess = (response: any) => {
  if (response.data && response.data.filePath) {
    ElMessage.success('文件上传成功')
    loadFiles()
  } else {
    ElMessage.error('文件上传失败')
  }
}

const handleUploadError = () => {
  ElMessage.error('文件上传失败')
}

const handleDownload = async (file: FileInfo) => {
  try {
    const blob = await fileApi.downloadFile(file.type, file.name)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.name
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
    ElMessage.success('文件下载成功')
  } catch (error: any) {
    ElMessage.error('文件下载失败: ' + (error.message || '未知错误'))
  }
}

const handleDelete = async (file: FileInfo) => {
  try {
    await ElMessageBox.confirm('确定要删除这个文件吗？', '确认删除', {
      type: 'warning'
    })
    
    await fileApi.deleteFile(file.type, file.name)
    ElMessage.success('文件删除成功')
    loadFiles()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('文件删除失败: ' + (error.message || '未知错误'))
    }
  }
}

const handleSearch = () => {
  // 搜索逻辑已在computed中实现
}

const loadFiles = async () => {
  try {
    loading.value = true
    // 注意：后端可能还没有实现文件列表接口，这里先使用空数组
    // 实际使用时需要后端提供文件列表接口
    files.value = await fileApi.getFileList().catch(() => [])
  } catch (error: any) {
    console.error('加载文件列表失败:', error)
    files.value = []
  } finally {
    loading.value = false
  }
}

const handleClose = () => {
  searchKeyword.value = ''
}

onMounted(() => {
  if (visible.value) {
    loadFiles()
  }
})

// 监听对话框打开
watch(() => props.modelValue, (val) => {
  if (val) {
    loadFiles()
  }
})
</script>

<style scoped lang="scss">
.file-manager {
  min-height: 400px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #e4e7ed;
}

.file-list {
  min-height: 300px;
}

.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  
  .file-icon {
    font-size: 18px;
    color: var(--primary-color);
  }
}

:deep(.el-dialog) {
  border-radius: var(--border-radius-large);
  box-shadow: var(--box-shadow-base);
  border: 1px solid var(--border-color-base);
}

:deep(.el-dialog__header) {
  background: var(--bg-color);
  border-bottom: 1px solid var(--border-color-light);
  padding: var(--spacing-lg) var(--spacing-xl);
  
  .el-dialog__title {
    font-size: var(--font-size-xl);
    font-weight: 700;
    color: var(--text-color-primary);
    letter-spacing: -0.01em;
  }
}

:deep(.el-dialog__body) {
  padding: 24px;
}
</style>

