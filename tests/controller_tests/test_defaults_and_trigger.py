"""The defaults a driver names, and acquisition settings that say how to trigger.

The driver decides every default and the answers say it: ``get_actuators``
names the default motor per axis, ``get_xyz`` and ``set_xyz`` both use it
for an axis the caller leaves out and say which motor they used, and every
acquisition setting carries a ``default``. ``get_info`` answers the
description and the set-up items; where a microscope saves is a set-up item.
"""

from __future__ import annotations

import pytest

from zmart_controller import ZmartController, validate_driver
from zmart_controller.template.zmart_driver import ZmartDriver

ACTUATORS = (
    {"options": ["motoric"], "default": "motoric"},
    {"options": ["motoric"], "default": "motoric"},
    {"options": ["motoric", "piezo"], "default": "motoric"},
)


class Scope(ZmartDriver):
    """A driver in memory that remembers which motors each move was asked to use."""

    actuators = ACTUATORS
    settings = {"trigger": {"options": ["snap", "full"], "default": "snap", "active": "snap"}}
    info = (
        "A scope in memory. +z points up.",
        {"saving": {"done": True, "says": "OME-TIFF under D:/data"}},
    )

    def __init__(self, connection):
        self.asked = []

    def disconnect(self):
        pass

    def get_info(self):
        return True, self.info

    def get_actuators(self):
        return True, self.actuators

    def get_xyz(self, with_actuators):
        self.asked.append(with_actuators)
        readings = {
            "x": {"motoric": 0.0},
            "y": {"motoric": 0.0},
            "z": {"motoric": 0.0, "piezo": 0.0},
        }
        return True, (0.0, 0.0, 0.0, readings, (-10.0, 10.0, -10.0, 10.0, -1.0, 1.0))

    def set_xyz(self, x, y, z, with_actuators):
        return self.get_xyz(with_actuators)

    def get_state(self):
        return True, ({}, {})

    def get_acquisition_settings(self):
        return True, self.settings

    def get_procedures(self):
        return True, {}


def scope(**answers):
    return type("Answering", (Scope,), answers)


# ---- the default actuator


def test_get_actuators_names_the_default_per_axis():
    content = ZmartController(Scope, {}).get_actuators()["content"]

    assert content == {
        "x": {"options": ["motoric"], "default": "motoric"},
        "y": {"options": ["motoric"], "default": "motoric"},
        "z": {"options": ["motoric", "piezo"], "default": "motoric"},
    }


def test_the_driver_decides_the_default_not_the_list_order():
    piezo_first = scope(
        actuators=(
            ACTUATORS[0],
            ACTUATORS[1],
            {"options": ["motoric", "piezo"], "default": "piezo"},
        )
    )
    session = ZmartController(piezo_first, {})

    answer = session.get_xyz()["content"]

    assert answer["z"]["actuator"] == "piezo"
    assert session._handle.asked == [{"x": "motoric", "y": "motoric", "z": "piezo"}]


@pytest.mark.parametrize("command", ["get_xyz", "set_xyz"])
def test_get_and_set_use_the_same_default_and_say_which_motor(command):
    session = ZmartController(Scope, {})
    call = getattr(session, command)

    answer = call() if command == "get_xyz" else call(1.0, 2.0, 0.0)

    assert {axis: reading["actuator"] for axis, reading in answer["content"].items()} == {
        "x": "motoric",
        "y": "motoric",
        "z": "motoric",
    }
    assert session._handle.asked == [{"x": "motoric", "y": "motoric", "z": "motoric"}]


def test_a_chosen_motor_replaces_the_default_for_that_axis_only():
    session = ZmartController(Scope, {})

    answer = session.set_xyz(0.0, 0.0, 5.0, with_actuators={"z": "piezo"})["content"]

    assert answer["z"]["actuator"] == "piezo"
    assert answer["x"]["actuator"] == "motoric"
    assert session._handle.asked == [{"x": "motoric", "y": "motoric", "z": "piezo"}]


@pytest.mark.parametrize(
    ("chosen", "says"),
    [
        ({"z": "hovercraft"}, "'hovercraft' is not an actuator of axis 'z'"),
        ({"w": "motoric"}, "no axis 'w'"),
    ],
)
def test_an_unknown_motor_is_refused_before_the_driver_is_asked(chosen, says):
    session = ZmartController(Scope, {})

    answer = session.set_xyz(0.0, 0.0, 0.0, with_actuators=chosen)

    assert answer["success"] is False
    assert says in answer["content"]
    assert session._handle.asked == []


# ---- get_info: the description and what is set up


def test_get_info_answers_the_description_and_the_setup():
    content = ZmartController(Scope, {}).get_info()["content"]

    assert content == {
        "description": "A scope in memory. +z points up.",
        "setup": {"saving": {"done": True, "says": "OME-TIFF under D:/data"}},
    }


# ---- the validator


def test_a_scope_that_names_every_default_fits():
    assert validate_driver(Scope, {}) == []


@pytest.mark.parametrize(
    ("actuators", "says"),
    [
        ((["motoric"], ["motoric"], ["motoric"]), "get_actuators: axis 'x' must be"),
        (
            (ACTUATORS[0], ACTUATORS[1], {"options": ["motoric", "piezo"]}),
            "get_actuators: axis 'z' must name its default",
        ),
        (
            (ACTUATORS[0], ACTUATORS[1], {"options": ["motoric"], "default": "piezo"}),
            "not one of its options",
        ),
        ((ACTUATORS[0], ACTUATORS[1], {"options": [], "default": "motoric"}), "at least one"),
    ],
)
def test_a_wrong_actuator_answer_is_named(actuators, says):
    problems = validate_driver(scope(actuators=actuators), {})

    assert any(says in problem for problem in problems), problems


@pytest.mark.parametrize(
    ("settings", "says"),
    [
        (
            {"trigger": {"options": ["snap"], "active": "snap"}},
            '\'trigger\' must have "options", "default" and "active"',
        ),
        ({"trigger": {"options": ["snap"], "default": "full", "active": "snap"}}, "default 'full'"),
        (
            {"trigger": {"options": ["snap"], "default": "snap", "active": "burst"}},
            "active 'burst'",
        ),
    ],
)
def test_a_setting_without_a_proper_default_is_named(settings, says):
    problems = validate_driver(scope(settings=settings), {})

    assert any(says in problem for problem in problems), problems


def test_a_setting_described_in_words_still_names_a_default():
    driver = scope(
        settings={
            "trigger": {
                "options": "snap, or a hardware pulse on line 3",
                "default": "snap",
                "active": "snap",
            }
        }
    )

    assert validate_driver(driver, {}) == []
