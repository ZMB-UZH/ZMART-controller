from __future__ import annotations

from typing import Any

from ..configuration import user_from_raw
from ..configuration.checks import SETTING_NAMES
from .dispatch import Reading

VENDOR_NAMES: dict[str, str] = {
    "laser_power": "laser_power_percent",
    "gain": "detector_gain",
    "exposure_ms": "exposure_ms",
}

ACTUATORS: dict[str, list[str]] = {"x": ["motoric"], "y": ["motoric"], "z": ["motoric", "piezo"]}


def version(ctx) -> Reading:
    return ctx.get.read("software version", ctx.vendor.version)


def hardware(ctx) -> Reading:
    return ctx.get.read("hardware description", ctx.vendor.hardware)


def stage(ctx) -> Reading:
    return ctx.get.read("stage position", ctx.vendor.stage_position)


def focus(ctx) -> Reading:
    return ctx.get.read("focus position", ctx.vendor.focus_position)


def settings(ctx) -> Reading:
    return ctx.get.read("settings", ctx.vendor.settings)


def status(ctx) -> Reading:
    return ctx.get.read("status", ctx.vendor.status)


def _combine(*readings: Reading) -> Reading | None:
    for reading in readings:
        if not reading.known:
            return reading
    return None


def raw_position(ctx) -> Reading:
    xy, z, current = stage(ctx), focus(ctx), settings(ctx)
    unknown = _combine(xy, z, current)
    if unknown is not None:
        return unknown
    value = {
        "x": xy.value["x"],
        "y": xy.value["y"],
        "z": z.value["focus"] + z.value["piezo"],
        "focus": z.value["focus"],
        "piezo": z.value["piezo"],
        "objective": int(current.value["objective_slot"]),
    }
    return Reading(value, max(xy.observed_at, z.observed_at), xy.source)


def user_position(ctx) -> Reading:
    raw = raw_position(ctx)
    if not raw.known:
        return raw
    value = user_from_raw(raw.value, raw.value["objective"], ctx.config)
    return Reading(value, raw.observed_at, raw.source)


def state(ctx) -> Reading:
    current = settings(ctx)
    if not current.known:
        return current
    value: dict[str, Any] = {name: current.value[VENDOR_NAMES[name]] for name in SETTING_NAMES}
    value["objective"] = int(current.value["objective_slot"])
    return Reading(value, current.observed_at, current.source)
