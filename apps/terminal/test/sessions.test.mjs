import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtempSync, mkdirSync, existsSync, readFileSync, rmSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import * as pty from 'node-pty'
import { TerminalSessions, shellEnvironment } from '../src/sessions.mjs'
import { createTerminalServer } from '../src/server.mjs'

function fakePty() {
  const process = { pid: 42, onData(callback) { this.data = callback; return { dispose() {} } },
    onExit(callback) { this.exit = callback; return { dispose() {} } },
    writes: [], write(value) { this.writes.push(value) }, resize() {}, kill() { this.killed = true } }
  return { process, spawn() { return process } }
}
async function until(check, timeout = 12000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) { if (check()) return; await new Promise(resolve => setTimeout(resolve, 50)) }
  assert.fail('Timed out waiting for terminal condition')
}
function alive(pid) { try { process.kill(pid, 0); return true } catch { return false } }

test('shells inherit user environment but never service credentials or Node injection', () => {
  const environment = shellEnvironment({ PATH: 'user-path', USERPROFILE: 'user-home',
    KINLIN_TERMINAL_TOKEN: 'private', AI_INTERNAL_TOKEN: 'private', DEEPSEEK_API_KEY: 'private', NODE_OPTIONS: '--require malicious.js' })
  assert.equal(environment.PATH, 'user-path')
  for (const key of ['KINLIN_TERMINAL_TOKEN', 'AI_INTERNAL_TOKEN', 'DEEPSEEK_API_KEY', 'NODE_OPTIONS']) assert.equal(key in environment, false)
})

test('owners, output bounds, resize validation and closed sessions are enforced', () => {
  const fake = fakePty(), store = new TerminalSessions(fake, { maxBufferBytes: 64 })
  const session = store.create('first', { cwd: os.tmpdir() })
  fake.process.data('a'.repeat(60)); fake.process.data('b'.repeat(60))
  const output = store.read('first', session.id, 0)
  assert.equal(output.truncated, true)
  assert.ok(output.chunks.reduce((n, chunk) => n + Buffer.byteLength(chunk.data), 0) <= 64)
  assert.throws(() => store.read('second', session.id), /not found/)
  assert.throws(() => store.resize('first', session.id, -1, 30), /dimensions/)
  assert.throws(() => store.create('first', { executable: 'injected' }), /options/)
  store.write('first', session.id, '\x03')
  assert.deepEqual(fake.process.writes, ['\x03'])
  store.close('first', session.id)
  assert.equal(fake.process.killed, true)
  assert.equal(store.list('first').length, 0)
})

test('HTTP transport requires its own token and isolates terminal owners', async () => {
  const store = new TerminalSessions(fakePty()), token = 'test-terminal-token-'.repeat(3)
  const server = createTerminalServer(store, token)
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const base = `http://127.0.0.1:${server.address().port}`
  const headers = { Authorization: 'Bearer ' + token, 'X-Terminal-Owner': 'first', 'Content-Type': 'application/json' }
  try {
    assert.equal((await fetch(base + '/profiles')).status, 401)
    assert.equal((await fetch(base + '/health')).status, 200)
    const response = await fetch(base + '/sessions', { method: 'POST', headers, body: JSON.stringify({ cwd: os.tmpdir() }) })
    assert.equal(response.status, 201)
    const session = await response.json()
    assert.equal((await fetch(base + `/sessions/${session.id}/output`, { headers: { ...headers, 'X-Terminal-Owner': 'other' } })).status, 404)
    assert.equal((await fetch(base + `/sessions/${session.id}/resize`, { method: 'POST', headers, body: JSON.stringify({ cols: 120, rows: 32 }) })).status, 200)
    assert.equal((await fetch(base + '/sessions', { method: 'DELETE', headers })).status, 200)
    assert.deepEqual((await (await fetch(base + '/sessions', { headers })).json()).sessions, [])
  } finally { store.dispose(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
})

test('real ConPTY supports persistent cwd, file writes, Ctrl+C and complete session cleanup', { skip: process.platform !== 'win32', timeout: 30000 }, async () => {
  const directory = mkdtempSync(path.join(os.tmpdir(), 'zhiyi-terminal-test-'))
  assert.equal(path.dirname(directory), path.resolve(os.tmpdir()))
  const store = new TerminalSessions(pty)
  let childPid
  try {
    mkdirSync(path.join(directory, 'child'))
    const session = store.create('real', { profileId: 'cmd', cwd: directory })
    store.write('real', session.id, 'cd child\recho terminal-write>receipt.txt\r')
    await until(() => existsSync(path.join(directory, 'child/receipt.txt')))
    assert.match(readFileSync(path.join(directory, 'child/receipt.txt'), 'utf8'), /terminal-write/)
    store.resize('real', session.id, 115, 28)
    store.write('real', session.id, `node -e "require('fs').writeFileSync('child.pid',String(process.pid));setInterval(()=>{},1000)"\r`)
    await until(() => existsSync(path.join(directory, 'child/child.pid')))
    childPid = Number(readFileSync(path.join(directory, 'child/child.pid'), 'utf8'))
    assert.ok(alive(childPid))
    store.write('real', session.id, '\x03')
    await until(() => !alive(childPid))
    assert.equal(store.read('real', session.id).session.state, 'running')
    store.close('real', session.id)
    await until(() => !alive(session.pid))
  } finally {
    store.dispose()
    if (childPid) await until(() => !alive(childPid))
    rmSync(directory, { recursive: true, force: true })
  }
})
