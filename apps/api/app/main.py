"""FastAPI application factory with lifespan-managed engine lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import settings
from app.core.logging import configure_logging
from app.core.neo4j_driver import close_neo4j, init_neo4j
from app.core.redis_client import close_redis, init_redis
from app.core.security import hash_password
from app.db.session import SessionLocal, engine
from app.models.llm_usage import LLMUsage  # noqa: F401 -- Base.metadata/Alembic discovery
from app.models.run import Execution, Run  # noqa: F401 -- Base.metadata/Alembic discovery
from app.models.user import User
from app.routers.admin_llm import router as admin_llm_router
from app.routers.auth import router as auth_router
from app.routers.executions import router as executions_router
from app.routers.explore import router as explore_router
from app.routers.health import router as health_router
from app.routers.targets import router as targets_router

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
    await seed_admin()
    yield
    await close_neo4j()
    await close_redis()
    await engine.dispose()


app = FastAPI(title="Autonomous QA Engineer Platform API", lifespan=lifespan)

# /health at root (NOT under /api) — container healthcheck and verify_stack use it
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(targets_router)
app.include_router(admin_llm_router)
app.include_router(explore_router)
app.include_router(executions_router)
