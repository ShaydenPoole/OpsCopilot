/**
 * Proxy route: forwards `POST /api/proxy` to the agent backend's `/query`
 * endpoint and streams the SSE response straight back to the browser.
 *
 * Keeping the proxy server-side means the real backend URL (`BACKEND_URL`)
 * never reaches the client, and the backend can be swapped without a frontend
 * change. Error statuses (e.g. 429 rate limit) are forwarded verbatim so the
 * client can render them.
 */

import type { NextRequest } from 'next/server';

const BACKEND_URL = process.env.BACKEND_URL ?? 'http://localhost:8000';

// Node runtime: streams upstream response bodies without buffering.
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function POST(request: NextRequest): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ detail: 'Request body must be valid JSON.' }, { status: 400 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND_URL}/query`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    return Response.json(
      { detail: 'The agent service is unreachable. It may be cold-starting — try again shortly.' },
      { status: 502 },
    );
  }

  // Forward non-streaming error responses (4xx/5xx) with their status + body.
  if (!upstream.ok) {
    const text = await upstream.text();
    const headers = new Headers({
      'content-type': upstream.headers.get('content-type') ?? 'application/json',
    });
    const retryAfter = upstream.headers.get('retry-after');
    if (retryAfter) headers.set('retry-after', retryAfter);
    return new Response(text, { status: upstream.status, headers });
  }

  if (!upstream.body) {
    return Response.json({ detail: 'The agent service returned an empty response.' }, { status: 502 });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache, no-transform',
      connection: 'keep-alive',
    },
  });
}
