"""The mock microscope's ZMART controller plugin: the 11 functions.

This is part 8 of the driver anatomy (``docs/driver-anatomy.md`` in ZMART-drivers). It presents the driver to the ZMART
Controller in the shape every microscope shares, and it does nothing else:
no coordinate arithmetic and no safety checks of its own. Those happened
further down. Each function here only maps a controller command onto the
driver's get actions, set actions, procedures and data handling.

The mock is a complete driver, built from the same parts a real one has::

    vendor_interface/   talks to MockScope Control, the pretend vendor software
    error_handling/     sorts every problem into a kind, and says what to do
    get_actions/        asks the microscope things, through the get dispatcher
    set_actions/        changes the microscope, through the set dispatcher
    procedures/         recipes: autofocus, backlash takeup, parking the piezo
    data_handling/      turns the vendor's files into OME-TIFF or OME-Zarr
    configuration/      origin, registration, limits, calibration
    zmart_controller_plugin.py  this file
    testing/            the mock API and everything else for testing

Plug it in like any driver::

    zmart_controller.ZmartController(zmart_controller.mock)

The connection dictionary is optional. It may hold ``output_root`` (where
images are saved), ``format`` (``"ome-tiff"``, the default, or
``"ome-zarr"``), ``backlash_correction`` (``True``, the default, takes up
the stage's slack before each acquisition), ``token`` (the vendor login,
default ``"mock-token"``) and ``mock_timing``: ``"realistic"`` (the
default) lets moves and acquisitions take time, ``"instant"`` makes them
finish at once. How the mock saves and settles is set once here, like a
real microscope's setup, never per acquisition.

Every function except ``connect`` and ``disconnect`` takes the handle first
and returns ``{"success": bool, "content": ...}``.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import inspect
import logging
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zmart_controller.mock import get_actions as get
from zmart_controller.mock import set_actions as setter
from zmart_controller.mock.configuration import (
    IDENTITY,
    SETTING_NAMES,
    Configuration,
    load_configuration,
    user_range,
)
from zmart_controller.mock.data_handling import FORMATS, CommandLog, save_acquisition
from zmart_controller.mock.data_handling.save import safe_name
from zmart_controller.mock.error_handling import classify
from zmart_controller.mock.get_actions import GetDispatcher
from zmart_controller.mock.procedures import PROCEDURES
from zmart_controller.mock.set_actions import Gate, SetDispatcher
from zmart_controller.mock.vendor_interface import NAME_LIMIT, MockScopeConnection
from zmart_controller.zmart_controller import UNIT

logger = logging.getLogger("zmart_controller.mock")

# The driver's name in the controller's list, and its configuration. The
# mock needs none; a real driver would put, for example, where its vendor
# software runs and where images go here.
NAME = "mock"
CONNECTION: dict[str, Any] = {}

# Where images go when the connection does not say: a folder in the
# computer's temporary space, so trying the mock never litters a project.
DEFAULT_OUTPUT_ROOT = Path(tempfile.gettempdir()) / "zmart-mock-output"

# The order in which set_state applies settings: the objective first, since
# changing it can change what the other settings mean.
_STATE_ORDER = ("objective", *SETTING_NAMES)

# The stored stack the ``full`` trigger takes, part of the changeable state.
_STACK = ("z_planes", "z_step_um")

#: The ways an acquisition can be triggered, and the one used when none is chosen.
TRIGGERS = ("snap", "full")
DEFAULT_TRIGGER = "snap"


@dataclass
class MockHandle:
    """Everything a connected mock driver holds.

    ``vendor`` is the connection to MockScope Control (``vendor.scope`` is
    the pretend software itself, for tests). ``get`` and ``set`` are the two
    dispatchers, ``config`` the configuration loaded at connect, ``log`` the
    command log, and ``output_root`` the folder where images are saved, in
    ``image_format``. ``backlash_correction`` says whether the stage's slack
    is taken up before each acquisition. ``camera`` is the camera's frame in
    pixels, read once at connect: it never changes while the software runs.
    ``stack`` is the stack the ``full`` trigger takes, which the vendor
    software would keep as a stored acquisition; it is part of the state.
    """

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
        """The pretend vendor software, for tests that make it misbehave."""
        return self.vendor.scope


def _answer(content: Any, *, success: bool = True) -> dict:
    """Wrap the content in the shape every command returns."""
    return {"success": success, "content": content}


def _require_open(handle: MockHandle) -> None:
    if handle.closed:
        raise RuntimeError("session is disconnected")


# --- connecting ---------------------------------------------------------------


def connect(connection: dict | None = None) -> MockHandle:
    """Start the pretend vendor software, check it, and load this microscope's configuration.

    The steps, in order: start the software and log in; load the
    configuration (machine description, registration and origin, then the
    limits, which switch on the limits gate, then the calibration); check
    the software's version and serial number against the machine
    description. If any step fails, the software is closed again and the
    error is raised.
    """
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
        _check_machine(handle, hardware["serial"])
        handle.camera = {
            "width": hardware["camera"]["width"],
            "height": hardware["camera"]["height"],
        }
    except BaseException:
        vendor.close()
        raise
    return handle


def _check_machine(handle: MockHandle, serial: str) -> None:
    """Refuse a configuration that belongs to another microscope; warn about an untested version."""
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
    """Close the session. Every later call raises; a second disconnect is harmless."""
    if handle.closed:
        return
    handle.closed = True
    handle.vendor.close()


# --- describing the setup -----------------------------------------------------

# The microscope in plain words, for whoever drives it: a person, a notebook, or
# the ZMART AI agent, which builds its picture of the instrument from this. It
# says what the other answers cannot: what each setting means, in which unit and
# within which bounds, and which objective sits in which slot. Travel ranges and
# routines are left to get_xyz and get_procedures, which report them live. The
# bounds of the settings come from this microscope's limits file when get_info
# runs, so the description never promises more than the driver allows.
DESCRIPTION = """A pretend widefield fluorescence microscope that runs entirely in software (MockScope Control), for trying workflows without hardware. It images a sample of scattered fluorescent spots on a slide that is slightly tilted, so the height at which the spots are sharp changes a little from place to place.

