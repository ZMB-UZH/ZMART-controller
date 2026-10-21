"""Origin: the point that reads as (0, 0, 0) in user coordinates.

``default.json`` beside this file is what the driver ships; ``check``
refuses a malformed value, saying which file and what is wrong.
"""

from __future__ import annotations

from typing import Any

from ..checks import AXES, _keys, _number


def check(value: Any, where: str) -> None:
    """Refuse a malformed the origin, naming the file (``where``) and what is wrong."""
    _keys(value, set(AXES), where)
    for axis in AXES:
        _number(value[axis], where, axis)
