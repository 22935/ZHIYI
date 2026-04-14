<template>
  <div class="chat-view-container">
    <!-- Background Elements for Atmosphere -->
    <div class="ambient-glow top-left"></div>
    <div class="ambient-glow bottom-right"></div>

    <!-- Main Chat Content -->
    <main class="chat-stage">
      <div class="top-zone">

      <!-- Top Right: Header Actions (Role & Settings) -->
      <div class="header-actions">
        <el-tooltip :content="t('role.title')" placement="bottom" effect="light">
          <div class="action-btn glass-btn" @click="showRoleDrawer = true">
             <el-avatar :size="32" :src="currentRole?.avatar" class="current-role-avatar">
               {{ currentRole?.name?.charAt(0) }}
             </el-avatar>
             <span class="role-name-label">{{ currentRole?.name || t('role.title') }}</span>
             <el-icon class="icon-right"><ArrowDown /></el-icon>
          </div>
        </el-tooltip>
        
        <el-tooltip :content="t('settings.title')" placement="bottom" effect="light">
          <div class="action-btn glass-btn icon-only" @click="goToSettings">
             <el-icon><MoreFilled /></el-icon>
          </div>
        </el-tooltip>
      </div>

      <section class="agent-spotlight glass-panel" :class="{ 'is-active': isLawyerMode }">
        <div class="agent-spotlight-main">
          <div class="agent-kicker">AGENT WORKSPACE</div>
          <h2 class="agent-title">律师 Agent 工作台</h2>
          <p class="agent-subtitle">
            ReAct 自主规划 + 五项法律技能，支持案情理解、法条检索、判例检索、文书生成和风险评估。
          </p>
          <div class="agent-skill-chips">
            <span>案情理解</span>
            <span>法条检索</span>
            <span>判例检索</span>
            <span>文书生成</span>
            <span>风险评估</span>
          </div>
        </div>
        <div class="agent-spotlight-actions">
          <el-tag :type="isLawyerMode ? 'success' : 'info'" effect="dark">
            {{ isLawyerMode ? '律师 Agent 已启用' : '当前为普通对话模式' }}
          </el-tag>
          <el-button type="primary" @click="activateLawyerAgent">
            {{ isLawyerMode ? '保持律师 Agent 模式' : '一键切换律师 Agent' }}
          </el-button>
          <el-button plain @click="showRoleDrawer = true">角色选择</el-button>
          <div class="agent-runtime-hint">
            本轮已记录 {{ latestLawyerMeta.trace.length }} 条执行轨迹
          </div>
        </div>
      </section>
      </div>

      <div class="chat-body" :class="{ 'with-lawyer-panel': isLawyerMode }">
        <!-- Chat Messages Scroll Area -->
        <div class="messages-container" ref="messagesRef">
          <div v-if="chatStore.messages.length === 0" class="empty-state">
             <div class="hero-content">
               <!-- 动态Logo和欢迎动画 -->
               <div class="logo-mark-container">
                 <div class="logo-mark animated-logo">
                   <span class="logo-icon">🌐</span>
                   <span class="logo-text">联邦智能枢</span>
                 </div>
                 <div class="logo-pulse"></div>
               </div>
               
               <!-- 动态欢迎文本 -->
               <div class="welcome-section">
                 <h1 class="welcome-text">{{ $t('chat.noMessages') }}</h1>
                 <p class="subtitle">{{ $t('chat.newChat') }}</p>
                 
                 <!-- 快速启动按钮组 -->
                 <div class="quick-start-grid">
                   <div class="quick-action-card" @click="useTemplate('请帮我分析这个法律案件的关键风险点')">
                     <div class="action-icon">⚖️</div>
                     <div class="action-text">法律咨询</div>
                     <div class="action-hint">分析案件风险</div>
                   </div>
                   
                   <div class="quick-action-card" @click="useTemplate('请帮我撰写一份商业合同草案')">
                     <div class="action-icon">📝</div>
                     <div class="action-text">文书起草</div>
                     <div class="action-hint">生成专业文档</div>
                   </div>
                   
                   <div class="quick-action-card" @click="useTemplate('请帮我检索相关法律条文')">
                     <div class="action-icon">🔍</div>
                     <div class="action-text">法条检索</div>
                     <div class="action-hint">查找相关法规</div>
                   </div>
                   
                   <div class="quick-action-card" @click="useTemplate('请帮我评估这个商业决策的法律风险')">
                     <div class="action-icon">📊</div>
                     <div class="action-text">风险评估</div>
                     <div class="action-hint">分析潜在风险</div>
                   </div>
                 </div>
               </div>
               
               <!-- 主要操作按钮 -->
               <div class="empty-actions">
                 <button
                   type="button"
                   class="empty-action-btn primary"
                   @click="useTemplate(currentTemplates[0] || '请帮我梳理这个案件的关键法律风险')"
                 >
                   <el-icon><ChatDotRound /></el-icon>
                   开始智能对话
                 </button>
                 <button type="button" class="empty-action-btn secondary" @click="showRoleDrawer = true">
                   <el-icon><User /></el-icon>
                   选择专业角色
                 </button>
                 <button type="button" class="empty-action-btn ghost" @click="toggleLawyerMode">
                   <el-icon><Scale /></el-icon>
                   {{ isLawyerMode ? '退出律师模式' : '进入律师工作台' }}
                 </button>
               </div>
               
               <!-- 功能提示 -->
               <div class="feature-hints">
                 <div class="hint-item">
                   <el-icon><Check /></el-icon>
                   <span>支持多轮对话和上下文记忆</span>
                 </div>
                 <div class="hint-item">
                   <el-icon><Check /></el-icon>
                   <span>提供专业法律分析和建议</span>
                 </div>
                 <div class="hint-item">
                   <el-icon><Check /></el-icon>
                   <span>支持文件上传和文档处理</span>
                 </div>
               </div>
             </div>
          </div>

          <div v-else class="message-list">
            <div 
              v-for="msg in chatStore.messages" 
              :key="msg.id" 
              class="message-row"
              :class="msg.role"
            >
               <div class="message-content-wrapper">
                  <MessageBubble 
                    :message="{
                      id: msg.id,
                      role: msg.role,
                      content: msg.content || '',
                      createdAt: msg.createdAt || (msg.timestamp ? new Date(msg.timestamp) : new Date()),
                      confidence: msg.confidence,
                      fileUrl: msg.fileUrl,
                      tokensUsed: msg.tokensUsed,
                      sources: msg.sources,
                      reasoningPath: msg.reasoningPath,
                      modelInfo: msg.modelInfo
                    }"
                  />
               </div>
            </div>
          </div>

          <div v-if="loading" class="typing-row">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-text">AI is thinking...</span>
          </div>
        </div>

        <button
          v-if="showScrollToBottom"
          class="jump-bottom-btn"
          type="button"
          title="回到底部"
          @click="handleScrollToBottom"
        >
          <el-icon><ArrowDownBold /></el-icon>
          <span v-if="pendingMessageCount > 0" class="jump-bottom-badge">
            {{ pendingMessageCount > 9 ? '9+' : pendingMessageCount }}
          </span>
        </button>

        <aside v-if="isLawyerMode" class="lawyer-panel-wrap">
          <LawyerSkillPanel
            :skills-used="latestLawyerMeta.skillsUsed"
            :trace="latestLawyerMeta.trace"
            :federated="latestLawyerMeta.federated"
            :risk-level="latestLawyerMeta.riskLevel"
          />
        </aside>
      </div>

      <!-- Bottom: Input Area (Floating) -->
      <div class="input-dock-wrapper">
        <div class="assist-toolbar">
          <button type="button" class="assist-toggle-btn" @click="toggleAssistTools">
            {{ showAssistTools ? '收起快捷操作' : '展开快捷操作' }}
          </button>
          <span class="assist-tip">Enter 发送，Shift/Ctrl + Enter 换行</span>
        </div>

        <!-- Quick Reply Templates -->
        <div v-if="showAssistTools && currentTemplates.length > 0" class="templates-container">
          <div 
            v-for="template in currentTemplates" 
            :key="template"
            class="template-tag"
            @click="useTemplate(template)"
          >
            {{ template }}
          </div>
        </div>

        <!-- Recommendations -->
        <div v-if="showAssistTools && recommendations.length > 0" class="recommendations-container">
          <div class="recommendations-label">💡 推荐问题</div>
          <div class="recommendations-tags">
            <div 
              v-for="rec in recommendations" 
              :key="rec"
              class="recommendation-tag"
              @click="useRecommendation(rec)"
            >
              {{ rec }}
            </div>
          </div>
        </div>

        <div class="input-dock glass-panel">
          <!-- Textarea -->
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 6 }"
            resize="none"
            :placeholder="$t('chat.placeholder')"
            class="dock-input"
            @keydown="handleKeydown"
          />

          <!-- Dock Footer -->
          <div class="dock-footer">
             <div class="footer-left">
                <el-popover
                  placement="top-start"
                  :width="200"
                  trigger="click"
                  popper-class="tools-popover"
                >
                  <template #reference>
                    <div class="plus-trigger">
                      <el-icon><CirclePlus /></el-icon>
                    </div>
                  </template>
                  <div class="tools-grid">
                    <div class="tool-item" @click="isRecording ? stopVoiceInput() : startVoiceInput()">
                      <el-icon :class="{ 'is-recording': isRecording }"><Microphone /></el-icon>
                      <span>{{ isRecording ? $t('voice.stopRecording') : $t('voice.startRecording') }}</span>
                    </div>
                    <div class="tool-item" @click="handleControl('folder')">
                      <el-icon><Folder /></el-icon>
                      <span>{{ $t('rag.upload') }}</span>
                    </div>
                    <div class="tool-item" @click="handleControl('image')">
                      <el-icon><Picture /></el-icon>
                      <span>{{ $t('common.search') }}</span>
                    </div>
                  </div>
                </el-popover>
                
                <div class="word-count" :class="{ 'warning': inputText.length > 500 }">
                  {{ $t('chat.wordCount', { count: inputText.length }) }}
                  <span v-if="inputText.length > 500" class="hint"> ({{ $t('chat.wordCountHint') }})</span>
                  <el-button 
                    v-if="inputText.length > 500" 
                    link 
                    type="primary" 
                    size="small" 
                    @click="autoSegment"
                    class="segment-btn"
                  >
                    自动分段
                  </el-button>
                </div>
             </div>

             <div class="footer-right">
                <div class="emotion-pill">
                  <span class="label">Emotion</span>
                  <input v-model="emotionTag" placeholder="Auto" class="transparent-input" />
                </div>
                <button class="send-trigger" @click="sendMessage" :disabled="isSendDisabled">
                   <el-icon v-if="!loading"><ArrowUp /></el-icon>
                   <el-icon v-else class="is-loading"><Loading /></el-icon>
                </button>
             </div>
          </div>
        </div>
      </div>
    </main>

    <!-- Role Selection Drawer (Minimalist) -->
    <el-drawer
      v-model="showRoleDrawer"
      direction="rtl"
      :size="320"
      :with-header="false"
      class="role-drawer"
    >
      <div class="drawer-content">
         <div class="drawer-header">
           <h2>Choose a Persona</h2>
           <el-button circle text @click="showRoleDrawer = false"><el-icon><Close /></el-icon></el-button>
         </div>
         
         <div class="role-grid">
            <div 
              v-for="role in roles" 
              :key="role.id"
              class="role-card-minimal"
              :class="{ 'active': roleStore.currentRole?.id === role.id || selectedRoleId === role.id }"
              @click="selectRole(role)"
            >
               <el-avatar :size="48" :src="role.avatar" class="role-avatar-lg">
                  {{ role.name.charAt(0) }}
               </el-avatar>
               <div class="role-info">
                  <div class="name">{{ role.name }}</div>
                  <div class="desc">{{ role.description || 'AI Assistant' }}</div>
               </div>
               <div class="check-mark" v-if="roleStore.currentRole?.id === role.id || selectedRoleId === role.id">
                 <el-icon><Check /></el-icon>
               </div>
            </div>
         </div>
      </div>
    </el-drawer>

    <!-- File Manager Modal -->
    <FileManager
      v-model="showFileManager"
      @fileSelected="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowUp, ArrowDown, Microphone, Folder, MoreFilled, 
  Close, Check, Loading, CirclePlus, Picture, ArrowDownBold
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MessageBubble from '@/components/MessageBubble.vue'
import FileManager from '@/components/FileManager.vue'
import LawyerSkillPanel from '@/components/agent/LawyerSkillPanel.vue'
import { useRoleStore } from '@/stores/role'
import { useChatStore } from '@/stores/chat'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const roleStore = useRoleStore()
const chatStore = useChatStore()

