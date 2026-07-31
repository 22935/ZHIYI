<!-- 主对话页面 — 角色快速导航（律师/教师/程序员/作家）与聊天工作台 -->
<template>
  <div class="chat-view detail-interface">
    <div
      class="chat-main"
      :class="[
        chatMainClass,
        {
          'has-agent-results': isAgentMode,
          'agent-panel-collapsed': isAgentMode && agentPanelCollapsed,
          'agent-panel-resizing': agentPanelResizing
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
        <Transition name="context-panel-slide" @after-leave="finishContextPanelClose">
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
                  <el-icon><ArrowUp /></el-icon>
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

        <div class="messages" ref="messagesRef">
          <div v-if="showHeroMode" class="empty-state">
            <div class="rgb-orb" aria-hidden="true">
              <span class="rgb-orb__aura"></span>
              <span class="rgb-orb__core"></span>
              <span class="rgb-orb__ring rgb-orb__ring--outer"></span>
              <span class="rgb-orb__ring rgb-orb__ring--inner"></span>
              <span class="rgb-orb__particle rgb-orb__particle--1"></span>
              <span class="rgb-orb__particle rgb-orb__particle--2"></span>
              <span class="rgb-orb__particle rgb-orb__particle--3"></span>
              <span class="rgb-orb__particle rgb-orb__particle--4"></span>
              <span class="rgb-orb__particle rgb-orb__particle--5"></span>
              <span class="rgb-orb__particle rgb-orb__particle--6"></span>
            </div>
            <h2>{{ agentTitle }}</h2>
            <p>{{ agentSubtitle }}</p>
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
                  modelInfo: msg.modelInfo,
                  thinkingState: msg.thinkingState,
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

        <div ref="composerRef" class="composer" :style="{ bottom: composerDockOffset }">
          <div
            v-if="isSubmittingWorkflow || activeWorkflowRunId"
            class="chat-workflow-progress"
          >
            <WorkflowProgressBar
              :progress="workflowProgressState.progress.value"
              :loading="isSubmittingWorkflow || workflowProgressState.isLoading.value"
              :sync-error="workflowProgressState.syncError.value"
              variant="compact"
            />
            <DynamicRunSummaryCard
              :progress="workflowProgressState.progress.value"
              :run="activeWorkflowRun"
              :view="activeAcgView"
            />
          </div>

          <p v-if="workflowStartError" class="chat-workflow-error" role="alert">
            {{ workflowStartError }}
          </p>

          <WorkflowReviewPanel
            v-if="activeWorkflowRunId && activeWorkflowStatus === 'waiting_review'"
            class="chat-workflow-review"
            :run-id="activeWorkflowRunId"
            :progress="workflowProgressState.progress.value"
            :run="activeWorkflowRun"
            compact
            @reviewed="handleChatWorkflowReviewed"
            @conflict="handleChatReviewConflict"
          />

          <div
            v-if="activeWorkflowRunId"
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

          <div v-if="showAssistTools && currentTemplates.length" class="composer-popover template-row">
            <button v-for="tpl in currentTemplates" :key="tpl" class="template-item" @click="useTemplate(tpl)">
              {{ tpl }}
            </button>
          </div>

          <div v-show="!recommendationCollapsed" class="composer-popover recommendation-panel-wrap">
            <RecommendationPanel
              title="下一步推荐"
              subtitle="基于当前角色和最近对话生成"
              :items="chatRecommendations"
              :loading="recommendationLoading"
              refreshable
              @refresh="loadChatRecommendations"
              @select="applyChatRecommendation"
            />
          </div>

          <div class="composer-shelf">
            <button class="composer-shelf-action" type="button" @click="handleControl('folder')">
              <el-icon><Folder /></el-icon>
              <span>选择文件</span>
            </button>
            <button class="composer-shelf-action" type="button" @click="toggleAssistTools">
              <el-icon><Notebook /></el-icon>
              <span>快捷模板</span>
            </button>
            <button
              class="composer-shelf-action"
              type="button"
              :class="{ active: !recommendationCollapsed }"
              :aria-expanded="!recommendationCollapsed"
              @click="toggleRecommendationPanel"
            >
              <span v-if="recommendationLoading" class="recommendation-loading-dot" aria-hidden="true"></span>
              <span>下一步推荐</span>
              <span class="composer-shelf-count">{{ chatRecommendations.length }}</span>
            </button>
            <button
              class="composer-shelf-action"
              type="button"
              :disabled="isWorkflowUpgradeDisabled"
              @click="upgradeChatToWorkflow"
            >
              <span>{{ isSubmittingWorkflow ? '正在创建' : 'Workflow' }}</span>
            </button>
            <button v-if="isTeacherMode" class="composer-shelf-action" type="button" @click="openTeacherUploadDialog">
              <el-icon><UploadFilled /></el-icon>
              <span>上传作业</span>
            </button>
            <input
              ref="teacherUploadInputRef"
              class="hidden-file-input"
              type="file"
              accept=".png,.jpg,.jpeg,.pdf,.txt,.doc,.docx"
              @change="handleTeacherFileUpload"
            />
          </div>

          <div class="composer-card">
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
                <button class="composer-icon-action" type="button" aria-label="添加文件" title="添加文件" @click="handleControl('folder')">
                  <el-icon><Plus /></el-icon>
                </button>
                <button
                  class="composer-agent-mode"
                  type="button"
                  aria-haspopup="dialog"
                  :aria-expanded="roleTemplateDialogOpen"
                  title="切换角色与模板"
                  @click="openRoleTemplateDialog"
                >
                  <el-icon><component :is="agentIcon" /></el-icon>
                  {{ currentRole?.name || 'Agent' }} 模式
                  <el-icon class="composer-agent-mode__chevron"><ArrowDownBold /></el-icon>
                </button>
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
              </div>
              <div class="right-actions">
                <span v-if="isAgentMode" class="composer-runtime-lock" title="简单问答直接响应，专业任务自动进入 ACG Workflow">
                  <el-icon><Share /></el-icon>
                  ACG 路由
                </span>
                <ModelRuntimeControls v-else compact />
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
                <el-button class="composer-send" type="primary" :disabled="isSendDisabled" @click="sendMessage">
                  <el-icon v-if="!loading"><ArrowUp /></el-icon>
                  <el-icon v-else class="is-loading"><Loading /></el-icon>
                </el-button>
              </div>
            </div>
          </div>
        </div>

        <Transition name="workflow-acg-slide">
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
            <RuntimeChangeTimeline
              v-if="activeAcgView"
              class="chat-runtime-timeline"
              :runtime-events="activeAcgView.runtimeEvents"
              :applied-patches="activeAcgView.appliedPatches"
              :branch-decisions="activeAcgView.branchDecisions"
              :step-states="activeAcgView.stepStates"
            />
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

          <div v-show="!agentPanelCollapsed" class="agent-panel-content">
          <LawyerSkillPanel
            v-if="isLawyerMode"
            :skills-used="latestLawyerMeta.skillsUsed"
            :trace="latestLawyerMeta.trace"
            :federated="latestLawyerMeta.federated"
            :risk-level="latestLawyerMeta.riskLevel"
            :result-count="availableLawyerResultPanels.length"
            @open-federated-console="openFederatedConsole"
            @optimize-federated="handleFederatedOptimize"
          >
          <template #results>
            <div v-if="!availableLawyerResultPanels.length" class="results-empty">
              <el-icon class="empty-icon"><Notebook /></el-icon>
              <span>暂无技能调用结果</span>
              <span class="results-empty-hint">发送消息后，这里会整理 Agent 的结构化结果</span>
            </div>
            <el-collapse v-else v-model="activeLawyerResultPanels">
              <el-collapse-item
                v-if="availableLawyerResultPanels.includes('evidence')"
                title="证据分析结果"
                name="evidence"
              >
                <EvidenceAnalysisCard :data="latestLawyerSkillResults.evidenceAnalysis" />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableLawyerResultPanels.includes('limitation')"
                title="诉讼时效结果"
                name="limitation"
              >
                <LimitationTimeline :data="latestLawyerSkillResults.limitationCalc" />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableLawyerResultPanels.includes('jurisdiction')"
                title="管辖法院建议"
                name="jurisdiction"
              >
                <JurisdictionCard :data="latestLawyerSkillResults.jurisdiction" />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableLawyerResultPanels.includes('hearing')"
                title="庭审提纲"
                name="hearing"
              >
                <HearingOutlineViewer :data="latestLawyerSkillResults.hearingOutline" />
              </el-collapse-item>
            </el-collapse>
          </template>
        </LawyerSkillPanel>

        <TeacherSkillPanel
          v-else-if="isTeacherMode"
          :skills-used="latestTeacherMeta.skillsUsed"
          :trace="latestTeacherMeta.trace"
          :federated="latestTeacherMeta.federated"
          :result-count="availableTeacherResultPanels.length"
          @open-federated-console="openFederatedConsole"
          @optimize-federated="handleFederatedOptimize"
        >
          <template #results>
            <div v-if="!availableTeacherResultPanels.length" class="results-empty">
              <el-icon class="empty-icon"><Reading /></el-icon>
              <span>暂无技能调用结果</span>
              <span class="results-empty-hint">发送消息后，这里会整理 Agent 的结构化结果</span>
            </div>
            <el-collapse v-else v-model="activeTeacherResultPanels">
              <el-collapse-item
                v-if="availableTeacherResultPanels.includes('diagnosis')"
                title="学情诊断"
                name="diagnosis"
              >
                <DiagnosisRadar :data="latestTeacherSkillResults.studentDiagnosis" />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableTeacherResultPanels.includes('lessonPlan')"
                title="个性化教案"
                name="lessonPlan"
              >
                <LessonPlanViewer :data="latestTeacherSkillResults.lessonPlan" />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableTeacherResultPanels.includes('grading')"
                title="作业批改"
                name="grading"
              >
                <GradingResultCard :data="latestTeacherSkillResults.homeworkGrading" />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableTeacherResultPanels.includes('questionPush')"
                title="错题归因与推题"
                name="questionPush"
              >
                <QuestionPushList :data="latestTeacherSkillResults.errorQuestionPush" />
              </el-collapse-item>
            </el-collapse>
          </template>
        </TeacherSkillPanel>

        <ProgrammerSkillPanel
          v-else-if="isProgrammerMode"
          :skills-used="latestProgrammerMeta.skillsUsed"
          :trace="latestProgrammerMeta.trace"
          :federated="latestProgrammerMeta.federated"
          :result-count="availableProgrammerResultPanels.length"
          @open-federated-console="openFederatedConsole"
          @optimize-federated="handleFederatedOptimize"
        >
          <template #results>
            <div v-if="!availableProgrammerResultPanels.length" class="results-empty">
              <el-icon class="empty-icon"><Cpu /></el-icon>
              <span>暂无技能调用结果</span>
              <span class="results-empty-hint">发送消息后，这里会整理 Agent 的结构化结果</span>
            </div>
            <el-collapse v-else v-model="activeProgrammerResultPanels">
              <el-collapse-item
                v-if="availableProgrammerResultPanels.includes('requirement')"
                title="需求分析"
                name="requirement"
              >
                <div class="programmer-block">
                  <div class="programmer-grid two-cols">
                    <div class="programmer-card">
                      <div class="card-title">功能需求</div>
                      <ul>
                        <li v-for="(item, idx) in (latestProgrammerSkillResults.requirementAnalysis?.functional_requirements || [])" :key="`fr-${idx}`">
                          {{ item }}
                        </li>
                      </ul>
                    </div>
                    <div class="programmer-card">
                      <div class="card-title">边界条件</div>
                      <ul>
                        <li v-for="(item, idx) in (latestProgrammerSkillResults.requirementAnalysis?.boundary_conditions || [])" :key="`bc-${idx}`">
                          {{ item }}
                        </li>
                      </ul>
                    </div>
                  </div>
                  <div class="programmer-grid two-cols">
                    <div class="programmer-card">
                      <div class="card-title">输入</div>
                      <ul>
                        <li v-for="(item, idx) in (latestProgrammerSkillResults.requirementAnalysis?.inputs || [])" :key="`in-${idx}`">{{ item }}</li>
                      </ul>
                    </div>
                    <div class="programmer-card">
                      <div class="card-title">输出</div>
                      <ul>
                        <li v-for="(item, idx) in (latestProgrammerSkillResults.requirementAnalysis?.outputs || [])" :key="`out-${idx}`">{{ item }}</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </el-collapse-item>

              <el-collapse-item
                v-if="availableProgrammerResultPanels.includes('search')"
                title="代码库语义检索"
                name="search"
              >
                <div class="programmer-block">
                  <div class="programmer-meta">
                    命中 {{ latestProgrammerSkillResults.searchHits.length }} 条 · 向量检索
                    {{ latestProgrammerSkillResults.codebaseSemanticSearch?.index_status?.vector_enabled ? '已启用' : '未启用（关键词降级）' }}
                  </div>
                  <div class="programmer-search-list">
                    <div
                      v-for="(hit, idx) in latestProgrammerSkillResults.searchHits"
                      :key="`hit-${idx}`"
                      class="search-item"
                    >
                      <div class="search-head">
                        <span class="path">{{ hit.file_path || 'unknown file' }}</span>
                        <span class="score">score: {{ Number(hit.score || 0).toFixed(3) }}</span>
                      </div>
                      <pre>{{ hit.content }}</pre>
                    </div>
                  </div>
                </div>
              </el-collapse-item>

              <el-collapse-item
                v-if="availableProgrammerResultPanels.includes('code')"
                title="代码生成"
                name="code"
              >
                <div class="programmer-block">
                  <div class="programmer-meta">{{ latestProgrammerSkillResults.codeGeneration?.explanation || '暂无说明' }}</div>
                  <pre class="code-block">{{ latestProgrammerSkillResults.generatedCode || '// 暂无代码输出' }}</pre>
                  <div v-if="latestProgrammerSkillResults.suggestedTests.length" class="programmer-card">
                    <div class="card-title">建议测试点</div>
                    <ul>
                      <li v-for="(item, idx) in latestProgrammerSkillResults.suggestedTests" :key="`test-${idx}`">{{ item }}</li>
                    </ul>
                  </div>
                </div>
              </el-collapse-item>

              <el-collapse-item
                v-if="availableProgrammerResultPanels.includes('diagram')"
                title="Mermaid 图表"
                name="diagram"
              >
                <DiagramViewer :data="latestProgrammerSkillResults.diagramData" />
              </el-collapse-item>
            </el-collapse>
          </template>
        </ProgrammerSkillPanel>

        <WriterSkillPanel
          v-else-if="isWriterMode"
          :skills-used="latestWriterMeta.skillsUsed"
          :trace="latestWriterMeta.trace"
          :federated="latestWriterMeta.federated"
          :result-count="availableWriterResultPanels.length"
          @open-federated-console="openFederatedConsole"
          @optimize-federated="handleFederatedOptimize"
        >
          <template #results>
            <div v-if="!availableWriterResultPanels.length" class="results-empty">
              <el-icon class="empty-icon"><EditPen /></el-icon>
              <span>暂无技能调用结果</span>
              <span class="results-empty-hint">发送消息后，这里会整理 Agent 的结构化结果</span>
            </div>
            <el-collapse v-else v-model="activeWriterResultPanels">
              <el-collapse-item
                v-if="availableWriterResultPanels.includes('inspiration')"
                title="创意树思维导图"
                name="inspiration"
              >
                <MindMapViewer
                  title="创意树"
                  :creative-tree="latestWriterSkillResults.creativeTree"
                />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableWriterResultPanels.includes('outline')"
                title="章节大纲思维导图"
                name="outline"
              >
                <MindMapViewer
                  title="章节大纲"
                  :outline-markdown="latestWriterSkillResults.outlineMarkdown"
                />
              </el-collapse-item>

              <el-collapse-item
                v-if="availableWriterResultPanels.includes('content')"
                title="正文撰写"
                name="content"
              >
                <div class="writer-content-preview">
                  {{ latestWriterSkillResults.content || '暂无正文内容' }}
                </div>
              </el-collapse-item>

              <el-collapse-item
                v-if="availableWriterResultPanels.includes('relation')"
                title="人物关系图"
                name="relation"
              >
                <RelationGraph :data="latestWriterSkillResults.characterRelationMap" />
              </el-collapse-item>
            </el-collapse>
          </template>
        </WriterSkillPanel>
          </div>
      </aside>
      </Transition>
    </div>

    <RoleTemplateSwitchDialog
      :open="roleTemplateDialogOpen"
      :current-role-name="currentRole?.name"
      :current-template-key="selectedChatTemplateKey"
      @close="roleTemplateDialogOpen = false"
      @confirm="applyRoleTemplateSelection"
    />

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
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDownBold,
  ArrowUp,
  ChatDotRound,
  Check,
  Close,
  Cpu,
  DArrowLeft,
  DArrowRight,
  EditPen,
  Folder,
  Loading,
  Microphone,
  Notebook,
  Plus,
  Reading,
  ScaleToOriginal,
  Share,
  School,
  UploadFilled
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MessageBubble from '@/components/MessageBubble.vue'
import ModelRuntimeControls from '@/components/ModelRuntimeControls.vue'
import FileManager from '@/components/FileManager.vue'
import LawyerSkillPanel from '@/components/agent/LawyerSkillPanel.vue'
import TeacherSkillPanel from '@/components/agent/TeacherSkillPanel.vue'
import ProgrammerSkillPanel from '@/components/agent/ProgrammerSkillPanel.vue'
import WriterSkillPanel from '@/components/agent/WriterSkillPanel.vue'
import EvidenceAnalysisCard from '@/components/agent/EvidenceAnalysisCard.vue'
import LimitationTimeline from '@/components/agent/LimitationTimeline.vue'
import JurisdictionCard from '@/components/agent/JurisdictionCard.vue'
import HearingOutlineViewer from '@/components/agent/HearingOutlineViewer.vue'
import DiagnosisRadar from '@/components/agent/DiagnosisRadar.vue'
import LessonPlanViewer from '@/components/agent/LessonPlanViewer.vue'
import GradingResultCard from '@/components/agent/GradingResultCard.vue'
import QuestionPushList from '@/components/agent/QuestionPushList.vue'
import DiagramViewer from '@/components/agent/DiagramViewer.vue'
import MindMapViewer from '@/components/agent/MindMapViewer.vue'
import RelationGraph from '@/components/agent/RelationGraph.vue'
import RecommendationPanel from '@/components/RecommendationPanel.vue'
import RoleTemplateSwitchDialog from '@/components/RoleTemplateSwitchDialog.vue'
import AcgTopologyGraph from '@/components/agentos/AcgTopologyGraph.vue'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import DynamicRunSummaryCard from '@/components/agentos/DynamicRunSummaryCard.vue'
import RuntimeChangeTimeline from '@/components/agentos/RuntimeChangeTimeline.vue'
import WorkflowReviewPanel from '@/components/agentos/WorkflowReviewPanel.vue'
import { agentosApi, type AcgBlueprint, type AcgView, type WorkflowRun } from '@/services/api/agentos'
import type { WorkflowProgress } from '@/services/api/workflow'
import { agentTeacherApi } from '@/services/api/agentTeacher'
import { federatedModelApi } from '@/services/api/federatedModel'
import { fileApi } from '@/services/api/file'
import { recommendationApi, type RecommendationItem } from '@/services/api/recommendation'
import { useChatStore, type ChatWorkflowBinding } from '@/stores/chat'
import { useRoleStore } from '@/stores/role'
import { useDebounce } from '@/composables/useDebounce'
import { useWorkflowProgress } from '@/composables/useWorkflowProgress'
import { runtimeProjectionChanged } from '@/utils/runtimePresentation'
import { loadModelSettings } from '@/config/modelSettings'
import { roleTemplateGroups, type RoleId } from '@/config/agentWorkbench'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const roleStore = useRoleStore()
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
const WORKFLOW_SUBMISSION_KEY_PREFIX = 'chat.workflow_submission.'
const draftConversationId = ref(
  localStorage.getItem(DRAFT_CONVERSATION_KEY) || `draft:${createClientRequestId()}`
)
localStorage.setItem(DRAFT_CONVERSATION_KEY, draftConversationId.value)
const workspaceMode = ref<WorkspaceMode>(
  route.query.workspace === 'agent' || localStorage.getItem(WORKSPACE_MODE_KEY) === 'agent'
    ? 'agent'
    : 'chat'
)

const selectedRoleId = ref<string | null>(null)
const inputText = ref('')
const loading = ref(false)
const showRoleDrawer = ref(false)
const roleTemplateDialogOpen = ref(false)
const CHAT_TEMPLATE_KEY = 'chat.active_template_key'
const selectedChatTemplateKey = ref(localStorage.getItem(CHAT_TEMPLATE_KEY) || '')
const showFileManager = ref(false)
const isRecording = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const composerRef = ref<HTMLElement | null>(null)
const chatPanelRef = ref<HTMLElement | null>(null)
const teacherUploadInputRef = ref<HTMLInputElement | null>(null)
const showAssistTools = ref(false)
const isNearBottom = ref(true)
const pendingMessageCount = ref(0)
const federatedOptimizing = ref(false)
const activeLawyerResultPanels = ref<string[]>([])
const activeTeacherResultPanels = ref<string[]>([])
const activeProgrammerResultPanels = ref<string[]>([])
const activeWriterResultPanels = ref<string[]>([])
const chatRecommendations = ref<RecommendationItem[]>([])
const recommendationLoading = ref(false)
const recommendationCollapsed = ref(true)
const ASSIST_TOOL_VISIBLE_KEY = 'chat.composer_templates_visible'
const RECOMMENDATION_COLLAPSED_KEY = 'chat.recommendation_collapsed'
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
const workflowStartError = ref<string | null>(null)
const currentConversationId = computed(() => {
  const routeContextId = typeof route.query.contextId === 'string' ? route.query.contextId.trim() : ''
  return routeContextId || chatStore.contextId || draftConversationId.value
})
const isStreamingChat = computed(() => chatStore.isStreaming)
const isLoadingConversation = computed(() => chatStore.isLoadingConversation)
const workflowProgressState = useWorkflowProgress({
  intervalMs: 2000,
  onProgressChanged: handleWorkflowProgressChanged,
  onTerminal: handleWorkflowTerminal
})
const hasActiveWorkflow = computed(() => Boolean(activeWorkflowRunId.value))
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
let conversationGeneration = 0
const terminalResultLoaded = new Set<string>()
const workflowResultCache = new Map<string, { run: WorkflowRun; view: AcgView }>()
let composerResizeObserver: ResizeObserver | undefined

const workflowRunBlueprint = computed<AcgBlueprint | null>(() => {
  const run = activeWorkflowRun.value
  if (!run?.steps?.length) return null

  const agentIds = new Map<string, string>()
  run.steps.forEach(step => {
    const name = step.agentName || 'Agent'
    if (!agentIds.has(name)) agentIds.set(name, `agent:${name}`)
  })

  const nodes: AcgBlueprint['nodes'] = [
    { nodeId: 'workflow:start', nodeType: 'control', name: 'START', controlType: 'start' },
    ...run.steps.map(step => ({
      nodeId: step.stepId,
      nodeType: 'step' as const,
      name: step.name || step.stepId,
      agentName: step.agentName,
      capability: step.capability,
      metadata: { status: step.status }
    })),
    ...Array.from(agentIds.entries()).map(([name, nodeId]) => ({
      nodeId,
      nodeType: 'agent' as const,
      name
    }))
  ]

  const edges: AcgBlueprint['edges'] = []
  run.steps.forEach((step, index) => {
    edges.push({
      edgeId: `flow:${index}`,
      sourceId: index === 0 ? 'workflow:start' : run.steps[index - 1].stepId,
      targetId: step.stepId,
      edgeType: 'dependency'
    })
    const agentId = agentIds.get(step.agentName || 'Agent')
    if (agentId) {
      edges.push({
        edgeId: `exec:${step.stepId}`,
        sourceId: agentId,
        targetId: step.stepId,
        edgeType: 'execution'
      })
    }
  })

  return {
    graphId: `workflow:${run.runId}`,
    taskId: run.taskId,
    objective: run.workflowId,
    nodes,
    edges,
    metadata: { source: 'workflow-run' }
  }
})

const displayAcgBlueprint = computed(() => activeAcgView.value?.acgBlueprint || workflowRunBlueprint.value)
const displayCompletedStepIds = computed(() => {
  if (activeAcgView.value?.acgBlueprint) return activeAcgView.value.completedStepIds
  return activeWorkflowRun.value?.steps
    .filter(step => step.status === 'completed')
    .map(step => step.stepId) || []
})
const contextNodes = computed(() => displayAcgBlueprint.value?.nodes || [])
const contextEdges = computed(() => displayAcgBlueprint.value?.edges || [])
const contextStepNodes = computed(() => contextNodes.value.filter(node => node.nodeType === 'step'))
const contextObjective = computed(() => {
  return displayAcgBlueprint.value?.objective || activeWorkflowRun.value?.workflowId || '等待工作流'
})
const activeWorkflowStatus = computed(() => (
  workflowProgressState.progress.value?.status
  || activeWorkflowRun.value?.status
  || activeAcgView.value?.status
  || [...chatStore.messages].reverse().find(message => message.workflowRunId === activeWorkflowRunId.value)?.workflowStatus
  || 'pending'
))
const activeWorkflowStatusLabel = computed(() => ({
  pending: '等待规划',
  planning: '规划中',
  running: '运行中',
  waiting_review: '等待人工审核',
  retrying: '正在重试',
  failed: '运行失败',
  completed: '运行完成',
  cancelled: '已取消'
}[activeWorkflowStatus.value] || activeWorkflowStatus.value))
const contextTabs = computed(() => [
  { key: 'lineage' as const, label: '数据血缘', count: contextEdges.value.length },
  { key: 'nodes' as const, label: '节点', count: contextNodes.value.length },
  { key: 'steps' as const, label: '任务步骤', count: contextStepNodes.value.length }
])
const contextNodeLabel = (nodeId: string) => {
  const node = contextNodes.value.find(item => item.nodeId === nodeId)
  return node?.name || node?.agentName || nodeId
}
const contextEdgeLabel = (edgeType: string) => ({
  dependency: '依赖',
  communication: '通信',
  control_flow: '控制流',
  execution: '执行',
  write: '写入',
  read: '读取',
  support: '支撑'
}[edgeType] || edgeType)
const contextNodeTypeLabel = (nodeType: string) => ({
  step: '步骤',
  agent: '智能体',
  skill: '技能',
  memory: '记忆',
  evidence: '证据',
  control: '控制'
}[nodeType] || nodeType)
const debouncedInputText = useDebounce(inputText, 350)

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

const finishContextPanelClose = async () => {
  const previousComposerRect = composerRef.value?.getBoundingClientRect()
  contextPanelClosing.value = false
  await nextTick()

  const composer = composerRef.value
  if (!composer || !previousComposerRect || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  const nextComposerRect = composer.getBoundingClientRect()
  const deltaY = previousComposerRect.top - nextComposerRect.top
  if (Math.abs(deltaY) < 1) return

  composer.animate(
    [
      { translate: `0 ${deltaY}px`, opacity: 0.82 },
      { translate: '0 0', opacity: 1 }
    ],
    { duration: 320, easing: 'cubic-bezier(0.22, 1, 0.36, 1)' }
  )
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

const invalidateWorkflowResultRequest = () => {
  workflowResultGeneration += 1
  workflowResultController?.abort()
  workflowResultController = null
  isLoadingWorkflowResult.value = false
}

const loadActiveAcgView = async (runId = activeWorkflowRunId.value, force = false) => {
  if (!runId || runId !== activeWorkflowRunId.value) return false
  if (isLoadingWorkflowResult.value && !force) return false
  const requestGeneration = ++workflowResultGeneration
  workflowResultController?.abort()
  workflowResultController = new AbortController()
  const signal = workflowResultController.signal
  isLoadingWorkflowResult.value = true
  try {
    const [run, view] = await Promise.all([
      agentosApi.getWorkflowRun(runId, { signal }),
      agentosApi.getAcgView(runId, { signal })
    ])
    if (requestGeneration !== workflowResultGeneration || runId !== activeWorkflowRunId.value) return false
    activeWorkflowRun.value = run
    activeAcgView.value = view
    workflowResultCache.set(runId, { run, view })
    syncWorkflowMessageStatus(run.runId, run.status)
    return true
  } catch (error: unknown) {
    if (!axios.isCancel(error) && force && requestGeneration === workflowResultGeneration) {
      ElMessage.warning('ACG 最终结果暂时未能加载')
    }
    return false
  } finally {
    if (requestGeneration === workflowResultGeneration) {
      workflowResultController = null
      isLoadingWorkflowResult.value = false
    }
  }
}

function handleWorkflowProgressChanged(current: WorkflowProgress, previous: WorkflowProgress | null) {
  if (current.runId !== activeWorkflowRunId.value) return
  const conversationId = currentConversationId.value
  chatStore.updateWorkflowBindingStatus(conversationId, current.runId, current.status)
  if (activeWorkflowBinding.value?.runId === current.runId) {
    activeWorkflowBinding.value = { ...activeWorkflowBinding.value, status: current.status }
  }
  syncWorkflowMessageStatus(current.runId, current.status)

  if (runtimeProjectionChanged(current, previous) && !['completed', 'failed', 'cancelled'].includes(current.status)) {
    void loadActiveAcgView(current.runId, true)
    return
  }

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
  if (loaded) terminalResultLoaded.add(progress.runId)
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
  void router.push({ path: '/agentos-console', query: { runId: activeWorkflowRunId.value } })
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

const roles = computed(() => roleStore.roles)
const currentRole = computed(() => roleStore.currentRole)

const isLawyerMode = computed(() => {
  const name = (currentRole.value?.name || '').toLowerCase()
  return name.includes('律师') || name.includes('lawyer') || name.includes('法律')
})

const isTeacherMode = computed(() => {
  const name = (currentRole.value?.name || '').toLowerCase()
  return name.includes('教师') || name.includes('teacher') || name.includes('教学')
})

const isProgrammerMode = computed(() => {
  const name = (currentRole.value?.name || '').toLowerCase()
  return name.includes('程序') || name.includes('programmer') || name.includes('开发')
})

const isWriterMode = computed(() => {
  const name = (currentRole.value?.name || '').toLowerCase()
  return name.includes('作家') || name.includes('writer') || name.includes('写作')
})

const isAgentMode = computed(() => workspaceMode.value === 'agent')

const chatMainClass = computed(() => {
  if (isLawyerMode.value) return 'lawyer'
  if (isTeacherMode.value) return 'teacher'
  if (isProgrammerMode.value) return 'programmer'
  if (isWriterMode.value) return 'writer'
  return ''
})

const agentIcon = computed(() => {
  if (isLawyerMode.value) return ScaleToOriginal
  if (isTeacherMode.value) return School
  if (isProgrammerMode.value) return Cpu
  if (isWriterMode.value) return EditPen
  return ChatDotRound
})

const agentTitle = computed(() => {
  if (isLawyerMode.value) return '律师 Agent 对话'
  if (isTeacherMode.value) return '教师 Agent 对话'
  if (isProgrammerMode.value) return '程序员 Agent 对话'
  if (isWriterMode.value) return '作家 Agent 对话'
  return '开始一次新对话'
})

const agentSubtitle = computed(() => {
  if (isLawyerMode.value) return '专业法律咨询，智能证据分析与风险评估'
  if (isTeacherMode.value) return '智能学情诊断、个性化教案与作业批改'
  if (isProgrammerMode.value) return '需求分析、代码库语义检索、代码生成与 Mermaid 图表'
  if (isWriterMode.value) return '灵感拓展、大纲生成、正文写作与人物关系图'
  return '你可以直接输入问题，或使用下方快捷模板。'
})

const latestLawyerMessage = computed(() => {
  return [...chatStore.messages]
    .reverse()
    .find(msg => msg.role === 'assistant' && msg.agentMode === 'lawyer')
})

const latestTeacherMessage = computed(() => {
  return [...chatStore.messages]
    .reverse()
    .find(msg => msg.role === 'assistant' && msg.agentMode === 'teacher')
})

const latestProgrammerMessage = computed(() => {
  return [...chatStore.messages]
    .reverse()
    .find(msg => msg.role === 'assistant' && msg.agentMode === 'programmer')
})

const latestWriterMessage = computed(() => {
  return [...chatStore.messages]
    .reverse()
    .find(msg => msg.role === 'assistant' && msg.agentMode === 'writer')
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

const latestTeacherMeta = computed(() => {
  const lastAssistant = latestTeacherMessage.value
  return {
    skillsUsed: lastAssistant?.skillsUsed || [],
    trace: lastAssistant?.trace || [],
    federated: lastAssistant?.federated || {}
  }
})

const latestProgrammerMeta = computed(() => {
  const lastAssistant = latestProgrammerMessage.value
  return {
    skillsUsed: lastAssistant?.skillsUsed || [],
    trace: lastAssistant?.trace || [],
    federated: lastAssistant?.federated || {}
  }
})

const latestWriterMeta = computed(() => {
  const lastAssistant = latestWriterMessage.value
  return {
    skillsUsed: lastAssistant?.skillsUsed || [],
    trace: lastAssistant?.trace || [],
    federated: lastAssistant?.federated || {}
  }
})

const latestLawyerSkillResults = computed(() => {
  const lastAssistant = latestLawyerMessage.value
  return {
    evidenceAnalysis: lastAssistant?.evidenceAnalysis,
    limitationCalc: lastAssistant?.limitationCalc,
    jurisdiction: lastAssistant?.jurisdiction,
    hearingOutline: lastAssistant?.hearingOutline
  }
})

const latestTeacherSkillResults = computed(() => {
  const lastAssistant = latestTeacherMessage.value
  return {
    studentDiagnosis: lastAssistant?.studentDiagnosis,
    lessonPlan: lastAssistant?.lessonPlan,
    homeworkGrading: lastAssistant?.homeworkGrading,
    errorQuestionPush: lastAssistant?.errorQuestionPush
  }
})

const latestProgrammerSkillResults = computed(() => {
  const lastAssistant = latestProgrammerMessage.value
  const searchPayload = lastAssistant?.codebaseSemanticSearch
  const codeGenerationPayload = lastAssistant?.codeGeneration
  const diagramPayload = lastAssistant?.diagramGeneration
  const generationMermaidCode = codeGenerationPayload?.mermaid_code
  const diagramMermaidCode = diagramPayload?.mermaid_code
  const searchHits = Array.isArray(searchPayload?.hits) ? searchPayload?.hits : []
  const suggestedTests = Array.isArray(codeGenerationPayload?.suggested_tests) ? codeGenerationPayload?.suggested_tests : []

  const diagramData = diagramPayload?.mermaid_code
    ? diagramPayload
    : (generationMermaidCode
      ? {
        title: 'Generated Diagram',
        diagram_type: 'flowchart',
        mermaid_code: generationMermaidCode
      }
      : undefined)

  return {
    requirementAnalysis: lastAssistant?.requirementAnalysis,
    codebaseSemanticSearch: searchPayload,
    codeGeneration: codeGenerationPayload,
    diagramGeneration: diagramPayload,
    generatedCode: codeGenerationPayload?.code || '',
    suggestedTests,
    searchHits,
    diagramData,
    diagramCode: diagramMermaidCode || generationMermaidCode || ''
  }
})

const latestWriterSkillResults = computed(() => {
  const lastAssistant = latestWriterMessage.value
  return {
    creativeTree: lastAssistant?.inspirationExpand?.creative_tree || lastAssistant?.inspirationExpand?.creativeTree,
    outlineMarkdown: lastAssistant?.outlineGenerate?.outline_markdown || lastAssistant?.outlineGenerate?.outlineMarkdown,
    content: lastAssistant?.contentWrite?.content,
    characterRelationMap: lastAssistant?.characterRelationMap
  }
})

const availableLawyerResultPanels = computed(() => {
  const skillSet = new Set(latestLawyerMeta.value.skillsUsed || [])
  const panels: string[] = []
  if (latestLawyerSkillResults.value.evidenceAnalysis || skillSet.has('evidence_analysis')) panels.push('evidence')
  if (latestLawyerSkillResults.value.limitationCalc || skillSet.has('limitation_calculation')) panels.push('limitation')
  if (latestLawyerSkillResults.value.jurisdiction || skillSet.has('jurisdiction_determination')) panels.push('jurisdiction')
  if (latestLawyerSkillResults.value.hearingOutline || skillSet.has('hearing_outline_generation')) panels.push('hearing')
  return panels
})

const availableTeacherResultPanels = computed(() => {
  const skillSet = new Set(latestTeacherMeta.value.skillsUsed || [])
  const panels: string[] = []
  if (latestTeacherSkillResults.value.studentDiagnosis || skillSet.has('student_diagnosis')) panels.push('diagnosis')
  if (latestTeacherSkillResults.value.lessonPlan || skillSet.has('lesson_plan_generation') || skillSet.has('lesson_plan')) panels.push('lessonPlan')
  if (latestTeacherSkillResults.value.homeworkGrading || skillSet.has('homework_grading') || skillSet.has('grading')) panels.push('grading')
  if (latestTeacherSkillResults.value.errorQuestionPush || skillSet.has('error_analysis_question_push') || skillSet.has('error_attribution')) panels.push('questionPush')
  return panels
})

const availableProgrammerResultPanels = computed(() => {
  const skillSet = new Set(latestProgrammerMeta.value.skillsUsed || [])
  const panels: string[] = []
  if (latestProgrammerSkillResults.value.requirementAnalysis || skillSet.has('requirement_analysis')) panels.push('requirement')
  if (latestProgrammerSkillResults.value.searchHits.length || skillSet.has('codebase_semantic_search')) panels.push('search')
  if (latestProgrammerSkillResults.value.generatedCode || skillSet.has('code_generation')) panels.push('code')
  if (latestProgrammerSkillResults.value.diagramCode || skillSet.has('diagram_generation')) panels.push('diagram')
  return panels
})

const availableWriterResultPanels = computed(() => {
  const skillSet = new Set(latestWriterMeta.value.skillsUsed || [])
  const panels: string[] = []
  if (latestWriterSkillResults.value.creativeTree || skillSet.has('inspiration_expand')) panels.push('inspiration')
  if (latestWriterSkillResults.value.outlineMarkdown || skillSet.has('outline_generate')) panels.push('outline')
  if (latestWriterSkillResults.value.content || skillSet.has('content_write')) panels.push('content')
  if (latestWriterSkillResults.value.characterRelationMap || skillSet.has('character_relation_map')) panels.push('relation')
  return panels
})

// 右侧工作台：仅当当前模式有技能调用结果时才显示
const hasAgentResults = computed(() => {
  if (isLawyerMode.value) return availableLawyerResultPanels.value.length > 0
  if (isTeacherMode.value) return availableTeacherResultPanels.value.length > 0
  if (isProgrammerMode.value) return availableProgrammerResultPanels.value.length > 0
  if (isWriterMode.value) return availableWriterResultPanels.value.length > 0
  return false
})

const hasAgentActivity = computed(() => {
  if (hasAgentResults.value) return true
  if (isLawyerMode.value) return latestLawyerMeta.value.skillsUsed.length > 0 || latestLawyerMeta.value.trace.length > 0
  if (isTeacherMode.value) return latestTeacherMeta.value.skillsUsed.length > 0 || latestTeacherMeta.value.trace.length > 0
  if (isProgrammerMode.value) return latestProgrammerMeta.value.skillsUsed.length > 0 || latestProgrammerMeta.value.trace.length > 0
  if (isWriterMode.value) return latestWriterMeta.value.skillsUsed.length > 0 || latestWriterMeta.value.trace.length > 0
  return false
})

const showScrollToBottom = computed(() => !isNearBottom.value && chatStore.messages.length > 0)
const isSendDisabled = computed(() => loading.value || (!inputText.value.trim() && !isRecording.value))
const isWorkflowTerminal = computed(() => {
  const phase = workflowProgressState.progress.value?.phase
  const status = workflowProgressState.progress.value?.status || activeWorkflowBinding.value?.status
  const terminal = ['completed', 'failed', 'cancelled']
  return terminal.includes(phase || '') || terminal.includes(status || '')
})
const isWorkflowUnavailable = computed(() =>
  workflowProgressState.syncError.value === '该运行记录不存在或当前账户无权访问'
)
const isWorkflowUpgradeDisabled = computed(() =>
  isSubmittingWorkflow.value
  || (Boolean(activeWorkflowRunId.value) && !isWorkflowTerminal.value && !isWorkflowUnavailable.value)
  || !inputText.value.trim()
)

const recommendationToggleText = computed(() => {
  if (recommendationLoading.value) return '正在生成推荐...'
  const count = chatRecommendations.value.length
  if (count > 0) {
    return recommendationCollapsed.value ? `${count} 条建议，点击展开` : `${count} 条建议已展开`
  }
  return recommendationCollapsed.value ? '暂无推荐，点击展开或刷新' : '暂无推荐内容'
})

const currentTemplates = computed(() => {
  const roleName = currentRole.value?.name || ''
  const lower = roleName.toLowerCase()

  if (roleName.includes('律师') || lower.includes('lawyer')) {
    return ['合同纠纷咨询', '劳动仲裁流程', '法律风险评估', '文书草稿生成']
  }
  if (roleName.includes('教师') || lower.includes('teacher')) {
    return ['制定学习计划', '错题归因推题', '生成课堂互动脚本', '学情报告总结']
  }
  if (roleName.includes('程序') || lower.includes('developer') || lower.includes('programmer')) {
    return ['帮我做需求技术规格分析', '检索代码库中登录相关函数', '根据规格生成后端接口代码', '生成用户登录流程 Mermaid 图']
  }
  if (roleName.includes('作家') || lower.includes('writer')) {
    return ['灵感拓展并生成创意树', '生成章节大纲思维导图', '按鲁迅体写第一章', '分析角色并生成人物关系图']
  }
  return ['日常问答', '帮我做个计划', '总结这段内容', '给我几个建议']
})

const getLawyerRole = () => {
  return roles.value.find(role => {
    const roleName = (role.name || '').toLowerCase()
    return roleName.includes('律师') || roleName.includes('法律') || roleName.includes('lawyer')
  })
}

const getTeacherRole = () => {
  return roles.value.find(role => {
    const roleName = (role.name || '').toLowerCase()
    return roleName.includes('教师') || roleName.includes('教学') || roleName.includes('teacher')
  })
}

const getProgrammerRole = () => {
  return roles.value.find(role => {
    const roleName = (role.name || '').toLowerCase()
    return roleName.includes('程序') || roleName.includes('开发') || roleName.includes('programmer')
  })
}

const getWriterRole = () => {
  return roles.value.find(role => {
    const roleName = (role.name || '').toLowerCase()
    return roleName.includes('作家') || roleName.includes('写作') || roleName.includes('writer')
  })
}

const switchRoleWithoutReset = async (role: any) => {
  selectedRoleId.value = role.id
  await roleStore.setCurrentRole(role)
  chatStore.setRole(role.id)
}

const activateLawyerAgent = async () => {
  if (isLawyerMode.value) {
    ElMessage.info('当前已在律师模式')
    return
  }

  const lawyerRole = getLawyerRole()
  if (!lawyerRole) {
    ElMessage.warning('未找到律师角色，请先在角色管理中启用律师角色')
    showRoleDrawer.value = true
    return
  }
  await switchRoleWithoutReset(lawyerRole)
  ElMessage.success('已切换到律师 Agent')
}

const activateTeacherAgent = async () => {
  if (isTeacherMode.value) {
    ElMessage.info('当前已在教师模式')
    return
  }

  const teacherRole = getTeacherRole()
  if (!teacherRole) {
    ElMessage.warning('未找到教师角色，请先在角色管理中启用教师角色')
    showRoleDrawer.value = true
    return
  }
  await switchRoleWithoutReset(teacherRole)
  ElMessage.success('已切换到教师 Agent')
}

const activateProgrammerAgent = async () => {
  if (isProgrammerMode.value) {
    ElMessage.info('当前已在程序员模式')
    return
  }

  const programmerRole = getProgrammerRole()
  if (!programmerRole) {
    ElMessage.warning('未找到程序员角色，请先在角色管理中启用程序员角色')
    showRoleDrawer.value = true
    return
  }
  await switchRoleWithoutReset(programmerRole)
  ElMessage.success('已切换到程序员 Agent')
}

const activateWriterAgent = async () => {
  if (isWriterMode.value) {
    ElMessage.info('当前已在作家模式')
    return
  }

  const writerRole = getWriterRole()
  if (!writerRole) {
    ElMessage.warning('未找到作家角色，请先在角色管理中启用作家角色')
    showRoleDrawer.value = true
    return
  }
  await switchRoleWithoutReset(writerRole)
  ElMessage.success('已切换到作家 Agent')
}

const toggleLawyerMode = async () => {
  if (isLawyerMode.value) {
    ElMessage.info('当前已在律师模式')
    return
  }
  await activateLawyerAgent()
}

const toggleTeacherMode = async () => {
  if (isTeacherMode.value) {
    ElMessage.info('当前已在教师模式')
    return
  }
  await activateTeacherAgent()
}

const toggleProgrammerMode = async () => {
  if (isProgrammerMode.value) {
    ElMessage.info('当前已在程序员模式')
    return
  }
  await activateProgrammerAgent()
}

const toggleWriterMode = async () => {
  if (isWriterMode.value) {
    ElMessage.info('当前已在作家模式')
    return
  }
  await activateWriterAgent()
}

const openFederatedConsole = () => {
  router.push('/federated-learning')
}

const handleFederatedOptimize = async () => {
  if (federatedOptimizing.value) return
  federatedOptimizing.value = true
  try {
    const result = await federatedModelApi.optimizeModel('advanced', 'federated', 'quality', 1)
    if (result?.success) {
      ElMessage.success('联邦优化已触发')
      return
    }
    ElMessage.warning('联邦优化请求未成功')
  } catch (error: any) {
    ElMessage.error(error?.message || '联邦优化触发失败')
  } finally {
    federatedOptimizing.value = false
  }
}

const toggleAssistTools = () => {
  showAssistTools.value = !showAssistTools.value
}

const toggleRecommendationPanel = () => {
  recommendationCollapsed.value = !recommendationCollapsed.value
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

const currentRecommendationRoleName = computed(() => {
  if (currentRole.value?.name) return currentRole.value.name
  if (isLawyerMode.value) return '律师'
  if (isTeacherMode.value) return '教师'
  if (isProgrammerMode.value) return '程序员'
  if (isWriterMode.value) return '作家'
  return undefined
})

const buildConversationHistoryForRecommendation = () => {
  return chatStore.messages
    .slice(-6)
    .map(msg => msg.content?.trim())
    .filter((content): content is string => Boolean(content))
}

const loadChatRecommendations = async () => {
  recommendationLoading.value = true
  try {
    chatRecommendations.value = await recommendationApi.getContextualRecommendations({
      roleName: currentRecommendationRoleName.value,
      scope: 'chat',
      currentInput: inputText.value.trim(),
      conversationHistory: buildConversationHistoryForRecommendation()
    })
  } catch (error) {
    console.warn('加载聊天推荐失败', error)
    chatRecommendations.value = []
  } finally {
    recommendationLoading.value = false
  }
}

const applyChatRecommendation = (item: RecommendationItem) => {
  useTemplate(item.text)
  recommendationCollapsed.value = true
}

const selectRole = async (role: any): Promise<boolean> => {
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
      return false
    }
  }

  selectedRoleId.value = role.id
  await roleStore.setCurrentRole(role)
  chatStore.setRole(role.id)
  showRoleDrawer.value = false
  ElMessage.success(`已切换到角色: ${role.name}`)
  return true
}

const roleNameAliases: Record<RoleId, string[]> = {
  lawyer: ['律师', '法律', 'lawyer'],
  teacher: ['教师', '教学', 'teacher'],
  programmer: ['程序', '开发', 'programmer', 'developer'],
  writer: ['作家', '写作', 'writer']
}

const openRoleTemplateDialog = () => {
  roleTemplateDialogOpen.value = true
}

const findRuntimeRole = (roleId: RoleId) => {
  const aliases = roleNameAliases[roleId]
  return roles.value.find(role => {
    const name = (role.name || '').toLowerCase()
    return aliases.some(alias => name.includes(alias))
  })
}

const applyRoleTemplateSelection = async (selection: { roleId: RoleId; templateKey: string }) => {
  const targetRole = findRuntimeRole(selection.roleId)
  const template = roleTemplateGroups
    .find(role => role.id === selection.roleId)
    ?.templates.find(item => item.key === selection.templateKey)

  if (!targetRole) {
    ElMessage.warning('该角色尚未启用，请先在角色管理中启用后再切换')
    return
  }

  if (targetRole.id !== currentRole.value?.id) {
    const switched = await selectRole(targetRole)
    if (!switched) return
  } else {
    ElMessage.success(`已选择 ${targetRole.name}${template ? ` / ${template.name}` : ''}`)
  }

  selectedChatTemplateKey.value = selection.templateKey
  localStorage.setItem(CHAT_TEMPLATE_KEY, selection.templateKey)
  roleTemplateDialogOpen.value = false
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
  inputText.value = ''
  const composerStartRect = chatStore.messages.length === 0
    ? composerRef.value?.getBoundingClientRect()
    : undefined

  try {
    let response: any
    if (isLawyerMode.value) {
      response = await chatStore.sendLawyerMessage(userText)
    } else if (isTeacherMode.value) {
      response = await chatStore.sendTeacherMessage(userText)
    } else if (isProgrammerMode.value) {
      response = await chatStore.sendProgrammerMessage(userText)
    } else if (isWriterMode.value) {
      response = await chatStore.sendWriterMessage(userText)
    } else {
      loading.value = false
      inputText.value = userText
      await upgradeChatToWorkflow()
      return
    }

    if (composerStartRect) await animateComposerToConversation(composerStartRect)
    if (response?.workflowRunId) {
      const binding = chatStore.getLatestWorkflowBinding(currentConversationId.value)
      await activateWorkflowRun(
        response.workflowRunId,
        binding?.runId === response.workflowRunId ? binding : null,
        false
      )
      ElMessage.success(`专业任务已进入 ACG：${response.workflowRunId}`)
    }
    scrollToBottom()
  } catch (error: any) {
    inputText.value = userText
    ElMessage.error(error?.message || '发送消息失败')
  } finally {
    loading.value = false
  }
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

  if (isAgentMode.value) {
    await sendAgentWorkspaceMessage()
    return
  }

  loading.value = true
  const userText = inputText.value.trim()
  inputText.value = ''
  const composerStartRect = chatStore.messages.length === 0
    ? composerRef.value?.getBoundingClientRect()
    : undefined

  try {
    const agentMode = isLawyerMode.value
      ? 'lawyer'
      : isTeacherMode.value
        ? 'teacher'
        : isProgrammerMode.value
          ? 'programmer'
          : isWriterMode.value
            ? 'writer'
            : 'default'
    const sendPromise = chatStore.sendMessageStream(userText, agentMode, loadModelSettings())
    if (composerStartRect) {
      await animateComposerToConversation(composerStartRect)
    }
    await sendPromise
    scrollToBottom()
  } catch (err: any) {
    ElMessage.error(err.message || '发送消息失败')
    inputText.value = userText
  } finally {
    loading.value = false
  }
}

interface PendingWorkflowSubmission {
  conversationId: string
  text: string
  clientRequestId: string
}

const workflowSubmissionStorageKey = (conversationId: string) =>
  `${WORKFLOW_SUBMISSION_KEY_PREFIX}${conversationId}`

const getWorkflowClientRequestId = (conversationId: string, text: string) => {
  try {
    const raw = sessionStorage.getItem(workflowSubmissionStorageKey(conversationId))
    const pending = raw ? JSON.parse(raw) as PendingWorkflowSubmission : null
    if (pending?.conversationId === conversationId && pending.text === text && pending.clientRequestId) {
      return pending.clientRequestId
    }
  } catch {
    // A malformed pending submission is replaced by a new explicit operation.
  }
  const clientRequestId = createClientRequestId()
  sessionStorage.setItem(workflowSubmissionStorageKey(conversationId), JSON.stringify({
    conversationId,
    text,
    clientRequestId
  } satisfies PendingWorkflowSubmission))
  return clientRequestId
}

const activateWorkflowRun = async (
  runId: string,
  binding: ChatWorkflowBinding | null,
  fresh: boolean
) => {
  conversationGeneration += 1
  workflowProgressState.reset()
  invalidateWorkflowResultRequest()
  activeWorkflowRunId.value = runId
  activeWorkflowBinding.value = binding
  activeWorkflowRun.value = null
  activeAcgView.value = null
  workflowStartError.value = null
  void workflowProgressState.start(runId, { fresh })
  await router.replace({ query: { ...route.query, runId } })
}

const workflowStartErrorMessage = (error: unknown) => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409) return '本次请求标识与原任务参数冲突，请重新发起'
    if (error.response?.status === 503 || !error.response) return 'ACG 任务暂时不可用，请稍后重试'
  }
  if (error instanceof Error && error.name === 'WorkflowApiContractError') {
    return 'ACG 启动响应契约无效'
  }
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
  const clientRequestId = getWorkflowClientRequestId(conversationId, userText)
  isSubmittingWorkflow.value = true
  workflowStartError.value = null
  inputText.value = ''
  try {
    const result = await chatStore.upgradeToWorkflow(userText, {
      domain: 'legal',
      intent: isLawyerMode.value ? 'case_analysis' : 'case_analysis',
      workflowId: 'legal_case_analysis_v1',
      reviewMode: 'human_in_loop',
      conversationId,
      clientRequestId
    })
    if (result) {
      sessionStorage.removeItem(workflowSubmissionStorageKey(conversationId))
      await activateWorkflowRun(result.binding.runId, result.binding, true)
      ElMessage.success(`已创建 WorkflowRun：${result.binding.runId}`)
    }
    scrollToBottom()
  } catch (error: unknown) {
    inputText.value = userText
    workflowStartError.value = workflowStartErrorMessage(error)
    if (axios.isAxiosError(error) && error.response?.status === 409) {
      sessionStorage.removeItem(workflowSubmissionStorageKey(conversationId))
    }
  } finally {
    isSubmittingWorkflow.value = false
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

const openTeacherUploadDialog = () => {
  if (!teacherUploadInputRef.value) return
  teacherUploadInputRef.value.value = ''
  teacherUploadInputRef.value.click()
}

const handleTeacherFileUpload = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return

  loading.value = true
  try {
    // Reuse FileManager upload backend.
    await fileApi.uploadFile(file, 'teacher').catch(() => undefined)

    const ocr = await agentTeacherApi.extractOcrText(file)
    if (!ocr.text) {
      ElMessage.warning('未识别到文本，请更换更清晰的文件后重试')
      return
    }

    const injected = `\n\n[OCR识别文本 - ${file.name}]\n${ocr.text}`
    inputText.value = `${inputText.value}${injected}`.trim()
    ElMessage.success('OCR 识别完成，已注入输入框')
  } catch (error: any) {
    ElMessage.error(error.message || '上传或 OCR 处理失败')
  } finally {
    loading.value = false
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

  if (isTeacherMode.value) {
    showFileManager.value = false
    ElMessage.info('教师模式建议使用“上传作业”按钮自动 OCR 注入文本')
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
  const composerStartRect = chatStore.messages.length === 0
    ? composerRef.value?.getBoundingClientRect()
    : undefined

  try {
    const sendPromise = chatStore.sendMessage('', fileUrl, loadModelSettings())
    if (composerStartRect) {
      await animateComposerToConversation(composerStartRect)
    }
    await sendPromise
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
  workspaceMode.value = mode
  if (mode === 'agent') {
    agentPanelCollapsed.value = showHeroMode.value
    setContextPanelOpen(!showHeroMode.value)
    setWorkflowPanelOpen(!showHeroMode.value)
  }
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

watch(
  availableLawyerResultPanels,
  panels => {
    activeLawyerResultPanels.value = [...panels]
  },
  { immediate: true }
)

watch(
  availableTeacherResultPanels,
  panels => {
    activeTeacherResultPanels.value = [...panels]
  },
  { immediate: true }
)

watch(
  availableProgrammerResultPanels,
  panels => {
    activeProgrammerResultPanels.value = [...panels]
  },
  { immediate: true }
)

watch(
  availableWriterResultPanels,
  panels => {
    activeWriterResultPanels.value = [...panels]
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

const bindMessagesScroll = () => {
  if (!messagesRef.value) return
  messagesRef.value.removeEventListener('scroll', checkScrollState)
  messagesRef.value.addEventListener('scroll', checkScrollState)
  checkScrollState()
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

watch(
  [() => chatStore.messages.length, debouncedInputText, currentRecommendationRoleName],
  () => {
    void loadChatRecommendations()
  },
  { immediate: true }
)

watch(showAssistTools, visible => {
  localStorage.setItem(ASSIST_TOOL_VISIBLE_KEY, visible ? '1' : '0')
})

watch(recommendationCollapsed, collapsed => {
  localStorage.setItem(RECOMMENDATION_COLLAPSED_KEY, collapsed ? '1' : '0')
})

watch(agentPanelCollapsed, collapsed => {
  localStorage.setItem(AGENT_PANEL_COLLAPSED_KEY, collapsed ? '1' : '0')
})

const restoreWorkflowForConversation = async (conversationChanged = false) => {
  const conversationId = currentConversationId.value
  const binding = chatStore.getActiveWorkflowBinding(conversationId)
    || chatStore.getLatestWorkflowBinding(conversationId)
  const routeRunId = typeof route.query.runId === 'string' ? route.query.runId.trim() : ''
  const queryRunId = conversationChanged && !binding ? '' : routeRunId
  const runId = binding?.runId || queryRunId

  if (runId && runId === activeWorkflowRunId.value && workflowProgressState.runId.value === runId) return

  const restoreGeneration = ++conversationGeneration
  workflowProgressState.reset()
  invalidateWorkflowResultRequest()
  activeWorkflowRunId.value = ''
  activeWorkflowBinding.value = null
  activeWorkflowRun.value = null
  activeAcgView.value = null
  workflowStartError.value = null
  if (!runId) {
    if (conversationChanged && routeRunId) {
      const { runId: _removed, ...remainingQuery } = route.query
      await router.replace({ query: remainingQuery })
    }
    return
  }

  activeWorkflowRunId.value = runId
  activeWorkflowBinding.value = binding?.runId === runId ? binding : null
  const cachedResult = workflowResultCache.get(runId)
  if (cachedResult) {
    activeWorkflowRun.value = cachedResult.run
    activeAcgView.value = cachedResult.view
  }
  await workflowProgressState.start(runId, { fresh: false })
  if (restoreGeneration !== conversationGeneration || runId !== activeWorkflowRunId.value) return
  if (binding && queryRunId !== runId) {
    await router.replace({ query: { ...route.query, runId } })
  }
}

watch(
  [currentConversationId, () => route.query.runId],
  ([conversationId], previous) => {
    const previousConversationId = previous?.[0]
    void restoreWorkflowForConversation(Boolean(previousConversationId && previousConversationId !== conversationId))
  },
  { immediate: true }
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

onMounted(async () => {
  window.addEventListener('workspace-mode-change', handleWorkspaceModeChange)
  window.addEventListener('resize', handleWorkflowPanelViewportResize)
  if (showHeroMode.value) {
    setContextPanelOpen(false)
    setWorkflowPanelOpen(false)
    agentPanelCollapsed.value = true
  }
  await roleStore.loadRoles()
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

  const assistToolVisible = localStorage.getItem(ASSIST_TOOL_VISIBLE_KEY)
  if (assistToolVisible === '1') {
    showAssistTools.value = true
  }

  const recommendationPanelCollapsed = localStorage.getItem(RECOMMENDATION_COLLAPSED_KEY)
  if (recommendationPanelCollapsed === '0') {
    recommendationCollapsed.value = false
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

  bindMessagesScroll()
})

onUnmounted(() => {
  window.removeEventListener('workspace-mode-change', handleWorkspaceModeChange)
  window.removeEventListener('resize', handleWorkflowPanelViewportResize)
  composerResizeObserver?.disconnect()
  stopAgentPanelResize()
  stopWorkflowPanelResize()
  stopContextPanelResize()
  workflowProgressState.reset()
  invalidateWorkflowResultRequest()
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
  background: transparent;
}

.chat-view.landing-active {
  background:
    radial-gradient(circle at 12% 16%, var(--primary-fade) 0, transparent 28%),
    radial-gradient(circle at 84% 18%, var(--accent-fade) 0, transparent 30%),
    linear-gradient(135deg, var(--bg-app) 0%, #fff 46%, var(--bg-app) 100%);
}

.simple-chat-home {
  position: relative;
  min-height: 100%;
  overflow: hidden;
  background:
    radial-gradient(circle at 18% 18%, var(--primary-fade) 0, transparent 30%),
    radial-gradient(circle at 82% 20%, var(--accent-fade) 0, transparent 30%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.58), rgba(255, 255, 255, 0.16)),
    var(--bg-app);
  color: var(--text-primary);
}

.landing-topbar {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  min-height: 72px;
  padding: 12px 14px 0;
  border-bottom: 1px solid var(--primary-line);
  background:
    linear-gradient(90deg, var(--primary-fade), var(--accent-fade)),
    rgba(255, 255, 255, 0.86);
  box-shadow: 0 10px 24px rgba(29, 36, 34, 0.06);
  backdrop-filter: blur(18px);
}

.landing-brand {
  width: 300px;
  min-width: 220px;
}

.landing-brand h1 {
  margin: 0;
  font-family: var(--font-serif);
  font-size: 20px;
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: -0.01em;
  color: var(--primary-color);
}

.landing-brand p {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1;
  font-weight: 500;
  color: var(--text-secondary);
  white-space: nowrap;
}

.landing-role-nav {
  position: absolute;
  left: 50%;
  top: 34px;
  display: flex;
  align-items: center;
  gap: 40px;
  transform: translateX(-50%);
  white-space: nowrap;
}

.landing-role {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-card) 58%, transparent);
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 650;
  line-height: 1;
  cursor: pointer;
}

.landing-role-mark {
  font-size: 14px;
  font-weight: 800;
  color: var(--accent-color);
}

.landing-network-btn {
  position: absolute;
  top: 24px;
  right: 17px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-width: 114px;
  height: 32px;
  padding: 0 17px;
  border: 1px solid var(--primary-color);
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.42);
}

.landing-network-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent-color);
  box-shadow: 0 0 0 4px var(--accent-fade);
}

.interface-switch {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 34px;
  padding: 3px;
  border: 1px solid var(--primary-line);
  border-radius: 999px;
  background: color-mix(in srgb, var(--bg-card) 76%, transparent);
  box-shadow: 0 8px 18px rgba(28, 39, 35, 0.06);
  backdrop-filter: blur(12px);
}

.interface-switch button {
  height: 26px;
  min-width: 58px;
  padding: 0 11px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.interface-switch button.active {
  background: linear-gradient(135deg, var(--primary-color), var(--accent-color));
  color: #fff;
  box-shadow: var(--shadow-glow);
}

.interface-switch.compact {
  height: 32px;
  box-shadow: none;
}

.interface-switch.compact button {
  height: 24px;
  min-width: 54px;
  padding: 0 10px;
}

.landing-interface-switch {
  position: absolute;
  top: 23px;
  right: 145px;
}

.chat-view.simple-interface .landing-topbar {
  padding-left: 92px;
}

.landing-hero {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  min-height: calc(100vh - 72px);
  padding: 0 24px;
  text-align: center;
}

.landing-hero h2 {
  position: absolute;
  left: 50%;
  bottom: calc(50% + 156px);
  width: min(820px, calc(100vw - 48px));
  margin: 0;
  font-family: var(--font-serif);
  font-size: 44px;
  line-height: 1.3;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  transform: translateX(-50%);
}

.landing-hero p {
  position: absolute;
  left: 50%;
  bottom: calc(50% + 104px);
  width: min(720px, calc(100vw - 48px));
  margin: 0;
  font-size: 17px;
  line-height: 1.5;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--text-secondary);
  transform: translateX(-50%);
}

.landing-composer {
  position: absolute;
  top: 50%;
  left: 50%;
  width: min(980px, calc(100vw - 48px));
  min-height: 160px;
  margin-top: 0;
  border: 1.5px solid var(--border-light);
  border-radius: 20px;
  background: color-mix(in srgb, var(--bg-card) 95%, transparent);
  box-shadow: var(--shadow-md), 0 2px 8px rgba(217, 119, 87, 0.06);
  text-align: left;
  transform: translate(-50%, -50%);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.landing-composer:focus-within {
  border-color: var(--primary-color);
  box-shadow: 0 0 0 4px rgba(217, 119, 87, 0.08), var(--shadow-md);
}

.landing-message-input {
  display: block;
  width: 100%;
  height: 94px;
  padding: 28px 23px 0;
  border: 0;
  outline: 0;
  resize: none;
  background: transparent;
  color: var(--text-primary);
  font: inherit;
  font-size: 15px;
  line-height: 1.5;
  font-weight: 500;
}

.landing-message-input::placeholder {
  color: var(--text-muted);
  opacity: 1;
}

.landing-composer-footer {
  position: absolute;
  right: 10px;
  bottom: 10px;
  left: 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.landing-quick-actions {
  flex: 1 1 auto;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.landing-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 32px;
  padding: 0 14px;
  border: none;
  border-radius: 999px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 1;
  font-weight: 500;
  white-space: nowrap;
  cursor: pointer;
}

.landing-chip-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--primary-color);
  opacity: 0.6;
}

.landing-composer-actions {
  display: flex;
  align-items: center;
  gap: 13px;
  flex: 0 0 auto;
}

.landing-composer-actions :deep(.model-runtime-controls) {
  margin-right: 2px;
}

.landing-attach-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 38px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--accent-color);
  cursor: pointer;
}

.landing-attach-btn svg {
  width: 27px;
  height: 27px;
  stroke-width: 2.4;
}

.landing-send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 42px;
  height: 42px;
  border: 0;
  border-radius: 999px;
  background: var(--primary-color);
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(217, 119, 87, 0.32);
  transition: background-color 0.18s ease, box-shadow 0.18s ease, transform 0.18s ease;
}

.landing-send-btn:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
}

.landing-role,
.landing-network-btn,
.landing-chip,
.landing-attach-btn,
.landing-send-btn {
  transition: border-color 160ms ease, background-color 160ms ease, color 160ms ease, transform 160ms ease;
}

.landing-role:hover,
.landing-network-btn:hover,
.landing-chip:hover,
.landing-attach-btn:hover,
.landing-send-btn:not(:disabled):hover {
  transform: translateY(-1px);
}

.landing-send-btn:not(:disabled):hover {
  background: var(--primary-hover);
  box-shadow: 0 6px 18px rgba(217, 119, 87, 0.4);
}

.landing-chip:hover,
.landing-network-btn:hover,
.landing-role:hover {
  color: var(--primary-color);
  background: rgba(217, 119, 87, 0.08);
}

.chat-view.simple-interface:not(.landing-active) {
  background:
    radial-gradient(circle at 18% 12%, var(--primary-fade) 0, transparent 30%),
    radial-gradient(circle at 82% 8%, var(--accent-fade) 0, transparent 28%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.58), rgba(255, 255, 255, 0.2)),
    var(--bg-app);
}

.simple-session-topbar {
  min-height: 70px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 22px 12px 92px;
  border-bottom: 1px solid var(--primary-line);
  background:
    linear-gradient(90deg, var(--primary-fade), var(--accent-fade)),
    rgba(255, 255, 255, 0.9);
  box-shadow: 0 10px 26px rgba(29, 36, 34, 0.07);
  backdrop-filter: blur(18px);
  position: relative;
  z-index: 5;
}

.simple-session-brand {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.simple-session-kicker {
  display: block;
  color: var(--accent-color);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.simple-session-brand h1 {
  margin: 0;
  overflow: hidden;
  color: var(--primary-color);
  font-size: 20px;
  font-weight: 750;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 8px;
}

.simple-session-brand h1::before {
  content: '';
  width: 7px;
  height: 7px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: var(--accent-color);
  box-shadow: 0 0 0 5px var(--accent-fade);
  animation: simple-thread-pulse 2.2s ease-in-out infinite;
}

@keyframes simple-thread-pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.55; transform: scale(0.85); }
}

.simple-session-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.simple-session-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--primary-line);
  border-radius: 8px;
  background: color-mix(in srgb, var(--bg-card) 78%, transparent);
  color: var(--text-secondary);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease, transform 0.16s ease;
}

.simple-session-btn:hover {
  border-color: var(--border-focus);
  background: var(--surface-solid);
  color: var(--primary-color);
  transform: translateY(-1px);
}

.chat-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
  padding: 0;
  transition: grid-template-columns 0.24s var(--ease-out);
}

