<!-- 主对话页面 — 角色快速导航（律师/教师/程序员/作家）与聊天工作台 -->
<template>
  <div class="chat-view detail-interface">
    <div
      ref="chatMainRef"
      class="chat-main"
      :class="[
        {
          'has-agent-results': isAgentMode,
          'agent-panel-collapsed': isAgentMode && agentPanelCollapsed,
          'agent-panel-resizing': agentPanelResizing,
          'workspace-mode-switching': workspaceModeSwitching,
          'hero-settling': !heroSettled
        }
      ]"
      :style="agentPanelLayoutStyle"
    >
      <section
        ref="chatPanelRef"
        class="chat-panel"
        :class="{ 'hero-mode': showHeroMode }"
        :aria-busy="isLoadingConversation || isStreamingChat"
      >
        <header v-if="!isAgentMode" class="chat-workspace-header">
          <el-icon aria-hidden="true"><ChatDotRound /></el-icon>
          <span>{{ conversationInfo.title }}</span>
        </header>
        <Transition name="context-panel-slide" :css="!workspaceModeSwitching" @after-leave="finishContextPanelClose">
          <section
            v-if="isAgentMode && contextPanelOpen"
            class="context-panel"
            :class="{ resizing: contextPanelResizing }"
            :style="{ height: `${contextPanelHeight}px` }"
            aria-label="运行上下文"
          >
            <header class="context-panel__header">
              <div class="context-panel__identity">
                <el-icon><Cpu /></el-icon>
                <strong>运行上下文</strong>
                <span>{{ contextObjective }}</span>
              </div>
              <div class="context-panel__metrics">
                <span>{{ contextStepNodes.length }} 步骤</span>
                <span>{{ contextNodes.length }} 节点</span>
                <span>{{ contextEdges.length }} 关系</span>
                <button type="button" title="收起运行上下文" aria-label="收起运行上下文" @click="setContextPanelOpen(false)">
                  <el-icon><ArrowDownBold /></el-icon>
                </button>
              </div>
            </header>

            <nav class="context-panel__tabs" aria-label="运行上下文视图">
              <button
                v-for="tab in contextTabs"
                :key="tab.key"
                type="button"
                :class="{ active: contextPanelTab === tab.key }"
                @click="contextPanelTab = tab.key"
              >
                {{ tab.label }}
                <span>{{ tab.count }}</span>
              </button>
            </nav>

            <div class="context-panel__body">
              <div v-if="!contextNodes.length" class="context-panel__empty">
                启用 Workflow 后，这里会同步展示数据血缘、执行节点和任务步骤。
              </div>

              <div v-else-if="contextPanelTab === 'lineage'" class="context-lineage">
                <div v-for="edge in contextEdges" :key="edge.edgeId" class="context-lineage__row">
                  <span class="context-node-pill">{{ contextNodeLabel(edge.sourceId) }}</span>
                  <span class="context-edge-label">{{ contextEdgeLabel(edge.edgeType) }}</span>
                  <span class="context-lineage__arrow">→</span>
                  <span class="context-node-pill target">{{ contextNodeLabel(edge.targetId) }}</span>
                </div>
                <div v-if="!contextEdges.length" class="context-panel__empty">当前蓝图暂无血缘关系。</div>
              </div>

              <div v-else-if="contextPanelTab === 'nodes'" class="context-node-grid">
                <article v-for="node in contextNodes" :key="node.nodeId" class="context-node-card">
                  <span class="context-node-card__type">{{ contextNodeTypeLabel(node.nodeType) }}</span>
                  <strong>{{ node.name || node.agentName || node.nodeId }}</strong>
                  <small>{{ node.description || node.capability || node.nodeId }}</small>
                </article>
              </div>

              <div v-else class="context-step-list">
                <article v-for="(step, index) in contextStepNodes" :key="step.nodeId" class="context-step-item">
                  <span class="context-step-item__index">{{ String(index + 1).padStart(2, '0') }}</span>
                  <div>
                    <strong>{{ step.name || step.nodeId }}</strong>
                    <small>{{ step.agentName || step.capability || '等待分配 Agent' }}</small>
                  </div>
                  <span class="context-step-item__status" :class="{ done: displayCompletedStepIds.includes(step.nodeId) }">
                    {{ displayCompletedStepIds.includes(step.nodeId) ? '已完成' : '待执行' }}
                  </span>
                </article>
                <div v-if="!contextStepNodes.length" class="context-panel__empty">当前蓝图暂无任务步骤。</div>
              </div>
            </div>

            <div
              class="context-panel__resizer"
              role="separator"
              aria-label="调整运行上下文面板高度"
              aria-orientation="horizontal"
              :aria-valuemin="CONTEXT_PANEL_MIN_HEIGHT"
              :aria-valuemax="CONTEXT_PANEL_MAX_HEIGHT"
              :aria-valuenow="contextPanelHeight"
              tabindex="0"
              title="拖动调整高度，双击恢复默认"
              @pointerdown="startContextPanelResize"
              @keydown="handleContextPanelResizeKeydown"
              @dblclick="resetContextPanelHeight"
            ><span aria-hidden="true"></span></div>
          </section>
        </Transition>

        <button
          v-if="isAgentMode && !contextPanelOpen && !contextPanelClosing"
          class="context-panel-dock"
          type="button"
          aria-label="展开运行上下文"
          @click="setContextPanelOpen(true)"
        >
          <span class="context-panel-dock__pulse" aria-hidden="true"></span>
          <strong>运行上下文</strong>
          <span>{{ contextStepNodes.length }} 步骤</span>
          <span>{{ contextNodes.length }} 节点</span>
          <span>{{ contextEdges.length }} 关系</span>
          <el-icon><ArrowDownBold /></el-icon>
        </button>

        <div class="messages-shell">
          <div class="messages" ref="messagesRef">
          <div v-if="showHeroMode" class="empty-state">
            <div
              ref="heroLogoFieldRef"
              class="hero-logo-field"
              :class="{ 'is-pressed': heroLogoPressed }"
              aria-hidden="true"
              @pointermove="handleHeroLogoPointerMove"
              @pointerleave="handleHeroLogoPointerLeave"
              @pointerdown="handleHeroLogoPointerDown"
              @pointerup="handleHeroLogoPointerUp"
              @pointercancel="handleHeroLogoPointerUp"
            >
              <svg class="hero-logo-filter-defs" aria-hidden="true" focusable="false">
                <defs>
                  <filter id="hero-logo-fluid" x="-24%" y="-24%" width="148%" height="148%" color-interpolation-filters="sRGB">
                    <feTurbulence
                      ref="heroLogoTurbulenceRef"
                      type="fractalNoise"
                      baseFrequency="0.012 0.018"
                      numOctaves="2"
                      seed="11"
                      result="hero-logo-noise"
                    />
                    <feDisplacementMap
                      ref="heroLogoDisplacementRef"
                      in="SourceGraphic"
                      in2="hero-logo-noise"
                      scale="0"
                      xChannelSelector="R"
                      yChannelSelector="B"
                    />
                  </filter>
                </defs>
              </svg>
              <img class="hero-watermark" src="/logo.webp" alt="" />
            </div>
            <h2 class="hero-greeting">{{ heroGreeting }}</h2>
          </div>

          <section v-else-if="showWorkflowHistoryDetail" class="workflow-history-detail" aria-label="Agent 历史任务详情">
            <div v-if="!activeWorkflowRun" class="workflow-history-loading" :class="{ 'is-error': workflowResultState === 'error' || workflowResultState === 'partial' }">
              <template v-if="workflowResultState === 'loading' || workflowResultState === 'idle'">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在恢复任务详情…</span>
              </template>
              <template v-else>
                <strong>任务详情暂时未能加载</strong>
                <span>{{ workflowResultError || '请重新加载任务详情。' }}</span>
                <button type="button" @click="retryWorkflowHistoryDetail">重新加载</button>
              </template>
            </div>
            <template v-else>
              <div v-if="workflowResultState === 'partial'" class="workflow-history-partial" role="status">
                <span>{{ workflowResultError }}</span>
                <button type="button" @click="retryWorkflowHistoryDetail">补充加载</button>
              </div>
              <article class="workflow-history-request">
                <header>
                  <div>
                    <span class="workflow-history-eyebrow">历史任务输入</span>
                    <h3>{{ workflowHistoryTitle }}</h3>
                  </div>
                  <div class="workflow-history-identity">
                    <span>{{ activeWorkflowRun.workflowId }}</span>
                    <code>{{ activeWorkflowRun.runId }}</code>
                  </div>
                </header>
                <pre>{{ workflowHistoryInput }}</pre>
              </article>

              <GenericArtifactPanel
                :step-outputs="workflowHistoryStepOutputs"
                :final-artifacts="workflowHistoryFinalArtifacts"
                :final-report="workflowHistoryFinalReport"
                :status="activeWorkflowStatus"
              />
            </template>
          </section>

          <div v-else class="message-list">
            <div
              v-for="msg in chatStore.messages"
              :key="msg.id"
              class="message-row"
              :class="[msg.role, { 'rail-flash': railFlashId === msg.id }]"
              :data-message-id="String(msg.id)"
              :data-role="msg.role"
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
                  modelInfo: msg.modelInfo,
                  thinkingState: msg.thinkingState,
                  streamError: msg.streamError,
                  streamActivity: msg.streamActivity,
                  streamPhase: msg.streamPhase,
                  thinkingDurationMs: msg.thinkingDurationMs,
                  reasoningContent: msg.reasoningContent,
                  requestedThinkingMode: msg.requestedThinkingMode,
                  effectiveThinkingMode: msg.effectiveThinkingMode,
                  effectiveReasoningEffort: msg.effectiveReasoningEffort,
                  reasoningTokens: msg.reasoningTokens,
                  executionSummary: msg.executionSummary
                }"
              />
            </div>
          </div>
          </div>

          <nav
            v-if="conversationRailVisible"
            ref="conversationRailRef"
            class="conversation-rail"
            aria-label="对话导航"
            @pointerleave="handleRailLeave"
          >
            <div class="conversation-rail__ticks">
              <button
                v-for="item in conversationRailItems"
                :key="item.id"
                type="button"
                class="conversation-rail__tick"
                :class="{ 'is-active': item.id === activeRailTickId }"
                :aria-label="`跳转到第 ${item.round} 轮对话`"
                @click="jumpToRailInteraction(item.id)"
                @pointerenter="handleRailHover(item, $event)"
              ></button>
            </div>
            <Transition name="rail-preview">
              <div
                v-if="railHoverItem"
                class="conversation-rail__preview"
                :style="{ top: `${railPreviewTop}px` }"
              >
                <span class="conversation-rail__preview-round">第 {{ railHoverItem.round }} 轮 · 提问预览</span>
                <p>{{ railHoverItem.preview }}</p>
              </div>
            </Transition>
          </nav>
        </div>

        <div ref="composerRef" class="composer" :style="{ bottom: composerDockOffset }">
          <div v-if="isSubmittingWorkflow || activeWorkflowRunId" class="chat-workflow-progress">
            <WorkflowProgressBar
              :progress="workflowProgressState.progress.value"
              :loading="isSubmittingWorkflow || workflowProgressState.isLoading.value"
              :sync-error="workflowProgressState.syncError.value"
              variant="compact"
            />
            <AgentOsRunSummaryCard
              :progress="workflowProgressState.progress.value"
              :run="activeWorkflowRun"
              :view="activeAcgView"
              :events="activeAcgAuditEvents"
            />
            <label v-if="navigationBindings.length > 1">选择 Run
              <select aria-label="选择任务 Run" :value="activeWorkflowRunId || ''" @change="selectNavigationRun">
                <option v-for="binding in navigationBindings" :key="binding.runId" :value="binding.runId">{{ binding.runId }}</option>
              </select>
            </label>
            <button v-if="verifiedNavigationRun" type="button" :disabled="handoffPending" @click="enterSelectedWorkbench">打开所选 Run 的 Workbench</button>
            <p v-if="handoffError" role="alert">{{ handoffError }}</p>
          </div>

          <p v-if="workflowStartError" class="chat-workflow-error" role="alert">
            {{ workflowStartError }}
          </p>

          <FormalExecutionControls
            v-if="chatFormalRun"
            :key="`${currentConversationId}:${chatFormalRun.runId}`"
            :run="chatFormalRun" :run-id="chatFormalRun.runId" :mission-id="chatFormalRun.missionId"
            :historical="chatFormalHistorical" :can-cancel="false" :cancel-pending="false" embedded
            @refresh="handleChatReviewConflict" @succeeded="handleFormalSucceeded"
          />
          <div v-if="dispatchPrompt" role="status" class="chat-workflow-progress">
            <p>任务已正式派发，服务端已接受执行命令。是否切换到 Workbench 查看运行过程？</p>
            <button type="button" :disabled="handoffPending" @click="enterDispatchedWorkbench">进入 Workbench</button>
            <button type="button" @click="dispatchPrompt = null">稍后</button>
          </div>
          <WorkflowReviewPanel
            v-if="!chatFormalRun && activeWorkflowRunId && activeWorkflowStatus === 'waiting_review'"
            class="chat-workflow-review"
            :run-id="activeWorkflowRunId"
            :progress="workflowProgressState.progress.value"
            :run="activeWorkflowRun"
            compact
            @reviewed="handleChatWorkflowReviewed"
            @conflict="handleChatReviewConflict"
          />

          <div
            v-if="activeWorkflowRunId && !isAgentMode"
            class="workflow-run-strip"
            :class="activeWorkflowStatus"
          >
            <span class="workflow-run-strip__state">
              <span class="workflow-run-strip__dot" aria-hidden="true"></span>
              {{ activeWorkflowStatusLabel }}
            </span>
            <code :title="activeWorkflowRunId">{{ activeWorkflowRunId }}</code>
            <span class="workflow-run-strip__workflow">{{ activeWorkflowRun?.workflowId || activeWorkflowBinding?.workflowId || 'WorkflowRun' }}</span>
            <div class="workflow-run-strip__actions">
              <button type="button" @click="openActiveWorkflowOperations">
                <span>查看 ACG</span>
                <el-icon><DArrowRight /></el-icon>
              </button>
              <button type="button" @click="openActiveWorkflowConsole">
                <span>运行控制</span>
                <el-icon><DArrowRight /></el-icon>
              </button>
            </div>
          </div>

          <div class="composer-missions" :class="{ 'is-conversation': !showHeroMode }">
            <button v-if="pendingLaunchForView" type="button" :disabled="isSubmittingWorkflow" @click="resumePendingConversationLaunch">核对并恢复原提交</button>
            <NativeWorkspacePicker class="composer-missions__workspace" />
          </div>

          <div class="composer-card">
            <el-input
              v-model="inputText"
              type="textarea"
              :rows="1"
              :autosize="{ minRows: 1, maxRows: 6 }"
              resize="none"
              :placeholder="$t(isAgentMode ? 'chat.placeholder' : 'chat.conversationPlaceholder')"
              @keydown="handleKeydown"
            />
              <div class="composer-footer">
                <div class="left-actions">
                <div ref="composerToolsAnchorRef" class="composer-tools-anchor">
                  <button
                    class="composer-icon-action composer-tools-toggle"
                    :class="{ active: composerToolsOpen }"
                    type="button"
                    aria-label="更多输入工具"
                    aria-haspopup="menu"
                    :aria-expanded="composerToolsOpen"
                    title="更多输入工具"
                    @click="toggleComposerTools"
                  >
                    <el-icon><Plus /></el-icon>
                  </button>
                  <Transition name="composer-tools-pop">
                    <div v-if="composerToolsOpen" class="composer-tools-menu" role="menu" aria-label="输入工具">
                      <button class="composer-tools-menu__item" type="button" role="menuitem" @click="openComposerFileManager">
                        <el-icon><UploadFilled /></el-icon>
                        <span>添加文件</span>
                      </button>
                      <div v-if="!isAgentMode" class="composer-tools-menu__runtime">
                        <span class="composer-tools-menu__label">模型设置</span>
                        <ModelRuntimeControls compact />
                      </div>
                    </div>
                  </Transition>
                </div>
                <PermissionSelector v-if="isAgentMode" />
                <button
                  v-if="isAgentMode"
                  class="composer-acg-toggle"
                  :class="{ active: workflowPanelOpen }"
                  type="button"
                  :aria-pressed="workflowPanelOpen"
                  :title="workflowPanelOpen ? '收起 ACG 拓扑' : '展开 ACG 拓扑'"
                  @click="toggleWorkflowPanel"
                >
                  <el-icon><Share /></el-icon>
                  <span>ACG</span>
                </button>
                <el-tooltip v-if="contextUsage.visible" placement="top" :show-after="200">
                  <template #content>
                    <div class="context-usage-tip">
                      <div>上下文窗口</div>
                      <div>{{ contextUsage.percent }}% 已用</div>
                      <div>已用 {{ contextUsage.usedLabel }}，共 {{ contextUsage.windowLabel }}</div>
                    </div>
                  </template>
                  <button
                    class="context-usage"
                    :class="contextUsage.level"
                    type="button"
                    title="上下文窗口用量"
                  >
                    {{ contextUsage.percent }}%
                  </button>
                </el-tooltip>
              </div>
              <div class="right-actions">
                <ModelRuntimeControls composer />
                <span v-if="inputText.length" class="word-count" :class="{ warning: inputText.length > 500 }">
                  {{ inputText.length }} 字
                </span>
                <button
                  class="composer-icon-action"
                  type="button"
                  :class="{ active: isRecording }"
                  :aria-label="isRecording ? '停止录音' : '语音输入'"
                  :title="isRecording ? '停止录音' : '语音输入'"
                  @click="isRecording ? stopVoiceInput() : startVoiceInput()"
                >
                  <el-icon><Microphone /></el-icon>
                </button>
                <el-button v-if="inputText.length > 500" text @click="autoSegment">自动分段</el-button>
                <el-button
                  v-if="isStreamingChat"
                  class="composer-cancel"
                  type="danger"
                  @click="cancelMessageStream"
                >
                  <span>停止</span>
                </el-button>
                <el-button class="composer-send" type="primary" :disabled="isSendDisabled" @click="sendMessage">
                  <el-icon v-if="!loading"><ArrowUp /></el-icon>
                  <el-icon v-else class="is-loading"><Loading /></el-icon>
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <Transition name="workflow-acg-slide" :css="!workspaceModeSwitching">
          <section
            v-if="isAgentMode && workflowPanelOpen"
            class="workflow-acg-panel"
            :class="{ resizing: workflowPanelResizing }"
            :style="{ height: `${workflowPanelHeight}px` }"
            aria-label="ACG 动态拓扑"
          >
            <div
              class="workflow-panel-resizer"
              role="separator"
              aria-label="调整 ACG 拓扑面板高度"
              aria-orientation="horizontal"
              :aria-valuemin="WORKFLOW_PANEL_MIN_HEIGHT"
              :aria-valuemax="getWorkflowPanelHardMaxHeight()"
              :aria-valuenow="workflowPanelHeight"
              tabindex="0"
              title="拖动调整高度，双击恢复默认"
              @pointerdown="startWorkflowPanelResize"
              @keydown="handleWorkflowPanelResizeKeydown"
              @dblclick="resetWorkflowPanelHeight"
            >
              <span aria-hidden="true"></span>
            </div>
            <AcgTopologyGraph
              :blueprint="displayAcgBlueprint"
              :completed-step-ids="displayCompletedStepIds"
              :step-states="activeAcgView?.stepStates"
              collapsible
              @collapse="setWorkflowPanelOpen(false)"
            />
            <RuntimeAuditTimeline
              v-if="activeAcgView"
              class="chat-runtime-timeline"
              :events="activeAcgAuditEvents"
              :patch-refs="[]"
              :max-items="8"
            />
            <div v-else class="workflow-audit-empty">
              <span class="workflow-audit-empty__badge" aria-hidden="true"><el-icon><Clock /></el-icon></span>
              <p class="workflow-audit-empty__title">暂无运行审计事件</p>
              <p class="workflow-audit-empty__hint">启动工作流后，这里会按时间同步 Trace、恢复、Checkpoint、Review 与 GraphPatch 引用。</p>
            </div>
            <div v-if="isLoadingWorkflowResult && !activeAcgView" class="workflow-acg-loading">正在加载动态拓扑…</div>
          </section>
        </Transition>
        <button
          v-if="isAgentMode && !workflowPanelOpen"
          class="workflow-acg-dock"
          :class="{ idle: !hasActiveWorkflow }"
          type="button"
          aria-label="展开 ACG 动态拓扑"
          @click="setWorkflowPanelOpen(true)"
        >
          <span class="workflow-acg-dock__pulse" aria-hidden="true"></span>
          <span>ACG 动态拓扑</span>
          <span class="workflow-acg-dock__meta">
            {{ hasActiveWorkflow ? `${displayAcgBlueprint?.nodes.length || 0} 节点` : '等待任务' }}
          </span>
          <el-icon><ArrowUp /></el-icon>
        </button>
      </section>

      <Transition name="agent-panel-slide">
        <aside
          v-if="isAgentMode"
          class="agent-panel"
          :class="{ collapsed: agentPanelCollapsed, resizing: agentPanelResizing }"
        >
          <div
            v-if="!agentPanelCollapsed"
            class="agent-panel-resizer"
            role="separator"
            aria-label="调整右侧工作台宽度"
            aria-orientation="vertical"
            :aria-valuemin="AGENT_PANEL_MIN_WIDTH"
            :aria-valuemax="AGENT_PANEL_MAX_WIDTH"
            :aria-valuenow="agentPanelWidth"
            tabindex="0"
            title="拖动调整宽度，双击恢复默认"
            @pointerdown="startAgentPanelResize"
            @keydown="handleAgentPanelResizeKeydown"
            @dblclick="resetAgentPanelWidth"
          ></div>

          <div class="agent-panel-toggle-row">
            <button
              class="agent-panel-toggle"
              type="button"
              :aria-label="agentPanelCollapsed ? '展开右侧工作台' : '收起右侧工作台'"
              :title="agentPanelCollapsed ? '展开右侧工作台' : '收起右侧工作台'"
              @click="agentPanelCollapsed = !agentPanelCollapsed"
            >
              <el-icon>
                <DArrowLeft v-if="agentPanelCollapsed" />
                <DArrowRight v-else />
              </el-icon>
              <span v-if="!agentPanelCollapsed">收起</span>
            </button>
          </div>

          <div v-if="agentPanelCollapsed" class="agent-panel-rail" aria-hidden="true">
            <span class="agent-panel-rail-icon">
              <el-icon><component :is="agentIcon" /></el-icon>
            </span>
          </div>

          <div ref="agentPanelContentRef" v-show="!agentPanelCollapsed" class="agent-panel-content">
            <AcgRunInspector
              :run-id="activeWorkflowRunId"
              :status="activeWorkflowStatus"
              :status-label="activeWorkflowStatusLabel"
              :run="activeWorkflowRun"
              :view="activeAcgView"
              :progress="workflowProgressState.progress.value"
              :blueprint="displayAcgBlueprint"
              :loading="isSubmittingWorkflow || isLoadingWorkflowResult || workflowProgressState.isLoading.value"
              @open-acg="openActiveWorkflowOperations"
              @open-console="openActiveWorkflowConsole"
            />
          </div>
      </aside>
      </Transition>

      <!-- Chat 模式右侧停靠信息栏：ZCode/DSH 式可拖宽、可收起、宽度持久化 -->
      <aside
        v-if="!isAgentMode"
        class="chat-info-dock"
        :class="{ collapsed: chatInfoCollapsed, resizing: chatInfoResizing }"
        :style="{ width: `${chatInfoCollapsed ? CHAT_INFO_COLLAPSED_WIDTH : effectiveChatInfoWidth}px` }"
        aria-label="对话信息"
      >
        <div
          v-if="!chatInfoCollapsed"
          class="chat-info-dock__resizer"
          role="separator"
          aria-label="调整信息栏宽度"
          aria-orientation="vertical"
          :aria-valuemin="CHAT_INFO_MIN_WIDTH"
          :aria-valuemax="chatInfoMaxWidth"
          :aria-valuenow="effectiveChatInfoWidth"
          tabindex="0"
          title="拖动调整宽度，双击恢复默认"
          @pointerdown="startChatInfoResize"
          @keydown="handleChatInfoResizeKeydown"
          @dblclick="resetChatInfoWidth"
        ><span aria-hidden="true"></span></div>

        <template v-if="!chatInfoCollapsed">
          <header class="chat-info-dock__header">
            <span class="chat-info-dock__eyebrow">对话信息</span>
            <button
              type="button"
              class="chat-info-dock__collapse"
              aria-label="收起对话信息栏"
              title="收起对话信息栏"
              @click="setChatInfoCollapsed(true)"
            >
              <el-icon><DArrowRight /></el-icon>
            </button>
          </header>

          <div class="chat-info-card">
            <strong class="chat-info-card__title" :title="conversationInfo.title">{{ conversationInfo.title }}</strong>

            <dl class="chat-info-card__metrics">
              <div class="chat-info-card__row">
                <dt>模型</dt>
                <dd :title="conversationInfo.model">{{ conversationInfo.model }}</dd>
              </div>
              <div class="chat-info-card__row">
                <dt>消息</dt>
                <dd>{{ conversationInfo.messageLabel }}</dd>
              </div>
              <div v-if="contextUsage.visible" class="chat-info-card__row">
                <dt>上下文</dt>
                <dd :title="`已用 ${contextUsage.usedLabel}，共 ${contextUsage.windowLabel}`">
                  {{ contextUsage.percent }}% · {{ contextUsage.usedLabel }} / {{ contextUsage.windowLabel }}
                </dd>
              </div>
              <div class="chat-info-card__row">
                <dt>累计 Token</dt>
                <dd>{{ conversationInfo.tokensLabel }}</dd>
              </div>
              <div v-if="conversationInfo.createdAtLabel" class="chat-info-card__row">
                <dt>开始</dt>
                <dd>{{ conversationInfo.createdAtLabel }}</dd>
              </div>
              <div v-if="conversationInfo.updatedAtLabel" class="chat-info-card__row">
                <dt>最近更新</dt>
                <dd>{{ conversationInfo.updatedAtLabel }}</dd>
              </div>
            </dl>

            <template v-if="conversationInfo.sources.length">
              <div class="chat-info-card__rule" role="separator"></div>
              <p class="chat-info-card__section">来源 <span>{{ conversationInfo.sources.length }}</span></p>
              <ul class="chat-info-card__sources">
                <li v-for="source in conversationInfo.sources" :key="source.key" :title="source.label">
                  <el-icon aria-hidden="true"><Link /></el-icon>
                  <span>{{ source.label }}</span>
                </li>
              </ul>
            </template>
          </div>
        </template>

        <div v-else class="chat-info-dock__rail">
          <button
            type="button"
            class="chat-info-dock__expand"
            aria-label="展开对话信息栏"
            title="展开对话信息栏"
            @click="setChatInfoCollapsed(false)"
          >
            <el-icon><DArrowLeft /></el-icon>
          </button>
        </div>
      </aside>
    </div>

    <footer v-if="!isAgentMode" class="chat-workspace-status" aria-label="对话状态">
      <span>{{ isStreamingChat ? '正在回复' : isLoadingConversation ? '正在加载对话' : 'Chat' }}</span>
      <span>{{ conversationInfo.messageLabel }}</span>
      <span class="chat-workspace-status__model">{{ conversationInfo.model }}</span>
    </footer>
    <FileManager v-model="showFileManager" @fileSelected="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { DOCK_RIGHT_DEFAULT, useDockedWorkspaceGeometry } from '@/composables/useDockedWorkspaceGeometry'
