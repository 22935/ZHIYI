<template>
  <main class="projects-hub" aria-label="项目预加载">
    <img class="projects-hub__emblem" :src="activePack.mark" alt="" aria-hidden="true" />
  </main>
</template>

<script setup lang="ts">
import { useBrand } from '@/features/brand/useBrand'

// 顶部「项目」下拉的默认落点：纯色底 + 居中彩色品牌标的预加载屏，
// 不承载实际内容；任务列表走「打开 Mission」，新建走「新建 Mission」。
const { activePack } = useBrand()
</script>

<style scoped>
.projects-hub {
  display: grid;
  place-items: center;
  width: 100%;
  height: 100%;
  background: var(--bg-app);
}

/* 参考编辑器空态的居中大 logo：品牌标保持原色 */
.projects-hub__emblem {
  width: clamp(260px, 34vh, 400px);
  height: auto;
  animation: projects-hub-breathe 3s ease-in-out infinite alternate;
}

@keyframes projects-hub-breathe {
  from { opacity: .86; transform: scale(.99); }
  to { opacity: 1; transform: scale(1.01); }
}

@media (prefers-reduced-motion: reduce) {
  .projects-hub__emblem { animation: none; }
}
</style>
