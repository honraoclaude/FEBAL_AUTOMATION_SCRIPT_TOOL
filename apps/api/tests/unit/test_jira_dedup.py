"""Fingerprint-label JQL dedup + per-run create cap (JIRA-03 / D-05) over FakeJira — keyless.

`file_or_update(gateway, defect, artifacts, *, run_counter)` is the dedup+cap core. Driven
against the in-memory FakeJira (no Jira, no token), these tests pin:

  - MISS -> CREATE exactly one issue carrying the `fp-<hash>` label + the v3 fields, then
    add_attachment per artifact; the create consumes one cap slot (counter increments);
  - HIT (a second identical-fingerprint defect) -> UPDATE the existing key (add_comment +
    re-attach), NEVER a duplicate create, and NEVER consumes a cap slot (T-09-14);
  - at the cap (run_counter == settings.jira_max_tickets_per_run) a fresh MISS returns a
    NO-FILE result (action 'none', jira_key None) WITHOUT dropping the draft (Pitfall 5);
  - the JQL is a fixed `labels = "fp-<hash>" AND statusCategory != Done` template built from
    the server-side fingerprint — no user text in the query (T-09-13, V5).

Run: cd apps/api && uv run python -m pytest tests/unit/test_jira_dedup.py -q
"""

from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.defects.pipeline import file_or_update
from app.services.jira.fake import FakeJira

FP = "deadbeefcafe1234"


class _Defect:
    """A minimal Defect stand-in (the pipeline reads only these attrs for filing)."""

    def __init__(self, fingerprint: str = FP) -> None:
        self.run_id = "run-abc"
        self.flow_id = "flow-0"
        self.classification = "product_defect"
        self.confidence = 90
        self.fingerprint = fingerprint
        self.jira_label = f"fp-{fingerprint}"


@pytest.mark.asyncio
async def test_miss_creates_one_issue_with_fp_label() -> None:
    """A fingerprint MISS creates exactly one issue carrying the fp-<hash> label."""
    gw = FakeJira()
    res = await file_or_update(gw, _Defect(), artifacts=[], run_counter=0)

    assert res.action == "create"
    assert res.jira_key == "FAKE-1"
    assert res.counter == 1  # the create consumed one cap slot
    assert len(gw.issues) == 1
    (issue,) = gw.issues.values()
    assert f"fp-{FP}" in issue["labels"]


@pytest.mark.asyncio
async def test_jql_is_a_server_built_label_template_no_user_text() -> None:
    """The dedup search uses the fixed `labels = "fp-<hash>"` template (no injectable text)."""
    seen: list[str] = []

    class _Spy(FakeJira):
        async def search_jql(self, jql: str):
            seen.append(jql)
            return await super().search_jql(jql)

    gw = _Spy()
    await file_or_update(gw, _Defect(), artifacts=[], run_counter=0)
    assert seen == [f'labels = "fp-{FP}" AND statusCategory != Done']


@pytest.mark.asyncio
async def test_create_attaches_each_run_id_derived_artifact() -> None:
    """On a create, each provided artifact is attached to the new key."""
    gw = FakeJira()
    res = await file_or_update(
        gw, _Defect(), artifacts=["flow-0/test/trace.zip", "flow-0/test/shot.png"], run_counter=0
    )
    attached_keys = {k for (k, _p) in gw.attachments}
    assert attached_keys == {res.jira_key}
    assert len(gw.attachments) == 2


@pytest.mark.asyncio
async def test_second_identical_fingerprint_updates_never_duplicates() -> None:
    """A second identical-fingerprint defect HITS the JQL and UPDATES (comment + re-attach)."""
    gw = FakeJira()
    first = await file_or_update(gw, _Defect(), artifacts=[], run_counter=0)
    assert first.action == "create"

    second = await file_or_update(
        gw, _Defect(), artifacts=["flow-0/test/shot.png"], run_counter=first.counter
    )
    assert second.action == "update"
    assert second.jira_key == first.jira_key  # the EXISTING key, not a new one
    assert second.counter == first.counter  # an update consumes NO cap slot
    assert len(gw.issues) == 1  # never a duplicate
    assert len(gw.comments) == 1  # the update added a comment
    # The re-attached evidence is resolved to an ABSOLUTE run_dir-derived path (the containment
    # guard) — never the raw run-relative request string (T-09-15).
    assert len(gw.attachments) == 1
    (att_key, att_path) = gw.attachments[0]
    assert att_key == "FAKE-1"
    assert att_path.endswith("shot.png")
    assert "run-abc" in att_path


@pytest.mark.asyncio
async def test_at_the_cap_a_miss_returns_no_file_without_dropping(monkeypatch) -> None:
    """At the cap a fresh MISS returns NO-FILE (action 'none') — the draft is NOT dropped."""
    monkeypatch.setattr(settings, "jira_max_tickets_per_run", 1)
    gw = FakeJira()
    # First distinct create reaches the cap (counter -> 1 == max).
    first = await file_or_update(gw, _Defect("aaaa1111bbbb2222"), artifacts=[], run_counter=0)
    assert first.action == "create"
    assert first.counter == 1

    # A second DISTINCT fingerprint would be a create, but the cap is reached -> NO-FILE.
    res = await file_or_update(gw, _Defect("cccc3333dddd4444"), artifacts=[], run_counter=1)
    assert res.action == "none"
    assert res.jira_key is None
    assert res.counter == 1  # unchanged
    assert len(gw.issues) == 1  # no second issue was created


@pytest.mark.asyncio
async def test_update_is_free_under_the_cap(monkeypatch) -> None:
    """An UPDATE is never throttled by the cap (updates are free — only creates are capped)."""
    monkeypatch.setattr(settings, "jira_max_tickets_per_run", 1)
    gw = FakeJira()
    first = await file_or_update(gw, _Defect(), artifacts=[], run_counter=0)
    assert first.counter == 1  # at the cap now

    # Same fingerprint -> a HIT -> UPDATE, allowed even though the cap is reached.
    res = await file_or_update(gw, _Defect(), artifacts=[], run_counter=1)
    assert res.action == "update"
    assert res.jira_key == first.jira_key
