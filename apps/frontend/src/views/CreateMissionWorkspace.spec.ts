import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import CreateMissionView from './CreateMissionView.vue'
import { workflowApi } from '@/services/api/workflow'

const native = vi.hoisted(() => ({ openDirectory: vi.fn() }))
vi.mock('@/platform', () => ({ platform: { platform: 'desktop', openDirectory: native.openDirectory }, apiUrl: (path: string) => path }))
vi.mock('@/services/api/workflow', async original => {
  const actual = await original<typeof import('@/services/api/workflow')>()
  return { ...actual, workflowApi: { ...actual.workflowApi,
    startWorkflowAsync: vi.fn(), createMaterial: vi.fn(), reconcileMissionLaunch: vi.fn() } }
})

let binding: Record<string, unknown>
let wrapper: VueWrapper | undefined
const trusted = () => ({ workspaceId: 'ws-demo', workspaceRoot: 'C:/work/demo', grantId: 'server-grant', selected: true, revoked: false })
const clickPanel = async (text: string) => {
  const button = [...document.querySelectorAll<HTMLButtonElement>('.workspace-trust__panel button')]
    .find(item => item.textContent?.trim() === text)
  expect(button).toBeTruthy()
  button!.click(); await flushPromises()
}
const page = async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/new', name: 'CreateMission', component: CreateMissionView },
    { path: '/missions/:missionId', name: 'MissionWorkspace', component: { template: '<div />' } }
  ] })
  await router.push('/new'); await router.isReady()
  wrapper = mount(CreateMissionView, { attachTo: document.body, global: { plugins: [router], stubs: {
    WorkbenchLayout: { template: '<main><slot name="main" /></main>' }, PluginExtensionHost: true
  } } })
  await flushPromises()
  await wrapper.get('#mission-goal').setValue('在工作区生成验收文档')
  return { wrapper, router }
}

describe('Create Mission desktop workspace', () => {
  beforeEach(() => {
    localStorage.clear(); sessionStorage.clear(); vi.clearAllMocks()
    binding = { workspaceRoot: '', selected: false }
    vi.mocked(workflowApi.startWorkflowAsync).mockResolvedValue({ missionId: 'mission-demo', runId: 'run-demo', status: 'pending' } as any)
    vi.stubGlobal('fetch', vi.fn(async (url, init) => {
      if (String(url).endsWith('/workspaces/select')) {
        expect(JSON.parse(init!.body as string)).toEqual({ path: 'C:/work/demo' })
        binding = trusted()
      }
      return new Response(JSON.stringify(String(url).includes('/workspaces/') ? binding : { models: [] }), { status: 200 })
    }))
    native.openDirectory.mockResolvedValue('C:/work/demo')
  })
  afterEach(() => { wrapper?.unmount(); wrapper = undefined; document.body.innerHTML = ''; vi.unstubAllGlobals(); vi.restoreAllMocks() })

  it('requires choosing and trusting a directory, then rechecks it before launch', async () => {
    const { wrapper, router } = await page()
    expect(wrapper.get('.mission-workspace').text()).toContain('尚未选择工作区')
    expect(wrapper.get('.create-mission__submit').attributes('disabled')).toBeDefined()
    await wrapper.get('.workspace-trust__trigger').trigger('click')
    await clickPanel('选择工作区')
    expect(wrapper.get('[aria-label="当前工作区目录"]').text()).toBe('C:/work/demo')
    expect(wrapper.get('.create-mission__submit').attributes('disabled')).toBeDefined()
    await clickPanel('信任工作区')
    expect(wrapper.get('.create-mission__submit').attributes('disabled')).toBeUndefined()
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(workflowApi.startWorkflowAsync).toHaveBeenCalledOnce()
    expect(vi.mocked(fetch).mock.calls.filter(call => String(call[0]).endsWith('/workspaces/current'))).toHaveLength(2)
    const request = vi.mocked(workflowApi.startWorkflowAsync).mock.calls[0][0]
    expect(request.input).not.toHaveProperty('workspaceBinding')
    expect(router.currentRoute.value.params.missionId).toBe('mission-demo')
  })

  it('blocks launch if authorization was revoked after the directory was displayed', async () => {
    binding = trusted()
    const { wrapper } = await page()
    expect(wrapper.get('.create-mission__submit').attributes('disabled')).toBeUndefined()
    binding = { ...trusted(), revoked: true }
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(workflowApi.startWorkflowAsync).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('工作区授权已变化')
  })

  it('blocks direct form submission while a different directory is awaiting trust', async () => {
    binding = trusted()
    const { wrapper } = await page()
    await wrapper.get('.workspace-trust__trigger').trigger('click')
    await clickPanel('选择工作区')
    await wrapper.get('form').trigger('submit'); await flushPromises()
    expect(workflowApi.startWorkflowAsync).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先信任所选工作区')
  })
})
