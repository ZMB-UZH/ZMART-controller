from __future__ import annotations

from typing import Any


class Gate:
    def __init__(self, limits: dict[str, Any] | None) -> None:
        self._limits = limits

    def check(self, key: str, values: dict[str, Any]) -> str | None:
        limits = self._limits
        if limits is None:
            return "the limits are not loaded, so nothing on the microscope may change"
        if key == "stage":
            return self._stage(values, limits["stage_um"])
        if key in limits["settings"]:
            low, high = limits["settings"][key]
            value = values["value"]
            if not low <= value <= high:
                return f"{key} = {value} is outside the limits [{low}, {high}]"
            return None
        if key == "objective":
            if values["slot"] not in limits["objectives"]:
                return f"objective {values['slot']} is not allowed; the limits allow {limits['objectives']}"
            return None
        if key == "acquire":
            most = limits["acquisition"]["max_z_planes"]
            if values["z_planes"] > most:
                return f"{values['z_planes']} z planes is more than the limit of {most}"
            low, high = limits["stage_um"]["z"]
            if values["z_bottom"] < low or values["z_top"] > high:
                return (
                    f"the z-stack would reach from {values['z_bottom']:.2f} to "
                    f"{values['z_top']:.2f} µm (stage coordinates), outside the travel "
                    f"range [{low}, {high}]"
                )
            return None
        return f"there is no limit for {key!r}, so it is refused"

    @staticmethod
    def _stage(values: dict[str, float], stage: dict[str, list[float]]) -> str | None:
        for axis in ("x", "y", "z"):
            low, high = stage[axis]
            if not low <= values[axis] <= high:
                return (
                    f"{axis} would go to {values[axis]:.2f} µm (stage coordinates), "
                    f"outside the travel range [{low}, {high}] set in the limits"
                )
        return None
