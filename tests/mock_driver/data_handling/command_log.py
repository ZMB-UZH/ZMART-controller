from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("mock_driver")

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

MAX_ENTRIES = 10_000


class CommandLog:
    def __init__(self) -> None:
        self._entries: list[dict[str, Any]] = []
        self._dropped = 0

    def record(self, level: str, message: str) -> None:
        self._entries.append({"time": time.time(), "level": level, "message": message})
        logger.log(_LEVELS.get(level, logging.INFO), message)
        if len(self._entries) > MAX_ENTRIES:
            del self._entries[0]
            self._dropped += 1

    def mark(self) -> int:
        return self._dropped + len(self._entries)

    def since(self, mark: int) -> list[dict[str, Any]]:
        start = max(0, mark - self._dropped)
        return [dict(entry) for entry in self._entries[start:]]
