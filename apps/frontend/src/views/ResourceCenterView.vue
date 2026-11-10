<template>
  <div class="resource-center">
    <WorkbenchLayout :show-left="false" :show-right="false" storage-key="zhiyi.resources.layout.v1">
      <template #main>
        <main class="resource-center__main" aria-label="资源与连接中心" data-max-width="1400px">
          <WorkspacePageHero eyebrow="RESOURCE & CONNECTIONS" title="资源与连接中心">
            <template #actions>
              <button class="resource-action resource-action--primary" type="button" @click="openRegistration">
                <el-icon aria-hidden="true"><Plus /></el-icon>
                <span>接入资源</span>
              </button>
              <button class="resource-action" type="button" :disabled="resourceTab !== 'overview'" @click="refreshOverview">
                <el-icon aria-hidden="true"><Refresh /></el-icon>
                <span>刷新</span>
              </button>
            </template>
          </WorkspacePageHero>

          <nav class="resource-tabs" aria-label="资源中心导航">
            <button
              v-for="tab in resourceTabs"
              :key="tab.id"
              :data-testid="`resource-tab-${tab.id}`"
              type="button"
              :class="{ active: resourceTab === tab.id }"
              :aria-current="resourceTab === tab.id ? 'page' : undefined"
              @click="selectResourceTab(tab.id)"
            >{{ tab.label }}</button>
          </nav>

          <section class="resource-center__content">
            <ResourceOverviewPanel v-if="resourceTab === 'overview'" ref="overviewPanel" />
            <ModelManagementPanel v-else />
          </section>
        </main>
      </template>
    </WorkbenchLayout>

    <ResourceRegistrationDialog v-model="registrationOpen" @registered="handleRegistered" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Plus, Refresh } from '@element-plus/icons-vue'
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import WorkspacePageHero from '@/components/app/WorkspacePageHero.vue'
import ResourceOverviewPanel from '@/components/resource-center/ResourceOverviewPanel.vue'
import ModelManagementPanel from '@/components/resource-center/ModelManagementPanel.vue'
import ResourceRegistrationDialog from '@/components/resource-center/ResourceRegistrationDialog.vue'

type ResourceTab = 'overview' | 'models'
const resourceTabs: Array<{ id: ResourceTab; label: string }> = [
  { id: 'overview', label: '资源概览' },
  { id: 'models', label: '模型管理' }
]
const route = useRoute()
const router = useRouter()
const overviewPanel = ref<InstanceType<typeof ResourceOverviewPanel> | null>(null)
const registrationOpen = ref(false)
const isResourceTab = (value: unknown): value is ResourceTab => resourceTabs.some(tab => tab.id === value)
const resourceTab = computed<ResourceTab>(() => isResourceTab(route.query.tab) ? route.query.tab : 'overview')

const selectResourceTab = (tab: ResourceTab) => {
  void router.replace({ path: '/agentos/resources', query: tab === 'overview' ? {} : { tab } })
}

const refreshOverview = () => {
  overviewPanel.value?.loadResources()
}

const openRegistration = () => {
  registrationOpen.value = true
}

const handleRegistered = () => {
  registrationOpen.value = false
  refreshOverview()
}

watch(() => route.query.tab, value => {
  if (value !== undefined && !isResourceTab(value)) void router.replace({ path: '/agentos/resources', query: {} })
}, { immediate: true })
</script>

<style scoped>
.resource-center { width: 100%; height: 100%; min-width: 0; min-height: 0; overflow: hidden; background: var(--bg-app); }
.resource-center__main { width: min(100%, 1400px); height: 100%; margin: 0 auto; overflow: auto; padding: 0 clamp(20px, 4vw, 58px) 48px; color: var(--text-primary); }
.resource-action { display: inline-flex; align-items: center; gap: 6px; min-height: 32px; padding: 0 12px; border: 1px solid var(--primary-line); border-radius: 5px; color: var(--primary-color); background: var(--primary-fade); cursor: pointer; font: inherit; font-size: 11px; }
.resource-action--primary { border-color: transparent; color: #fff; background: var(--primary-color); box-shadow: 0 4px 12px color-mix(in srgb, var(--primary-color) 28%, transparent); }
.resource-action--primary:hover { filter: brightness(1.06); }
.resource-action:disabled { cursor: default; opacity: .55; }
.resource-tabs { display: flex; gap: 4px; padding: 14px 0 0; border-bottom: 1px solid var(--border-light); }
.resource-tabs button { min-height: 36px; padding: 0 14px; border: 0; border-bottom: 2px solid transparent; color: var(--text-secondary); background: transparent; cursor: pointer; font: inherit; font-size: 12px; }
.resource-tabs button:hover, .resource-tabs button.active { color: var(--primary-color); }
.resource-tabs button.active { border-bottom-color: var(--primary-color); font-weight: 650; }
.resource-center__content { min-width: 0; padding-top: 4px; }
@media (max-width: 700px) {
  .resource-center__main { width: 100%; padding-right: 16px; padding-left: 16px; }
  .resource-tabs { overflow-x: auto; }
  .resource-tabs button { flex: 0 0 auto; }
}
</style>
