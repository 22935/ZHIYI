import pg, { type PoolClient, type QueryResultRow } from 'pg';

// The existing schema uses timestamp without time zone. Keep its wall-clock wire
// value instead of silently applying the Node process timezone on history reads.
pg.types.setTypeParser(1114, value => value.replace(' ', 'T'));

export type Database = pg.Pool;
export type Connection = Pick<pg.Pool, 'query'> | Pick<PoolClient, 'query'>;
export function createDatabase(config: { databaseUrl?: string } = {}): Database {
  return new pg.Pool({
    connectionString: config.databaseUrl ?? process.env.ZHIYI_DATABASE_URL ?? process.env.DATABASE_URL,
    max: 8, connectionTimeoutMillis: 5000, idleTimeoutMillis: 30000,
    statement_timeout: 15000, application_name: 'zhiyi-backend-ts',
  });
}

export async function transaction<T>(db: Database, action: (client: PoolClient) => Promise<T>): Promise<T> {
  const client = await db.connect();
  try {
    await client.query('BEGIN');
    const value = await action(client);
    await client.query('COMMIT');
    return value;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally { client.release(); }
}

export class HttpError extends Error {
  constructor(public readonly statusCode: number, public readonly code: string, message: string = code) {
    super(message);
  }
}
export function notFound(): never { throw new HttpError(404, 'NOT_FOUND', '资源不存在或无权访问'); }
export function invalid(message: string): never { throw new HttpError(400, 'INVALID_REQUEST', message); }
export const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
export function uuidValue(value: unknown, nullable = false): string | null {
  if (nullable && (value === undefined || value === null || value === '')) return null;
  if (typeof value !== 'string' || !uuidPattern.test(value)) invalid('UUID 格式无效');
  return value;
}
export function objectValue(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) invalid('请求体必须是对象');
  return value as Record<string, unknown>;
}
export function textValue(value: unknown, max: number, required = false): string | null {
  if (value === undefined || value === null) {
    if (required) invalid('缺少必填文本');
    return null;
  }
  if (typeof value !== 'string' || value.length > max || (required && !value.trim())) invalid('文本格式或长度无效');
  return value;
}
export function workspaceMode(value: unknown): 'agent' | 'chat' {
  if (value === undefined || value === null || value === '') return 'chat';
  if (value !== 'agent' && value !== 'chat') invalid('工作区模式无效');
  return value;
}
export async function one<T extends QueryResultRow>(db: Connection, sql: string, params: unknown[] = []): Promise<T> {
  const result = await db.query<T>(sql, params);
  return result.rows[0] ?? notFound();
}

export interface ConversationRow extends QueryResultRow {
  id: string; user_id: string; role_id: string | null; context_id: string;
  title: string | null; workspace_mode: 'agent' | 'chat'; created_at: string; updated_at: string;
  preview?: string;
}
export interface MessageRow extends QueryResultRow {
  id: string; conversation_id: string; role: string; content: string; message_type: string;
  file_url: string | null; metadata: Record<string, unknown> | null; created_at: string;
}
export function conversationWire(row: ConversationRow) {
  const preview = row.preview === undefined ? null : row.preview;
  return { id: row.id, userId: row.user_id, roleId: row.role_id, contextId: row.context_id,
    title: row.title || (preview && preview.length > 30 ? preview.slice(0, 30) + '...' : preview),
    workspaceMode: row.workspace_mode, preview, createdAt: row.created_at, updatedAt: row.updated_at };
}
const metadataKeys = new Set(['confidence', 'tokens_used', 'totalTokens', 'effectiveModel', 'model_info',
  'requestedThinkingMode', 'effectiveThinkingMode', 'effectiveReasoningEffort', 'reasoningPhaseMs',
  'inputTokens', 'reasoningTokens', 'outputTokens', 'latencyMs', 'thinkingEnabled', 'reasoningContent',
  'reasoningTruncated', 'executionSummary']);
export function messageWire(row: MessageRow) {
  const metadata = row.metadata === null ? null : Object.fromEntries(Object.entries(row.metadata).filter(([key]) => metadataKeys.has(key)));
  return { id: row.id, conversationId: row.conversation_id, role: row.role, content: row.content,
    messageType: row.message_type, fileUrl: row.file_url, metadata, createdAt: row.created_at };
}

export async function ownedConversation(db: Connection, key: string, actorId: string, lock = false): Promise<ConversationRow> {
  return one<ConversationRow>(db, `SELECT * FROM conversations WHERE user_id=$1 AND (context_id=$2 OR id::text=$2)${lock ? ' FOR UPDATE' : ''}`, [actorId, key]);
}

export async function saveMessage(db: Connection, conversationId: string, actorId: string,
  role: 'USER' | 'ASSISTANT', content: string, metadata: Record<string, unknown> | null = null,
  fileUrl: string | null = null): Promise<MessageRow> {
  // The INSERT also carries owner filtering, so a late stream cannot recreate a
  // deleted conversation or insert a message into somebody else's history.
  const row = await one<MessageRow>(db, `INSERT INTO messages (conversation_id,role,content,message_type,file_url,metadata)
    SELECT id,$3,$4,$5,$6,$7::jsonb FROM conversations WHERE id=$1 AND user_id=$2 RETURNING *`,
  [conversationId, actorId, role, content, fileUrl ? 'IMAGE' : 'TEXT', fileUrl, metadata ? JSON.stringify(metadata) : null]);
  await db.query('UPDATE conversations SET updated_at=CURRENT_TIMESTAMP WHERE id=$1 AND user_id=$2', [conversationId, actorId]);
  return row;
}
