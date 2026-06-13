# apps/api — FastAPI backend

Platform API tier (uv project, Python 3.13). Provides typed settings, structlog
JSON logging with credential redaction, async SQLAlchemy + Alembic, and the
`/health` endpoint pinging Postgres and Redis.

## Run modes (D-09 — same repo-root `.env` for both)

- **Compose:** `docker compose -f infra/docker-compose.yml --env-file .env up -d --wait`
  from the repo root (api container self-migrates via `alembic upgrade head`).
- **Hybrid host:** infra in Docker, API on the host:
  `cd apps/api && uv run uvicorn app.main:app --reload`

## Tests

Functional tests hit the RUNNING stack over live HTTP (D-02):

```bash
cd apps/api && uv run pytest tests/functional -x -q
```