.chat-main.has-agent-results {
  gap: 0;
  padding: 0;
}

.chat-main.lawyer,
.chat-main.teacher,
.chat-main.programmer,
.chat-main.writer {
  grid-template-columns: 1fr;
}

.chat-main.has-agent-results.lawyer,
.chat-main.has-agent-results.teacher,
.chat-main.has-agent-results.programmer,
.chat-main.has-agent-results.writer {
  grid-template-columns: minmax(0, 1fr) var(--agent-panel-width, 340px);
}

.chat-main.has-agent-results.agent-panel-collapsed {
  grid-template-columns: minmax(0, 1fr) 52px;
}

.chat-main.agent-panel-resizing {
  transition: none;
}

.chat-main.simple-session {
  grid-template-columns: minmax(0, 1fr);
  padding: 0;
  gap: 0;
}

.chat-main.simple-session .chat-panel {
  width: 100%;
  max-width: none;
  margin: 0 auto;
  border: 0;
  border-radius: 0;
  background: color-mix(in srgb, var(--bg-card) 72%, transparent);
  box-shadow: none;
}

.chat-main.simple-session .messages {
  padding-bottom: var(--composer-clearance, 220px);
  scroll-padding-bottom: var(--composer-clearance, 220px);
  background:
    radial-gradient(circle at 18% 0%, var(--primary-fade) 0, transparent 32%),
    radial-gradient(circle at 88% 4%, var(--accent-fade) 0, transparent 30%),
    transparent;
}

