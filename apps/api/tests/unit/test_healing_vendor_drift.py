"""Byte-equivalence drift guard (RESEARCH Open Q2) — the vendored in-spec scorer cannot drift.

The generated project CANNOT `import app.services`, so templates/healing/_healing.py.j2 VENDORS
the pure scorer from app/services/healing/ (confidence/geometry/candidates) + the verbatim
_XPATH_JS from explorer/locators.py. This test renders the template, extracts each vendored
function's exact source segment, and asserts it is BYTE-IDENTICAL to the canonical source — so a
change to the canonical engine that is not mirrored into the template FAILS the build (the
in-spec heal would otherwise silently use a stale scorer).

The ONE sanctioned normalization: the canonical `score_candidate` does a function-local lazy
`from app.services.healing.geometry import iou, size_proximity` (so the canonical module-level
import gate stays at 0); the vendored copy lives in the SAME module as iou/size_proximity, so that
single import line is dropped. The guard strips exactly that line from the canonical before
comparing — every other byte must match.
"""

from __future__ import annotations

import ast
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

_APP = Path(__file__).resolve().parents[2] / "app"
_TEMPLATES = _APP / "templates"
_HEALING = _APP / "services" / "healing"
_LOCATORS = _APP / "services" / "explorer" / "locators.py"

# Functions vendored from each canonical source module that MUST be byte-identical.
_VENDORED = {
    "confidence.py": ["HealWeights", "confidence", "heal_outcome"],
    "geometry.py": ["iou", "size_proximity"],
    "candidates.py": [
        "_attr_set",
        "_jaccard",
        "_xpath_overlap",
        "dom_sim",
        "a11y_sim",
        "_chain_key",
        "history_sim",
        "score_candidate",
    ],
}

# The single sanctioned normalization (the canonical lazy geometry import — plus the blank line
# that follows it — not present in the vendored copy, which lives in the same module as
# iou/size_proximity so the docstring is immediately followed by the body).
_LAZY_GEOMETRY_IMPORT = (
    "    from app.services.healing.geometry import iou, size_proximity\n\n"
)


def _render_template() -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        keep_trailing_newline=True,
    )
    return env.get_template("healing/_healing.py.j2").render()


def _segments(source: str, names: list[str]) -> dict[str, str]:
    """Map each top-level def/class name -> its exact ast source segment."""
    tree = ast.parse(source)
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name in names:
                seg = ast.get_source_segment(source, node)
                assert seg is not None, f"no source segment for {node.name}"
                found[node.name] = seg
    return found


def test_vendored_scorer_is_byte_equivalent_to_canonical() -> None:
    rendered = _render_template()
    wanted = [name for names in _VENDORED.values() for name in names]
    vendored = _segments(rendered, wanted)

    missing = [n for n in wanted if n not in vendored]
    assert not missing, f"vendored functions missing from _healing.py.j2: {missing}"

    for module_file, names in _VENDORED.items():
        canonical_src = (_HEALING / module_file).read_text(encoding="utf-8")
        canonical = _segments(canonical_src, names)
        for name in names:
            expected = canonical[name]
            if name == "score_candidate":
                # Drop the sanctioned lazy geometry import from the canonical before comparing.
                expected = expected.replace(_LAZY_GEOMETRY_IMPORT, "")
            assert vendored[name] == expected, (
                f"VENDOR DRIFT: '{name}' in _healing.py.j2 diverged from "
                f"app/services/healing/{module_file} — re-vendor the canonical source.\n"
                f"--- canonical ---\n{expected}\n--- vendored ---\n{vendored[name]}"
            )


def test_vendored_xpath_js_is_byte_equivalent_to_canonical() -> None:
    """_XPATH_JS must be vendored verbatim from explorer/locators.py."""
    rendered = _render_template()
    locators_src = _LOCATORS.read_text(encoding="utf-8")

    def _xpath_assignment(source: str) -> str:
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "_XPATH_JS":
                        seg = ast.get_source_segment(source, node)
                        assert seg is not None
                        return seg
        raise AssertionError("_XPATH_JS assignment not found")

    assert _xpath_assignment(rendered) == _xpath_assignment(locators_src), (
        "VENDOR DRIFT: _XPATH_JS in _healing.py.j2 diverged from explorer/locators.py"
    )