import axios from 'axios'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDownBold,
  ArrowUp,
  Clock,
  Cpu,
  ChatDotRound,
  DArrowLeft,
  DArrowRight,
  Link,
  Loading,
  Microphone,
  Plus,
  Share,
  UploadFilled
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import MessageBubble from '@/components/MessageBubble.vue'
import ModelRuntimeControls from '@/components/ModelRuntimeControls.vue'
import NativeWorkspacePicker from '@/components/platform/NativeWorkspacePicker.vue'
import PermissionSelector from '@/components/PermissionSelector.vue'
import FormalExecutionControls from '@/components/workspace/FormalExecutionControls.vue'
import type { FormalOperationSuccess } from '@/features/acg/formalControl'
import { conversationWorkbenchTarget } from '@/features/workspace/navigation'
const FileManager = defineAsyncComponent(() => import('@/components/FileManager.vue').then(module => module.default))
const AcgTopologyGraph = defineAsyncComponent(() => import('@/components/agentos/AcgTopologyGraph.vue'))
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
const WorkflowReviewPanel = defineAsyncComponent(() => import('@/components/agentos/WorkflowReviewPanel.vue').then(module => module.default))
import AgentOsRunSummaryCard from '@/components/agentos/AgentOsRunSummaryCard.vue'
const RuntimeAuditTimeline = defineAsyncComponent(() => import('@/components/agentos/RuntimeAuditTimeline.vue').then(module => module.default))
const AcgRunInspector = defineAsyncComponent(() => import('@/components/agentos/AcgRunInspector.vue').then(module => module.default))
const GenericArtifactPanel = defineAsyncComponent(() => import('@/features/acg/GenericArtifactPanel.vue').then(module => module.default))
import {
  agentosApi,
  type AcgView,
  type WorkflowRun
} from '@/services/api/agentos'
import type { WorkflowProgress } from '@/services/api/workflow'
import { workflowApi } from '@/services/api/workflow'
import { conversationApi, type Conversation } from '@/services/api/conversation'
import { useChatStore, type ChatWorkflowBinding, type Message } from '@/stores/chat'
import { useChatWorkflowPresentation } from '@/composables/useChatWorkflowPresentation'
import { useWorkflowProgress } from '@/composables/useWorkflowProgress'
import { setConversationWorkspace } from '@/utils/conversationWorkspace'
import { wasErrorUserNotified } from '@/utils/request'
import { plainMissionTitle } from '@/utils/missionTitle'
import { loadModelSettings } from '@/config/modelSettings'
import { belongsToConversation, contextQuery, conversationBindings, isTerminalRunStatus, runMatchesSelection, selectSessionRun } from '@/features/workspace/session'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const chatStore = useChatStore()
const createClientRequestId = (): string => {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, byte => byte.toString(16).padStart(2, '0'))
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`
}
type WorkspaceMode = 'agent' | 'chat'
const WORKSPACE_MODE_KEY = 'layout.workspace_mode'
const DRAFT_CONVERSATION_KEY = 'chat.workflow_draft_conversation_id'
const draftConversationId = ref(
  localStorage.getItem(DRAFT_CONVERSATION_KEY) || (route.query.contextId || route.query.runId || route.query.missionId || chatStore.contextId ? '' : `draft:${createClientRequestId()}`)
)
if (draftConversationId.value) localStorage.setItem(DRAFT_CONVERSATION_KEY, draftConversationId.value)
let sendingDraftId: string | null = null
let composerGeneration = 0
let viewActive = true
let viewSuspended = false
let savedScrollTop = 0
const isSameConversation = (owner: string, target: string) => owner === target || (
  Boolean(owner && target) && conversationBindings(chatStore.workflowBindings, owner)
    .some(binding => belongsToConversation(binding, target))
)
const isConversationVisible = (owner = currentConversationId.value) => {
  const visibleRoute = router.currentRoute.value
  if (!viewActive || visibleRoute.path !== '/chat' || visibleRoute.query.newConversation === '1') return false
  const context = typeof visibleRoute.query.contextId === 'string' ? visibleRoute.query.contextId.trim() : ''
  return isSameConversation(owner, currentConversationId.value)
    && isSameConversation(owner, context || chatStore.contextId || draftConversationId.value)
}
const ownsComposerRequest = (owner: string, generation: number) =>
  generation === composerGeneration && isSameConversation(owner, currentConversationId.value)
  && (router.currentRoute.value.path !== '/chat' || isConversationVisible(owner))
let selectedConversationId = ''
// A single read result is handed to the existing detail loader, avoiding a second GET on restoration.
let restoredRunDetail: WorkflowRun | null = null
const workspaceMode = ref<WorkspaceMode>(
  route.query.workspace === 'agent' || localStorage.getItem(WORKSPACE_MODE_KEY) === 'agent'
    ? 'agent'
    : 'chat'
)
const workspaceModeSwitching = ref(false)

const inputText = ref('')
const loading = ref(false)
const showFileManager = ref(false)
const isRecording = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const composerRef = ref<HTMLElement | null>(null)
const chatPanelRef = ref<HTMLElement | null>(null)
const chatMainRef = ref<HTMLElement | null>(null)
const heroLogoFieldRef = ref<HTMLElement | null>(null)
const heroLogoTurbulenceRef = ref<SVGFETurbulenceElement | null>(null)
const heroLogoDisplacementRef = ref<SVGFEDisplacementMapElement | null>(null)
const heroLogoPressed = ref(false)
const isNearBottom = ref(true)
const pendingMessageCount = ref(0)
const AGENT_PANEL_COLLAPSED_KEY = 'chat.agent_panel_collapsed'
const AGENT_PANEL_WIDTH_KEY = 'chat.agent_panel_width'
const AGENT_PANEL_DEFAULT_WIDTH = 340
const AGENT_PANEL_MIN_WIDTH = 280
const AGENT_PANEL_MAX_WIDTH = 520
const WORKFLOW_PANEL_HEIGHT_KEY = 'chat.workflow_panel_height'
const WORKFLOW_PANEL_OPEN_KEY = 'chat.workflow_panel_open_v2'
const WORKFLOW_PANEL_DEFAULT_HEIGHT = 280
const WORKFLOW_PANEL_MIN_HEIGHT = 180
const CONTEXT_PANEL_HEIGHT_KEY = 'chat.context_panel_height'
const CONTEXT_PANEL_OPEN_KEY = 'chat.context_panel_open'
const CONTEXT_PANEL_DEFAULT_HEIGHT = 250
const CONTEXT_PANEL_MIN_HEIGHT = 170
const CONTEXT_PANEL_MAX_HEIGHT = 420
const agentPanelCollapsed = ref(localStorage.getItem(AGENT_PANEL_COLLAPSED_KEY) === '1')
const storedAgentPanelWidth = Number(localStorage.getItem(AGENT_PANEL_WIDTH_KEY))
const agentPanelWidth = ref(
  Number.isFinite(storedAgentPanelWidth) && storedAgentPanelWidth >= AGENT_PANEL_MIN_WIDTH && storedAgentPanelWidth <= AGENT_PANEL_MAX_WIDTH
    ? storedAgentPanelWidth
    : AGENT_PANEL_DEFAULT_WIDTH
)
const agentPanelResizing = ref(false)
// —— Chat 模式右侧停靠信息栏（ZCode/DSH 式：拖宽 + 收起 + 持久化）——
const CHAT_INFO_COLLAPSED_KEY = 'chat.chat_info_collapsed'
const CHAT_INFO_WIDTH_KEY = 'chat.chat_info_width'
const CHAT_INFO_DEFAULT_WIDTH = DOCK_RIGHT_DEFAULT
const CHAT_INFO_MIN_WIDTH = 280
const CHAT_INFO_MAX_WIDTH = 960
const CHAT_INFO_COLLAPSED_WIDTH = 44
const CHAT_INFO_MIN_CONVERSATION_WIDTH = 560
const chatInfoCollapsed = ref(localStorage.getItem(CHAT_INFO_COLLAPSED_KEY) === '1')
const dockGeometry = useDockedWorkspaceGeometry()
const chatInfoWidth = dockGeometry.rightWidth
const chatInfoResizing = ref(false)
const chatInfoViewportWidth = ref(window.innerWidth)
const chatInfoMainWidth = ref(0)
let chatInfoResizeObserver: ResizeObserver | null = null
const storedWorkflowPanelHeight = Number(localStorage.getItem(WORKFLOW_PANEL_HEIGHT_KEY))
const workflowPanelHeight = ref(
  Number.isFinite(storedWorkflowPanelHeight) && storedWorkflowPanelHeight >= WORKFLOW_PANEL_MIN_HEIGHT
    ? storedWorkflowPanelHeight
    : WORKFLOW_PANEL_DEFAULT_HEIGHT
)
const workflowPanelResizing = ref(false)
const workflowPanelOpen = ref(localStorage.getItem(WORKFLOW_PANEL_OPEN_KEY) === '1')
const storedContextPanelHeight = Number(localStorage.getItem(CONTEXT_PANEL_HEIGHT_KEY))
const contextPanelHeight = ref(
  Number.isFinite(storedContextPanelHeight) && storedContextPanelHeight >= CONTEXT_PANEL_MIN_HEIGHT && storedContextPanelHeight <= CONTEXT_PANEL_MAX_HEIGHT
    ? storedContextPanelHeight
    : CONTEXT_PANEL_DEFAULT_HEIGHT
)
const contextPanelOpen = ref(localStorage.getItem(CONTEXT_PANEL_OPEN_KEY) === '1')
const contextPanelClosing = ref(false)
const contextPanelResizing = ref(false)
const contextPanelTab = ref<'lineage' | 'nodes' | 'steps'>('lineage')
const activeWorkflowRunId = ref('')
const activeWorkflowBinding = ref<ChatWorkflowBinding | null>(null)
const activeWorkflowRun = ref<WorkflowRun | null>(null)
const activeAcgView = ref<AcgView | null>(null)
const isSubmittingWorkflow = ref(false)
const isLoadingWorkflowResult = ref(false)
type WorkflowResultState = 'idle' | 'loading' | 'ready' | 'partial' | 'error'
type WorkflowResultCacheEntry = { run?: WorkflowRun; view?: AcgView }
const workflowResultState = ref<WorkflowResultState>('idle')
const workflowResultError = ref<string | null>(null)
const workflowStartError = ref<string | null>(null)
const currentConversationId = computed(() => {
  if (route.query.newConversation === '1') return ''
  const routeContextId = typeof route.query.contextId === 'string' ? route.query.contextId.trim() : ''
  return routeContextId || chatStore.contextId || draftConversationId.value
})
const navigationBindings = computed(() => conversationBindings(chatStore.workflowBindings, currentConversationId.value)
  .filter(binding => !binding.invalidAt))
const selectNavigationRun = (event: Event) => {
  const binding = navigationBindings.value.find(item => item.runId === (event.target as HTMLSelectElement).value)
  if (binding) void router.push({ path: '/chat', query: { ...route.query, missionId: binding.missionId, runId: binding.runId } })
}
const verifiedNavigationRun = computed(() => {
  const run = activeWorkflowRun.value
  if (!run || run.runId !== activeWorkflowRunId.value || !isConversationVisible()) return null
  const matches = conversationBindings(chatStore.workflowBindings, currentConversationId.value)
    .filter(binding => !binding.invalidAt && binding.runId === run.runId)
  const owners = new Set(Object.values(chatStore.workflowBindings).flat().filter(binding =>
    !binding.invalidAt && binding.runId === run.runId).map(binding => `${binding.conversationId}\u0000${binding.missionId}`))
  return owners.size === 1 && matches.length === 1 && matches[0].missionId === run.missionId ? run : null
})
const chatFormalRun = computed(() => verifiedNavigationRun.value?.formalControl ? verifiedNavigationRun.value : null)
const chatFormalHistorical = computed(() => Boolean(chatFormalRun.value?.lineage?.supersededByRunId)
  || ['completed', 'succeeded', 'failed', 'cancelled', 'superseded'].includes(chatFormalRun.value?.status || ''))
const dispatchPrompt = ref<(FormalOperationSuccess & { conversationId: string }) | null>(null)
const handoffPending = ref(false)
const handoffError = ref('')
const promptedDispatches = new Set<string>()
watch([currentConversationId, activeWorkflowRunId], () => {
  handoffGeneration++
  dispatchPrompt.value = null
  handoffPending.value = false
  handoffError.value = ''
}, { flush: 'sync' })
const handleFormalSucceeded = (event: FormalOperationSuccess) => {
  const run = chatFormalRun.value
  if (!run || chatFormalHistorical.value || event.action !== 'dispatch' || !event.dispatchId
    || !['ACCEPTED', 'IDEMPOTENT_REPLAY'].includes(event.status)
    || run.runId !== event.runId || run.missionId !== event.missionId) return
  const key = `agentos.chat.dispatch-prompt.v1:${event.runId}:${event.dispatchId}`
  if (promptedDispatches.has(key)) return
  try { if (sessionStorage.getItem(key)) return; sessionStorage.setItem(key, '1') } catch { /* local dedup remains available */ }
  promptedDispatches.add(key)
  handoffError.value = ''
  dispatchPrompt.value = { ...event, conversationId: currentConversationId.value }
}
let handoffGeneration = 0
const enterDispatchedWorkbench = () => enterSelectedWorkbench()
const enterSelectedWorkbench = async () => {
  const run = verifiedNavigationRun.value
  if (!run || handoffPending.value) return
  const prompt = { conversationId: currentConversationId.value, runId: run.runId, missionId: run.missionId }
  const generation = ++handoffGeneration
  const sourceRoute = route.fullPath
  handoffPending.value = true
  handoffError.value = ''
  try {
    const index = chatStore.workflowBindings
    const target = await conversationWorkbenchTarget(index, currentConversationId.value,
      activeWorkflowRunId.value, agentosApi.getWorkflowRun)
    if (generation !== handoffGeneration || sourceRoute !== route.fullPath || !isConversationVisible(prompt.conversationId)
      || currentConversationId.value !== prompt.conversationId || activeWorkflowRunId.value !== prompt.runId) return
    if (index !== chatStore.workflowBindings || !target || target.query.runId !== prompt.runId
      || !verifiedNavigationRun.value || verifiedNavigationRun.value.missionId !== prompt.missionId) {
      handoffError.value = '无法验证当前对话与任务归属，请刷新后重试。'
      return
    }
    await router.push(target)
  } catch {
    if (generation === handoffGeneration) handoffError.value = '无法进入 Workbench，请核对任务归属后重试。'
  } finally { if (generation === handoffGeneration) handoffPending.value = false }
}
const isStreamingChat = computed(() => chatStore.isStreaming)
const cancelMessageStream = () => {
  const cancel = (chatStore as typeof chatStore & { cancelMessageStream?: () => unknown }).cancelMessageStream
  if (typeof cancel === 'function') void cancel()
}
const isLoadingConversation = computed(() => chatStore.isLoadingConversation)
const workflowProgressState = useWorkflowProgress({
  intervalMs: 2000,
  onProgressChanged: handleWorkflowProgressChanged,
  onTerminal: handleWorkflowTerminal
})
const hasActiveWorkflow = computed(() => Boolean(activeWorkflowRunId.value))
const showWorkflowHistoryDetail = computed(() => (
  Boolean(activeWorkflowRunId.value) && (
    chatStore.messages.length === 0
    || (
      isAgentMode.value
      && (
        workflowProgressState.progress.value?.phase === 'completed'
        || workflowProgressState.progress.value?.status === 'completed'
      )
      && !['idle', 'loading'].includes(workflowResultState.value)
    )
  )
))
const showHeroMode = computed(() => {
  return chatStore.messages.length === 0
    && !isSubmittingWorkflow.value
    && !activeWorkflowRunId.value
})
const composerDockOffset = computed(() => {
  if (showHeroMode.value) return 'auto'
  if (!isAgentMode.value) return '0px'
  return workflowPanelOpen.value ? `${workflowPanelHeight.value}px` : '30px'
})
const composerHeight = ref(180)
const composerReservedSpace = computed(() => {
  if (showHeroMode.value) return 0
  const dockHeight = isAgentMode.value
    ? (workflowPanelOpen.value ? workflowPanelHeight.value : 30)
    : 0
  return Math.ceil(composerHeight.value + dockHeight + 24)
})
const agentPanelLayoutStyle = computed(() => ({
  '--agent-panel-width': `${agentPanelWidth.value}px`,
  '--composer-clearance': `${composerReservedSpace.value}px`
}))
let agentPanelResizeStartX = 0
let agentPanelResizeStartWidth = AGENT_PANEL_DEFAULT_WIDTH
let workflowPanelResizeStartY = 0
let workflowPanelResizeStartHeight = WORKFLOW_PANEL_DEFAULT_HEIGHT
let workflowPanelResizeMaxHeight = Number.MAX_SAFE_INTEGER
let contextPanelResizeStartY = 0
let contextPanelResizeStartHeight = CONTEXT_PANEL_DEFAULT_HEIGHT
let workflowResultController: AbortController | null = null
let workflowResultGeneration = 0
let workflowResultInFlight: { runId: string; promise: Promise<boolean> } | null = null
let workflowResultRetryTimer: ReturnType<typeof window.setTimeout> | null = null
let workflowResultRetryCount = 0
let conversationGeneration = 0
const terminalResultLoaded = new Set<string>()
const workflowResultCache = new Map<string, WorkflowResultCacheEntry>()
let composerResizeObserver: ResizeObserver | undefined
const agentPanelContentRef = ref<HTMLElement | null>(null)

const {
  displayAcgBlueprint,
  displayCompletedStepIds,
  activeAcgAuditEvents,
  contextNodes,
  contextEdges,
  contextStepNodes,
  contextObjective,
  workflowHistoryInput,
  workflowHistoryTitle,
  workflowHistoryStepOutputs,
  workflowHistoryFinalArtifacts,
  workflowHistoryFinalReport,
  activeWorkflowStatus,
  activeWorkflowStatusLabel,
  contextTabs,
  contextNodeLabel,
  contextEdgeLabel,
  contextNodeTypeLabel
} = useChatWorkflowPresentation({
  activeWorkflowRun,
  activeAcgView,
  activeWorkflowRunId,
  progress: workflowProgressState.progress,
  messages: computed(() => chatStore.messages)
})
const clampAgentPanelWidth = (width: number) => {
  return Math.min(AGENT_PANEL_MAX_WIDTH, Math.max(AGENT_PANEL_MIN_WIDTH, Math.round(width)))
}

const persistAgentPanelWidth = () => {
  localStorage.setItem(AGENT_PANEL_WIDTH_KEY, String(agentPanelWidth.value))
}

const handleAgentPanelResizeMove = (event: PointerEvent) => {
  if (!agentPanelResizing.value) return
  agentPanelWidth.value = clampAgentPanelWidth(agentPanelResizeStartWidth + agentPanelResizeStartX - event.clientX)
}

const stopAgentPanelResize = () => {
  if (!agentPanelResizing.value) return
  agentPanelResizing.value = false
  persistAgentPanelWidth()
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleAgentPanelResizeMove)
  window.removeEventListener('pointerup', stopAgentPanelResize)
  window.removeEventListener('pointercancel', stopAgentPanelResize)
}

const startAgentPanelResize = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  agentPanelResizeStartX = event.clientX
  agentPanelResizeStartWidth = agentPanelWidth.value
  agentPanelResizing.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleAgentPanelResizeMove)
  window.addEventListener('pointerup', stopAgentPanelResize)
  window.addEventListener('pointercancel', stopAgentPanelResize)
}

const resetAgentPanelWidth = () => {
  agentPanelWidth.value = AGENT_PANEL_DEFAULT_WIDTH
  persistAgentPanelWidth()
}

const handleAgentPanelResizeKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Home') {
    agentPanelWidth.value = AGENT_PANEL_MIN_WIDTH
  } else if (event.key === 'End') {
    agentPanelWidth.value = AGENT_PANEL_MAX_WIDTH
  } else if (event.key === 'ArrowLeft') {
    agentPanelWidth.value = clampAgentPanelWidth(agentPanelWidth.value + 8)
  } else if (event.key === 'ArrowRight') {
    agentPanelWidth.value = clampAgentPanelWidth(agentPanelWidth.value - 8)
  } else {
    return
  }

  event.preventDefault()
  persistAgentPanelWidth()
}

// —— 信息栏停靠宽度：拖拽/键盘/双击复位，镜像 agent-panel 的交互 ——
const chatInfoResizeStartX = ref(0)
let chatInfoResizeStartWidth = CHAT_INFO_MIN_WIDTH

const defaultChatInfoWidth = () => {
  return clampChatInfoWidth(CHAT_INFO_DEFAULT_WIDTH)
}

const clampChatInfoWidth = (width: number) => {
  const mainWidth = chatInfoMainWidth.value || chatInfoViewportWidth.value
  const maxWidth = Math.max(
    CHAT_INFO_MIN_WIDTH,
    Math.min(CHAT_INFO_MAX_WIDTH, Math.floor(chatInfoViewportWidth.value * 0.45), mainWidth - CHAT_INFO_MIN_CONVERSATION_WIDTH)
  )
  return Math.min(maxWidth, Math.max(CHAT_INFO_MIN_WIDTH, Math.round(width)))
}

const chatInfoMaxWidth = computed(() => clampChatInfoWidth(CHAT_INFO_MAX_WIDTH))
const effectiveChatInfoWidth = computed(() => clampChatInfoWidth(chatInfoWidth.value))

const persistChatInfoWidth = () => {
  localStorage.setItem(CHAT_INFO_WIDTH_KEY, String(chatInfoWidth.value))
  dockGeometry.persist({ rightWidth: chatInfoWidth.value })
}

const handleChatInfoResizeMove = (event: PointerEvent) => {
  if (!chatInfoResizing.value) return
  chatInfoWidth.value = clampChatInfoWidth(chatInfoResizeStartWidth + chatInfoResizeStartX.value - event.clientX)
}

const stopChatInfoResize = () => {
  if (!chatInfoResizing.value) return
  chatInfoResizing.value = false
  persistChatInfoWidth()
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleChatInfoResizeMove)
  window.removeEventListener('pointerup', stopChatInfoResize)
  window.removeEventListener('pointercancel', stopChatInfoResize)
}

const startChatInfoResize = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  chatInfoResizeStartX.value = event.clientX
  chatInfoResizeStartWidth = effectiveChatInfoWidth.value
  chatInfoResizing.value = true
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleChatInfoResizeMove)
  window.addEventListener('pointerup', stopChatInfoResize)
  window.addEventListener('pointercancel', stopChatInfoResize)
}

const resetChatInfoWidth = () => {
  chatInfoWidth.value = defaultChatInfoWidth()
  persistChatInfoWidth()
}

const handleChatInfoResizeKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Home') {
    chatInfoWidth.value = CHAT_INFO_MIN_WIDTH
  } else if (event.key === 'End') {
    chatInfoWidth.value = chatInfoMaxWidth.value
  } else if (event.key === 'ArrowLeft') {
    chatInfoWidth.value = clampChatInfoWidth(effectiveChatInfoWidth.value + 8)
  } else if (event.key === 'ArrowRight') {
    chatInfoWidth.value = clampChatInfoWidth(effectiveChatInfoWidth.value - 8)
  } else {
    return
  }

  event.preventDefault()
  persistChatInfoWidth()
}

const setChatInfoCollapsed = (value: boolean) => {
  chatInfoCollapsed.value = value
  localStorage.setItem(CHAT_INFO_COLLAPSED_KEY, value ? '1' : '0')
}

// 视口变化时回收超宽的信息栏，保证消息列可用宽度
const handleChatInfoViewportResize = () => {
  chatInfoViewportWidth.value = window.innerWidth
  chatInfoMainWidth.value = chatMainRef.value?.clientWidth || 0
}

const getWorkflowPanelHardMaxHeight = () => {
  const panelHeight = chatPanelRef.value?.clientHeight || window.innerHeight
  const topPanelHeight = contextPanelOpen.value ? contextPanelHeight.value : 30
  // The composer is absolutely positioned and follows the ACG panel edge,
  // so reserving its height here prevents the panel from ever reaching the top.
  const availableHeight = Math.max(0, panelHeight - topPanelHeight)
  return Math.max(WORKFLOW_PANEL_MIN_HEIGHT, Math.floor(availableHeight))
}

const clampWorkflowPanelHeight = (height: number, maxHeight = getWorkflowPanelHardMaxHeight()) => {
  const safeMaxHeight = Math.max(WORKFLOW_PANEL_MIN_HEIGHT, maxHeight)
  return Math.min(safeMaxHeight, Math.max(WORKFLOW_PANEL_MIN_HEIGHT, Math.round(height)))
}

const handleWorkflowPanelViewportResize = () => {
  const nextHeight = clampWorkflowPanelHeight(workflowPanelHeight.value)
  if (nextHeight !== workflowPanelHeight.value) workflowPanelHeight.value = nextHeight
}

const persistWorkflowPanelHeight = () => {
  localStorage.setItem(WORKFLOW_PANEL_HEIGHT_KEY, String(workflowPanelHeight.value))
}

const handleWorkflowPanelResizeMove = (event: PointerEvent) => {
  if (!workflowPanelResizing.value) return
  workflowPanelHeight.value = clampWorkflowPanelHeight(
    workflowPanelResizeStartHeight + workflowPanelResizeStartY - event.clientY,
    workflowPanelResizeMaxHeight
  )
}

const stopWorkflowPanelResize = () => {
  if (!workflowPanelResizing.value) return
  workflowPanelResizing.value = false
  persistWorkflowPanelHeight()
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleWorkflowPanelResizeMove)
  window.removeEventListener('pointerup', stopWorkflowPanelResize)
  window.removeEventListener('pointercancel', stopWorkflowPanelResize)
}

const startWorkflowPanelResize = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  workflowPanelResizeStartY = event.clientY
  workflowPanelResizeStartHeight = workflowPanelHeight.value
  workflowPanelResizeMaxHeight = getWorkflowPanelHardMaxHeight()
  workflowPanelResizing.value = true
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleWorkflowPanelResizeMove)
  window.addEventListener('pointerup', stopWorkflowPanelResize)
  window.addEventListener('pointercancel', stopWorkflowPanelResize)
}

const resetWorkflowPanelHeight = () => {
  workflowPanelHeight.value = clampWorkflowPanelHeight(WORKFLOW_PANEL_DEFAULT_HEIGHT)
  persistWorkflowPanelHeight()
}

const setWorkflowPanelOpen = (open: boolean) => {
  workflowPanelOpen.value = open
  localStorage.setItem(WORKFLOW_PANEL_OPEN_KEY, open ? '1' : '0')
}

const toggleWorkflowPanel = () => {
  const open = !workflowPanelOpen.value
  setWorkflowPanelOpen(open)
  if (open && activeWorkflowRunId.value) void loadActiveAcgView(activeWorkflowRunId.value)
}

const handleWorkflowPanelResizeKeydown = (event: KeyboardEvent) => {
  const step = event.shiftKey ? 24 : 8
  if (event.key === 'Home') {
    workflowPanelHeight.value = WORKFLOW_PANEL_MIN_HEIGHT
  } else if (event.key === 'End') {
    workflowPanelHeight.value = getWorkflowPanelHardMaxHeight()
  } else if (event.key === 'ArrowUp') {
    workflowPanelHeight.value = clampWorkflowPanelHeight(
      workflowPanelHeight.value + step,
      getWorkflowPanelHardMaxHeight()
    )
  } else if (event.key === 'ArrowDown') {
    workflowPanelHeight.value = clampWorkflowPanelHeight(workflowPanelHeight.value - step)
  } else {
    return
  }
  event.preventDefault()
  persistWorkflowPanelHeight()
}

const clampContextPanelHeight = (height: number) => {
  return Math.min(CONTEXT_PANEL_MAX_HEIGHT, Math.max(CONTEXT_PANEL_MIN_HEIGHT, Math.round(height)))
}

const persistContextPanelHeight = () => {
  localStorage.setItem(CONTEXT_PANEL_HEIGHT_KEY, String(contextPanelHeight.value))
}

const handleContextPanelResizeMove = (event: PointerEvent) => {
  if (!contextPanelResizing.value) return
  contextPanelHeight.value = clampContextPanelHeight(
    contextPanelResizeStartHeight + event.clientY - contextPanelResizeStartY
  )
}

const stopContextPanelResize = () => {
  if (!contextPanelResizing.value) return
  contextPanelResizing.value = false
  persistContextPanelHeight()
  document.body.style.cursor = ''
  document.body.style.userSelect = ''
  window.removeEventListener('pointermove', handleContextPanelResizeMove)
  window.removeEventListener('pointerup', stopContextPanelResize)
  window.removeEventListener('pointercancel', stopContextPanelResize)
}

const startContextPanelResize = (event: PointerEvent) => {
  if (event.button !== 0) return
  event.preventDefault()
  contextPanelResizeStartY = event.clientY
  contextPanelResizeStartHeight = contextPanelHeight.value
  contextPanelResizing.value = true
  document.body.style.cursor = 'row-resize'
  document.body.style.userSelect = 'none'
  window.addEventListener('pointermove', handleContextPanelResizeMove)
  window.addEventListener('pointerup', stopContextPanelResize)
  window.addEventListener('pointercancel', stopContextPanelResize)
}

const resetContextPanelHeight = () => {
  contextPanelHeight.value = CONTEXT_PANEL_DEFAULT_HEIGHT
  persistContextPanelHeight()
}

const setContextPanelOpen = (open: boolean) => {
  if (open) contextPanelClosing.value = false
  else if (contextPanelOpen.value) contextPanelClosing.value = true
  contextPanelOpen.value = open
  localStorage.setItem(CONTEXT_PANEL_OPEN_KEY, open ? '1' : '0')
}

const finishContextPanelClose = () => {
  contextPanelClosing.value = false
}

const handleContextPanelResizeKeydown = (event: KeyboardEvent) => {
  const step = event.shiftKey ? 24 : 8
  if (event.key === 'Home') {
    contextPanelHeight.value = CONTEXT_PANEL_MIN_HEIGHT
  } else if (event.key === 'End') {
    contextPanelHeight.value = CONTEXT_PANEL_MAX_HEIGHT
  } else if (event.key === 'ArrowUp') {
    contextPanelHeight.value = clampContextPanelHeight(contextPanelHeight.value - step)
  } else if (event.key === 'ArrowDown') {
    contextPanelHeight.value = clampContextPanelHeight(contextPanelHeight.value + step)
  } else {
    return
  }
  event.preventDefault()
  persistContextPanelHeight()
}

const invalidateWorkflowResultRequest = (preserveResult = false) => {
  workflowResultGeneration += 1
  workflowResultController?.abort()
  workflowResultController = null
  workflowResultInFlight = null
  if (workflowResultRetryTimer !== null) window.clearTimeout(workflowResultRetryTimer)
  workflowResultRetryTimer = null
  workflowResultRetryCount = 0
  isLoadingWorkflowResult.value = false
  if (!preserveResult) {
    workflowResultState.value = 'idle'
    workflowResultError.value = null
  }
}

const scheduleWorkflowResultRetry = (runId: string) => {
  if (workflowResultRetryCount >= 2 || workflowResultRetryTimer !== null) return
  workflowResultRetryCount += 1
  workflowResultRetryTimer = window.setTimeout(() => {
    workflowResultRetryTimer = null
    if (runId === activeWorkflowRunId.value) void loadActiveAcgView(runId)
  }, workflowResultRetryCount * 1500)
}

const loadActiveAcgView = (runId = activeWorkflowRunId.value, force = false): Promise<boolean> => {
  if (!viewActive) return Promise.resolve(false)
  if (!runId || runId !== activeWorkflowRunId.value) return Promise.resolve(false)
  if (workflowResultInFlight?.runId === runId) {
    const inFlight = workflowResultInFlight.promise
    if (!force) return inFlight
    return inFlight.then(() => (
      runId === activeWorkflowRunId.value
        ? loadActiveAcgView(runId, true)
        : false
    ))
  }
  const requestGeneration = ++workflowResultGeneration
  workflowResultController?.abort()
  workflowResultController = new AbortController()
  const signal = workflowResultController.signal
  isLoadingWorkflowResult.value = true
  if (!activeWorkflowRun.value && !activeAcgView.value) workflowResultState.value = 'loading'
  workflowResultError.value = null

  const pending = (async () => {
    const runPromise = restoredRunDetail?.runId === runId
      ? Promise.resolve(restoredRunDetail) : agentosApi.getWorkflowRun(runId, { signal })
    restoredRunDetail = null
    const [runResult, viewResult] = await Promise.allSettled([
      runPromise,
      agentosApi.getAcgView(runId, { signal, run: runPromise })
    ])
    if (requestGeneration !== workflowResultGeneration || runId !== activeWorkflowRunId.value) return false

    if (runResult.status === 'fulfilled') {
      const expectedMission = typeof route.query.missionId === 'string' ? route.query.missionId
        : activeWorkflowBinding.value?.missionId
      if (!runMatchesSelection(runResult.value, runId, expectedMission)) {
        workflowProgressState.reset()
        activeWorkflowRunId.value = ''
        activeWorkflowBinding.value = null
        activeWorkflowRun.value = null
        activeAcgView.value = null
        workflowStartError.value = '运行记录与指定任务不匹配，未恢复关联'
        return false
      }
      activeWorkflowRun.value = runResult.value
      syncWorkflowMessageStatus(runResult.value.runId, runResult.value.status)
    }
    if (viewResult.status === 'fulfilled') activeAcgView.value = viewResult.value

    const cached = workflowResultCache.get(runId) || {}
    workflowResultCache.set(runId, {
      run: activeWorkflowRun.value || cached.run,
      view: activeAcgView.value || cached.view
    })

    const hasRun = Boolean(activeWorkflowRun.value)
    const hasView = Boolean(activeAcgView.value)
    if (hasRun && hasView) {
      workflowResultRetryCount = 0
      workflowResultState.value = 'ready'
      workflowResultError.value = null
      return true
    }

    const rejected = [runResult, viewResult].filter(result => result.status === 'rejected')
    const wasCancelled = rejected.length > 0
      && rejected.every(result => result.status === 'rejected' && axios.isCancel(result.reason))
    workflowResultState.value = hasRun || hasView ? 'partial' : 'error'
    workflowResultError.value = hasRun
      ? '运行详情已恢复，动态拓扑暂时未能加载。'
      : hasView
        ? '动态拓扑已恢复，任务报告暂时未能加载。'
        : '任务报告和动态拓扑均暂时未能加载。'
    if (!wasCancelled) {
      scheduleWorkflowResultRetry(runId)
      if (force) ElMessage.warning('ACG 最终结果暂时未能完整加载')
    }
    return false
  })().finally(() => {
    if (requestGeneration === workflowResultGeneration) {
      workflowResultController = null
      workflowResultInFlight = null
      isLoadingWorkflowResult.value = false
    }
  })
  workflowResultInFlight = { runId, promise: pending }
  return pending
}

const retryWorkflowHistoryDetail = () => {
  if (!activeWorkflowRunId.value) return
  if (workflowResultRetryTimer !== null) window.clearTimeout(workflowResultRetryTimer)
  workflowResultRetryTimer = null
  workflowResultRetryCount = 0
  void loadActiveAcgView(activeWorkflowRunId.value, true)
}

function handleWorkflowProgressChanged(current: WorkflowProgress, previous: WorkflowProgress | null) {
  if (current.runId !== activeWorkflowRunId.value) return
  const conversationId = currentConversationId.value
  chatStore.updateWorkflowBindingStatus(conversationId, current.runId, current.status)
  if (activeWorkflowBinding.value?.runId === current.runId) {
    activeWorkflowBinding.value = { ...activeWorkflowBinding.value, status: current.status }
  }
  syncWorkflowMessageStatus(current.runId, current.status)

  const phaseChanged = previous?.phase !== current.phase
  if (current.phase === 'review' && phaseChanged) {
    void loadActiveAcgView(current.runId)
  } else if (workflowPanelOpen.value && phaseChanged && current.phase === 'executing') {
    void loadActiveAcgView(current.runId)
  }
}

async function handleWorkflowTerminal(progress: WorkflowProgress): Promise<void> {
  if (progress.runId !== activeWorkflowRunId.value || terminalResultLoaded.has(progress.runId)) return
  const loaded = await loadActiveAcgView(progress.runId, true)
  if (loaded) {
    terminalResultLoaded.add(progress.runId)
    window.dispatchEvent(new Event('history-refresh'))
  }
}

const syncWorkflowMessageStatus = (runId: string, status: string) => {
  chatStore.messages.forEach(message => {
    if (message.workflowRunId === runId) message.workflowStatus = status
  })
}

const openActiveWorkflowOperations = () => {
  if (!activeWorkflowRunId.value) return
  void router.push({ path: '/agentos/acg', query: { runId: activeWorkflowRunId.value } })
}

const openActiveWorkflowConsole = () => {
  if (!activeWorkflowRunId.value) return
  void router.push({ path: '/history', query: { tab: 'acg', runId: activeWorkflowRunId.value } })
}

const handleChatWorkflowReviewed = async (run: WorkflowRun) => {
  if (run.runId !== activeWorkflowRunId.value) return
  activeWorkflowRun.value = run
  syncWorkflowMessageStatus(run.runId, run.status)
  chatStore.updateWorkflowBindingStatus(currentConversationId.value, run.runId, run.status)
  await workflowProgressState.refresh()
  await loadActiveAcgView(run.runId)
}

const handleChatReviewConflict = async () => {
  await workflowProgressState.refresh()
  if (activeWorkflowRunId.value) await loadActiveAcgView(activeWorkflowRunId.value)
}

const isAgentMode = computed(() => workspaceMode.value === 'agent')
const agentIcon = computed(() => Cpu)
const heroGreeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 5) return '夜深了，把任务交给 Agent 值守吧'
  if (hour < 9) return '早上好呀，新的一天开始啦'
  if (hour < 12) return '上午好，把想法交给 Agent 去执行'
  if (hour < 14) return '中午好，休息之余也可以派个任务'
  if (hour < 18) return '下午好，继续推进手头的事'
  return '晚上好，适合深度工作的时段'
})
const formatContextTokens = (value: number): string => {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1).replace(/\.0$/, '')}m`
  if (value >= 1_000) return `${Math.round(value / 1_000)}k`
  return String(value)
}

