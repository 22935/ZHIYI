import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { basename, dirname, join, resolve } from 'node:path';
import { readConfig } from '../src/config.js';

// Synthetic values only. Never load the real N03 Home, DB, audit snapshot or Workspace.
export const legacyUserId = '11111111-1111-4111-8111-111111111111';
export const otherUserId = '22222222-2222-4222-8222-222222222222';
export const mapping = {
  format: 'zhiyi-local-identity-v1', version: 1,
  actorId: legacyUserId, legacyUserId, wireTenantId: null, homeBinding: 'isolated-test-home',
};

export async function fixture(value: unknown = mapping) {
  const directory = await mkdtemp(join(tmpdir(), 'zhiyi-backend-ts-test-'));
  const file = join(directory, 'identity.json');
  await writeFile(file, JSON.stringify(value));
  const env = {
    ZHIYI_BACKEND_TS_PORT: '0',
    ZHIYI_BACKEND_TS_IDENTITY_FILE: file,
    ZHIYI_BACKEND_TS_EXPECTED_USER_ID: legacyUserId,
    ZHIYI_BACKEND_TS_HOME_BINDING: mapping.homeBinding,
  };
  return {
    file, env, config: readConfig(env),
    async cleanup() {
      // Only this helper's newly-created, direct temp child may be recursively removed.
      if (dirname(resolve(directory)) !== resolve(tmpdir()) || !basename(directory).startsWith('zhiyi-backend-ts-test-')) {
        throw new Error('Unsafe test cleanup path');
      }
      await rm(directory, { recursive: true, force: true });
    },
  };
}
