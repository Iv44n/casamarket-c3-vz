# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this
repository's `backend/`.

## Project state

FastAPI server for Casa Market's Contact Center Cloud (C3, `casamarket.c3.pe`, Laravel/PHP) data
extraction. This backend was migrated from a standalone CLI project (`c3-data-extraccion`) into this
monorepo (`c3-panel`) so a frontend (`../frontend/`) could be added alongside it. `uv run uvicorn
app.main:app` is the **only** entry point -- there is no CLI (the original project's `main.py` +
`ui.py` terminal presentation layer were removed once the server could do everything they did) and
**no scheduler**: this server never decides when to run an extraction, it only exposes
`POST /extraction/refresh` and runs it when called. There was briefly an internal APScheduler daily
cron here (replacing the *external* cron the original CLI project relied on), but it was removed in
favor of the frontend driving refreshes on its own configurable interval (see
`frontend/CLAUDE.md` -- the auto-refresh provider) -- don't add a scheduler back here without
checking that decision first. Unit tests exist (`tests/`, pytest, no live network); no CI yet.

**Auth**: every endpoint except `POST /auth/login` requires `Authorization: Bearer <jwt>`
(`app/auth/`, wired onto `runs.router`/`data.router`/`benchmarks.router` via
`dependencies=[Depends(get_current_user)]` at each `APIRouter(...)` construction --
`app/auth/dependencies.py`). Individual accounts (`app/auth/store.py`'s `users` table in Turso,
bcrypt-hashed passwords, no open self-registration -- new accounts are admin-created via
`POST /auth/users`). The JWT is stateless (14-day expiry, no refresh-token flow, no server-side
session table) precisely because the browser never calls this API directly -- see the frontend
integration note below. CORS stays wide open (`allow_origins=["*"]`) on purpose: it was never a
real security boundary for a server that's only ever called server-to-server (CORS is a
browser-enforced mechanism, meaningless to a non-browser HTTP client), so narrowing it wouldn't add
protection -- the JWT check is what actually gates access now.

First account: set `AUTH_JWT_SECRET` (required for any endpoint to work -- generate with
`openssl rand -hex 32`) plus `AUTH_BOOTSTRAP_USERNAME`/`AUTH_BOOTSTRAP_PASSWORD` (optional) as env
vars. If both bootstrap vars are set and the `users` table is empty, `main.py`'s `lifespan` hook
seeds that one admin account at startup (`app/auth/store.py`'s `seed_bootstrap_admin()`) --
deliberately done in `lifespan`, not lazily on first `auth/store.get_connection()` like schema init
already is, so it can't race against the very first real login attempt. It's a no-op on every
later restart once at least one user exists. Further accounts are created via the now-authenticated
`POST /auth/users` (admin-only, `Depends(require_admin)`), not by re-running bootstrap.

Missing `AUTH_JWT_SECRET` doesn't crash the server (same fail-lazy philosophy as
`load_credentials()`/`load_turso_config()` below -- never validated eagerly at import time, only
when something actually calls `config.load_auth_config()`): a missing `Authorization` header still
401s (checked before config is even loaded), but a *present* header hits the `RuntimeError` and
surfaces as a 500 -- that's a server misconfiguration, not "your token is invalid," so it's
deliberately not caught into a 401.

**Frontend integration** (not implemented in this repo -- coordinate with `frontend/CLAUDE.md`):
the browser never calls this API directly, only the frontend's own server does
(`frontend/src/server/backend.server.ts`'s `backendFetch()`, the sole choke point for every backend
call). The plan is for the frontend to store the JWT returned by `POST /auth/login` in an HttpOnly
cookie on its own domain (no cross-site cookie issue, since the browser only ever talks to the
frontend) and forward it as `Authorization: Bearer <token>` on every backend call from that one
choke point.

## Tooling

Managed entirely by **uv**, lockfile `uv.lock`. Requires Python >= 3.14 (pinned in
`.python-version`). Do not use `pip` or edit `uv.lock` by hand.

```bash
uv sync                          # install/refresh the venv from uv.lock
uv add <pkg>                     # add a runtime dependency (updates pyproject.toml + uv.lock)
uv add --dev <pkg>                # add a dev-only dependency
uv run uvicorn app.main:app --reload   # run the server
uv run pytest                    # run the test suite
uv run pytest tests/c3/test_downloads.py::test_run_job_success_writes_file_and_reports_timing
```

