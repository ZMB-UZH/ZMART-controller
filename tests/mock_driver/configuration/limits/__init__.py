"""Limits: how far the stage may travel, and the allowed range of each setting.

``default.json`` beside this file is what the driver ships; ``check``
refuses a malformed value, saying which file and what is wrong.
"""

from __future__ import annotations

from typing import Any

from ..checks import AXES, SETTING_NAMES, _fail, _keys, _span


def check(value: Any, where: str) -> None:
    """Refuse a malformed the limits, naming the file (``where``) and what is wrong."""
    _keys(value, {"stage_um", "settings", "objectives", "acquisition"}, where)
    _keys(value["stage_um"], set(AXES), f"{where} (stage_um)")
    for axis in AXES:
        _span(value["stage_um"][axis], where, f"stage_um.{axis}")
    _keys(value["settings"], set(SETTING_NAMES), f"{where} (settings)")
    for name in SETTING_NAMES:
        _span(value["settings"][name], where, f"settings.{name}")
    objectives = value["objectives"]
    if not isinstance(objectives, list) or not all(
        isinstance(slot, int) and not isinstance(slot, bool) for slot in objectives
    ):
        _fail(where, "objectives must list the allowed slot numbers, e.g. [1, 2, 3]")
    _keys(value["acquisition"], {"max_z_planes"}, f"{where} (acquisition)")
    planes = value["acquisition"]["max_z_planes"]
    if isinstance(planes, bool) or not isinstance(planes, int) or planes < 1:
        _fail(where, "acquisition.max_z_planes must be a whole number of at least 1")
