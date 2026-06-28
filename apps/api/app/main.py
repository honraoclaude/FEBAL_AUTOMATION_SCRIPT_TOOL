"""FastAPI application factory with lifespan-managed engine lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import ServiceUnavailable
from sqlalchemy import select

from app.core.checkpointer import close_checkpointer, init_checkpointer
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.neo4j_driver import close_neo4j, get_neo4j, init_neo4j
from app.core.redis_client import close_redis, init_redis
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.execution_history import (  # noqa: F401 -- Base.metadata/Alembic discovery
    TestArtifact,
    TestResult,
    TestRun,
)
from app.models.heal_audit import HealAudit  # noqa: F401 -- Base.metadata/Alembic discovery
from app.models.llm_usage import LLMUsage  # noqa: F401 -- Base.metadata/Alembic discovery
from app.models.run import Execution, Run  # noqa: F401 -- Base.metadata/Alembic discovery
from app.models.scenario import Scenario  # noqa: F401 -- Base.metadata/Alembic discovery
from app.models.user import User
from app.routers.admin_llm import router as admin_llm_router
from app.routers.auth import router as auth_router
from app.routers.defects import router as defects_router
from app.routers.executions import router as executions_router
from app.routers.execute import router as execute_router
from app.routers.explore import router as explore_router
from app.routers.generate import router as generate_router
from app.routers.health import router as health_router
from app.routers.heals import router as heals_router
from app.routers.kg import router as kg_router
from app.routers.scenarios import router as scenarios_router
from app.routers.stubs import router as stubs_router
from app.routers.targets import router as targets_router
from app.routers.users import router as users_router
from app.services.kg.schema import ensure_constraints

log = structlog.get_logger()


async def seed_admin() -> None:
    """Idempotent admin seed from ADMIN_EMAIL/ADMIN_PASSWORD (D-03, Pitfall 7).

    Check-then-create inside one transaction; single-worker dev so no race.
    Restarting the api never creates a second row or crashes.
    """
    async with SessionLocal() as session:
        async with session.begin():
            existing = await session.scalar(select(User).where(User.email == settings.admin_email))
            if existing is None:
                session.add(
                    User(
                        email=settings.admin_email,
                        password_hash=hash_password(settings.admin_password),
                        # D-01: the env-seeded admin is the platform Admin. Set explicitly on
                        # create (in addition to the column server_default) so the intent is
                        # local to the seed, not only an implicit migration default.
                        role="admin",
                    )
                )
                log.info("admin_user_seeded", email=settings.admin_email)
            else:
                log.info("admin_user_exists", email=settings.admin_email)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    init_redis()  # open the single long-lived gateway Redis client (hot-path GET/MGET/pipeline)
    init_neo4j()  # open the single lifespan Neo4j driver/pool (lazy connect — boots even if neo4j is down)
    # KG-03: create the uniqueness constraints backing the idempotent fingerprint-MERGE.
    # ensure_constraints is GRACEFUL — it catches an unreachable neo4j and returns without
    # raising, so the api still boots when the graph profile is down (no depends_on:neo4j).
    await ensure_constraints(get_neo4j())
    # Open the LangGraph checkpointer pool + run setup() ONCE (creates checkpoint tables
    # OUTSIDE Alembic, idempotent — Pitfall 6). Coexists with the asyncpg SQLAlchemy engine.
    await init_checkpointer()
    await seed_admin()
    yield
    await close_checkpointer()
    await close_neo4j()
    await close_redis()
    await engine.dispose()


app = FastAPI(title="Autonomous QA Engineer Platform API", lifespan=lifespan)


@app.exception_handler(ServiceUnavailable)
async def _neo4j_unavailable_handler(request: Request, exc: ServiceUnavailable) -> JSONResponse:
    """KG read endpoints need Neo4j; the graph profile is optional (api boots without it).

    When Neo4j is unreachable, return a clean 503 the browse UI renders as its
    'graph unavailable' state — never leak an unhandled 500/stack trace. Consistent
    with the graceful-without-neo4j contract (lazy driver, graceful ensure_constraints).
    """
    log.warning("neo4j_unavailable", path=str(request.url.path))
    return JSONResponse(
        status_code=503,
        content={"detail": "Knowledge graph is unavailable — start the graph profile to browse it."},
    )


# /health at root (NOT under /api) — container healthcheck and verify_stack use it
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(targets_router)
app.include_router(admin_llm_router)
app.include_router(explore_router)
app.include_router(executions_router)
app.include_router(generate_router)
app.include_router(execute_router)
# KG read API (KG-02 / D-06) — real /flows + /coverage + /graph/pages/elements, auth-gated.
# Included BEFORE stubs_router so its real /flows + /coverage win over any residual stub route.
app.include_router(kg_router)
# Scenario review queue (GEN-02 / D-01..D-04) — auth-gated list/get/edit/approve/reject.
# Included BEFORE stubs_router (like kg_router) so its real routes win over any residual stub.
app.include_router(scenarios_router)
# Heal review/stats API (HEAL-03 review surface + HEAL-04 stats / D-05) — auth-gated
# list/apply/reject + per-element stats. API ONLY (no heal UI — deferred to Phase 10). Included
# BEFORE stubs_router so its real /api/heals routes win over any residual stub (mirrors kg/scenarios).
app.include_router(heals_router)
# Defect draft-review API (JIRA-02 / D-04) — auth-gated list/detail/calibration/apply/reject.
# The human-in-the-loop surface the autonomy gate requires. Included BEFORE stubs_router so its
# real /api/defects routes win over any residual stub (mirrors kg/scenarios/heals).
app.include_router(defects_router)
# Admin user-management API (PLAT-04 / D-01) — Admin-only list + role assignment. Included
# BEFORE stubs_router so its real /api/users routes win over any residual stub (mirrors the
# kg/scenarios/heals/defects precedent).
app.include_router(users_router)
app.include_router(stubs_router)
