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

**Security gap, read before deploying beyond localhost**: there is currently **no authentication on
this API**. `POST /extraction/refresh` and `GET /data/{report_name}` (which serves parsed customer
PII -- contacts, WhatsApp attentions, calls) are open to anyone who can reach the port. CORS is
wide open (`allow_origins=["*"]`) to make local frontend development frictionless. Add auth (and
narrow CORS) before this server is reachable from anywhere but a trusted local/internal network.

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
defaults to `https://casamarket.c3.pe`). `.env` is gitignored -- never commit real credentials.

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

  c3/                 knowledge of + a client for Contact Center Cloud, the external system.
                       Grows when a NEW C3 REPORT TYPE is added (25+ are documented but not
                       implemented yet, see recon/rutas_reportes.md) -- new mechanism definitions
                       and download logic land here, nowhere else needs to change.
    session.py          login() -> authenticated httpx.Client; is_authenticated() probe
    reports.py           hardcoded knowledge of how each report's export works (3 mechanism families)
    downloads.py          builds each export request from reports.py + config, saves the file,
                           finds the latest saved file for a report name (latest_file())
    massive.py             async "generar reporte masivo" cycle for WhatsApp attentions (see below)

  extraction/         orchestrating a full run and tracking its result. Grows when extraction gets
                       MORE STATEFUL (Fase 2 of ANALYTICS_PLAN.md: a persistent history/DB instead of
                       "just the latest file") -- that logic is additive here, it doesn't change what
                       c3/ or routers/ know.
    service.py           orchestrates a run -- `run_all()`/`run()` for the 5 daily downloads,
                          `run_massive_cycle()`/`run_massive()` for one massive-cycle step, kept
                          deliberately SEPARATE (see "Massive export is a dedicated route" below);
                          named service.py, not extraction.py, so it doesn't clash with the package
                          name it lives in
    parsing.py            parses a downloaded .xlsx into list[dict] for the /data endpoints
    state.py               in-memory last-run caches (one for downloads, one for the massive cycle)
                            + a shared threading.Lock (concurrent refresh calls -- manual, or the
                            frontend's auto-refresh interval, possibly from more than one browser
                            tab -- never overlap)

  routers/            the HTTP surface. Grows when a NEW ENDPOINT is added -- one file per resource,
                       same shape FastAPI's own "Bigger Applications" tutorial recommends.
    runs.py             POST /extraction/refresh, GET /extraction/status (the 5 daily downloads) plus
                        POST /extraction/massive/refresh, GET /extraction/massive/status (the
                        dedicated massive-cycle pair) -- named runs.py (not extraction.py) to avoid
                        clashing with the extraction/ package above; the actual API prefix
                        (`/extraction/...`) is unchanged
    data.py              GET /data/{report_name} -- parsed rows from the latest download
