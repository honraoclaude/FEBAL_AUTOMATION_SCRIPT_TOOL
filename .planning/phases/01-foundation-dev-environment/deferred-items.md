# Deferred Items — Phase 01

Out-of-scope discoveries logged during execution (not fixed inline per scope boundary).

| Found During | Item | Suggested Resolution |
|--------------|------|----------------------|
| 01-03 | Pre-existing untracked runtime logs at repo root: `alembic-run.log`, `uvicorn.log`, `verify-t2.log` (from earlier plan-01-02 sessions) | Add `*.log` to `.gitignore` during plan 01-08 (phase-gate cleanup/docs plan) |
| 01-03 | Pre-existing untracked `.claude/` directory at repo root | Decide in 01-08 whether to commit (project settings) or gitignore |
