import Fastify from 'fastify';
import type { Config } from './config.js';
import { loadIdentity, type LocalIdentity } from './identity.js';

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
    if (!item || typeof item !== 'object') continue;
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
  const app = Fastify({
    logger: false,
    trustProxy: false,
    bodyLimit: 16 * 1024,
    requestTimeout: 5000,
    connectionTimeout: 5000,
    forceCloseConnections: 'idle',
    return503OnClosing: true,
  });
  app.decorateRequest('localIdentity', null);

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
    }
    reply.header('Cache-Control', 'no-store');
    const path = request.url.split('?')[0];
    const health = ['GET', 'HEAD'].includes(request.method)
      && ['/health/live', '/health/ready'].includes(path);
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
  app.get('/health/live', async () => ({ status: 'UP' }));
  app.get('/health/ready', async (_request, reply) => state.identity
    ? { status: 'UP' }
    : reply.code(503).send({ status: 'DOWN', reason: state.error }));
  return app;
}