Note `uv add` has no `--dry-run` flag in uv 0.12.x. No linter or formatter is configured.
`httpx2` is a dev-only dependency: `starlette.testclient.TestClient` (used by the router tests)
prefers it over plain `httpx` and warns if it's missing -- app code itself still uses `httpx`
directly (`session.login()`, `downloads.run_job()`), `httpx2` is not a runtime dependency.

Tests are pytest, under `tests/` at the repo root, mirroring `app/`'s package layout (see Layout
below), and never touch the live site -- HTTP-dependent tests use
`httpx.MockTransport` instead of real network calls (`session.login()` takes an optional
`transport=` param specifically so tests can inject one, and `service.run()` forwards it), and
router tests use FastAPI's `TestClient` with `state.run_extraction`/`last_run` monkeypatched so they
don't depend on real login/network either. `pyproject.toml` sets
`[tool.pytest.ini_options] pythonpath = ["."]` -- without it, `from app import config` fails under
pytest, because `tests/` has no `__init__.py` and pytest's default import mode only auto-adds a
directory to `sys.path` when it (or an ancestor) lacks `__init__.py`, which for a bare `tests/` means
`tests/` itself, not this repo root where `app/` lives.

## Setup

Copy `.env.example` to `.env` and fill in `C3_USERNAME` / `C3_PASSWORD` (`C3_BASE_URL` is optional,
defaults to `https://casamarket.c3.pe`), `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN`, and
`AUTH_JWT_SECRET` (generate with `openssl rand -hex 32`) -- see the Auth section above for what
that last one gates and how to seed the first account. `.env` is gitignored -- never commit real
credentials.

## Layout

Organized **by domain, not by technical layer**, so each direction this project is already known to
grow in (see `ANALYTICS_PLAN.md`) has one obvious place to land without disturbing the others:

```
app/
  main.py             entry point: FastAPI factory + lifespan + CORS + include_router (stays at
                       root -- this is what `uv run uvicorn app.main:app` targets)
  config.py           credentials/paths/timezone -- cross-cutting, everything below depends on it
  schemas.py          Pydantic response models -- cross-cutting, both c3/extraction and routers/
                       use these types (routers/ for responses, extraction/state.py to build them)

  auth/               identity/access control for this API itself -- distinct domain from c3/'s
                       "knowledge of the external C3 system" and extraction/'s "C3 report data".
                       Grows when auth gets MORE FEATURES (password reset, roles beyond the current
                       admin/non-admin bit) -- additive here, doesn't change what c3/, extraction/,
                       or routers/ know.
    store.py             `users` table + its own Turso get_connection() -- self-contained, mirrors
                          extraction/store.py's exact lazy-schema-init pattern rather than extending
                          that module (same physical Turso DB, unrelated domain/table)
    security.py           bcrypt hashing + JWT encode/decode, print-free like c3/ and extraction/
                           (returns values or raises, HTTP layer decides what to do)
    dependencies.py        get_current_user/require_admin -- the only Depends() in this codebase;
                            wired onto runs.router/data.router/benchmarks.router at APIRouter(...)
                            construction so no existing handler had to change

  c3/                 knowledge of + a client for Contact Center Cloud, the external system.
                       Grows when a NEW C3 REPORT TYPE is added (25+ are documented but not
                       implemented yet, see recon/rutas_reportes.md) -- new mechanism definitions
                       and download logic land here, nowhere else needs to change.
    session.py          login() -> authenticated httpx.Client; is_authenticated() probe
    reports.py           hardcoded knowledge of how each report's export works (3 mechanism families)
    downloads.py          builds each export request from reports.py + config, saves the file,
                           finds the latest saved file for a report name (latest_file())

  extraction/         orchestrating a full run and tracking its result. Grows when extraction gets
                       MORE STATEFUL (Fase 2 of ANALYTICS_PLAN.md: a persistent history/DB instead of
                       "just the latest file") -- that logic is additive here, it doesn't change what
                       c3/ or routers/ know.
    service.py           orchestrates a run -- `run_all()`/`run()` for the 5 daily downloads; named
                          service.py, not extraction.py, so it doesn't clash with the package name it
                          lives in
    parsing.py            parses a downloaded .xlsx into list[dict] for the /data endpoints
    state.py               in-memory last-run cache + a shared threading.Lock (concurrent refresh
                            calls -- manual, or the frontend's auto-refresh interval, possibly from
                            more than one browser tab -- never overlap)

  routers/            the HTTP surface. Grows when a NEW ENDPOINT is added -- one file per resource,
                       same shape FastAPI's own "Bigger Applications" tutorial recommends.
    runs.py             POST /extraction/refresh, GET /extraction/status (the 5 daily downloads) plus
                        POST /extraction/backfill, GET /extraction/backfill/status (re-fetch one past
                        day for the 4 dated families -- see "Backfilling a past day" below) -- named
                        runs.py (not extraction.py) to avoid clashing with the extraction/ package
                        above; the actual API prefix (`/extraction/...`) is unchanged
    data.py              GET /data/{report_name} -- parsed rows from the latest download, plus
                         GET /data/{report_name}/history -- every downloaded day's rows concatenated
    auth.py               POST /auth/login (public), GET /auth/me, POST /auth/users (admin-only) --
                          the only router NOT given `dependencies=[Depends(get_current_user)]` at
                          construction, since /login has to stay reachable without a token yet
```

