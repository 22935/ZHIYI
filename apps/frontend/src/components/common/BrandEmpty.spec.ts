import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BrandEmpty from './BrandEmpty.vue'

describe('BrandEmpty', () => {
  it('renders the wreath mark with the given text', () => {
    const wrapper = mount(BrandEmpty, {
      props: { text: 'Empty / 未观测通信记录。' }
    })

    const mark = wrapper.find('.brand-empty__mark')
    expect(mark.attributes('src')).toBe('/logo-mark.svg')
    expect(mark.attributes('style')).toContain('width: 96px')
    expect(wrapper.find('.brand-empty__text').text()).toBe('Empty / 未观测通信记录。')
  })

  it('honors a custom size and slot content', () => {
    const wrapper = mount(BrandEmpty, {
      props: { size: 44 },
      slots: { default: '尚未观测到 Runtime Activity' }
    })

    expect(wrapper.find('.brand-empty__mark').attributes('style')).toContain('width: 44px')
    expect(wrapper.find('.brand-empty__text').text()).toBe('尚未观测到 Runtime Activity')
  })
})
