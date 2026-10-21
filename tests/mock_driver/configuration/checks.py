"""What the checks of every configuration item share.

A configuration file decides where the stage may go, so a mistake in it must
be caught when the driver connects, not halfway through an experiment. Each
check raises ``ValueError`` with the file name and a plain description of the
problem.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import math
from typing import Any

AXES = ("x", "y", "z")
SETTING_NAMES = ("laser_power", "gain", "exposure_ms")


def _fail(where: str, problem: str) -> None:
    raise ValueError(f"{where}: {problem}")


def _keys(value: Any, expected: set[str], where: str) -> None:
    if not isinstance(value, dict):
        _fail(where, "must be a JSON object")
    missing = expected - set(value)
    extra = set(value) - expected
    if missing:
        _fail(where, f"is missing {sorted(missing)}")
    if extra:
        _fail(where, f"has unknown entries {sorted(extra)}")


def _number(value: Any, where: str, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(where, f"{name} must be a number")
    return float(value)


def _span(value: Any, where: str, name: str) -> None:
    if not isinstance(value, list) or len(value) != 2:
        _fail(where, f"{name} must be [lowest, highest]")
    low = _number(value[0], where, name)
    high = _number(value[1], where, name)
    if not low < high:
        _fail(where, f"{name}: the lowest value must be below the highest")


def _slots(value: Any, where: str, name: str) -> None:
    if not isinstance(value, dict) or not value:
        _fail(where, f"{name} must list at least one objective slot")
    for slot in value:
        if not str(slot).isdigit():
            _fail(where, f"{name}: {slot!r} is not an objective slot number")
