<!-- 消息展示组件 — 用户使用紧凑气泡，助手使用无边框阅读流 -->
<template>
  <div v-if="message && message.role && message.content !== undefined" :class="['message-bubble', message.role]">
    <div class="message-content-wrapper">
      <div class="message-content">
        <!-- 文件展示 -->
        <div v-if="message.fileUrl" class="message-file">
          <div
            v-if="isImage(message.fileUrl)"
            class="message-image-wrapper"
            @click="openImageViewer"
          >
            <img :src="message.fileUrl" class="message-image" />
            <div class="image-overlay">
              <el-icon><FullScreen /></el-icon>
            </div>
          </div>
          <div v-else class="file-attachment">
            <el-icon><Document /></el-icon>
            <div class="file-info">
              <span class="filename">附件文件</span>
              <a :href="message.fileUrl" target="_blank" class="download-link">下载</a>
            </div>
          </div>
        </div>

        <ImageViewer
          v-model:visible="imageViewerVisible"
          :src="message.fileUrl"
          :file-name="'image.png'"
        />

        <!-- DeepSeek 风格的内联思考状态；仅展示真实状态和已有运行详情 -->
        <section
          v-if="message.role === 'assistant' && showThinkingStatus"
          class="thinking-status"
          :class="{ 'is-thinking': headerThinkingActive }"
          aria-label="AI 思考状态"
        >
          <button
            v-if="canExpandDetails"
            type="button"
            class="thinking-status__trigger"
            :aria-expanded="detailsOpen"
            :aria-controls="detailsId"
            @click="detailsOpen = !detailsOpen"
          >
            <span class="thinking-status__identity">
              <el-icon class="thinking-status__icon"><Cpu /></el-icon>
              <Transition name="thinking-phase" mode="out-in">
                <span :key="thinkingLabel" class="thinking-status__phase">{{ thinkingLabel }}</span>
              </Transition>
            </span>
            <span v-if="!detailsOpen && collapsedHint" class="thinking-status__hint">{{ collapsedHint }}</span>
            <el-icon class="thinking-status__chevron" :class="{ open: detailsOpen }"><ArrowDown /></el-icon>
          </button>
          <div v-else class="thinking-status__summary" role="status" aria-live="polite">
            <span class="thinking-status__identity">
              <el-icon class="thinking-status__icon"><Cpu /></el-icon>
              <Transition name="thinking-phase" mode="out-in">
                <span :key="thinkingLabel" class="thinking-status__phase">{{ thinkingLabel }}</span>
              </Transition>
            </span>
            <span v-if="headerThinkingActive" class="thinking-status__dots" aria-hidden="true">
              <i></i><i></i><i></i>
            </span>
          </div>

          <button
            v-if="!detailsOpen && reasoningPreview"
            type="button"
            class="thinking-status__preview"
            @click="detailsOpen = true"
          >
            <span class="thinking-status__preview-label">思考</span>
            <span class="thinking-status__preview-text">{{ reasoningPreview }}</span>
          </button>

          <Transition name="thinking-details">
            <div v-if="detailsOpen && canExpandDetails" :id="detailsId" class="thinking-status__details">
              <div v-if="thinkingMetaChips.length" class="thinking-meta">
                <span v-for="chip in thinkingMetaChips" :key="chip.label" class="thinking-meta__chip">
                  <span class="thinking-meta__label">{{ chip.label }}</span>
                  <strong class="thinking-meta__value">{{ chip.value }}</strong>
                </span>
              </div>

              <div v-if="message.reasoningContent" class="thinking-section">
                <div class="thinking-section__head">
                  <span>思考过程</span>
                  <button
                    v-if="reasoningIsLong"
                    type="button"
                    class="thinking-section__link"
                    @click="reasoningExpanded = !reasoningExpanded"
                  >
                    {{ reasoningExpanded ? '收起' : '展开全文' }}
                  </button>
                  <span v-else class="thinking-section__hint">模型原始推理</span>
                </div>
                <pre class="reasoning-content" :class="{ 'is-expanded': reasoningExpanded }">{{ message.reasoningContent }}</pre>
                <p v-if="message.reasoningTruncated" class="thinking-section__note">思考正文超过保存上限，已截断。</p>
              </div>

              <div v-else-if="message.thinkingState" class="thinking-empty">
                本次回复没有返回可展示的思考正文。
              </div>

              <div v-if="message.confidence" class="explanation-item">
                <span class="explanation-label">置信度</span>
                <div class="explanation-value-row">
                  <el-progress
                    :percentage="(message.confidence * 100)"
                    :color="getConfidenceColor(message.confidence)"
                    :stroke-width="5"
                    :show-text="false"
                    style="width: 96px;"
                  />
                  <span class="value-text">{{ (message.confidence * 100).toFixed(1) }}%</span>
                </div>
              </div>

              <div v-if="message.sources && message.sources.length > 0" class="explanation-item vertical">
                <span class="explanation-label">参考来源</span>
                <div class="sources-list">
                  <template v-for="(source, index) in message.sources" :key="source.citationId || source.url || index">
                    <a
                      v-if="source.url && isSafeUrl(source.url)"
                      class="source-tag"
                      :href="source.url"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <el-icon><Link /></el-icon>
                      {{ source.title || source.filename || `来源 ${index + 1}` }}
                    </a>
                    <span v-else class="source-tag">
                      <el-icon><Link /></el-icon>
                      {{ source.title || source.filename || `来源 ${index + 1}` }}
                    </span>
                  </template>
                </div>
              </div>

              <div v-if="message.reasoningPath && message.reasoningPath.length > 0" class="explanation-item vertical">
                <span class="explanation-label">推理路径</span>
                <div class="reasoning-path">
                  <div v-for="(step, index) in message.reasoningPath" :key="index" class="reasoning-step">
                    <div class="step-dot"></div>
                    <div class="step-content">
                      <div class="step-title">{{ step.title }}</div>
                      <div class="step-desc">{{ step.description }}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div v-if="message.executionSummary && message.executionSummary.length > 0" class="thinking-section">
                <button
                  type="button"
                  class="thinking-section__toggle"
                  :aria-expanded="summaryOpen"
                  @click="summaryOpen = !summaryOpen"
                >
                  <span class="thinking-section__toggle-title">执行摘要</span>
                  <span class="thinking-section__hint">
                    {{ message.executionSummary.length }} 项
                    <template v-if="executionTotalDuration"> · {{ formatDuration(executionTotalDuration) }}</template>
                  </span>
                  <el-icon class="thinking-section__chevron" :class="{ open: summaryOpen }"><ArrowDown /></el-icon>
                </button>
                <div v-if="summaryOpen" class="execution-summary">
                  <div
                    v-for="item in message.executionSummary"
                    :key="`${item.stage}-${item.status}`"
                    class="execution-summary__item"
                    :class="`is-${executionStatusTone(item.status)}`"
                  >
                    <span class="execution-summary__dot" aria-hidden="true"></span>
                    <div class="execution-summary__content">
                      <div class="execution-summary__head">
                        <code class="execution-summary__tool">{{ executionToolName(item.stage) }}</code>
                        <span class="execution-summary__status">{{ executionStatusLabel(item.status) }}</span>
                        <span v-if="item.durationMs" class="execution-summary__duration">{{ formatDuration(item.durationMs) }}</span>
                      </div>
                      <p v-if="item.description" class="execution-summary__description">{{ item.description }}</p>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </Transition>
        </section>

        <p v-if="message.streamError && message.streamError !== message.content" class="stream-error" role="status">{{ message.streamError }}</p>

        <!-- 命令/文件执行与审批已迁移到右侧「对话信息」栏（ConversationWorkFeed），主对话区只保留思考与输出。 -->

        <!-- 文本内容 -->
        <div
          v-if="message.content"
          class="message-text markdown-body"
          v-html="renderedMessageHtml"
        />

        <Transition name="continuation-status">
          <div
            v-if="showContinuationStatus"
            class="continuation-status"
            role="status"
            aria-live="polite"
          >
            <span class="continuation-status__pulse" aria-hidden="true">
              <i></i><i></i><i></i>
            </span>
            <span class="continuation-status__eyebrow">执行脉络</span>
            <Transition name="thinking-phase" mode="out-in">
              <span :key="continuationLabel" class="continuation-status__label">
                {{ continuationLabel }}
              </span>
            </Transition>
          </div>
        </Transition>
      </div>

      <!-- Message Actions Area -->
      <div v-if="message.content" class="message-actions">
        <el-tooltip content="复制" placement="top">
          <div class="action-item" @click="handleAction('copy')"><el-icon><CopyDocument /></el-icon></div>
        </el-tooltip>
        <el-tooltip content="引用" placement="top">
          <div class="action-item" @click="handleAction('quote')"><el-icon><ChatLineSquare /></el-icon></div>
        </el-tooltip>
        <el-tooltip content="生成语音" placement="top">
          <div class="action-item" @click="handleAction('tts')"><el-icon><Microphone /></el-icon></div>
        </el-tooltip>
        <el-tooltip content="导出" placement="top">
          <div class="action-item" @click="handleAction('export')"><el-icon><Download /></el-icon></div>
        </el-tooltip>
        <el-tooltip content="删除" placement="top">
          <div class="action-item delete" @click="handleAction('delete')"><el-icon><Delete /></el-icon></div>
        </el-tooltip>
        <span class="message-action-time">{{ formatTime(message.createdAt) }}</span>
      </div>
    </div>
  </div>
  <div v-else class="message-bubble error">
    <div class="message-content">
      <div class="message-text">消息数据无效</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowDown, Cpu, Document, Link, CopyDocument, ChatLineSquare, Delete, Microphone, Download, FullScreen } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ImageViewer from '@/components/common/ImageViewer.vue'
