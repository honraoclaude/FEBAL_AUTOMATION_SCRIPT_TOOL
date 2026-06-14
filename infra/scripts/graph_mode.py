#!/usr/bin/env python3
"""``graph_mode <up|down>`` — stop-web-first choreography for Neo4j graph work (D-01/02/03).

The host has 5.7 GB RAM behind a 3 GB WSL cap. neo4j (trimmed to ~1 g) cannot run
alongside the web tier (1.5 g) under that cap. This helper enforces the ONLY safe
ordering (RESEARCH Pitfall 4):

  MEMORY MATH (must stay < 3 GB):
    default `up`:  postgres .5 + redis .25 + api 1 + web 1.5 + saucedemo .128 ≈ 3.4g  (web up, neo4j down)
    graph `up`:    postgres .5 + redis .25 + api 1 + neo4j 1 + saucedemo .128 ≈ 2.9g  (web DOWN, neo4j up)

  `up` path (NEVER reorder):
    1. docker compose stop web              # free the 1.5g FIRST
    2. docker compose --profile graph up -d neo4j
    3. poll http://localhost:7474 until healthy (or time out)
    → exit 0 so the caller runs graph work; neo4j stays up.

  `down`/`restore` path:
    1. docker compose start web             # restore the default stack

Starting neo4j BEFORE stopping web can blow the cap and OOM-kill the WSL VM, so this
script always stops web first. It NEVER raises the WSL cap.

Contract (mirrors reset_target.py):
  graph_mode.py up      bring neo4j up (web stopped) and wait for health
  graph_mode.py down    restore web (neo4j may be left running for the next call)
  exit 0 success / 1 compose-or-health failure / 2 unknown subcommand

Stdlib only — no third-party imports — so it runs with the host's plain Python
without a uv environment (and a Python entrypoint sidesteps the CRLF shell-script
pitfall, RESEARCH Pitfall 5).

Security (T-03-01, mirrors reset_target T-01-26): every compose argv token is a
literal constant. The only CLI input is the subcommand, used solely as a dict KEY
into SUBCOMMANDS — never interpolated into argv. All argv are lists with no
shell=True, so nothing the caller passes can inject a command.
"""

from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# Compose file resolved relative to THIS script's location so cwd does not matter
# (script lives at infra/scripts/, compose at infra/docker-compose.yml).
COMPOSE_FILE = (Path(__file__).resolve().parent.parent / "docker-compose.yml").resolve()

# Neo4j HTTP browser/health endpoint on the host (Bolt is 7687; HTTP 7474 answers 200
# once the DB is accepting). Matches the container healthcheck target.
NEO4J_HEALTH_URL = "http://localhost:7474"

HEALTH_TIMEOUT_SECONDS = 120  # first neo4j boot on this host is slow; be generous
HEALTH_POLL_INTERVAL_SECONDS = 3


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
        f"graph-mode: '{health_url}' not healthy within {timeout}s (last: {last_err})\n"
    )
    return False


def _run_compose(args: list[str]) -> int:
    """Run a `docker compose -f <COMPOSE_FILE> ...` command from literal-constant argv.

    No name interpolation, no shell=True (T-03-01). Returns the compose returncode,
    or 1 if `docker` is not on PATH.
    """
    argv = ["docker", "compose", "-f", str(COMPOSE_FILE), *args]
    try:
        result = subprocess.run(argv, capture_output=True, text=True)
    except FileNotFoundError:
        sys.stderr.write("graph-mode: 'docker' not found on PATH\n")
        return 1
    if result.returncode != 0:
        sys.stderr.write(
            f"graph-mode: '{' '.join(argv)}' failed (exit {result.returncode}): "
            f"{result.stderr.strip()}\n"
        )
        return 1
    return 0


def graph_up() -> int:
    """Stop web (Pitfall 4: FIRST), bring neo4j up under the graph profile, wait healthy."""
    # 1. Free web's 1.5g BEFORE neo4j starts — the whole point of this helper.
    if _run_compose(["stop", "web"]) != 0:
        return 1
    # 2. Start neo4j (graph profile is otherwise dormant — D-08).
    if _run_compose(["--profile", "graph", "up", "-d", "neo4j"]) != 0:
        return 1
    # 3. Wait until neo4j answers on the HTTP port.
    if not _wait_for_health(NEO4J_HEALTH_URL):
        return 1
    return 0


def graph_down() -> int:
    """Restore the default stack by starting web again (neo4j may be left running)."""
    return _run_compose(["start", "web"])


# Subcommand dispatch — the CLI arg is used ONLY as a dict KEY (T-03-01).
SUBCOMMANDS = {
    "up": graph_up,
    "down": graph_down,
}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in SUBCOMMANDS:
        known = ", ".join(sorted(SUBCOMMANDS))
        sys.stderr.write(f"usage: graph_mode.py <{'|'.join(sorted(SUBCOMMANDS))}>\n")
        sys.stderr.write(f"known subcommands: {known}\n")
        return 2
    return SUBCOMMANDS[argv[0]]()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
