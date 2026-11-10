import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import ResourceOverviewView from './ResourceOverviewView.vue'
import ResourceManagementView from './ResourceManagementView.vue'
import ResourceMarketplaceView from './ResourceMarketplaceView.vue'

describe('resource center routes', () => {
  it('redirects the resource center entry to the overview page', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/agentos/resources', redirect: '/agentos/resources/overview' },
        { path: '/agentos/resources/overview', component: ResourceOverviewView },
        { path: '/agentos/resources/manage', component: ResourceManagementView },
        { path: '/agentos/resources/store', component: ResourceMarketplaceView }
      ]
    })

    await router.push('/agentos/resources')

    expect(router.currentRoute.value.path).toBe('/agentos/resources/overview')
  })
})
