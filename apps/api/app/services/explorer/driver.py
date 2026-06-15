"""LangGraph explorer driver (Phase 4, EXPL-03/EXPL-05) — POST /explore BackgroundTask.

`run_explore` is the entrypoint. It KEEPS the Phase-3 wrapper verbatim (fresh SessionLocal,
set_status running/passed/failed, single decrypt surface) and REPLACES the deterministic
crawl body with a real LangGraph StateGraph loop:
  - launch ONE Playwright browser/context/page, log in (single decrypt surface),
  - register the live handles in the per-run registry BEFORE ainvoke (H-1),
  - build the graph via get_checkpointer() + a per-run ExploreBudget and ainvoke it with
    config thread_id=run_id (resumable),
  - in a finally: browser.close() (Pitfall 2 memory) AND clear_handles(run_id) so the
    non-serializable handle never outlives the run (H-1),
  - persist the terminal stop_reason onto the Run row.

CRITICAL invariants (carried from Phase 3):
  - Pitfall 2: the task opens its OWN SessionLocal — never the request's get_db session.
  - PLAT-07/T-03-06: creds ONLY via target_service.get_decrypted_credentials; never logged,
    never written to a node.
  - T-03-09: a failure flips the run to "failed" with an error string, never a silent crash.
"""

from __future__ import annotations

import time

import structlog
from playwright.async_api import async_playwright

from app.core.checkpointer import get_checkpointer
from app.core.config import settings
from app.db.session import SessionLocal
from app.services import run_service, target_service
from app.services.explorer.actions import page_key
from app.services.explorer.budget import build_budget
from app.services.explorer.graph import build_explorer_graph
from app.services.explorer.state import (
    STOP_REASONS,
    BrowserHandles,
    clear_handles,
    set_handles,
)

log = structlog.get_logger()

# SauceDemo (Swag Labs) stable selectors — the Slice-1 login fast path. The generalized
# input[type=password] heuristic + storageState reuse + relogin recovery land in Slice 2.
_USER_SEL = "#user-name"
_PASS_SEL = "#password"
_LOGIN_SEL = "#login-button"
_INVENTORY_SEL = ".inventory_list"


async def _login(page, base_url: str, user: str, password: str) -> None:  # noqa: ANN001
    """Drive the SauceDemo login with the decrypted creds (single decrypt surface)."""
    await page.goto(f"{base_url}/", wait_until="domcontentloaded")
    await page.fill(_USER_SEL, user)
    await page.fill(_PASS_SEL, password)
    await page.click(_LOGIN_SEL)
    await page.wait_for_selector(_INVENTORY_SEL)


async def run_explore(run_id: str, target_id: int) -> None:
    """BackgroundTask entrypoint: a LangGraph StateGraph crawl of the target, threaded by run_id."""
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
            budget = build_budget(getattr(target, "budget_overrides", None), settings)

            stop_reason: str | None = None
            async with async_playwright() as p:
                browser = await p.chromium.launch()
                try:
                    context = await browser.new_context()
                    page = await context.new_page()
                    await _login(page, base_url, user, password)

                    # H-1: register the live, NON-serializable handles OUTSIDE state.
                    set_handles(run_id, BrowserHandles(browser, context, page))

                    initial_state = {
                        "run_id": run_id,
                        "target_id": target_id,
                        "base_url": base_url,
                        "current_url": page.url,
                        "step": 0,
                        "depth": 0,
                        "started_at": time.monotonic(),
                        "seen_keys": {},
                        "seen_pairs": [],
                        "steps_since_new": 0,
                        "frontier": [],
                        "visited_keys": [page_key(page.url)],
                        "action_menu": [],
                        "chosen_index": None,
                        "pending_action": None,
                        "last_snapshot_yaml": "",
                        "current_screenshot": None,
                        "events": [],
                        "stop_reason": None,
                    }

                    graph = build_explorer_graph(get_checkpointer(), budget)
                    final_state = await graph.ainvoke(
                        initial_state,
                        config={"configurable": {"thread_id": run_id}},
                    )
                    stop_reason = final_state.get("stop_reason") or "stopped"
                finally:
                    # H-1 lifecycle: tear down the non-serializable handle + free Chromium
                    # memory (Pitfall 2) regardless of how the invoke ended.
                    await browser.close()
                    clear_handles(run_id)

            if stop_reason not in STOP_REASONS:
                stop_reason = "stopped"
            await run_service.set_status(db, run_id, "passed")
            await _record_stop_reason(db, run_id, stop_reason)
            log.info("explore_completed", run_id=run_id, target_id=target_id, stop_reason=stop_reason)
        except Exception as exc:  # noqa: BLE001 -- never crash the task silently (T-03-09)
            await run_service.set_status(db, run_id, "failed", error=str(exc))
            await _record_stop_reason(db, run_id, "failed")
            log.warning("explore_failed", run_id=run_id, target_id=target_id, error=str(exc))


async def _record_stop_reason(db, run_id: str, stop_reason: str) -> None:  # noqa: ANN001
    """Persist the terminal stop_reason onto the Run row (best-effort, idempotent)."""
    run = await run_service.get_run(db, run_id)
    if run is not None:
        run.stop_reason = stop_reason
        await db.commit()
