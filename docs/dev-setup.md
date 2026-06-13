# Development Environment Setup

Windows 11 + Docker Desktop (WSL2 backend). All platform services run locally via Docker Compose; a documented **hybrid mode** (infra in Docker, API/web on the host) is the primary fast-iteration workflow.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker Desktop | 4.x (Engine 29.x, Compose v5.x) | WSL2 backend required |
| Node.js | 22 LTS (host: 24 also fine — Next 16 needs >= 20.9) | Frontend + executor tooling |
| Python | 3.13.x | Backend (FastAPI), managed with uv |
| uv | 0.11.x | Python package/env manager (`uv sync`) |

## 1. WSL2 memory cap (`.wslconfig`) — do this first

Without a cap, the WSL2 VM (`Vmmem` / `VmmemWSL`) grabs memory and does not return it, OOM-killing containers (PITFALLS Pitfall 9 / INFRA-01).

1. Copy the template to your user profile (skip if you already have one):

   ```powershell
   if (-not (Test-Path "$env:USERPROFILE\.wslconfig")) { Copy-Item .wslconfig.example "$env:USERPROFILE\.wslconfig" }
   ```

2. **Tune `memory=` to YOUR host's RAM.** This is the single most important setting:

   | Host RAM | Recommended `memory=` | Notes |
   |----------|-----------------------|-------|
   | 24–32 GB | `16GB` (template default) | Leave ≥ 8 GB for Windows |
   | 8 GB     | `4GB`–`5GB` | |
   | ~6 GB (low-RAM) | `3GB` | The full Phase 1 stack (api 1g + web 1.5g + postgres 512m + redis 256m + saucedemo 128m ≈ 3.4 GB of *limits*) is close to this cap. See the low-RAM note below. |

   > **Low-RAM hosts (≤ 8 GB):** the template's `16GB` default will wedge the WSL VM on a machine that does not have that much RAM (the VM tries to reserve memory the host cannot give it, and Docker Desktop fails to start — this required a reboot to recover on a 5.7 GB machine). Always edit `memory=` down to fit your host **before** the first `wsl --shutdown`. On a 3 GB cap the stack still boots, but a *simultaneous* cold start of all five services can brush the ceiling — if `up --wait` ever OOMs, bring services up in stages (`up -d postgres redis api`, then `up -d web saucedemo`) rather than raising the cap.

3. Apply it: `wsl --shutdown`, then restart Docker Desktop.

   > `wsl --shutdown` stops the Docker engine and every container. Do it when no containers are mid-work. After Docker Desktop restarts, bring the stack back with the canonical command in §3 and confirm health with `verify_stack.py` (§6). Watch `Vmmem`/`VmmemWSL` in **Task Manager → Details**: its memory should settle *near the `memory=` cap*, not climb toward total host RAM. (This is the human half of the INFRA-01 phase gate — no script can read the Windows memory meter.)

## 2. Environment file (`.env`)

```powershell
Copy-Item .env.example .env
```

Then replace every `<generate...>` placeholder using the one-liners documented inline in `.env.example`. The three secrets you must generate:

```powershell
# JWT_SECRET — signs access/refresh tokens
python -c "import secrets; print(secrets.token_urlsafe(48))"

# TARGET_CREDENTIAL_KEY — Fernet key encrypting target credentials at rest
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# ADMIN_PASSWORD — first admin login (any strong value)
python -c "import secrets; print(secrets.token_urlsafe(18))"
```

`.env` is gitignored — **never commit it**. This one file is the single config source for **both** Compose (`--env-file .env`) and hybrid host mode (§4) — there is no second config to keep in sync (D-09).

## 3. Run mode A — full Docker stack (canonical)

Canonical invocation, from the **repo root**:

```powershell
docker compose -f infra/docker-compose.yml --env-file .env up -d --build --wait
```

`--wait` blocks until every service is healthy (or fails). The Phase 1 **default profile** is exactly five services:

| Service | Host port | Role |
|---------|-----------|------|
| postgres | 5432 | App DB (executions, RBAC, targets) |
| redis | 6379 | Cache / locks |
| api | **8001** | FastAPI backend (container-internal 8000; host 8000 is held by an unrelated local project) |
| web | 3000 | Next.js dashboard |
| saucedemo | 8080 | Self-hosted demo target to explore |