const contextUsage = computed(() => {
  const used = chatStore.contextUsedTokens
  const windowTokens = chatStore.contextWindowTokens
  if (typeof used !== 'number' || typeof windowTokens !== 'number' || windowTokens <= 0) {
    return { visible: false, percent: 0, level: 'normal', usedLabel: '', windowLabel: '' }
  }
  const ratio = Math.min(1, used / windowTokens)
  const percent = Math.round(ratio * 100)
  const level = ratio >= 0.9 ? 'danger' : ratio >= 0.7 ? 'warning' : 'normal'
  return {
    visible: true,
    percent,
    level,
    usedLabel: formatContextTokens(used),
    windowLabel: formatContextTokens(windowTokens)
  }
})

const latestAssistantMessage = computed(() => [...chatStore.messages]
  .reverse()
  .find(message => message.role === 'assistant'))

// —— 对话信息栏（Chat 模式右侧）：所有取值都来自当前会话的真实消息与对话元数据 ——
const conversationMeta = ref<Conversation | null>(null)
let conversationMetaController: AbortController | null = null
let conversationMetaTimer: number | null = null

const loadConversationMeta = async () => {
  if (!viewActive) return
  if (isAgentMode.value) {
    conversationMeta.value = null
    return
  }
  const conversationKey = currentConversationId.value
  if (!conversationKey || conversationKey.startsWith('draft:')) {
    conversationMeta.value = null
    return
  }
  conversationMetaController?.abort()
  const controller = new AbortController()
  conversationMetaController = controller
  try {
    const userId = localStorage.getItem('userId') || undefined
    const conversations = await conversationApi.getUserConversations(userId, 'chat', { signal: controller.signal })
    if (controller.signal.aborted) return
    conversationMeta.value = conversations.find(item => (item.contextId || item.id) === conversationKey) || null
  } catch {
    // 元数据加载失败只影响信息卡展示，不打断对话
  }
}

