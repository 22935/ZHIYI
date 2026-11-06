<!-- 知弈OS 原生 ACG 工作台 — 专业语义通过编译期 Plugin UI Extension 增量注入。 -->
<template>
  <div class="acg-view ui-shell" :class="{ 'has-progress': isSubmitting || progressTracker.progress.value || progressTracker.syncError.value, 'has-run': !!activeRunId, 'is-draft': !activeRunId }">
    <WorkbenchLayout :show-right="Boolean(acgView)">
      <template #left>
        <AcgRunManager
          :active-run-id="activeRunId"
          @new="startNewAcgFromExplorer"
          @select="openAcgRunFromExplorer"
          @deleted="handleAcgRunDeletedFromExplorer"
          @manage="openAcgOperationsFromExplorer"
        />
      </template>

      <template #main>
        <div ref="acgMainPane" class="acg-main-pane">
    <header class="workbench-editor-toolbar" aria-label="当前任务信息">
      <div class="hero-left">
        <div class="editor-toolbar__identity">
          <strong>{{ editorTitle }}</strong>
          <span>{{ editorMetadata }}</span>
        </div>
      </div>
      <div class="hero-right">
        <button v-if="pendingInitialLaunch" type="button" :disabled="isSubmitting" @click="resumeInitialLaunch">核对并恢复原提交</button>
        <span v-if="displayedMissionId" class="hero-run-chip" :title="`任务 ID: ${displayedMissionId}`">
          <span>任务 ID</span>
          <code>{{ displayedMissionId }}</code>
        </span>
        <button class="hero-operations" type="button" @click="openOperations">
          <el-icon><Monitor /></el-icon>
          <span>运维查看</span>
        </button>
      </div>
    </header>

    <header class="workbench-editor-tabbar" aria-label="已打开的 ACG 任务">
      <div
        v-for="tab in visibleEditorTabs"
        :key="tab.id"
        class="workbench-editor-tab"
        :class="{ 'is-active': tab.id === activeEditorTabId }"
      >
        <button
          class="workbench-editor-tab__main"
          type="button"
          role="tab"
          :aria-selected="tab.id === activeEditorTabId"
          @click="selectEditorTab(tab.id)"
        >
          <span class="workbench-editor-tab__icon"><el-icon><Cpu /></el-icon></span>
          <span class="workbench-editor-tab__title" :title="tab.title">{{ tab.title }}</span>
          <span v-if="tab.status" class="workbench-editor-tab__status" :class="`is-${tab.status}`">{{ editorTabStatusLabel(tab.status) }}</span>
        </button>
        <button
          v-if="tab.runId"
          class="workbench-editor-tab__close"
          type="button"
          :title="`关闭 ${tab.title}`"
          :aria-label="`关闭 ${tab.title}`"
          @click.stop="closeEditorTab(tab.id)"
        >
          <el-icon><Close /></el-icon>
        </button>
      </div>
    </header>

    <!-- 任务配置栏目：与运行概览保持独立，可分别折叠。 -->
    <section class="acg-task-config-section" aria-label="任务配置">
    <div v-show="inputPanelExpanded" class="acg-task-config-expanded">
    <!-- 控制台 -->
    <section class="control-bar" :class="{ collapsed: inputPanelCompact, 'advanced-open': advancedSettingsExpanded }">
      <button
        class="input-panel-toggle"
        type="button"
        title="收起任务配置"
        aria-label="收起任务配置"
        :aria-expanded="inputPanelExpanded"
        @click="inputPanelExpanded = !inputPanelExpanded"
      >
        <el-icon><ArrowUp v-if="inputPanelExpanded" /><ArrowDown v-else /></el-icon>
      </button>
      <div v-if="inputPanelCompact" class="input-summary">
        <span class="input-summary__copy">
          <el-icon><Document /></el-icon>
          <strong>{{ taskName || '未命名 ACG 任务' }}</strong>
          <small>任务材料 · {{ taskMaterialLength.toLocaleString('zh-CN') }} 字｜{{ planningModeSummary }}｜{{ advancedSettingsSummary }}｜{{ activePluginSummary }}</small>
        </span>
      </div>
      <Transition
        :duration="380"
        @before-enter="beforeInputPanelEnter"
        @enter="enterInputPanel"
        @after-enter="afterInputPanelEnter"
        @before-leave="beforeInputPanelLeave"
        @leave="leaveInputPanel"
        @after-leave="afterInputPanelLeave"
      >
        <div v-show="inputPanelExpanded" class="input-panel-expandable">
      <div class="workbench-identity">
        <!-- <div><strong>知弈OS 原生任务工作台</strong><small>默认只使用 Native 能力；专业能力包按 Run 显式启用</small></div> -->
      </div>
      <div class="input-fields">
        <div class="input-pane contract-pane">
          <span class="pane-heading">任务材料</span>
          <div class="ctrl-row">
            <label class="ctrl-label">文本材料（可选）</label>
            <el-input class="contract-textarea" v-model="contractText" type="textarea" :autosize="{ minRows: 6, maxRows: 14 }" placeholder="粘贴需求、背景资料、研究材料或其他任务上下文" />
          </div>
          <div class="contract-upload" :class="{ dragging: uploadDragging, populated: selectedContractFile, loading: loading.upload }" @dragenter.prevent="uploadDragging = true" @dragover.prevent="uploadDragging = true" @dragleave.prevent="uploadDragging = false" @drop.prevent="handleContractDrop">
            <input ref="contractFileInput" class="contract-file-input" type="file" accept=".pdf,.docx,.txt,.md,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown" @change="handleContractFileSelection" />
            <span class="contract-upload__icon" aria-hidden="true"><el-icon><Document v-if="selectedContractFile" /><UploadFilled v-else /></el-icon></span>
            <span class="contract-upload__copy">
              <strong>{{ selectedContractFile?.originalFilename || (uploadState === 'parsing' ? '正在解析任务文件' : loading.upload ? '正在上传任务文件' : '补充任务文件') }}</strong>
              <small v-if="selectedContractFile">{{ formatFileSize(selectedContractFile.size) }} · 已提取 {{ selectedContractFile.textLength.toLocaleString('zh-CN') }} 字</small>
              <small v-if="uploadError" class="contract-upload__error">{{ uploadError }}</small>
              <small v-else-if="!selectedContractFile">拖放到此处，或选择 PDF、DOCX、TXT、MD，最大 10MB</small>
            </span>
            <span class="contract-upload__actions">
              <el-button size="small" :loading="loading.upload" @click="openContractFilePicker"><el-icon><UploadFilled /></el-icon>{{ selectedContractFile ? '替换文件' : '选择文件' }}</el-button>
              <el-button v-if="selectedContractFile" circle size="small" title="移除任务文件" aria-label="移除任务文件" @click="clearContractFile"><el-icon><Delete /></el-icon></el-button>
            </span>
          </div>
        </div>
        <div class="input-pane definition-pane">
          <span class="pane-heading">任务定义</span>
          <label class="ctrl-label">任务名称</label>
          <el-input v-model="taskName" placeholder="为本次任务命名" />
          <div class="ctrl-row">
            <label class="ctrl-label">任务目标</label>
            <el-input class="intent-textarea" v-model="userIntent" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" placeholder="描述目标、范围和成功标准" />
          </div>
          <label class="ctrl-label">执行约束</label>
          <el-input v-model="constraintsText" placeholder="使用逗号分隔，例如：两周内完成、控制预算" />
          <label class="ctrl-label">预期交付物</label>
          <el-input v-model="expectedArtifactsText" placeholder="使用逗号分隔，例如：实施方案、风险清单" />
        </div>
      </div>
      <section class="plugin-selector" aria-label="专业能力扩展">
        <header><div><strong>专业能力扩展</strong><small>Native Core 始终启用；每个 Run 最多叠加一个专业能力包</small></div></header>
        <div class="plugin-options">
          <button type="button" class="plugin-card native-card" :class="{ selected: !draft.enabledPluginIds.length }" :aria-pressed="!draft.enabledPluginIds.length" :disabled="scopeLocked" @click="clearPlugins">
            <span class="plugin-card__top"><strong>Native Core · 始终启用</strong><span class="plugin-card__state">{{ !draft.enabledPluginIds.length ? '已启用' : '基础' }}</span></span>
            <small>{{ draft.enabledPluginIds.length ? '作为专业能力包的运行基础' : '当前仅使用通用规划、分析与交付能力' }}</small>
            <code>不叠加专业能力包</code>
          </button>
          <button v-for="plugin in installedPlugins" :key="plugin.pluginId" type="button" class="plugin-card" :class="{ selected: draft.enabledPluginIds[0] === plugin.pluginId }" :aria-pressed="draft.enabledPluginIds[0] === plugin.pluginId" :disabled="scopeLocked || !plugin.available" @click="togglePlugin(plugin.pluginId)">
            <span class="plugin-card__top"><strong>{{ plugin.displayName }}</strong><span class="plugin-card__state">{{ draft.enabledPluginIds[0] === plugin.pluginId ? '已启用' : '选择' }}</span></span>
            <small>{{ plugin.description }}</small>
            <code>{{ plugin.pluginId }} · v{{ plugin.version }}</code>
          </button>
        </div>
      </section>
      <PluginExtensionHost :extensions="draftExtensions" :draft="draft" :readonly="scopeLocked" @update:plugin-data="draft.pluginData = $event" />
        </div>
      </Transition>
      <div class="ctrl-options">
        <div v-show="inputPanelExpanded" class="primary-options">
          <div class="primary-config">
            <span class="ctrl-label">规划方式</span>
            <div class="segmented-control" role="radiogroup" aria-label="规划方式">
              <button type="button" role="radio" class="segment-option" :aria-checked="planningMode === 'dynamic'" :class="{ selected: planningMode === 'dynamic' }" @click="planningMode = 'dynamic'">动态规划</button>
              <button type="button" role="radio" class="segment-option" :aria-checked="planningMode === 'template_preferred'" :class="{ selected: planningMode === 'template_preferred' }" @click="planningMode = 'template_preferred'">模板优先</button>
            </div>
          </div>
          <div class="primary-config">
            <span class="ctrl-label">审核方式</span>
            <div class="segmented-control" role="radiogroup" aria-label="审核方式">
              <button type="button" role="radio" class="segment-option" :aria-checked="draft.reviewMode === 'auto'" :class="{ selected: draft.reviewMode === 'auto' }" @click="draft.reviewMode = 'auto'">自动</button>
              <button type="button" role="radio" class="segment-option" :aria-checked="draft.reviewMode === 'human_in_loop'" :class="{ selected: draft.reviewMode === 'human_in_loop' }" @click="draft.reviewMode = 'human_in_loop'">人工介入</button>
            </div>
          </div>
          <div class="advanced-settings-popover">
            <button ref="advancedSettingsToggle" class="advanced-toggle" type="button" :aria-expanded="advancedSettingsExpanded" @click="toggleAdvancedSettings">
              <span class="advanced-toggle__copy"><strong>高级设置</strong><small>{{ advancedSettingsSummary }}</small></span>
              <el-icon><ArrowUp v-if="advancedSettingsExpanded" /><ArrowDown v-else /></el-icon>
            </button>
            <Teleport to="body">
            <div v-if="advancedSettingsExpanded" ref="advancedSettingsElement" class="advanced-settings" :style="{ left: `${advancedSettingsPosition.x}px`, top: `${advancedSettingsPosition.y}px` }">
              <header class="advanced-settings__head">
                <div>
                  <strong>高级运行策略</strong>
                  <small>仅在需要控制推理、规划或调试行为时调整</small>
                </div>
                <div class="advanced-settings__head-actions">
                  <span>{{ advancedSettingsSummary }}</span>
                  <button class="advanced-settings__close" type="button" title="关闭高级设置" aria-label="关闭高级设置" @click="closeAdvancedSettings">
                    <el-icon><Close /></el-icon>
                  </button>
                </div>
              </header>
              <section class="advanced-presets" aria-label="高级设置快速方案">
                <div class="advanced-presets__intro">
                  <strong>快速方案</strong>
                  <small>一键应用常用的运行组合</small>
                </div>
                <div class="advanced-presets__options">
                  <button type="button" class="advanced-preset" :class="{ selected: advancedPreset === 'fast' }" @click="applyAdvancedPreset('fast')">
                    <strong>快速</strong><small>低耗时 · 稳定规划</small>
                  </button>
                  <button type="button" class="advanced-preset" :class="{ selected: advancedPreset === 'balanced' }" @click="applyAdvancedPreset('balanced')">
                    <strong>均衡</strong><small>标准思考 · 联网检索</small>
                  </button>
                  <button type="button" class="advanced-preset" :class="{ selected: advancedPreset === 'deep' }" @click="applyAdvancedPreset('deep')">
                    <strong>深度</strong><small>深度思考 · 探索规划</small>
                  </button>
                </div>
              </section>
              <div class="advanced-item advanced-item--segmented">
                <div class="advanced-item__heading"><span>思考强度</span><small>影响耗时与推理深度</small></div>
                <div class="segmented-control" role="radiogroup" aria-label="思考强度">
                  <button type="button" role="radio" class="segment-option" :aria-checked="thinkingMode === 'disabled'" :class="{ selected: thinkingMode === 'disabled' }" @click="thinkingMode = 'disabled'">关闭</button>
                  <button type="button" role="radio" class="segment-option" :aria-checked="thinkingMode === 'standard'" :class="{ selected: thinkingMode === 'standard' }" @click="thinkingMode = 'standard'">标准</button>
                  <button type="button" role="radio" class="segment-option" :aria-checked="thinkingMode === 'deep'" :class="{ selected: thinkingMode === 'deep' }" @click="thinkingMode = 'deep'">深度</button>
                </div>
              </div>
              <div class="advanced-item advanced-item--switch">
                <div class="advanced-item__heading"><span>联网检索</span><small>按模型隔离：GLM → 智谱原生 · DeepSeek → Tavily</small></div>
                <button class="settings-switch" type="button" role="switch" :aria-checked="draft.webSearchEnabled" :disabled="isSubmitting" @click="draft.webSearchEnabled = !draft.webSearchEnabled">
                  <span class="settings-switch__track"><span></span></span>
                  <span>{{ draft.webSearchEnabled ? '开启' : '关闭' }}</span>
                </button>
              </div>
              <label class="advanced-item">
                <span class="advanced-item__label">图规划多样性</span>
                <el-select v-model="draft.planningDiversity" aria-label="图规划多样性">
                  <el-option label="稳定（可重复）" value="stable" />
                  <el-option label="均衡（推荐）" value="balanced" />
                  <el-option label="探索（变化更大）" value="exploratory" />
                </el-select>
              </label>
              <label class="advanced-item">
                <span class="advanced-item__label">能力档位</span>
                <el-select v-model="draft.capabilityProfile" aria-label="能力档位">
                  <el-option label="自动" value="auto" />
                  <el-option label="标准" value="standard" />
                  <el-option label="完整" value="full" />
                </el-select>
              </label>
              <label class="advanced-item">
                <span class="advanced-item__label">随机种子（可选）</span>
                <el-input-number v-model="draft.planningSeed" :min="0" :max="2147483647" :controls="false" placeholder="留空则自动生成" />
              </label>
              <label v-if="activeRunId && draft.planningDiversity !== 'stable'" class="advanced-item">
                <span class="advanced-item__label">规划变体</span>
                <el-button @click="rerunWithNewPlanningSeed">换一种规划</el-button>
              </label>
              <div class="advanced-item advanced-item--switch">
                <div class="advanced-item__heading"><span>调试轨迹</span><small>记录更详细的执行诊断</small></div>
                <button class="settings-switch" type="button" role="switch" :aria-checked="debugTraceEnabled" @click="debugTraceEnabled = !debugTraceEnabled">
                  <span class="settings-switch__track"><span></span></span>
                  <span>{{ debugTraceEnabled ? '开启' : '关闭' }}</span>
                </button>
              </div>
              <div class="advanced-item advanced-item--switch">
                <div class="advanced-item__heading"><span>通信血缘</span><small>保留低熵通信的来源与去向记录</small></div>
                <button class="settings-switch" type="button" role="switch" :aria-checked="lowEntropyOptions.includes('trace_provenance')" @click="lowEntropyOptions = lowEntropyOptions.includes('trace_provenance') ? [] : ['trace_provenance']">
                  <span class="settings-switch__track"><span></span></span>
                  <span>{{ lowEntropyOptions.includes('trace_provenance') ? '记录' : '不记录' }}</span>
                </button>
              </div>
            </div>
            </Teleport>
          </div>
        </div>
        <el-button
          class="main-action"
          :class="`main-action--${mainAction.action}`"
          :type="mainAction.type"
          :loading="mainAction.loading"
          :disabled="mainAction.disabled"
          @click="handleMainAction"
        >
          <span class="main-action__label">{{ mainAction.label }}</span>
          <el-icon v-if="!mainAction.loading" class="main-action__arrow" aria-hidden="true"><ArrowRight /></el-icon>
        </el-button>
      </div>
    </section>

    </div>
    <div v-if="!inputPanelExpanded" class="acg-config-thumbnail" aria-label="已折叠的任务配置">
      <button
        class="input-panel-toggle"
        type="button"
        title="展开任务配置"
        aria-label="展开任务配置"
        aria-expanded="false"
        @click="inputPanelExpanded = true"
      >
        <el-icon><ArrowDown /></el-icon>
      </button>
      <div class="acg-overview-thumbnail__summary">
        <el-icon><Document /></el-icon>
        <strong>{{ taskName || editorTitle || '未命名 ACG 任务' }}</strong>
        <span>任务配置已折叠 · {{ planningModeSummary }} · {{ activePluginSummary }}</span>
      </div>
      <el-button
        class="main-action"
        :class="`main-action--${mainAction.action}`"
        :type="mainAction.type"
        :loading="mainAction.loading"
        :disabled="mainAction.disabled"
        @click="handleMainAction"
      >
        <span class="main-action__label">{{ mainAction.label }}</span>
        <el-icon v-if="!mainAction.loading" class="main-action__arrow" aria-hidden="true"><ArrowRight /></el-icon>
      </el-button>
    </div>
    </section>

    <!-- 运行概览栏目：保留进度、资源和执行合同的业务组件，只切换展示状态。 -->
    <section
      v-if="activeRunId || isSubmitting || progressTracker.progress.value || progressTracker.syncError.value"
      class="acg-runtime-section"
      aria-label="ACG 运行概览"
    >
      <div v-show="runtimeOverviewExpanded" class="acg-runtime-expanded">
        <button
          class="runtime-panel-toggle"
          type="button"
          title="收起运行概览"
          aria-label="收起运行概览"
          aria-expanded="true"
          @click="runtimeOverviewExpanded = false"
        >
          <el-icon><ArrowUp /></el-icon>
        </button>
        <section class="editor-runtime-strip">
          <WorkflowProgressBar
            v-if="isSubmitting || progressTracker.progress.value || progressTracker.syncError.value"
            :progress="progressTracker.progress.value"
            :loading="isSubmitting || progressTracker.isLoading.value"
            :sync-error="progressTracker.syncError.value"
          />
          <RunResourceStrip
            v-if="activeRunId"
            :usage="resourceUsage"
            @open="openResourceInspector"
          />
          <AcgExecutionContractBar
            v-if="acgView"
            :view="acgView"
            @open-run="openRelatedRun"
          />
        </section>
      </div>
      <div v-if="!runtimeOverviewExpanded" class="acg-runtime-thumbnail" aria-label="已折叠的运行概览">
        <button
          class="runtime-panel-toggle"
          type="button"
          title="展开运行概览"
          aria-label="展开运行概览"
          aria-expanded="false"
          @click="runtimeOverviewExpanded = true"
        >
          <el-icon><ArrowDown /></el-icon>
        </button>
        <span class="acg-overview-thumbnail__dot" :class="{ 'is-running': isSubmitting || progressTracker.progress.value?.status === 'running' }" aria-hidden="true"></span>
        <strong>ACG 执行状态</strong>
        <span class="acg-runtime-thumbnail__message">{{ progressTracker.progress.value?.message || activeRun?.lifecycleMessage || '运行概览已折叠' }}</span>
        <span v-if="progressTracker.progress.value?.percent != null" class="acg-overview-thumbnail__percent">
          {{ progressTracker.progress.value.percent.toFixed(0) }}%
        </span>
      </div>
    </section>

    <el-drawer
      id="acg-resource-drawer"
      v-model="resourceDrawerOpen"
      class="resource-drawer"
      direction="rtl"
      size="520px"
      :with-header="true"
      :destroy-on-close="false"
      aria-label="资源详情"
    >
      <template #header>
        <div class="resource-drawer__header">
          <div>
            <strong>资源详情</strong>
            <span>当前 Run 的 API、用量与上下文观测</span>
          </div>
          <el-tag v-if="activeRun" effect="plain" type="info">{{ activeRun.status }}</el-tag>
        </div>
      </template>
      <div class="resource-drawer__body">
        <AcgResourceInspector
          v-if="activeRunId"
          :run-id="activeRunId"
          :usage="resourceUsage"
        />
      </div>
    </el-drawer>

    <p v-if="startError" class="run-error" role="alert">{{ startError }}</p>

    <WorkflowReviewPanel
      v-if="reviewPending"
      :run-id="activeRunId"
      :progress="progressTracker.progress.value"
      :run="activeRun"
      @reviewed="handleAcgReviewed"
      @conflict="handleAcgReviewConflict"
    />

    <!-- 主区：拓扑编辑器 + 独立垂直分割运行面板 -->
    <WorkbenchVerticalSplit v-if="acgView" class="acg-editor-body">
      <template #graph>
        <div class="acg-editor-surface">
          <AcgTopologyGraph
            :key="topologyGraphKey"
            class="acg-editor-graph"
            :blueprint="acgView.acgBlueprint"
            :completed-step-ids="acgView.completedStepIds"
            :step-states="acgView.stepStates"
            :workbench="true"
          />
        </div>
      </template>

      <template #bottom="{ collapsed, setCollapsed }">
        <WorkbenchBottomPanel
          :model-value="collapsed"
          :tabs="bottomPanelTabs"
          @update:model-value="setCollapsed"
        >
      <template #tab-result>
        <div class="bottom-panel-result">
          <template v-if="artifactRenderers.length">
            <component
              v-for="renderer in artifactRenderers"
              :key="renderer.pluginId"
              :is="renderer.component"
              :deliverables="acgView.deliverables"
              :final-report="acgView.finalReport"
            />
          </template>
          <GenericArtifactPanel
            v-else
            :step-outputs="acgView.stepOutputs || acgView.deliverables"
            :final-artifacts="acgView.finalArtifacts || []"
            :final-report="acgView.finalReport"
            :status="acgView.status"
            :step-states="acgView.stepStates"
          />
        </div>
      </template>

      <template #tab-trace>
        <div class="bottom-panel-trace">
          <AgentOsRunSummaryCard
            v-if="activeRunId"
            class="run-summary-card"
            :progress="progressTracker.progress.value"
            :run="activeRun"
            :view="acgView"
            :events="acgAuditEvents"
          />
          <section v-if="scheduleBatches.length" class="schedule-strip" aria-label="就绪集调度轨迹">
            <h4>就绪集调度轨迹（动态拓扑）</h4>
            <div class="batch-row">
              <div v-for="b in scheduleBatches" :key="b.id" class="batch">
                <span class="batch-idx">第{{ b.round }}轮</span>
                <span v-for="sid in b.nodes" :key="sid" class="batch-node">{{ sid }}</span>
              </div>
            </div>
          </section>
          <RuntimeAuditTimeline
            :events="acgAuditEvents"
            :patch-refs="[]"
          />
        </div>
      </template>

      <template #tab-events>
        <div v-if="acgAuditEvents.length" class="bottom-panel-event-list">
          <article v-for="(event, index) in acgAuditEvents" :key="event.eventId || `${event.eventType}-${event.createdAt || index}`" class="bottom-panel-event-row">
            <strong>{{ event.eventType }}</strong>
            <span>{{ event.observation || '运行事件已记录' }}</span>
            <time v-if="event.createdAt">{{ event.createdAt }}</time>
          </article>
        </div>
        <div v-else class="bottom-panel-empty">暂无事件数据</div>
      </template>

      <template #tab-tools>
        <div class="bottom-panel-empty">暂无工具调用数据</div>
      </template>
        </WorkbenchBottomPanel>
      </template>
    </WorkbenchVerticalSplit>

    <div v-else class="task-brief">
      <strong>ACG 动态智能体长程任务</strong>
    </div>
        </div>
      </template>

      <template #right>
        <div id="acg-run-details" class="acg-inspector-pane" aria-label="ACG 运行详情">
          <div class="acg-inspector-pane__content">
            <AcgOperationalInspector
              v-if="acgView"
              :view="acgView"
              :audit-events="acgAuditEvents"
              :patch-refs="[]"
              :runtime-store="runtimeEventStore"
              @export-audit="exportAudit"
            />
            <section v-if="acgView" class="side-provenance ui-surface" aria-label="数据血缘与通信轨迹">
              <AcgProvenancePanel
                :consumptions="acgView.provenance.consumptions"
                :interactions="acgView.interactions"
                :recovery-trace="acgView.recoveryTrace"
                :contract-violations="acgView.contractViolations"
                @export-json="exportAudit('json')"
                @export-csv="exportAudit('csv')"
              />
            </section>
          </div>
        </div>
      </template>
    </WorkbenchLayout>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch, type DeepReadonly } from 'vue'
