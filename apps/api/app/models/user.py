"""User model — platform accounts (Phase 1: only the env-seeded admin, D-03)."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # RBAC role (PLAT-04 / D-01): admin | qa_lead | qa_engineer | developer. String(16) mirrors
    # the project's status/class-vocab convention (scenario.status, defects.classification);
    # server_default='admin' so the Phase-1 seeded admin is an Admin (migration 0010). The role
    # is read OFF THE ROW each request by require_role — never baked into the JWT (no stale-role
    # window). The vocabulary is guarded at the service/schema layer, not by a DB enum.
    role: Mapped[str] = mapped_column(String(16), server_default="admin")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