// State
const selectedRoleId = ref<string | null>(null)
const inputText = ref('')
const emotionTag = ref('')
const loading = ref(false)
const isSpeaking = ref(false)
const currentAudioUrl = ref('')
const showRoleDrawer = ref(false)
const showFileManager = ref(false)
const isRecording = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const recommendations = ref<string[]>([])
const showAssistTools = ref(true)
const isNearBottom = ref(true)
const pendingMessageCount = ref(0)
const ASSIST_TOOL_VISIBLE_KEY = 'chat.assist_tools_visible'

// Computed
const roles = computed(() => roleStore.roles)
// 直接使用 roleStore 的 currentRole，确保显示一致
const currentRole = computed(() => roleStore.currentRole)
const isLawyerMode = computed(() => {
  const name = (currentRole.value?.name || '').toLowerCase()
  return name.includes('\u5f8b\u5e08') || name.includes('lawyer') || name.includes('\u6cd5\u5f8b')
})

const latestLawyerMeta = computed(() => {
  const lastAssistant = [...chatStore.messages]
    .reverse()
    .find(msg => msg.role === 'assistant' && (msg.agentMode === 'lawyer' || (msg.trace && msg.trace.length > 0)))

  return {
    skillsUsed: lastAssistant?.skillsUsed || [],
    trace: lastAssistant?.trace || [],
    federated: lastAssistant?.federated || {},
    riskLevel: lastAssistant?.riskLevel || ''
  }
})