.chat-main.simple-session .message-list {
  width: min(100%, 940px);
  margin: 0 auto;
  padding: 6px 0 22px;
}

.chat-main.simple-session .empty-state {
  position: relative;
  max-width: 720px;
  margin: 56px auto;
  padding: 0 24px;
  border: none;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
  backdrop-filter: none;
}

.chat-main.simple-session .empty-state .rgb-orb {
  width: 56px;
  height: 56px;
}

.chat-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: var(--bg-app);
}

.context-panel {
  position: relative;
  z-index: 6;
  flex: 0 0 auto;
  min-height: 170px;
  overflow: hidden;
  border-bottom: 1px solid var(--border-light);
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
  border-bottom: 1px solid var(--border-light);
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
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  z-index: 6;
  min-height: 180px;
  overflow: hidden;
  border-top: 1px solid var(--border-light);
  background: color-mix(in srgb, var(--bg-card) 94%, var(--primary-fade));
  box-shadow: 0 -12px 30px rgba(26, 31, 58, 0.035);
  transition: height 0.2s var(--ease-out);
}

.workflow-acg-panel.resizing {
  transition: none;
}

.workflow-panel-resizer {
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
  position: absolute;
  inset: 42px 0 0;
  display: grid;
  place-items: center;
  color: var(--text-disabled);
  font-size: 12px;
  pointer-events: none;
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
  border-top: 1px solid var(--border-light);
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

.chat-panel.hero-mode .messages {
  overflow: hidden;
  padding-bottom: 0;
}

.chat-panel.hero-mode .empty-state {
  margin-top: clamp(96px, 12vh, 138px);
}

.chat-panel.hero-mode .composer {
  position: absolute;
  top: 52%;
  right: 0;
  left: 0;
  z-index: 4;
  transform: translateY(-50%);
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

.rgb-orb {
  --orb-cyan: rgb(75 220 255);
  --orb-magenta: rgb(210 99 255);
  --orb-green: rgb(92 255 177);
  position: relative;
  width: 52px;
  height: 52px;
  display: inline-block;
  margin-bottom: 20px;
  isolation: isolate;
  filter: saturate(1.08);
  animation: rgb-orb-breathe 3.8s ease-in-out infinite;
}

.rgb-orb__aura,
.rgb-orb__core,
.rgb-orb__ring,
.rgb-orb__particle {
  position: absolute;
  display: block;
  pointer-events: none;
}

.rgb-orb__aura {
  inset: 5px;
  z-index: -1;
  border-radius: 50%;
  background:
    radial-gradient(circle at 30% 32%, color-mix(in srgb, var(--orb-cyan) 68%, transparent), transparent 48%),
    radial-gradient(circle at 68% 35%, color-mix(in srgb, var(--orb-magenta) 68%, transparent), transparent 50%),
    radial-gradient(circle at 48% 72%, color-mix(in srgb, var(--orb-green) 58%, transparent), transparent 52%);
  filter: blur(9px);
  opacity: 0.72;
}

.rgb-orb__core {
  inset: 11px;
  border: 1px solid color-mix(in srgb, var(--text-primary) 24%, transparent);
  border-radius: 50%;
  background:
    radial-gradient(circle at 35% 28%, rgb(255 255 255 / 0.78) 0 3%, transparent 12%),
    conic-gradient(from 215deg, var(--orb-cyan), var(--orb-magenta), var(--orb-green), var(--orb-cyan));
  box-shadow:
    inset -5px -7px 13px rgb(21 22 39 / 0.48),
    inset 4px 3px 10px rgb(255 255 255 / 0.16),
    0 0 12px color-mix(in srgb, var(--orb-magenta) 42%, transparent);
  animation: rgb-orb-core 7s linear infinite;
}

.rgb-orb__core::after {
  content: '';
  position: absolute;
  inset: 5px;
  border-radius: inherit;
  background: radial-gradient(circle, rgb(30 31 46 / 0.08), rgb(30 31 46 / 0.52));
  backdrop-filter: blur(1px);
}

.rgb-orb__ring {
  inset: 4px;
  border-radius: 50%;
  border: 1px solid transparent;
  border-top-color: color-mix(in srgb, var(--orb-cyan) 74%, transparent);
  border-right-color: color-mix(in srgb, var(--orb-magenta) 54%, transparent);
  animation: rgb-orb-orbit 8s linear infinite;
}

.rgb-orb__ring--inner {
  inset: 8px;
  border-top-color: color-mix(in srgb, var(--orb-green) 68%, transparent);
  border-right-color: transparent;
  border-bottom-color: color-mix(in srgb, var(--orb-magenta) 46%, transparent);
  animation-duration: 5.8s;
  animation-direction: reverse;
}

.rgb-orb__particle {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 6px 1px currentColor;
  animation: rgb-orb-particle 2.8s ease-in-out infinite;
}

.rgb-orb__particle--1 { top: 3px; left: 25px; color: var(--orb-cyan); }
.rgb-orb__particle--2 { top: 12px; right: 4px; color: var(--orb-magenta); animation-delay: -0.6s; }
.rgb-orb__particle--3 { right: 8px; bottom: 8px; color: var(--orb-green); animation-delay: -1.2s; }
.rgb-orb__particle--4 { bottom: 3px; left: 20px; color: var(--orb-cyan); animation-delay: -1.8s; }
.rgb-orb__particle--5 { top: 27px; left: 2px; color: var(--orb-magenta); animation-delay: -2.2s; }
.rgb-orb__particle--6 { top: 9px; left: 9px; color: var(--orb-green); animation-delay: -2.6s; }

@keyframes rgb-orb-breathe {
  0%, 100% { transform: scale(0.96); filter: saturate(1.02) brightness(0.94); }
  50% { transform: scale(1.04); filter: saturate(1.18) brightness(1.08); }
}

@keyframes rgb-orb-core {
  to { transform: rotate(360deg); }
}

@keyframes rgb-orb-orbit {
  to { transform: rotate(360deg); }
}

@keyframes rgb-orb-particle {
  0%, 100% { opacity: 0.28; transform: scale(0.72); }
  48% { opacity: 1; transform: scale(1.18); }
}

.empty-state h2 {
  font-family: var(--font-serif);
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--text-primary);
  margin: 0 0 10px;
}

.empty-state p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.7;
}