`tests/` mirrors this exactly: `tests/c3/`, `tests/extraction/`, `tests/routers/`, `tests/auth/`,
plus `tests/test_config.py` at the root next to `test_config`'s subject (`config.py`, also at the
app root). No `__init__.py` needed in the test subdirectories -- pytest discovers `test_*.py` files
recursively regardless, and no two test files share a basename across directories, so there's no
ambiguity for its default import mode to resolve -- this is why `tests/auth/`'s store test is named
`test_auth_store.py`, not `test_store.py` (that basename is already taken by
`tests/extraction/test_store.py`).

`pyproject.toml` has **no `[build-system]`, no `[project.scripts]`, no `[tool.uv.build-backend]`**
-- this is a *virtual* uv project (`source = { virtual = "." }` in `uv.lock`): uv manages the venv
and dependencies but never builds or installs this code as a distribution. `app/` here is purely an
organizational choice, not packaging.

**Path gotcha**: `app/config.py` derives `PROJECT_ROOT` as `Path(__file__).resolve().parent.parent`
because `.env`, `recon/`, `downloads/`, and `state/` all live at this repo's root (`backend/`), one
level above `app/`. `RECON_DIR`/`DOWNLOADS_DIR`/`STATE_DIR` are computed from `PROJECT_ROOT`, not
from `Path(__file__).parent` -- if that ever changes back to `.parent`, output silently starts
landing inside `app/` instead. This holds regardless of how deep a module sits inside `app/` (e.g.
`c3/session.py` still does `from .. import config`, never duplicating this computation itself).

**Extraction logic stays print-free.** Everything under `c3/` and `extraction/` never calls
`print()` or `sys.exit()` -- it returns values or raises exceptions; the HTTP layer (`main.py`,
`routers/`, and `extraction/state.py` specifically, since it's the part of `extraction/` that talks
to the server rather than to C3) decides what to do with that. Where the HTTP layer needs to report
something outside a response, it uses the standard `logging` module, never `print()` -- there's no
terminal UI to write to anymore.

## Architecture

