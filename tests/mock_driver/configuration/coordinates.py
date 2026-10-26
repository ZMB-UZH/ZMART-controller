from __future__ import annotations

from .checks import AXES
from .store import Configuration


def _offset(config: Configuration, slot: int) -> dict[str, float]:
    offsets = config.optical_calibration["objective_offsets_um"]
    try:
        return offsets[str(slot)]
    except KeyError:
        raise RuntimeError(
            f"the optical calibration has no entry for objective {slot}; "
            f"calibrate it before using this objective"
        ) from None


def sample_point(raw: dict[str, float], slot: int, config: Configuration) -> dict[str, float]:
    offset = _offset(config, slot)
    return {axis: raw[axis] + offset[axis] for axis in AXES}


def user_from_raw(raw: dict[str, float], slot: int, config: Configuration) -> dict[str, float]:
    point = sample_point(raw, slot, config)
    return {axis: point[axis] - config.origin[axis] for axis in AXES}


def raw_from_user(user: dict[str, float], slot: int, config: Configuration) -> dict[str, float]:
    offset = _offset(config, slot)
    return {axis: user[axis] + config.origin[axis] - offset[axis] for axis in AXES}


def user_range(config: Configuration, slot: int) -> dict[str, list[float]]:
    stage = config.limits["stage_um"]
    low = user_from_raw({axis: stage[axis][0] for axis in AXES}, slot, config)
    high = user_from_raw({axis: stage[axis][1] for axis in AXES}, slot, config)
    return {axis: [low[axis], high[axis]] for axis in AXES}