.message-list {
  display: flex;
  flex-direction: column;
  gap: 26px;
}

.template-row {
  display: flex;
  gap: 8px;
  padding: 10px 16px 0;
  overflow-x: auto;
}

.recommendation-row {
  flex-shrink: 0;
  padding: 6px 16px 10px;
}

.recommendation-row.collapsed {
  padding-bottom: 8px;
}

.recommendation-toggle {
  width: 100%;
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 8px 12px;
  border: 1px solid var(--border-light);
  border-radius: 10px;
  background: color-mix(in srgb, var(--bg-card) 92%, transparent);
  color: var(--text-primary);
  font: inherit;
  cursor: pointer;
  transition: border-color 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
}

.recommendation-toggle:hover {
  border-color: var(--primary-color);
  background: var(--primary-fade);
  box-shadow: 0 8px 18px rgba(22, 101, 52, 0.08);
}

.recommendation-toggle-copy {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 10px;
  text-align: left;
}

.recommendation-toggle-title {
  flex: 0 0 auto;
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}

.recommendation-toggle-subtitle {
  min-width: 0;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.4;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recommendation-toggle-side {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--primary-color);
  font-size: 13px;
  font-weight: 700;
}

.recommendation-count {
  min-width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 12px;
  line-height: 1;
}

.recommendation-loading-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--primary-color);
  box-shadow: 0 0 0 0 rgba(47, 143, 131, 0.42);
  animation: recommendation-pulse 1.2s ease-out infinite;
}

