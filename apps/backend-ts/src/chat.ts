import { randomUUID } from 'node:crypto';
import { once } from 'node:events';
import type { FastifyInstance, FastifyReply, FastifyRequest } from 'fastify';
import { type Database, type MessageRow, type ConversationRow, type Connection, transaction, one,
  ownedConversation, saveMessage, messageWire, objectValue, textValue, uuidValue, workspaceMode, HttpError, invalid } from './db.js';
import { actor } from './platform.js';
import { GatewayError, type PythonGateway } from './gateway.js';

interface PreparedChat {
  conversationId: string; contextId: string; actorId: string; body: Record<string, unknown>;
}
export interface ChatConfig { streamIdleTimeoutMs?: number; streamMaxDurationMs?: number }

export async function prepareChat(db: Database, actorId: string, input: unknown): Promise<PreparedChat> {
  const data = objectValue(input);
  const text = textValue(data.text ?? data.message, 1000000, true)!;
  const contextId = textValue(data.context_id ?? data.contextId, 100);
  const mode = workspaceMode(data.workspace_mode ?? data.workspaceMode);
  const roleId = uuidValue(data.role_id ?? data.roleId, true);
  const fileUrl = textValue(data.file_url ?? data.fileUrl, 255);
  const body: Record<string, unknown> = { text };
  for (const [snake, camel] of [['model', 'model'], ['base_url', 'baseUrl'], ['api_key', 'apiKey'],
    ['thinking_mode', 'thinkingMode'], ['reasoning_effort', 'reasoningEffort'], ['tool_mode', 'toolMode'], ['approval_mode', 'approvalMode']]) {
    const value = data[snake] ?? data[camel];
    if (value !== undefined && value !== null) body[snake] = textValue(value, 20000);
  }
  if (roleId) body.role_id = roleId;
  if (data.context !== undefined && data.context !== null) {
    if (!Array.isArray(data.context) || data.context.length > 10000) invalid('对话上下文格式无效');
    body.context = data.context.map(value => {
      const item = objectValue(value);
      if (!['user', 'assistant', 'system'].includes(String(item.role))) invalid('上下文角色无效');
      return { role: item.role, content: textValue(item.content, 1000000) ?? '',
        ...(typeof item.file_url === 'string' ? { file_url: textValue(item.file_url, 255) } : {}) };
    });
  }
  return transaction(db, async client => {
    if (roleId) await one(client, "SELECT id FROM roles WHERE id=$1 AND (user_id=$2 OR role_type='BUILTIN')", [roleId, actorId]);
    // Existing context IDs are authority-bearing references, never hints to
    // silently fall back to a newly-created conversation owned by this caller.
    let conversation: ConversationRow;
    if (contextId) {
      conversation = await ownedConversation(client, contextId, actorId, true);
      if (conversation.workspace_mode !== mode) throw new HttpError(409, 'WORKSPACE_MODE_MISMATCH');
    } else {
      conversation = await one<ConversationRow>(client, `INSERT INTO conversations(user_id,role_id,context_id,title,workspace_mode)
        VALUES($1,$2,$3,$4,$5) RETURNING *`, [actorId, roleId, 'ctx_' + randomUUID(), text.length > 50 ? text.slice(0, 50) + '...' : text, mode]);
    }
    if (body.context === undefined) {
      const history = await client.query<MessageRow>('SELECT * FROM messages WHERE conversation_id=$1 ORDER BY created_at,id', [conversation.id]);
      body.context = history.rows.filter(item => item.content.trim() && !unfinished(item)).map(item => ({
        role: item.role.toLowerCase(), content: item.content, ...(item.file_url ? { file_url: item.file_url } : {}) }));
    }
    await saveMessage(client, conversation.id, actorId, 'USER', text, null, fileUrl);
    body.context_id = conversation.context_id;
    return { conversationId: conversation.id, contextId: conversation.context_id, actorId, body };
  });
}
function unfinished(message: MessageRow) {
  const summary = message.metadata?.executionSummary;
  return message.role === 'ASSISTANT' && Array.isArray(summary) && summary.some(item =>
    item && typeof item === 'object' && item.stage === 'chat_stream' && item.status !== 'completed');
}

