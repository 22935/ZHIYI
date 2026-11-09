import { beforeEach, describe, expect, it } from 'vitest'
import { initBrand, brandLogoFilter, useBrand } from './useBrand'

// 品牌标三选一：持久化读取、非法值回退、favicon 跟随、per-pack 浅色反相。
// 滤镜口径：只有弈章（白线深底）在浅色主题反相，位图彩色标恒不反相。

const favicon = () => document.querySelector<HTMLLinkElement>("link[rel='icon']")

describe('useBrand', () => {
  beforeEach(() => {
    localStorage.clear()
    document.head.innerHTML = ''
    document.documentElement.removeAttribute('data-color-scheme')
    document.documentElement.style.removeProperty('--brand-logo-filter')
  })

  it('defaults to ember (current visuals unchanged) and rewrites the favicon', () => {
    document.head.innerHTML = '<link rel="icon" href="/logo-compact.svg" type="image/svg+xml">'
    initBrand()
    const { activePack } = useBrand()
    expect(activePack.value.id).toBe('ember')
    expect(favicon()?.getAttribute('href')).toBe('/logo.webp')
    expect(favicon()?.getAttribute('type')).toBe('image/webp')
  })

  it('creates the favicon link when the document has none', () => {
    initBrand()
    expect(favicon()).not.toBeNull()
    expect(favicon()?.getAttribute('href')).toBe('/logo.webp')
  })

  it('reads a persisted ink pack and points the favicon at the compact plate', () => {
    localStorage.setItem('appSettings', JSON.stringify({ brand: 'ink' }))
    initBrand()
    const { activePack } = useBrand()
    expect(activePack.value.id).toBe('ink')
    expect(favicon()?.getAttribute('href')).toBe('/logo-compact.svg')
    expect(favicon()?.getAttribute('type')).toBe('image/svg+xml')
  })

  it('falls back to ember on an unknown persisted pack', () => {
    localStorage.setItem('appSettings', JSON.stringify({ brand: 'nope' }))
    initBrand()
    const { activePack } = useBrand()
    expect(activePack.value.id).toBe('ember')
  })

  it('survives a corrupt appSettings payload', () => {
    localStorage.setItem('appSettings', '{broken')
    expect(() => initBrand()).not.toThrow()
    const { activePack } = useBrand()
    expect(activePack.value.id).toBe('ember')
  })

  it('inverts only the ink mark, and only under light schemes', () => {
    const root = document.documentElement
    const { setBrand } = useBrand()

    root.dataset.colorScheme = 'claude-warm'
    setBrand('ink')
    expect(root.style.getPropertyValue('--brand-logo-filter'))
      .toBe('invert(1) hue-rotate(180deg) saturate(.9) brightness(.96)')

    setBrand('ember')
    expect(root.style.getPropertyValue('--brand-logo-filter')).toBe('none')

    setBrand('wreath')
    expect(root.style.getPropertyValue('--brand-logo-filter')).toBe('none')

    root.dataset.colorScheme = 'codex-dark'
    setBrand('ink')
    expect(root.style.getPropertyValue('--brand-logo-filter')).toBe('none')
  })

  it('keeps the pure filter helper consistent with the pack flag', () => {
    const { setBrand } = useBrand()
    setBrand('ink')
    expect(brandLogoFilter(false)).not.toBe('none')
    expect(brandLogoFilter(true)).toBe('none')
    setBrand('ember')
    expect(brandLogoFilter(false)).toBe('none')
  })
})
