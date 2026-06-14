"""Generation service (PLAT-02, D-07) — the metered generate-bdd / generate-scripts seam.

Slice B of the tracer: read the explored graph for a run_id, route BOTH generation steps
through the Phase-2 LLM gateway (the ONLY money-control surface — D-07), validate the
generated Gherkin with gherkin-official BEFORE writing, render a runnable pytest-playwright
spec from a Jinja2 skeleton (the LLM fills ONLY crawl-observed SauceDemo selectors —
Pitfall 5), and write both artifacts under workspaces/<run_id>/.

CRITICAL invariants:
  - D-07 / T-03-14: generate_bdd and generate_scripts call llm_gateway.complete() with the
    slice run_id — NEVER a direct provider-SDK chat call. The gateway owns budgets, the
    kill-switch, caching, and the cost ledger.
  - T-03-12: the .feature is validated by gherkin-official's Parser BEFORE any file is
    written; malformed Gherkin raises GenerationError and writes NOTHING.
  - Pitfall 5 / T-03-11: the LLM fills NARROW slots only. The Jinja2 template
    (templates/test_login.py.j2) owns ALL spec structure and every selector
    (#user-name, #password, #login-button, .inventory_list). Selectors are never
    free-hand LLM output.
  - PLAT-07 / T-03-10: SauceDemo's PUBLIC demo creds are used as literal template values;
    target ciphertext / decrypted creds NEVER enter a prompt or an artifact.

The run_id threads explore -> generate -> (Plan 04) execute: the rendered spec_path is
returned so the execute path can find it.
"""

import ast
from pathlib import Path

import structlog
from gherkin.parser import Parser
from jinja2 import Environment, FileSystemLoader, select_autoescape
from neo4j import AsyncDriver
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.neo4j_driver import get_neo4j
from app.core.workspaces import run_dir as _ws_run_dir
from app.core.workspaces import (  # noqa: F401 -- re-exported for 03-03 unit tests
    workspaces_root as _workspaces_root,
)
from app.services import llm_gateway

log = structlog.get_logger()

# The ONLY selectors the crawl OBSERVED for SauceDemo (Pitfall 5 / A4). The LLM may use
# ONLY these — they are hard-coded in the Jinja2 template, never free-hand LLM output.
OBSERVED_SELECTORS = ("#user-name", "#password", "#login-button", ".inventory_list")

# SauceDemo public demo credentials — literal template values, NEVER target ciphertext
# (PLAT-07 / T-03-10). These are the well-known public Swag Labs demo creds.
_SAUCEDEMO_USER = "standard_user"
_SAUCEDEMO_PASSWORD = "secret_sauce"
_SAUCEDEMO_BASE_URL = "https://www.saucedemo.com"

# Token budgets kept small — the LLM fills narrow slots, not whole files.
_BDD_MAX_TOKENS = 512
_SCRIPTS_MAX_TOKENS = 256

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
_SPEC_TEMPLATE = "test_login.py.j2"

# Jinja2 environment over app/templates/. autoescape off for .py output (we render Python,
# not HTML); structure is owned by the template and values flow through `tojson`.
_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(enabled_extensions=(), default=False),
    keep_trailing_newline=True,
)


class GenerationError(Exception):
    """Raised when generation fails (malformed Gherkin, unrenderable spec, etc.).

    On a Gherkin validation failure NO .feature is written — the file write happens only
    AFTER the parser accepts the text (T-03-12).
    """


def _run_dir(run_id: str) -> Path:
    """workspaces/<run_id>/ — created on demand; both artifacts land here, keyed by run_id.

    Delegates to app.core.workspaces so generate-scripts WRITES to the SAME root /execute
    DISCOVERS from (settings.workspaces_dir in the container, repo-root on the host).
    """
    return _ws_run_dir(run_id, create=True)


def validate_gherkin(text: str) -> None:
    """Validate Gherkin with gherkin-official BEFORE writing (Pattern 5, T-03-12).

    `Parser().parse(...)` raises (CompositeParserException / token errors) on malformed
    input. We wrap any parser failure as GenerationError so the caller can decide WITHOUT
    a file ever being written.
    """
    try:
        Parser().parse(text)
    except Exception as exc:  # noqa: BLE001 -- any parse failure => reject before write
        raise GenerationError(f"invalid Gherkin: {exc}") from exc


async def _read_observed_pages(driver: AsyncDriver, run_id: str) -> list[dict]:
    """Read the explored Page nodes for this run_id to GROUND the prompt (best-effort).

    Returns a list of {url, title} dicts (parameterized Cypher, T-03-05). On any graph
    error (neo4j down for a unit run, no nodes yet) returns [] — generation stays grounded
    in the deterministic OBSERVED selectors regardless, so a missing graph never blocks
    the tracer. The unit tests mock the gateway and do not require a live graph.
    """
    cypher = (
        "MATCH (p:Page) WHERE p.run_id = $run_id "
        "RETURN p.url AS url, p.title AS title ORDER BY p.url"
    )
    try:
        async with driver.session() as session:
            result = await session.run(cypher, run_id=run_id)
            records = await result.data()
        return [{"url": r.get("url"), "title": r.get("title")} for r in records]
    except Exception as exc:  # noqa: BLE001 -- graph absence must not block generation
        log.info("generation_graph_read_skipped", run_id=run_id, error=str(exc))
        return []