export class StreamCapture {
  content = ''; reasoning = ''; completed = false; cancelled = false;
  failure: string | null = null; requestId = 'unknown'; sequence = 0;
  private buffer = ''; private readonly decoder = new TextDecoder();
  private reasoningStarted = false; private reasoningCompleted = false; private reasoningTruncated = false;
  private readonly usage: Record<string, unknown> = {};
  private readonly tools = new Map<string, Record<string, unknown>>();
  private readonly sources = new Map<string, Record<string, unknown>>();

  accept(chunk: Uint8Array) { this.acceptText(this.decoder.decode(chunk, { stream: true })); }
  finish() { this.acceptText(this.decoder.decode()); }
  private acceptText(text: string) {
    this.buffer += text;
    let separator: RegExpExecArray | null;
    while ((separator = /\r?\n\r?\n/.exec(this.buffer))) {
      const event = this.buffer.slice(0, separator.index);
      this.buffer = this.buffer.slice(separator.index + separator[0].length);
      this.acceptEvent(event);
    }
    if (this.buffer.length > 2 * 1024 * 1024) this.buffer = '';
  }
  private acceptEvent(frame: string) {
    const lines = frame.split(/\r?\n/); const data = lines.filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    if (!data) return;
    try {
      const envelope = JSON.parse(data) as Record<string, unknown>;
      const kind = String(envelope.event ?? lines.find(line => line.startsWith('event:'))?.slice(6).trim());
      const payload = envelope.data && typeof envelope.data === 'object' && !Array.isArray(envelope.data) ? envelope.data as Record<string, unknown> : {};
      if (typeof envelope.requestId === 'string') this.requestId = envelope.requestId;
      if (typeof envelope.sequence === 'number') this.sequence = Math.max(this.sequence, envelope.sequence);
      const copy = (...keys: string[]) => { for (const key of keys) if (payload[key] !== undefined && payload[key] !== null) this.usage[key] = payload[key]; };
      if (kind === 'reasoning_start') { this.reasoningStarted = true; copy('requestedThinkingMode', 'effectiveThinkingMode', 'effectiveReasoningEffort'); }
      if (kind === 'reasoning_delta' && typeof payload.delta === 'string') {
        this.reasoningStarted = true;
        const remaining = Math.max(0, 200000 - this.reasoning.length);
        this.reasoning += payload.delta.slice(0, remaining); this.reasoningTruncated ||= payload.delta.length > remaining;
      }
      if (kind === 'reasoning_end') { this.reasoningCompleted = true; copy('reasoningPhaseMs'); }
      if (kind === 'content_delta' && typeof payload.delta === 'string') this.content += payload.delta;
      if (kind === 'usage') copy('inputTokens', 'input_tokens', 'reasoningTokens', 'reasoning_tokens', 'outputTokens', 'output_tokens',
        'totalTokens', 'total_tokens', 'latencyMs', 'effectiveModel', 'requestedModel', 'requestedThinkingMode', 'effectiveThinkingMode', 'effectiveReasoningEffort', 'resolutionReasons', 'contextFixedTokens', 'contextTokenMethod');
      if (kind === 'tool_result' || kind === 'tool_error') { this.addTool(payload); this.addSources(payload.sources); }
      if (kind === 'done') {
        this.completed = !this.failure && payload.status === 'completed';
        if (!this.completed && !this.failure) { this.cancelled = payload.status === 'cancelled'; this.failure = this.cancelled ? '已停止生成' : '回复生成未完成，请重试'; }
        this.addSources(payload.sources);
        if (Array.isArray(payload.toolExecutions)) for (const value of payload.toolExecutions) {
          if (value && typeof value === 'object') this.addTool(value as Record<string, unknown>);
        }
        copy('toolsUsed');
      }
      if (kind === 'error') { this.completed = false; this.failure = typeof payload.message === 'string' ? payload.message : '回复生成失败，请重试'; }
    } catch { /* Invalid provider frames still reach the browser, but never enter history. */ }
  }
  private addTool(data: Record<string, unknown>) {
    const key = String(data.callId ?? data.toolName ?? this.tools.size);
    this.tools.set(key, Object.fromEntries(Object.entries(data).filter(([field]) => ['callId', 'toolName', 'status', 'durationMs',
      'inputSummary', 'outputSummary', 'sourceRefs', 'errorCode', 'terminal', 'activity'].includes(field))));
  }
  private addSources(data: unknown) {
    if (!Array.isArray(data)) return;
    for (const value of data) {
      if (!value || typeof value !== 'object') continue;
      const source = value as Record<string, unknown>; const key = String(source.citationId ?? source.url ?? source.title ?? '');
      if (key) this.sources.set(key, Object.fromEntries(Object.entries(source).filter(([field]) => ['citationId', 'title', 'filename', 'url', 'snippet', 'provider', 'retrievedAt'].includes(field))));
    }
  }
  cancel() { if (!this.completed && !this.failure) { this.cancelled = true; this.failure = '已停止生成'; } }
  metadata(model?: unknown): Record<string, unknown> {
    const data = { ...this.usage };
    for (const name of ['input', 'reasoning', 'output', 'total']) {
      if (data[`${name}_tokens`] !== undefined && data[`${name}Tokens`] === undefined) data[`${name}Tokens`] = data[`${name}_tokens`];
      delete data[`${name}_tokens`];
    }
    const status = this.completed ? 'completed' : this.cancelled ? 'cancelled' : 'failed';
    const summary: Record<string, unknown>[] = [{ stage: 'chat_stream', status,
      description: this.completed ? '回复已完成' : this.failure ?? '回复连接中断，请重试' }];
    for (const item of this.tools.values()) summary.push({ stage: `tool:${item.toolName ?? 'unknown'}:${item.callId ?? item.toolName}`,
      status: item.status ?? 'completed', description: `${item.toolName ?? '工具'} 调用${item.status === 'failed' ? '失败' : '完成'}`,
      ...(item.durationMs !== undefined ? { durationMs: item.durationMs } : {}),
      ...(item.terminal ? { terminal: item.terminal } : {}), ...(item.activity ? { activity: item.activity } : {}) });
    if (this.reasoningStarted) summary.push({ stage: 'reasoning', status: this.reasoningCompleted ? 'completed' : 'interrupted',
      description: this.reasoningCompleted ? '模型完成思考阶段' : '模型思考阶段未完整结束' });
    if (this.content) summary.push({ stage: 'answer_generation', status: this.completed ? 'completed' : 'interrupted',
      description: this.completed ? '模型完成最终回答生成' : '最终回答生成未完整结束' });
    return { ...data, thinkingEnabled: this.reasoningStarted, fallbackUsed: false, executionSummary: summary,
      ...(data.effectiveModel === undefined ? { model_info: typeof model === 'string' ? model : '' } : {}),
      ...(this.reasoning ? { reasoningContent: this.reasoning } : {}), ...(this.reasoningTruncated ? { reasoningTruncated: true } : {}),
      ...(this.tools.size ? { toolExecutions: [...this.tools.values()], toolsUsed: [...new Set([...this.tools.values()].map(item => item.toolName))] } : {}),
      ...(this.sources.size ? { sources: [...this.sources.values()] } : {}) };
  }
}

