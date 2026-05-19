<template>
  <div
    class="chat-view"
    :class="{
      'landing-active': shouldShowLanding,
      'simple-interface': isSimpleInterface,
      'detail-interface': isDetailInterface
    }"
  >
    <section v-if="shouldShowLanding" class="simple-chat-home" aria-label="知弈对话中心">
      <header class="landing-topbar">
        <section class="landing-brand" aria-label="产品信息">
          <h1>知弈对话中心</h1>
          <p>多角色协作 · ReAct Trace · RAG 引用</p>
        </section>

        <nav class="landing-role-nav" aria-label="角色导航">
          <button type="button" class="landing-role" @click="switchLandingRole('lawyer')">
            <span class="landing-role-mark lawyer">法</span>
            <span>律师</span>
          </button>
          <button type="button" class="landing-role" @click="switchLandingRole('teacher')">
            <span class="landing-role-mark teacher">教</span>
            <span>教师</span>
          </button>
          <button type="button" class="landing-role" @click="switchLandingRole('programmer')">
            <span class="landing-role-mark programmer">码</span>
            <span>程序员</span>
          </button>
          <button type="button" class="landing-role" @click="switchLandingRole('writer')">
            <span class="landing-role-mark writer">写</span>
            <span>作家</span>
          </button>
        </nav>

        <div class="interface-switch landing-interface-switch" aria-label="界面模式">
          <button
            type="button"
            :class="{ active: isSimpleInterface }"
            @click="switchToSimpleInterface"
          >
            简单版
          </button>
          <button
            type="button"
            :class="{ active: isDetailInterface }"
            @click="switchToDetailInterface"
          >
            详情版
          </button>
        </div>

        <button class="landing-network-btn" type="button" @click="openLandingNetwork">
          <span class="landing-network-dot" aria-hidden="true"></span>
          <span>联邦网络</span>
        </button>
      </header>

      <section class="landing-hero">
        <h2>知识如棋局，Agent 如棋手，任务如推演</h2>
        <p>迈向全局知识推演智能</p>

        <form class="landing-composer" autocomplete="off" @submit.prevent="submitLandingMessage">
          <textarea
            v-model="landingInputText"
            class="landing-message-input"
            aria-label="输入消息"
            placeholder="输入消息或选择任务模板..."
            @keydown="handleLandingKeydown"
          ></textarea>

          <div class="landing-composer-footer">
            <div class="landing-quick-actions" aria-label="任务模板">
              <button
                v-for="template in landingTemplates"
                :key="template"
                class="landing-chip"
                type="button"
                @click="applyLandingTemplate(template)"
              >
                <span class="landing-chip-dot" aria-hidden="true"></span>
                <span>{{ template }}</span>
              </button>
            </div>

            <div class="landing-composer-actions">
              <button class="landing-attach-btn" type="button" aria-label="添加附件" @click="openLandingAttachment">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="m21.4 11.1-9.5 9.5a6 6 0 0 1-8.5-8.5l10-10a4 4 0 0 1 5.7 5.7l-10 10a2 2 0 1 1-2.8-2.8l9.4-9.4" />
                </svg>
              </button>
              <button class="landing-send-btn" type="submit" :disabled="loading || !landingInputText.trim()">
                发送
              </button>
            </div>
          </div>
        </form>
      </section>
    </section>

    <template v-else>
    <header v-if="isSimpleInterface" class="simple-session-topbar" :class="headerClass">
      <div class="simple-session-brand">
        <span class="simple-session-kicker">简单版对话</span>
        <h1>{{ agentTitle }}</h1>
      </div>
      <div class="simple-session-actions">
        <div class="interface-switch compact" aria-label="界面模式">
          <button
            type="button"
            :class="{ active: isSimpleInterface }"
            @click="switchToSimpleInterface"
          >
            简单版
          </button>
          <button
            type="button"
            :class="{ active: isDetailInterface }"
            @click="switchToDetailInterface"
          >
            详情版
          </button>
        </div>
        <button class="simple-session-btn" type="button" @click="showRoleDrawer = true">
          <el-icon><User /></el-icon>
          <span>角色</span>
        </button>
        <button class="simple-session-btn" type="button" @click="goToAgentOsConsole">
          AgentOS
        </button>
      </div>
    </header>

    <header v-else class="chat-header" :class="headerClass">
      <div class="left">
        <span class="title">联邦智能体对话中心</span>
        <div class="mode-switcher">
          <button
            class="mode-btn"
            :class="{ active: isLawyerMode }"
            @click="toggleLawyerMode"
          >
            <el-icon class="mode-icon"><ScaleToOriginal /></el-icon>
            <span class="mode-label">律师</span>
          </button>
          <button
            class="mode-btn"
            :class="{ active: isTeacherMode }"
            @click="toggleTeacherMode"
          >
            <el-icon class="mode-icon"><School /></el-icon>
            <span class="mode-label">教师</span>
          </button>
          <button
            class="mode-btn"
            :class="{ active: isProgrammerMode }"
            @click="toggleProgrammerMode"
          >
            <el-icon class="mode-icon"><Cpu /></el-icon>
            <span class="mode-label">程序员</span>
          </button>
          <button
            class="mode-btn"
            :class="{ active: isWriterMode }"
            @click="toggleWriterMode"
          >
            <el-icon class="mode-icon"><EditPen /></el-icon>
            <span class="mode-label">作家</span>
          </button>
        </div>
      </div>
      <div class="right">
        <div class="interface-switch compact" aria-label="界面模式">
          <button
            type="button"
            :class="{ active: isSimpleInterface }"
            @click="switchToSimpleInterface"
          >
            简单版
          </button>
          <button
            type="button"
            :class="{ active: isDetailInterface }"
            @click="switchToDetailInterface"
          >
            详情版
          </button>
        </div>
        <el-button size="small" @click="showRoleDrawer = true">
          <el-icon><User /></el-icon>
          角色
        </el-button>
        <el-button size="small" @click="goToAgentOsConsole">
          AgentOS
        </el-button>
        <el-button size="small" @click="goToSettings">
          <el-icon><MoreFilled /></el-icon>
          设置
        </el-button>
      </div>
    </header>

    <div class="chat-main" :class="[chatMainClass, { 'simple-session': isSimpleInterface }]">
      <section class="chat-panel">
        <div class="messages" ref="messagesRef">
          <div v-if="chatStore.messages.length === 0" class="empty-state">
            <div class="empty-icon">
              <el-icon><component :is="agentIcon" /></el-icon>
            </div>
            <h2>{{ agentTitle }}</h2>
            <p>{{ agentSubtitle }}</p>
            <div class="quick-actions">
              <button v-if="currentTemplates[0]" class="quick-btn" @click="useTemplate(currentTemplates[0])">{{ currentTemplates[0] }}</button>
              <button v-if="currentTemplates[1]" class="quick-btn" @click="useTemplate(currentTemplates[1])">{{ currentTemplates[1] }}</button>
              <button v-if="currentTemplates[2]" class="quick-btn" @click="useTemplate(currentTemplates[2])">{{ currentTemplates[2] }}</button>
              <button v-if="!isLawyerMode" class="quick-btn lawyer-btn" @click="toggleLawyerMode">
                <el-icon><ScaleToOriginal /></el-icon>
                <span>律师 Agent</span>
              </button>
              <button v-if="!isTeacherMode" class="quick-btn teacher-btn" @click="toggleTeacherMode">
                <el-icon><School /></el-icon>
                <span>教师 Agent</span>
              </button>
              <button v-if="!isProgrammerMode" class="quick-btn programmer-btn" @click="toggleProgrammerMode">
                <el-icon><Cpu /></el-icon>
                <span>程序员 Agent</span>
              </button>
              <button v-if="!isWriterMode" class="quick-btn writer-btn" @click="toggleWriterMode">
                <el-icon><EditPen /></el-icon>
                <span>作家 Agent</span>
              </button>
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

        <div class="recommendation-row" :class="{ collapsed: recommendationCollapsed }">
          <button
            class="recommendation-toggle"
            type="button"
            :aria-expanded="!recommendationCollapsed"
            @click="toggleRecommendationPanel"
          >
            <span class="recommendation-toggle-copy">
              <span class="recommendation-toggle-title">下一步推荐</span>
              <span class="recommendation-toggle-subtitle">{{ recommendationToggleText }}</span>
            </span>
            <span class="recommendation-toggle-side">
              <span v-if="recommendationLoading" class="recommendation-loading-dot" aria-hidden="true"></span>
              <span class="recommendation-count">{{ chatRecommendations.length }}</span>
              <el-icon><component :is="recommendationCollapsed ? ArrowDownBold : ArrowUp" /></el-icon>
            </span>
          </button>

          <div v-show="!recommendationCollapsed" class="recommendation-panel-wrap">
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
              <el-button v-if="isTeacherMode" text @click="openTeacherUploadDialog">
                <el-icon><UploadFilled /></el-icon>
                上传作业
              </el-button>
              <el-button v-if="isDetailInterface" text :disabled="isWorkflowUpgradeDisabled" @click="upgradeChatToWorkflow">
                升级 Workflow
              </el-button>
              <input
                ref="teacherUploadInputRef"
                class="hidden-file-input"
                type="file"
                accept=".png,.jpg,.jpeg,.pdf,.txt,.doc,.docx"
                @change="handleTeacherFileUpload"
              />
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

      <aside v-if="isAgentMode && isDetailInterface" class="agent-panel">
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowDownBold,
  ArrowUp,
  ChatDotRound,
  Check,
  Close,
  Cpu,
  EditPen,
  Folder,
  Loading,
  Microphone,
  MoreFilled,
  Notebook,
  Reading,
  ScaleToOriginal,
  School,
  UploadFilled,
  User
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MessageBubble from '@/components/MessageBubble.vue'
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
import { agentTeacherApi } from '@/services/api/agentTeacher'
import { federatedModelApi } from '@/services/api/federatedModel'
import { fileApi } from '@/services/api/file'
import { recommendationApi, type RecommendationItem } from '@/services/api/recommendation'
import { useChatStore } from '@/stores/chat'
import { useRoleStore } from '@/stores/role'
import { useDebounce } from '@/composables/useDebounce'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

