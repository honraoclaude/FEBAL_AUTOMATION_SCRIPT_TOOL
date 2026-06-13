# Phase 2: LLM Gateway - Pattern Map

**Mapped:** 2026-06-13
**Files analyzed:** 13 (11 new, 2 modified)
**Analogs found:** 11 / 13 (2 net-new patterns with no in-app analog)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `app/services/llm_gateway.py` | service | request-response | `app/services/target_service.py` | role-match (orchestration is net-new) |
| `app/core/config.py` (modify) | config | — | itself (extend in place) | exact |
| `app/core/llm_pricing.py` | utility (focused module) | transform | `app/core/crypto.py` | role-match (small no-logger module) |
| `app/models/llm_usage.py` | model | CRUD | `app/models/target.py` | exact |
| `app/schemas/llm.py` | schema | request-response | `app/schemas/target.py` | exact |
| `app/routers/admin_llm.py` | router | request-response | `app/routers/targets.py` | exact |
| `app/main.py` (modify) | config | — | itself (router include) | exact |
| `alembic/versions/0003_llm_usage.py` | migration | — | `alembic/versions/0002_targets.py` | exact |
| Redis client wiring (counters/cache/kill-flag) | utility | — | `app/routers/health.py` (redis ping only) | **NET-NEW — flag** |
| `tests/unit/conftest.py` | test (fixture) | — | `tests/conftest.py` | role-match (NEW unit style, mocked) |
| `tests/unit/test_*.py` (budget/cache/pricing/killswitch/provider) | test | — | — (mocked, no live analog) | **NET-NEW — flag** |
| `tests/functional/test_killswitch.py`, `test_usage_ledger.py`, `test_llm_log_safety.py` | test | request-response | `tests/functional/test_targets.py` + `test_credential_security.py` | exact |
| `tests/integration/test_llm_parity.py` | test (live, gated) | request-response | — (new `live_llm` marker) | **NET-NEW — flag** |

---

## Pattern Assignments

### `app/services/llm_gateway.py` (service, request-response)

**Analog:** `app/services/target_service.py`

Mirror the service-module shape: a docstring stating the single-surface discipline, typed domain exceptions defined at module top, private `_helpers` for sub-steps, public async functions taking `db: AsyncSession` as first arg. The gateway's `complete(...)` is the single public entry point the way `get_decrypted_credentials` is the single decrypt surface.

**Module docstring + typed-exception pattern** (`target_service.py` lines 1-27):
```python
"""Target registry service (PLAT-01/PLAT-07).

Encrypt-on-write lives HERE ...: routers never touch ... and decryption has
exactly one caller surface — get_decrypted_credentials ...
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

class DuplicateTargetNameError(Exception):
    """Raised when a create/update would violate the unique target name."""
```
> New gateway defines `BudgetExceeded`, `KillSwitchActive`, `UnknownModelPriceError`, `TransientProviderError` the same way (typed, module-top, raised — never returned as a result object, per D-02).

**Async session + commit/refresh pattern** for the ledger insert (`target_service.py` lines 44-70):
```python
async def create_target(db: AsyncSession, data: TargetCreate) -> Target:
    target = Target(...)
    db.add(target)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateTargetNameError(data.name)
    await db.refresh(target)
    return target
```
> The `llm_usage` ledger INSERT in `complete()` reuses `db.add()` + `await db.commit()`. No IntegrityError branch needed (no unique constraint), but keep the commit/refresh shape.

