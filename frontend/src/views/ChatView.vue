<template>
  <div class="chat-view">
    <header class="chat-header">
      <div class="left">
        <span class="title">联邦智能枢对话中心</span>
        <el-tag size="small" :type="isLawyerMode ? 'success' : 'info'">
          {{ isLawyerMode ? '律师 Agent 已启用' : '普通对话模式' }}
        </el-tag>
      </div>
      <div class="right">
        <el-button size="small" type="primary" @click="toggleLawyerMode">
          <el-icon><ScaleToOriginal /></el-icon>
          {{ isLawyerMode ? '保持律师模式' : '切换律师模式' }}
        </el-button>
        <el-button size="small" @click="showRoleDrawer = true">
          <el-icon><User /></el-icon>
          角色
        </el-button>
        <el-button size="small" @click="goToSettings">
          <el-icon><MoreFilled /></el-icon>
          设置
        </el-button>
      </div>
    </header>

    <div class="chat-main" :class="{ lawyer: isLawyerMode }">
      <section class="chat-panel">
        <div class="messages" ref="messagesRef">
          <div v-if="chatStore.messages.length === 0" class="empty-state">
            <h2>开始一次新对话</h2>
            <p>你可以直接输入问题，或使用下方快捷模板。</p>
            <div class="quick-actions">
              <el-button @click="useTemplate(currentTemplates[0])">{{ currentTemplates[0] }}</el-button>
              <el-button @click="useTemplate(currentTemplates[1])">{{ currentTemplates[1] }}</el-button>
              <el-button @click="showRoleDrawer = true">选择角色</el-button>
            </div>
          </div>

          <div v-else class="message-list">
            <div
              v-for="msg in chatStore.messages"
              :key="msg.id"
              class="message-row"
              :class="msg.role"
            >
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

          <div v-if="loading" class="typing">AI 正在思考...</div>
        </div>

        <button v-if="showScrollToBottom" class="to-bottom" @click="handleScrollToBottom">
          <el-icon><ArrowDownBold /></el-icon>
          <span v-if="pendingMessageCount > 0" class="badge">{{ pendingMessageCount > 9 ? '9+' : pendingMessageCount }}</span>
        </button>

        <div class="template-row" v-if="showAssistTools && currentTemplates.length">
          <button v-for="tpl in currentTemplates" :key="tpl" class="template-item" @click="useTemplate(tpl)">
            {{ tpl }}
          </button>
        </div>

        <div class="composer">
          <el-input
            v-model="inputText"
            type="textarea"
            :rows="1"
            :autosize="{ minRows: 1, maxRows: 6 }"
            resize="none"
            :placeholder="$t('chat.placeholder')"
            @keydown="handleKeydown"
          />
          <div class="composer-footer">
            <div class="left-actions">
              <el-button text @click="toggleAssistTools">{{ showAssistTools ? '收起模板' : '展开模板' }}</el-button>
              <el-button text @click="isRecording ? stopVoiceInput() : startVoiceInput()">
                <el-icon><Microphone /></el-icon>
                {{ isRecording ? '停止录音' : '语音输入' }}
              </el-button>
              <el-button text @click="handleControl('folder')">
                <el-icon><Folder /></el-icon>
                文件
              </el-button>
            </div>
            <div class="right-actions">
              <span class="word-count" :class="{ warning: inputText.length > 500 }">
                {{ $t('chat.wordCount', { count: inputText.length }) }}
              </span>
              <el-button v-if="inputText.length > 500" text @click="autoSegment">自动分段</el-button>
              <el-button type="primary" :disabled="isSendDisabled" @click="sendMessage">
                <el-icon v-if="!loading"><ArrowUp /></el-icon>
                <el-icon v-else class="is-loading"><Loading /></el-icon>
              </el-button>
            </div>
          </div>
        </div>
      </section>

      <aside v-if="isLawyerMode" class="lawyer-panel">
        <LawyerSkillPanel
          :skills-used="latestLawyerMeta.skillsUsed"
          :trace="latestLawyerMeta.trace"
          :federated="latestLawyerMeta.federated"
          :risk-level="latestLawyerMeta.riskLevel"
        />

        <div v-if="availableResultPanels.length" class="lawyer-results">
          <el-collapse v-model="activeResultPanels">
            <el-collapse-item
              v-if="availableResultPanels.includes('evidence')"
              title="证据分析结果"
              name="evidence"
            >
              <EvidenceAnalysisCard :data="latestSkillResults.evidenceAnalysis" />
            </el-collapse-item>

            <el-collapse-item
              v-if="availableResultPanels.includes('limitation')"
              title="诉讼时效结果"
              name="limitation"
            >
              <LimitationTimeline :data="latestSkillResults.limitationCalc" />
            </el-collapse-item>

            <el-collapse-item
              v-if="availableResultPanels.includes('jurisdiction')"
              title="管辖法院建议"
              name="jurisdiction"
            >
              <JurisdictionCard :data="latestSkillResults.jurisdiction" />
            </el-collapse-item>

            <el-collapse-item
              v-if="availableResultPanels.includes('hearing')"
              title="庭审提纲"
              name="hearing"
            >
              <HearingOutlineViewer :data="latestSkillResults.hearingOutline" />
            </el-collapse-item>
          </el-collapse>
        </div>
      </aside>
    </div>

    <el-drawer v-model="showRoleDrawer" direction="rtl" :size="320" :with-header="false">
      <div class="drawer-head">
        <h3>角色列表</h3>
        <el-button text @click="showRoleDrawer = false"><el-icon><Close /></el-icon></el-button>
      </div>
      <div class="role-list">
        <div
          v-for="role in roles"
          :key="role.id"
          class="role-item"
          :class="{ active: roleStore.currentRole?.id === role.id || selectedRoleId === role.id }"
          @click="selectRole(role)"
        >
          <el-avatar :size="36" :src="role.avatar">{{ role.name?.charAt(0) }}</el-avatar>
          <div class="role-text">
            <div class="name">{{ role.name }}</div>
            <div class="desc">{{ role.description || 'AI Assistant' }}</div>
          </div>
          <el-icon v-if="roleStore.currentRole?.id === role.id || selectedRoleId === role.id"><Check /></el-icon>
        </div>
      </div>
    </el-drawer>

    <FileManager v-model="showFileManager" @fileSelected="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowUp,
  Microphone,
  Folder,
  MoreFilled,
  Close,
  Check,
  Loading,
  ArrowDownBold,
  User,
  ScaleToOriginal
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MessageBubble from '@/components/MessageBubble.vue'
import FileManager from '@/components/FileManager.vue'
import LawyerSkillPanel from '@/components/agent/LawyerSkillPanel.vue'
import EvidenceAnalysisCard from '@/components/agent/EvidenceAnalysisCard.vue'
import LimitationTimeline from '@/components/agent/LimitationTimeline.vue'
import JurisdictionCard from '@/components/agent/JurisdictionCard.vue'
import HearingOutlineViewer from '@/components/agent/HearingOutlineViewer.vue'
import { useRoleStore } from '@/stores/role'
import { useChatStore } from '@/stores/chat'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const roleStore = useRoleStore()
const chatStore = useChatStore()

