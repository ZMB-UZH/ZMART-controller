from __future__ import annotations

import inspect
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zmart_controller.zmart_controller import UNIT

from . import get_actions as get
from . import set_actions as setter
from .configuration import (
    IDENTITY,
    SETTING_NAMES,
    Configuration,
    load_configuration,
    user_range,
)
from .data_handling import FORMATS, CommandLog, save_acquisition
from .data_handling.save import safe_name
from .error_handling import classify
from .get_actions import GetDispatcher
from .procedures import PROCEDURES
from .set_actions import Gate, SetDispatcher
from .vendor_interface import NAME_LIMIT, MockScopeConnection

logger = logging.getLogger("mock_driver")

DEFAULT_OUTPUT_ROOT = Path(tempfile.gettempdir()) / "zmart-mock-output"

STATE_ORDER = ("objective", *SETTING_NAMES)

STACK = ("z_planes", "z_step_um")

TRIGGERS = ("snap", "full")
DEFAULT_TRIGGER = "snap"


@dataclass
class MockHandle:
    vendor: MockScopeConnection
    config: Configuration
    get: GetDispatcher
    set: SetDispatcher
    log: CommandLog
    output_root: Path
    image_format: str
    backlash_correction: bool
    identity: tuple[str, str, str]
    client: Any = None
    closed: bool = False
    software: dict[str, str] = field(default_factory=dict)
    camera: dict[str, int] = field(default_factory=dict)
    stack: dict[str, Any] = field(default_factory=lambda: {"z_planes": 1, "z_step_um": 1.0})

    @property
    def scope(self):
        return self.vendor.scope


def require_open(handle: MockHandle) -> None:
    if handle.closed:
        raise RuntimeError("session is disconnected")


def connect(connection: dict | None = None) -> MockHandle:
    connection = connection or {}
    identity = IDENTITY
    output_root = Path(connection.get("output_root") or DEFAULT_OUTPUT_ROOT)
    output_root.mkdir(parents=True, exist_ok=True)
    timing = connection.get("mock_timing", "realistic")
    if timing not in ("realistic", "instant"):
        raise ValueError(f"mock_timing must be 'realistic' or 'instant', not {timing!r}")
    image_format = connection.get("format", "ome-tiff")
    if image_format not in FORMATS:
        raise ValueError(f"format must be one of {list(FORMATS)}, not {image_format!r}")
    backlash_correction = connection.get("backlash_correction", True)
    if not isinstance(backlash_correction, bool):
        raise ValueError(f"backlash_correction must be True or False, not {backlash_correction!r}")
    vendor = MockScopeConnection.start(
        output_folder=output_root / "_vendor_raw",
        token=connection.get("token", "mock-token"),
        instant=timing == "instant",
    )
    try:
        log = CommandLog()
        config = load_configuration(identity)
        handle = MockHandle(
            vendor=vendor,
            config=config,
            get=GetDispatcher(classify=classify, record=log.record),
            set=SetDispatcher(gate=Gate(config.limits), classify=classify, record=log.record),
            log=log,
            output_root=output_root,
            image_format=image_format,
            backlash_correction=backlash_correction,
            identity=identity,
            client=connection.get("client"),
        )
        handle.software = get.version(handle).value_or_raise("the software version")
        hardware = get.hardware(handle).value_or_raise("the hardware description")
        check_machine(handle, hardware["serial"])
        handle.camera = {
            "width": hardware["camera"]["width"],
            "height": hardware["camera"]["height"],
        }
    except BaseException:
        vendor.close()
        raise
    return handle


def check_machine(handle: MockHandle, serial: str) -> None:
    machine = handle.config.machine_description
    if serial != machine["serial"]:
        raise RuntimeError(
            f"this microscope reports serial {serial}, but the configuration in "
            f"{handle.config.sources['machine_description']} belongs to {machine['serial']}"
        )
    version = handle.software["version"]
    if version not in machine["tested_versions"]:
        message = (
            f"{handle.software['software']} {version} has not been tested with this driver "
            f"(tested: {machine['tested_versions']}); watch the first commands closely"
        )
        logger.warning(message)
        handle.log.record("warning", message)


def disconnect(handle: MockHandle) -> None:
    if handle.closed:
        return
    handle.closed = True
    handle.vendor.close()


