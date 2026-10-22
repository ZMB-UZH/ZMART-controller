from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..error_handling import RULES, Action, Kind
from .gate import Gate
from .tuning import DEFAULT_SET_TUNING, SetTuning

REPLY_LOST = object()


class NeverConfirmed(Exception): ...


@dataclass
class SetCommand:
    name: str
    send: Callable[[], Any]
    confirm: Callable[[Any], bool]
    limits: tuple[str, dict[str, Any]] | None
    ready: Callable[[], bool] | None = None
    tuning: SetTuning = DEFAULT_SET_TUNING


@dataclass
class Outcome:
    confirmed: bool
    result: Any
    sends: int
    confirm_windows: int
    reason: str | None = None


class SetDispatcher:
    def __init__(
        self,
        *,
        gate: Gate,
        classify: Callable[[BaseException], Kind],
        record: Callable[[str, str], None],
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._gate = gate
        self._classify = classify
        self._record = record
        self._clock = clock
        self._sleep = sleep

    def run(self, command: SetCommand) -> Outcome:
        if command.limits is not None:
            refusal = self._gate.check(*command.limits)
            if refusal is not None:
                self._record("warning", f"{command.name} refused by the limits: {refusal}")
                raise ValueError(f"{command.name} refused: {refusal}")
        if command.ready is not None:
            self._wait_until_ready(command)
        tuning = command.tuning
        sends = 0
        result: Any = None
        reason = "the microscope accepted the command, but the readback never showed the target"
        for window in range(1, tuning.max_confirm_attempts + 1):
            if window == 1 or tuning.send_again_if_unconfirmed:
                result = self._send(command)
                sends += 1
            confirm_with = None if result is REPLY_LOST else result
            try:
                confirmed = self._confirm(command, confirm_with)
            except NeverConfirmed as never:
                self._record("warning", f"{command.name} will not be confirmed: {never}")
                reason = str(never)
                if tuning.send_again_if_unconfirmed:
                    continue
                return Outcome(False, confirm_with, sends, window, str(never))
            if confirmed:
                self._record("info", f"{command.name} confirmed")
                return Outcome(True, confirm_with, sends, window)
            self._record(
                "warning",
                f"{command.name} not confirmed within {tuning.confirm_window_s} s "
                f"(window {window} of {tuning.max_confirm_attempts})",
            )
        return Outcome(
            False,
            None if result is REPLY_LOST else result,
            sends,
            tuning.max_confirm_attempts,
            reason,
        )

    def _wait_until_ready(self, command: SetCommand) -> None:
        deadline = self._clock() + command.tuning.ready_timeout_s
        while not command.ready():
            if self._clock() >= deadline:
                raise RuntimeError(
                    f"{command.name}: the microscope stayed busy for "
                    f"{command.tuning.ready_timeout_s} s, so the command was not sent"
                )
            self._sleep(command.tuning.poll_interval_s)

    def _send(self, command: SetCommand) -> Any:
        tuning = command.tuning
        tries = 0
        while True:
            try:
                return command.send()
            except Exception as error:
                kind = self._classify(error)
                rule = RULES[kind]
                if isinstance(error, TimeoutError) and kind is Kind.TEMPORARY:
                    self._record("warning", f"{command.name}: reply lost; reading back to find out")
                    return REPLY_LOST
                if rule.set is Action.RETRY and tries < tuning.max_retries:
                    pause = tuning.retry_pause_s * 2**tries
                    tries += 1
                    self._record("info", f"{command.name}: {error}; sending again in {pause} s")
                    self._sleep(pause)
                    continue
                if rule.set is Action.RETRY:
                    raise RuntimeError(
                        f"{command.name} failed {tries + 1} times; last answer: {error}"
                    ) from error
                self._record("error", f"{command.name}: {kind.value}: {error}")
                raise rule.error(f"{command.name}: {error}") from error

    def _confirm(self, command: SetCommand, result: Any) -> bool:
        tuning = command.tuning
        deadline = self._clock() + tuning.confirm_window_s
        while True:
            if command.confirm(result):
                return True
            if self._clock() >= deadline:
                return False
            self._sleep(tuning.poll_interval_s)
