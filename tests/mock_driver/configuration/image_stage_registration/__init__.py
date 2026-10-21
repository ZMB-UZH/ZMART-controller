"""Image stage registration: which way the camera sits on the stage, and the
size of a pixel for each objective.

``default.json`` beside this file is what the driver ships; ``check``
refuses a malformed value, saying which file and what is wrong.
"""

from __future__ import annotations

from typing import Any

from ..checks import _fail, _keys, _number, _slots


def check(value: Any, where: str) -> None:
    """Refuse a malformed the registration, naming the file (``where``) and what is wrong."""
    _keys(value, {"orientation", "pixel_size_um"}, where)
    orientation = value["orientation"]
    try:
        (a, b), (c, d) = orientation
    except (TypeError, ValueError):
        _fail(where, "orientation must be [[a, b], [c, d]]")
    entries = (a, b, c, d)
    if any(isinstance(e, bool) or e not in (-1, 0, 1) for e in entries) or abs(a * d - b * c) != 1:
        _fail(where, "orientation must be a 90° turn or a mirror, using only -1, 0 and 1")
    if (a != 0 and b != 0) or (c != 0 and d != 0):
        _fail(where, "orientation must line the camera up with the stage axes")
    _slots(value["pixel_size_um"], where, "pixel_size_um")
    for slot, size in value["pixel_size_um"].items():
        if _number(size, where, f"pixel_size_um[{slot}]") <= 0:
            _fail(where, f"pixel_size_um[{slot}] must be above 0")