DESCRIPTION = """A pretend widefield fluorescence microscope that runs entirely in software (MockScope Control), for trying workflows without hardware. It images a sample of scattered fluorescent spots on a slide that is slightly tilted, so the height at which the spots are sharp changes a little from place to place.

Stage: x and y move the slide, z moves the focus, all in micrometres from the origin. z has two motors: "motoric", the default, for long moves and "piezo" for fine, fast steps around the current height.

Objectives, by slot: 1 is 10x/0.30 Air (1.0 µm per pixel), 2 is 20x/0.75 Air (0.5 µm per pixel), 3 is 40x/0.95 Air (0.25 µm per pixel). Every image is 64 x 64 pixels, so the field of view shrinks as the magnification grows. Changing objective shifts the view slightly; the driver corrects for it.

Settings (the changeable part of the state): objective is the slot number above; laser_power is the excitation in percent, {laser_power}; gain is the detector gain, {gain}; exposure_ms is the exposure time in milliseconds, {exposure_ms}. The image gets brighter with more laser power, gain or exposure; very bright settings saturate it. z_planes and z_step_um are the stored stack, the number of planes and the step between them in micrometres, upwards from the current height.

Triggers: snap takes one plane here with the settings as they are; full takes the stored stack. Each image is saved in the output folder acquire is given, or else under the connection's output_root, in a file whose name is the acquisition type, then the position label."""


def described(limits: dict) -> str:
    bounds = {name: f"{low:g} to {high:g}" for name, (low, high) in limits["settings"].items()}
    return DESCRIPTION.format(**bounds)


FORMAT_NAMES = {"ome-tiff": "OME-TIFF", "ome-zarr": "OME-Zarr"}

DEFAULT_ACTUATORS = {"x": "motoric", "y": "motoric", "z": "motoric"}


def get_info(handle: MockHandle) -> dict:
    require_open(handle)
    saving = (
        f"{FORMAT_NAMES[handle.image_format]} files in the output_folder acquire is given, "
        f"or else under {handle.output_root}, as the connection's output_root and format say"
    )
    return {
        "description": described(handle.config.limits),
        "client": handle.client,
        "serial": handle.config.machine_description["serial"],
        "software": dict(handle.software),
        "configuration": dict(handle.config.sources),
        "setup": {"saving": {"done": True, "says": saving}},
        "chooses_its_own_folder": False,
        "connection_status": {
            "software": f"answers, version {handle.software['version']}",
            "stage": "found",
        },
    }


def get_actuators(handle: MockHandle) -> dict:
    require_open(handle)
    return {
        axis: {"options": list(names), "default": DEFAULT_ACTUATORS[axis]}
        for axis, names in get.ACTUATORS.items()
    }


def actuators_to_use(with_actuators: dict | None) -> dict[str, str]:
    chosen = dict(DEFAULT_ACTUATORS)
    for axis, name in (with_actuators or {}).items():
        if axis not in get.ACTUATORS or name not in get.ACTUATORS[axis]:
            raise ValueError(f"unknown actuator {name!r} for axis {axis!r}")
        chosen[axis] = name
    return chosen


def get_xyz(handle: MockHandle, *, with_actuators: dict | None = None) -> dict:
    require_open(handle)
    chosen = actuators_to_use(with_actuators)
    raw = get.raw_position(handle).value_or_raise("the position")
    user = get.user_position(handle).value_or_raise("the position")
    ranges = user_range(handle.config, raw["objective"])
    canvas = canvas_of(handle, ranges)
    readings = {
        "x": {"motoric": raw["x"]},
        "y": {"motoric": raw["y"]},
        "z": {"motoric": raw["focus"], "piezo": raw["piezo"]},
    }
    return {
        axis: {
            "position": user[axis],
            "unit": UNIT,
            "used_actuator": chosen[axis],
            "actuator_readings": readings[axis],
            "canvas": canvas[axis],
        }
        for axis in ("x", "y", "z")
    }


def canvas_of(handle: MockHandle, ranges: dict[str, list[float]]) -> dict[str, list[float]]:
    pixel_sizes = handle.config.image_stage_registration["pixel_size_um"]
    widest_pixel = max(float(pixel_sizes[str(slot)]) for slot in handle.config.limits["objectives"])
    half_field = max(handle.camera["width"], handle.camera["height"]) * widest_pixel / 2
    widen = {"x": half_field, "y": half_field, "z": 0.0}
    return {axis: [low - widen[axis], high + widen[axis]] for axis, (low, high) in ranges.items()}


def set_xyz(
    handle: MockHandle, *, x: float, y: float, z: float, with_actuators: dict | None = None
) -> dict:
    require_open(handle)
    chosen = actuators_to_use(with_actuators)
    outcome, raw = setter.move_to_user(handle, x=x, y=y, z=z, z_actuator=chosen["z"])
    if not outcome.confirmed:
        raise RuntimeError(f"the move to ({x}, {y}, {z}) could not be confirmed: {outcome.reason}")
    return get_xyz(handle, with_actuators=with_actuators)


def get_state(handle: MockHandle) -> dict:
    require_open(handle)
    changeable = {**get.state(handle).value_or_raise("the settings"), **handle.stack}
    slot = str(changeable["objective"])
    hardware = get.hardware(handle).value_or_raise("the hardware description")
    pixel = float(handle.config.image_stage_registration["pixel_size_um"].get(slot, 0.0))
    camera = hardware["camera"]
    return {
        "changeable": changeable,
        "observed": {
            "serial": hardware["serial"],
            "objective": hardware["objectives"][int(slot)]["name"],
            "pixel_size": {"x": pixel, "y": pixel, "unit": "um"},
            "frame_size": {
                "x": camera["width"] * pixel,
                "y": camera["height"] * pixel,
                "unit": "um",
            },
            "software": dict(handle.software),
            "image_size_px": [int(camera["width"]), int(camera["height"])],
            "pixel_size_um": [pixel, pixel],
        },
    }


