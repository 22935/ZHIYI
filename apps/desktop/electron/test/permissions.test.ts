import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  buildAllowedOrigins,
  isAudioOnlyMediaRequest,
  normalizeOrigin,
  shouldGrantPermissionCheck,
  shouldGrantPermissionRequest
} from '../src/lib/permissions.ts'

const origins = new Set(['kinlin-app://shell', 'http://127.0.0.1:5173'])

test('normalizeOrigin 提取 Origin，解析失败返回 null', () => {
  assert.equal(normalizeOrigin('kinlin-app://shell/index.html'), 'kinlin-app://shell')
  assert.equal(normalizeOrigin('http://127.0.0.1:5173/chat'), 'http://127.0.0.1:5173')
  assert.equal(normalizeOrigin('http://127.0.0.1:5173'), 'http://127.0.0.1:5173')
  assert.equal(normalizeOrigin(''), null)
  assert.equal(normalizeOrigin(undefined), null)
  assert.equal(normalizeOrigin(null), null)
  assert.equal(normalizeOrigin('not a url'), null)
})

test('isAudioOnlyMediaRequest 只认纯音频；摄像头与 unknown 一律拒绝', () => {
  assert.equal(isAudioOnlyMediaRequest(['audio']), true)
  assert.equal(isAudioOnlyMediaRequest(undefined), true)
  assert.equal(isAudioOnlyMediaRequest(null), true)
  assert.equal(isAudioOnlyMediaRequest([]), true)
  assert.equal(isAudioOnlyMediaRequest(['audio', 'video']), false)
  assert.equal(isAudioOnlyMediaRequest(['video']), false)
  assert.equal(isAudioOnlyMediaRequest(['unknown']), false)
  assert.equal(isAudioOnlyMediaRequest(['audio', 'unknown']), false)
})

test('请求侧：自有来源的纯音频 media 放行，其余全拒', () => {
  const ask = (permission: string, mediaTypes: readonly string[] | undefined, url: string | undefined) =>
    shouldGrantPermissionRequest({ permission, mediaTypes, requestingUrl: url, allowedOrigins: origins })

  // 麦克管 / 语音识别的唯一放行路径
  assert.equal(ask('media', ['audio'], 'kinlin-app://shell/index.html'), true)
  assert.equal(ask('media', ['audio'], 'http://127.0.0.1:5173/chat'), true)
  // 老版本 Electron 的 Web Speech 请求可能不带 mediaTypes
  assert.equal(ask('media', undefined, 'kinlin-app://shell/index.html'), true)
  // 摄像头与混合请求
  assert.equal(ask('media', ['video'], 'kinlin-app://shell/index.html'), false)
  assert.equal(ask('media', ['audio', 'video'], 'kinlin-app://shell/index.html'), false)
  // 非自有来源：即使权限与媒体类型正确也不放行
  assert.equal(ask('media', ['audio'], 'https://evil.example/'), false)
  assert.equal(ask('media', ['audio'], 'kinlin-app://attacker/'), false)
  assert.equal(ask('media', ['audio'], undefined), false)
  assert.equal(ask('media', ['audio'], 'not a url'), false)
  // 其他权限维持全拒
  assert.equal(ask('geolocation', undefined, 'kinlin-app://shell/index.html'), false)
  assert.equal(ask('notifications', undefined, 'kinlin-app://shell/index.html'), false)
  assert.equal(ask('display-capture', undefined, 'kinlin-app://shell/index.html'), false)
  assert.equal(ask('clipboard-read', undefined, 'kinlin-app://shell/index.html'), false)
})

test('检查侧：音频 media 通过，视频与其余权限拒绝', () => {
  const check = (permission: string, mediaType: string | undefined, origin: string | undefined) =>
    shouldGrantPermissionCheck({ permission, mediaType, requestingOrigin: origin, allowedOrigins: origins })

  assert.equal(check('media', 'audio', 'kinlin-app://shell'), true)
  assert.equal(check('media', undefined, 'http://127.0.0.1:5173'), true)
  assert.equal(check('media', 'video', 'kinlin-app://shell'), false)
  assert.equal(check('media', 'audio', 'https://evil.example'), false)
  assert.equal(check('media', 'audio', undefined), false)
  assert.equal(check('geolocation', undefined, 'kinlin-app://shell'), false)
  assert.equal(check('notifications', undefined, 'kinlin-app://shell'), false)
})

test('buildAllowedOrigins 打包形态只含应用协议，开发形态附带 dev server', () => {
  const parseHttp = (raw: string | undefined) => {
    try {
      const url = new URL(String(raw))
      return url.protocol === 'http:' || url.protocol === 'https:' ? url : null
    } catch {
      return null
    }
  }
  const packaged = buildAllowedOrigins(undefined, parseHttp)
  assert.deepEqual([...packaged].sort(), ['kinlin-app://shell'])
  const dev = buildAllowedOrigins('http://127.0.0.1:5173/', parseHttp)
  assert.equal(dev.has('kinlin-app://shell'), true)
  assert.equal(dev.has('http://127.0.0.1:5173'), true)
  // 非 http(s) 的开发服务器地址不进入白名单
  const bogus = buildAllowedOrigins('ftp://127.0.0.1:5173', parseHttp)
  assert.equal(bogus.has('ftp://127.0.0.1:5173'), false)
  assert.equal(bogus.has('kinlin-app://shell'), true)
})
