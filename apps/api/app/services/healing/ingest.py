"""Heal-journal ingest — the worker-side heal-as-commit (D-03, NOT git) for HEAL-03.

After the in-spec subprocess exits, the worker calls into here to perform the three persistence
side-effects of a heal (the in-spec layer only WROTE the per-flow heal-journal; the worker, with
DB + KG access the subprocess lacks, COMMITS them):

  1. a Postgres `HealAudit` row per journal entry (before/after chain, confidence, outcome,
     run/flow keys) — the auditable record the before/after diff renders from;
  2. for `auto_heal` ONLY, a SAFE ast-validated page-object locator rewrite (the script-repo
     update) — quarantine / fail_as_defect STAGE in the audit row, no file rewrite (Open Q3);
  3. a KG Element-history append through the SINGLE writer (kg/writer.append_element_history) —
     parameterized + read-back guarded, so the single-write-path gate stays green.

heal-as-commit is NOT a git commit (D-03): "commit" = these three durable side-effects.

THREAT POSTURE:
  - The heal-journal is machine-written by the UNTRUSTED in-spec subprocess. `parse_heal_journal`
    is a TOLERANT BOUNDED parse (mirrors kg/reader._loads): malformed/oversized entries are
    SKIPPED, never crash; required keys + bounded sizes are validated before a row is written
    (T-08-09).
  - The page-object rewrite is a LINE-TARGETED replace keyed by the attr name ONLY (the template
    guarantees exactly one `self.<attr> = page.locator(<literal>)` line per attr); the result is
    `ast.parse`-validated before it is returned — a non-parsing rewrite RAISES, never persisting
    broken source (T-08-10). It never executes or evaluates journal/page text.
  - `out_dir` / `project_root` are run_id-DERIVED by the worker (workspaces helpers); a path is
    NEVER taken from the journal body (T-08-12 carries T-07-11).
  - The KG write-back routes EXCLUSIVELY through kg/writer.append_element_history (no execute_write
    here — the single-write-path grep gate finds nothing in this module).

NO LLM / explorer import (SC3 — the worker imports this module, and the worker-plane gate scans
job.py's import graph; this module reaches only the DB session, the model, kg/writer, and the
pure locators helper).
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import structlog

log = structlog.get_logger()

# --- Bounded-parse limits (T-08-09: a malicious/oversized journal must not poison ingest) ----
_MAX_JOURNAL_BYTES = 1_000_000  # 1 MB ceiling on the whole journal file
_MAX_ENTRIES = 1_000  # at most this many entries are ingested (extra are dropped)
_MAX_KEY_LEN = 255  # element_key must fit the indexed String(255) column
_MAX_CHAIN_ENTRIES = 50  # a chain longer than this is rejected (garbage / DoS)
_VALID_OUTCOMES = frozenset(
    {"auto_heal", "quarantine", "fail_as_defect", "applied", "rejected"}
)


def parse_heal_journal(out_dir: Path) -> list[dict]:
    """Tolerantly read + validate the per-flow heal-journal at <out_dir>/heal-journal.json.

    `out_dir` is the spec's KNOWN per-flow workspace path, passed by the worker (run_id-derived,
    NEVER a path from the journal body — T-08-12). Returns the list of VALID entries; a missing
    file, an oversized file, a non-list payload, or a malformed/oversized entry yields fewer (or
    zero) entries — this NEVER raises (mirrors kg/reader._loads tolerance, T-08-09).

    An entry is valid iff it is a dict carrying a non-empty bounded `element_key`, a recognized
    `outcome`, a numeric `confidence`, and (optionally) bounded before/after chains. Unknown keys
    are ignored; only the fields the audit row needs are read.
    """
    journal_path = Path(out_dir) / "heal-journal.json"
    try:
        raw = journal_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return []
    if len(raw.encode("utf-8", errors="ignore")) > _MAX_JOURNAL_BYTES:
        log.warning("heal_journal_oversized", path=str(journal_path), bytes=len(raw))
        return []
    try:
        loaded = json.loads(raw)
    except (ValueError, TypeError):
        log.warning("heal_journal_malformed", path=str(journal_path))
        return []
    if not isinstance(loaded, list):
        return []

    valid: list[dict] = []
    for item in loaded[:_MAX_ENTRIES]:
        entry = _validate_entry(item)
        if entry is not None:
            valid.append(entry)
    return valid


def _bounded_chain(value: object) -> list:
    """Coerce a chain to a bounded list of {strategy, value} dicts (garbage -> [])."""
    if not isinstance(value, list) or len(value) > _MAX_CHAIN_ENTRIES:
        return []
    out: list = []
    for e in value:
        if isinstance(e, dict):
            out.append(e)
    return out


def _validate_entry(item: object) -> dict | None:
    """Return a normalized entry dict if `item` is a valid journal entry, else None (skip).

    Required: a non-empty bounded str `element_key` + a recognized `outcome` + a numeric
    `confidence`. The chains are bounded-coerced; missing/garbage chains become []. This is the
    single gate every entry passes before it can become a HealAudit row (T-08-09).
    """
    if not isinstance(item, dict):
        return None
    key = item.get("element_key")
    if not isinstance(key, str) or not key or len(key) > _MAX_KEY_LEN:
        return None
    outcome = item.get("outcome")
    if outcome not in _VALID_OUTCOMES:
        return None
    conf = item.get("confidence")
    if not isinstance(conf, (int, float)) or isinstance(conf, bool):
        return None
    match_count = item.get("live_match_count")
    if not isinstance(match_count, int) or isinstance(match_count, bool):
        match_count = 0
    flow_id = item.get("flow_id")
    if not isinstance(flow_id, str) or len(flow_id) > _MAX_KEY_LEN:
        flow_id = ""
    return {
        "element_key": key,
        "outcome": outcome,
        "confidence": float(conf),
        "before_chain": _bounded_chain(item.get("before_chain")),
        "after_chain": _bounded_chain(item.get("after_chain")),
        "live_match_count": match_count,
        "flow_id": flow_id,
    }


# --- Page-object rewrite (the script-repo update; T-08-10) ------------------------------------


def _attr_assignment_re(element_key: str) -> re.Pattern[str]:
    """A regex matching the page-object's single `self.<element_key> = page.locator(<literal>)` line.

    The page_object.py.j2 template guarantees EXACTLY ONE such line per attr (rendered from the
    repo's top chain entry). Matching by the attr name only — never by the literal — makes the
    rewrite key-targeted: other attrs' literals are untouched. The literal group captures either a
    single- or double-quoted string (the template emits `| tojson`, i.e. double-quoted).
    """
    return re.compile(
        r"(?P<prefix>^\s*self\." + re.escape(element_key) + r"\s*=\s*page\.locator\(\s*)"
        r"(?P<lit>(?:\"(?:[^\"\\]|\\.)*\")|(?:'(?:[^'\\]|\\.)*'))"
        r"(?P<suffix>\s*\))",
        re.MULTILINE,
    )


def rewrite_page_object_locator(
    source: str, *, element_key: str, new_selector: str
) -> str:
    """Rewrite ONLY the `self.<element_key>` page.locator literal to `new_selector`; ast-validate.

    A LINE-TARGETED, key-targeted replace (Open Q1 recommendation): find the single
    `self.<element_key> = page.locator(<literal>)` line, swap its literal for `new_selector`
    (re-quoted safely via json.dumps so the rewrite is always a valid Python string literal — no
    arbitrary code is ever inserted, T-08-10), then `ast.parse` the WHOLE result.

      - An UNKNOWN element_key (no matching line) -> the source is returned UNCHANGED (no-op).
      - A rewrite that would produce invalid Python -> raises SyntaxError (the mutated source is
        NEVER returned).

    Other attrs' literals are never touched (the match is anchored to the attr name).
    """
    pattern = _attr_assignment_re(element_key)
    if not pattern.search(source):
        return source  # unknown key -> no-op (no crash)

    # json.dumps yields a valid double-quoted Python string literal with all special chars
    # escaped — never raw journal/page text spliced into code (T-08-10).
    new_literal = json.dumps(new_selector)

    def _sub(m: re.Match[str]) -> str:
        return f"{m.group('prefix')}{new_literal}{m.group('suffix')}"

    rewritten = pattern.sub(_sub, source, count=1)
    ast.parse(rewritten)  # raises SyntaxError on a malformed result -> caller never persists it
    return rewritten
