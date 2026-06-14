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

# Self-migrating entrypoint (D-08): one command means one command — no manual pre-steps
CMD ["sh", "-c", "uv run alembic upgrade head && uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"]
