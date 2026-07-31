<!-- 历史记录页面 — 查看、搜索、刷新和清空对话与文件历史 -->
<template>
  <div class="history-view">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-inner">
        <div class="header-left">
          <div class="header-icon-wrapper">
            <el-icon class="header-icon"><Clock /></el-icon>
          </div>
          <div class="header-text">
            <h1 class="page-title">历史记录</h1>
            <p class="page-subtitle">查看和管理您的对话与文件历史</p>
          </div>
        </div>
        
        <div class="header-actions">
          <div class="search-box">
            <el-icon class="search-icon"><Search /></el-icon>
            <input
              v-model="searchKeyword"
              type="text"
              placeholder="搜索历史记录..."
              class="search-input"
            />
          </div>
          <button class="action-button" @click="refresh" title="刷新">
            <el-icon><Refresh /></el-icon>
            <span>刷新</span>
          </button>
          <button class="action-button danger" @click="clearAll">
            <el-icon><Delete /></el-icon>
            <span>清空全部</span>
          </button>
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
            :class="{ active: activeTab === 'conversations' }"
            @click="activeTab = 'conversations'"
          >
            <el-icon><ChatLineRound /></el-icon>
            <span>对话历史</span>
          </button>
          <button
            class="tab-button"
            :class="{ active: activeTab === 'files' }"
            @click="activeTab = 'files'"
          >
            <el-icon><Document /></el-icon>
            <span>文件历史</span>
          </button>
        </div>

        <!-- 内容区域 -->
        <div class="content-section">
          <ConversationList
            v-if="activeTab === 'conversations'"
            :key="`conversations-${refreshKey}`"
            :search-keyword="searchKeyword"
            :user-id="userStore.currentUser?.id"
            @select="handleSelectConversation"
          />
          
          <div v-else class="files-content">
            <FileHistoryList 
              :key="`files-${refreshKey}`"
              :search-keyword="searchKeyword" 
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { Search, Delete, Clock, ChatLineRound, Document, Refresh } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ConversationList from '@/components/ConversationList.vue'
import FileHistoryList from '@/components/FileHistoryList.vue'
import { conversationApi } from '@/services/api/conversation'
import { useUserStore } from '@/stores/user'

const router = useRouter()
const userStore = useUserStore()
const searchKeyword = ref('')
const activeTab = ref('conversations')
const refreshKey = ref(0)

const handleSelectConversation = (conversation: { id: string; contextId?: string }) => {
  const contextId = conversation.contextId || conversation.id
  router.push(`/chat?contextId=${encodeURIComponent(contextId)}`)
}

// 刷新当前标签页的数据
const refresh = () => {
  refreshKey.value++
  ElMessage.success('已刷新')
}

const clearAll = async () => {
  try {
    await ElMessageBox.confirm('确定要清空所有历史记录吗？此操作不可恢复。', '确认清空', {
      confirmButtonText: '确定清空',
      cancelButtonText: '取消',
      type: 'warning'
    })
    
    const userId = userStore.currentUser?.id
    if (!userId) {
      ElMessage.error('无法获取用户信息')
      return
    }
    
    await conversationApi.deleteAllConversations(userId)
    ElMessage.success('历史记录已清空')
    refresh()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('清空失败: ' + (error.message || '未知错误'))
    }
  }
}
</script>

<style scoped lang="scss">
.history-view {
  height: 100%;
  width: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
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
  flex-wrap: wrap;
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

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.search-box {
  position: relative;
  display: flex;
  align-items: center;
  width: 320px;
  height: 40px;
  background: var(--bg-input);
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 0 14px;
  transition: all 0.2s ease;
}

.search-box:focus-within {
  background: var(--surface-solid);
  border-color: var(--primary-color);
  box-shadow: 0 0 0 3px var(--primary-fade);
}

.search-icon {
  font-size: 18px;
  color: var(--text-secondary);
  margin-right: 10px;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 14px;
  font-family: inherit;
  color: var(--text-primary);
}

.search-input::placeholder {
  color: var(--text-disabled);
}

.action-button {
  height: 40px;
  padding: 0 20px;
  border: 1px solid var(--border-light);
  background: var(--surface-solid);
  border-radius: 10px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 8px;
  transition: all 0.2s ease;
  font-family: inherit;
}

.action-button:hover {
  background: var(--bg-input);
  border-color: var(--border-hover);
}

.action-button.danger {
  color: var(--danger);
  border-color: rgba(220, 38, 38, 0.2);
}

.action-button.danger:hover {
  background: rgba(220, 38, 38, 0.05);
  border-color: var(--danger);
}

/* 主要内容区域 */
.page-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--page-padding-y) var(--page-padding-x);
}

.content-inner {
  max-width: var(--page-content-max-width);
  margin: 0 auto;
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
  font-size: 18px;
}

/* 内容区域 */
.content-section {
  min-height: 0;
}

.files-content {
  padding: var(--space-2xl) 0;
}

/* 响应式设计 */
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

  .search-box {
    width: 100%;
  }

  .action-button {
    width: 100%;
    justify-content: center;
  }

  .page-content {
    padding: var(--space-xl) var(--space-lg);
  }

  .tabs-nav {
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;

    &::-webkit-scrollbar {
      display: none;
    }
  }

  .tab-button {
    white-space: nowrap;
    padding: 10px 16px;
  }
}
</style>
