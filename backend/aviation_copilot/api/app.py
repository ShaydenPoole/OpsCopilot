"""FastAPI application factory.

Build the app via :func:`create_app`. Tests construct app instances with
injected state; ``modal_app.py`` (U11) and ``uvicorn`` use ``create_app()``
directly with defaults from :mod:`aviation_copilot.config`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aviation_copilot.agent.core import AgentDeps, build_agent
from aviation_copilot.api.rate_limit import DailyBudget, RateLimiter
from aviation_copilot.api.routes import router
from aviation_copilot.config import Settings, get_settings
from aviation_copilot.tools import register_default_registrars

if TYPE_CHECKING:
    from pydantic_ai import Agent


def create_app(
    *,
    settings: Settings | None = None,
    agent: Agent[AgentDeps, str] | None = None,
    flight_db: object | None = None,
    corpus_index: object | None = None,
    rate_limiter: RateLimiter | None = None,
    daily_budget: DailyBudget | None = None,
    cors_origins: list[str] | None = None,
) -> FastAPI:
    """Build a FastAPI app with optionally-injected dependencies.

    For production (Modal/uvicorn) callers pass nothing and let the
    lifespan resolve everything from settings + disk. Tests build the app
    with a pre-wired agent (e.g. using TestModel) and in-memory state.
    """
    s = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # Set state populated either from injected args or from settings.
        app.state.settings = s
        app.state.trace_store = {}
        app.state.rate_limiter = rate_limiter or RateLimiter()
        app.state.daily_budget = daily_budget or DailyBudget(
            max_tokens_per_day=2_000_000  # generous portfolio cap
        )
        app.state.flight_db = flight_db
        app.state.corpus_index = corpus_index
        if flight_db is None and s.flight_duckdb_path.exists():
            from aviation_copilot.data.duckdb_client import DuckDBClient

            app.state.flight_db = DuckDBClient(s.flight_duckdb_path, read_only=True)
            app.state.flight_db.connect()
        if corpus_index is None and s.corpus_lance_path.exists():
            from aviation_copilot.corpus.embed import SentenceTransformersEmbedder
            from aviation_copilot.corpus.index import CorpusIndex

            app.state.corpus_index = CorpusIndex(
                s.corpus_lance_path,
                embedder=SentenceTransformersEmbedder(),
            )
            app.state.corpus_index.open()
        # Build agent + register tools unless caller supplied one.
        if agent is None:
            register_default_registrars()
            app.state.agent = build_agent(settings=s, apply_tool_registrars=True)
        else:
            app.state.agent = agent
        # Optional version manifests
        app.state.flight_data_version = _maybe_load_json(
            s.flight_duckdb_path.parent / "data_version.json"
        )
        app.state.corpus_version = _maybe_load_json(
            s.flight_duckdb_path.parent / "corpus_version.json"
        )
        try:
            yield
        finally:
            db = getattr(app.state, "flight_db", None)
            if db is not None and hasattr(db, "close"):
                db.close()

    app = FastAPI(
        title="Aviation Ops Copilot",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


def _maybe_load_json(path: Any) -> dict[str, Any] | None:
    try:
        import json
        from pathlib import Path

        p = Path(path)
        if not p.exists():
            return None
        parsed = json.loads(p.read_text(encoding="utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None
