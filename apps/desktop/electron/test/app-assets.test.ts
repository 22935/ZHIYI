import assert from 'node:assert/strict'
import * as path from 'node:path'
import { test } from 'node:test'
import { buildCsp, contentTypeFor, decodeAppPath, resolveAppPath } from '../src/lib/app-assets.ts'

test('decodeAppPath 解码并拦截穿越变体', () => {
  assert.equal(decodeAppPath('/'), '')
  assert.equal(decodeAppPath('/assets/app%20v2.js'), 'assets/app v2.js')
  assert.equal(decodeAppPath('/a/../../etc/passwd'), null)
  assert.equal(decodeAppPath('/..%5Cx'), null) // 反斜杠归一后含 ..
  assert.equal(decodeAppPath('/%zz'), null) // 非法百分号序列
  assert.equal(decodeAppPath('/a\u0000b'), null)
})

test('resolveAppPath 限定在 rootDir 内（win32 与 posix 双语义）', () => {
  const root = path.win32.resolve('C:', 'app', 'renderer')
  assert.equal(resolveAppPath(root, 'assets/app.js', path.win32), path.win32.join(root, 'assets', 'app.js'))
  assert.equal(resolveAppPath(root, 'C:/windows/system32', path.win32), null)
  assert.equal(resolveAppPath(root, 'a/../../../x', path.win32), null)

  const posixRoot = '/srv/app/renderer'
  assert.equal(resolveAppPath(posixRoot, 'index.html', path.posix), '/srv/app/renderer/index.html')
  assert.equal(resolveAppPath(posixRoot, '../../etc/passwd', path.posix), null)
  assert.equal(resolveAppPath(posixRoot, '', path.posix), '/srv/app/renderer')
})

test('contentTypeFor 常见映射与未知回退', () => {
  assert.equal(contentTypeFor('index.html'), 'text/html; charset=utf-8')
  assert.equal(contentTypeFor('app.js'), 'text/javascript; charset=utf-8')
  assert.equal(contentTypeFor('style.css'), 'text/css; charset=utf-8')
  assert.equal(contentTypeFor('logo.webp'), 'image/webp')
  assert.equal(contentTypeFor('logo.svg'), 'image/svg+xml')
  assert.equal(contentTypeFor('logo-compact.svg'), 'image/svg+xml')
  assert.equal(contentTypeFor('font.woff2'), 'font/woff2')
  assert.equal(contentTypeFor('blob.bin'), 'application/octet-stream')
})

test('buildCsp 严格且不含通配符', () => {
  const csp = buildCsp('http://127.0.0.1:18080')
  assert.ok(csp.includes("script-src 'self'"), 'script-src 只允许 self')
  // vue-i18n 运行时消息编译需要 new Function：收紧到无 eval 会让相关组件被
  // 错误边界拦截（发行包实测 EvalError ×3），故保留 'unsafe-eval'。
  assert.ok(csp.includes("script-src 'self' 'unsafe-eval'"), 'script-src 允许 eval（vue-i18n 运行时编译）')
  assert.ok(!csp.includes('*'), '不出现任何通配符来源')
  assert.ok(csp.includes('connect-src') && csp.includes('http://127.0.0.1:18080') && csp.includes('ws://127.0.0.1:18080'))
  assert.ok(csp.includes('https:') && csp.includes('wss:'), '保留上层 HTTPS/WSS 出口')
  assert.ok(csp.includes("frame-ancestors 'none'"))
  assert.ok(csp.includes("object-src 'none'"))

  const custom = buildCsp('http://10.1.2.3:8080')
  assert.ok(custom.includes('http://10.1.2.3:8080') && custom.includes('ws://10.1.2.3:8080'))
  // 非法注入回退默认的本机 Java 后端。
  assert.ok(buildCsp('not-a-url').includes('http://127.0.0.1:18080'))
})