import { renderMarkdown } from '@/utils/markdown'

interface Source {
  title?: string
  filename?: string
  url?: string
  content?: string
  snippet?: string
  provider?: string
  citationId?: string
  retrievedAt?: string
}

interface ReasoningStep {
  title: string
  description: string
}

interface TerminalExecution {
  command: string
  cwd: string
  exitCode: number | null
  stdout: string
  stderr: string
  timedOut: boolean
  truncated: boolean
  durationMs?: number
}

interface ToolExecutionActivity {
  kind: string
  capabilityId?: string
  relativePath?: string
  status?: string
  summary?: string
  addedLines?: number
  removedLines?: number
  entryCount?: number
  errorCode?: string
}

interface ChatApproval {
  approvalId: string
  toolCallId: string
  invocationId: string
  toolName: string
  capabilityId: string
  relativePath?: string
  operationSummary: string
  createdAt: string
  status: string
  sessionId: string
  operation?: string
  command?: string
  cwd?: string
  riskNotice?: string
}

interface ExecutionSummaryItem {
  stage: string
  status: string
  description: string
  durationMs?: number
  terminal?: TerminalExecution
  activity?: ToolExecutionActivity
  approval?: ChatApproval
}

interface Props {
  message: {
    id: number | string
    role: 'user' | 'assistant'
    content: string
    createdAt: Date
    confidence?: number
    fileUrl?: string
    tokensUsed?: number
    sources?: Source[]
    reasoningPath?: ReasoningStep[]
    modelInfo?: string
    thinkingState?: 'thinking' | 'complete' | 'error'
    streamError?: string
    streamActivity?: 'receiving' | 'waiting' | 'complete'
    streamPhase?: string
    thinkingDurationMs?: number
    reasoningContent?: string
    reasoningTruncated?: boolean
    requestedThinkingMode?: string
    effectiveThinkingMode?: string
    effectiveReasoningEffort?: string
    reasoningTokens?: number
    executionSummary?: ExecutionSummaryItem[]
  }
}

