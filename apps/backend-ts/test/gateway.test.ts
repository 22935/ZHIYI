import { createServer, type Server } from 'node:http';
import { once } from 'node:events';
import Fastify from 'fastify';
import multipart from '@fastify/multipart';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { PythonGateway, registerGateway } from '../src/gateway.js';
import { projectAgentOsResponse } from '../src/gateway-projections.js';

const identity = { actorId: '11111111-1111-4111-8111-111111111111', tenantId: null } as const;
const token = 'gateway-test-service-authentication-token';

describe('Python gateway transport contracts', () => {
  let server: Server;
  let baseUrl: string;
  beforeAll(async () => {
    server = createServer(async (request, reply) => {
      if (request.url === '/ai/slow') {
        setTimeout(() => reply.end('late'), 200).unref();
        return;
      }
      if (request.url?.startsWith('/ai/events')) {
        reply.writeHead(200, { 'content-type': 'text/event-stream' });
        reply.write('event: runtime\nid: 1\ndata: {"text":"首段"}\n\n');
        if (request.url === '/ai/events-idle') return;
        setTimeout(() => reply.end('event: done\ndata: {"usage":{"total_tokens":7}}\n\n'), 30).unref();
        return;
      }
      if (request.url === '/ai/error') {
        reply.writeHead(409, { 'content-type': 'application/json', 'set-cookie': 'private=value' });
        reply.end(JSON.stringify({ code: 'REVISION_CONFLICT', message: 'revision changed', requestId: 'python-request' }));
        return;
      }
      const chunks: Buffer[] = [];
      for await (const chunk of request) chunks.push(Buffer.from(chunk));
      const body = Buffer.concat(chunks);
      if (request.url === '/ai/binary') {
        reply.writeHead(206, { 'content-type': 'application/octet-stream', 'content-disposition': 'attachment; filename="artifact.bin"', 'content-range': 'bytes 0-3/4' });
        reply.end(Buffer.from([0, 255, 127, 10]));
      } else if (request.url === '/ai/upload') {
        reply.writeHead(201, { 'content-type': request.headers['content-type'] }); reply.end(body);
      } else {
        reply.setHeader('content-type', 'application/json');
        reply.end(JSON.stringify({ method: request.method, path: request.url, headers: request.headers, body: body.toString() }));
      }
    });
    server.listen(0, '127.0.0.1'); await once(server, 'listening');
    const address = server.address();
    if (!address || typeof address === 'string') throw new Error('missing listener');
    baseUrl = `http://127.0.0.1:${address.port}`;
  });
  afterAll(async () => { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); });

  const gateway = () => new PythonGateway({ pythonBaseUrl: baseUrl, internalServiceToken: token });

  it('rebuilds trusted identity and service authentication, stripping supplied authority and cookie headers', async () => {
    const client = gateway();
    const response = await client.request('/ai/echo?cursor=a%2Fb', { identity, method: 'POST', body: { message: '真实输入' },
      headers: { authorization: 'old-user-jwt', cookie: 'session=old', 'x-authenticated-user-id': 'forged', 'x-internal-service-token': 'forged', 'x-authenticated-tenant-id': 'forged' } });
    const value = await response.json() as { path: string; headers: Record<string, string>; body: string };
    expect(value.path).toBe('/ai/echo?cursor=a%2Fb');
    expect(value.headers['x-internal-service-token']).toBe(token);
    expect(value.headers['x-authenticated-user-id']).toBe(identity.actorId);
    expect(value.headers['x-authenticated-tenant-id']).toBeUndefined();
    expect(value.headers.authorization).toBeUndefined(); expect(value.headers.cookie).toBeUndefined();
    expect(JSON.parse(value.body)).toEqual({ message: '真实输入' });
    client.close();
  });

  it('preserves HTTP business errors and binary responses through Fastify', async () => {
    const app = Fastify();
    app.decorateRequest('localIdentity', null);
    app.addHook('onRequest', async request => { request.localIdentity = identity; });
    registerGateway(app, gateway());
    const error = await app.inject('/ai/error');
    expect(error.statusCode).toBe(409); expect(error.json()).toEqual({ code: 'REVISION_CONFLICT', message: 'revision changed', requestId: 'python-request' });
    expect(error.headers['set-cookie']).toBeUndefined();
    const binary = await app.inject('/ai/binary');
    expect(binary.statusCode).toBe(206); expect(binary.rawPayload).toEqual(Buffer.from([0, 255, 127, 10]));
    expect(binary.headers['content-disposition']).toBe('attachment; filename="artifact.bin"');
    expect(binary.headers['content-range']).toBe('bytes 0-3/4');
    const apiAlias = await app.inject('/api/ai/error');
    expect(apiAlias.statusCode).toBe(409);
    expect(apiAlias.json().code).toBe('REVISION_CONFLICT');
    await app.close();
  });

  it('keeps raw multipart bytes after the parent registers multipart handling', async () => {
    const app = Fastify();
    await app.register(multipart);
    app.decorateRequest('localIdentity', null);
    app.addHook('onRequest', async request => { request.localIdentity = identity; });
    registerGateway(app, gateway());
    const bytes = Buffer.concat([Buffer.from('--test-boundary\r\nContent-Disposition: form-data; name="file"; filename="sample.bin"\r\nContent-Type: application/octet-stream\r\n\r\n'), Buffer.from([0, 255, 1, 10]), Buffer.from('\r\n--test-boundary--\r\n')]);
    const response = await app.inject({ method: 'POST', url: '/ai/upload', headers: { 'content-type': 'multipart/form-data; boundary=test-boundary' }, payload: bytes });
    expect(response.statusCode).toBe(201); expect(response.rawPayload).toEqual(bytes);
    await app.close();
  });

  it('forwards SSE chunks before completion and retains event ids and usage', async () => {
    const client = gateway();
    const response = await client.request('/ai/events', { identity });
    const reader = response.body!.getReader();
    expect(new TextDecoder().decode((await reader.read()).value)).toContain('event: runtime\nid: 1');
    let text = '';
    for (;;) { const chunk = await reader.read(); if (chunk.done) break; text += new TextDecoder().decode(chunk.value); }
    expect(text).toContain('"total_tokens":7'); client.close();
  });

  it('propagates cancellation, request deadlines and stream idle timeouts', async () => {
    const client = new PythonGateway({ pythonBaseUrl: baseUrl, internalServiceToken: token, aiTimeoutMs: 30, streamIdleTimeoutMs: 30 });
    await expect(client.request('/ai/slow', { identity })).rejects.toMatchObject({ status: 504, code: 'AI_UPSTREAM_TIMEOUT' });
    const signal = new AbortController();
    const response = await client.request('/ai/events-idle', { identity, signal: signal.signal });
    const reader = response.body!.getReader(); await reader.read(); signal.abort();
    await expect(reader.read()).rejects.toBeDefined();
    const idle = await client.request('/ai/events-idle', { identity });
    const idleReader = idle.body!.getReader(); await idleReader.read();
    await expect(idleReader.read()).rejects.toMatchObject({ status: 504 }); client.close();
  });

  it('rejects traversal and missing service credentials without making an upstream request', async () => {
    const client = gateway();
    for (const path of ['//third-party/ai/x', '/ai/%2e%2e/private', '/ai/../private', '/ai/%5cprivate']) {
      await expect(client.request(path, { identity })).rejects.toMatchObject({ status: 400 });
    }
    await expect(new PythonGateway({ pythonBaseUrl: baseUrl }).request('/ai/echo', { identity })).rejects.toMatchObject({ status: 503 });
    client.close();
  });
});

