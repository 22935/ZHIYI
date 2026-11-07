import { randomUUID } from 'node:crypto';
import { mkdir, readFile, writeFile, unlink, readdir, lstat } from 'node:fs/promises';
import { resolve, sep, extname } from 'node:path';
import multipart from '@fastify/multipart';
import type { FastifyInstance, FastifyRequest } from 'fastify';
import { type Database, type ConversationRow, type MessageRow, conversationWire, messageWire,
  ownedConversation, transaction, one, notFound, invalid, uuidValue, textValue, objectValue, workspaceMode, HttpError } from './db.js';

export interface PlatformConfig { uploadDir?: string }
export function actor(request: FastifyRequest): string {
  return request.localIdentity?.actorId ?? (() => { throw new HttpError(503, 'LOCAL_IDENTITY_NOT_CONFIGURED'); })();
}
const conversationSelect = `SELECT c.*, CASE WHEN p.content IS NOT NULL THEN
  CASE WHEN length(p.content)>50 THEN left(p.content,50)||'...' ELSE p.content END
  WHEN EXISTS(SELECT 1 FROM messages m WHERE m.conversation_id=c.id) THEN '暂无预览' ELSE '暂无消息' END AS preview
  FROM conversations c LEFT JOIN LATERAL (SELECT content FROM messages WHERE conversation_id=c.id AND role='USER'
    ORDER BY created_at,id LIMIT 1) p ON true`;
function roleWire(row: Record<string, unknown>) {
  return { id: row.id, name: row.name, description: row.description, roleType: row.role_type,
    userId: row.user_id, stableKey: row.stable_key, systemPrompt: row.system_prompt,
    dialogueStyle: row.dialogue_style, personality: row.personality, avatarConfig: row.avatar_config,
    createdAt: row.created_at, updatedAt: row.updated_at };
}
function userWire(row: Record<string, unknown>) {
  return { id: row.id, username: row.username, email: row.email, avatar: row.avatar_url,
    createdAt: row.created_at, updatedAt: row.updated_at };
}
function jsonValue(value: unknown): string | null {
  if (value === undefined || value === null) return null;
  if (typeof value !== 'object' || Array.isArray(value)) invalid('角色配置必须是对象');
  return JSON.stringify(value);
}
function roleValues(body: unknown) {
  const data = objectValue(body);
  return [textValue(data.name, 100, true), textValue(data.description, 200000), textValue(data.systemPrompt, 200000, true),
    jsonValue(data.dialogueStyle), jsonValue(data.personality), jsonValue(data.avatarConfig)];
}