import axios from 'axios'
import { ArrowDown, ArrowRight, ArrowUp, Close, Cpu, Delete, Document, Monitor, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useRoute, useRouter } from 'vue-router'
import {
  workflowApi,
  type AcgView,
  type WorkflowRun,
  type WorkflowProgress,
  type RunResourceUsage,
  type WorkflowRerunRequest
} from '@/services/api/workflow'
import AcgTopologyGraph from '@/components/agentos/AcgTopologyGraph.vue'
import AcgExecutionContractBar from '@/components/agentos/AcgExecutionContractBar.vue'
import AcgOperationalInspector from '@/components/agentos/AcgOperationalInspector.vue'
import AcgProvenancePanel from '@/components/agentos/AcgProvenancePanel.vue'
import AcgRunManager from '@/components/agentos/AcgRunManager.vue'
import WorkflowProgressBar from '@/components/agentos/WorkflowProgressBar.vue'
import { chooseFailedRunRetryMode, type FailedRunRetryMode } from '@/utils/retryModeChoice'
import WorkflowReviewPanel from '@/components/agentos/WorkflowReviewPanel.vue'
import { getRunRuntimeStore, type RunRuntimeStore } from '@/workbench/runtime/runtimeEvents'
import AgentOsRunSummaryCard from '@/components/agentos/AgentOsRunSummaryCard.vue'
import RunResourceStrip from '@/components/agentos/RunResourceStrip.vue'
import AcgResourceInspector from '@/components/agentos/AcgResourceInspector.vue'
import RuntimeAuditTimeline from '@/components/agentos/RuntimeAuditTimeline.vue'
import WorkbenchBottomPanel from '@/components/workbench/WorkbenchBottomPanel.vue'
import WorkbenchVerticalSplit from '@/components/workbench/WorkbenchVerticalSplit.vue'
import { useWorkflowProgress } from '@/composables/useWorkflowProgress'
import { useWorkflowRunsStore } from '@/stores/workflowRuns'
import { createMissionLaunchAttempt } from '@/features/mission/launchAttempt'
import { legacyAcgLaunchCommand } from '@/features/mission/command'
import type { ThinkingMode } from '@/config/modelSettings'
import { fileApi } from '@/services/api/file'
import { buildAcgAuditCsv, buildAcgAuditExport } from '@/utils/acgAuditExport'
import { isWorkflowReviewPending } from '@/utils/workflowReviewState'
import { resolveAcgTaskTitle, resolveAcgTaskTitleAutoUpdate } from '@/utils/acgTaskTitle'
import { notifyAcgRunInvalidated } from '@/utils/acgHistoryFilter'
import PluginExtensionHost from '@/features/acg/PluginExtensionHost.vue'
import GenericArtifactPanel from '@/features/acg/GenericArtifactPanel.vue'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import {
  buildWorkbenchStartRequest,
  createNativeWorkbenchDraft,
  restoreWorkbenchDraft,
  type WorkbenchDraft
} from '@/features/acg/workbench'
import { pluginUiExtensions } from '@/plugins'

