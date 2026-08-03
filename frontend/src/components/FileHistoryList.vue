<!-- 文件历史列表组件 — 展示已上传文件列表，含类型图标、名称、大小、时间戳和下载/删除操作 -->
<template>
  <div class="file-history-list">
    <!-- 文件列表 -->
    <div v-if="!loading && filteredFiles.length > 0" class="list-content">
      <div
        v-for="file in filteredFiles"
        :key="file.id || file.name"
        class="file-item"
      >
        <div class="item-left">
          <div class="file-icon-wrapper">
            <el-icon class="file-icon"><Document /></el-icon>
          </div>
        </div>
        
        <div class="item-main">
          <div class="item-header">
            <span class="filename">{{ file.name }}</span>
            <span class="time">{{ formatTime(file.uploadTime || file.createdAt) }}</span>
          </div>
          <div class="item-meta">
            <span class="file-size">{{ formatFileSize(file.size) }}</span>
            <span class="file-type">{{ file.type }}</span>
          </div>
        </div>
        
        <div class="item-right">
          <button 
            class="action-btn download-btn" 
            @click.stop="handleDownload(file)"
            title="下载文件"
          >
            <el-icon><Download /></el-icon>
          </button>
          <button 
            class="action-btn delete-btn" 
            @click.stop="handleDelete(file)"
            title="删除文件"
          >
            <el-icon><Delete /></el-icon>
          </button>
        </div>
      </div>
    </div>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <div v-for="i in 3" :key="i" class="skeleton-item">
        <div class="skeleton-icon"></div>
        <div class="skeleton-content">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-text"></div>
        </div>
      </div>
    </div>
    
    <!-- 空状态 -->
    <div v-else-if="filteredFiles.length === 0" class="empty-state">
      <div class="empty-content">
        <div class="empty-icon">
          <el-icon><Document /></el-icon>
        </div>
        <p class="empty-text">暂无文件历史</p>
        <p class="empty-hint">上传的文件将显示在这里</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { Document, Delete, Download } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ragApi } from '@/services/api/rag'
import { fileApi } from '@/services/api/file'

interface Props {
  searchKeyword?: string
}

const props = withDefaults(defineProps<Props>(), {
  searchKeyword: ''
})

interface FileItem {
  id?: string
  name: string
  size: number
  type: string
  uploadTime?: string
  createdAt?: string
}

const files = ref<FileItem[]>([])
const loading = ref(false)

// 从RAG API获取文档列表（作为文件历史）
const loadFiles = async () => {
  try {
    loading.value = true
    const response = await ragApi.listDocuments()
    
    // 转换为文件列表格式
    files.value = (response.documents || []).map(doc => ({
      id: doc.doc_id,
      name: doc.filename,
      size: doc.metadata?.size || 0,
      type: getFileType(doc.filename),
      uploadTime: doc.upload_time,
      createdAt: doc.upload_time
    }))
  } catch (error: any) {
    ElMessage.error('加载文件列表失败: ' + (error.message || '未知错误'))
    files.value = []
  } finally {
    loading.value = false
  }
}

const getFileType = (filename: string) => {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  const typeMap: Record<string, string> = {
    'pdf': 'PDF文档',
    'doc': 'Word文档',
    'docx': 'Word文档',
    'txt': '文本文件',
    'md': 'Markdown',
    'xls': 'Excel表格',
    'xlsx': 'Excel表格',
    'ppt': 'PowerPoint',
    'pptx': 'PowerPoint'
  }
  return typeMap[ext] || '未知类型'
}

const filteredFiles = computed(() => {
  if (!props.searchKeyword) return files.value
  
  const keyword = props.searchKeyword.toLowerCase()
  return files.value.filter(file => 
    file.name.toLowerCase().includes(keyword) ||
    file.type.toLowerCase().includes(keyword)
  )
})

const formatTime = (timeStr?: string) => {
  if (!timeStr) return ''
  try {
    const date = new Date(timeStr)
    const now = new Date()
    const diff = now.getTime() - date.getTime()
    const days = Math.floor(diff / (1000 * 60 * 60 * 24))
    
    if (days === 0) {
      return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    } else if (days === 1) {
      return '昨天'
    } else if (days < 7) {
      return `${days}天前`
    } else {
      return date.toLocaleDateString('zh-CN')
    }
  } catch {
    return timeStr
  }
}

const formatFileSize = (bytes: number) => {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i]
}

