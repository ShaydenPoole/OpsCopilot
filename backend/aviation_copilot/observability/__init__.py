"""Observability for the aviation_copilot agent (U8).

Exposes the :class:`AgentObserver` interface and a Langfuse-backed
implementation. See :mod:`aviation_copilot.observability.langfuse_client`.
"""

from __future__ import annotations

from aviation_copilot.observability.langfuse_client import (
    AgentObserver,
    LangfuseObserver,
    NoopObserver,
    build_observer,
    get_observer,
)

__all__ = [
    "AgentObserver",
    "LangfuseObserver",
    "NoopObserver",
    "build_observer",
    "get_observer",
]
