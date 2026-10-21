"""Optical calibration: how far each objective's view is shifted from objective 1.

``default.json`` beside this file is what the driver ships; ``check``
refuses a malformed value, saying which file and what is wrong.
"""

from __future__ import annotations

from typing import Any

from ..checks import AXES, _keys, _number, _slots


def check(value: Any, where: str) -> None:
    """Refuse a malformed the calibration, naming the file (``where``) and what is wrong."""
    _keys(value, {"objective_offsets_um"}, where)
    _slots(value["objective_offsets_um"], where, "objective_offsets_um")
    for slot, offset in value["objective_offsets_um"].items():
        _keys(offset, set(AXES), f"{where} (objective {slot})")
        for axis in AXES:
            _number(offset[axis], where, f"objective_offsets_um[{slot}].{axis}")
