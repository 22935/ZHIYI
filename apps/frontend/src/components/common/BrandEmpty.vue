<!-- 品牌空态 — 花环静置水印 + 说明文案，统一「无内容」呈现（区别于 BrandLoader 的加载呼吸态） -->
<template>
  <div class="brand-empty">
    <img class="brand-empty__mark" :src="activePack.mark" alt="" aria-hidden="true" :style="{ width: `${size}px`, height: `${size}px` }" />
    <p class="brand-empty__text">
      <slot>{{ text }}</slot>
    </p>
  </div>
</template>

<script setup lang="ts">
import { useBrand } from '@/features/brand/useBrand'

withDefaults(defineProps<{
  text?: string
  size?: number
}>(), {
  text: '',
  size: 96
})

const { activePack } = useBrand()
</script>

<style scoped>
.brand-empty { display: grid; justify-items: center; align-content: center; gap: 12px; box-sizing: border-box; padding: 24px 14px; text-align: center; }
.brand-empty__mark { object-fit: contain; opacity: .38; filter: var(--brand-logo-filter, none) grayscale(1) saturate(.55) contrast(.85) brightness(1.12); pointer-events: none; user-select: none; }
.brand-empty__text { margin: 0; color: var(--wb-text-muted, var(--text-secondary)); font-size: 11px; line-height: 1.6; }
</style>