type ChatInterfaceMode = 'simple' | 'detail'
const CHAT_INTERFACE_MODE_KEY = 'chat.interface_mode'
const CHAT_INTERFACE_MODE_EVENT = 'chat-interface-mode-change'
const getInitialChatInterfaceMode = (): ChatInterfaceMode => {
  return localStorage.getItem(CHAT_INTERFACE_MODE_KEY) === 'detail' ? 'detail' : 'simple'
}

const roleStore = useRoleStore()
const chatStore = useChatStore()

const selectedRoleId = ref<string | null>(null)
const inputText = ref('')
const landingInputText = ref('')
const loading = ref(false)
const showRoleDrawer = ref(false)
const showFileManager = ref(false)
const isRecording = ref(false)
const messagesRef = ref<HTMLElement | null>(null)
const teacherUploadInputRef = ref<HTMLInputElement | null>(null)
const showAssistTools = ref(true)
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
const ASSIST_TOOL_VISIBLE_KEY = 'chat.assist_tools_visible'
const RECOMMENDATION_COLLAPSED_KEY = 'chat.recommendation_collapsed'
const landingTemplates = ['合同纠纷咨询', '劳动仲裁流程', '法律风险评估', '文书草稿生成']
const debouncedInputText = useDebounce(inputText, 350)