const selectedRoleId = ref<string | null>(null)
const inputText = ref('')
const loading = ref(false)
const showRoleDrawer = ref(false)
const showFileManager = ref(false)
const isRecording = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const showAssistTools = ref(true)
const isNearBottom = ref(true)
const pendingMessageCount = ref(0)
const activeResultPanels = ref<string[]>([])
const ASSIST_TOOL_VISIBLE_KEY = 'chat.assist_tools_visible'

const roles = computed(() => roleStore.roles)
const currentRole = computed(() => roleStore.currentRole)
const isLawyerMode = computed(() => {
  const name = (currentRole.value?.name || '').toLowerCase()
  return name.includes('律师') || name.includes('lawyer') || name.includes('法律')
})

const latestLawyerMessage = computed(() => {
  return [...chatStore.messages]
    .reverse()
    .find(msg => msg.role === 'assistant' && (msg.agentMode === 'lawyer' || (msg.trace && msg.trace.length > 0)))
})

const latestLawyerMeta = computed(() => {
  const lastAssistant = latestLawyerMessage.value

  return {
    skillsUsed: lastAssistant?.skillsUsed || [],
    trace: lastAssistant?.trace || [],
    federated: lastAssistant?.federated || {},
    riskLevel: lastAssistant?.riskLevel || ''
  }
})

const latestSkillResults = computed(() => {
  const lastAssistant = latestLawyerMessage.value
  return {
    evidenceAnalysis: lastAssistant?.evidenceAnalysis,
    limitationCalc: lastAssistant?.limitationCalc,
    jurisdiction: lastAssistant?.jurisdiction,
    hearingOutline: lastAssistant?.hearingOutline
  }
})

const availableResultPanels = computed(() => {
  const skillSet = new Set(latestLawyerMeta.value.skillsUsed || [])
  const panels: string[] = []
  if (latestSkillResults.value.evidenceAnalysis || skillSet.has('evidence_analysis')) panels.push('evidence')
  if (latestSkillResults.value.limitationCalc || skillSet.has('limitation_calculation')) panels.push('limitation')
  if (latestSkillResults.value.jurisdiction || skillSet.has('jurisdiction_determination')) panels.push('jurisdiction')
  if (latestSkillResults.value.hearingOutline || skillSet.has('hearing_outline_generation')) panels.push('hearing')
  return panels
})

