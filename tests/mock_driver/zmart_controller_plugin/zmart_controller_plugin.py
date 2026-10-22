from __future__ import annotations

from typing import Any

from .. import instrument

AXES = ("x", "y", "z")


class ZmartControllerPlugin:
    def __init__(self, connection: dict[str, Any]) -> None:
        self.handle = instrument.connect(connection)

    def disconnect(self) -> None:
        instrument.disconnect(self.handle)

    def get_info(self):
        info = instrument.get_info(self.handle)
        return True, (
            info["description"],
            info["setup"],
            info["chooses_its_own_folder"],
            info["connection_status"],
        )

    def get_actuators(self):
        motors = instrument.get_actuators(self.handle)
        return True, tuple(motors[axis] for axis in AXES)

    def get_xyz(self, with_actuators):
        return True, xyz_values(instrument.get_xyz(self.handle, with_actuators=with_actuators))

    def set_xyz(self, x, y, z, with_actuators):
        moved = instrument.set_xyz(self.handle, x=x, y=y, z=z, with_actuators=with_actuators)
        return True, xyz_values(moved)

    def get_state(self):
        state = instrument.get_state(self.handle)
        return True, (state["changeable"], state["observed"])

    def set_state(self, changeable):
        done = instrument.set_state(self.handle, changeable=changeable)
        if done["unconfirmed"]:
            reasons = "; ".join(f"{name}: {reason}" for name, reason in done["unconfirmed"].items())
            return False, f"these settings could not be confirmed: {reasons}"
        if not done["applied"]:
            return False, "nothing was applied: changeable names no setting"
        return True, done["applied"]

    def get_acquisition_settings(self):
        return True, instrument.get_acquisition_settings(self.handle)

    def acquire(self, position_label, acquisition_type, output_folder, acquisition_settings):
        taken = instrument.acquire(
            self.handle,
            position_label=position_label,
            acquisition_type=acquisition_type,
            output_folder=output_folder,
            acquisition_settings=acquisition_settings,
        )
        if not taken["confirmed"]:
            return False, f"the acquisition could not be confirmed: {taken['reason']}"
        return True, (taken["files"], taken["planes"])

    def get_procedures(self):
        return True, instrument.get_procedures(self.handle)

    def run_procedure(self, procedure):
        return True, instrument.run_procedure(self.handle, procedure=procedure)["ran"]


def xyz_values(reading: dict) -> tuple:
    readings = {axis: dict(reading[axis]["actuator_readings"]) for axis in AXES}
    canvas = tuple(end for axis in AXES for end in reading[axis]["canvas"])
    return (*(reading[axis]["position"] for axis in AXES), readings, canvas)
