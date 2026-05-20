# Aviation Ops Copilot — Backend

Python 3.12, Pydantic-AI agent + FastAPI service. Managed with [`uv`](https://docs.astral.sh/uv/).

## Setup

```bash
cd backend
uv sync --all-extras
uv run pytest
```

`uv sync` reads `pyproject.toml` and creates `.venv/`. Add `--all-extras` to include the `dev`, `eval`, and `deploy` optional groups.

> **`uv` not on PATH?** On this project's dev machine `uv` was installed via `pip install --user uv`, which does not add it to PATH. Invoke it as a module instead: `python -m uv run pytest`. Add `--no-sync` (`python -m uv run --no-sync pytest`) to skip the dependency re-sync when the environment is already current — faster for repeated test runs.

## Layout

```
backend/
├── aviation_copilot/    # flat layout (not under src/) so local imports work without packaging
│   ├── agent/           # Pydantic-AI agent (U4)
│   ├── tools/           # 4 tools (U5)
│   ├── corpus/          # AIM chunking + embedding + LanceDB (U3)
│   ├── data/            # DuckDB client (U2)
│   ├── api/             # FastAPI app (U6)
│   ├── observability/   # Langfuse (U8)
│   └── config.py        # env + settings
├── tests/
│   ├── unit/
│   ├── integration/     # cassette-backed end-to-end (U6 / U10)
│   └── conftest.py
├── pyproject.toml
└── modal_app.py         # Modal deploy entry (U11)
```

> **Layout note:** the plan's Output Structure shows `src/aviation_copilot/`. The flat layout here is a deliberate local-dev deviation — Windows Smart App Control blocks uv's local-build subprocess, and the flat layout avoids needing one. Production deploys (Modal, CI on Linux) build normally from `pyproject.toml`.

## Commands

| Command | Purpose |
|---------|---------|
| `uv run pytest` | run all tests |
| `uv run pytest -m "not live"` | skip tests that hit real external services |
| `uv run ruff check .` | lint |
| `uv run ruff format .` | format |
| `uv run mypy aviation_copilot/` | type-check |
| `uv run uvicorn aviation_copilot.api.app:app --reload` | run the API locally (after U6) |

See the [implementation plan](../docs/plans/2026-05-19-001-feat-aviation-ops-copilot-plan.md) for what each unit owns.
