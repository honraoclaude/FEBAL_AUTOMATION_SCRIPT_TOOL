"""Target model — registered target applications (D-05/D-06/D-07).

Credentials are stored ONLY as Fernet ciphertext (encrypted_username /
encrypted_password, LargeBinary). The schema carries the Phase 4 Explorer's
input contract: origin_allowlist, sandbox, budget_overrides.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Target(Base):
    __tablename__ = "targets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    base_url: Mapped[str] = mapped_column(String(2048))
    # Fernet ciphertext only — plaintext never touches the database (T-01-16).
    encrypted_username: Mapped[bytes] = mapped_column(LargeBinary)
    encrypted_password: Mapped[bytes] = mapped_column(LargeBinary)
    # Exploration rules (Phase 4 Explorer input contract, D-05).
    origin_allowlist: Mapped[list[str]] = mapped_column(JSON)
    sandbox: Mapped[bool] = mapped_column(Boolean, server_default="false")
    budget_overrides: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Soft delete (D-07): deactivate, never drop the row.
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    @property
    def has_credentials(self) -> bool:
        """The only credential-derived value any response schema may carry (D-06)."""
        return bool(self.encrypted_username and self.encrypted_password)
