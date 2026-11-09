import { computed, ref } from 'vue'
import { isDarkColorScheme } from '@/themes/presets'
import { BRAND_PACKS, DEFAULT_BRAND_ID, getBrandPack, isBrandId, type BrandId, type BrandPack } from './brandPacks'

// 品牌标是全局外观状态，与 useTheme 同款模式：模块级 ref 单例 + 启动初始化 +
// localStorage appSettings 持久化。依赖方向单向：useTheme → useBrand（滤镜纯函数），
// 本模块不反向 import useTheme，主题深浅用 root.dataset.colorScheme 现场判定。

const activeBrandId = ref<BrandId>(DEFAULT_BRAND_ID)

// 与 useTheme 旧实现逐字一致：浅色主题下反相并 180° 色相回正，避免深底方章压在浅色界面上。
const LIGHT_INVERT_FILTER = 'invert(1) hue-rotate(180deg) saturate(.9) brightness(.96)'

/** 品牌标在当前主题下的滤镜：只有白线深底的弈章需要在浅色主题反相，位图彩色标恒不反相。 */
export function brandLogoFilter(isDark: boolean): string {
  return isDark || !getBrandPack(activeBrandId.value).needsLightInvert ? 'none' : LIGHT_INVERT_FILTER
}

function applyBrandVisuals(pack: BrandPack): void {
  const root = document.documentElement
  const schemeId = root.dataset.colorScheme
  const isDark = typeof schemeId === 'string' ? isDarkColorScheme(schemeId) : true
  root.style.setProperty('--brand-logo-filter', brandLogoFilter(isDark))
  let link = document.querySelector<HTMLLinkElement>("link[rel='icon']")
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  link.type = pack.faviconType
  link.href = pack.favicon
}

function setBrand(id: BrandId): void {
  activeBrandId.value = isBrandId(id) ? id : DEFAULT_BRAND_ID
  applyBrandVisuals(getBrandPack(activeBrandId.value))
}

export function useBrand() {
  const activePack = computed(() => getBrandPack(activeBrandId.value))

  return {
    activeBrandId,
    activePack,
    brandOptions: BRAND_PACKS,
    setBrand,
    initBrand
  }
}

/** 启动时调用（main.ts，initTheme 之后）：读 appSettings.brand 并应用滤镜与 favicon。 */
export function initBrand(): void {
  let saved: unknown = null
  const raw = localStorage.getItem('appSettings')
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as { brand?: unknown }
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) saved = parsed.brand
    } catch {
      saved = null
    }
  }
  setBrand(isBrandId(saved) ? saved : DEFAULT_BRAND_ID)
}
