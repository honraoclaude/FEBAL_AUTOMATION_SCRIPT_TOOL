"""Structural-skeleton state fingerprint (Phase 4, EXPL-06) — THE experimental unknown.

A PURE, tunable hash of a visited STATE that:
  (a) collapses revisits of the same logical screen (so the converge node dedups by
      structure, not URL), and
  (b) distinguishes a TEMPLATE (e.g. "product list") from INSTANCE data (which/how-many
      products) so two consecutive runs converge to ~the same graph (EXPL-05).

This module REPLACES the Slice-1 `actions.page_key` URL stand-in (the `# TEMP` marker) as
the converge node's dedup key.

Algorithm (RESEARCH "Fingerprint Normalization", Candidate A — structural skeleton):
  Walk the normalized node tree depth-first; at each node keep `role-or-tag` + the sorted
  subset of attributes in `cfg.kept_attrs` (structural ARIA only) and STRIP everything that
  is instance data: text content, id / dynamic attribute VALUES, numbers, href query
  strings. When `cfg.fold_siblings` is True, collapse runs of structurally-identical sibling
  subtrees to a SINGLE representative + a count-agnostic marker — this is exactly what
  separates a template from its instance count (6 items vs 4 items hash identically).
  Serialize `depth:role:attrs` lines and SHA-256 the join.

PURITY (load-bearing): the hashing path imports NOTHING from playwright / llm_gateway /
neo4j / the DB. `structural_fingerprint(tree, cfg)` consumes a plain node tree
    {"role": str, "tag": str | None, "attrs": {str: str}, "children": [<node>, ...]}
so it is unit-testable on hand-built fixtures with zero stack. The thin
`normalize_aria_tree` adapter (which DOES touch a Playwright page) is kept SEPARATE so the
hash stays pure.

UPGRADE PATH (Candidate B — SimHash near-duplicate): the public seam is the module-level
`fingerprint(tree, cfg=DEFAULT_CONFIG) -> str`. A SimHash-over-structural-shingles
implementation can drop in behind this same signature later (returning a bucket id) without
touching any caller — the converge node, the convergence proof, and the Neo4j MERGE key all
go through `fingerprint(...)`.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field, replace

# Structural ARIA / layout attributes worth KEEPING (their VALUES are kept only when they
# are structural, e.g. aria-level; dynamic value-bearing attrs are normalized to a marker).
_DEFAULT_KEPT_ATTRS = frozenset(
    {
        "role",
        "aria-level",
        "aria-orientation",
        "aria-haspopup",
        "aria-expanded",
        "type",  # input type is structural (text vs password vs submit) — kept
    }
)

# Attribute names whose VALUES are instance data (ids, test hooks, names) — kept as a
# presence marker only (the value is stripped), so two renders with different ids match.
_VALUE_STRIPPED_ATTRS = frozenset({"id", "name", "data-test", "data-testid", "class", "href"})

_NUM_RE = re.compile(r"\d+")


@dataclass(frozen=True)
class FingerprintConfig:
    """Tunables that drive convergence sensitivity (EXPL-05).

    max_depth:     stop walking below this depth (coarser hash, fewer false splits).
    kept_attrs:    structural attribute names whose presence (and structural value) is hashed.
    fold_siblings: collapse runs of identical sibling subtrees to one + a marker. ON by
                   default — THIS is the template-vs-instance separator (6 vs 4 items match).
    strip_text:    drop text content before hashing (text is instance data). ON by default.
    """

    max_depth: int = 12
    kept_attrs: frozenset = field(default_factory=lambda: _DEFAULT_KEPT_ATTRS)
    fold_siblings: bool = True
    strip_text: bool = True


DEFAULT_CONFIG = FingerprintConfig()


def _role_or_tag(node: dict) -> str:
    """The node's identity token: prefer ARIA role, fall back to tag, else 'node'."""
    return node.get("role") or node.get("tag") or "node"


def _normalize_attr_value(name: str, value: str) -> str:
    """Strip instance data out of an attribute value, keeping only structural signal.

    Value-bearing attrs (id/name/data-test/href/class) keep only a presence marker (their
    value is instance data). Other kept attrs (e.g. aria-level, type) keep a number-stripped
    value so structural levels survive but counters do not.
    """
    if name in _VALUE_STRIPPED_ATTRS:
        return "*"  # presence only — value is instance data
    # Strip query strings already handled at href level; strip numbers from the rest.
    return _NUM_RE.sub("#", value or "")


def _attrs_token(node: dict, cfg: FingerprintConfig) -> str:
    """Sorted, normalized kept-attr token for a node: 'name=val' joined by ','."""
    attrs = node.get("attrs") or {}
    kept: list[str] = []
    for name in sorted(attrs):
        if name in cfg.kept_attrs or name in _VALUE_STRIPPED_ATTRS:
            kept.append(f"{name}={_normalize_attr_value(name, attrs[name])}")
    return ",".join(kept)


def _child_signature(node: dict, cfg: FingerprintConfig, remaining_depth: int) -> str:
    """A recursive structural signature of a subtree, used to detect identical siblings.

    Independent of the absolute depth so two identical list items at the same level fold
    regardless of where they sit. Honors fold_siblings recursively.
    """
    parts: list[str] = []

    def walk(n: dict, d: int) -> None:
        if d > remaining_depth:
            return
        parts.append(f"{d}:{_role_or_tag(n)}:{_attrs_token(n, cfg)}")
        _emit_children(n, cfg, d, remaining_depth, parts)

    walk(node, 0)
    return "|".join(parts)


