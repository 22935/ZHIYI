export interface Config {
  readonly port: number;
  readonly allowedOrigins: readonly string[];
  readonly identityFile?: string;
  readonly expectedUserId?: string;
  readonly homeBinding?: string;
}

// Deliberately independent of SERVER_PORT and all Java/Native configuration.
export function readConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const rawPort = env.ZHIYI_BACKEND_TS_PORT ?? '18081';
  if (!/^\d+$/.test(rawPort)) throw new Error('Invalid backend-ts port');
  const port = Number(rawPort);
  const existingPorts = [15432, 16379, 18761, 18765, 18080, 15200, 18766, 19222];
  if (!Number.isSafeInteger(port) || port > 65535 || existingPorts.includes(port)) {
    throw new Error('Invalid or reserved backend-ts port');
  }

  const allowedOrigins = ['kinlin-app://shell'];
  const devOrigin = env.ZHIYI_BACKEND_TS_DEV_ORIGIN;
  if (devOrigin !== undefined) {
    const url = new URL(devOrigin);
    if (url.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(url.hostname)
      || !url.port || url.origin !== devOrigin) {
      throw new Error('Development origin must be an exact loopback HTTP origin with a port');
    }
    allowedOrigins.push(devOrigin);
  }
  return Object.freeze({
    port,
    allowedOrigins: Object.freeze(allowedOrigins),
    identityFile: env.ZHIYI_BACKEND_TS_IDENTITY_FILE,
    expectedUserId: env.ZHIYI_BACKEND_TS_EXPECTED_USER_ID,
    homeBinding: env.ZHIYI_BACKEND_TS_HOME_BINDING,
  });
}
