# Development Environment Setup

Windows 11 + Docker Desktop (WSL2 backend). All platform services run locally via Docker Compose; a documented hybrid mode (infra in Docker, API/web on the host) exists for fast iteration.

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Docker Desktop | 4.x (Engine 29.x, Compose v5.x) | WSL2 backend required |
| Node.js | 22 LTS (host: 24 also fine — Next 16 needs >= 20.9) | Frontend + executor tooling |
| Python | 3.13.x | Backend (FastAPI), managed with uv |
| uv | 0.11.x | Python package/env manager (`uv sync`) |

## 1. WSL2 memory cap (`.wslconfig`) — do this first

Without a cap, the WSL2 VM (Vmmem) grabs memory and does not return it, OOM-killing containers (PITFALLS Pitfall 9).

1. Copy the template to your user profile (skip if you already have one):

   ```powershell
   if (-not (Test-Path "$env:USERPROFILE\.wslconfig")) { Copy-Item .wslconfig.example "$env:USERPROFILE\.wslconfig" }
   ```

2. Tune `memory=` to your host — leave at least 8 GB for Windows (the template's `16GB` suits a 24-32 GB machine).
3. Apply it: `wsl --shutdown`, then restart Docker Desktop. (Do this when no containers are mid-work; the phase gate verifies the stack comes up healthy afterwards.)

## 2. Environment file (`.env`)

```powershell
Copy-Item .env.example .env
```

Then replace every `<generate...>` placeholder using the one-liners documented inline in `.env.example`. `.env` is gitignored — never commit it. This one file is the single config source for both Compose (`--env-file .env`) and hybrid host mode.

## 3. Start the core stack

Canonical invocation (from the repo root):

```powershell
docker compose -f infra/docker-compose.yml --env-file .env up -d --wait
```

Phase 1 default profile: Postgres + Redis (API, web, and the SauceDemo demo target are added by later plans). Neo4j / RabbitMQ / Elasticsearch are defined as dormant compose profiles and never start by default.

## Quick start

> Placeholder — completed in plan 01-08 once the full walking skeleton (API + web + demo target) is wired into the compose stack.

1. `.wslconfig` installed (step 1)
2. `.env` populated (step 2)
3. `docker compose -f infra/docker-compose.yml --env-file .env up -d --wait`
4. (coming) open http://localhost:3000, log in with `ADMIN_EMAIL` / `ADMIN_PASSWORD`
