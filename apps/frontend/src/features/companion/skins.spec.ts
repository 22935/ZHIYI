import { describe, expect, it } from 'vitest'
import { BUILTIN_SKINS, SkinRegistry } from './skins'
import type { CompanionState, SkinManifest } from './types'

const allStates: CompanionState[] = [
  'idle', 'listening', 'thinking', 'working', 'happy', 'alert', 'sleeping', 'error'
]

describe('companion skin registry', () => {
  it('declares a complete state map for every built-in skin', () => {
    for (const skin of BUILTIN_SKINS) {
      expect(allStates.every(state => typeof skin.stateMap[state] === 'string')).toBe(true)
    }
  })

  it('falls back to the static skin for unknown ids', () => {
    const registry = new SkinRegistry()
    expect(registry.resolve('missing').id).toBe('companion-static')
    expect(registry.resolve(null).rendererType).toBe('inline-svg')
  })

  it('gives the animated skin a fallback target', () => {
    const registry = new SkinRegistry()
    const animated = registry.resolve('companion-grok')
    expect(animated.rendererType).toBe('grok-svg')
    expect(animated.fallbackSkinId).toBe('companion-static')
  })

  it('rejects duplicate ids and incomplete state maps', () => {
    const registry = new SkinRegistry()
    expect(() => registry.register(BUILTIN_SKINS[0])).toThrow(/Duplicate/)
    const broken: SkinManifest = {
      id: 'broken', version: '1', label: 'broken', rendererType: 'inline-svg',
      stateMap: { idle: 'idle' } as SkinManifest['stateMap'], fallbackSkinId: null
    }
    expect(() => registry.register(broken)).toThrow(/stateMap/)
  })
})
