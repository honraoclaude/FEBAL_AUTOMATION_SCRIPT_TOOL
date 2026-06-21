"""SQLAlchemy models — one module per table; alembic/env.py imports each for autogenerate."""

from app.models.execution_history import TestArtifact, TestResult, TestRun

__all__ = ["TestArtifact", "TestResult", "TestRun"]