Stage: x and y move the slide, z moves the focus, all in micrometres from the origin. z has two motors: "motoric", the default, for long moves and "piezo" for fine, fast steps around the current height.

Objectives, by slot: 1 is 10x/0.30 Air (1.0 µm per pixel), 2 is 20x/0.75 Air (0.5 µm per pixel), 3 is 40x/0.95 Air (0.25 µm per pixel). Every image is 64 x 64 pixels, so the field of view shrinks as the magnification grows. Changing objective shifts the view slightly; the driver corrects for it.

Settings (the changeable part of the state): objective is the slot number above; laser_power is the excitation in percent, {laser_power}; gain is the detector gain, {gain}; exposure_ms is the exposure time in milliseconds, {exposure_ms}. The image gets brighter with more laser power, gain or exposure; very bright settings saturate it. z_planes and z_step_um are the stored stack, the number of planes and the step between them in micrometres, upwards from the current height.

Triggers: snap takes one plane here with the settings as they are; full takes the stored stack. Each image is saved under the output folder, in a file whose name starts with the position label."""


def _described(limits: dict) -> str:
    """The description, with each setting's bounds as this microscope's limits set them."""
    bounds = {name: f"{low:g} to {high:g}" for name, (low, high) in limits["settings"].items()}
    return DESCRIPTION.format(**bounds)


#: The names of the file formats, as a person reads them.
FORMAT_NAMES = {"ome-tiff": "OME-TIFF", "ome-zarr": "OME-Zarr"}

#: The motor used per axis when a command does not choose one. The driver
#: decides it; "motoric" reaches the whole travel, the piezo only a little.
DEFAULT_ACTUATORS = {"x": "motoric", "y": "motoric", "z": "motoric"}


def get_info(handle: MockHandle) -> dict:
    """A description of the microscope, what is set up on it, and the configuration in use.

    The one set-up item is saving: where the images go and in which format,
    as the connection chose them. The workflow decides where its own runs go.
    """
    _require_open(handle)
    saving = (
        f"{FORMAT_NAMES[handle.image_format]} files under {handle.output_root}, "
        "as the connection's output_root and format say"
    )
    return _answer(
        {
            "description": _described(handle.config.limits),
            "client": handle.client,
            "serial": handle.config.machine_description["serial"],
            "software": dict(handle.software),
            "configuration": dict(handle.config.sources),
            "setup": {"saving": {"done": True, "says": saving}},
        }
    )


def get_actuators(handle: MockHandle) -> dict:
    """The motors that can move each axis, and the one used when none is chosen."""
    _require_open(handle)
    return _answer(
        {
            axis: {"options": list(names), "default": DEFAULT_ACTUATORS[axis]}
            for axis, names in get.ACTUATORS.items()
        }
    )


def _actuators(with_actuators: dict | None) -> dict[str, str]:
    """The motor to use per axis: the one named, or else the default.

    A choice made for one call does not carry over to the next call.
    """
    chosen = dict(DEFAULT_ACTUATORS)
    for axis, name in (with_actuators or {}).items():
        if axis not in get.ACTUATORS or name not in get.ACTUATORS[axis]:
            raise ValueError(f"unknown actuator {name!r} for axis {axis!r}")
        chosen[axis] = name
    return chosen


# --- moving -------------------------------------------------------------------


def get_xyz(handle: MockHandle, *, with_actuators: dict | None = None) -> dict:
    """Where the stage is, per axis: ``position``, ``unit``, ``actuator``, ``actuators``, ``canvas``.

    ``position`` is micrometres from the origin. ``actuator`` is the motor
    this call used: the one ``with_actuators`` named, or the default.
    ``actuators`` holds every motor of the axis with its own raw reading, in
    the stage's own coordinates: for z, the coarse drive and the piezo, whose
    sum is the focus height. ``canvas`` is everywhere a picture can show
    along the axis.
    """
    _require_open(handle)
    chosen = _actuators(with_actuators)
    raw = get.raw_position(handle).value_or_raise("the position")
    user = get.user_position(handle).value_or_raise("the position")
    ranges = user_range(handle.config, raw["objective"])
    canvas = _canvas(handle, ranges)
    readings = {
        "x": {"motoric": raw["x"]},
        "y": {"motoric": raw["y"]},
        "z": {"motoric": raw["focus"], "piezo": raw["piezo"]},
    }
    return _answer(
        {
            axis: {
                "position": user[axis],
                "unit": UNIT,
                "actuator": chosen[axis],
                "actuators": readings[axis],
                "canvas": canvas[axis],
            }
            for axis in ("x", "y", "z")
        }
    )


def _canvas(handle: MockHandle, ranges: dict[str, list[float]]) -> dict[str, list[float]]:
    """Everywhere a picture can show, per axis: the travel widened by half the widest field.

    A picture is centred on the stage position, so one taken at the edge of
    travel shows half a field beyond it. The widest field belongs to the
    objective with the largest pixels among those the limits allow; its
    longest side is used for x and y alike, so a turned camera is covered
    too. z is not widened: this microscope's z-stacks go upwards from the
    stage height and the limits keep the whole stack inside the travel, so
    no plane is ever taken outside it.
    """
    pixel_sizes = handle.config.image_stage_registration["pixel_size_um"]
    widest_pixel = max(float(pixel_sizes[str(slot)]) for slot in handle.config.limits["objectives"])
    half_field = max(handle.camera["width"], handle.camera["height"]) * widest_pixel / 2
    widen = {"x": half_field, "y": half_field, "z": 0.0}
    return {axis: [low - widen[axis], high + widen[axis]] for axis, (low, high) in ranges.items()}


def set_xyz(
    handle: MockHandle, x: float, y: float, z: float, *, with_actuators: dict | None = None
) -> dict:
    """Move to a position in micrometres from the origin, then answer like ``get_xyz``.

    Once the stage has arrived, the position is read back from the
    microscope, so the answer shows where the stage really is rather than
    the numbers that were asked for. Raises ``ValueError`` for a position
    outside the limits or an unknown motor, and ``RuntimeError`` when the
    move cannot be confirmed: carrying on at an unknown position is never
    safe.
    """
    _require_open(handle)
    chosen = _actuators(with_actuators)
    outcome, _raw = setter.move_to_user(handle, x=x, y=y, z=z, z_actuator=chosen["z"])
    if not outcome.confirmed:
        raise RuntimeError(f"the move to ({x}, {y}, {z}) could not be confirmed: {outcome.reason}")
    return get_xyz(handle, with_actuators=with_actuators)


# --- state --------------------------------------------------------------------


def get_state(handle: MockHandle) -> dict:
    """The settings that can be changed, and a read-only description of the instrument."""
    _require_open(handle)
    changeable = {**get.state(handle).value_or_raise("the settings"), **handle.stack}
    slot = str(changeable["objective"])
    hardware = get.hardware(handle).value_or_raise("the hardware description")
    pixel = float(handle.config.image_stage_registration["pixel_size_um"].get(slot, 0.0))
    camera = hardware["camera"]
    return _answer(
        {
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
            },
        }
    )


def set_state(handle: MockHandle, state: dict) -> dict:
    """Apply the ``changeable`` settings, confirm each one, and report what happened.

    ``observed`` is never read. A setting name this microscope does not know,
    or a stack that is not one, is refused with ``ValueError`` before
    anything is applied, so a typo never passes silently. The stack
    (``z_planes``, ``z_step_um``) is kept by the driver, as the vendor
    software keeps a stored acquisition, so it takes at once. ``success`` is
    False when nothing was applied, or when a setting was sent but could not
    be confirmed; both are safe to carry on from, so they are reported, not
    raised.
    """
    _require_open(handle)
    changeable = dict(state.get("changeable", {}))
    known = (*_STATE_ORDER, *_STACK)
    unknown = sorted(set(changeable) - set(known))
    if unknown:
        raise ValueError(f"unknown settings {unknown}; this microscope has {list(known)}")
    stack = {name: changeable[name] for name in _STACK if name in changeable}
    _check_stack({**handle.stack, **stack})
    handle.stack.update(stack)
    applied: dict[str, Any] = dict(stack)
    unconfirmed: dict[str, str] = {}
    for name in _STATE_ORDER:
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
    success = bool(applied) and not unconfirmed
    content = {"applied": applied, "unconfirmed": unconfirmed}
    return _answer(content, success=success)


# --- acquiring ----------------------------------------------------------------


def _menu() -> dict:
    """The acquisition settings: only how to trigger, with the driver's default."""
    return {
        "trigger": {
            "options": list(TRIGGERS),
            "default": DEFAULT_TRIGGER,
            "active": DEFAULT_TRIGGER,
        },
    }