const showScrollToBottom = computed(() => !isNearBottom.value && chatStore.messages.length > 0)
const isSendDisabled = computed(() => loading.value || (!inputText.value.trim() && !isRecording.value))

const currentTemplates = computed(() => {
  const roleName = currentRole.value?.name || ''
  if (roleName.includes('律师')) {
    return ['合同纠纷咨询', '劳动仲裁流程', '知识产权保护', '法律风险评估']
  } else if (roleName.includes('教师')) {
    return ['制定学习计划', '解题思路讲解', '考试重点预测', '口语对练']
  } else if (roleName.includes('程序员')) {
    return ['代码性能优化', 'Bug排除思路', '新功能实现方案', '技术架构咨询']
  } else if (roleName.includes('作家')) {
    return ['创意灵感激发', '文章润色建议', '情节构思设计', '诗歌散文创作']
  }
  return ['日常打招呼', '今日天气如何', '帮我安排日程', '写一段总结']
})

const getLawyerRole = () => {
  return roles.value.find(role => {
    const roleName = (role.name || '').toLowerCase()
    return roleName.includes('律师') || roleName.includes('法律') || roleName.includes('lawyer')
  })
}

// 加载推荐问题
// const loadRecommendations = async () => {
//   if (loadingRecommendations.value) return
  
//   try {
//     loadingRecommendations.value = true
//     const conversationHistory = chatStore.messages
//       .slice(-6) // 最近6条消息
//       .map(msg => msg.content)
//     const roleName = currentRole.value?.name
    
//     const result = await recommendationApi.getRecommendations(conversationHistory, roleName)
//     recommendations.value = result || []
//   } catch (error) {
//     console.error('加载推荐问题失败:', error)
//     recommendations.value = []
//   } finally {
//     loadingRecommendations.value = false
//   }
// }

// Methods
const activateLawyerAgent = async () => {
  if (isLawyerMode.value) {
    ElMessage.success('当前已是律师 Agent 模式')
    return
  }

  const lawyerRole = getLawyerRole()
  if (!lawyerRole) {
    ElMessage.warning('未找到律师角色，请先在角色管理中创建或启用律师角色')
    showRoleDrawer.value = true
    return
  }

  await selectRole(lawyerRole)
}

const goToSettings = () => {
  router.push('/settings')
}

const toggleAssistTools = () => {
  showAssistTools.value = !showAssistTools.value
}

const useTemplate = (text: string) => {
  if (!text) return
  inputText.value = text
  // 自动聚焦到输入框
  nextTick(() => {
    const textarea = document.querySelector('.dock-input textarea') as HTMLTextAreaElement
    if (textarea) {
      textarea.focus()
      textarea.setSelectionRange(text.length, text.length)
    }
  })
}

const useRecommendation = (text: string) => {
  inputText.value = text
  // 自动聚焦到输入框
  nextTick(() => {
    const textarea = document.querySelector('.dock-input textarea') as HTMLTextAreaElement
    if (textarea) {
      textarea.focus()
      textarea.setSelectionRange(text.length, text.length)
    }
  })
}

const autoSegment = () => {
  if (inputText.value.length <= 500) return
  // Simple segmentation by punctuation or space
  const segments = inputText.value.match(/.{1,500}/g) || []
  inputText.value = segments.join('\n\n---\n\n')
  ElMessage.success(t('chat.autoSegment'))
}