const showScrollToBottom = computed(() => !isNearBottom.value && chatStore.messages.length > 0)
const isSendDisabled = computed(() => loading.value || (!inputText.value.trim() && !isRecording.value))

const currentTemplates = computed(() => {
  const roleName = currentRole.value?.name || ''
  const lower = roleName.toLowerCase()

  if (roleName.includes('律师') || lower.includes('lawyer')) {
    return ['合同纠纷咨询', '劳动仲裁流程', '法律风险评估', '文书草稿生成']
  }
  if (roleName.includes('教师') || lower.includes('teacher')) {
    return ['制定学习计划', '题目讲解', '考试重点整理', '口语训练']
  }
  if (roleName.includes('程序') || lower.includes('developer')) {
    return ['代码优化建议', '排查报错思路', '功能设计方案', '接口联调清单']
  }
  if (roleName.includes('作家') || lower.includes('writer')) {
    return ['文章润色', '标题优化', '情节大纲', '文案创作']
  }
  return ['日常问答', '帮我做个计划', '总结这段内容', '给我几个建议']
})

const getLawyerRole = () => {
  return roles.value.find(role => {
    const roleName = (role.name || '').toLowerCase()
    return roleName.includes('律师') || roleName.includes('法律') || roleName.includes('lawyer')
  })
}

const activateLawyerAgent = async () => {
  if (isLawyerMode.value) {
    ElMessage.success('当前已经是律师模式')
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

const toggleLawyerMode = async () => {
  if (isLawyerMode.value) {
    ElMessage.info('当前已在律师模式')
    return
  }
  await activateLawyerAgent()
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
  nextTick(() => {
    const textarea = document.querySelector('.composer textarea') as HTMLTextAreaElement | null
    if (textarea) {
      textarea.focus()
      textarea.setSelectionRange(text.length, text.length)
    }
  })
}

const autoSegment = () => {
  if (inputText.value.length <= 500) return
  const segments = inputText.value.match(/.{1,500}/g) || []
  inputText.value = segments.join('\n\n---\n\n')
  ElMessage.success(t('chat.autoSegment'))
}

const selectRole = async (role: any) => {
  if (chatStore.messages.length > 0) {
    try {
      await ElMessageBox.confirm(
        `切换到角色 "${role.name}" 会清空当前对话，是否继续？`,
        '切换角色',
        {
          confirmButtonText: '继续',
          cancelButtonText: '取消',
          type: 'warning'
        }
      )
      chatStore.clearMessages()
    } catch {
      return
    }
  }

  selectedRoleId.value = role.id
  await roleStore.setCurrentRole(role)
  chatStore.setRole(role.id)
  showRoleDrawer.value = false
  ElMessage.success(`已切换到角色: ${role.name}`)
}

const sendMessage = async () => {
  if (loading.value) return
  if (!inputText.value.trim() && !isRecording.value) return

  if (!selectedRoleId.value && roles.value.length > 0) {
    const firstRole = roles.value[0]
    await roleStore.setCurrentRole(firstRole)
    selectedRoleId.value = firstRole.id
    chatStore.setRole(firstRole.id)
  } else if (!selectedRoleId.value) {
    ElMessage.warning('请先选择角色')
    showRoleDrawer.value = true
    return
  }

  loading.value = true
  const userText = inputText.value.trim()
  inputText.value = ''

  try {
    const response = isLawyerMode.value
      ? await chatStore.sendLawyerMessage(userText)
      : await chatStore.sendMessage(userText)

    if (!response) throw new Error('消息发送失败')
    scrollToBottom()
  } catch (err: any) {
    ElMessage.error(err.message || '发送消息失败')
    inputText.value = userText
  } finally {
    loading.value = false
  }
}

const startVoiceInput = () => {
  isRecording.value = true
}

const stopVoiceInput = () => {
  isRecording.value = false
}

const handleKeydown = (event: KeyboardEvent) => {
  if (event.isComposing || event.keyCode === 229) return
  if (event.key !== 'Enter') return

  if (event.ctrlKey || event.shiftKey) {
    event.preventDefault()
    const textarea = event.target as HTMLTextAreaElement
    const cursorPosition = textarea.selectionStart
    const textBefore = inputText.value.substring(0, cursorPosition)
    const textAfter = inputText.value.substring(cursorPosition)
    inputText.value = `${textBefore}\n${textAfter}`

    nextTick(() => {
      textarea.selectionStart = cursorPosition + 1
      textarea.selectionEnd = cursorPosition + 1
    })
    return
  }

  event.preventDefault()
  sendMessage()
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

const scrollToBottom = () => {
  if (!messagesRef.value) return
  nextTick(() => {
    messagesRef.value?.scrollTo({
      top: messagesRef.value.scrollHeight,
      behavior: 'smooth'
    })
  })
}

const handleScrollToBottom = () => {
  pendingMessageCount.value = 0
  scrollToBottom()
}

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

watch(
  availableResultPanels,
  panels => {
    activeResultPanels.value = [...panels]
  },
  { immediate: true }
)

const checkScrollState = () => {
  if (!messagesRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messagesRef.value
  const isAtBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 24
  isNearBottom.value = isAtBottom
  if (isAtBottom) pendingMessageCount.value = 0
}

watch(
  () => route.query.contextId,
  async contextId => {
    const targetContextId = typeof contextId === 'string' ? contextId.trim() : ''
    if (!targetContextId) return
    if (chatStore.contextId === targetContextId) return

    await chatStore.loadHistory(targetContextId)
    scrollToBottom()
  },
  { immediate: true }
)

watch(
  () => roleStore.currentRole,
  newRole => {
    if (!newRole) return
    selectedRoleId.value = newRole.id
    chatStore.setRole(newRole.id)
  },
  { immediate: true }
)

watch(showAssistTools, visible => {
  localStorage.setItem(ASSIST_TOOL_VISIBLE_KEY, visible ? '1' : '0')
})

onMounted(async () => {
  await roleStore.loadRoles()

  const assistToolVisible = localStorage.getItem(ASSIST_TOOL_VISIBLE_KEY)
  if (assistToolVisible === '0') {
    showAssistTools.value = false
  }

  if (roles.value.length > 0) {
    if (!roleStore.currentRole) {
      const firstRole = roles.value[0]
      await roleStore.setCurrentRole(firstRole)
      selectedRoleId.value = firstRole.id
      chatStore.setRole(firstRole.id)
    } else {
      selectedRoleId.value = roleStore.currentRole.id
      chatStore.setRole(roleStore.currentRole.id)
    }
  }

  if (messagesRef.value) {
    messagesRef.value.addEventListener('scroll', checkScrollState)
    checkScrollState()
  }
})

onUnmounted(() => {
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', checkScrollState)
  }
})
</script>

<style scoped>
.chat-view {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-app);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border-light);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(8px);
}

.chat-header .left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chat-header .title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.chat-header .right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr;
}