.recommendation-panel-wrap {
  max-height: min(28vh, 260px);
  margin-top: 8px;
  padding-right: 2px;
  overflow-y: auto;
}

.recommendation-panel-wrap::-webkit-scrollbar {
  width: 5px;
}

.recommendation-panel-wrap::-webkit-scrollbar-track {
  background: transparent;
}

.recommendation-panel-wrap::-webkit-scrollbar-thumb {
  background: var(--border-light);
  border-radius: 999px;
}

/* 右侧工作台滑入动画 */
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

  .rgb-orb,
  .rgb-orb__core,
  .rgb-orb__ring,
  .rgb-orb__particle {
    animation: none;
  }
}

@keyframes recommendation-pulse {
  0% {
    box-shadow: 0 0 0 0 rgba(47, 143, 131, 0.42);
  }
  100% {
    box-shadow: 0 0 0 8px rgba(47, 143, 131, 0);
  }
}

@media (max-width: 620px) {
  .recommendation-toggle {
    align-items: flex-start;
  }

  .recommendation-toggle-copy {
    flex-direction: column;
    gap: 2px;
  }

  .recommendation-panel-wrap {
    max-height: min(34vh, 240px);
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
  width: 50%;
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
  width: 50%;
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

.composer-popover.recommendation-panel-wrap {
  max-height: min(28vh, 260px);
  margin-top: 0;
  padding: 7px;
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

.composer-shelf-count {
  min-width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0 5px;
  border-radius: 999px;
  background: var(--primary-fade);
  color: var(--primary-color);
  font-size: 9px;
  font-weight: 700;
}

.composer-card {
  order: 1;
  position: relative;
  z-index: 2;
  width: 50%;
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

.chat-main.simple-session .composer {
  padding: 18px 24px 22px;
  border-top: 0;
  background: transparent;
}

.chat-main.simple-session .composer-card,
.chat-main.simple-session .composer-popover {
  width: calc(50% - 24px);
}

.chat-main.simple-session .composer-shelf {
  width: calc(50% - 24px);
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

.composer-agent-mode {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: color 160ms ease, background 160ms ease, border-color 160ms ease;
}

.composer-agent-mode:hover {
  border-color: color-mix(in srgb, var(--primary-color) 26%, var(--border-light));
  background: color-mix(in srgb, var(--primary-color) 9%, transparent);
}

.composer-agent-mode:focus-visible {
  outline: 2px solid color-mix(in srgb, var(--primary-color) 58%, transparent);
  outline-offset: 2px;
}

.composer-agent-mode__chevron {
  font-size: 9px;
  opacity: 0.72;
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

.composer-runtime-lock {
  height: 28px;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 9px;
  border: 1px solid var(--primary-line);
  border-radius: 8px;
  background: color-mix(in srgb, var(--primary-fade) 72%, transparent);
  color: var(--primary-color);
  font-size: 11px;
  font-weight: 650;
  white-space: nowrap;
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

.agent-panel {
  position: relative;
  --agent-panel-accent: var(--primary-color);
  background: var(--bg-sidebar);
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
  border: 0;
  border-left: 1px solid var(--border-light);
  border-radius: 0;
  transition: border-color 0.2s ease, background-color 0.2s ease;
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

.chat-main.lawyer .agent-panel {
  --agent-panel-accent: #496b8f;
  border-left-color: rgba(73, 107, 143, 0.22);
}

.chat-main.teacher .agent-panel {
  --agent-panel-accent: #3d7656;
  border-left-color: rgba(61, 118, 86, 0.22);
}

.chat-main.programmer .agent-panel {
  --agent-panel-accent: #6f668f;
  border-left-color: rgba(111, 102, 143, 0.22);
}

.chat-main.writer .agent-panel {
  --agent-panel-accent: #9a7432;
  border-left-color: rgba(154, 116, 50, 0.22);
}

.results-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-start;
  gap: 7px;
  padding: 52px 18px 24px;
  color: var(--text-secondary);
  font-size: 13px;
}

.results-empty .empty-icon {
  width: 34px;
  height: 34px;
  padding: 8px;
  border-radius: 9px;
  background: var(--bg-panel);
  color: var(--agent-panel-accent);
  font-size: 18px;
  opacity: 1;
}

.results-empty-hint {
  max-width: 230px;
  color: var(--text-disabled);
  font-size: 11px;
  line-height: 1.55;
  text-align: center;
  text-wrap: pretty;
}

.agent-panel-content :deep(.skill-panel) {
  height: 100%;
  border: 0;
  border-radius: 0;
  background: transparent;
}

.agent-panel-content :deep(.lawyer-panel),
.agent-panel-content :deep(.teacher-panel),
.agent-panel-content :deep(.programmer-panel),
.agent-panel-content :deep(.writer-panel) {
  border-top: 0;
}

.agent-panel-content :deep(.panel-header) {
  min-height: 64px;
  padding: 10px 46px 10px 14px;
  gap: 8px;
  background: transparent;
  border-bottom: 1px solid var(--border-light);
}

.agent-panel-content :deep(.header-left) {
  min-width: 0;
  gap: 9px;
}

.agent-panel-content :deep(.agent-avatar) {
  flex: 0 0 30px;
  width: 30px;
  height: 30px;
  border-radius: 8px;
  background: var(--primary-fade);
  color: var(--agent-panel-accent);
  box-shadow: none;
  font-size: 15px;
}

.agent-panel-content :deep(.header-text) {
  min-width: 0;
  gap: 1px;
}

.agent-panel-content :deep(.panel-header h3) {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-panel-content :deep(.header-sub) {
  overflow: hidden;
  color: var(--text-disabled);
  font-size: 10px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-panel-content :deep(.header-badges) {
  flex: 0 0 auto;
}

.agent-panel-content :deep(.skill-pill),
.agent-panel-content :deep(.risk-pill) {
  padding: 3px 7px;
  border: 0;
  background: var(--bg-panel);
  color: var(--text-secondary);
  font-size: 10px;
  box-shadow: none;
}

.agent-panel-content :deep(.pill-dot) {
  width: 5px;
  height: 5px;
  background: var(--agent-panel-accent);
  animation: none;
}

.agent-panel-content :deep(.panel-tabs) {
  height: 32px;
  min-height: 32px;
  padding: 0 8px;
  background: transparent;
  border-bottom: 1px solid var(--border-light);
}

.agent-panel-content :deep(.tab-btn) {
  gap: 4px;
  height: 32px !important;
  min-height: 32px !important;
  max-height: 32px !important;
  box-sizing: border-box;
  padding: 0 6px !important;
  border-bottom-width: 1px;
  background: transparent;
  color: var(--text-disabled);
  font-size: 10px;
  font-weight: 600;
}

.agent-panel-content :deep(.tab-btn:hover) {
  background: transparent;
  color: var(--text-primary);
}

.agent-panel-content :deep(.tab-btn.active) {
  background: transparent;
  color: var(--text-primary);
  border-bottom-color: var(--agent-panel-accent);
}

.agent-panel-content :deep(.tab-icon) {
  display: none;
}

.agent-panel-content :deep(.tab-badge),
.agent-panel-content :deep(.tab-btn.active .tab-badge) {
  min-width: 13px;
  height: 13px;
  padding: 0 3px;
  line-height: 13px;
  background: var(--bg-panel);
  color: var(--text-secondary);
  font-size: 8px;
}

.agent-panel-content :deep(.empty) {
  justify-content: flex-start;
  min-height: 0;
  padding: 48px 18px 24px;
  color: var(--text-secondary);
}

.agent-panel-content :deep(.empty-illustration) {
  width: 34px;
  height: 34px;
  border: 0;
  border-radius: 9px;
  background: var(--bg-panel);
  color: var(--agent-panel-accent);
  box-shadow: none;
  font-size: 18px;
}

.agent-panel-content :deep(.empty-hint) {
  max-width: 230px;
  color: var(--text-disabled);
  font-size: 11px;
  line-height: 1.55;
  text-wrap: pretty;
}

.writer-content-preview {
  border: 1px solid rgba(154, 116, 50, 0.18);
  background: rgba(154, 116, 50, 0.05);
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: #67491c;
  white-space: pre-wrap;
}

.programmer-block {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.programmer-grid {
  display: grid;
  gap: 10px;
}

.programmer-grid.two-cols {
  grid-template-columns: 1fr 1fr;
}

.programmer-card {
  border: 1px solid rgba(111, 102, 143, 0.16);
  background: rgba(111, 102, 143, 0.05);
  border-radius: 8px;
  padding: 10px;
}

.programmer-card .card-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--accent-color);
  margin-bottom: 6px;
}

.programmer-card ul {
  margin: 0;
  padding-left: 16px;
  font-size: 13px;
  color: var(--text-regular);
  line-height: 1.5;
}

.programmer-meta {
  font-size: 12px;
  color: var(--text-regular);
}

.programmer-search-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-item {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-card);
  padding: 8px 10px;
}

.search-head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  margin-bottom: 6px;
}

.search-head .path {
  font-size: 12px;
  font-weight: 600;
  color: var(--primary-color);
  word-break: break-all;
}

.search-head .score {
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.search-item pre,
.code-block {
  margin: 0;
  border-radius: 8px;
  background: #1f2428;
  color: #e8ece8;
  padding: 10px;
  font-size: 12px;
  line-height: 1.45;
  overflow: auto;
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
  transition: all 0.2s ease;
}

.role-item:hover {
  border-color: var(--primary-color);
  background: var(--primary-fade);
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
  .landing-composer {
    min-height: 204px;
  }

  .landing-composer-footer {
    position: static;
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
    padding: 8px 14px 12px;
  }

  .landing-quick-actions {
    flex-wrap: wrap;
  }

  .landing-composer-actions {
    justify-content: flex-end;
  }
}

@media (max-width: 900px) {
  .workflow-run-strip,
  .chat-workflow-progress,
  .chat-workflow-review,
  .chat-workflow-error {
    width: calc(100% - 32px);
  }

  .landing-topbar {
    min-height: 118px;
    padding: 14px 18px 0;
  }

  .chat-view.simple-interface .landing-topbar {
    padding-left: 104px;
  }

  .landing-brand {
    width: auto;
  }

  .landing-role-nav {
    top: 78px;
    gap: 22px;
  }

  .landing-network-btn {
    top: 20px;
  }

  .landing-interface-switch {
    top: 20px;
    right: 142px;
  }

  .simple-session-topbar {
    align-items: flex-start;
    padding: 12px 18px 12px 78px;
  }

  .landing-hero {
    min-height: calc(100vh - 118px);
  }

  .landing-hero h2 {
    bottom: calc(50% + 184px);
    max-width: 680px;
    font-size: clamp(34px, 4.8vw, 38px);
    text-wrap: balance;
  }

  .landing-hero p {
    bottom: calc(50% + 132px);
    margin: 0;
    font-size: 18px;
  }

}

@media (max-width: 620px) {
  .chat-main:not(.simple-session) .composer-card,
  .workflow-run-strip,
  .chat-workflow-progress,
  .chat-workflow-review,
  .chat-workflow-error {
    width: 100%;
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

  .landing-topbar {
    min-height: 136px;
  }

  .landing-brand h1 {
    font-size: 20px;
  }

  .chat-view.simple-interface .landing-topbar {
    padding-left: 58px;
  }

  .landing-brand p {
    white-space: normal;
  }

  .landing-network-btn {
    min-width: 42px;
    width: 42px;
    padding: 0;
  }

  .landing-interface-switch {
    top: 58px;
    right: 16px;
  }

  .interface-switch button {
    min-width: 52px;
    padding: 0 9px;
  }

  .landing-network-btn span:last-child {
    display: none;
  }

  .landing-role-nav {
    top: 100px;
    right: 16px;
    left: 16px;
    justify-content: space-between;
    gap: 8px;
    transform: none;
    font-size: 11px;
  }

  .landing-role {
    gap: 4px;
  }

  .landing-hero {
    justify-content: flex-start;
    min-height: auto;
    padding: 42px 14px 24px;
  }

  .simple-session-topbar {
    flex-direction: column;
    align-items: stretch;
    min-height: 118px;
    padding-left: 58px;
  }

  .simple-session-actions {
    justify-content: flex-start;
  }

  .chat-main.simple-session {
    padding: 0;
  }

  .chat-main.simple-session .messages {
    padding: 16px 10px;
  }

  .chat-main.simple-session .empty-state {
    margin: 24px auto;
    padding: 24px 16px;
    border-radius: 14px;
  }

  .chat-main:not(.simple-session) .empty-state {
    margin: 18px auto;
    padding: 0 12px;
  }

  .chat-main:not(.simple-session) .empty-state .rgb-orb {
    width: 44px;
    height: 44px;
    margin-bottom: 12px;
  }

  .chat-main:not(.simple-session) .empty-state h2 {
    margin-bottom: 6px;
    font-size: 22px;
  }

  .chat-main:not(.simple-session) .empty-state p {
    line-height: 1.5;
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

  .chat-main.simple-session .composer {
    padding: 12px 10px 14px;
  }

  .chat-main.simple-session .composer > .el-textarea,
  .chat-main.simple-session .composer > .el-input,
  .chat-main.simple-session .composer-footer {
    width: 100%;
  }

  .chat-main .composer-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .composer-footer .left-actions {
    width: 100%;
  }

  .chat-main.simple-session .right-actions {
    justify-content: space-between;
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

  .landing-hero h2 {
    position: static;
    width: 100%;
    font-size: 30px;
    line-height: 1.28;
    transform: none;
  }

  .landing-hero p {
    position: static;
    width: 100%;
    margin: 14px 0 0;
    font-size: 16px;
    transform: none;
  }

  .landing-composer {
    position: relative;
    top: auto;
    left: auto;
    width: calc(100vw - 28px);
    min-height: 0;
    margin-top: 24px;
    border-radius: 14px;
    transform: none;
  }

  .landing-message-input {
    height: 76px;
    padding: 18px 18px 0;
  }

  .landing-chip {
    min-width: calc(50% - 6px);
    padding: 0 10px;
    font-size: 12px;
  }
}

@media (max-width: 1100px) {
  .chat-main.has-agent-results.lawyer,
  .chat-main.has-agent-results.teacher,
  .chat-main.has-agent-results.programmer,
  .chat-main.has-agent-results.writer {
    grid-template-columns: 1fr;
  }

  .agent-panel {
    border-left: none;
    border-top: 1px solid var(--border-light);
    max-height: 300px;
  }

  .agent-panel-resizer {
    display: none;
  }

  .programmer-grid.two-cols {
    grid-template-columns: 1fr;
  }
}
</style>
