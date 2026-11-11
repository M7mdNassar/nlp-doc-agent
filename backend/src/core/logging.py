import logging
import sys

import structlog

from src.core.config import settings


class PollingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        return not (
            isinstance(args, tuple)
            and len(args) == 5
            and args[1] == "GET"
            and str(args[2]).split("?")[0] in {"/health", "/documents"}
            and str(args[4]) == "200"
        )


def setup_logging() -> None:
    """Configures structlog for JSON output in production and pretty output in dev."""

    # Set standard library logging level
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    # Keep meaningful application diagnostics visible instead of drowning them in polling.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(
            logging.DEBUG if log_level == logging.DEBUG else logging.WARNING
        )
    access = logging.getLogger("uvicorn.access")
    for existing in list(access.filters):
        if isinstance(existing, PollingFilter):
            access.removeFilter(existing)
    if log_level != logging.DEBUG:
        access.addFilter(PollingFilter())

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            # If dev, use ConsoleRenderer, else JSONRenderer
            structlog.dev.ConsoleRenderer()
            if settings.LOG_LEVEL == "debug"
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
