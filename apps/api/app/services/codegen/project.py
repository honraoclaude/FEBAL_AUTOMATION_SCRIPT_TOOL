"""Element-Repository-sourced Playwright project codegen (GEN-04 / GEN-05a / D-05/D-06).

Turn the APPROVED scenarios of a run into a full Playwright project tree under the run-scoped
gitignored workspaces path:

    workspaces/<run_id>/<target>/
        pages/      <- a Page Object per KG page (locators = repo chain entries)
        steps/      <- pytest-bdd step-defs bound to each approved .feature
        features/   <- the approved .feature files
        fixtures/   <- shared fixtures (per scenario)
        utils/      <- deterministic helpers
        data/       <- dataclass models from the scenario-outline Examples columns
        reports/    <- (created empty; the runner writes here)
        conftest.py <- pytest-playwright wiring + env-overridable base URL

INVARIANTS (carried from Phase 3/5):
  - Jinja2 owns ALL structure; the LLM fills only NON-locator slots. Selectors are TEMPLATE
    LOOKUPS from the Element Repository (codegen.locators), never slots, never freehand.
  - Codegen reads ONLY status=approved scenarios (scenario_service.list_approved — D-01).
  - For EVERY rendered .py: ast.parse it (a non-importable render raises GenerationError BEFORE
    write — the Phase-3 invariant), THEN run the freehand-selector gate
    (assert_no_freehand_selectors) — a literal in a spec/step REJECTS the whole codegen (no
    partial write). Page objects pass with is_page_object=True (their literals are repo-traceable
    by construction) and are additionally asserted repo-sourced.
  - Read-only Cypher for locator reads (single-write-path grep gate stays green).

The whole tree is rendered + gated IN MEMORY first; only when every file passes BOTH the
ast.parse and the selector gate is anything written to disk (no partial write on a violation).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import structlog
from jinja2 import Environment, FileSystemLoader, select_autoescape
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.neo4j_driver import get_neo4j
from app.core.workspaces import run_dir as _ws_run_dir
from app.services import scenario_service
from app.services.codegen.examples import derive_examples
from app.services.codegen.locators import page_object_locators
from app.services.gates.gherkin_lint import GenerationError
from app.services.gates.selector_gate import (
    assert_no_freehand_selectors,
    assert_page_object_literals_are_repo_sourced,
)
from app.services.kg import reader
from app.services.kg.flows import build_flows

log = structlog.get_logger()

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "templates"
_NON_IDENT = re.compile(r"[^0-9a-zA-Z]+")

# The default target subtree name + the base-url env var the conftest reads (Slice 4 overrides it).
_TARGET = "target"
_BASE_URL_ENV = "TARGET_BASE_URL"
_DEFAULT_BASE_URL = "http://saucedemo:80"

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=(), default=False),
    keep_trailing_newline=True,
)


def _pascal(text: str) -> str:
    """Deterministic PascalCase identifier from arbitrary text (KG page title / feature name)."""
    parts = [p for p in _NON_IDENT.split(text or "") if p]
    name = "".join(p[:1].upper() + p[1:] for p in parts) or "Page"
    if name[0].isdigit():
        name = f"P{name}"
    return name


def _snake(text: str) -> str:
    """Deterministic snake_case identifier from arbitrary text (module/feature file names)."""
    name = _NON_IDENT.sub("_", (text or "").lower()).strip("_") or "page"
    if name[0].isdigit():
        name = f"p_{name}"
    return name


def _render_checked_py(template_name: str, *, is_page_object: bool, **slots) -> str:
    """Render a .py template, ast.parse it (GenerationError on failure), then run the selector gate.

    Returns the rendered source. Page-object literals are allowed (is_page_object=True); a
    freehand literal in a spec/step raises SelectorGateError (which propagates — no partial write).
    """
    rendered = _jinja_env.get_template(template_name).render(**slots)
    try:
        ast.parse(rendered)
    except SyntaxError as exc:
        raise GenerationError(
            f"rendered {template_name} is not valid Python: {exc}"
        ) from exc
    assert_no_freehand_selectors(rendered, is_page_object=is_page_object)
    return rendered


async def _pages_for_flows(flows: list[dict], *, driver: AsyncDriver | None) -> dict[str, dict]:
    """Collect {fingerprint: page_detail} for every page on the given flows (read-only)."""
    fps: list[str] = []
    for flow in flows:
        for fp in flow.get("node_fps") or []:
            if fp not in fps:
                fps.append(fp)
    pages: dict[str, dict] = {}
    for fp in fps:
        detail = await reader.page_detail(fp, driver=driver)
        if detail:
            pages[fp] = detail
    return pages


async def generate_project(
    db: AsyncSession, run_id: str, *, driver: AsyncDriver | None = None
) -> str:
    """Generate the full Playwright project tree from the run's APPROVED scenarios. Returns root.

    Reads scenario_service.list_approved (D-01 — approved only); mines the run's flows to find the
    KG pages on those flows; renders page objects (repo locators), the approved .feature(s), the
    bound pytest-bdd step-defs, and conftest/fixtures/utils/data. Every rendered .py is ast-parsed
    + selector-gated BEFORE any write (no partial write on a violation). Page-object literals are
    additionally asserted repo-sourced.
    """
    drv = driver or get_neo4j()

    approved = await scenario_service.list_approved(db, run_id)
    if not approved:
        raise GenerationError(
            f"no approved scenarios for run {run_id} — nothing to codegen (D-01)"
        )

    graph = await reader.flows_source(driver=drv)
    flows = await build_flows(graph, run_id)
    flows_by_id = {f.get("id"): f for f in flows}
    pages = await _pages_for_flows(flows, driver=drv)

    # Render EVERYTHING in memory; write only after all gates pass (no partial write).
    files: dict[str, str] = {}

    # --- Page objects (one per KG page on the approved flows) — repo-sourced locators --------
    page_module_for_fp: dict[str, str] = {}
    page_class_for_fp: dict[str, str] = {}
    for fp, detail in pages.items():
        locators = await page_object_locators(fp, driver=drv)
        class_name = _pascal(detail.get("title") or detail.get("url") or fp)
        module = _snake(detail.get("title") or detail.get("url") or fp)
        page_module_for_fp[fp] = module
        page_class_for_fp[fp] = class_name
        source = _render_checked_py(
            "pages/page_object.py.j2",
            is_page_object=True,
            class_name=class_name,
            page_url=detail.get("url") or "",
            locators=locators,
        )
        # Page-object literals MUST equal a repo chain entry (repo-traceable by construction).
        assert_page_object_literals_are_repo_sourced(source, set(locators.values()))
        files[f"pages/{module}.py"] = source

    files["pages/__init__.py"] = ""

    # A fallback page object when a scenario's flow has no usable KG page (keeps steps importable).
    if not pages:
        files["pages/target_page.py"] = _render_checked_py(
            "pages/page_object.py.j2",
            is_page_object=True,
            class_name="TargetPage",
            page_url=_DEFAULT_BASE_URL,
            locators={},
        )

    def _page_for_scenario(row) -> tuple[str, str]:
        """The (module, class) of the page a scenario's flow lands on (terminal page)."""
        flow = flows_by_id.get(row.flow_id)
        if flow:
            for fp in reversed(flow.get("node_fps") or []):
                if fp in page_module_for_fp:
                    return page_module_for_fp[fp], page_class_for_fp[fp]
        # Fall back to any rendered page object, else the synthesized TargetPage.
        if page_module_for_fp:
            first_fp = next(iter(page_module_for_fp))
            return page_module_for_fp[first_fp], page_class_for_fp[first_fp]
        return "target_page", "TargetPage"

    # --- Features + bound step-defs + data models (one set per approved scenario) ------------
    for row in approved:
        slug = _snake(f"{row.feature_name}_{row.id}")
        feature_rel = f"../features/{slug}.feature"
        feature_path = f"features/{slug}.feature"
        files[feature_path] = (
            row.gherkin_text
            if row.gherkin_text.endswith("\n")
            else row.gherkin_text + "\n"
        )

        page_module, page_class = _page_for_scenario(row)
        files[f"steps/test_{slug}.py"] = _render_checked_py(
            "steps/steps.py.j2",
            is_page_object=False,
            feature_rel=feature_rel,
            page_module=page_module,
            page_class=page_class,
            base_url_env=_BASE_URL_ENV,
        )

        # Data model from the scenario-outline Examples columns (KG-derived; LLM never invents).
        flow = flows_by_id.get(row.flow_id)
        columns: list[str] = []
        if flow:
            for fp in reversed(flow.get("node_fps") or []):
                detail = pages.get(fp)
                if detail:
                    columns = derive_examples(detail).get("columns", [])
                    break
        files[f"data/{slug}_data.py"] = _render_checked_py(
            "data_model.py.j2",
            is_page_object=False,
            model_name=f"{_pascal(row.feature_name)}Row",
            columns=[_snake(c) for c in columns],
        )

    files["steps/__init__.py"] = ""
    files["data/__init__.py"] = ""

    # --- Project-wide files (conftest / fixtures / utils) -----------------------------------
    files["conftest.py"] = _render_checked_py(
        "conftest.py.j2",
        is_page_object=False,
        base_url_env=_BASE_URL_ENV,
        default_base_url=_DEFAULT_BASE_URL,
    )
    files["fixtures/__init__.py"] = ""
    files["fixtures/data_fixtures.py"] = _render_checked_py(
        "fixtures.py.j2", is_page_object=False, run_id=run_id
    )
    files["utils/__init__.py"] = ""
    files["utils/helpers.py"] = _render_checked_py(
        "utils.py.j2", is_page_object=False
    )

    # --- Write the tree (only now that EVERY file passed ast.parse + the selector gate) -------
    root = _ws_run_dir(run_id, create=True) / _TARGET
    for rel, content in files.items():
        dest = root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(content, encoding="utf-8")
    (root / "reports").mkdir(parents=True, exist_ok=True)

    log.info("generate_project_written", run_id=run_id, root=str(root), files=len(files))
    return str(root)