**Login** (`c3/session.py`): plain Laravel form POST, not a SPA. `GET /user/login` to scrape the
`_token` and pick up cookies, `POST /user/signin` with `{_token, username, password}`. A 200 from
that POST proves nothing -- Laravel re-renders the login form with 200 on wrong credentials too.
Session validity is always checked with `is_authenticated()`, which does a `GET` against a known
protected report path with `follow_redirects=False`: unauthenticated requests come back as a `302`
to `/user/login`; a real session doesn't. That redirect check is the only trustworthy signal.
`login()` builds its own `httpx.Client` internally but takes an optional `transport=` -- the one
seam that lets tests (and `extraction/service.py`'s `run()`) swap in `httpx.MockTransport` instead of
hitting the real site.

**Export mechanisms** (`c3/reports.py`): none of these report pages have a `<form>` -- filtering and
export are built by jQuery at runtime, so the mechanism isn't scrapable from the DOM. Each family was
reverse-engineered by reading that page's dedicated JS and is fixed as data in `reports.py`, not
rediscovered at runtime. Three families, each with its own shape -- **do not assume they're
symmetric**:

- **Atenciones** (`EXPORT_MECHANISMS`, messaging): `/user/report_message/attention` and
  `/user/report_message/outboundattention` share one endpoint,
  `GET /user/report_message/attentions-export`; only `type` (`INBOUND`/`OUTBOUND`) differs. Button
  variants read via `data-type`.
- **Llamadas** (`CALL_EXPORT_MECHANISMS`, `report/call/appincoming.js` / `appoutgoing.js`):
  `/user/report/callincoming` and `/user/report/calloutgoing` share
  `GET /user/report/calls/export`; the direction param is called `typeExport` (not `type`), and the
  button variant attribute is `data-with` (not `data-type`). **incoming and outgoing are not
  symmetric**: incoming sends `vip_only` and has no dialer fields; outgoing sends
  `manual_dialer_id`/`dialer_id` and has no `vip_only`. There's also a 4th button variant here,
  `SURVEY` ("Incluir encuestas"), that the messaging family doesn't have.
- **Contactos** (`CONTACTS_EXPORT_DEFAULT_PARAMS`, `contacts/app.js`): `GET /user/contacts/export`.
  No date range at all -- a contact isn't a dated event, this exports the whole roster as it stands
  today. Simplest of the three: no direction, no button-variant dropdown.

All three have a separate, unrelated **async** path too (a `-massive`/`calls/massive` endpoint -> a
job queued for later pickup, can take hours) -- **not implemented** for any of the three families
right now: this backend used to implement it for atenciones (`c3/massive.py`, a dedicated
"generar reporte masivo" cycle), but that feature was removed (2026-08-18) since it wasn't needed for
the moment -- see the git history if it needs to come back. `recon/rutas_reportes.md` maps 25+ other
C3 report routes that aren't implemented at all yet -- new ones belong in `c3/`, following this same
reverse-engineering approach (read the page's JS, don't guess).

Of each export's button variants, only **`FORM`** ("Incluir formulario") is in scope -- a deliberate,
user-confirmed narrowing, not a technical constraint. `selected_download_type` /
`selected_with` record that choice per family; don't start using another variant (`NONE`, `SURVEY`,
`MASSIVE`) without checking first. Contacts has no such variant to choose from.

**Downloads** (`c3/downloads.py`): every "no filter applied" param value was verified against each
page's actual default form state (empty selects, unchecked checkboxes, the first `<option>`), not
guessed -- see the comments next to each params dict for exactly which default was checked where.
For the two dated families (atenciones, llamadas), the date range is always the current day in
`America/Lima` (`config.hoy()`), formatted `YYYY-MM-DD HH:mm`, 00:00 to 23:59 -- the timezone fix
matters because the server responds in GMT and Peru is UTC-5, so a naive local-clock "today" can
drift by a day near midnight. **Deliberately kept single-day, not widened**: the frontend's
`/atenciones` day filter (`frontend/src/routes/atenciones.tsx`) needs data for days other than today,
but that's solved by *reading* multiple already-downloaded daily files together (`all_files()` below
+ `extraction/parsing.py`'s `parse_report_history()`), not by requesting a wider range from C3 in a
single file -- one file per day stays the on-disk shape. Saved filename prefers the server's
`Content-Disposition`; falls back to a content-type-derived extension.

Built in two steps, specifically so the caller can report exactly what's happening without
`downloads.py` printing anything itself:

- `build_jobs()` -- pure, no I/O. Returns a `list[DownloadJob]`, each one the "spec sheet" of a
  download (`name`, `endpoint`, `params`) *before* it's requested.
- `run_job(client, job)` -- does the actual GET, times it with `time.monotonic()`, sniffs for an
  HTML response (means login/server error, not the expected file), rejects empty bodies, writes to
  `config.DOWNLOADS_DIR`, and returns a `DownloadResult` carrying `status_code`, `size_bytes`,
  `content_type`, and `elapsed_seconds`. Passes `params=job.params or None`, not `params=job.params`
  bare -- a real httpx footgun confirmed live on 2026-08-13: `client.get(url, params={})`
  **replaces** the URL's existing query string, even with an empty dict, which would silently strip
  the signature off a presigned URL (e.g. one with `?X-Amz-Signature=...` already in it) and turn a
  valid signed request into an unsigned one (`403 Forbidden`). If a future job's `endpoint` is ever a
  pre-built URL with its own query string, this is why `params` can't just be `job.params`.