function abortForReply(reply: FastifyReply) {
  const controller = new AbortController();
  const onClose = () => { if (!reply.raw.writableEnded) controller.abort(new Error('CLIENT_DISCONNECTED')); };
  reply.raw.once('close', onClose);
  return { controller, dispose: () => reply.raw.off('close', onClose) };
}
async function forwardError(response: Response, reply: FastifyReply) {
  const type = response.headers.get('content-type');
  if (type) reply.header('content-type', type);
  return reply.code(response.status).send(Buffer.from(await response.arrayBuffer()));
}
async function persistCapture(db: Database, prepared: PreparedChat, capture: StreamCapture) {
  if (capture.completed && !capture.content) { capture.completed = false; capture.failure = 'AI 返回了空响应，请重试'; }
  await transaction(db, async client => {
    await ownedConversation(client, prepared.conversationId, prepared.actorId, true);
    await saveMessage(client, prepared.conversationId, prepared.actorId, 'ASSISTANT',
      capture.content || capture.failure || '回复连接中断，请重试', capture.metadata(prepared.body.model));
  });
}

export async function registerChat(app: FastifyInstance, db: Database, gateway: PythonGateway, config: ChatConfig = {}) {
  const sync = async (request: FastifyRequest, reply: FastifyReply) => {
    const prepared = await prepareChat(db, actor(request), request.body); const abort = abortForReply(reply);
    let persisted = false;
    const saveFailure = async (message: string) => {
      const capture = new StreamCapture(); capture.failure = message;
      if (abort.controller.signal.aborted) capture.cancelled = true;
      await persistCapture(db, prepared, capture);
      persisted = true;
    };
    try {
      const response = await gateway.request('/ai/chat/text', { identity: request.localIdentity!, method: 'POST', body: prepared.body, signal: abort.controller.signal });
      if (!response.ok) {
        await saveFailure(`模型服务请求失败（HTTP ${response.status}）`);
        return await forwardError(response, reply);
      }
      const data = objectValue(await response.json());
      if (typeof data.text !== 'string' || !data.text) throw new HttpError(502, 'AI_EMPTY_RESPONSE');
      const metadata = data.metadata && typeof data.metadata === 'object' ? data.metadata as Record<string, unknown> : {};
      const combined = { ...metadata, confidence: data.confidence, tokens_used: data.tokens_used ?? data.tokensUsed,
        model_info: data.model_info ?? data.modelInfo, sources: data.sources, reasoning_path: data.reasoning_path ?? data.reasoningPath };
      await transaction(db, async client => {
        await ownedConversation(client, prepared.conversationId, prepared.actorId, true);
        await saveMessage(client, prepared.conversationId, prepared.actorId, 'ASSISTANT', data.text as string, combined);
      });
      persisted = true;
      return { ...data, contextId: prepared.contextId, tokensUsed: data.tokens_used ?? data.tokensUsed,
        modelInfo: data.model_info ?? data.modelInfo, reasoningPath: data.reasoning_path ?? data.reasoningPath };
    } catch (error) {
      if (!persisted) await saveFailure(abort.controller.signal.aborted ? '已停止生成' : '模型请求失败，请重试').catch(() => {
        console.error('CHAT_PERSIST_FAILED');
      });
      if (error instanceof GatewayError) throw new HttpError(error.status, error.code);
      throw error;
    } finally { abort.dispose(); }
  };
  app.post('/api/chat/text', sync);
  app.post('/ai/chat/text', sync);
  app.post('/api/ai/chat/text', sync);

  const stream = async (request: FastifyRequest, reply: FastifyReply) => {
    const prepared = await prepareChat(db, actor(request), request.body); const abort = abortForReply(reply);
    const capture = new StreamCapture(); let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
    let idleTimer: ReturnType<typeof setTimeout> | undefined; let durationTimer: ReturnType<typeof setTimeout> | undefined;
    const timeout = (code: string, message: string) => { capture.failure = message; abort.controller.abort(new Error(code)); };
    const resetIdle = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(() => timeout('SSE_IDLE_TIMEOUT', '等待模型响应超时，请重试'), config.streamIdleTimeoutMs ?? 240000);
      idleTimer.unref();
    };
    try {
      resetIdle();
      if (config.streamMaxDurationMs && config.streamMaxDurationMs > 0) {
        durationTimer = setTimeout(() => timeout('SSE_MAX_DURATION', '本次回复已达到最长生成时间，请重试'), config.streamMaxDurationMs); durationTimer.unref();
      }
      const response = await gateway.request('/ai/chat/text/stream', { identity: request.localIdentity!, method: 'POST', body: prepared.body,
        headers: { Accept: 'text/event-stream' }, signal: abort.controller.signal });
      if (!response.ok) { capture.failure = `模型服务请求失败（HTTP ${response.status}）`; return await forwardError(response, reply); }
      if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) throw new HttpError(502, 'AI_INVALID_STREAM');
      reply.hijack();
      for (const [key, value] of Object.entries(reply.getHeaders())) if (value !== undefined) reply.raw.setHeader(key, value);
      reply.raw.writeHead(response.status, { 'Content-Type': 'text/event-stream; charset=utf-8',
        'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no', Connection: 'keep-alive', 'X-Context-Id': prepared.contextId });
      reader = response.body.getReader();
      while (!abort.controller.signal.aborted) {
        const next = await reader.read();
        if (next.done) break;
        resetIdle(); capture.accept(next.value);
        if (!reply.raw.write(next.value)) await once(reply.raw, 'drain', { signal: abort.controller.signal });
      }
      capture.finish();
      if (!capture.completed && !capture.failure) capture.failure = '回复连接中断，请重试';
      if (capture.failure && !reply.raw.destroyed && !abort.controller.signal.aborted) {
        reply.raw.write(`event: error\ndata: ${JSON.stringify({ event: 'error', requestId: capture.requestId, sequence: ++capture.sequence,
          data: { code: 'AI_STREAM_INTERRUPTED', message: capture.failure, retryable: true } })}\n\n`);
      }
    } catch (error) {
      if (abort.controller.signal.aborted && !capture.failure) capture.cancel();
      else capture.failure ??= error instanceof HttpError ? error.message : '模型连接中断，请重试';
      if (!reply.raw.headersSent && !reply.raw.destroyed) {
        const status = error instanceof HttpError ? error.statusCode : error instanceof GatewayError ? error.status : 502;
        reply.code(status).send({ error: error instanceof GatewayError ? error.code : 'AI_STREAM_FAILED', message: capture.failure });
      } else if (!reply.raw.destroyed) {
        reply.raw.write(`event: error\ndata: ${JSON.stringify({ event: 'error', requestId: capture.requestId, sequence: ++capture.sequence,
          data: { code: 'AI_STREAM_INTERRUPTED', message: capture.failure, retryable: true } })}\n\n`);
      }
    } finally {
      clearTimeout(idleTimer); clearTimeout(durationTimer); abort.dispose();
      await reader?.cancel().catch(() => undefined);
      // Flush history before terminating the stream so the UI's immediate refresh
      // observes the assistant result, including cancelled/failed partial replies.
      await persistCapture(db, prepared, capture).catch(error => {
        if (error instanceof HttpError && error.statusCode === 404) return;
        console.error('CHAT_PERSIST_FAILED');
        if (reply.raw.headersSent && !reply.raw.destroyed && !reply.raw.writableEnded) {
          reply.raw.write(`event: error\ndata: ${JSON.stringify({ event: 'error', requestId: capture.requestId, sequence: ++capture.sequence,
            data: { code: 'CHAT_PERSIST_FAILED', message: '回复保存失败，请检查本机数据库', retryable: false } })}\n\n`);
        }
      });
      if (reply.raw.headersSent && !reply.raw.writableEnded) reply.raw.end();
    }
  };
  app.post('/ai/chat/text/stream', stream);
  app.post('/api/ai/chat/text/stream', stream);
  app.get<{ Params: { context: string } }>('/api/chat/history/:context', async request => {
    const conversation = await ownedConversation(db, request.params.context, actor(request));
    return (await db.query<MessageRow>('SELECT * FROM messages WHERE conversation_id=$1 ORDER BY created_at,id', [conversation.id])).rows.map(messageWire);
  });
  app.delete<{ Params: { context: string } }>('/api/chat/history/:context', async (request, reply) => {
    await transaction(db, async client => {
      const conversation = await ownedConversation(client, request.params.context, actor(request), true);
      await client.query('DELETE FROM messages WHERE conversation_id=$1', [conversation.id]);
      await client.query('DELETE FROM conversations WHERE id=$1 AND user_id=$2', [conversation.id, actor(request)]);
    });
    return reply.code(204).send();
  });
}
