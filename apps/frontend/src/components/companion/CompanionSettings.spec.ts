import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CompanionSettings from './CompanionSettings.vue'

const skins = [
  { id: 'companion-static', label: '轻量 SVG' },
  { id: 'companion-grok', label: '动效形象' },
  { id: 'companion-diy', label: 'DIY' }
]

const build = (props: Partial<InstanceType<typeof CompanionSettings>['$props']> = {}) => mount(
  CompanionSettings,
  {
    props: {
      skins,
      skinId: 'companion-static',
      wakeSupported: true,
      wakeEnabled: true,
      wakeWords: ['知宝', '小宝'],
      ...props
    } as InstanceType<typeof CompanionSettings>['$props']
  }
)

describe('CompanionSettings', () => {
  it('hosts skin switching, the DIY entry and the wake word toggle', () => {
    const wrapper = build()
    const select = wrapper.find('[data-testid="companion-skin"]')
    expect(select.exists()).toBe(true)
    expect((select.element as HTMLSelectElement).value).toBe('companion-static')
    expect(wrapper.findAll('option')).toHaveLength(skins.length)

    expect(wrapper.find('[data-testid="companion-diy-open"]').exists()).toBe(true)
    const wake = wrapper.find('[data-testid="companion-wake"]')
    expect((wake.element as HTMLInputElement).checked).toBe(true)
    expect((wake.element as HTMLInputElement).disabled).toBe(false)
    expect(wrapper.find('[data-testid="companion-wake-note"]').text()).toContain('知宝」或「小宝')
    wrapper.unmount()
  })

  it('emits skin-change, open-diy, toggle-wake and close without touching the host state', async () => {
    const wrapper = build({ skinId: 'companion-grok' })
    const select = wrapper.find('[data-testid="companion-skin"]') as ReturnType<typeof wrapper.find>
    ;(select.element as HTMLSelectElement).value = 'companion-diy'
    select.trigger('change')
    await Promise.resolve()
    expect(wrapper.emitted('skin-change')).toEqual([['companion-diy']])

    wrapper.find('[data-testid="companion-diy-open"]').trigger('click')
    await Promise.resolve()
    expect(wrapper.emitted('open-diy')).toHaveLength(1)

    const wake = wrapper.find('[data-testid="companion-wake"]')
    ;(wake.element as HTMLInputElement).checked = false
    wake.trigger('change')
    await Promise.resolve()
    expect(wrapper.emitted('toggle-wake')).toEqual([[false]])

    wrapper.find('[data-testid="companion-settings-close"]').trigger('click')
    await Promise.resolve()
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('stays honest when the host cannot listen or the microphone was denied', () => {
    const unsupported = build({ wakeSupported: false })
    const input = unsupported.find('[data-testid="companion-wake"]')
    expect((input.element as HTMLInputElement).disabled).toBe(true)
    expect(unsupported.find('[data-testid="companion-wake-note"]').text()).toContain('没有麦克风权限')
    unsupported.unmount()

    const denied = build({ wakeError: '麦克风权限没开，语音唤醒用不了。' })
    expect(denied.find('[data-testid="companion-wake-note"]').text())
      .toContain('麦克风权限没开')
    denied.unmount()
  })
})
