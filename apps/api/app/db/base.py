"""Declarative base — all models inherit; alembic target_metadata = Base.metadata."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
