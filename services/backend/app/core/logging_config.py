"""Logging configuration for Noesis backend.

NOTE: ``setup_logging()`` currently has zero call sites in this repository --
the "structured JSON logging" the project believes it has does not actually
run. Wiring it into the app entrypoints is a separate change; this module only
makes the formatter correct so that it is safe to wire.

The production formatter used to be a hand-rolled ``%``-format template that
pasted ``%(message)s`` straight between two quote characters. Any message
containing a double quote, a newline, or a backslash produced output that was
not valid JSON -- exactly the messages you most want to read (exception text,
LLM output, file paths). The record is now assembled as a dict and serialized
with ``json.dumps``, so escaping is correct by construction.
"""
import json
import logging
import sys
import os


class JsonFormatter(logging.Formatter):
    """Emit each record as a single valid JSON object.

    Field names and ordering match the previous ``%``-format template exactly
    (``time``, ``level``, ``module``, ``function``, ``line``, ``message``) so
    downstream log parsing is unaffected -- only the escaping changes.
    """

    default_time_format = "%Y-%m-%d %H:%M:%S"

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "time": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "module": record.name,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def setup_logging():
    """Configure application logging based on environment."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    environment = os.getenv("ENVIRONMENT", "development")

    handler = logging.StreamHandler(sys.stdout)

    if environment == "production":
        # Structured logging for production
        handler.setFormatter(JsonFormatter(datefmt='%Y-%m-%d %H:%M:%S'))
    else:
        # Human-readable for development
        handler.setFormatter(logging.Formatter(
            '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
        ))

    logging.basicConfig(
        level=getattr(logging, log_level),
        handlers=[handler],
    )

    # Set third-party loggers to WARNING to reduce noise
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for the specified module."""
    return logging.getLogger(name)
