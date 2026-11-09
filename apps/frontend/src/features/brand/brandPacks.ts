// 品牌标三选一的资产清单。三套标的现役来源：
// - ember（焰标，默认）：2026-11-09 提交 9f96644d 换上的橙色三角标，沿用 public 根路径
//   （/logo.svg、/logo-mark.svg、/logo.webp），保证默认视觉与既有部署逐字节一致。
// - ink（弈章）：深底白线矢量方章，真源取回自提交 d8d77f99 的 logo.svg / logo-mark.svg，
//   favicon 沿用像素网格对齐的 /logo-compact.svg，桌面端 icon.ico 也是这一套。
// - wreath（花环）：2026-11-08 之前退役的旧品牌标，从提交 73d172aa 的 logo.webp 取回。
// ACG 子系统专用标 /acglogo.* 不在此列（brand-spec.md：独立品牌资产，不参与主标适配）。

export type BrandId = 'ember' | 'ink' | 'wreath'

export interface BrandPack {
  id: BrandId
  label: string
  description: string
  /** 大尺寸展示：顶栏、加载态等 */
  main: string
  /** 低干扰水印：空态、编辑器空态、Chat hero */
  mark: string
  /** 落地页大图 */
  landing: string
  /** 浏览器标签页图标（跟随所选标；桌面原生 icon.ico 不跟随） */
  favicon: string
  faviconType: 'image/svg+xml' | 'image/webp'
  /** 浅色主题下是否需要反相适配：仅白线深底的弈章需要，位图彩色标反相会毁色 */
  needsLightInvert: boolean
}

export const BRAND_PACKS: BrandPack[] = [
  {
    id: 'ember',
    label: '焰标',
    description: '橙色三角焰形标，当前默认品牌标。',
    main: '/logo.svg',
    mark: '/logo-mark.svg',
    landing: '/logo.webp',
    favicon: '/logo.webp',
    faviconType: 'image/webp',
    needsLightInvert: false
  },
  {
    id: 'ink',
    label: '弈章',
    description: '深底白线矢量方章，与桌面应用图标同源。',
    main: '/brand/ink/logo.svg',
    mark: '/brand/ink/logo-mark.svg',
    landing: '/brand/ink/logo.svg',
    favicon: '/logo-compact.svg',
    faviconType: 'image/svg+xml',
    needsLightInvert: true
  },
  {
    id: 'wreath',
    label: '花环',
    description: '初代花环标，果实与新芽环绕成环。',
    main: '/brand/wreath/logo.webp',
    mark: '/brand/wreath/logo.webp',
    landing: '/brand/wreath/logo.webp',
    favicon: '/brand/wreath/logo.webp',
    faviconType: 'image/webp',
    needsLightInvert: false
  }
]

export const DEFAULT_BRAND_ID: BrandId = 'ember'

const BRAND_IDS: BrandId[] = ['ember', 'ink', 'wreath']

export function isBrandId(value: unknown): value is BrandId {
  return typeof value === 'string' && BRAND_IDS.includes(value as BrandId)
}

export function getBrandPack(id: BrandId): BrandPack {
  return BRAND_PACKS.find((pack) => pack.id === id) || BRAND_PACKS[0]
}