def get_acquisition_settings(handle: MockHandle) -> dict:
    """How an acquisition can be triggered: one plane as set now, or the stored stack."""
    _require_open(handle)
    return _answer(_menu())


def _with_defaults(settings: dict | None) -> dict:
    """Check the settings against the menu and fill in the ones left out."""
    menu = _menu()
    resolved = {name: spec["active"] for name, spec in menu.items()}
    for name, value in (settings or {}).items():
        if name not in menu:
            raise ValueError(f"unknown acquisition setting {name!r}")
        if value not in menu[name]["options"]:
            raise ValueError(f"invalid value {value!r} for acquisition setting {name!r}")
        resolved[name] = value
    return resolved


def _check_stack(stack: dict) -> None:
    """Refuse a stored stack that is not one: whole planes from 1, a step above 0."""
    planes = stack["z_planes"]
    if isinstance(planes, bool) or not isinstance(planes, int) or planes < 1:
        raise ValueError(f"z_planes must be a whole number from 1, not {planes!r}")
    step = stack["z_step_um"]
    if isinstance(step, bool) or not isinstance(step, (int, float)) or not step > 0:
        raise ValueError(f"z_step_um must be a number above 0, not {step!r}")


def acquire(
    handle: MockHandle, *, position_label: str, acquisition_settings: dict | None = None
) -> dict:
    """Capture an image (or the stored stack) here and save it, in one step.

    Every file name starts with ``position_label``. The ``trigger`` decides
    what is taken: ``snap``, one plane with the settings as they are, or
    ``full``, the whole stack stored in the state. How the files are saved and
    whether the stage settles first were set at connect. The content lists
    every saved file under ``files`` (the images, then the ``command_log``
    that records how they were made, which is also named on its own), and
    under ``planes`` which file, channel and depth each image plane is and
    the stage position it was taken at. When the acquisition cannot be
    confirmed, ``success`` is False and no files or planes are listed.
    """
    _require_open(handle)
    settings = _with_defaults(acquisition_settings)
    stack = handle.stack if settings["trigger"] == "full" else {"z_planes": 1, "z_step_um": 1.0}
    mark = handle.log.mark()
    if handle.backlash_correction:
        PROCEDURES["backlash_takeup"]["run"](handle)
    position = get.user_position(handle).value_or_raise("the position")
    # The vendor software takes short names only; the saved files keep the full label.
    vendor_name = safe_name(position_label)[:NAME_LIMIT]
    outcome = setter.acquire(
        handle, name=vendor_name, z_planes=stack["z_planes"], z_step_um=stack["z_step_um"]
    )
    content: dict[str, Any] = {
        "position_label": position_label,
        "trigger": settings["trigger"],
        "format": handle.image_format,
        "settle": "backlash-corrected" if handle.backlash_correction else "direct",
        "position": position,
        "confirmed": outcome.confirmed,
    }
    if not outcome.confirmed:
        return _answer(
            {**content, "files": [], "planes": [], "reason": outcome.reason}, success=False
        )
    saved = save_acquisition(
        handle,
        vendor_file=outcome.result,
        position_label=position_label,
        image_format=handle.image_format,
        position_um=position,
        log_mark=mark,
    )
    return _answer({**content, **saved, "vendor_file": outcome.result})


# --- procedures ---------------------------------------------------------------


def get_procedures(handle: MockHandle) -> dict:
    """The routines this microscope offers, each with a plain description."""
    _require_open(handle)
    return _answer(
        {name: {"description": spec["description"]} for name, spec in PROCEDURES.items()}
    )


def run_procedure(handle: MockHandle, procedure: dict) -> dict:
    """Run one routine by name; any other entries are passed to it. An unknown name is refused."""
    _require_open(handle)
    entries = dict(procedure)
    name = entries.pop("name", None)
    if name not in PROCEDURES:
        raise ValueError(f"unknown procedure {name!r}")
    run = PROCEDURES[name]["run"]
    try:
        inspect.signature(run).bind(handle, **entries)
    except TypeError as exc:
        raise ValueError(f"procedure {name!r} does not take these entries: {exc}") from None
    return _answer({"ran": name, **run(handle, **entries)})
