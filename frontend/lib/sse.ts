/**
 * Server-Sent Events parser for the agent `/query` stream.
 *
 * The backend emits one event per `data: {json}\n\n` block (see
 * `backend/aviation_copilot/api/routes.py::_sse`). This module turns a raw
 * byte stream into an async iterable of typed {@link SseEvent} objects,
 * tolerating chunk boundaries that fall mid-event.
 */

import type { SseEvent } from './types';

const VALID_TYPES = new Set(['step', 'delta', 'final', 'error', 'done']);

/**
 * Parse one SSE event block (the text between two blank-line delimiters).
 * Returns `null` for comment-only or malformed blocks so callers can skip them.
 */
export function parseEventBlock(block: string): SseEvent | null {
  const dataLines = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trimStart());

  if (dataLines.length === 0) return null;

  try {
    const parsed: unknown = JSON.parse(dataLines.join('\n'));
    if (
      typeof parsed === 'object' &&
      parsed !== null &&
      'type' in parsed &&
      typeof (parsed as { type: unknown }).type === 'string' &&
      VALID_TYPES.has((parsed as { type: string }).type)
    ) {
      return parsed as SseEvent;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * Consume a byte stream and yield decoded SSE events.
 *
 * Buffers across chunk boundaries: a `data:` line split between two network
 * chunks is reassembled before parsing.
 */
export async function* parseSseStream(
  stream: ReadableStream<Uint8Array>,
): AsyncGenerator<SseEvent> {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let delimiter = buffer.indexOf('\n\n');
      while (delimiter !== -1) {
        const block = buffer.slice(0, delimiter);
        buffer = buffer.slice(delimiter + 2);
        const event = parseEventBlock(block);
        if (event) yield event;
        delimiter = buffer.indexOf('\n\n');
      }
    }
    // Flush any trailing event that arrived without a final blank line.
    buffer += decoder.decode();
    const tail = parseEventBlock(buffer);
    if (tail) yield tail;
  } finally {
    reader.releaseLock();
  }
}
