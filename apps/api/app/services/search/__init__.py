"""Elasticsearch-backed full-text search (DASH-06).

Two seams:
  - indexer.py — the on-write dual-index hooks (swallow-and-log so an ES outage never breaks the
    Postgres write), the idempotent ensure-mappings, and the backfill/reindex command.
  - query.py — search() with a parameterized multi_match + highlight, graceful-degrading to an
    honest 503 (via the main.py ESConnectionError handler) when ES is down.
"""
