"""`FakeJira` — the in-memory `JiraGateway` double that makes JIRA-01/03/04 keyless-CI.

There is no Jira instance or token in dev (STATE.md), so the WHOLE create/attach/JQL/
comment/link contract is proven against this hand-written double (no recorded-HTTP lib,
no `responses`/`vcrpy` — RESEARCH "Zero other new packages"). The pipeline/router
program to the `JiraGateway` Protocol, so swapping FakeJira for AtlassianJira in tests is
a one-line change. Live filing/dedup is the only Manual-Only piece.

It records every call so a test can assert the contract:
  - create_issue mints `FAKE-{n}` and stores the fields (incl. the `fp-<hash>` label);
  - search_jql matches the `labels = "fp-<hash>" AND statusCategory != Done` dedup query
    against in-memory issues (so a second identical failure HITS and updates, never dups);
  - add_attachment / add_comment / create_issue_link append to recorded-call lists.
"""

from __future__ import annotations

import re

# Pull the `fp-<hash>` label out of a `labels = "fp-..."` clause (single or double
# quoted). The dedup JQL is built by the pipeline; the fake honours the same shape.
_LABEL_RE = re.compile(r'labels\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
# `statusCategory != Done` means "exclude resolved issues" — the fake treats any issue
# whose statusCategory is exactly "Done" as resolved (open issues use "To Do").
_EXCLUDE_DONE_RE = re.compile(
    r"statuscategory\s*!=\s*done", re.IGNORECASE
)


def _matches(jql: str, issue: dict) -> bool:
    """Match the dedup JQL (`labels = "fp-<hash>" [AND statusCategory != Done]`).

    A label clause is required to match (an issue must carry the queried fp-label); the
    `statusCategory != Done` clause, when present, excludes issues whose statusCategory
    is "Done". This is the keyless mirror of the live enhanced_jql dedup behaviour.
    """
    m = _LABEL_RE.search(jql)
    if not m:
        return False
    wanted_label = m.group(1)
    if wanted_label not in (issue.get("labels") or []):
        return False
    if _EXCLUDE_DONE_RE.search(jql) and issue.get("statusCategory") == "Done":
        return False
    return True


class FakeJira:
    """In-memory `JiraGateway` double recording every call (keyless CI for JIRA-01/03/04)."""

    def __init__(self) -> None:
        self.issues: dict[str, dict] = {}
        self._n = 0
        self.attachments: list[tuple[str, str]] = []
        self.comments: list[tuple[str, dict]] = []
        self.links: list[dict] = []

    @property
    def is_configured(self) -> bool:
        """The fake is always 'configured' — it needs no URL/email/token."""
        return True

    async def create_issue(self, fields: dict) -> dict:
        self._n += 1
        key = f"FAKE-{self._n}"
        # New issues are open ("To Do"), so the dedup query (statusCategory != Done)
        # finds them — exactly the live behaviour.
        self.issues[key] = {"key": key, **fields, "statusCategory": "To Do"}
        return self.issues[key]

    async def add_attachment(self, key: str, path: str) -> None:
        self.attachments.append((key, path))

    async def search_jql(self, jql: str) -> list[dict]:
        return [i for i in self.issues.values() if _matches(jql, i)]

    async def add_comment(self, key: str, adf: dict) -> None:
        self.comments.append((key, adf))

    async def create_issue_link(self, data: dict) -> None:
        self.links.append(data)
