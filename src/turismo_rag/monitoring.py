"""Registro de la aplicación en JSON por línea: stdout (Render) y data/logs/app.log."""

from datetime import datetime, timezone
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

from .config import Settings

# Raíz de los loggers del proyecto: api, metrics y evaluation heredan sus handlers.
logger = logging.getLogger("turismo_rag")
metrics = logging.getLogger("turismo_rag.metrics")
_file_handler: RotatingFileHandler | None = None


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
                "level": record.levelname, "logger": record.name}
        fields = getattr(record, "fields", None)
        data |= fields if fields else {"message": record.getMessage()}
        if record.exc_info:
            data["exception"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup_logging(settings: Settings) -> None:
    """Idempotente; vuelve a abrir el archivo solo si cambia LOG_FILE."""
    global _file_handler
    if not logger.handlers:
        # Handler propio: uvicorn no configura los loggers de la aplicación.
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(JsonFormatter())
        logger.addHandler(stream)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    path = Path(settings.log_file) if settings.log_file else None
    current = Path(_file_handler.baseFilename) if _file_handler else None
    if path and current == path.resolve():
        return
    if _file_handler:
        logger.removeHandler(_file_handler)
        _file_handler.close()
        _file_handler = None
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        _file_handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3,
                                            encoding="utf-8")
        _file_handler.setFormatter(JsonFormatter())
        logger.addHandler(_file_handler)


def log_event(settings: Settings, event: str, **fields) -> dict:
    setup_logging(settings)
    record = {"event": event, **fields}
    metrics.info(event, extra={"fields": record})
    return record
