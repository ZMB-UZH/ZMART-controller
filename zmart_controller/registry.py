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

PLUGIN_FOLDER = "zmart_controller_plugin"
SETTINGS_FILE = "zmart_controller_plugin.json"
PLUGIN_FILE = "zmart_controller_plugin.py"
PLUGIN_CLASS = "ZmartControllerPlugin"
SETTINGS_KEYS = ("name", "connection")
SECRET_WORDS = ("password", "token", "secret")


def config_root() -> Path:
    if os.environ.get("ZMART_MICROSCOPY_ROOT"):
        return Path(os.environ["ZMART_MICROSCOPY_ROOT"])
    if platform.system() == "Windows":
        return Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "zmart-microscopy"
    if platform.system() == "Darwin":
        return Path("/Library/Application Support/zmart-microscopy")
    return Path("/etc/zmart-microscopy")


def registry_file() -> Path:
    return config_root() / "zmart-controller" / "drivers.json"


def installed_drivers() -> dict[str, str]:
    try:
        return json.loads(registry_file().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def save_installed_drivers(installed: dict[str, str]) -> None:
    registry_file().parent.mkdir(parents=True, exist_ok=True)
    registry_file().write_text(json.dumps(installed, indent=2) + "\n", encoding="utf-8")


def get_instruments() -> dict[str, dict[str, Any]]:
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
    folder = driver_folder(where)
    driver = load_driver(folder)
    save_installed_drivers({**installed_drivers(), driver.NAME: str(folder)})
    return driver.NAME


def remove_driver(name: str) -> bool:
    installed = installed_drivers()
    if name not in installed:
        return False
    del installed[name]
    save_installed_drivers(installed)
    return True


def find_driver(name: str) -> tuple[Any, dict[str, Any]]:
    installed = installed_drivers()
    if name not in installed:
        raise ValueError(f"no driver installed as {name!r}; installed: {sorted(installed)}")
    driver = load_driver(registered_folder(name, installed[name]))
    return driver, dict(driver.CONNECTION)


def registered_folder(name: str, where: str) -> str:
    if not Path(where).is_dir():
        raise ValueError(
            f"{name!r} was registered from {where}, which is not a driver's folder; "
            "register the driver's folder again"
        )
    return where


def driver_folder(where: str | Path) -> Path:
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
    folder = driver_folder(where)
    settings_file = folder / PLUGIN_FOLDER / SETTINGS_FILE
    if not settings_file.is_file():
        raise ValueError(
            f"the driver's settings are in {SETTINGS_FILE}; {settings_file} is missing"
        )
    settings = json.loads(settings_file.read_text(encoding="utf-8"))
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
    found = driver if isinstance(driver, type) else getattr(driver, PLUGIN_CLASS, None)
    if not isinstance(found, type):
        raise ValueError(
            f"{driver_name(driver)} is not a driver the controller can use: a driver's plugin "
            f"is a {PLUGIN_CLASS} class, in {PLUGIN_FOLDER}/{PLUGIN_FILE}"
        )
    return found


def driver_name(driver: Any) -> str:
    return getattr(driver, "__name__", None) or type(driver).__name__


def import_plugin(folder: Path):
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
            del sys.modules[name]
            raise
    return sys.modules[name]


def forget_a_copy_from_elsewhere(package: str, top: Path) -> None:
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
