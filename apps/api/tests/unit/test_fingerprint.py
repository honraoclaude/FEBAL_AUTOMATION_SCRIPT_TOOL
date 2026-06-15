"""Unit tests for the structural-skeleton fingerprint (Phase 4, EXPL-06) — PURE, zero spend.

The fingerprint is THE experimental unknown: a stable hash of a visited STATE that
  (a) collapses revisits of the same logical screen, and
  (b) distinguishes a TEMPLATE (product list) from INSTANCE data (which/how-many products),
so two runs converge to ~the same graph (the EXPL-05 convergence guarantee).

These tests run on hand-built fixture node trees — NO browser, NO LLM, NO Playwright, NO
spend. They prove the four behaviors from the plan:
  1. template equality  — 6-item vs 4-item list hash IDENTICALLY (fold_siblings=True)
  2. instance collapse   — two renders, different text/ids → identical hash
  3. layout difference   — a different landmark/heading skeleton → different hash
  4. tunable             — fold_siblings=False makes 6-item vs 4-item differ
"""

from __future__ import annotations

from app.services.explorer.fingerprint import (
    DEFAULT_CONFIG,
    FingerprintConfig,
    fingerprint,
    structural_fingerprint,
)
from tests.fixtures.aria import (
    CART_PAGE,
    PRODUCT_LIST_4,
    PRODUCT_LIST_6,
    PRODUCT_LIST_6_ALT,
)


def test_template_equality_folds_instance_count():
    """6-item and 4-item product lists share a skeleton → identical fingerprint (fold ON)."""
    fp6 = structural_fingerprint(PRODUCT_LIST_6, DEFAULT_CONFIG)
    fp4 = structural_fingerprint(PRODUCT_LIST_4, DEFAULT_CONFIG)
    assert fp6 == fp4, "template-equal lists must collapse instance count when fold_siblings"
    # It is a real SHA-256 hex digest.
    assert isinstance(fp6, str) and len(fp6) == 64


def test_instance_collapse_strips_text_and_ids():
    """Two renders of the SAME screen with different text/ids hash identically."""
    fp_a = structural_fingerprint(PRODUCT_LIST_6, DEFAULT_CONFIG)
    fp_b = structural_fingerprint(PRODUCT_LIST_6_ALT, DEFAULT_CONFIG)
    assert fp_a == fp_b, "text + dynamic ids must be stripped before hashing"


def test_layout_difference_hashes_differently():
    """A structurally different page (cart table) hashes differently from a product list."""
    fp_list = structural_fingerprint(PRODUCT_LIST_6, DEFAULT_CONFIG)
    fp_cart = structural_fingerprint(CART_PAGE, DEFAULT_CONFIG)
    assert fp_list != fp_cart, "different landmark/heading skeleton must hash differently"


def test_fold_siblings_false_distinguishes_instance_count():
    """The tunable actually changes behavior: with folding OFF, 6 vs 4 items differ."""
    cfg = FingerprintConfig(fold_siblings=False)
    fp6 = structural_fingerprint(PRODUCT_LIST_6, cfg)
    fp4 = structural_fingerprint(PRODUCT_LIST_4, cfg)
    assert fp6 != fp4, "fold_siblings=False must keep the instance count significant"


def test_default_seam_matches_structural():
    """The module-level `fingerprint(tree)` seam delegates to structural_fingerprint."""
    assert fingerprint(PRODUCT_LIST_6) == structural_fingerprint(PRODUCT_LIST_6, DEFAULT_CONFIG)


def test_max_depth_truncation_changes_hash():
    """max_depth is a tunable: a shallower walk yields a different (coarser) hash."""
    shallow = FingerprintConfig(max_depth=1)
    deep = FingerprintConfig(max_depth=12)
    assert structural_fingerprint(PRODUCT_LIST_6, shallow) != structural_fingerprint(
        PRODUCT_LIST_6, deep
    )


def test_pure_no_browser_dependency():
    """The hashing path IMPORTS no playwright/db/llm — it is a pure function module.

    Parse the module's AST and assert no import statement references a forbidden module
    (docstring mentions are fine — only real imports matter for purity).
    """
    import ast

    import app.services.explorer.fingerprint as fp_mod

    with open(fp_mod.__file__, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    forbidden = ("playwright", "llm_gateway", "neo4j", "sqlalchemy", "session")
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    for mod in imported:
        low = mod.lower()
        assert not any(f in low for f in forbidden), f"fingerprint imports forbidden module {mod}"
