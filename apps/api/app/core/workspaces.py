"""Single source of truth for the artifact workspaces root + spec path convention.

generate-scripts WRITES the run's spec and /execute DISCOVERS it; both MUST agree on
where workspaces/<run_id>/test_login.py lives. The layout differs between host/hybrid
(repo-root workspaces/) and the container (WORKDIR /app, no apps/api/ ancestor), so the
root is resolved from settings.workspaces_dir when set, else from this file's location.

Host/hybrid: app/core/workspaces.py -> core -> app -> api -> apps -> repo root.
Container:   settings.workspaces_dir = /app/workspaces (compose env + bind mount).
"""

from pathlib import Path

from app.core.config import settings

# The spec filename is fixed by the Jinja2 skeleton (generation renders test_login.py).
SPEC_FILENAME = "test_login.py"


def workspaces_root() -> Path:
    """The gitignored workspaces/ root — settings override else repo-root (host layout)."""
    if settings.workspaces_dir:
        return Path(settings.workspaces_dir)
    # app/core/workspaces.py -> parents: core(0) app(1) api(2) apps(3) repo-root(4).
    return Path(__file__).resolve().parents[4] / "workspaces"


def run_dir(run_id: str, *, create: bool = False) -> Path:
    """workspaces/<run_id>/ — created on demand when create=True (the writer path)."""
    d = workspaces_root() / run_id
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def spec_path(run_id: str) -> Path:
    """workspaces/<run_id>/test_login.py — the run_id-derived spec convention (T-01-26)."""
    return run_dir(run_id) / SPEC_FILENAME
