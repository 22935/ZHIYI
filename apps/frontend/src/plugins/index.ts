import { PluginUiExtensionRegistry } from './registry'

export const pluginUiExtensions = new PluginUiExtensionRegistry()
pluginUiExtensions.register({
  pluginId: 'workspace',
  displayName: '本机工作区开发与测试',
  createDefaults: () => ({
    expectedArtifacts: ['开发与测试报告（含文件变更、pytest 结果与执行收据）'],
    webSearchEnabled: false
  })
})
