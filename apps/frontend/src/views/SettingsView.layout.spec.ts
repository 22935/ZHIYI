import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const settingsViewSource = readFileSync(resolve(process.cwd(), 'src/views/SettingsView.vue'), 'utf8')
const routerSource = readFileSync(resolve(process.cwd(), 'src/router/index.ts'), 'utf8')

describe('SettingsView desktop layout', () => {
  it('uses a wider content canvas to avoid oversized side margins', () => {
    expect(settingsViewSource).toContain('width: min(100%, 1400px)')
  })
})

describe('SettingsView shell integration', () => {
  it('uses a subtle neutral fill for the selected settings nav item (no accent bar, no primary tint)', () => {
    // 选中态 = VS Code 列表选中式：柔和中性圆角底 + 文字提亮，无强调色、无竖条。
    const activeBlock = settingsViewSource.match(/\.settings-nav-item\.active\s*\{[^}]*\}/)?.[0] ?? ''
    expect(activeBlock).toContain('color-mix(in srgb, var(--text-primary)')
    expect(activeBlock).not.toContain('var(--primary-color)')
    expect(settingsViewSource).not.toMatch(/\.settings-nav-item\.active::before/)
  })

  it('renders under the shared top bar (its drag region moves the frameless window)', () => {
    // /settings 曾带 hideNavigation，把 AppTopBar（唯一成熟拖拽区）整体卸载，
    // 无边框窗口在设置页拖不动；页面内自建拖拽区两轮尝试均无效，
    // 已改回公用顶栏。此断言防止 hideNavigation 回归。
    const routeBlock = routerSource.slice(
      routerSource.indexOf("path: '/settings'"),
      routerSource.indexOf("path: '/rag'")
    )
    expect(routeBlock.length).toBeGreaterThan(0)
    expect(routeBlock).not.toMatch(/hideNavigation:\s*true/)
  })

  it('keeps sidebar entries unique per settings tab', () => {
    const navSource = settingsViewSource.slice(
      settingsViewSource.indexOf('const settingsSections'),
      settingsViewSource.indexOf('const THEME_TONES')
    )
    const ids = Array.from(navSource.matchAll(/id: '([a-z]+)'/g), match => match[1])
    expect(ids.length).toBeGreaterThan(0)
    expect(new Set(ids).size).toBe(ids.length)
  })
})

describe('SettingsView brand picker', () => {
  it('offers the three brand packs in the appearance tab and applies on click', () => {
    // Logo 三选卡与主题卡片同构：点击即预览生效（滤镜 + favicon），保存设置统一落盘。
    expect(settingsViewSource).toContain('const { brandOptions, setBrand } = useBrand()')
    expect(settingsViewSource).toContain('v-for="pack in brandOptions"')
    expect(settingsViewSource).toContain('@click="settings.brand = pack.id; applyBrand()"')
  })

  it('defaults the brand to ember and persists it inside appSettings', () => {
    // 默认 ember = 2026-11-09 既有视觉零变化；brand 随整份 appSettings 落盘，
    // 启动链路由 main.ts 的 initBrand 消费。
    expect(settingsViewSource).toContain('brand: DEFAULT_BRAND_ID')
    expect(settingsViewSource).toContain("localStorage.setItem('appSettings', JSON.stringify(settings.value))")
  })
})
