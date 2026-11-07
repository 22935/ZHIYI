"""Prepare a new platform database, or validate an existing one without migrations.

Existing Home identity is checked against PostgreSQL independently of its JSON file.
Never creates a replacement identity for an existing database or rewrites a Grant.
"""
import hashlib
import json
import os
from pathlib import Path
import uuid


def prepare(home, database_url, migration_dir):
    import psycopg

    home = Path(home)
    identity_file = home / 'identity/local-identity.json'
    binding = hashlib.sha256((home / 'environment.json').read_bytes()).hexdigest()
    for path in [identity_file, *identity_file.parents]:
        if path.is_symlink() or path.is_junction():
            raise RuntimeError('Local identity may not traverse reparse points')
    with psycopg.connect(database_url, connect_timeout=5) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname='public'")}
        fresh = not tables
        if fresh:
            # Only an entirely empty public schema may execute historical SQL.
            # Existing user databases never enter this path.
            migrations = sorted(Path(migration_dir).glob('V*__*.sql'),
                                key=lambda path: int(path.name.split('__')[0][1:]))
            if len(migrations) != 13:
                raise RuntimeError('Platform historical schema bundle is incomplete')
            for migration in migrations:
                connection.execute(migration.read_text(encoding='utf-8'))
            connection.execute('CREATE TABLE platform_schema_version '
                               '(version integer PRIMARY KEY, installed_at timestamptz NOT NULL DEFAULT now())')
            connection.execute('INSERT INTO platform_schema_version(version) VALUES (13)')
        else:
            required = {'users', 'roles', 'conversations', 'messages', 'local_workspace_authorizations'}
            if not required.issubset(tables):
                raise RuntimeError('Existing platform schema is incomplete; no automatic repair was attempted')
            for table, columns in {
                'users': 'id,username,avatar_url',
                'conversations': 'id,user_id,role_id,title,workspace_mode',
                'messages': 'id,conversation_id,role,content,metadata,file_url',
                'roles': 'id,user_id,stable_key,dialogue_style,personality,avatar_config',
            }.items():
                connection.execute(f'SELECT {columns} FROM {table} LIMIT 0')
        users = [str(row[0]) for row in connection.execute('SELECT id FROM users ORDER BY id LIMIT 2')]
        if fresh:
            actor = str(uuid.uuid4())
            connection.execute('INSERT INTO users(id,username) VALUES (%s,%s)', (actor, 'local'))
        else:
            if len(users) != 1:
                raise RuntimeError('Expected the previously reconciled single local owner; refusing identity inference')
            if not identity_file.is_file():
                raise RuntimeError('Existing Home requires its verified LocalIdentity configuration')
            actor = users[0]
        expected = {'format': 'zhiyi-local-identity-v1', 'version': 1, 'actorId': actor,
                    'legacyUserId': actor, 'wireTenantId': None, 'homeBinding': binding}
        if identity_file.exists():
            if json.loads(identity_file.read_text(encoding='utf-8')) != expected:
                raise RuntimeError('LocalIdentity does not match the database owner or Home binding')
        elif fresh:
            identity_file.parent.mkdir(exist_ok=True)
            # Exclusive creation; never overwrite a user identity.
            with identity_file.open('x', encoding='utf-8') as handle:
                json.dump(expected, handle)
                handle.flush()
                os.fsync(handle.fileno())
    return {'ZHIYI_BACKEND_TS_IDENTITY_FILE': str(identity_file),
            'ZHIYI_BACKEND_TS_EXPECTED_USER_ID': actor,
            'ZHIYI_BACKEND_TS_HOME_BINDING': binding}
