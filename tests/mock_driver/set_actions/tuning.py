from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class SetTuning:
    max_retries: int = 2
    retry_pause_s: float = 0.05
    max_confirm_attempts: int = 3
    confirm_window_s: float = 1.0
    poll_interval_s: float = 0.01
    send_again_if_unconfirmed: bool = True
    ready_timeout_s: float = 10.0


DEFAULT_SET_TUNING = SetTuning()

OBJECTIVE_TUNING = replace(DEFAULT_SET_TUNING, confirm_window_s=3.0)

ACQUIRE_TUNING = replace(
    DEFAULT_SET_TUNING,
    confirm_window_s=60.0,
    max_confirm_attempts=1,
    send_again_if_unconfirmed=False,
)
