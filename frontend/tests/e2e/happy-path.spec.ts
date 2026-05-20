import { expect, test } from '@playwright/test';

/**
 * End-to-end happy path against a mocked backend.
 *
 * The `/api/proxy` route is intercepted and fulfilled with a canned SSE
 * stream, so the test exercises the full UI (page load → question → streamed
 * answer → expanded trace) without a live agent or LLM.
 */

const TS = '2026-05-19T12:00:00.000Z';

const STEPS = [
  {
    kind: 'tool_call',
    step_id: 's1',
    ts: TS,
    tool_name: 'weather_lookup',
    args: { icao: 'KJFK' },
    attempt: 1,
  },
  {
    kind: 'tool_result',
    step_id: 's2',
    ts: TS,
    tool_name: 'weather_lookup',
    result_preview: 'VFR, wind calm',
    success: true,
    latency_ms: 110,
  },
];

const SSE_EVENTS = [
  { type: 'step', payload: STEPS[0] },
  { type: 'step', payload: STEPS[1] },
  {
    type: 'final',
    payload: {
      trace_id: 't1',
      answer: 'KJFK is currently VFR with calm winds.',
      error: null,
      trace: {
        trace_id: 't1',
        question: 'What is the weather at KJFK?',
        started_at: TS,
        completed_at: TS,
        steps: STEPS,
      },
    },
  },
  { type: 'done', payload: {} },
];

const SSE_BODY = `${SSE_EVENTS.map((event) => `data: ${JSON.stringify(event)}`).join('\n\n')}\n\n`;

test('user asks a question and inspects the agent trace', async ({ page }) => {
  await page.route('**/api/proxy', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: SSE_BODY,
    });
  });

  await page.goto('/');

  await page.getByLabel(/ask an aviation/i).fill('What is the weather at KJFK?');
  await page.getByRole('button', { name: 'Ask' }).click();

  await expect(page.getByText('KJFK is currently VFR with calm winds.')).toBeVisible();

  await page.getByRole('button', { name: /show how the agent reached/i }).click();
  await expect(page.getByTestId('trace-step')).toHaveCount(2);
});
