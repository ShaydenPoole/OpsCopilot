"""Agent and tool error types.

All errors raised by tools (U5) inherit from :class:`ToolError`. The agent
loop (U4) distinguishes retryable from non-retryable cases via the
``retryable`` flag — retryable errors get one retry, non-retryable ones
surface immediately to the LLM as "tool unavailable".

Sanitized error messages: ``ToolError.user_message`` is the safe text that
flows back to the LLM (and ultimately the user). The original exception is
preserved on ``__cause__`` for logging.
"""

from __future__ import annotations

from typing import Literal

ToolErrorKind = Literal[
    "upstream_timeout",
    "upstream_client_error",
    "upstream_server_error",
    "db_error",
    "invalid_input",
    "no_data",
    "unavailable",
    "internal",
]


class AgentError(Exception):
    """Base for all agent-layer errors. Sanitized for user-facing surfaces."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ToolError(AgentError):
    """A tool failed in a way the agent loop should know about.

    Args:
        kind: A short categorical label used by the trace and retry policy.
        retryable: When True the agent loop retries once before giving up.
        user_message: A short, sanitized message safe to forward to the LLM
            (and ultimately the user). Should not contain SQL, stack traces,
            or other internal detail.
    """

    def __init__(
        self,
        kind: ToolErrorKind,
        *,
        retryable: bool,
        user_message: str,
    ) -> None:
        super().__init__(user_message)
        self.kind: ToolErrorKind = kind
        self.retryable = retryable
        self.user_message = user_message

    def __repr__(self) -> str:
        return (
            f"ToolError(kind={self.kind!r}, retryable={self.retryable}, "
            f"user_message={self.user_message!r})"
        )


class MaxStepsExceededError(AgentError):
    """The agent loop hit the configured ``max_steps`` cap before producing
    a final answer.

    The agent returns a graceful partial answer to the caller; this error
    is raised internally and converted into a structured trace step.
    """

    def __init__(self, max_steps: int) -> None:
        super().__init__(f"Agent exceeded max_steps={max_steps} without a final answer.")
        self.max_steps = max_steps
