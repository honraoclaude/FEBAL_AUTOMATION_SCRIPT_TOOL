# Phase 7: Execution Engine & Workers - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-20
**Phase:** 7-execution-engine-workers
**Areas discussed:** Suite tiers & risk selection, Worker model under 3GB, Artifacts & flaky/retry policy, Live view + kill switch + CI

---

## Suite tiers & risk-based selection (EXEC-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Gherkin @tags + dynamic risk | Native @smoke/@sanity/@regression tags on scenarios (editable in the review queue) → pytest-bdd marker selection; full = all; risk-based computed dynamically (top-N by risk + failure history) | ✓ |
| Risk-band auto-derived | Tiers auto-derived from flow risk bands; no manual tags; reviewer can't override | |
| Explicit tier column | A tier field on the scenario row set in the review UI | |

**User's choice:** Gherkin @tags + dynamic risk
**Notes:** Keeps tier composition in the reviewer's hands via pytest-bdd-native tagging; only risk-based is automatic and always reflects the latest risk + failure signal.

---

## Worker / parallelism model under the 3GB cap (EXEC-03)

| Option | Description | Selected |
|--------|-------------|----------|
| 1 worker, bounded prefetch | Single worker container, prefetch_count = parallel browser capacity (2–3 Chromium contexts); scale by replicas in K8s later | ✓ |
| N single-context workers | N containers, 1 context each; cleaner isolation but N overheads eat the 3GB budget | |
| 1 worker, pytest-xdist | Single worker runs pytest-xdist -n inside a job; not RabbitMQ-distributed flow-level parallelism | |

**User's choice:** 1 worker, bounded prefetch
**Notes:** Memory-safe under the 3GB cap; stateless worker so horizontal scale is just replica count later (Phase 11). Matches CLAUDE.md prefetch=browser-capacity pattern.

---

## Artifacts & flaky/retry policy (EXEC-04/05)

| Option | Description | Selected |
|--------|-------------|----------|
| Trace+screens always, video on fail, retry 2 | Per-step screenshots + trace + console/network logs always; video only on failure; retry 2× → pass-on-retry = flaky(infra), all-fail = product | ✓ |
| Everything always, retry 2 | Video on every test incl. passes; heaviest disk | |
| Minimal: screens on fail, no retry | Screenshots/logs on failure only, no video, no retries; loses flaky detection | |

**User's choice:** Trace+screens always, video on fail, retry 2
**Notes:** Balanced for the local disk/memory budget; retries provide the EXEC-05 infra-flake-vs-product-failure signal. Files under workspaces/<run_id>/, paths in Postgres.

---

## Live view, kill switch & CI (EXEC-06/02)

| Option | Description | Selected |
|--------|-------------|----------|
| Redis kill-flag poll + API trigger | Kill = Redis flag workers check between tests + drain + queue purge; CI = GH Actions calls the API and polls status | ✓ |
| Hard purge + worker SIGKILL | Purge queue + SIGKILL the worker; fast but orphans browsers / corrupts artifacts | |
| CI runs pytest directly | CI skips the queue and runs pytest in the runner; a second path that breaks determinism parity | |

**User's choice:** Redis kill-flag poll + API trigger
**Notes:** Graceful drain reuses the Phase-4 Redis seam; single engine code path for local/Docker/CI preserves the determinism goal (SC5).

---

## Claude's Discretion

- RabbitMQ exchange/queue/routing topology + per-run kill drain (aio-pika `connect_robust`, publisher confirms, QoS prefetch).
- Risk-based ranking formula (N, risk vs failure-history weighting) and failure-history source.
- pytest-playwright/conftest wiring for per-step capture + on-failure video + retries; flaky classifier rule + execution-history schema.
- Execution-history data model + migration 0007 + trends/durations/flaky queries.
- Determinism harness (reuse SauceDemo reset hook; keyless proof via the planted-spec trick).
- GitHub Actions trigger workflow + scoped CI auth token + status→check mapping.

## Deferred Ideas

- MinIO/S3 artifact store with presigned URLs → later (filesystem + Postgres paths this phase).
- Full 3-way failure classification + calibrated confidence + Jira → Phase 9.
- Self-healing of failing automation → Phase 8.
- Dashboards / RBAC / coverage / Elasticsearch execution search → Phase 10.
- K8s manifests + worker autoscaling + Prometheus/Grafana + platform CI/CD → Phase 11.
