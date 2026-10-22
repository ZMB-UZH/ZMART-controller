"""The registry: the drivers installed on this computer, and the folder ZMART keeps its files in.

A driver is a folder. Its plugin, the part the controller talks to, is
always in the driver's ``zmart_controller_plugin/`` folder, as two files:
``zmart_controller_plugin.json``, the driver's name and how to reach the
microscope, and ``zmart_controller_plugin.py``, the ``ZmartControllerPlugin``
class. :func:`load_driver` reads them. :func:`register_driver` writes the
driver's folder into this computer's list, :func:`registry_file`, so that
every Python session can connect by name. :func:`get_instruments` shows the
list.

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

#: The folder inside every driver that holds its plugin.
PLUGIN_FOLDER = "zmart_controller_plugin"

#: The plugin's settings: the driver's ``name`` and its ``connection``, nothing else.
SETTINGS_FILE = "zmart_controller_plugin.json"

#: The plugin's code, which holds :data:`PLUGIN_CLASS`.
PLUGIN_FILE = "zmart_controller_plugin.py"

#: The class the controller makes when it connects.
PLUGIN_CLASS = "ZmartControllerPlugin"

#: What the settings file may hold.
SETTINGS_KEYS = ("name", "connection")

#: A connection key holding one of these is secret: null in the file, typed when connecting.
SECRET_WORDS = ("password", "token", "secret")


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


def installed_drivers() -> dict[str, str]:
    """The installed drivers: name -> the driver's folder."""
    try:
        return json.loads(registry_file().read_text())
    except FileNotFoundError:
        return {}


def save_installed_drivers(installed: dict[str, str]) -> None:
    """Write the list of installed drivers."""
    registry_file().parent.mkdir(parents=True, exist_ok=True)
    registry_file().write_text(json.dumps(installed, indent=2) + "\n")


def get_instruments() -> dict[str, dict[str, Any]]:
    """Every installed driver by name, with how it connects. A password is always null: it is typed when connecting.

    A driver that can no longer be loaded shows ``{"error": ...}`` instead,
    so one broken driver never hides the others.
    """
    instruments: dict[str, dict[str, Any]] = {}
    for name, folder in sorted(installed_drivers().items()):
        try:
            connection = load_driver(registered_folder(name, folder)).CONNECTION
        except Exception as error:
            instruments[name] = {"error": f"{type(error).__name__}: {error}"}
            continue
        instruments[name] = connection
    return instruments


def register_driver(where: str | Path) -> str:
    """Install a driver on this computer: point at the driver's folder. Returns its name.

    The driver's folder is the one that holds ``zmart_controller_plugin/``.
    The driver is loaded first, so one that is missing something is refused
    with a message that says what, and nothing is written. Installing a
    driver again replaces its entry.
    """
    folder = driver_folder(where)
    driver = load_driver(folder)
    save_installed_drivers({**installed_drivers(), driver.NAME: str(folder)})
    return driver.NAME


def remove_driver(name: str) -> bool:
    """Take ``name`` off the list of installed drivers. Returns False if it was not there."""
    installed = installed_drivers()
    if name not in installed:
        return False
    del installed[name]
    save_installed_drivers(installed)
    return True


def find_driver(name: str) -> tuple[Any, dict[str, Any]]:
    """The driver installed as ``name``, loaded, and its connection."""
    installed = installed_drivers()
    if name not in installed:
        raise ValueError(f"no driver installed as {name!r}; installed: {sorted(installed)}")
    driver = load_driver(registered_folder(name, installed[name]))
    return driver, dict(driver.CONNECTION)


def registered_folder(name: str, where: str) -> str:
    """The folder ``name`` was registered from; refuses an entry an older controller wrote.

    An older controller kept the path of a settings file; such an entry is
    registered again from the driver's folder.
    """
    if not Path(where).is_dir():
        raise ValueError(
            f"{name!r} was registered from {where}, which is not a driver's folder; "
            "register the driver's folder again"
        )
    return where


def driver_folder(where: str | Path) -> Path:
    """The driver's folder ``where`` names, the one holding ``zmart_controller_plugin/``.

    Raises ``ValueError`` that says where the plugin belongs, for a file, for
    the plugin folder itself, or for a folder without one.
    """
    folder = Path(where).resolve()
    rule = f"a driver is given by the driver's folder, the one that holds {PLUGIN_FOLDER}/"
    if folder.is_file():
        raise ValueError(f"{rule}; {folder} is a file")
    if folder.name == PLUGIN_FOLDER:
        raise ValueError(f"{rule}; {folder} is the plugin folder itself, give {folder.parent}")
    if not (folder / PLUGIN_FOLDER).is_dir():
        raise ValueError(f"{rule}; {folder} has no {PLUGIN_FOLDER}/ folder")
    return folder


