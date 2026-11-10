<template>
  <nav class="resource-nav" aria-label="资源中心">
    <RouterLink to="/agentos/resources/overview" :aria-current="active === 'overview' ? 'page' : undefined">概览</RouterLink>
    <RouterLink to="/agentos/resources/manage" :aria-current="active === 'manage' ? 'page' : undefined">资源管理</RouterLink>
    <RouterLink to="/agentos/resources/store" :aria-current="active === 'store' ? 'page' : undefined">资源商店</RouterLink>
  </nav>
</template>

<script setup lang="ts">
defineProps<{ active: 'overview' | 'manage' | 'store' }>()
</script>

<style scoped>
.resource-nav { display: flex; gap: 22px; min-height: 42px; border-bottom: 1px solid var(--border-light); }
.resource-nav a { display: inline-flex; align-items: center; position: relative; color: var(--text-secondary); text-decoration: none; font-size: 12px; }
.resource-nav a:hover, .resource-nav a[aria-current="page"] { color: var(--text-primary); }
.resource-nav a[aria-current="page"]::after { position: absolute; right: 0; bottom: -1px; left: 0; height: 2px; content: ''; background: var(--primary-color); }
@media (max-width: 520px) { .resource-nav { gap: 18px; } }
</style>
