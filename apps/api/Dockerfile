FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Manifests first for layer caching — deps only re-resolve when pins change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY . .
RUN uv sync --frozen --no-dev

# Explore crawl (03-02): chromium + its OS libs baked in so the deterministic
# Playwright login/crawl runs in this container. --with-deps installs the apt
# shared libraries (libglib-2.0, etc.) python:3.13-slim lacks. Browser binaries
# are version-locked to the pinned playwright; rebuild when playwright bumps.
RUN uv run playwright install --with-deps chromium

EXPOSE 8000

# Self-migrating entrypoint (D-08): one command means one command — no manual pre-steps.
# PRODUCTION default (D-06, plan 11-02): NO --reload. This is the image GHCR publishes and
# K8s runs, so it serves with uvicorn --workers (CLAUDE.md "run with --workers in containers")
# — no dev file-watcher (T-11-08: a prod server, no hot-reload watchers in the published image).
# The worker Deployment reuses this SAME image with command ["python","-m","app.worker_main"].
#
# Local hot-reload DX is NOT the image default — it is provided by the compose dev override
# (bind-mount + a --reload command override / hybrid host `npm run dev` + uvicorn --reload),
# not baked here. Earlier this CMD carried --reload --reload-dir app for the bind-mount dev
# loop; --reload-dir scoped the watcher to app/ so writes under the mounted /app/workspaces
# (spec /execute runs + Chromium/pytest artifacts) didn't trigger a mid-run reload (03-04).
# The published image must never watch — so --reload is dropped entirely here.
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"]
