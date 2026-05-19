# Infrastructure

Deploy configurations for Modal (backend) and Vercel (frontend). Lands in U11.

## Layout (after U11 lands)

```
infra/
├── modal_app.py          # symlink or proxy to backend/modal_app.py — the Modal ASGI entry
└── vercel.json           # Vercel project config (env vars, edge functions, headers)
```

Modal handles: FastAPI service, Modal Volume (`aviation-copilot-data`), Modal Secrets (OpenRouter, Langfuse, optional FAA NOTAM), scheduled healthcheck warm-pinger.

Vercel handles: Next.js production deploy, `/api/proxy` edge route, env vars (`BACKEND_URL` pointing to the Modal endpoint).

See `docs/deploy.md` (lands with U11) for the deployment runbook.