const selectRole = async (role: any) => {
  // 如果当前有对话历史，询问用户如何处理
  if (chatStore.messages.length > 0) {
    try {
      const result = await ElMessageBox.confirm(
        `切换角色到"${role.name}"将清空当前对话，是否继续？`,
        '切换角色',
        {
          confirmButtonText: '继续',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
      
      // 用户确认切换角色
      if (result) {
        chatStore.clearMessages()
      } else {
        return // 用户取消切换
      }
    } catch (error) {
      // 用户关闭对话框，不进行任何操作
      return
    }
  }

  // 更新选中的角色
  selectedRoleId.value = role.id
  await roleStore.setCurrentRole(role)
  chatStore.setRole(role.id)
  showRoleDrawer.value = false // 自动关闭抽屉提供更流畅的体验
  
  // 显示角色切换成功提示
  ElMessage.success(`已切换到角色: ${role.name}`)
}

const sendMessage = async () => {
  if (loading.value) return
  if (!inputText.value.trim() && !isRecording.value) return
  
  // 确保有选中的角色
  if (!selectedRoleId.value && roles.value.length > 0) {
    // 如果没有选中角色，自动选择第一个角色
    const firstRole = roles.value[0]
    await roleStore.setCurrentRole(firstRole)
    selectedRoleId.value = firstRole.id
    chatStore.setRole(firstRole.id)
    ElMessage.success(`已自动选择角色: ${firstRole.name}`)
  } else if (!selectedRoleId.value) {
    ElMessage.warning('请先选择角色')
    showRoleDrawer.value = true
    return
  }

  loading.value = true
  const userText = inputText.value.trim()
  inputText.value = '' // 乐观清除

  try {
    const response = isLawyerMode.value
      ? await chatStore.sendLawyerMessage(userText)
      : await chatStore.sendMessage(userText)
    if (!response) throw new Error('消息发送失败')

    scrollToBottom()

    // 处理语音回复
    if ('audioUrl' in response && response.audioUrl) {
      currentAudioUrl.value = response.audioUrl
      isSpeaking.value = true
      // 模拟语音播放结束
      setTimeout(() => isSpeaking.value = false, 5000)
    }

  } catch (err: any) {
    ElMessage.error(err.message || '发送消息失败')
    inputText.value = userText // 出错时恢复文本
  } finally {
    loading.value = false
  }
}

// Voice (Stub)
const startVoiceInput = () => { isRecording.value = true }
const stopVoiceInput = () => { isRecording.value = false }

const handleKeydown = (event: KeyboardEvent) => {
  if (event.isComposing || event.keyCode === 229) return

  // 处理回车键发送消息（Ctrl+Enter 或 Shift+Enter 换行）
  if (event.key === 'Enter') {
    if (event.ctrlKey || event.shiftKey) {
      // Ctrl+Enter 或 Shift+Enter：插入换行
      event.preventDefault()
      const textarea = event.target as HTMLTextAreaElement
      const cursorPosition = textarea.selectionStart
      const textBefore = inputText.value.substring(0, cursorPosition)
      const textAfter = inputText.value.substring(cursorPosition)
      inputText.value = textBefore + '\n' + textAfter
      
      // 设置光标位置到新行
      nextTick(() => {
        textarea.selectionStart = cursorPosition + 1
        textarea.selectionEnd = cursorPosition + 1
      })
    } else {
      // 普通回车键：发送消息
      event.preventDefault()
      sendMessage()
    }
  }
}

const handleControl = (type: string) => {
  if (type === 'folder' || type === 'image') {
    showFileManager.value = true
  }
}

const handleFileSelected = async (file: any) => {
  const fileUrl = file?.path ? `/api/files/download/${file.path}` : (file?.url || file?.fileUrl)
  if (!fileUrl) {
    ElMessage.warning('文件地址无效，无法发送')
    return
  }

  if (!selectedRoleId.value && roles.value.length > 0) {
    const firstRole = roles.value[0]
    await roleStore.setCurrentRole(firstRole)
    selectedRoleId.value = firstRole.id
    chatStore.setRole(firstRole.id)
  }

  showFileManager.value = false
  loading.value = true

  try {
    await chatStore.sendMessage('', fileUrl)
    scrollToBottom()
    ElMessage.success(`已发送文件: ${file.name}`)
  } catch (error: any) {
    ElMessage.error(error.message || '发送文件失败')
  } finally {
    loading.value = false
  }
}

// 自动滚动到底部（当有新消息时）
const scrollToBottom = () => {
  if (!messagesRef.value) return
  
  nextTick(() => {
    messagesRef.value!.scrollTo({
      top: messagesRef.value!.scrollHeight,
      behavior: 'smooth'
    })
  })
}

const handleScrollToBottom = () => {
  pendingMessageCount.value = 0
  scrollToBottom()
}

// 监听消息变化：如果用户正在查看历史，不强制打断滚动
watch(
  () => chatStore.messages.length,
  (newLen, oldLen) => {
    if (newLen <= oldLen) return
    const latest = chatStore.messages[newLen - 1]
    const isUserMessage = latest?.role === 'user'

    if (isNearBottom.value || isUserMessage) {
      scrollToBottom()
      return
    }

    pendingMessageCount.value = Math.min(99, pendingMessageCount.value + 1)
  }
)

// 滚动状态检测
const checkScrollState = () => {
  if (!messagesRef.value) return
  
  const { scrollTop, scrollHeight, clientHeight } = messagesRef.value
  const isAtTop = scrollTop === 0
  const isAtBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 24
  isNearBottom.value = isAtBottom
  if (isAtBottom) {
    pendingMessageCount.value = 0
  }
  
  // 添加或移除滚动状态类
  messagesRef.value.classList.toggle('scrolled-top', !isAtTop)
  messagesRef.value.classList.toggle('scrolled-bottom', !isAtBottom)
}

// 监听滚动事件
onMounted(() => {
  if (messagesRef.value) {
    messagesRef.value.addEventListener('scroll', checkScrollState)
    // 初始检查滚动状态
    checkScrollState()
  }
})

onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', checkScrollState)
  }
})

