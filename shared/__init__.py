"""Cross-service shared contracts (queue message schemas, etc.).

The repo-root `shared/` package is mounted into the api container at /app/shared
(see infra/docker-compose.yml) and added to the host test path via pyproject's
pythonpath, so `import shared.events` resolves identically in both contexts.
"""
