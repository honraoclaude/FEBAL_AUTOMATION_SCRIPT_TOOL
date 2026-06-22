"""HEAL-01 visual sub-score proof — bounding-box IoU geometry (NO browser, NO pixel decode).

`iou(a, b)` is the PURE deterministic visual similarity: intersection-over-union of two
bounding boxes `{x, y, width, height}` (as returned by Playwright `locator.bounding_box()`),
computed with stdlib math on dicts — NO Playwright import, NO image library (RESEARCH Pitfall 7:
pixel diff is non-deterministic across font/AA rendering; geometry is keyless + reproducible).

Pins: identical boxes -> 1.0; None (off-screen) -> 0.0; disjoint boxes -> 0.0; half-overlap in
(0,1); union<=0 -> 0.0. Plus `size_proximity` (min-area/max-area ratio) in [0,1].
"""

from __future__ import annotations

import pytest

from app.services.healing.geometry import iou, size_proximity

_BOX = {"x": 0.0, "y": 0.0, "width": 10.0, "height": 10.0}


def test_none_box_is_zero() -> None:
    assert iou(None, _BOX) == 0.0
    assert iou(_BOX, None) == 0.0
    assert iou(None, None) == 0.0


def test_identical_boxes_is_one() -> None:
    assert iou(_BOX, _BOX) == 1.0


def test_disjoint_boxes_is_zero() -> None:
    far = {"x": 100.0, "y": 100.0, "width": 10.0, "height": 10.0}
    assert iou(_BOX, far) == 0.0


def test_edge_touching_boxes_is_zero() -> None:
    # Boxes that share only an edge (x in [10,20]) have zero intersection area.
    adjacent = {"x": 10.0, "y": 0.0, "width": 10.0, "height": 10.0}
    assert iou(_BOX, adjacent) == 0.0


def test_half_overlap_is_between_zero_and_one() -> None:
    # Shift right by 5 -> intersection 5x10=50, union 100+100-50=150 -> 1/3.
    shifted = {"x": 5.0, "y": 0.0, "width": 10.0, "height": 10.0}
    score = iou(_BOX, shifted)
    assert 0.0 < score < 1.0
    assert score == pytest.approx(50.0 / 150.0)


def test_contained_box_partial_overlap() -> None:
    # A 5x5 box fully inside the 10x10 box: inter 25, union 100+25-25=100 -> 0.25.
    inner = {"x": 0.0, "y": 0.0, "width": 5.0, "height": 5.0}
    assert iou(_BOX, inner) == pytest.approx(0.25)


def test_zero_area_box_is_zero() -> None:
    # A degenerate zero-area box -> union may be 0 (both zero-area) -> 0.0; with a real box,
    # intersection is 0 so iou is 0.
    zero = {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}
    assert iou(zero, zero) == 0.0
    assert iou(_BOX, zero) == 0.0


def test_size_proximity_identical_is_one() -> None:
    assert size_proximity(_BOX, _BOX) == 1.0


def test_size_proximity_half_area() -> None:
    # 10x10 (area 100) vs 10x5 (area 50) -> 50/100 = 0.5.
    half = {"x": 0.0, "y": 0.0, "width": 10.0, "height": 5.0}
    assert size_proximity(_BOX, half) == pytest.approx(0.5)


def test_size_proximity_none_is_zero() -> None:
    assert size_proximity(None, _BOX) == 0.0
    assert size_proximity(_BOX, None) == 0.0


def test_geometry_module_has_no_playwright_import() -> None:
    import inspect

    import app.services.healing.geometry as geo_mod

    src = inspect.getsource(geo_mod)
    assert "playwright" not in src, "geometry.py must be pure math — no playwright import"
