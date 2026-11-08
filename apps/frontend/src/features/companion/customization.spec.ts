import { describe, expect, it } from 'vitest'
import {
  CUSTOMIZATION_STORAGE_KEY, DEFAULT_CUSTOMIZATION, DIY_PRESETS, DIY_SKIN_ID,
  MAX_LINES, MAX_VOICE_URI_LENGTH, buildDiySkin, exportCustomization, importCustomization,
  loadCustomization, parseLines, sanitizeCustomization, saveCustomization,
  isValidImage, sanitizeName, sanitizeVoiceURI
} from './customization'

const fakeStorage = () => {
  const data = new Map<string, string>()
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => { data.set(key, value) },
    data
  }
}

describe('customization sanitization', () => {
  it('returns a complete default config for missing or broken input', () => {
    expect(sanitizeCustomization(null)).toEqual(DEFAULT_CUSTOMIZATION)
    expect(sanitizeCustomization({ shape: 'nope', primary: 'red' })).toEqual(DEFAULT_CUSTOMIZATION)
  })

  it('keeps user choices but clamps every field', () => {
    const result = sanitizeCustomization({
      name: '  小知  ',
      shape: 'star',
      primary: '#AABBCC',
      accent: '#112233',
      background: '#000000',
      voice: { rate: 99, pitch: -1, volume: 5, muted: true },
      lines: ['  一句台词  ', '', 42, 'x'.repeat(200)],
      motion: false
    })
    expect(result.name).toBe('小知')
    expect(result.shape).toBe('star')
    expect(result.primary).toBe('#aabbcc')
    expect(result.voice).toEqual({ rate: 2, pitch: 0, volume: 1, muted: true, voiceURI: null })
    expect(result.lines).toHaveLength(2)
    expect(result.lines[1]).toHaveLength(60)
    expect(result.motion).toBe(false)
  })

  it('rejects scripts and oversized images', () => {
    expect(isValidImage('data:image/svg+xml;base64,PHNjcmlwdD4=')).toBe(false)
    expect(isValidImage('javascript:alert(1)')).toBe(false)
    expect(isValidImage('data:image/png;base64,AAAA')).toBe(true)
    expect(isValidImage(`data:image/png;base64,${'A'.repeat(800_000)}`)).toBe(false)
    expect(sanitizeCustomization({ image: 'data:text/html;base64,AAAA' }).image).toBeNull()
  })

  it('sanitizes names and line lists', () => {
    expect(sanitizeName('')).toBe('知宝')
    expect(sanitizeName('a'.repeat(30))).toHaveLength(12)
    expect(sanitizeName('坏\u0000名字')).toBe('坏名字')
    expect(parseLines('第一句\n\n  第二句  \n第三句')).toEqual(['第一句', '第二句', '第三句'])
    expect(parseLines(Array.from({ length: MAX_LINES + 4 }, (_, i) => `第${i}句`).join('\n')))
      .toHaveLength(MAX_LINES)
  })

  it('every preset is a legal shape + color combination', () => {
    for (const preset of DIY_PRESETS) {
      const cleaned = sanitizeCustomization(preset.value)
      expect(cleaned.shape).toBe(preset.value.shape)
      expect(cleaned.primary).toBe(preset.value.primary)
    }
  })

  it('keeps a usable voice selection and drops unusable ones', () => {
    expect(sanitizeCustomization({ voice: { voiceURI: '  zh-cn-xiaoxiao  ' } }).voice.voiceURI)
      .toBe('zh-cn-xiaoxiao')
    // 空串是下拉框里的「自动」，归一成 null。
    expect(sanitizeCustomization({ voice: { voiceURI: '   ' } }).voice.voiceURI).toBeNull()
    // 超长不截断：截断后的 voiceURI 必然匹配不到声线，不如当作未指定。
    expect(sanitizeCustomization({
      voice: { voiceURI: 'x'.repeat(MAX_VOICE_URI_LENGTH + 1) }
    }).voice.voiceURI).toBeNull()
    expect(sanitizeCustomization({ voice: { voiceURI: 42 } }).voice.voiceURI).toBeNull()
    expect(sanitizeVoiceURI('坏\u0000声线')).toBe('坏声线')
  })

  it('round-trips the chosen voice through export / import', () => {
    const custom = sanitizeCustomization({ voice: { voiceURI: 'zh-cn-yunxi' } })
    expect(custom.voice.voiceURI).toBe('zh-cn-yunxi')
    expect(importCustomization(exportCustomization(custom))?.voice.voiceURI).toBe('zh-cn-yunxi')
  })
})

describe('customization persistence', () => {
  it('loads, saves and tolerates corrupt storage', () => {
    const storage = fakeStorage()
    expect(loadCustomization(storage)).toEqual(DEFAULT_CUSTOMIZATION)
    const custom = sanitizeCustomization({ name: '阿宝', shape: 'drop' })
    saveCustomization(storage, custom)
    expect(loadCustomization(storage).name).toBe('阿宝')
    storage.data.set(CUSTOMIZATION_STORAGE_KEY, '{not json')
    expect(loadCustomization(storage)).toEqual(DEFAULT_CUSTOMIZATION)
    expect(() => saveCustomization(null, custom)).not.toThrow()
  })

  it('round-trips through export / import and rejects bad JSON', () => {
    const custom = sanitizeCustomization({
      name: '团子', shape: 'blob', lines: ['你好呀'], image: 'data:image/png;base64,AAAA'
    })
    const json = exportCustomization(custom)
    expect(importCustomization(json)).toEqual(custom)
    expect(importCustomization('not json')).toBeNull()
    expect(importCustomization('42')).toBeNull()
  })
})

describe('DIY skin manifest', () => {
  it('is identity-mapped across all eight semantic states', () => {
    const skin = buildDiySkin(DEFAULT_CUSTOMIZATION)
    expect(skin.id).toBe(DIY_SKIN_ID)
    expect(skin.rendererType).toBe('diy-svg')
    expect(Object.keys(skin.stateMap)).toHaveLength(8)
    expect(skin.stateMap.thinking).toBe('thinking')
    expect(skin.fallbackSkinId).toBe('companion-static')
    expect(skin.custom?.name).toBe('知宝')
  })

  it('carries a sanitized copy so a dirty caller cannot reach the renderer', () => {
    const skin = buildDiySkin({
      ...DEFAULT_CUSTOMIZATION,
      primary: 'not-a-color',
      image: 'data:image/svg+xml;base64,AAAA'
    } as never)
    expect(skin.custom?.primary).toBe(DEFAULT_CUSTOMIZATION.primary)
    expect(skin.custom?.image).toBeNull()
  })
})
