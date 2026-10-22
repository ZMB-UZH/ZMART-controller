from __future__ import annotations

import inspect
import math
from pathlib import Path
from typing import Any

from .zmart_controller import ZmartController

AXES = ("x", "y", "z")


def validate_driver(driver: Any, connection: dict[str, Any] | None = None) -> list[str]:
    from .registry import find_driver, load_driver

    if isinstance(driver, (str, Path)) and Path(driver).exists():
        driver = load_driver(driver)
    elif isinstance(driver, str):
        driver, saved = find_driver(driver)
        connection = saved if connection is None else connection
    problems: list[str] = parameter_problems(driver)
    session = ZmartController(driver, connection)
    try:
        checks = {
            "get_info": _check_info,
            "get_actuators": _check_actuators,
            "get_xyz": _check_xyz,
            "get_state": _check_state,
            "get_acquisition_settings": _check_acquisition_settings,
            "get_procedures": _check_procedures,
        }
        for name, check in checks.items():
            try:
                answer = getattr(session, name)()
            except Exception as exc:
                problems.append(f"{name} raised {type(exc).__name__}: {exc}")
                continue
            output = _envelope(name, answer, problems)
            if output is not None:
                check(output, problems)
    finally:
        session.disconnect()
    return problems


PARAMETERS = {
    "get_xyz": ("with_actuators",),
    "set_xyz": ("x", "y", "z", "with_actuators"),
    "set_state": ("changeable",),
    "acquire": ("position_label", "acquisition_type", "output_folder", "acquisition_settings"),
    "run_procedure": ("procedure",),
}


def parameter_problems(driver: Any) -> list[str]:
    from .registry import plugin_class

    try:
        plugin = plugin_class(driver)
    except ValueError:
        return []
    problems = []
    for command, names in PARAMETERS.items():
        method = getattr(plugin, command, None)
        if not callable(method):
            continue
        parameters = inspect.signature(method).parameters
        if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
            continue
        missing = [name for name in names if name not in parameters]
        if missing:
            problems.append(
                f"{command} must take {', '.join(names)}, by these names; "
                f"it does not take {', '.join(missing)}"
            )
    return problems


def _envelope(name: str, answer: Any, problems: list[str]):
    if not isinstance(answer, dict) or not {"success", "output"} <= set(answer):
        problems.append(
            f'{name} must return {{"success": ..., "output": ...}}, got {type(answer).__name__}'
        )
        return None
    if not isinstance(answer["success"], bool):
        problems.append(f"{name}: success must be True or False")
    return answer["output"]


def _check_info(output, problems):
    description = output.get("description") if isinstance(output, dict) else None
    if not (isinstance(description, str) and description.strip()):
        problems.append(
            "get_info: the output must contain description, text that describes the microscope"
        )
    if not isinstance(output, dict):
        return
    if not isinstance(output.get("chooses_its_own_folder"), bool):
        problems.append(
            "get_info: chooses_its_own_folder must be True or False: whether acquire saves "
            "anywhere but in the output_folder it is given"
        )
    setup = output.get("setup", {})
    if not isinstance(setup, dict):
        problems.append('get_info: setup must map each set-up item to {"done": ..., "says": ...}')
        return
    for item, state in setup.items():
        if not isinstance(state, dict) or not isinstance(state.get("done"), bool):
            problems.append(f'get_info: setup {item!r} must say "done": True or False')
        elif not (isinstance(state.get("says"), str) and state["says"].strip()):
            problems.append(
                f"get_info: setup {item!r} must say in words what it holds or what to do"
            )
    status = output.get("connection_status", {})
    if not isinstance(status, dict):
        problems.append(
            "get_info: connection_status must map each of the connection's checks to its "
            'answer, "pending", or a text that begins with "failed"'
        )
        return
    for check, answer in status.items():
        if not (isinstance(answer, str) and answer.strip()):
            problems.append(
                f"get_info: connection_status {check!r} must say in words how the check went, "
                '"pending" until it has an answer'
            )


