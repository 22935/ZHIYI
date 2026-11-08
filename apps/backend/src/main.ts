import { createApp } from './app.js';
import { readConfig } from './config.js';

async function main() {
  const config = readConfig();
  const app = await createApp(config);
  let closing = false;
  let reloading = false;
  const stop = () => {
    if (closing) return;
    closing = true;
    void app.close().catch(() => {
      console.error('BACKEND_TS_SHUTDOWN_FAILED');
      process.exitCode = 1;
    });
  };
  const onMessage = (message: unknown) => {
    if (message === 'shutdown') stop();
    else if (message === 'reload' && !reloading && !closing) {
      reloading = true;
      process.send?.({ event: 'reload_pending' });
      void app.waitForIdle().then(stop);
    }
  };
  process.on('SIGINT', stop);
  process.on('SIGTERM', stop);
  // Parent-owned Node IPC gives Windows tests an explicit graceful shutdown path.
  if (process.send) process.on('message', onMessage);
  if (process.connected) process.on('disconnect', stop);
  app.addHook('onClose', async () => {
    process.off('SIGINT', stop);
    process.off('SIGTERM', stop);
    process.off('message', onMessage);
    process.off('disconnect', stop);
    if (process.connected) process.disconnect();
  });
  try {
    const address = await app.listen({ host: '127.0.0.1', port: config.port });
    console.log(JSON.stringify({ event: 'listening', address }));
    process.send?.({ event: 'listening', address });
  } catch (error) {
    await app.close();
    throw error;
  }
}

void main().catch(() => {
  console.error('BACKEND_TS_STARTUP_FAILED');
  process.exitCode = 1;
});
