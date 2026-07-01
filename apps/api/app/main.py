"""FastAPI application factory with lifespan-managed engine lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from elasticsearch.exceptions import ConnectionError as ESConnectionError
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from neo4j.exceptions import ServiceUnavailable
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import select

from app.core.checkpointer import close_checkpointer, init_checkpointer
from app.core.config import settings
from app.core.es_client import close_es, get_es, init_es
from app.core.logging import configure_logging
from app.core.metrics import start_metrics, stop_metrics
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
from app.routers.coverage_dash import router as coverage_dash_router
from app.routers.dashboards import router as dashboards_router
from app.routers.defects import router as defects_router
from app.routers.executions import router as executions_router
from app.routers.execute import router as execute_router
from app.routers.explore import router as explore_router
from app.routers.generate import router as generate_router
from app.routers.health import router as health_router
from app.routers.heals import router as heals_router
from app.routers.kg import router as kg_router
from app.routers.scenarios import router as scenarios_router
from app.routers.search import router as search_router
from app.routers.stubs import router as stubs_router
from app.routers.targets import router as targets_router
from app.routers.traceability import router as traceability_router
from app.routers.users import router as users_router
from app.services.kg.schema import ensure_constraints
from app.services.search.indexer import ensure_indices

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
    init_es()  # open the single lifespan AsyncElasticsearch client (lazy connect — boots even if ES is down)
    # KG-03: create the uniqueness constraints backing the idempotent fingerprint-MERGE.
    # ensure_constraints is GRACEFUL — it catches an unreachable neo4j and returns without
    # raising, so the api still boots when the graph profile is down (no depends_on:neo4j).
    await ensure_constraints(get_neo4j())
    # DASH-06: create the search index mappings (best-effort). ensure_indices is GRACEFUL —
    # it swallows an unreachable ES and returns without raising (the ensure_constraints
    # precedent), so the api still boots when the search profile is down (no depends_on:es).
    await ensure_indices(get_es())
    # Open the LangGraph checkpointer pool + run setup() ONCE (creates checkpoint tables
    # OUTSIDE Alembic, idempotent — Pitfall 6). Coexists with the asyncpg SQLAlchemy engine.
    await init_checkpointer()
    await seed_admin()
    # INFRA-04: register the domain-metric collector + start the 30s background refresher, then
    # mount HTTP instrumentation + the /metrics endpoint on the DEFAULT REGISTRY (which now
    # includes the custom collector). /metrics is unauthenticated-but-safe — the root /health
    # precedent: it emits only aggregate numeric gauges + HTTP histograms, no secrets/PII/prompts
    # (T-11-01 accept; llm_usage has no prompt/response columns, PLAT-07).
    start_metrics(app)
    # NOTE: Instrumentator().instrument(app) adds middleware, which Starlette forbids after
    # startup — it is set up at module scope right after app construction (below), NOT here.
    yield
    await stop_metrics()
    await close_checkpointer()
    await close_neo4j()
    await close_es()
    await close_redis()
    await engine.dispose()


app = FastAPI(title="Autonomous QA Engineer Platform API", lifespan=lifespan)

# INFRA-04: HTTP instrumentation + /metrics must be mounted at CONSTRUCTION time (adding
# middleware after startup raises "Cannot add middleware after an application has started").
# The custom domain-metric collector is registered on the default registry by start_metrics()
# in the lifespan; Instrumentator().expose() reads that same default registry at scrape time.
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


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


@app.exception_handler(ESConnectionError)
async def _es_unavailable_handler(request: Request, exc: ESConnectionError) -> JSONResponse:
    """The search endpoint needs Elasticsearch; the search profile is optional (api boots without it).

    When ES is unreachable, return a clean 503 the search UI renders as its 'search unavailable'
    state — NEVER an unhandled 500/stack trace and NEVER a fake empty hit list pretending zero
    results (T-10-20). Mirrors the neo4j-503 handler; consistent with the graceful-without-ES
    contract (lazy client, graceful ensure_indices, swallow-and-log on-write index).
    """
    log.warning("elasticsearch_unavailable", path=str(request.url.path))
    return JSONResponse(
        status_code=503,
        content={"detail": "Search is unavailable — start the search profile to use it."},
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
# DASH-04 lifecycle-coverage panel (role-gated /api/coverage/flows) — DISTINCT from the kg
# router's ground-truth /api/coverage (Pitfall 5). Included BEFORE stubs_router so its real route
# wins over any residual stub (mirrors the kg/scenarios/heals/defects/users precedent).
app.include_router(coverage_dash_router)
# The three role-gated dashboards (DASH-01/02/03) — per-route require_role(...) per the rbac.py
# matrix. Included BEFORE stubs_router so its real /api/dashboards/* routes win over any residual
# stub (mirrors the kg/scenarios/heals/defects/users/coverage precedent).
app.include_router(dashboards_router)
# Traceability viewer (DASH-05) — role-gated GET /api/traceability cross-store chain. Read-only
# join (no graph writes). Included BEFORE stubs_router so its real route wins over any residual
# stub (mirrors the kg/scenarios/heals/defects/users/coverage/dashboards precedent).
app.include_router(traceability_router)
# Full-text search (DASH-06) — role-gated GET /api/search over executions/failures/logs served
# by Elasticsearch. ES-down → honest 503 (the ESConnectionError handler above). Included BEFORE
# stubs_router so its real route wins over any residual stub (mirrors the kg/scenarios/heals/
# defects/users/coverage/dashboards/traceability precedent).
app.include_router(search_router)
app.include_router(stubs_router)
