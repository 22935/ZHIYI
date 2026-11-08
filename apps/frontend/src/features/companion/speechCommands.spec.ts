import { describe, expect, it } from 'vitest'
import { COMMAND_IDS, matchCompanionCommand } from './speechCommands'

describe('speech commands', () => {
  it.each([
    ['把面板收起来', 'collapse'],
    ['退下吧', 'collapse'],
    ['出来', 'summon'],
    ['免打扰', 'quiet-on'],
    ['关掉免打扰', 'quiet-off'],
    ['静音', 'mute-on'],
    ['打开声音', 'mute-off'],
    ['别说了', 'stop-speaking'],
    ['回到右下角', 'reset-position'],
    ['我要自定义形象', 'open-customizer'],
    ['换个形象', 'next-skin'],
    ['摸摸头', 'interact-pat'],
    ['喂点心', 'interact-feed'],
    ['陪我玩一会儿', 'interact-play']
  ])('maps %s to %s', (text, expected) => {
    expect(matchCompanionCommand(text)?.id).toBe(expected)
  })

  it('gives every command a spoken confirmation', () => {
    for (const id of COMMAND_IDS) {
      const text = {
        collapse: '收起', summon: '出来', 'quiet-on': '免打扰', 'quiet-off': '关掉免打扰',
        'mute-on': '静音', 'mute-off': '打开声音', 'stop-speaking': '别说了',
        'reset-position': '回到右下角', 'open-customizer': '自定义',
        'close-customizer': '关掉工坊', 'next-skin': '换个形象',
        'interact-pat': '摸摸头', 'interact-feed': '喂点心', 'interact-play': '玩一会儿'
      }[id]
      const match = matchCompanionCommand(text)
      expect(match?.id).toBe(id)
      expect(match?.reply.length).toBeGreaterThan(0)
    }
  })

  it('does not hijack normal conversation', () => {
    expect(matchCompanionCommand('现在的进度怎么样了')).toBeNull()
    expect(matchCompanionCommand('今天好累啊')).toBeNull()
    expect(matchCompanionCommand('帮我新建一个合同审查任务')).toBeNull()
    expect(matchCompanionCommand('')).toBeNull()
  })

  it('resolves overlapping phrases by the declared priority', () => {
    // 「关掉免打扰」同时含「免打扰」，但取消语义要优先。
    expect(matchCompanionCommand('关掉免打扰吧')?.id).toBe('quiet-off')
    // 「别说了」不是「别打扰」的免打扰指令。
    expect(matchCompanionCommand('别说了')?.id).toBe('stop-speaking')
  })
})
