import { describe, expect, it } from 'vitest';
import { parseEventBlock, parseSseStream } from '@/lib/sse';
import type { SseEvent } from '@/lib/types';

function streamFrom(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<SseEvent[]> {
  const events: SseEvent[] = [];
  for await (const event of parseSseStream(stream)) events.push(event);
  return events;
}

describe('parseEventBlock', () => {
  it('parses a well-formed data line', () => {
    const event = parseEventBlock('data: {"type":"done","payload":{}}');
    expect(event).toEqual({ type: 'done', payload: {} });
  });

  it('returns null for a comment-only block', () => {
    expect(parseEventBlock(': keep-alive')).toBeNull();
  });

  it('returns null for malformed JSON', () => {
    expect(parseEventBlock('data: {not json}')).toBeNull();
  });

  it('returns null for an unknown event type', () => {
    expect(parseEventBlock('data: {"type":"mystery","payload":{}}')).toBeNull();
  });
});

describe('parseSseStream', () => {
  it('yields multiple events delivered in a single chunk', async () => {
    const body =
      'data: {"type":"step","payload":{"kind":"llm_call","step_id":"a","ts":"t","model":"m","input_tokens":null,"output_tokens":null,"cost_usd":null,"latency_ms":null}}\n\n' +
      'data: {"type":"done","payload":{}}\n\n';
    const events = await collect(streamFrom([body]));
    expect(events.map((e) => e.type)).toEqual(['step', 'done']);
  });

  it('reassembles an event split across chunk boundaries', async () => {
    const events = await collect(
      streamFrom(['data: {"type":"do', 'ne","payload":{}}\n\n']),
    );
    expect(events).toEqual([{ type: 'done', payload: {} }]);
  });

  it('flushes a trailing event with no final blank line', async () => {
    const events = await collect(streamFrom(['data: {"type":"done","payload":{}}']));
    expect(events).toEqual([{ type: 'done', payload: {} }]);
  });

  it('skips malformed blocks but keeps parsing the rest', async () => {
    const body = 'data: {bad}\n\ndata: {"type":"done","payload":{}}\n\n';
    const events = await collect(streamFrom([body]));
    expect(events).toEqual([{ type: 'done', payload: {} }]);
  });
});
