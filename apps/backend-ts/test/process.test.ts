import { fork, type ChildProcess } from 'node:child_process';
import { readFile } from 'node:fs/promises';
import { get } from 'node:http';
import { resolve } from 'node:path';
import { createServer } from 'node:net';
import { once } from 'node:events';
import { expect, it } from 'vitest';
import { fixture } from './fixtures.js';

async function start(env: NodeJS.ProcessEnv) {
  const child = fork(resolve('dist/main.js'), [], {
    execArgv: [], windowsHide: true, stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
    env: { SystemRoot: process.env.SystemRoot, WINDIR: process.env.WINDIR,
      TEMP: process.env.TEMP, TMP: process.env.TMP, ...env },
  });
  let diagnostics = '';
  child.stderr!.on('data', chunk => { diagnostics += String(chunk); });
  child.stdout!.resume();
  const exited = new Promise<number | null>(resolve => child.once('exit', code => resolve(code)));
  const ready = new Promise<string>((resolve, reject) => {
    // The watch integration test also runs a real compiler in parallel.
    const timer = setTimeout(() => reject(new Error('Child did not become ready')), 10000);
    child.once('error', error => { clearTimeout(timer); reject(error); });
    child.once('exit', () => { clearTimeout(timer); reject(new Error(diagnostics || 'Child exited before listen')); });
    child.on('message', message => {
      if (message && typeof message === 'object' && 'event' in message && message.event === 'listening'
        && 'address' in message && typeof message.address === 'string') {
        clearTimeout(timer); resolve(message.address);
      }
    });
  });
  return { child, exited, ready, diagnostics: () => diagnostics };
}

async function stop(child: ChildProcess, exited: Promise<number | null>) {
  if (child.connected) child.send('shutdown');
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([exited, new Promise<never>((_, reject) => {
      timer = setTimeout(() => { child.kill(); reject(new Error('Graceful child shutdown timed out')); }, 4000);
    })]);
  } finally { clearTimeout(timer); }
}

it('runs compiled Node entry twice with the same read-only identity and exits cleanly through parent IPC', async () => {
  const f = await fixture(); const original = await readFile(f.file);
  try {
    for (let i = 0; i < 2; i++) {
      const running = await start(f.env);
      try {
        const address = await running.ready;
        expect(address).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
        expect(new URL(address).port).not.toBe('18080');
        const status = await new Promise<number | undefined>((resolve, reject) => {
          get(address + '/health/ready', response => { response.resume(); resolve(response.statusCode); }).on('error', reject);
        });
        expect(status).toBe(503); // identity is valid, but this isolated process has no database
      } finally { expect(await stop(running.child, running.exited), running.diagnostics()).toBe(0); }
      expect(running.diagnostics()).toBe('');
      expect(await readFile(f.file)).toEqual(original);
    }
  } finally { await f.cleanup(); }
}, 30000);

it('exits on an occupied isolated port without stopping its existing owner or leaking IPC', async () => {
  const owner = createServer(); const f = await fixture();
  try {
    owner.listen(0, '127.0.0.1'); await once(owner, 'listening');
    const address = owner.address();
    if (!address || typeof address === 'string') throw new Error('Missing fixture port');
    const running = await start({ ...f.env, ZHIYI_BACKEND_TS_PORT: String(address.port) });
    try {
      await expect(running.ready).rejects.toThrow();
      expect(await stop(running.child, running.exited)).toBe(1);
      expect(running.diagnostics()).toContain('BACKEND_TS_STARTUP_FAILED');
      expect(owner.listening).toBe(true);
    } finally { if (running.child.connected) await stop(running.child, running.exited); }
  } finally {
    await new Promise<void>(resolve => owner.close(() => resolve()));
    await f.cleanup();
  }
}, 10000);
