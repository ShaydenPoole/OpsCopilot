"""End-to-end API smoke tests using FastAPI's TestClient.

The agent is wired with a deterministic ``TestModel`` so the tests don't
hit OpenRouter. Full LLM-side behavior is covered by the eval suite (U7).
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from aviation_copilot.agent.core import build_agent, clear_tool_registrars
from aviation_copilot.api.app import create_app
from aviation_copilot.api.rate_limit import DailyBudget, RateLimiter
from aviation_copilot.config import Settings
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel


@pytest.fixture
def client() -> Iterator[TestClient]:
    clear_tool_registrars()
    settings = Settings(test_mode=True)
    agent = build_agent(model=TestModel(), settings=settings, apply_tool_registrars=False)
    app = create_app(
        settings=settings,
        agent=agent,
        rate_limiter=RateLimiter(rate_per_second=100.0, burst=100.0),
        daily_budget=DailyBudget(max_tokens_per_day=10_000_000),
    )
    with TestClient(app) as c:
        yield c


class TestHealthz:
    def test_returns_status_payload(self, client: TestClient) -> None:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] in ("ok", "degraded")
        # No flight_db / corpus_index wired in this test app.
        assert body["flight_db_ready"] is False
        assert body["corpus_index_ready"] is False
        assert body["notes"]


class TestVersion:
    def test_reports_models_and_version(self, client: TestClient) -> None:
        resp = client.get("/version")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "aviation-ops-copilot"
        assert body["version"]
        assert "openai/gpt-oss-120b" in body["agent_model"]
        assert body["judge_model"].startswith("meta-llama")


class TestQueryHappyPath:
    def test_streams_events_and_persists_trace(self, client: TestClient) -> None:
        resp = client.post("/query", json={"question": "What is the weather?"})
        assert resp.status_code == 200
        events = list(_parse_sse(resp.text))
        # Must contain a final event.
        finals = [e for e in events if e["type"] == "final"]
        assert len(finals) == 1
        final_payload = finals[0]["payload"]
        assert "answer" in final_payload
        assert "trace_id" in final_payload
        # And a done terminator.
        assert any(e["type"] == "done" for e in events)
        # Trace persisted for the /trace/{id} endpoint.
        trace_id = final_payload["trace_id"]
        trace_resp = client.get(f"/trace/{trace_id}")
        assert trace_resp.status_code == 200
        assert trace_resp.json()["trace_id"] == trace_id


class TestQueryInvalidInput:
    def test_empty_question_returns_422(self, client: TestClient) -> None:
        resp = client.post("/query", json={"question": ""})
        # FastAPI validation returns 422 for min_length violation.
        assert resp.status_code == 422


class TestTraceUnknownId:
    def test_returns_404(self, client: TestClient) -> None:
        resp = client.get("/trace/nonexistent")
        assert resp.status_code == 404


class TestRateLimitExceeded:
    def test_throttles_with_retry_after(self) -> None:
        clear_tool_registrars()
        settings = Settings(test_mode=True)
        agent = build_agent(model=TestModel(), settings=settings, apply_tool_registrars=False)
        # 1 token burst, slow refill -> second request throttled.
        app = create_app(
            settings=settings,
            agent=agent,
            rate_limiter=RateLimiter(rate_per_second=0.01, burst=1.0),
            daily_budget=DailyBudget(max_tokens_per_day=10_000_000),
        )
        with TestClient(app) as c:
            first = c.post("/query", json={"question": "first"})
            assert first.status_code == 200
            second = c.post("/query", json={"question": "second"})
            assert second.status_code == 429
            assert "Retry-After" in second.headers


class TestBudgetExceeded:
    def test_returns_429_with_used_today(self) -> None:
        clear_tool_registrars()
        settings = Settings(test_mode=True)
        agent = build_agent(model=TestModel(), settings=settings, apply_tool_registrars=False)
        # Cap of 1 token -> the first request will be allowed (budget.allow with
        # default requested=0), then add tokens, then second request blocked.
        budget = DailyBudget(max_tokens_per_day=1)
        budget.add(2)  # exhaust the cap immediately
        app = create_app(
            settings=settings,
            agent=agent,
            rate_limiter=RateLimiter(rate_per_second=100.0, burst=100.0),
            daily_budget=budget,
        )
        with TestClient(app) as c:
            resp = c.post("/query", json={"question": "anything"})
            assert resp.status_code == 429
            body = resp.json()
            assert body["used_today"] >= body["cap"]


# ----------------------------------------------------------------------
# SSE parsing helper
# ----------------------------------------------------------------------


def _parse_sse(text: str) -> Iterator[dict]:
    """Yield each SSE event payload parsed from raw text body.

    The test client returns the full body; we split on blank lines and
    pull the data: payload from each event block.
    """
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        for line in block.splitlines():
            if line.startswith("data: "):
                yield json.loads(line[len("data: ") :])
