# Autonomous QA Engineer Platform

## What This Is

An AI-driven autonomous testing platform that explores any web application without manually written scripts, learns its screens and business workflows into a living knowledge graph, and from that automatically generates BDD Gherkin scenarios and Playwright automation. It executes regression suites, self-heals automation when the UI changes, classifies failures intelligently, files Jira defects automatically, and surfaces everything through role-based dashboards. Built as a generic platform (works against any target web app), developed and operated initially by a single user.

## Core Value

**Autonomous discovery**: point the platform at a URL with credentials and it maps the application, learns its workflows, and builds the knowledge graph by itself — no manually written test scripts.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Explorer Agent: launches a browser, discovers pages/forms/menus/buttons/links/tables, detects workflows and validations, captures screenshots, builds a navigation graph
- [ ] Knowledge Graph Engine (Neo4j): stores pages, forms, workflows, buttons, business entities with navigates-to/submits/creates/updates/deletes edges
- [ ] Flow Learning Engine: discovers user journeys, categorizes business workflows, assigns risk scores, maintains an application digital twin
- [ ] BDD Generation Engine: generates Features, Scenarios, Scenario Outlines with data-driven examples from discovered flows
- [ ] Playwright Generation Engine: generates page objects, test specs, fixtures, utilities, and test data models in a standard folder structure
- [ ] Self-Healing Engine: detects broken locators via DOM/visual/accessibility similarity and historical mapping; heals using priority order (data-testid → aria-label → role → text → xpath) and updates the repository
- [ ] Execution Engine: smoke/sanity/regression/full/risk-based suites; local, Docker, and CI/CD modes; browser- and flow-level parallelism
- [ ] Defect Detection Engine: classifies failures (infrastructure / automation / product defect) with 0–100 confidence scoring and a Jira-creation threshold
- [ ] Jira Agent: auto-creates defects in Jira Cloud with summary, steps, expected/actual, severity, priority, screenshots, video, logs; links tests and updates dashboards
- [ ] Dashboard Engine: executive (coverage, pass rate, defects, trends), QA (execution history, failures, screenshots, videos), and developer (root cause, error trends, module failures) dashboards
- [ ] Platform RBAC: roles (Admin / QA Lead / QA Engineer / Developer) with per-dashboard permissions
- [ ] Traceability + Coverage engines: requirements/flows ↔ scenarios ↔ scripts ↔ executions ↔ defects
- [ ] REST API per spec: /explore, /generate-bdd, /generate-scripts, /execute, /heal, /create-defect, /flows, /coverage, /executions, /dashboard
- [ ] Historical execution results persisted (PostgreSQL) with analytics
- [ ] Provider-agnostic LLM layer (works with Anthropic or OpenAI behind one abstraction)
- [ ] Infrastructure: Docker Compose for local dev; Kubernetes manifests (validated on Docker Desktop K8s/kind); GitHub Actions CI/CD; Grafana + Prometheus monitoring; Elasticsearch search; RabbitMQ queue; Redis cache

### Out of Scope

- Multi-tenancy / customer billing — single-user deployment for now; RBAC exists but no tenant isolation
- Mobile app testing (native iOS/Android) — platform targets web applications only
- Cloud K8s cluster provisioning (EKS/GKE/AKS) — development targets Docker Desktop locally; manifests are cloud-ready but cluster ops are deferred
- Manual test case management (TestRail-style authoring) — the point is autonomous generation, not manual authoring
- Testing the FEBAL application specifically — platform is generic; validation uses public demo apps and self-hosted sample apps

## Context

- Greenfield project in an empty directory on Windows 11; development runs locally with Docker Desktop.
- Solo developer/operator ("just me for now"), but the platform ships with full RBAC by deliberate choice.
- Validation targets during development: public demo apps (OrangeHRM, SauceDemo, OpenCart demo) plus open-source apps self-hosted in Docker.
- A real Jira Cloud instance is available with API-token access for the Jira Agent.
- Full product specification was provided up front (architecture, modules, DB schema, API design, agent architecture, AI prompts, tech stack, project structure, roadmap, success metrics) and is the source of truth for scope.
- Spec success metrics: coverage > 80%, self-healing success > 90%, defect classification accuracy > 85%, BDD generation accuracy > 90%, automation generation accuracy > 90%, manual-effort reduction > 70%.

## Constraints

- **Tech stack**: Next.js/React/TypeScript frontend; FastAPI/Python backend; LangGraph agent orchestration; Playwright automation; PostgreSQL; Neo4j knowledge graph; Elasticsearch; RabbitMQ; Redis; Docker/Kubernetes; GitHub Actions; Grafana + Prometheus — adopted as specified, full stack from the start.
- **AI provider**: provider-agnostic LLM abstraction — must run on Anthropic or OpenAI without code changes outside the adapter.
- **Dev environment**: Windows 11 + Docker Desktop — all services must run locally via Docker Compose; K8s validated via Docker Desktop K8s or kind.
- **Integrations**: Jira Cloud via REST API token.
- **Scope**: full platform in v1 (all spec phases 1–4), not an incremental MVP — user explicitly chose full scope.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Generic platform, not FEBAL-specific | User wants a product that tests any web app | — Pending |
| Full platform scope for v1 | User explicitly chose full spec over phased MVP | — Pending |
| Full spec stack from day one (Neo4j, ES, RabbitMQ, K8s) | User chose spec stack as written over simplification | — Pending |
| Provider-agnostic LLM layer | Avoid lock-in; spec said OpenAI, user works in Anthropic ecosystem | — Pending |
| Docker Desktop as dev/K8s target | Solo dev on Windows; no cloud cluster needed yet | — Pending |
| Full RBAC despite solo user | User wants roles built in from the start | — Pending |
| Validate against public demo apps + self-hosted samples | Stable, free, well-known workflows for measuring discovery accuracy | — Pending |
| Real Jira Cloud integration (no mock) | User has an instance with API token access | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-06-11 after initialization*
