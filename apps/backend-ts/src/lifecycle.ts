import type { FastifyInstance } from 'fastify';

declare module 'fastify' {
  interface FastifyInstance { waitForIdle(): Promise<void> }
}

/** Track handler completion, including hijacked SSE cleanup after disconnect.
 * Socket close alone is too early: Chat may still be persisting its reply.
 */
export function trackRequestCompletion(app: FastifyInstance): void {
  let active = 0;
  const waiting = new Set<() => void>();
  const flush = () => {
    if (active || !waiting.size) return;
    setImmediate(() => {
      if (active) return;
      for (const resolve of waiting) resolve();
      waiting.clear();
    });
  };
  app.decorate('waitForIdle', () => new Promise<void>(resolve => { waiting.add(resolve); flush(); }));
  app.addHook('onRoute', options => {
    const handler = options.handler;
    options.handler = async function (request, reply) {
      active++;
      try { return await handler.call(this, request, reply); }
      finally { active--; flush(); }
    };
  });
}
