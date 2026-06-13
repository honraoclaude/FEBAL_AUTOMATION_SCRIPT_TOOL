"""Target registry service (PLAT-01/PLAT-07).

Encrypt-on-write lives HERE (RESEARCH Architectural Responsibility Map):
routers never touch plaintext-to-ciphertext conversion, and decryption has
exactly one caller surface — get_decrypted_credentials — consumed by the
Phase 4 Explorer (in Phase 1 only the round-trip test exercises it).
"""

from pydantic import HttpUrl
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt, encrypt
from app.models.target import Target
from app.schemas.target import TargetCreate, TargetUpdate

_DEFAULT_PORTS = {"http": 80, "https": 443}


class DuplicateTargetNameError(Exception):
    """Raised when a create/update would violate the unique target name."""


class TargetNotFoundError(Exception):
    """Raised when a target id does not exist."""


def _origin_of(url: HttpUrl) -> str:
    """scheme://host[:port] origin of a URL; port omitted when scheme-default."""
    origin = f"{url.scheme}://{url.host}"
    if url.port is not None and url.port != _DEFAULT_PORTS.get(url.scheme):
        origin += f":{url.port}"
    return origin


async def _name_taken(db: AsyncSession, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(Target.id).where(Target.name == name)
    if exclude_id is not None:
        stmt = stmt.where(Target.id != exclude_id)
    return (await db.scalar(stmt)) is not None


async def create_target(db: AsyncSession, data: TargetCreate) -> Target:
    """Create a target; allowlist defaults to the base_url origin (D-05)."""
    if await _name_taken(db, data.name):
        raise DuplicateTargetNameError(data.name)

    target = Target(
        name=data.name,
        base_url=str(data.base_url),
        encrypted_username=encrypt(data.credentials.username),
        encrypted_password=encrypt(data.credentials.password),
        origin_allowlist=(
            data.origin_allowlist
            if data.origin_allowlist is not None
            else [_origin_of(data.base_url)]
        ),
        sandbox=data.sandbox,
        budget_overrides=(data.budget_overrides.model_dump() if data.budget_overrides else None),
        is_active=True,
    )
    db.add(target)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateTargetNameError(data.name)
    await db.refresh(target)
    return target


async def list_targets(db: AsyncSession, include_inactive: bool = False) -> list[Target]:
    stmt = select(Target).order_by(Target.id)
    if not include_inactive:
        stmt = stmt.where(Target.is_active.is_(True))
    return list((await db.scalars(stmt)).all())


async def get_target(db: AsyncSession, target_id: int) -> Target | None:
    return await db.scalar(select(Target).where(Target.id == target_id))


async def update_target(db: AsyncSession, target: Target, data: TargetUpdate) -> Target:
    """Partial update (D-07): only provided fields change; credentials replace-if-present."""
    fields = data.model_dump(exclude_unset=True)

    if "name" in fields and fields["name"] != target.name:
        if await _name_taken(db, fields["name"], exclude_id=target.id):
            raise DuplicateTargetNameError(fields["name"])
        target.name = fields["name"]
    if data.base_url is not None:
        target.base_url = str(data.base_url)
    if data.credentials is not None:
        target.encrypted_username = encrypt(data.credentials.username)
        target.encrypted_password = encrypt(data.credentials.password)
    if "origin_allowlist" in fields and fields["origin_allowlist"] is not None:
        target.origin_allowlist = fields["origin_allowlist"]
    if "sandbox" in fields and fields["sandbox"] is not None:
        target.sandbox = fields["sandbox"]
    if "budget_overrides" in fields:
        target.budget_overrides = (
            data.budget_overrides.model_dump() if data.budget_overrides else None
        )
    if "is_active" in fields and fields["is_active"] is not None:
        target.is_active = fields["is_active"]

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise DuplicateTargetNameError(target.name)
    await db.refresh(target)
    return target


async def soft_delete(db: AsyncSession, target: Target) -> None:
    """Deactivate without deleting the row (D-07)."""
    target.is_active = False
    await db.commit()


async def get_decrypted_credentials(db: AsyncSession, target_id: int) -> tuple[str, str]:
    """The SINGLE decrypt surface (T-01-21) — Phase 4 Explorer's entry point."""
    target = await get_target(db, target_id)
    if target is None:
        raise TargetNotFoundError(target_id)
    return decrypt(target.encrypted_username), decrypt(target.encrypted_password)
