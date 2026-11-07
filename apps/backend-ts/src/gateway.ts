import { randomUUID } from 'node:crypto';
import { Readable } from 'node:stream';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import type { LocalIdentity } from './identity.js';
import { projectAgentOsResponse } from './gateway-projections.js';

export interface GatewayConfig {
  readonly pythonBaseUrl?: string;
  readonly internalServiceToken?: string;
  readonly aiTimeoutMs?: number;
  readonly streamIdleTimeoutMs?: number;
  readonly streamMaxDurationMs?: number;
}

export interface PythonRequest {
  identity: Readonly<LocalIdentity>;
  method?: string;
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
  timeoutMs?: number;
}

export class GatewayError extends Error {
  constructor(readonly status: number, readonly code: string) { super(code); }
}

const requestHeaders = ['accept', 'accept-language', 'content-type', 'last-event-id', 'range', 'if-range'];
const responseHeaders = ['content-type', 'content-disposition', 'cache-control', 'etag', 'last-modified',
  'content-range', 'accept-ranges', 'retry-after', 'x-mission-launch-conflict', 'x-request-id', 'x-trace-id', 'x-rag-download-source'];

function safePath(path: string): string {
  if (!path.startsWith('/') || path.startsWith('//') || /[\\\u0000-\u001f\u007f#]/u.test(path)) {
    throw new GatewayError(400, 'INVALID_UPSTREAM_PATH');
  }
  let decoded: string;
  try { decoded = decodeURIComponent(path.split('?')[0]!); }
  catch { throw new GatewayError(400, 'INVALID_UPSTREAM_PATH'); }
  if (decoded.split('/').some(segment => segment === '..' || segment === '.') || /[\\\u0000-\u001f\u007f]/u.test(decoded)) {
    throw new GatewayError(400, 'INVALID_UPSTREAM_PATH');
  }
  return path;
}

/** The only Python transport. Credentials and actor context are rebuilt on the server. */
export class PythonGateway {
  readonly config: GatewayConfig;
  readonly baseUrl: string;
  private readonly active = new Set<AbortController>();

  constructor(config: GatewayConfig) {
    this.config = config;
    const url = new URL(config.pythonBaseUrl ?? 'http://127.0.0.1:18761');
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
      throw new Error('Invalid Python service URL');
    }
    this.baseUrl = url.origin + url.pathname.replace(/\/$/u, '');
  }

  close(): void {
    for (const controller of this.active) controller.abort();
    this.active.clear();
  }

  async request(path: string, options: PythonRequest): Promise<Response> {
    safePath(path);
    const token = this.config.internalServiceToken?.trim();
    if (!token || token.length < 32) throw new GatewayError(503, 'AI_INTERNAL_AUTH_NOT_CONFIGURED');
    const headers = new Headers();
    const supplied = new Headers(options.headers);
    for (const name of requestHeaders) {
      const value = supplied.get(name);
      if (value !== null) headers.set(name, value);
    }
    headers.set('x-internal-service-token', token);
    headers.set('x-authenticated-user-id', options.identity.actorId);
    headers.set('x-authenticated-user-subject', options.identity.actorId);
    headers.set('x-authenticated-user-role', 'user');
    if (options.identity.tenantId) headers.set('x-authenticated-tenant-id', options.identity.tenantId);
    headers.set('x-trace-id', randomUUID());

    const controller = new AbortController();
    this.active.add(controller);
    const parentAborted = () => controller.abort(options.signal?.reason);
    options.signal?.addEventListener('abort', parentAborted, { once: true });
    if (options.signal?.aborted) parentAborted();
    let timeout: NodeJS.Timeout | undefined;
    let idle: NodeJS.Timeout | undefined;
    let timedOut = false;
    const expire = () => {
      timedOut = true;
      controller.abort(new GatewayError(504, 'AI_UPSTREAM_TIMEOUT'));
    };
    const schedule = (ms: number) => { const timer = setTimeout(expire, ms); timer.unref(); return timer; };
    timeout = schedule(options.timeoutMs ?? this.config.aiTimeoutMs ?? 120_000);
    const cleanup = () => {
      clearTimeout(timeout);
      clearTimeout(idle);
      options.signal?.removeEventListener('abort', parentAborted);
      this.active.delete(controller);
    };
    try {
      const method = options.method ?? 'GET';
      let body: BodyInit | undefined;
      if (options.body !== undefined && method !== 'GET' && method !== 'HEAD') {
        if (Buffer.isBuffer(options.body)) {
          body = new Uint8Array(options.body);
        } else if (typeof options.body === 'string' || options.body instanceof FormData
          || options.body instanceof Blob || options.body instanceof URLSearchParams || options.body instanceof ReadableStream) {
          body = options.body;
        } else {
          body = JSON.stringify(options.body);
          headers.set('content-type', 'application/json');
        }
      }
      const init: RequestInit & { duplex?: 'half' } = { method, headers, body, signal: controller.signal, redirect: 'manual' };
      if (body instanceof ReadableStream) init.duplex = 'half';
      const upstream = await fetch(this.baseUrl + path, init);
      if (!upstream.body || ['HEAD'].includes(method) || [204, 205, 304].includes(upstream.status)) {
        cleanup();
        return upstream;
      }
      const streaming = upstream.headers.get('content-type')?.toLowerCase().includes('text/event-stream');
      if (streaming) {
        clearTimeout(timeout);
        const maximum = this.config.streamMaxDurationMs ?? 0;
        if (maximum > 0) timeout = schedule(maximum);
      }
      const touch = () => {
        if (!streaming) return;
        clearTimeout(idle);
        idle = schedule(this.config.streamIdleTimeoutMs ?? 60_000);
      };
      touch();
      const reader = upstream.body.getReader();
      const stream = new ReadableStream<Uint8Array>({
        async pull(destination) {
          try {
            const result = await reader.read();
            if (result.done) { cleanup(); destination.close(); }
            else { touch(); destination.enqueue(result.value); }
          } catch (error) {
            cleanup();
            destination.error(timedOut ? new GatewayError(504, 'AI_UPSTREAM_TIMEOUT') : error);
          }
        },
        async cancel(reason) {
          controller.abort(reason);
          cleanup();
          await reader.cancel(reason).catch(() => undefined);
        },
      });
      return new Response(stream, { status: upstream.status, statusText: upstream.statusText, headers: upstream.headers });
    } catch (error) {
      cleanup();
      if (timedOut) throw new GatewayError(504, 'AI_UPSTREAM_TIMEOUT');
      if (controller.signal.aborted) throw error;
      if (error instanceof GatewayError) throw error;
      throw new GatewayError(503, 'AI_UPSTREAM_UNAVAILABLE');
    }
  }

  async forward(request: FastifyRequest, reply: FastifyReply, path: string, body: unknown = request.body): Promise<FastifyReply> {
    const controller = new AbortController();
    const aborted = () => controller.abort();
    const closed = () => { if (!reply.raw.writableEnded) aborted(); };
    request.raw.once('aborted', aborted);
    reply.raw.once('close', closed);
    const cleanup = () => {
      request.raw.off('aborted', aborted);
      reply.raw.off('close', closed);
    };
    reply.raw.once('finish', cleanup);
    try {
      if (!request.localIdentity) throw new GatewayError(503, 'LOCAL_IDENTITY_NOT_CONFIGURED');
      const upstream = await this.request(path, {
        identity: request.localIdentity,
        method: request.method,
        body,
        headers: Object.fromEntries(requestHeaders.flatMap(name => {
          const value = request.headers[name];
          return typeof value === 'string' ? [[name, value]] : [];
        })),
        signal: controller.signal,
      });
      reply.code(upstream.status);
      for (const name of responseHeaders) {
        const value = upstream.headers.get(name);
        if (value !== null) reply.header(name, value);
      }
      if (!upstream.body || request.method === 'HEAD') return reply.send();
      const jsonProjection = request.method === 'GET' && path.startsWith('/ai/agentos/v2/')
        && upstream.ok && upstream.headers.get('content-type')?.includes('application/json');
      if (jsonProjection) {
        const body: unknown = await upstream.json();
        return reply.send(projectAgentOsResponse(path.split('?')[0]!, body));
      }
      if (upstream.headers.get('content-type')?.includes('text/event-stream')) {
        reply.header('cache-control', 'no-cache').header('x-accel-buffering', 'no');
      }
      return reply.send(Readable.fromWeb(upstream.body as import('node:stream/web').ReadableStream));
    } catch (error) {
      cleanup();
      if (controller.signal.aborted || reply.raw.destroyed) return reply;
      const failure = error instanceof GatewayError ? error : new GatewayError(502, 'AI_UPSTREAM_INVALID_RESPONSE');
      const agentos = path.startsWith('/ai/agentos/v2/');
      return reply.code(failure.status).send(agentos
        ? { code: failure.code.replace(/^AI_/u, 'AGENTOS_'), message: 'AgentOS service request failed.' }
        : { error: failure.code, message: 'AI service request failed.' });
    }
  }
}