const roles = computed(() => roleStore.roles)
const currentRole = computed(() => roleStore.currentRole)
const chatInterfaceMode = ref<ChatInterfaceMode>(getInitialChatInterfaceMode())
const isSimpleInterface = computed(() => chatInterfaceMode.value === 'simple')
const isDetailInterface = computed(() => chatInterfaceMode.value === 'detail')
const showLanding = ref(chatInterfaceMode.value === 'simple')
const shouldShowLanding = computed(() => {
  return isSimpleInterface.value && showLanding.value && chatStore.messages.length === 0 && !route.query.contextId
})

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

const isAgentMode = computed(() => isLawyerMode.value || isTeacherMode.value || isProgrammerMode.value || isWriterMode.value)

const headerClass = computed(() => {
  if (isLawyerMode.value) return 'lawyer-active'
  if (isTeacherMode.value) return 'teacher-active'
  if (isProgrammerMode.value) return 'programmer-active'
  if (isWriterMode.value) return 'writer-active'
  return ''
})

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

const showScrollToBottom = computed(() => !isNearBottom.value && chatStore.messages.length > 0)
const isSendDisabled = computed(() => loading.value || (!inputText.value.trim() && !isRecording.value))
const isWorkflowUpgradeDisabled = computed(() => loading.value || !inputText.value.trim())

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