const props = defineProps<Props>()
const emit = defineEmits(['copy', 'quote', 'delete', 'tts', 'export'])
const detailsOpen = ref(false)
const summaryOpen = ref(false)
const reasoningExpanded = ref(false)
const imageViewerVisible = ref(false)
const detailsId = computed(() => `thinking-details-${String(props.message.id).replace(/[^a-zA-Z0-9_-]/g, '-')}`)

const openImageViewer = () => {
  imageViewerVisible.value = true
}

const handleAction = (type: 'copy' | 'quote' | 'delete' | 'tts' | 'export') => {
  if (type === 'copy') {
    navigator.clipboard.writeText(props.message.content)
    ElMessage.success('已复制到剪贴板')
  } else if (type === 'delete') {
    ElMessageBox.confirm('确定要删除这条消息吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
      customClass: 'destructive-confirm'
    }).then(() => {
      emit('delete', props.message.id)
    }).catch(() => {})
  } else {
    emit(type, props.message)
  }
}

const escapeHtml = (raw: string) => {
  return raw
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

const isSafeUrl = (url: string) => /^(https?:\/\/|mailto:|\/)/i.test(url)

const renderedMessageHtml = computed(() => {
  const content = props.message.content || ''
  if (!content) return ''
  if (props.message.role === 'assistant') return renderMarkdown(content)
  return escapeHtml(content).replace(/\n/g, '<br />')
})

const hasDetails = computed(() => {
  return !!(
    props.message.confidence ||
    props.message.tokensUsed ||
    (props.message.sources && props.message.sources.length > 0) ||
    (props.message.reasoningPath && props.message.reasoningPath.length > 0) ||
    props.message.reasoningContent ||
    props.message.effectiveThinkingMode ||
    props.message.reasoningTokens ||
    (props.message.executionSummary && props.message.executionSummary.length > 0) ||
    props.message.modelInfo
  )
})

const showThinkingStatus = computed(() => !!props.message.thinkingState || hasDetails.value)

const canExpandDetails = computed(() => {
  return hasDetails.value && (
    props.message.thinkingState !== 'thinking' || Boolean(props.message.reasoningContent)
  )
})

const thinkingModeLabel = computed(() => {
  const mode = props.message.effectiveThinkingMode || props.message.requestedThinkingMode
  if (mode === 'deep') return '深度'
  if (mode === 'standard') return '标准'
  return '关闭'
})

const formatTokenCount = (value: number) => {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2).replace(/\.?0+$/, '')}M`
  if (value >= 1_000) return `${(value / 1_000).toFixed(1).replace(/\.0$/, '')}K`
  return String(value)
}

const thinkingMetaChips = computed(() => {
  const chips: Array<{ label: string; value: string }> = []
  if (props.message.modelInfo) chips.push({ label: '模型', value: props.message.modelInfo })
  if (props.message.effectiveThinkingMode) chips.push({ label: '强度', value: thinkingModeLabel.value })
  if (props.message.reasoningTokens) {
    chips.push({ label: '思考', value: `${formatTokenCount(props.message.reasoningTokens)} tokens` })
  }
  if (props.message.tokensUsed) {
    chips.push({ label: '消耗', value: `${formatTokenCount(props.message.tokensUsed)} tokens` })
  }
  return chips
})

const reasoningPreview = computed(() => {
  const text = (props.message.reasoningContent || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  return text.length > 120 ? `${text.slice(0, 120)}…` : text
})

const reasoningIsLong = computed(() => (props.message.reasoningContent || '').trim().length > 600)

const collapsedHint = computed(() => {
  if (reasoningPreview.value) return '查看思考过程'
  const count = props.message.executionSummary?.length || 0
  return count ? `${count} 项工具调用` : ''
})

const executionTotalDuration = computed(() => (props.message.executionSummary || [])
  .reduce((total, item) => total + (item.durationMs || 0), 0))

const thinkingDurationSeconds = computed(() => {
  if (props.message.thinkingDurationMs === undefined) return null
  return Math.max(1, Math.ceil(props.message.thinkingDurationMs / 1000))
})

const headerThinkingActive = computed(() => {
  if (props.message.thinkingState === 'thinking') return true
  return !props.message.thinkingState
    && (props.message.streamActivity === 'receiving' || props.message.streamActivity === 'waiting')
})

const thinkingLabel = computed(() => {
  if (props.message.streamError) return props.message.streamError === '已停止生成' ? '已停止生成' : '回复已中断'
  const seconds = thinkingDurationSeconds.value
  const duration = seconds === null ? '' : `（用时 ${seconds} 秒）`
  if (props.message.thinkingState === 'complete') return `已思考${duration}`
  if (props.message.thinkingState === 'error') return `思考已中断${duration}`
  if (props.message.thinkingState === 'thinking') return '思考中'
  if (props.message.streamActivity === 'waiting') return props.message.streamPhase || '等待模型继续'
  if (props.message.streamActivity === 'receiving') {
    return props.message.streamPhase || '处理中'
  }
  return props.message.reasoningContent ? '思考详情' : '运行详情'
})

const showContinuationStatus = computed(() => {
  return props.message.role === 'assistant'
    && Boolean(props.message.content)
    && (props.message.streamActivity === 'receiving' || props.message.streamActivity === 'waiting')
})

const continuationLabel = computed(() => {
  if (props.message.streamPhase) return props.message.streamPhase
  return props.message.streamActivity === 'waiting' ? '等待模型继续' : '继续推进任务'
})

const getConfidenceColor = (confidence: number) => {
  if (confidence >= 0.8) return 'var(--success)'
  if (confidence >= 0.6) return 'var(--warning)'
  return 'var(--danger)'
}

const executionToolName = (stage: string) => {
  if (stage.startsWith('tool:')) return stage.split(':')[1] || 'tool'
  return stage
}

const executionStatusTone = (status: string) => {
  const value = status.toLowerCase()
  if (['completed', 'success', 'succeeded'].includes(value)) return 'completed'
  if (['failed', 'error', 'denied'].includes(value)) return 'failed'
  if (['running', 'in_progress', 'started'].includes(value)) return 'running'
  if (['approval_required', 'pending', 'waiting', 'waiting_review'].includes(value)) return 'pending'
  if (['cancelled', 'canceled', 'stopped'].includes(value)) return 'cancelled'
  return 'neutral'
}

const executionStatusLabel = (status: string) => {
  const tone = executionStatusTone(status)
  if (tone === 'completed') return '完成'
  if (tone === 'failed') return '失败'
  if (tone === 'running') return '进行中'
  if (tone === 'pending') return '待确认'
  if (tone === 'cancelled') return '已取消'
  return status
}

const formatDuration = (durationMs: number) => {
  if (durationMs < 1000) return `${Math.max(1, Math.round(durationMs))} ms`
  return `${(durationMs / 1000).toFixed(2).replace(/\.?0+$/, '')} s`
}

const isImage = (url: string) => {
  const imageExtensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
  return imageExtensions.some(ext => url.toLowerCase().includes(ext))
}

const formatTime = (date: Date) => {
  const d = new Date(date)
  return d.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit'
  })
}
</script>

<style scoped lang="scss">
.stream-error {
  color: var(--danger, #b54735);
  font-size: 13px;
  margin: 12px 0;
}
.message-bubble {
  width: 100%;
  display: flex;
  justify-content: center;
  box-sizing: border-box;
  margin: 0;
  animation: fadeIn 180ms var(--ease-out);
  padding: 0 28px;
}

.message-bubble.user {
  /* 行宽限制为消息列（780px 内容宽 + 两侧 28px 内边距），
     让用户气泡右缘贴齐居中列而不是飞到面板最右侧 */
  width: min(100%, 836px);
  margin-inline: auto;
  justify-content: flex-end;
}

.message-content-wrapper {
  width: min(100%, 780px);
  max-width: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.message-bubble.user .message-content-wrapper {
  width: auto;
  max-width: min(72%, 560px);
  align-items: flex-end;
}

.message-content {
  padding: 0;
  border-radius: 0;
  word-wrap: break-word;
  line-height: 1.75;
  font-size: 15.5px;
  position: relative;
  transition: var(--transition);
}

.message-bubble.user .message-content {
  padding: 9px 14px;
  border: 1px solid var(--border-light);
  border-radius: 18px;
  background: var(--bg-panel);
  color: var(--text-primary);
  box-shadow: none;
}

.message-bubble.assistant .message-content {
  background: transparent;
  color: var(--text-primary);
  border: 0;
  border-radius: 0;
  box-shadow: none;
}

/* System/History Messages (Placeholder for role='system') */
.message-bubble.system {
  justify-content: center;
  margin: 16px 0;
}
.message-bubble.system .message-content {
  background-color: var(--bg-input);
  color: var(--text-secondary);
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 8px;
  border: none;
  box-shadow: none;
}
.message-bubble.system .message-avatar, 
.message-bubble.system .message-meta {
  display: none;
}

.continuation-status {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
  margin-top: 10px;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.continuation-status__pulse {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  width: 14px;
  height: 12px;
}

.continuation-status__pulse i {
  display: block;
  width: 2px;
  height: 7px;
  border-radius: 999px;
  background: var(--primary-color);
  animation: continuationSignal 1.15s ease-in-out infinite;
}

.continuation-status__pulse i:nth-child(2) {
  height: 11px;
  animation-delay: 0.14s;
}

.continuation-status__pulse i:nth-child(3) {
  height: 8px;
  animation-delay: 0.28s;
}

.continuation-status__eyebrow {
  color: var(--text-disabled);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.08em;
  white-space: nowrap;
}

.continuation-status__label {
  color: var(--text-secondary);
}

.continuation-status-enter-active,
.continuation-status-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}

.continuation-status-enter-from,
.continuation-status-leave-to {
  opacity: 0;
  transform: translateY(-3px);
}

/* Error Message Style */
.message-bubble.error {
  justify-content: center;
  margin: 16px 0;
}
.message-bubble.error .message-content {
  background-color: rgba(178, 74, 74, 0.08);
  color: var(--danger);
  font-size: 13px;
  padding: 8px 16px;
  border-radius: 8px;
  border: 1px solid rgba(178, 74, 74, 0.18);
}
.message-bubble.error .message-avatar, 
.message-bubble.error .message-meta {
  display: none;
}

/* Message Actions Area */
.message-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  margin-top: 7px;
  padding: 0;
  opacity: 0.62;
  transition: opacity 0.2s;
}

/* 保持悬停效果，但不再控制显示/隐藏 */
.message-bubble:hover .message-actions,
.message-actions:focus-within {
  opacity: 1;
}

.message-bubble.user .message-actions {
  justify-content: flex-end;
}

.action-item {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  cursor: pointer;
  color: var(--text-disabled);
  transition: var(--transition);
  background: transparent;
}

.action-item:hover {
  background: var(--bg-panel);
  color: var(--text-primary);
  transform: none;
}

.action-item.delete:hover {
  color: var(--danger);
}

.action-item .el-icon {
  font-size: 14px;
}

.message-bubble.user .action-item {
  color: var(--text-disabled);
  background: transparent;
}

.message-bubble.user .action-item:hover {
  color: var(--text-primary);
  background: var(--bg-panel);
}

.message-action-time {
  margin-left: 6px;
  color: var(--text-disabled);
  font-size: 10px;
  white-space: nowrap;
}

.message-bubble.user .message-action-time {
  order: -1;
  margin: 0 6px 0 0;
}

/* File Attachments */
.message-image-wrapper {
  position: relative;
  display: inline-block;
  cursor: zoom-in;
  border-radius: 8px;
  overflow: hidden;
}

.message-image {
  max-width: 100%;
  border-radius: 8px;
  border: 1px solid var(--border-light);
  display: block;
}

.image-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0);
  transition: background 0.2s ease;
  border-radius: 8px;
  opacity: 0;
  transition: all 0.2s ease;
}

.message-image-wrapper:hover .image-overlay {
  background: rgba(29, 36, 34, 0.24);
  opacity: 1;
}

.image-overlay .el-icon {
  color: #fff;
  font-size: 20px;
}

.file-attachment {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: color-mix(in srgb, var(--bg-card) 72%, transparent);
  border: 1px solid var(--border-light);
  border-radius: 8px;
}

.message-bubble.assistant .file-attachment {
  background: var(--bg-input);
  border-color: var(--border-light);
}

.message-text {
  white-space: pre-wrap;
}

.message-text.markdown-body {
  white-space: normal;
  line-height: 1.78;
}

.message-text.markdown-body :deep(h1),
.message-text.markdown-body :deep(h2),
.message-text.markdown-body :deep(h3),
.message-text.markdown-body :deep(h4),
.message-text.markdown-body :deep(h5),
.message-text.markdown-body :deep(h6) {
  margin: 8px 0;
  line-height: 1.4;
  font-weight: 700;
}

.message-text.markdown-body :deep(h1) { font-size: 20px; }
.message-text.markdown-body :deep(h2) { font-size: 18px; }
.message-text.markdown-body :deep(h3) { font-size: 16px; }

.message-text.markdown-body :deep(p) {
  margin: 0 0 12px;
}

.message-text.markdown-body :deep(p:last-child) {
  margin-bottom: 0;
}

.message-text.markdown-body :deep(ul),
.message-text.markdown-body :deep(ol) {
  margin: 8px 0;
  padding-left: 20px;
}

.message-text.markdown-body :deep(li) {
  margin: 4px 0;
}

.message-text.markdown-body :deep(pre) {
  margin: 10px 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: #20262b;
  color: #eef1ef;
  overflow-x: auto;
}

.message-text.markdown-body :deep(code) {
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', monospace;
  padding: 0 4px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
}

.message-text.markdown-body :deep(pre code) {
  background: transparent;
  padding: 0;
}

.message-text.markdown-body :deep(a) {
  color: var(--primary-color);
  text-decoration: underline;
  word-break: break-all;
}

/* Markdown 表格样式收敛到 global.css 的全局三线表 */

/* Inline thinking status — compact, borderless and theme-token driven */
.thinking-status {
  width: 100%;
  margin: 0 0 14px;
  color: var(--text-secondary);
}

.thinking-status__trigger,
.thinking-status__summary {
  min-height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px 3px 7px;
  border: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-card) 76%, transparent);
  color: var(--text-primary);
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
}

.thinking-status__trigger {
  cursor: pointer;
  transition: color 180ms var(--ease-out), background 180ms var(--ease-out),
    border-color 180ms var(--ease-out);
}

.thinking-status__trigger:hover {
  color: var(--primary-color);
  border-color: color-mix(in srgb, var(--primary-color) 28%, var(--border-light));
  background: color-mix(in srgb, var(--primary-color) 8%, var(--bg-card));
}

.thinking-status__trigger:focus-visible {
  outline: 2px solid var(--border-focus);
  outline-offset: 3px;
}

.thinking-status__identity {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.thinking-status__phase {
  display: inline-block;
  min-width: 7em;
}

.thinking-status__hint {
  padding-left: 7px;
  border-left: 1px solid color-mix(in srgb, var(--border-light) 80%, transparent);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 400;
  white-space: nowrap;
  opacity: 0.78;
}

.thinking-phase-enter-active,
.thinking-phase-leave-active {
  transition: opacity 160ms var(--ease-out), transform 160ms var(--ease-out);
}

.thinking-phase-enter-from {
  opacity: 0;
  transform: translateY(2px);
}

.thinking-phase-leave-to {
  opacity: 0;
  transform: translateY(-2px);
}

.thinking-status__icon {
  flex: 0 0 auto;
  color: var(--primary-color);
  font-size: 16px;
}

.thinking-status.is-thinking .thinking-status__icon {
  animation: thinkingPulse 1.5s ease-in-out infinite;
}

.thinking-status__chevron {
  margin-left: 1px;
  color: var(--text-secondary);
  font-size: 12px;
  transition: transform 180ms var(--ease-out), color 180ms var(--ease-out);
}

.thinking-status__chevron.open {
  transform: rotate(180deg);
}

.thinking-status__dots {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 1px;
}

.thinking-status__dots i {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--text-secondary);
  animation: thinkingDot 1.2s ease-in-out infinite;
}

.thinking-status__dots i:nth-child(2) { animation-delay: 140ms; }
.thinking-status__dots i:nth-child(3) { animation-delay: 280ms; }

.thinking-status__details {
  width: min(100%, 760px);
  margin: 10px 0 2px;
  padding: 14px;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: color-mix(in srgb, var(--bg-card) 90%, transparent);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.1);
  color: var(--text-secondary);
  max-height: min(68vh, 720px);
  overflow: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
}

.thinking-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 12px;
}

.thinking-meta__chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-height: 24px;
  padding: 2px 9px;
  border: 1px solid color-mix(in srgb, var(--border-light) 76%, transparent);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-panel) 72%, transparent);
  font-size: 11px;
}

.thinking-meta__label {
  color: var(--text-secondary);
}

.thinking-meta__value {
  max-width: 260px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-regular);
  font-weight: 600;
}

.thinking-section {
  margin-top: 12px;
}

.thinking-section:first-of-type {
  margin-top: 0;
}

.thinking-section__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 7px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.thinking-section__hint {
  color: var(--text-secondary);
  font-size: 10px;
  font-weight: 400;
  opacity: 0.72;
}

.thinking-status__preview {
  display: flex;
  align-items: baseline;
  gap: 8px;
  max-width: min(100%, 760px);
  margin: 6px 0 0 7px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.thinking-status__preview-label {
  flex: 0 0 auto;
  padding: 1px 5px;
  border-radius: 4px;
  background: color-mix(in srgb, var(--primary-color) 12%, transparent);
  color: var(--primary-color);
  font-size: 10px;
  line-height: 1.5;
}

.thinking-status__preview-text {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  line-height: 1.5;
}

.thinking-status__preview:hover .thinking-status__preview-text {
  color: var(--text-regular);
}

.thinking-section__toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  margin: 0 0 7px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.thinking-section__toggle-title {
  font-size: 12px;
  font-weight: 600;
}

.thinking-section__toggle .thinking-section__hint {
  margin-left: auto;
}

.thinking-section__chevron {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--text-secondary);
  transition: transform 180ms var(--ease-out);
}

.thinking-section__chevron.open {
  transform: rotate(180deg);
}

.thinking-section__link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--primary-color);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
}

.thinking-section__link:hover {
  text-decoration: underline;
}

.thinking-section__note {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 10.5px;
  line-height: 1.5;
  opacity: 0.78;
}

.thinking-empty {
  margin-top: 4px;
  padding: 9px 11px;
  border: 1px dashed color-mix(in srgb, var(--border-light) 80%, transparent);
  border-radius: 9px;
  color: var(--text-secondary);
  font-size: 11.5px;
  line-height: 1.6;
}

.thinking-details-enter-active,
.thinking-details-leave-active {
  transition: opacity 180ms var(--ease-out), transform 180ms var(--ease-out);
}

.thinking-details-enter-from,
.thinking-details-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.explanation-item {
  display: flex;
  align-items: center;
  margin-bottom: 9px;
  gap: 12px;
  font-size: 13px;
  
  &.vertical {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }
}

.explanation-label {
  color: var(--text-secondary);
  font-weight: 500;
  min-width: 60px;
}

.explanation-value {
  min-width: 0;
  color: var(--text-regular);
  overflow-wrap: anywhere;
}

.explanation-value-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.value-text {
  font-size: 12px;
  color: var(--text-regular);
}

.reasoning-content {
  width: 100%;
  max-height: 240px;
  margin: 0;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: break-word;
  tab-size: 2;
  scrollbar-width: thin;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 11.5px;
  line-height: 1.65;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--bg-panel) 72%, transparent);
  border: 1px solid color-mix(in srgb, var(--border-light) 80%, transparent);
  border-radius: 10px;
  padding: 12px 14px;
}

.reasoning-content.is-expanded {
  max-height: none;
}

.execution-summary {
  display: grid;
  gap: 0;
  width: 100%;
  max-height: 260px;
  overflow-y: auto;
  scrollbar-width: thin;
  border: 1px solid color-mix(in srgb, var(--border-light) 80%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg-panel) 56%, transparent);
}

.execution-summary__item {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 9px 11px;
  min-width: 0;
  border-top: 1px solid color-mix(in srgb, var(--border-light) 65%, transparent);
}

.execution-summary__item:first-child {
  border-top: 0;
}

.execution-summary__item:hover {
  background: color-mix(in srgb, var(--primary-color) 4%, transparent);
}

.execution-summary__dot {
  flex: 0 0 auto;
  width: 6px;
  height: 6px;
  margin-top: 6px;
  border-radius: 50%;
  background: var(--text-secondary);
}

.execution-summary__item.is-completed .execution-summary__dot {
  background: var(--success);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 16%, transparent);
}

.execution-summary__item.is-failed .execution-summary__dot {
  background: var(--danger);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--danger) 16%, transparent);
}

.execution-summary__item.is-running .execution-summary__dot,
.execution-summary__item.is-pending .execution-summary__dot {
  background: var(--warning);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--warning) 16%, transparent);
}

.execution-summary__item.is-cancelled .execution-summary__dot,
.execution-summary__item.is-neutral .execution-summary__dot {
  background: var(--text-secondary);
  opacity: 0.5;
}

.execution-summary__content {
  min-width: 0;
  flex: 1 1 auto;
}

.execution-summary__head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  min-width: 0;
}

.execution-summary__tool {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 1px 6px;
  border: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent);
  border-radius: 5px;
  background: color-mix(in srgb, var(--bg-card) 76%, transparent);
  color: var(--text-regular);
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10.5px;
  line-height: 1.5;
}

.execution-summary__status {
  flex: 0 0 auto;
  padding: 1px 6px;
  border-radius: 999px;
  font-size: 10px;
  line-height: 1.5;
  color: var(--text-secondary);
  background: color-mix(in srgb, var(--text-secondary) 9%, transparent);
}

.execution-summary__item.is-completed .execution-summary__status {
  color: var(--success);
  background: color-mix(in srgb, var(--success) 12%, transparent);
}

.execution-summary__item.is-failed .execution-summary__status {
  color: var(--danger);
  background: color-mix(in srgb, var(--danger) 12%, transparent);
}

.execution-summary__item.is-running .execution-summary__status,
.execution-summary__item.is-pending .execution-summary__status {
  color: var(--warning);
  background: color-mix(in srgb, var(--warning) 12%, transparent);
}

.execution-summary__duration {
  flex: 0 0 auto;
  margin-left: auto;
  color: var(--text-secondary);
  font-size: 10px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  opacity: 0.8;
}

.execution-summary__description {
  margin: 4px 0 0;
  color: var(--text-regular);
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: break-word;
}

.source-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  background-color: var(--primary-fade);
  border-radius: 6px;
  font-size: 12px;
  color: var(--text-regular);
  margin-right: 4px;
  margin-bottom: 4px;
  border: 1px solid var(--primary-line);
  text-decoration: none;
}

.reasoning-path {
  padding-left: 8px;
  border-left: 1px solid var(--border-light);
  margin-left: 4px;
}

.reasoning-step {
  position: relative;
  padding-bottom: 12px;
  padding-left: 12px;
  
  &:last-child {
    padding-bottom: 0;
  }
  
  .step-dot {
    position: absolute;
    left: -5px;
    top: 6px;
    width: 8px;
    height: 8px;
    background-color: var(--primary-color);
    border-radius: 50%;
  }
  
  .step-title {
    font-weight: 500;
    font-size: 13px;
    color: var(--text-color-primary);
  }
  
  .step-desc {
    font-size: 12px;
    color: var(--text-color-secondary);
    margin-top: 2px;
  }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(5px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes thinkingPulse {
  0%, 100% { opacity: 0.58; transform: scale(0.94); }
  50% { opacity: 1; transform: scale(1); }
}

@keyframes thinkingDot {
  0%, 60%, 100% { opacity: 0.28; transform: translateY(0); }
  30% { opacity: 0.9; transform: translateY(-2px); }
}

@keyframes continuationSignal {
  0%, 100% { opacity: 0.28; transform: scaleY(0.7); }
  50% { opacity: 0.95; transform: scaleY(1); }
}

@media (max-width: 900px) {
  .thinking-status__hint {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .thinking-status__icon,
  .thinking-status__dots i,
  .continuation-status__pulse i {
    animation: none !important;
  }

  .thinking-details-enter-active,
  .thinking-details-leave-active,
  .thinking-status__chevron,
  .continuation-status-enter-active,
  .continuation-status-leave-active {
    transition: none;
  }
}
</style>
