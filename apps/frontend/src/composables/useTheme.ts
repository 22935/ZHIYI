import { ref } from 'vue'
import { getColorScheme, type ColorSchemeId } from '@/themes/presets'

const currentScheme = ref<ColorSchemeId>('codex-dark')
const CODEX_DARK_MIGRATION_KEY = 'theme.codex_dark_v1'
const PUBLIC_LIGHT_SCHEME_KEY = 'theme.public_light_scheme'

const DARK_SCHEMES: ColorSchemeId[] = ['codex-dark', 'one-dark-modern']

function isColorSchemeId(value: unknown): value is ColorSchemeId {
  return value === 'codex-dark' || value === 'one-dark-modern' || value === 'claude-warm' || value === 'tea-green' || value === 'blue-purple'
}

export function applyFontSize(fontSize: number): void {
  const normalizedSize = Math.min(20, Math.max(12, Number.isFinite(fontSize) ? fontSize : 14))
  const root = document.documentElement

  root.style.setProperty('--font-size-base', `${normalizedSize}px`)
  root.style.setProperty('--el-font-size-base', `${normalizedSize}px`)
  root.style.setProperty('--el-font-size-large', `${normalizedSize + 2}px`)
  root.style.setProperty('--el-font-size-small', `${Math.max(11, normalizedSize - 2)}px`)
  root.style.setProperty('--el-font-size-extra-small', `${Math.max(10, normalizedSize - 3)}px`)
  root.style.fontSize = `${normalizedSize}px`
}

function applySchemeVariables(schemeId: ColorSchemeId): void {
  const scheme = getColorScheme(schemeId)
  const root = document.documentElement
  for (const [key, value] of Object.entries(scheme.variables)) {
    root.style.setProperty(key, value)
  }
  // Keep the semantic layer derived from the active scheme, so legacy pages can
  // consume one vocabulary instead of baking a light-only surface into CSS.
  const isDark = DARK_SCHEMES.includes(scheme.id)
  const darkTopbarKeys = [
    '--app-topbar-bg',
    '--app-topbar-text',
    '--app-topbar-muted',
    '--app-topbar-border',
    '--app-topbar-hover',
    '--app-topbar-active',
    '--app-topbar-focus-ring',
    '--app-topbar-focus-border',
    '--app-topbar-input-bg',
    '--app-topbar-input-bg-hover',
    '--app-topbar-input-border',
    '--app-topbar-kbd-bg',
    '--app-topbar-logo-bg'
  ]
  if (isDark) {
    for (const key of darkTopbarKeys) {
      root.style.setProperty(key, scheme.variables[key])
    }
  } else {
    for (const key of darkTopbarKeys) {
      root.style.removeProperty(key)
    }
  }
  root.style.setProperty('--surface-solid', 'var(--bg-card)')
  root.style.setProperty('--surface-raised', 'color-mix(in srgb, var(--bg-card) 88%, transparent)')
  root.style.setProperty('--surface-subtle', 'color-mix(in srgb, var(--bg-panel) 80%, transparent)')
  root.style.setProperty('--surface-hover', 'var(--bg-panel)')
  root.style.setProperty('--overlay-backdrop', isDark ? 'rgba(8, 9, 18, 0.72)' : 'rgba(31, 30, 29, 0.42)')
  root.style.setProperty('--shadow-color', isDark ? 'rgba(8, 9, 18, 0.22)' : 'rgba(31, 30, 29, 0.08)')
  root.style.setProperty('--on-primary', '#FFFFFF')
  root.style.setProperty('--border-color', 'var(--border-light)')
  root.style.setProperty('--color-primary', 'var(--primary-color)')
  root.style.setProperty('--success-fade', 'color-mix(in srgb, var(--success) 12%, transparent)')
  root.style.setProperty('--warning-fade', 'color-mix(in srgb, var(--warning) 12%, transparent)')
  root.style.setProperty('--danger-fade', 'color-mix(in srgb, var(--danger) 12%, transparent)')
  root.style.setProperty('--info-fade', 'color-mix(in srgb, var(--info) 12%, transparent)')
  // Element Plus keeps its own palette. Without these aliases, a palette switch
  // can leave selects, popovers, and disabled fields on the previous scheme.
  root.style.setProperty('--el-bg-color', 'var(--bg-card)')
  root.style.setProperty('--el-bg-color-page', 'var(--bg-app)')
  root.style.setProperty('--el-bg-color-overlay', 'var(--bg-panel)')
  root.style.setProperty('--el-fill-color-blank', 'var(--bg-card)')
  root.style.setProperty('--el-fill-color', 'var(--bg-panel)')
  root.style.setProperty('--el-fill-color-light', 'var(--bg-input)')
  root.style.setProperty('--el-fill-color-lighter', 'var(--bg-panel)')
  root.style.setProperty('--el-fill-color-extra-light', 'var(--bg-input)')
  root.style.setProperty('--el-fill-color-dark', 'var(--bg-input)')
  root.style.setProperty('--el-fill-color-darker', 'var(--bg-app)')
  root.style.setProperty('--el-fill-color-disabled', 'var(--bg-input)')
  root.style.setProperty('--el-text-color-primary', 'var(--text-primary)')
  root.style.setProperty('--el-text-color-regular', 'var(--text-regular)')
  root.style.setProperty('--el-text-color-secondary', 'var(--text-secondary)')
  root.style.setProperty('--el-text-color-placeholder', 'var(--text-muted)')
  root.style.setProperty('--el-text-color-disabled', 'var(--text-disabled)')
  root.style.setProperty('--el-border-color', 'var(--border-light)')
  root.style.setProperty('--el-border-color-light', 'var(--border-light)')
  root.style.setProperty('--el-border-color-lighter', 'var(--border-light)')
  root.style.setProperty('--el-border-color-extra-light', 'var(--border-light)')
  root.style.setProperty('--el-border-color-dark', 'var(--border-hover)')
  root.style.setProperty('--el-border-color-darker', 'var(--border-hover)')
  root.style.setProperty('--el-mask-color', 'var(--overlay-backdrop)')
  for (const status of ['success', 'warning', 'danger', 'info']) {
    root.style.setProperty(`--el-color-${status}`, `var(--${status})`)
    root.style.setProperty(`--el-color-${status}-light-3`, `color-mix(in srgb, var(--${status}) 72%, var(--bg-card))`)
    root.style.setProperty(`--el-color-${status}-light-5`, `color-mix(in srgb, var(--${status}) 52%, var(--bg-card))`)
    root.style.setProperty(`--el-color-${status}-light-7`, `color-mix(in srgb, var(--${status}) 30%, var(--bg-card))`)
    root.style.setProperty(`--el-color-${status}-light-8`, `color-mix(in srgb, var(--${status}) 20%, var(--bg-card))`)
    root.style.setProperty(`--el-color-${status}-light-9`, `color-mix(in srgb, var(--${status}) 12%, var(--bg-card))`)
    root.style.setProperty(`--el-color-${status}-dark-2`, `color-mix(in srgb, var(--${status}) 82%, #000000)`)
  }
  // 品牌方章为深底浅线；浅色主题统一反相为浅底深线，避免深色块压在浅色界面上。
  // 反相后再做 180° 色相回正，使底色贴近各浅色方案的 --bg-app 而非发黄。
  root.style.setProperty('--brand-logo-filter', isDark ? 'none' : 'invert(1) hue-rotate(180deg) saturate(.9)')
  root.dataset.colorScheme = scheme.id
  root.style.colorScheme = isDark ? 'dark' : 'light'
  document.body.style.backgroundImage = scheme.bodyBackground
  document.body.style.backgroundColor = scheme.variables['--bg-app']
  if (!isDark) localStorage.setItem(PUBLIC_LIGHT_SCHEME_KEY, scheme.id)
  currentScheme.value = scheme.id
}