const goToSettings = () => {
  router.push('/settings')
}

const goToAgentOsConsole = () => {
  router.push('/agentos-console')
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

const setChatInterfaceMode = async (mode: ChatInterfaceMode) => {
  chatInterfaceMode.value = mode
  localStorage.setItem(CHAT_INTERFACE_MODE_KEY, mode)
  window.dispatchEvent(new CustomEvent(CHAT_INTERFACE_MODE_EVENT, { detail: { mode } }))

  if (mode === 'detail') {
    showLanding.value = false
  } else if (chatStore.messages.length === 0 && !route.query.contextId) {
    showLanding.value = true
  }

  await nextTick()
  bindMessagesScroll()
}

const switchToSimpleInterface = () => {
  void setChatInterfaceMode('simple')
}

const switchToDetailInterface = () => {
  void setChatInterfaceMode('detail')
}

const revealFullChat = async () => {
  showLanding.value = false
  await nextTick()
  bindMessagesScroll()
}

const submitLandingMessage = async () => {
  const text = landingInputText.value.trim()
  if (!text || loading.value) return

  await revealFullChat()
  inputText.value = text
  landingInputText.value = ''
  await sendMessage()
}

const handleLandingKeydown = (event: KeyboardEvent) => {
  if (event.isComposing || event.keyCode === 229) return
  if (event.key !== 'Enter') return
  if (event.ctrlKey || event.shiftKey) return

  event.preventDefault()
  submitLandingMessage()
}

const applyLandingTemplate = async (text: string) => {
  await revealFullChat()
  useTemplate(text)
}

const switchLandingRole = async (mode: 'lawyer' | 'teacher' | 'programmer' | 'writer') => {
  await revealFullChat()
  if (mode === 'lawyer') await toggleLawyerMode()
  if (mode === 'teacher') await toggleTeacherMode()
  if (mode === 'programmer') await toggleProgrammerMode()
  if (mode === 'writer') await toggleWriterMode()
}

const openLandingNetwork = async () => {
  await revealFullChat()
  openFederatedConsole()
}

const openLandingAttachment = async () => {
  await revealFullChat()
  handleControl('folder')
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
    if (isLawyerMode.value) {
      await chatStore.sendLawyerMessage(userText)
    } else if (isTeacherMode.value) {
      await chatStore.sendTeacherMessage(userText)
    } else if (isProgrammerMode.value) {
      await chatStore.sendProgrammerMessage(userText)
    } else if (isWriterMode.value) {
      await chatStore.sendWriterMessage(userText)
    } else {
      await chatStore.sendMessageStream(userText)
    }
    scrollToBottom()
  } catch (err: any) {
    ElMessage.error(err.message || '发送消息失败')
    inputText.value = userText
  } finally {
    loading.value = false
  }
}

