<template>
  <div class="rag-query-container">
    <div class="query-card">
      <div class="card-header">
        <div class="header-left">
          <el-icon class="header-icon"><Search /></el-icon>
          <span class="header-title">智能检索</span>
        </div>
        <div class="header-settings">
          <span class="settings-label">Top K:</span>
          <el-input-number 
            v-model="topK" 
            :min="1" 
            :max="10" 
            size="small"
            controls-position="right"
            class="k-input"
          />
        </div>
      </div>
      
      <div class="query-body">
        <div class="input-area">
          <textarea
            v-model="queryText"
            placeholder="请输入您的问题，AI 将基于知识库为您解答..."
            class="query-textarea"
            @keydown.enter.prevent.ctrl="handleQuery"
            rows="4"
          ></textarea>
        </div>
        <div class="input-footer">
          <span class="hint-text">Ctrl + Enter 发送</span>
          <button
            class="submit-button"
            @click="handleQuery"
            :disabled="loading"
          >
            <el-icon v-if="!loading" class="submit-icon"><ArrowRight /></el-icon>
            <el-icon v-else class="submit-icon loading"><Loading /></el-icon>
            <span>查询</span>
          </button>
        </div>
      </div>

      <transition name="fade-slide">
        <div v-if="result" class="result-area">
          <div class="result-header">
            <div class="result-title-wrapper">
              <div class="title-indicator"></div>
              <span class="result-title">AI 回答</span>
            </div>
            <div class="confidence-badge" v-if="result.confidence">
              <span class="confidence-label">置信度</span>
              <div class="confidence-value">{{ Math.round(result.confidence * 100) }}%</div>
            </div>
          </div>
          
          <div class="answer-box">
            <div class="answer-content">{{ result.answer }}</div>
          </div>
          
          <div v-if="result.sources && result.sources.length > 0" class="sources-section">
            <div class="sources-header">
              <el-icon class="sources-icon"><Link /></el-icon>
              <span class="sources-title">参考来源</span>
            </div>
            <div class="sources-list">
              <div 
                v-for="(source, index) in result.sources" 
                :key="index"
                class="source-item"
              >
                <div class="source-number">{{ index + 1 }}</div>
                <div class="source-text">{{ source.title || source.url || '未知来源' }}</div>
              </div>
            </div>
          </div>
        </div>
      </transition>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Search, ArrowRight, Link, Loading } from '@element-plus/icons-vue'
import { ragApi } from '@/services/api/rag'
import { useRoleStore } from '@/stores/role'
import { resolveKnowledgeRoleId } from '@/utils/knowledgeRole'

const emit = defineEmits<{
  refresh: []
}>()

const queryText = ref('')
const topK = ref(5)
const loading = ref(false)
const result = ref<any>(null)


const roleStore = useRoleStore()
const currentRoleId = computed(() => resolveKnowledgeRoleId(roleStore.currentRole))

const handleQuery = async () => {
  if (!queryText.value.trim()) {
    ElMessage.warning('请输入查询内容')
    return
  }

  loading.value = true
  result.value = null // Clear previous result for animation
  
  try {
    // 传递当前角色ID，确保只查询该角色的知识库
    result.value = await ragApi.query(queryText.value, topK.value, undefined, currentRoleId.value)
    ElMessage.success('查询成功')
  } catch (error: any) {
    ElMessage.error('查询失败: ' + (error.message || '未知错误'))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped lang="scss">
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

.rag-query-container {
  height: 100%;
}

.query-card {
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

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.header-icon {
  font-size: 20px;
  color: var(--primary-color);
}

.header-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.header-settings {
  display: flex;
  align-items: center;
  gap: 8px;
}

.settings-label {
  font-size: 13px;
  color: var(--text-secondary);
  font-weight: 400;
}

.k-input {
  width: 100px;
}

.query-body {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.input-area {
  position: relative;
}

.query-textarea {
  width: 100%;
  min-height: 120px;
  padding: 16px;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--bg-input);
  font-size: 15px;
  font-family: inherit;
  color: var(--text-primary);
  line-height: 1.6;
  resize: none;
  outline: none;
  transition: all 0.2s ease;
}

.query-textarea:focus {
  background: #ffffff;
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-fade);
}

.query-textarea::placeholder {
  color: var(--text-disabled);
}

.input-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.hint-text {
  font-size: 12px;
  color: var(--text-disabled);
  font-weight: 400;
}

.submit-button {
  height: 36px;
  padding: 0 20px;
  background: var(--primary-color);
  border: none;
  border-radius: 10px;
  color: #ffffff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
  font-family: inherit;
}

.submit-button:hover:not(:disabled) {
  background: var(--primary-hover);
  transform: translateY(-1px);
}

.submit-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.submit-icon {
  font-size: 16px;
}

.submit-icon.loading {
  animation: rotate 1s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.result-area {
  margin-top: 32px;
  padding-top: 24px;
  border-top: 1px solid var(--border-light);
}

.result-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.result-title-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
}

.title-indicator {
  width: 3px;
  height: 18px;
  background: var(--primary-color);
  border-radius: 2px;
}

.result-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.confidence-badge {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: 8px;
}

.confidence-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 400;
}

.confidence-value {
  font-size: 13px;
  font-weight: 600;
  color: var(--primary-color);
  letter-spacing: -0.01em;
}

.answer-box {
  background: var(--bg-input);
  border-radius: 12px;
  padding: 20px;
  border: 1px solid var(--border-light);
  margin-bottom: 24px;
}

.answer-content {
  line-height: 1.8;
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 400;
  letter-spacing: 0.01em;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.sources-section {
  margin-top: 24px;
}

.sources-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.sources-icon {
  font-size: 16px;
  color: var(--primary-color);
}

.sources-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.01em;
}

.sources-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  transition: all 0.2s ease;
}

.source-item:hover {
  background: #ffffff;
  border-color: var(--border-hover);
}

.source-number {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: var(--primary-fade);
  color: var(--primary-color);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.source-text {
  flex: 1;
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.5;
  word-break: break-word;
  font-weight: 400;
}

/* 过渡动画 */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
}

.fade-slide-enter-from,
.fade-slide-leave-to {
  opacity: 0;
  transform: translateY(20px);
}
</style>





