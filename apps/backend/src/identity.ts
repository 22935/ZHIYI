import { readFile } from 'node:fs/promises';
import { isAbsolute } from 'node:path';
import type { Config } from './config.js';

export interface LocalIdentity {
  readonly actorId: string;
  readonly tenantId: null;
}

export type IdentityState =
  | { readonly identity: Readonly<LocalIdentity>; readonly error: null }
  | { readonly identity: null; readonly error: 'LOCAL_IDENTITY_NOT_CONFIGURED' | 'LOCAL_IDENTITY_INVALID' };

const uuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const keys = ['format', 'version', 'actorId', 'legacyUserId', 'wireTenantId', 'homeBinding'];

// Pure validation: never infer an actor from a request, the first DB row, or a new UUID.
export function parseIdentity(value: unknown, expectedUserId?: string, homeBinding?: string): Readonly<LocalIdentity> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('Invalid local identity');
  const mapping = value as Record<string, unknown>;
  if (Object.keys(mapping).length !== keys.length || !keys.every(key => Object.hasOwn(mapping, key))
    || mapping.format !== 'zhiyi-local-identity-v1' || mapping.version !== 1
    || !expectedUserId || !uuid.test(expectedUserId)
    || mapping.actorId !== expectedUserId || mapping.legacyUserId !== expectedUserId
    || mapping.wireTenantId !== null || !homeBinding?.trim() || mapping.homeBinding !== homeBinding) {
    throw new Error('Invalid local identity');
  }
  return Object.freeze({ actorId: expectedUserId, tenantId: null });
}

export async function loadIdentity(config: Config): Promise<IdentityState> {
  if (!config.identityFile) return { identity: null, error: 'LOCAL_IDENTITY_NOT_CONFIGURED' };
  try {
    if (!isAbsolute(config.identityFile)) throw new Error('Absolute identity file required');
    const value: unknown = JSON.parse(await readFile(config.identityFile, 'utf8'));
    return { identity: parseIdentity(value, config.expectedUserId, config.homeBinding), error: null };
  } catch {
    // Do not expose a path, UUID, JSON content or OS error in health responses/logs.
    return { identity: null, error: 'LOCAL_IDENTITY_INVALID' };
  }
}