def set_state(handle: MockHandle, *, changeable: dict) -> dict:
    require_open(handle)
    changeable = dict(changeable)
    known = (*STATE_ORDER, *STACK)
    unknown = sorted(set(changeable) - set(known))
    if unknown:
        raise ValueError(f"unknown settings {unknown}; this microscope has {list(known)}")
    stack = {name: changeable[name] for name in STACK if name in changeable}
    check_stack({**handle.stack, **stack})
    handle.stack.update(stack)
    applied: dict[str, Any] = dict(stack)
    unconfirmed: dict[str, str] = {}
    for name in STATE_ORDER:
        if name not in changeable:
            continue
        value = changeable[name]
        if name == "objective":
            outcome = setter.set_objective(handle, value)
        else:
            outcome = setter.set_setting(handle, name, value)
        if outcome.confirmed:
            applied[name] = value
        else:
            unconfirmed[name] = outcome.reason
    return {"applied": applied, "unconfirmed": unconfirmed}


def acquisition_menu() -> dict:
    return {
        "trigger": {
            "options": list(TRIGGERS),
            "default": DEFAULT_TRIGGER,
            "active": DEFAULT_TRIGGER,
        },
    }


def get_acquisition_settings(handle: MockHandle) -> dict:
    require_open(handle)
    return acquisition_menu()


def settings_with_defaults(settings: dict | None) -> dict:
    menu = acquisition_menu()
    resolved = {name: spec["active"] for name, spec in menu.items()}
    for name, value in (settings or {}).items():
        if name not in menu:
            raise ValueError(f"unknown acquisition setting {name!r}")
        if value not in menu[name]["options"]:
            raise ValueError(f"invalid value {value!r} for acquisition setting {name!r}")
        resolved[name] = value
    return resolved


def check_stack(stack: dict) -> None:
    planes = stack["z_planes"]
    if isinstance(planes, bool) or not isinstance(planes, int) or planes < 1:
        raise ValueError(f"z_planes must be a whole number from 1, not {planes!r}")
    step = stack["z_step_um"]
    if isinstance(step, bool) or not isinstance(step, (int, float)) or not step > 0:
        raise ValueError(f"z_step_um must be a number above 0, not {step!r}")


def acquire(
    handle: MockHandle,
    *,
    position_label: str,
    acquisition_type: str,
    output_folder: str | None,
    acquisition_settings: dict | None,
) -> dict:
    require_open(handle)
    folder = Path(output_folder) if output_folder is not None else Path(handle.output_root)
    settings = settings_with_defaults(acquisition_settings)
    stack = handle.stack if settings["trigger"] == "full" else {"z_planes": 1, "z_step_um": 1.0}
    mark = handle.log.mark()
    if handle.backlash_correction:
        PROCEDURES["backlash_takeup"]["run"](handle)
    position = get.user_position(handle).value_or_raise("the position")
    vendor_name = safe_name(position_label)[:NAME_LIMIT]
    outcome = setter.acquire(
        handle, name=vendor_name, z_planes=stack["z_planes"], z_step_um=stack["z_step_um"]
    )
    taken: dict[str, Any] = {
        "position_label": position_label,
        "acquisition_type": acquisition_type,
        "trigger": settings["trigger"],
        "format": handle.image_format,
        "settle": "backlash-corrected" if handle.backlash_correction else "direct",
        "position": position,
        "confirmed": outcome.confirmed,
    }
    if not outcome.confirmed:
        return {**taken, "files": [], "planes": [], "reason": outcome.reason}
    saved = save_acquisition(
        handle,
        vendor_file=outcome.result,
        position_label=position_label,
        acquisition_type=acquisition_type,
        folder=folder,
        image_format=handle.image_format,
        position_um=position,
        log_mark=mark,
    )
    return {**taken, **saved, "vendor_file": outcome.result}


def get_procedures(handle: MockHandle) -> dict:
    require_open(handle)
    return {name: {"description": spec["description"]} for name, spec in PROCEDURES.items()}


def run_procedure(handle: MockHandle, *, procedure: dict) -> dict:
    require_open(handle)
    entries = dict(procedure)
    name = entries.pop("name", None)
    if name not in PROCEDURES:
        raise ValueError(f"unknown procedure {name!r}")
    run = PROCEDURES[name]["run"]
    try:
        inspect.signature(run).bind(handle, **entries)
    except TypeError as exc:
        raise ValueError(f"procedure {name!r} does not take these entries: {exc}") from None
    return {"ran": name, **run(handle, **entries)}
