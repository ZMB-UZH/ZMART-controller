from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..error_handling import RULES, Action, Kind


@dataclass(frozen=True)
class GetTuning:
    max_retries: int = 2
    retry_pause_s: float = 0.02
    time_limit_s: float = 0.5
    wait_for_turn_s: float = 2.0


DEFAULT_GET_TUNING = GetTuning()


@dataclass(frozen=True)
class Reading:
    value: Any
    observed_at: float | None
    source: str
    reason: str | None = None

    @property
    def known(self) -> bool:
        return self.reason is None

    def value_or_raise(self, what: str) -> Any:
        if not self.known:
            raise RuntimeError(f"could not read {what}: {self.reason}")
        return self.value


class GetDispatcher:
    def __init__(
        self,
        *,
        classify: Callable[[BaseException], Kind],
        record: Callable[[str, str], None],
        tuning: GetTuning = DEFAULT_GET_TUNING,
        source: str = "api",
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._classify = classify
        self._record = record
        self._tuning = tuning
        self._source = source
        self._clock = clock
        self._sleep = sleep
        self._turn = threading.RLock()

    def read(self, label: str, primitive: Callable[[], Any]) -> Reading:
        tuning = self._tuning
        if not self._turn.acquire(timeout=tuning.wait_for_turn_s):
            return self._unknown(label, "another read kept the microscope busy for too long")
        try:
            deadline = self._clock() + tuning.time_limit_s
            tries = 0
            while True:
                try:
                    value = primitive()
                    return Reading(value, self._clock(), self._source)
                except Exception as error:
                    kind = self._classify(error)
                    rule = RULES[kind]
                    if rule.get is not Action.RETRY:
                        raise rule.error(f"reading {label} failed: {error}") from error
                    tries += 1
                    pause = tuning.retry_pause_s
                    if tries > tuning.max_retries or self._clock() + pause > deadline:
                        return self._unknown(label, f"{kind.value} problem: {error}")
                    self._record("debug", f"reading {label}: {error}; trying again")
                    self._sleep(pause)
        finally:
            self._turn.release()

    def _unknown(self, label: str, reason: str) -> Reading:
        self._record("warning", f"reading {label} is unknown: {reason}")
        return Reading(None, None, self._source, reason)