const draft = reactive<WorkbenchDraft>(createNativeWorkbenchDraft())
const acgMainPane = ref<HTMLElement | null>(null)
const taskName = computed({ get: () => draft.title, set: value => { draft.title = value } })
const contractText = computed({ get: () => draft.materialText, set: value => { draft.materialText = value } })
const userIntent = computed({ get: () => draft.taskGoal, set: value => { draft.taskGoal = value } })
const planningMode = computed({ get: () => draft.planningMode, set: value => { draft.planningMode = value } })
const thinkingMode = computed<ThinkingMode>({ get: () => draft.thinkingMode, set: value => { draft.thinkingMode = value } })
const constraintsText = computed({
  get: () => draft.constraints.join('，'),
  set: value => { draft.constraints = value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean) }
})
const expectedArtifactsText = computed({
  get: () => draft.expectedArtifacts.join('，'),
  set: value => { draft.expectedArtifacts = value.split(/[,，\n]/).map(item => item.trim()).filter(Boolean) }
})
const advancedSettingsExpanded = ref(false)
const advancedSettingsToggle = ref<HTMLButtonElement | null>(null)
const advancedSettingsElement = ref<HTMLElement | null>(null)
const advancedSettingsPosition = reactive({ x: 0, y: 0 })
const debugTraceEnabled = ref(false)
const lowEntropyOptions = ref(['trace_provenance'])
const autoGeneratedTaskName = ref('')

const positionAdvancedSettings = async () => {
  await nextTick()
  const trigger = advancedSettingsToggle.value
  const panel = advancedSettingsElement.value
  if (!trigger || !panel) return
  const rect = trigger.getBoundingClientRect()
  const gutter = 16
  const panelWidth = panel.offsetWidth
  const panelHeight = panel.offsetHeight
  advancedSettingsPosition.x = Math.max(gutter, Math.min(rect.right - panelWidth, window.innerWidth - panelWidth - gutter))
  advancedSettingsPosition.y = Math.max(gutter, Math.min(rect.bottom + 10, window.innerHeight - panelHeight - gutter))
}

const toggleAdvancedSettings = async () => {
  advancedSettingsExpanded.value = !advancedSettingsExpanded.value
  if (advancedSettingsExpanded.value) await positionAdvancedSettings()
}

const closeAdvancedSettings = () => {
  advancedSettingsExpanded.value = false
}

const applyAdvancedPreset = (preset: AdvancedPreset) => {
  draft.capabilityProfile = preset === 'fast' ? 'standard' : preset === 'deep' ? 'full' : 'auto'
  if (preset === 'fast') {
    thinkingMode.value = 'disabled'
    draft.webSearchEnabled = false
    draft.planningDiversity = 'stable'
    return
  }
  if (preset === 'balanced') {
    thinkingMode.value = 'standard'
    draft.webSearchEnabled = true
    draft.planningDiversity = 'balanced'
    return
  }
  thinkingMode.value = 'deep'
  draft.webSearchEnabled = true
  draft.planningDiversity = 'exploratory'
}

const handleAdvancedSettingsViewportChange = () => {
  if (advancedSettingsExpanded.value) void positionAdvancedSettings()
}

const handleAdvancedSettingsDismiss = (event: PointerEvent) => {
  const target = event.target as Node | null
  if (!target) return
  if (advancedSettingsElement.value?.contains(target) || advancedSettingsToggle.value?.contains(target)) return
  if (target instanceof Element && target.closest('.el-popper')) return
  closeAdvancedSettings()
}

const handleAdvancedSettingsKeydown = (event: KeyboardEvent) => {
  if (event.key !== 'Escape' || !advancedSettingsExpanded.value) return
  closeAdvancedSettings()
  nextTick(() => advancedSettingsToggle.value?.focus())
}

watch(userIntent, value => {
  if (activeRunId.value) return
  const update = resolveAcgTaskTitleAutoUpdate({
    currentTitle: taskName.value,
    previousAutoTitle: autoGeneratedTaskName.value,
    taskGoal: value,
    defaultTitle: createNativeWorkbenchDraft().title
  })
  taskName.value = update.title
  autoGeneratedTaskName.value = update.autoTitle
})

