"""Auth request/response schemas (plan 01-03 interfaces contract)."""

from typing import Literal

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class MeResponse(BaseModel):
    id: int
    email: str
    # PLAT-04 / D-01: the caller's RBAC role (admin | qa_lead | qa_engineer | developer). The
    # frontend gates nav/views off this; it is read off the User row, never from the JWT.
    role: str


class UserSummary(BaseModel):
    """One row in the admin user list (GET /api/users) — id/email/role only (no secrets)."""

    id: int
    email: str
    role: str


# The four-role vocabulary, validated at the schema boundary so an invalid role 422s before any
# DB write (T-10: the body role is the value being ASSIGNED, never an authorization claim).
RoleLiteral = Literal["admin", "qa_lead", "qa_engineer", "developer"]


class RoleAssignRequest(BaseModel):
    """POST /api/users/{id}/role body — the role to assign (Literal -> 422 on an unknown role)."""

    role: RoleLiteral
