from __future__ import annotations

from typing import Any

from .. import get_actions as get
from .. import set_actions as setter
from ..configuration import user_from_raw
from ..data_handling import wait_for_file
from .focus_score import brenner

_runs = 0


def autofocus(ctx, *, range_um: float = 20.0, step_um: float = 2.0) -> dict[str, Any]:
    global _runs
    if not step_um > 0 or not range_um >= step_um:
        raise ValueError("autofocus needs step_um above 0 and range_um at least step_um")
    here = get.raw_position(ctx).value_or_raise("the current position")
    planes = int(range_um // step_um) + 1
    bottom = here["z"] - (planes - 1) * step_um / 2
    start = setter.move(
        ctx, x=here["x"], y=here["y"], focus=bottom - here["piezo"], piezo=here["piezo"]
    )
    if not start.confirmed:
        raise RuntimeError(f"autofocus could not reach the bottom of its stack: {start.reason}")
    _runs += 1
    stack = setter.acquire(ctx, name=f"autofocus_{_runs:04d}", z_planes=planes, z_step_um=step_um)
    if not stack.confirmed:
        raise RuntimeError(f"the autofocus z-stack could not be confirmed: {stack.reason}")
    header, images = wait_for_file(ctx, stack.result)
    scores = [brenner(plane, header["width"]) for plane in images]
    best = max(range(len(scores)), key=scores.__getitem__)
    sharp = bottom + best * step_um
    finish = setter.move(
        ctx, x=here["x"], y=here["y"], focus=sharp - here["piezo"], piezo=here["piezo"]
    )
    if not finish.confirmed:
        raise RuntimeError(
            f"autofocus could not move to the height of sharpest focus: {finish.reason}"
        )
    user = user_from_raw(
        {"x": here["x"], "y": here["y"], "z": sharp}, here["objective"], ctx.config
    )
    return {"ran": "autofocus", "focus_um": sharp, "z_um": user["z"], "scores": scores}
