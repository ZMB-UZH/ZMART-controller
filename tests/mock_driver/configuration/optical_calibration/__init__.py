from __future__ import annotations

from typing import Any

from ..checks import AXES, _keys, _number, _slots


def check(value: Any, where: str) -> None:
    _keys(value, {"objective_offsets_um"}, where)
    _slots(value["objective_offsets_um"], where, "objective_offsets_um")
    for slot, offset in value["objective_offsets_um"].items():
        _keys(offset, set(AXES), f"{where} (objective {slot})")
        for axis in AXES:
            _number(offset[axis], where, f"objective_offsets_um[{slot}].{axis}")
