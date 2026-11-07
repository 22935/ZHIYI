<template>
  <div v-if="runtimeAvailable" class="desktop-window-controls">
    <button type="button" class="dwc-button" aria-label="最小化" title="最小化" @click="minimize">
      <svg class="dwc-icon" width="14" height="14" viewBox="0 0 14 14" shape-rendering="crispEdges" aria-hidden="true">
        <path d="M2 7h10" />
      </svg>
    </button>
    <button
      type="button"
      class="dwc-button"
      :aria-label="maximized ? '向下还原' : '最大化'"
      :title="maximized ? '向下还原' : '最大化'"
      @click="toggleMaximize"
    >
      <svg v-if="!maximized" class="dwc-icon" width="14" height="14" viewBox="0 0 14 14" shape-rendering="crispEdges" aria-hidden="true">
        <rect x="2.5" y="2.5" width="9" height="9" />
      </svg>
      <svg v-else class="dwc-icon" width="14" height="14" viewBox="0 0 14 14" shape-rendering="crispEdges" aria-hidden="true">
        <rect x="2.5" y="4.5" width="7" height="7" />
        <path d="M4.5 4.5v-2h7v7h-2" />
      </svg>
    </button>
    <button type="button" class="dwc-button dwc-button--close" aria-label="关闭" title="关闭" @click="closeWindow">
      <svg class="dwc-icon" width="14" height="14" viewBox="0 0 14 14" shape-rendering="crispEdges" aria-hidden="true">
        <path d="m3 3 8 8M11 3l-8 8" />
      </svg>
    </button>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { getElectronBridge, type KinlinDesktopBridge } from '@/platform/electron/bridge'

// 只负责窗口本体：最小化 / 最大化 / 还原 / 关闭 / 真实窗口状态同步；不感知任何业务概念；
// F11 全屏由 Main 进程 before-input-event 接管（页面僵死后仍可用），此处不再监听键盘。
const maximized = ref(false)
const runtimeAvailable = ref(false)
let bridge: KinlinDesktopBridge | null = null
let unlistenMaximize: (() => void) | null = null
let disposed = false

onMounted(() => {
  // 桌面适配在构建期决定，但 Electron 桥是运行期能力，挂载后再解析；
  // 桥缺失（非 Electron 宿主、Preload 未注入）时组件渲染为空，不打断页面导航。
  bridge = getElectronBridge()
  if (!bridge) return

  runtimeAvailable.value = true
  void bridge.window.isMaximized().then((value) => {
    if (!disposed) maximized.value = value
  }).catch(() => {})
  unlistenMaximize = bridge.window.onMaximizeChanged((value) => {
    maximized.value = value
  })
})

onBeforeUnmount(() => {
  disposed = true
  unlistenMaximize?.()
  unlistenMaximize = null
  bridge = null
})

const minimize = (): void => {
  void bridge?.window.minimize()
}

const toggleMaximize = (): void => {
  void bridge?.window.toggleMaximize()
}

const closeWindow = (): void => {
  void bridge?.window.close()
}
</script>

<style scoped>
.desktop-window-controls {
  display: flex;
  align-items: stretch;
  height: 100%;
}

.dwc-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 100%;
  padding: 0;
  color: var(--app-topbar-muted, var(--text-secondary, #737991));
  background: transparent;
  border: 0;
  border-radius: 0;
  cursor: default;
  outline-offset: -2px;
  transition: background-color 120ms ease, color 120ms ease;
}

.dwc-button:hover {
  background: var(--app-topbar-hover, rgba(0, 0, 0, 0.05));
}

.dwc-button:active {
  background: var(--app-topbar-active, rgba(0, 0, 0, 0.08));
}

.dwc-button:focus-visible {
  outline: 2px solid var(--app-topbar-focus-ring, rgba(167, 139, 250, 0.3));
}

.dwc-icon {
  fill: none;
  stroke: currentColor;
  stroke-width: 1;
}

.dwc-button--close:hover {
  color: #ffffff;
  background: color-mix(in srgb, #c42b1c 85%, #ffffff);
}

.dwc-button--close:active {
  color: #ffffff;
  background: #c42b1c;
}

@media (prefers-reduced-motion: reduce) {
  .dwc-button {
    transition: none;
  }
}
</style>
