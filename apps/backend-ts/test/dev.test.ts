import { fork } from 'node:child_process';
import { once } from 'node:events';
import { cp, mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { createServer } from 'node:http';
import { basename, dirname, join, resolve } from 'node:path';
import { expect, it } from 'vitest';
import { fixture } from './fixtures.js';

it('watches valid source, keeps the last build on errors, and drains SSE before replacing its child', async () => {
  const f = await fixture();
  const base = resolve('.cache');
  await mkdir(base, { recursive: true });
  const directory = await mkdtemp(join(base, 'backend-watch-test-'));
  await cp(resolve('src'), join(directory, 'src'), { recursive: true });
  await cp(resolve('tsconfig.json'), join(directory, 'tsconfig.json'));
  await cp(resolve('tsconfig.build.json'), join(directory, 'tsconfig.build.json'));
  const appFile = join(directory, 'src/app.ts');
  const original = await readFile(appFile, 'utf8');
  const version = (value: string) => original.replace("async () => ({ status: 'UP' })", `async () => ({ status: '${value}' })`);
  expect(version('v1')).not.toBe(original);
  await writeFile(appFile, version('v1'));
  const identity = await readFile(f.file);
  let entered!: () => void, release!: () => void;
  const started = new Promise<void>(resolve => { entered = resolve; });
  const python = createServer((_request, response) => {
    response.writeHead(200, { 'content-type': 'text/event-stream' });
    response.write('data: first\n\n');
    release = () => response.end('data: final\n\n');
    entered();
  });
  python.listen(0, '127.0.0.1'); await once(python, 'listening');
  const pythonAddress = python.address();
  if (!pythonAddress || typeof pythonAddress === 'string') throw new Error('Missing Python fixture port');
  const reservation = createServer(); reservation.listen(0, '127.0.0.1'); await once(reservation, 'listening');
  const portAddress = reservation.address();
  if (!portAddress || typeof portAddress === 'string') throw new Error('Missing backend fixture port');
  const port = portAddress.port;
  await new Promise<void>(resolve => reservation.close(() => resolve()));
  const child = fork(resolve('scripts/dev.mjs'), ['--project', join(directory, 'tsconfig.build.json')], {
    execArgv: [], windowsHide: true, stdio: ['ignore', 'pipe', 'pipe', 'ipc'],
    env: { SystemRoot: process.env.SystemRoot, WINDIR: process.env.WINDIR,
      TEMP: process.env.TEMP, TMP: process.env.TMP, ...f.env,
      ZHIYI_BACKEND_TS_PORT: String(port), AI_INTERNAL_TOKEN: 'synthetic-test-token-'.repeat(3),
      AI_SERVICE_URL: `http://127.0.0.1:${pythonAddress.port}` },
  });
  let diagnostics = '';
  child.stderr!.on('data', chunk => { diagnostics += String(chunk); });
  child.stdout!.resume();
  const events: Array<Record<string, unknown>> = [];
  child.on('message', message => { if (message && typeof message === 'object') events.push(message as Record<string, unknown>); });
  const exited = new Promise<number | null>(resolve => child.once('exit', code => resolve(code)));
  const wait = async (name: string, offset = 0) => {
    const deadline = Date.now() + 15000;
    while (Date.now() < deadline) {
      const event = events.slice(offset).find(item => item.event === name);
      if (event) return event;
      if (child.exitCode !== null) throw new Error('Watcher exited: ' + diagnostics);
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(`Missing ${name}: ${diagnostics}`);
  };
  const live = async () => {
    const response = await fetch(`http://127.0.0.1:${port}/health/live`);
    return response.json();
  };
  try {
    const first = await wait('backend_ready');
    const supervisorPid = child.pid;
    expect(await live()).toEqual({ status: 'v1' });
    const offset = events.length;
    await writeFile(appFile, version('v2'));
    const second = await wait('backend_ready', offset);
    expect(second.pid).not.toBe(first.pid);
    expect(second.address).toBe(first.address);
    expect(child.pid).toBe(supervisorPid);
    expect(await live()).toEqual({ status: 'v2' });

    const errorOffset = events.length;
    await writeFile(appFile, version('v2') + '\nconst invalid: number = "type error";\n');
    await wait('build_failed', errorOffset);
    expect(events.slice(errorOffset).some(item => item.event === 'backend_ready')).toBe(false);
    expect(await live()).toEqual({ status: 'v2' });

    const responsePromise = fetch(`http://127.0.0.1:${port}/ai/hold`, { headers: { Origin: 'kinlin-app://shell' } });
    await started;
    const response = await responsePromise;
    const responseText = response.text();
    const reloadOffset = events.length;
    await writeFile(join(directory, 'src/watch-value.ts'), "export const watchValue = 'v3';\n");
    await writeFile(appFile, "import { watchValue } from './watch-value.js';\n"
      + original.replace("async () => ({ status: 'UP' })", 'async () => ({ status: watchValue })'));
    await wait('reload_pending', reloadOffset);
    expect(events.slice(reloadOffset).some(item => item.event === 'backend_ready')).toBe(false);
    expect(await live()).toEqual({ status: 'v2' });
    release();
    expect(await responseText).toBe('data: first\n\ndata: final\n\n');
    const third = await wait('backend_ready', reloadOffset);
    expect(third.pid).not.toBe(second.pid);
    expect(third.address).toBe(first.address);
    expect(await live()).toEqual({ status: 'v3' });
    expect(await readFile(f.file)).toEqual(identity);
    expect(child.pid).toBe(supervisorPid);
  } finally {
    release?.();
    if (child.connected) child.send('shutdown');
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      expect(await Promise.race([exited, new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error('Watcher cleanup timed out')), 6000);
      })])).toBe(0);
    } finally { clearTimeout(timer); }
    await new Promise<void>(resolve => python.close(() => resolve()));
    // Only this test's new cache directory may be removed recursively.
    if (dirname(resolve(directory)) !== base || !basename(directory).startsWith('backend-watch-test-')) {
      throw new Error('Unsafe watcher test cleanup');
    }
    await rm(directory, { recursive: true });
    await f.cleanup();
  }
}, 45000);
