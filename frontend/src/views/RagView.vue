<template>
  <div class="rag-view">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-inner">
        <div class="header-left">
          <div class="header-icon-wrapper">
            <el-icon class="header-icon"><Reading /></el-icon>
          </div>
          <div class="header-text">
            <h1 class="page-title">知识库</h1>
            <p class="page-subtitle">智能检索与文档管理</p>
          </div>
        </div>
        <div class="header-stats">
          <div class="stat-badge">
            <el-icon class="stat-icon"><Document /></el-icon>
            <span class="stat-value">{{ documents.length }}</span>
            <span class="stat-label">文档</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 主要内容区域 -->
    <div class="page-content">
      <div class="content-inner">
        <!-- 标签导航 -->
        <div class="tabs-nav">
          <button
            class="tab-button"
            :class="{ active: activeTab === 'query' }"
            @click="activeTab = 'query'"
          >
            <el-icon><Search /></el-icon>
            <span>知识检索</span>
          </button>
          <button
            class="tab-button"
            :class="{ active: activeTab === 'graph' }"
            @click="activeTab = 'graph'"
          >
            <el-icon><Share /></el-icon>
            <span>知识图谱</span>
          </button>
          <button
            class="tab-button"
            :class="{ active: activeTab === 'docs' }"
            @click="activeTab = 'docs'"
          >
            <el-icon><Document /></el-icon>
            <span>文档管理</span>
          </button>
        </div>
        
        <div class="layout-grid" v-if="activeTab === 'query'">
          <!-- 查询区域 -->
          <div class="query-section">
            <RagQuery @refresh="loadDocuments" />
          </div>
          
          <!-- 文档管理区域 -->
          <div class="docs-section">
            <div class="docs-card">
              <div class="card-header">
                <div class="header-title">
                  <el-icon class="title-icon"><Files /></el-icon>
                  <span class="title-text">文档管理</span>
                </div>
                <button class="upload-button" @click="showUploadDialog = true">
                  <el-icon><Upload /></el-icon>
                  <span>上传</span>
                </button>
              </div>
              
              <div class="docs-list">
                <div v-if="documents.length === 0" class="empty-docs">
                  <div class="empty-icon-wrapper">
                    <el-icon class="empty-icon"><Document /></el-icon>
                  </div>
                  <p class="empty-text">暂无文档</p>
                  <p class="empty-hint">上传文档以开始使用知识库</p>
                </div>
                
                <div v-else class="docs-items">
                  <div
                    v-for="doc in documents"
                    :key="doc.doc_id"
                    class="doc-item"
                  >
                    <div class="doc-icon-wrapper">
                      <el-icon class="doc-icon"><Document /></el-icon>
                    </div>
                    <div class="doc-info">
                      <div class="doc-name">{{ doc.filename }}</div>
                      <div class="doc-meta">
                        <span class="doc-time">{{ formatTime(doc.upload_time) }}</span>
                      </div>
                    </div>
                    <button class="doc-action" @click="handleDelete(doc.doc_id)" title="删除">
                      <el-icon><Delete /></el-icon>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        
        <!-- 知识图谱可视化区域 -->
        <div v-if="activeTab === 'graph'" class="graph-section">
          <KnowledgeGraphVisualization />
        </div>
        
        <!-- 文档管理独立区域 -->
        <div v-if="activeTab === 'docs'" class="docs-only-section">
          <div class="docs-card">
            <div class="card-header">
              <div class="header-title">
                <el-icon class="title-icon"><Files /></el-icon>
                <span class="title-text">文档管理</span>
              </div>
              <button class="upload-button" @click="showUploadDialog = true">
                <el-icon><Upload /></el-icon>
                <span>上传</span>
              </button>
            </div>
            
            <div class="docs-list">
              <div v-if="documents.length === 0" class="empty-docs">
                <div class="empty-icon-wrapper">
                  <el-icon class="empty-icon"><Document /></el-icon>
                </div>
                <p class="empty-text">暂无文档</p>
                <p class="empty-hint">上传文档以开始使用知识库</p>
              </div>
              
              <div v-else class="docs-items">
                <div
                  v-for="doc in documents"
                  :key="doc.doc_id"
                  class="doc-item"
                >
                  <div class="doc-icon-wrapper">
                    <el-icon class="doc-icon"><Document /></el-icon>
                  </div>
                  <div class="doc-info">
                    <div class="doc-name">{{ doc.filename }}</div>
                    <div class="doc-meta">
                      <span class="doc-time">{{ formatTime(doc.upload_time) }}</span>
                    </div>
                  </div>
                  <button class="doc-action" @click="handleDelete(doc.doc_id)" title="删除">
                    <el-icon><Delete /></el-icon>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 上传对话框 -->
    <el-dialog
      v-model="showUploadDialog"
      title="上传文档"
      width="520px"
      align-center
      class="upload-dialog"
    >
      <div class="upload-container">
        <el-upload
          class="upload-area"
          :http-request="handleUpload"
          :on-success="handleUploadSuccess"
          :on-error="handleUploadError"
          :before-upload="beforeUpload"
          drag
        >
          <div class="upload-content">
            <div class="upload-icon-wrapper">
              <el-icon class="upload-icon"><upload-filled /></el-icon>
            </div>
            <h3 class="upload-title">点击或拖拽上传</h3>
            <p class="upload-hint">支持 PDF, Word, TXT, MD 等格式</p>
          </div>
        </el-upload>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Reading, Document, Files, Upload, Delete, Search, Share } from '@element-plus/icons-vue'