// 监听 roleStore.currentRole 变化，同步 selectedRoleId
watch(() => roleStore.currentRole, (newRole) => {
  if (newRole) {
    selectedRoleId.value = newRole.id
    chatStore.setRole(newRole.id)
  }
}, { immediate: true })

watch(
  () => route.query.contextId,
  async (contextId) => {
    const targetContextId = typeof contextId === 'string' ? contextId.trim() : ''
    if (!targetContextId) return
    if (chatStore.contextId === targetContextId) return

    await chatStore.loadHistory(targetContextId)
    scrollToBottom()
  },
  { immediate: true }
)

onMounted(async () => {
  await roleStore.loadRoles()
  const assistToolVisible = localStorage.getItem(ASSIST_TOOL_VISIBLE_KEY)
  if (assistToolVisible === '0') {
    showAssistTools.value = false
  }
  // 如果有角色，设置第一个为当前角色，并同步 selectedRoleId
  if (roles.value.length > 0) {
    const firstRole = roles.value[0]
    // 如果 roleStore 中没有当前角色，则设置
    if (!roleStore.currentRole) {
      await roleStore.setCurrentRole(firstRole)
      selectedRoleId.value = firstRole.id
      chatStore.setRole(firstRole.id)
    } else {
      // 如果已有当前角色，同步 selectedRoleId
      selectedRoleId.value = roleStore.currentRole.id
      chatStore.setRole(roleStore.currentRole.id)
    }
  }
  // 初始加载推荐问题
  // await loadRecommendations()
})

watch(showAssistTools, (visible) => {
  localStorage.setItem(ASSIST_TOOL_VISIBLE_KEY, visible ? '1' : '0')
})
</script>

<style scoped>
/* --- Layout & Container --- */
.chat-view-container {
  height: 100%;
  width: 100%;
  position: relative;
  overflow: hidden;
  background-color: var(--bg-app);
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.chat-stage {
  flex: 1;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.top-zone {
  margin: 20px 8% 10px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  z-index: 2;
}

.agent-spotlight {
  margin: 0;
  padding: 18px 20px;
  border-radius: 18px;
  border: 1px solid rgba(59, 130, 246, 0.16);
  background:
    linear-gradient(120deg, rgba(59, 130, 246, 0.1) 0%, rgba(16, 185, 129, 0.06) 55%, rgba(255, 255, 255, 0.9) 100%);
  backdrop-filter: blur(14px);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  z-index: 2;
}

.agent-spotlight.is-active {
  border-color: rgba(16, 185, 129, 0.35);
  box-shadow: 0 8px 28px rgba(16, 185, 129, 0.14);
}

.agent-spotlight-main {
  min-width: 0;
}

.agent-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: #2563eb;
  margin-bottom: 6px;
}

.agent-title {
  margin: 0;
  font-size: 23px;
  line-height: 1.2;
  color: var(--text-primary);
}

.agent-subtitle {
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1.5;
}

.agent-skill-chips {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-skill-chips span {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid rgba(37, 99, 235, 0.22);
  background: rgba(255, 255, 255, 0.68);
  color: #1e40af;
  font-size: 12px;
  font-weight: 600;
}

.agent-spotlight-actions {
  min-width: 260px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-start;
}

.agent-runtime-hint {
  font-size: 12px;
  color: var(--text-secondary);
}

.chat-body {
  flex: 1;
  display: flex;
  min-height: 0;
  position: relative;
}

.chat-body.with-lawyer-panel {
  gap: 12px;
  padding-right: 12px;
}

.lawyer-panel-wrap {
  width: 360px;
  flex: 0 0 360px;
  padding-top: 12px;
  padding-bottom: 210px;
  min-height: 0;
}

/* Ambient Background */
.ambient-glow {
  position: absolute;
  width: 600px;
  height: 600px;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.4;
  z-index: 0;
  pointer-events: none;
}
.top-left {
  top: -200px;
  left: -200px;
  background: radial-gradient(circle, var(--primary-fade) 0%, transparent 70%);
}
.bottom-right {
  bottom: -200px;
  right: -200px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.05) 0%, transparent 70%);
}

/* --- Digital Human Widget (Top-Left Floating) --- */
.digital-human-widget {
  position: absolute;
  top: 24px;
  left: 24px;
  width: 220px; /* Increased size */
  height: 300px;
  z-index: 5; /* 降低z-index，确保不遮挡消息 */
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.6);
  pointer-events: none; /* 允许点击穿透到消息区域 */
}

.digital-human-widget:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
}

/* Active state for speaking: Subtle glow border */
.digital-human-widget.is-speaking {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 2px var(--primary-fade), 0 8px 32px rgba(0, 0, 0, 0.1);
}

.dh-content {
  width: 100%;
  height: 100%;
  background: #000; /* Placeholder for video area */
}

.dh-controls-overlay {
  position: absolute;
  bottom: 12px;
  left: 0;
  right: 0;
  display: flex;
  justify-content: center;
  pointer-events: none;
}

.digital-human-widget .dh-controls-overlay {
  pointer-events: auto; /* 控件区域可以交互 */
}

.status-indicator {
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  padding: 4px 10px;
  border-radius: 12px;
  color: white;
  font-size: 10px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 6px;
  opacity: 0; /* Hidden by default */
  transition: opacity 0.3s;
}

.status-indicator.active {
  opacity: 1;
}

.pulse {
  width: 6px;
  height: 6px;
  background-color: #10b981;
  border-radius: 50%;
  animation: pulse-animation 1.5s infinite;
}