export async function registerPlatform(app: FastifyInstance, db: Database, config: PlatformConfig = {}) {
  await app.register(multipart, { limits: { fileSize: 10 * 1024 * 1024, files: 1, fields: 10 } });
  const uploadRoot = resolve(config.uploadDir ?? process.env.ZHIYI_UPLOAD_DIR ?? 'uploads');
  const localFile = (value: string) => {
    const full = resolve(uploadRoot, value.replace(/^[\\/]+/, ''));
    if (!full.startsWith(uploadRoot + sep)) invalid('文件路径无效');
    return full;
  };
  const fileType = (value: unknown) => {
    const type = value === undefined ? 'general' : String(value);
    if (!/^[a-zA-Z0-9_-]{1,80}$/.test(type) || type === 'avatars') invalid('文件类型无效');
    return type;
  };
  const fileTarget = (type: string, filename: string) => {
    if (!/^[a-zA-Z0-9_.-]{1,200}$/.test(filename) || filename.startsWith('.')) invalid('文件名无效');
    return localFile(`${fileType(type)}/${filename}`);
  };
  app.post('/api/files/upload', async request => {
    let type = (request.query as { type?: string }).type ?? 'general';
    let bytes: Buffer | undefined; let filename = ''; let mimetype = '';
    for await (const part of request.parts()) {
      if (part.type === 'file') {
        if (part.fieldname !== 'file') invalid('文件字段无效');
        bytes = await part.toBuffer(); filename = part.filename; mimetype = part.mimetype;
      } else if (part.fieldname === 'type') type = String(part.value);
    }
    if (!bytes?.length) invalid('缺少文件');
    type = fileType(type);
    const suffix = extname(filename).toLowerCase();
    const name = randomUUID() + (/^\.[a-z0-9]{1,16}$/.test(suffix) ? suffix : '');
    const path = fileTarget(type, name); await mkdir(resolve(path, '..'), { recursive: true });
    await writeFile(path, bytes, { flag: 'wx' });
    return { filePath: `${type}/${name}`, originalFilename: filename, size: bytes.length, contentType: mimetype };
  });
  app.get<{ Params: { type: string; filename: string } }>('/api/files/download/:type/:filename', async (request, reply) => {
    const target = fileTarget(request.params.type, request.params.filename);
    try {
      if (!(await lstat(target)).isFile()) notFound();
      const mime = ({ '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp',
        '.gif': 'image/gif', '.pdf': 'application/pdf', '.txt': 'text/plain; charset=utf-8', '.md': 'text/plain; charset=utf-8',
        '.mp3': 'audio/mpeg', '.wav': 'audio/wav', '.mp4': 'video/mp4' } as Record<string, string>)[extname(target).toLowerCase()];
      return reply.type(mime ?? 'application/octet-stream').header('X-Content-Type-Options', 'nosniff')
        .header('Content-Disposition', `attachment; filename="${request.params.filename}"`).send(await readFile(target));
    } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') notFound(); throw error; }
  });
  app.delete<{ Params: { type: string; filename: string } }>('/api/files/:type/:filename', async (request, reply) => {
    const target = fileTarget(request.params.type, request.params.filename);
    try { if (!(await lstat(target)).isFile()) notFound(); await unlink(target); }
    catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') notFound(); throw error; }
    return reply.code(204).send();
  });
  app.get('/api/files', async request => {
    const type = fileType((request.query as { type?: string }).type); const directory = localFile(type);
    const names = await readdir(directory).catch(error => { if (error.code === 'ENOENT') return []; throw error; });
    const files = await Promise.all(names.filter(name => !name.startsWith('.')).map(async name => {
      const info = await lstat(fileTarget(type, name));
      return info.isFile() ? { id: `${type}/${name}`, name, path: `${type}/${name}`, size: info.size,
        type, uploadTime: info.mtime.toISOString() } : null;
    }));
    return files.filter(file => file !== null).sort((a, b) => b.uploadTime.localeCompare(a.uploadTime));
  });

  app.get('/api/conversations', async request => {
    const query = request.query as { workspaceMode?: string };
    const mode = query.workspaceMode === undefined ? null : workspaceMode(query.workspaceMode);
    const result = await db.query<ConversationRow>(`${conversationSelect} WHERE c.user_id=$1 AND ($2::text IS NULL OR c.workspace_mode=$2) ORDER BY c.updated_at DESC,c.id`, [actor(request), mode]);
    return result.rows.map(conversationWire);
  });
  app.post('/api/conversations', async (request, reply) => {
    const body = objectValue(request.body ?? {}); const userId = actor(request); const roleId = uuidValue(body.roleId, true);
    if (roleId) await one(db, "SELECT id FROM roles WHERE id=$1 AND (user_id=$2 OR role_type='BUILTIN')", [roleId, userId]);
    const row = await one<ConversationRow>(db, `INSERT INTO conversations(user_id,role_id,context_id,title,workspace_mode)
      VALUES($1,$2,$3,$4,$5) RETURNING *`, [userId, roleId, 'ctx_' + randomUUID(), textValue(body.title, 200), workspaceMode(body.workspaceMode)]);
    return reply.code(201).send(conversationWire(row));
  });
  app.get<{ Params: { key: string } }>('/api/conversations/:key', async request => {
    const row = await one<ConversationRow>(db, `${conversationSelect} WHERE c.user_id=$1 AND (c.context_id=$2 OR c.id::text=$2)`, [actor(request), request.params.key]);
    return conversationWire(row);
  });
  app.get<{ Params: { id: string } }>('/api/conversations/:id/detail', async request => {
    const row = await one<ConversationRow>(db, `${conversationSelect} WHERE c.user_id=$1 AND c.id=$2`, [actor(request), uuidValue(request.params.id)]);
    return { conversation: conversationWire(row), preview: row.preview };
  });
  app.put<{ Params: { id: string } }>('/api/conversations/:id/title', async request => {
    const title = textValue(objectValue(request.body).title, 200, true);
    return conversationWire(await one<ConversationRow>(db, `UPDATE conversations SET title=$3,updated_at=CURRENT_TIMESTAMP
      WHERE id=$1 AND user_id=$2 RETURNING *`, [uuidValue(request.params.id), actor(request), title]));
  });
  app.delete('/api/conversations/all', async (request, reply) => {
    const query = request.query as { workspaceMode?: string }; const mode = query.workspaceMode === undefined ? null : workspaceMode(query.workspaceMode);
    await transaction(db, async client => {
      const rows = await client.query<{ id: string }>('SELECT id FROM conversations WHERE user_id=$1 AND ($2::text IS NULL OR workspace_mode=$2) FOR UPDATE', [actor(request), mode]);
      const ids = rows.rows.map(row => row.id);
      if (ids.length) {
        await client.query('DELETE FROM messages WHERE conversation_id=ANY($1::uuid[])', [ids]);
        await client.query('DELETE FROM conversations WHERE id=ANY($1::uuid[]) AND user_id=$2', [ids, actor(request)]);
      }
    });
    return reply.code(204).send();
  });
  app.delete<{ Params: { id: string } }>('/api/conversations/:id', async (request, reply) => {
    await transaction(db, async client => {
      const row = await ownedConversation(client, request.params.id, actor(request), true);
      await client.query('DELETE FROM messages WHERE conversation_id=$1', [row.id]);
      await client.query('DELETE FROM conversations WHERE id=$1 AND user_id=$2', [row.id, actor(request)]);
    });
    return reply.code(204).send();
  });

  app.get('/api/roles/custom', async request => (await db.query("SELECT * FROM roles WHERE user_id=$1 AND role_type='CUSTOM' ORDER BY created_at DESC,id", [actor(request)])).rows.map(roleWire));
  app.get('/api/roles/builtin', async request => (await db.query("SELECT * FROM roles WHERE role_type='BUILTIN' ORDER BY created_at,id", [])).rows.map(roleWire));
  app.get<{ Params: { id: string } }>('/api/roles/:id', async request => roleWire(await one(db,
    "SELECT * FROM roles WHERE id=$1 AND (user_id=$2 OR role_type='BUILTIN')", [uuidValue(request.params.id), actor(request)])));
  app.get<{ Params: { id: string } }>('/api/roles/:id/context', async request => {
    const row = await one(db, "SELECT * FROM roles WHERE id=$1 AND (user_id=$2 OR role_type='BUILTIN')", [uuidValue(request.params.id), actor(request)]);
    return { role_id: row.id, name: row.name, description: row.description, personality: row.personality,
      system_prompt: row.system_prompt, dialogue_style: row.dialogue_style };
  });
  app.post('/api/roles/custom', async (request, reply) => reply.code(201).send(roleWire(await one(db,
    `INSERT INTO roles(user_id,name,description,system_prompt,dialogue_style,personality,avatar_config,role_type)
      VALUES($1,$2,$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,'CUSTOM') RETURNING *`, [actor(request), ...roleValues(request.body)]))));
  app.put<{ Params: { id: string } }>('/api/roles/:id', async request => roleWire(await one(db,
    `UPDATE roles SET name=$3,description=$4,system_prompt=$5,dialogue_style=$6::jsonb,personality=$7::jsonb,
      avatar_config=$8::jsonb,updated_at=CURRENT_TIMESTAMP WHERE id=$1 AND user_id=$2 AND role_type='CUSTOM' RETURNING *`,
    [uuidValue(request.params.id), actor(request), ...roleValues(request.body)])));
  app.delete<{ Params: { id: string } }>('/api/roles/:id', async (request, reply) => {
    await one(db, "DELETE FROM roles WHERE id=$1 AND user_id=$2 AND role_type='CUSTOM' RETURNING id", [uuidValue(request.params.id), actor(request)]);
    return reply.code(204).send();
  });

  const currentUser = async (request: FastifyRequest) => userWire(await one(db, 'SELECT id,username,email,avatar_url,created_at,updated_at FROM users WHERE id=$1', [actor(request)]));
  app.get('/api/users/me', currentUser);
  app.get('/api/user/profile', currentUser);
  app.get<{ Params: { id: string } }>('/api/users/:id', async request => {
    if (request.params.id !== actor(request)) notFound();
    return currentUser(request);
  });
  const updateUser = async (request: FastifyRequest) => {
    const data = objectValue(request.body); const username = textValue(data.username, 50); const email = textValue(data.email, 100);
    if (username !== null && !username.trim()) invalid('名称不能为空');
    if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) invalid('邮箱格式无效');
    return userWire(await one(db, `UPDATE users SET username=COALESCE($2,username),
      email=CASE WHEN $4 THEN $3 ELSE email END,updated_at=CURRENT_TIMESTAMP WHERE id=$1 RETURNING *`,
    [actor(request), username, email || null, Object.hasOwn(data, 'email')]));
  };
  app.put('/api/user/profile', updateUser);
  app.put<{ Params: { id: string } }>('/api/users/:id', async request => {
    if (request.params.id !== actor(request)) notFound();
    return updateUser(request);
  });

  const avatars = new Map([['image/jpeg', '.jpg'], ['image/jpg', '.jpg'], ['image/png', '.png'], ['image/webp', '.webp'], ['image/gif', '.gif']]);
  app.post<{ Params: { id: string } }>('/api/users/:id/avatar', async request => {
    if (request.params.id !== actor(request)) notFound();
    const file = await request.file();
    if (!file || !avatars.has(file.mimetype)) invalid('请选择 JPEG、PNG、WebP 或 GIF 图片');
    const bytes = await file.toBuffer();
    if (!bytes.length || bytes.length > 5 * 1024 * 1024) throw new HttpError(413, 'AVATAR_TOO_LARGE');
    const mime = file.mimetype;
    const valid = mime.includes('jpeg') || mime === 'image/jpg' ? bytes[0] === 0xff && bytes[1] === 0xd8
      : mime === 'image/png' ? bytes.subarray(0, 8).equals(Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]))
      : mime === 'image/gif' ? /^GIF8[79]a$/.test(bytes.subarray(0, 6).toString('ascii'))
      : bytes.subarray(0, 4).toString() === 'RIFF' && bytes.subarray(8, 12).toString() === 'WEBP';
    if (!valid) invalid('图片内容与格式不匹配');
    const previous = await one(db, 'SELECT avatar_url FROM users WHERE id=$1', [actor(request)]);
    const relative = `avatars/${actor(request)}/${randomUUID()}${avatars.get(mime)}`;
    const target = localFile(relative); await mkdir(resolve(target, '..'), { recursive: true }); await writeFile(target, bytes, { flag: 'wx' });
    try {
      const row = await one(db, 'UPDATE users SET avatar_url=$2,updated_at=CURRENT_TIMESTAMP WHERE id=$1 RETURNING *', [actor(request), relative]);
      if (typeof previous.avatar_url === 'string' && previous.avatar_url.startsWith(`avatars/${actor(request)}/`)) {
        await unlink(localFile(previous.avatar_url)).catch(() => undefined);
      }
      return userWire(row);
    } catch (error) { await unlink(target).catch(() => undefined); throw error; }
  });
  app.get<{ Params: { id: string } }>('/api/users/:id/avatar', async (request, reply) => {
    if (request.params.id !== actor(request)) notFound();
    const row = await one(db, 'SELECT avatar_url FROM users WHERE id=$1', [actor(request)]);
    if (typeof row.avatar_url !== 'string' || !row.avatar_url.startsWith(`avatars/${actor(request)}/`)) notFound();
    try {
      const type = ({ '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp' } as Record<string, string>)[extname(row.avatar_url).toLowerCase()];
      return reply.type(type ?? 'application/octet-stream').header('X-Content-Type-Options', 'nosniff').send(await readFile(localFile(row.avatar_url)));
    } catch (error) { if ((error as NodeJS.ErrnoException).code === 'ENOENT') notFound(); throw error; }
  });

  for (const path of ['/api/search/messages', '/api/search/all-messages']) app.get(path, async request => {
    const query = request.query as { keyword?: string; contextId?: string }; const keyword = textValue(query.keyword, 500, true)!;
    const result = await db.query<MessageRow>(`SELECT m.* FROM messages m JOIN conversations c ON c.id=m.conversation_id
      WHERE c.user_id=$1 AND position(lower($2) in lower(m.content))>0 AND ($3::text IS NULL OR c.context_id=$3)
      ORDER BY m.created_at DESC,m.id DESC LIMIT 200`, [actor(request), keyword, query.contextId ?? null]);
    return result.rows.map(messageWire);
  });

  app.get<{ Params: { id: string } }>('/api/profile/:id', async request => {
    if (request.params.id !== actor(request)) notFound();
    const user = await currentUser(request);
    const usage = (await db.query<{ role_id: string | null; count: string; name: string | null }>(`SELECT c.role_id,count(*)::text AS count,max(r.name) AS name
      FROM conversations c LEFT JOIN roles r ON r.id=c.role_id AND (r.user_id=$1 OR r.role_type='BUILTIN')
      WHERE c.user_id=$1 GROUP BY c.role_id ORDER BY count(*) DESC,c.role_id`, [actor(request)])).rows;
    const count = usage.reduce((sum, item) => sum + Number(item.count), 0); const favorite = usage.find(item => item.role_id);
    return { userId: user.id, username: user.username, email: user.email, conversationCount: count,
      favoriteRoleId: favorite?.role_id ?? null, favoriteRoleName: favorite?.name ?? null,
      roleUsageCount: usage.filter(item => item.role_id).map(item => ({ roleId: item.role_id, count: Number(item.count) })),
      activityLevel: count > 100 ? 'very_active' : count > 50 ? 'active' : count > 10 ? 'moderate' : 'low' };
  });

  // This is the small rule-based recommendation feature already used by the UI.
  // Its suggestions are derived from current context; no model or new data store.
  app.post('/api/recommendations/contextual', async request => recommendations(objectValue(request.body ?? {})));
  app.post('/api/recommendations/questions', async request => {
    if (!Array.isArray(request.body) || request.body.some(value => typeof value !== 'string')) invalid('对话历史格式无效');
    return recommendations({ conversationHistory: request.body, roleName: (request.query as { roleName?: string }).roleName }).map(item => item.text);
  });
}

