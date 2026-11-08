<template>
  <el-container class="app-layout public-layout">
    <el-container class="app-shell-body">
      <el-container class="main-container">
        <el-main class="app-main public-main">
          <Suspense>
            <template #default>
              <router-view v-slot="{ Component }">
                <component :is="Component" :key="route.path" />
              </router-view>
            </template>
            <template #fallback>
              <div class="route-loading" role="status" aria-live="polite">
                <BrandLoader :size="52" title="页面加载中…" />
              </div>
            </template>
          </Suspense>
        </el-main>
      </el-container>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import BrandLoader from '@/components/common/BrandLoader.vue'

const route = useRoute()
</script>

<style scoped>
.app-layout {
  width: 100%;
  background: var(--app-layout-bg);
  display: flex;
  flex-direction: column;
}

.app-layout.public-layout {
  min-height: 100%;
  overflow: visible;
  background: transparent;
}

.app-shell-body {
  display: flex;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  width: 100%;
  overflow: hidden;
}

.public-layout .app-shell-body {
  display: block;
  min-height: 100vh;
  min-height: 100dvh;
  overflow: visible;
}

.main-container {
  flex: 1;
  min-width: 0;
  background-color: transparent;
  position: relative;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.app-main {
  flex: 1;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  width: 100%;
  position: relative;
}

.app-main.public-main {
  min-height: 100vh;
  min-height: 100dvh;
  overflow: visible;
}

.route-loading {
  display: grid;
  min-height: 100%;
  place-items: center;
  color: var(--text-secondary);
  font-size: 13px;
}
</style>
