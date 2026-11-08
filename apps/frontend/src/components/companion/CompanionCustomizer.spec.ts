import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it } from 'vitest'
import CompanionCustomizer from './CompanionCustomizer.vue'
import { DEFAULT_CUSTOMIZATION, DIY_PRESETS } from '@/features/companion/customization'

const build = () => mount(CompanionCustomizer, {
  props: { value: { ...DEFAULT_CUSTOMIZATION, voice: { ...DEFAULT_CUSTOMIZATION.voice }, lines: [] } }
})

describe('CompanionCustomizer', () => {
  it('exposes name, shape, colors, image, lines, voice knobs and export/import', () => {
    const wrapper = build()
    for (const id of [
      'companion-diy-name', 'companion-diy-shape', 'companion-diy-primary',
      'companion-diy-accent', 'companion-diy-background', 'companion-diy-image',
      'companion-diy-lines', 'companion-diy-rate', 'companion-diy-pitch',
      'companion-diy-volume', 'companion-diy-motion', 'companion-diy-share',
      'companion-diy-save', 'companion-diy-reset'
    ]) {
      expect(wrapper.find(`[data-testid="${id}"]`).exists(), id).toBe(true)
    }
    expect(wrapper.findAll(`[data-testid^="companion-diy-preset-"]`)).toHaveLength(DIY_PRESETS.length)
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
