"""The mock driver's plugin: the class the controller makes when it connects.

It only translates. The work of every command is in ``instrument.py`` and
the parts below it; each method here hands the call on and gives the
controller the values the contract asks for, as ``True`` and the values, or
``False`` and a message when the microscope did not do it. A request that is
wrong raises ``ValueError``, a microscope that failed ``RuntimeError``, and
the controller reports either with its text.

``handle`` is the connected mock, for tests that look inside it, such as
``handle.scope``, the pretend vendor software.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

from typing import Any

from .. import instrument

#: The axes, in the order the controller takes them.
AXES = ("x", "y", "z")


class ZmartControllerPlugin:
    """One connected mock microscope."""

    def __init__(self, connection: dict[str, Any]) -> None:
        self.handle = instrument.connect(connection)

    def disconnect(self) -> None:
        instrument.disconnect(self.handle)

    def get_info(self):
        info = instrument.get_info(self.handle)
        return True, (info["description"], info["setup"], info["chooses_its_own_folder"])

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
        """Apply the settings; a setting that could not be confirmed, or none at all, is a failure."""
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
    """``(x, y, z, actuators, canvas)``, the values the controller builds ``get_xyz`` from."""
    actuators = {axis: dict(reading[axis]["actuators"]) for axis in AXES}
    canvas = tuple(end for axis in AXES for end in reading[axis]["canvas"])
    return (*(reading[axis]["position"] for axis in AXES), actuators, canvas)
