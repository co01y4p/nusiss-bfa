import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

# Identifier of the HTTP request being handled, set by RequestIdMiddleware. Every log line
# written while handling the request (including the uvicorn access line) carries it.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


class RequestIdFilter(logging.Filter):
    """Adds the current request id to log records so one request can be followed end to end."""

    def filter(self, record: logging.LogRecord) -> bool:
        request_id = request_id_var.get()
        if request_id is not None:
            record.request_id = request_id
        return True


# Redaction patterns for secrets
BEARER_PATTERN = re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE)
API_KEY_PATTERN = re.compile(
    r"(?:api[_-]?key|secret|password|authorization)\s*[:=]\s*['\"]?([^'\"\s]+)",
    re.IGNORECASE,
)

# Field names that must be suppressed to comply with M4/M6 security rules
FORBIDDEN_FIELDS = {
    "chain_of_thought",
    "thought",
    "internal_reasoning",
    "reasoning_content",
    "jwt_secret",
    "api_key",
    "password",
    "authorization",
    "token",
}


def sanitize_log_message(msg: str) -> str:
    """Strip tokens, secrets, and auth headers from message strings."""
    if not isinstance(msg, str):
        return str(msg)
    sanitized = BEARER_PATTERN.sub("Bearer [REDACTED]", msg)
    sanitized = API_KEY_PATTERN.sub(r"secret=[REDACTED]", sanitized)
    return sanitized


def sanitize_extra_data(extra: dict[str, Any]) -> dict[str, Any]:
    """Filter out chain-of-thought and secrets from structured extra attributes."""
    cleaned: dict[str, Any] = {}
    for key, value in extra.items():
        if key.lower() in FORBIDDEN_FIELDS:
            continue
        if isinstance(value, str):
            cleaned[key] = sanitize_log_message(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            cleaned[key] = value
        elif isinstance(value, (list, tuple)):
            if key == "reason_codes":
                cleaned[key] = [str(item) for item in value]
            else:
                cleaned[key] = [
                    sanitize_log_message(str(item)) if isinstance(item, str) else item
                    for item in value
                ]
        elif isinstance(value, dict):
            cleaned[key] = sanitize_extra_data(value)
        else:
            cleaned[key] = sanitize_log_message(str(value))
    return cleaned


class StructuredJsonFormatter(logging.Formatter):
    """Outputs log records formatted as compact, sanitized JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": sanitize_log_message(record.getMessage()),
            "module": record.module,
            "line": record.lineno,
        }

        # Include traceback details safely if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        # Include custom domain attributes if passed via extra={}
        standard_attrs = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "taskName",
        }

        extra_fields = {
            k: v
            for k, v in record.__dict__.items()
            if k not in standard_attrs and not k.startswith("_")
        }
        if extra_fields:
            log_payload.update(sanitize_extra_data(extra_fields))

        return json.dumps(log_payload, default=str)


def setup_logging(*, level: str = "INFO", json_format: bool = True) -> None:
    """Configures structured logging across root and key third-party loggers."""
    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())

    # Remove existing handlers to avoid duplicates
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stream_handler = logging.StreamHandler()
    stream_handler.addFilter(RequestIdFilter())
    if json_format:
        stream_handler.setFormatter(StructuredJsonFormatter())
    else:
        stream_handler.setFormatter(
            logging.Formatter("[%(asctime)s] %(levelname)s in %(name)s: %(message)s")
        )

    root_logger.addHandler(stream_handler)

    # Align uvicorn loggers with the same formatter
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        u_logger = logging.getLogger(uvicorn_logger_name)
        u_logger.handlers = [stream_handler]
        u_logger.propagate = False
