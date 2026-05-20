import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatSurface } from '@/components/ChatSurface';
import { streamQuery } from '@/lib/api-client';
import type { QueryResponse, TraceStep } from '@/lib/types';

vi.mock('@/lib/api-client', () => ({
  streamQuery: vi.fn(),
  PROXY_ENDPOINT: '/api/proxy',
}));

const TS = '2026-05-19T12:00:00.000Z';

const TOOL_CALL: TraceStep = {
  kind: 'tool_call',
  step_id: 's1',
  ts: TS,
  tool_name: 'weather_lookup',
  args: { icao: 'KORD' },
  attempt: 1,
};
const TOOL_RESULT: TraceStep = {
  kind: 'tool_result',
  step_id: 's2',
  ts: TS,
  tool_name: 'weather_lookup',
  result_preview: 'VFR, wind 8kt',
  success: true,
  latency_ms: 120,
};

function finalResponse(answer: string, steps: TraceStep[]): QueryResponse {
  return {
    trace_id: 't1',
    answer,
    error: null,
    trace: {
      trace_id: 't1',
      question: 'q',
      started_at: TS,
      completed_at: TS,
      steps,
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ChatSurface', () => {
  it('streams an answer and reveals the tool trace on request', async () => {
    const user = userEvent.setup();
    vi.mocked(streamQuery).mockImplementation(async (_question, callbacks) => {
      callbacks.onStep?.(TOOL_CALL);
      callbacks.onStep?.(TOOL_RESULT);
      callbacks.onFinal?.(
        finalResponse('ORD is currently VFR with light winds.', [TOOL_CALL, TOOL_RESULT]),
      );
      callbacks.onDone?.();
    });

    render(<ChatSurface />);
    await user.type(screen.getByLabelText(/ask an aviation/i), 'weather at ORD');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    expect(await screen.findByText('weather at ORD')).toBeInTheDocument();
    expect(
      await screen.findByText('ORD is currently VFR with light winds.'),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /show how the agent reached/i }));
    expect(screen.getAllByTestId('trace-step')).toHaveLength(2);
  });

  it('prefills the input and focuses the textarea when a sample is picked', async () => {
    const user = userEvent.setup();
    render(<ChatSurface />);

    await user.click(
      screen.getByRole('button', { name: /average departure delay at ORD/i }),
    );

    const textarea = screen.getByLabelText(/ask an aviation/i);
    expect(textarea).toHaveValue('What was the average departure delay at ORD in summer 2024?');
    expect(textarea).toHaveFocus();
  });

  it('keeps submit disabled until the input has non-whitespace text', async () => {
    const user = userEvent.setup();
    render(<ChatSurface />);

    const button = screen.getByRole('button', { name: /^ask$/i });
    expect(button).toBeDisabled();

    const textarea = screen.getByLabelText(/ask an aviation/i);
    await user.type(textarea, '    ');
    expect(button).toBeDisabled();

    await user.type(textarea, 'real question');
    expect(button).toBeEnabled();
  });

  it('surfaces a rate-limit message linking to the repo', async () => {
    const user = userEvent.setup();
    vi.mocked(streamQuery).mockImplementation(async (_question, callbacks) => {
      callbacks.onError?.({
        kind: 'rate_limit',
        message: "You've reached the demo rate limit. Give it a moment and try again.",
      });
    });

    render(<ChatSurface />);
    await user.type(screen.getByLabelText(/ask an aviation/i), 'hello');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    expect(await screen.findByText(/reached the demo rate limit/i)).toBeInTheDocument();
    const link = screen.getByRole('link', { name: /portfolio demo with cost guards/i });
    expect(link.getAttribute('href')).toContain('github.com');
  });

  it('offers a retry control when the stream is interrupted', async () => {
    const user = userEvent.setup();
    const seen: string[] = [];
    vi.mocked(streamQuery).mockImplementation(async (question, callbacks) => {
      seen.push(question);
      if (seen.length === 1) {
        callbacks.onError?.({
          kind: 'interrupted',
          message: 'The connection was interrupted before the answer finished.',
        });
      } else {
        callbacks.onFinal?.(finalResponse('Here is the recovered answer.', []));
        callbacks.onDone?.();
      }
    });

    render(<ChatSurface />);
    await user.type(screen.getByLabelText(/ask an aviation/i), 'hello');
    await user.click(screen.getByRole('button', { name: /^ask$/i }));

    expect(await screen.findByText(/connection was interrupted/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByText('Here is the recovered answer.')).toBeInTheDocument();
    expect(seen).toEqual(['hello', 'hello']);
  });
});
