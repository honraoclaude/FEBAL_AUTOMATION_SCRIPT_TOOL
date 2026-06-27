"""PURE failure fingerprint (JIRA-03 / D-05) — stdlib hashlib + re, NO new package.

The deterministic, keyless sibling of explorer/fingerprint.py (which strips instance data from a
structural tree; this strips it from an error STRING). The fingerprint is a stable hash of
(class + NORMALIZED error message + flow id + failing step). normalize() strips the instance data
that would otherwise split one logical failure into many — numbers, ids, uuids, ISO timestamps,
hex pointers — and collapses whitespace, so two failures differing ONLY in such noise collapse to
the SAME fingerprint. That fingerprint becomes the Jira LABEL `fp-<hash>` AND the local defect
row's dedup key.

PURITY (load-bearing): stdlib only (hashlib + re + dataclasses) — imports NOTHING from the LLM/
gateway/graph/DB/browser plane (the test_no_llm_in_classifier gate scans this file). The hash is
sha1[:16] per RESEARCH Pattern 5 — an IDENTITY key, not a credential (ASVS V6 N/A; do not treat
as crypto). A hostile error string only changes the hex digest; it never escapes into SQL/JQL (the
label is the server-built `fp-<hash>`, T-09-02).
"""

from __future__ import annotations

import hashlib
import re

# Order matters: UUID before HEX/NUM (a uuid contains hex+digits), TS before NUM (a timestamp is
# digits). Each compiled once at module scope (the explorer/fingerprint discipline).
_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\S*")
_HEX_RE = re.compile(r"\b0x[0-9a-f]+\b", re.I)
_NUM_RE = re.compile(r"\d+")


def normalize(msg: str) -> str:
    """PURE: strip uuids / ISO-timestamps / hex / digits to placeholders + collapse whitespace.

    Deterministic + idempotent: the placeholders (`<uuid>`/`<ts>`/`<hex>`/`<n>`) contain no digits
    or hex, so a second pass is a fixed point. Returns a single-space-joined, stripped string.
    """
    s = _UUID_RE.sub("<uuid>", msg or "")
    s = _TS_RE.sub("<ts>", s)
    s = _HEX_RE.sub("<hex>", s)
    s = _NUM_RE.sub("<n>", s)
    return " ".join(s.split())


def fingerprint(cls: str, msg: str, flow_id: str, step: str) -> str:
    """PURE: sha1[:16] of `class | normalize(msg) | flow_id | step` — the `fp-<hash>` dedup key.

    All four components are part of the key, so a different class, flow, or failing step yields a
    different fingerprint; only number/id/timestamp noise in the message is normalized away.
    """
    key = f"{cls}|{normalize(msg)}|{flow_id}|{step}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
