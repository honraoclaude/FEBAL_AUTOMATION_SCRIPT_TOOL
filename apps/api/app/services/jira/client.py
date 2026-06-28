"""The `JiraGateway` Protocol + the real `AtlassianJira` implementation (JIRA-01/03/04).

The pipeline + router (Plan 04) depend on the `JiraGateway` Protocol — NEVER on the
concrete atlassian client — so the whole create/attach/JQL/comment/link contract is
keyless-CI-testable against `FakeJira` (fake.py). Only LIVE filing/dedup against a real
Jira Cloud + token is Manual-Only (there is no instance in dev).

THREE load-bearing disciplines (the 09 threat register):

  T-09-08 (Information Disclosure): the Jira token is a boot-safe optional secret
  (settings.jira_api_token: str|None=None). It is NEVER written to a structlog event —
  no event in this module carries url/username/password/token. The only logged facts
  are method name + (when present) the issue KEY, which is not a secret.

  T-09-09 (Denial of Service): atlassian-python-api 4.x is SYNC (requests). A bare sync
  call inside the async event loop blocks EVERY request. So EVERY library call is
  offloaded via `anyio.to_thread.run_sync(...)` — the gateway exposes async methods, the
  offload is cancellation-aware (anyio is the FastAPI-native bridge; do NOT add it).

  T-09-10 (Tampering): the client is constructed `cloud=True, api_version="3"` so the
  description accepts an ADF doc DICT (build_adf, adf.py) — never a string (Pitfall 2/6).

`is_configured` reflects whether the secret (token) is present; calling any method while
unconfigured raises `JiraNotConfiguredError` (a clear, secret-free error) rather than
constructing a half-broken client.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import anyio
import structlog

from app.core.config import settings

log = structlog.get_logger()


class JiraNotConfiguredError(RuntimeError):
    """Raised when a live Jira call is attempted without the Jira secret (token).

    Carries NO secret — only the fact that JIRA_API_TOKEN (and URL/email) are needed.
    The contract is fully testable against FakeJira; live filing is Manual-Only.
    """

    def __init__(self) -> None:
        super().__init__(
            "Jira is not configured: set JIRA_URL, JIRA_EMAIL and JIRA_API_TOKEN "
            "(live filing/dedup is Manual-Only; the contract is keyless via FakeJira)."
        )


@runtime_checkable
class JiraGateway(Protocol):
    """The async Jira contract both AtlassianJira and FakeJira satisfy (JIRA-01/03/04).

    All methods are async so the sync atlassian client can be offloaded behind the same
    shape the FakeJira double implements directly. The pipeline/router program to THIS.
    """

    async def create_issue(self, fields: dict) -> dict:
        """Create a Jira issue from a v3 `fields` dict (description is an ADF doc dict).

        Returns the created-issue dict (at minimum `{"key": "PROJ-123", ...}`).
        """
        ...

    async def add_attachment(self, key: str, path: str) -> None:
        """Attach one artifact (screenshot/video/log) by absolute path to issue `key`."""
        ...

    async def search_jql(self, jql: str) -> list[dict]:
        """Run a JQL search (dedup: `labels = "fp-<hash>" AND statusCategory != Done`).

        Returns the matched issues list (the `enhanced_jql` `res["issues"]`).
        """
        ...

    async def add_comment(self, key: str, adf: dict) -> None:
        """Add an ADF v3 comment to issue `key` (the update-on-dup path)."""
        ...

    async def create_issue_link(self, data: dict) -> None:
        """Create a Jira-side issue link (JIRA-04: the optional issue<->issue link)."""
        ...


class AtlassianJira:
    """`JiraGateway` over atlassian-python-api 4.x — every call offloaded via anyio.

    Constructed lazily: the underlying `atlassian.Jira` is only built on first use AND
    only when the secret is present, so importing this module (and constructing the
    object) is boot-safe without a token. Each method wraps the SYNC library call in
    `anyio.to_thread.run_sync` (T-09-09) and logs NO secret (T-09-08).
    """

    def __init__(self) -> None:
        # The concrete client is built lazily (first call) so construction is boot-safe
        # without a token. We never hold the token on the instance — it stays in settings.
        self._jira = None

    @property
    def is_configured(self) -> bool:
        """True only when URL + email + token are all present (live calls are possible)."""
        return bool(
            settings.jira_url and settings.jira_email and settings.jira_api_token
        )

    def _client(self):
        """Build (once) the sync atlassian client; raise if the secret is absent.

        cloud=True + api_version="3" is load-bearing: it makes the description field
        accept an ADF doc DICT (Pitfall 2/6 / T-09-10). The token is passed straight
        into the library and never copied to the instance or a log event.
        """
        if not self.is_configured:
            raise JiraNotConfiguredError()
        if self._jira is None:
            from atlassian import Jira

            self._jira = Jira(
                url=settings.jira_url,
                username=settings.jira_email,
                password=settings.jira_api_token,
                cloud=True,
                api_version="3",
            )
        return self._jira

    async def create_issue(self, fields: dict) -> dict:
        client = self._client()
        issue = await anyio.to_thread.run_sync(
            lambda: client.create_issue(fields=fields)
        )
        # Log the method + the resulting KEY only — never url/email/token/fields.
        log.info("jira_create_issue", key=(issue or {}).get("key"))
        return issue

    async def add_attachment(self, key: str, path: str) -> None:
        client = self._client()
        await anyio.to_thread.run_sync(lambda: client.add_attachment(key, path))
        log.info("jira_add_attachment", key=key)

    async def search_jql(self, jql: str) -> list[dict]:
        client = self._client()
        # enhanced_jql is the 2025 nextPageToken-paginated search (the jira pkg botched
        # this migration; 4.x is v3-native). We return res["issues"] (the matched list).
        res = await anyio.to_thread.run_sync(lambda: client.enhanced_jql(jql))
        issues = (res or {}).get("issues", [])
        log.info("jira_search_jql", matched=len(issues))
        return issues

    async def add_comment(self, key: str, adf: dict) -> None:
        client = self._client()
        await anyio.to_thread.run_sync(lambda: client.issue_add_comment(key, adf))
        log.info("jira_add_comment", key=key)

    async def create_issue_link(self, data: dict) -> None:
        client = self._client()
        await anyio.to_thread.run_sync(lambda: client.create_issue_link(data))
        log.info("jira_create_issue_link")
