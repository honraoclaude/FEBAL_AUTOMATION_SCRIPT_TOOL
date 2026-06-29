"""Typed application settings — single config class for compose and hybrid modes (D-09).

Env vars injected by compose take precedence over the repo-root .env file
(pydantic-settings default source ordering: init kwargs > env vars > env_file).
"""

from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env",  # repo-root .env when run from apps/api (hybrid host mode)
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str  # env DATABASE_URL
    redis_url: str  # env REDIS_URL
    jwt_secret: str  # env JWT_SECRET
    # env TARGET_CREDENTIAL_KEY, comma-separated (MultiFernet rotation: first key
    # encrypts, all keys decrypt). NoDecode disables JSON parsing so the
    # before-validator below owns the comma-split.
    credential_keys: Annotated[list[str], NoDecode] = Field(
        validation_alias="TARGET_CREDENTIAL_KEY"
    )
    admin_email: str  # env ADMIN_EMAIL
    admin_password: str  # env ADMIN_PASSWORD
    cookie_secure: bool = False  # env COOKIE_SECURE

    # --- LLM gateway (Phase 2, plan 02-01) ---
    # Provider-prefixed default model passed straight to init_chat_model
    # (e.g. "anthropic:claude-..." / "openai:gpt-..."), D-13.
    llm_default_model: str  # env LLM_DEFAULT_MODEL
    # Provider keys default None so the app boots without them; live tests skip
    # when absent (RESEARCH Pitfall 6). Never logged, never stored in the ledger.
    anthropic_api_key: str | None = None  # env ANTHROPIC_API_KEY
    openai_api_key: str | None = None  # env OPENAI_API_KEY
    # Optional LangSmith tracing — env-gated, OFF by default (RESEARCH Q3).
    langsmith_tracing: bool = False  # env LANGSMITH_TRACING
    langsmith_api_key: str | None = None  # env LANGSMITH_API_KEY

    # --- LLM budget caps (Phase 2, plan 02-02; PLAT-06, D-03/D-04) ---
    # Global env defaults for all three scopes (per-call / per-run / per-day), on
    # BOTH the USD and token axes (D-03). A breach on EITHER axis in ANY scope
    # raises BudgetExceeded before spend (D-01/D-02).
    #
    # PER-RUN OVERRIDE CONTRACT (D-04, RESEARCH Q4): a caller's per-run override may
    # only TIGHTEN — the gateway clamps it to min(override, global cap) and NEVER
    # loosens past these global ceilings. Phase 4 feeds Target.budget_overrides in
    # as the per-run override; this clamp is the hard ceiling it cannot exceed.
    llm_per_call_usd_cap: float = 1.0  # env LLM_PER_CALL_USD_CAP — max USD for one call
    llm_run_usd_cap: float = 25.0  # env LLM_RUN_USD_CAP — max USD across one run_id
    llm_daily_usd_cap: float = 100.0  # env LLM_DAILY_USD_CAP — max USD per UTC day (auto-trips kill-switch)
    llm_per_call_token_cap: int = 200_000  # env LLM_PER_CALL_TOKEN_CAP — max (in+out) tokens for one call
    llm_run_token_cap: int = 5_000_000  # env LLM_RUN_TOKEN_CAP — max tokens across one run_id
    llm_daily_token_cap: int = 20_000_000  # env LLM_DAILY_TOKEN_CAP — max tokens per UTC day
    llm_run_ttl_s: int = 86400  # env LLM_RUN_TTL_S — TTL on per-run Redis budget counters

    # --- LLM response cache (Phase 2, plan 02-03; PLAT-06, D-11/D-12) ---
    # TTL (seconds) on a cached deterministic (temperature==0) response. Only
    # temperature==0 calls without no_cache are cached; a hit costs $0 and writes a
    # cache_hit=true ledger row. Default ~24h, env-configurable.
    llm_cache_ttl_s: int = 86400  # env LLM_CACHE_TTL_S

    # --- Neo4j knowledge graph (Phase 3, plan 03-01; PLAT-02) ---
    # Bolt URI + auth for the lifespan-managed AsyncGraphDatabase driver. Required
    # so Settings() fails loudly if compose/.env omit them (compose enumerates env
    # explicitly; 02-01 deviation #2). The driver opens lazily, so the api still
    # boots when neo4j is down (graph profile inactive) — only a graph query errors.
    neo4j_uri: str  # env NEO4J_URI (bolt://neo4j:7687 in-cluster, bolt://localhost:7687 host)
    neo4j_user: str  # env NEO4J_USER
    neo4j_password: str  # env NEO4J_PASSWORD

    # --- Elasticsearch full-text search (Phase 10, plan 10-04; DASH-06) ---
    # The HTTP URL for the lifespan-managed AsyncElasticsearch client. Default points at the
    # in-cluster `elasticsearch` host so the api boots without it set; the search profile is OFF
    # by default and the client opens LAZILY (mirroring the neo4j driver), so the api still boots
    # when ES is down — only a search query / on-write index then errors (graceful-degraded). Plain
    # http:// (the compose ES block disables xpack security — 10-04 Pitfall 1). Compose enumerates
    # env explicitly (the NEO4J_URI precedent — "compose does NOT pass the whole .env").
    elasticsearch_url: str = "http://elasticsearch:9200"  # env ELASTICSEARCH_URL

    # --- Artifact workspaces + execution runner (Phase 3, plan 03-04; PLAT-02) ---
    # WORKSPACES_DIR: where generate-scripts writes (and /execute discovers) the run's
    #   spec at <WORKSPACES_DIR>/<run_id>/test_login.py. Default None => resolve the
    #   gitignored repo-root workspaces/ relative to this file (host/hybrid layout). In
    #   the container the path differs (WORKDIR /app), so compose sets WORKSPACES_DIR
    #   explicitly to /app/workspaces (a bind mount of the host repo-root workspaces/).
    # EXECUTION_CWD: the cwd for the `uv run pytest` subprocess — the dir holding the uv
    #   project (pyproject.toml). Default None => apps/api relative to this file (host);
    #   compose sets it to /app (the container WORKDIR / project root).
    workspaces_dir: str | None = None  # env WORKSPACES_DIR
    execution_cwd: str | None = None  # env EXECUTION_CWD

    # --- Stability + seeded-bug acceptance harness (Phase 6, plan 06-04; GEN-05 / D-07/D-08) ---
    # STABILITY_RUNS: a generated spec is ACCEPTED only if it passes N consecutive subprocess
    #   runs (any flaky/non-green run rejects it). Env-configurable, default 3.
    # SEEDED_BUG_BASE_URL: the in-cluster URL of the profile-gated saucedemo-bug build. The
    #   harness re-runs the SAME accepted spec against it (via the TARGET_BASE_URL override the
    #   generated conftest reads) and the run MUST FAIL — proving real-breakage detection.
    #   Optional so the api boots without it (the planted-spec proof passes it explicitly).
    stability_runs: int = 3  # env STABILITY_RUNS
    seeded_bug_base_url: str | None = None  # env SEEDED_BUG_BASE_URL

    # --- Explorer budget caps (Phase 4, plan 04-01; EXPL-05, D-05/D-06) ---
    # Code-enforced EXPLORATION caps (NOT token/USD — the Phase-2 gateway owns spend,
    # D-06). Per-run overrides come from Target.budget_overrides, clamped TIGHTEN-ONLY
    # (min(override, global)) by explorer.budget.build_budget — mirroring the LLM-cap
    # clamp at llm_gateway._effective_caps. These globals are the hard ceiling a target
    # override can never loosen past.
    explore_max_steps: int = 60  # env EXPLORE_MAX_STEPS — max loop iterations per run
    explore_max_depth: int = 6  # env EXPLORE_MAX_DEPTH — max navigation depth per run
    explore_max_revisits_per_fingerprint: int = 2  # env EXPLORE_MAX_REVISITS_PER_FINGERPRINT
    explore_wall_clock_seconds: int = 600  # env EXPLORE_WALL_CLOCK_SECONDS — hard time cap
    explore_saturation_window: int = 8  # env EXPLORE_SATURATION_WINDOW — steps w/o new fp -> stop

    # --- Execution engine + RabbitMQ workers (Phase 7, plan 07-01; EXEC-03) ---
    # AMQP_URL: the RabbitMQ broker the producer (api) publishes execution jobs to and the
    #   worker container consumes from (in-cluster amqp://guest:guest@rabbitmq:5672/; host
    #   tests reach the queue-profile broker at amqp://guest:guest@localhost:5672/). Optional
    #   so the api boots without the queue profile up (only an enqueue would then error).
    # EXEC_PREFETCH_COUNT: the worker's QoS prefetch — the HARD bound on concurrent in-flight
    #   jobs = parallel Chromium contexts under the 3GB WSL cap. Default 2 (safe; 3 ceiling).
    amqp_url: str | None = None  # env AMQP_URL
    exec_prefetch_count: int = 2  # env EXEC_PREFETCH_COUNT

    # --- CI trigger scoped credential (Phase 7, plan 07-05; EXEC-02 / D-08) ---
    # CI_TOKEN: the SCOPED start+poll credential the GitHub Actions workflow
    #   (.github/workflows/run-suite.yml) presents as a Bearer to start a tier run and
    #   poll its status — the SAME engine code path as local/Docker (D-08), never a
    #   separate pytest path in CI. It is scoped to start-run + read-status ONLY (Pitfall
    #   7 / T-07-08); the route-level bearer enforcement on the executions start/poll
    #   routes lives in plan 07-03 (routers/executions.py, I1). Default None so the api
    #   boots without it (mirrors the optional anthropic_api_key / amqp_url contract), and
    #   it is NEVER echoed/logged (T-07-07).
    ci_token: str | None = None  # env CI_TOKEN

    # --- Self-healing engine thresholds (Phase 8, plan 08-01; HEAL-02 / D-04) ---
    # CONFIG-tunable confidence bands for the deterministic heal resolver (mirror stability_runs).
    # Auto-heal requires conf >= heal_high_threshold AND a UNIQUE live match (the hard uniqueness
    # gate in healing/confidence.heal_outcome is applied FIRST, independent of these bands); a
    # conf in [med, high) -> quarantine; below med -> fail-as-defect. Starting points (RESEARCH
    # A2) tuned by the mutation harness (QUAL-02). heal_enabled is the kill-switch for the inline
    # heal hook. Compose does NOT pass the whole .env — add each to the compose env explicitly.
    heal_enabled: bool = True  # env HEAL_ENABLED
    # Tuned by the QUAL-02 mutation harness (08-04): the geometry/DOM-only confidence blend is
    # compressed — realistic benign drift (even a data-testid rename, the canonical heal case) tops
    # out ~0.21–0.41, a removed element's best leftover candidate scores ~0.06, a duplicated element
    # is held by the uniqueness gate. Empirical separation window 0.06 < high <= 0.21; 0.15/0.10 sits
    # in it (every benign clears high; BREAK_REMOVE@0.06 < med stays fail_as_defect). The earlier
    # 0.85/0.60 starting points were UNREACHABLE for real drift → benign would fail-as-defect in
    # production (SC4 miss). med MUST be <= high for the quarantine band to be non-empty.
    heal_high_threshold: float = 0.15  # env HEAL_HIGH_THRESHOLD — auto-heal band floor
    heal_med_threshold: float = 0.10  # env HEAL_MED_THRESHOLD — quarantine band floor

    # --- Defect intelligence + Jira agent (Phase 9, plan 09-01; DEF/JIRA, D-03/D-04/D-05) ---
    # Jira Cloud connection. ALL default None so the api boots without a Jira instance (none in
    # dev) — the deterministic classifier + the keyless harness + the draft queue work without it;
    # only LIVE filing/dedup needs these (Manual-Only). jira_api_token is a SECRET: optional-default
    # + NEVER logged (the anthropic_api_key / ci_token precedent — the SENSITIVE regex matches
    # "token"; the gateway/client structlog events must omit it entirely). Compose does NOT pass the
    # whole .env — add each to the compose env explicitly (the heal_high_threshold note).
    jira_url: str | None = None  # env JIRA_URL (the Jira Cloud base URL)
    jira_email: str | None = None  # env JIRA_EMAIL (the Jira Cloud account email)
    jira_api_token: str | None = None  # env JIRA_API_TOKEN — SECRET, NEVER echoed/logged
    jira_project_key: str | None = None  # env JIRA_PROJECT_KEY (the target project, e.g. "QA")
    # AUTONOMOUS FILING OFF BY DEFAULT (D-04): until a human reviews QUAL-03 accuracy (>=85%) +
    # draft precision (>=90%) and EXPLICITLY flips this on, every classification stays a draft for
    # human apply/reject. Even flag-on additionally requires confidence >= the calibrated threshold.
    jira_autonomous_enabled: bool = False  # env JIRA_AUTONOMOUS_ENABLED
    # The autonomous-filing eligibility floor — a STARTING POINT (RESEARCH A1) the QUAL-03 harness
    # CALIBRATES from the measured per-class confidence distribution, exactly as the QUAL-02
    # mutation harness tuned heal_high_threshold (0.85 -> 0.15) into its empirical separation
    # window. The harness asserts against THIS shipped default (never a test-local literal) so the
    # config can never silently drift from the proof. Read at the autonomy gate, never hardcoded.
    jira_confidence_threshold: int = 70  # env JIRA_CONFIDENCE_THRESHOLD — calibrated by QUAL-03
    # The per-run CREATE cap (D-05 / Pitfall 5): throttles new-issue filing to prevent ticket
    # storms. Updates to existing fp-<hash> issues are free; the local Defect row persists
    # regardless of the cap (a capped defect is still in the review queue, just not auto-filed).
    jira_max_tickets_per_run: int = 25  # env JIRA_MAX_TICKETS_PER_RUN

    @property
    def checkpoint_dsn(self) -> str:
        """Plain psycopg3 conninfo for AsyncPostgresSaver (Pitfall 1: NOT the SQLAlchemy DSN).

        langgraph-checkpoint-postgres uses psycopg3, which rejects the SQLAlchemy
        `postgresql+asyncpg://` dialect prefix. Strip the `+asyncpg` so the SAME database
        is reached over a plain `postgresql://` conninfo. Two drivers, one Postgres.
        """
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")

    @field_validator("credential_keys", mode="before")
    @classmethod
    def _split_credential_keys(cls, value: object) -> object:
        if isinstance(value, str):
            return [key.strip() for key in value.split(",") if key.strip()]
        return value


settings = Settings()  # module-level singleton: `from app.core.config import settings`