**Redis client (net-new in service layer)** — see Shared Patterns → Redis. The only in-app reference is `health.py` (ping only); the gateway needs GET/MGET/SETEX/INCRBY/pipeline. Scaffold a single module-level `redis.asyncio` client from `settings.redis_url` (mirroring `health.py`'s `aioredis.from_url(settings.redis_url)`), not a per-call connection.

---

### `app/core/config.py` (config, MODIFY in place)

**Analog:** itself — extend the existing `Settings` class.

**Existing pattern to extend** (`config.py` lines 13-39):
```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    database_url: str  # env DATABASE_URL
    redis_url: str  # env REDIS_URL
    ...
    cookie_secure: bool = False  # env COOKIE_SECURE
```
> Add new fields IN this class (env names are the contract): `llm_default_model: str`, provider keys `anthropic_api_key: str | None = None` / `openai_api_key: str | None = None`, budget caps (`llm_per_call_usd_cap`, `llm_daily_usd_cap`, `llm_run_usd_cap` and token equivalents), `llm_cache_ttl_s: int = 86400`, plus optional `langsmith_*`. Follow the `# env VAR_NAME` inline-comment convention on every field. Provider keys default `None` so the app boots without them (live tests skip when absent — see Pitfall 6 in RESEARCH). Reuse the `@field_validator(mode="before")` comma-split pattern (lines 33-38) only if any new var is a list. Do NOT create a second Settings class — `settings = Settings()` singleton at line 41 stays the sole instance.

---

### `app/core/llm_pricing.py` (utility, transform)

**Analog:** `app/core/crypto.py` (the small, focused, no-logger module style)

`crypto.py` is the template for a tight pure-data/pure-function `core/` module: module docstring naming the responsibility, module-level constant built from settings, two small functions, **and the explicit "NO logger" discipline**.

**No-logger focused-module pattern** (`crypto.py` lines 1-24):
```python
"""Fernet credential encryption (PLAT-07, D-06, T-01-16).
...
This module deliberately has NO logger and never logs its inputs.
"""
from app.core.config import settings

fernet = MultiFernet([Fernet(key) for key in settings.credential_keys])

def encrypt(value: str) -> bytes:
    """Encrypt a plaintext credential to a Fernet token ..."""
    return fernet.encrypt(value.encode())
```
> `llm_pricing.py` mirrors this: module-level `PRICING: list[PriceRow]` constant + `lookup_price(model, at)` pure function (RESEARCH Pattern 4). Use a `pydantic.BaseModel` `PriceRow` with `effective_date: date`; fail-closed with a module-top `UnknownModelPriceError`. Keep it logger-free like crypto — it is pure data + lookup.

---

### `app/models/llm_usage.py` (model, CRUD)

**Analog:** `app/models/target.py`

**SQLAlchemy 2.0 Mapped/mapped_column style** (`target.py` lines 8-35):
```python
from datetime import datetime
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class Target(Base):
    __tablename__ = "targets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    sandbox: Mapped[bool] = mapped_column(Boolean, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```
> `LLMUsage(Base)` reuses: `Base` import from `app.db.base`, `Mapped[...] = mapped_column(...)`, `String(N)` lengths, `Boolean` + `server_default="false"` for `cache_hit`, `DateTime(timezone=True)` + `func.now()` for `created_at`. Per RESEARCH Pattern 5, add `index=True` on `run_id`/`operation_type`, and use `Numeric(12, 6)` (NOT Float) for `cost_usd`. **No prompt/response columns** (PLAT-07).

---

### `app/schemas/llm.py` (schema, request-response)

**Analog:** `app/schemas/target.py`

**Pydantic schema conventions** (`target.py` lines 11-36, 51-65):
```python
from pydantic import BaseModel, ConfigDict, Field

class BudgetOverrides(BaseModel):
    """Optional per-target exploration budget overrides (Phase 4 contract)."""
    max_steps: Annotated[int | None, Field(ge=1)] = None
    token_budget: Annotated[int | None, Field(ge=1)] = None

class TargetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # ORM read models
    id: int
    ...
```
> New `LLMRequest` / `LLMResult` / `RunBudgetOverrides` follow this: `Field(ge=1)` bounds on budget params (validation rejects negatives → 422, mirroring `test_targets.py::test_validation`), `ConfigDict(from_attributes=True)` on any model read from a `LLMUsage` row, and the admin kill-switch body schema (e.g. `KillSwitchRequest{reason: str}`). Note: a `RunBudgetOverrides` analog already exists as `BudgetOverrides` here — the gateway's run-budget param shape should align field names with it (Phase 4 feeds `Target.budget_overrides` in, per D-04).

---

### `app/routers/admin_llm.py` (router, request-response)

**Analog:** `app/routers/targets.py`

**Router-level auth gate + handler shape** (`targets.py` lines 7-33):
```python
from fastapi import APIRouter, Depends, HTTPException
from app.core.security import get_current_user
from app.db.session import get_db
from app.services import target_service

router = APIRouter(
    prefix="/api/targets",
    tags=["targets"],
    dependencies=[Depends(get_current_user)],  # router-level gate
)

@router.post("", status_code=201, response_model=TargetResponse)
async def register_target(body: TargetCreate, db: AsyncSession = Depends(get_db)):
    try:
        target = await target_service.create_target(db, body)
    except DuplicateTargetNameError:
        raise HTTPException(status_code=409, detail=_DUPLICATE)
    return TargetResponse.model_validate(target)
```
> `admin_llm.py` uses `prefix="/api/admin/llm"`, the same `dependencies=[Depends(get_current_user)]` router-level gate (V2/V4 auth — RESEARCH Security Domain; Admin-RBAC deferred to Phase 10, document the gap), and handlers `POST /killswitch` (set Redis flag) / `DELETE /killswitch` (clear) / optional `GET /killswitch` (status). The kill-switch writes Redis, not Postgres, so handlers call a gateway helper rather than a `db`-session service — but keep the try/except → `HTTPException` translation shape. Register in `main.py` (see below).

---

### `app/main.py` (config, MODIFY — router include)

**Analog:** itself (`main.py` lines 14-56)

**Router-include pattern** (`main.py` lines 16-17, 54-56):
```python
from app.routers.targets import router as targets_router
...
app.include_router(targets_router)
```
> Add `from app.routers.admin_llm import router as admin_llm_router` and `app.include_router(admin_llm_router)`. Models are imported for metadata via existing pattern (`from app.models.user import User` line 14) — ensure `app/models/llm_usage.py` is imported somewhere on the metadata path so Alembic autogenerate / `Base.metadata` sees it (mirror how `user`/`target` are wired). No lifespan change required unless a shared Redis client is created at startup.

---

### `alembic/versions/0003_llm_usage.py` (migration)

**Analog:** `alembic/versions/0002_targets.py`

**Migration chain + create_table/create_index style** (`0002_targets.py` lines 14-39):
```python
revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'

def upgrade() -> None:
    op.create_table('targets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sandbox', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_targets_name'), 'targets', ['name'], unique=True)
```
> `0003_llm_usage.py`: `revision = '0003'`, **`down_revision = '0002'`** (chains after targets, per D-09). Create `llm_usage` with columns matching the model; use `sa.Numeric(12, 6)` for `cost_usd`, `sa.Boolean(server_default='false')` for `cache_hit`, `sa.text('now()')` for `created_at`. Add non-unique indexes on `run_id`, `operation_type`, `created_at` (RESEARCH Pattern 5). Prefer autogenerate then hand-adjust, matching the `# auto generated by Alembic - please adjust!` convention in 0002.

---

### `tests/unit/conftest.py` + `tests/unit/test_*.py` (test — NEW mocked style)

**Analog:** `tests/conftest.py` (fixture mechanics) — but the unit suite INVERTS the Phase-1 live-only philosophy.

**Phase-1 fixture/env-loading pattern to reuse** (`conftest.py` lines 14-27, 55-60):
```python
from dotenv import load_dotenv
_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env", override=False)

@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(base_url=API_BASE) as c:
        yield c
```
> **KEY DIFFERENCE (net-new):** Phase-1 `conftest.py` docstring states "tests are FUNCTIONAL — they hit the RUNNING stack ... No ... in-process shortcut." The NEW `tests/unit/conftest.py` is the opposite: a fixture that **mocks `init_chat_model`** to return a fake `AIMessage` with controllable `usage_metadata` (no provider, no spend), plus a Redis fixture (RESEARCH recommends the running compose Redis with a test key-prefix + flush per test, AVOIDING a new `fakeredis` package gate). Reuse the `load_dotenv(..., override=False)` repo-root pattern and the path-parents idiom; adjust `parents[N]` for the new `tests/unit/` depth. Note Redis-rewrite-for-host idiom in `_host_dsn()` (lines 30-35) is the model for any host-side Redis URL rewrite.

**Marker registration** — `pyproject.toml` `[tool.pytest.ini_options]` lines 39-42 currently registers `functional` + `e2e`. Add `live_llm: needs real provider keys; skipped when absent; off the default gate` to that `markers` list (RESEARCH Validation Architecture). The `pytest_collection_modifyitems` loop-ordering hook (`conftest.py` lines 38-52) is the precedent for any cross-suite ordering if unit+functional+e2e collide in one process.

---

### `tests/functional/test_killswitch.py` / `test_usage_ledger.py` / `test_llm_log_safety.py` (functional, live HTTP)

**Analogs:** `tests/functional/test_targets.py` (HTTP CRUD shape) + `tests/functional/test_credential_security.py` (DB-at-rest + log-capture shape)

**Live-HTTP functional test shape** (`test_targets.py` lines 12-43):
```python
import uuid
import pytest
pytestmark = pytest.mark.functional

def _unique_name(prefix: str = "target") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"

async def test_register_target_minimal_defaults(authed_client, clean_targets):
    r = await authed_client.post("/api/targets", json=payload)
    assert r.status_code == 201, r.text
```
> Reuse `pytestmark = pytest.mark.functional`, the `authed_client` fixture for auth'd endpoints (kill-switch admin POST/DELETE), uuid-suffixed unique identifiers, and the "assert only entities this test created" discipline (Pitfall 8). `test_killswitch.py` drives the live admin endpoint and asserts subsequent gateway calls raise / return refused.

**DB-at-rest + log-safety verification** (`test_credential_security.py` lines 44-67, 121-147):
```python
def _host_dsn() -> str:
    url = os.environ["DATABASE_URL"]
    return url.replace("postgresql+asyncpg://", "postgresql://").replace("@postgres:", "@localhost:")

async def _fetch_ciphertext(name: str) -> tuple[bytes, bytes]:
    conn = await asyncpg.connect(_host_dsn())
    ...
# docker compose logs capture for leak assertions:
proc = subprocess.run(["docker","compose","-f","infra/docker-compose.yml",
    "--env-file",".env","logs","api","--since","2m"], cwd=REPO_ROOT, ...)
assert password not in captured
```
> `test_usage_ledger.py` reuses the `_host_dsn()` + `asyncpg.connect` raw-SQL read to assert a `llm_usage` row landed with correct USD/tokens/`cache_hit`. `test_llm_log_safety.py` reuses the `docker compose logs api` capture (lines 131-147) to assert NO prompt text / provider keys appear in logs (PLAT-07, RESEARCH Pitfall 5). A `clean_llm_usage` fixture mirroring `clean_targets` (`tests/conftest.py` lines 74-89, TRUNCATE-after-test) should be added for ledger isolation.

---

### `tests/integration/test_llm_parity.py` (test — NET-NEW, gated live)

**Analog:** none in-app (first gated/skippable live-provider test).

> No existing test calls an external paid API. Build with `@pytest.mark.live_llm` + `@pytest.mark.skipif(not (ANTHROPIC_API_KEY and OPENAI_API_KEY), ...)` (RESEARCH Pitfall 6). Keep OUT of the default gate (`-m "not live_llm"`). Closest mechanical reference is `tests/conftest.py`'s env-key reads (`os.environ["ADMIN_EMAIL"]`) for the skipif guard. This is a planner scaffold-carefully item.

---

## Shared Patterns

### Authentication (admin kill-switch endpoint)
**Source:** `app/routers/targets.py` lines 16-21 (router-level gate) + `app/core/security.py` lines 120-141 (`get_current_user`)
**Apply to:** `app/routers/admin_llm.py`
```python
router = APIRouter(
    prefix="/api/admin/llm",
    tags=["admin-llm"],
    dependencies=[Depends(get_current_user)],  # no route reachable unauthenticated
)
```
> `get_current_user` resolves the user from the `access_token` httpOnly cookie or raises 401. Admin-only RBAC is NOT yet available (Phase 10) — auth-gate now, document the role gap (RESEARCH V4 Access Control).

### Structured logging + redaction (usage events)
**Source:** `app/core/logging.py` lines 14-24 (`redact_sensitive` + `SENSITIVE` regex)
**Apply to:** `app/services/llm_gateway.py` usage-event emission
```python
SENSITIVE = re.compile(r"password|passwd|secret|credential|token", re.I)
def redact_sensitive(logger, method_name, event_dict):
    for key in list(event_dict):
        if SENSITIVE.search(key):
            event_dict[key] = "[REDACTED]"
    return event_dict
```
> Emit usage events via `structlog.get_logger()` (pattern: `main.py` line 19 `log = structlog.get_logger()`). Log ONLY `{operation_type, run_id, provider, model, input_tokens, output_tokens, cost_usd, cache_hit}` — never `messages`/prompt bodies (PLAT-07, RESEARCH Pitfall 5). Redaction is a backstop, not the primary control: don't pass a key named `*_token` for token COUNTS, or it gets `[REDACTED]` — use `input_tokens`/`output_tokens` which the regex would match on "token"... **flag:** the existing `SENSITIVE` regex matches the substring `token`, so `input_tokens`/`output_tokens` keys WILL be redacted. Planner must either rename the logged keys (e.g. `input_token_count`) or scope the regex — call this out in the plan.

### Settings singleton (env contract)
**Source:** `app/core/config.py` lines 13-41
**Apply to:** every new module needing config (`llm_gateway`, `llm_pricing`, `admin_llm`, Redis client)
```python
from app.core.config import settings
# settings.redis_url, settings.llm_default_model, settings.llm_daily_usd_cap, ...
```
> One import surface; never re-instantiate `Settings()`. All new env vars are added to the single class (see config.py assignment above).

### Async DB session (ledger writes)
**Source:** `app/db/session.py` lines 13-20 + `app/services/target_service.py` lines 63-70
**Apply to:** `llm_usage` INSERT in the gateway
```python
async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
# in service: db.add(row); await db.commit(); await db.refresh(row)
```
> `Base` from `app.db.base` (line 1-7) for the new model; `target_metadata = Base.metadata` is how Alembic already discovers models.

### Redis client (counters / cache / kill-flag) — **NET-NEW, no in-app analog**
**Source (closest, ping-only):** `app/routers/health.py` lines 8, 31-37
**Apply to:** `app/services/llm_gateway.py` (and the kill-switch helper used by `admin_llm.py`)
```python
import redis.asyncio as aioredis
client = aioredis.from_url(settings.redis_url)
await client.ping()
await client.aclose()
```
> **FLAG FOR PLANNER:** Phase-1 app code touches Redis ONLY for a health ping. Everything the gateway needs — `GET`/`MGET` (kill-flag + budget read), `SETEX` (cache), `INCRBY`/`INCRBYFLOAT` + `pipeline(transaction=True)` (atomic counters), date-bucketed daily keys (RESEARCH Pattern 3) — is net-new in this codebase. There is NO established pattern for a long-lived shared `redis.asyncio` client. Scaffold deliberately: create ONE module-level client (or a lifespan-managed client in `main.py`) reused across calls — do NOT open a new connection per call like `health.py` does (that pattern is fine for a once-per-healthcheck ping, wrong for a hot path). `aioredis` (the name health.py imports `redis.asyncio as aioredis`) is just an alias — the dead `aioredis` package is NOT used; `redis.asyncio` is correct (CLAUDE.md).

---

## No Analog Found

Files/patterns with no close in-app match (planner should use RESEARCH.md patterns + scaffold carefully):

| File / Pattern | Role | Data Flow | Reason |
|----------------|------|-----------|--------|
| Redis counters/cache/kill-flag wiring | utility | event/transform | Phase-1 app only pings Redis in `/health`; GET/MGET/SETEX/INCRBY/pipeline + date-bucket keys are all net-new (RESEARCH Pattern 3/6) |
| `init_chat_model` provider call + tenacity retry | service | request-response | No LangChain usage exists yet; `init_chat_model(...).ainvoke()` wrapped in `tenacity` is net-new (RESEARCH Code Examples, Pattern 1) |
| Token pre-estimate (`tiktoken` / `anthropic.count_tokens`) | utility | transform | No tokenizer usage exists; net-new and gated behind package-legitimacy `checkpoint:human-verify` (RESEARCH Package Legitimacy Audit) |
| `tests/integration/test_llm_parity.py` | test | request-response | First gated live-provider test; `live_llm` marker net-new |
| `tests/unit/*` mocked suite | test | — | Phase-1 tests are live-stack-only by design; mocked-provider unit tests invert that philosophy |

---

## Metadata

**Analog search scope:** `apps/api/app/{services,core,models,schemas,routers,db}/`, `apps/api/alembic/versions/`, `apps/api/tests/`, `apps/api/pyproject.toml`
**Files scanned:** 13 analog files read in full (all ≤ 200 lines, single-pass)
**Pattern extraction date:** 2026-06-13
**Key cross-cutting flags for planner:**
1. Redis hot-path client is net-new — do not copy `health.py`'s per-call connect/close.
2. `SENSITIVE` redaction regex matches the substring `token` — `input_tokens`/`output_tokens` log keys will be redacted unless renamed or the regex is scoped.
3. New `tests/unit/` suite inverts Phase-1's live-only test philosophy (mocked provider + prefixed Redis, no `fakeredis` gate).
4. NEW packages (langchain*, tenacity, tiktoken, anthropic, langsmith) are all `[ASSUMED]` — gate behind `checkpoint:human-verify` (Phase-1 plan 01-02 Task-1 precedent).
```