def load_driver(where: str | Path) -> SimpleNamespace:
    """The driver in the folder ``where``, ready to hand to the controller.

    Reads the name and the connection from ``zmart_controller_plugin.json``
    and imports ``zmart_controller_plugin.py``, which must hold a
    ``ZmartControllerPlugin`` class. Returns an object with ``NAME``,
    ``CONNECTION`` and ``ZmartControllerPlugin``. Raises ``ValueError``
    naming what is missing.
    """
    folder = driver_folder(where)
    settings_file = folder / PLUGIN_FOLDER / SETTINGS_FILE
    if not settings_file.is_file():
        raise ValueError(
            f"the driver's settings are in {SETTINGS_FILE}; {settings_file} is missing"
        )
    settings = json.loads(settings_file.read_text())
    extra = sorted(set(settings) - set(SETTINGS_KEYS))
    if extra:
        raise ValueError(f"{settings_file} holds only 'name' and 'connection', not {extra}")
    name = settings.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f'{settings_file} must give the driver\'s "name"')
    connection = dict(settings.get("connection") or {})
    for key, value in connection.items():
        if value is not None and any(word in key.lower() for word in SECRET_WORDS):
            raise ValueError(f"{settings_file}: {key!r} must be null; it is typed when connecting")
    plugin_file = folder / PLUGIN_FOLDER / PLUGIN_FILE
    if not plugin_file.is_file():
        raise ValueError(f"the driver's plugin is {PLUGIN_FILE}; {plugin_file} is missing")
    found = getattr(import_plugin(folder), PLUGIN_CLASS, None)
    if not isinstance(found, type):
        raise ValueError(f"{plugin_file} must hold a {PLUGIN_CLASS} class")
    return SimpleNamespace(
        __name__=name,
        NAME=name,
        CONNECTION=connection,
        ZmartControllerPlugin=found,
    )


def plugin_class(driver: Any) -> type:
    """The ``ZmartControllerPlugin`` class of ``driver``: the class itself, or the one it holds.

    Raises ``ValueError`` for anything else, such as a module of functions.
    """
    found = driver if isinstance(driver, type) else getattr(driver, PLUGIN_CLASS, None)
    if not isinstance(found, type):
        raise ValueError(
            f"{driver_name(driver)} is not a driver the controller can use: a driver's plugin "
            f"is a {PLUGIN_CLASS} class, in {PLUGIN_FOLDER}/{PLUGIN_FILE}"
        )
    return found


def driver_name(driver: Any) -> str:
    """A short name for ``driver``, to show in messages."""
    return getattr(driver, "__name__", None) or type(driver).__name__


def import_plugin(folder: Path):
    """Import the plugin of the driver in ``folder`` as part of the driver, so it can use its code.

    The plugin folder needs no ``__init__.py``. A driver that is a package
    is imported as one, with the plugin as its ``zmart_controller_plugin``
    part, so the plugin's relative imports reach the driver's code; a copy
    of the same package imported earlier from another place is forgotten
    first, so the driver registered last is the one that runs. A driver in a
    plain folder has its plugin imported by path, with the driver's folder
    importable, so the plugin can import the driver's modules by name.
    """
    importlib.invalidate_caches()
    stem = Path(PLUGIN_FILE).stem
    if (folder / "__init__.py").is_file():
        parts, top = [folder.name], folder.parent
        while (top / "__init__.py").is_file():
            parts.insert(0, top.name)
            top = top.parent
        forget_a_copy_from_elsewhere(parts[0], top)
        if str(top) not in sys.path:
            sys.path.insert(0, str(top))
        return importlib.import_module(".".join([*parts, PLUGIN_FOLDER, stem]))
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    plugin_file = folder / PLUGIN_FOLDER / PLUGIN_FILE
    name = "zmart_controller_plugin_" + "".join(c if c.isalnum() else "_" for c in str(plugin_file))
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, plugin_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        try:
            spec.loader.exec_module(module)
        except BaseException:
            del sys.modules[name]  # so a fixed file is read again next time
            raise
    return sys.modules[name]


def forget_a_copy_from_elsewhere(package: str, top: Path) -> None:
    """Forget ``package`` and its parts when they were imported from somewhere other than ``top``.

    The package then comes from ``top``, which goes first on ``sys.path``.
    """
    loaded = sys.modules.get(package)
    if loaded is None:
        return
    places = [Path(place).resolve() for place in getattr(loaded, "__path__", [])]
    if places and all(place.parent == top.resolve() for place in places):
        return
    for name in [name for name in sys.modules if name == package or name.startswith(package + ".")]:
        del sys.modules[name]
    if str(top) in sys.path:
        sys.path.remove(str(top))
    sys.path.insert(0, str(top))
