# Aviation Ops Copilot

> **Status: in active development.** This is a portfolio-grade LLM agent project. Polished README, architecture docs, eval results, and demo GIF land in U12. For now, this placeholder records the project shape so contributors and reviewers can navigate the repo.

A production-grade aviation operations LLM agent that orchestrates multiple tools (flight data queries, weather, NOTAMs, RAG over FAA documents) using [Pydantic-AI](https://ai.pydantic.dev/), with a first-class eval suite built on [Inspect AI](https://inspect.aisi.org.uk/) and full observability via [Langfuse](https://langfuse.com/). Deployed to [Modal](https://modal.com/) (Python backend) and [Vercel](https://vercel.com/) (Next.js frontend).

## Where to start

- **Brainstorm / requirements**: [`docs/brainstorms/aviation-ops-copilot-requirements.md`](docs/brainstorms/aviation-ops-copilot-requirements.md)
- **Implementation plan**: [`docs/plans/2026-05-19-001-feat-aviation-ops-copilot-plan.md`](docs/plans/2026-05-19-001-feat-aviation-ops-copilot-plan.md)
- **Architecture deep-dive** (TBD in U12): `docs/architecture.md`
- **Eval methodology** (TBD in U12): `docs/eval_methodology.md`

## Repo layout

```
OpsCopilot/
├── backend/          # FastAPI + Pydantic-AI agent + tools (Python 3.12, managed with uv)
├── frontend/         # Next.js 14 + Tailwind chat UI (TypeScript, managed with npm)
├── data_pipeline/    # BTS flight data + FAA AIM ingestion scripts
├── evals/            # Question banks, scorers, Inspect AI runner
├── docs/             # Brainstorms, plans, architecture, eval methodology
├── .github/          # CI workflows (lands in U10)
└── infra/            # Modal + Vercel deploy configs (lands in U11)
```

## Local development setup

Tools you'll need:
- Python 3.12+ — managed via [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+ with `npm`
- Optionally `pnpm` (the plan prefers pnpm; on Windows without admin, this repo falls back to npm — see [`docs/deviations.md`](docs/deviations.md) when it exists)

```bash
# Backend
cd backend
uv sync
uv run pytest

# Frontend
cd frontend
npm install
npm run dev
```

## Status by Implementation Unit

| U# | Unit | Status |
|----|------|--------|
| U1 | Monorepo scaffolding | active |
| U2 | Flight data → DuckDB | pending |
| U3 | Corpus → LanceDB | pending |
| U4 | Agent orchestration | pending |
| U5 | 4 tool implementations | pending |
| U6 | FastAPI service | pending |
| U7 | Eval suite | pending |
| U8 | Observability | pending |
| U9 | Next.js chat UI | pending |
| U10 | CI/CD pipeline | pending |
| U11 | Production deploy | pending |
| U12 | README + docs polish | pending |

## License

MIT — see [LICENSE](LICENSE).
