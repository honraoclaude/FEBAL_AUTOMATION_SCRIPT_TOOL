"""Ground-truth coverage metric (QUAL-01 / D-08) — PURE + deterministic.

Coverage = matched ground-truth pages/flows ÷ ground-truth total. A ground-truth page
matches a discovered page when its FINGERPRINT (if the GT entry carries one) is among the
discovered fingerprints, OR `normalize_url(its url)` is among the discovered normalized
URLs (fingerprint PRIMARY, normalized-URL FALLBACK — RESEARCH Pitfall 4 / A5). The
ground-truth fixture is hand-authored from public URLs (humans don't compute fingerprints),
while the discovered graph is fingerprint-keyed; storing both `url` and `fingerprint` on the
discovered side makes both comparisons available.

`normalize_url` canonicalizes to a PATH-ONLY form (strip scheme + host) so the in-cluster
host the explorer sees (`http://saucedemo:80/cart.html`) and the public host in the fixture
(`https://www.saucedemo.com/cart.html`) both reduce to `/cart.html` and therefore match
(RESEARCH Open Q2).

This module is PURE in the discipline of `explorer/budget.py` / `fingerprint.py`: the only
I/O is `load_ground_truth`, a thin stdlib-`json` reader of the committed fixture (NO YAML
dep, D-07). `compute_coverage` itself performs zero I/O — no neo4j, no LLM, no keys — so the
metric is unit-testable against a fixture KG to a KNOWN percentage. It NEVER fabricates a
figure: when the discovered graph is empty there are zero matches and the caller reads
`screens_covered == 0` as "not yet measured" (the router maps that to `measured=false`).

No write-Cypher lives here (the single-write-path grep gate stays green).
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

# The committed ground-truth fixture (D-07). apps/api/app/services/kg/coverage.py
# -> parents[3] = apps/api, then tests/fixtures/ground_truth/saucedemo.json.
_GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "fixtures"
    / "ground_truth"
    / "saucedemo.json"
)


def default_ground_truth_path() -> Path:
    """The path to the committed SauceDemo ground-truth fixture."""
    return _GROUND_TRUTH_PATH


def load_ground_truth(path: str | Path | None = None) -> dict:
    """Load the committed ground-truth fixture (stdlib json; no YAML dep, D-07)."""
    p = Path(path) if path is not None else _GROUND_TRUTH_PATH
    with p.open(encoding="utf-8") as fh:
        return json.load(fh)


def normalize_url(url: str | None) -> str:
    """Canonicalize a URL to a PATH-ONLY form so cross-host URLs match (RESEARCH Open Q2).

    Strips scheme + host, keeps the path with a trailing slash collapsed (so `/` and ``
    both become `/`, and `/cart.html` stays `/cart.html`). The query/fragment are dropped:
    page identity on SauceDemo is the path, not query state. A bare path with no scheme
    (already path-only) is normalized the same way.
    """
    if not url:
        return "/"
    parts = urlsplit(url)
    path = parts.path or "/"
    # Collapse a multi-slash / empty path to the canonical root; strip a trailing slash on
    # non-root paths so "/inventory.html" and "/inventory.html/" coincide.
    if path != "/":
        path = path.rstrip("/") or "/"
    return path


def _discovered_keys(discovered: dict) -> tuple[set[str], set[str]]:
    """Return (normalized urls, fingerprints) present in the discovered graph."""
    pages = discovered.get("pages") or []
    urls = {normalize_url(p.get("url")) for p in pages}
    fps = {p.get("fingerprint") for p in pages if p.get("fingerprint")}
    return urls, fps


def _page_matches(gt_page: dict, disc_urls: set[str], disc_fps: set[str]) -> bool:
    """A GT page matches when its fingerprint is discovered (PRIMARY) or its normalized URL
    is discovered (FALLBACK) — RESEARCH Pitfall 4."""
    fp = gt_page.get("fingerprint")
    if fp and fp in disc_fps:
        return True
    return normalize_url(gt_page.get("url")) in disc_urls


def compute_coverage(ground_truth: dict, discovered: dict) -> dict:
    """Deterministic matched ÷ total coverage (QUAL-01 / D-08) — PURE, no I/O.

    Args:
        ground_truth: the hand-labeled fixture — {pages:[{name,url,fingerprint?}], flows:[...]}.
        discovered:   the discovered graph — {pages:[{url, fingerprint?}, ...]} (extra keys
                      are ignored). An empty pages list yields zero matches (never a
                      fabricated percent — the caller treats covered==0 as "not measured").

    Returns:
        {screens_total, screens_covered, coverage_percent, flows_total, flows_covered,
         flows_percent, matched} where coverage_percent/flows_percent are rounded 1dp and
         0.0 when the respective total is 0.
    """
    disc_urls, disc_fps = _discovered_keys(discovered)

    gt_pages = ground_truth.get("pages") or []
    matched_pages = [g for g in gt_pages if _page_matches(g, disc_urls, disc_fps)]
    screens_total = len(gt_pages)
    screens_covered = len(matched_pages)
    coverage_percent = (
        round(100.0 * screens_covered / screens_total, 1) if screens_total else 0.0
    )

    # A flow is covered when EVERY page in its sequence matched (the journey is reachable
    # on the discovered graph). Matched page NAMES drive flow matching.
    matched_names = {g["name"] for g in matched_pages}
    gt_flows = ground_truth.get("flows") or []
    flows_covered = sum(
        1 for f in gt_flows if all(name in matched_names for name in (f.get("pages") or []))
    )
    flows_total = len(gt_flows)
    flows_percent = round(100.0 * flows_covered / flows_total, 1) if flows_total else 0.0

    return {
        "screens_total": screens_total,
        "screens_covered": screens_covered,
        "coverage_percent": coverage_percent,
        "flows_total": flows_total,
        "flows_covered": flows_covered,
        "flows_percent": flows_percent,
        "matched": [g["name"] for g in matched_pages],
    }
