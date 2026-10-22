"""One kind of driver: a ``ZmartControllerPlugin`` class, asked by name, answered with ``output``.

Every driver is a class. The controller asks it for the values, handing every
value over by name, and writes every answer itself as
``{"success": ..., "output": ...}``, so the same call behaves the same on every
microscope. ``acquire`` takes ``position_label``, ``acquisition_type``,
``output_folder`` and ``acquisition_settings``, in that order.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import inspect
import types

import pytest

from zmart_controller import ZmartController, validate_driver
from zmart_controller.template.zmart_controller_plugin.zmart_controller_plugin import (
    ZmartControllerPlugin,
)
from zmart_controller.zmart_controller import COMMANDS

AXIS = {"options": ["motoric"], "default": "motoric"}
READING = (1.0, 2.0, 3.0, {"x": {"motoric": 1.0}, "y": {"motoric": 2.0}, "z": {"motoric": 3.0}})
CANVAS = (-10.0, 10.0, -10.0, 10.0, -5.0, 5.0)


class KeywordOnly(ZmartControllerPlugin):
    """A plugin whose methods take every value by name only, and remember what they were given."""

    def __init__(self, connection):
        self.asked = {}

    def disconnect(self):
        pass

    def get_info(self):
        return True, ("A scope in memory. +z points up.", {}, False, {})

    def get_actuators(self):
        return True, (AXIS, AXIS, AXIS)

    def get_xyz(self, *, with_actuators):
        self.asked["get_xyz"] = {"with_actuators": with_actuators}
        return True, (*READING, CANVAS)

    def set_xyz(self, *, z, y, x, with_actuators):
        self.asked["set_xyz"] = {"x": x, "y": y, "z": z, "with_actuators": with_actuators}
        return True, (*READING, CANVAS)

    def get_state(self):
        return True, (
            {"exposure_ms": 10.0},
            {"frame": {"size_px": [512, 512], "pixel_size_um": [1.0, 1.0]}},
        )

    def set_state(self, *, changeable):
        self.asked["set_state"] = {"changeable": changeable}
        return True, dict(changeable)

    def get_acquisition_settings(self):
        return True, {"trigger": {"options": ["snap"], "default": "snap", "active": "snap"}}

    def acquire(self, *, acquisition_settings, output_folder, acquisition_type, position_label):
        self.asked["acquire"] = {
            "position_label": position_label,
            "acquisition_type": acquisition_type,
            "output_folder": output_folder,
            "acquisition_settings": acquisition_settings,
        }
        return True, ([], [])

    def get_procedures(self):
        return True, {"autofocus": {"description": "Finds the focus."}}

    def run_procedure(self, *, procedure):
        self.asked["run_procedure"] = {"procedure": procedure}
        return True, procedure["name"]


@pytest.fixture
def session():
    scope = ZmartController(KeywordOnly, {})
    yield scope
    scope.disconnect()


class TestTheAnswer:
    def test_every_answer_has_success_and_output(self, session):
        answers = {
            "get_info": session.get_info(),
            "get_actuators": session.get_actuators(),
            "get_xyz": session.get_xyz(),
            "set_xyz": session.set_xyz(1, 2, 3),
            "get_state": session.get_state(),
            "set_state": session.set_state({"changeable": {"exposure_ms": 20.0}}),
            "get_acquisition_settings": session.get_acquisition_settings(),
            "acquire": session.acquire("A1"),
            "get_procedures": session.get_procedures(),
            "run_procedure": session.run_procedure({"name": "autofocus"}),
        }
        for command, answer in answers.items():
            assert set(answer) == {"success", "output"}, command
            assert answer["success"] is True, (command, answer["output"])

    def test_a_failure_says_why_under_output(self, session):
        answer = session.set_xyz(0, 0, 0, with_actuators={"w": "motoric"})
        assert answer == {
            "success": False,
            "output": "ValueError: there is no axis 'w'; the axes are 'x', 'y' and 'z'",
        }


class TestAcquireOrder:
    def test_settings_come_last(self):
        parameters = list(inspect.signature(ZmartController.acquire).parameters)
        assert parameters == [
            "self",
            "position_label",
            "acquisition_type",
            "output_folder",
            "acquisition_settings",
        ]

    def test_the_template_takes_them_in_the_same_order(self):
        parameters = list(inspect.signature(ZmartControllerPlugin.acquire).parameters)
        assert parameters == [
            "self",
            "position_label",
            "acquisition_type",
            "output_folder",
            "acquisition_settings",
        ]

    def test_given_in_order_each_value_reaches_its_parameter(self, session):
        session.acquire("A1", "overview", "D:/run 1", {"trigger": "snap"})
        assert session.plugin.asked["acquire"] == {
            "position_label": "A1",
            "acquisition_type": "overview",
            "output_folder": "D:/run 1",
            "acquisition_settings": {"trigger": "snap"},
        }


class TestAskedByName:
    """The plugin above takes every value by name only, in its own order; nothing is mixed up."""

    def test_every_value_reaches_the_plugin_by_name(self, session):
        session.set_xyz(4, 5, 6, with_actuators={"z": "motoric"})
        session.set_state({"changeable": {"exposure_ms": 20.0}})
        session.acquire(position_label="B2", acquisition_settings={"trigger": "snap"})
        session.run_procedure({"name": "autofocus"})
        motors = {"x": "motoric", "y": "motoric", "z": "motoric"}
        assert session.plugin.asked == {
            "set_xyz": {"x": 4, "y": 5, "z": 6, "with_actuators": motors},
            "set_state": {"changeable": {"exposure_ms": 20.0}},
            "acquire": {
                "position_label": "B2",
                "acquisition_type": "acquisition",
                "output_folder": None,
                "acquisition_settings": {"trigger": "snap"},
            },
            "run_procedure": {"procedure": {"name": "autofocus"}},
        }

    def test_validate_driver_names_a_parameter_the_controller_cannot_hand_over(self):
        class WrongName(KeywordOnly):
            def acquire(self, label, acquisition_type, output_folder, acquisition_settings):
                return True, ([], [])

        problems = validate_driver(WrongName, {})
        assert any("acquire" in problem and "position_label" in problem for problem in problems)

    def test_validate_driver_accepts_any_order(self):
        assert validate_driver(KeywordOnly, {}) == []


class TestOnlyClasses:
    def test_a_module_of_functions_is_refused(self):
        functions = types.ModuleType("functions")
        for command in COMMANDS:
            setattr(functions, command, lambda *args, **kwargs: None)
        functions.connect = lambda connection: None
        with pytest.raises(ValueError, match="ZmartControllerPlugin"):
            ZmartController(functions, {})

    def test_a_module_that_holds_the_class_is_accepted(self):
        holder = types.ModuleType("holder")
        holder.ZmartControllerPlugin = KeywordOnly
        scope = ZmartController(holder, {})
        assert scope.get_info()["success"] is True
        scope.disconnect()


class TestTheSameOnEveryDriver:
    """Every command, called by position and by name, on the mock and on a class in memory."""

    CALLS = {
        "get_info": ((), {}),
        "get_actuators": ((), {}),
        "get_xyz": ((), {"with_actuators": {"z": "motoric"}}),
        "set_xyz": ((0, 0, 0), {}),
        "get_state": ((), {}),
        "get_acquisition_settings": ((), {}),
        "acquire": (("A1", "overview"), {}),
        "get_procedures": ((), {}),
    }

    @pytest.mark.parametrize("command", sorted(CALLS))
    def test_by_position_and_by_name(self, command, mock, tmp_path):
        args, kwargs = self.CALLS[command]
        names = [p for p in inspect.signature(getattr(ZmartController, command)).parameters][1:]
        by_name = {**dict(zip(names, args, strict=False)), **kwargs}
        for driver, connection in ((mock, {"mock_timing": "instant"}), (KeywordOnly, {})):
            scope = ZmartController(driver, connection)
            try:
                positional = getattr(scope, command)(*args, **kwargs)
                named = getattr(scope, command)(**by_name)
            finally:
                scope.disconnect()
            assert positional["success"] is True, (driver, positional["output"])
            assert named["success"] is True, (driver, named["output"])
            assert set(positional) == set(named) == {"success", "output"}
