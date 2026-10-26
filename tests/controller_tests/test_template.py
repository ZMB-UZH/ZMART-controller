from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

import zmart_controller
from zmart_controller import check_acquire_answer, validate_driver
from zmart_controller import zmart_controller as controller
from zmart_controller.template.zmart_controller_plugin.zmart_controller_plugin import (
    ZmartControllerPlugin,
)

README = Path(__file__).parents[2] / "docs" / "plug_in_a_driver" / "README.md"
TEMPLATE = Path(zmart_controller.template.__file__).parent / "zmart_controller_plugin"


class PretendDriver(ZmartControllerPlugin):
    folder: Path

    def __init__(self, connection):
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.exposure_ms = 10.0

    def disconnect(self):
        pass

    def get_info(self):
        return True, ("A pretend microscope. +z points up.", {}, False, {})

    def get_actuators(self):
        return True, (
            {"options": ["motor"], "default": "motor"},
            {"options": ["motor"], "default": "motor"},
            {"options": ["motor", "piezo"], "default": "motor"},
        )

    def get_xyz(self, with_actuators):
        p = self.position
        actuators = {
            "x": {"motor": p["x"]},
            "y": {"motor": p["y"]},
            "z": {"motor": p["z"], "piezo": 0.0},
        }
        canvas = (-1050.0, 1050.0, -1050.0, 1050.0, -100.0, 100.0)
        return True, (p["x"], p["y"], p["z"], actuators, canvas)

    def set_xyz(self, x, y, z, with_actuators):
        self.position = {"x": x, "y": y, "z": z}
        return self.get_xyz(with_actuators)

    def get_state(self):
        return True, (
            {"exposure_ms": self.exposure_ms},
            {"objective": "10x", "image_size_px": [512, 512], "pixel_size_um": [1.0, 1.0]},
        )

    def set_state(self, changeable):
        if changeable.get("exposure_ms") == 999.0:
            return False, "exposure_ms stayed 10.0"
        if changeable.get("exposure_ms") == -1.0:
            raise ValueError("exposure_ms must be positive")
        self.exposure_ms = changeable.get("exposure_ms", self.exposure_ms)
        return True, dict(changeable)

    def get_acquisition_settings(self):
        return True, {"trigger": {"options": ["snap"], "default": "snap", "active": "snap"}}

    def acquire(self, position_label, acquisition_type, output_folder, acquisition_settings):
        folder = Path(output_folder) if output_folder is not None else self.folder
        path = folder / f"{acquisition_type}_{position_label}.json"
        path.write_text(json.dumps({"position": self.position, "exposure_ms": self.exposure_ms}))
        p = self.position
        plane = {"path": str(path), "c": 0, "z": 0, "t": 0}
        plane.update(x_um=p["x"], y_um=p["y"], z_um=p["z"])
        return True, ([str(path)], [plane])

    def get_procedures(self):
        return True, {"park": {"description": "Move the stage to its parking position."}}

    def run_procedure(self, procedure):
        if procedure["name"] != "park":
            raise ValueError(f"unknown procedure {procedure['name']!r}")
        return True, procedure["name"]


def test_the_template_loads_and_offers_every_function():
    driver = zmart_controller.load_driver(TEMPLATE.parent)
    assert driver.NAME.startswith("<the name you want")
    assert set(driver.CONNECTION) == {
        "microscope",
        "api_type",
        "host",
        "client",
        "password",
        "config",
        "output_root",
    }
    assert driver.CONNECTION["password"] is None
    assert driver.ZmartControllerPlugin.__name__ == "ZmartControllerPlugin"


def test_an_unfilled_driver_says_what_is_missing():
    with pytest.raises(NotImplementedError, match="ZmartControllerPlugin.__init__"):
        validate_driver(zmart_controller.load_driver(TEMPLATE.parent))


def test_a_filled_in_driver_passes_validation_and_acquires(tmp_path):
    PretendDriver.folder = tmp_path
    driver = PretendDriver
    assert validate_driver(driver) == []
    session = zmart_controller.ZmartController(driver)
    try:
        session.set_xyz(100.0, 50.0, 0.0)
        answer = session.acquire(position_label="A1")
        assert check_acquire_answer(answer) == []
        assert session.run_procedure({"name": "park"})["output"] == {"ran": "park"}
    finally:
        session.disconnect()


def test_the_three_outcomes(tmp_path):
    PretendDriver.folder = tmp_path
    session = zmart_controller.ZmartController(PretendDriver)
    try:
        ok = session.set_state({"changeable": {"exposure_ms": 20.0}})
        assert ok == {"success": True, "output": {"applied": {"exposure_ms": 20.0}}}
        failed = session.set_state({"changeable": {"exposure_ms": 999.0}})
        assert failed == {"success": False, "output": "exposure_ms stayed 10.0"}
        raised = session.set_state({"changeable": {"exposure_ms": -1.0}})
        assert raised == {"success": False, "output": "ValueError: exposure_ms must be positive"}
    finally:
        session.disconnect()


def test_every_method_the_plugin_calls_exists_on_the_class():
    called = set(re.findall(r"\bself\.plugin\.(\w+)\(", Path(controller.__file__).read_text()))
    assert called <= {name for name in dir(ZmartControllerPlugin) if not name.startswith("_")}


def test_a_missing_class_file_is_refused(tmp_path):
    (tmp_path / "zmart_controller_plugin").mkdir()
    shutil.copy(TEMPLATE / "zmart_controller_plugin.json", tmp_path / "zmart_controller_plugin")
    with pytest.raises(ValueError, match="zmart_controller_plugin.py is missing"):
        zmart_controller.load_driver(tmp_path)


def test_a_copied_template_is_installed_from_the_drivers_folder(tmp_path):
    folder = tmp_path / "my_scope"
    shutil.copytree(TEMPLATE, folder / "zmart_controller_plugin")
    settings = folder / "zmart_controller_plugin" / "zmart_controller_plugin.json"
    filled = json.loads(settings.read_text())
    filled["name"], filled["connection"]["host"] = "my-scope-2", "127.0.0.1"
    settings.write_text(json.dumps(filled))
    try:
        assert zmart_controller.register_driver(folder) == "my-scope-2"
        assert list(zmart_controller.get_instruments()) == ["my-scope-2"]
        shown = zmart_controller.get_instruments()["my-scope-2"]
        assert shown["host"] == "127.0.0.1" and shown["password"] is None
        with pytest.raises(NotImplementedError):
            zmart_controller.ZmartController("my-scope-2")
    finally:
        zmart_controller.remove_driver("my-scope-2")


def test_the_readme_names_every_driver_method():
    text = README.read_text()
    for name in dir(ZmartControllerPlugin):
        if not name.startswith("_"):
            assert f"def {name}(self" in text, f"the driver guide does not show {name}"