import RagQuery from '@/components/RagQuery.vue'
import KnowledgeGraphVisualization from '@/components/KnowledgeGraphVisualization.vue'
import { ragApi } from '@/services/api/rag'
import { useRoleStore } from '@/stores/role'

const roleStore = useRoleStore()
const showUploadDialog = ref(false)
const activeTab = ref('query')
const documents = ref<Array<{
  doc_id: string
  filename: string
  upload_time: string
  role_id?: string
  metadata: any
}>>([])

const beforeUpload = (file: File) => {
  const maxSize = 10 * 1024 * 1024 // 10MB
  if (file.size > maxSize) {
    ElMessage.error('文件大小不能超过10MB')
    return false
  }
  
  // 如果有当前角色，提示用户文档将分类到该角色
  if (currentRoleId.value) {
    const roleName = roleStore.currentRole?.name || '当前角色'
    ElMessage.info(`文档将添加到"${roleName}"的知识库`)
  } else {
    ElMessage.warning('未选择角色，文档将添加到通用知识库')
  }
  
  return true
}

const handleUpload = async (options: any) => {
  try {
    await ragApi.uploadDocument(options.file, currentRoleId.value)
    handleUploadSuccess()
  } catch (error: any) {
    handleUploadError(error)
  }
}

const handleUploadSuccess = () => {
  ElMessage.success('文档上传成功')
  showUploadDialog.value = false
  loadDocuments()
}

const currentRoleId = computed(() => roleStore.currentRole?.id)

const handleUploadError = (error?: any) => {
  ElMessage.error('文档上传失败' + (error?.message ? `: ${error.message}` : ''))
}

const handleDelete = async (docId: string) => {
  try {
    await ragApi.deleteDocument(docId)
    ElMessage.success('文档删除成功')
    loadDocuments()
  } catch (error: any) {
    ElMessage.error('删除失败: ' + (error.message || '未知错误'))
  }
}

const loadDocuments = async () => {
  try {
    // 只加载当前角色的文档
    const response = await ragApi.listDocuments(currentRoleId.value)
    documents.value = response.documents || []
  } catch (error: any) {
    ElMessage.error('加载文档列表失败: ' + (error.message || '未知错误'))
  }
}

const formatTime = (timeStr: string) => {
  if (!timeStr) return ''
  try {
    const date = new Date(timeStr)
    // 只显示日期部分，节省空间
    return date.toLocaleDateString()
  } catch {
    return timeStr
  }
}

onMounted(() => {
  loadDocuments()
})
</script>

<style scoped lang="scss">
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

