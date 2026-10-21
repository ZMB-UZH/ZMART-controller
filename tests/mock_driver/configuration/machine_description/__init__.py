"""Machine description: the fixed facts about this instrument, such as its
serial number, so a configuration is never used on the wrong microscope.

``default.json`` beside this file is what the driver ships; ``check``
refuses a malformed value, saying which file and what is wrong.
"""

from __future__ import annotations

from typing import Any

from ..checks import _fail, _keys


def check(value: Any, where: str) -> None:
    """Refuse a malformed the machine description, naming the file (``where``) and what is wrong."""
    _keys(value, {"serial", "software", "tested_versions"}, where)
    if not isinstance(value["serial"], str) or not value["serial"]:
        _fail(where, "serial must be the instrument's serial number")
    if not isinstance(value["tested_versions"], list) or not value["tested_versions"]:
        _fail(where, "tested_versions must list at least one software version")
