from __future__ import annotations

from os import PathLike
from typing import Any

UNIT = "micrometer"
DEFAULT_ACQUISITION_TYPE = "acquisition"


class ZmartController:
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
        self.plugin = plugin_class(driver)(dict(connection or {}))

    def disconnect(self) -> None:
        if hasattr(self.plugin, "disconnect"):
            self.plugin.disconnect()

    def get_info(self) -> dict:
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
        try:
            ok, result = self.plugin.get_actuators()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        x, y, z = result

        return {"success": True, "output": {"x": x, "y": y, "z": z}}

    def get_xyz(self, with_actuators: dict | None = None) -> dict:
        try:
            chosen = chosen_actuators(self.get_actuators(), with_actuators)
            ok, result = self.plugin.get_xyz(with_actuators=chosen)

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        return {"success": True, "output": xyz_output(result, chosen)}

    def set_xyz(self, x: float, y: float, z: float, with_actuators: dict | None = None) -> dict:
        try:
            chosen = chosen_actuators(self.get_actuators(), with_actuators)
            ok, result = self.plugin.set_xyz(x=x, y=y, z=z, with_actuators=chosen)

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        return {"success": True, "output": xyz_output(result, chosen)}

    def get_state(self) -> dict:
        try:
            ok, result = self.plugin.get_state()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        changeable, observed = result

        return {"success": True, "output": {"changeable": changeable, "observed": observed}}

    def set_state(self, state: dict) -> dict:
        try:
            ok, result = self.plugin.set_state(changeable=state["changeable"])

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        applied = result

        return {"success": True, "output": {"applied": applied}}

    def get_acquisition_settings(self) -> dict:
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
        try:
            ok, result = self.plugin.get_procedures()

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        procedures = result

        return {"success": True, "output": procedures}

    def run_procedure(self, procedure: dict) -> dict:
        try:
            ok, result = self.plugin.run_procedure(procedure=procedure)

        except Exception as error:
            return {"success": False, "output": f"{type(error).__name__}: {error}"}

        if not ok:
            return {"success": False, "output": result}

        ran = result

        return {"success": True, "output": {"ran": ran}}


def chosen_actuators(offered: dict, with_actuators: dict | None) -> dict[str, str]:
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
    if acquisition_type is None:
        return DEFAULT_ACQUISITION_TYPE
    if not isinstance(acquisition_type, str) or not acquisition_type.strip():
        raise ValueError(
            f"acquisition_type must be a word, such as 'overview', not {acquisition_type!r}"
        )
    return acquisition_type


def output_folder_as_text(output_folder: str | PathLike | None) -> str | None:
    if output_folder is None:
        return None
    if not isinstance(output_folder, (str, PathLike)) or not str(output_folder).strip():
        raise ValueError(f"output_folder must be a folder's path, not {output_folder!r}")
    return str(output_folder)


def xyz_output(result, chosen: dict[str, str]) -> dict:
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


COMMANDS = tuple(name for name, value in vars(ZmartController).items() if not name.startswith("_"))


class Mic:
    def __init__(self) -> None:
        self._connected: ZmartController | None = None

    def connect(self, driver: Any, connection: dict[str, Any] | None = None) -> None:
        self.disconnect()
        self._connected = ZmartController(driver, connection)

    def disconnect(self) -> None:
        if self._connected is not None:
            self._connected.disconnect()
            self._connected = None

    @staticmethod
    def get_instruments() -> dict:
        from .registry import get_instruments

        return get_instruments()

    @staticmethod
    def register_driver(where) -> str:
        from .registry import register_driver

        return register_driver(where)

    @staticmethod
    def remove_driver(name: str) -> bool:
        from .registry import remove_driver

        return remove_driver(name)

    @staticmethod
    def validate_driver(driver, connection=None) -> list:
        from .validate import validate_driver

        return validate_driver(driver, connection)

    def __getattr__(self, name: str):
        if name in COMMANDS:
            if self._connected is None:
                raise RuntimeError(
                    f"no microscope connected: call mic.connect(driver) before mic.{name}()"
                )
            return getattr(self._connected, name)
        raise AttributeError(f"mic has no command {name!r}")


mic = Mic()
