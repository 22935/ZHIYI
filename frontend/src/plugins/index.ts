import { PluginUiExtensionRegistry } from './registry'
import { legalUiExtension } from './legal'

export const pluginUiExtensions = new PluginUiExtensionRegistry()
pluginUiExtensions.register(legalUiExtension)
