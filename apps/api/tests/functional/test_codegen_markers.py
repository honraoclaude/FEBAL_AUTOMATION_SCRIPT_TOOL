"""Generated-project tier-marker registration (EXEC-01 / D-01) — functional, no neo4j, no keys.

The generated Playwright project must REGISTER the tier markers (smoke/sanity/regression) so a
`-m smoke` tier run SELECTS the @smoke-tagged scenarios instead of warning + selecting nothing
(RESEARCH Pitfall 3). Two layers, both keyless and graph-free:

1. RENDER: the conftest.py.j2 template (the home chosen for the registration) renders through the
   codegen `_render_checked_py` seam (ast-parses + selector-gated) and declares all three markers.
2. COLLECT: a throwaway pytest-bdd project (a planted @smoke feature + an untagged feature + the
   rendered conftest) collects EXACTLY the @smoke scenario under `-m smoke --collect-only`, with
   NO PytestUnknownMarkWarning — proving the markers actually drive tier selection.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app.services.codegen import project as codegen_project


def _render_conftest() -> str:
    """Render the conftest template through the REAL codegen gate (ast-parse + selector gate)."""
    return codegen_project._render_checked_py(
        "conftest.py.j2",
        is_page_object=False,
        base_url_env=codegen_project._BASE_URL_ENV,
        default_base_url=codegen_project._DEFAULT_BASE_URL,
    )


@pytest.mark.functional
def test_rendered_conftest_registers_the_three_tier_markers() -> None:
    rendered = _render_conftest()
    assert "pytest_configure" in rendered
    for marker in ("smoke", "sanity", "regression"):
        assert f'"{marker}:' in rendered or f"{marker}:" in rendered, (
            f"the rendered conftest must register the {marker} marker"
        )


@pytest.mark.functional
def test_smoke_selection_collects_only_the_tagged_scenario(tmp_path: Path) -> None:
    """`-m smoke --collect-only` against a planted project collects the @smoke scenario only."""
    proj = tmp_path / "gen"
    (proj / "features").mkdir(parents=True)
    (proj / "steps").mkdir(parents=True)

    # The rendered conftest carries the marker registration (the artifact under test).
    (proj / "conftest.py").write_text(_render_conftest(), encoding="utf-8")
    (proj / "pytest.ini").write_text(
        "[pytest]\nbdd_features_base_dir = features\n", encoding="utf-8"
    )

    (proj / "features" / "tagged.feature").write_text(
        textwrap.dedent(
            """\
            Feature: Tagged

              @smoke
              Scenario: A smoke scenario
                Given a starting point
                Then it is fine
            """
        ),
        encoding="utf-8",
    )
    (proj / "features" / "untagged.feature").write_text(
        textwrap.dedent(
            """\
            Feature: Untagged

              Scenario: An untagged scenario
                Given a starting point
                Then it is fine
            """
        ),
        encoding="utf-8",
    )

    # Step defs binding BOTH features (pytest-bdd tag → pytest marker is automatic).
    (proj / "steps" / "__init__.py").write_text("", encoding="utf-8")
    (proj / "steps" / "test_tiers.py").write_text(
        textwrap.dedent(
            """\
            from pytest_bdd import given, scenarios, then

            scenarios("../features/tagged.feature", "../features/untagged.feature")


            @given("a starting point")
            def _start():
                pass


            @then("it is fine")
            def _fine():
                pass
            """
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-m", "smoke", "--collect-only", "-q"],
        cwd=str(proj),
        capture_output=True,
        text=True,
    )
    out = result.stdout + result.stderr
    # pytest-bdd names each scenario's collected test after the scenario (snake-cased).
    assert "test_a_smoke_scenario" in out, f"the @smoke scenario must be collected:\n{out}"
    assert "test_an_untagged_scenario" not in out, (
        f"the untagged scenario must NOT be collected:\n{out}"
    )
    # Exactly one of the two collected, the other deselected by -m smoke.
    assert "1 deselected" in out, f"the untagged scenario must be deselected by -m smoke:\n{out}"
    assert "PytestUnknownMarkWarning" not in out, f"markers must be registered:\n{out}"
