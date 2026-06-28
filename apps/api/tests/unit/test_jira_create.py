"""Keyless JIRA-01/03/04 contract against FakeJira (no real Jira, no token, no neo4j).

The pipeline/router program to the `JiraGateway` Protocol, so the WHOLE create/attach/
JQL/comment/link contract is provable against the in-memory `FakeJira` double. These
tests pin that contract:

  - create_issue mints a key (FAKE-1) and stores the `fp-<hash>` label + the v3 fields;
  - add_attachment records every (key, path);
  - the dedup JQL `labels = "fp-<hash>" AND statusCategory != Done` HITS the created issue
    (so a second identical failure UPDATES it — comment + re-attach — never duplicates),
    and MISSES a different fingerprint;
  - a Done issue is excluded by `statusCategory != Done`;
  - add_comment + create_issue_link record their calls (the update-on-dup + JIRA-04 link);
  - both FakeJira AND AtlassianJira satisfy the JiraGateway Protocol (one shape).

Token-safety acceptance (T-09-08): AtlassianJira, when UNCONFIGURED, raises a clear
secret-free JiraNotConfiguredError rather than constructing a half-broken client; and the
jira-client source carries no structlog event referencing the token/password.

Run: cd apps/api && uv run python -m pytest tests/unit/test_jira_create.py -q
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.jira import (
    AtlassianJira,
    FakeJira,
    JiraGateway,
    JiraNotConfiguredError,
)

FP = "deadbeefcafe1234"
DEDUP_JQL = f'labels = "fp-{FP}" AND statusCategory != Done'


def _fields(label: str = f"fp-{FP}") -> dict:
    return {
        "project": {"key": "QA"},
        "issuetype": {"name": "Bug"},
        "summary": "Login fails on submit",
        "description": {"type": "doc", "version": 1, "content": []},
        "labels": [label],
        "priority": {"name": "High"},
    }


async def test_create_issue_mints_key_with_fp_label_and_fields() -> None:
    fake = FakeJira()
    issue = await fake.create_issue(_fields())

    assert issue["key"] == "FAKE-1"
    assert issue["labels"] == [f"fp-{FP}"]
    assert issue["summary"] == "Login fails on submit"
    # New issues are open so the dedup query (statusCategory != Done) finds them.
    assert issue["statusCategory"] == "To Do"
    # Stored under the minted key.
    assert fake.issues["FAKE-1"]["key"] == "FAKE-1"


async def test_dedup_jql_hits_the_created_issue() -> None:
    fake = FakeJira()
    await fake.create_issue(_fields())

    hits = await fake.search_jql(DEDUP_JQL)
    assert [i["key"] for i in hits] == ["FAKE-1"]


async def test_dedup_jql_misses_a_different_fingerprint() -> None:
    fake = FakeJira()
    await fake.create_issue(_fields())

    other = await fake.search_jql('labels = "fp-0000000000000000" AND statusCategory != Done')
    assert other == []


async def test_dedup_excludes_done_issues() -> None:
    fake = FakeJira()
    await fake.create_issue(_fields())
    # Resolve the issue -> statusCategory Done -> excluded by `statusCategory != Done`.
    fake.issues["FAKE-1"]["statusCategory"] = "Done"

    assert await fake.search_jql(DEDUP_JQL) == []


async def test_update_on_dup_records_comment_and_reattach_never_duplicates() -> None:
    fake = FakeJira()
    await fake.create_issue(_fields())

    # Second identical failure: dedup HITS, so we update (comment + re-attach) — no create.
    hits = await fake.search_jql(DEDUP_JQL)
    existing = hits[0]["key"]
    await fake.add_comment(existing, {"type": "doc", "version": 1, "content": []})
    await fake.add_attachment(existing, str(Path("/runs/r1/shot.png")))

    assert len(fake.issues) == 1  # never duplicated
    assert fake.comments == [(existing, {"type": "doc", "version": 1, "content": []})]
    assert fake.attachments == [(existing, str(Path("/runs/r1/shot.png")))]


async def test_add_attachment_records_each_path() -> None:
    fake = FakeJira()
    issue = await fake.create_issue(_fields())
    key = issue["key"]

    for name in ("shot.png", "trace.zip", "log.txt"):
        await fake.add_attachment(key, str(Path(f"/runs/r1/{name}")))

    assert fake.attachments == [
        (key, str(Path("/runs/r1/shot.png"))),
        (key, str(Path("/runs/r1/trace.zip"))),
        (key, str(Path("/runs/r1/log.txt"))),
    ]


async def test_create_issue_link_records_the_link() -> None:
    fake = FakeJira()
    link = {
        "type": {"name": "Relates"},
        "inwardIssue": {"key": "FAKE-2"},
        "outwardIssue": {"key": "FAKE-1"},
    }
    await fake.create_issue_link(link)

    assert fake.links == [link]


def test_both_impls_satisfy_the_jira_gateway_protocol() -> None:
    # runtime_checkable Protocol: both the fake and the real client present the contract.
    assert isinstance(FakeJira(), JiraGateway)
    assert isinstance(AtlassianJira(), JiraGateway)


async def test_atlassian_jira_unconfigured_raises_secret_free_error(monkeypatch) -> None:
    # T-09-08: with no token, a live call raises a clear, secret-free error (never builds
    # a half-broken client, never logs the token). Tokenless == not configured.
    from app.core.config import settings

    monkeypatch.setattr(settings, "jira_api_token", None, raising=False)
    client = AtlassianJira()
    assert client.is_configured is False

    with pytest.raises(JiraNotConfiguredError) as exc:
        await client.create_issue(_fields())
    # The error message carries the env-var names, NOT any secret value.
    assert "JIRA_API_TOKEN" in str(exc.value)
    assert "secret" not in str(exc.value).lower() or "token" in str(exc.value)


def test_client_source_logs_no_token_or_password() -> None:
    # T-09-08 static acceptance: no structlog event in the jira client carries the token
    # or password field. We scan the source for a log call referencing those secret keys.
    src = (
        Path(__file__).resolve().parents[2]
        / "app"
        / "services"
        / "jira"
        / "client.py"
    ).read_text(encoding="utf-8")

    # No log.* line may mention the token/password (the values live only in settings and
    # are passed straight into the library constructor, never into an event).
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith("log."):
            lowered = stripped.lower()
            assert "token" not in lowered, f"token leaked into a log event: {stripped}"
            assert "password" not in lowered, f"password leaked into a log event: {stripped}"
