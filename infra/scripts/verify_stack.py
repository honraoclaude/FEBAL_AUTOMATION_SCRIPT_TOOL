#!/usr/bin/env python3
"""INFRA-01 evidence script: prove the Phase 1 stack is correctly stood up.

This is the machine-checkable half of the phase gate (the host-level WSL/Vmmem
and UI-walkthrough checks are human-only — see 01-VALIDATION.md Manual-Only table
and docs/dev-setup.md). Run it against the running stack:

    python infra/scripts/verify_stack.py

It asserts four things and prints a PASS/FAIL line per check group, exiting 0
only if every group passes (so it is self-demonstrating: stop a service and it
exits non-zero naming that service):

  1. Default-profile services are EXACTLY {postgres, redis, api, web, saucedemo}
     and every one reports Health=healthy (docker compose ps --format json).
  2. Dormant services {neo4j, rabbitmq, elasticsearch} are ABSENT from ps output
     — profiles are verified by absence, never by a flag (RESEARCH anti-pattern:
     a profile that silently activates is worse than one that never runs).
  3. Every running container has a NON-ZERO HostConfig.Memory limit
     (docker inspect -f '{{.HostConfig.Memory}}') — PITFALLS Pitfall 3: an
     unbounded container on a 3 GB WSL cap OOM-kills its neighbours.
  4. The three host-facing entrypoints answer: GET /health on the api returns 200
     with postgres+redis both true; the web root returns 200 or a 3xx redirect
     (unauthenticated `/` 307s to /login); the saucedemo root returns 200.

Stdlib only — no third-party imports — so it runs with the host's plain Python
without a uv environment, mirroring reset_target.py.

Security (T-01-28 / read-only boundary): every docker subprocess is built from
constants as an argv list with no shell=True and no untrusted interpolation; the
script only READS daemon state (ps / inspect) and probes HTTP — it mutates
nothing.

Host ports differ from container ports by design (01-02 decision): the api is
published on host 8001 because host 8000 is held by an unrelated local project.
The container-internal port stays 8000. HTTP probes below use the HOST ports.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Compose file resolved relative to THIS script so cwd does not matter
# (script lives at infra/scripts/, compose at infra/docker-compose.yml).
COMPOSE_FILE = (Path(__file__).resolve().parent.parent / "docker-compose.yml").resolve()

# The exact default-profile service set (no `profiles:` key in compose).
EXPECTED_SERVICES = {"postgres", "redis", "api", "web", "saucedemo"}

# Dormant services carry `profiles:` and must NEVER appear in a plain `up`.
DORMANT_SERVICES = {"neo4j", "rabbitmq", "elasticsearch"}

# Host-facing HTTP entrypoints (HOST ports — api is 8001, not 8000).
HTTP_PROBES = [
    {
        "name": "api /health (8001)",
        "url": "http://localhost:8001/health",
        "expect": "health-json",  # 200 + {"postgres": true, "redis": true}
    },
    {
        "name": "web / (3000)",
        "url": "http://localhost:3000",
        "expect": "ok-or-redirect",  # 200 or 3xx (unauth `/` 307s to /login)
    },
    {
        "name": "saucedemo / (8080)",
        "url": "http://localhost:8080",
        "expect": "ok",  # 200
    },
]

HTTP_TIMEOUT_SECONDS = 8


class CheckResult:
    """One check group's outcome: a name, pass/fail, and a detail line."""

    def __init__(self, name: str, passed: bool, detail: str) -> None:
        self.name = name
        self.passed = passed
        self.detail = detail


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    """Run a docker subprocess (argv list, no shell) and return the result."""
    return subprocess.run(argv, capture_output=True, text=True)


def _compose_ps() -> list[dict]:
    """Return parsed `docker compose ps --format json` rows for the project.

    Compose emits either a JSON array or newline-delimited JSON objects
    depending on version; handle both.
    """
    argv = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "ps",
        "--format",
        "json",
    ]
    result = _run(argv)
    if result.returncode != 0:
        raise RuntimeError(
            f"'docker compose ps' failed (exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )
    out = result.stdout.strip()
    if not out:
        return []
    # NDJSON (one object per line) — the common Compose v2/v5 shape.
    if out.lstrip().startswith("{"):
        rows = []
        for line in out.splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows
    # JSON array shape.
    return json.loads(out)


def _container_memory_limit(container_id: str) -> int:
    """Return HostConfig.Memory (bytes) for a container via docker inspect."""
    argv = [
        "docker",
        "inspect",
        "-f",
        "{{.HostConfig.Memory}}",
        container_id,
    ]
    result = _run(argv)
    if result.returncode != 0:
        raise RuntimeError(
            f"'docker inspect {container_id}' failed "
            f"(exit {result.returncode}): {result.stderr.strip()}"
        )
    raw = result.stdout.strip()
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"unexpected memory value for {container_id}: {raw!r}"
        ) from exc


