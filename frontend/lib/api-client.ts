/**
 * Client for the agent `/query` SSE endpoint.
 *
 * Calls the same-origin `/api/proxy` route (which forwards to the Modal
 * backend — see `app/api/proxy/route.ts`) so the real backend URL never
 * reaches the browser. Translates HTTP and transport failures into the
 * typed {@link QueryError} model the chat surface renders.
 */

import { parseSseStream } from './sse';
import type { QueryError, QueryResponse, TraceStep } from './types';

export const PROXY_ENDPOINT = '/api/proxy';

export interface StreamCallbacks {
  /** One trace step streamed as the agent runs. */
  onStep?: (step: TraceStep) => void;
  /** A partial answer token (emitted only if the backend streams deltas). */
  onDelta?: (text: string) => void;
  /** The final answer + complete trace. */
  onFinal?: (response: QueryResponse) => void;
  /** A terminal failure. After `onError`, no further callbacks fire. */
  onError?: (error: QueryError) => void;
  /** The stream closed cleanly. */
  onDone?: () => void;
}

export interface StreamOptions {
  signal?: AbortSignal;
  endpoint?: string;
}

/**
 * Stream an agent answer for `question`, dispatching events to `callbacks`.
 *
 * Resolves when the stream ends (cleanly or with an error already reported via
 * `onError`). Never rejects — every failure mode is surfaced through `onError`
 * so callers have a single place to handle them.
 */
export async function streamQuery(
  question: string,
  callbacks: StreamCallbacks,
  options: StreamOptions = {},
): Promise<void> {
  const endpoint = options.endpoint ?? PROXY_ENDPOINT;
  let response: Response;

  try {
    response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ question }),
      signal: options.signal,
    });
  } catch (err) {
    if (isAbort(err)) return;
    callbacks.onError?.({
      kind: 'network',
      message: 'Could not reach the agent service. Check your connection and try again.',
    });
    return;
  }

  if (!response.ok) {
    callbacks.onError?.(await toHttpError(response));
    return;
  }

  if (!response.body) {
    callbacks.onError?.({ kind: 'server', message: 'The agent service returned an empty response.' });
    return;
  }

  let sawTerminal = false;
  try {
    for await (const event of parseSseStream(response.body)) {
      switch (event.type) {
        case 'step':
          callbacks.onStep?.(event.payload);
          break;
        case 'delta':
          callbacks.onDelta?.(event.payload.text);
          break;
        case 'final':
          sawTerminal = true;
          callbacks.onFinal?.(event.payload);
          break;
        case 'error':
          sawTerminal = true;
          callbacks.onError?.({ kind: 'server', message: event.payload.message });
          return;
        case 'done':
          sawTerminal = true;
          callbacks.onDone?.();
          return;
      }
    }
  } catch (err) {
    if (isAbort(err)) return;
    callbacks.onError?.({
      kind: 'interrupted',
      message: 'The connection was interrupted before the answer finished.',
    });
    return;
  }

  // Stream ended without a `final`/`done`/`error` event — treat as interrupted.
  if (!sawTerminal) {
    callbacks.onError?.({
      kind: 'interrupted',
      message: 'The connection was interrupted before the answer finished.',
    });
  }
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === 'AbortError';
}

/** Map a non-2xx response to a typed error, reading rate-limit metadata. */
async function toHttpError(response: Response): Promise<QueryError> {
  let detail = '';
  let retryAfter: number | undefined;

  const headerRetry = response.headers.get('retry-after');
  if (headerRetry) {
    const parsed = Number.parseInt(headerRetry, 10);
    if (!Number.isNaN(parsed)) retryAfter = parsed;
  }

  try {
    const body: unknown = await response.json();
    if (body && typeof body === 'object' && 'detail' in body) {
      detail = String((body as { detail: unknown }).detail);
    }
    if (
      body &&
      typeof body === 'object' &&
      'retry_after' in body &&
      retryAfter === undefined
    ) {
      const ra = Number((body as { retry_after: unknown }).retry_after);
      if (!Number.isNaN(ra)) retryAfter = Math.ceil(ra);
    }
  } catch {
    // non-JSON error body — fall through to a generic message
  }

  if (response.status === 429) {
    const isBudget = detail.toLowerCase().includes('budget');
    return {
      kind: isBudget ? 'budget' : 'rate_limit',
      message: isBudget
        ? "The demo's daily cost guard has been reached. It resets at midnight UTC."
        : "You've reached the demo rate limit. Give it a moment and try again.",
      retryAfter,
    };
  }

  return {
    kind: 'server',
    message: detail || `The agent service returned an error (HTTP ${response.status}).`,
  };
}
