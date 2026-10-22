from __future__ import annotations

from typing import Any

from ..checks import AXES, _keys, _number


def check(value: Any, where: str) -> None:
    _keys(value, set(AXES), where)
    for axis in AXES:
        _number(value[axis], where, axis)
