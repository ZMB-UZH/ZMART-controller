"""The ZmartController: one microscope, one method per command.

Make one with a driver, and it connects::

    from zmart_controller import mic

    mic.connect("my-scope")    # connect to an installed driver
    mic.set_xyz(100, 50, 0)    # every command goes to the microscope connected last

To hold several microscopes at once, keep each one::

    left, right = ZmartController("left-scope"), ZmartController("right-scope")
    left.set_xyz(100, 50, 0)

Each method calls the method of the same name on the ``ZmartDriver``, which
hands back ``True`` and the values, or ``False`` and a message. There are
three outcomes, and the answer always has the same shape:

- success: ``{"success": True, "content": ...}`` with the values;
- failure, the driver says the microscope did not do it:
  ``{"success": False, "content": "..."}`` with the driver's message;
- call failure, the method itself raised: the same, with the error text.

Every call returns when the driver has finished.

A driver may also be a module with one function per command, such as the
mock; its functions already build the answers themselves.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

from functools import partial
from typing import Any

#: The unit of every position, reading and canvas in a ``get_xyz`` or ``set_xyz`` answer.
UNIT = "micrometer"


class ZmartController:
    """One connected microscope. ``context`` names the driver: ``{"driver": ...}``."""

    def __init__(self, driver: Any, connection: dict[str, Any] | None = None) -> None:
        from .registry import driver_functions, driver_name, find_driver

        name = None
        if isinstance(driver, str):
            name = driver
            driver, saved = find_driver(name)
            connection = saved if connection is None else connection
        elif connection is None:
            connection = getattr(driver, "CONNECTION", None)
        connection = dict(connection or {})
        self.context = {"driver": name or driver_name(driver)}

        driver_class = driver if isinstance(driver, type) else getattr(driver, "ZmartDriver", None)
        if driver_class is not None:
            self._handle = driver_class(connection)  # making it connects
            return
        # An older driver, a module with one function per command: its
        # functions answer directly, so they stand in for the methods below.
        functions = driver_functions(driver)
        self._handle = functions.pop("connect")(connection)
        for command, function in functions.items():
            setattr(self, command, _answering(partial(function, self._handle)))

    def disconnect(self) -> None:
        """Close the connection, if the driver has a way to close it."""
        if hasattr(self._handle, "disconnect"):
            self._handle.disconnect()

    def get_info(self) -> dict:
        """The microscope in plain words, and what is set up on it, such as where it saves."""
        try:
            ok, result = self._handle.get_info()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        description, setup = result

        return {"success": True, "content": {"description": description, "setup": setup}}

    def get_actuators(self) -> dict:
        """The motors per axis, and the one used when none is chosen.

        For example ``{"z": {"options": ["motoric", "piezo"], "default": "motoric"}}``.
        The driver decides the default; ``get_xyz`` and ``set_xyz`` both use it.
        """
        try:
            ok, result = self._handle.get_actuators()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        x, y, z = result

        return {"success": True, "content": {"x": x, "y": y, "z": z}}

    def get_xyz(self, with_actuators: dict | None = None) -> dict:
        """Where the stage is. Each axis: ``position``, ``unit``, ``actuator``, ``actuators``, ``canvas``.

        ``position`` is measured from the origin. ``unit`` says that every
        number here is in micrometres. ``actuator`` is the motor this call
        used: the one ``with_actuators`` chose for the axis, or else the
        default ``get_actuators`` names. ``actuators`` gives each motor of
        that axis with its own raw reading, as the microscope reports it.
        ``canvas`` is everywhere a picture can show.
        """
        try:
            chosen = chosen_actuators(self.get_actuators(), with_actuators)
            ok, result = self._handle.get_xyz(chosen)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        return {"success": True, "content": _xyz_content(result, chosen)}

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
            ok, result = self._handle.set_xyz(x, y, z, chosen)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        return {"success": True, "content": _xyz_content(result, chosen)}

    def get_state(self) -> dict:
        """The settings: ``changeable``, which ``set_state`` applies, and ``observed``, read-only."""
        try:
            ok, result = self._handle.get_state()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        changeable, observed = result

        return {"success": True, "content": {"changeable": changeable, "observed": observed}}

    def set_state(self, state: dict) -> dict:
        """Apply the settings under ``changeable``; the answer names what was applied."""
        try:
            ok, result = self._handle.set_state(state["changeable"])

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        applied = result

        return {"success": True, "content": {"applied": applied}}

    def get_acquisition_settings(self) -> dict:
        """How an acquisition is triggered: ``{name: {"options": ..., "default": ..., "active": ...}}``."""
        try:
            ok, result = self._handle.get_acquisition_settings()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        settings = result

        return {"success": True, "content": settings}

    def acquire(self, position_label: str, acquisition_settings: dict | None = None) -> dict:
        """Capture an image here and save it; the answer lists every file and image plane."""
        try:
            ok, result = self._handle.acquire(position_label, acquisition_settings)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        files, planes = result

        return {
            "success": True,
            "content": {"position_label": position_label, "files": files, "planes": planes},
        }

    def get_procedures(self) -> dict:
        """The routines the microscope offers: ``{name: {"description": ...}}``."""
        try:
            ok, result = self._handle.get_procedures()

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        procedures = result

        return {"success": True, "content": procedures}

    def run_procedure(self, procedure: dict) -> dict:
        """Run the routine named by ``procedure["name"]``; the other keys are its arguments."""
        try:
            ok, result = self._handle.run_procedure(procedure)

        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "content": result}

        ran = result

        return {"success": True, "content": {"ran": ran}}


def chosen_actuators(offered: dict, with_actuators: dict | None) -> dict[str, str]:
    """The motor for every axis: the one asked for, or else the driver's default.

    ``offered`` is the answer of ``get_actuators``. A driver therefore always
    receives one motor per axis, and ``get_xyz`` and ``set_xyz`` cannot
    differ about the default. Raises ``ValueError`` for an axis or a motor
    the driver does not offer, before the driver is asked anything, and
    ``RuntimeError`` when the driver could not say which motors it has.
    """
    if not offered["success"]:
        raise RuntimeError(f"the driver could not list its actuators: {offered['content']}")
    motors = offered["content"]
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


def _xyz_content(result, chosen: dict[str, str]) -> dict:
    """Build the answer of ``get_xyz`` and ``set_xyz`` from what the driver hands back.

    The driver returns ``(x, y, z, actuators, canvas)``: the position in
    micrometres from the origin, the raw reading of every motor per axis
    (``{"x": {...}, "y": {...}, "z": {...}}``), and the canvas
    ``(x_min, x_max, y_min, y_max, z_min, z_max)``. Every number is in
    micrometres, and each axis says so under ``unit``. ``chosen`` is the
    motor used per axis, which each axis names under ``actuator``.
    """
    x, y, z, actuators, canvas = result
    x_min, x_max, y_min, y_max, z_min, z_max = canvas
    axes = {
        "x": (x, actuators["x"], [x_min, x_max]),
        "y": (y, actuators["y"], [y_min, y_max]),
        "z": (z, actuators["z"], [z_min, z_max]),
    }
    return {
        axis: {
            "position": position,
            "unit": UNIT,
            "actuator": chosen[axis],
            "actuators": dict(motors),
            "canvas": canvas,
        }
        for axis, (position, motors, canvas) in axes.items()
    }


def _answering(function):
    """Give a module driver's function the same three outcomes as the methods above."""

    def answer(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as error:
            return {"success": False, "content": f"{type(error).__name__}: {error}"}

    return answer


#: The commands: the public methods of the controller. A ZmartDriver has a
#: method for each, a module driver a function. disconnect is optional.
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
        """Install a driver on this computer: point at its ``zmart_driver.json``. Returns its name."""
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
