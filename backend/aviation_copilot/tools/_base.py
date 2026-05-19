"""Shared tool utilities.

- :func:`new_http_client` — configured httpx.AsyncClient with sensible timeouts
- :func:`map_http_error`  — convert httpx exceptions to ToolError
- :func:`truncate_for_trace` — short preview text for trace.append_tool_result
"""

from __future__ import annotations

import httpx

from aviation_copilot.agent.errors import ToolError

DEFAULT_TIMEOUT_SECONDS = 5.0
USER_AGENT = "aviation-ops-copilot/0.1 (portfolio project; contact: pooleshayden@gmail.com)"


def new_http_client(
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    base_url: str | None = None,
) -> httpx.AsyncClient:
    """Construct an httpx.AsyncClient with project-standard headers and timeout.

    Callers should ``async with new_http_client(...) as client:`` to ensure
    connections are closed.
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    kwargs: dict[str, object] = {"timeout": timeout, "headers": headers}
    if base_url:
        kwargs["base_url"] = base_url
    return httpx.AsyncClient(**kwargs)  # type: ignore[arg-type]


def map_http_error(exc: httpx.HTTPError, *, source: str) -> ToolError:
    """Translate an httpx exception into a sanitized :class:`ToolError`.

    The returned error never carries raw URLs, query strings, or stack
    traces — only a category and a short message that's safe to surface
    to the LLM (and ultimately the user).
    """
    if isinstance(exc, httpx.TimeoutException):
        return ToolError(
            kind="upstream_timeout",
            retryable=True,
            user_message=f"{source} timed out before responding.",
        )
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if 500 <= status < 600:
            return ToolError(
                kind="upstream_server_error",
                retryable=True,
                user_message=f"{source} returned a server error ({status}).",
            )
        if 400 <= status < 500:
            return ToolError(
                kind="upstream_client_error",
                retryable=False,
                user_message=f"{source} rejected the request ({status}).",
            )
    # Generic transport / network failure.
    return ToolError(
        kind="unavailable",
        retryable=True,
        user_message=f"{source} is currently unreachable.",
    )


def truncate_for_trace(text: str, *, max_len: int = 240) -> str:
    """Truncate text for the trace.append_tool_result preview field."""
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1].rstrip() + "…"  # ellipsis
