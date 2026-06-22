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
  - The KG write-back routes EXCLUSIVELY through kg/writer.append_element_history (no managed
    write-txn here — the single-write-path grep gate finds nothing in this module).

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


def _resolve_page_module(pages_dir: Path, element_key: str) -> Path | None:
    """MED-3 strategy (a): find the pages/<module>.py owning `self.<element_key> = page.locator(`.

    The heal-journal carries element_key (the page-object attr name) but NOT the page module —
    codegen maps modules by page fingerprint, which the journal does not record. Rather than
    re-open Plan 02 to thread the module name into the journal, the ingest SCANS the run's
    generated page objects for the single line that assigns this attr (the template guarantees
    exactly one such line per attr across the project). Returns the owning module path, or None
    if no page object declares it (then the audit row still persists; only the rewrite is skipped).
    `pages_dir` is run_id-derived (worker-supplied) — never a path from the journal body (T-08-12).
    """
    if not pages_dir.is_dir():
        return None
    needle = _attr_assignment_re(element_key)
    for module in sorted(pages_dir.glob("*.py")):
        try:
            text = module.read_text(encoding="utf-8")
        except OSError:
            continue
        if needle.search(text):
            return module
    return None


def _selector_from_chain(chain: list) -> str | None:
    """The healed locator literal: the top chain entry's `value` (what the page object stores).

    The page object's `self.<attr> = page.locator(<literal>)` literal is the TOP chain entry's
    raw value string (codegen.locators._top_chain_entry). The rewrite swaps in the healed
    after_chain's top value. Returns None for an empty/malformed chain (no rewrite).
    """
    if not chain:
        return None
    top = chain[0]
    if isinstance(top, dict):
        value = top.get("value")
        return value if isinstance(value, str) and value else None
    if isinstance(top, str) and top:
        return top
    return None


def _apply_page_object_rewrite(
    pages_dir: Path, *, element_key: str, after_chain: list
) -> str | None:
    """For an auto_heal: resolve the owning module + rewrite its locator literal (ast-validated).

    Returns the rewritten module's path (str) on success, or None when the module/selector can't
    be resolved or the rewrite is a no-op. Tolerant of I/O errors and a non-parsing rewrite — a
    rewrite failure is LOGGED and skipped (the audit row + KG append still persist); it never
    crashes the worker. Only an `auto_heal` ever reaches here (the caller gates on outcome).
    """
    new_selector = _selector_from_chain(after_chain)
    if new_selector is None:
        return None
    module = _resolve_page_module(pages_dir, element_key)
    if module is None:
        log.warning("heal_rewrite_no_module", element_key=element_key, pages_dir=str(pages_dir))
        return None
    try:
        source = module.read_text(encoding="utf-8")
        rewritten = rewrite_page_object_locator(
            source, element_key=element_key, new_selector=new_selector
        )
        if rewritten == source:
            return None  # unknown-key no-op (shouldn't happen — module was matched — but safe)
        module.write_text(rewritten, encoding="utf-8")
        return str(module)
    except (OSError, SyntaxError) as exc:  # a bad rewrite never crashes the worker
        log.warning("heal_rewrite_failed", element_key=element_key, error=str(exc))
        return None


async def _append_kg_history(
    entry: dict, *, driver, now: str
) -> bool:
    """Best-effort KG Element-history append via the SINGLE writer (HEAL-03 write-back, T-08-14).

    Builds the merged history (explorer/locators.merge_locator_history) from the before+after
    chains and routes through kg/writer.append_element_history (parameterized + read-back guarded).
    Best-effort: a down neo4j (or an unknown element key -> read-back RAISE) is caught + logged so
    the worker never crashes mid-run — the audit row + page-object rewrite persist regardless.
    Returns True on a successful append, False otherwise.
    """
    # Imported lazily so importing this module never requires neo4j when the KG is off.
    from app.services.explorer.locators import merge_locator_history
    from app.services.kg import writer

    after_chain = entry.get("after_chain") or entry.get("before_chain") or []
    history = merge_locator_history([], after_chain, step=0)
    try:
        await writer.append_element_history(
            key=entry["element_key"],
            history_json=json.dumps(history),
            chain_json=json.dumps(after_chain),
            now=now,
            driver=driver,
        )
        return True
    except Exception as exc:  # noqa: BLE001 -- a down neo4j must not crash the worker (T-08-14)
        log.warning(
            "heal_kg_writeback_skipped", element_key=entry.get("element_key"), error=str(exc)
        )
        return False


async def ingest_heal_journal(
    db,
    run_id: str,
    flow_id: str,
    *,
    project_root: Path,
    journal_dir: Path,
    driver=None,
    now: str | None = None,
) -> list[str]:
    """Ingest the per-flow heal-journal: audit rows + page-object rewrite + KG write-back.

    The worker calls this INSIDE its fresh SessionLocal block AFTER the subprocess exits. For each
    VALID journal entry (parse_heal_journal: tolerant + bounded, T-08-09):

      1. `db.add(HealAudit(...))` — does NOT commit (the worker owns the commit on its session,
         so the heal rows ride the SAME transaction as the TestResult, Pitfall 2);
      2. for outcome == "auto_heal" ONLY, rewrite the owning page object under
         project_root/pages/<module>.py (ast-validated; quarantine/fail STAGE in the audit row,
         no rewrite — Open Q3);
      3. for auto_heal/applied, append the KG Element history via the single writer (best-effort —
         a down neo4j never crashes the worker, T-08-14).

    Both `project_root` (where pages/ lives, run_dir(run_id)/<target>) and `journal_dir` (where the
    in-spec layer wrote heal-journal.json, run_dir(run_id)/<flow_id>) are run_id-derived
    (worker-supplied) — NEVER paths from the journal body (T-08-12). Returns the list of journal
    outcomes (for reconcile_verdict).
    """
    import time

    from app.models.heal_audit import HealAudit

    now = now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    entries = parse_heal_journal(journal_dir)

    pages_dir = project_root / "pages"
    outcomes: list[str] = []
    for entry in entries:
        outcome = entry["outcome"]
        outcomes.append(outcome)

        # (1) the auditable row — added to the worker's session, committed by the worker.
        db.add(
            HealAudit(
                element_key=entry["element_key"],
                run_id=run_id,
                flow_id=flow_id,
                before_chain=entry["before_chain"],
                after_chain=entry["after_chain"] or None,
                confidence=entry["confidence"],
                outcome=outcome,
                live_match_count=entry["live_match_count"],
            )
        )

        # (2) the script-repo update — auto_heal ONLY (quarantine/fail stage in the audit row).
        if outcome == "auto_heal":
            _apply_page_object_rewrite(
                pages_dir,
                element_key=entry["element_key"],
                after_chain=entry["after_chain"],
            )

        # (3) the KG write-back — auto_heal/applied, best-effort (T-08-14).
        if outcome in ("auto_heal", "applied"):
            await _append_kg_history(entry, driver=driver, now=now)

    if entries:
        log.info(
            "heal_journal_ingested", run_id=run_id, flow_id=flow_id, entries=len(entries),
            outcomes=outcomes,
        )
    return outcomes
