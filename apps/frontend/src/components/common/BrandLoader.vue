<!-- 品牌加载态 — 花环生长环呼吸动画，统一全应用加载视觉 -->
<template>
  <div class="brand-loader">
    <img class="brand-loader__mark" :src="activePack.main" alt="" aria-hidden="true" :style="{ width: `${size}px`, height: `${size}px` }" />
    <strong v-if="title">{{ title }}</strong>
    <span v-if="subtitle">{{ subtitle }}</span>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { useBrand } from '@/features/brand/useBrand'

withDefaults(defineProps<{
  title?: string
  subtitle?: string
  size?: number
}>(), {
  title: '',
  subtitle: '',
  size: 64
})

const { activePack } = useBrand()
</script>

<style scoped>
.brand-loader { display: grid; justify-items: center; gap: 10px; color: var(--text-secondary); text-align: center; }
.brand-loader__mark { object-fit: contain; animation: brand-loader-breathe 3.2s ease-in-out infinite; }
.brand-loader strong { color: var(--text-primary); font-size: 15px; }
.brand-loader span { font-size: 12px; line-height: 1.65; }

@keyframes brand-loader-breathe {
  0%, 100% { opacity: .6; transform: scale(.97); }
  50% { opacity: 1; transform: scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .brand-loader__mark { animation: none; }
}
</style>
