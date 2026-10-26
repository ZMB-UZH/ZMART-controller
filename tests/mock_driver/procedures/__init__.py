from .autofocus import autofocus
from .focus_score import brenner
from .stage import backlash_takeup, record_origin, zero_piezo

PROCEDURES = {
    "autofocus": {
        "description": (
            "Take a short z-stack around the current height, find the sharpest "
            "plane, and move there. Optional: range_um (default 20), step_um (default 2)."
        ),
        "run": autofocus,
    },
    "backlash_takeup": {
        "description": (
            "Approach the current position from the same side every time, so "
            "that positions repeat exactly."
        ),
        "run": backlash_takeup,
    },
    "zero_piezo": {
        "description": "Move the piezo to the middle of its range, keeping the focus height.",
        "run": zero_piezo,
    },
}

__all__ = ["PROCEDURES", "autofocus", "backlash_takeup", "brenner", "record_origin", "zero_piezo"]