const handleDelete = async (file: FileItem) => {
  if (!file.id) {
    ElMessage.warning('无法删除：文件ID不存在')
    return
  }
  
  try {
    await ElMessageBox.confirm(
      `确定要删除文件"${file.name}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await ragApi.deleteDocument(file.id)
    ElMessage.success('文件已删除')
    await loadFiles()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + (error.message || '未知错误'))
    }
  }
}

const handleDownload = async (file: FileItem) => {
  if (!file.id || !file.name) {
    ElMessage.warning('无法下载：文件信息不完整')
    return
  }
  
  try {
    // 尝试从RAG API下载文档
    const response = await fetch(`/api/rag/documents/${file.id}/download`)
    if (!response.ok) {
      throw new Error('下载失败')
    }
    
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = file.name
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    window.URL.revokeObjectURL(url)
    
    ElMessage.success('文件下载成功')
  } catch (error: any) {
    ElMessage.error('下载失败: ' + (error.message || '未知错误'))
  }
}

const handleRefresh = () => {
  loadFiles()
}

onMounted(() => {
  loadFiles()
  window.addEventListener('history-refresh', handleRefresh)
})

onUnmounted(() => {
  window.removeEventListener('history-refresh', handleRefresh)
})

// 监听搜索关键词变化（如果需要实时搜索）
watch(() => props.searchKeyword, () => {
  // 搜索是computed属性，会自动更新
})
</script>

<style scoped lang="scss">
.file-history-list {
  width: 100%;
  min-height: 400px;
}

.list-content {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  
  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

.file-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 16px;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  
  &:hover {
    background: color-mix(in srgb, var(--bg-card) 100%, transparent);
    transform: translateY(-2px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
    border-color: rgba(99, 102, 241, 0.2);
  }
}

.item-left {
  flex-shrink: 0;
  
  .file-icon-wrapper {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: linear-gradient(135deg, #6366f1, var(--accent-color));
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 20px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }
}

.item-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.item-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  
  .filename {
    font-size: 16px;
    font-weight: 600;
    color: var(--text-primary);
    line-height: 1.3;
    letter-spacing: -0.01em;
    flex: 1;
    min-width: 0;
    display: -webkit-box;
    -webkit-line-clamp: 1;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  
  .time {
    font-size: 12px;
    color: var(--text-secondary);
    flex-shrink: 0;
    font-weight: 400;
    white-space: nowrap;
  }
}

.item-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text-secondary);
  
  .file-size {
    font-weight: 500;
  }
  
  .file-type {
    padding: 2px 8px;
    background: rgba(99, 102, 241, 0.1);
    border-radius: 4px;
    color: var(--primary-color);
  }
}

.item-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  
  .action-btn {
    width: 32px;
    height: 32px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: transparent;
    border: none;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.2s ease;
    
    .el-icon {
      font-size: 16px;
    }
    
    &.download-btn:hover {
      background: rgba(99, 102, 241, 0.1);
      color: var(--primary-color);
    }
    
    &.delete-btn:hover {
      background: rgba(220, 38, 38, 0.1);
      color: #dc2626;
    }
  }
}

// 加载状态和空状态样式（复用ConversationList的样式）
.loading-state,
.empty-state {
  padding: 80px 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  
  .empty-content {
    text-align: center;
    
    .empty-icon {
      width: 80px;
      height: 80px;
      border-radius: 20px;
      background: rgba(99, 102, 241, 0.08);
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--primary-color);
      font-size: 40px;
      margin: 0 auto 20px;
    }
    
    .empty-text {
      margin: 0 0 8px;
      font-size: 18px;
      font-weight: 600;
      color: var(--text-primary);
      letter-spacing: -0.01em;
    }
    
    .empty-hint {
      margin: 0;
      font-size: 14px;
      color: var(--text-secondary);
      font-weight: 400;
    }
  }
}

.skeleton-item {
  display: flex;
  gap: 16px;
  padding: 20px;
  background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 16px;
  
  .skeleton-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
    background-size: 200% 100%;
    animation: skeleton-loading 1.5s ease-in-out infinite;
    flex-shrink: 0;
  }
  
  .skeleton-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 8px;
    
    .skeleton-line {
      height: 16px;
      border-radius: 4px;
      background: linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%);
      background-size: 200% 100%;
      animation: skeleton-loading 1.5s ease-in-out infinite;
    }
    
    .skeleton-title {
      width: 60%;
    }
    
    .skeleton-text {
      width: 85%;
    }
  }
}

@keyframes skeleton-loading {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

/* Compact history list aligned with the app workbench. */
.file-history-list { min-height: 0; }
.list-content { display: flex; flex-direction: column; gap: 0; }
.file-item {
  align-items: center;
  gap: 10px;
  min-height: 62px;
  padding: 9px 12px;
  border: 0;
  border-bottom: 1px solid var(--border-light);
  border-radius: 0;
  background: transparent;
  transition: background-color 160ms ease;
}
.file-item:last-child { border-bottom: 0; }
.file-item:hover { transform: none; box-shadow: none; border-color: var(--border-light); background: var(--primary-fade); }
.item-left .file-icon-wrapper {
  width: 32px;
  height: 32px;
  border: 1px solid var(--primary-line);
  border-radius: 7px;
  color: var(--primary-color);
  background: var(--bg-card);
  box-shadow: none;
}
.item-left .file-icon { font-size: 15px; }
.item-main { gap: 3px; }
.item-header .filename { font-size: 13px; }
.item-header .time { font-size: 10px; }
.item-meta { gap: 6px; font-size: 11px; }
.item-meta .file-type { padding: 1px 5px; border-radius: 4px; background: var(--primary-fade); }
.item-right { gap: 2px; opacity: 1; transform: none; }
.item-right .action-btn { width: 26px; height: 26px; border-radius: 5px; color: var(--text-disabled); }
.loading-state { display: flex; flex-direction: column; gap: 0; }
.skeleton-item { padding: 9px 12px; border: 0; border-bottom: 1px solid var(--border-light); border-radius: 0; }
.empty-state { padding: 64px 20px; }
.empty-state .empty-content .empty-icon { width: 40px; height: 40px; margin-bottom: 10px; border-radius: 8px; font-size: 20px; background: var(--primary-fade); }
</style>

