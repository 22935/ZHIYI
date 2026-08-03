<!-- 知识库（RAG）页面 — 智能检索与文档管理，Tab 切换知识检索和知识图谱视图 -->
<template>
  <div class="rag-view">
    <!-- 页面头部 -->
    <div class="page-header workspace-page-header">
      <div class="header-inner">
        <div class="header-left">
          <div class="header-icon-wrapper workspace-page-header__icon">
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
import { resolveKnowledgeRoleId } from '@/utils/knowledgeRole'

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

const currentRoleId = computed(() => resolveKnowledgeRoleId(roleStore.currentRole))

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
.rag-view {
  min-height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: visible;
  background: transparent;
}

/* 页面头部 */
.page-header {
  flex-shrink: 0;
  background: var(--surface-solid);
  border-bottom: 1px solid var(--border-light);
  padding: var(--page-header-padding-y) var(--page-padding-x);
}

.header-inner {
  max-width: var(--page-content-max-width);
  margin: 0 auto;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-2xl);
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
  flex: 0 1 auto;
  min-height: auto;
  overflow: visible;
  padding: var(--page-padding-y) var(--page-padding-x);
}

.content-inner {
  max-width: var(--page-content-max-width);
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 0;
}

/* 标签导航 */
.tabs-nav {
  display: flex;
  gap: 8px;
  margin-bottom: var(--space-xl);
  border-bottom: 1px solid var(--border-light);
}

.tab-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: var(--space-md) var(--space-xl);
  border: none;
  background: transparent;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: inherit;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: color 0.18s ease, border-color 0.18s ease;
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
  font-size: 16px;
}

.layout-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 400px);
  gap: var(--section-gap);
  align-items: stretch;
  min-height: min(760px, calc(100vh - 210px));
}

.graph-section {
  min-height: min(760px, calc(100vh - 210px));
  display: flex;
  flex-direction: column;
}

.docs-only-section {
  max-width: var(--page-content-max-width);
  margin: 0 auto;
  width: 100%;
  min-height: min(680px, calc(100vh - 210px));
  display: flex;
  flex-direction: column;
}

.query-section {
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.docs-section {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.docs-card {
  background: var(--surface-solid);
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
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
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  max-height: clamp(320px, 58vh, 720px);
  scrollbar-gutter: stable;
  
  &::-webkit-scrollbar {
    width: 6px;
  }
  
  &::-webkit-scrollbar-thumb {
    background: rgba(0, 0, 0, 0.1);
    border-radius: 3px;
  }
}

.empty-docs {
  padding: var(--space-3xl) var(--space-xl);
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

.query-section :deep(.rag-query-container),
.query-section :deep(.query-card),
.graph-section :deep(.knowledge-graph-viz) {
  flex: 1 1 auto;
  min-height: 0;
}

.query-section :deep(.rag-query-container) {
  display: flex;
  flex-direction: column;
  height: auto;
}

.query-section :deep(.query-card),
.graph-section :deep(.knowledge-graph-viz) {
  border-radius: 8px;
}

.query-section :deep(.query-body) {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  scrollbar-gutter: stable;
}

.query-section :deep(.result-area) {
  max-height: clamp(280px, 42vh, 560px);
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.query-section :deep(.sources-list) {
  max-height: clamp(180px, 28vh, 360px);
  overflow-y: auto;
  padding-right: 4px;
  scrollbar-gutter: stable;
}

.graph-section :deep(.graph-container) {
  min-height: 520px;
}

.doc-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-light);
  background: var(--surface-solid);
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
    min-height: 0;
  }

  .docs-section {
    min-height: 0;
  }
}

@media (max-width: 768px) {
  .page-header {
    padding: var(--space-lg) var(--space-lg);
  }

  .header-inner {
    flex-direction: column;
    align-items: stretch;
    gap: var(--space-lg);
  }

  .header-left {
    gap: var(--space-md);
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
    padding: var(--space-xl) var(--space-lg);
  }

  .layout-grid {
    gap: var(--space-lg);
    min-height: 0;
  }
}

/* Workbench v0: align with the compact ACG workspace language. */
.rag-view {
  gap: 12px;
  padding: 12px;
  overflow: hidden;
}

.page-header {
  box-sizing: border-box;
  min-height: 50px;
  padding: 7px 12px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 80%, transparent);
  box-shadow: var(--shadow-sm);
  backdrop-filter: var(--backdrop-blur);
}

.header-inner,
.content-inner {
  width: 100%;
  max-width: none;
}

.header-left { gap: 10px; }
.header-icon-wrapper {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  color: var(--primary-color);
  background: var(--bg-card);
  border: 1px solid var(--border-light);
}
.header-icon { font-size: 15px; color: var(--primary-color); }
.header-text .page-title { margin: 0; font-size: 18px; font-weight: 700; line-height: 1.2; }
.header-text .page-subtitle { display: none; }
.stat-badge { height: 30px; padding: 0 10px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--surface-solid); }
.stat-value { font-size: 13px; }
.stat-label { font-size: 11px; }
.stat-icon { font-size: 14px; }

.page-content { flex: 1; min-height: 0; padding: 0; overflow: hidden; }
.content-inner { height: 100%; min-height: 0; }
.tabs-nav { flex: 0 0 38px; height: 38px; gap: 2px; margin: 0 0 8px; }
.tab-button { height: 38px; padding: 0 12px; gap: 6px; font-size: 12px; }
.tab-button .el-icon { font-size: 14px; }
.layout-grid {
  height: calc(100% - 46px);
  min-height: 0;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 320px);
  gap: 10px;
}
.docs-card { border-radius: 8px; box-shadow: none; }
.card-header { min-height: 42px; padding: 8px 10px; }
.title-icon { font-size: 15px; }
.title-text { font-size: 13px; }
.upload-button { height: 28px; padding: 0 10px; border-radius: 6px; font-size: 12px; }
.docs-list { padding: 8px; }
.empty-docs { padding: 48px 16px; }
.empty-icon-wrapper { width: 38px; height: 38px; margin-bottom: 10px; border-radius: 8px; }
.empty-icon { font-size: 19px; }
.empty-text { margin-bottom: 4px; font-size: 13px; }
.empty-hint { font-size: 11px; }
.doc-item { gap: 8px; padding: 8px; border-radius: 7px; }
.doc-icon-wrapper { width: 30px; height: 30px; border-radius: 6px; }
.doc-icon { font-size: 14px; }
.doc-name { margin-bottom: 2px; font-size: 12px; }
.doc-time { font-size: 10px; }
</style>
