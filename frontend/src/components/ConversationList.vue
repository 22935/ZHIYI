<!-- 对话列表组件 — 可滚动对话列表，含头像、标题、预览、时间戳和编辑/删除操作 -->
<template>
  <div class="conversation-list-container">
    <!-- 对话列表 -->
    <div v-if="!loading && filteredConversations.length > 0" class="list-content">
      <div
        v-for="conversation in filteredConversations"
        :key="conversation.id"
        class="conversation-item"
        @click="$emit('select', conversation)"
      >
        <div class="item-left">
          <div class="avatar-wrapper">
            <el-icon v-if="!conversation.avatar"><User /></el-icon>
            <span v-else class="avatar-text">{{ conversation.title?.charAt(0) || 'C' }}</span>
          </div>
        </div>
        
        <div class="item-main">
          <div class="item-header">
            <span class="title">{{ conversation.title || '未命名对话' }}</span>
            <span class="time">{{ formatTime(conversation.updatedAt) }}</span>
          </div>
          <div class="item-preview">
            {{ conversation.preview || '暂无预览内容...' }}
          </div>
        </div>
        
        <div class="item-right">
          <div class="action-buttons">
            <button 
              class="action-btn edit-btn" 
              @click.stop="handleEdit(conversation)"
              title="编辑标题"
            >
              <el-icon><Edit /></el-icon>
            </button>
            <button 
              class="action-btn delete-btn" 
              @click.stop="handleDelete(conversation)"
              title="删除对话"
            >
              <el-icon><Delete /></el-icon>
            </button>
            <div class="action-btn">
              <el-icon><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>
    </div>
    
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <div v-for="i in 3" :key="i" class="skeleton-item">
        <div class="skeleton-avatar"></div>
        <div class="skeleton-content">
          <div class="skeleton-line skeleton-title"></div>
          <div class="skeleton-line skeleton-text"></div>
        </div>
      </div>
    </div>
    
    <!-- 空状态 -->
    <div v-else-if="filteredConversations.length === 0" class="empty-state">
      <div class="empty-content">
        <div class="empty-icon">
          <el-icon><ChatLineRound /></el-icon>
        </div>
        <p class="empty-text">{{ props.workspaceMode === 'agent' ? '暂无 Agent 历史' : '暂无 Chat 历史' }}</p>
        <p class="empty-hint">
          {{ props.workspaceMode === 'agent' ? '开始新的 Agent 任务后，记录将显示在这里' : '开始新的对话后，记录将显示在这里' }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { User, ArrowRight, ChatLineRound, Edit, Delete } from '@element-plus/icons-vue'
import { conversationApi } from '@/services/api/conversation'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { getConversationWorkspace } from '@/utils/conversationWorkspace'

interface Conversation {
  id: string
  contextId: string
  title?: string
  preview?: string
  avatar?: string
  workspaceMode?: 'agent' | 'chat'
  updatedAt: number | Date
}

interface Props {
  searchKeyword?: string
  userId?: string
  workspaceMode?: 'agent' | 'chat'
}

const props = withDefaults(defineProps<Props>(), {
  searchKeyword: '',
  userId: '',
  workspaceMode: 'chat'
})

const userStore = useUserStore()

defineEmits<{
  select: [conversation: Conversation]
}>()

const conversations = ref<Conversation[]>([])
const loading = ref(false)

// 从API获取对话列表
const loadConversations = async () => {
  // 优先使用props中的userId，否则从userStore获取
  const userId = props.userId || userStore.currentUser?.id
  
  if (!userId) {
    conversations.value = []
    return
  }

  if (loading.value) {
    return
  }

  try {
    loading.value = true
    const apiConversations = await conversationApi.getUserConversations(userId, props.workspaceMode)
    
    // 转换为组件需要的格式，预览内容由列表接口直接返回，避免逐条请求详情触发限流。
    const conversationsWithPreview = apiConversations.map((conv) => {
      const resolvedContextId = conv.contextId || conv.id

      return {
        id: conv.id,
        contextId: resolvedContextId,
        title: conv.title || `对话 ${resolvedContextId.substring(0, 8)}`,
        preview: conv.preview || `上下文ID: ${resolvedContextId}`,
        avatar: undefined,
        workspaceMode: conv.workspaceMode,
        updatedAt: new Date(conv.updatedAt || conv.createdAt)
      }
    })
    
    conversations.value = conversationsWithPreview
  } catch (error: any) {
    ElMessage.error('加载对话列表失败: ' + (error.message || '未知错误'))
    conversations.value = []
  } finally {
    loading.value = false
  }
}

// 编辑标题
const handleEdit = async (conv: Conversation) => {
  try {
    const { value: newTitle } = await ElMessageBox.prompt(
      '请输入新的对话标题',
      '编辑标题',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputValue: conv.title || '',
        inputValidator: (value) => {
          if (!value || value.trim().length === 0) {
            return '标题不能为空'
          }
          if (value.length > 50) {
            return '标题不能超过50个字符'
          }
          return true
        }
      }
    )
    
    if (newTitle && newTitle.trim()) {
      await conversationApi.updateTitle(conv.id, newTitle.trim())
      ElMessage.success('标题更新成功')
      await loadConversations()
    }
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('更新标题失败: ' + (error.message || '未知错误'))
    }
  }
}

// 删除对话
const handleDelete = async (conv: Conversation) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除对话"${conv.title || '未命名对话'}"吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '确定删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await conversationApi.deleteConversation(conv.id)
    ElMessage.success('对话已删除')
    await loadConversations()
  } catch (error: any) {
    if (error !== 'cancel') {
      ElMessage.error('删除失败: ' + (error.message || '未知错误'))
    }
  }
}

