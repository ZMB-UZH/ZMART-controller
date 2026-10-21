"""The ZmartController: one microscope, one method per command.

Make one with a driver, and it connects::

    from zmart_controller import mic

    mic.connect("my-scope")    # connect to an installed driver
    mic.set_xyz(100, 50, 0)    # every command goes to the microscope connected last

To hold several microscopes at once, keep each one::

    left, right = ZmartController("left-scope"), ZmartController("right-scope")
    left.set_xyz(100, 50, 0)

Each method calls the method of the same name on the driver's
``ZmartControllerPlugin``, handing every value over by name, and the plugin
hands back ``True`` and the values, or ``False`` and a message. The
controller writes every answer itself, so it holds exactly what the contract
says on every microscope. There are three outcomes, and the answer always
has the same shape:

- success: ``{"success": True, "output": ...}`` with the values;
- failure, the plugin says the microscope did not do it:
  ``{"success": False, "output": "..."}`` with the plugin's message;
- call failure, the method itself raised: the same, with the error text.

Every call returns when the driver has finished.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

from os import PathLike
from typing import Any

#: The unit of every position, reading and canvas in a ``get_xyz`` or ``set_xyz`` answer.
UNIT = "micrometer"

#: The kind of acquisition ``acquire`` names when the workflow gives none.
DEFAULT_ACQUISITION_TYPE = "acquisition"


class ZmartController:
    """One connected microscope.

    ``driver`` is the name of an installed driver, a driver loaded with
    ``load_driver``, a ``ZmartControllerPlugin`` class, or anything that holds
    one under that name, such as a module. ``context`` names the driver:
    ``{"driver": ...}``. ``plugin`` is the connected ``ZmartControllerPlugin``.
    """

    def __init__(self, driver: Any, connection: dict[str, Any] | None = None) -> None:
        from .registry import driver_name, find_driver, plugin_class

        name = None
        if isinstance(driver, str):
            name = driver
            driver, saved = find_driver(name)
            connection = saved if connection is None else connection
        elif connection is None:
            connection = getattr(driver, "CONNECTION", None)
        self.context = {"driver": name or driver_name(driver)}
        self.plugin = plugin_class(driver)(dict(connection or {}))  # making it connects

    def disconnect(self) -> None:
        """Close the connection, if the plugin has a way to close it."""
        if hasattr(self.plugin, "disconnect"):
            self.plugin.disconnect()

    def get_info(self) -> dict:
        """The microscope in plain words, what is set up on it, whether it
        chooses its own folder, and how the connection's checks went.

        ``chooses_its_own_folder`` is True for a microscope whose software
        always saves in its own place, whatever ``output_folder`` ``acquire``
        is given; its answers then list where the files really are.
        ``connection_status`` holds the connection's checks in the driver's
        order, each with its answer, ``"pending"`` until it has one, or a
        text that begins with ``failed``; ``{}`` when there is nothing to
        check.
        """
        try:
            ok, result = self.plugin.get_info()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        description, setup, chooses_its_own_folder, connection_status = result

        return {
            "success": True,
            "output": {
                "description": description,
                "setup": setup,
                "chooses_its_own_folder": chooses_its_own_folder,
                "connection_status": connection_status,
            },
        }

    def get_actuators(self) -> dict:
        """The motors per axis, and the one used when none is chosen.

        For example ``{"z": {"options": ["motoric", "piezo"], "default": "motoric"}}``.
        The driver decides the default; ``get_xyz`` and ``set_xyz`` both use it.
        """
        try:
            ok, result = self.plugin.get_actuators()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        x, y, z = result

        return {"success": True, "output": {"x": x, "y": y, "z": z}}

    def get_xyz(self, with_actuators: dict | None = None) -> dict:
        """Where the stage is. Each axis: ``position``, ``unit``, ``used_actuator``, ``actuator_readings``, ``canvas``.

        ``position`` is measured from the origin. ``unit`` says that every
        number here is in micrometres. ``used_actuator`` is the motor this
        call used: the one ``with_actuators`` chose for the axis, or else the
        default ``get_actuators`` names. ``actuator_readings`` gives each
        motor of that axis with its own reading, as the microscope reports
        it, measured from the motor's own zero rather than from the origin.
        ``canvas`` is everywhere a picture can show.
        """
        try:
            chosen = chosen_actuators(self.get_actuators(), with_actuators)
            ok, result = self.plugin.get_xyz(with_actuators=chosen)

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        return {"success": True, "output": xyz_output(result, chosen)}

    def set_xyz(self, x: float, y: float, z: float, with_actuators: dict | None = None) -> dict:
        """Move to a position in micrometres from the origin, and answer like ``get_xyz``.

        ``with_actuators`` picks the motor per axis, such as ``{"z": "piezo"}``;
        an axis left out moves with the default ``get_actuators`` names, the
        same rule as ``get_xyz``. The position is micrometres from the origin
        whichever motor moves, never the motor's own units. The answer is read
        from the microscope after the stage has arrived, so it shows where the
        stage really is, not the numbers that were asked for.
        """
        try:
            chosen = chosen_actuators(self.get_actuators(), with_actuators)
            ok, result = self.plugin.set_xyz(x=x, y=y, z=z, with_actuators=chosen)

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        return {"success": True, "output": xyz_output(result, chosen)}

    def get_state(self) -> dict:
        """The settings: ``changeable``, which ``set_state`` applies, and ``observed``, read-only."""
        try:
            ok, result = self.plugin.get_state()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        changeable, observed = result

        return {"success": True, "output": {"changeable": changeable, "observed": observed}}

    def set_state(self, state: dict) -> dict:
        """Apply the settings under ``changeable``; the answer names what was applied."""
        try:
            ok, result = self.plugin.set_state(changeable=state["changeable"])

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        applied = result

        return {"success": True, "output": {"applied": applied}}

    def get_acquisition_settings(self) -> dict:
        """How an acquisition is triggered: ``{name: {"options": ..., "default": ..., "active": ...}}``."""
        try:
            ok, result = self.plugin.get_acquisition_settings()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        settings = result

        return {"success": True, "output": settings}

    def acquire(
        self,
        position_label: str,
        acquisition_type: str | None = None,
        output_folder: str | PathLike | None = None,
        acquisition_settings: dict | None = None,
    ) -> dict:
        """Capture an image here and save it; the answer lists every file and image plane.

        ``acquisition_type`` says what kind of acquisition this is in the
        run, such as ``"overview"`` or ``"targets"``; the driver puts it in
        its file names and metadata, and the answer reports it beside
        ``position_label``. Left out, it is ``DEFAULT_ACQUISITION_TYPE``.
        ``output_folder`` is where the files go; left out, the driver saves
        where it was set up to. A microscope whose software always saves in
        its own place saves there instead and says so in ``get_info``; the
        answer always lists where the files really are.
        ``acquisition_settings`` says how to trigger the acquisition; left
        out, the plugin uses the ``active`` value of each setting.
        """
        try:
            acquisition_type = acquisition_type_or_default(acquisition_type)
            output_folder = output_folder_as_text(output_folder)
            ok, result = self.plugin.acquire(
                position_label=position_label,
                acquisition_type=acquisition_type,
                output_folder=output_folder,
                acquisition_settings=acquisition_settings,
            )

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        files, planes = result

        return {
            "success": True,
            "output": {
                "position_label": position_label,
                "acquisition_type": acquisition_type,
                "files": files,
                "planes": planes,
            },
        }

    def get_procedures(self) -> dict:
        """The routines the microscope offers: ``{name: {"description": ...}}``."""
        try:
            ok, result = self.plugin.get_procedures()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        procedures = result

        return {"success": True, "output": procedures}

    def run_procedure(self, procedure: dict) -> dict:
        """Run the routine named by ``procedure["name"]``; the other keys are its arguments."""
        try:
            ok, result = self.plugin.run_procedure(procedure=procedure)

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        ran = result

        return {"success": True, "output": {"ran": ran}}


def chosen_actuators(offered: dict, with_actuators: dict | None) -> dict[str, str]:
    """The motor for every axis: the one asked for, or else the driver's default.

    ``offered`` is the answer of ``get_actuators``. A driver therefore always
    receives one motor per axis, and ``get_xyz`` and ``set_xyz`` cannot
    differ about the default. Raises ``ValueError`` for an axis or a motor
    the driver does not offer, before the driver is asked anything, and
    ``RuntimeError`` when the driver could not say which motors it has.
    """
    if not offered["success"]:
        raise RuntimeError(f"the driver could not list its actuators: {offered['output']}")
    motors = offered["output"]
    chosen = {axis: motors[axis]["default"] for axis in ("x", "y", "z")}
    for axis, name in (with_actuators or {}).items():
        if axis not in chosen:
            raise ValueError(f"there is no axis {axis!r}; the axes are 'x', 'y' and 'z'")
        if name not in motors[axis]["options"]:
            raise ValueError(
                f"{name!r} is not an actuator of axis {axis!r}; it has {motors[axis]['options']}"
            )
        chosen[axis] = name
    return chosen


def acquisition_type_or_default(acquisition_type: str | None) -> str:
    """The kind of acquisition: the one given, or ``DEFAULT_ACQUISITION_TYPE`` when none is.

    Every driver receives a word, so the kind is named the same way in every
    file and answer. Raises ``ValueError`` for anything but a word, before the
    driver is asked anything.
    """
    if acquisition_type is None:
        return DEFAULT_ACQUISITION_TYPE
    if not isinstance(acquisition_type, str) or not acquisition_type.strip():
        raise ValueError(
            f"acquisition_type must be a word, such as 'overview', not {acquisition_type!r}"
        )
    return acquisition_type


def output_folder_as_text(output_folder: str | PathLike | None) -> str | None:
    """The folder to save in as text, or None when the driver's own place is meant.

    Raises ``ValueError`` for anything that is not a folder's path, before the
    driver is asked anything.
    """
    if output_folder is None:
        return None
    if not isinstance(output_folder, (str, PathLike)) or not str(output_folder).strip():
        raise ValueError(f"output_folder must be a folder's path, not {output_folder!r}")
    return str(output_folder)


def xyz_output(result, chosen: dict[str, str]) -> dict:
    """Build the answer of ``get_xyz`` and ``set_xyz`` from what the plugin hands back.

    The plugin returns ``(x, y, z, actuator_readings, canvas)``: the
    position in micrometres from the origin, the reading of every motor per
    axis (``{"x": {...}, "y": {...}, "z": {...}}``), and the canvas
    ``(x_min, x_max, y_min, y_max, z_min, z_max)``. Every number is in
    micrometres, and each axis says so under ``unit``. ``chosen`` is the
    motor used per axis, which each axis names under ``used_actuator``.
    """
    x, y, z, readings, canvas = result
    x_min, x_max, y_min, y_max, z_min, z_max = canvas
    axes = {
        "x": (x, readings["x"], [x_min, x_max]),
        "y": (y, readings["y"], [y_min, y_max]),
        "z": (z, readings["z"], [z_min, z_max]),
    }
    return {
        axis: {
            "position": position,
            "unit": UNIT,
            "used_actuator": chosen[axis],
            "actuator_readings": dict(motors),
            "canvas": canvas,
        }
        for axis, (position, motors, canvas) in axes.items()
    }


#: The commands: the public methods of the controller. A ZmartControllerPlugin
#: has a method of the same name for each; disconnect is optional.
COMMANDS = tuple(name for name, value in vars(ZmartController).items() if not name.startswith("_"))


class Mic:
    """``mic``: connect once, then every command goes to that microscope::

        from zmart_controller import mic

        mic.connect("my-scope")
        mic.set_xyz(100, 50, 0)
        mic.disconnect()

    It also carries the calls that need no microscope: ``get_instruments``,
    ``register_driver``, ``remove_driver`` and ``validate_driver``. To hold
    several microscopes at once, make a ``ZmartController`` for each instead.
    """

    def __init__(self) -> None:
        self._connected: ZmartController | None = None

    def connect(self, driver: Any, connection: dict[str, Any] | None = None) -> None:
        """Connect to a microscope; the previous one, if any, is disconnected first."""
        self.disconnect()
        self._connected = ZmartController(driver, connection)

    def disconnect(self) -> None:
        """Close the connection. With nothing connected this does nothing."""
        if self._connected is not None:
            self._connected.disconnect()
            self._connected = None

    @staticmethod
    def get_instruments() -> dict:
        """The drivers installed on this computer, by name, each with how it connects."""
        from .registry import get_instruments

        return get_instruments()

    @staticmethod
    def register_driver(where) -> str:
        """Install a driver on this computer: point at its folder. Returns its name."""
        from .registry import register_driver

        return register_driver(where)

    @staticmethod
    def remove_driver(name: str) -> bool:
        """Take an installed driver off this computer's list."""
        from .registry import remove_driver

        return remove_driver(name)

    @staticmethod
    def validate_driver(driver, connection=None) -> list:
        """The problems with a driver's answers, one sentence each; empty when it fits."""
        from .validate import validate_driver

        return validate_driver(driver, connection)

    def __getattr__(self, name: str):
        # A command such as get_xyz goes to the connected microscope.
        if name in COMMANDS:
            if self._connected is None:
                raise RuntimeError(
                    f"no microscope connected: call mic.connect(driver) before mic.{name}()"
                )
            return getattr(self._connected, name)
        raise AttributeError(f"mic has no command {name!r}")


#: Connect once with ``mic.connect(driver)``, then call the commands on ``mic``.
mic = Mic()
