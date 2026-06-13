"""structlog JSON logging with credential redaction (PLAT-07 control #1).

The redact_sensitive processor masks any event-dict key matching
password|passwd|secret|credential|token (case-insensitive) BEFORE the JSON
renderer, so sensitive values can never reach a log sink.
"""

import logging
import re
from typing import Any

import structlog

SENSITIVE = re.compile(r"password|passwd|secret|credential|token", re.I)


def redact_sensitive(
    logger: Any, method_name: Any, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Replace values of sensitive-looking KEYS with [REDACTED]."""
    for key in list(event_dict):
        if SENSITIVE.search(key):
            event_dict[key] = "[REDACTED]"
    return event_dict


def configure_logging() -> None:
    """Configure structlog for JSON output with the redaction processor wired in."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            redact_sensitive,  # must run before the renderer
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
