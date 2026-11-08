export interface Config {
  readonly port: number;
  readonly allowedOrigins: readonly string[];
  readonly identityFile?: string;
  readonly expectedUserId?: string;
  readonly homeBinding?: string;
  readonly databaseUrl?: string;
  readonly pythonBaseUrl?: string;
  readonly internalServiceToken?: string;
  readonly aiTimeoutMs?: number;
  readonly streamIdleTimeoutMs?: number;
  readonly streamMaxDurationMs?: number;
  readonly uploadDir?: string;
}

export function readConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const rawPort = env.ZHIYI_BACKEND_TS_PORT ?? '18080';
  if (!/^\d+$/.test(rawPort)) throw new Error('Invalid backend-ts port');
  const port = Number(rawPort);
  const existingPorts = [15432, 16379, 18761, 18765, 15200, 18766, 19222];
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
  const numeric = (value: string | undefined, fallback: number, minimum: number, maximum: number) => {
    if (value === undefined || value === '') return fallback;
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed < minimum || parsed > maximum) throw new Error('Invalid backend timeout');
    return parsed;
  };
  return Object.freeze({
    port,
    allowedOrigins: Object.freeze(allowedOrigins),
    identityFile: env.ZHIYI_BACKEND_TS_IDENTITY_FILE,
    expectedUserId: env.ZHIYI_BACKEND_TS_EXPECTED_USER_ID,
    homeBinding: env.ZHIYI_BACKEND_TS_HOME_BINDING,
    databaseUrl: env.ZHIYI_DATABASE_URL ?? env.DATABASE_URL,
    pythonBaseUrl: env.AI_SERVICE_URL ?? env.PYTHON_SERVICE_URL ?? 'http://127.0.0.1:18761',
    internalServiceToken: env.AI_INTERNAL_TOKEN,
    aiTimeoutMs: numeric(env.AI_TIMEOUT_MS, 240000, 1, 86_400_000),
    streamIdleTimeoutMs: numeric(env.SSE_IDLE_TIMEOUT_MS ?? env.SSE_IDLE_TIMEOUT, 240000, 1, 86_400_000),
    streamMaxDurationMs: numeric(env.SSE_MAX_DURATION_MS ?? env.SSE_MAX_DURATION, 0, 0, 86_400_000),
    uploadDir: env.APP_UPLOAD_DIR,
  });
}
