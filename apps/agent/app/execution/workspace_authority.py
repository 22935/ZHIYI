"""Trusted local workspace issuer. PostgreSQL is authority; Hands JSON is a projection.

No model input is consumed here. Any accessible directory can be selected;
aliases resolve to their real location. Revoked grants are never reused.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import threading
from uuid import uuid4

from contracts.local_runtime import LocalRuntimeAuthorizationRef


def canonical_directory(value):
    raw = str(value)
    if not raw or '\x00' in raw or not Path(raw).is_absolute():
        raise PermissionError('Absolute local directory required')
    try:
        resolved = Path(raw).resolve(strict=True)
    except RuntimeError as exc:
        raise PermissionError('Directory link cannot be resolved') from exc
    info = resolved.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise PermissionError('An existing directory is required')
    return os.path.normcase(str(resolved)), f'{info.st_dev}:{info.st_ino}'


class WorkspaceAuthority:
    def __init__(self, environment, resource_id):
        self.environment = dict(environment)
        self.resource_id = resource_id
        self.grants_file = Path(environment['AGENTOS_WORKSPACE_GRANTS_FILE'])
        self.caller = environment['AGENTOS_LOCAL_RUNTIME_CREDENTIAL_ID']
        self._lock = threading.RLock()

    def connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.environment['AGENTOS_WORKSPACE_DATABASE_URL'],
                              row_factory=dict_row, connect_timeout=5)

    @staticmethod
    def owner(actor):
        if actor is None:
            raise PermissionError('Authenticated user required')
        return str(actor.user_id), actor.tenant_id or '__unscoped__'

    def _project(self, conn):
        rows = conn.execute('SELECT * FROM local_workspace_authorizations').fetchall()
        existing = json.loads(self.grants_file.read_text(encoding='utf-8')) if self.grants_file.exists() else {'grants': []}
        # Retain only operator-owned startup grants; dynamic records come from PG.
        grants = [g for g in existing['grants'] if not g['grantId'].startswith('wgrant_')]
        grants += [dict(grantId=r['grant_id'], workspaceId=r['workspace_id'], canonicalRoot=r['canonical_root'],
                        capabilities=['fs.list', 'fs.read', 'fs.write', 'fs.patch', 'shell.exec'],
                        allowedCallers=[self.caller], revoked=r['revoked']) for r in rows]
        temporary = self.grants_file.with_suffix('.next.json')
        temporary.write_text(json.dumps({'grants': grants}), encoding='utf-8')
        temporary.replace(self.grants_file)

    def select(self, actor, path):
        root, identity = canonical_directory(path)
        owner, tenant = self.owner(actor)
        workspace = 'ws_' + hashlib.sha256(f'{owner}\0{tenant}\0{root}\0{identity}'.encode()).hexdigest()[:48]
        with self._lock, self.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(71320512)')
            conn.execute('UPDATE local_workspace_authorizations SET selected=FALSE WHERE user_id=%s AND tenant_id=%s', (owner, tenant))
            row = conn.execute('SELECT * FROM local_workspace_authorizations WHERE workspace_id=%s', (workspace,)).fetchone()
            if row and row['revoked']:
                # Stable workspace identity, a new grant epoch invalidates every old Run.
                conn.execute('UPDATE local_workspace_authorizations SET grant_id=%s, revoked=FALSE, revoked_at=NULL, selected=TRUE WHERE workspace_id=%s', ('wgrant_'+uuid4().hex, workspace))
            elif row:
                conn.execute('UPDATE local_workspace_authorizations SET selected=TRUE WHERE workspace_id=%s', (workspace,))
            else:
                conn.execute('INSERT INTO local_workspace_authorizations(workspace_id,user_id,tenant_id,canonical_root,root_identity,resource_id,grant_id,selected) VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE)',
                             (workspace, owner, tenant, root, identity, self.resource_id, 'wgrant_'+uuid4().hex))
            self._project(conn)
            conn.commit()
        return self.current(actor)

    def current(self, actor):
        owner, tenant = self.owner(actor)
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM local_workspace_authorizations WHERE user_id=%s AND tenant_id=%s AND selected AND NOT revoked', (owner, tenant)).fetchone()
        return self.view(row) if row else None

    def list(self, actor):
        owner, tenant = self.owner(actor)
        with self.connect() as conn:
            return [self.view(r) for r in conn.execute('SELECT * FROM local_workspace_authorizations WHERE user_id=%s AND tenant_id=%s ORDER BY created_at', (owner, tenant)).fetchall()]

    def revoke(self, actor, workspace):
        owner, tenant = self.owner(actor)
        with self._lock, self.connect() as conn:
            conn.execute('SELECT pg_advisory_xact_lock(71320512)')
            row = conn.execute('UPDATE local_workspace_authorizations SET revoked=TRUE, selected=FALSE, revoked_at=CURRENT_TIMESTAMP WHERE workspace_id=%s AND user_id=%s AND tenant_id=%s RETURNING *', (workspace, owner, tenant)).fetchone()
            if row is None:
                raise PermissionError('Workspace not owned by current user')
            # Publish denial before committing. A crash can only deny too much.
            self._project(conn)
            conn.commit()
        return self.view(row)

    @staticmethod
    def view(row):
        return dict(workspaceId=row['workspace_id'], workspaceRoot=row['canonical_root'], grantId=row['grant_id'],
                    resourceId=row['resource_id'], rootIdentity=row['root_identity'], revoked=row['revoked'],
                    selected=row['selected'], scope='user-workspace', confinement='none',
                    risk='Host-approved project commands run with the host user permissions; this is not an OS sandbox.')

    def freeze(self, run_input):
        from app.security.internal_auth import current_trusted_user
        # An input parameter cannot assert an authority snapshot.
        run_input.pop('workspaceBinding', None)
        selected = self.current(current_trusted_user())
        if selected:
            run_input['workspaceBinding'] = selected

    def resolve(self, run):
        binding = run.input.get('workspaceBinding')
        return self._resolve(binding, str(run.input.get('authenticatedUserId')),
                             run.input.get('authenticatedTenantId') or '__unscoped__')

    def resolve_current(self, actor):
        owner, tenant = self.owner(actor)
        selected = self.current(actor)
        return self._resolve(selected, owner, tenant) if selected else None

    def _resolve(self, binding, owner, tenant):
        if not isinstance(binding, dict):
            raise PermissionError('Run has no frozen authorized workspace; select a directory before creating the Run')
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM local_workspace_authorizations WHERE workspace_id=%s', (binding['workspaceId'],)).fetchone()
        if (not row or row['revoked'] or row['grant_id'] != binding['grantId'] or
                row['user_id'] != owner or row['tenant_id'] != tenant or
                row['resource_id'] != self.resource_id or row['canonical_root'] != binding['workspaceRoot']):
            raise PermissionError('Workspace grant is revoked or does not match the frozen Run')
        root, identity = canonical_directory(row['canonical_root'])
        if identity != row['root_identity'] or root != row['canonical_root']:
            raise PermissionError('Workspace directory identity changed')
        return LocalRuntimeAuthorizationRef(grantId=row['grant_id'], workspaceId=row['workspace_id'])
