"""LLM agent orchestration (Pydantic-AI).

Public surface:

- :func:`build_agent`    : factory returning a configured Pydantic-AI Agent.
- :func:`run_with_trace` : run an agent end-to-end, capturing a structured trace.
- :class:`AgentResult`   : answer + trace + error envelope.
- :class:`AgentDeps`     : dependency object passed to every tool invocation.

Tool implementations live in :mod:`aviation_copilot.tools` (U5) and register
themselves via :func:`register_tools`. This module owns only the orchestration.
"""

from aviation_copilot.agent.core import (
    AgentDeps,
    AgentResult,
    build_agent,
    register_tools,
    run_with_trace,
)
from aviation_copilot.agent.errors import (
    AgentError,
    MaxStepsExceededError,
    ToolError,
)
from aviation_copilot.agent.trace import (
    ErrorStep,
    LLMCallStep,
    ToolCallStep,
    ToolResultStep,
    Trace,
    TraceStep,
)

__all__ = [
    "AgentDeps",
    "AgentError",
    "AgentResult",
    "ErrorStep",
    "LLMCallStep",
    "MaxStepsExceededError",
    "ToolCallStep",
    "ToolError",
    "ToolResultStep",
    "Trace",
    "TraceStep",
    "build_agent",
    "register_tools",
    "run_with_trace",
]
