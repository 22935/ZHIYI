import type { PluginUiExtension } from '@/features/acg/workbench'

export class PluginUiExtensionRegistry {
  private readonly extensions = new Map<string, PluginUiExtension>()

  register(extension: PluginUiExtension): void {
    if (this.extensions.has(extension.pluginId)) {
      throw new Error(`duplicate UI extension: ${extension.pluginId}`)
    }
    this.extensions.set(extension.pluginId, extension)
  }

  get(pluginId: string): PluginUiExtension | undefined {
    return this.extensions.get(pluginId)
  }

  resolve(pluginIds: readonly string[]): PluginUiExtension[] {
    return pluginIds
      .map(pluginId => this.extensions.get(pluginId))
      .filter((item): item is PluginUiExtension => Boolean(item))
  }

  all(): PluginUiExtension[] {
    return Array.from(this.extensions.values())
  }
}
