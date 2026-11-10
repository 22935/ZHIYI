import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import CustomResourceDialog from './CustomResourceDialog.vue'

const stubs = {
  'el-dialog': { template: '<div><slot /></div>' }
}

describe('CustomResourceDialog', () => {
  it('does not expose a command field and rejects non-loopback service addresses', async () => {
    const wrapper = mount(CustomResourceDialog, {
      props: { modelValue: true },
      global: { stubs }
    })

    expect(wrapper.find('[name="command"]').exists()).toBe(false)
    await wrapper.findAll('input')[1].setValue('https://example.com/v1')
    await wrapper.get('form').trigger('submit')

    expect(wrapper.emitted('submit')).toBeUndefined()
    expect(wrapper.text()).toContain('仅允许 localhost 或本机回环地址。')
  })
})
