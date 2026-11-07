import { request, Agent } from 'node:http';
import { createServer, createConnection } from 'node:net';
import { once } from 'node:events';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createApp } from '../src/app.js';
import { readConfig } from '../src/config.js';
import { fixture, legacyUserId, mapping, otherUserId } from './fixtures.js';

function getPort(app: Awaited<ReturnType<typeof createApp>>) {
  const address = app.server.address();
  if (!address || typeof address === 'string') throw new Error('Missing TCP listener');
  expect(address.address).toBe('127.0.0.1');
  return address.port;
}

async function call(port: number, path = '/health/live', headers: Record<string, string | string[]> = {},
  method = 'GET', body?: unknown, agent?: Agent) {
  return new Promise<{ status: number; body: string; headers: import('node:http').IncomingHttpHeaders }>((resolve, reject) => {
    const data = body === undefined ? undefined : JSON.stringify(body);
    const req = request({ host: '127.0.0.1', port, path, method, agent,
      headers: { ...(data ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) } : {}), ...headers } }, res => {
      let text = '';
      res.setEncoding('utf8');
      res.on('data', chunk => { text += chunk; });
      res.on('end', () => resolve({ status: res.statusCode!, body: text, headers: res.headers }));
    });
    req.on('error', reject);
    req.setTimeout(3000, () => req.destroy(new Error('Test HTTP timeout')));
    req.end(data);
  });
}

async function rawRequest(port: number, headers: string[]) {
  return new Promise<string>((resolve, reject) => {
    const socket = createConnection({ host: '127.0.0.1', port });
    let response = '';
    socket.setEncoding('utf8');
    socket.setTimeout(3000, () => socket.destroy(new Error('Raw HTTP test timeout')));
    socket.on('error', reject);
    socket.on('data', chunk => { response += chunk; });
    socket.on('end', () => resolve(response));
    socket.on('connect', () => socket.write(['GET /health/live HTTP/1.1', ...headers, 'Connection: close', '', ''].join('\r\n')));
  });
}

describe('real loopback HTTP contracts', () => {
  let f: Awaited<ReturnType<typeof fixture>>;
  let app: Awaited<ReturnType<typeof createApp>>;
  let port: number;
  beforeAll(async () => {
    f = await fixture(); app = await createApp(f.config);
    // These probes exist only inside the test, never in the production app.
    app.get('/_test/actor', request => request.localIdentity);
    app.post('/_test/write', async () => ({ handled: true }));
    await app.listen({ host: '127.0.0.1', port: 0 }); port = getPort(app);
  });
  afterAll(async () => { await app?.close(); await f?.cleanup(); });

  it('reports live/ready without disclosing identity or requiring an Origin', async () => {
    for (const path of ['/health/live', '/health/ready']) {
      const result = await call(port, path);
      expect(result.status).toBe(200); expect(JSON.parse(result.body)).toEqual({ status: 'UP' });
      expect(result.headers['cache-control']).toBe('no-store');
      expect(result.body).not.toContain(legacyUserId);
    }
    expect((await call(port, '/health/live', {}, 'HEAD')).body).toBe('');
  });
  it.each(['evil.example', 'localhost:1', '127.0.0.1:18080', '127.0.0.1.evil:1234'])(
    'rejects Host %j even if forwarding headers claim loopback', async host => {
      const result = await call(port, '/health/live', { Host: host, 'X-Forwarded-Host': `127.0.0.1:${port}` });
      expect(result.status).toBe(403); expect(JSON.parse(result.body).error).toBe('LOCAL_HOST_REJECTED');
    },
  );
  it('rejects duplicate Host headers', async () => {
    expect(await rawRequest(port, [`Host: 127.0.0.1:${port}`, 'Host: evil.example'])).toMatch(/^HTTP\/1.1 403 /);
  });
  it('rejects duplicate Origin headers and HTTP/1.1 requests without a Host', async () => {
    expect(await rawRequest(port, [`Host: 127.0.0.1:${port}`, 'Origin: kinlin-app://shell', 'Origin: http://evil.example']))
      .toMatch(/^HTTP\/1.1 403 /);
    expect(await rawRequest(port, [])).toMatch(/^HTTP\/1.1 4\d\d /);
  });
  it.each(['null', 'http://evil.example', 'kinlin-app://shell.evil', 'kinlin-app://shell/'])(
    'rejects Origin %j', async origin => {
      const result = await call(port, '/health/live', { Origin: origin });
      expect(result.status).toBe(403); expect(result.headers['access-control-allow-origin']).toBeUndefined();
    },
  );
  it('requires an allowed Origin for non-health access and attaches only server identity', async () => {
    expect((await call(port, '/_test/actor')).status).toBe(403);
    const result = await call(port, '/_test/actor', { Origin: 'kinlin-app://shell' });
    expect(result.status).toBe(200);
    expect(JSON.parse(result.body)).toEqual({ actorId: legacyUserId, tenantId: null });
    expect(result.headers['access-control-allow-origin']).toBe('kinlin-app://shell');
  });
  it.each(['Authorization', 'X-User-Id', 'X-Actor-Id', 'X-Tenant-Id', 'X-Authenticated-User-Id',
    'X-Authenticated-User-Role', 'X-Authenticated-Tenant-Id', 'X-Internal-Service-Token'])(
    'rejects forged identity header %s', async name => {
      expect((await call(port, '/health/live', { [name]: otherUserId })).status).toBe(403);
    },
  );
  it.each(['userId', 'user_id', 'actorId', 'tenantId', 'identity[userId]'])(
    'rejects authority query %s', async field => {
      expect((await call(port, '/_test/actor?' + encodeURIComponent(field) + '=' + otherUserId,
        { Origin: 'kinlin-app://shell' })).status).toBe(403);
    },
  );
  it('rejects body identity overrides before a handler runs', async () => {
    const result = await call(port, '/_test/write', { Origin: 'kinlin-app://shell', 'X-Zhiyi-Local-Request': '1' },
      'POST', { nested: [{ authenticated_user_id: otherUserId }] });
    expect(result.status).toBe(403); expect(JSON.parse(result.body).error).toBe('IDENTITY_OVERRIDE_FORBIDDEN');
  });
  it('rejects simple cross-site writes and requires the local non-simple request header', async () => {
    expect((await call(port, '/_test/write', { Origin: 'kinlin-app://shell' }, 'POST', {})).status).toBe(403);
    expect((await call(port, '/_test/write', { Origin: 'http://evil.example', 'X-Zhiyi-Local-Request': '1' }, 'POST', {})).status).toBe(403);
    expect((await call(port, '/_test/write', { Origin: 'kinlin-app://shell', 'X-Zhiyi-Local-Request': '1' }, 'POST', {})).status).toBe(200);
  });
});

