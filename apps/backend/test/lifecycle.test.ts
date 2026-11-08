import Fastify from 'fastify';
import { once } from 'node:events';
import { get } from 'node:http';
import { expect, it } from 'vitest';
import { trackRequestCompletion } from '../src/lifecycle.js';

it('waits for handler cleanup after an SSE client disconnects', async () => {
  const app = Fastify(); trackRequestCompletion(app);
  let cleanup!: () => void, disconnected!: () => void;
  const cleanupGate = new Promise<void>(resolve => { cleanup = resolve; });
  const sawDisconnect = new Promise<void>(resolve => { disconnected = resolve; });
  app.get('/stream', async (_request, reply) => {
    reply.hijack(); reply.raw.writeHead(200, { 'content-type': 'text/event-stream' });
    reply.raw.write('data: first\n\n');
    await once(reply.raw, 'close');
    disconnected();
    await cleanupGate; // represents Chat's asynchronous history transaction
  });
  await app.listen({ host: '127.0.0.1', port: 0 });
  const address = app.server.address();
  if (!address || typeof address === 'string') throw new Error('Missing test listener');
  try {
    const request = get(`http://127.0.0.1:${address.port}/stream`);
    request.on('error', () => undefined);
    const [response] = await once(request, 'response');
    response.on('error', () => undefined);
    response.destroy();
    await sawDisconnect;
    let idle = false;
    const drained = app.waitForIdle().then(() => { idle = true; });
    await new Promise(resolve => setTimeout(resolve, 30));
    expect(idle).toBe(false);
    cleanup(); await drained;
    expect(idle).toBe(true);
  } finally { cleanup(); await app.close(); }
});