/* --- Header Actions (Top-Right Floating) --- */
.header-actions {
  position: static;
  align-self: flex-end;
  display: flex;
  gap: 8px;
  z-index: 2;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all 0.2s ease;
  user-select: none;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(255, 255, 255, 0.05);
  backdrop-filter: blur(10px);
}

.action-btn:hover {
  background: rgba(255, 255, 255, 0.1);
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.action-btn:active {
  transform: translateY(0);
}

.action-btn.icon-only {
  padding: 8px;
}

.current-role-avatar {
  flex-shrink: 0;
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.role-name-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 120px;
}

.icon-right {
  margin-left: auto;
  opacity: 0.6;
  transition: opacity 0.2s ease;
}

.action-btn:hover .icon-right {
  opacity: 1;
}

/* --- Messages Container --- */
.messages-container {
  flex: 1 1 auto;
  height: 100%;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 40px 10% 200px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  z-index: 1;
  scroll-behavior: smooth;
  min-height: 0;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  cursor: default;
}

.chat-body.with-lawyer-panel .messages-container {
  padding-right: 16px;
}

.typing-row {
  margin: 8px auto 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  border-radius: 999px;
  background: rgba(79, 70, 229, 0.08);
  color: var(--text-secondary);
  font-size: 12px;
}

.typing-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary-color);
  animation: typing-pulse 1.1s ease-in-out infinite;
}

.typing-dot:nth-child(2) {
  animation-delay: 0.12s;
}

.typing-dot:nth-child(3) {
  animation-delay: 0.24s;
}

.typing-text {
  margin-left: 4px;
}

.jump-bottom-btn {
  position: absolute;
  right: 32px;
  bottom: 224px;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 12px;
  background: rgba(37, 99, 235, 0.92);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  z-index: 18;
  box-shadow: 0 8px 20px rgba(37, 99, 235, 0.28);
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.jump-bottom-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 24px rgba(37, 99, 235, 0.32);
}

.jump-bottom-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
  line-height: 18px;
  text-align: center;
}

/* 消息容器滚动条样式 */
.messages-container::-webkit-scrollbar {
  width: 8px;
}

.messages-container::-webkit-scrollbar-track {
  background: transparent;
  border-radius: 4px;
}

.messages-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 4px;
  border: 2px solid transparent;
  background-clip: content-box;
  transition: background-color 0.3s ease;
}

.messages-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.5);
  border: 2px solid transparent;
  background-clip: content-box;
}

.messages-container::-webkit-scrollbar-thumb:active {
  background: rgba(255, 255, 255, 0.6);
}

/* 滚动时显示滚动条 */
.messages-container:hover::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.4);
}

/* 滚动容器阴影效果 */
.messages-container {
  scrollbar-gutter: stable;
}

/* 滚动时添加渐变遮罩 */
.messages-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 20px;
  background: linear-gradient(to bottom, var(--bg-app), transparent);
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s ease;
  z-index: 2;
}

.messages-container::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 20px;
  background: linear-gradient(to top, var(--bg-app), transparent);
  pointer-events: none;
  opacity: 0;
  transition: opacity 0.3s ease;
  z-index: 2;
}

.messages-container.scrolled-top::before {
  opacity: 1;
}

.messages-container.scrolled-bottom::after {
  opacity: 1;
}

/* Empty State */
.empty-state {
  margin: auto;
  text-align: center;
  opacity: 0.9;
  max-width: 800px;
  width: 100%;
  padding: 80px 0;
  min-height: 70vh;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

/* 动态Logo容器 */
.logo-mark-container {
  position: relative;
  margin-bottom: 32px;
  display: inline-block;
}

.logo-mark {
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 700;
  color: var(--primary-color);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 20px;
  background: rgba(79, 70, 229, 0.08);
  border-radius: 12px;
  border: 1px solid rgba(79, 70, 229, 0.2);
  transition: all 0.3s ease;
}

.logo-mark:hover {
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(79, 70, 229, 0.15);
}

.logo-icon {
  font-size: 18px;
}

.logo-text {
  font-size: 14px;
}

.logo-pulse {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 60px;
  height: 60px;
  background: rgba(79, 70, 229, 0.1);
  border-radius: 50%;
  transform: translate(-50%, -50%);
  animation: pulse 2s ease-in-out infinite;
  z-index: -1;
}

@keyframes pulse {
  0%, 100% { transform: translate(-50%, -50%) scale(1); opacity: 1; }
  50% { transform: translate(-50%, -50%) scale(1.2); opacity: 0.7; }
}

.welcome-section {
  margin-bottom: 32px;
}

.welcome-text {
  font-size: 32px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 12px;
  font-family: var(--font-serif);
}

.subtitle {
  font-size: 16px;
  color: var(--text-secondary);
  margin-bottom: 32px;
}

/* 快速启动网格 */
.quick-start-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 20px;
  margin-bottom: 40px;
  width: 100%;
  max-width: 900px;
}

