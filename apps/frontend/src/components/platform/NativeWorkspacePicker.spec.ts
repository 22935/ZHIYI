import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import NativeWorkspacePicker from './NativeWorkspacePicker.vue'

const mocks = vi.hoisted(() => ({
  openDirectory: vi.fn()
}))

vi.mock('@/platform', () => ({
  LOCAL_REQUEST_HEADERS: { 'X-Zhiyi-Local-Request': '1' },
  platform: { platform: 'desktop', openDirectory: mocks.openDirectory },
  apiUrl: (path: string) => path
}))

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)

const unselected = { workspaceRoot: '', selected: false, scope: 'unselected' }
const trusted = {
  workspaceRoot: 'C:\\work\\demo',
  workspaceId: 'ws_demo',
  grantId: 'wgrant_demo',
  revoked: false,
  risk: 'Host-approved project commands run with the host user permissions; this is not an OS sandbox.'
}

const response = (body: unknown, ok = true, status = 200) =>
  ({ ok, status, json: vi.fn(async () => body) }) as unknown as Response

const triggerButton = (wrapper: VueWrapper) => wrapper.get('.workspace-trust__trigger')

const panelButton = (selector: string): HTMLButtonElement | null =>
  document.querySelector<HTMLButtonElement>(`.workspace-trust__panel ${selector}`)

describe('NativeWorkspacePicker', () => {
  let wrapper: VueWrapper | null = null

  beforeEach(() => {
    vi.clearAllMocks()
    fetchMock.mockReset()
    mocks.openDirectory.mockReset()
    document.body.innerHTML = ''
    localStorage.clear()
  })

  afterEach(() => {
    wrapper?.unmount()
    wrapper = null
    document.body.innerHTML = ''
  })

  it('opens a compact trust panel with select and trust actions', async () => {
    fetchMock.mockResolvedValueOnce(response(unselected))
    wrapper = mount(NativeWorkspacePicker)
    await flushPromises()

    expect(triggerButton(wrapper).text()).toContain('工作区未信任')
    expect(triggerButton(wrapper).attributes('aria-expanded')).toBe('false')

    await triggerButton(wrapper).trigger('click')
    await nextTick()

    expect(triggerButton(wrapper).attributes('aria-expanded')).toBe('true')
    const panel = document.querySelector('.workspace-trust__panel')
    expect(panel).not.toBeNull()
    expect(panel?.textContent).toContain('本机工作区')
    expect(panel?.textContent).toContain('尚未选择工作区')
    expect(panel?.textContent).toContain('选择工作区')
    expect(panel?.textContent).toContain('信任工作区')

    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await nextTick()
    expect(document.querySelector('.workspace-trust__panel')).toBeNull()
    expect(triggerButton(wrapper).attributes('aria-expanded')).toBe('false')
  })

  it('selects a directory, then trusts it from the expanded panel', async () => {
    fetchMock.mockResolvedValueOnce(response(unselected))
    wrapper = mount(NativeWorkspacePicker)
    await flushPromises()

    await triggerButton(wrapper).trigger('click')
    await nextTick()

    mocks.openDirectory.mockResolvedValueOnce('C:\\work\\demo')
    panelButton('.workspace-trust__action')?.click()
    await flushPromises()

    expect(triggerButton(wrapper).text()).toContain('待信任 · demo')
    expect(document.querySelector('.workspace-trust__panel')?.textContent).toContain('待信任目录')
    expect(panelButton('.workspace-trust__action.is-primary')?.disabled).toBe(false)

    fetchMock.mockResolvedValueOnce(response(trusted))
    panelButton('.workspace-trust__action.is-primary')?.click()
    await flushPromises()

    expect(document.querySelector('.workspace-trust__panel')).toBeNull()
    expect(triggerButton(wrapper).text()).toContain('已信任 · demo')
    const selectCall = fetchMock.mock.calls.find(([url]) => String(url).includes('/workspaces/select'))
    expect(selectCall).toBeTruthy()
    expect(JSON.parse(String(selectCall?.[1]?.body))).toEqual({ path: 'C:\\work\\demo' })
  })

  it('can pick and trust a directory in one action', async () => {
    fetchMock.mockResolvedValueOnce(response(unselected))
    wrapper = mount(NativeWorkspacePicker)
    await flushPromises()

    await triggerButton(wrapper).trigger('click')
    await nextTick()

    mocks.openDirectory.mockResolvedValueOnce('C:\\work\\direct')
    fetchMock.mockResolvedValueOnce(response({ ...trusted, workspaceRoot: 'C:\\work\\direct' }))
    panelButton('.workspace-trust__action.is-primary')?.click()
    await flushPromises()

    expect(triggerButton(wrapper).text()).toContain('已信任 · direct')
    expect(mocks.openDirectory).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledWith('/api/agentos/v2/workspaces/select', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ path: 'C:\\work\\direct' })
    }))
  })

  it('cancels a pending directory selection without changing the trusted workspace', async () => {
    fetchMock.mockResolvedValueOnce(response(trusted))
    wrapper = mount(NativeWorkspacePicker)
    await flushPromises()

    await triggerButton(wrapper).trigger('click')
    await nextTick()
    mocks.openDirectory.mockResolvedValueOnce('C:\\work\\other')
    panelButton('.workspace-trust__action')?.click()
    await flushPromises()
    expect(triggerButton(wrapper).text()).toContain('待信任 · other')

    panelButton('.workspace-trust__revoke')?.click()
    await flushPromises()

    expect(triggerButton(wrapper).text()).toContain('已信任 · demo')
    expect(document.querySelector('.workspace-trust__panel')?.textContent).not.toContain('待信任目录')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('revokes trust from the expanded panel', async () => {
    fetchMock.mockResolvedValueOnce(response(trusted))
    wrapper = mount(NativeWorkspacePicker)
    await flushPromises()
    expect(triggerButton(wrapper).text()).toContain('已信任 · demo')

    await triggerButton(wrapper).trigger('click')
    await nextTick()
    expect(panelButton('.workspace-trust__revoke')).not.toBeNull()

    fetchMock.mockResolvedValueOnce(response({ ...trusted, revoked: true }))
    panelButton('.workspace-trust__revoke')?.click()
    await flushPromises()

    expect(document.querySelector('.workspace-trust__panel')).toBeNull()
    expect(triggerButton(wrapper).text()).toContain('工作区未信任')
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/agentos/v2/workspaces/ws_demo/revoke',
      expect.objectContaining({ method: 'POST' })
    )
  })
})