describe('workbench response compatibility', () => {
  it('retains the workbench graph, execution resource and node health field names', () => {
    expect(projectAgentOsResponse('/ai/agentos/v2/missions/mission', { mission: {}, tasks: [], blueprints: [{ graphId: 'graph', version: 1 }], runs: [] })).toHaveProperty('graphs', [{ graphId: 'graph', version: 1, createdAt: null }]);
    expect(projectAgentOsResponse('/ai/agentos/v2/nodes', { items: [{ profile: { nodeId: 'node' }, health: { status: 'healthy' }, snapshotVersion: 2 }], total: 1 })).toMatchObject({ items: [{ healthStatus: 'healthy' }] });
    expect(projectAgentOsResponse('/ai/agentos/v2/runs/run/execution-tree', { run: {}, blueprint: { graphId: 'graph', version: 1, graph: { nodes: [], edges: [] } }, nodes: [{ task: { taskId: 'task', constraints: [] }, attempts: [{ attempt: {}, executions: [], executionBinding: { resourceId: 'resource' } }] }] })).toMatchObject({ graph: { graphId: 'graph' }, lifecycles: [], nodes: [{ attempts: [{ resourceUse: { resourceId: 'resource' } }] }] });
  });
  it('projects review, lineage and output references without exposing execution snapshots', () => {
    const result = projectAgentOsResponse('/ai/agentos/v2/runs/run', { runId: 'run', missionId: 'mission', status: 'waiting_review',
      executionState: { graphVersion: 2, reviewPayload: { subjectId: 'review', secret: 'private' }, parentRunId: 'parent', outputRefs: { step: 'manifest' }, outputSummaries: { step: 'summary' }, pendingMemory: 'private' } });
    expect(result).toMatchObject({ runId: 'run', graphVersion: 2, review: { subjectId: 'review' }, lineage: { parentRunId: 'parent' }, outputs: [{ stepId: 'step', outputRef: 'manifest', summary: 'summary' }] });
    expect(JSON.stringify(result)).not.toContain('private'); expect(result).not.toHaveProperty('executionState');
  });
  it('preserves product output content while keeping dynamic history/catalog associations readable', () => {
    expect(projectAgentOsResponse('/ai/agentos/v2/runs/run/outputs/ref', { runId: 'run', outputRef: 'ref', content: { report: ['完整输出', false, 1.25, null] } })).toMatchObject({ content: { kind: 'object', members: [{ name: 'report', value: { kind: 'list', items: [{ text: '完整输出' }, { bool: false }, { number: 1.25 }, { kind: 'null' }] } }] } });
    expect(projectAgentOsResponse('/ai/agentos/v2/runs/run/history-config', { runId: 'run', input: { pluginData: { plugin: { enabled: false, limit: 2, name: 'saved', internal: { private: true } } } } })).toMatchObject({ input: { pluginData: [{ pluginId: 'plugin', entries: [{ name: 'enabled', bool: false }, { name: 'limit', number: 2 }, { name: 'name', text: 'saved' }] }] } });
  });
});