def _check_actuators(output, problems):
    if not isinstance(output, dict):
        problems.append("get_actuators: the output must map each axis to its motors and default")
        return
    for axis in AXES:
        motors = output.get(axis)
        if not isinstance(motors, dict) or not isinstance(motors.get("options"), list):
            problems.append(
                f"get_actuators: axis {axis!r} must be "
                '{"options": [motor names], "default": one of them}'
            )
            continue
        if not motors["options"]:
            problems.append(f"get_actuators: axis {axis!r} must list at least one motor")
        elif "default" not in motors:
            problems.append(
                f"get_actuators: axis {axis!r} must name its default, "
                "the motor used when none is chosen"
            )
        elif motors["default"] not in motors["options"]:
            problems.append(
                f"get_actuators: axis {axis!r} has default {motors['default']!r}, "
                f"which is not one of its options {motors['options']!r}"
            )


def _check_xyz(output, problems):
    if not isinstance(output, dict):
        problems.append("get_xyz: the output must map each axis to its reading")
        return
    for axis in AXES:
        reading = output[axis]
        if not _is_number(reading["position"]):
            problems.append(f"get_xyz: axis {axis!r} position must be a number, in micrometres")
        found = len(problems)
        _check_readings(axis, reading["actuator_readings"], problems)
        used = reading["used_actuator"]
        if len(problems) == found and used not in reading["actuator_readings"]:
            problems.append(
                f"get_xyz: axis {axis!r} used_actuator {used!r} must be one of its "
                f"actuator_readings, {list(reading['actuator_readings'])}"
            )
        _check_canvas(axis, reading["canvas"], problems)


def _check_readings(axis, readings, problems):
    if not (
        isinstance(readings, dict)
        and readings
        and all(isinstance(name, str) and name for name in readings)
        and all(_is_number(value) for value in readings.values())
    ):
        problems.append(
            f"get_xyz: axis {axis!r} actuator_readings must name every motor of the axis "
            f"with its reading as a number, in micrometres"
        )


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_canvas(axis, canvas, problems):
    if not (
        isinstance(canvas, (list, tuple))
        and len(canvas) == 2
        and all(_is_number(end) for end in canvas)
        and canvas[0] <= canvas[1]
    ):
        problems.append(
            f"get_xyz: axis {axis!r} canvas must be [min, max] in micrometres, "
            f"with min no larger than max"
        )


def _check_state(output, problems):
    if not isinstance(output, dict) or not isinstance(output.get("changeable"), dict):
        problems.append('get_state: the output must contain "changeable", a dictionary of settings')
    if not isinstance(output, dict) or not isinstance(output.get("observed"), dict):
        problems.append('get_state: the output must contain "observed", a dictionary')
        return
    sizes = output["observed"].get("image_size_px")
    pixels = output["observed"].get("pixel_size_um")
    if not (
        isinstance(sizes, (list, tuple))
        and len(sizes) == 2
        and all(isinstance(n, int) and not isinstance(n, bool) and n > 0 for n in sizes)
        and isinstance(pixels, (list, tuple))
        and len(pixels) == 2
        and all(_is_number(size) and size > 0 for size in pixels)
    ):
        problems.append(
            'get_state: "observed" must contain "image_size_px", [width, height] in whole '
            'pixels, and "pixel_size_um", [x, y] in micrometres above 0: the image size and '
            "pixel size of the current settings"
        )


def _check_acquisition_settings(output, problems):
    if not isinstance(output, dict):
        problems.append("get_acquisition_settings: the output must map each setting to its choices")
        return
    for name, spec in output.items():
        if not isinstance(spec, dict) or not {"options", "default", "active"} <= set(spec):
            problems.append(
                f'get_acquisition_settings: {name!r} must have "options", "default" and "active"'
            )
            continue
        if not isinstance(spec["options"], list):
            continue
        for key in ("default", "active"):
            if spec[key] not in spec["options"]:
                problems.append(
                    f"get_acquisition_settings: {name!r} has {key} {spec[key]!r}, "
                    f"which is not one of its options {spec['options']!r}"
                )


def _check_procedures(output, problems):
    if not isinstance(output, dict):
        problems.append(
            "get_procedures: the output must map each procedure name to its description"
        )
        return
    for name, spec in output.items():
        if not isinstance(spec, dict) or "description" not in spec:
            problems.append(f'get_procedures: {name!r} must have a "description"')