const upgradeChatToWorkflow = async () => {
  if (loading.value) return
  const userText = inputText.value.trim()
  if (!userText) {
    ElMessage.warning('请输入要升级为 Workflow 的内容')
    return
  }

  loading.value = true
  inputText.value = ''
  try {
    const response = await chatStore.upgradeToWorkflow(userText, {
      domain: 'legal',
      intent: isLawyerMode.value ? 'case_analysis' : 'case_analysis',
      reviewMode: 'human_in_loop'
    })
    if (response?.run?.runId) {
      ElMessage.success(`已创建 WorkflowRun：${response.run.runId}`)
    }
    scrollToBottom()
  } catch (err: any) {
    inputText.value = userText
    ElMessage.error(err.message || '升级 Workflow 失败')
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

onMounted(async () => {
  window.dispatchEvent(new CustomEvent(CHAT_INTERFACE_MODE_EVENT, { detail: { mode: chatInterfaceMode.value } }))
  if (chatInterfaceMode.value === 'detail') {
    showLanding.value = false
  }

  await roleStore.loadRoles()

  const assistToolVisible = localStorage.getItem(ASSIST_TOOL_VISIBLE_KEY)
  if (assistToolVisible === '0') {
    showAssistTools.value = false
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
  background: #f6f8f5;
}

.simple-chat-home {
  position: relative;
  min-height: 100%;
  overflow: hidden;
  background: #f6f8f5;
  color: #1f2937;
}

.landing-topbar {
  position: relative;
  z-index: 2;
  display: flex;
  align-items: flex-start;
  min-height: 72px;
  padding: 12px 14px 0;
  border-bottom: 1px solid #e2e7e2;
  background: #f6f8f5;
}

.landing-brand {
  width: 300px;
  min-width: 220px;
}

.landing-brand h1 {
  margin: 0;
  font-size: 20px;
  line-height: 1.2;
  font-weight: 750;
  letter-spacing: 0;
  color: #1f2937;
}

.landing-brand p {
  margin: 10px 0 0;
  font-size: 13px;
  line-height: 1;
  font-weight: 500;
  color: #6f7885;
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
  padding: 0;
  border: none;
  background: transparent;
  color: #6f7885;
  font: inherit;
  font-size: 12px;
  font-weight: 650;
  line-height: 1;
  cursor: pointer;
}

.landing-role-mark {
  font-size: 14px;
  font-weight: 800;
}

.landing-role-mark.lawyer,
.landing-role-mark.teacher {
  color: #2f8f83;
}

.landing-role-mark.programmer {
  color: #3f566f;
}

.landing-role-mark.writer {
  color: #c58a1d;
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
  border: 1px solid #2f8f83;
  border-radius: 999px;
  background: transparent;
  color: #2f8f83;
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}

.landing-network-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #2f8f83;
}

.interface-switch {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  height: 34px;
  padding: 3px;
  border: 1px solid #dce5df;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.82);
  box-shadow: 0 8px 18px rgba(28, 39, 35, 0.06);
}

.interface-switch button {
  height: 26px;
  min-width: 58px;
  padding: 0 11px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: #6f7885;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  white-space: nowrap;
  transition: background-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease;
}

.interface-switch button.active {
  background: #2f8f83;
  color: #fff;
  box-shadow: 0 6px 12px rgba(47, 143, 131, 0.18);
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
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 220px 24px 80px;
  text-align: center;
}

.landing-hero h2 {
  margin: 0;
  font-family: "STXingkai", "KaiTi", "FangSong", serif;
  font-size: 52px;
  line-height: 1.25;
  font-weight: 500;
  letter-spacing: 0;
  color: #1f2937;
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.7);
}

.landing-hero p {
  margin: 35px 0 0;
  font-size: 21px;
  line-height: 1.35;
  font-weight: 760;
  letter-spacing: 0;
  color: #1f2937;
}

.landing-composer {
  position: relative;
  width: min(900px, calc(100vw - 48px));
  height: 164px;
  margin-top: 58px;
  border: 1px solid #dde4df;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 16px 24px rgba(28, 39, 35, 0.08);
  text-align: left;
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
  color: #1f2937;
  font: inherit;
  font-size: 15px;
  line-height: 1.5;
  font-weight: 500;
}

.landing-message-input::placeholder {
  color: #b8c0c4;
  opacity: 1;
}

.landing-composer-footer {
  position: absolute;
  right: 10px;
  bottom: 10px;
  left: 33px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 24px;
}

.landing-quick-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.landing-chip {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
  min-width: 126px;
  height: 34px;
  padding: 0 17px 0 13px;
  border: 1.4px solid #8794a3;
  border-radius: 999px;
  background: #fff;
  color: #667280;
  font-size: 13px;
  line-height: 1;
  font-weight: 650;
  white-space: nowrap;
  cursor: pointer;
}

.landing-chip-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 auto;
  border-radius: 50%;
  background: #6f7d8b;
}

.landing-composer-actions {
  display: flex;
  align-items: center;
  gap: 13px;
  flex: 0 0 auto;
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
  color: #b6bcc0;
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
  width: 96px;
  height: 43px;
  border: 0;
  border-radius: 8px;
  background: #2f8f83;
  color: #fff;
  font: inherit;
  font-size: 14px;
  font-weight: 650;
  cursor: pointer;
  box-shadow: 0 8px 16px rgba(47, 143, 131, 0.18);
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
  background: #23786e;
}

.landing-chip:hover,
.landing-network-btn:hover {
  border-color: #2f8f83;
  color: #2f8f83;
  background: rgba(47, 143, 131, 0.04);
}

.chat-view.simple-interface:not(.landing-active) {
  background: #f6f8f5;
}

.simple-session-topbar {
  min-height: 72px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 22px 12px 92px;
  border-bottom: 1px solid #e2e7e2;
  background: rgba(246, 248, 245, 0.92);
  backdrop-filter: blur(18px);
}

.simple-session-brand {
  min-width: 0;
}

.simple-session-kicker {
  display: block;
  margin-bottom: 4px;
  color: #6f7885;
  font-size: 12px;
  font-weight: 700;
}

.simple-session-brand h1 {
  margin: 0;
  overflow: hidden;
  color: #1f2937;
  font-size: 20px;
  font-weight: 750;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
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
  border: 1px solid #dce5df;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.82);
  color: #3f566f;
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
  transition: border-color 0.16s ease, background-color 0.16s ease, transform 0.16s ease;
}

.simple-session-btn:hover {
  border-color: rgba(47, 143, 131, 0.36);
  background: #fff;
  transform: translateY(-1px);
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 18px 24px 14px;
  border-bottom: 1px solid var(--border-light);
  background: rgba(251, 251, 248, 0.72);
  backdrop-filter: blur(18px);
  transition: border-bottom-color 0.3s ease, background 0.3s ease;
}

.chat-header.lawyer-active {
  border-bottom-color: rgba(73, 107, 143, 0.32);
}

.chat-header.teacher-active {
  border-bottom-color: rgba(61, 118, 86, 0.32);
}

.chat-header.programmer-active {
  border-bottom-color: rgba(111, 102, 143, 0.32);
}

.chat-header.writer-active {
  border-bottom-color: rgba(154, 116, 50, 0.32);
}

.chat-header .left {
  display: flex;
  align-items: center;
  gap: 14px;
}

.chat-header .title {
  font-size: 17px;
  font-weight: 650;
  color: var(--text-primary);
  letter-spacing: 0;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 4px;
  background: #fff;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 3px;
  box-shadow: var(--shadow-sm);
}

.mode-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  min-height: 32px;
  padding: 6px 12px;
  border: none;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 560;
  color: var(--text-secondary);
  transition: var(--transition);
  white-space: nowrap;
}

