"""LocalIdentity compatibility without opening a database or a real Home."""
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'windows/native'))
import platform_database


ACTOR = '11111111-1111-4111-8111-111111111111'


@pytest.fixture
def existing_home(tmp_path, monkeypatch):
    (tmp_path / 'environment.json').write_text('{"format":"isolated-home"}', encoding='utf-8')
    identity = tmp_path / 'identity/local-identity.json'
    identity.parent.mkdir()
    digest = hashlib.sha256((tmp_path / 'environment.json').read_bytes()).hexdigest()
    queries = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def execute(self, sql):
            # Existing databases must never enter the schema/user creation path.
            assert sql.startswith('SELECT ')
            queries.append(sql)
            if 'FROM pg_tables' in sql:
                rows = [(name,) for name in
                        ['users', 'roles', 'conversations', 'messages', 'local_workspace_authorizations']]
            elif sql == 'SELECT id FROM users ORDER BY id LIMIT 2':
                rows = [(ACTOR,)]
            else:
                rows = []
            return rows

    monkeypatch.setitem(sys.modules, 'psycopg', SimpleNamespace(connect=lambda *_args, **_kwargs: Connection()))
    mapping = {'format': 'zhiyi-local-identity-v1', 'version': 1, 'actorId': ACTOR,
               'legacyUserId': ACTOR, 'wireTenantId': None, 'homeBinding': 'sha256:' + digest}
    return tmp_path, identity, digest, mapping, queries


@pytest.mark.parametrize('prefix', ['sha256:', ''])
def test_existing_binding_formats_are_validated_and_forwarded_without_rewriting(existing_home, prefix):
    home, identity, digest, mapping, queries = existing_home
    mapping['homeBinding'] = prefix + digest
    original = json.dumps(mapping).encode()
    identity.write_bytes(original)
    modified = identity.stat().st_mtime_ns

    first = platform_database.prepare(home, 'isolated-test-database', home / 'unused-migrations')
    second = platform_database.prepare(home, 'isolated-test-database', home / 'unused-migrations')

    assert first == second
    assert first['ZHIYI_BACKEND_TS_HOME_BINDING'] == mapping['homeBinding']
    assert first['ZHIYI_BACKEND_TS_EXPECTED_USER_ID'] == ACTOR
    assert identity.read_bytes() == original and identity.stat().st_mtime_ns == modified
    assert queries


@pytest.mark.parametrize('change', [
    {'homeBinding': 'sha256:' + '0' * 64},
    {'homeBinding': '0' * 64},
    {'homeBinding': 'sha512:' + '0' * 64},
    {'actorId': '22222222-2222-4222-8222-222222222222'},
    {'legacyUserId': '22222222-2222-4222-8222-222222222222'},
    {'wireTenantId': '__unscoped__'},
    {'version': 2},
])
def test_binding_compatibility_does_not_accept_changed_identity_or_home(existing_home, change):
    home, identity, _, mapping, _ = existing_home
    mapping.update(change)
    original = json.dumps(mapping).encode()
    identity.write_bytes(original)
    with pytest.raises(RuntimeError, match='LocalIdentity does not match'):
        platform_database.prepare(home, 'isolated-test-database', home / 'unused-migrations')
    assert identity.read_bytes() == original
