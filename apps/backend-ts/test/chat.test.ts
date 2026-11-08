import { describe, expect, it } from 'vitest';
import { StreamCapture } from '../src/chat.js';
import { recommendations } from '../src/platform.js';

describe('stream history capture', () => {
  it('handles UTF-8 and SSE frame boundaries without losing reasoning or output', () => {
    const stream = [
      { event: 'reasoning_start', data: { requestedThinkingMode: 'deep' } },
      { event: 'reasoning_delta', data: { delta: '推理😀' } },
      { event: 'reasoning_end', data: { reasoningPhaseMs: 17 } },
      { event: 'content_delta', data: { delta: '答案中文' } },
      { event: 'usage', data: { input_tokens: 11, reasoning_tokens: 3, output_tokens: 5, total_tokens: 19,
        contextFixedTokens: 100, contextTokenMethod: 'utf8-upper-bound' } },
      { event: 'done', data: { status: 'completed' } },
    ].map((value, index) => `event: ${value.event}\r\ndata: ${JSON.stringify({ requestId: 'request-a', sequence: index + 1, ...value })}\r\n\r\n`).join('');
    const bytes = new TextEncoder().encode(stream); const capture = new StreamCapture();
    for (let offset = 0; offset < bytes.length; offset += 7) capture.accept(bytes.slice(offset, offset + 7));
    capture.finish();
    expect(capture.content).toBe('答案中文'); expect(capture.completed).toBe(true);
    expect(capture.metadata()).toMatchObject({ reasoningContent: '推理😀', reasoningPhaseMs: 17, totalTokens: 19, reasoningTokens: 3,
      contextFixedTokens: 100, contextTokenMethod: 'utf8-upper-bound',
      executionSummary: [{ stage: 'chat_stream', status: 'completed' }, { stage: 'reasoning', status: 'completed' }, { stage: 'answer_generation', status: 'completed' }] });
  });
  it('persists partial cancelled output and bounded reasoning', () => {
    const capture = new StreamCapture();
    capture.accept(new TextEncoder().encode(`data: ${JSON.stringify({ event: 'reasoning_delta', data: { delta: 'x'.repeat(200010) } })}\n\n`));
    capture.accept(new TextEncoder().encode('data: {"event":"content_delta","data":{"delta":"partial"}}\n\n'));
    capture.cancel();
    const metadata = capture.metadata();
    expect(capture.content).toBe('partial'); expect(capture.cancelled).toBe(true);
    expect(String(metadata.reasoningContent)).toHaveLength(200000); expect(metadata.reasoningTruncated).toBe(true);
    expect((metadata.executionSummary as any[])[0]).toMatchObject({ stage: 'chat_stream', status: 'cancelled' });
  });
  it('keeps terminal and file activity for a history reload and ignores malformed frames', () => {
    const capture = new StreamCapture();
    capture.accept(new TextEncoder().encode('data: invalid\n\n'));
    const tool = { callId: 'call-1', toolName: 'run_command', status: 'completed', terminal: { command: 'node --version', stdout: 'v24' }, activity: { kind: 'command', summary: 'check node' } };
    capture.accept(new TextEncoder().encode(`data: ${JSON.stringify({ event: 'tool_result', data: tool })}\n\n`));
    capture.accept(new TextEncoder().encode(`data: ${JSON.stringify({ event: 'done', data: { status: 'completed', toolExecutions: [tool] } })}\n\n`));
    const summary = capture.metadata().executionSummary as any[];
    expect(summary.filter(item => item.stage.startsWith('tool:'))).toHaveLength(1);
    expect(summary[1].terminal).toMatchObject({ command: 'node --version', stdout: 'v24' });
  });
});
it('uses scene and question context for the existing lightweight recommendation rules', () => {
  const items = recommendations({ currentInput: '如何处理合同验收？', scene: 'clause', scope: 'rag' });
  expect(items.map(item => item.text)).toContain('具体步骤是什么？');
  expect(items.map(item => item.text)).toContain('补充阶段验收的判定标准');
  expect(items.every(item => item.targetAction === 'fill_query')).toBe(true);
});
