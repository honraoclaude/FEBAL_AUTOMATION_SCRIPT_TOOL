"""Target schemas (PLAT-01, D-05/D-06).

TargetResponse is structurally credential-free: it simply HAS no credential
fields (whitelist by omission, never blacklist filtering). Credential fields
exist exclusively on the input-side CredentialsIn schema.
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CredentialsIn(BaseModel):
    """Write-only credential input — accepted on create/update, never returned."""

    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class BudgetOverrides(BaseModel):
    """Optional per-target exploration budget overrides (Phase 4 contract)."""

    max_steps: Annotated[int | None, Field(ge=1)] = None
    max_depth: Annotated[int | None, Field(ge=1)] = None
    wall_clock_seconds: Annotated[int | None, Field(ge=1)] = None
    token_budget: Annotated[int | None, Field(ge=1)] = None


class TargetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    base_url: HttpUrl
    credentials: CredentialsIn
    origin_allowlist: list[str] | None = None  # default: base_url origin (server-side)
    sandbox: bool = False
    budget_overrides: BudgetOverrides | None = None


class TargetUpdate(BaseModel):
    """PATCH body — every field optional; credentials replace-only-when-present."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: HttpUrl | None = None
    credentials: CredentialsIn | None = None
    origin_allowlist: list[str] | None = None
    sandbox: bool | None = None
    budget_overrides: BudgetOverrides | None = None
    is_active: bool | None = None


class TargetResponse(BaseModel):
    """Public target shape — NO credential fields exist on this model (D-06)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    base_url: str
    has_credentials: bool
    origin_allowlist: list[str]
    sandbox: bool
    budget_overrides: BudgetOverrides | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
