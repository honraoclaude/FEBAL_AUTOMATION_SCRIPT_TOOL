"""Run/Execution API schemas (PLAT-02, D-04).

Request: ExploreRequest (the POST /explore body — just a target_id).
Responses: RunResponse / ExecutionResponse are ORM-readable (from_attributes) so
routers build them straight from a Run/Execution row. RunStatus is the small
run_id-keyed poll shape GET /executions/{run_id} returns for BOTH paths.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExploreRequest(BaseModel):
    """POST /explore body — explore the registered target with this id."""

    target_id: int = Field(ge=1)


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    kind: str
    target_id: int | None
    status: str
    error: str | None
    created_at: datetime


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    spec_path: str
    status: str
    exit_code: int | None
    output: str | None
    created_at: datetime


class RunStatus(BaseModel):
    """The single run_id-keyed poll surface (resolves Execution row else Run row)."""

    run_id: str
    kind: str
    status: str
    error: str | None = None
