"""
Minimal logger utility for consistent, prefixed console output.

Usage:
    from utils.logger import logger
    logger.info("message")
    logger.warn("message")
    logger.error("message")
    logger.debug("message")
"""

from datetime import datetime
import os


class _Logger:
    LEVELS = {"DEBUG": 10, "INFO": 20, "WARN": 30, "ERROR": 40}

    def __init__(self):
        level = os.environ.get("APP_LOG_LEVEL", "INFO").upper()
        self.level = self.LEVELS.get(level, 20)

    def set_level(self, level: str):
        self.level = self.LEVELS.get(level.upper(), self.level)

    def _ts(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _emit(self, lvl_name: str, msg: str):
        print(f"[{self._ts()}] {lvl_name}: {msg}")

    def debug(self, msg: str):
        if self.level <= self.LEVELS["DEBUG"]:
            self._emit("DEBUG", msg)

    def info(self, msg: str):
        if self.level <= self.LEVELS["INFO"]:
            self._emit("INFO", msg)

    def warn(self, msg: str):
        if self.level <= self.LEVELS["WARN"]:
            self._emit("WARN", msg)

    # Backwards compatibility alias
    def warning(self, msg: str):
        self.warn(msg)

    def error(self, msg: str):
        if self.level <= self.LEVELS["ERROR"]:
            self._emit("ERROR", msg)


logger = _Logger()