watch(
  [currentConversationId, () => chatStore.messages.length],
  () => {
    if (conversationMetaTimer) window.clearTimeout(conversationMetaTimer)
    if (!viewActive) return
    // 标题由后端在首轮回复后生成，留出短暂窗口再刷新
    conversationMetaTimer = window.setTimeout(() => { void loadConversationMeta() }, 600)
  },
  { immediate: true }
)

const formatInfoTime = (value?: string | Date): string => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

const conversationInfo = computed(() => {
  const meta = conversationMeta.value
  const firstUserMessage = chatStore.messages.find(message => message.role === 'user')
  const title = plainMissionTitle(meta?.title, '') || plainMissionTitle(firstUserMessage?.content, '新对话')
  const model = String(latestAssistantMessage.value?.modelInfo || '') || (() => {
    try {
      const settings = loadModelSettings()
      const connection = settings.providerConnections?.[settings.provider]
      return connection?.selectedModel || settings.selectedModel || '系统默认模型'
    } catch {
      return '系统默认模型'
    }
  })()
  const rounds = chatStore.messages.filter(message => message.role === 'user').length
  const tokensTotal = chatStore.messages.reduce((sum, message) => {
    if (typeof message.tokensUsed === 'number') return sum + message.tokensUsed
    if (typeof message.inputTokens === 'number' || typeof message.outputTokens === 'number') {
      return sum + (message.inputTokens || 0) + (message.outputTokens || 0) + (message.reasoningTokens || 0)
    }
    return sum
  }, 0)
  const seenSources = new Set<string>()
  const sources: Array<{ key: string; label: string }> = []
  for (const message of chatStore.messages) {
    for (const source of message.sources || []) {
      const label = String(source?.title || source?.filename || '').trim()
      if (!label) continue
      const key = String(source?.citationId || source?.url || label)
      if (seenSources.has(key)) continue
      seenSources.add(key)
      sources.push({ key, label })
    }
  }
  return {
    title,
    model,
    messageLabel: `${chatStore.messages.length} 条 · ${rounds} 轮`,
    tokensLabel: tokensTotal > 0 ? tokensTotal.toLocaleString('zh-CN') : '—',
    createdAtLabel: formatInfoTime(meta?.createdAt || chatStore.messages[0]?.createdAt),
    updatedAtLabel: formatInfoTime(meta?.updatedAt || latestAssistantMessage.value?.createdAt),
    sources: sources.slice(0, 4)
  }
})

const hasAgentActivity = computed(() => {
  const assistant = latestAssistantMessage.value
  return isAgentMode.value && (
    hasActiveWorkflow.value
    || Boolean(assistant?.skillsUsed?.length)
    || Boolean(assistant?.trace?.length)
    || Boolean(assistant?.executionSummary?.length)
  )
})

const showScrollToBottom = computed(() => !isNearBottom.value && chatStore.messages.length > 0)
const isSendDisabled = computed(() => loading.value || (!inputText.value.trim() && !isRecording.value))
const isWorkflowTerminal = computed(() => {
  const status = workflowProgressState.progress.value?.status || activeWorkflowBinding.value?.status
  return isTerminalRunStatus(status)
})
const isWorkflowUnavailable = computed(() =>
  workflowProgressState.syncError.value === '该运行记录不存在或当前账户无权访问'
)
const isWorkflowUpgradeDisabled = computed(() =>
  isSubmittingWorkflow.value
  || (Boolean(activeWorkflowRunId.value) && !isWorkflowTerminal.value && !isWorkflowUnavailable.value)
  || !inputText.value.trim()
)

const resetWorkspace = async () => {
  ++composerGeneration
  sendingDraftId = null
  loading.value = false
  isSubmittingWorkflow.value = false
  chatStore.clearMessages()
  draftConversationId.value = `draft:${createClientRequestId()}`
  localStorage.setItem(DRAFT_CONVERSATION_KEY, draftConversationId.value)

  conversationGeneration += 1
  workflowProgressState.reset()
  invalidateWorkflowResultRequest()
  selectedConversationId = ''
  restoredRunDetail = null
  activeWorkflowRunId.value = ''
  activeWorkflowBinding.value = null
  activeWorkflowRun.value = null
  activeAcgView.value = null
  workflowStartError.value = null
  pendingMessageCount.value = 0

  const {
    runId: _runId,
    missionId: _missionId,
    contextId: _contextId,
    newConversation: _newConversation,
    ...remainingQuery
  } = route.query
  await router.replace({
    path: '/chat',
    query: { ...remainingQuery, workspace: workspaceMode.value }
  })
}

const handleNewAgentTask = () => {
  void resetWorkspace()
}

// Shell sends this route intent even when ChatView is not mounted (for example,
// when the user starts a conversation from History). It is consumed exactly once.
watch(
  () => route.query.newConversation,
  intent => {
    if (intent === '1') void resetWorkspace()
  },
  { immediate: true }
)

const composerToolsAnchorRef = ref<HTMLElement | null>(null)
const composerToolsOpen = ref(false)

const toggleComposerTools = () => {
  composerToolsOpen.value = !composerToolsOpen.value
}

const openComposerFileManager = () => {
  composerToolsOpen.value = false
  handleControl('folder')
}

const autoSegment = () => {
  if (inputText.value.length <= 500) return
  const segments = inputText.value.match(/.{1,500}/g) || []
  inputText.value = segments.join('\n\n---\n\n')
  ElMessage.success(t('chat.autoSegment'))
}

const handleComposerOutsideClick = (event: MouseEvent) => {
  const target = event.target as Node
  if (composerToolsOpen.value && !composerToolsAnchorRef.value?.contains(target)) {
    composerToolsOpen.value = false
  }
}

