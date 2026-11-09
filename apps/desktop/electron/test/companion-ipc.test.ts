import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { test } from 'node:test'
import { shouldGrantPermissionRequest } from '../src/lib/permissions.ts'

/**
 * 通道四处同构的一致性门禁：项目此前只靠人工核对 preload / Main /
 * frontend bridge，PR-EL-01 明确登记过这个已知问题。新增 Companion 通道
 * 顺手把「漂移」变成可失败的测试，而不是继续靠约定。
 *
 * 与 lsp-host / workspace-diagnostics 等测试保持一致，以 npm 脚本约定的
 * 包目录 cwd 定位文件：桌面端 tsconfig 是 CommonJS，不能用 import.meta。
 */
const read = (relative: string): string => readFileSync(resolve(process.cwd(), relative), 'utf8')

const contract = read('src/lib/ipc-contract.ts')
const main = read('src/main.ts')
const preload = read('src/preload.ts')
const frontendBridge = read('../../frontend/src/platform/electron/bridge.ts')
const frontendAdapter = read('../../frontend/src/features/companion/adapters/desktop.ts')

const CHANNELS = ['companionState', 'companionNotify', 'companionTrayAction'] as const

test('every companion channel is declared once and used by Main and Preload', () => {
  for (const key of CHANNELS) {
    assert.equal(contract.split(`${key}:`).length - 1, 1, `${key} must be declared exactly once`)
    assert.ok(main.includes(`IPC.${key}`), `main.ts is missing IPC.${key}`)
    assert.ok(preload.includes(`IPC.${key}`), `preload.ts is missing IPC.${key}`)
  }
  assert.ok(preload.includes('ipcRenderer.on(IPC.companionTrayAction'))
  assert.ok(main.includes('webContents.send(IPC.companionTrayAction'))
})

test('renderer-to-main companion handlers keep the owner-renderer guard and input validation', () => {
  for (const key of ['companionState', 'companionNotify'] as const) {
    const start = main.indexOf(`ipcMain.handle(IPC.${key}`)
    assert.notEqual(start, -1, `${key} handler missing`)
    const next = main.indexOf('ipcMain.handle(', start + 1)
    const body = main.slice(start, next === -1 ? undefined : next)
    assert.match(body, /guard\(event\)/, `${key} lost its sender guard`)
    assert.match(body, /throw new Error\('Invalid companion /, `${key} lost payload validation`)
  }
})

test('frontend bridge and adapter stay in sync with the preload surface', () => {
  assert.match(frontendBridge, /companion\?: \{/)
  for (const method of ['publishState', 'notifyIfBackground', 'onTrayAction']) {
    assert.ok(frontendBridge.includes(method), `bridge.ts is missing ${method}`)
    assert.ok(frontendAdapter.includes(`.${method}(`) || frontendAdapter.includes(`${method}(`),
      `desktop adapter is missing ${method}`)
  }
  assert.deepEqual(
    /TRAY_ACTIONS = \[([^\]]+)\]/.exec(frontendAdapter)?.[1].replace(/['"\s]/g, '').split(','),
    ['toggle', 'summon', 'progress', 'quiet', 'focus', 'voice']
  )
})

test('desktop companion work does not weaken the existing security baseline', () => {
  // 单窗口授权模型：不建第二个 BrowserWindow。
  assert.equal(main.split('new BrowserWindow(').length - 1, 1)
  // 会话加固仍然接线：请求与检查两侧都必须走 lib/permissions 的白名单决策，
  // 不允许在 main.ts 里手写绕过（例如直接 callback(true)）。
  assert.match(main, /hardenSession\(session\.defaultSession/)
  assert.match(main, /setPermissionRequestHandler/)
  assert.match(main, /setPermissionCheckHandler/)
  assert.ok(main.includes('shouldGrantPermissionRequest'), 'request side must route through lib/permissions')
  assert.ok(main.includes('shouldGrantPermissionCheck'), 'check side must route through lib/permissions')
  assert.doesNotMatch(main, /callback\(true\)/, 'no unconditional permission grants in main.ts')
  // 白名单语义门禁（比旧的源码正则更强）：唯一放行项是自有 Origin 的纯音频 media 请求。
  const origins = new Set(['kinlin-app://shell'])
  const ask = (permission: string, mediaTypes: readonly string[] | undefined, url: string | undefined) =>
    shouldGrantPermissionRequest({ permission, mediaTypes, requestingUrl: url, allowedOrigins: origins })
  assert.equal(ask('media', ['audio'], 'kinlin-app://shell/index.html'), true, 'mic for app pages must work')
  assert.equal(ask('media', ['video'], 'kinlin-app://shell/index.html'), false, 'camera must stay denied')
  assert.equal(ask('media', ['audio'], 'https://evil.example/'), false, 'foreign origin must stay denied')
  assert.equal(ask('geolocation', undefined, 'kinlin-app://shell/index.html'), false, 'other permissions stay denied')
  // 托盘只在 whenReady 后创建，且退出时销毁。
  assert.ok(main.includes('createCompanionTray()'))
  assert.ok(main.includes('companionTray?.destroy()'))
  // 图标必须随 dist/icons 进 asar，否则生产包托盘会静默消失。
  assert.match(read('build.mjs'), /companion-tray\.png/)
})