.rag-view {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #ffffff;
  display: flex;
  flex-direction: column;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* 页面头部 */
.page-header {
  background: #ffffff;
  border-bottom: 1px solid var(--border-light);
  padding: 32px 40px;
  position: sticky;
  top: 0;
  z-index: 10;
}

.header-inner {
  max-width: 1400px;
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 32px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 20px;
}

.header-icon-wrapper {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  background: var(--primary-color);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-icon {
  font-size: 28px;
  color: #ffffff;
}

.header-text {
  .page-title {
    margin: 0 0 6px 0;
    font-size: 28px;
    font-weight: 700;
    color: var(--text-primary);
    letter-spacing: -0.02em;
    line-height: 1.2;
  }
  
  .page-subtitle {
    margin: 0;
    font-size: 14px;
    color: var(--text-secondary);
    font-weight: 400;
    letter-spacing: 0.01em;
  }
}

.header-stats {
  display: flex;
  align-items: center;
}

.stat-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: 10px;
}

.stat-icon {
  font-size: 18px;
  color: var(--primary-color);
}

.stat-value {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.stat-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 400;
}

/* 主要内容区域 */
.page-content {
  flex: 1;
  overflow-y: auto;
  padding: 32px 40px;
}

.content-inner {
  max-width: 1400px;
  margin: 0 auto;
}

/* 标签导航 */
.tabs-nav {
  display: flex;
  gap: 8px;
  margin-bottom: 32px;
  border-bottom: 1px solid var(--border-light);
  padding-bottom: 0;
}

.tab-button {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 24px;
  border: none;
  background: transparent;
  font-size: 15px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.2s ease;
  font-family: inherit;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}

.tab-button:hover {
  color: var(--text-primary);
}

.tab-button.active {
  color: var(--primary-color);
  font-weight: 600;
  border-bottom-color: var(--primary-color);
}

.tab-button .el-icon {
  font-size: 18px;
}

.layout-grid {
  display: grid;
  grid-template-columns: 1fr 400px;
  gap: 32px;
}

.graph-section {
  min-height: 600px;
}

.docs-only-section {
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
}

.query-section {
  min-width: 0;
}

.docs-section {
  position: sticky;
  top: 100px;
  height: fit-content;
  max-height: calc(100vh - 200px);
}

.docs-card {
  background: #ffffff;
  border: 1px solid var(--border-light);
  border-radius: 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.card-header {
  padding: 20px 24px;
  border-bottom: 1px solid var(--border-light);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-icon {
  font-size: 20px;
  color: var(--primary-color);
}

.title-text {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.upload-button {
  height: 32px;
  padding: 0 14px;
  background: var(--primary-color);
  border: none;
  border-radius: 8px;
  color: #ffffff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.2s ease;
  font-family: inherit;
}

.upload-button:hover {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

.docs-list {
  padding: 16px;
  overflow-y: auto;
  max-height: 100%;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.1);
    border-radius: 3px;
  }
}

.empty-docs {
  padding: 60px 20px;
  text-align: center;
}

.empty-icon-wrapper {
  width: 64px;
  height: 64px;
  border-radius: 16px;
  background: var(--primary-fade);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 16px;
}

.empty-icon {
  font-size: 32px;
  color: var(--primary-color);
}

.empty-text {
  margin: 0 0 8px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.empty-hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 400;
}

.docs-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: #ffffff;
  transition: all 0.2s ease;
}

.doc-item:hover {
  background: var(--bg-input);
  border-color: var(--border-hover);
}

.doc-icon-wrapper {
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: var(--primary-fade);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.doc-icon {
  font-size: 18px;
  color: var(--primary-color);
}

.doc-info {
  flex: 1;
  min-width: 0;
}

.doc-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  letter-spacing: -0.01em;
}

.doc-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.doc-time {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 400;
}

.doc-action {
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.doc-action:hover {
  background: rgba(220, 38, 38, 0.1);
  color: var(--danger);
}

/* 上传对话框 */
.upload-container {
  padding: 8px 0;
}

.upload-area {
  :deep(.el-upload-dragger) {
    width: 100%;
    height: 240px;
    border: 2px dashed var(--border-light);
    border-radius: 12px;
    background: var(--bg-input);
    transition: all 0.2s ease;
  }
  
  :deep(.el-upload-dragger:hover) {
    border-color: var(--primary-color);
    background: var(--primary-fade);
  }
}

.upload-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
}

.upload-icon-wrapper {
  width: 64px;
  height: 64px;
  border-radius: 50%;
  background: var(--primary-fade);
  display: flex;
  align-items: center;
  justify-content: center;
}

.upload-icon {
  font-size: 32px;
  color: var(--primary-color);
}

.upload-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.upload-hint {
  margin: 0;
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 400;
}

/* 响应式设计 */
@media (max-width: 1024px) {
  .layout-grid {
    grid-template-columns: 1fr;
  }
  
  .docs-section {
    position: static;
    max-height: none;
  }
}

@media (max-width: 768px) {
  .page-header {
    padding: 24px 20px;
  }
  
  .header-inner {
    flex-direction: column;
    align-items: stretch;
    gap: 20px;
  }
  
  .header-left {
    gap: 16px;
  }
  
  .header-icon-wrapper {
    width: 48px;
    height: 48px;
  }
  
  .header-icon {
    font-size: 24px;
  }
  
  .page-title {
    font-size: 24px;
  }
  
  .page-content {
    padding: 24px 20px;
  }
  
  .layout-grid {
    gap: 24px;
  }
}
</style>
