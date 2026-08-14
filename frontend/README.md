# c3-panel frontend

TanStack Start app that consumes the `../backend` FastAPI service: browse C3's daily reports
(WhatsApp attentions, calls, contacts) and check/trigger the extraction run. UI is shadcn (Base UI
primitives, "maia" preset, matching `../../RCTM_WEB`'s setup) with a red/rose theme. See `CLAUDE.md`
for the full architecture (SSR strategy, server-only boundaries, deployment target, shadcn setup).

## Setup

```bash
cp .env.example .env   # C3_API_URL, defaults to http://127.0.0.1:8000 (the backend's default port)
bun install
bun run dev             # http://localhost:3000 -- requires ../backend running
```

## Scripts

```bash
bun run dev             # dev server, port 3000
bun run typecheck       # tsc --noEmit
bun run check           # biome check (lint + format)
bun run build           # production build (client + SSR + Nitro server bundle)
bun run start           # run the built server (bun, matches the Nitro `bun` preset)
```

## Routes

- `/` -- links to the two sections below.
- `/reports` -- the 5 known report names.
- `/reports/$reportName` -- a report's rows (client-rendered, paginated via validated `page`/
  `pageSize` search params), with a column-population summary streamed in after the table.
- `/status` -- the backend's last extraction run, with a button to trigger a refresh.

**Read-only by default**: browsing reports/status only reads already-downloaded data or the
backend's own state. The one exception is `/status`'s "Refresh ahora" button, which triggers a real
login + download cycle against the live C3 system (`casamarket.c3.pe`) via the backend -- don't click
it just to poke around.
