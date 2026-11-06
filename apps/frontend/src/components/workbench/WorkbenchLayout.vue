<template>
  <section
    ref="containerRef"
    class="workbench-layout"
    :class="{
      'is-resizing': Boolean(resizingSide),
      'is-left-collapsed': !leftVisible,
      'is-right-collapsed': !rightPaneVisible,
      'is-right-maximized': rightPaneMaximized
    }"
    :style="{
      '--workbench-left-width': `${leftPaneWidth}px`,
      '--workbench-right-width': `${effectiveRightPaneWidth}px`,
      '--workbench-right-max-width': `${rightMaxWidth}px`
    }"
  >
    <div class="workbench-layout__body">
      <aside v-if="leftVisible && !rightPaneMaximized" class="workbench-pane workbench-pane--left" aria-label="项目导航">
        <slot name="left" />
      </aside>

      <ResizeHandle
        v-if="showLeft && (leftPaneVisible || leftAutoHidden)"
        v-show="!rightPaneMaximized"
        side="left"
        :value="leftPaneWidth"
        :min="LEFT_MIN_WIDTH"
        :max="maxWidthFor('left')"
        :ariaLabel="leftAutoHidden ? '拖动或单击恢复左侧任务导航并调整宽度' : '调整左侧任务导航宽度'"
        @resize-start="startResize('left', $event)"
        @resize-keydown="handleResizeKeydown('left', $event)"
        @reset="resetWidth('left')"
        @click="leftAutoHidden && restoreLeftPane()"
      />

      <main v-show="!rightPaneMaximized" class="workbench-pane workbench-pane--main">
        <WorkbenchVerticalSplit
          v-if="showBottomPanel"
          ref="splitRef"
          :storage-key="bottomPanelStorageKey"
          :default-collapsed="bottomPanelDefaultCollapsed"
          :collapsed-height="bottomPanelCollapsedHeight"
        >
          <template #graph>
            <slot
              name="main"
              :left-auto-hidden="leftAutoHidden"
              :restore-left-pane="restoreLeftPane"
              :right-auto-hidden="rightAutoHidden"
              :right-enabled="rightEnabled"
              :right-pane-visible="rightPaneVisible"
              :right-collapsed-by-user="rightCollapsedByUser"
              :toggle-right-pane="toggleRightPane"
            />
          </template>
          <template #bottom="bottomState">
            <slot name="bottom" v-bind="bottomState" />
          </template>
        </WorkbenchVerticalSplit>
          <slot
            v-else
            name="main"
            :left-auto-hidden="leftAutoHidden"
            :restore-left-pane="restoreLeftPane"
            :right-auto-hidden="rightAutoHidden"
            :right-enabled="rightEnabled"
            :right-pane-visible="rightPaneVisible"
            :right-collapsed-by-user="rightCollapsedByUser"
            :toggle-right-pane="toggleRightPane"
          />
      </main>

      <ResizeHandle
        v-if="rightPaneVisible || rightAutoHidden"
        v-show="!rightPaneMaximized"
        side="right"
        :value="effectiveRightPaneWidth"
        :min="rightPaneMinWidth"
        :max="maxWidthFor('right')"
        :ariaLabel="rightAutoHidden ? '拖动恢复右侧运行详情并调整宽度' : '调整右侧运行详情宽度'"
        @resize-start="startResize('right', $event)"
        @resize-keydown="handleResizeKeydown('right', $event)"
        @reset="resetWidth('right')"
      />

      <aside v-if="rightPaneVisible" class="workbench-pane workbench-pane--right" aria-label="Workspace Inspector">
        <slot
          name="right"
          :right-pane-maximized="rightPaneMaximized"
          :toggle-right-pane-maximized="toggleRightPaneMaximized"
          :toggle-right-pane="toggleRightPane"
        />
      </aside>
    </div>

    <footer v-if="$slots['status-bar']" class="workbench-layout__status-bar">
      <slot
        name="status-bar"
        :collapsed="bottomPanelCollapsed"
        :set-collapsed="setBottomPanelCollapsed"
        :toggle-collapsed="toggleBottomPanelCollapsed"
      />
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch } from 'vue'
import ResizeHandle from './ResizeHandle.vue'
import WorkbenchVerticalSplit from './WorkbenchVerticalSplit.vue'
import { useWorkbenchLayout } from '@/composables/useWorkbenchLayout'

