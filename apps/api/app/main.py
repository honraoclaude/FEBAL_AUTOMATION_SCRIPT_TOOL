"""FastAPI application factory with lifespan-managed engine lifecycle."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.logging import configure_logging
from app.db.session import engine
from app.routers.health import router as health_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    # extension point: seed admin (plan 01-03)
    yield
    await engine.dispose()


app = FastAPI(title="Autonomous QA Engineer Platform API", lifespan=lifespan)

# /health at root (NOT under /api) — container healthcheck and verify_stack use it
app.include_router(health_router)
