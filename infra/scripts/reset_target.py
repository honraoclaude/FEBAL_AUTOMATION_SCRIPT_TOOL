#!/usr/bin/env python3
"""Generic ``reset-target <name>`` snapshot/restore contract (QUAL-04 / D-10).

A small registry maps a target *name* to a reset *strategy*. Phase 1 ships one
strategy (``compose-restart``); Phase 4 adds ``db-snapshot`` for a stateful
target (OrangeHRM) by adding ONE registry entry — the CLI contract and callers
do not change (D-10). Phase 7's reproducibility checks consume the same exit-code
contract.

Contract:
  reset_target.py <name>
    1. perform the registered strategy for <name>
    2. wait until the target's health_url returns HTTP 200 (or time out)
    3. exit 0 on success / 1 on strategy-or-health failure / 2 on unknown name

Stdlib only — no third-party imports — so it runs with the host's plain Python
without a uv environment (and a Python entrypoint sidesteps the CRLF shell-script
pitfall, RESEARCH Pitfall 5).

Security (T-01-26): the CLI <name> is used ONLY as a dict KEY lookup into
STRATEGIES. It is never interpolated into the subprocess argv. The docker
compose argv is built entirely from registry constants as a list with no
shell=True, so a hostile target name cannot inject a command.

Honesty note (RESEARCH Pattern 6): SauceDemo's mutable state lives in browser
localStorage, so a container restart resets nothing the *tests* observe —
Playwright's fresh contexts provide the real isolation. The contract ships now
because Phase 4 (stateful targets) and Phase 7 (reproducibility) consume it.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Compose file resolved relative to THIS script's location so cwd does not
# matter (script lives at infra/scripts/, compose at infra/docker-compose.yml).
COMPOSE_FILE = (Path(__file__).resolve().parent.parent / "docker-compose.yml").resolve()

# Registry keyed by target name. Phase 4 adds e.g.
#   "orangehrm": {"strategy": "db-snapshot", "service": "orangehrm",
#                 "health_url": "http://localhost:8090", ...}
# without changing the CLI contract below.
STRATEGIES: dict[str, dict[str, str]] = {
    "saucedemo": {
        "strategy": "compose-restart",
        "service": "saucedemo",
        "health_url": "http://localhost:8080",
    },
}

HEALTH_TIMEOUT_SECONDS = 60
HEALTH_POLL_INTERVAL_SECONDS = 2


def _wait_for_health(health_url: str, timeout: int = HEALTH_TIMEOUT_SECONDS) -> bool:
    """Poll ``health_url`` until it returns HTTP 200 or the timeout elapses."""
    deadline = time.monotonic() + timeout
    last_err = "no attempt made"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=5) as resp:
                if resp.status == 200:
                    return True
                last_err = f"HTTP {resp.status}"
        except (urllib.error.URLError, OSError) as exc:  # connection refused etc.
            last_err = str(exc)
        time.sleep(HEALTH_POLL_INTERVAL_SECONDS)
    sys.stderr.write(
        f"reset-target: '{health_url}' not healthy within {timeout}s "
        f"(last: {last_err})\n"
    )
    return False


def _compose_restart(config: dict[str, str]) -> int:
    """compose-restart strategy: restart the service, then wait for health.

    argv is built from registry constants only (T-01-26): no name interpolation,
    no shell=True.
    """
    service = config["service"]
    argv = [
        "docker",
        "compose",
        "-f",
        str(COMPOSE_FILE),
        "restart",
        service,
    ]
    try:
        result = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        sys.stderr.write("reset-target: 'docker' not found on PATH\n")
        return 1
    if result.returncode != 0:
        sys.stderr.write(
            f"reset-target: 'docker compose restart {service}' failed "
            f"(exit {result.returncode}): {result.stderr.strip()}\n"
        )
        return 1
    if not _wait_for_health(config["health_url"]):
        return 1
    return 0


# Strategy dispatch — Phase 4 registers "db-snapshot" here.
STRATEGY_DISPATCH = {
    "compose-restart": _compose_restart,
}


def reset_target(name: str) -> int:
    config = STRATEGIES.get(name)
    if config is None:
        known = ", ".join(sorted(STRATEGIES)) or "(none)"
        sys.stderr.write(
            f"reset-target: unknown target '{name}'. Known targets: {known}\n"
        )
        return 2
    handler = STRATEGY_DISPATCH.get(config["strategy"])
    if handler is None:  # registry/dispatch drift guard
        sys.stderr.write(
            f"reset-target: no handler for strategy '{config['strategy']}'\n"
        )
        return 1
    return handler(config)


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        known = ", ".join(sorted(STRATEGIES)) or "(none)"
        sys.stderr.write(
            f"usage: reset_target.py <name>\nKnown targets: {known}\n"
        )
        return 2
    return reset_target(argv[0])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
