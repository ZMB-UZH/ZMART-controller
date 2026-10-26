from __future__ import annotations

from .. import get_actions as get
from ..configuration import raw_from_user
from .dispatch import NeverConfirmed, Outcome, SetCommand
from .tuning import ACQUIRE_TUNING, OBJECTIVE_TUNING

POSITION_TOLERANCE_UM = 0.05

PIEZO_TRAVEL_UM = (-100.0, 100.0)


def _idle(ctx) -> bool:
    reading = get.status(ctx)
    return reading.known and reading.value["state"] == "idle"


def _not_acquiring(ctx) -> bool:
    reading = get.status(ctx)
    return reading.known and reading.value["state"] not in ("acquiring", "changing_objective")


def move(ctx, *, x: float, y: float, focus: float, piezo: float) -> Outcome:
    def send():
        lost = None
        try:
            ctx.vendor.move_stage(x=x, y=y)
        except TimeoutError as error:
            lost = error
        ctx.vendor.move_focus(focus=focus, piezo=piezo)
        if lost is not None:
            raise lost

    def confirm(_result) -> bool:
        xy, z = get.stage(ctx), get.focus(ctx)
        if not (xy.known and z.known):
            return False
        reached = {**xy.value, **z.value}
        target = {"x": x, "y": y, "focus": focus, "piezo": piezo}
        return all(abs(reached[axis] - target[axis]) <= POSITION_TOLERANCE_UM for axis in target)

    return ctx.set.run(
        SetCommand(
            name="move",
            send=send,
            confirm=confirm,
            limits=("stage", {"x": x, "y": y, "z": focus + piezo}),
            ready=lambda: _not_acquiring(ctx),
        )
    )


def move_to_user(
    ctx, *, x: float, y: float, z: float, z_actuator: str = "motoric"
) -> tuple[Outcome, dict[str, float]]:
    if z_actuator not in get.ACTUATORS["z"]:
        raise ValueError(f"unknown actuator {z_actuator!r} for axis 'z'")
    here = get.raw_position(ctx).value_or_raise("the current position")
    target = raw_from_user({"x": x, "y": y, "z": z}, here["objective"], ctx.config)
    focus, piezo = here["focus"], here["piezo"]
    if z_actuator == "piezo":
        piezo = target["z"] - focus
        low, high = PIEZO_TRAVEL_UM
        if not low <= piezo <= high:
            raise ValueError(
                f"z = {z} needs the piezo at {piezo:.2f} µm, beyond its reach of "
                f"[{low}, {high}]; use the motoric drive for larger steps"
            )
    else:
        focus = target["z"] - piezo
    outcome = move(ctx, x=target["x"], y=target["y"], focus=focus, piezo=piezo)
    return outcome, target


def set_setting(ctx, name: str, value: float) -> Outcome:
    if name not in get.SETTING_NAMES:
        raise ValueError(f"unknown setting {name!r}; known: {list(get.SETTING_NAMES)}")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, not {value!r}")
    vendor_name = get.VENDOR_NAMES[name]
    value = float(value)

    def confirm(_result) -> bool:
        reading = get.settings(ctx)
        return reading.known and reading.value[vendor_name] == value

    return ctx.set.run(
        SetCommand(
            name=f"set {name}",
            send=lambda: ctx.vendor.set_setting(vendor_name, value),
            confirm=confirm,
            limits=(name, {"value": value}),
            ready=lambda: _not_acquiring(ctx),
        )
    )


def set_objective(ctx, slot: int) -> Outcome:
    if isinstance(slot, bool) or not isinstance(slot, int):
        raise ValueError(f"objective must be a slot number, not {slot!r}")

    def confirm(_result) -> bool:
        reading = get.settings(ctx)
        return reading.known and reading.value["objective_slot"] == slot

    return ctx.set.run(
        SetCommand(
            name=f"set objective {slot}",
            send=lambda: ctx.vendor.set_objective(slot),
            confirm=confirm,
            limits=("objective", {"slot": slot}),
            ready=lambda: _idle(ctx),
            tuning=OBJECTIVE_TUNING,
        )
    )


def acquire(ctx, *, name: str, z_planes: int = 1, z_step_um: float = 1.0) -> Outcome:
    here = get.raw_position(ctx).value_or_raise("the current position")
    z_top = here["z"] + (z_planes - 1) * z_step_um
    before = get.status(ctx).value_or_raise("the status")["last_acquisition"]
    previous_file = before["file"] if before is not None else None
    found: dict[str, str] = {}

    def confirm(file) -> bool:
        reading = get.status(ctx)
        if not reading.known:
            return False
        last = reading.value["last_acquisition"]
        if file is not None:
            ours = last is not None and last["file"] == file
        else:
            ours = last is not None and last["file"] != previous_file and last["name"] == name
        if ours and last["state"] == "done":
            found["file"] = last["file"]
            return True
        if ours and last["state"] == "aborted":
            raise NeverConfirmed("the acquisition was stopped before it finished")
        if not ours and reading.value["state"] == "idle":
            raise NeverConfirmed("the microscope is idle, but our acquisition is not running")
        return False

    outcome = ctx.set.run(
        SetCommand(
            name=f"acquire {name}",
            send=lambda: ctx.vendor.start_acquisition(name, z_planes=z_planes, z_step_um=z_step_um),
            confirm=confirm,
            limits=("acquire", {"z_planes": z_planes, "z_bottom": here["z"], "z_top": z_top}),
            ready=lambda: _idle(ctx),
            tuning=ACQUIRE_TUNING,
        )
    )
    if outcome.confirmed and outcome.result is None:
        outcome.result = found["file"]
    return outcome


def stop(ctx) -> Outcome:
    def confirm(_result) -> bool:
        reading = get.status(ctx)
        return reading.known and reading.value["state"] in ("idle", "changing_objective")

    return ctx.set.run(SetCommand(name="stop", send=ctx.vendor.abort, confirm=confirm, limits=None))
