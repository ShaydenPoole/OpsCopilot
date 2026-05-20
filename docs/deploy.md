# Deployment runbook

How to deploy Aviation Ops Copilot, wire up its secrets, and operate it.

## Topology

| Piece | Host | Source of truth |
|-------|------|-----------------|
| Agent API (FastAPI) | Modal — `backend/modal_app.py` | `modal deploy` |
| Data (DuckDB, LanceDB, model weights) | Modal Volume `aviation-copilot-data` | `modal volume put` |
| Frontend (Next.js) | Vercel — `frontend/` | `vercel deploy` or Git integration |
| Observability | Langfuse Cloud | runtime traces |
| LLM inference | OpenRouter | runtime API calls |

The frontend never calls Modal directly: the browser hits the same-origin
`/api/proxy` route, which forwards to Modal. The Modal URL stays server-side.

## Prerequisites

Free-tier accounts: [Modal](https://modal.com), [Vercel](https://vercel.com),
[OpenRouter](https://openrouter.ai) (pay-as-you-go, a few dollars),
[Langfuse Cloud](https://langfuse.com).

Install the CLIs locally:

```bash
cd backend && uv sync --all-extras   # provides the `modal` CLI
modal token new                      # authenticate the Modal CLI
npm i -g vercel                      # optional — only for CLI deploys
```

## First-time setup

### 1. Build the data artifacts

```bash
cd backend
uv run python ../data_pipeline/download_bts_otp.py
uv run python ../data_pipeline/build_flight_duckdb.py
uv run python ../data_pipeline/download_faa_aim.py
uv run python ../data_pipeline/build_corpus_index.py
uv run python ../data_pipeline/hydrate_volume.py --local   # verify artifacts
```

This produces `data/flights.duckdb`, `data/corpus_index.lance/`, and the
`*_version.json` manifests.

### 2. Hydrate the Modal Volume

The volume holds the data the API reads at runtime. Upload the built
artifacts (run from the repo root):

```bash
modal volume create aviation-copilot-data        # no-op if it already exists
modal volume put aviation-copilot-data data/flights.duckdb        /flights.duckdb
modal volume put aviation-copilot-data data/corpus_index.lance    /corpus_index.lance
modal volume put aviation-copilot-data data/data_version.json     /data_version.json
modal volume put aviation-copilot-data data/corpus_version.json   /corpus_version.json
```

The embedding-model weights are cached to the volume under `hf-cache/`
automatically on the first request after a deploy.

### 3. Create the Modal secret

```bash
modal secret create aviation-copilot-secrets \
  OPENROUTER_API_KEY=sk-or-... \
  LANGFUSE_PUBLIC_KEY=pk-lf-... \
  LANGFUSE_SECRET_KEY=sk-lf-...
# FAA_NOTAM_API_KEY is optional — the NOTAM tool falls back to aviationweather.gov.
```

### 4. Deploy the backend

```bash
cd backend
uv run --extra deploy modal deploy modal_app.py
```

Modal prints the public URL (e.g. `https://<workspace>--aviation-ops-copilot-serve.modal.run`).
Verify: `curl <url>/healthz` → `{"status":"ok",...}`.

### 5. Deploy the frontend

Create a Vercel project with **root directory `frontend/`** and set one
environment variable:

| Variable | Value |
|----------|-------|
| `BACKEND_URL` | the Modal URL from step 4 |
| `NEXT_PUBLIC_LANGFUSE_URL` | (optional) public Langfuse project URL — shows a "Traces" header link |

Then either connect the repo (Vercel auto-deploys on push to `main`) or
deploy from the CLI:

```bash
cd frontend
vercel --prod
```

## CI secrets and variables

Set these under **GitHub repo → Settings → Secrets and variables → Actions**.
Every one is optional — the workflow step that needs it skips gracefully (with
a notice) when it is absent, so CI is never red just for missing config.

### Secrets

| Secret | Used by | Purpose |
|--------|---------|---------|
| `OPENROUTER_API_KEY` | eval-smoke, eval-full | run the agent during evals |
| `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | eval-* (optional) | trace eval runs |
| `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET` | backend-ci deploy | `modal deploy` on push to main |
| `VERCEL_TOKEN` / `VERCEL_ORG_ID` / `VERCEL_PROJECT_ID` | frontend-ci deploy | `vercel deploy` on push to main |

Leave the Vercel secrets unset if you use Vercel's Git integration instead of
the CI deploy step.

### Variables

| Variable | Used by | Purpose |
|----------|---------|---------|
| `EVAL_DATA_URL` | eval-smoke, eval-full | URL of a prebuilt data tarball (see below) |
| `EVAL_RUN_COST_ESTIMATE` | eval-full | $ added to `evals/budget.json` per run (default `0.50`) |
| `DEMO_BACKEND_URL` | healthcheck | the Modal URL — enables the warm-pinger |

### Publishing the eval-data tarball

CI cannot rebuild the multi-GB BTS dataset per run, so data-backed eval
questions need a prebuilt tarball:

```bash
tar -czf eval-data.tar.gz -C data \
  flights.duckdb corpus_index.lance data_version.json corpus_version.json
```

Upload it somewhere public (a GitHub release asset, Cloudflare R2, or a
HuggingFace dataset) and set `EVAL_DATA_URL` to the direct download URL. When
unset, weather / NOTAM / refusal / security questions still run; flight- and
corpus-backed questions degrade gracefully (the agent reports the data as
unavailable, per R3).

## Routine operations

| Task | Command |
|------|---------|
| Redeploy the backend | `cd backend && uv run --extra deploy modal deploy modal_app.py` (or push to `main`) |
| Refresh the data | rebuild artifacts (setup step 1), then re-run `modal volume put` (step 2) |
| View backend logs | `modal app logs aviation-ops-copilot` |
| View traces | the Langfuse Cloud dashboard |
| Rotate a key | update the Modal secret (`modal secret create ... --force`) and the GitHub secret, then redeploy |
| Watch eval spend | `evals/budget.json` (CI-managed) and the OpenRouter dashboard (source of truth) |

There is no cassette re-recording step: the integration-test "cassettes" are
scripted `FunctionModel` conversations in `backend/tests/integration/`, not
recorded HTTP — see that directory's `README.md`.

## Cold starts and the warm pinger

The Modal container scales to zero when idle. The first request after an idle
period pays a cold start (~5–8s: image start + volume mount + model load). The
`healthcheck` GitHub Actions workflow pings `/healthz` every 5 minutes during
demo hours (09:00–22:00 UTC, weekdays) to keep one container warm, so most
visitor first-requests are effectively warm. Set the `DEMO_BACKEND_URL`
variable to enable it. The frontend shows a "warming up" affordance for slow
first responses so an off-hours cold start does not read as a bug.

## Cost

Steady state (demo traffic only) is well under $5/month: Modal, Vercel, and
Langfuse stay on free tiers; OpenRouter is the only metered cost. The
`evals/budget.json` cap (default $20/month) bounds CI eval spend — `eval-full`
records an estimated spend per run and the budget guard blocks further runs
once the cap is reached.
