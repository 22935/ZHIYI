import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { agentosApi } from '@/services/api/agentos'
import ResourceMarketplaceView from './ResourceMarketplaceView.vue'

const CatalogStub = {
  props: ['items', 'installations', 'loading', 'busy'],
  emits: ['install'],
  template: '<section><button data-testid="install-model.demo" @click="$emit(\'install\', items[0])">安装</button></section>'
}
const InstalledStub = { template: '<section data-testid="installed-panel" />' }
const layoutStub = { template: '<div><slot name="main" /></div>' }
const stubs = {
  WorkbenchLayout: layoutStub,
  WorkspacePageHero: { inheritAttrs: false, template: '<header><slot name="actions" /></header><h1>资源商店</h1>' },
  ResourceCenterNav: true,
  MarketplaceCatalogPanel: CatalogStub,
  MarketplaceInstalledPanel: InstalledStub,
  CustomResourceDialog: true,
  'el-icon': true
}
const router = async () => {
  const value = createRouter({ history: createMemoryHistory(), routes: [{ path: '/agentos/resources/store', component: ResourceMarketplaceView }] })
  await value.push('/agentos/resources/store')
  await value.isReady()
  return value
}

describe('ResourceMarketplaceView', () => {
  afterEach(() => vi.restoreAllMocks())

  it('installs a catalog entry through the backend and refreshes task state', async () => {
    const item = { catalogId: 'model.demo', kind: 'model_server', version: '1.0.0', displayName: 'Demo' }
    const listCatalog = vi.spyOn(agentosApi, 'listMarketplaceCatalog').mockResolvedValue({ items: [item] } as never)
    const listJobs = vi.spyOn(agentosApi, 'listMarketplaceInstallations').mockResolvedValue({ items: [] } as never)
    const install = vi.spyOn(agentosApi, 'installMarketplaceItem').mockResolvedValue({ jobId: 'job-1', status: 'queued' } as never)
    const testRouter = await router()
    const wrapper = mount(ResourceMarketplaceView, {
      global: { plugins: [testRouter], stubs }
    })
    await flushPromises()

    await wrapper.get('[data-testid="install-model.demo"]').trigger('click')
    await flushPromises()

    expect(install).toHaveBeenCalledWith({ catalogId: 'model.demo' })
    expect(listJobs).toHaveBeenCalledTimes(2)
    expect(wrapper.find('[data-testid="installed-panel"]').exists()).toBe(true)
    expect(listCatalog).toHaveBeenCalled()
  })
})
