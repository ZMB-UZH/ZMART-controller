"""Tests for the two-file driver: the template to copy, and the controller that drives it.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest

import zmart_controller
from zmart_controller import check_acquire_answer, validate_driver
from zmart_controller import zmart_controller as controller
from zmart_controller.template.zmart_driver import ZmartDriver

README = Path(__file__).parents[2] / "docs" / "plug_in_a_driver" / "README.md"
TEMPLATE = Path(zmart_controller.template.__file__).parent


class PretendDriver(ZmartDriver):
    """A ZmartDriver filled in for a microscope that lives in memory."""

    folder: Path  # set by the test before connecting

    def __init__(self, connection):
        self.position = {"x": 0.0, "y": 0.0, "z": 0.0}
        self.exposure_ms = 10.0

    def disconnect(self):
        pass

    def get_info(self):
        return True, ("A pretend microscope. +z points up.", {})

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
        return True, ({"exposure_ms": self.exposure_ms}, {"objective": "10x"})

    def set_state(self, changeable):
        if changeable.get("exposure_ms") == 999.0:  # a value this pretend camera silently ignores
            return False, "exposure_ms stayed 10.0"
        if changeable.get("exposure_ms") == -1.0:
            raise ValueError("exposure_ms must be positive")
        self.exposure_ms = changeable.get("exposure_ms", self.exposure_ms)
        return True, dict(changeable)

    def get_acquisition_settings(self):
        return True, {"trigger": {"options": ["snap"], "default": "snap", "active": "snap"}}

    def acquire(self, position_label, acquisition_settings):
        path = self.folder / f"{position_label}.json"
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
    driver = zmart_controller.load_driver(TEMPLATE)
    assert driver.NAME.startswith("<the name you want")
    assert set(driver.CONNECTION) == {"microscope", "api_type", "host", "password", "config"}
    assert driver.ZmartDriver.__name__ == "ZmartDriver"


def test_an_unfilled_driver_says_what_is_missing():
    with pytest.raises(NotImplementedError, match="ZmartDriver.__init__"):
        validate_driver(zmart_controller.load_driver(TEMPLATE))


def test_a_filled_in_driver_passes_validation_and_acquires(tmp_path):
    PretendDriver.folder = tmp_path
    driver = PretendDriver
    assert validate_driver(driver) == []
    session = zmart_controller.ZmartController(driver)
    try:
        session.set_xyz(100.0, 50.0, 0.0)
        answer = session.acquire(position_label="A1")
        assert check_acquire_answer(answer) == []
        assert session.run_procedure({"name": "park"})["content"] == {"ran": "park"}
    finally:
        session.disconnect()


def test_the_three_outcomes(tmp_path):
    PretendDriver.folder = tmp_path
    session = zmart_controller.ZmartController(PretendDriver)
    try:
        ok = session.set_state({"changeable": {"exposure_ms": 20.0}})
        assert ok == {"success": True, "content": {"applied": {"exposure_ms": 20.0}}}
        failed = session.set_state({"changeable": {"exposure_ms": 999.0}})
        assert failed == {"success": False, "content": "exposure_ms stayed 10.0"}
        raised = session.set_state({"changeable": {"exposure_ms": -1.0}})
        assert raised == {"success": False, "content": "ValueError: exposure_ms must be positive"}
    finally:
        session.disconnect()


def test_every_method_the_plugin_calls_exists_on_the_class():
    called = set(re.findall(r"\bhandle\.(\w+)\(", Path(controller.__file__).read_text()))
    assert called <= {name for name in dir(ZmartDriver) if not name.startswith("_")}


def test_a_missing_class_file_is_refused(tmp_path):
    shutil.copy(TEMPLATE / "zmart_driver.json", tmp_path)
    with pytest.raises(ValueError, match="zmart_driver.py is missing"):
        zmart_controller.load_driver(tmp_path)


def test_the_json_can_point_at_a_class_file_elsewhere(tmp_path):
    (tmp_path / "code").mkdir()
    shutil.copy(TEMPLATE / "zmart_driver.py", tmp_path / "code" / "my_scope.py")
    settings = json.loads((TEMPLATE / "zmart_driver.json").read_text())
    settings["driver"] = "code/my_scope.py"
    (tmp_path / "zmart_driver.json").write_text(json.dumps(settings))
    assert zmart_controller.load_driver(tmp_path / "zmart_driver.json").NAME == settings["name"]


def test_a_copied_template_is_installed_from_its_folder_or_json(tmp_path):
    folder = tmp_path / "my_scope"
    shutil.copytree(TEMPLATE, folder)
    settings = folder / "zmart_driver.json"
    filled = json.loads(settings.read_text())
    filled["name"], filled["connection"]["host"] = "my-scope-2", "127.0.0.1"
    settings.write_text(json.dumps(filled))
    try:
        assert zmart_controller.register_driver(folder) == "my-scope-2"
        assert zmart_controller.register_driver(settings) == "my-scope-2"
        assert list(zmart_controller.get_instruments()) == ["mock", "my-scope-2"]
        shown = zmart_controller.get_instruments()["my-scope-2"]
        assert shown["host"] == "127.0.0.1" and "password" not in shown
        with pytest.raises(NotImplementedError):  # it connects through the class
            zmart_controller.ZmartController("my-scope-2")
    finally:
        zmart_controller.remove_driver("my-scope-2")


def test_the_readme_names_every_driver_method():
    """The driver guide shows each method a driver must offer, so a new or renamed
    method in the template cannot go unmentioned in the guide."""
    text = README.read_text()
    for name in dir(ZmartDriver):
        if not name.startswith("_"):
            assert f"def {name}(self" in text, f"the driver guide does not show {name}"
