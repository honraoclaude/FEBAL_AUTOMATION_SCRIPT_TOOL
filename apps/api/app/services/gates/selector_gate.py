"""Static freehand-selector gate (GEN-05a / D-05) — the AST cousin of the single-write-path grep.

EVERY locator in generated automation comes from the Phase-5 Element Repository by element key;
the LLM/template fills ONLY non-locator slots. This gate STATICALLY scans rendered `.py` source
and REJECTS any freehand selector literal in a SPEC/STEP module. Page-object modules are the
single sanctioned home for a literal locator — and even there each literal must be traceable to a
repo chain entry (`assert_page_object_literals_are_repo_sourced`, asserted by the unit suite).

Detection (RESEARCH Novel Mechanism 3):
  - AST-walk for Call nodes whose func is a SELECTOR SINK with a Constant str FIRST arg:
      page.locator / page.fill / page.click / page.type / page.hover / page.dblclick /
      page.check / page.uncheck / page.press / page.select_option / page.wait_for_selector
      with a CSS-string first arg, AND
      get_by_role / get_by_text / get_by_test_id / get_by_label / get_by_placeholder
      (any string-literal first arg).
  - Regex FALLBACK for raw CSS/XPath/attr string CONSTANTS (^#, ^., ^//, [attr=]) anywhere in
    spec/step source — catches a selector parked in a module constant before it reaches a sink.
  - ALLOWED: page-object ATTRIBUTE references (self.login_button / inventory_page.add_to_cart) —
    these resolve to a repo-sourced Locator in the page-object layer, never a literal here.
  - UNLESS is_page_object: a page-object module is the sanctioned literal home, so no violation.

PURE: operates on a source STRING (no I/O, no neo4j, no keys) — unit-testable on rendered
fixtures. Conceptually the AST cousin of the Phase-4 single-write-path grep gate.
"""

from __future__ import annotations

import ast
import re

# The Playwright selector-sink method names. get_by_* always take a string-literal locator;
# the page.* navigation/interaction methods take a CSS/selector string as their FIRST arg.
_GET_BY_SINKS = frozenset(
    {
        "get_by_role",
        "get_by_text",
        "get_by_test_id",
        "get_by_label",
        "get_by_placeholder",
        "get_by_alt_text",
        "get_by_title",
    }
)
_CSS_FIRST_ARG_SINKS = frozenset(
    {
        "locator",
        "fill",
        "click",
        "type",
        "hover",
        "dblclick",
        "check",
        "uncheck",
        "press",
        "select_option",
        "set_input_files",
        "wait_for_selector",
        "query_selector",
        "query_selector_all",
        "is_visible",
        "is_enabled",
        "is_checked",
        "input_value",
        "text_content",
        "inner_text",
        "get_attribute",
    }
)

# Regex fallback: a raw CSS/XPath/attr selector parked in a string CONSTANT. A leading '#'
# (id), '.' (class), '//' (xpath), or an '[attr=...]' attribute selector are unambiguous.
_RAW_SELECTOR_RE = re.compile(r"^\s*(#[\w-]|\.[\w-]|//|\[[\w-]+\s*[~|^$*]?=)")


class SelectorGateError(Exception):
    """Raised when a freehand selector literal is found in a spec/step module (or a page-object
    literal is not traceable to a repo chain entry)."""


def _is_str_constant(node: ast.expr | None) -> str | None:
    """Return the string value if node is a `str` Constant, else None."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


class _SinkVisitor(ast.NodeVisitor):
    """Collect selector-sink Call violations (string-literal first arg into a sink method)."""

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 (ast visitor naming)
        func = node.func
        if isinstance(func, ast.Attribute):
            method = func.attr
            first = node.args[0] if node.args else None
            literal = _is_str_constant(first)
            if literal is not None and (
                method in _GET_BY_SINKS or method in _CSS_FIRST_ARG_SINKS
            ):
                self.violations.append(
                    f"freehand selector literal in {method}(...): {literal!r}"
                )
        self.generic_visit(node)


def _string_constants(tree: ast.AST) -> list[str]:
    """Every str Constant in the tree (for the raw CSS/XPath regex fallback)."""
    return [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def scan_for_freehand_selectors(source: str, *, is_page_object: bool) -> list[str]:
    """Return a list of freehand-selector violation descriptions for `source`.

    In a SPEC/STEP module (is_page_object=False): any selector-sink string-literal first arg,
    and any raw CSS/XPath/attr string constant, is a violation. In a PAGE-OBJECT module
    (is_page_object=True): literals are the sanctioned home — returns [].
    """
    if is_page_object:
        return []

    tree = ast.parse(source)
    visitor = _SinkVisitor()
    visitor.visit(tree)
    violations = list(visitor.violations)

    # Regex fallback: raw CSS/XPath/attr string constants parked outside a sink call.
    for value in _string_constants(tree):
        if _RAW_SELECTOR_RE.match(value):
            desc = f"raw selector string constant: {value!r}"
            if desc not in violations:
                violations.append(desc)
    return violations


def assert_no_freehand_selectors(source: str, *, is_page_object: bool) -> None:
    """Raise SelectorGateError if `source` contains any freehand selector (the codegen caller).

    Page-object modules pass unconditionally (their literals are repo-traceable by construction;
    `assert_page_object_literals_are_repo_sourced` is the complementary check codegen runs).
    """
    violations = scan_for_freehand_selectors(source, is_page_object=is_page_object)
    if violations:
        raise SelectorGateError(
            "freehand selector(s) rejected (locators must come from the Element Repository):\n"
            + "\n".join(violations)
        )


def assert_page_object_literals_are_repo_sourced(
    source: str, repo_chains: set[str]
) -> None:
    """Assert EVERY locator literal in a page-object module equals a supplied repo chain entry.

    Page objects are the only place a literal locator may live; this proves each such literal was
    sourced from the Element Repository (never invented). Walks the selector-sink Calls (the same
    sinks the gate detects) and requires each string-literal first arg ∈ repo_chains.
    """
    tree = ast.parse(source)
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            method = node.func.attr
            if method in _GET_BY_SINKS or method in _CSS_FIRST_ARG_SINKS:
                first = node.args[0] if node.args else None
                literal = _is_str_constant(first)
                if literal is not None and literal not in repo_chains:
                    offenders.append(literal)
    if offenders:
        raise SelectorGateError(
            "page-object locator literal(s) not traceable to a repo chain entry: "
            + ", ".join(repr(o) for o in offenders)
        )
