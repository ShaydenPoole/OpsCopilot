"""Modal deployment for the Aviation Ops Copilot agent service.

The FastAPI app (:func:`aviation_copilot.api.app.create_app`) is served as a
Modal ASGI app. Data artifacts — the flight DuckDB, the corpus LanceDB index,
and the cached embedding-model weights — live on a **Modal Volume** mounted at
``/data``, not baked into the image. That keeps the image thin (fast cold
start) and lets data refresh independently of code deploys.

Deploy::

    cd backend
    uv run --extra deploy modal deploy modal_app.py

Before the first deploy, create the secret and hydrate the volume — see
``docs/deploy.md``. The container scales to zero when idle; the
``healthcheck`` GitHub Actions workflow keeps one warm during demo hours so
the demo costs nothing at rest.
"""

from __future__ import annotations

from pathlib import Path

import modal

APP_NAME = "aviation-ops-copilot"
VOLUME_NAME = "aviation-copilot-data"
SECRET_NAME = "aviation-copilot-secrets"  # noqa: S105 — a Modal secret's name, not a credential
DATA_MOUNT = "/data"

_BACKEND_ROOT = Path(__file__).resolve().parent

app = modal.App(APP_NAME)

# Persistent volume holding flights.duckdb, corpus_index.lance/, the version
# manifests, and the cached sentence-transformers weights (under hf-cache/).
# Hydrated once via `modal volume put` — see docs/deploy.md.
data_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)

# Thin image: runtime Python deps only (read from [project.dependencies] in
# pyproject.toml, so it never drifts from local dev). The aviation_copilot
# package source is added from the local checkout; data stays on the volume.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_pyproject(str(_BACKEND_ROOT / "pyproject.toml"))
    .add_local_python_source("aviation_copilot")
    .env(
        {
            # Point Settings at the volume mount instead of the local repo.
            "FLIGHT_DUCKDB_PATH": f"{DATA_MOUNT}/flights.duckdb",
            "CORPUS_LANCE_PATH": f"{DATA_MOUNT}/corpus_index.lance",
            # Cache embedding-model weights on the volume so they load once and
            # are reused across cold starts rather than re-downloaded.
            "HF_HOME": f"{DATA_MOUNT}/hf-cache",
            "SENTENCE_TRANSFORMERS_HOME": f"{DATA_MOUNT}/hf-cache",
        }
    )
)

# Bundles OPENROUTER_API_KEY, LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, and
# (optionally) FAA_NOTAM_API_KEY. Create it with:
#   modal secret create aviation-copilot-secrets OPENROUTER_API_KEY=... ...
runtime_secret = modal.Secret.from_name(SECRET_NAME)


@app.function(
    image=image,
    volumes={DATA_MOUNT: data_volume},
    secrets=[runtime_secret],
    timeout=120,
    # min_containers stays at the default 0 (scale to zero). The
    # healthcheck workflow pings /healthz on a schedule to keep one container
    # warm during demo hours — see .github/workflows/healthcheck.yml.
)
@modal.asgi_app()
def serve() -> object:
    """Entry point Modal serves. Builds the FastAPI app inside the container."""
    from aviation_copilot.api.app import create_app

    return create_app()
