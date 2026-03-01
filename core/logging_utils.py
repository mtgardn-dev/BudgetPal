from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QObject, Signal

from core.path_registry import BudgetPalPathRegistry


class QtLogEmitter(QObject):
    message = Signal(str)


class QtLogHandler(logging.Handler):
    def __init__(self, emitter: QtLogEmitter) -> None:
        super().__init__()
        self.emitter = emitter

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.emitter.message.emit(msg)
        except Exception:
            self.handleError(record)


def configure_logging(settings: dict) -> tuple[logging.Logger, QtLogEmitter]:
    logger = logging.getLogger("budgetpal")
    logger.setLevel(getattr(logging, settings["logging"]["level"].upper(), logging.INFO))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        BudgetPalPathRegistry.log_file(),
        maxBytes=int(settings["logging"].get("max_bytes", 1_000_000)),
        backupCount=int(settings["logging"].get("backup_count", 5)),
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    emitter = QtLogEmitter()
    qt_handler = QtLogHandler(emitter)
    qt_handler.setFormatter(formatter)
    logger.addHandler(qt_handler)

    return logger, emitter
