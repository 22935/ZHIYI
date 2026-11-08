import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { agentosApi, type WorkspaceEntry } from '@/services/api/agentos'
import ArtifactEditor from './ArtifactEditor.vue'

const entry = (overrides: Partial<WorkspaceEntry> = {}): WorkspaceEntry => ({
  entryId: 'task:capacity:primary', kind: 'artifact', name: 'capacity.md', group: 'steps', displayOrder: 0,
  semanticTaskKey: 'capacity', artifactKey: 'primary', artifactId: 'artifact_1', contentRef: 'manifest_1',
  mediaType: 'text/markdown', identityQuality: 'canonical', ...overrides
})

const mountEditor = (overrides: Partial<WorkspaceEntry> = {}, props: { available?: boolean; runId?: string | null } = {}) => mount(ArtifactEditor, {
  props: { entry: entry(overrides), runId: props.runId === undefined ? 'run_1' : props.runId, available: props.available ?? true },
  global: { stubs: { 'el-icon': true } }
})

describe('ArtifactEditor', () => {
  afterEach(() => vi.restoreAllMocks())

  it('loads markdown only after the artifact editor is mounted and renders it', async () => {
    vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'text/markdown', content: '# Read me\n\n**ready**', manifestId: 'manifest_1' })
    const wrapper = mountEditor()
    await flushPromises()
    expect(agentosApi.getArtifactContent).toHaveBeenCalledWith('run_1', 'manifest_1', expect.anything())
    expect(wrapper.find('.markdown-body').html()).toContain('<h1>Read me</h1>')
    expect(wrapper.find('.markdown-body').html()).toContain('<strong>ready</strong>')
  })

  it('formats application/json as structured readable text', async () => {
    vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'application/json', content: '{"ok":true,"count":2}', manifestId: 'manifest_1' })
    const wrapper = mountEditor({ mediaType: 'application/json' })
    await flushPromises()
    expect(wrapper.find('.json-body').text()).toContain('ok')
    expect(wrapper.find('.json-body').text()).toContain('true')
    expect(wrapper.find('.json-body pre').exists()).toBe(false)
    expect(wrapper.find('.json-body').text()).toContain('count')
    expect(wrapper.find('.json-body').text()).toContain('2')
  })

  it('renders text/plain without interpreting markup', async () => {
    vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'text/plain', content: '# not markdown', manifestId: 'manifest_1' })
    const wrapper = mountEditor({ mediaType: 'text/plain' })
    await flushPromises()
    expect(wrapper.find('.text-body').text()).toBe('# not markdown')
    expect(wrapper.find('.markdown-body').exists()).toBe(false)
  })

  it('keeps loaded content when the projection replaces an unchanged entry', async () => {
    const request = vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'text/markdown', content: '# Ready', manifestId: 'manifest_1' })
    const wrapper = mountEditor()
    await flushPromises()
    await wrapper.setProps({ entry: entry() })
    await flushPromises()
    expect(request).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.markdown-body').text()).toContain('Ready')
    await wrapper.setProps({ entry: entry({ contentRef: 'manifest_2', artifactId: 'artifact_2' }) })
    await flushPromises()
    expect(request).toHaveBeenCalledTimes(2)
  })

  it('normalizes media types with parameters before choosing a readable renderer', async () => {
    vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'text/markdown; charset=utf-8', content: '# Read me', manifestId: 'manifest_1' })
    const wrapper = mountEditor({ mediaType: 'text/markdown; charset=utf-8' })
    await flushPromises()
    expect(wrapper.find('.markdown-body').exists()).toBe(true)
    expect(wrapper.find('.markdown-body').text()).toContain('Read me')
  })

  it('keeps unknown media types in a generic preview', async () => {
    const getContent = vi.spyOn(agentosApi, 'getArtifactContent')
    vi.spyOn(agentosApi, 'getArtifactDetail').mockResolvedValue({ mediaType: 'application/pdf', manifestId: 'manifest_1', byteLength: 12 })
    const wrapper = mountEditor({ mediaType: 'application/pdf' })
    await flushPromises()
    expect(wrapper.text()).toContain('Generic Artifact Preview')
    expect(wrapper.text()).toContain('application/pdf')
    expect(wrapper.find('button').text()).toContain('在图中定位')
    expect(getContent).not.toHaveBeenCalled()
  })

  it('shows Not available in this Run and never fetches another Run body', async () => {
    const getContent = vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'text/plain', content: 'wrong run', manifestId: 'manifest_1' })
    const wrapper = mountEditor({}, { available: false, runId: 'run_historical' })
    await flushPromises()
    expect(wrapper.text()).toContain('Not available in this Run')
    expect(getContent).not.toHaveBeenCalled()
  })

  it('disables graph positioning for legacy identity', async () => {
    vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'text/plain', content: 'legacy', manifestId: 'manifest_legacy' })
    const wrapper = mountEditor({ entryId: 'legacy:manifest_legacy', identityQuality: 'legacy', semanticTaskKey: null, artifactId: null, contentRef: 'manifest_legacy' })
    await flushPromises()
    expect(wrapper.find('button').attributes('disabled')).toBeDefined()
  })

  it('emits locateGraph only from a proven canonical artifact', async () => {
    vi.spyOn(agentosApi, 'getArtifactContent').mockResolvedValue({ mediaType: 'text/plain', content: 'ready', manifestId: 'manifest_1' })
    const wrapper = mountEditor()
    await flushPromises()
    await wrapper.find('button').trigger('click')
    expect(wrapper.emitted('locateGraph')).toHaveLength(1)
  })

  it('rebinds the same stable entry to a different Run', async () => {
    const getContent = vi.spyOn(agentosApi, 'getArtifactContent')
      .mockResolvedValueOnce({ mediaType: 'text/plain', content: 'run one', manifestId: 'manifest_1' })
      .mockResolvedValueOnce({ mediaType: 'text/plain', content: 'run two', manifestId: 'manifest_2' })
    const wrapper = mountEditor()
    await flushPromises()
    await wrapper.setProps({ runId: 'run_2' })
    await flushPromises()
    expect(getContent).toHaveBeenLastCalledWith('run_2', 'manifest_1', expect.anything())
    expect(wrapper.text()).toContain('run two')
  })
})
