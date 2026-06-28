"""Static role->permission map proof (PLAT-04 / D-01) — pure, keyless.

`app.services.rbac` holds the STATIC `ROLE_PERMISSIONS` dict (NOT a permissions table, D-01)
mapping each of the four roles to its permitted capability set, plus a pure `can(role, cap)`
helper the routers and the /me-driven frontend both reason from.

D-01 + the 10-UI-SPEC "Cross-cutting: role-gated nav" matrix:
  - Admin        = ALL capabilities
  - QA Lead      = manage suites/scenarios + ALL dashboards + coverage + traceability + search
  - QA Engineer  = run executions + QA dashboard + search
  - Developer    = read + Developer dashboard + coverage + traceability + search

Run: cd apps/api && uv run python -m pytest tests/unit/test_rbac_map.py -x -q
"""

from __future__ import annotations

import pytest

from app.services.rbac import ROLE_PERMISSIONS, ROLES, can


def test_exactly_four_roles() -> None:
    """ROLE_PERMISSIONS contains EXACTLY the four roles (no more, no fewer)."""
    assert set(ROLE_PERMISSIONS) == {"admin", "qa_lead", "qa_engineer", "developer"}
    assert set(ROLES) == {"admin", "qa_lead", "qa_engineer", "developer"}


def test_admin_has_everything() -> None:
    """Admin = all capabilities — can(...) is True for every capability any role holds."""
    every_cap = set().union(*ROLE_PERMISSIONS.values())
    for cap in every_cap:
        assert can("admin", cap) is True, f"admin should hold {cap}"


def test_qa_engineer_run_plus_qa_dashboard_plus_search() -> None:
    """QA Engineer = run executions + QA dashboard + search; NOT manage, NOT admin."""
    assert can("qa_engineer", "run_executions") is True
    assert can("qa_engineer", "dashboard_qa") is True
    assert can("qa_engineer", "search") is True
    # Denied: cannot manage scenarios/suites, cannot reach the exec/dev dashboards or user admin.
    assert can("qa_engineer", "manage_scenarios") is False
    assert can("qa_engineer", "dashboard_exec") is False
    assert can("qa_engineer", "manage_users") is False


def test_developer_read_plus_dev_dashboard_plus_coverage_traceability_search() -> None:
    """Developer = read + Developer dashboard + coverage + traceability + search; NOT run/manage."""
    assert can("developer", "dashboard_dev") is True
    assert can("developer", "coverage") is True
    assert can("developer", "traceability") is True
    assert can("developer", "search") is True
    # Denied: cannot run executions, cannot manage, cannot reach QA/exec dashboards or user admin.
    assert can("developer", "run_executions") is False
    assert can("developer", "manage_scenarios") is False
    assert can("developer", "dashboard_qa") is False
    assert can("developer", "manage_users") is False


def test_qa_lead_manage_plus_all_dashboards_plus_coverage_traceability_search() -> None:
    """QA Lead = manage suites/scenarios + ALL dashboards + coverage + traceability + search."""
    assert can("qa_lead", "manage_scenarios") is True
    assert can("qa_lead", "dashboard_exec") is True
    assert can("qa_lead", "dashboard_qa") is True
    assert can("qa_lead", "dashboard_dev") is True
    assert can("qa_lead", "coverage") is True
    assert can("qa_lead", "traceability") is True
    assert can("qa_lead", "search") is True
    # Denied: QA Lead is not an admin — cannot manage users/roles.
    assert can("qa_lead", "manage_users") is False


def test_only_admin_manages_users() -> None:
    """manage_users (role assignment) is Admin-only across all four roles."""
    assert can("admin", "manage_users") is True
    for role in ("qa_lead", "qa_engineer", "developer"):
        assert can(role, "manage_users") is False


def test_can_unknown_role_is_false() -> None:
    """An unknown role grants nothing (deny-by-default, never a KeyError)."""
    assert can("superuser", "search") is False
    assert can("", "search") is False
