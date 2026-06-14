"""Deterministic, LLM-free explore crawl (D-04/D-06) — the Playwright→Neo4j seam.

`run_explore` is the POST /explore BackgroundTask entrypoint. It proves two seams with
ZERO gateway calls: (1) an async Playwright login+crawl of the registered SauceDemo
target, (2) writing minimal Page/NavigatesTo nodes to Neo4j, both threaded by run_id.

CRITICAL invariants:
  - Pitfall 2: the task opens its OWN `async with SessionLocal()` — NEVER the request's
    get_db session (that session is closed once the 202 response is sent). The lifespan
    neo4j driver IS safe to reuse across tasks.
  - PLAT-07 / T-03-06: credentials come ONLY from target_service.get_decrypted_credentials
    (the single decrypt surface) and are NEVER written to a Page node or logged.
  - T-03-05: graph writes use PARAMETERIZED Cypher only — never f-string page-derived
    text into the query.
  - T-03-09: the whole body is wrapped so a failure flips the run to "failed" with an
    error string rather than crashing the task silently.

The `key`/MERGE here is a deliberate TRACER seam (a normalized-url node identity), NOT
the Phase-5 structural fingerprint — Phase 5 replaces write_page_graph.
"""

from urllib.parse import urlsplit, urlunsplit

import structlog
from neo4j import AsyncDriver
from playwright.async_api import async_playwright

from app.core.neo4j_driver import get_neo4j
from app.db.session import SessionLocal
from app.services import run_service, target_service

log = structlog.get_logger()

# SauceDemo (Swag Labs) stable selectors the crawl OBSERVES (A4 / interfaces).
_USER_SEL = "#user-name"
_PASS_SEL = "#password"
_LOGIN_SEL = "#login-button"
_INVENTORY_SEL = ".inventory_list"
# One deterministic click target on the inventory page → the second (detail) page.
_ITEM_LINK_SEL = ".inventory_item_name, [data-test='inventory-item-name']"


def _page_key(url: str) -> str:
    """Stable node identity for the tracer: scheme+host+path (drop query/fragment).

    A normalized-url key — the TRACER seam, NOT the Phase-5 structural fingerprint.
    """
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") or "/", "", ""))


async def write_page_graph(
    driver: AsyncDriver,
    run_id: str,
    landing: dict,
    second: dict,
) -> None:
    """Write two Page nodes + one NavigatesTo edge via PARAMETERIZED Cypher (T-03-05).

    TRACER seam: a minimal landing→second navigation. Phase 5 replaces this with the
    full structural-fingerprint write. Never f-string page text into the query.
    """
    cypher = (
        "MERGE (a:Page {key:$a_key}) "
        "ON CREATE SET a.url=$a_url, a.title=$a_title, a.run_id=$run_id "
        "MERGE (b:Page {key:$b_key}) "
        "ON CREATE SET b.url=$b_url, b.title=$b_title, b.run_id=$run_id "
        "MERGE (a)-[:NavigatesTo]->(b)"
    )
    async with driver.session() as session:
        await session.run(
            cypher,
            a_key=landing["key"],
            a_url=landing["url"],
            a_title=landing["title"],
            b_key=second["key"],
            b_url=second["url"],
            b_title=second["title"],
            run_id=run_id,
        )


async def run_explore(run_id: str, target_id: int) -> None:
    """BackgroundTask entrypoint: deterministic SauceDemo crawl → Neo4j, threaded by run_id."""
    # Pitfall 2: a FRESH session owned by this task — never the request's get_db session.
    async with SessionLocal() as db:
        try:
            await run_service.set_status(db, run_id, "running")

            target = await target_service.get_target(db, target_id)
            if target is None:
                raise target_service.TargetNotFoundError(target_id)
            # The SINGLE decrypt surface — creds never touch the graph or logs (PLAT-07).
            user, password = await target_service.get_decrypted_credentials(db, target_id)
            base_url = target.base_url.rstrip("/")

            async with async_playwright() as p:
                browser = await p.chromium.launch()
                try:
                    page = await browser.new_page()
                    await page.goto(f"{base_url}/")
                    await page.fill(_USER_SEL, user)
                    await page.fill(_PASS_SEL, password)
                    await page.click(_LOGIN_SEL)
                    await page.wait_for_selector(_INVENTORY_SEL)

                    landing = {
                        "url": page.url,
                        "title": await page.title(),
                        "key": _page_key(page.url),
                    }

                    # One deterministic click → the second page (item detail).
                    await page.click(_ITEM_LINK_SEL)
                    await page.wait_for_load_state("networkidle")
                    second = {
                        "url": page.url,
                        "title": await page.title(),
                        "key": _page_key(page.url),
                    }
                finally:
                    await browser.close()

            # The lifespan neo4j driver IS safe to reuse across tasks.
            await write_page_graph(get_neo4j(), run_id, landing, second)

            await run_service.set_status(db, run_id, "passed")
            log.info("explore_completed", run_id=run_id, target_id=target_id)
        except Exception as exc:  # noqa: BLE001 -- never crash the task silently (T-03-09)
            # Capture failure as status+error; do NOT log credentials or page secrets.
            await run_service.set_status(db, run_id, "failed", error=str(exc))
            log.warning("explore_failed", run_id=run_id, target_id=target_id, error=str(exc))