const animateComposerToConversation = async (startRect: DOMRect) => {
  await nextTick()
  const composer = composerRef.value
  if (!composer || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

  const endRect = composer.getBoundingClientRect()
  const offsetX = startRect.left - endRect.left
  const offsetY = startRect.top - endRect.top
  if (Math.abs(offsetX) < 1 && Math.abs(offsetY) < 1) return

  const animation = composer.animate(
    [
      { transform: `translate(${offsetX}px, ${offsetY}px)`, opacity: 0.98 },
      { transform: 'translate(0, 0)', opacity: 1 }
    ],
    {
      duration: 480,
      easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      fill: 'both'
    }
  )

  try {
    await animation.finished
  } catch {
    // The animation may be cancelled when switching routes or roles.
  } finally {
    animation.cancel()
  }
}

const sendAgentWorkspaceMessage = async () => {
  const userText = inputText.value.trim()
  if (!userText) return

  loading.value = true
  const conversationId = currentConversationId.value
  const generation = ++composerGeneration
  const composerStartRect = chatStore.messages.length === 0
    ? composerRef.value?.getBoundingClientRect()
    : undefined

  try {
    inputText.value = userText
    await upgradeChatToWorkflow()
    if (!ownsComposerRequest(conversationId, generation)) return
    if (composerStartRect) await animateComposerToConversation(composerStartRect)
    if (ownsComposerRequest(conversationId, generation)) scrollToBottom()
  } catch (error: any) {
    if (!ownsComposerRequest(conversationId, generation)) return
    inputText.value = userText
    if (!wasErrorUserNotified(error)) ElMessage.error(error?.message || 'Send failed')
  } finally {
    if (ownsComposerRequest(conversationId, generation)) loading.value = false
  }
}

const sendMessage = async () => {
  if (loading.value) return
  if (!inputText.value.trim() && !isRecording.value) return

  if (isAgentMode.value) {
    await sendAgentWorkspaceMessage()
    return
  }

  loading.value = true
  const generation = ++composerGeneration
  const userText = inputText.value.trim()
  inputText.value = ''
  const composerStartRect = chatStore.messages.length === 0
    ? composerRef.value?.getBoundingClientRect()
    : undefined

  try {
    sendingDraftId = !chatStore.contextId && !route.query.contextId && currentConversationId.value.startsWith('draft:')
      ? currentConversationId.value : null
    const sendPromise = chatStore.sendMessageStream(userText, 'default', loadModelSettings(), workspaceMode.value)
    if (composerStartRect) {
      await animateComposerToConversation(composerStartRect)
    }
    await sendPromise
    if (generation !== composerGeneration) return
    scrollToBottom()
  } catch (err: any) {
    if (generation !== composerGeneration) return
    if (!wasErrorUserNotified(err)) ElMessage.error(err.message || '发送消息失败')
    inputText.value = userText
  } finally {
    if (generation === composerGeneration) {
      sendingDraftId = null
      loading.value = false
    }
  }
}

const activateWorkflowRun = async (
  runId: string,
  binding: ChatWorkflowBinding | null,
  fresh: boolean,
  conversationId: string
) => {
  if (!isSameConversation(conversationId, currentConversationId.value)
    || (binding && !belongsToConversation(binding, conversationId))) return
  conversationGeneration += 1
  workflowProgressState.reset()
  invalidateWorkflowResultRequest()
  activeWorkflowRunId.value = runId
  selectedConversationId = conversationId
  activeWorkflowBinding.value = binding
  activeWorkflowRun.value = null
  activeAcgView.value = null
  workflowStartError.value = null
  if (isConversationVisible(conversationId)) {
    void workflowProgressState.start(runId, { fresh })
    await router.replace({ path: '/chat', query: { ...route.query, runId } })
  }
}

const workflowStartErrorMessage = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409) return '本次提交发生冲突，已保留原身份；请核对创建结果'
    if (error.response?.status === 503 || !error.response) return 'ACG 任务暂时不可用，请稍后重试'
  }
  if (error instanceof Error && error.name === 'WorkflowApiContractError') {
    return 'ACG 启动响应契约无效'
  }
  if (error instanceof Error && error.name === 'MissionLaunchStateError') return error.message
  return 'ACG 任务未能启动'
}

const upgradeChatToWorkflow = async () => {
  if (isSubmittingWorkflow.value || (activeWorkflowRunId.value && !isWorkflowTerminal.value)) return
  const userText = inputText.value.trim()
  if (!userText) {
    ElMessage.warning('请输入要升级为 Workflow 的内容')
    return
  }

  const conversationId = currentConversationId.value
  const generation = composerGeneration
  isSubmittingWorkflow.value = true
  workflowStartError.value = null
  inputText.value = ''
  try {
    const startWorkflow = isAgentMode.value ? chatStore.startAgentRun : chatStore.upgradeToWorkflow
    const result = await startWorkflow(userText, {
      policyProfile: 'conversation-workspace',
      conversationId,
      execution: {
        thinkingMode: loadModelSettings().thinkingMode,
        reasoningEffort: loadModelSettings().reasoningEffort
      }
    })
    if (!ownsComposerRequest(conversationId, generation)) return
    if (result) {
      await activateWorkflowRun(result.binding.runId, result.binding, true, conversationId)
      if (ownsComposerRequest(conversationId, generation) && isConversationVisible(conversationId)) {
        ElMessage.success(`已创建 WorkflowRun：${result.binding.runId}`)
      }
    }
    if (ownsComposerRequest(conversationId, generation)) scrollToBottom()
  } catch (error: unknown) {
    if (!ownsComposerRequest(conversationId, generation)) return
    inputText.value = userText
    workflowStartError.value = workflowStartErrorMessage(error)
    pendingLaunchForView.value = chatStore.pendingMissionLaunch(conversationId)
  } finally {
    if (ownsComposerRequest(conversationId, generation)) isSubmittingWorkflow.value = false
  }
}

const pendingLaunchForView = ref<ReturnType<typeof chatStore.pendingMissionLaunch>>(null)
const resumePendingConversationLaunch = async () => {
  if (isSubmittingWorkflow.value) return
  const conversationId = currentConversationId.value
  const generation = composerGeneration
  isSubmittingWorkflow.value = true
  try {
    const result = await chatStore.resumeMissionLaunch(conversationId)
    if (!ownsComposerRequest(conversationId, generation)) return
    if (result) {
      pendingLaunchForView.value = null
      await activateWorkflowRun(result.binding.runId, result.binding, true, conversationId)
    }
  } catch (error) { if (ownsComposerRequest(conversationId, generation)) workflowStartError.value = workflowStartErrorMessage(error) }
  finally { if (ownsComposerRequest(conversationId, generation)) isSubmittingWorkflow.value = false }
}
// Store history may already contain the route target. Identity changes must still
// retire the previous composer's callbacks, even when no history fetch is needed.
watch(currentConversationId, (id, previous) => {
  if (isSameConversation(previous, id)) return
  // The existing first-send proof migrates Draft bindings in the context watcher
  // below. Do not retire that request before it can establish the Alias.
  if (previous === sendingDraftId && previous === draftConversationId.value
    && !route.query.contextId && !chatStore.isLoadingConversation && id === chatStore.contextId) return
  ++composerGeneration
  sendingDraftId = null
  loading.value = false
  isSubmittingWorkflow.value = false
  inputText.value = ''
  workflowStartError.value = null
}, { flush: 'sync' })
watch(currentConversationId, id => {
  try {
    pendingLaunchForView.value = chatStore.pendingMissionLaunch(id)
    if (pendingLaunchForView.value && !inputText.value) inputText.value = pendingLaunchForView.value.commandSnapshot.semantics?.objective || ''
  } catch (error) { workflowStartError.value = workflowStartErrorMessage(error) }
}, { immediate: true })

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

  showFileManager.value = false
  loading.value = true
  const generation = ++composerGeneration
  const composerStartRect = chatStore.messages.length === 0
    ? composerRef.value?.getBoundingClientRect()
    : undefined

  try {
    sendingDraftId = !chatStore.contextId && !route.query.contextId && currentConversationId.value.startsWith('draft:')
      ? currentConversationId.value : null
    const sendPromise = chatStore.sendMessage('', fileUrl, loadModelSettings(), workspaceMode.value)
    if (composerStartRect) {
      await animateComposerToConversation(composerStartRect)
    }
    await sendPromise
    if (generation !== composerGeneration) return
    scrollToBottom()
    ElMessage.success(`已发送文件: ${file.name}`)
  } catch (error: any) {
    if (generation !== composerGeneration) return
    ElMessage.error(error.message || '发送文件失败')
  } finally {
    if (generation === composerGeneration) {
      sendingDraftId = null
      loading.value = false
    }
  }
}

let pendingScrollFrame: number | null = null

interface ConversationRailItem {
  id: Message['id']
  round: number
  preview: string
}

const CONVERSATION_RAIL_MIN_ROUNDS = 3
const CONVERSATION_RAIL_OVERFLOW_GAP = 120

const conversationRailItems = computed<ConversationRailItem[]>(() => {
  const items: ConversationRailItem[] = []
  chatStore.messages.forEach(message => {
    if (message.role !== 'user') return
    const text = (message.content || '').replace(/\s+/g, ' ').trim()
    const preview = text || (message.fileUrl ? '[文件附件]' : '（空消息）')
    items.push({
      id: message.id,
      round: items.length + 1,
      preview: preview.slice(0, 200)
    })
  })
  return items
})

const conversationRailOverflow = ref(false)
const conversationRailVisible = computed(() =>
  !isAgentMode.value
  && conversationRailItems.value.length >= CONVERSATION_RAIL_MIN_ROUNDS
  && conversationRailOverflow.value
)
const conversationRailRef = ref<HTMLElement | null>(null)
const activeRailTickId = ref<Message['id'] | ''>('')
const railHoverItem = ref<ConversationRailItem | null>(null)
const railPreviewTop = ref(0)
const railFlashId = ref<Message['id'] | ''>('')
let railFlashTimer: number | null = null
let railScrollFallback: number | null = null

// 隐藏页/禁用平滑滚动的环境里 scrollTo smooth 会原地不动：140ms 无位移则瞬时到位兜底
const animateRailScrollTo = (container: HTMLElement, target: number) => {
  if (railScrollFallback !== null) window.clearTimeout(railScrollFallback)
  const start = container.scrollTop
  if (Math.abs(target - start) < 2) return
  container.scrollTo({ top: target, behavior: 'smooth' })
  railScrollFallback = window.setTimeout(() => {
    railScrollFallback = null
    if (Math.abs(container.scrollTop - target) > 4 && Math.abs(container.scrollTop - start) < 2) {
      container.scrollTo({ top: target, behavior: 'auto' })
    }
  }, 140)
}

const updateRailOverflow = () => {
  const el = messagesRef.value
  if (!el) {
    conversationRailOverflow.value = false
    return
  }
  conversationRailOverflow.value = el.scrollHeight > el.clientHeight + CONVERSATION_RAIL_OVERFLOW_GAP
}

const updateRailActiveTick = () => {
  const container = messagesRef.value
  if (!conversationRailVisible.value || !container) {
    activeRailTickId.value = ''
    return
  }
  const box = container.getBoundingClientRect()
  const probe = box.top + box.height * 0.35
  let current: Message['id'] | '' = ''
  container.querySelectorAll<HTMLElement>('[data-role="user"][data-message-id]').forEach(row => {
    if (row.getBoundingClientRect().top <= probe) current = (row.dataset.messageId as Message['id']) || ''
  })
  activeRailTickId.value = current
}

const jumpToRailInteraction = (id: Message['id']) => {
  const container = messagesRef.value
  if (!container) return
  let target: HTMLElement | null = null
  container.querySelectorAll<HTMLElement>('[data-role="user"][data-message-id]').forEach(row => {
    if (row.dataset.messageId === String(id)) target = row
  })
  if (!target) return

  const box = container.getBoundingClientRect()
  const top = container.scrollTop + target.getBoundingClientRect().top - box.top - 18
  animateRailScrollTo(container, Math.max(0, top))
  activeRailTickId.value = id
  railFlashId.value = id
  if (railFlashTimer !== null) window.clearTimeout(railFlashTimer)
  railFlashTimer = window.setTimeout(() => {
    railFlashId.value = ''
    railFlashTimer = null
  }, 1600)
}

const handleRailHover = (item: ConversationRailItem, event: PointerEvent) => {
  railHoverItem.value = item
  const railEl = conversationRailRef.value
  const tick = event.currentTarget as HTMLElement | null
  if (!railEl || !tick) return
  const railRect = railEl.getBoundingClientRect()
  const tickRect = tick.getBoundingClientRect()
  const center = tickRect.top - railRect.top + tickRect.height / 2
  railPreviewTop.value = Math.min(Math.max(center, 48), Math.max(railRect.height - 48, 48))
}

const handleRailLeave = () => {
  railHoverItem.value = null
}

watch(
  () => chatStore.messages.length,
  () => {
    void nextTick(() => {
      updateRailOverflow()
      updateRailActiveTick()
    })
  }
)

const scrollToBottom = (behavior: ScrollBehavior = 'auto') => {
  if (!viewActive || !messagesRef.value) return

  if (pendingScrollFrame !== null) {
    window.cancelAnimationFrame(pendingScrollFrame)
  }

  pendingScrollFrame = window.requestAnimationFrame(() => {
    pendingScrollFrame = null
    void nextTick(() => {
      const messagesElement = messagesRef.value
      if (!viewActive || !messagesElement) return

      messagesElement.scrollTo({
        top: messagesElement.scrollHeight,
        behavior
      })
    })
  })
}

const handleScrollToBottom = () => {
  pendingMessageCount.value = 0
  scrollToBottom('smooth')
}

watch(
  () => route.query.workspace,
  workspace => {
    if (workspace !== 'agent' && workspace !== 'chat') return
    workspaceMode.value = workspace
    localStorage.setItem(WORKSPACE_MODE_KEY, workspace)
  },
  { immediate: true }
)

const handleWorkspaceModeChange = (event: Event) => {
  const mode = (event as CustomEvent<{ mode?: WorkspaceMode }>).detail?.mode
  if (mode !== 'agent' && mode !== 'chat') return
  workspaceModeSwitching.value = true
  workspaceMode.value = mode
  if (mode === 'agent') {
    agentPanelCollapsed.value = showHeroMode.value
    setContextPanelOpen(!showHeroMode.value)
    setWorkflowPanelOpen(!showHeroMode.value)
  } else {
    contextPanelOpen.value = false
    contextPanelClosing.value = false
    workflowPanelOpen.value = false
    localStorage.setItem(CONTEXT_PANEL_OPEN_KEY, '0')
    localStorage.setItem(WORKFLOW_PANEL_OPEN_KEY, '0')
  }
  void nextTick(() => {
    workspaceModeSwitching.value = false
  })
}

