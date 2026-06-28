"""The Jira agent seam (JIRA-01/03/04).

This package is the contract Plan 04's defect pipeline + router consume:

- `client.py` — the `JiraGateway` Protocol + the real `AtlassianJira` impl (the sync
  atlassian-python-api 4.x client, EVERY call offloaded via `anyio.to_thread.run_sync`
  so it never blocks the event loop — Pitfall 3 / T-09-09). The Jira token is a
  boot-safe optional secret that NEVER enters a log event (T-09-08).
- `fake.py` — the hand-written `FakeJira` in-memory double implementing the same
  Protocol, so all create/attach/JQL/comment/link LOGIC is keyless-CI-testable
  WITHOUT a real Jira instance or token.
- `adf.py` — the PURE `build_adf(...)` returning an ADF v3 description DOC DICT
  (a dict, not a string — Cloud v3 requires it, Pitfall 2/6).
- `description.py` — the LLM description-PROSE enrichment via the metered gateway
  (operation_type "defect.describe") with a DETERMINISTIC no-key fallback.
"""

from app.services.jira.client import AtlassianJira, JiraGateway, JiraNotConfiguredError
from app.services.jira.fake import FakeJira

__all__ = [
    "AtlassianJira",
    "FakeJira",
    "JiraGateway",
    "JiraNotConfiguredError",
]
