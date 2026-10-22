from __future__ import annotations

from typing import Any

from .. import get_actions as get
from .. import set_actions as setter
from ..configuration import sample_point, save

BACKLASH_STEP_UM = 50.0


def _require(outcome, what: str) -> None:
    if not outcome.confirmed:
        raise RuntimeError(f"{what} could not be confirmed: {outcome.reason}")


def backlash_takeup(ctx) -> dict[str, Any]:
    here = get.raw_position(ctx).value_or_raise("the current position")
    stage = ctx.config.limits["stage_um"]
    step = {
        axis: max(0.0, min(BACKLASH_STEP_UM, here[axis] - stage[axis][0])) for axis in ("x", "y")
    }
    if step["x"] > 0 or step["y"] > 0:
        back = setter.move(
            ctx,
            x=here["x"] - step["x"],
            y=here["y"] - step["y"],
            focus=here["focus"],
            piezo=here["piezo"],
        )
        _require(back, "stepping back")
        forward = setter.move(
            ctx, x=here["x"], y=here["y"], focus=here["focus"], piezo=here["piezo"]
        )
        _require(forward, "the approach")
    return {"approach": "+x +y", "step_um": step}


def zero_piezo(ctx) -> dict[str, Any]:
    here = get.raw_position(ctx).value_or_raise("the current position")
    outcome = setter.move(ctx, x=here["x"], y=here["y"], focus=here["z"], piezo=0.0)
    _require(outcome, "parking the piezo")
    return {"focus_um": here["z"], "piezo_um": 0.0}


def record_origin(ctx) -> dict[str, float]:
    here = get.raw_position(ctx).value_or_raise("the current position")
    origin = sample_point(here, here["objective"], ctx.config)
    save("origin", origin, ctx.identity)
    return origin
