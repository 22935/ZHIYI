import { readFile, stat, writeFile } from 'node:fs/promises';
import { describe, expect, it } from 'vitest';
import { parseIdentity, loadIdentity } from '../src/identity.js';
import { readConfig } from '../src/config.js';
import { fixture, mapping, legacyUserId, otherUserId } from './fixtures.js';

describe('stable local identity', () => {
  it('preserves the legacy UUID exactly and keeps raw tenant null', () => {
    const identity = parseIdentity(mapping, legacyUserId, mapping.homeBinding);
    expect(identity).toEqual({ actorId: legacyUserId, tenantId: null });
    expect(Object.isFrozen(identity)).toBe(true);
  });
  it.each([
    null, [], {}, { ...mapping, version: 2 }, { ...mapping, format: 'other' },
    { ...mapping, actorId: otherUserId }, { ...mapping, legacyUserId: otherUserId },
    { ...mapping, wireTenantId: '__unscoped__' }, { ...mapping, wireTenantId: '' },
    { ...mapping, homeBinding: 'another-home' }, { ...mapping, actorId: 'not-a-uuid' },
    { ...mapping, extra: true }, { ...mapping, legacyUserId: undefined },
  ])('rejects a mismatched, malformed or unknown-version mapping %#', value => {
    expect(() => parseIdentity(value, legacyUserId, mapping.homeBinding)).toThrow('Invalid local identity');
  });
  it('requires independent expected legacy identity and Home binding', () => {
    expect(() => parseIdentity(mapping)).toThrow();
    expect(() => parseIdentity(mapping, 'not-a-uuid', mapping.homeBinding)).toThrow();
    expect(() => parseIdentity(mapping, legacyUserId, '')).toThrow();
  });
  it('reloads identically without changing the mapping file', async () => {
    const f = await fixture();
    try {
      const before = await stat(f.file);
      const bytes = await readFile(f.file);
      expect(await loadIdentity(f.config)).toEqual(await loadIdentity(f.config));
      expect((await loadIdentity(f.config)).identity?.actorId).toBe(legacyUserId);
      expect(await readFile(f.file)).toEqual(bytes);
      expect((await stat(f.file)).mtimeMs).toBe(before.mtimeMs);
    } finally { await f.cleanup(); }
  });
  it('fails closed for missing configuration, missing file, malformed JSON and relative paths', async () => {
    expect(await loadIdentity(readConfig({}))).toEqual({ identity: null, error: 'LOCAL_IDENTITY_NOT_CONFIGURED' });
    const f = await fixture();
    try {
      expect((await loadIdentity({ ...f.config, identityFile: f.file + '.missing' })).error).toBe('LOCAL_IDENTITY_INVALID');
      expect((await loadIdentity({ ...f.config, identityFile: 'relative.json' })).error).toBe('LOCAL_IDENTITY_INVALID');
      await writeFile(f.file, '{bad json');
      expect(await loadIdentity(f.config)).toEqual({ identity: null, error: 'LOCAL_IDENTITY_INVALID' });
    } finally { await f.cleanup(); }
  });
});