export function recommendations(data: Record<string, unknown>) {
  const history = Array.isArray(data.conversationHistory) ? data.conversationHistory.filter((item): item is string => typeof item === 'string').slice(0, 4) : [];
  const recent = [...history, data.currentInput, data.currentOutput].filter(item => typeof item === 'string' && item.trim()).join(' ');
  const scene = typeof data.scene === 'string' ? data.scene.toLowerCase() : '';
  const scope = ['chat', 'rag', 'workbench'].includes(String(data.scope)) ? String(data.scope) : 'chat';
  const texts: string[] = [];
  if (recent.includes('什么')) texts.push('能详细解释一下吗？');
  if (/如何|怎么/.test(recent)) texts.push('具体步骤是什么？');
  if (recent.includes('为什么')) texts.push('有什么原因吗？');
  if (scene === 'clause') {
    if (/合同|验收/.test(recent)) texts.push('补充阶段验收的判定标准', '增加源代码交付与部署文档清单');
    if (/知识产权|代码/.test(recent)) texts.push('明确知识产权归属与开源组件责任');
  }
  if (scene === 'risk') texts.push('检查需求变更计费机制是否完整', '补充逾期交付的宽限期与违约责任');
  if (scene === 'case') texts.push('补充与当前条款最接近的争议案例摘要', '对比近三年类似合同纠纷的裁判倾向');
  if (texts.length < 3) texts.push('能详细解释一下吗？', '有什么建议吗？', '还有其他相关问题吗？');
  return [...new Set(texts)].slice(0, 5).map(text => ({ text, scope, targetAction: scope === 'rag' ? 'fill_query' : 'fill_input',
    confidence: Math.min(0.96, 0.72 + (scene ? 0.08 : 0) + (recent.includes('合同') && text.includes('合同') ? 0.07 : 0) + (/验收|知识产权|学习/.test(text) ? 0.05 : 0)),
    reason: `基于${scope === 'rag' ? '知识检索' : scope === 'workbench' ? '工作台' : '对话'}场景${data.roleName ? `与${String(data.roleName)}角色` : ''}${scene ? `，聚焦${scene}标签` : ''}${recent ? '的当前上下文生成' : ''}` }));
}