const handleRefresh = () => {
  loadConversations()
}

onMounted(async () => {
  // 如果userStore中没有用户信息，先加载
  if (!userStore.currentUser) {
    await userStore.loadCurrentUser()
  }
  loadConversations()
  
  // 监听刷新事件
  window.addEventListener('history-refresh', handleRefresh)
})

onUnmounted(() => {
  window.removeEventListener('history-refresh', handleRefresh)
})

// 监听userId变化
watch(() => props.userId, () => {
  loadConversations()
})

// 监听userStore中的用户变化
watch(() => userStore.currentUser, () => {
  loadConversations()
})

const filteredConversations = computed(() => {
  const workspaceConversations = conversations.value.filter(conversation =>
    (conversation.workspaceMode || getConversationWorkspace(conversation.contextId)) === props.workspaceMode
  )
  if (!props.searchKeyword) return workspaceConversations
  
  const keyword = props.searchKeyword.toLowerCase()
  return workspaceConversations.filter(conv =>
    conv.title?.toLowerCase().includes(keyword) ||
    conv.preview?.toLowerCase().includes(keyword)
  )
})

const formatTime = (time: number | Date) => {
  const date = time instanceof Date ? time : new Date(time)
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
}
</script>

<style scoped lang="scss">
// 变量定义 - 现代优雅的设计系统
$primary-color: var(--primary-color);
$primary-light: rgba(99, 102, 241, 0.08);
$border-color: rgba(0, 0, 0, 0.08);
$border-light: rgba(0, 0, 0, 0.05);
$shadow-subtle: 0 2px 8px rgba(0, 0, 0, 0.04);
$shadow-hover: 0 4px 16px rgba(0, 0, 0, 0.06);

.conversation-list-container {
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

.conversation-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 20px;
  background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  border: 1px solid $border-color;
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  position: relative;
  overflow: hidden;
  
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: $primary-color;
    transform: scaleY(0);
    transition: transform 0.25s;
  }
  
  &:hover {
    background: color-mix(in srgb, var(--bg-card) 100%, transparent);
    transform: translateY(-2px);
    box-shadow: $shadow-hover;
    border-color: rgba(99, 102, 241, 0.2);
    
    &::before {
      transform: scaleY(1);
    }
    
    .action-btn {
      opacity: 1;
      transform: translateX(0);
      background: $primary-light;
      color: $primary-color;
    }
  }
}

.item-left {
  flex-shrink: 0;
  
  .avatar-wrapper {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-size: 20px;
    font-weight: 600;
    box-shadow: $shadow-subtle;
    flex-shrink: 0;
    
    .avatar-text {
      font-size: 18px;
      font-weight: 600;
      letter-spacing: -0.01em;
    }
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
  
  .title {
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

.item-preview {
  font-size: 13px;
  color: var(--text-regular);
  line-height: 1.5;
  font-weight: 400;
  letter-spacing: 0.01em;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.item-right {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  
  .action-buttons {
    display: flex;
    align-items: center;
    gap: 4px;
    opacity: 0;
    transform: translateX(10px);
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  }
  
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
    
    &.edit-btn:hover {
      background: rgba(99, 102, 241, 0.1);
      color: var(--primary-color);
    }
    
    &.delete-btn:hover {
      background: rgba(220, 38, 38, 0.1);
      color: #dc2626;
    }
  }
}

.conversation-item:hover .item-right .action-buttons {
  opacity: 1;
  transform: translateX(0);
}

// 加载状态
.loading-state {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
  
  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
}

.skeleton-item {
  display: flex;
  gap: 16px;
  padding: 20px;
  background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  border: 1px solid $border-color;
  border-radius: 16px;
  
  .skeleton-avatar {
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
.conversation-list-container { min-height: 0; }
.list-content { display: flex; flex-direction: column; gap: 0; }
.conversation-item {
  align-items: center;
  gap: 10px;
  min-height: 62px;
  padding: 9px 12px;
  border: 0;
  border-bottom: 1px solid var(--border-light);
  border-radius: 0;
  background: transparent;
  overflow: visible;
  transition: background-color 160ms ease;
}
.conversation-item::before { display: none; }
.conversation-item:last-child { border-bottom: 0; }
.conversation-item:hover { transform: none; box-shadow: none; border-color: var(--border-light); background: var(--primary-fade); }
.item-left .avatar-wrapper {
  width: 32px;
  height: 32px;
  border: 1px solid var(--primary-line);
  border-radius: 7px;
  color: var(--primary-color);
  background: var(--bg-card);
  box-shadow: none;
  font-size: 15px;
}
.item-main { gap: 3px; }
.item-header { align-items: center; }
.item-header .title { font-size: 13px; line-height: 1.3; }
.item-header .time { font-size: 10px; }
.item-preview { max-width: 760px; font-size: 11px; line-height: 1.4; -webkit-line-clamp: 1; }
.item-right .action-buttons { gap: 2px; opacity: 1; transform: none; }
.item-right .action-btn { width: 26px; height: 26px; border-radius: 5px; color: var(--text-disabled); }
.item-right .action-btn .el-icon { font-size: 13px; }
.loading-state { display: flex; flex-direction: column; gap: 0; }
.skeleton-item { padding: 9px 12px; border: 0; border-bottom: 1px solid var(--border-light); border-radius: 0; }
.empty-state { padding: 64px 20px; }
.empty-state .empty-content .empty-icon { width: 40px; height: 40px; margin-bottom: 10px; border-radius: 8px; font-size: 20px; background: var(--primary-fade); }
.empty-state .empty-content .empty-text { margin-bottom: 4px; font-size: 13px; }
.empty-state .empty-content .empty-hint { font-size: 11px; }

// 空状态
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
      color: $primary-color;
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
</style>
