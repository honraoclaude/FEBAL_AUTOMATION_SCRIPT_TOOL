"""Auth request/response schemas (plan 01-03 interfaces contract)."""

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