export function useTheme() {
  function applyColorScheme(schemeId: ColorSchemeId): void {
    applySchemeVariables(schemeId)
  }

  function setPersistedColorScheme(schemeId: ColorSchemeId): void {
    applySchemeVariables(schemeId)

    let settings: Record<string, unknown> = {}
    const saved = localStorage.getItem('appSettings')
    if (saved) {
      try {
        const parsed = JSON.parse(saved)
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) settings = parsed as Record<string, unknown>
      } catch {
        settings = {}
      }
    }
    settings.colorScheme = schemeId
    localStorage.setItem('appSettings', JSON.stringify(settings))
  }

  function toggleColorScheme(): void {
    if (currentScheme.value === 'codex-dark') {
      const savedLightScheme = localStorage.getItem(PUBLIC_LIGHT_SCHEME_KEY)
      const nextLightScheme = isColorSchemeId(savedLightScheme) && savedLightScheme !== 'codex-dark'
        ? savedLightScheme
        : 'blue-purple'
      setPersistedColorScheme(nextLightScheme)
      return
    }
    setPersistedColorScheme('codex-dark')
  }

  return { currentScheme, applyColorScheme, setPersistedColorScheme, toggleColorScheme }
}

export function initTheme(): void {
  const saved = localStorage.getItem('appSettings')
  if (!saved) {
    localStorage.setItem(CODEX_DARK_MIGRATION_KEY, '1')
    applySchemeVariables('codex-dark')
    applyFontSize(14)
    return
  }
  try {
    const parsed = JSON.parse(saved)
    if (!localStorage.getItem(CODEX_DARK_MIGRATION_KEY)) {
      parsed.colorScheme = 'codex-dark'
      localStorage.setItem('appSettings', JSON.stringify(parsed))
      localStorage.setItem(CODEX_DARK_MIGRATION_KEY, '1')
    }
    const schemeId: ColorSchemeId = parsed.colorScheme || 'codex-dark'
    applySchemeVariables(schemeId)
    applyFontSize(Number(parsed.fontSize) || 14)
  } catch {
    applySchemeVariables('codex-dark')
    applyFontSize(14)
  }
}

export { type ColorSchemeId }