watch(
  () => chatStore.messages.length,
  (newLen, oldLen) => {
    if (newLen === 0) {
      setContextPanelOpen(false)
      setWorkflowPanelOpen(false)
      agentPanelCollapsed.value = true
      return
    }
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
  () => chatStore.messages[chatStore.messages.length - 1]?.content,
  () => {
    if (isNearBottom.value) scrollToBottom()
  },
  { flush: 'post' }
)

const checkScrollState = () => {
  if (!messagesRef.value) return
  const { scrollTop, scrollHeight, clientHeight } = messagesRef.value
  const isAtBottom = Math.abs(scrollHeight - clientHeight - scrollTop) < 24
  isNearBottom.value = isAtBottom
  if (isAtBottom) pendingMessageCount.value = 0
  updateRailOverflow()
  updateRailActiveTick()
}

const bindMessagesScroll = () => {
  if (!messagesRef.value) return
  messagesRef.value.removeEventListener('scroll', checkScrollState)
  messagesRef.value.addEventListener('scroll', checkScrollState)
  checkScrollState()
}

watch(
  () => route.query.contextId,
  async contextId => {
    if (!viewActive || route.query.newConversation === '1') return
    const targetContextId = typeof contextId === 'string' ? contextId.trim() : ''
    if (!targetContextId) return
    if (chatStore.contextId === targetContextId) return

    await chatStore.loadHistory(targetContextId)
    scrollToBottom()
  },
  { immediate: true }
)

const restoreWorkflowForConversation = async (resume = false) => {
  if (!isConversationVisible() || route.query.newConversation === '1') return
  const conversationId = currentConversationId.value
  const bindings = conversationBindings(chatStore.workflowBindings, conversationId)
  const selectedRunId = selectedConversationId === conversationId ? activeWorkflowRun.value?.runId : undefined
  const selectedBinding = selectedConversationId === conversationId && activeWorkflowRun.value
    ? activeWorkflowBinding.value : null
  let binding = selectedBinding || chatStore.getActiveWorkflowBinding(conversationId)
    || chatStore.getLatestWorkflowBinding(conversationId)
  const routeRunId = typeof route.query.runId === 'string' ? route.query.runId.trim() : ''
  const missionId = typeof route.query.missionId === 'string' ? route.query.missionId.trim() : ''
  let runId = routeRunId || (selectedConversationId === conversationId ? activeWorkflowRun.value?.runId : '') || binding?.runId || ''

  if (runId && runId === activeWorkflowRunId.value && workflowProgressState.runId.value === runId
    && (!missionId || activeWorkflowRun.value?.missionId === missionId)) {
    if (resume) {
      await workflowProgressState.refresh()
      await loadActiveAcgView(runId, true)
    }
    return
  }

  const restoreGeneration = ++conversationGeneration
  restoredRunDetail = null
  workflowProgressState.reset()
  invalidateWorkflowResultRequest()
  activeWorkflowRunId.value = ''
  activeWorkflowBinding.value = null
  activeWorkflowRun.value = null
  activeAcgView.value = null
  workflowStartError.value = null
  if (missionId && !routeRunId) {
    // Resolve the canonical Mission projection without creating a Run or replacing explicit history.
    try {
      const workspace = await agentosApi.getMissionWorkspace(missionId)
      if (restoreGeneration !== conversationGeneration) return
      runId = workspace.mission.missionId === missionId ? workspace.activeRun?.runId || '' : ''
      binding = binding?.runId === runId && binding.missionId === missionId ? binding : undefined
    } catch {
      if (restoreGeneration === conversationGeneration) workflowStartError.value = '任务关联暂时未能恢复'
      return
    }
  }
  if (!runId) return

  const candidateIds = routeRunId || missionId ? [runId]
    : [...new Set([selectedRunId, ...bindings.filter(item => !item.invalidAt).map(item => item.runId)].filter((id): id is string => Boolean(id)))]
  const results = await Promise.allSettled(candidateIds.map(id => agentosApi.getWorkflowRun(id)))
  if (restoreGeneration !== conversationGeneration) return
  const verified = results.flatMap((result, i) => {
    if (result.status !== 'fulfilled') return []
    const expectedMission = missionId || bindings.find(item => item.runId === candidateIds[i])?.missionId
    return runMatchesSelection(result.value, candidateIds[i], expectedMission) ? [result.value] : []
  })
  const resolved = selectSessionRun({
    explicitRunId: routeRunId || (missionId ? runId : undefined), explicitMissionId: missionId || undefined,
    selectedRunId, verified, bindings,
    historicalRunId: [...bindings].reverse().find(item => !item.invalidAt && verified.some(run => run.runId === item.runId))?.runId
  })
  if (resolved) {
    runId = resolved.runId
    binding = bindings.find(item => item.runId === runId) || undefined
    restoredRunDetail = resolved
  } else if (!(routeRunId && results[0]?.status === 'rejected')) {
    workflowStartError.value = '运行记录与指定任务不匹配或不可访问，未恢复关联'
    return
  }
  // An explicit unavailable history ID may show the existing retry UI, but is never a verified binding.
  if (!resolved) binding = undefined

  activeWorkflowRunId.value = runId
  selectedConversationId = conversationId
  activeWorkflowBinding.value = binding?.runId === runId ? binding : null
  const cachedResult = workflowResultCache.get(runId)
  if (cachedResult && resolved) {
    activeWorkflowRun.value = resolved
    activeAcgView.value = cachedResult.view || null
    workflowResultState.value = cachedResult.run && cachedResult.view ? 'ready' : 'partial'
  }
  await workflowProgressState.start(runId, { fresh: false })
  if (restoreGeneration !== conversationGeneration || runId !== activeWorkflowRunId.value) return
  if ((!activeWorkflowRun.value || !activeAcgView.value) && !isLoadingWorkflowResult.value) {
    await loadActiveAcgView(runId)
  }
  if (restoreGeneration !== conversationGeneration || runId !== activeWorkflowRunId.value) return
  if (!routeRunId && resolved && isConversationVisible(conversationId)) {
    await router.replace({ query: { ...route.query, runId } })
  }
}

watch(
  [currentConversationId, () => route.query.runId, () => route.query.missionId],
  () => { void restoreWorkflowForConversation() },
  { immediate: true }
)

watch(
  () => chatStore.contextId,
  (contextId, previous) => {
    if (!contextId || contextId.startsWith('draft:') || chatStore.isLoadingConversation) return
    // Only a context emitted by this draft's first send proves ownership. A saved draft key is insufficient.
    if (!previous && sendingDraftId && !route.query.contextId && sendingDraftId === draftConversationId.value) {
      chatStore.migrateDraftBindings(sendingDraftId, contextId)
    }
    if (isConversationVisible() && !previous && !route.query.contextId) {
      setConversationWorkspace(contextId, chatStore.conversationWorkspaceMode || workspaceMode.value)
      void router.replace({ query: contextQuery(route.query, contextId) })
    }
  },
  { flush: 'sync' }
)

watch(
  () => workflowProgressState.syncError.value,
  error => {
    if (error !== '该运行记录不存在或当前账户无权访问') return
    const binding = activeWorkflowBinding.value
    if (!binding) return
    chatStore.markWorkflowBindingInvalid(binding.conversationId, binding.runId)
    activeWorkflowBinding.value = { ...binding, invalidAt: new Date().toISOString() }
  }
)

watch(hasAgentActivity, active => {
  if (active) agentPanelCollapsed.value = false
})

watch(
  [isAgentMode, activeWorkflowRunId],
  async ([generalMode], previous) => {
    if (!generalMode) return
    const previousRunId = previous?.[1]
    if (previousRunId === activeWorkflowRunId.value && previous?.[0] === generalMode) return
    await nextTick()
    agentPanelContentRef.value?.scrollTo({ top: 0 })
  }
)

// 英雄区锚定在容器高度的 57%，若挂载/出现瞬间面板高度未稳定（残留的工作流
// 状态让 showHeroMode 晚一拍翻真、面板先按内容高度排布再撑满），整块英雄区
// 会从高处滑到中心。因此英雄区每次出现都重新布防：面板高度连续 3 帧不变才
// 显示，400ms 兜底。
const heroSettled = ref(false)
let heroSettleFrame = 0
let heroSettleTimer: ReturnType<typeof setTimeout> | undefined
const startHeroSettleCheck = () => {
  cancelAnimationFrame(heroSettleFrame)
  if (heroSettleTimer) clearTimeout(heroSettleTimer)
  heroSettled.value = false
  let lastHeight = -1
  let stableFrames = 0
  const tick = () => {
    const panel = chatPanelRef.value
    const height = panel ? Math.round(panel.getBoundingClientRect().height) : 0
    stableFrames = height > 0 && height === lastHeight ? stableFrames + 1 : 0
    lastHeight = height
    if (stableFrames >= 3) {
      heroSettled.value = true
      return
    }
    heroSettleFrame = requestAnimationFrame(tick)
  }
  heroSettleFrame = requestAnimationFrame(tick)
  heroSettleTimer = setTimeout(() => {
    cancelAnimationFrame(heroSettleFrame)
    heroSettled.value = true
  }, 400)
}
watch(showHeroMode, value => {
  if (value) startHeroSettleCheck()
})
onMounted(() => {
  if (showHeroMode.value) startHeroSettleCheck()
})
onUnmounted(() => {
  cancelAnimationFrame(heroSettleFrame)
  if (heroSettleTimer) clearTimeout(heroSettleTimer)
  conversationMetaController?.abort()
  if (conversationMetaTimer !== null) {
    window.clearTimeout(conversationMetaTimer)
    conversationMetaTimer = null
  }
})

const attachViewEvents = () => {
  window.addEventListener('workspace-mode-change', handleWorkspaceModeChange)
  window.addEventListener('agent-new-task', handleNewAgentTask)
  window.addEventListener('resize', handleWorkflowPanelViewportResize)
  window.addEventListener('resize', handleChatInfoViewportResize)
  window.addEventListener('pointerdown', handleComposerOutsideClick)
}
const detachViewEvents = () => {
  window.removeEventListener('workspace-mode-change', handleWorkspaceModeChange)
  window.removeEventListener('agent-new-task', handleNewAgentTask)
  window.removeEventListener('resize', handleWorkflowPanelViewportResize)
  window.removeEventListener('resize', handleChatInfoViewportResize)
  window.removeEventListener('pointerdown', handleComposerOutsideClick)
}
onMounted(async () => {
  heroLogoMotion.reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  attachViewEvents()
  if (showHeroMode.value) {
    setContextPanelOpen(false)
    setWorkflowPanelOpen(false)
    agentPanelCollapsed.value = true
  }
  // Measure available space without replacing the user's shared dock preference.
  handleChatInfoViewportResize()
  if (typeof ResizeObserver !== 'undefined' && chatMainRef.value) {
    chatInfoResizeObserver = new ResizeObserver(handleChatInfoViewportResize)
    chatInfoResizeObserver.observe(chatMainRef.value)
  }
  workflowPanelHeight.value = clampWorkflowPanelHeight(workflowPanelHeight.value)

  if (composerRef.value) {
    composerResizeObserver = new ResizeObserver(entries => {
      const height = entries[0]?.borderBoxSize?.[0]?.blockSize || entries[0]?.contentRect.height
      if (height) composerHeight.value = Math.ceil(height)
    })
    composerResizeObserver.observe(composerRef.value)
  }

  if (localStorage.getItem(AGENT_PANEL_COLLAPSED_KEY) === null && isAgentMode.value && !hasAgentActivity.value) {
    agentPanelCollapsed.value = true
  }


  void chatStore.fetchContextWindows()

  bindMessagesScroll()
})

onDeactivated(() => {
  viewActive = false
  viewSuspended = true
  savedScrollTop = messagesRef.value?.scrollTop || 0
  detachViewEvents()
  conversationGeneration += 1
  workflowProgressState.stop()
  invalidateWorkflowResultRequest(true)
  conversationMetaController?.abort()
  if (conversationMetaTimer !== null) window.clearTimeout(conversationMetaTimer)
  conversationMetaTimer = null
  chatInfoResizeObserver?.disconnect()
  composerResizeObserver?.disconnect()
  stopChatInfoResize()
  stopAgentPanelResize()
  stopWorkflowPanelResize()
  stopContextPanelResize()
  if (pendingScrollFrame !== null) window.cancelAnimationFrame(pendingScrollFrame)
  pendingScrollFrame = null
  if (heroLogoMotion.frame !== null) window.cancelAnimationFrame(heroLogoMotion.frame)
  heroLogoMotion.frame = null
  cancelAnimationFrame(heroSettleFrame)
  if (heroSettleTimer) clearTimeout(heroSettleTimer)
})
onActivated(async () => {
  if (!viewSuspended) return
  viewSuspended = false
  viewActive = true
  attachViewEvents()
  if (chatMainRef.value) chatInfoResizeObserver?.observe(chatMainRef.value)
  if (composerRef.value) composerResizeObserver?.observe(composerRef.value)
  if (chatStore.contextId && !route.query.contextId) {
    await router.replace({ path: '/chat', query: contextQuery(route.query, chatStore.contextId) })
  }
  void restoreWorkflowForConversation(true)
  void loadConversationMeta()
  await nextTick()
  if (messagesRef.value) messagesRef.value.scrollTop = savedScrollTop
  if (showHeroMode.value) startHeroSettleCheck()
})
onUnmounted(() => {
  ++composerGeneration
  viewActive = false
  detachViewEvents()
  stopChatInfoResize()
  chatInfoResizeObserver?.disconnect()
  chatInfoResizeObserver = null
  if (railFlashTimer !== null) {
    window.clearTimeout(railFlashTimer)
    railFlashTimer = null
  }
  if (railScrollFallback !== null) {
    window.clearTimeout(railScrollFallback)
    railScrollFallback = null
  }
  composerResizeObserver?.disconnect()
  stopAgentPanelResize()
  stopWorkflowPanelResize()
  stopContextPanelResize()
  if (heroLogoMotion.frame !== null) window.cancelAnimationFrame(heroLogoMotion.frame)
  heroLogoMotion.frame = null
  if (pendingScrollFrame !== null) window.cancelAnimationFrame(pendingScrollFrame)
  pendingScrollFrame = null
  workflowProgressState.reset()
  invalidateWorkflowResultRequest()
  if (messagesRef.value) {
    messagesRef.value.removeEventListener('scroll', checkScrollState)
  }
})

type HeroLogoMotionState = {
  x: number
  y: number
  intensity: number
  targetX: number
  targetY: number
  targetIntensity: number
  pointerActive: boolean
  pressed: boolean
  frame: number | null
  reducedMotion: boolean
}

const heroLogoMotion: HeroLogoMotionState = {
  x: 0,
  y: 0,
  intensity: 0,
  targetX: 0,
  targetY: 0,
  targetIntensity: 0,
  pointerActive: false,
  pressed: false,
  frame: null,
  reducedMotion: false
}

const clampHeroLogo = (value: number) => Math.max(-1, Math.min(1, value))

const scheduleHeroLogoMotion = () => {
  if (heroLogoMotion.reducedMotion || heroLogoMotion.frame !== null || typeof window.requestAnimationFrame !== 'function') return
  heroLogoMotion.frame = window.requestAnimationFrame(animateHeroLogoMotion)
}

const animateHeroLogoMotion = (timestamp: number) => {
  heroLogoMotion.frame = null
  const field = heroLogoFieldRef.value
  const logo = field?.querySelector<HTMLImageElement>('.hero-watermark')
  const turbulence = heroLogoTurbulenceRef.value
  const displacement = heroLogoDisplacementRef.value

  if (!field || !logo || !turbulence || !displacement || heroLogoMotion.reducedMotion) return

  const smoothing = heroLogoMotion.intensity > 0.02 ? 0.14 : 0.1
  heroLogoMotion.x += (heroLogoMotion.targetX - heroLogoMotion.x) * smoothing
  heroLogoMotion.y += (heroLogoMotion.targetY - heroLogoMotion.y) * smoothing
  heroLogoMotion.intensity += (heroLogoMotion.targetIntensity - heroLogoMotion.intensity) * smoothing

  const wave = Math.sin(timestamp / 780) * heroLogoMotion.intensity
  const intensity = heroLogoMotion.intensity
  const rotation = heroLogoMotion.x * 2.4 - heroLogoMotion.y * 1.1
  const skewX = heroLogoMotion.x * intensity * 2.2
  const skewY = heroLogoMotion.y * intensity * -1.4
  const scale = 1 + intensity * 0.035
  const displacementScale = 5 + intensity * 24 + wave * 2
  const frequencyX = 0.009 + intensity * 0.006 + wave * 0.0007
  const frequencyY = 0.014 + intensity * 0.007 - wave * 0.0007

  logo.style.transform = `translate3d(${(heroLogoMotion.x * intensity * 4).toFixed(2)}px, ${(heroLogoMotion.y * intensity * 3).toFixed(2)}px, 0) rotate(${rotation.toFixed(2)}deg) skew(${skewX.toFixed(2)}deg, ${skewY.toFixed(2)}deg) scale(${scale.toFixed(4)})`
  displacement.setAttribute('scale', displacementScale.toFixed(2))
  turbulence.setAttribute('baseFrequency', `${frequencyX.toFixed(4)} ${frequencyY.toFixed(4)}`)
  field.style.setProperty('--hero-logo-aura-opacity', (0.12 + intensity * 0.2).toFixed(3))
  field.style.setProperty('--hero-logo-aura-scale', (1 + intensity * 0.12).toFixed(3))

  const settled = Math.abs(heroLogoMotion.targetIntensity - intensity) < 0.006
    && Math.abs(heroLogoMotion.targetX - heroLogoMotion.x) < 0.006
    && Math.abs(heroLogoMotion.targetY - heroLogoMotion.y) < 0.006

  if (heroLogoMotion.pointerActive || heroLogoMotion.pressed || !settled) scheduleHeroLogoMotion()
}

const updateHeroLogoPointer = (event: PointerEvent) => {
  const field = heroLogoFieldRef.value
  if (!field || heroLogoMotion.reducedMotion) return

  const rect = field.getBoundingClientRect()
  const x = clampHeroLogo(((event.clientX - rect.left) / rect.width) * 2 - 1)
  const y = clampHeroLogo(((event.clientY - rect.top) / rect.height) * 2 - 1)
  const distance = Math.min(1, Math.hypot(x, y) * 0.72 + 0.08)

  heroLogoMotion.targetX = x
  heroLogoMotion.targetY = y
  heroLogoMotion.targetIntensity = Math.max(distance, heroLogoMotion.pressed ? 0.72 : 0)
  scheduleHeroLogoMotion()
}

const handleHeroLogoPointerMove = (event: PointerEvent) => {
  heroLogoMotion.pointerActive = true
  updateHeroLogoPointer(event)
}

const handleHeroLogoPointerLeave = () => {
  heroLogoMotion.pointerActive = false
  heroLogoMotion.pressed = false
  heroLogoPressed.value = false
  heroLogoMotion.targetX = 0
  heroLogoMotion.targetY = 0
  heroLogoMotion.targetIntensity = 0
  scheduleHeroLogoMotion()
}

const handleHeroLogoPointerDown = (event: PointerEvent) => {
  heroLogoMotion.pointerActive = true
  heroLogoMotion.pressed = true
  heroLogoPressed.value = true
  updateHeroLogoPointer(event)
  const field = event.currentTarget
  if (field instanceof HTMLElement && field.setPointerCapture) field.setPointerCapture(event.pointerId)
}

const handleHeroLogoPointerUp = () => {
  heroLogoMotion.pressed = false
  heroLogoPressed.value = false
  heroLogoMotion.targetIntensity = heroLogoMotion.pointerActive
    ? Math.min(heroLogoMotion.targetIntensity, 0.18)
    : 0
  scheduleHeroLogoMotion()
}
</script>

<style scoped>
.chat-view {
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: transparent;
}

.chat-workspace-header {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 var(--wb-tab-height);
  height: var(--wb-tab-height);
  box-sizing: border-box;
  padding: 0 16px;
  background: var(--wb-surface-pane);
  color: var(--wb-text-secondary);
  font-size: 11px;
}
.chat-workspace-header .el-icon { color: var(--wb-accent); }
.chat-workspace-header span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chat-workspace-status {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 60;
  height: var(--workbench-status-bar-height, 22px);
  display: flex;
  align-items: center;
  gap: 14px;
  box-sizing: border-box;
  padding: 0 12px;
  background: var(--wb-surface-section);
  color: var(--wb-text-muted);
  font-size: 10px;
}
.chat-workspace-status__model { margin-left: auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }


.chat-main {
  flex: 1;
  min-height: 0;
  display: grid;
  /* Chat 模式第二列为停靠信息栏（宽度自持，默认 ≈ 主区对半，可拖拽调整）；
     Agent 模式由 .has-agent-results 覆盖为工作台列 */
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 0;
  padding: 0;
  transition: grid-template-columns 0.24s var(--ease-out);
}

.chat-main.has-agent-results {
  grid-template-columns: minmax(0, 1fr) var(--agent-panel-width, 340px);
  gap: 0;
  padding: 0;
}

.chat-main.has-agent-results.agent-panel-collapsed {
  grid-template-columns: minmax(0, 1fr) 52px;
}

.chat-main.agent-panel-resizing {
  transition: none;
}


.chat-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: var(--wb-surface-shell);
}

.context-panel {
  position: relative;
  z-index: 6;
  flex: 0 0 auto;
  min-height: 170px;
  overflow: hidden;
  background: color-mix(in srgb, var(--bg-card) 91%, var(--primary-fade));
  box-shadow: 0 12px 30px rgba(26, 31, 58, 0.035);
  transition: height 0.22s var(--ease-out);
}

.context-panel.resizing { transition: none; }

.context-panel__header {
  height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  padding: 0 16px;
  border-bottom: 1px solid color-mix(in srgb, var(--border-light) 72%, transparent);
}

.context-panel__identity,
.context-panel__metrics,
.context-panel__tabs,
.context-panel-dock {
  display: flex;
  align-items: center;
}

.context-panel__identity { min-width: 0; gap: 8px; }
.context-panel__identity .el-icon { color: var(--primary-color); }
.context-panel__identity strong { flex: 0 0 auto; font-size: 12px; color: var(--text-primary); }
.context-panel__identity span {
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.context-panel__metrics { flex: 0 0 auto; gap: 6px; }
.context-panel__metrics > span {
  padding: 3px 7px;
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--text-secondary);
  font-size: 9px;
  font-weight: 650;
}

.context-panel__metrics button {
  width: 26px;
  height: 26px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}
.context-panel__metrics button:hover { background: var(--primary-fade); color: var(--primary-color); }

.context-panel__tabs {
  height: 34px;
  gap: 4px;
  padding: 4px 12px 0;
}

.context-panel__tabs button {
  height: 30px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 11px;
  border: 0;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 10px;
  cursor: pointer;
}
.context-panel__tabs button.active { border-bottom-color: var(--primary-color); color: var(--primary-color); }
.context-panel__tabs button span {
  min-width: 16px;
  height: 16px;
  display: inline-grid;
  place-items: center;
  border-radius: 999px;
  background: var(--primary-fade);
  font-size: 8px;
  font-weight: 700;
}

.context-panel__body {
  height: calc(100% - 76px);
  padding: 10px 14px 14px;
  overflow: auto;
}

.context-panel__empty {
  height: 100%;
  display: grid;
  place-items: center;
  color: var(--text-disabled);
  font-size: 11px;
}

.context-lineage {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 7px;
}
.context-lineage__row {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto minmax(0, 1fr);
  align-items: center;
  gap: 7px;
  padding: 7px 9px;
  border: 1px solid color-mix(in srgb, var(--border-light) 76%, transparent);
  border-radius: 9px;
  background: color-mix(in srgb, var(--bg-card) 68%, transparent);
}
.context-node-pill {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 10px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.context-node-pill.target { color: var(--primary-color); }
.context-edge-label { color: var(--text-muted); font-size: 8px; }
.context-lineage__arrow { color: var(--primary-color); font-size: 12px; }

.context-node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(158px, 1fr));
  gap: 8px;
}
.context-node-card {
  min-width: 0;
  padding: 9px 10px;
  border: 1px solid color-mix(in srgb, var(--border-light) 78%, transparent);
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg-card) 70%, transparent);
}
.context-node-card__type {
  display: block;
  margin-bottom: 5px;
  color: var(--primary-color);
  font-size: 8px;
  font-weight: 700;
  letter-spacing: 0.08em;
}
.context-node-card strong,
.context-node-card small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.context-node-card strong { color: var(--text-primary); font-size: 10px; }
.context-node-card small { margin-top: 4px; color: var(--text-muted); font-size: 8px; }

