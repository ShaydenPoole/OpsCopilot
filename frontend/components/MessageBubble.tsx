import { SITE } from '@/lib/site';
import type { ChatMessage, TraceStep } from '@/lib/types';
import { StreamingText } from './StreamingText';
import { ToolTracePanel } from './ToolTracePanel';

/**
 * One turn in the conversation: a right-aligned user question or a
 * left-aligned assistant answer with its expandable tool trace.
 */

interface MessageBubbleProps {
  message: ChatMessage;
  onRetry: (question: string) => void;
}

export function MessageBubble({ message, onRetry }: MessageBubbleProps) {
  if (message.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-slate-800 px-4 py-2.5 text-slate-100">
          {message.text}
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-[92%] rounded-2xl rounded-bl-sm border border-slate-800 bg-slate-900 px-4 py-3">
        {message.error ? (
          <ErrorBanner message={message} onRetry={onRetry} />
        ) : (
          <AssistantAnswer message={message} />
        )}
      </div>
    </div>
  );
}

function AssistantAnswer({ message }: { message: ChatMessage }) {
  const streaming = message.status === 'streaming';
  const hasAnswer = message.text.length > 0;
  const degraded = !streaming && message.steps.some((step) => step.kind === 'error');

  return (
    <>
      {!hasAnswer && streaming ? (
        <LiveActivity steps={message.steps} />
      ) : (
        <StreamingText text={message.text} streaming={streaming} />
      )}

      {degraded && (
        <p className="mt-2 rounded-md bg-amber-500/10 px-2.5 py-1.5 text-xs text-amber-300">
          The agent flagged a data issue while answering — open the trace below for details.
        </p>
      )}

      <ToolTracePanel steps={message.steps} />
    </>
  );
}

/** Compact progress line shown before the answer text arrives. */
function LiveActivity({ steps }: { steps: TraceStep[] }) {
  const latest = steps[steps.length - 1];
  return (
    <div className="flex items-center gap-2 text-sm text-slate-400">
      <span className="cursor-blink text-accent" aria-hidden>
        ●
      </span>
      <span>{describeActivity(latest)}</span>
    </div>
  );
}

function describeActivity(step: TraceStep | undefined): string {
  if (!step) return 'Analyzing your question…';
  switch (step.kind) {
    case 'tool_call':
      return `Calling ${step.tool_name}…`;
    case 'tool_result':
      return `Reviewing results from ${step.tool_name}…`;
    case 'error':
      return 'Handling a tool error…';
    case 'llm_call':
      return 'Composing the answer…';
  }
}

function ErrorBanner({ message, onRetry }: MessageBubbleProps) {
  const error = message.error;
  if (!error) return null;

  const isLimit = error.kind === 'rate_limit' || error.kind === 'budget';
  const canRetry = !isLimit && message.question !== undefined;

  return (
    <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 p-3">
      <p className="text-sm text-rose-200">{error.message}</p>
      <div className="mt-2 flex items-center gap-3 text-xs">
        {canRetry && (
          <button
            type="button"
            onClick={() => onRetry(message.question as string)}
            className="rounded border border-rose-400/50 px-2.5 py-1 font-medium text-rose-200 transition-colors hover:bg-rose-500/20"
          >
            Retry
          </button>
        )}
        {isLimit && (
          <a
            href={SITE.repoUrl}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-rose-200 underline underline-offset-2 hover:text-rose-100"
          >
            This is a portfolio demo with cost guards — see the repo
          </a>
        )}
      </div>
    </div>
  );
}
