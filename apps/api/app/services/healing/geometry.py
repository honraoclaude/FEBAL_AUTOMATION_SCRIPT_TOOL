"""PURE bounding-box geometry — the deterministic VISUAL sub-score (HEAL-01, D-02).

Visual similarity is intersection-over-union (IoU) of two bounding boxes plus a size-proximity
ratio — pure stdlib math on `{x, y, width, height}` dicts as returned by Playwright
`locator.bounding_box()`. NO Playwright import here (the live read happens in the in-spec layer;
this is pure math), and NO image library: pixel diff is non-deterministic across font/anti-alias
rendering and would add a new dependency (RESEARCH Pitfall 7 / Anti-Patterns). Geometry is keyless,
reproducible, and zero-dep. A None box (off-screen / not visible) -> 0.0.
"""

from __future__ import annotations


def iou(a: dict | None, b: dict | None) -> float:
    """PURE: intersection-over-union of two bounding boxes -> [0,1]. None (off-screen) -> 0.0.

    Box = {"x", "y", "width", "height"}. Identical boxes -> 1.0; disjoint or edge-touching -> 0.0;
    union <= 0 (both degenerate) -> 0.0. The clamp at 0 on each axis discards non-overlapping cases.
    """
    if not a or not b:
        return 0.0
    ax2, ay2 = a["x"] + a["width"], a["y"] + a["height"]
    bx2, by2 = b["x"] + b["width"], b["y"] + b["height"]
    ix = max(0.0, min(ax2, bx2) - max(a["x"], b["x"]))
    iy = max(0.0, min(ay2, by2) - max(a["y"], b["y"]))
    inter = ix * iy
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union > 0 else 0.0


def size_proximity(a: dict | None, b: dict | None) -> float:
    """PURE: min-area / max-area ratio of two boxes -> [0,1]. None or zero-area -> 0.0.

    Complements IoU: two equally-sized boxes in different positions still score 1.0 here, so a
    moved-but-same-size element retains visual signal even when IoU drops. Folded into the visual
    sub-score (averaged with IoU) so position shift alone does not zero out the visual evidence.
    """
    if not a or not b:
        return 0.0
    area_a = a["width"] * a["height"]
    area_b = b["width"] * b["height"]
    if area_a <= 0 or area_b <= 0:
        return 0.0
    return min(area_a, area_b) / max(area_a, area_b)