.context-step-list { display: flex; flex-direction: column; gap: 6px; }
.context-step-item {
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  align-items: center;
  gap: 9px;
  padding: 7px 9px;
  border-radius: 9px;
  background: color-mix(in srgb, var(--bg-card) 66%, transparent);
}
.context-step-item__index { color: var(--text-disabled); font-size: 9px; font-variant-numeric: tabular-nums; }
.context-step-item strong,
.context-step-item small { display: block; }
.context-step-item strong { color: var(--text-primary); font-size: 10px; }
.context-step-item small { margin-top: 2px; color: var(--text-muted); font-size: 8px; }
.context-step-item__status { color: var(--text-muted); font-size: 9px; }
.context-step-item__status.done { color: var(--success); }

.context-panel__resizer {
  position: absolute;
  z-index: 10;
  right: 0;
  bottom: -5px;
  left: 0;
  height: 11px;
  cursor: row-resize;
  touch-action: none;
  outline: none;
}
.context-panel__resizer::before {
  content: '';
  position: absolute;
  right: 0;
  bottom: 5px;
  left: 0;
  height: 1px;
  background: transparent;
}
.context-panel__resizer > span {
  position: absolute;
  bottom: 3px;
  left: 50%;
  width: 34px;
  height: 4px;
  border-radius: 999px;
  background: var(--border-light);
  opacity: 0;
  transform: translateX(-50%);
}
.context-panel__resizer:hover::before,
.context-panel__resizer:focus-visible::before,
.context-panel.resizing .context-panel__resizer::before { background: var(--primary-color); }
.context-panel__resizer:hover > span,
.context-panel__resizer:focus-visible > span,
.context-panel.resizing .context-panel__resizer > span { opacity: 1; background: var(--primary-color); }

.context-panel-dock {
  flex: 0 0 30px;
  width: 100%;
  height: 30px;
  justify-content: center;
  gap: 7px;
  padding: 0 14px;
  border: 0;
  background: color-mix(in srgb, var(--bg-card) 94%, var(--primary-fade));
  color: var(--text-muted);
  font: inherit;
  font-size: 9px;
  cursor: pointer;
}
.context-panel-dock strong { color: var(--text-secondary); font-size: 10px; }
.context-panel-dock:hover { background: color-mix(in srgb, var(--bg-card) 88%, var(--primary-fade)); color: var(--primary-color); }
.context-panel-dock__pulse {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 0 4px var(--primary-fade);
  animation: acg-dock-pulse 1.8s ease-in-out infinite;
}

.context-panel-slide-enter-active,
.context-panel-slide-leave-active { transition: opacity 0.2s ease, transform 0.24s var(--ease-out); }
.context-panel-slide-enter-from,
.context-panel-slide-leave-to { opacity: 0; transform: translateY(-18px); }

.workflow-acg-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 34%);
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 6;
  min-height: 180px;
  overflow: hidden;
  background: color-mix(in srgb, var(--bg-card) 94%, var(--primary-fade));
  box-shadow: 0 -12px 30px rgba(26, 31, 58, 0.035);
  transition: height 0.2s var(--ease-out);
}

.workflow-acg-panel > :deep(.chat-runtime-timeline) {
  height: 100%;
  overflow: auto;
  border-top: 0;
  border-right: 0;
  border-bottom: 0;
  border-radius: 0;
  background: color-mix(in srgb, var(--bg-card) 96%, var(--primary-fade));
}

.workflow-audit-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 0;
  padding: 24px 20px;
  overflow: auto;
  border-left: 1px solid color-mix(in srgb, var(--border-light) 82%, transparent);
  background: color-mix(in srgb, var(--bg-card) 96%, var(--primary-fade));
  text-align: center;
}

.workflow-audit-empty__badge {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  margin-bottom: 10px;
  border-radius: 13px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 26px;
}

.workflow-audit-empty__title { margin: 0; color: var(--text-primary); font-size: 15px; font-weight: 600; letter-spacing: -0.02em; }
.workflow-audit-empty__hint { margin: 0; max-width: 440px; color: var(--text-secondary); font-size: 13px; line-height: 1.65; letter-spacing: -0.01em; }

.workflow-acg-panel.resizing {
  transition: none;
}

.workflow-panel-resizer {
  grid-column: 1 / -1;
  position: absolute;
  z-index: 10;
  top: -5px;
  right: 0;
  left: 0;
  height: 11px;
  cursor: row-resize;
  touch-action: none;
  outline: none;
}

.workflow-panel-resizer::before {
  content: '';
  position: absolute;
  top: 5px;
  right: 0;
  left: 0;
  height: 1px;
  background: transparent;
  transition: background-color 0.16s ease, box-shadow 0.16s ease;
}

.workflow-panel-resizer > span {
  position: absolute;
  top: 3px;
  left: 50%;
  width: 34px;
  height: 4px;
  border-radius: 999px;
  background: var(--border-light);
  opacity: 0;
  transform: translateX(-50%);
  transition: opacity 0.16s ease, background-color 0.16s ease;
}

.workflow-panel-resizer:hover::before,
.workflow-panel-resizer:focus-visible::before,
.workflow-acg-panel.resizing .workflow-panel-resizer::before {
  background: var(--primary-color);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--primary-color) 16%, transparent);
}

.workflow-panel-resizer:hover > span,
.workflow-panel-resizer:focus-visible > span,
.workflow-acg-panel.resizing .workflow-panel-resizer > span {
  opacity: 1;
  background: var(--primary-color);
}

.workflow-acg-panel :deep(.acg-topology) {
  height: 100%;
  padding: 10px 12px 8px;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}

.workflow-acg-panel :deep(.panel-head) {
  flex: 0 0 auto;
  min-height: 28px;
  margin-bottom: 4px;
}

.workflow-acg-panel :deep(.graph-stage) {
  flex: 1 1 auto;
  min-height: 0;
}

.workflow-acg-panel :deep(.graph-canvas) {
  flex: 1 1 auto;
  height: auto;
  min-height: 0;
}

.workflow-acg-panel :deep(.node-detail) {
  height: auto;
  min-height: 0;
}

.workflow-acg-panel :deep(.legend) {
  flex: 0 0 auto;
  margin-top: 4px;
  padding-top: 6px;
}

.workflow-acg-loading {
  grid-column: 1 / -1;
  position: absolute;
  inset: 42px 0 0;
  display: grid;
  place-items: center;
  color: var(--text-disabled);
  font-size: 12px;
  pointer-events: none;
}

@media (max-width: 900px) {
  .workflow-acg-panel {
    grid-template-columns: minmax(0, 1fr) minmax(220px, 38%);
  }
}

.workflow-acg-dock {
  flex: 0 0 30px;
  width: 100%;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 14px;
  border: 0;
  background: color-mix(in srgb, var(--bg-card) 94%, var(--primary-fade));
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.workflow-acg-dock:hover,
.workflow-acg-dock:focus-visible {
  background: var(--primary-fade);
  color: var(--primary-color);
  outline: none;
}

.workflow-acg-dock__pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 0 4px var(--primary-fade);
  animation: acg-dock-pulse 2s ease-in-out infinite;
}

.workflow-acg-dock.idle .workflow-acg-dock__pulse {
  background: var(--text-disabled);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--text-disabled) 12%, transparent);
  animation: none;
}

.workflow-acg-dock__meta {
  color: var(--text-disabled);
  font-weight: 500;
}

.workflow-acg-dock .el-icon {
  margin-left: 2px;
}

@keyframes acg-dock-pulse {
  50% { opacity: 0.55; transform: scale(0.86); }
}

.workflow-acg-slide-enter-active,
.workflow-acg-slide-leave-active {
  transition: opacity 0.2s ease, transform 0.24s var(--ease-out);
}

.workflow-acg-slide-enter-from,
.workflow-acg-slide-leave-to {
  opacity: 0;
  transform: translateY(18px);
}

.chat-panel.hero-mode {
  --hero-composer-center-y: 57%;
  --hero-slogan-offset-y: 236px;
}

.chat-main.hero-settling .chat-panel.hero-mode .empty-state { visibility: hidden; animation: none; }
.chat-main.hero-settling .chat-panel.hero-mode .composer { visibility: hidden; }

.chat-panel.hero-mode .messages {
  overflow: hidden;
  padding-bottom: 0;
}

.chat-panel.hero-mode .empty-state {
  position: absolute;
  top: calc(var(--hero-composer-center-y) - var(--hero-slogan-offset-y));
  left: 50%;
  z-index: 3;
  width: min(calc(100% - 48px), 640px);
  margin: 0;
  transform: translate(-50%, -50%);
  pointer-events: none;
  animation: hero-fade-in 0.28s var(--ease-out);
}

.chat-panel.hero-mode .composer {
  position: absolute;
  top: calc(var(--hero-composer-center-y) + var(--hero-composer-offset-y, 0px));
  right: 0;
  left: 0;
  z-index: 4;
  transform: translateY(-50%);
}

@keyframes hero-fade-in {
  from { opacity: 0; transform: translate(-50%, calc(-50% + 8px)); }
  to { opacity: 1; transform: translate(-50%, -50%); }
}

.chat-panel:not(.hero-mode) .composer {
  position: absolute;
  right: 0;
  left: 0;
  z-index: 5;
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 22px 16px var(--composer-clearance, 220px);
  scroll-padding-bottom: var(--composer-clearance, 220px);
}

.messages::-webkit-scrollbar {
  width: 5px;
}

.messages::-webkit-scrollbar-track {
  background: transparent;
}

.messages::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 999px;
}

.empty-state {
  margin: 64px auto;
  text-align: center;
  max-width: 640px;
  animation: fade-in 0.28s var(--ease-out);
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.hero-watermark {
  display: block;
  width: 190px;
  height: auto;
  margin: 0 auto 4px;
  opacity: 1;
  user-select: none;
  pointer-events: none;
}

.hero-greeting {
  font-family: var(--font-serif);
  font-size: 30px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--text-primary);
  margin: 0;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.messages-shell {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.conversation-rail {
  position: absolute;
  top: 50%;
  left: 6px;
  z-index: 6;
  display: flex;
  max-height: 76%;
  flex-direction: column;
  transform: translateY(-50%);
}

.conversation-rail__ticks {
  display: flex;
  flex: 0 1 auto;
  min-height: 0;
  flex-direction: column;
  gap: 2px;
  padding: 4px 7px;
  overflow-y: auto;
  border-radius: 12px;
  scrollbar-width: none;
}

.conversation-rail__ticks::-webkit-scrollbar {
  display: none;
}

.conversation-rail__tick {
  flex: none;
  /* 统一宽度：18px 横杠 + 左右各 6px 命中区，静止时全部刻度左右边缘对齐 */
  width: 30px;
  height: 10px;
  padding: 0 6px;
  display: flex;
  align-items: center;
  border: 0;
  background: transparent;
  cursor: pointer;
  box-sizing: border-box;
}

.conversation-rail__tick::after {
  content: '';
  width: 100%;
  height: 2px;
  border-radius: 0;
  background: color-mix(in srgb, var(--text-secondary) 36%, transparent);
  transition: background-color 0.16s var(--ease-out), height 0.16s var(--ease-out);
}

.conversation-rail__tick:hover::after {
  height: 3px;
  background: color-mix(in srgb, var(--text-primary) 64%, transparent);
}

.conversation-rail__tick.is-active::after {
  background: var(--accent-color);
}

.conversation-rail__tick.is-active:hover::after {
  background: var(--accent-color);
}

.conversation-rail__preview {
  position: absolute;
  top: 0;
  left: calc(100% + 2px);
  z-index: 8;
  width: min(320px, 56vw);
  padding: 10px 12px 11px;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--bg-panel);
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.36);
  transform: translateY(-50%);
  text-align: left;
  pointer-events: none;
}

.conversation-rail__preview-round {
  display: block;
  margin-bottom: 4px;
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--text-secondary);
}

.conversation-rail__preview p {
  margin: 0;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--text-primary);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 5;
  overflow: hidden;
  overflow-wrap: anywhere;
}

.rail-preview-enter-active,
.rail-preview-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}

.rail-preview-enter-from,
.rail-preview-leave-to {
  opacity: 0;
  transform: translateY(-50%) translateX(-4px);
}

.message-row.rail-flash {
  border-radius: 12px;
  animation: rail-flash-highlight 1.6s var(--ease-out);
}

@keyframes rail-flash-highlight {
  0% {
    background: var(--accent-fade);
    box-shadow: inset 2px 0 0 var(--accent-color);
  }
  100% {
    background: transparent;
    box-shadow: inset 2px 0 0 transparent;
  }
}

.workflow-history-detail {
  display: flex;
  width: min(100%, 920px);
  margin: 0 auto;
  flex-direction: column;
  gap: 18px;
  animation: fade-in 0.24s var(--ease-out);
}

.workflow-history-loading {
  display: flex;
  min-height: 220px;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: var(--text-secondary);
}
.workflow-history-loading.is-error { flex-direction: column; }
.workflow-history-loading strong { color: var(--text-primary); font-size: 14px; }
.workflow-history-loading button,
.workflow-history-partial button {
  min-height: 30px;
  padding: 0 10px;
  border: 1px solid var(--primary-line);
  border-radius: 6px;
  background: var(--primary-fade);
  color: var(--primary-color);
  cursor: pointer;
}
.workflow-history-partial {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 9px 12px;
  border: 1px solid color-mix(in srgb, var(--warning) 34%, var(--border-light));
  border-radius: 7px;
  background: var(--warning-fade);
  color: var(--text-secondary);
  font-size: 12px;
}


.workflow-history-request {
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: var(--surface-solid);
  box-shadow: var(--shadow-sm);
}

.workflow-history-request header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border-light);
}

.workflow-history-eyebrow {
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.workflow-history-request h3 {
  margin: 5px 0 0;
  color: var(--text-primary);
  font-size: 17px;
}

.workflow-history-identity {
  display: flex;
  min-width: 0;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  color: var(--text-secondary);
  font-size: 11px;
}

.workflow-history-identity code {
  max-width: 240px;
  overflow: hidden;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-history-request pre {
  max-height: 320px;
  margin: 0;
  padding: 18px 20px;
  overflow: auto;
  color: var(--text-primary);
  font: inherit;
  font-size: 14px;
  line-height: 1.75;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.template-row {
  display: flex;
  gap: 8px;
  padding: 10px 16px 0;
  overflow-x: auto;
}

/* 右侧工作台滑入动画 */
/* 切回 Chat 模式时 has-agent-results 先于面板卸载移除，若不脱离布局流，
   离开中的面板会掉进网格第二行把主面板压扁，英雄区随 57% 锚点滑动。 */
.chat-main:not(.has-agent-results) > .agent-panel { display: none; }

/* —— Chat 模式右侧停靠信息栏（ZCode/DSH 式：拖宽 + 收起 + 持久化）—— */
.chat-info-dock {
  box-sizing: border-box;
  position: relative;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--wb-surface-pane);
  border-left: 0;
  transition: width 0.16s var(--ease-out);
}

.chat-info-dock.resizing { transition: none; }

.chat-info-dock__resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 12;
  width: 8px;
  cursor: col-resize;
  touch-action: none;
  outline: none;
}

.chat-info-dock__resizer::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 2px;
  background: var(--primary-color);
  opacity: 0;
  transform: scaleY(0.96);
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.chat-info-dock__resizer:hover::after,
.chat-info-dock__resizer:focus-visible::after,
.chat-info-dock.resizing .chat-info-dock__resizer::after {
  opacity: 0.8;
  transform: scaleY(1);
}

.chat-info-dock__header {
  flex: 0 0 var(--wb-tab-height);
  height: var(--wb-tab-height);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0 14px 0 16px;
}

.chat-info-dock__eyebrow {
  font-size: 10px;
  font-weight: 650;
  letter-spacing: 0.12em;
  color: var(--text-secondary);
}

.chat-info-dock__collapse {
  width: 26px;
  height: 26px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.chat-info-dock__collapse:hover {
  background: var(--bg-panel);
  color: var(--text-primary);
}

.chat-info-dock__collapse:focus-visible,
.chat-info-dock__expand:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.chat-info-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 12px 16px 18px;
  overflow-y: auto;
}

.chat-info-card__title {
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-info-card__metrics {
  margin: 0;
  /* 宽信息卡下指标自动换列，窄卡退化为单列 */
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 10px 22px;
}

.chat-info-card__row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.chat-info-card__row dt {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--text-secondary);
}

.chat-info-card__row dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  font-size: 12px;
  color: var(--text-primary);
  text-align: right;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-info-card__rule {
  height: 1px;
  background: color-mix(in srgb, var(--border-light) 78%, transparent);
}

.chat-info-card__section {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 650;
  color: var(--text-secondary);
}

.chat-info-card__section span {
  min-width: 18px;
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 10px;
  text-align: center;
}

.chat-info-card__sources {
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  list-style: none;
}

.chat-info-card__sources li {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.chat-info-card__sources .el-icon {
  flex: 0 0 auto;
  color: var(--text-muted);
}

.chat-info-card__sources span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-info-dock__rail {
  flex: 1;
  display: flex;
  justify-content: center;
  padding-top: 14px;
}

.chat-info-dock__expand {
  width: 30px;
  height: 30px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.chat-info-dock__expand:hover {
  background: var(--primary-fade);
  color: var(--primary-color);
}
.agent-panel-slide-enter-active {
  transition: opacity 0.22s var(--ease-out), transform 0.22s var(--ease-out);
}
.agent-panel-slide-leave-active {
  transition: opacity 0.18s ease, transform 0.18s ease;
}
.agent-panel-slide-enter-from {
  opacity: 0;
  transform: translateX(12px);
}
.agent-panel-slide-leave-to {
  opacity: 0;
  transform: translateX(12px);
}

@media (prefers-reduced-motion: reduce) {
  .agent-panel-slide-enter-active,
  .agent-panel-slide-leave-active {
    transition: none;
  }
}

.template-item {
  border: 1px solid var(--border-light);
  background: var(--bg-card);
  border-radius: 8px;
  padding: 6px 14px;
  white-space: nowrap;
  cursor: pointer;
  font-size: 13px;
  transition: var(--transition);
}

.template-item:hover {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}

.composer {
  flex-shrink: 0;
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 8px 14px 12px;
  background: transparent;
  will-change: transform;
}

.chat-workflow-progress,
.chat-workflow-review,
.chat-workflow-error {
  order: 0;
  /* 与消息列（780px）对齐：不再随面板拉宽 */
  width: min(100%, 780px);
  margin: 0 auto 7px;
}
.chat-workflow-error {
  padding: 8px 10px;
  border: 1px solid color-mix(in srgb, var(--danger) 36%, var(--border-light));
  border-radius: 6px;
  background: var(--danger-fade);
  color: var(--danger);
  font-size: 12px;
  line-height: 1.45;
  text-wrap: pretty;
}

.workflow-run-strip {
  order: 0;
  width: min(100%, 780px);
  min-height: 34px;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 auto 7px;
  padding: 5px 7px 5px 10px;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-card);
  color: var(--text-secondary);
  box-shadow: var(--shadow-sm);
}

.workflow-run-strip__state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 650;
}

.workflow-run-strip__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--primary-color);
}