```

`tests/` mirrors this exactly: `tests/c3/`, `tests/extraction/`, `tests/routers/`, plus
`tests/test_config.py` at the root next to `test_config`'s subject (`config.py`, also at the app
root). No `__init__.py` needed in the test subdirectories -- pytest discovers `test_*.py` files
recursively regardless, and no two test files share a basename across directories, so there's no
ambiguity for its default import mode to resolve.

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
job queued for later pickup, can take hours). For calls and contacts it's still **not implemented**
-- only the synchronous direct-download path is. For atenciones, the async path *is* implemented --
see **Async massive export** below. `recon/rutas_reportes.md` maps 25+ other C3 report routes that
aren't implemented at all yet -- new ones belong in `c3/`, following this same reverse-engineering
approach (read the page's JS, don't guess).

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
  `content_type`, and `elapsed_seconds`.
- `latest_file(name)` -- the most recently modified already-downloaded file for a report name (used
  by `extraction/parsing.py`, in turn used by `/data/{report_name}`). Matches
  `f"{name}_20??-??-??_*"`, not a bare `f"{name}_*"`: the latter would also match
  `attention_masivo_*` (the async zip from `massive.py`) when looking up `"attention"` -- both share
  the `attention_` prefix but are unrelated reports.
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

**Massive export is a dedicated route, not part of the regular refresh.** `run_all()`/`run()` used
to also advance one step of `massive.run_cycle(client)` at the end -- meaning every automatic
refresh (by default every few minutes, see `frontend/CLAUDE.md`'s auto-refresh provider) would queue
or advance an hours-long async job on the live `casamarket.c3.pe` site, with nobody having asked for
it that specific time. That's backwards from what a scheduled, frequent refresh should do, so the
massive step was split out into its own function (`run_massive_cycle(client)`/`run_massive(creds=
None, transport=None)`, same shape as `run_all()`/`run()`) and its own HTTP pair,
`POST /extraction/massive/refresh` / `GET /extraction/massive/status` (`routers/runs.py`), tracked in
its own `extraction/state.py` cache (`_last_massive_run`/`run_massive_extraction()`/
`last_massive_run()`) separate from the regular run's. Nothing calls the massive pair
automatically -- today the only caller is a manual button on the frontend's `/status` page
(`frontend/src/routes/status.tsx`'s `MassiveRefreshCard`). If a future need calls for the massive
cycle to advance on its own cadence again, that belongs on its own separate (and much longer)
interval, not bundled back into the regular refresh.

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

**Async massive export** (`c3/massive.py`): "Generar reporte masivo" for attention/outboundattention
is encolar-y-recoger-despues, not request-and-save. `GET .../attentions-massive` (same params as the
FORM job but `with_form=0`) queues a job; the system's own UI warns it "puede demorar incluso varias
horas". `GET /user/report_general/get_massives` lists all massive jobs (any report family, not just
these two) -- **it needs `Accept: application/json`**, since it's a Vue/SPA route that otherwise
serves the page's HTML instead of JSON.

The hard constraint driving this module's design: **a `get_massives` record has no field
distinguishing `attention` (INBOUND) from `outboundattention` (OUTBOUND)** -- only `channel:
"WHATSAPP"` for both. Neither exposes the original filter/direction. The only correct way to
handle both directions is to never have more than one in flight and remember which one ourselves --
hence `config.MASSIVE_STATE_FILE` (`state/massive_attentions.json`), **the one piece of persistent
state the extraction logic owns**; everything else in `config.py`/`c3/session.py`/`c3/downloads.py`
is stateless by design (`extraction/state.py`'s in-memory last-run cache is a separate, server-only,
restart-losable thing -- don't confuse the two, despite the similar names).

`run_cycle(client)` advances exactly one step per call:

- no state file -> trigger `attention` (starts the cycle)
- tracked job still `PENDING`/`PROCESSING` -> do nothing, report it's still going
- tracked job `COMPLETED` -> download it (reusing `downloads.run_job`), clear the state, and
  trigger the *other* direction -- this is where the alternation happens
- tracked job `FAILED` (or vanished from the listing entirely -- e.g. expired) -> clear the state
  and retrigger the **same** direction, so a transient failure doesn't silently skip it forever

`describe(cycle)` turns a `CycleResult` into a sentence -- used by `extraction/state.py`'s run
summary.

**Gotcha confirmed live on 2026-08-13**: once `COMPLETED`, `download_url` isn't on `casamarket.c3.pe`
at all -- it's a presigned S3 URL (`sfo3.digitaloceanspaces.com`) with the signature *in the query
string*. `downloads.run_job` downloads it by reusing the same `DownloadJob`/`run_job` machinery with
`params={}`. That surfaced a real httpx footgun: `client.get(url, params={})` **replaces** the URL's
existing query string, even with an empty dict -- silently stripping the signature and turning a
valid presigned request into an unsigned one (`403 Forbidden`). Fixed in `run_job` by passing
`params=job.params or None`. If `run_job` ever grows another caller with a pre-built URL, remember
this.

**The server** (`main.py` / `extraction/state.py` / `routers/`) -- **no scheduler lives here**:

- `extraction/state.py` holds `_last_run` (a plain `RunSummary`, lost on restart -- it's a
  convenience cache for `GET /extraction/status`, not persistent state) and `_last_massive_run` (a
  `MassiveRunSummary`, same deal for `GET /extraction/massive/status`), plus a single `threading.Lock`
  shared by `run_extraction()` and `run_massive_extraction()`. The lock is real (not `asyncio.Lock`)
  because concurrent refresh calls genuinely happen on different threads via FastAPI's threadpool --
  a manual click and the frontend's auto-refresh timer landing at the same moment, or two browser
  tabs each running their own timer -- and both downloads and the massive cycle log into the same
  C3 session mechanism and touch `config.MASSIVE_STATE_FILE`, so letting any two runs overlap
  (regular/regular, regular/massive, or massive/massive) could corrupt that shared state. If the lock
  is already held, either function raises `AlreadyRunningError` immediately rather than queuing (a
  normal run takes seconds, not worth making a caller wait).
- `routers/runs.py`: `POST /extraction/refresh` runs `state.run_extraction()` (the 5 daily
  downloads only) and maps `AlreadyRunningError` -> 409, any other `RuntimeError`/`httpx.HTTPError`
  (bad credentials, network failure during login) -> 502; `GET /extraction/status` returns the last
  known summary, or `NoRunsYet` if the server hasn't completed a run since it started. Nothing on
  this server decides *when* refresh runs -- that's entirely the caller's choice, currently the
  frontend's auto-refresh provider (`frontend/CLAUDE.md`) plus the manual button on `/status`.
  `POST /extraction/massive/refresh` / `GET /extraction/massive/status` are the separate, dedicated
  pair for the massive cycle (see "Massive export is a dedicated route" above) -- same error mapping,
  own summary type (`MassiveRunSummary`), own cache, and (unlike the pair above) no automatic caller
  at all today.
- `routers/data.py`: `GET /data/{report_name}` validates the name against the 5 known tabular
  reports (`attention`, `outboundattention`, `callincoming`, `calloutgoing`, `contacts` -- not the
  massive zip, which isn't tabular), 404s on an unknown name or on no file downloaded yet, otherwise
  returns `parsing.parse_report(name)` as JSON.

**Following FastAPI's own docs** (fastapi.tiangolo.com), deliberately, this project:

- Uses `-> ReturnType` return annotations (not `response_model=`) for `/extraction/*`, backed by
  Pydantic models in `schemas.py` (`JobSummary`, `RunSummary`, `MassiveRunSummary`, `NoRunsYet`) --
  see "Bigger Applications" (routers with `prefix`/`tags` on the `APIRouter` itself) and "Response
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
(`docker build` + `docker run` against the real image, confirmed `GET /extraction/status`/`GET
/extraction/massive/status` respond, the container reports `healthy`, and both the default port and
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
- **`downloads/`/`state/` are declared `VOLUME`s in the Dockerfile, but that alone does NOT give
  persistence on Render** -- they're this app's only runtime writes (the latest `.xlsx` per report,
  and `state/massive_attentions.json`, see the "Path gotcha" and "Async massive export" notes above),
  and Render's filesystem is ephemeral by default: anything written there is gone on the next deploy
  or restart unless a Render **persistent Disk** is explicitly attached and mounted at `/app/downloads`
  and `/app/state`. `VOLUME` here is honored by plain `docker run`/local Docker (an anonymous volume
  survives container recreation with the same image), but don't assume it does anything on Render
  without also configuring that Disk there.
- **Credentials: Render's normal "Environment Variables" dashboard section works** -- set
  `C3_USERNAME`/`C3_PASSWORD` (and optionally `C3_BASE_URL`) there like any other Render service.
  This wasn't always true: `config.py`'s `load_credentials()` used to read only a literal `.env`
  *file* and ignore process env vars entirely, which meant Render's plain env vars silently did
  nothing (confirmed live on 2026-08-14) and the only working option was Render's **Secret Files**
  feature pointed at `/app/.env`. `load_credentials()` was changed the same day to also read
  `os.environ` (see the "pydantic-settings" note above for the merge order) specifically so the
  ordinary env-var path works -- Secret Files still work too if preferred, but aren't required
  anymore.
- **Healthcheck hits `GET /extraction/status` with plain `urllib`** (no curl/wget installed in the
  image on purpose, keeps it minimal) -- that route always returns 200 (a real summary, or
  `{"status": "no_runs_yet"}` before the first run) with no side effects, so it's a safe, cheap
  target even on a freshly started container that hasn't extracted anything yet. Reads `$PORT` too,
  same reasoning as `CMD`.
- **Exactly one process, always** -- no `--reload` (dev-only) and deliberately no
  `--workers`/multiple replicas either. `extraction/state.py`'s last-run caches and the refresh
  `threading.Lock` are plain in-memory process state (see "The server" above); a second worker
  process or container replica would get its own independent copy of both, so two refreshes could
  overlap (the exact corruption the lock exists to prevent) and `GET /extraction/status` could
  answer from whichever instance happened to handle that particular request. Don't scale this
  service horizontally (Render's autoscaling / multiple instances included) without moving that state
  somewhere shared (Redis, a DB row) first.
- **Still no auth, still wide-open CORS** (see the security note near the top of this file) -- this
  Docker work doesn't change that, and deploying to a public Render URL makes it reachable from the
  entire internet instead of just a local/internal network. Put a reverse proxy + auth layer in front
  (or otherwise restrict who can reach it) before/soon after this goes live on Render.