.mode-btn:hover {
  background: var(--bg-panel);
  color: var(--text-primary);
}

.mode-btn.active {
  background: var(--primary-fade);
  color: var(--primary-color);
  box-shadow: inset 0 0 0 1px var(--primary-line);
}

.mode-btn:first-child.active {
  color: var(--info);
}

.mode-btn:nth-child(2).active {
  color: var(--success);
}

.mode-btn:nth-child(3).active {
  color: var(--accent-color);
}

.mode-btn:nth-child(4).active {
  color: var(--warning);
}

.mode-icon {
  font-size: 15px;
}

.mode-label {
  font-size: 12px;
}

.chat-header .right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.chat-main {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr;
  gap: 16px;
  padding: 16px 18px 18px;
  transition: grid-template-columns 0.24s var(--ease-out);
}

.chat-main.lawyer,
.chat-main.teacher,
.chat-main.programmer,
.chat-main.writer {
  grid-template-columns: 1fr 340px;
}

.chat-main.simple-session {
  grid-template-columns: minmax(0, 1fr);
  padding: 16px 22px 22px;
}

.chat-main.simple-session .chat-panel {
  width: min(100%, 980px);
  margin: 0 auto;
}

.chat-panel {
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.86);
  box-shadow: var(--shadow-sm);
}

