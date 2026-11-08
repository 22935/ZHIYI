import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  COMPANION_STATES, DEFAULT_COMPANION_SNAPSHOT, TRAY_ACTIONS,
  formatTrayTooltip, isTrayAction, parseCompanionSnapshot, parseNotification,
  shouldDeliverNotification, trayMenuDescriptor
} from '../src/lib/companion-tray.ts'

const valid = {
  state: 'working', label: '跟进中', level: 3, affinity: 140, quiet: false
}

test('parseCompanionSnapshot accepts a well-formed snapshot', () => {
  assert.deepEqual(parseCompanionSnapshot(valid), valid)
  assert.ok(COMPANION_STATES.includes('sleeping'))
})

test('parseCompanionSnapshot rejects malformed or hostile payloads', () => {
  for (const bad of [
    null, undefined, 'text', 42,
    { ...valid, state: 'hacked' },
    { ...valid, label: '' },
    { ...valid, label: 'x'.repeat(33) },
    { ...valid, label: 'bad\u0000text' },
    { ...valid, level: '3' },
    { ...valid, affinity: Number.NaN },
    { ...valid, quiet: 'false' },
    { state: 'idle' }
  ]) {
    assert.equal(parseCompanionSnapshot(bad), null, `should reject ${JSON.stringify(bad)}`)
  }
  // 数值越界收敛到合法区间，而不是让托盘显示离谱的等级。
  assert.equal(parseCompanionSnapshot({ ...valid, level: 99 })?.level, 12)
  assert.equal(parseCompanionSnapshot({ ...valid, affinity: 1e9 })?.affinity, 720)
  const rounded = parseCompanionSnapshot({ ...valid, level: 2.6, affinity: 12.7 })
  assert.equal(rounded?.level, 3)
  assert.equal(rounded?.affinity, 13)
})

test('parseCompanionSnapshot accepts optional DIY name and voice phase', () => {
  assert.deepEqual(parseCompanionSnapshot(valid), valid)
  const enriched = parseCompanionSnapshot({ ...valid, name: '团子', voice: 'listening' })
  assert.equal(enriched?.name, '团子')
  assert.equal(enriched?.voice, 'listening')
  // 非法语音态与超长名字直接丢弃，不让脏数据进 tooltip。
  const dirty = parseCompanionSnapshot({ ...valid, name: 'x'.repeat(30), voice: 'hacked' })
  assert.equal(dirty?.name, undefined)
  assert.equal(dirty?.voice, undefined)
})

test('formatTrayTooltip reflects mood, level, affinity, voice and quiet mode', () => {
  assert.equal(formatTrayTooltip(valid), '知宝 · 跟进中 · Lv.3（好感 140）')
  assert.match(formatTrayTooltip({ ...valid, quiet: true }), /免打扰/)
  assert.match(formatTrayTooltip(DEFAULT_COMPANION_SNAPSHOT), /待机/)
  assert.equal(formatTrayTooltip({ ...valid, name: '团子', voice: 'speaking' }),
    '团子 · 跟进中 · Lv.3（好感 140） · 正在说')
  assert.match(formatTrayTooltip({ ...valid, voice: 'listening' }), /正在听/)
})

test('tray menu uses fixed labels, a voice entry, a quiet checkbox and a Main-only quit item', () => {
  const items = trayMenuDescriptor(valid)
  assert.equal(items[0].label, '叫一声知宝')
  assert.equal(items[1].label, '听我说话')
  assert.equal(items[1].action, 'voice')
  assert.equal(items.filter(item => item.kind === 'separator').length, 2)
  const quiet = items.find(item => item.kind === 'checkbox')
  assert.equal(quiet?.label, '免打扰')
  assert.equal(quiet?.checked, false)
  assert.equal(trayMenuDescriptor({ ...valid, quiet: true }).find(item => item.kind === 'checkbox')?.checked, true)
  assert.equal(items.at(-1)?.action, 'quit')
  for (const item of items) {
    if (item.action && item.action !== 'quit') assert.ok(isTrayAction(item.action))
  }
  assert.deepEqual(TRAY_ACTIONS, ['toggle', 'summon', 'progress', 'quiet', 'focus', 'voice'])
  assert.equal(isTrayAction('quit'), false)
  assert.equal(isTrayAction({}), false)
})

test('native notifications are suppressed by quiet mode or a focused window', () => {
  const quiet = { ...valid, quiet: true }
  assert.equal(shouldDeliverNotification(valid, true, false), false)
  assert.equal(shouldDeliverNotification(valid, false, false), true)
  assert.equal(shouldDeliverNotification(valid, true, true), true)
  assert.equal(shouldDeliverNotification(quiet, false, false), false)
})

test('parseNotification bounds title and body', () => {
  assert.deepEqual(parseNotification({ title: '知宝', body: '有个运行出问题了' }),
    { title: '知宝', body: '有个运行出问题了' })
  assert.deepEqual(parseNotification({ title: '知宝' }), { title: '知宝', body: undefined })
  assert.equal(parseNotification({ title: '' }), null)
  assert.equal(parseNotification({ title: 'x'.repeat(201) }), null)
  assert.equal(parseNotification({ title: '知宝', body: 'x'.repeat(2001) })?.body, undefined)
  assert.equal(parseNotification(null), null)
})
