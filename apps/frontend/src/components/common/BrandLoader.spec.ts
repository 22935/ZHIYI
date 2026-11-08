import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import BrandLoader from './BrandLoader.vue'

describe('BrandLoader', () => {
  it('renders the wreath mark with title and subtitle', () => {
    const wrapper = mount(BrandLoader, {
      props: { title: '正在加载项目', subtitle: '读取 Mission Project 列表…' }
    })

    const mark = wrapper.find('.brand-loader__mark')
    expect(mark.attributes('src')).toBe('/logo.svg')
    expect(mark.attributes('style')).toContain('width: 64px')
    expect(wrapper.find('strong').text()).toBe('正在加载项目')
    expect(wrapper.find('span').text()).toBe('读取 Mission Project 列表…')
  })

  it('omits empty text lines and honors a custom size', () => {
    const wrapper = mount(BrandLoader, {
      props: { size: 52, title: '页面加载中…' }
    })

    expect(wrapper.find('strong').text()).toBe('页面加载中…')
    expect(wrapper.find('span').exists()).toBe(false)
    expect(wrapper.find('.brand-loader__mark').attributes('style')).toContain('width: 52px')
  })
})