.messages {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 22px 16px;
}

.messages::-webkit-scrollbar {
  width: 5px;
}

.messages::-webkit-scrollbar-track {
  background: transparent;
}

.messages::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 999px;
}

.empty-state {
  margin: 58px auto;
  text-align: center;
  max-width: 640px;
  animation: fade-in 0.28s var(--ease-out);
}

@keyframes fade-in {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.empty-state .empty-icon {
  width: 56px;
  height: 56px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 16px;
  border: 1px solid var(--primary-line);
  border-radius: 8px;
  background: #fff;
  color: var(--primary-color);
  font-size: 26px;
  box-shadow: var(--shadow-sm);
}

.empty-state h2 {
  font-size: 22px;
  font-weight: 650;
  color: var(--text-primary);
  margin: 0 0 10px;
}

.empty-state p {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0;
  line-height: 1.7;
}

.quick-actions {
  margin-top: 20px;
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 8px;
}

.quick-btn {
  border: 1px solid var(--border-light);
  background: #fff;
  border-radius: 8px;
  padding: 8px 14px;
  white-space: nowrap;
  cursor: pointer;
  font-size: 13px;
  font-weight: 560;
  color: var(--text-primary);
  transition: var(--transition);
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.quick-btn:hover {
  border-color: var(--primary-color);
  background: var(--primary-fade);
  transform: translateY(-1px);
}

.quick-btn.lawyer-btn {
  border-color: rgba(73, 107, 143, 0.2);
  color: var(--info);
}

.quick-btn.lawyer-btn:hover {
  background: rgba(73, 107, 143, 0.08);
}

.quick-btn.teacher-btn {
  border-color: rgba(61, 118, 86, 0.2);
  color: var(--success);
}

.quick-btn.teacher-btn:hover {
  background: rgba(61, 118, 86, 0.08);
}

.quick-btn.programmer-btn {
  border-color: rgba(111, 102, 143, 0.2);
  color: var(--accent-color);
}

.quick-btn.programmer-btn:hover {
  background: rgba(111, 102, 143, 0.08);
}

.quick-btn.writer-btn {
  border-color: rgba(154, 116, 50, 0.2);
  color: var(--warning);
}

.quick-btn.writer-btn:hover {
  background: rgba(154, 116, 50, 0.08);
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
  border-radius: 8px;
  background: var(--primary-color);
  color: #fff;
  cursor: pointer;
  transition: var(--transition);
}

.to-bottom:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-glow);
}

.chat-main.teacher .to-bottom {
  background: var(--success);
}

