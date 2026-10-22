from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from zmart_controller.registry import config_root

from . import (
    image_stage_registration,
    limits,
    machine_description,
    optical_calibration,
    origin,
)

ITEMS: tuple[str, ...] = (
    "machine_description",
    "image_stage_registration",
    "origin",
    "limits",
    "optical_calibration",
)

HERE = Path(__file__).resolve().parent
CHECKS = {
    "machine_description": machine_description.check,
    "image_stage_registration": image_stage_registration.check,
    "origin": origin.check,
    "limits": limits.check,
    "optical_calibration": optical_calibration.check,
}

IDENTITY = ("mock", "mock-scope", "mock-api")


@dataclass(frozen=True)
class Configuration:
    machine_description: dict[str, Any]
    image_stage_registration: dict[str, Any]
    origin: dict[str, float]
    limits: dict[str, Any]
    optical_calibration: dict[str, Any]
    sources: dict[str, str]


def saved_path(item: str, identity: tuple[str, str, str] = IDENTITY) -> Path:
    _known(item)
    return config_root().joinpath(*identity, item, f"{item}.json")


def _known(item: str) -> None:
    if item not in ITEMS:
        raise ValueError(f"unknown configuration item {item!r}; known: {list(ITEMS)}")


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from None


def load(item: str, identity: tuple[str, str, str] = IDENTITY) -> tuple[Any, str]:
    path = saved_path(item, identity)
    if not path.is_file():
        path = HERE / item / "default.json"
    value = _read(path)
    CHECKS[item](value, str(path))
    return value, str(path)


def load_configuration(identity: tuple[str, str, str] = IDENTITY) -> Configuration:
    values = {}
    sources = {}
    for item in ITEMS:
        values[item], sources[item] = load(item, identity)
    return Configuration(**values, sources=sources)


def save(item: str, value: Any, identity: tuple[str, str, str] = IDENTITY) -> Path:
    CHECKS[item](value, f"the new {item}")
    path = saved_path(item, identity)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    except PermissionError:
        raise PermissionError(
            f"cannot write {path}. Run this with the rights to write there, "
            f"or point ZMART_MICROSCOPY_ROOT at a folder you can write."
        ) from None
    return path