def _bdd_messages(run_id: str, pages: list[dict]) -> list[dict]:
    """Prompt for generate-bdd: ground the model in the observed login flow.

    Feeds ONLY the deterministic observed selectors + page metadata (never raw page DOM —
    T-03-11). Asks for a single valid Gherkin Feature for the SauceDemo login.
    """
    page_lines = "\n".join(
        f"- {p.get('url')} ({p.get('title')})" for p in pages
    ) or "- (no graph nodes available; generate from the known SauceDemo login flow)"
    return [
        {
            "role": "system",
            "content": (
                "You write a SINGLE valid Gherkin Feature for a SauceDemo login flow. "
                "Output ONLY Gherkin (Feature/Scenario/Given/When/Then), no code fences, "
                "no prose. Use exactly one Scenario."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Explored pages for run {run_id}:\n{page_lines}\n\n"
                f"Observed selectors: {', '.join(OBSERVED_SELECTORS)}.\n"
                "Write a Gherkin Feature 'Login' with one Scenario that logs in as a "
                "standard user and lands on the inventory page."
            ),
        },
    ]


def _scripts_messages(run_id: str) -> list[dict]:
    """Prompt for generate-scripts: the LLM fills ONLY a narrow scenario label.

    The Jinja2 template owns ALL structure and every selector. We constrain the model to
    the OBSERVED selector set and ask for a short identifier-safe scenario name only —
    never control flow, never a selector (Pitfall 5).
    """
    return [
        {
            "role": "system",
            "content": (
                "You provide ONLY a short, human-readable scenario label (a few words) "
                "for a SauceDemo login test. Do NOT write code or selectors."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Run {run_id}. Allowed selectors are fixed: "
                f"{', '.join(OBSERVED_SELECTORS)}. "
                "Give a one-line scenario label for logging into SauceDemo as a "
                "standard user and reaching the inventory page."
            ),
        },
    ]


def _sanitize_scenario_label(text: str | None) -> str:
    """Reduce free-form LLM text to a safe single-line label (defense in depth).

    The label only ever lands in a docstring slot via Jinja2 `tojson`, but we still strip
    it to a single trimmed line and cap length so nothing odd leaks into the rendered file.
    """
    if not text:
        return "SauceDemo login"
    first_line = text.strip().splitlines()[0].strip()
    cleaned = first_line.strip("\"'` ")
    return cleaned[:80] or "SauceDemo login"


async def generate_bdd(db: AsyncSession, run_id: str) -> str:
    """Generate + gherkin-validate a .feature for run_id; write it ONLY if valid (D-07).

    Routes through llm_gateway.complete(operation_type="generate-bdd", run_id=run_id) —
    the ONLY LLM path. Validates result.content with gherkin-official BEFORE writing; on
    a malformed result raises GenerationError and writes NOTHING (T-03-12). Returns the
    written feature path.
    """
    pages = await _read_observed_pages(get_neo4j(), run_id)
    result = await llm_gateway.complete(
        db,
        _bdd_messages(run_id, pages),
        operation_type="generate-bdd",
        run_id=run_id,
        max_tokens=_BDD_MAX_TOKENS,
    )
    text = result.content
    if not text or not text.strip():
        raise GenerationError("gateway returned empty Gherkin")

    # VALIDATE BEFORE WRITE (T-03-12): a malformed feature never reaches disk.
    validate_gherkin(text)

    feature_path = _run_dir(run_id) / "login.feature"
    feature_path.write_text(text, encoding="utf-8")
    log.info("generate_bdd_written", run_id=run_id, feature_path=str(feature_path))
    return str(feature_path)


async def generate_scripts(db: AsyncSession, run_id: str) -> str:
    """Render a runnable pytest-playwright spec for run_id from the Jinja2 skeleton (D-07).

    Routes through llm_gateway.complete(operation_type="generate-scripts", run_id=run_id)
    to fill ONLY a narrow scenario label; the Jinja2 template owns ALL structure and every
    (observed) selector (Pitfall 5). Renders templates/test_login.py.j2 with SauceDemo's
    PUBLIC demo creds as literal values (never target ciphertext — PLAT-07), verifies the
    rendered output is ast-parseable, writes workspaces/<run_id>/test_login.py, and returns
    that spec_path (for executions.spec_path in Plan 04).
    """
    result = await llm_gateway.complete(
        db,
        _scripts_messages(run_id),
        operation_type="generate-scripts",
        run_id=run_id,
        max_tokens=_SCRIPTS_MAX_TOKENS,
    )
    scenario_name = _sanitize_scenario_label(result.content)

    template = _jinja_env.get_template(_SPEC_TEMPLATE)
    rendered = template.render(
        base_url=_SAUCEDEMO_BASE_URL,
        username=_SAUCEDEMO_USER,
        password=_SAUCEDEMO_PASSWORD,
        scenario_name=scenario_name,
    )

    # The rendered spec MUST be importable Python (ast-parseable) before we write it.
    try:
        ast.parse(rendered)
    except SyntaxError as exc:
        raise GenerationError(f"rendered spec is not valid Python: {exc}") from exc

    spec_path = _run_dir(run_id) / "test_login.py"
    spec_path.write_text(rendered, encoding="utf-8")
    log.info("generate_scripts_written", run_id=run_id, spec_path=str(spec_path))
    return str(spec_path)
