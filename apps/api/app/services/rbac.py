"""Static role->permission map for RBAC (PLAT-04 / D-01).

A STATIC dict, NOT a permissions table (D-01 explicitly rejects a table for four fixed roles;
CLAUDE.md: "no extra library needed for 4 static roles"). The four roles and their permitted
CAPABILITY sets encode the D-01 decision + the 10-UI-SPEC "Cross-cutting: role-gated nav" matrix.

The same map drives two consumers from ONE source of truth:
  - the backend routers (each gates with `require_role(...)` — the security boundary), and
  - the frontend nav/view gating off the role returned by `/me` (UX only, never the boundary).

Capability vocabulary (the verbs/views the platform gates):
  - manage_users       admin role-assignment (POST /api/users/{id}/role) — Admin only
  - manage_scenarios   create/edit/approve suites & scenarios
  - run_executions     launch test runs
  - read               read-only access to platform data
  - dashboard_exec     the Executive dashboard (DASH-01)
  - dashboard_qa       the QA dashboard (DASH-02)
  - dashboard_dev      the Developer dashboard (DASH-03)
  - coverage           the coverage panel (DASH-04)
  - traceability       the traceability viewer (DASH-05)
  - search             search across executions/failures/logs (DASH-06)

Role -> permission summary (D-01):
  - Admin       = ALL capabilities
  - QA Lead     = manage suites/scenarios + ALL dashboards + coverage + traceability + search + read
  - QA Engineer = run executions + QA dashboard + search + read
  - Developer   = read + Developer dashboard + coverage + traceability + search

==============================================================================================
ENDPOINT -> ROLE MATRIX (for Plans 02-05 to wire `require_role(...)` consistently)
==============================================================================================
Each gated router declares a router-level `dependencies=[Depends(require_role(<roles>))]`. This
matrix is the single reference downstream plans copy from so the gates stay consistent with the
capability map above. (Capabilities map to roles via ROLE_PERMISSIONS; the roles column below is
the concrete `require_role(...)` argument list.)

  | Router / Endpoint                         | Capability       | require_role(...) roles                 |
  |-------------------------------------------|------------------|-----------------------------------------|
  | POST /api/users/{id}/role  (Plan 01)      | manage_users     | "admin"                                 |
  | GET  /api/users            (Plan 01)      | manage_users     | "admin"                                 |
  | GET  /api/dashboards/exec  (Plan 02)      | dashboard_exec   | "admin","qa_lead"                       |
  | GET  /api/dashboards/qa    (Plan 02)      | dashboard_qa     | "admin","qa_lead","qa_engineer"         |
  | GET  /api/dashboards/dev   (Plan 02)      | dashboard_dev    | "admin","qa_lead","developer"           |
  | GET  /api/coverage/flows   (Plan 03)      | coverage         | "admin","qa_lead","developer"           |
  | GET  /api/traceability     (Plan 03)      | traceability     | "admin","qa_lead","developer"           |
  | GET  /api/search           (Plan 04)      | search           | "admin","qa_lead","qa_engineer","developer" |

(The `manage_scenarios` / `run_executions` capabilities gate the EXISTING scenarios/executions
routers — those keep their current router-level `Depends(get_current_user)` gate; tightening them
to `require_role(...)` per this matrix is a Plan 02-05 follow-up, NOT this plan's surface.)
"""

from __future__ import annotations

# The four-role vocabulary (String(16) on users.role; D-01 / A2).
ROLES: tuple[str, ...] = ("admin", "qa_lead", "qa_engineer", "developer")

# The full capability vocabulary Admin holds (the union of every permitted set).
_ALL_CAPABILITIES: frozenset[str] = frozenset(
    {
        "manage_users",
        "manage_scenarios",
        "run_executions",
        "read",
        "dashboard_exec",
        "dashboard_qa",
        "dashboard_dev",
        "coverage",
        "traceability",
        "search",
    }
)

# The STATIC role -> permitted-capability map (D-01). Admin gets the full set; the others get
# exactly their decided slice. frozenset so the constant cannot be mutated by a consumer.
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "admin": _ALL_CAPABILITIES,
    "qa_lead": frozenset(
        {
            "read",
            "manage_scenarios",
            "dashboard_exec",
            "dashboard_qa",
            "dashboard_dev",
            "coverage",
            "traceability",
            "search",
        }
    ),
    "qa_engineer": frozenset(
        {
            "read",
            "run_executions",
            "dashboard_qa",
            "search",
        }
    ),
    "developer": frozenset(
        {
            "read",
            "dashboard_dev",
            "coverage",
            "traceability",
            "search",
        }
    ),
}


def can(role: str, capability: str) -> bool:
    """True iff `role` holds `capability` (deny-by-default for an unknown role; never raises).

    The pure helper the routers and the /me-driven frontend both reason from — one source of
    truth for "what may this role do."
    """
    return capability in ROLE_PERMISSIONS.get(role, frozenset())
