"""Execution worker plane (EXEC-03) — stateless RabbitMQ consumer + per-flow job runner.

SC3 invariant: NOTHING in this package may import the LLM gateway / LangChain / LangGraph /
the explorer agent. The worker only consumes a job and runs `uv run pytest <spec>` in an
isolated subprocess. Enforced by tests/unit/test_no_llm_in_worker.py.
"""