def check_services_present_and_healthy(rows: list[dict]) -> CheckResult:
    """(1) Exactly the default service set, every one healthy."""
    running = {
        r.get("Service")
        for r in rows
        if r.get("State") == "running"
    }
    missing = EXPECTED_SERVICES - running
    extra = running - EXPECTED_SERVICES - DORMANT_SERVICES
    if missing:
        return CheckResult(
            "services present",
            False,
            f"missing/not-running: {', '.join(sorted(missing))}",
        )
    if extra:
        return CheckResult(
            "services present",
            False,
            f"unexpected extra services: {', '.join(sorted(extra))}",
        )

    unhealthy = []
    for r in rows:
        if r.get("Service") in EXPECTED_SERVICES:
            health = r.get("Health", "")
            if health != "healthy":
                unhealthy.append(f"{r.get('Service')}={health or 'no-healthcheck'}")
    if unhealthy:
        return CheckResult(
            "services healthy",
            False,
            f"not healthy: {', '.join(sorted(unhealthy))}",
        )
    return CheckResult(
        "services present + healthy",
        True,
        f"all healthy: {', '.join(sorted(EXPECTED_SERVICES))}",
    )


def check_dormant_absent(rows: list[dict]) -> CheckResult:
    """(2) Dormant profile services must be absent from ps output."""
    present = {r.get("Service") for r in rows} & DORMANT_SERVICES
    if present:
        return CheckResult(
            "dormant absent",
            False,
            f"dormant services unexpectedly present: {', '.join(sorted(present))}",
        )
    return CheckResult(
        "dormant absent",
        True,
        f"absent as expected: {', '.join(sorted(DORMANT_SERVICES))}",
    )


def check_memory_limits(rows: list[dict]) -> CheckResult:
    """(3) Every running container reports a non-zero HostConfig.Memory."""
    unbounded = []
    details = []
    for r in rows:
        if r.get("State") != "running":
            continue
        cid = r.get("ID") or r.get("Name")
        service = r.get("Service", cid)
        limit = _container_memory_limit(cid)
        if limit <= 0:
            unbounded.append(service)
        else:
            details.append(f"{service}={limit}")
    if unbounded:
        return CheckResult(
            "memory limits",
            False,
            f"unbounded (Memory=0): {', '.join(sorted(unbounded))}",
        )
    return CheckResult(
        "memory limits",
        True,
        "; ".join(sorted(details)),
    )


def _probe(url: str) -> tuple[int, str]:
    """GET url; return (status, body). 3xx is returned, not auto-followed."""
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):  # noqa: D401, ANN001
            return None  # surface the redirect status instead of following it

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(url, timeout=HTTP_TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", "replace")
            return resp.status, body
    except urllib.error.HTTPError as exc:
        # 3xx/4xx/5xx arrive here when redirects are suppressed.
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:  # noqa: BLE001
            pass
        return exc.code, body


def check_http_entrypoints() -> CheckResult:
    """(4) api /health, web root, saucedemo root all answer correctly."""
    failures = []
    oks = []
    for probe in HTTP_PROBES:
        name, url, expect = probe["name"], probe["url"], probe["expect"]
        try:
            status, body = _probe(url)
        except (urllib.error.URLError, OSError) as exc:
            failures.append(f"{name}: unreachable ({exc})")
            continue

        if expect == "health-json":
            if status != 200:
                failures.append(f"{name}: HTTP {status} (want 200)")
                continue
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                failures.append(f"{name}: 200 but body is not JSON")
                continue
            if data.get("postgres") is True and data.get("redis") is True:
                oks.append(f"{name}: 200 postgres+redis true")
            else:
                failures.append(
                    f"{name}: 200 but postgres={data.get('postgres')} "
                    f"redis={data.get('redis')}"
                )
        elif expect == "ok-or-redirect":
            if status == 200 or 300 <= status < 400:
                oks.append(f"{name}: HTTP {status}")
            else:
                failures.append(f"{name}: HTTP {status} (want 200 or 3xx)")
        else:  # "ok"
            if status == 200:
                oks.append(f"{name}: 200")
            else:
                failures.append(f"{name}: HTTP {status} (want 200)")

    if failures:
        return CheckResult("http entrypoints", False, "; ".join(failures))
    return CheckResult("http entrypoints", True, "; ".join(oks))


def main() -> int:
    print(f"verify_stack.py — INFRA-01 evidence (compose: {COMPOSE_FILE})\n")

    try:
        rows = _compose_ps()
    except RuntimeError as exc:
        print(f"FAIL  compose ps      : {exc}")
        return 1

    if not rows:
        print("FAIL  compose ps      : no services running — start the stack first")
        return 1

    results = [
        check_services_present_and_healthy(rows),
        check_dormant_absent(rows),
        check_memory_limits(rows),
        check_http_entrypoints(),
    ]

    all_passed = True
    for res in results:
        tag = "PASS" if res.passed else "FAIL"
        if not res.passed:
            all_passed = False
        print(f"{tag}  {res.name:<22}: {res.detail}")

    print()
    if all_passed:
        print("RESULT: PASS — Phase 1 stack verified (INFRA-01 evidence).")
        return 0
    print("RESULT: FAIL — see failing checks above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
