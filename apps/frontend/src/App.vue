<template>
  <ErrorBoundary>
    <div id="app">
      <transition name="fade">
        <div v-if="globalError" class="global-error-banner">
          <el-alert :title="globalError" type="error" show-icon @close="clearGlobalError" />
        </div>
      </transition>

      <PublicRouteLayout v-if="isPublicRoute" />
      <AuthenticatedAppShell v-else />
      <ZoomIndicator />
      <CompanionHost v-if="!isPublicRoute" />
    </div>
  </ErrorBoundary>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import PublicRouteLayout from '@/components/app/PublicRouteLayout.vue'
import ZoomIndicator from '@/components/desktop/ZoomIndicator.vue'
import { initUiZoom } from '@ui-zoom'

const AuthenticatedAppShell = defineAsyncComponent(
  () => import('@/components/app/AuthenticatedAppShell.vue')
)
// 虚拟伙伴是接入层可拔插能力：只在认证态挂载，公开路由不加载任何会话依赖。
const CompanionHost = defineAsyncComponent(
  () => import('@/components/companion/CompanionHost.vue')
)

const route = useRoute()
const isPublicRoute = computed(() => route.path === '/' || route.path === '/login')
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