const props = withDefaults(defineProps<{
  showLeft?: boolean
  showRight?: boolean
  showBottomPanel?: boolean
  bottomPanelStorageKey?: string
  bottomPanelDefaultCollapsed?: boolean
  /** Bottom slot height while collapsed; 0 hides the panel (a status bar replaces it). */
  bottomPanelCollapsedHeight?: number
  rightPaneMinWidth?: number
  rightPaneDefaultWidth?: number
  rightPaneMaxWidth?: number
  storageKey?: string
  sharedDockGeometry?: boolean
}>(), {
  showLeft: true,
  showRight: true,
  showBottomPanel: false,
  bottomPanelStorageKey: 'zhiyi.workbench.bottom-panel.v1',
  bottomPanelDefaultCollapsed: false,
  rightPaneMinWidth: 300,
  rightPaneDefaultWidth: 400,
  rightPaneMaxWidth: 960,
  storageKey: 'zhiyi.acg.workbench.layout.v1'
})

interface SplitExposed {
  collapsed: boolean
  setCollapsed: (value: boolean) => void
  toggleCollapsed: () => void
}
const splitRef = ref<SplitExposed | null>(null)
const bottomPanelCollapsed = computed(() => Boolean(splitRef.value?.collapsed))
const setBottomPanelCollapsed = (value: boolean) => splitRef.value?.setCollapsed(value)
const toggleBottomPanelCollapsed = () => splitRef.value?.toggleCollapsed()

const layout = useWorkbenchLayout({
  sharedDockGeometry: props.sharedDockGeometry,
  storageKey: props.storageKey,
  right: {
    minWidth: props.rightPaneMinWidth,
    defaultWidth: props.rightPaneDefaultWidth,
    maxWidth: props.rightPaneMaxWidth
  },
  rightEnabled: toRef(props, 'showRight')
})

const {
  containerRef,
  leftPaneWidth,
  effectiveRightPaneWidth,
  rightMaxWidth,
  leftAutoHidden,
  rightAutoHidden,
  rightCollapsedByUser,
  rightEnabled,
  resizingSide,
  leftPaneVisible,
  rightPaneVisible,
  maxWidthFor,
  toggleRightPane,
  restoreLeftPane,
  startResize,
  handleResizeKeydown,
  resetWidth
} = layout

const rightPaneMaximized = ref(false)
const toggleRightPaneMaximized = () => {
  if (rightPaneVisible.value) rightPaneMaximized.value = !rightPaneMaximized.value
}
watch(rightPaneVisible, visible => {
  if (!visible) rightPaneMaximized.value = false
})

const leftVisible = computed(() => props.showLeft && leftPaneVisible.value)

const LEFT_MIN_WIDTH = 240
defineExpose({ restoreLeftPane })
</script>

<style scoped>
.workbench-layout {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: var(--wb-surface-0);
}

.workbench-layout__body {
  flex: 1 1 auto;
  display: flex;
  width: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.workbench-layout__status-bar {
  flex: 0 0 auto;
  min-width: 0;
}

.workbench-pane {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: flex-basis 180ms var(--ease-out), width 180ms var(--ease-out), opacity 180ms var(--ease-out);
}

.workbench-pane--left {
  flex: 0 0 var(--workbench-left-width);
  width: var(--workbench-left-width);
  border-right: 0;
  background: var(--wb-surface-1);
}

.workbench-pane--main {
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  overscroll-behavior: contain;
  scrollbar-gutter: auto;
}

.workbench-pane--right {
  flex: 0 0 min(var(--workbench-right-width), var(--workbench-right-max-width));
  width: min(var(--workbench-right-width), var(--workbench-right-max-width));
  max-width: var(--workbench-right-max-width);
  box-sizing: border-box;
  border-left: 0;
  background: var(--wb-surface-1);
}
.workbench-layout.is-right-maximized .workbench-pane--right {
  flex: 1 1 auto;
  width: 100%;
  max-width: none;
  border-left: 0;
}

.workbench-layout.is-resizing .workbench-pane {
  transition: none;
}

@media (prefers-reduced-motion: reduce) {
  .workbench-pane { transition-duration: 1ms; }
}
</style>
