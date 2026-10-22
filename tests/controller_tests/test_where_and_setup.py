"""What a microscope still needs set up, and what each acquisition setting starts at.

``get_info`` answers four things: the microscope in words, its set-up
items, each done or not with what to do about it, whether it chooses its
own folder, and how the connection's checks went (``connection_status``). Where the microscope saves is one of the set-up items, in words:
the workflow decides where its own runs go.
Each acquisition setting says its ``default`` beside its ``active`` value.
"""

from __future__ import annotations

import pytest

from zmart_controller import ZmartController, validate_driver
from zmart_controller.template.zmart_controller_plugin.zmart_controller_plugin import (
    ZmartControllerPlugin,
)


class Scope(ZmartControllerPlugin):
    """A driver that lives in memory; ``info`` and ``settings`` are what it answers."""

    info = (
        "A scope in memory. +z points up.",
        {"limits": {"done": True, "says": "published"}},
        False,
        {"stage": "found, at x 0 y 0 z 0 um", "limits": "pending"},
    )
    settings = {"trigger": {"options": ["snap", "full"], "default": "snap", "active": "snap"}}
    observed = {"image_size_px": [512, 256], "pixel_size_um": [0.5, 0.5]}

    def __init__(self, connection):
        pass

    def disconnect(self):
        pass

    def get_info(self):
        return True, self.info

    def get_actuators(self):
        return True, tuple({"options": ["motor"], "default": "motor"} for _ in "xyz")

    def get_xyz(self, with_actuators):
        return True, (
            0.0,
            0.0,
            0.0,
            {"x": {"motor": 0.0}, "y": {"motor": 0.0}, "z": {"motor": 0.0}},
            (-10.0, 10.0, -10.0, 10.0, -1.0, 1.0),
        )

    def get_state(self):
        return True, ({}, self.observed)

    def get_acquisition_settings(self):
        return True, self.settings

    def get_procedures(self):
        return True, {}


def scope(**answers):
    return type("Answering", (Scope,), answers)


def test_get_info_says_what_is_set_up():
    session = ZmartController(Scope, {})

    content = session.get_info()["output"]

    assert content == {
        "description": "A scope in memory. +z points up.",
        "setup": {"limits": {"done": True, "says": "published"}},
        "chooses_its_own_folder": False,
        "connection_status": {"stage": "found, at x 0 y 0 z 0 um", "limits": "pending"},
    }
    assert validate_driver(Scope, {}) == []


def test_the_connections_checks_keep_their_order():
    """A client shows one row per check, in the driver's order."""
    checks = {"driver": "loaded", "stage": "pending", "saving": "failed: no disk D:"}
    driver = scope(info=("A scope in memory. +z points up.", {}, False, checks))

    content = ZmartController(driver, {}).get_info()["output"]

    assert list(content["connection_status"].items()) == list(checks.items())
    assert validate_driver(driver, {}) == []


def test_a_scope_not_yet_told_where_to_save_says_so_and_how():
    driver = scope(
        info=(
            "A scope in memory. +z points up.",
            {"data_location": {"done": False, "says": "run set_data_location.ipynb once"}},
            False,
            {},
        )
    )

    content = ZmartController(driver, {}).get_info()["output"]

    assert content["setup"]["data_location"] == {
        "done": False,
        "says": "run set_data_location.ipynb once",
    }
    assert validate_driver(driver, {}) == []


@pytest.mark.parametrize(
    ("info", "says"),
    [
        (("A scope. +z up.", ["limits"], False, {}), "setup"),
        (("A scope. +z up.", {"limits": {"done": "yes", "says": "x"}}, False, {}), "done"),
        (("A scope. +z up.", {"limits": {"done": False, "says": ""}}, False, {}), "what to do"),
        (("A scope. +z up.", {}, False, ["stage"]), "connection_status"),
        (("A scope. +z up.", {}, False, {"stage": 3}), "connection_status"),
        (("A scope. +z up.", {}, False, {"stage": ""}), "connection_status"),
    ],
)
def test_a_wrong_answer_is_named(info, says):
    problems = validate_driver(scope(info=info), {})

    assert any(says in problem for problem in problems), problems


def test_the_state_says_the_image_size_and_pixel_size_of_its_settings():
    """Before anything is captured, a workflow can plan: how many pixels, and how large each is."""
    observed = ZmartController(Scope, {}).get_state()["output"]["observed"]

    assert (observed["image_size_px"], observed["pixel_size_um"]) == ([512, 256], [0.5, 0.5])
    assert validate_driver(Scope, {}) == []


@pytest.mark.parametrize(
    "observed",
    [
        {},
        {"image_size_px": [512, 256]},
        {"image_size_px": [512], "pixel_size_um": [0.5, 0.5]},
        {"image_size_px": [512, 0], "pixel_size_um": [0.5, 0.5]},
        {"image_size_px": [512.5, 256], "pixel_size_um": [0.5, 0.5]},
        {"image_size_px": [512, 256], "pixel_size_um": [0.5, -1.0]},
        {"image_size_px": [512, 256], "pixel_size_um": [True, 0.5]},
    ],
)
def test_an_image_size_or_pixel_size_missing_or_wrong_is_named(observed):
    problems = validate_driver(scope(observed=observed), {})

    assert any("image_size_px" in problem for problem in problems), problems


def test_a_default_may_differ_from_the_active_value():
    driver = scope(
        settings={"trigger": {"options": ["snap", "full"], "default": "snap", "active": "full"}}
    )

    content = ZmartController(driver, {}).get_acquisition_settings()["output"]

    assert content["trigger"] == {"options": ["snap", "full"], "default": "snap", "active": "full"}
    assert validate_driver(driver, {}) == []