.chat-main.teacher .to-bottom:hover {
  box-shadow: 0 10px 24px rgba(61, 118, 86, 0.18);
}

.chat-main.programmer .to-bottom {
  background: var(--accent-color);
}

.chat-main.programmer .to-bottom:hover {
  box-shadow: 0 10px 24px rgba(111, 102, 143, 0.18);
}

.chat-main.writer .to-bottom {
  background: var(--warning);
}

.chat-main.writer .to-bottom:hover {
  box-shadow: 0 10px 24px rgba(154, 116, 50, 0.18);
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
  background: rgba(255, 255, 255, 0.92);
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
  background: #d1d5db;
  border-radius: 999px;
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
  background: #fff;
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
  border-top: 1px solid var(--border-light);
  background: rgba(255, 255, 255, 0.94);
  padding: 14px 16px 16px;
  transition: border-top-color 0.3s ease;
}

.chat-main.teacher .composer {
  border-top-color: rgba(61, 118, 86, 0.22);
}

.chat-main.lawyer .composer {
  border-top-color: rgba(73, 107, 143, 0.22);
}

.chat-main.programmer .composer {
  border-top-color: rgba(111, 102, 143, 0.22);
}

.chat-main.writer .composer {
  border-top-color: rgba(154, 116, 50, 0.22);
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
  flex-wrap: wrap;
}

.hidden-file-input {
  display: none;
}

.word-count.warning {
  color: #f59e0b;
}

.agent-panel {
  border-left: 1px solid var(--border-light);
  background: rgba(251, 251, 248, 0.9);
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 12px;
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  transition: border-left-color 0.3s ease, background 0.3s ease;
}

.chat-main.lawyer .agent-panel {
  border-left-color: rgba(73, 107, 143, 0.22);
}

.chat-main.teacher .agent-panel {
  border-left-color: rgba(61, 118, 86, 0.22);
}

.chat-main.programmer .agent-panel {
  border-left-color: rgba(111, 102, 143, 0.22);
}

.chat-main.writer .agent-panel {
  border-left-color: rgba(154, 116, 50, 0.22);
}

.results-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 32px 16px;
  color: var(--text-secondary);
  font-size: 13px;
}

.results-empty .empty-icon {
  font-size: 24px;
  opacity: 0.8;
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
  color: #374151;
  line-height: 1.5;
}

.programmer-meta {
  font-size: 12px;
  color: #475569;
}

.programmer-search-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-item {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: #fff;
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
  color: #64748b;
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

@media (max-width: 900px) {
  .landing-topbar {
    min-height: 118px;
    padding: 14px 18px 0;
  }

  .chat-view.simple-interface .landing-topbar {
    padding-left: 78px;
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
    padding-top: 150px;
  }

  .landing-hero h2 {
    max-width: 680px;
    font-size: 40px;
  }

  .landing-hero p {
    margin-top: 24px;
    font-size: 18px;
  }

  .landing-composer {
    height: auto;
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

@media (max-width: 620px) {
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
    padding: 110px 16px 56px;
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
    padding: 12px 10px 14px;
  }

  .landing-hero h2 {
    font-size: 32px;
  }

  .landing-hero p {
    font-size: 16px;
  }

  .landing-composer {
    width: calc(100vw - 28px);
    margin-top: 42px;
    border-radius: 14px;
  }

  .landing-message-input {
    height: 104px;
    padding: 23px 18px 0;
  }

  .landing-chip {
    min-width: calc(50% - 6px);
    padding: 0 10px;
    font-size: 12px;
  }
}

@media (max-width: 1100px) {
  .chat-main.lawyer,
  .chat-main.teacher,
  .chat-main.programmer,
  .chat-main.writer {
    grid-template-columns: 1fr;
  }

  .agent-panel {
    border-left: none;
    border-top: 1px solid var(--border-light);
    max-height: 300px;
  }

  .programmer-grid.two-cols {
    grid-template-columns: 1fr;
  }
}
</style>
