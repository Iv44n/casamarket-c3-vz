# syntax=docker/dockerfile:1

# Production image for the c3-panel backend (FastAPI, uv-managed, Python 3.14
# per .python-version). Multi-stage: `builder` resolves the locked venv from
# uv.lock, `runtime` copies just that venv + app code onto a clean base --
# no compiler toolchain, no uv binary, no source-controlled dev files ship in
# the final image.
#
# There is no "python3.14" tag of ghcr.io/astral-sh/uv (checked its tag list
# on 2026-08-14 -- it stops at 3.13), so this doesn't use that combined
# image. Instead it follows uv's other documented pattern: a plain official
# Python image + copying the standalone `uv`/`uvx` binaries out of the uv
# image (uv itself doesn't care what Python version it's copied next to).

FROM python:3.14-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first, in their own layer keyed only on the lockfile/manifest
# -- app code changes (the common case) don't invalidate this and force a
# re-resolve/re-download. `--no-install-project` on purpose: the project
# itself has no [build-system] (see CLAUDE.md -- it's a virtual uv project,
# never built as a distribution), so there's nothing to "install" for it
# beyond copying app/ in below; only the real third-party deps need to land
# in .venv here. `--no-dev` drops pytest/httpx2 -- test-only, per
# pyproject.toml's [dependency-groups], not needed to run the server.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY pyproject.toml uv.lock ./
COPY app/ ./app/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev


FROM python:3.14-slim-bookworm AS runtime

# Runs as a non-root user -- this API serves parsed customer PII (contacts,
# WhatsApp/call attentions, see CLAUDE.md's security note) with no auth of
# its own yet; least-privilege inside the container is still worth having
# even though the real gap (no auth, open CORS) is an application-level
# decision outside this Dockerfile's scope.
RUN groupadd --system app && useradd --system --gid app --create-home --home-dir /app app

WORKDIR /app

COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# downloads/ is this app's only local write at runtime (the latest .xlsx/.csv
# per report -- see CLAUDE.md's "Path gotcha" note). Declared as a volume so a
# redeploy (new container, same image) doesn't silently lose already-
# downloaded reports. There's no state/ directory anymore -- the historical/
# contacts data lives in Turso (app/extraction/store.py), a remote database
# reached over the network via TURSO_DATABASE_URL/TURSO_AUTH_TOKEN, not a
# local file that would need its own Disk.
RUN mkdir -p /app/downloads && chown -R app:app /app/downloads
VOLUME ["/app/downloads"]

USER app

# Not a fixed port: Render (and most PaaS container hosts) inject their own
# $PORT at runtime and require the process to bind to THAT, not whatever
# EXPOSE says -- EXPOSE here is just the local-docker-run default/doc value.
EXPOSE 8000
ENV PORT=8000

# GET /health is public on purpose (no Authorization header available to a probe) and always
# returns 200 with no side effects -- GET /extraction/status used to serve this role but no longer
# can, since it's now behind auth (app/auth/). Plain urllib instead of curl/wget so the image
# doesn't need either installed. Reads $PORT too, same reason as CMD below.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health', timeout=3)" || exit 1

# No --reload (that's dev-only), and deliberately no --workers >1 either:
# extraction/state.py's last-run cache and the refresh lock are plain
# in-memory process state (see CLAUDE.md), so more than one worker process
# would give each its own independent lock/cache -- concurrent refreshes
# could overlap (the exact corruption the lock exists to prevent) and
# GET /extraction/status could answer from whichever worker happened to
# handle that request. Scale this service by running one container, not by
# adding workers/replicas, unless that in-memory state moves somewhere
# shared first.
#
# Shell form wrapping `exec` (not a plain JSON-array CMD) on purpose: needs
# a shell to expand $PORT at container start (a JSON-array CMD never invokes
# a shell, so "$PORT" would be passed to uvicorn literally, unexpanded), but
# a bare shell-form CMD leaves the shell itself as PID 1 and swallows
# SIGTERM instead of forwarding it to uvicorn -- `exec` replaces the shell
# process with uvicorn so it becomes PID 1 directly and shuts down cleanly.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
