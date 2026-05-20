"""Tests for the agent error types."""

from __future__ import annotations

import pytest
from aviation_copilot.agent.errors import (
    AgentError,
    MaxStepsExceededError,
    ToolError,
)


class TestToolError:
    def test_basic_fields(self) -> None:
        err = ToolError(
            kind="upstream_timeout",
            retryable=True,
            user_message="weather service timed out",
        )
        assert err.kind == "upstream_timeout"
        assert err.retryable is True
        assert err.user_message == "weather service timed out"
        assert str(err) == "weather service timed out"

    def test_repr_includes_kind_and_retryable(self) -> None:
        err = ToolError(kind="invalid_input", retryable=False, user_message="bad arg")
        r = repr(err)
        assert "invalid_input" in r
        assert "retryable=False" in r

    def test_is_agent_error(self) -> None:
        err = ToolError(kind="db_error", retryable=False, user_message="boom")
        assert isinstance(err, AgentError)

    def test_kind_constraint_documented(self) -> None:
        # Literal type means valid kinds at compile-time; runtime accepts any
        # string. Document the canonical set in passing.
        valid = {
            "upstream_timeout",
            "upstream_client_error",
            "upstream_server_error",
            "db_error",
            "invalid_input",
            "no_data",
            "unavailable",
            "internal",
        }
        for k in valid:
            ToolError(kind=k, retryable=False, user_message="x")  # type: ignore[arg-type]


class TestMaxStepsExceededError:
    def test_carries_step_limit(self) -> None:
        err = MaxStepsExceededError(max_steps=8)
        assert err.max_steps == 8
        assert "max_steps=8" in str(err)

    def test_is_agent_error(self) -> None:
        assert isinstance(MaxStepsExceededError(max_steps=4), AgentError)


class TestAgentError:
    def test_carries_message(self) -> None:
        err = AgentError("config missing")
        assert err.message == "config missing"
        assert str(err) == "config missing"

    def test_inherits_from_exception(self) -> None:
        with pytest.raises(AgentError):
            raise AgentError("boom")
