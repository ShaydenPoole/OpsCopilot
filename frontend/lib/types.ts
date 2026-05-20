/**
 * Shared types for the Aviation Ops Copilot frontend.
 *
 * These mirror the backend Pydantic models in `backend/aviation_copilot/api`
 * and `backend/aviation_copilot/agent/trace.py`. The SSE envelope contract is
 * the documented seam between the two — keep this file in sync with
 * `api/models.py` (`SseEvent`, `QueryResponse`) and `agent/trace.py`.
 */

// ---------------------------------------------------------------------------
// Trace steps — discriminated union on `kind`
// ---------------------------------------------------------------------------

interface BaseStep {
  step_id: string;
  /** ISO-8601 timestamp. */
  ts: string;
}

export interface LLMCallStep extends BaseStep {
  kind: 'llm_call';
  model: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  latency_ms: number | null;
}

export interface ToolCallStep extends BaseStep {
  kind: 'tool_call';
  tool_name: string;
  args: Record<string, unknown>;
  attempt: number;
}

export interface ToolResultStep extends BaseStep {
  kind: 'tool_result';
  tool_name: string;
  result_preview: string;
  success: boolean;
  latency_ms: number | null;
}

export interface ErrorStep extends BaseStep {
  kind: 'error';
  error_kind: string;
  message: string;
  retryable: boolean;
  tool_name: string | null;
}

export type TraceStep = LLMCallStep | ToolCallStep | ToolResultStep | ErrorStep;

// ---------------------------------------------------------------------------
// Trace + query response
// ---------------------------------------------------------------------------

export interface Trace {
  trace_id: string;
  question: string;
  steps: TraceStep[];
  started_at: string;
  completed_at: string | null;
}

export interface QueryResponse {
  trace_id: string;
  answer: string;
  trace: Trace;
  error: string | null;
}

// ---------------------------------------------------------------------------
// SSE envelope — `data:` payloads streamed from `POST /query`
// ---------------------------------------------------------------------------

export type SseEvent =
  | { type: 'step'; payload: TraceStep }
  | { type: 'delta'; payload: { text: string } }
  | { type: 'final'; payload: QueryResponse }
  | { type: 'error'; payload: { kind: string; message: string } }
  | { type: 'done'; payload: Record<string, never> | null };

// ---------------------------------------------------------------------------
// Client-side error model
// ---------------------------------------------------------------------------

export type QueryErrorKind =
  | 'rate_limit'
  | 'budget'
  | 'network'
  | 'interrupted'
  | 'server';

export interface QueryError {
  kind: QueryErrorKind;
  message: string;
  /** Seconds to wait before retrying, when the backend supplies `Retry-After`. */
  retryAfter?: number;
}

// ---------------------------------------------------------------------------
// Chat surface state
// ---------------------------------------------------------------------------

export type ChatMessageStatus = 'streaming' | 'complete' | 'error';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  /** Trace steps as they stream in, before the `final` event lands. */
  steps: TraceStep[];
  /** The full trace, populated from the `final` event. */
  trace?: Trace;
  error?: QueryError;
  status: ChatMessageStatus;
  /** The originating question — kept on assistant messages so retry can resend. */
  question?: string;
}