.chat-main.lawyer {
  grid-template-columns: 1fr 320px;
}

.chat-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 16px;
}

.empty-state {
  margin: 60px auto;
  text-align: center;
  max-width: 720px;
}

.quick-actions {
  margin-top: 16px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 10px;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.typing {
  margin-top: 12px;
  color: var(--text-secondary);
  font-size: 13px;
}

.to-bottom {
  position: absolute;
  right: 18px;
  bottom: 180px;
  width: 40px;
  height: 40px;
  border: none;
  border-radius: 12px;
  background: #2563eb;
  color: #fff;
  cursor: pointer;
}

.to-bottom .badge {
  position: absolute;
  top: -6px;
  right: -6px;
  min-width: 16px;
  height: 16px;
  border-radius: 999px;
  line-height: 16px;
  font-size: 10px;
  background: #ef4444;
}

.template-row {
  display: flex;
  gap: 8px;
  padding: 8px 16px;
  overflow-x: auto;
}

.template-item {
  border: 1px solid var(--border-light);
  background: #fff;
  border-radius: 999px;
  padding: 6px 12px;
  white-space: nowrap;
  cursor: pointer;
}

.composer {
  border-top: 1px solid var(--border-light);
  background: #fff;
  padding: 12px 16px;
}

.composer-footer {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.left-actions,
.right-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.word-count.warning {
  color: #f59e0b;
}

.lawyer-panel {
  border-left: 1px solid var(--border-light);
  background: #fff;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px;
  overflow-y: auto;
}

.lawyer-results {
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: #fff;
  padding: 8px;
}

.lawyer-results :deep(.el-collapse) {
  border-top: none;
  border-bottom: none;
}

.lawyer-results :deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 600;
}

.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border-light);
}

.role-list {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.role-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  padding: 10px;
  cursor: pointer;
}

.role-item.active {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}

.role-text .name {
  font-size: 14px;
  font-weight: 600;
}

.role-text .desc {
  font-size: 12px;
  color: var(--text-secondary);
}

@media (max-width: 1100px) {
  .chat-main.lawyer {
    grid-template-columns: 1fr;
  }

  .lawyer-panel {
    border-left: none;
    border-top: 1px solid var(--border-light);
    max-height: 260px;
  }
}
</style>