describe('not-ready and shutdown behavior', () => {
  it.each(['missing', 'wrong-actor', 'wrong-home'])(
    '%s mapping keeps live but rejects readiness and business handlers', async failure => {
      const f = await fixture(failure === 'wrong-home' ? { ...mapping, homeBinding: 'other-home' }
        : { ...mapping, actorId: otherUserId });
      const config = failure === 'missing' ? readConfig({ ZHIYI_BACKEND_TS_PORT: '0' }) : f.config;
      const app = await createApp(config);
      let handled = false;
      app.get('/_test/business', async () => { handled = true; return {}; });
      try {
        await app.listen({ host: '127.0.0.1', port: 0 }); const port = getPort(app);
        expect((await call(port)).status).toBe(200);
        const ready = await call(port, '/health/ready'); expect(ready.status).toBe(503);
        expect(ready.body).not.toContain(f.file); expect(ready.body).not.toContain(legacyUserId);
        expect((await call(port, '/_test/business', { Origin: 'kinlin-app://shell' })).status).toBe(503);
        expect(handled).toBe(false);
      } finally { await app.close(); await f.cleanup(); }
    },
  );
  it('closes idle keep-alive connections and releases the listener for immediate reuse', async () => {
    const app = await createApp(readConfig({ ZHIYI_BACKEND_TS_PORT: '0' }));
    const agent = new Agent({ keepAlive: true });
    try {
      await app.listen({ host: '127.0.0.1', port: 0 }); const port = getPort(app);
      await call(port, '/health/live', {}, 'GET', undefined, agent);
      await app.close(); expect(app.server.listening).toBe(false);
      const replacement = createServer();
      try {
        replacement.listen(port, '127.0.0.1'); await once(replacement, 'listening');
      } finally { await new Promise<void>(resolve => replacement.close(() => resolve())); }
    } finally { agent.destroy(); await app.close(); }
  });
  it('finishes an in-flight handler before close resolves', async () => {
    const f = await fixture(); const app = await createApp(f.config);
    let release!: () => void;
    let entered!: () => void;
    const gate = new Promise<void>(resolve => { release = resolve; });
    const started = new Promise<void>(resolve => { entered = resolve; });
    app.get('/_test/inflight', async () => { entered(); await gate; return { completed: true }; });
    try {
      await app.listen({ host: '127.0.0.1', port: 0 }); const port = getPort(app);
      const response = call(port, '/_test/inflight', { Origin: 'kinlin-app://shell' });
      await started;
      const closing = app.close();
      release();
      const result = await response;
      expect(result.status).toBe(200); expect(JSON.parse(result.body)).toEqual({ completed: true });
      await closing; expect(app.server.listening).toBe(false);
    } finally { release(); await app.close(); await f.cleanup(); }
  });
});