const acgView = ref<AcgView | null>(null)
const activeRun = ref<WorkflowRun | null>(null)
const resourceUsage = ref<RunResourceUsage | null>(null)
const resourceDrawerOpen = ref(false)
const openResourceInspector = () => {
  resourceDrawerOpen.value = true
}
const acgAuditEvents = computed(() => {
  const events = [
    ...(acgView.value?.recoveryTrace || []),
    ...(acgView.value?.scheduleTrace || []),
    ...(acgView.value?.contractViolations || [])
  ]
  const seen = new Set<string>()
  return events.filter((event, index) => {
    const key = event.eventId || `${event.eventType}:${event.createdAt || index}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
})
const bottomPanelTabs = computed(() => [
  { id: 'result', label: '结果' },
  { id: 'trace', label: '运行轨迹', count: acgAuditEvents.value.length },
  { id: 'events', label: '事件', count: acgAuditEvents.value.length },
  { id: 'tools', label: '工具调用' }
])
const editorTitle = computed(() => activeRun.value?.title || (activeRunId.value
  ? (taskName.value || '当前 ACG 任务')
  : 'ACG 动态群体智能引擎'))
const editorMetadata = computed(() => [
  planningModeSummary.value,
  draft.webSearchEnabled ? '联网' : '仅本地',
  ({ stable: '稳定', balanced: '均衡', exploratory: '探索' } as const)[draft.planningDiversity],
  activePluginSummary.value
].join(' · '))
const taskMaterialLength = computed(() => contractText.value.trim().length)
const loading = reactive({ upload: false })
const isSubmitting = ref(false)
const isAcgLoading = ref(false)
const startError = ref<string | null>(null)
const route = useRoute()
const router = useRouter()
const workflowRunsStore = useWorkflowRunsStore()
const activeRunId = ref('')
const runtimeEventStore = ref<RunRuntimeStore | null>(null)
const reconnectRuntimeEvents = (runId: string) => {
  runtimeEventStore.value = getRunRuntimeStore(runId || null)
}
watch(activeRunId, runId => reconnectRuntimeEvents(runId))
type AcgEditorTab = {
  id: string
  runId?: string
  title: string
  status?: string
}

const DRAFT_EDITOR_TAB_ID = 'acg-editor-draft'
const openedEditorTabs = ref<AcgEditorTab[]>([])
const draftEditorTabOpen = ref(false)
const editorStatusLabels: Record<string, string> = {
  completed: '已完成', failed: '失败', running: '执行中',
  waiting_review: '待审核', cancelled: '已取消', retrying: '重试中',
  planning: '规划中', pending: '待启动'
}
const activeEditorTabId = computed(() => activeRunId.value || DRAFT_EDITOR_TAB_ID)
const visibleEditorTabs = computed<AcgEditorTab[]>(() => {
  const tabs = openedEditorTabs.value.slice()
  if (draftEditorTabOpen.value || !tabs.length) {
    tabs.unshift({ id: DRAFT_EDITOR_TAB_ID, title: tabs.length ? '新建 ACG 任务' : 'ACG 动态群体智能引擎' })
  }
  return tabs
})
const editorTabStatusLabel = (status?: string) => status ? (editorStatusLabels[status] || status) : ''
const editorTabTitle = (run: WorkflowRun | null | undefined, fallback = '') => {
  if (run) return resolveAcgTaskTitle(run)
  return fallback || '当前 ACG 任务'
}
const ensureEditorTab = (runId: string, title?: string, status?: string) => {
  if (!runId) return
  const existing = openedEditorTabs.value.find(tab => tab.id === runId)
  if (existing) {
    if (title) existing.title = title
    if (status) existing.status = status
    return
  }
  openedEditorTabs.value.push({
    id: runId,
    runId,
    title: title || `任务 ${runId.slice(0, 10)}`,
    status
  })
}
const updateEditorTabFromRun = (run: WorkflowRun) => {
  ensureEditorTab(run.runId, editorTabTitle(run), run.status)
}
const updateEditorTabStatus = (runId: string, status?: string) => {
  if (!runId || !status) return
  const tab = openedEditorTabs.value.find(item => item.id === runId)
  if (tab) tab.status = status
}
const removeEditorTab = (tabId: string) => {
  openedEditorTabs.value = openedEditorTabs.value.filter(tab => tab.id !== tabId)
}
const installedPlugins = computed(() => pluginUiExtensions.all().map(extension => ({
  pluginId: extension.pluginId,
  displayName: extension.displayName,
  description: '随前端扩展与应用 Pack 一同部署',
  version: 'workspace',
  available: true
})))
const scopeLocked = computed(() => Boolean(activeRunId.value))
const draftExtensions = computed(() => pluginUiExtensions.resolve(draft.enabledPluginIds))
const activePluginIds = computed(() => draft.enabledPluginIds)
const activeExtensions = computed(() => pluginUiExtensions.resolve(activePluginIds.value))
const artifactRenderers = computed(() => activeExtensions.value
  .filter(item => item.artifactRenderer)
  .map(item => ({ pluginId: item.pluginId, component: item.artifactRenderer! })))
const activePluginSummary = computed(() => activePluginIds.value.length
  ? activePluginIds.value.join('、')
  : 'Native only')
const inputPanelExpanded = ref(true)
const runtimeOverviewExpanded = ref(true)
const topologyGraphKey = ref(0)
const inputPanelCompact = ref(false)
const loadedRunId = ref('')
const contractFileInput = ref<HTMLInputElement | null>(null)
const uploadDragging = ref(false)
type SelectedMaterial = { originalFilename: string; size: number; textLength: number; extractedText: string }
const selectedContractFile = ref<SelectedMaterial | null>(null)
const uploadState = ref<'idle' | 'uploading' | 'parsing' | 'ready' | 'error'>('idle')
const uploadError = ref('')

const resetDraftContent = () => {
  Object.assign(draft, createNativeWorkbenchDraft())
  autoGeneratedTaskName.value = ''
  selectedContractFile.value = null
  uploadState.value = 'idle'
  uploadError.value = ''
}

const applyExtensionDefaults = (pluginId: string) => {
  const defaults = pluginUiExtensions.get(pluginId)?.createDefaults?.()
  if (!defaults) return
  const nativeDefaults = createNativeWorkbenchDraft()
  if (defaults.title && draft.title === nativeDefaults.title) draft.title = defaults.title
  if (defaults.taskGoal && draft.taskGoal === nativeDefaults.taskGoal) draft.taskGoal = defaults.taskGoal
  if (defaults.expectedArtifacts && draft.expectedArtifacts.join('\u0000') === nativeDefaults.expectedArtifacts.join('\u0000')) {
    draft.expectedArtifacts = [...defaults.expectedArtifacts]
  }
  if (defaults.reviewMode) draft.reviewMode = defaults.reviewMode
  if (defaults.capabilityProfile && draft.capabilityProfile === nativeDefaults.capabilityProfile) draft.capabilityProfile = defaults.capabilityProfile
  if (defaults.planningDiversity && draft.planningDiversity === nativeDefaults.planningDiversity) draft.planningDiversity = defaults.planningDiversity
  if (typeof defaults.webSearchEnabled === 'boolean' && draft.webSearchEnabled === nativeDefaults.webSearchEnabled) draft.webSearchEnabled = defaults.webSearchEnabled
  if (defaults.thinkingMode && draft.thinkingMode === nativeDefaults.thinkingMode) draft.thinkingMode = defaults.thinkingMode
  if (defaults.reasoningEffort && !draft.reasoningEffort) draft.reasoningEffort = defaults.reasoningEffort
  if (defaults.pluginData) draft.pluginData = { ...draft.pluginData, ...defaults.pluginData }
}

const removeExtensionDefaults = (pluginId: string) => {
  const defaults = pluginUiExtensions.get(pluginId)?.createDefaults?.()
  const nativeDefaults = createNativeWorkbenchDraft()
  if (defaults?.title && draft.title === defaults.title) draft.title = nativeDefaults.title
  if (defaults?.taskGoal && draft.taskGoal === defaults.taskGoal) draft.taskGoal = nativeDefaults.taskGoal
  if (defaults?.expectedArtifacts && draft.expectedArtifacts.join('\u0000') === defaults.expectedArtifacts.join('\u0000')) {
    draft.expectedArtifacts = [...nativeDefaults.expectedArtifacts]
  }
}

const togglePlugin = (pluginId: string) => {
  if (scopeLocked.value) return
  if (draft.enabledPluginIds[0] === pluginId) {
    clearPlugins()
    return
  }
  for (const selectedPluginId of draft.enabledPluginIds) removeExtensionDefaults(selectedPluginId)
  draft.enabledPluginIds = [pluginId]
  draft.pluginData = {}
  draft.reviewMode = 'auto'
  applyExtensionDefaults(pluginId)
}

const clearPlugins = () => {
  if (scopeLocked.value) return
  for (const pluginId of draft.enabledPluginIds) removeExtensionDefaults(pluginId)
  draft.enabledPluginIds = []
  draft.pluginData = {}
  draft.reviewMode = 'auto'
}

const progressTracker = useWorkflowProgress({
  intervalMs: 2000,
  onProgressChanged: value => workflowRunsStore.updateObservedState(
    value.runId,
    value.status,
    value.phase,
    value.updatedAt
  ),
  onTerminal: handleTerminal
})
const displayedMissionId = computed(() =>
  activeRun.value?.missionId || progressTracker.progress.value?.missionId || ''
)
const reviewPending = computed(() => Boolean(
  activeRunId.value && isWorkflowReviewPending(progressTracker.progress.value, activeRun.value)
))

const CONTRACT_FILE_MAX_SIZE = 10 * 1024 * 1024
const CONTRACT_FILE_EXTENSIONS = ['pdf', 'docx', 'txt', 'md']

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

const openContractFilePicker = () => {
  if (!loading.upload) contractFileInput.value?.click()
}

const validateContractFile = (file: File) => {
  const extension = file.name.split('.').pop()?.toLowerCase() || ''
  if (!CONTRACT_FILE_EXTENSIONS.includes(extension)) {
    throw new Error('仅支持 PDF、DOCX、TXT、MD 格式')
  }
  if (file.size <= 0) throw new Error('文件内容为空')
  if (file.size > CONTRACT_FILE_MAX_SIZE) throw new Error('文件不能超过 10MB')
}

const processContractFile = async (file: File) => {
  if (loading.upload) return

  try {
    validateContractFile(file)
    loading.upload = true
    uploadState.value = 'uploading'
    uploadError.value = ''
    uploadState.value = 'parsing'
    const result = await fileApi.extractDocumentText(file)
    const extractedText = (result.text || result.content || '').trim()
    if (!extractedText) throw new Error('未能从文件中提取到文本，请确认文档包含可复制文字')

    contractText.value = extractedText
    draft.materialIds = []
    selectedContractFile.value = {
      originalFilename: result.filename || file.name,
      size: file.size,
      textLength: extractedText.length,
      extractedText
    }
    uploadState.value = 'ready'
    ElMessage.success(`已载入任务文件：${file.name}`)
  } catch (error: any) {
    const message = materialErrorMessage(error)
    uploadState.value = 'error'
    uploadError.value = message
    ElMessage.error(message)
  } finally {
    loading.upload = false
    uploadDragging.value = false
    if (contractFileInput.value) contractFileInput.value.value = ''
  }
}

const handleContractFileSelection = (event: Event) => {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) void processContractFile(file)
}

const handleContractDrop = (event: DragEvent) => {
  uploadDragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) void processContractFile(file)
}

const clearContractFile = () => {
  const selected = selectedContractFile.value
  if (selected?.extractedText && contractText.value === selected.extractedText) contractText.value = ''
  draft.materialIds = []
  selectedContractFile.value = null
  uploadState.value = 'idle'
  uploadError.value = ''
  if (contractFileInput.value) contractFileInput.value.value = ''
}

const materialErrorMessage = (error: any): string => {
  const data = error?.response?.data
  const detail = typeof data?.detail === 'string' ? data.detail : data?.detail?.message
  return data?.message || detail || error?.message || '任务文件上传失败'
}

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    completed: '已完成', failed: '失败', running: '执行中',
    waiting_review: '待审核', cancelled: '已取消', retrying: '重试中', planning: '规划中', pending: '待启动'
  }
  const status = progressTracker.progress.value?.status || acgView.value?.status
  return status ? (map[status] || status) : '准备中'
})
const effectiveStatus = computed(() => progressTracker.progress.value?.status || acgView.value?.status || '')
const effectivePhase = computed(() => progressTracker.progress.value?.phase || '')
const planningModeSummary = computed(() => ({
  template_preferred: '模板优先',
  dynamic: '动态规划'
})[planningMode.value])
const thinkingModeSummary = computed(() => ({ disabled: '关闭', standard: '标准', deep: '深度' })[thinkingMode.value])
type AdvancedPreset = 'fast' | 'balanced' | 'deep'
const advancedPreset = computed<AdvancedPreset | 'custom'>(() => {
  if (thinkingMode.value === 'disabled' && !draft.webSearchEnabled && draft.planningDiversity === 'stable') return 'fast'
  if (thinkingMode.value === 'standard' && draft.webSearchEnabled && draft.planningDiversity === 'balanced') return 'balanced'
  if (thinkingMode.value === 'deep' && draft.webSearchEnabled && draft.planningDiversity === 'exploratory') return 'deep'
  return 'custom'
})
const advancedSettingsSummary = computed(() => `${thinkingModeSummary.value}思考 · ${draft.webSearchEnabled ? '联网' : '仅本地'} · ${({
  stable: '稳定',
  balanced: '均衡',
  exploratory: '探索'
} as const)[draft.planningDiversity]}规划`)
const mainAction = computed<{
  action: 'start' | 'planning' | 'view' | 'review' | 'rerun' | 'retry' | 'resume'
  label: string
  type: 'primary' | 'warning' | 'danger' | 'info'
  loading: boolean
  disabled: boolean
}>(() => {
  const status = effectiveStatus.value
  const phase = effectivePhase.value
  if (isSubmitting.value || (activeRunId.value && ['understanding', 'planning', 'graph_building'].includes(phase))) {
    return { action: 'planning', label: '正在生成编排', type: 'info', loading: true, disabled: true }
  }
  if (loading.upload) return { action: 'planning', label: '正在解析文件', type: 'info', loading: true, disabled: true }
  if (!activeRunId.value) return { action: 'start', label: '启动 ACG', type: 'primary', loading: false, disabled: false }
  if (status === 'waiting_review' || phase === 'review') return { action: 'review', label: '进入人工审核', type: 'warning', loading: false, disabled: false }
  if (status === 'completed' || phase === 'completed') return { action: 'rerun', label: '基于当前配置重新运行', type: 'primary', loading: false, disabled: false }
  if (status === 'failed' || phase === 'failed') return { action: 'resume', label: '从失败处继续', type: 'danger', loading: false, disabled: false }
  if (status === 'cancelled' || phase === 'cancelled') return { action: 'retry', label: '重新运行', type: 'primary', loading: false, disabled: false }
  if (status === 'pending' || status === 'planning') return { action: 'planning', label: '正在生成编排', type: 'info', loading: true, disabled: true }
  return { action: 'view', label: '查看运行', type: 'primary', loading: false, disabled: false }
})
// 从调度 trace 还原"每轮就绪集批次"，可视化并行调度
const scheduleBatches = computed(() => {
  const events = acgView.value?.scheduleTrace || []
  const batches = new Map<string, { id: string; round: number; nodes: string[] }>()
  for (const e of events) {
    const batch = (e.payload?.batch as string[]) || (e.stepId ? [e.stepId] : [])
    const round = Number(e.payload?.round || batches.size + 1)
    const id = String(e.payload?.batchId || `${round}:${e.eventId}`)
    if (batch.length && !batches.has(id)) {
      batches.set(id, { id, round, nodes: batch })
    }
  }
  return Array.from(batches.values()).sort((a, b) => a.round - b.round)
})

// 规划/建图早期阶段同样持续刷新：拓扑、资源横幅与运行详情从任务一开始就有内容。
const ACTIVE_TOPOLOGY_PHASES = new Set([
    'understanding', 'planning', 'graph_building', 'executing', 'recovery', 'review'
])
const TOPOLOGY_REFRESH_MS = 1200
let topologyController: AbortController | null = null
let topologyTimer: ReturnType<typeof setTimeout> | null = null
let topologyGeneration = 0
let lastTopologyRefreshAt = 0
let lastTopologyMarker: string | null = null
let submitController: AbortController | null = null
let inputCollapseTimer: ReturnType<typeof setTimeout> | null = null
let inputPanelCompactTimer: ReturnType<typeof setTimeout> | null = null
let topologyGraphRefreshTimer: ReturnType<typeof setTimeout> | null = null
let terminalNotificationRunId: string | null = null

const clearInputCollapseTimer = () => {
  if (inputCollapseTimer !== null) window.clearTimeout(inputCollapseTimer)
  inputCollapseTimer = null
}

const clearInputPanelCompactTimer = () => {
  if (inputPanelCompactTimer !== null) window.clearTimeout(inputPanelCompactTimer)
  inputPanelCompactTimer = null
}

const clearTopologyGraphRefreshTimer = () => {
  if (topologyGraphRefreshTimer !== null) window.clearTimeout(topologyGraphRefreshTimer)
  topologyGraphRefreshTimer = null
}

const scheduleTopologyGraphRefresh = () => {
  clearTopologyGraphRefreshTimer()
  // Wait for the task configuration collapse transition to finish, then let
  // vis-network initialize against the settled canvas size and fit once.
  topologyGraphRefreshTimer = window.setTimeout(() => {
    topologyGraphRefreshTimer = null
    topologyGraphKey.value += 1
  }, 420)
}

const topologyMarker = (value: {
  runtimeRevision?: number
  updatedAt?: string | null
  completedSteps?: number
  completedStepIds?: readonly string[]
  activeStepIds?: readonly string[]
  currentStepId?: string | null
  status?: string
  phase?: string | null
}) => JSON.stringify([
  value.runtimeRevision ?? null,
  value.updatedAt ?? null,
  value.completedSteps ?? null,
  [...(value.completedStepIds || [])],
  [...(value.activeStepIds || [])],
  value.currentStepId ?? null,
  value.status ?? null,
  value.phase ?? null
])

const runTopologyMarker = (run: WorkflowRun) => topologyMarker({
  runtimeRevision: run.runtimeRevision,
  updatedAt: run.updatedAt,
  completedSteps: run.completedStepIds?.length,
  completedStepIds: run.completedStepIds,
  activeStepIds: run.activeStepIds,
  currentStepId: run.currentStepId,
  status: run.status,
  phase: run.lifecyclePhase
})

const inputPanelElement = (element: Element) => element as HTMLElement

const beforeInputPanelEnter = (element: Element) => {
  const panel = inputPanelElement(element)
  inputPanelCompact.value = false
  panel.style.height = '0'
  panel.style.opacity = '0'
  panel.style.transform = 'translateY(-8px)'
}

const enterInputPanel = (element: Element) => {
  const panel = inputPanelElement(element)
  window.requestAnimationFrame(() => {
    panel.style.height = `${panel.scrollHeight}px`
    panel.style.opacity = '1'
    panel.style.transform = 'translateY(0)'
  })
}

const afterInputPanelEnter = (element: Element) => {
  clearInputPanelCompactTimer()
  const panel = inputPanelElement(element)
  panel.style.height = 'auto'
  panel.style.opacity = ''
  panel.style.transform = ''
}

const beforeInputPanelLeave = (element: Element) => {
  const panel = inputPanelElement(element)
  panel.style.height = `${panel.scrollHeight}px`
  panel.style.opacity = '1'
  panel.style.transform = 'translateY(0)'
}

const leaveInputPanel = (element: Element) => {
  const panel = inputPanelElement(element)
  void panel.offsetHeight
  window.requestAnimationFrame(() => {
    panel.style.height = '0'
    panel.style.opacity = '0'
    panel.style.transform = 'translateY(-8px)'
  })
}

const afterInputPanelLeave = (element: Element) => {
  clearInputPanelCompactTimer()
  const panel = inputPanelElement(element)
  panel.style.height = ''
  panel.style.opacity = ''
  panel.style.transform = ''
  if (!inputPanelExpanded.value) inputPanelCompact.value = true
}

const scheduleInputCollapse = (delayMs = 1400) => {
  clearInputCollapseTimer()
  inputCollapseTimer = window.setTimeout(() => {
    inputCollapseTimer = null
    inputPanelExpanded.value = false
  }, delayMs)
}

const clearTopologyTimer = () => {
  if (topologyTimer !== null) {
    window.clearTimeout(topologyTimer)
    topologyTimer = null
  }
}

const clearRunData = () => {
  clearTopologyTimer()
  clearTopologyGraphRefreshTimer()
  topologyGeneration += 1
  topologyController?.abort()
  topologyController = null
  acgView.value = null
  activeRun.value = null
  resourceUsage.value = null
  resourceDrawerOpen.value = false
  loadedRunId.value = ''
  isAcgLoading.value = false
  lastTopologyRefreshAt = 0
  lastTopologyMarker = null
}

const enterNewAcgDraft = () => {
  submitController?.abort()
  progressTracker.reset()
  clearRunData()
  clearInputCollapseTimer()
  clearInputPanelCompactTimer()
  activeRunId.value = ''
  draftEditorTabOpen.value = openedEditorTabs.value.length > 0
  startError.value = null
  inputPanelExpanded.value = true
  runtimeOverviewExpanded.value = true
  inputPanelCompact.value = false
  advancedSettingsExpanded.value = false
  resetDraftContent()
}

async function refreshAcgForRun(runId: string, force = false): Promise<void> {
  if (!runId || runId !== activeRunId.value) return
  if (!force && progressTracker.progress.value && topologyMarker(progressTracker.progress.value) === lastTopologyMarker) return

  const requestGeneration = ++topologyGeneration
  topologyController?.abort()
  topologyController = new AbortController()
  const signal = topologyController.signal
  isAcgLoading.value = true
  try {
    const runPromise = workflowApi.getRun(runId, { signal })
    const [runResult, viewResult, historyConfigResult, resourceResult] = await Promise.allSettled([
      runPromise,
      workflowApi.getAcgView(runId, { signal, run: runPromise }),
      workflowApi.getRunHistoryConfig(runId, { signal }),
      workflowApi.getRunResourceUsage(runId, { signal })
    ])
    if (requestGeneration !== topologyGeneration || runId !== activeRunId.value) return
    if (runResult.status === 'rejected') {
      if (axios.isAxiosError(runResult.reason) && runResult.reason.response?.status === 404) {
        await removeMissingAcgRun(runId)
      } else if (!axios.isCancel(runResult.reason) && force) {
        ElMessage.warning('运行信息暂时未能加载，请稍后刷新')
      }
      return
    }
    const run = runResult.value
    activeRun.value = run
    updateEditorTabFromRun(run)
    if (viewResult.status === 'fulfilled') {
      acgView.value = viewResult.value
    } else if (!axios.isCancel(viewResult.reason) && force) {
      ElMessage.warning('ACG 运行详情暂时未能完整加载，已保留已有结果')
    }
    // 资源是辅助投影，失败时保留上一次已观测调用/Token，不能清空节点答案。
    if (resourceResult.status === 'fulfilled') resourceUsage.value = resourceResult.value
    if (loadedRunId.value !== runId && historyConfigResult.status === 'fulfilled') {
      const historyConfig = historyConfigResult.value
      restoreWorkbenchDraft(draft, historyConfig, pluginUiExtensions.resolve(historyConfig.enabledPluginIds || []))
    } else {
      taskName.value = resolveAcgTaskTitle(run)
    }
    loadedRunId.value = runId
    lastTopologyRefreshAt = Date.now()
    lastTopologyMarker = runTopologyMarker(run)
  } catch (error: unknown) {
    if (!axios.isCancel(error) && requestGeneration === topologyGeneration && force) {
      ElMessage.warning('最终 ACG 数据暂时未能加载，请稍后刷新')
    }
  } finally {
    if (requestGeneration === topologyGeneration) {
      topologyController = null
      isAcgLoading.value = false
    }
  }
}

const removeMissingAcgRun = async (runId: string) => {
  workflowRunsStore.removeReference(runId)
  notifyAcgRunInvalidated(runId)
  removeEditorTab(runId)
  if (activeRunId.value !== runId) return
  progressTracker.reset()
  clearRunData()
  activeRunId.value = ''
  draftEditorTabOpen.value = openedEditorTabs.value.length > 0
  const query = { ...route.query }
  delete query.runId
  await router.replace({ query })
  ElMessage.warning('该运行记录已不存在。')
}

const scheduleTopologyRefresh = (value: DeepReadonly<WorkflowProgress>) => {
  if (!ACTIVE_TOPOLOGY_PHASES.has(value.phase) || value.runId !== activeRunId.value) return
  if (topologyMarker(value) === lastTopologyMarker) return
  clearTopologyTimer()
  const remaining = Math.max(0, TOPOLOGY_REFRESH_MS - (Date.now() - lastTopologyRefreshAt))
  topologyTimer = window.setTimeout(() => {
    topologyTimer = null
    void refreshAcgForRun(value.runId)
  }, remaining)
}

async function handleTerminal(value: WorkflowProgress): Promise<void> {
  const shouldNotify = terminalNotificationRunId === value.runId
  if (shouldNotify) terminalNotificationRunId = null
  clearTopologyTimer()
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await refreshAcgForRun(value.runId, true)
    const projectedStepCount = acgView.value?.stepOutputs?.length || 0
    const hasFinalResult = Boolean(
      acgView.value?.finalArtifacts?.length || acgView.value?.finalReport
    )
    const identityProjectionComplete = acgView.value?.identityProjection?.status === 'available'
    const projectionComplete = projectedStepCount >= value.completedSteps
      && (value.phase !== 'completed' || hasFinalResult)
      && identityProjectionComplete
    if (projectionComplete) break
    await new Promise(resolve => window.setTimeout(resolve, 300))
  }
  if (!shouldNotify) return
  if (value.phase === 'completed') ElMessage.success('ACG 引擎执行完成')
  if (value.phase === 'failed') ElMessage.error('ACG 工作流执行失败')
  if (value.phase === 'cancelled') ElMessage.info('ACG 工作流已取消')
}

watch(
  () => progressTracker.progress.value,
  (value, previous) => {
    if (!value) return
    updateEditorTabStatus(value.runId, value.status)
    const stateChanged = value.status !== previous?.status || value.phase !== previous?.phase
    if (value.status === 'failed' || value.phase === 'failed') {
      clearInputCollapseTimer()
      inputPanelExpanded.value = true
    } else if (stateChanged && (value.status === 'waiting_review' || ['review', 'completed', 'cancelled'].includes(value.phase))) {
      scheduleInputCollapse(0)
    }
    if (isWorkflowReviewPending(value, activeRun.value) && !isWorkflowReviewPending(previous, activeRun.value)) {
      clearTopologyTimer()
      void refreshAcgForRun(value.runId, true)
      return
    }
    scheduleTopologyRefresh(value)
  }
)

watch(() => progressTracker.syncError.value, error => {
  if (error === '该运行记录不存在或当前账户无权访问' && activeRunId.value) {
    void removeMissingAcgRun(activeRunId.value)
  }
})

watch(inputPanelExpanded, value => {
  clearInputPanelCompactTimer()
  if (value) {
    inputPanelCompact.value = false
    return
  }
  advancedSettingsExpanded.value = false
  inputPanelCompactTimer = window.setTimeout(() => {
    inputPanelCompactTimer = null
    if (!inputPanelExpanded.value) inputPanelCompact.value = true
  }, 380)
})

watch([inputPanelExpanded, runtimeOverviewExpanded], () => {
  scheduleTopologyGraphRefresh()
})

watch(
  () => route.query.runId,
  (value) => {
    if (typeof value !== 'string' || !value.trim()) return
    const runId = value.trim()
    ensureEditorTab(runId)
    draftEditorTabOpen.value = false
    if (runId === activeRunId.value && progressTracker.runId.value === runId) return
    terminalNotificationRunId = null
    progressTracker.reset()
    clearRunData()
    startError.value = null
    activeRunId.value = runId
    inputPanelExpanded.value = false
    runtimeOverviewExpanded.value = true
    inputPanelCompact.value = true
    advancedSettingsExpanded.value = false
    workflowRunsStore.register({ runId, source: 'restored' })
    void progressTracker.start(runId, { fresh: false })
  },
  { immediate: true }
)


const openOperations = () => {
  void router.push({
    path: '/history',
    query: activeRunId.value ? { tab: 'acg', runId: activeRunId.value, source: 'acg' } : { tab: 'acg', source: 'acg' }
  })
}

const startNewAcgFromExplorer = async () => {
  if (route.query.runId) {
    await router.replace({ path: '/agentos/acg', query: {} })
  }
  enterNewAcgDraft()
}

const openAcgRunFromExplorer = (runId: string) => {
  ensureEditorTab(runId)
  void router.push({ path: '/agentos/acg', query: { runId } })
}

const handleAcgRunDeletedFromExplorer = async (runId: string) => {
  removeEditorTab(runId)
  if (route.query.runId !== runId) return
  await startNewAcgFromExplorer()
}

const openAcgOperationsFromExplorer = () => {
  void router.push({ path: '/history', query: { tab: 'acg', source: 'acg' } })
}

const openRelatedRun = (runId: string) => {
  ensureEditorTab(runId)
  void router.push({ path: '/agentos/acg', query: { runId } })
}

const selectEditorTab = (tabId: string) => {
  if (tabId === DRAFT_EDITOR_TAB_ID) {
    void startNewAcgFromExplorer()
    return
  }
  const tab = openedEditorTabs.value.find(item => item.id === tabId)
  if (!tab?.runId || tab.runId === activeRunId.value) return
  ensureEditorTab(tab.runId)
  void router.push({ path: '/agentos/acg', query: { runId: tab.runId } })
}

const closeEditorTab = async (tabId: string) => {
  const tabIndex = openedEditorTabs.value.findIndex(item => item.id === tabId)
  if (tabIndex < 0) return
  const isActive = tabId === activeRunId.value
  removeEditorTab(tabId)
  if (!isActive) return

  const nextTab = draftEditorTabOpen.value
    ? null
    : openedEditorTabs.value[tabIndex] || openedEditorTabs.value[tabIndex - 1]
  if (nextTab?.runId) {
    ensureEditorTab(nextTab.runId)
    await router.push({ path: '/agentos/acg', query: { runId: nextTab.runId } })
    return
  }
  await startNewAcgFromExplorer()
}

const scrollToSection = (selector: string) => {
  const mainPane = acgMainPane.value?.closest<HTMLElement>('.workbench-pane--main')
  const target = acgMainPane.value?.querySelector<HTMLElement>(selector)
  if (!mainPane || !target) return
  const top = mainPane.scrollTop + target.getBoundingClientRect().top - mainPane.getBoundingClientRect().top - 16
  mainPane.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
}

const rerunWithNewPlanningSeed = () => {
  const values = new Uint32Array(1)
  crypto.getRandomValues(values)
  draft.planningSeed = values[0] & 0x7fffffff
  void startRun('planning_variant')
}

const handleMainAction = () => {
  if (mainAction.value.action === 'start') {
    void startRun()
    return
  }
  if (mainAction.value.action === 'rerun') {
    void startRun('current_configuration')
    return
  }
  if (mainAction.value.action === 'retry') {
    void startRun('retry_after_failure')
    return
  }
  if (mainAction.value.action === 'resume') {
    void chooseAndResumeFailedRun()
    return
  }
  if (mainAction.value.action === 'review') {
    scrollToSection('.workflow-review')
    return
  }
  if (mainAction.value.action === 'view') scrollToSection('.workflow-progress')
}

const handleAcgReviewed = async (run: WorkflowRun) => {
  if (run.runId !== activeRunId.value) return
  activeRun.value = run
  await progressTracker.refresh()
  await refreshAcgForRun(run.runId, true)
}

const handleAcgReviewConflict = async () => {
  await progressTracker.refresh()
  if (activeRunId.value) await refreshAcgForRun(activeRunId.value, true)
}

const downloadText = (content: string, filename: string, type: string) => {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

const exportAudit = (format: 'json' | 'csv') => {
  if (!acgView.value) return
  const filename = `acg-audit-${acgView.value.runId}.${format}`
  if (format === 'json') {
    downloadText(
      JSON.stringify(buildAcgAuditExport(acgView.value), null, 2),
      filename,
      'application/json;charset=utf-8'
    )
  } else {
    downloadText(`\ufeff${buildAcgAuditCsv(acgView.value)}`, filename, 'text/csv;charset=utf-8')
  }
  ElMessage.success(`ACG 审计 ${format.toUpperCase()} 已导出`)
}

const missionLaunchAttempt = createMissionLaunchAttempt({ slot: 'legacy-acg' })
const restoredInitialLaunch = missionLaunchAttempt.pending()
const pendingInitialLaunch = ref(restoredInitialLaunch)
if (restoredInitialLaunch && !route.query.runId) restoreWorkbenchDraft(draft, {
  runId: '', title: restoredInitialLaunch.commandSnapshot.title,
  reviewMode: restoredInitialLaunch.commandSnapshot.reviewMode,
  enabledPluginIds: restoredInitialLaunch.commandSnapshot.enabledPluginIds || [], input: restoredInitialLaunch.commandSnapshot.input
}, [])
const resumeInitialLaunch = async () => {
  if (isSubmitting.value || !pendingInitialLaunch.value) return
  isSubmitting.value = true
  try {
    const result = await missionLaunchAttempt.resume(pendingInitialLaunch.value.operationId)
    await router.replace({ query: { ...route.query, runId: result.runId } })
    missionLaunchAttempt.complete(result.clientRequestId)
    pendingInitialLaunch.value = null
  } catch (error) { startError.value = startErrorMessage(error) }
  finally { isSubmitting.value = false }
}
const startRun = async (rerunReason?: WorkflowRerunRequest['rerunReason']) => {
  if (isSubmitting.value) return
  if (!taskName.value.trim()) {
    ElMessage.warning('请输入任务名称')
    return
  }
  if (!userIntent.value.trim()) {
    ElMessage.warning('请输入任务目标')
    return
  }
  for (const extension of draftExtensions.value) {
    const validation = extension.validateDraft?.(draft)
    if (validation && !validation.valid) {
      ElMessage.warning(validation.message || `${extension.displayName}配置不完整`)
      return
    }
  }
  isSubmitting.value = true
  startError.value = null
  submitController?.abort()
  submitController = new AbortController()
  const sourceRunId = rerunReason ? activeRunId.value : ''
  const sourceMissionId = rerunReason ? displayedMissionId.value : ''
  if (rerunReason && (!sourceRunId || !sourceMissionId)) {
    isSubmitting.value = false
    ElMessage.error('当前运行缺少 Mission 身份，无法安全重新运行')
    return
  }
  progressTracker.reset()
  clearRunData()
  activeRunId.value = ''
  terminalNotificationRunId = null
  try {
    const clientRequestId = rerunReason ? createClientRequestId() : ''
    const initialCommand = rerunReason ? null : legacyAcgLaunchCommand(draft, draftExtensions.value, {
      attachmentIds: restoredInitialLaunch?.commandSnapshot.attachmentIds,
      materialRefs: restoredInitialLaunch?.commandSnapshot.materialRefs,
      input: { taskName: taskName.value.trim(), debugTrace: debugTraceEnabled.value, lowEntropyOptions: [...lowEntropyOptions.value] }
    })
    const request = initialCommand?.request || buildWorkbenchStartRequest(draft, draftExtensions.value, clientRequestId)
    const requestInput: Record<string, unknown> = {
      ...request.input,
      taskName: taskName.value.trim(),
      debugTrace: debugTraceEnabled.value,
      lowEntropyOptions: [...lowEntropyOptions.value]
    }
    if (rerunReason) request.input = requestInput
    const material = String(request.input.materialText || '')
    if (material && rerunReason) {
      const manifest = await workflowApi.createMaterial(material, 'text/plain')
      request.materialRefs = [manifest.manifestId]
      delete request.input.materialText
    }
    const res = rerunReason
      ? await workflowApi.rerunWorkflowAsync(sourceMissionId, {
          workflowId: request.workflowId,
          reviewMode: request.reviewMode,
          input: request.input,
          enabledPluginIds: request.enabledPluginIds,
          materialRefs: request.materialRefs,
          clientRequestId,
          sourceRunId,
          rerunReason
        }, { signal: submitController.signal })
      : (await missionLaunchAttempt.launch(initialCommand!, { signal: submitController.signal })).run
    activeRunId.value = res.runId
    ensureEditorTab(res.runId, request.title, res.status)
    draftEditorTabOpen.value = false
    scheduleInputCollapse()
    advancedSettingsExpanded.value = false
    workflowRunsStore.register({
      runId: res.runId,
      missionId: res.missionId,
      workflowId: res.workflowId || request.workflowId || 'native_acg_runtime_v1',
      source: 'acg',
      status: res.status,
      phase: res.lifecyclePhase || undefined
    })
    window.dispatchEvent(new Event('acg-runs-refresh'))
    terminalNotificationRunId = res.runId
    void progressTracker.start(res.runId, { fresh: true, expectedMissionId: res.missionId })
    // 提交成功立即拉取一次图与资源详情，运行中再由进度 watcher 按 8s 节奏续刷。
    void refreshAcgForRun(res.runId, true)
    await router.replace({ query: { ...route.query, runId: res.runId } })
    if (!rerunReason) {
      const pending = missionLaunchAttempt.pending()
      if (pending) missionLaunchAttempt.complete(pending.operationId)
    }
  } catch (error: unknown) {
    if (axios.isCancel(error)) return
    pendingInitialLaunch.value = missionLaunchAttempt.pending()
    startError.value = startErrorMessage(error)
  } finally {
    isSubmitting.value = false
    submitController = null
  }
}

const chooseAndResumeFailedRun = async () => {
  const sourceRunId = activeRun.value?.runId
  if (!sourceRunId) return
  const mode = await chooseFailedRunRetryMode(sourceRunId)
  if (mode) await resumeFailedRun(mode)
}

const resumeFailedRun = async (mode: FailedRunRetryMode) => {
  if (isSubmitting.value) return
  const sourceRun = activeRun.value
  const failedStep = sourceRun?.steps.find(step => step.status === 'failed')
  if (!sourceRun?.runId || !failedStep?.stepId) {
    startError.value = '未找到可恢复的失败节点，请刷新运行状态后重试'
    return
  }

  isSubmitting.value = true
  startError.value = null
  submitController?.abort()
  submitController = new AbortController()
  try {
    const resumed = await workflowApi.retryWorkflowStepAsync(
      sourceRun.runId,
      failedStep.stepId,
      {
        clientRequestId: createClientRequestId(),
        reason: 'resume_failed',
        expectedRuntimeRevision: sourceRun.runtimeRevision,
        mode
      },
      { signal: submitController.signal }
    )
    progressTracker.reset()
    clearRunData()
    activeRunId.value = resumed.runId
    ensureEditorTab(resumed.runId, sourceRun.title || taskName.value, resumed.status)
    draftEditorTabOpen.value = false
    workflowRunsStore.register({
      runId: resumed.runId,
      missionId: resumed.missionId,
      workflowId: resumed.workflowId || sourceRun.workflowId || 'native_acg_runtime_v1',
      source: 'acg',
      status: resumed.status,
      phase: resumed.lifecyclePhase || undefined
    })
    window.dispatchEvent(new Event('acg-runs-refresh'))
    terminalNotificationRunId = resumed.runId
    void progressTracker.start(resumed.runId, { fresh: true, expectedMissionId: resumed.missionId })
    void refreshAcgForRun(resumed.runId, true)
    await router.replace({ query: { ...route.query, runId: resumed.runId } })
  } catch (error: unknown) {
    if (axios.isCancel(error)) return
    startError.value = startErrorMessage(error)
  } finally {
    isSubmitting.value = false
    submitController = null
  }
}

const createClientRequestId = (): string => {
  if (typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'))
  return `${hex.slice(0, 4).join('')}-${hex.slice(4, 6).join('')}-${hex.slice(6, 8).join('')}-${hex.slice(8, 10).join('')}-${hex.slice(10).join('')}`
}

const startErrorDetail = (data: unknown): string | null => {
  if (!data || typeof data !== 'object') return null
  const response = data as Record<string, unknown>
  const parts = [response.message, response.error, response.detail]
    .filter((value): value is string => typeof value === 'string' && Boolean(value.trim()))
    .map((value) => value.trim())
  const unique = [...new Set(parts)]
  return unique.length ? unique.join('：').slice(0, 240) : null
}

const startErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    if (error.response?.status === 409) {
      return '相同请求标识已用于不同参数，请重新发起任务'
    }
    if (!error.response) return '任务未能启动：网络连接暂时不可用'
    const detail = startErrorDetail(error.response.data)
    if (detail) return `任务未能启动：${detail}`
  }
  return '任务未能启动'
}

onMounted(() => {
  reconnectRuntimeEvents(activeRunId.value)
  window.addEventListener('acg-new-task', enterNewAcgDraft)
  window.addEventListener('resize', handleAdvancedSettingsViewportChange)
  window.addEventListener('pointerdown', handleAdvancedSettingsDismiss)
  window.addEventListener('keydown', handleAdvancedSettingsKeydown)
})

onBeforeUnmount(() => {
  submitController?.abort()
  clearTopologyTimer()
  clearTopologyGraphRefreshTimer()
  topologyGeneration += 1
  topologyController?.abort()
  clearInputCollapseTimer()
  clearInputPanelCompactTimer()
  window.removeEventListener('acg-new-task', enterNewAcgDraft)
  window.removeEventListener('resize', handleAdvancedSettingsViewportChange)
  window.removeEventListener('pointerdown', handleAdvancedSettingsDismiss)
  window.removeEventListener('keydown', handleAdvancedSettingsKeydown)
})
</script>

<style scoped>
.acg-view.ui-shell { width: 100%; height: 100%; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 0; padding: 0; }
.acg-view.is-draft { min-height: 0; }
.acg-main-pane { min-width: 0; min-height: 0; display: flex; flex-direction: column; padding: var(--space-sm) var(--space-md) 24px; }
.acg-task-config-expanded { min-width: 0; display: flex; flex-direction: column; flex: 0 0 auto; }
.acg-view.is-draft .acg-task-config-expanded { flex: 1 1 auto; min-height: 0; }
.acg-view.is-draft .acg-task-config-expanded > .control-bar { flex: 1 1 auto; min-height: 0; }
.acg-view.is-draft .acg-task-config-expanded > .control-bar.collapsed { flex: 0 0 auto; min-height: 58px; }
.acg-view.has-progress:not(.has-run) .acg-task-config-expanded > .control-bar { border-bottom: 0; border-radius: 0; box-shadow: none; }
:global(.resource-drawer) {
  --el-drawer-padding-primary: 0;
  border-radius: var(--radius-panel) 0 0 var(--radius-panel);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}
:global(.resource-drawer .el-drawer__header) {
  margin: 0;
  padding: 18px 22px 16px;
  border-bottom: 1px solid var(--border-light);
}
:global(.resource-drawer .el-drawer__body) {
  padding: 0;
  overflow-y: auto;
  background: var(--surface-solid);
}
:global(.resource-drawer .el-drawer__close-btn) { border-radius: var(--radius-control); }
:global(.resource-drawer .el-tag) { border-radius: var(--radius-full); }
.resource-drawer__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.resource-drawer__header > div { display: grid; gap: 4px; min-width: 0; }
.resource-drawer__header strong { color: var(--text-primary); font-size: 16px; font-weight: 800; line-height: 1.25; }
.resource-drawer__header span { color: var(--text-secondary); font-size: 11px; line-height: 1.4; }
.resource-drawer__body { min-height: 100%; padding: 0 22px 24px; }
.hero-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
.ui-hero h3 { overflow: hidden; margin: 0; color: var(--text-primary); font-size: 18px; font-weight: 800; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
.hero-right { display: flex; gap: 8px; align-items: center; justify-content: flex-end; flex-wrap: nowrap; }
.hero-run-chip { min-width: 0; height: 30px; display: inline-flex; align-items: center; gap: 5px; padding: 0 9px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-input); color: var(--text-muted); font-size: 10px; }
.hero-run-chip code { overflow: hidden; max-width: 150px; color: var(--text-secondary); font-family: var(--font-mono, ui-monospace, SFMono-Regular, Consolas, monospace); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.hero-icon-action, .hero-operations { height: 32px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--border-light); background: var(--surface-solid); color: var(--text-secondary); cursor: pointer; transition: var(--transition); }
.hero-icon-action { width: 32px; padding: 0; border-radius: 50%; }
.hero-operations { gap: 5px; padding: 0 11px; border-radius: 7px; font: inherit; font-size: 11px; }
.hero-icon-action:hover:not(:disabled), .hero-operations:hover { border-color: var(--primary-line); background: var(--primary-fade); color: var(--primary-color); }
.hero-icon-action:disabled { cursor: not-allowed; opacity: .5; }
.hero-icon-action:focus-visible, .hero-operations:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.control-bar { position: relative; display: flex; flex-direction: column; gap: var(--space-md); padding-right: 52px; padding-bottom: 10px; }
.control-bar.advanced-open { z-index: 40; }
.control-bar.collapsed { flex-direction: row; align-items: center; gap: 14px; padding: 10px 52px 10px 14px; }
.control-bar.collapsed .input-summary { flex: 1 1 auto; }
.control-bar.collapsed .ctrl-options { flex: 0 0 auto; padding: 0; border: 0; }
.control-bar.collapsed .ctrl-options > :deep(.el-button:last-child) { margin-left: 0; }
.workbench-identity, .plugin-selector header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.workbench-identity div, .plugin-selector header div { display:flex; flex-direction:column; gap:3px; }
.workbench-identity small, .plugin-selector small, .plugin-selector header span { color:var(--text-secondary); font-size:11px; }
.plugin-selector { display:flex; flex-direction:column; gap:10px; padding:0; }
.plugin-selector header { align-items:flex-end; }
.plugin-selector header strong { color:var(--text-primary); font-size:14px; font-weight:780; }
.plugin-selector header small { color:var(--text-muted); font-size:10px; }
.plugin-options { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:10px; }
.plugin-card { position:relative; display:flex; flex-direction:column; align-items:stretch; gap:7px; min-height:92px; padding:13px 14px; border:1px solid var(--border-light); border-radius:var(--radius-card); background:var(--surface-solid); color:var(--text-primary); text-align:left; cursor:pointer; transition:var(--transition); }
.plugin-card:hover:not(:disabled) { border-color:var(--border-hover); background:var(--surface-hover); transform:translateY(-1px); }
.plugin-card.selected { border-color:var(--primary-line); background:color-mix(in srgb, var(--primary-fade) 68%, var(--surface-solid)); box-shadow:inset 0 0 0 1px color-mix(in srgb, var(--primary-color) 24%, transparent), var(--shadow-sm); }
.plugin-card__top { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.plugin-card__top strong { min-width:0; color:var(--text-primary); font-size:12px; font-weight:760; }
.plugin-card__state { flex:0 0 auto; padding:4px 7px; border-radius:var(--radius-full); background:var(--bg-input); color:var(--text-muted); font-size:9px; line-height:1; }
.plugin-card.selected .plugin-card__state { background:var(--primary-fade); color:var(--primary-color); }
.plugin-card small { min-height:28px; color:var(--text-secondary); font-size:10px; line-height:1.45; }
.plugin-card code { align-self:flex-start; padding:4px 7px; border-radius:5px; background:var(--bg-input); color:var(--text-muted); font-family:var(--font-mono); font-size:9px; }
.plugin-card:disabled { cursor:not-allowed; opacity:.6; }
.plugin-card:focus-visible { outline:2px solid var(--primary-color); outline-offset:2px; }
.input-panel-expandable {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  min-width: 0;
  overflow: hidden;
  transform-origin: top center;
  transition:
    height 380ms cubic-bezier(0.22, 1, 0.36, 1),
    opacity 220ms ease,
    transform 380ms cubic-bezier(0.22, 1, 0.36, 1);
  will-change: height, opacity, transform;
}
.input-panel-toggle {
  position: absolute; top: 10px; left: 12px; z-index: 1;
  width: 28px; height: 28px; display: inline-grid; place-items: center;
  padding: 0; border: 1px solid var(--border-light); border-radius: 6px;
  background: var(--surface-solid); color: var(--text-secondary); cursor: pointer;
  transition: var(--transition);
}
.input-panel-toggle:hover { border-color: var(--primary-line); color: var(--primary-color); background: var(--primary-fade); }
.input-panel-toggle:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--primary-fade); }
.input-fields { display: grid; grid-template-columns: minmax(0, 13fr) minmax(280px, 7fr); align-items: stretch; gap: 24px; min-width: 0; }
.input-pane { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.contract-pane .ctrl-row { flex: 1 1 auto; min-height: 0; }
.contract-pane .contract-textarea { flex: 1 1 auto; min-height: 0; }
.definition-pane { min-width: 0; gap: 12px; }
.definition-pane :deep(.el-input__wrapper) {
  min-height: 42px;
  border-radius: 6px;
  background: var(--bg-input);
  box-shadow: none;
}
.definition-pane :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--border-light) inset;
}
.definition-pane :deep(.el-input__wrapper.is-focus) {
  background: var(--surface-solid);
  box-shadow: 0 0 0 1px var(--primary-color) inset;
}
.pane-heading { color: var(--text-primary); font-size: 13px; font-weight: 750; }
.pane-heading small { margin-left: 4px; color: var(--text-disabled); font-size: 10px; font-weight: 600; }
.input-summary { display: flex; align-items: center; min-width: 0; }
.input-summary__copy { display: grid; grid-template-columns: 28px minmax(0, auto) minmax(0, 1fr); align-items: center; gap: 8px; min-width: 0; color: var(--text-secondary); }
.input-summary__copy .el-icon { width: 28px; height: 28px; display: inline-grid; place-items: center; border: 1px solid var(--primary-line); border-radius: 7px; background: var(--primary-fade); color: var(--primary-color); }
.input-summary__copy strong { overflow: hidden; max-width: min(240px, 28vw); color: var(--text-primary); font-size: 13px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.input-summary__copy small { overflow: hidden; padding-left: 9px; border-left: 1px solid var(--border-light); text-overflow: ellipsis; white-space: nowrap; font-size: 11px; }
.run-error {
  margin: 0;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--danger) 38%, var(--border-light));
  border-radius: 6px;
  background: var(--danger-fade);
  color: var(--danger);
  font-size: 12px;
}
.ctrl-row { display: flex; flex-direction: column; gap: 6px; }
.ctrl-label { font-size: 12px; font-weight: 600; color: var(--text-secondary); }
.ctrl-options {
  order: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  flex-wrap: wrap;
  padding-top: 6px;
}
.primary-options { display: flex; align-items: center; gap: 18px; min-width: 0; flex-wrap: wrap; overflow: visible; }
.primary-config { display: inline-flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ctrl-label { white-space: nowrap; font-size: 11px; font-weight: 650; color: var(--text-secondary); }
.segmented-control {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 2px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-full);
  background: var(--bg-input);
  box-shadow: inset 0 1px 0 color-mix(in srgb, var(--surface-solid) 45%, transparent);
}
.segment-option {
  min-height: 26px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-secondary);
  font: inherit;
  font-size: 11px;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color 160ms var(--ease-out), color 160ms var(--ease-out), box-shadow 160ms var(--ease-out), transform 160ms var(--ease-out);
}
.segment-option:hover { color: var(--text-primary); }
.segment-option.selected {
  background: var(--surface-solid);
  color: var(--primary-color);
  box-shadow: var(--shadow-sm), 0 0 0 1px var(--primary-line);
}
.segment-option:active { transform: scale(.98); }
.segment-option:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.advanced-toggle {
  min-height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 4px 9px 4px 11px;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-card);
  background: var(--surface-solid);
  color: var(--text-secondary);
  text-align: left;
  cursor: pointer;
  transition: var(--transition);
}
.advanced-toggle:hover, .advanced-toggle[aria-expanded="true"] { border-color: var(--primary-line); background: var(--primary-fade); color: var(--primary-color); }
.advanced-toggle:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.advanced-toggle__copy { display: grid; gap: 1px; min-width: 0; }
.advanced-toggle__copy strong { color: inherit; font-size: 11px; font-weight: 700; line-height: 1.2; }
.advanced-toggle__copy small { overflow: hidden; max-width: 210px; color: var(--text-muted); font-size: 9px; line-height: 1.2; text-overflow: ellipsis; white-space: nowrap; }
.advanced-toggle:hover .advanced-toggle__copy small, .advanced-toggle[aria-expanded="true"] .advanced-toggle__copy small { color: color-mix(in srgb, var(--primary-color) 72%, var(--text-secondary)); }
.advanced-settings-popover { position: relative; z-index: 20; }
.ctrl-options > :deep(.main-action:last-child) {
  --main-action-tone: var(--primary-color);
  --main-action-hover: var(--primary-hover);
  position: relative;
  isolation: isolate;
  min-width: 126px;
  min-height: 44px;
  padding: 0 15px 0 17px;
  overflow: visible;
  border: 1px solid color-mix(in srgb, var(--main-action-tone) 82%, white 18%) !important;
  border-radius: var(--radius-card);
  background: var(--main-action-tone) !important;
  color: var(--on-primary) !important;
  font-weight: 780;
  letter-spacing: .01em;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .22), 0 7px 14px color-mix(in srgb, var(--main-action-tone) 22%, transparent), 0 0 0 1px color-mix(in srgb, var(--main-action-tone) 16%, transparent);
  transform: translateY(0);
  transition: background-color 180ms var(--ease-out), border-color 180ms var(--ease-out), box-shadow 180ms var(--ease-out), transform 180ms var(--ease-out);
}
.ctrl-options > :deep(.main-action:last-child)::before {
  content: '';
  position: absolute;
  inset: -5px;
  z-index: -1;
  border: 1px solid color-mix(in srgb, var(--main-action-tone) 42%, transparent);
  border-radius: calc(var(--radius-card) + 4px);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--main-action-tone) 7%, transparent);
  opacity: 0;
  transform: scale(.94);
  transition: opacity 180ms var(--ease-out), transform 220ms var(--ease-out);
  pointer-events: none;
}
.ctrl-options > :deep(.main-action:last-child)::after {
  content: '';
  position: absolute;
  inset: 1px;
  z-index: -1;
  border-radius: calc(var(--radius-card) - 1px);
  background: rgba(255, 255, 255, .1);
  opacity: .55;
  pointer-events: none;
}
.ctrl-options > :deep(.main-action.el-button--primary) { background: var(--primary-color) !important; }
.ctrl-options > :deep(.main-action.el-button--warning) { --main-action-tone: var(--warning); --main-action-hover: color-mix(in srgb, var(--warning) 86%, white 14%); }
.ctrl-options > :deep(.main-action.el-button--danger) { --main-action-tone: var(--danger); --main-action-hover: color-mix(in srgb, var(--danger) 86%, white 14%); }
.ctrl-options > :deep(.main-action.el-button--info) { --main-action-tone: var(--info); --main-action-hover: color-mix(in srgb, var(--info) 86%, white 14%); }
.ctrl-options > :deep(.main-action:last-child:hover:not(:disabled)) {
  background: var(--main-action-hover) !important;
  border-color: color-mix(in srgb, var(--main-action-tone) 90%, white 10%) !important;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .26), 0 12px 24px color-mix(in srgb, var(--main-action-tone) 30%, transparent), 0 0 0 1px color-mix(in srgb, var(--main-action-tone) 22%, transparent);
  transform: translateY(-2px);
}
.ctrl-options > :deep(.main-action:last-child:hover:not(:disabled))::before { opacity: 1; transform: scale(1); }
.ctrl-options > :deep(.main-action:last-child:active:not(:disabled)) {
  box-shadow: inset 0 2px 3px rgba(8, 9, 18, .18), 0 3px 8px color-mix(in srgb, var(--main-action-tone) 20%, transparent);
  transform: translateY(1px) scale(.985);
}
.ctrl-options > :deep(.main-action:last-child:focus-visible) { outline: 3px solid color-mix(in srgb, var(--main-action-tone) 34%, transparent); outline-offset: 3px; }
.ctrl-options > :deep(.main-action:last-child:disabled) { box-shadow: var(--shadow-sm); cursor: wait; opacity: .72; }
.main-action__label, .main-action__arrow { position: relative; z-index: 1; }
.main-action__arrow { margin-left: 6px; transition: transform 180ms var(--ease-out); }
.ctrl-options > :deep(.main-action:last-child:hover:not(:disabled)) .main-action__arrow { transform: translateX(3px); }
.advanced-settings {
  position: fixed;
  top: 0;
  left: 0;
  right: auto;
  z-index: 100;
  width: min(688px, calc(100vw - 32px));
  max-height: min(520px, calc(100dvh - 104px));
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  padding: 8px;
  overflow-x: hidden;
  overflow-y: auto;
  border: 1px solid color-mix(in srgb, var(--border-light) 78%, var(--surface-solid));
  border-radius: 16px;
  background: var(--bg-input);
  box-shadow: 0 22px 56px color-mix(in srgb, var(--shadow-color) 80%, transparent), 0 4px 12px color-mix(in srgb, var(--shadow-color) 42%, transparent);
  transform-origin: top right;
  animation: advanced-settings-in 180ms var(--ease-out) both;
}
.advanced-settings__head {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-width: 0;
  min-height: 72px;
  padding: 15px 16px;
  border: 1px solid var(--border-light);
  border-radius: 11px;
  background: var(--surface-solid);
}
.advanced-settings__head > div { display: grid; gap: 3px; min-width: 0; }
.advanced-settings__head strong { color: var(--text-primary); font-size: 15px; font-weight: 780; letter-spacing: -.015em; }
.advanced-settings__head small { color: var(--text-muted); font-size: 10px; line-height: 1.4; }
.advanced-settings__head > .advanced-settings__head-actions { display: flex; align-items: center; gap: 8px; flex: 0 0 auto; }
.advanced-settings__head-actions > span { max-width: 220px; overflow: hidden; padding: 7px 10px; border: 1px solid var(--primary-line); border-radius: var(--radius-full); background: var(--primary-fade); color: var(--primary-color); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.advanced-settings__close { width: 32px; height: 32px; display: inline-grid; place-items: center; padding: 0; border: 1px solid var(--border-light); border-radius: var(--radius-control); background: var(--bg-input); color: var(--text-secondary); cursor: pointer; transition: var(--transition); }
.advanced-settings__close:hover, .advanced-settings__close:focus-visible { border-color: var(--primary-line); background: var(--primary-fade); color: var(--primary-color); outline: none; }
.advanced-settings__close:focus-visible { box-shadow: 0 0 0 3px var(--primary-fade); }
.advanced-presets { grid-column: 1 / -1; display: grid; grid-template-columns: minmax(142px, .7fr) minmax(0, 2fr); align-items: center; gap: 14px; padding: 12px 14px; border: 1px solid var(--border-light); border-radius: 11px; background: var(--surface-solid); }
.advanced-presets__intro { display: grid; gap: 3px; min-width: 0; }
.advanced-presets__intro strong { color: var(--text-primary); font-size: 12px; font-weight: 780; }
.advanced-presets__intro small { color: var(--text-muted); font-size: 10px; }
.advanced-presets__options { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 6px; min-width: 0; }
.advanced-preset { min-height: 48px; display: grid; align-content: center; gap: 3px; padding: 7px 10px; border: 1px solid var(--border-light); border-radius: 9px; background: var(--bg-input); color: var(--text-secondary); text-align: left; cursor: pointer; transition: var(--transition); }
.advanced-preset strong { color: inherit; font-size: 11px; font-weight: 750; }
.advanced-preset small { overflow: hidden; color: var(--text-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.advanced-preset:hover, .advanced-preset.selected { border-color: var(--primary-color); background: var(--primary-fade); color: var(--primary-color); }
.advanced-preset:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
.advanced-item {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
  min-height: 82px;
  padding: 13px 14px;
  border: 1px solid var(--border-light);
  border-radius: 11px;
  background: var(--surface-solid);
}
.advanced-item__heading { display: grid; gap: 3px; min-width: 0; }
.advanced-item__heading > span, .advanced-item__label { color: var(--text-primary); font-size: 12px; font-weight: 740; }
.advanced-item__heading small { overflow: hidden; color: var(--text-muted); font-size: 10px; line-height: 1.35; text-overflow: ellipsis; white-space: nowrap; }
.advanced-item--segmented .segmented-control { align-self: flex-start; }
.advanced-item--switch { flex-direction: row; align-items: center; justify-content: space-between; gap: 12px; }
.advanced-item--switch .advanced-item__heading { flex: 1 1 auto; }
.advanced-item--wide { grid-column: span 2; }
.advanced-item :deep(.el-select), .advanced-item :deep(.el-input-number) { width: 100%; }
.advanced-item :deep(.el-input__wrapper) {
  min-height: 36px;
  border: 1px solid var(--border-light);
  border-radius: 9px;
  background: var(--bg-input);
  box-shadow: none;
  transition: border-color 160ms var(--ease-out), background-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out);
}
.advanced-item :deep(.el-input__wrapper:hover) { border-color: var(--border-hover); }
.advanced-item :deep(.el-input__wrapper.is-focus) { border-color: var(--primary-color); background: var(--surface-solid); box-shadow: 0 0 0 3px var(--primary-fade); }
.advanced-item :deep(.el-input__inner) { color: var(--text-primary); font-size: 11px; }
.advanced-item :deep(.el-select .el-input__inner) { color: var(--text-primary); }
.advanced-item :deep(.el-button) { min-height: 34px; border-radius: 9px; }
.settings-switch { display: inline-flex; align-items: center; gap: 7px; flex: 0 0 auto; padding: 0; border: 0; background: transparent; color: var(--text-muted); font: inherit; font-size: 10px; cursor: pointer; }
.settings-switch:hover:not(:disabled), .settings-switch[aria-checked="true"] { color: var(--primary-color); }
.settings-switch:disabled { cursor: not-allowed; opacity: .55; }
.settings-switch:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 4px; border-radius: var(--radius-full); }
.settings-switch__track { position: relative; width: 36px; height: 22px; flex: 0 0 36px; display: inline-flex; align-items: center; padding: 2px; border-radius: var(--radius-full); background: var(--border-hover); transition: background-color 160ms var(--ease-out), box-shadow 160ms var(--ease-out); }
.settings-switch__track > span { width: 18px; height: 18px; display: block; border-radius: 50%; background: var(--surface-solid); box-shadow: var(--shadow-sm); transform: translateX(0); transition: transform 160ms var(--ease-out); }
.settings-switch[aria-checked="true"] .settings-switch__track { background: var(--primary-color); box-shadow: 0 0 0 2px var(--primary-fade); }
.settings-switch[aria-checked="true"] .settings-switch__track > span { transform: translateX(14px); }
.settings-switch:active .settings-switch__track > span { transform: scale(.92); }
.settings-switch[aria-checked="true"]:active .settings-switch__track > span { transform: translateX(14px) scale(.92); }
@keyframes advanced-settings-in {
  from { opacity: 0; transform: translateY(-6px) scale(.985); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.contract-textarea :deep(.el-textarea__inner),
.intent-textarea :deep(.el-textarea__inner) {
  line-height: 1.72;
  font-size: 14px;
  padding: 12px 14px;
  resize: vertical;
}
.contract-pane .contract-textarea :deep(.el-textarea__inner) { height: 100% !important; }
.acg-view.is-draft .input-panel-expandable,
.acg-view.is-draft .input-fields,
.acg-view.is-draft .definition-pane .ctrl-row,
.acg-view.is-draft .contract-textarea,
.acg-view.is-draft .intent-textarea { flex: 1 1 auto; min-height: 0; }
.acg-view.is-draft .contract-textarea :deep(.el-textarea__inner),
.acg-view.is-draft .intent-textarea :deep(.el-textarea__inner) { height: 100% !important; }
.acg-view.is-draft .ctrl-options { margin-top: auto; }
.contract-textarea :deep(.el-textarea__inner),
.intent-textarea :deep(.el-textarea__inner) { min-height: 150px !important; }

.contract-file-input { display: none; }
.contract-upload {
  min-height: 42px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 8px;
  border: 0;
  border-radius: 0;
  background: var(--bg-input);
  transition: border-color 0.16s ease, background-color 0.16s ease;
}
.contract-upload.dragging {
  border-color: var(--primary-color);
  background: var(--primary-fade);
}
.contract-upload.loading { opacity: 0.72; }
.contract-upload__icon {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  display: inline-grid;
  place-items: center;
  border-radius: 5px;
  background: var(--surface-solid);
  color: var(--primary-color);
  box-shadow: 0 0 0 1px var(--border-light);
}
.contract-upload__copy {
  min-width: 0;
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.contract-upload__copy strong,
.contract-upload__copy small {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.contract-upload__copy strong { color: var(--text-primary); font-size: 11px; font-weight: 700; }
.contract-upload__copy small { color: var(--text-secondary); font-size: 10px; }
.contract-upload__copy .contract-upload__error { color: var(--el-color-danger); }
.contract-upload__actions { flex: 0 0 auto; display: inline-flex; align-items: center; gap: 6px; }

.acg-inspector-pane { min-width: 0; min-height: 0; display: flex; flex-direction: column; overflow: hidden; background: var(--surface-solid); }
.acg-inspector-pane__content { flex: 1 1 auto; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: var(--space-lg); overflow-y: auto; overflow-x: hidden; overscroll-behavior: contain; scrollbar-gutter: stable; scrollbar-width: thin; }
.side-provenance { flex: 0 0 auto; min-width: 0; display: flex; overflow: hidden; }
.side-provenance :deep(.acg-provenance) { flex: 1 1 auto; min-height: 0; border: 0; border-radius: 0; box-shadow: none; }
.side-provenance :deep(.panel-head) { padding: 14px 16px 10px; }
.side-provenance :deep(.tabs) { margin-right: 16px; margin-left: 16px; }
.side-provenance :deep(.tab-body) { padding: 0 16px 14px; }

.schedule-strip { padding: var(--space-md); }
.schedule-strip h4 { margin: 0 0 var(--space-sm); font-size: 13px; font-weight: 700; color: var(--text-primary); }
.batch-row { display: flex; gap: var(--space-md); flex-wrap: wrap; }
.batch { display: flex; align-items: center; gap: 4px; padding: 4px 8px; background: var(--bg-input); border-radius: var(--radius-md); }
.batch-idx { font-size: 11px; color: var(--text-secondary); font-weight: 600; margin-right: 4px; }
.batch-node { font-size: 11px; padding: 2px 8px; background: var(--primary-fade); color: var(--primary-color); border-radius: 10px; font-family: monospace; }

.task-brief {
  min-height: 62px;
  display: grid;
  place-items: center;
  margin-top: var(--space-md);
  padding: 12px 20px;
  border-radius: var(--radius-lg);
}
.acg-view.is-draft .acg-main-pane > .task-brief { flex: 0 0 62px; margin-bottom: var(--space-md); }
.task-brief strong { color: var(--text-secondary); font-size: 13px; font-weight: 700; letter-spacing: .02em; }

/* ACG route-scoped Workbench tokens and density rules. */
.acg-view {
  --wb-bg: var(--bg-app, #f7f8fc);
  --wb-sidebar-bg: var(--bg-card, #fff);
  --wb-editor-bg: var(--bg-card, #fff);
  --wb-panel-bg: var(--bg-card, #fff);
  --wb-border: var(--border-light, #e5e7ef);
  --wb-hover: var(--bg-input, #f3f4f8);
  --wb-active: var(--primary-fade, #f0edff);
  --wb-muted: var(--text-secondary, #73798c);
  --wb-text: var(--text-primary, #25283a);
  --wb-accent: var(--primary-color, #7562e8);
  background: var(--wb-bg);
}
.acg-main-pane {
  height: 100%;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  padding: 0;
  overflow: visible;
  background: var(--wb-editor-bg);
}
.workbench-editor-tabbar {
  flex: 0 0 36px;
  min-width: 0;
  display: flex;
  align-items: stretch;
  overflow-x: auto;
  overflow-y: hidden;
  border-bottom: 1px solid var(--wb-border);
  background: var(--wb-bg);
  scrollbar-width: thin;
}
.workbench-editor-tab {
  min-width: 0;
  max-width: min(420px, 62%);
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  border-right: 1px solid var(--wb-border);
  border-bottom: 2px solid transparent;
  background: var(--wb-bg);
  color: var(--wb-muted);
  font-size: 11px;
}
.workbench-editor-tab.is-active {
  border-bottom-color: var(--wb-accent);
  background: var(--wb-editor-bg);
  color: var(--wb-text);
}
.workbench-editor-tab__main {
  min-width: 0;
  max-width: 100%;
  flex: 1 1 auto;
  height: 34px;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 0 8px 0 12px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}
.workbench-editor-tab__main:focus-visible {
  outline: 2px solid var(--wb-accent);
  outline-offset: -2px;
}
.workbench-editor-tab__icon { display: inline-grid; place-items: center; color: var(--wb-accent); }
.workbench-editor-tab__title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workbench-editor-tab__status {
  flex: 0 0 auto;
  padding: 2px 5px;
  border-radius: 3px;
  background: var(--wb-active);
  color: var(--wb-accent);
  font-size: 9px;
  line-height: 1.2;
}
.workbench-editor-tab__status.is-failed { background: var(--danger-fade); color: var(--danger); }
.workbench-editor-tab__close {
  width: 24px;
  height: 24px;
  flex: 0 0 24px;
  display: inline-grid;
  place-items: center;
  margin-right: 4px;
  padding: 0;
  border: 0;
  border-radius: 5px;
  background: transparent;
  color: var(--wb-muted);
  cursor: pointer;
  opacity: 0;
  transition: background-color .16s ease, color .16s ease, opacity .16s ease;
}
.workbench-editor-tab:hover .workbench-editor-tab__close,
.workbench-editor-tab.is-active .workbench-editor-tab__close,
.workbench-editor-tab__close:focus-visible { opacity: 1; }
.workbench-editor-tab__close:hover {
  background: var(--wb-hover);
  color: var(--wb-accent);
}
.workbench-editor-tab__close:focus-visible {
  outline: 2px solid var(--wb-accent);
  outline-offset: -1px;
}
.workbench-editor-toolbar {
  flex: 0 0 42px;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 0 10px;
  border-bottom: 1px solid var(--wb-border);
  background: var(--wb-editor-bg);
  position: sticky;
  top: 0;
  z-index: 30;
}
.workbench-editor-toolbar .hero-left,
.workbench-editor-toolbar .hero-right { min-width: 0; gap: 6px; }
.editor-toolbar__identity { min-width: 0; display: grid; gap: 1px; }
.editor-toolbar__identity strong { overflow: hidden; color: var(--wb-text); font-size: 12px; font-weight: 760; text-overflow: ellipsis; white-space: nowrap; }
.editor-toolbar__identity span { overflow: hidden; color: var(--wb-muted); font-size: 9px; text-overflow: ellipsis; white-space: nowrap; }
.workbench-editor-toolbar .hero-operations { height: 28px; border-radius: 5px; box-shadow: inset 0 1px 0 rgba(255, 255, 255, .76), 0 1px 2px rgba(46, 50, 78, .08); }
.workbench-editor-toolbar .hero-run-chip { height: 26px; padding: 0 7px; border-radius: 4px; background: transparent; font-size: 9px; }
.workbench-editor-toolbar .hero-run-chip code { max-width: 120px; font-size: 9px; }
.workbench-editor-toolbar .hero-operations { padding: 0 8px; border-color: var(--wb-border); background: var(--surface-solid); font-size: 10px; }
.workbench-editor-toolbar .hero-operations:hover { background: var(--wb-hover); }
.control-bar {
  flex: 0 0 auto;
  min-width: 0;
  margin: 0;
  padding: 0 10px;
  gap: 0;
  border: 0;
  border-bottom: 1px solid var(--wb-border);
  border-radius: 0;
  background: var(--wb-bg);
  box-shadow: none;
}
.acg-task-config-section,
.acg-runtime-section {
  min-width: 0;
  flex: 0 0 auto;
  border-top: 1px solid #dfe2f0;
  border-bottom: 1px solid #dfe2f0;
}
.acg-task-config-section { background: #f0f1f9; }
.acg-runtime-section { background: #e9ecf7; }
.acg-task-config-expanded > .control-bar { border-bottom: 0; background: #f0f1f9; }
.control-bar:not(.collapsed) { padding-right: 10px; padding-left: 52px; }
.control-bar.collapsed { min-height: 38px; padding: 5px 10px; gap: 10px; }
.control-bar.collapsed .input-panel-toggle { position: static; flex: 0 0 28px; }
.input-panel-expandable { padding: 10px 0 0; }
.control-bar .ctrl-options { padding: 8px 0; }
.control-bar.collapsed .ctrl-options { padding: 0; }
.control-bar.collapsed .input-summary__copy .el-icon { border: 0; background: transparent; }
.control-bar.collapsed .input-summary__copy strong { font-size: 11px; }
.control-bar.collapsed .input-summary__copy small { font-size: 10px; }
.editor-runtime-strip {
  flex: 0 0 auto;
  min-width: 0;
  display: grid;
  gap: 0;
  overflow: hidden;
  border-bottom: 0;
  background: #e9ecf7;
  padding-left: 40px;
}
.acg-runtime-expanded { position: relative; min-width: 0; }
.runtime-panel-toggle {
  position: absolute;
  top: 8px;
  left: 12px;
  z-index: 1;
  width: 28px;
  height: 28px;
  display: inline-grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--surface-solid);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}
.runtime-panel-toggle:hover { border-color: var(--primary-line); color: var(--primary-color); background: var(--primary-fade); }
.runtime-panel-toggle:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--primary-fade); }
.editor-runtime-strip > :deep(.workflow-progress),
.editor-runtime-strip > :deep(.resource-strip),
.editor-runtime-strip > :deep(.execution-contract) {
  margin: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.editor-runtime-strip > :deep(.workflow-progress) { padding: 7px 10px; }
.editor-runtime-strip > :deep(.resource-strip) { padding: 6px 10px; border-top: 0; }
.editor-runtime-strip > :deep(.execution-contract) { margin-top: 0; border-top: 0; }
.editor-runtime-strip > :deep(.workflow-progress__sync-error) { border-top: 0; padding-top: 0; }
.acg-config-thumbnail,
.acg-runtime-thumbnail {
  min-width: 0;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 5px 10px;
  border-top: 0;
}
.acg-config-thumbnail { background: #f0f1f9; }
.acg-runtime-thumbnail { background: #e9ecf7; }
.acg-config-thumbnail .input-panel-toggle { position: static; flex: 0 0 28px; }
.acg-runtime-thumbnail .runtime-panel-toggle { position: static; flex: 0 0 28px; }
.acg-overview-thumbnail__summary { min-width: 0; flex: 1 1 auto; display: flex; align-items: center; gap: 7px; overflow: hidden; color: var(--wb-muted); font-size: 10px; }
.acg-overview-thumbnail__summary strong { flex: 0 1 auto; min-width: 0; overflow: hidden; color: var(--wb-text); font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.acg-overview-thumbnail__summary > span:last-child { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.acg-overview-thumbnail__dot { width: 7px; height: 7px; flex: 0 0 7px; border-radius: 50%; background: var(--wb-muted); }
.acg-overview-thumbnail__dot.is-running { background: var(--sem-running); box-shadow: 0 0 0 3px var(--sem-running-fade); }
.acg-overview-thumbnail__percent { flex: 0 0 auto; color: var(--wb-accent); font-size: 11px; font-weight: 750; }
.acg-config-thumbnail > :deep(.main-action) { flex: 0 0 auto; min-width: 126px; height: 30px; padding: 0 10px; border-radius: 6px; font-size: 10px; font-weight: 750; }
.acg-runtime-thumbnail__message { min-width: 0; overflow: hidden; color: var(--wb-muted); font-size: 10px; text-overflow: ellipsis; white-space: nowrap; }
.acg-editor-surface {
  flex: 1 1 auto;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  display: flex;
  overflow: hidden;
  background: var(--wb-editor-bg);
}
.acg-editor-body { flex: 1 1 0; min-width: 0; min-height: 0; }
.acg-editor-surface > :deep(.acg-editor-graph) { flex: 1 1 auto; min-width: 0; min-height: 0; }
.acg-main-pane > :deep(.workflow-review) { margin: 0; border-radius: 0; border-right: 0; border-left: 0; box-shadow: none; }
.bottom-panel-result,
.bottom-panel-trace,
.bottom-panel-event-list { min-width: 0; padding: 0 12px 10px; }
.bottom-panel-result :deep(.generic-artifacts),
.bottom-panel-trace :deep(.agentos-run-summary),
.bottom-panel-trace :deep(.runtime-audit-timeline) {
  border: 0;
  border-radius: 0;
  background: transparent;
  box-shadow: none;
}
.bottom-panel-result :deep(.generic-artifacts) { padding: 8px 0; }
.bottom-panel-result :deep(.delivery-overview),
.bottom-panel-result :deep(.delivery-facts > div),
.bottom-panel-result :deep(.calculation-card),
.bottom-panel-result :deep(.decision-grid > article),
.bottom-panel-result :deep(details) { border-radius: 0; box-shadow: none; }
.bottom-panel-trace :deep(.agentos-run-summary),
.bottom-panel-trace :deep(.runtime-audit-timeline) { padding: 8px 0; }
.bottom-panel-trace :deep(.summary-grid) { grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }
.bottom-panel-trace :deep(.summary-grid > div) { min-height: 40px; border-radius: 0; }
.bottom-panel-event-row {
  display: grid;
  grid-template-columns: minmax(120px, .35fr) minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 34px;
  border-bottom: 1px solid var(--wb-border);
  color: var(--wb-muted);
  font-size: 10px;
}
.bottom-panel-event-row strong { color: var(--wb-text); font-size: 10px; }
.bottom-panel-event-row span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bottom-panel-event-row time { color: var(--text-disabled); font-family: var(--font-mono, monospace); font-size: 9px; }
.bottom-panel-empty { display: grid; min-height: 96px; place-items: center; color: var(--wb-muted); font-size: 11px; }
.schedule-strip { padding: 8px 0; border-bottom: 1px solid var(--wb-border); }
.schedule-strip h4 { margin-bottom: 6px; font-size: 11px; }
.batch-row { gap: 6px; }
.batch { padding: 3px 6px; border-radius: 3px; }
.batch-node { padding: 2px 5px; border-radius: 3px; font-size: 10px; }
.task-brief { min-height: 62px; margin: 0; border-radius: 0; }
.acg-view.is-draft .acg-main-pane > .task-brief { margin-bottom: 0; }
.acg-inspector-pane { background: var(--wb-sidebar-bg); }
.acg-inspector-pane__content { gap: 0; scrollbar-gutter: auto; }
.side-provenance { border: 0; border-top: 1px solid var(--wb-border); border-radius: 0; background: transparent; box-shadow: none; }
.side-provenance :deep(.panel-head) { padding: 9px 12px 7px; }
.side-provenance :deep(.tabs) { margin-right: 12px; margin-left: 12px; }
.side-provenance :deep(.tab-body) { padding: 0 12px 10px; }

@keyframes restore-pulse {
  to { opacity: 1; }
}

@media (max-width: 1160px) {
  .advanced-settings { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (prefers-reduced-motion: reduce) {
  .advanced-settings { animation: none; }
}

@media (max-width: 720px) {
  :global(.resource-drawer) { width: 92vw !important; }
  .resource-drawer__body { padding-right: 16px; padding-left: 16px; }
  .hero-left { width: 100%; }
  .hero-right { justify-content: flex-start; width: 100%; flex-wrap: wrap; }
  .hero-run-chip code { max-width: 120px; }
  .contract-upload { align-items: flex-start; flex-wrap: wrap; }
  .contract-upload__copy { width: calc(100% - 34px); }
  .contract-upload__actions { width: 100%; padding-left: 34px; }
  .input-fields { grid-template-columns: 1fr; }
  .definition-pane { padding-top: 14px; }
  .advanced-settings { left: 0; right: auto; width: min(620px, calc(100vw - 32px)); grid-template-columns: 1fr; }
  .advanced-presets { grid-template-columns: 1fr; }
  .advanced-presets__options { grid-template-columns: 1fr; }
  .advanced-item--wide { grid-column: auto; }
  .ctrl-options > :deep(.el-button:last-child) { width: 100%; margin-left: 0; }
  .input-summary__copy { align-items: flex-start; flex-wrap: wrap; }
  .input-summary__copy small { width: 100%; white-space: normal; }
  .control-bar.collapsed { align-items: stretch; flex-direction: column; }
  .control-bar.collapsed .ctrl-options { width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .input-panel-expandable { transition-duration: 1ms; }
}
</style>
