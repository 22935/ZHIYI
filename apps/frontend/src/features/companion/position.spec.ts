import { describe, expect, it } from 'vitest'
import {
  COMPANION_POSITION_KEY, clampCompanionPosition, clampExpandedPosition,
  companionPositionFromDrag, loadCompanionPosition, parseCompanionPosition
} from './position'

describe('companion position', () => {
  it('clamps right/bottom to the visible viewport with a margin', () => {
    const view = { width: 1024, height: 768 }
    expect(clampCompanionPosition({ right: 300, bottom: 200 }, view)).toEqual({ right: 300, bottom: 200 })
    expect(clampCompanionPosition({ right: -50, bottom: -50 }, view)).toEqual({ right: 12, bottom: 12 })
    // bottom 上限为「视口高 - 面板预留空间」：再往上拖，展开的面板就会顶出视口。
    expect(clampCompanionPosition({ right: 5000, bottom: 5000 }, view)).toEqual({ right: 936, bottom: 396 })
    expect(clampCompanionPosition({ right: 300.6, bottom: 200.4 }, view)).toEqual({ right: 301, bottom: 200 })
  })

  it('keeps room above the avatar for the expanded panel on a short window', () => {
    const short = { width: 1200, height: 700 }
    const clamped = clampCompanionPosition({ right: 24, bottom: 900 }, short)
    expect(clamped.bottom).toBe(328)
    // 角色底边 + 最小面板(240) + 头像/气泡(132) ≤ 视口高，顶部不会溢出。
    expect(700 - clamped.bottom - (240 + 132)).toBeGreaterThanOrEqual(0)
  })

  it('pulls a left-docked companion back when its panel opens', () => {
    const view = { width: 1024, height: 768 }
    // 收起态可以贴左，展开态必须为 320px 面板留出横向空间。
    expect(clampCompanionPosition({ right: 936, bottom: 200 }, view)).toEqual({ right: 936, bottom: 200 })
    expect(clampExpandedPosition({ right: 936, bottom: 200 }, view)).toEqual({ right: 692, bottom: 200 })
    // 默认右下角无需调整。
    expect(clampExpandedPosition({ right: 24, bottom: 24 }, view)).toEqual({ right: 24, bottom: 24 })
  })

  it('never produces a negative usable area on a tiny viewport', () => {
    expect(clampCompanionPosition({ right: 999, bottom: 999 }, { width: 40, height: 40 }))
      .toEqual({ right: 12, bottom: 12 })
  })

  it('converts a drag into right/bottom so the panel always grows upward', () => {
    const view = { width: 1024, height: 768 }
    // 按住点距角色左上角 10px，把角色拖到 (100, 200)。
    expect(companionPositionFromDrag(
      { width: 76, height: 76 },
      { x: 110, y: 210 },
      { x: 10, y: 10 },
      view
    )).toEqual({ right: 848, bottom: 396 })
    // 拖到视口外会被夹回边缘，不会把角色或面板推没。
    expect(companionPositionFromDrag(
      { width: 76, height: 76 }, { x: 5000, y: 5000 }, { x: 10, y: 10 }, view
    )).toEqual({ right: 12, bottom: 12 })
    // jsdom 的 getBoundingClientRect 返回 0 尺寸时退化为默认角色尺寸。
    expect(companionPositionFromDrag(
      { width: 0, height: 0 }, { x: 110, y: 210 }, { x: 10, y: 10 }, view
    )).toEqual({ right: 848, bottom: 396 })
  })

  it('rejects malformed persisted positions', () => {
    expect(parseCompanionPosition({ right: 10, bottom: 20 })).toEqual({ right: 10, bottom: 20 })
    expect(parseCompanionPosition({ left: 10, top: 20 })).toBeNull()
    expect(parseCompanionPosition({ right: '10', bottom: 20 })).toBeNull()
    expect(parseCompanionPosition({ right: Number.NaN, bottom: 20 })).toBeNull()
    expect(parseCompanionPosition(null)).toBeNull()
  })

  it('loads from storage and degrades to the default corner on bad JSON', () => {
    const map = new Map<string, string>([[COMPANION_POSITION_KEY, '{"right":120,"bottom":80}']])
    const storage = { getItem: (key: string) => map.get(key) ?? null }
    expect(loadCompanionPosition(storage)).toEqual({ right: 120, bottom: 80 })
    map.set(COMPANION_POSITION_KEY, '{broken')
    expect(loadCompanionPosition(storage)).toBeNull()
    expect(loadCompanionPosition(null)).toBeNull()
  })
})