.quick-action-card {
  background: rgba(255, 255, 255, 0.08);
  border: 1px solid rgba(255, 255, 255, 0.15);
  border-radius: 16px;
  padding: 30px 20px;
  cursor: pointer;
  transition: all 0.3s ease;
  text-align: center;
  min-height: 120px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.quick-action-card:hover {
  background: rgba(255, 255, 255, 0.15);
  transform: translateY(-4px);
  box-shadow: 0 12px 35px rgba(0, 0, 0, 0.15);
  border-color: rgba(255, 255, 255, 0.25);
}

.action-icon {
  font-size: 24px;
  margin-bottom: 8px;
}

.action-text {
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.action-hint {
  font-size: 12px;
  color: var(--text-secondary);
  opacity: 0.8;
}

.empty-actions {
  margin-top: 40px;
  margin-bottom: 40px;
  display: flex;
  justify-content: center;
  gap: 16px;
  flex-wrap: wrap;
  width: 100%;
  max-width: 800px;
}

.empty-action-btn {
  border: none;
  border-radius: 16px;
  padding: 16px 32px;
  cursor: pointer;
  font-size: 15px;
  font-weight: 600;
  color: #fff;
  background: linear-gradient(135deg, #2563eb 0%, #4f46e5 100%);
  box-shadow: 0 8px 25px rgba(37, 99, 235, 0.3);
  transition: all 0.3s ease;
  min-width: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.empty-action-btn:hover {
  transform: translateY(-4px);
  box-shadow: 0 16px 35px rgba(37, 99, 235, 0.4);
}

.empty-action-btn.ghost {
  color: var(--text-regular);
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid rgba(0, 0, 0, 0.08);
  box-shadow: none;
}

.empty-action-btn.primary {
  background: linear-gradient(135deg, var(--primary-color), var(--primary-active));
  box-shadow: 0 8px 25px rgba(79, 70, 229, 0.3);
}

.empty-action-btn.secondary {
  background: rgba(255, 255, 255, 0.1);
  color: var(--text-primary);
  border: 1px solid rgba(255, 255, 255, 0.2);
}

.empty-action-btn.secondary:hover {
  background: rgba(255, 255, 255, 0.2);
  transform: translateY(-2px);
  box-shadow: 0 8px 25px rgba(0, 0, 0, 0.1);
}

/* 功能提示样式 */
.feature-hints {
  display: flex;
  flex-direction: row;
  gap: 24px;
  align-items: center;
  justify-content: center;
  margin-top: 40px;
  padding: 20px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  width: 100%;
  max-width: 800px;
}

.hint-item {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 14px;
  opacity: 0.8;
}

.hint-item .el-icon {
  color: var(--success);
  font-size: 16px;
}

/* --- Message List --- */
.message-list {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 1200px; /* 进一步拓宽消息列表最大宽度 */
  margin: 0 auto;
  width: 100%;
}

/* --- Input Dock (Floating Bottom) --- */
.input-dock-wrapper {
  position: absolute; /* 改为absolute，相对于chat-stage定位 */
  bottom: 0;
  left: 0;
  right: 0;
  padding: 24px 32px 32px; /* 调整padding */
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  pointer-events: none; /* Let clicks pass through area */
  z-index: 20;
  background: linear-gradient(to top, var(--bg-app) 60%, transparent);
  max-width: 100%;
}

.assist-toolbar {
  pointer-events: auto;
  width: 100%;
  max-width: 1400px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 4px;
}

.assist-toggle-btn {
  border: none;
  background: rgba(255, 255, 255, 0.85);
  color: var(--text-regular);
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
  padding: 6px 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.assist-toggle-btn:hover {
  background: #fff;
  color: var(--primary-color);
}

.assist-tip {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.templates-container {
  pointer-events: auto;
  display: flex;
  gap: 10px;
  overflow-x: auto;
  max-width: 1400px; /* 拓宽模板容器以匹配输入框 */
  width: 100%;
  padding: 6px 4px;
  scrollbar-width: thin;
  scroll-behavior: smooth;
  cursor: grab;
}

.templates-container:active {
  cursor: grabbing;
}

/* 模板容器滚动条样式 */
.templates-container::-webkit-scrollbar {
  height: 4px;
  display: block;
}

.templates-container::-webkit-scrollbar-track {
  background: transparent;
}

.templates-container::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.templates-container::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.4);
}

.template-tag {
  flex-shrink: 0;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 16px;
  font-size: 13px;
  color: var(--text-regular);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  font-weight: 500;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.template-tag:hover {
  background: white;
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.15);
}

.recommendations-container {
  pointer-events: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-width: 1400px; /* 拓宽推荐问题容器以匹配输入框 */
  width: 100%;
  padding: 6px 4px;
}

.recommendations-tags {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  padding: 4px 0;
  scrollbar-width: thin;
  scroll-behavior: smooth;
  cursor: grab;
}

.recommendations-tags:active {
  cursor: grabbing;
}

/* 推荐问题容器滚动条样式 */
.recommendations-tags::-webkit-scrollbar {
  height: 4px;
}

.recommendations-tags::-webkit-scrollbar-track {
  background: transparent;
}

.recommendations-tags::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.2);
  border-radius: 2px;
}

.recommendations-tags::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.4);
}

.recommendations-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
  margin-bottom: 4px;
}

.recommendation-tag {
  flex-shrink: 0;
  padding: 8px 16px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 16px;
  font-size: 13px;
  color: var(--text-regular);
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  font-weight: 500;
  white-space: nowrap;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.recommendation-tag:hover {
  background: white;
  border-color: var(--primary-color);
  color: var(--primary-color);
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.15);
}

.input-dock {
  pointer-events: auto;
  width: 100%;
  max-width: 1400px; /* 进一步拓宽输入框最大宽度 */
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(24px) saturate(180%);
  border-radius: 20px;
  border: 1px solid rgba(255, 255, 255, 0.9);
  box-shadow: 
    0 8px 32px rgba(0, 0, 0, 0.08),
    0 2px 8px rgba(0, 0, 0, 0.04),
    inset 0 1px 0 rgba(255, 255, 255, 0.9);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.input-dock:focus-within {
  box-shadow: 
    0 12px 48px rgba(79, 70, 229, 0.12),
    0 4px 16px rgba(79, 70, 229, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.95);
  border-color: rgba(79, 70, 229, 0.2);
  transform: translateY(-2px);
}

.dock-input :deep(.el-textarea__inner) {
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 10px 0;
  font-size: 15px;
  line-height: 1.6;
  color: var(--text-primary);
  font-family: var(--font-sans);
  resize: none;
  min-height: 24px !important;
}

.dock-input :deep(.el-textarea__inner)::placeholder {
  color: var(--text-disabled);
  opacity: 0.6;
}

.dock-input :deep(.el-textarea__inner):focus {
  outline: none;
}

.dock-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 2px;
  border-top: 1px solid rgba(0, 0, 0, 0.05);
  padding-top: 10px;
  min-height: 40px;
}

