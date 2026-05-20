"""Shared pytest fixtures for the aviation_copilot test suite.

This file is intentionally thin in U1. Tool-specific fixtures (mocked HTTP
clients, sample DuckDB/LanceDB fixtures, recorded LLM cassettes) land in U2-U7.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    """Repo root, two parents up from this conftest."""
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    """Directory where test fixtures live."""
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    """Strip env vars that would otherwise leak real credentials into tests.

    Tests that need credentials set them explicitly via monkeypatch.
    """
    for key in (
        "OPENROUTER_API_KEY",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "FAA_NOTAM_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    # Tell the app it's running under test so it skips real Langfuse/OpenRouter init.
    monkeypatch.setenv("AVIATION_COPILOT_TEST_MODE", "1")
    yield
