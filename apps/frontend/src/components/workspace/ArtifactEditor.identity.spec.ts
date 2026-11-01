import { mount, flushPromises } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { agentosApi } from '@/services/api/agentos'
import ArtifactEditor from './ArtifactEditor.vue'
afterEach(() => vi.restoreAllMocks())
it('a late body from A cannot overwrite B when the Artifact Editor instance is reused', async () => {
  let finish!: (value: any) => void
  vi.spyOn(agentosApi, 'getArtifactContent').mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    .mockResolvedValueOnce({ manifestId: 'b', mediaType: 'text/plain', content: 'B original artifact' })
  const wrapper = mount(ArtifactEditor, { props: { runId: 'a', available: true, entry: {
    entryId: 'shared-slot', kind: 'artifact', name: 'artifact.txt', group: 'output', displayOrder: 0, artifactId: 'a', contentRef: 'a', mediaType: 'text/plain'
  } }, global: { stubs: { 'el-icon': true } } })
  await wrapper.setProps({ runId: 'b', entry: { ...wrapper.props('entry'), artifactId: 'b', contentRef: 'b' } })
  await flushPromises(); expect(wrapper.text()).toContain('B original artifact')
  finish({ manifestId: 'a', mediaType: 'text/plain', content: 'A late artifact' }); await flushPromises()
  expect(wrapper.text()).toContain('B original artifact'); expect(wrapper.text()).not.toContain('A late artifact')
  wrapper.unmount()
})