.footer-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.plus-trigger {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  font-size: 20px;
  background: rgba(0, 0, 0, 0.02);
  border-radius: 10px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.plus-trigger:hover {
  color: var(--primary-color);
  background: rgba(79, 70, 229, 0.08);
  transform: scale(1.05);
}

.tools-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  padding: 8px;
}

.tool-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 12px;
  border-radius: var(--radius-md);
  transition: all 0.2s;
}

.tool-item:hover {
  background: var(--bg-app);
  color: var(--primary-color);
}

.tool-item .el-icon {
  font-size: 24px;
}

.tool-item .el-icon.is-recording {
  color: var(--danger);
  animation: pulse-animation 1s infinite;
}

.word-count {
  font-size: 13px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 400;
  letter-spacing: -0.01em;
}

.word-count.warning {
  color: #f59e0b;
  font-weight: 500;
}

.word-count .hint {
  font-weight: 500;
  opacity: 0.8;
}

.segment-btn {
  font-size: 12px;
  padding: 0;
}

.footer-right {
  display: flex;
  align-items: center;
  gap: 16px;
}

.emotion-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(0, 0, 0, 0.04);
  padding: 6px 12px;
  border-radius: 10px;
  font-size: 12px;
  border: 1px solid rgba(0, 0, 0, 0.05);
  transition: all 0.2s ease;
}

.emotion-pill:hover {
  background: rgba(0, 0, 0, 0.06);
  border-color: rgba(79, 70, 229, 0.2);
}

.emotion-pill .label {
  font-weight: 500;
  color: var(--text-regular);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  opacity: 0.7;
}

.emotion-pill .transparent-input {
  background: transparent;
  border: none;
  outline: none;
  font-size: 12px;
  color: var(--text-primary);
  font-weight: 500;
  width: 60px;
  padding: 0;
}

.emotion-pill .transparent-input::placeholder {
  color: var(--text-disabled);
  opacity: 0.6;
}

.send-trigger {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--primary-color) 0%, #6366f1 100%);
  color: white;
  border: none;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
  box-shadow: 
    0 4px 12px rgba(79, 70, 229, 0.25),
    0 2px 4px rgba(79, 70, 229, 0.15);
  position: relative;
  overflow: hidden;
}

.send-trigger::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.2) 0%, transparent 100%);
  opacity: 0;
  transition: opacity 0.2s;
}

.send-trigger:hover:not(:disabled)::before {
  opacity: 1;
}

.send-trigger:hover:not(:disabled) {
  transform: translateY(-2px) scale(1.05);
  background: linear-gradient(135deg, var(--primary-hover) 0%, #818cf8 100%);
  box-shadow: 
    0 6px 20px rgba(79, 70, 229, 0.35),
    0 4px 8px rgba(79, 70, 229, 0.2);
}

.send-trigger:active:not(:disabled) {
  transform: translateY(0) scale(0.98);
}

.send-trigger:disabled {
  background: var(--text-disabled);
  cursor: not-allowed;
  box-shadow: none;
  opacity: 0.5;
}

.send-trigger .el-icon {
  font-size: 18px;
  font-weight: 600;
}

/* --- Drawer Styles --- */
.drawer-content {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-app);
}

.drawer-header {
  padding: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.drawer-header h2 {
  font-family: var(--font-serif);
  font-size: 20px;
}

.role-grid {
  flex: 1;
  overflow-y: auto;
  padding: 0 24px 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.role-card-minimal {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px;
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 16px;
  cursor: pointer;
  transition: all 0.2s;
  position: relative;
}

.role-card-minimal:hover {
  border-color: var(--primary-color);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}

.role-card-minimal.active {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}

.role-info {
  flex: 1;
}

.role-info .name {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}

.role-info .desc {
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.check-mark {
  color: var(--primary-color);
}

/* Animation */
@keyframes pulse-animation {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.5); opacity: 0.5; }
  100% { transform: scale(1); opacity: 1; }
}

@keyframes typing-pulse {
  0%, 80%, 100% { transform: scale(0.7); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

.role-fade-enter-active, .role-fade-leave-active {
  transition: opacity 0.5s ease, filter 0.5s ease;
}
.role-fade-enter-from, .role-fade-leave-to {
  opacity: 0;
  filter: blur(10px);
}

@media (max-width: 1280px) {
  .top-zone {
    margin: 16px 16px 8px;
  }

  .chat-body.with-lawyer-panel {
    padding-right: 0;
  }

  .lawyer-panel-wrap {
    width: 320px;
    flex-basis: 320px;
  }
}

@media (max-width: 1024px) {
  .top-zone {
    margin: 14px 12px 6px;
  }

  .header-actions {
    align-self: stretch;
    justify-content: flex-end;
  }

  .agent-spotlight {
    padding: 14px;
    flex-direction: column;
    align-items: stretch;
  }

  .agent-title {
    font-size: 20px;
  }

  .agent-spotlight-actions {
    min-width: 0;
    width: 100%;
  }

  .agent-spotlight-actions :deep(.el-button),
  .agent-spotlight-actions :deep(.el-tag) {
    width: 100%;
    justify-content: center;
  }

  .chat-body.with-lawyer-panel {
    display: block;
  }

  .lawyer-panel-wrap {
    width: 100%;
    padding: 8px 16px 0;
  }

  .jump-bottom-btn {
    right: 16px;
    bottom: 214px;
  }

  .messages-container {
    padding: 10px 16px 200px;
  }

  .assist-toolbar {
    flex-wrap: wrap;
    align-items: flex-start;
  }

  .assist-tip {
    white-space: normal;
  }

  .message-list {
    max-width: 100%; /* 小屏幕上使用全宽 */
  }
  .input-dock {
    max-width: 100%;
  }
  .templates-container,
  .recommendations-container {
    max-width: 100%;
  }
}
</style>