/** Raw multipart preserves filenames, binary data, field order and the original boundary. */
export function registerGateway(app: FastifyInstance, config: GatewayConfig | PythonGateway): PythonGateway {
  const gateway = config instanceof PythonGateway ? config : new PythonGateway(config);
  app.register(async scope => {
  for (const type of ['multipart/form-data', 'application/octet-stream', 'audio/wav', 'audio/mpeg']) {
    if (scope.hasContentTypeParser(type)) scope.removeContentTypeParser(type);
    scope.addContentTypeParser(type, { parseAs: 'buffer', bodyLimit: 100 * 1024 * 1024 }, (_request, body, done) => done(null, body));
  }
  scope.route({ method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'], url: '/api/agentos/v2/*',
    bodyLimit: 100 * 1024 * 1024,
    handler: (request, reply) => gateway.forward(request, reply, request.url.replace(/^\/api\/agentos\/v2/u, '/ai/agentos/v2')) });
  scope.route({ method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'], url: '/ai/*',
    bodyLimit: 100 * 1024 * 1024,
    handler: (request, reply) => gateway.forward(request, reply, request.url) });
  scope.route({ method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'], url: '/api/ai/*',
    bodyLimit: 100 * 1024 * 1024,
    handler: (request, reply) => gateway.forward(request, reply, request.url.replace(/^\/api\/ai/u, '/ai')) });
  for (const prefix of ['/rag', '/api/rag']) {
    scope.route({ method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'], url: `${prefix}/*`,
      bodyLimit: 100 * 1024 * 1024,
      handler: (request, reply) => gateway.forward(request, reply, request.url.replace(/^\/api\/rag/u, '/rag')) });
  }
  scope.route({ method: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD'], url: '/api/knowledge-graph/*',
    handler: (request, reply) => {
      const url = new URL(request.url, 'http://localhost');
      const body = request.body as Record<string, unknown> | undefined;
      let payload: unknown = body;
      if (request.method === 'POST' && url.pathname.endsWith('/build')) {
        payload = { ...body, role_id: body?.roleId ?? body?.role_id,
          documents: (Array.isArray(body?.documents) ? body.documents : []).map(document => {
            const value = document as Record<string, unknown>;
            return { ...value, doc_id: value.docId ?? value.doc_id };
          }) };
      } else if (request.method === 'POST' && url.pathname.endsWith('/search') && Array.isArray(body)) {
        payload = { question: url.searchParams.get('question'), vector_db_results: body, top_k: Number(url.searchParams.get('topK') ?? 5) };
      } else if (request.method === 'POST' && url.pathname.endsWith('/reason') && !body?.question) {
        payload = { question: url.searchParams.get('question') };
      }
      return gateway.forward(request, reply, request.url, payload);
    } });
  scope.route({ method: ['GET', 'POST'], url: '/api/role-fusion/*',
    handler: (request, reply) => {
      const body = request.body as Record<string, unknown> | undefined;
      const role = (value: unknown) => {
        const source = value as Record<string, unknown>;
        return { role_id: String(source.roleId ?? source.role_id), knowledge_domain: source.knowledgeDomain ?? source.knowledge_domain ?? [], personality: source.personality };
      };
      const payload = Array.isArray(body) ? body.map(role) : {
        question: body?.question, available_roles: (Array.isArray(body?.availableRoles) ? body.availableRoles : Array.isArray(body?.available_roles) ? body.available_roles : []).map(role),
        role_responses: body?.roleResponses ?? body?.role_responses ?? {},
      };
      return gateway.forward(request, reply, request.url.replace(/^\/api\/role-fusion/u, '/ai/role-fusion'), payload);
    } });
  });
  app.addHook('onClose', async () => gateway.close());
  app.addHook('preClose', async () => gateway.close());
  return gateway;
}
