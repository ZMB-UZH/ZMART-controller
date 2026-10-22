from __future__ import annotations

from typing import Any

from ..checks import _fail, _keys


def check(value: Any, where: str) -> None:
    _keys(value, {"serial", "software", "tested_versions"}, where)
    if not isinstance(value["serial"], str) or not value["serial"]:
        _fail(where, "serial must be the instrument's serial number")
    if not isinstance(value["tested_versions"], list) or not value["tested_versions"]:
        _fail(where, "tested_versions must list at least one software version")
