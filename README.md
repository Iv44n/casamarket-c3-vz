# c3-panel

Casa Market's C3 (Contact Center Cloud) data platform: a FastAPI backend and a TanStack Start
frontend for browsing daily reports and the extraction run status.

## Layout

- `backend/` -- FastAPI server + daily scheduler that logs into `casamarket.c3.pe`, downloads the
  day's reports (WhatsApp attentions, calls, contacts), advances the async "massive report" cycle,
  and serves the parsed data over HTTP. See `backend/CLAUDE.md` for the full architecture. Migrated
  from the standalone `c3-data-extraccion` CLI project (there's no separate CLI anymore -- the
  server replaced it); organized by domain under `app/` (`c3/` talks to Contact Center Cloud,
  `extraction/` orchestrates+schedules+tracks runs, `routers/` is the HTTP surface).
- `frontend/` -- TanStack Start app (React, bun, Biome) consuming `backend`'s `/data/*` and
  `/extraction/*` endpoints: browse reports, check/trigger the extraction run. See
  `frontend/CLAUDE.md` for the full architecture (SSR strategy, server-only boundaries, deployment
  target). Covers `ANALYTICS_PLAN.md`'s Fase 1 (single-day snapshot) -- Fase 2 (historical
  accumulation) isn't built yet.

## Getting started

```bash
cd backend
cp .env.example .env   # fill in C3_USERNAME / C3_PASSWORD
uv sync
uv run uvicorn app.main:app --reload   # http://127.0.0.1:8000
```

```bash
cd frontend
cp .env.example .env   # C3_API_URL, defaults to the backend's port above
bun install
bun run dev             # http://localhost:3000 -- requires the backend running
```

**No authentication anywhere in this stack yet** -- see the security note at the top of
`backend/CLAUDE.md` before running this anywhere reachable beyond your own machine. The frontend has
no login of its own and inherits this gap.
