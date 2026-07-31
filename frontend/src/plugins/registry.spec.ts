import { describe, expect, it } from 'vitest'
import { PluginUiExtensionRegistry } from './registry'
import workbenchViewSource from '../views/AcgVisualizationView.vue?raw'

describe('PluginUiExtensionRegistry', () => {
  it('registers and resolves multiple compile-time extensions without assuming one plugin', () => {
    const registry = new PluginUiExtensionRegistry()
    registry.register({ pluginId: 'plugin.a', displayName: 'A' })
    registry.register({ pluginId: 'plugin.b', displayName: 'B' })

    expect(registry.resolve(['plugin.b', 'missing', 'plugin.a']).map(item => item.pluginId))
      .toEqual(['plugin.b', 'plugin.a'])
    expect(registry.all()).toHaveLength(2)
  })

  it('rejects duplicate plugin IDs', () => {
    const registry = new PluginUiExtensionRegistry()
    registry.register({ pluginId: 'plugin.a', displayName: 'A' })
    expect(() => registry.register({ pluginId: 'plugin.a', displayName: 'Duplicate' }))
      .toThrow('duplicate UI extension')
  })

  it('keeps the generic workbench independent from Legal implementation modules', () => {
    expect(workbenchViewSource).not.toMatch(
      /plugins\/legal|LegalTaskExtension|LegalStrategyPanel|LegalArtifactRenderer/
    )
  })
})
