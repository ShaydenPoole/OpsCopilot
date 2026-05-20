import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { ToolTracePanel } from '@/components/ToolTracePanel';
import type { TraceStep } from '@/lib/types';

const TS = '2026-05-19T12:00:00.000Z';

const STEPS: TraceStep[] = [
  { kind: 'tool_call', step_id: 's1', ts: TS, tool_name: 'weather_lookup', args: { icao: 'KORD' }, attempt: 1 },
  {
    kind: 'tool_result',
    step_id: 's2',
    ts: TS,
    tool_name: 'weather_lookup',
    result_preview: 'VFR, wind 8kt',
    success: true,
    latency_ms: 120,
  },
  {
    kind: 'llm_call',
    step_id: 's3',
    ts: TS,
    model: 'openai/gpt-oss-120b',
    input_tokens: 900,
    output_tokens: 120,
    cost_usd: 0.00041,
    latency_ms: 850,
  },
];

describe('ToolTracePanel', () => {
  it('renders nothing when there are no steps', () => {
    const { container } = render(<ToolTracePanel steps={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('is collapsed by default and shows the step count', () => {
    render(<ToolTracePanel steps={STEPS} />);
    expect(screen.queryByTestId('trace-step')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /show how the agent reached this answer/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('3 steps')).toBeInTheDocument();
  });

  it('reveals the step cards in chronological order when expanded', async () => {
    const user = userEvent.setup();
    render(<ToolTracePanel steps={STEPS} />);

    await user.click(screen.getByRole('button', { name: /show how the agent reached/i }));

    const cards = screen.getAllByTestId('trace-step');
    expect(cards).toHaveLength(3);
    expect(cards[0]).toHaveTextContent('Tool call');
    expect(cards[0]).toHaveTextContent('weather_lookup');
    expect(cards[1]).toHaveTextContent('Tool result');
    expect(cards[2]).toHaveTextContent('LLM');
    expect(cards[2]).toHaveTextContent('openai/gpt-oss-120b');
  });

  it('shows tool-call arguments as formatted JSON', async () => {
    const user = userEvent.setup();
    render(<ToolTracePanel steps={STEPS} />);
    await user.click(screen.getByRole('button', { name: /show how the agent reached/i }));
    expect(screen.getByText(/"icao": "KORD"/)).toBeInTheDocument();
  });

  it('honours defaultOpen so a streaming run shows steps immediately', () => {
    render(<ToolTracePanel steps={STEPS} defaultOpen />);
    expect(screen.getAllByTestId('trace-step')).toHaveLength(3);
  });
});
