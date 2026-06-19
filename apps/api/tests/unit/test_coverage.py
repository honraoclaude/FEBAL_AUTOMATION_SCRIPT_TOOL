"""Deterministic coverage-metric proof (QUAL-01 / D-08) — NO keys, NO stack.

Loads the committed SauceDemo ground truth and runs `compute_coverage` against a
hand-built fixture discovered graph, asserting a KNOWN expected percentage. Also proves:
the fingerprint-PRIMARY match path, the normalized-URL FALLBACK across hosts (in-cluster
vs public), the empty-graph 0.0 honest case, and flow coverage. This is the no-key proof
that the metric LOGIC is correct; the live ≥80%-on-a-real-graph gate is the Manual-Only
`tests/functional/test_coverage_live.py`.
"""

from __future__ import annotations

from app.services.kg import coverage

# --- normalize_url: path-only so cross-host URLs coincide ---------------------------------


def test_normalize_url_strips_scheme_and_host() -> None:
    assert coverage.normalize_url("https://www.saucedemo.com/cart.html") == "/cart.html"
    assert coverage.normalize_url("http://saucedemo:80/cart.html") == "/cart.html"
    # The two hosts reduce to the SAME path (the whole point — RESEARCH Open Q2).
    public = coverage.normalize_url("https://www.saucedemo.com/inventory.html")
    incluster = coverage.normalize_url("http://saucedemo:80/inventory.html")
    assert public == incluster == "/inventory.html"


def test_normalize_url_root_and_trailing_slash() -> None:
    assert coverage.normalize_url("https://www.saucedemo.com/") == "/"
    assert coverage.normalize_url("https://www.saucedemo.com") == "/"
    # Trailing slash on a non-root path collapses so it matches the bare path.
    assert coverage.normalize_url("https://x/inventory.html/") == "/inventory.html"
    # A query/fragment is dropped (path identity).
    assert coverage.normalize_url("https://x/cart.html?foo=1#frag") == "/cart.html"
    assert coverage.normalize_url(None) == "/"


# --- compute_coverage: KNOWN percentage on a fixture GT + fixture discovered graph --------


def test_known_percentage_six_of_seven() -> None:
    """6 of the 7 ground-truth pages discovered -> 85.7% (the hand-computed value)."""
    gt = coverage.load_ground_truth()
    assert len(gt["pages"]) == 7  # the fixture invariant the known % depends on

    # Discovered graph: 6 of 7 pages (MISSING "Item Detail"), seen at the IN-CLUSTER host so
    # the url-fallback must canonicalize hosts. Two pages also carry fingerprints.
    discovered = {
        "pages": [
            {"url": "http://saucedemo:80/", "fingerprint": "fp-login"},
            {"url": "http://saucedemo:80/inventory.html", "fingerprint": "fp-inv"},
            {"url": "http://saucedemo:80/cart.html"},
            {"url": "http://saucedemo:80/checkout-step-one.html"},
            {"url": "http://saucedemo:80/checkout-step-two.html"},
            {"url": "http://saucedemo:80/checkout-complete.html"},
        ]
    }
    result = coverage.compute_coverage(gt, discovered)
    assert result["screens_total"] == 7
    assert result["screens_covered"] == 6
    assert result["coverage_percent"] == 85.7  # round(100*6/7, 1)
    assert "Item Detail" not in result["matched"]
    assert "Login" in result["matched"]


def test_url_fallback_matches_across_hosts() -> None:
    """A GT page with NO fingerprint matches via normalized-URL across differing hosts."""
    gt = {"pages": [{"name": "Cart", "url": "https://www.saucedemo.com/cart.html"}], "flows": []}
    discovered = {"pages": [{"url": "http://saucedemo:80/cart.html"}]}  # in-cluster host, no fp
    result = coverage.compute_coverage(gt, discovered)
    assert result["coverage_percent"] == 100.0
    assert result["matched"] == ["Cart"]


def test_fingerprint_primary_match() -> None:
    """A GT page carrying a fingerprint matches by fingerprint even when the URL differs."""
    gt = {
        "pages": [{"name": "Inventory", "url": "https://nope.example/x", "fingerprint": "fp-7"}],
        "flows": [],
    }
    # Discovered URL would NOT match by path; only the fingerprint does.
    discovered = {"pages": [{"url": "http://other/y.html", "fingerprint": "fp-7"}]}
    result = coverage.compute_coverage(gt, discovered)
    assert result["screens_covered"] == 1
    assert result["coverage_percent"] == 100.0


def test_empty_graph_is_zero_not_fabricated() -> None:
    """An empty discovered graph yields 0.0 and zero covered — the honest 'not measured' case."""
    gt = coverage.load_ground_truth()
    result = coverage.compute_coverage(gt, {"pages": []})
    assert result["screens_covered"] == 0
    assert result["coverage_percent"] == 0.0
    assert result["flows_covered"] == 0
    assert result["matched"] == []


def test_flow_coverage_counts_full_journeys() -> None:
    """A flow is covered only when EVERY page in its sequence matched."""
    gt = coverage.load_ground_truth()
    # Discover only the Login flow's pages (Login + Inventory); the checkout flow is partial.
    discovered = {
        "pages": [
            {"url": "http://saucedemo:80/"},
            {"url": "http://saucedemo:80/inventory.html"},
        ]
    }
    result = coverage.compute_coverage(gt, discovered)
    assert result["flows_total"] == 2
    assert result["flows_covered"] == 1  # only "Login" is fully covered
    assert result["flows_percent"] == 50.0


def test_all_pages_discovered_is_full_coverage() -> None:
    """All 7 GT pages discovered -> 100% pages + 100% flows."""
    gt = coverage.load_ground_truth()
    discovered = {"pages": [{"url": p["url"]} for p in gt["pages"]]}
    result = coverage.compute_coverage(gt, discovered)
    assert result["coverage_percent"] == 100.0
    assert result["flows_covered"] == result["flows_total"] == 2
