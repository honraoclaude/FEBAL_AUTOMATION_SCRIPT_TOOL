"""Execution-engine API schemas (EXEC-01/03/04/05).

Request: ExecuteTierRequest (the POST /execute body — which tier to run).
Responses: TestRunResponse / TestResultResponse / TestArtifactResponse are ORM-readable
(from_attributes=True) so routers build them straight from a TestRun/TestResult/TestArtifact
row. Mirrors schemas/run.py exactly (ConfigDict(from_attributes=True), Field on the request).
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecuteTierRequest(BaseModel):
    """POST /execute body — run the named tier (smoke | sanity | regression | full)."""

    tier: str = Field(min_length=1)


class TestRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    tier: str
    selector: str | None
    status: str
    total: int
    passed: int
    failed: int
    flaky: int
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime


class TestResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    flow_id: str
    verdict: str
    attempts: int
    exit_codes: list
    duration_ms: int | None
    created_at: datetime


class TestArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    run_id: str
    flow_id: str
    kind: str
    path: str
    created_at: datetime
