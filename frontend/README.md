# Aviation Ops Copilot — Frontend

Next.js 15 (App Router) + TypeScript + Tailwind. Chat surface for the agent API.

## Setup

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000
```

> **Tooling note:** the implementation plan targets `pnpm`. On Windows without admin privileges, Corepack-managed `pnpm` cannot be activated globally, so this repo currently uses `npm`. Both work with the `package.json` as written; future contributors with `pnpm` available can use `pnpm install` / `pnpm run dev` interchangeably. The CI workflow (U10) uses whichever is available in the runner image.

## Commands

| Command | Purpose |
|---------|---------|
| `npm run dev` | start dev server (HMR) |
| `npm run build` | production build |
| `npm run start` | start production server |
| `npm run lint` | eslint |
| `npm run type-check` | tsc --noEmit |
| `npm run format` | prettier write |
| `npm test` | run Vitest unit/component tests |
| `npm run test:e2e` | run Playwright E2E (needs `test:e2e:install` once) |

## Layout

```
frontend/
├── app/                  # Next.js App Router (lands in U9)
├── components/           # Chat UI, trace inspector, sample questions (U9)
├── lib/                  # API client, types, SSE consumer (U9)
├── tests/
│   ├── components/       # Vitest + Testing Library
│   ├── e2e/              # Playwright
│   └── setup.ts
├── public/               # Static assets
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── next.config.js
└── playwright.config.ts
```

Backend API base URL is read from `BACKEND_URL` env var (defaults to `http://localhost:8000` for local dev). The production frontend hides the real backend behind `/api/proxy` (the edge route lands in U9).
