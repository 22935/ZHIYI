import Fastify from 'fastify';
import type { Config } from './config.js';
import { loadIdentity, type LocalIdentity } from './identity.js';
import { createDatabase } from './db.js';
import { registerPlatform } from './platform.js';
import { registerChat } from './chat.js';
import { PythonGateway, registerGateway } from './gateway.js';
import { trackRequestCompletion } from './lifecycle.js';

declare module 'fastify' {
  interface FastifyRequest { localIdentity: Readonly<LocalIdentity> | null }
}

const authorityFields = new Set([
  'actorid', 'userid', 'tenantid', 'legacyuserid', 'authenticateduserid', 'authenticatedtenantid',
]);

function hasIdentityClaim(value: unknown): boolean {
  const pending = [value];
  while (pending.length) {
    const item = pending.pop();
    if (!item || typeof item !== 'object' || Buffer.isBuffer(item)) continue;
    for (const [key, child] of Object.entries(item)) {
      if (key.split(/[\[\].]/).some(part => authorityFields.has(part.replace(/[_-]/g, '').toLowerCase()))) {
        return true;
      }
      pending.push(child);
    }
  }
  return false;
}

export async function createApp(config: Config) {
  const state = await loadIdentity(config);
  const db = createDatabase(config);
  // An idle connection failure must not become an unhandled EventEmitter error.
  db.on('error', () => undefined);
  const gateway = new PythonGateway(config);
  const app = Fastify({
    logger: false,
    trustProxy: false,
    bodyLimit: 32 * 1024 * 1024,
    requestTimeout: 120000,
    connectionTimeout: 0,
    forceCloseConnections: 'idle',
    return503OnClosing: true,
  });
  trackRequestCompletion(app);
  app.decorateRequest('localIdentity', null);
  app.setErrorHandler((error, request, reply) => {
    const failure = error as { statusCode?: number; code?: string; message?: string };
    if (failure.code === '23505') {
      return reply.code(409).send({ error: 'RESOURCE_CONFLICT', message: '资源已存在，请使用其他名称' });
    }
    const status = typeof failure.statusCode === 'number' ? failure.statusCode : 500;
    if (status >= 500) {
      request.log.error({ code: failure.code ?? 'BACKEND_REQUEST_FAILED' }, 'Backend request failed');
      return reply.code(status).send({ error: 'BACKEND_REQUEST_FAILED', message: '平台服务请求失败' });
    }
    return reply.code(status).send({ error: failure.code ?? 'INVALID_REQUEST', message: failure.message });
  });

  app.addHook('onRequest', async (request, reply) => {
    const address = app.server.address();
    const port = address && typeof address !== 'string' ? address.port : config.port;
    const countHeader = (name: string) => request.raw.rawHeaders.filter((v, i) =>
      i % 2 === 0 && v.toLowerCase() === name).length;
    if (countHeader('host') !== 1 || request.headers.host !== `127.0.0.1:${port}`) {
      return reply.code(403).send({ error: 'LOCAL_HOST_REJECTED' });
    }
    const origin = request.headers.origin;
    if (countHeader('origin') > 1 || (origin !== undefined && !config.allowedOrigins.includes(origin))) {
      return reply.code(403).send({ error: 'LOCAL_ORIGIN_REJECTED' });
    }
    const forgedHeader = Object.keys(request.headers).some(name => name.startsWith('x-authenticated-')
      || ['authorization', 'x-user-id', 'x-actor-id', 'x-tenant-id', 'x-internal-service-token'].includes(name));
    if (forgedHeader || hasIdentityClaim(request.query)) {
      return reply.code(403).send({ error: 'IDENTITY_OVERRIDE_FORBIDDEN' });
    }
    if (origin !== undefined) {
      reply.header('Access-Control-Allow-Origin', origin).header('Vary', 'Origin');
      reply.header('Access-Control-Expose-Headers', 'Content-Disposition, Content-Range, X-Request-Id, X-Context-Id, X-Chat-Context-Id, X-Chat-Request-Id, X-RAG-Download-Source, X-Mission-Launch-Conflict');
    }
    if (request.method === 'OPTIONS' && origin) {
      return reply.header('Access-Control-Allow-Methods', 'GET,HEAD,POST,PUT,PATCH,DELETE,OPTIONS')
        .header('Access-Control-Allow-Headers', 'Content-Type, X-Zhiyi-Local-Request, Last-Event-ID')
        .code(204).send();
    }
    reply.header('Cache-Control', 'no-store');
    const path = request.url.split('?')[0];
    const health = ['GET', 'HEAD'].includes(request.method)
      && ['/health/live', '/health/ready', '/api/health/ready', '/api/health/live'].includes(path);
    if (!health) {
      if (!origin) return reply.code(403).send({ error: 'LOCAL_ORIGIN_REQUIRED' });
      if (!state.identity) return reply.code(503).send({ error: state.error });
      if (!['GET', 'HEAD', 'OPTIONS'].includes(request.method)
        && request.headers['x-zhiyi-local-request'] !== '1') {
        return reply.code(403).send({ error: 'LOCAL_REQUEST_HEADER_REQUIRED' });
      }
    }
    request.localIdentity = state.identity;
  });
  app.addHook('preValidation', async (request, reply) => {
    if (hasIdentityClaim(request.body)) {
      return reply.code(403).send({ error: 'IDENTITY_OVERRIDE_FORBIDDEN' });
    }
  });
  for (const path of ['/health/live', '/api/health/live']) app.get(path, async () => ({ status: 'UP' }));
  for (const path of ['/health/ready', '/api/health/ready']) app.get(path, async (_request, reply) => {
    if (!state.identity) return reply.code(503).send({ status: 'DOWN', reason: state.error });
    if (!config.databaseUrl && !process.env.PGHOST) {
      return reply.code(503).send({ status: 'DOWN', reason: 'DATABASE_NOT_CONFIGURED' });
    }
    try {
      const result = await db.query('SELECT id FROM users WHERE id=$1', [state.identity.actorId]);
      if (result.rowCount !== 1) throw new Error('Owner missing');
      return { status: 'UP' };
    } catch { return reply.code(503).send({ status: 'DOWN', reason: 'DATABASE_NOT_READY' }); }
  });
  await registerPlatform(app, db, config);
  await registerChat(app, db, gateway, config);
  registerGateway(app, gateway);
  app.addHook('preClose', async () => gateway.close());
  app.addHook('onClose', async () => db.end());
  return app;
}