- `latest_file(name)` -- the most recently modified already-downloaded file for a report name (used
  by `extraction/parsing.py`, in turn used by `/data/{report_name}`). Matches
  `f"{name}_20??-??-??_*"`, not a bare `f"{name}_*"`: the latter would also match
  `attention_historical_2026-05-20_to_2026-08-18_*` (a wide-range historical backfill file, named
  after its date range, not a single day) when looking up `"attention"` -- both share the
  `attention_` prefix but are unrelated snapshots.
- `all_files(name)` -- every downloaded file for a report name, oldest first (same glob as
  `latest_file`, just not reduced to the single newest). Used by `parse_report_history()` below to
  reconstruct multi-day history from daily snapshots that already exist on disk, instead of widening
  what a single day's C3 request asks for.

**Extraction orchestration** (`extraction/service.py`): `run_all(client)` loops
`build_jobs()`/`run_job()` (a failed job doesn't abort the rest), returning an `ExtractionRun` (list
of `JobOutcome`). `run(creds=None, transport=None)` adds login + closing the client around
`run_all()` -- this is the entry point `extraction/state.py`'s `run_extraction()` calls on every
`POST /extraction/refresh`, whether that call came from a manual click or the frontend's
auto-refresh timer.

**Backfilling a past day** (`c3/downloads.py`, `extraction/service.py`/`state.py`,
`routers/runs.py`): the regular refresh only ever requests "today" from C3 (see the Downloads note
above), so if a day's file is missing/wrong, or the refresh simply didn't run that day -- there's no
way to get it back *except* asking C3 for that specific day again. `POST /extraction/backfill` (body:
`{"date": "YYYY-MM-DD"}`) does exactly that, for the 4 dated families only
(`downloads.build_backfill_jobs`) -- **not contacts**, whose export has no date range at all (see
`_contacts_job`), so a "backfill" of it would just save today's roster mislabeled as a past day,
which is wrong, not merely redundant. `DownloadJob` gained a `file_date` field for this: normally
`config.hoy()` (a regular refresh's file is still named after today, unchanged), but a backfill job
sets it to the requested past day so `run_job()` names the saved file after *that* day, not today --
otherwise `all_files()`/`parse_report_history()` would file the re-fetched data under the wrong day.
Same locking/single-flight discipline as the regular run (shares `extraction/state.py`'s one
`threading.Lock` -- a backfill can't run concurrently with it), its own summary type
(`BackfillRunSummary`, adds `target_date` to `RunSummary`'s shape) and its own last-run cache
(`_last_backfill_run`/`run_backfill()`/`last_backfill_run()`). Nothing calls this automatically --
it's a manual, one-day-at-a-time action from the frontend's `/status` page.

**Parsing** (`extraction/parsing.py`): `parse_xlsx(path)` concatenates **every sheet** in the
workbook into one `list[dict]`, using each sheet's own first row as its header. This matters because
the four atenciones/llamadas reports come back with **10 fixed sheets, one per campaign** (confirmed
in `ANALYTICS_PLAN.md` §6.1) -- reading only the first sheet silently drops ~90% of the rows.
`contacts.xlsx` happens to have one sheet, so it's unaffected either way. No date/duration/"-"
normalization happens here -- that's Fase 2 ingestion work per `ANALYTICS_PLAN.md`, out of scope for
now; this returns whatever value each cell holds. `parse_report(name)` is the `latest_file(name)` +
`parse_xlsx()` composition `GET /data/{report_name}` calls; returns `None` (not `[]`) when nothing has
been downloaded yet, so the router can tell "no data yet" (404) apart from "downloaded, but zero
rows" (200 with `[]`). `parse_report_history(name)` is the equivalent composition over
`all_files(name)`, concatenating every day's file oldest-first -- exposed as
`GET /data/{report_name}/history`, and what `frontend/src/routes/atenciones.tsx`'s per-day filter
reads from instead of the single-snapshot `/data/{report_name}` (see that route's frontend CLAUDE.md
for why: the dashboard needs more than just today, but the raw `/reports/$reportName` table still
only ever shows the latest snapshot, unchanged). No dedup across days: each day's export already
only covers that single day's `date_init`/`date_end` window, so consecutive files can't overlap.

**The server** (`main.py` / `extraction/state.py` / `routers/`) -- **no scheduler lives here**:

- `extraction/state.py` holds `_last_run` (a plain `RunSummary`, lost on restart -- it's a
  convenience cache for `GET /extraction/status`, not persistent state), plus a single
  `threading.Lock` shared by every run function (`run_extraction()`, `run_backfill()`, etc). The lock
  is real (not `asyncio.Lock`) because concurrent refresh calls genuinely happen on different threads
  via FastAPI's threadpool -- a manual click and the frontend's auto-refresh timer landing at the same
  moment, or two browser tabs each running their own timer -- and letting any two runs overlap could
  corrupt shared state (the same C3 session mechanism, or the downloaded files on disk). If the lock
  is already held, the run function raises `AlreadyRunningError` immediately rather than queuing (a
  normal run takes seconds, not worth making a caller wait).
- `routers/runs.py`: `POST /extraction/refresh` runs `state.run_extraction()` (the 5 daily
  downloads only) and maps `AlreadyRunningError` -> 409, any other `RuntimeError`/`httpx.HTTPError`
  (bad credentials, network failure during login) -> 502; `GET /extraction/status` returns the last
  known summary, or `NoRunsYet` if the server hasn't completed a run since it started. Nothing on
  this server decides *when* refresh runs -- that's entirely the caller's choice, currently the
  frontend's auto-refresh provider (`frontend/CLAUDE.md`) plus the manual button on `/status`.
- `routers/data.py`: `GET /data/{report_name}` validates the name against the 5 known tabular
  reports (`attention`, `outboundattention`, `callincoming`, `calloutgoing`, `contacts`), 404s on an
  unknown name or on no file downloaded yet, otherwise returns `parsing.parse_report(name)` as JSON.
  `GET /data/{report_name}/history` is the same validation over `parsing.parse_report_history(name)`
  instead -- every downloaded day's file for that report, concatenated (see that function's
  docstring for why no dedup is needed).

**Following FastAPI's own docs** (fastapi.tiangolo.com), deliberately, this project:

- Uses `-> ReturnType` return annotations (not `response_model=`) for `/extraction/*`, backed by
  Pydantic models in `schemas.py` (`JobSummary`, `RunSummary`, `NoRunsYet`) -- see "Bigger
  Applications" (routers with `prefix`/`tags` on the `APIRouter` itself) and "Response
  Model" tutorials. `/data/{report_name}` stays `list[dict]` on purpose: its columns come from each
  `.xlsx`'s real header row (see `extraction/parsing.py`) and vary by report, so a fixed schema would
  silently drop columns instead of validating anything real.
- Sets `FastAPI(title=..., description=..., version=..., openapi_tags=...)` in `main.py` per the
  "Metadata and Docs URLs" tutorial, with `openapi_tags` entries matching the `tags=["extraction"]`/
  `tags=["data"]` already on each `APIRouter`.
- CORS follows the "CORS (Cross-Origin Resource Sharing)" tutorial's `CORSMiddleware` shape exactly;
  `allow_credentials` is deliberately left at its default (`False`) specifically so `allow_origins=
  ["*"]` stays legal -- the tutorial calls out that `*` + `allow_credentials=True` together are
  invalid. That doesn't erase the security gap noted above, just confirms the CORS config itself
  isn't misconfigured relative to the docs.

Two things the docs recommend that this project **deliberately did not adopt**, so a future reader
doesn't "fix" them back in without knowing why:

- **FastAPI CLI** (`fastapi dev`/`fastapi run`, installed via `fastapi[standard]`): tried it, then
  reverted to plain `fastapi` + `uvicorn[standard]`. The `[standard]` extra also pulls in
  `fastapi-cli`, `fastapi-cloud-cli`, `sentry-sdk`, `jinja2`, `python-multipart`, and
  `email-validator` -- none used by this API (no HTML templates, no multipart file uploads, no
  email-typed fields, no interest in a hosted-cloud CLI or baked-in Sentry telemetry). That's a lot
  of unused surface area for a PII-serving internal tool with no auth yet; `uv run uvicorn
  app.main:app --reload` does everything this project needs without it.
- **`pydantic-settings` `BaseSettings`** (the "Settings and Environment Variables" tutorial's
  recommended config pattern): still not adopted, but the reasoning that used to be here is now
  outdated and worth correcting rather than leaving stale -- `config.py`'s `load_credentials()`
  originally read `.env` via `dotenv_values()` only and never fell back to the process's real
  environment variables, on purpose, to avoid a developer's shell having stale `C3_USERNAME`/
  `C3_PASSWORD` exports silently masking a missing/incomplete `.env`. That guarantee turned out to
  be the wrong tradeoff once this got deployed on Render (see "Docker (production, deployed on
  Render)" below): Render's normal dashboard "Environment Variables" only set process env vars, so
  under the old behavior they were silently ignored -- confirmed live on 2026-08-14 when they didn't
  take effect on container start. `load_credentials()` now merges `os.environ` on top of whatever
  `dotenv_values()` read from the file (`_CREDENTIAL_KEYS`, process env wins over the file for any
  key present in both -- mirrors `python-dotenv`'s own `load_dotenv()` default of not overriding
  already-set real env vars), so local dev keeps working off `.env` exactly as before while Render's
  plain env vars now work too, no Secret Files needed. Still not `pydantic-settings.BaseSettings`
  itself, though -- three fields with one small merge doesn't justify that dependency.

`recon/` holds artifacts from the discovery passes (raw HTML dumps, `hallazgos.md`,
`rutas_reportes.md` mapping every report-like menu route and whether it exposes an export button,
the fetched JS files) -- historical reference for how the mechanisms in `c3/reports.py` were derived,
not something regenerated automatically. `c3/reports.py` still has the discovery/inspection functions
(`inspect_report`/`inspect_all`) if a page's markup ever needs re-checking by hand. `ANALYTICS_PLAN.md`
is the analytics/dashboard plan this data is meant to eventually feed (Fase 1/2/3) -- read it before
adding new `/data` shapes, so new endpoints line up with that plan instead of drifting from it.

## Docker (production, deployed on Render)

`Dockerfile` (multi-stage: `builder` resolves the locked venv, `runtime` copies just that + `app/`
onto a clean base -- no compiler toolchain or uv binary ships) and `.dockerignore` at this
directory's root. Deployment target is Render's native Docker support (a Render service builds this
`Dockerfile` directly and runs the resulting container) -- **no `docker-compose.yml`**: one existed
briefly for local orchestration, but Render doesn't read compose files at all (it only builds the
Dockerfile and runs the image), so it was dead weight and got removed. Built and smoke-tested live
(`docker build` + `docker run` against the real image, confirmed `GET /extraction/status` responds,
the container reports `healthy`, and both the default port and
a Render-style overridden `$PORT` work with a clean `exec`-based SIGTERM shutdown) on 2026-08-14.

- **Base image**: `python:3.14-slim-bookworm` for both stages, with the standalone `uv`/`uvx`
  binaries copied in from `ghcr.io/astral-sh/uv:latest` (`COPY --from=ghcr.io/astral-sh/uv:latest
  /uv /uvx /bin/`) rather than one of uv's own combined `python3.X-...` images -- checked that
  image's tag list on 2026-08-14 and it only goes up to `python3.13-*`, no `3.14` tag yet, so it
  can't be used as this project's base (`.python-version` pins `3.14`). uv's binary itself doesn't
  care what Python version it's copied next to, so this is uv's own documented fallback pattern, not
  a workaround.
- **No README.md needed at build time**: `pyproject.toml` declares `readme = "README.md"` but no
  such file exists in this directory (a pre-existing gap, not something this Dockerfile work
  introduced) -- confirmed live that `uv sync` doesn't need it to exist, presumably because this is
  a virtual project with no `[build-system]` (see the "Layout" section above), so uv never actually
  builds a distribution that would need to package the readme's contents.
- **Non-root user**: runtime stage creates and switches to an unprivileged `app` user before
  `CMD`. This API serves parsed customer PII with no auth of its own yet (see the security note
  near the top of this file) -- least-privilege inside the container doesn't fix that gap, but it's
  still worth having regardless.
- **Listens on `$PORT`, not a hardcoded port**: Render (like most PaaS container hosts) injects its
  own `$PORT` at runtime and expects the process to bind to *that*, which won't necessarily be 8000
  -- `EXPOSE 8000`/`ENV PORT=8000` in the Dockerfile are just the local-`docker run` default. `CMD` is
  deliberately shell-form (`CMD exec uvicorn ... --port "$PORT"`), not a plain JSON-array `CMD`,
  specifically so `$PORT` gets expanded at container start rather than passed to uvicorn literally
  unexpanded (a JSON-array `CMD` never invokes a shell, so it can't do that substitution) -- and the
  leading `exec` matters just as much: without it, the shell itself stays PID 1 and swallows SIGTERM
  instead of forwarding it to uvicorn, which is exactly the "JSONArgsRecommended" warning `docker
  build` prints for this line (a generic, can't-tell-you-used-`exec` lint, not a real issue here --
  confirmed live with `docker top` that uvicorn itself is PID 1, and `docker stop` shuts it down
  cleanly in ~0.5s instead of hanging out to the SIGKILL timeout).
- **`downloads/` is declared a `VOLUME` in the Dockerfile, but that alone does NOT give persistence
  on Render** -- it's this app's only remaining local runtime write (the latest `.xlsx`/`.csv` per
  report, see the "Path gotcha" note above), and Render's filesystem is ephemeral by default: anything
  written there is gone on the next deploy or restart unless a Render **persistent Disk** is
  explicitly attached and mounted at `/app/downloads`. `VOLUME` here is honored by plain
  `docker run`/local Docker (an anonymous volume survives container recreation with the same image),
  but don't assume it does anything on Render without also configuring that Disk there. There's no
  `state/` directory/volume anymore -- the historical/contacts data that used to need local persistent
  state (`config.MASSIVE_STATE_FILE`, before the massive-report feature was removed) now lives in
  Turso (`app/extraction/store.py`), a remote database reached over the network with its own
  credentials (see below), not a local file needing a Disk.
- **Credentials: Render's normal "Environment Variables" dashboard section works** -- set
  `C3_USERNAME`/`C3_PASSWORD` (and optionally `C3_BASE_URL`) there like any other Render service, plus
  `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` for the historical-data store (`config.load_turso_config()`,
  same merge-order/fallback behavior as `load_credentials()` below -- without these two, anything that
  touches the store, e.g. the regular refresh's upsert step or the historical backfill, fails at that
  point rather than at startup), and `AUTH_JWT_SECRET` (plus optionally
  `AUTH_BOOTSTRAP_USERNAME`/`AUTH_BOOTSTRAP_PASSWORD` for the first deploy only -- see the Auth
  section) for `config.load_auth_config()`. This wasn't always true for the C3 pair: `config.py`'s
  `load_credentials()` used to read only a literal `.env` *file* and ignore process env vars entirely,
  which meant Render's plain env vars silently did nothing (confirmed live on 2026-08-14) and the only
  working option was Render's **Secret Files** feature pointed at `/app/.env`. `load_credentials()`
  was changed the same day to also read `os.environ` (see the "pydantic-settings" note above for the
  merge order) specifically so the ordinary env-var path works -- Secret Files still work too if
  preferred, but aren't required anymore.
- **Healthcheck hits `GET /health` with plain `urllib`** (no curl/wget installed in the
  image on purpose, keeps it minimal) -- deliberately public (no `Depends(get_current_user)`,
  unlike every other route except `/auth/login`), since a Docker/Render probe has no JWT to send.
  It replaces `GET /extraction/status`'s old role here: that route always returned 200 (a real
  summary, or `{"status": "no_runs_yet"}` before the first run) with no side effects, so it's a safe, cheap
  target even on a freshly started container that hasn't extracted anything yet. Reads `$PORT` too,
  same reasoning as `CMD`.
- **Exactly one process, always** -- no `--reload` (dev-only) and deliberately no
  `--workers`/multiple replicas either. `extraction/state.py`'s last-run caches, the refresh
  `threading.Lock`, and the historical backfill's background-thread status (`_historical_backfill_
  status`, polled by the frontend while it runs) are all plain in-memory process state (see "The
  server" above); a second worker process or container replica would get its own independent copy of
  all three, so two refreshes could overlap (the exact corruption the lock exists to prevent),
  `GET /extraction/status` could answer from whichever instance happened to handle that particular
  request, and a historical backfill started on one worker would look stuck at `"idle"`/never progress
  if the next status poll happens to land on a different worker. Don't scale this service horizontally
  (Render's autoscaling / multiple instances included) without moving that state somewhere shared
  (Redis, a DB row) first.
- **Auth is required, CORS stays wide-open** (see the Auth section near the top of this file) --
  every route except `/auth/login` and `/health` needs a valid JWT. Set `AUTH_JWT_SECRET` (and
  optionally `AUTH_BOOTSTRAP_USERNAME`/`AUTH_BOOTSTRAP_PASSWORD` for the very first account) in
  Render's Environment Variables alongside `C3_USERNAME`/`TURSO_*` -- without `AUTH_JWT_SECRET`,
  every protected route 500s (fail-lazy, not a startup crash -- see the Auth section).
