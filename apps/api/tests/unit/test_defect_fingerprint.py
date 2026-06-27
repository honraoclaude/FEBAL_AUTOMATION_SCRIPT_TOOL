"""Failure-fingerprint determinism (JIRA-03 / D-05) — pure, keyless, stdlib-only.

Named test_defect_fingerprint.py (NOT test_fingerprint.py — that is the Phase-4 explorer
structural fingerprint; the kg/risk -> test_kg_risk naming discipline carries) so the two pure
fingerprint modules never clobber each other.

The defect fingerprint = a stable hash of (class + NORMALIZED error message + flow id + failing
step), where normalize() strips the instance data (numbers / ids / uuids / ISO timestamps / hex)
so two failures that differ ONLY in such noise collapse to the SAME fingerprint (the `fp-<hash>`
dedup key). These tests pin:

  - normalize() collapses uuids / timestamps / hex / digits to placeholders + collapses whitespace;
  - normalize() is idempotent (normalizing twice == once);
  - two messages differing ONLY in numbers/ids/timestamps/uuids -> the SAME fingerprint;
  - a different class, flow, or step -> a DIFFERENT fingerprint (the four components all matter);
  - the digest is a stable 16-char hex (sha1[:16]).

Run: cd apps/api && uv run python -m pytest tests/unit/test_defect_fingerprint.py -q
"""

from __future__ import annotations

import re

from app.services.defects.fingerprint import fingerprint, normalize


def test_normalize_strips_instance_data_and_collapses_whitespace() -> None:
    msg = "Timeout 30000ms exceeded at 2026-06-27T18:00:00.123Z id=550e8400-e29b-41d4-a716-446655440000 ptr=0xDEADBEEF"
    out = normalize(msg)
    assert "30000" not in out
    assert "2026-06-27" not in out
    assert "550e8400" not in out
    assert "0xdeadbeef" not in out.lower()
    # whitespace collapsed to single spaces (no double spaces, no leading/trailing).
    assert "  " not in out
    assert out == out.strip()


def test_normalize_is_idempotent() -> None:
    msg = "AssertionError: expected 5 but got 7 at row 42 ts 2026-01-01T00:00:00Z"
    once = normalize(msg)
    twice = normalize(once)
    assert once == twice


def test_numbers_ids_timestamps_collapse_to_one_fingerprint() -> None:
    a = "Timeout 30000ms at 2026-06-27T18:00:00Z req=550e8400-e29b-41d4-a716-446655440000"
    b = "Timeout 45000ms at 2026-06-28T09:15:42Z req=11111111-2222-3333-4444-555555555555"
    fa = fingerprint("infrastructure", a, "flow-0", "step-3")
    fb = fingerprint("infrastructure", b, "flow-0", "step-3")
    assert fa == fb, "messages differing only in numbers/ids/timestamps must fingerprint the same"


def test_distinct_class_flow_step_produce_distinct_fingerprints() -> None:
    msg = "element not found: .inventory_list"
    base = fingerprint("product_defect", msg, "flow-0", "step-1")
    assert fingerprint("automation", msg, "flow-0", "step-1") != base  # class matters
    assert fingerprint("product_defect", msg, "flow-9", "step-1") != base  # flow matters
    assert fingerprint("product_defect", msg, "flow-0", "step-9") != base  # step matters


def test_fingerprint_is_stable_16_char_hex() -> None:
    fp = fingerprint("product_defect", "boom", "flow-0", "step-0")
    assert re.fullmatch(r"[0-9a-f]{16}", fp), f"expected sha1[:16] hex, got {fp!r}"
    # deterministic across calls.
    assert fp == fingerprint("product_defect", "boom", "flow-0", "step-0")