def check_acquire_answer(
    answer: Any,
    output_folder: str | Path | None = None,
    chooses_its_own_folder: bool = False,
) -> list[str]:
    problems: list[str] = []
    output = _envelope("acquire", answer, problems)
    if output is None:
        return problems
    if not isinstance(output, dict):
        return problems + ["acquire: the output must be a dict"]
    if "position_label" not in output:
        problems.append("acquire: the output must contain position_label")
    kind = output.get("acquisition_type")
    if not (isinstance(kind, str) and kind.strip()):
        problems.append(
            "acquire: the output must contain acquisition_type, the kind of acquisition it was"
        )
    if "files" not in output:
        problems.append(
            "acquire: the output must contain files, the list of paths of every file it saved"
        )
        return problems
    files = output["files"]
    if not isinstance(files, list) or not all(isinstance(path, str) for path in files):
        problems.append("acquire: files must be a list of paths, one per saved file")
        return problems
    if answer.get("success") is True and not files:
        problems.append("acquire: a successful acquisition must list at least one file in files")
    for path in files:
        if not Path(path).exists():
            problems.append(f"acquire: files names {path}, which does not exist")
        elif output_folder is not None and not chooses_its_own_folder:
            if not Path(path).resolve().is_relative_to(Path(output_folder).resolve()):
                problems.append(
                    f"acquire: files names {path}, which is not in the output_folder "
                    f"{output_folder} it was given; a driver whose software saves in its own "
                    "place says so in get_info (chooses_its_own_folder)"
                )
    return problems + _plane_problems(answer.get("success") is True, output, files)


_PLANE_COUNTS = ("c", "z", "t")
_PLANE_POSITION_UM = ("x_um", "y_um", "z_um")
_PLANE_KEYS = ("path", *_PLANE_COUNTS, *_PLANE_POSITION_UM)


def _plane_problems(succeeded: bool, output: dict, files: list[str]) -> list[str]:
    if "planes" not in output:
        return [
            "acquire: the output must contain planes, one entry per saved image saying which "
            "file, channel, depth and stage position it is"
        ]
    planes = output["planes"]
    if not isinstance(planes, list) or not all(isinstance(plane, dict) for plane in planes):
        return ["acquire: planes must be a list with one dictionary per saved image plane"]
    problems: list[str] = []
    if succeeded and not planes:
        problems.append(
            "acquire: a successful acquisition must describe at least one image plane in planes"
        )
    listed = {str(Path(path)) for path in files}
    seen: set[tuple[int, int, int]] = set()
    heights: dict[tuple[int, int, int], float] = {}
    for number, plane in enumerate(planes):
        name = f"acquire: planes[{number}]"
        missing = [key for key in _PLANE_KEYS if key not in plane]
        if missing:
            problems.append(f"{name} must contain {', '.join(missing)}")
            continue
        path = plane["path"]
        if not isinstance(path, str) or str(Path(path)) not in listed:
            problems.append(f"{name} names {path}, which is not in files")
        counts_fit = True
        for key in _PLANE_COUNTS:
            value = plane[key]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                problems.append(f"{name} {key} must be a whole number from 0, got {value!r}")
                counts_fit = False
        for key in _PLANE_POSITION_UM:
            if not (_is_number(plane[key]) and math.isfinite(plane[key])):
                problems.append(f"{name} {key} must be a number of micrometres, got {plane[key]!r}")
        if counts_fit:
            slot = (plane["c"], plane["z"], plane["t"])
            if slot in seen:
                problems.append(
                    f"{name} repeats channel {slot[0]}, depth {slot[1]} and time {slot[2]} "
                    "of an earlier plane"
                )
            elif _is_number(plane["z_um"]) and math.isfinite(plane["z_um"]):
                heights[slot] = plane["z_um"]
            seen.add(slot)
    return problems + _stack_problems(heights)


def _stack_problems(heights: dict[tuple[int, int, int], float]) -> list[str]:
    problems = []
    for (c, z, t), height in sorted(heights.items()):
        first = min(one for one in heights if one[1:] == (z, t))
        if heights[first] != height:
            problems.append(
                f"acquire: depth {z} at time {t} is at z_um {heights[first]} in channel "
                f"{first[0]} but {height} in channel {c}; the channels of one slice share its height"
            )
        below = max(
            (one for one in heights if one[0] == c and one[2] == t and one[1] < z), default=None
        )
        if below is not None and height <= heights[below]:
            problems.append(
                f"acquire: channel {c} at time {t}: depth {z} is at z_um {height}, not above "
                f"depth {below[1]} at {heights[below]}; z counts upwards, so the lowest slice "
                "is depth 0"
            )
    return problems
