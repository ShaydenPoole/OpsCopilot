'use client';

import { useState } from 'react';
import type { TraceStep } from '@/lib/types';

/**
 * Collapsible inspector that shows how the agent reached an answer: every LLM
 * call, tool call, tool result, and error, in the order they happened.
 *
 * Collapsed by default so the answer stays the focus; one click reveals the
 * full chain. The same panel updates live while a run streams.
 */

interface ToolTracePanelProps {
  steps: TraceStep[];
  /** Open on first render — used while a run is still streaming. */
  defaultOpen?: boolean;
}

export function ToolTracePanel({ steps, defaultOpen = false }: ToolTracePanelProps) {
  const [open, setOpen] = useState(defaultOpen);

  if (steps.length === 0) return null;

  return (
    <div className="mt-3 border-t border-slate-800 pt-3">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 text-left text-sm font-medium text-accent transition-colors hover:text-accent/80"
      >
        <span>{open ? 'Hide agent trace' : 'Show how the agent reached this answer'}</span>
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
          {steps.length} {steps.length === 1 ? 'step' : 'steps'}
        </span>
      </button>

      {open && (
        <ol className="mt-3 space-y-2">
          {steps.map((step, index) => (
            <li key={`${step.step_id}-${index}`} data-testid="trace-step">
              <TraceStepCard step={step} index={index} />
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

const KIND_META: Record<TraceStep['kind'], { label: string; tone: string }> = {
  llm_call: { label: 'LLM', tone: 'border-sky-500/40 text-sky-300' },
  tool_call: { label: 'Tool call', tone: 'border-accent/40 text-accent' },
  tool_result: { label: 'Tool result', tone: 'border-emerald-500/40 text-emerald-300' },
  error: { label: 'Error', tone: 'border-rose-500/50 text-rose-300' },
};

function TraceStepCard({ step, index }: { step: TraceStep; index: number }) {
  const meta = KIND_META[step.kind];
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-slate-600">{index + 1}</span>
        <span className={`rounded border px-1.5 py-0.5 font-medium ${meta.tone}`}>{meta.label}</span>
        <span className="font-mono text-slate-300">{stepTitle(step)}</span>
        <span className="ml-auto font-mono text-slate-500">{stepMeta(step)}</span>
      </div>
      <StepDetail step={step} />
    </div>
  );
}

function StepDetail({ step }: { step: TraceStep }) {
  switch (step.kind) {
    case 'tool_call':
      return (
        <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-2 font-mono text-xs text-slate-400">
          {JSON.stringify(step.args, null, 2)}
        </pre>
      );
    case 'tool_result':
      return <p className="mt-2 text-xs text-slate-400">{step.result_preview}</p>;
    case 'error':
      return <p className="mt-2 text-xs text-rose-300/90">{step.message}</p>;
    case 'llm_call':
      return null;
  }
}

function stepTitle(step: TraceStep): string {
  switch (step.kind) {
    case 'llm_call':
      return step.model;
    case 'tool_call':
    case 'tool_result':
      return step.tool_name;
    case 'error':
      return step.error_kind;
  }
}

function stepMeta(step: TraceStep): string {
  switch (step.kind) {
    case 'llm_call': {
      const parts: string[] = [];
      if (step.input_tokens != null || step.output_tokens != null) {
        parts.push(`${step.input_tokens ?? 0}→${step.output_tokens ?? 0} tok`);
      }
      if (step.cost_usd != null) parts.push(formatCost(step.cost_usd));
      if (step.latency_ms != null) parts.push(formatMs(step.latency_ms));
      return parts.join(' · ');
    }
    case 'tool_result':
      return step.latency_ms != null ? formatMs(step.latency_ms) : step.success ? 'ok' : 'failed';
    case 'tool_call':
      return step.attempt > 1 ? `attempt ${step.attempt}` : '';
    case 'error':
      return step.retryable ? 'retryable' : '';
  }
}

function formatMs(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`;
}

function formatCost(usd: number): string {
  return usd >= 0.01 ? `$${usd.toFixed(2)}` : `$${usd.toFixed(4)}`;
}
