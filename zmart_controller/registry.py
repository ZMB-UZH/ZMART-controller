"""The registry: the drivers installed on this computer, and the folder ZMART keeps its files in.

A driver is two files: ``zmart_driver.json``, its name and how to reach the
microscope, and the class file it names, with a ``ZmartDriver`` class (or,
for an older driver, one function per command). :func:`load_driver` reads
them. :func:`register_driver` writes the JSON's path into this computer's
list, :func:`registry_file`, so that every Python session
can connect by name. :func:`get_instruments` shows the list.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .zmart_controller import COMMANDS

SETTINGS_FILE = "zmart_driver.json"
MOCK = "mock"


def config_root() -> Path:
    """The folder where ZMART keeps its files on this computer: the list of drivers,
    and what each driver measures once per microscope, such as the origin and the limits.

    ``ZMART_MICROSCOPY_ROOT`` overrides it. Otherwise it is
    ``C:\\ProgramData\\zmart-microscopy`` on Windows,
    ``/Library/Application Support/zmart-microscopy`` on macOS and
    ``/etc/zmart-microscopy`` on Linux.
    """
    if os.environ.get("ZMART_MICROSCOPY_ROOT"):
        return Path(os.environ["ZMART_MICROSCOPY_ROOT"])
    if platform.system() == "Windows":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "zmart-microscopy"
    if platform.system() == "Darwin":
        return Path("/Library/Application Support/zmart-microscopy")
    return Path("/etc/zmart-microscopy")


def registry_file() -> Path:
    """The controller's list of installed drivers: ``zmart-controller/drivers.json`` under :func:`config_root`."""
    return config_root() / "zmart-controller" / "drivers.json"


def _installed() -> dict[str, str]:
    """The installed drivers: name -> path of its zmart_driver.json."""
    try:
        return json.loads(registry_file().read_text())
    except FileNotFoundError:
        return {}


def _save(installed: dict[str, str]) -> None:
    registry_file().parent.mkdir(parents=True, exist_ok=True)
    registry_file().write_text(json.dumps(installed, indent=2) + "\n")


def get_instruments() -> dict[str, dict[str, Any]]:
    """Every installed driver by name, with how it connects. Passwords and tokens are left out.

    The mock is always first. A driver that can no longer be loaded shows
    ``{"error": ...}`` instead, so one broken driver never hides the others.
    """
    instruments: dict[str, dict[str, Any]] = {MOCK: {}}
    for name, settings in sorted(_installed().items()):
        try:
            connection = load_driver(settings).CONNECTION
        except Exception as error:
            instruments[name] = {"error": f"{type(error).__name__}: {error}"}
            continue
        instruments[name] = {
            key: value
            for key, value in connection.items()
            if not any(word in key.lower() for word in ("password", "token", "secret"))
        }
    return instruments


def register_driver(where: str | Path) -> str:
    """Install a driver on this computer: point at its ``zmart_driver.json``, or its folder.

    The driver is loaded first, so one that is missing something is refused
    with a message that says what, and nothing is written. Installing a
    driver again replaces its entry. Returns its name.
    """
    settings = Path(where).resolve()
    if settings.is_dir():
        settings = settings / SETTINGS_FILE
    driver = load_driver(settings)
    if driver.NAME == MOCK:
        raise ValueError(f"{MOCK!r} is the mock driver's name; choose another name in {settings}")
    _save({**_installed(), driver.NAME: str(settings)})
    return driver.NAME


def remove_driver(name: str) -> bool:
    """Take ``name`` off the list of installed drivers. Returns False if it was not there."""
    installed = _installed()
    if name not in installed:
        return False
    del installed[name]
    _save(installed)
    return True


def find_driver(name: str) -> tuple[Any, dict[str, Any]]:
    """The driver installed as ``name``, loaded, and its connection."""
    if name == MOCK:
        return importlib.import_module("zmart_controller.mock"), {}
    if name not in _installed():
        raise ValueError(f"no driver installed as {name!r}; installed: {list(get_instruments())}")
    driver = load_driver(_installed()[name])
    return driver, dict(driver.CONNECTION)


def load_driver(where: str | Path) -> SimpleNamespace:
    """The driver at ``where``, its ``zmart_driver.json`` or its folder, ready to hand to the controller.

    Reads the name, the connection and the class file (``driver``, relative
    to the JSON's folder) and imports that file. It must hold a
    ``ZmartDriver`` class, or one function per command. Returns an object
    with ``NAME``, ``CONNECTION`` and either ``ZmartDriver`` or the
    functions. Raises ``ValueError`` naming what is missing.
    """
    settings_file = Path(where).resolve()
    if settings_file.is_dir():
        settings_file = settings_file / SETTINGS_FILE
    if not settings_file.is_file():
        raise ValueError(
            f"a driver is installed from its {SETTINGS_FILE}; {settings_file} is missing"
        )
    settings = json.loads(settings_file.read_text())
    name = settings.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f'{settings_file} must give the driver\'s "name"')
    driver_file = (settings_file.parent / settings.get("driver", "zmart_driver.py")).resolve()
    if not driver_file.is_file():
        raise ValueError(f'{settings_file} names the class file "driver": {driver_file} is missing')
    module = _import(driver_file)
    driver = SimpleNamespace(
        __name__=name, NAME=name, CONNECTION=dict(settings.get("connection") or {})
    )
    if isinstance(getattr(module, "ZmartDriver", None), type):
        driver.ZmartDriver = module.ZmartDriver
    else:
        vars(driver).update(driver_functions(module))  # an older driver: one function per command
    return driver


def driver_functions(driver: Any) -> dict[str, Any]:
    """The functions of an older driver, one per command, found by name on a module.

    Raises ``ValueError`` naming every missing function.
    """
    functions = {name: getattr(driver, name, None) for name in ("connect", *COMMANDS)}
    missing = [name for name, f in functions.items() if name != "disconnect" and not callable(f)]
    if missing:
        raise ValueError(f"driver {driver_name(driver)} is missing functions: {missing}")
    return {name: f for name, f in functions.items() if f is not None}


def driver_name(driver: Any) -> str:
    """A short name for ``driver``, to show in messages."""
    return getattr(driver, "__name__", None) or type(driver).__name__


def _import(file: Path):
    """Import a driver's class file. Inside a package it is imported as part of it, so its
    own imports work; in a plain folder it is imported by path."""
    parts, folder = [file.stem], file.parent
    while (folder / "__init__.py").is_file():
        parts.insert(0, folder.name)
        folder = folder.parent
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    if len(parts) > 1:
        return importlib.import_module(".".join(parts))
    name = "zmart_driver_" + "".join(c if c.isalnum() else "_" for c in str(file))
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]  # so a fixed file is read again next time
            raise
    return sys.modules[name]
