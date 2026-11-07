import { describe, expect, it } from 'vitest';
import { readConfig } from '../src/config.js';

describe('isolated configuration', () => {
  it('uses an independent default and ignores Java/Native environment', () => {
    const config = readConfig({ SERVER_PORT: '18080', SERVER_ADDRESS: '0.0.0.0' });
    expect(config.port).toBe(18081);
    expect(config.allowedOrigins).toEqual(['kinlin-app://shell']);
  });
  it('supports an OS-assigned test port', () => {
    expect(readConfig({ ZHIYI_BACKEND_TS_PORT: '0' }).port).toBe(0);
  });
  it.each(['-1', '', ' ', '1.2', 'NaN', '65536', '18080', '15432', '16379', '18761', '18765', '15200', '18766', '19222'])(
    'rejects invalid or existing-system port %j', port => {
      expect(() => readConfig({ ZHIYI_BACKEND_TS_PORT: port })).toThrow();
    },
  );
  it('accepts an explicit development loopback origin', () => {
    expect(readConfig({ ZHIYI_BACKEND_TS_DEV_ORIGIN: 'http://127.0.0.1:34567' }).allowedOrigins)
      .toContain('http://127.0.0.1:34567');
  });
  it.each(['null', '*', 'https://example.com', 'http://127.0.0.1', 'http://127.0.0.1:34567/',
    'http://user@127.0.0.1:34567', 'http://127.0.0.1:34567/path', 'http://127.0.0.1:34567?x=1'])(
    'rejects non-origin or non-loopback development configuration %j', origin => {
      expect(() => readConfig({ ZHIYI_BACKEND_TS_DEV_ORIGIN: origin })).toThrow();
    },
  );
});
