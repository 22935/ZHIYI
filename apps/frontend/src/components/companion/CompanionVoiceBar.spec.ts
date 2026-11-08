import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CompanionVoiceBar from './CompanionVoiceBar.vue'

const build = (props: Record<string, unknown> = {}) => mount(CompanionVoiceBar, {
  props: { phase: 'idle', hint: '点一下说话', ...props }
})

describe('CompanionVoiceBar', () => {
  it('renders a microphone, animated waveform and mute control without a text field', () => {
    const wrapper = build()
    expect(wrapper.find('[data-testid="companion-mic"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="companion-wave"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="companion-mute"]').text()).toBe('有声')
    expect(wrapper.find('input[type="text"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="companion-voice-subtitle"]').text()).toBe('点一下说话')
    wrapper.unmount()
  })

  it('shows live subtitles ahead of the hint and reflects listening state', async () => {
    const wrapper = build({ phase: 'listening', interim: '帮我查一下进度' })
    expect(wrapper.find('[data-testid="companion-voice-subtitle"]').text()).toBe('帮我查一下进度')
    expect(wrapper.find('[data-testid="companion-mic"]').classes()).toContain('is-active')
    expect(wrapper.find('[data-testid="companion-wave"]').classes()).toContain('is-active')
    await wrapper.setProps({ phase: 'speaking', interim: '' })
    expect(wrapper.find('[data-testid="companion-mic"]').classes()).toContain('is-speaking')
    wrapper.unmount()
  })

  it('emits voice and mute intents instead of submitting text', async () => {
    const wrapper = build({ muted: true })
    await wrapper.find('[data-testid="companion-mic"]').trigger('click')
    await wrapper.find('[data-testid="companion-mute"]').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
    expect(wrapper.emitted('toggle-mute')).toHaveLength(1)
    expect(wrapper.find('[data-testid="companion-mute"]').text()).toBe('静音')
    wrapper.unmount()
  })

  it('builds bar heights from the level value', () => {
    const wrapper = build({ level: 0.9 })
    const bars = wrapper.findAll('.voice-wave-bar')
    expect(bars).toHaveLength(11)
    const first = bars[0].attributes('style') || ''
    expect(first).toContain('--amp')
    wrapper.unmount()
  })
})
