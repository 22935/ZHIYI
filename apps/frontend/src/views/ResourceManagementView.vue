<template>
  <div class="resource-page">
    <WorkbenchLayout :show-left="false" :show-right="false" storage-key="zhiyi.resources.manage.v2">
      <template #main>
        <main class="resource-page__main" aria-label="资源管理">
          <WorkspacePageHero eyebrow="RESOURCE PLANE / 02" title="资源管理">
            <template #actions>
              <RouterLink class="resource-manage-action" to="/agentos/resources/store">添加资源</RouterLink>
            </template>
          </WorkspacePageHero>
          <ResourceCenterNav active="manage" />
          <ResourceOverviewPanel />
        </main>
      </template>
    </WorkbenchLayout>
  </div>
</template>

<script setup lang="ts">
import WorkbenchLayout from '@/components/workbench/WorkbenchLayout.vue'
import WorkspacePageHero from '@/components/app/WorkspacePageHero.vue'
import ResourceCenterNav from '@/components/resource-center/ResourceCenterNav.vue'
import ResourceOverviewPanel from '@/components/resource-center/ResourceOverviewPanel.vue'
</script>

<style scoped>
.resource-page { width: 100%; height: 100%; min-height: 0; overflow: hidden; background: var(--bg-app); }
.resource-page__main { width: min(100%, 1400px); height: 100%; overflow: auto; margin: 0 auto; padding: 0 clamp(18px, 4vw, 58px) 42px; color: var(--text-primary); }
.resource-manage-action { display: inline-flex; align-items: center; min-height: 36px; padding: 0 14px; border: 1px solid var(--primary-color); color: #fff; background: var(--primary-color); text-decoration: none; font-size: 11px; }
</style>
