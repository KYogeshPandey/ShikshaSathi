"""Structured logging setup.

Replaces every ``print()`` call in the legacy backend (docs/AUDIT.md
§2.7) with leveled, structured, machine-parseable log events. Production
(or any run where ``DEBUG`` is false) emits single-line JSON suitable for
log aggregation; development emits a readable, colored console format.

Hard rule enforced by convention across this codebase (see
app/core/config.py, app/db/session.py, app/api/routes/health.py): no log
call anywhere ever receives a whole ``Settings`` object, a database URL,
a password, a JWT/secret value, a cookie or Authorization header, or a
full request body. Only specific, safe, individually-chosen fields are
ever passed to a logger call.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure structlog + stdlib logging exactly once, at startup."""
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=settings.LOG_LEVEL,
        # Without force=True, basicConfig silently does nothing if the
        # root logger already has a handler attached (e.g. depending on
        # import order relative to uvicorn's own logging setup) — that
        # would silently defeat the structured formatting configured
        # below with no error or warning.
        force=True,
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: structlog.types.Processor
    if settings.DEBUG:
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    root_logger = logging.getLogger()
    for handler in root_logger.handlers:
        handler.setFormatter(formatter)