.workflow-run-strip.waiting_review .workflow-run-strip__dot,
.workflow-run-strip.retrying .workflow-run-strip__dot {
  background: var(--warning);
}

.workflow-run-strip.completed .workflow-run-strip__dot {
  background: var(--success);
}

.workflow-run-strip.failed .workflow-run-strip__dot {
  background: var(--danger);
}

.workflow-run-strip.cancelled .workflow-run-strip__dot { background: var(--text-muted); }

.workflow-run-strip code {
  min-width: 96px;
  max-width: 180px;
  overflow: hidden;
  color: var(--text-primary);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-run-strip__workflow {
  min-width: 0;
  flex: 1 1 auto;
  overflow: hidden;
  color: var(--text-muted);
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.workflow-run-strip__actions {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 0 0 auto;
}

.workflow-run-strip__actions button {
  height: 24px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 0 7px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--primary-color);
  font: inherit;
  font-size: 10px;
  font-weight: 600;
  cursor: pointer;
}

.workflow-run-strip__actions button:hover,
.workflow-run-strip__actions button:focus-visible {
  background: var(--primary-fade);
  outline: none;
}

.workflow-run-strip__actions button:disabled {
  cursor: wait;
  opacity: 0.55;
}

.composer-popover {
  order: 0;
  width: 50%;
  margin: 0 auto 7px;
  border: 1px solid var(--border-light);
  border-radius: 12px;
  background: var(--bg-card);
  box-shadow: var(--shadow-md);
}

.composer-popover.template-row {
  padding: 6px;
}

.composer-popover.template-row .template-item {
  padding: 4px 10px;
  font-size: 12px;
}

.composer-shelf {
  order: 2;
  position: relative;
  z-index: 1;
  width: calc(50% - 24px);
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 4px;
  margin: -2px auto 0;
  padding: 7px 14px 6px;
  overflow-x: auto;
  border: 1px solid color-mix(in srgb, var(--primary-color) 14%, var(--border-light));
  border-top-color: color-mix(in srgb, var(--primary-color) 9%, var(--border-light));
  border-radius: 0 0 16px 16px;
  background:
    linear-gradient(120deg,
      color-mix(in srgb, var(--primary-fade) 42%, transparent),
      color-mix(in srgb, var(--bg-sidebar) 78%, transparent) 28%,
      color-mix(in srgb, var(--bg-sidebar) 72%, transparent) 72%,
      color-mix(in srgb, var(--accent-fade) 34%, transparent));
  backdrop-filter: blur(16px) saturate(1.08);
  -webkit-backdrop-filter: blur(16px) saturate(1.08);
  box-shadow:
    0 12px 30px color-mix(in srgb, var(--text-primary) 6%, transparent),
    -16px 8px 30px color-mix(in srgb, var(--bg-app) 42%, transparent),
    16px 8px 30px color-mix(in srgb, var(--bg-app) 42%, transparent);
}

.composer-shelf-action {
  height: 26px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 0 7px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.composer-shelf-action:hover,
.composer-shelf-action.active {
  background: var(--bg-panel);
  color: var(--text-primary);
}

.composer-shelf-action:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.composer-card {
  order: 1;
  position: relative;
  z-index: 2;
  /* 与消息列（780px 内容宽）对齐，宽窄面板下都保持同一列宽 */
  width: min(100%, 780px);
  min-height: 112px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  margin: 0 auto;
  overflow: hidden;
  border: 1px solid transparent;
  border-radius: 18px;
  background:
    linear-gradient(color-mix(in srgb, var(--bg-card) 82%, transparent), color-mix(in srgb, var(--bg-card) 82%, transparent)) padding-box,
    linear-gradient(115deg,
      color-mix(in srgb, var(--primary-color) 26%, var(--border-light)),
      color-mix(in srgb, var(--border-light) 76%, transparent) 34%,
      color-mix(in srgb, var(--accent-color) 18%, var(--border-light)) 76%,
      color-mix(in srgb, var(--primary-color) 30%, var(--border-light))) border-box;
  backdrop-filter: blur(18px) saturate(1.08);
  -webkit-backdrop-filter: blur(18px) saturate(1.08);
  box-shadow:
    0 18px 44px color-mix(in srgb, var(--text-primary) 9%, transparent),
    0 4px 16px color-mix(in srgb, var(--primary-color) 8%, transparent),
    -28px 10px 46px color-mix(in srgb, var(--bg-app) 58%, transparent),
    28px 10px 46px color-mix(in srgb, var(--bg-app) 58%, transparent);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.composer-card:focus-within {
  border-color: var(--border-focus);
  box-shadow: 0 0 0 4px var(--primary-fade), var(--shadow-md);
}

.composer-card > .el-textarea,
.composer-card > .el-input {
  flex: 1 1 auto;
  display: block;
  width: 100%;
  padding: 13px 16px 0;
  background: transparent;
}

.composer :deep(.el-textarea__inner) {
  min-height: 50px !important;
  padding: 2px 0 0 !important;
  border: 0 !important;
  background: transparent !important;
  box-shadow: none !important;
  font-size: 14px;
  line-height: 1.6;
}

/* Conversation state: collapse the capability composer into a Codex-like input bar. */
.chat-panel:not(.hero-mode) .composer-shelf {
  display: none;
}

.chat-panel:not(.hero-mode) .composer-card {
  min-height: 76px;
  border-radius: 18px;
}

.chat-panel:not(.hero-mode) .composer-card > .el-textarea,
.chat-panel:not(.hero-mode) .composer-card > .el-input {
  padding: 9px 14px 0;
}

.chat-panel:not(.hero-mode) .composer :deep(.el-textarea__inner) {
  min-height: 28px !important;
  line-height: 1.45;
}

.chat-panel:not(.hero-mode) .composer-footer {
  padding: 2px 9px 7px;
}

.composer-footer {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 4px 10px 8px;
}

/* ZCode 式两层输入卡：上层深一档托盘条与卡片同宽（略内收），下层浅色卡片叠压其上 */
.composer-missions {
  order: 0;
  position: relative;
  z-index: 1;
  width: calc(60% - 32px);
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 10px 12px 28px;
  border: 1px solid var(--border-light);
  border-radius: 14px;
  background: color-mix(in srgb, var(--text-secondary) 7%, var(--bg-card));
}

.composer-missions__workspace {
  min-width: 0;
}

/* Conversation state: the same shelf becomes a transparent status strip above the input. */
.composer-missions.is-conversation {
  width: min(100%, 780px);
  margin: 0 auto 6px;
  padding: 0 2px;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.chat-panel.hero-mode .composer-card {
  width: 60%;
  margin-top: -20px;
  min-height: 140px;
  box-shadow:
    0 22px 48px color-mix(in srgb, var(--text-primary) 13%, transparent),
    0 4px 16px color-mix(in srgb, var(--primary-color) 9%, transparent),
    -28px 10px 46px color-mix(in srgb, var(--bg-app) 58%, transparent),
    28px 10px 46px color-mix(in srgb, var(--bg-app) 58%, transparent);
}


.left-actions,
.right-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}

.composer-icon-action {
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 16px;
  cursor: pointer;
  transition: background-color 0.16s ease, color 0.16s ease;
}

.composer-icon-action:hover,
.composer-icon-action.active {
  background: var(--primary-fade);
  color: var(--primary-color);
}

.composer-acg-toggle {
  height: 25px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 8px;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.16s ease, background-color 0.16s ease;
}

.composer-acg-toggle:hover,
.composer-acg-toggle:focus-visible,
.composer-acg-toggle.active {
  background: var(--primary-fade);
  color: var(--primary-color);
  outline: none;
}

.composer-acg-toggle:disabled {
  cursor: not-allowed;
  opacity: 0.42;
}

.composer-send.el-button {
  width: 34px;
  height: 34px;
  margin-left: 2px;
  padding: 0;
  border-radius: 50%;
}

.word-count {
  color: var(--text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.hidden-file-input {
  display: none;
}

.word-count.warning {
  color: #f59e0b;
}

.context-usage {
  min-height: 22px;
  padding: 2px 8px;
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: transparent;
  color: var(--text-muted);
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.4;
  white-space: nowrap;
  cursor: default;
  transition: color 160ms ease, border-color 160ms ease;
}

.context-usage.normal {
  color: var(--text-secondary);
}

.context-usage.warning {
  color: #f59e0b;
  border-color: color-mix(in srgb, #f59e0b 45%, transparent);
}

.context-usage.danger {
  color: #ef4444;
  border-color: color-mix(in srgb, #ef4444 45%, transparent);
}

.context-usage-tip {
  text-align: center;
  line-height: 1.6;
}

.agent-panel {
  position: relative;
  background: var(--bg-sidebar);
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
  border: 0;
  border-radius: 0;
  transition: background-color 0.2s ease;
}

.agent-panel-resizer {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  z-index: 12;
  width: 8px;
  cursor: col-resize;
  touch-action: none;
  outline: none;
}

.agent-panel-resizer::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 2px;
  background: var(--primary-color);
  opacity: 0;
  transform: scaleY(0.96);
  transition: opacity 0.16s ease, transform 0.16s ease;
}

.agent-panel-resizer:hover::after,
.agent-panel-resizer:focus-visible::after,
.agent-panel.resizing .agent-panel-resizer::after {
  opacity: 0.8;
  transform: scaleY(1);
}

.agent-panel-toggle-row {
  position: absolute;
  top: 0;
  right: 8px;
  z-index: 20;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  border: 0;
}

.agent-panel-toggle {
  min-width: 30px;
  width: 30px;
  height: 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  padding: 0;
  border: 0;
  border-radius: 7px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  box-shadow: none;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.agent-panel-toggle:hover {
  background: var(--bg-panel);
  color: var(--text-primary);
  box-shadow: none;
}

.agent-panel-toggle span {
  display: none;
}

.agent-panel-toggle:focus-visible {
  outline: 2px solid var(--primary-color);
  outline-offset: 2px;
}

.agent-panel.collapsed .agent-panel-toggle-row {
  position: static;
  flex: 0 0 54px;
  height: 54px;
  justify-content: center;
  padding: 0;
}

.agent-panel.collapsed .agent-panel-toggle {
  width: 38px;
  padding: 0;
  font-size: 16px;
}

.agent-panel-content {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: auto;
}

.agent-panel-rail {
  flex: 1;
  display: flex;
  justify-content: center;
  padding-top: 14px;
}

.agent-panel-rail-icon {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 9px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 17px;
}
@media (max-width: 900px) {
  .workflow-run-strip,
  .chat-workflow-progress,
  .chat-workflow-review,
  .chat-workflow-error {
    width: calc(100% - 32px);
  }


}

@media (max-width: 620px) {
  .composer-card,
  .workflow-run-strip,
  .chat-workflow-progress,
  .chat-workflow-review,
  .chat-workflow-error {
    width: 100%;
  }

  .composer-missions {
    width: calc(100% - 32px);
  }

  .workflow-run-strip {
    flex-wrap: wrap;
    overflow: visible;
  }

  .workflow-run-strip__workflow {
    display: none;
  }

  .workflow-run-strip__actions {
    margin-left: auto;
  }


  .chat-main .empty-state {
    margin: 18px auto;
    padding: 0 12px;
  }

  .chat-main .hero-watermark {
    width: 128px;
  }

  .chat-main .hero-greeting {
    font-size: 24px;
  }

  .chat-main .template-row {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    overflow: visible;
  }

  .chat-main .template-item {
    min-width: 0;
    padding: 6px 8px;
    white-space: normal;
  }


  .chat-main .composer-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .composer-footer .left-actions {
    width: 100%;
  }


  .composer-footer .right-actions {
    display: grid;
    grid-template-columns: 1fr auto;
    width: 100%;
  }

  .composer-footer .right-actions :deep(.model-runtime-controls) {
    grid-column: 1 / -1;
    width: 100%;
  }

}

@media (max-width: 1100px) {
  .chat-main.has-agent-results {
    grid-template-columns: 1fr;
  }

  /* 窄窗口收起对话信息栏，保证消息列可用宽度 */
  .chat-main {
    grid-template-columns: 1fr;
  }

  .chat-info-dock {
    display: none;
  }

  .agent-panel {
    border-left: none;
    border-top: 1px solid var(--border-light);
    max-height: 300px;
  }

  .agent-panel-resizer {
    display: none;
  }

}

/* Screenshot refinement: quieter surfaces, clearer focus, and a lighter hero rhythm. */
.chat-panel.hero-mode {
  --hero-composer-center-y: 55.5%;
  --hero-slogan-offset-y: 218px;
  /* Keep breathing room between the hero slogan and the composer shelf. */
  --hero-composer-offset-y: 24px;
}

.chat-panel.hero-mode .empty-state {
  width: min(calc(100% - 48px), 720px);
}

.hero-watermark {
  width: 170px;
  margin-bottom: 12px;
  opacity: 0.94;
  filter: saturate(0.9) brightness(0.94);
}

.hero-logo-field {
  --hero-logo-aura-opacity: 0.12;
  --hero-logo-aura-scale: 1;
  position: relative;
  width: 170px;
  aspect-ratio: 1;
  display: grid;
  place-items: center;
  margin: 0 auto 12px;
  isolation: isolate;
  pointer-events: auto;
  cursor: default;
  touch-action: none;
}

.hero-logo-field::before {
  position: absolute;
  inset: 22%;
  z-index: -1;
  border-radius: 50%;
  background: radial-gradient(circle, color-mix(in srgb, var(--primary-color) 18%, transparent), transparent 70%);
  content: '';
  opacity: var(--hero-logo-aura-opacity);
  transform: scale(var(--hero-logo-aura-scale));
  filter: blur(18px);
  pointer-events: none;
  transition: opacity 260ms ease, transform 260ms ease;
}

.hero-logo-filter-defs {
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
  pointer-events: none;
}

.hero-logo-field .hero-watermark {
  width: 100%;
  margin: 0;
  filter: url('#hero-logo-fluid') saturate(0.9) brightness(0.94);
  transform-origin: center;
  will-change: transform, filter;
  pointer-events: none;
  transition: filter 240ms ease;
}

.hero-logo-field.is-pressed::before {
  opacity: 0.38;
}

.hero-greeting {
  font-size: 32px;
  font-weight: 580;
  letter-spacing: 0.015em;
  text-wrap: balance;
}

.composer-card {
  border: 0;
  border-radius: 22px;
  background: color-mix(in srgb, var(--bg-card) 94%, var(--bg-panel));
  overflow: visible;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: 0 18px 44px rgba(0, 0, 0, 0.3);
}

.composer-card:focus-within {
  box-shadow:
    0 18px 44px rgba(0, 0, 0, 0.38),
    0 0 30px color-mix(in srgb, var(--accent-color) 12%, transparent);
}

.chat-panel.hero-mode .composer-card {
  margin-top: -16px;
  min-height: 134px;
  box-shadow: 0 20px 46px rgba(0, 0, 0, 0.36);
}

.composer-footer {
  margin-top: 0;
  padding-top: 4px;
  border-top: 0;
}

.composer-missions {
  padding: 8px 12px 24px;
  border: 0;
  border-radius: 18px 18px 0 0;
  background: color-mix(in srgb, var(--bg-card) 54%, transparent);
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  box-shadow: none;
}

.composer-card :deep(.model-runtime-controls) {
  gap: 2px;
}

.composer-card :deep(.model-runtime-controls .el-select__wrapper) {
  min-height: 26px;
  padding: 0 4px;
  border: 0 !important;
  border-radius: 0;
  background: transparent !important;
  box-shadow: none !important;
}

.composer-card :deep(.model-runtime-controls .el-select__wrapper:hover),
.composer-card :deep(.model-runtime-controls .el-select__wrapper.is-focused) {
  background: color-mix(in srgb, var(--text-primary) 6%, transparent) !important;
  box-shadow: none !important;
}

.composer-tools-anchor {
  position: relative;
  display: inline-flex;
  align-items: center;
}

.composer-tools-toggle.active {
  background: color-mix(in srgb, var(--primary-color) 14%, transparent);
  color: var(--primary-color);
}

.composer-tools-menu {
  position: absolute;
  bottom: calc(100% + 12px);
  left: 0;
  z-index: 30;
  width: min(360px, calc(100vw - 36px));
  padding: 10px 12px;
  border: 0;
  border-radius: 16px;
  background: color-mix(in srgb, var(--bg-card) 96%, var(--bg-panel));
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.34);
}

.composer-tools-menu__item {
  width: 100%;
  height: 32px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 7px;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  text-align: left;
  cursor: pointer;
}

.composer-tools-menu__item:hover,
.composer-tools-menu__item:focus-visible {
  background: color-mix(in srgb, var(--text-primary) 7%, transparent);
  color: var(--text-primary);
  outline: none;
}

.composer-tools-menu__runtime {
  display: grid;
  gap: 4px;
  margin-top: 6px;
  padding: 4px 0 0;
}

.composer-tools-menu__label {
  padding: 0 7px;
  color: var(--text-muted);
  font-size: 10px;
  line-height: 1.4;
}

.composer-tools-menu__runtime :deep(.model-runtime-controls) {
  width: 100%;
  justify-content: space-between;
}





.composer-icon-action:hover,
.composer-icon-action.active {
  background: color-mix(in srgb, var(--primary-color) 18%, transparent);
}

/* 按钮配色取自首页花环：白花 #E2E1DA / 松果褐 #482E19 */
.composer-send.el-button {
  width: 38px;
  height: 38px;
  border-color: transparent;
  background: #E2E1DA;
  color: #482E19;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}

.composer-send.el-button:hover,
.composer-send.el-button:focus-visible {
  border-color: transparent;
  background: #EFEEE6;
  color: #482E19;
}

.composer-send.el-button:active {
  background: #D6D4C9;
}

.composer-send.el-button:focus-visible {
  outline: 2px solid rgba(226, 225, 218, 0.42);
  outline-offset: 2px;
}

/* 放在 hover 之后：同优先级下靠源顺序压过 hover，避免禁用态悬停变亮 */
.composer-send.el-button:disabled {
  border-color: transparent;
  background: color-mix(in srgb, #E2E1DA 14%, var(--bg-panel));
  color: rgba(226, 225, 218, 0.38);
  box-shadow: none;
}

@media (max-width: 900px) {
  .hero-watermark { width: 128px; }
  .hero-logo-field { width: 128px; }
  .hero-greeting { font-size: 24px; }
  .composer-footer { margin-top: 8px; }
}

@media (prefers-reduced-motion: reduce) {
  .hero-logo-field::before {
    display: none;
  }

  .hero-logo-field .hero-watermark {
    filter: saturate(0.9) brightness(0.94);
    transform: none !important;
    transition: none;
  }
}
</style>