Neo4j / RabbitMQ / Elasticsearch are defined as **dormant** compose profiles and never start by default (they activate in Phases 3 / 7 / 9–10).

Open http://localhost:3000, you are redirected to `/login`; sign in with `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env`.

Tear down (and wipe the DB volume for a clean-state run): `docker compose -f infra/docker-compose.yml --env-file .env down -v`. The api re-seeds the admin idempotently on next startup, so admin login survives a `down -v`; registered targets are wiped.

## 4. Run mode B — hybrid host (primary iteration workflow, D-09)

The Docker `web`/`api` mounts give you a working stack, **not** sub-second hot reload (Turbopack/webpack polling over a Windows bind mount is slow — Pitfall 1). For fast inner-loop work, run **infra in Docker** and the **app on the host**, sharing the same `.env`:

```powershell
# 1. Infra only (Postgres + Redis + the demo target) in Docker:
docker compose -f infra/docker-compose.yml --env-file .env up -d postgres redis saucedemo

# 2. API on the host (hot reload), reading the SAME repo-root .env:
cd apps/api
uv run uvicorn app.main:app --reload --port 8001

# 3. Web on the host (Turbopack hot reload):
cd apps/web
npm run dev
```

API URL switch: in Docker mode the web container reaches the api at `http://api:8000` (compose-internal DNS). In hybrid mode the host-run web reaches the host-run api at **`http://localhost:8001`** — this is the configured rewrite fallback (01-04 decision), so no code change is needed when you switch modes. Postgres (5432) and Redis (6379) are published to the host so the host-run api connects to them exactly as the containerized api does.

## 5. Test workflow

Functional tests are D-02 *functional* — they hit the running app over real HTTP with real Postgres (no in-process ASGI shortcut, no DB mocking). e2e tests drive Playwright against the running web app.

```powershell
# One-time: install the Playwright browser used by e2e tests
cd apps/api
uv run playwright install chromium

# Quick loop (functional only, stop on first failure) — needs the stack (or hybrid infra+api) up:
cd apps/api
uv run pytest tests/functional -x -q

# Full suite (functional + e2e) — needs web (3000) + api (8001) + saucedemo (8080) reachable:
docker compose -f infra/docker-compose.yml --env-file .env up -d --wait
cd apps/api
uv run pytest tests -q
```

e2e prerequisites: the full default stack must be up (web on 3000, api on 8001, saucedemo on 8080) and `playwright install chromium` must have run once.

## 6. Demo target & `reset-target`

The self-hosted demo target (SauceDemo / "Swag Labs") serves at http://localhost:8080. Reset it to a known state with the generic reset contract:

```powershell
python infra/scripts/reset_target.py saucedemo
```

It exits `0` on success (service restarted + healthy), `1` on a strategy/health failure, `2` on an unknown target name.

> **Honesty note:** SauceDemo's mutable state lives entirely in the browser's `localStorage`, so a container restart resets nothing the *tests* observe — real per-run isolation comes from Playwright's fresh browser contexts. `reset-target` ships now as the generic seam that Phase 4 (a stateful target via a future `db-snapshot` strategy) and Phase 7 (reproducibility checks) plug into without changing the CLI or its callers (D-10).

## 7. Verify the stack (`verify_stack.py`) — INFRA-01 evidence

With the stack up, prove it is correctly stood up:

```powershell
python infra/scripts/verify_stack.py
```

It asserts, and prints a PASS/FAIL line for each: (1) the default services are exactly `{postgres, redis, api, web, saucedemo}` and all healthy; (2) the dormant services `{neo4j, rabbitmq, elasticsearch}` are absent; (3) every running container has a non-zero memory limit; (4) api `/health` returns 200 with `postgres`+`redis` true, the web root answers (200 or a 3xx redirect to `/login`), and saucedemo answers 200. It exits `0` only if every check passes — stop any service and it exits non-zero naming it. Stdlib only; runs with the host's plain Python.

## Quick start (TL;DR)

1. `.wslconfig` installed and `memory=` tuned to your host (§1), `wsl --shutdown`, restart Docker Desktop.
2. `.env` populated from `.env.example` (§2).
3. `docker compose -f infra/docker-compose.yml --env-file .env up -d --build --wait`
4. Open http://localhost:3000 → log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`.
5. `python infra/scripts/verify_stack.py` → exit 0.