def _emit_children(
    node: dict, cfg: FingerprintConfig, depth: int, max_depth: int, parts: list[str]
) -> None:
    """Walk children, folding runs of structurally-identical siblings when configured."""
    children = node.get("children") or []
    if depth >= max_depth:
        return

    if not cfg.fold_siblings:
        for child in children:
            _walk_into(child, cfg, depth + 1, max_depth, parts)
        return

    # Fold: collapse consecutive structurally-identical siblings to ONE representative.
    last_sig: str | None = None
    for child in children:
        sig = _child_signature(child, cfg, max_depth - (depth + 1))
        if sig == last_sig:
            continue  # identical sibling subtree → folded (count-agnostic)
        last_sig = sig
        _walk_into(child, cfg, depth + 1, max_depth, parts)


def _walk_into(node: dict, cfg: FingerprintConfig, depth: int, max_depth: int, parts: list[str]) -> None:
    """Emit a node line + recurse (the depth-first serializer)."""
    if depth > max_depth:
        return
    parts.append(f"{depth}:{_role_or_tag(node)}:{_attrs_token(node, cfg)}")
    _emit_children(node, cfg, depth, max_depth, parts)


def structural_fingerprint(tree: dict, cfg: FingerprintConfig = DEFAULT_CONFIG) -> str:
    """SHA-256 of the normalized structural skeleton of `tree` (Candidate A) — PURE.

    Walks depth-first keeping role/tag + structural attrs, stripping text/ids/numbers, and
    folding identical sibling subtrees when cfg.fold_siblings. Returns a 64-char hex digest.
    """
    parts: list[str] = []
    _walk_into(tree, cfg, 0, cfg.max_depth, parts)
    skeleton = "|".join(parts)
    return hashlib.sha256(skeleton.encode("utf-8")).hexdigest()


def fingerprint(tree: dict, cfg: FingerprintConfig = DEFAULT_CONFIG) -> str:
    """The public state-fingerprint SEAM (EXPL-06).

    Delegates to `structural_fingerprint` (Candidate A) today. A SimHash near-duplicate
    implementation (Candidate B) can replace the body later WITHOUT changing this signature
    — the converge node, the convergence proof, and the Neo4j MERGE key all call this.
    """
    return structural_fingerprint(tree, cfg)


def normalize_aria_tree(snapshot_tree: dict) -> dict:
    """Adapter: turn a Playwright aria_snapshot-derived dict into the node tree the hash eats.

    Kept SEPARATE from the hashing path so `structural_fingerprint` stays pure (no browser).
    Playwright's `aria_snapshot()` returns YAML; an upstream caller may instead pass an
    already-parsed structure. This normalizer accepts a dict node already in
    {"role"/"tag"/"attrs"/"children"} shape (the fixture shape) and returns it unchanged,
    providing the seam where a YAML/role-tree parser is wired for the live loop.
    """
    if not isinstance(snapshot_tree, dict):
        return {"role": "node", "tag": None, "attrs": {}, "children": []}
    return {
        "role": snapshot_tree.get("role"),
        "tag": snapshot_tree.get("tag"),
        "attrs": dict(snapshot_tree.get("attrs") or {}),
        "children": [normalize_aria_tree(c) for c in (snapshot_tree.get("children") or [])],
    }


def with_overrides(**kwargs) -> FingerprintConfig:
    """Convenience: a DEFAULT_CONFIG with selected tunables overridden (for callers/tests)."""
    return replace(DEFAULT_CONFIG, **kwargs)


# DOM-walk JS that returns the {role/tag/attrs/children} node tree the hash consumes.
# Kept as a string constant (NOT executed here) so this module stays import-pure; the
# perceive node passes it to page.evaluate(). Only structural attrs are surfaced; text is
# intentionally omitted (strip_text). The walk is depth-capped client-side too.
_DOM_TREE_JS = """
(maxDepth) => {
  const KEEP = ['role','aria-level','aria-orientation','aria-haspopup','aria-expanded',
                'type','id','name','data-test','data-testid','class','href'];
  function walk(el, d) {
    if (!el || d > maxDepth) return null;
    const attrs = {};
    for (const a of KEEP) { const v = el.getAttribute && el.getAttribute(a);
      if (v !== null && v !== undefined) attrs[a] = v; }
    const children = [];
    if (el.children) for (const c of el.children) {
      const n = walk(c, d + 1); if (n) children.push(n);
    }
    return { role: attrs['role'] || null, tag: (el.tagName||'').toLowerCase(),
             attrs, children };
  }
  return walk(document.body, 0);
}
"""


async def page_fingerprint(page, cfg: FingerprintConfig = DEFAULT_CONFIG) -> str:  # noqa: ANN001
    """Live-page seam: extract a structural node tree from the page and fingerprint it.

    This is the ONLY function here that touches a Playwright page, and it does so via a
    string `evaluate` (no top-level playwright import) so the hashing path stays pure. The
    converge/persist nodes call this to replace the Slice-1 URL `page_key`.
    """
    tree = await page.evaluate(_DOM_TREE_JS, cfg.max_depth)
    normalized = normalize_aria_tree(tree or {})
    return structural_fingerprint(normalized, cfg)
