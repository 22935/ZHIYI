<template>
  <ErrorBoundary>
    <div id="app">
      <transition name="fade">
        <div v-if="globalError" class="global-error-banner">
          <el-alert :title="globalError" type="error" show-icon @close="clearGlobalError" />
        </div>
      </transition>

      <AppShell />
      <ZoomIndicator />
      <CompanionHost v-if="companionEnabled" />
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import ZoomIndicator from '@/components/desktop/ZoomIndicator.vue'
import { initUiZoom } from '@ui-zoom'
import { useCompanionEnabled } from '@/features/companion/enabled'

const AppShell = defineAsyncComponent(
  () => import('@/components/app/AppShell.vue')
)
// 虚拟伙伴按需加载，使用同一本机后端。
const CompanionHost = defineAsyncComponent(
  () => import('@/components/companion/CompanionHost.vue')
)
// 显隐开关由设置页（外观→界面）控制，缺省开启。
const companionEnabled = useCompanionEnabled()

const globalError = ref('')

const clearGlobalError = () => {
  globalError.value = ''
}

const handleGlobalError = (event: Event) => {
  const detail = (event as CustomEvent<{ clear?: boolean; message?: string; duration?: number }>).detail
  if (detail?.clear) {
    clearGlobalError()
    return
  }

  if (detail?.message) {
    globalError.value = detail.message
    window.setTimeout(clearGlobalError, detail.duration || 5000)
  }
}

let disposeUiZoom: (() => void) | null = null

onMounted(() => {
  window.addEventListener('global-error', handleGlobalError)
  disposeUiZoom = initUiZoom()
})

onUnmounted(() => {
  window.removeEventListener('global-error', handleGlobalError)
  disposeUiZoom?.()
  disposeUiZoom = null
})
</script>

<style scoped>
#app {
  position: relative;
  min-height: 100%;
}

.global-error-banner {
  position: absolute;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  min-width: 300px;
}
</style>
