import { execFile, spawn, type ChildProcess } from 'node:child_process';
import { promisify } from 'node:util';
import { existsSync } from 'node:fs';
import { mkdtemp, readdir, readFile, rm, mkdir, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve, dirname, basename } from 'node:path';
import { createServer } from 'node:net';
import { once } from 'node:events';
import Fastify, { type FastifyInstance } from 'fastify';
import { beforeAll, afterAll, describe, expect, it } from 'vitest';
import { createDatabase, saveMessage, transaction, type Database } from '../src/db.js';
import { registerPlatform } from '../src/platform.js';
import { prepareChat, registerChat, StreamCapture } from '../src/chat.js';
import { PythonGateway } from '../src/gateway.js';
import { fixture, legacyUserId, otherUserId } from './fixtures.js';
import { createApp } from '../src/app.js';

const run = promisify(execFile);
const binaryDir = process.env.ZHIYI_TEST_POSTGRES_BIN ?? join(process.env.LOCALAPPDATA ?? '', 'ZhiyiNative/dependencies/postgresql-15.19/pgsql/bin');
const postgres = join(binaryDir, process.platform === 'win32' ? 'postgres.exe' : 'postgres');

// Always create a brand-new cluster under tmpdir. This suite never reads a Home
// manifest, credential store, environment database URL or existing PostgreSQL data.
describe.skipIf(!existsSync(postgres))('isolated PostgreSQL business integration', () => {
  let directory: string; let processHandle: ChildProcess | undefined; let db: Database; let databaseUrl: string; let archive: string;
  let app: FastifyInstance; let owner = legacyUserId; let roleId: string; let contextId: string; let conversationId: string;
  beforeAll(async () => {
    directory = await mkdtemp(join(tmpdir(), 'zhiyi-platform-pg-test-'));
    const data = join(directory, 'pgdata');
    await run(join(binaryDir, process.platform === 'win32' ? 'initdb.exe' : 'initdb'),
      ['-D', data, '--encoding=UTF8', '--locale=C', '--auth=trust', '--username=postgres'], { windowsHide: true });
    const probe = createServer(); probe.listen(0, '127.0.0.1'); await once(probe, 'listening');
    const address = probe.address(); if (!address || typeof address === 'string') throw new Error('Missing test port');
    const port = address.port; await new Promise<void>(done => probe.close(() => done()));
    processHandle = spawn(postgres, ['-D', data, '-h', '127.0.0.1', '-p', String(port), '-c', 'fsync=off'],
      { windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'] });
    let diagnostics = ''; processHandle.stderr?.on('data', chunk => { diagnostics += String(chunk); });
    databaseUrl = `postgresql://postgres@127.0.0.1:${port}/postgres`;
    db = createDatabase({ databaseUrl });
    const deadline = Date.now() + 15000;
    while (true) {
      try { await db.query('SELECT 1'); break; }
      catch { if (Date.now() > deadline || processHandle.exitCode !== null) throw new Error('Isolated PostgreSQL start failed: ' + diagnostics); await new Promise(done => setTimeout(done, 100)); }
    }
    archive = resolve('migrations');
    const migrations = (await readdir(archive)).filter(name => /^V\d+__.*\.sql$/.test(name)).sort((a, b) => Number(a.match(/^V(\d+)/)![1]) - Number(b.match(/^V(\d+)/)![1]));
    for (const file of migrations) await db.query(await readFile(join(archive, file), 'utf8'));
    await db.query('INSERT INTO users(id,username) VALUES($1,$2),($3,$4)', [legacyUserId, 'isolated-local-user', otherUserId, 'isolated-other-user']);
    app = Fastify({ logger: false }); app.decorateRequest('localIdentity', null);
    app.addHook('onRequest', async request => { request.localIdentity = { actorId: owner, tenantId: null }; });
    await registerPlatform(app, db, { uploadDir: join(directory, 'uploads') });
    await registerChat(app, db, new PythonGateway({ internalServiceToken: 'isolated-test-internal-service-token-12345' }));
    await app.ready();
  }, 30000);
  afterAll(async () => {
    await app?.close(); await db?.end();
    if (processHandle && processHandle.exitCode === null) {
      await run(join(binaryDir, process.platform === 'win32' ? 'pg_ctl.exe' : 'pg_ctl'), ['-D', join(directory, 'pgdata'), 'stop', '-m', 'fast', '-w'], { windowsHide: true });
    }
    if (directory && dirname(resolve(directory)) === resolve(tmpdir()) && basename(directory).startsWith('zhiyi-platform-pg-test-')) {
      await rm(directory, { recursive: true, force: true });
    }
  }, 15000);

  it('initializes only a fresh platform schema and validates existing Home identity without rewriting it', async () => {
    await db.query('CREATE DATABASE platform_prepare_test');
    const home = join(directory, 'new-platform-home'); await mkdir(home);
    await writeFile(join(home, 'environment.json'), JSON.stringify({ format: 'isolated-test-home', version: 1 }));
    const helper = resolve('../../ops/scripts/infra/windows/native/platform_database.py');
    const script = `import importlib.util,json,sys,uuid\nfrom pathlib import Path\nimport psycopg\nspec=importlib.util.spec_from_file_location('platform_database',sys.argv[1])\nmodule=importlib.util.module_from_spec(spec)\nspec.loader.exec_module(module)\nhome,url,migrations=Path(sys.argv[2]),sys.argv[3],Path(sys.argv[4])\nfirst=module.prepare(home,url,migrations)\nidentity=Path(first['ZHIYI_BACKEND_TS_IDENTITY_FILE'])\noriginal=identity.read_bytes()\nmtime=identity.stat().st_mtime_ns\nwith psycopg.connect(url) as c:\n assert c.execute('SELECT count(*) FROM users').fetchone()[0]==1\n assert c.execute('SELECT version FROM platform_schema_version').fetchone()[0]==13\nsecond=module.prepare(home,url,migrations)\nassert second==first and identity.read_bytes()==original and identity.stat().st_mtime_ns==mtime\nwrong=json.loads(original)\nwrong['actorId']=str(uuid.uuid4())\nidentity.write_text(json.dumps(wrong),encoding='utf-8')\ntry:\n module.prepare(home,url,migrations)\nexcept RuntimeError:\n pass\nelse:\n raise AssertionError('Mismatched identity was accepted')\nidentity.write_bytes(original)\nwith psycopg.connect(url) as c:\n assert c.execute('SELECT count(*) FROM users').fetchone()[0]==1\n assert c.execute('SELECT count(*) FROM local_workspace_authorizations').fetchone()[0]==0\nprint('fresh schema, stable identity, existing validation, mismatch rejection: passed')\n`;
    const result = await run(process.env.ZHIYI_TEST_PYTHON ?? 'python', ['-c', script, helper, home,
      databaseUrl.replace(/\/postgres$/, '/platform_prepare_test'), archive], { windowsHide: true });
    expect(result.stdout).toContain('mismatch rejection: passed');
  }, 15000);

  it('reads and edits the configured local profile without credential fields', async () => {
    const initial = await app.inject('/api/users/me'); expect(initial.statusCode).toBe(200);
    expect(initial.json()).toMatchObject({ id: legacyUserId, username: 'isolated-local-user', avatar: null });
    expect(initial.json()).not.toHaveProperty('passwordHash');
    const updated = await app.inject({ method: 'PUT', url: '/api/user/profile', payload: { username: '本地用户', email: 'local@example.test' } });
    expect(updated.statusCode).toBe(200); expect(updated.json().username).toBe('本地用户');
    expect((await app.inject(`/api/users/${otherUserId}`)).statusCode).toBe(404);
  });
  it('starts the complete Fastify application against PostgreSQL with a ready local identity', async () => {
    const identity = await fixture(); const running = await createApp({ ...identity.config, databaseUrl,
      uploadDir: join(directory, 'entry-uploads') });
    try {
      const address = await running.listen({ host: '127.0.0.1', port: 0 });
      expect((await fetch(address + '/health/ready')).status).toBe(200);
      const response = await fetch(address + '/api/users/me', { headers: { Origin: 'kinlin-app://shell' } });
      expect(response.status).toBe(200); expect(await response.json()).toMatchObject({ id: legacyUserId });
      const options = await fetch(address + '/api/conversations', { method: 'OPTIONS', headers: {
        Origin: 'kinlin-app://shell', 'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type,x-zhiyi-local-request' } });
      expect(options.status).toBe(204);
      expect(options.headers.get('access-control-allow-headers')).toContain('X-Zhiyi-Local-Request');
    } finally { await running.close(); await identity.cleanup(); }
  });
  it('uploads, lists, downloads and deletes actual local files and saves a profile avatar', async () => {
    const boundary = 'isolated-file-upload-boundary';
    const upload = await app.inject({ method: 'POST', url: '/api/files/upload', headers: {
      'content-type': `multipart/form-data; boundary=${boundary}` }, payload: Buffer.from(
      `--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="notes.txt"\r\nContent-Type: text/plain\r\n\r\n真实文件内容\r\n--${boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ngeneral\r\n--${boundary}--\r\n`) });
    expect(upload.statusCode).toBe(200); const path = upload.json().filePath;
    const files = await app.inject('/api/files'); expect(files.json().map((file: any) => file.path)).toContain(path);
    const download = await app.inject('/api/files/download/' + path); expect(download.statusCode).toBe(200);
    expect(download.body).toBe('真实文件内容');
    expect((await app.inject({ method: 'DELETE', url: '/api/files/' + path })).statusCode).toBe(204);
    expect((await app.inject('/api/files/download/' + path)).statusCode).toBe(404);
    const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Zqv8AAAAASUVORK5CYII=', 'base64');
    const avatar = await app.inject({ method: 'POST', url: `/api/users/${legacyUserId}/avatar`, headers: {
      'content-type': `multipart/form-data; boundary=${boundary}` }, payload: Buffer.concat([
      Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="avatar.png"\r\nContent-Type: image/png\r\n\r\n`),
      png, Buffer.from(`\r\n--${boundary}--\r\n`)]) });
    expect(avatar.statusCode).toBe(200); expect(avatar.json().avatar).toContain(`avatars/${legacyUserId}/`);
    const read = await app.inject(`/api/users/${legacyUserId}/avatar`); expect(read.statusCode).toBe(200);
    expect(read.rawPayload).toEqual(png);
  });
  it('creates roles and conversations with existing JSONB/timestamp columns', async () => {
    const role = await app.inject({ method: 'POST', url: '/api/roles/custom', payload: {
      name: '测试角色', systemPrompt: '请准确回答', personality: { precise: true }, dialogueStyle: { concise: 1 } } });
    expect(role.statusCode).toBe(201); roleId = role.json().id;
    expect(role.json()).toMatchObject({ personality: { precise: true }, roleType: 'CUSTOM', userId: legacyUserId });
    expect(role.json().createdAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    const conversation = await app.inject({ method: 'POST', url: '/api/conversations', payload: { roleId, workspaceMode: 'chat' } });
    expect(conversation.statusCode).toBe(201); contextId = conversation.json().contextId; conversationId = conversation.json().id;
    const renamed = await app.inject({ method: 'PUT', url: `/api/conversations/${conversationId}/title`, payload: { title: '已重命名' } });
    expect(renamed.json().title).toBe('已重命名');
    expect((await app.inject(`/api/conversations/${contextId}`)).json().id).toBe(conversationId);
  });
  it('prepares a chat turn once, preserves repeated text and reloads reasoning/usage', async () => {
    const first = await prepareChat(db, legacyUserId, { text: '同一条消息', role_id: roleId, context_id: contextId, workspace_mode: 'chat' });
    expect(first.body.context).toEqual([]);
    await transaction(db, client => saveMessage(client, first.conversationId, legacyUserId, 'ASSISTANT', '第一次回复', { totalTokens: 5 }));
    const second = await prepareChat(db, legacyUserId, { text: '同一条消息', contextId, workspaceMode: 'chat' });
    expect(second.body.context).toEqual([{ role: 'user', content: '同一条消息' }, { role: 'assistant', content: '第一次回复' }]);
    const capture = new StreamCapture(); const encoder = new TextEncoder();
    for (const event of [
      { event: 'reasoning_delta', data: { delta: '思考过程' } },
      { event: 'content_delta', data: { delta: '第二次回复' } },
      { event: 'usage', data: { input_tokens: 3, output_tokens: 4, total_tokens: 7, effectiveModel: 'test-model' } },
      { event: 'done', data: { status: 'completed', contextId } },
    ]) capture.accept(encoder.encode(`event: ${event.event}\ndata: ${JSON.stringify(event)}\n\n`));
    await transaction(db, client => saveMessage(client, second.conversationId, legacyUserId, 'ASSISTANT', capture.content, capture.metadata()));
    const history = await app.inject(`/api/chat/history/${contextId}`);
    expect(history.statusCode).toBe(200); expect(history.json()).toHaveLength(4);
    expect(history.json()[3]).toMatchObject({ content: '第二次回复', metadata: { totalTokens: 7, reasoningContent: '思考过程', effectiveModel: 'test-model' } });
    const results = await app.inject('/api/search/messages?keyword=' + encodeURIComponent('同一条'));
    expect(results.json()).toHaveLength(2);
  });
  it('enforces owner filtering for history, role modification, search and deletion', async () => {
    owner = otherUserId;
    try {
      expect((await app.inject('/api/conversations')).json()).toEqual([]);
      expect((await app.inject(`/api/chat/history/${contextId}`)).statusCode).toBe(404);
      expect((await app.inject(`/api/roles/${roleId}`)).statusCode).toBe(404);
      expect((await app.inject({ method: 'DELETE', url: `/api/roles/${roleId}` })).statusCode).toBe(404);
      expect((await app.inject({ method: 'DELETE', url: `/api/conversations/${conversationId}` })).statusCode).toBe(404);
      await expect(prepareChat(db, otherUserId, { text: 'forbidden', contextId })).rejects.toMatchObject({ statusCode: 404 });
      expect((await app.inject('/api/search/all-messages?keyword=' + encodeURIComponent('回复'))).json()).toEqual([]);
    } finally { owner = legacyUserId; }
    expect((await db.query('SELECT count(*) FROM messages WHERE conversation_id=$1', [conversationId])).rows[0].count).toBe('4');
  });
  it('keeps workspace modes separate and atomically deletes owned conversation history', async () => {
    await expect(prepareChat(db, legacyUserId, { text: 'wrong mode', contextId, workspaceMode: 'agent' })).rejects.toMatchObject({ statusCode: 409 });
    expect((await app.inject('/api/conversations?workspaceMode=agent')).json()).toEqual([]);
    expect((await app.inject(`/api/conversations/${conversationId}/detail`)).json()).toMatchObject({ preview: '同一条消息', conversation: { title: '已重命名' } });
    expect((await app.inject({ method: 'DELETE', url: `/api/conversations/${conversationId}` })).statusCode).toBe(204);
    expect((await db.query('SELECT count(*) FROM messages WHERE conversation_id=$1', [conversationId])).rows[0].count).toBe('0');
    expect((await app.inject(`/api/chat/history/${contextId}`)).statusCode).toBe(404);
  });
});
