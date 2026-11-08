import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import CompanionCustomizer from './CompanionCustomizer.vue'
import { DEFAULT_CUSTOMIZATION, DIY_PRESETS } from '@/features/companion/customization'
import type { VoiceOption } from '@/features/companion/voice'

const VOICES: VoiceOption[] = [
  { uri: 'zh-cn-xiaoxiao', name: '晓晓', lang: 'zh-CN', local: true },
  { uri: 'zh-cn-yunxi', name: '云希', lang: 'zh-CN', local: false }
]

const build = (voices: VoiceOption[] = VOICES) => mount(CompanionCustomizer, {
  props: {
    value: { ...DEFAULT_CUSTOMIZATION, voice: { ...DEFAULT_CUSTOMIZATION.voice }, lines: [] },
    voices
  }
})

describe('CompanionCustomizer', () => {
  it('exposes name, shape, colors, image, lines, voice knobs and export/import', () => {
    const wrapper = build()
    for (const id of [
      'companion-diy-name', 'companion-diy-shape', 'companion-diy-primary',
      'companion-diy-accent', 'companion-diy-background', 'companion-diy-image',
      'companion-diy-lines', 'companion-diy-voice', 'companion-diy-audition',
      'companion-diy-rate', 'companion-diy-pitch',
      'companion-diy-volume', 'companion-diy-motion', 'companion-diy-share',
      'companion-diy-save', 'companion-diy-reset'
    ]) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(true)
    }
    expect(wrapper.findAll(`[data-testid^="companion-diy-preset-"]`)).toHaveLength(DIY_PRESETS.length)
    wrapper.unmount()
  })

  it('lists system voices, previews the pick and auditions it', async () => {
    const wrapper = build()
    const select = wrapper.find('[data-testid="companion-diy-voice"]')
    // 「自动」+ 两条系统声线；在线声线要标出来，用户才知道断网会掉。
    expect(select.findAll('option')).toHaveLength(VOICES.length + 1)
    expect(select.text()).toContain('云希')
    expect(select.text()).toContain('· 在线')

    await select.setValue('zh-cn-yunxi')
    await nextTick()
    const previews = wrapper.emitted('preview') ?? []
    expect((previews[previews.length - 1] as unknown[])[0])
      .toMatchObject({ voice: { voiceURI: 'zh-cn-yunxi' } })

    await wrapper.find('[data-testid="companion-diy-audition"]').trigger('click')
    const auditions = wrapper.emitted('audition') ?? []
    expect(auditions).toHaveLength(1)
    expect((auditions[0] as unknown[])[0]).toMatchObject({ voiceURI: 'zh-cn-yunxi' })
    wrapper.unmount()
  })

  it('stores「自动」as null and admits when the host offers no voices', async () => {
    const wrapper = build([])
    expect(wrapper.find('[data-testid="companion-diy-voice-empty"]').exists()).toBe(true)
    await wrapper.find('[data-testid="companion-diy-voice"]').setValue('')
    await nextTick()
    await wrapper.find('[data-testid="companion-diy-save"]').trigger('click')
    const value = (wrapper.emitted('apply')?.[0] as unknown[])[0] as Record<string, unknown>
    expect((value.voice as { voiceURI: string | null }).voiceURI).toBeNull()
    wrapper.unmount()
  })

  it('previews name edits live and applies them on save', async () => {
    const wrapper = build()
    await wrapper.find('[data-testid="companion-diy-name"]').setValue('团子')
    await nextTick()
    const previews = wrapper.emitted('preview') ?? []
    expect(previews.length).toBeGreaterThan(0)
    expect((previews[previews.length - 1] as unknown[])[0]).toMatchObject({ name: '团子' })

    await wrapper.find('[data-testid="companion-diy-save"]').trigger('click')
    const applied = wrapper.emitted('apply') ?? []
    expect(applied).toHaveLength(1)
    expect((applied[0] as unknown[])[0]).toMatchObject({ name: '团子' })
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('applies a preset and sanitizes custom lines on save', async () => {
    const wrapper = build()
    await wrapper.find('[data-testid="companion-diy-preset-grape"]').trigger('click')
    await wrapper.find('[data-testid="companion-diy-lines"]').setValue('第一句\n\n  第二句  ')
    await nextTick()
    await wrapper.find('[data-testid="companion-diy-save"]').trigger('click')
    const value = (wrapper.emitted('apply')?.[0] as unknown[])[0] as Record<string, unknown>
    expect(value.shape).toBe('star')
    expect(value.primary).toBe('#a98bff')
    expect(value.lines).toEqual(['第一句', '第二句'])
    wrapper.unmount()
  })

  it('exports a shareable JSON and rejects malformed imports', async () => {
    const wrapper = build()
    await wrapper.find('[data-testid="companion-diy-export"]').trigger('click')
    await nextTick()
    const share = wrapper.find('[data-testid="companion-diy-share"]')
    expect((share.element as HTMLTextAreaElement).value).toContain('"version"')

    await share.setValue('{not json')
    await wrapper.find('[data-testid="companion-diy-import"]').trigger('click')
    await nextTick()
    expect(wrapper.find('[data-testid="companion-diy-image-hint"]').text()).toContain('读不出来')
    expect(wrapper.emitted('apply')).toBeUndefined()
    wrapper.unmount()
  })
})
