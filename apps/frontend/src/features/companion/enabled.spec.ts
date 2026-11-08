import { mount } from '@vue/test-utils'
import { defineComponent, h, type Ref } from 'vue'
import { beforeEach, describe, expect, it } from 'vitest'
import { APP_SETTINGS_SAVED_EVENT, applyCompanionEnabled, readCompanionEnabled, useCompanionEnabled } from './enabled'

describe('readCompanionEnabled', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('defaults to enabled when nothing is stored', () => {
    expect(readCompanionEnabled()).toBe(true)
  })

  it('reads the explicit switch from appSettings', () => {
    localStorage.setItem('appSettings', JSON.stringify({ companionEnabled: false }))
    expect(readCompanionEnabled()).toBe(false)
    localStorage.setItem('appSettings', JSON.stringify({ companionEnabled: true }))
    expect(readCompanionEnabled()).toBe(true)
  })

  it('falls back to enabled for legacy saves without the key', () => {
    localStorage.setItem('appSettings', JSON.stringify({ language: 'zh-CN', speed: 1.0 }))
    expect(readCompanionEnabled()).toBe(true)
  })

  it('falls back to enabled on malformed settings', () => {
    localStorage.setItem('appSettings', '{not json')
    expect(readCompanionEnabled()).toBe(true)
  })
})

describe('applyCompanionEnabled', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('writes only its own field and keeps sibling settings intact', () => {
    localStorage.setItem('appSettings', JSON.stringify({ language: 'zh-CN', speed: 1.0 }))
    applyCompanionEnabled(false)
    const parsed = JSON.parse(localStorage.getItem('appSettings') || '{}') as Record<string, unknown>
    expect(parsed.companionEnabled).toBe(false)
    expect(parsed.language).toBe('zh-CN')
    expect(parsed.speed).toBe(1.0)
  })

  it('starts a fresh settings object when none exists', () => {
    applyCompanionEnabled(false)
    expect(readCompanionEnabled()).toBe(false)
  })

  it('recovers when the stored settings are malformed', () => {
    localStorage.setItem('appSettings', '{not json')
    applyCompanionEnabled(true)
    expect(readCompanionEnabled()).toBe(true)
  })

  it('notifies live subscribers immediately', () => {
    let enabled!: Ref<boolean>
    const Host = defineComponent({
      setup() {
        enabled = useCompanionEnabled()
        return () => h('div')
      }
    })
    const wrapper = mount(Host)

    applyCompanionEnabled(false)
    expect(enabled.value).toBe(false)

    applyCompanionEnabled(true)
    expect(enabled.value).toBe(true)

    wrapper.unmount()
  })
})

describe('useCompanionEnabled', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('re-reads the switch when the settings-saved event fires', () => {
    localStorage.setItem('appSettings', JSON.stringify({ companionEnabled: true }))
    let enabled!: Ref<boolean>
    const Host = defineComponent({
      setup() {
        enabled = useCompanionEnabled()
        return () => h('div')
      }
    })
    const wrapper = mount(Host)

    expect(enabled.value).toBe(true)

    localStorage.setItem('appSettings', JSON.stringify({ companionEnabled: false }))
    window.dispatchEvent(new CustomEvent(APP_SETTINGS_SAVED_EVENT))
    expect(enabled.value).toBe(false)

    wrapper.unmount()
  })

  it('stops syncing after unmount', () => {
    let enabled!: Ref<boolean>
    const Host = defineComponent({
      setup() {
        enabled = useCompanionEnabled()
        return () => h('div')
      }
    })
    const wrapper = mount(Host)
    wrapper.unmount()

    localStorage.setItem('appSettings', JSON.stringify({ companionEnabled: false }))
    window.dispatchEvent(new CustomEvent(APP_SETTINGS_SAVED_EVENT))
    expect(enabled.value).toBe(true)
  })
})
