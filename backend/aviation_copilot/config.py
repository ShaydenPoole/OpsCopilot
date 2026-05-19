"""Centralized settings for the aviation_copilot package.

Reads from environment variables. The pattern keeps every runtime knob in
one place so tests can monkey-patch and deploys can override via Modal
Secrets / Vercel env vars without touching code.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Path roots for local development. Production overrides via env vars.
_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent

LLMProvider = Literal["openrouter", "anthropic", "openai", "google", "test"]


class Settings(BaseSettings):
    """Runtime configuration for the agent service.

    Env vars are case-insensitive and may be loaded from ``.env`` for local
    development. Production deploys inject them as Modal Secrets / Vercel env.
    """

    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ----- Test-mode flag -----
    test_mode: bool = False
    """When set, the agent service short-circuits real LLM/observability calls."""

    # ----- LLM provider / model -----
    llm_provider: LLMProvider = "openrouter"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    agent_model: str = "openai/gpt-oss-120b"
    """OpenRouter model slug for the agent. Defaults to gpt-oss-120b per the
    plan; the F3 model-selection spike may swap this to gemini-2.5-flash or
    claude-haiku-4 based on tool-call accuracy on a 10-question probe set."""

    judge_model: str = "meta-llama/llama-3.3-70b-instruct"
    """OpenRouter model slug for the LLM-as-judge eval scorer. Paid tier,
    different lineage from the agent."""

    agent_max_steps: int = 8
    """Maximum number of agent loop iterations before returning a partial answer."""

    agent_tool_retries: int = 1
    """Retries per tool call before falling back to 'tool unavailable'."""

    # ----- Data paths -----
    flight_duckdb_path: Path = _REPO_ROOT / "data" / "flights.duckdb"
    corpus_lance_path: Path = _REPO_ROOT / "data" / "corpus_index.lance"

    # ----- Observability -----
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    # ----- Optional NOTAM key -----
    faa_notam_api_key: str = ""

    @property
    def is_openrouter_configured(self) -> bool:
        return bool(self.openrouter_api_key)

    @property
    def is_langfuse_configured(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance. Tests should clear the cache via
    ``get_settings.cache_clear()`` if they need to re-read the environment.
    """
    return Settings(
        test_mode=os.environ.get("AVIATION_COPILOT_TEST_MODE", "").lower() in ("1", "true", "yes"),
    )
