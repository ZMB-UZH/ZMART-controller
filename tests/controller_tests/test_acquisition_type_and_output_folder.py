"""The two parameters that organise a run: what kind of acquisition it is, and where it goes.

``acquire(position_label, acquisition_type=None, output_folder=None,
acquisition_settings=None)``. ``acquisition_type`` (for example ``"overview"``) goes
into the driver's file names and metadata and comes back in the answer; left
out, it is ``"acquisition"``. ``output_folder`` is where the files go when
the microscope's software lets the driver choose; a driver whose software
always saves to its own place says so in ``get_info``
(``chooses_its_own_folder``) and reports the real paths. Nothing is refused
for that.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from zmart_controller import ZmartController, check_acquire_answer, validate_driver
from zmart_controller.template.zmart_controller_plugin.zmart_controller_plugin import (
    ZmartControllerPlugin,
)
from zmart_controller.zmart_controller import DEFAULT_ACQUISITION_TYPE


class Scope(ZmartControllerPlugin):
    """A driver in memory that saves where it is asked and remembers what acquire was given."""

    own_folder: Path  # where it saves when no output_folder is given; set by each test
    chooses_its_own_folder = False

    def __init__(self, connection):
        self.asked = []

    def disconnect(self):
        pass

    def get_info(self):
        return True, ("A scope in memory. +z points up.", {}, self.chooses_its_own_folder)

    def get_actuators(self):
        motor = {"options": ["motoric"], "default": "motoric"}
        return True, (motor, motor, motor)

    def get_xyz(self, with_actuators):
        readings = {axis: {"motoric": 0.0} for axis in ("x", "y", "z")}
        return True, (0.0, 0.0, 0.0, readings, (-10.0, 10.0, -10.0, 10.0, -1.0, 1.0))

    def get_state(self):
        return True, ({}, {})

    def get_acquisition_settings(self):
        return True, {"trigger": {"options": ["snap"], "default": "snap", "active": "snap"}}

    def acquire(self, position_label, acquisition_type, output_folder, acquisition_settings):
        self.asked.append((position_label, acquisition_type, output_folder, acquisition_settings))
        folder = self.own_folder if self.chooses_its_own_folder or output_folder is None else None
        folder = Path(folder or output_folder)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{acquisition_type}_{position_label}.json"
        path.write_text("{}")
        plane = {"path": str(path), "c": 0, "z": 0, "t": 0, "x_um": 0.0, "y_um": 0.0, "z_um": 0.0}
        return True, ([str(path)], [plane])

    def get_procedures(self):
        return True, {}


@pytest.fixture
def scope(tmp_path):
    Scope.own_folder = tmp_path / "its own place"
    return Scope


# ---- the controller hands both to the driver


def test_both_reach_the_driver_and_the_answer_says_the_type(scope, tmp_path):
    session = ZmartController(scope, {})

    answer = session.acquire(
        "A1", acquisition_type="overview", output_folder=str(tmp_path / "run 1")
    )

    assert session.plugin.asked == [("A1", "overview", str(tmp_path / "run 1"), None)]
    assert answer["success"] is True
    assert answer["output"]["position_label"] == "A1"
    assert answer["output"]["acquisition_type"] == "overview"
    assert answer["output"]["files"] == [str(tmp_path / "run 1" / "overview_A1.json")]


def test_left_out_the_type_is_the_default_and_the_folder_is_the_drivers(scope):
    session = ZmartController(scope, {})

    answer = session.acquire("A1")

    assert DEFAULT_ACQUISITION_TYPE == "acquisition"
    assert session.plugin.asked == [("A1", "acquisition", None, None)]
    assert answer["output"]["acquisition_type"] == "acquisition"


def test_a_folder_given_as_a_path_reaches_the_driver_as_text(scope, tmp_path):
    session = ZmartController(scope, {})

    session.acquire("A1", output_folder=tmp_path / "run 2")

    assert session.plugin.asked[0][2] == str(tmp_path / "run 2")


@pytest.mark.parametrize(
    ("asked", "says"),
    [
        ({"acquisition_type": ""}, "acquisition_type must be a word"),
        ({"acquisition_type": 3}, "acquisition_type must be a word"),
        ({"output_folder": 3}, "output_folder must be a folder"),
    ],
)
def test_a_type_or_folder_that_is_not_one_is_refused_before_the_driver_is_asked(scope, asked, says):
    session = ZmartController(scope, {})

    answer = session.acquire("A1", **asked)

    assert answer["success"] is False
    assert says in answer["output"]
    assert session.plugin.asked == []


def test_get_info_says_whether_the_driver_chooses_its_own_folder(scope):
    assert ZmartController(scope, {}).get_info()["output"]["chooses_its_own_folder"] is False


# ---- the validator


def test_a_driver_that_takes_both_fits(scope):
    assert validate_driver(scope, {}) == []


def test_a_driver_whose_acquire_takes_neither_is_named(scope):
    def acquire(self, position_label, acquisition_settings):
        raise AssertionError("validate_driver never acquires")

    old = type("Old", (scope,), {"acquire": acquire})

    assert validate_driver(old, {}) == [
        "acquire must take position_label, acquisition_type, output_folder, "
        "acquisition_settings, by these names; it does not take acquisition_type, output_folder"
    ]


def test_a_driver_that_does_not_say_whether_it_chooses_its_folder_is_named(scope):
    def get_info(self):
        return True, ("A scope in memory. +z points up.", {}, "sometimes")

    vague = type("Vague", (scope,), {"get_info": get_info})

    assert validate_driver(vague, {}) == [
        "get_info: chooses_its_own_folder must be True or False: whether acquire saves "
        "anywhere but in the output_folder it is given"
    ]


def test_an_answer_must_say_its_acquisition_type(tmp_path):
    saved = tmp_path / "A1.json"
    saved.write_text("{}")
    plane = {"path": str(saved), "c": 0, "z": 0, "t": 0, "x_um": 0.0, "y_um": 0.0, "z_um": 0.0}
    answer = {
        "success": True,
        "output": {"position_label": "A1", "files": [str(saved)], "planes": [plane]},
    }

    assert check_acquire_answer(answer) == [
        "acquire: the output must contain acquisition_type, the kind of acquisition it was"
    ]


def test_files_outside_the_output_folder_are_named(scope, tmp_path):
    scope.chooses_its_own_folder = True  # it saves in its own place, but does not say so
    session = ZmartController(scope, {})
    answer = session.acquire("A1", output_folder=str(tmp_path / "run"))

    problems = check_acquire_answer(answer, output_folder=str(tmp_path / "run"))

    assert problems == [
        f"acquire: files names {tmp_path / 'its own place' / 'acquisition_A1.json'}, which is "
        f"not in the output_folder {tmp_path / 'run'} it was given; a driver whose software "
        "saves in its own place says so in get_info (chooses_its_own_folder)"
    ]


def test_a_driver_that_chooses_its_own_folder_fits_with_the_real_paths(scope, tmp_path):
    scope.chooses_its_own_folder = True
    session = ZmartController(scope, {})
    answer = session.acquire("A1", output_folder=str(tmp_path / "run"))

    assert Path(answer["output"]["files"][0]).parent == tmp_path / "its own place"
    assert (
        check_acquire_answer(
            answer, output_folder=str(tmp_path / "run"), chooses_its_own_folder=True
        )
        == []
    )


def test_a_driver_that_chooses_its_own_folder_still_reports_files_that_exist(tmp_path):
    plane = {"path": "nowhere.json", "c": 0, "z": 0, "t": 0, "x_um": 0.0, "y_um": 0.0, "z_um": 0.0}
    answer = {
        "success": True,
        "output": {
            "position_label": "A1",
            "acquisition_type": "overview",
            "files": ["nowhere.json"],
            "planes": [plane],
        },
    }

    problems = check_acquire_answer(
        answer, output_folder=str(tmp_path), chooses_its_own_folder=True
    )

    assert problems == ["acquire: files names nowhere.json, which does not exist"]


# ---- the mock: its software lets it choose, so it saves where it is asked


def test_the_mock_saves_in_the_output_folder_under_the_type(mock, tmp_path):
    session = ZmartController(mock, {"output_root": str(tmp_path / "images")})
    try:
        info = session.get_info()["output"]
        answer = session.acquire(
            position_label="A1", acquisition_type="overview", output_folder=str(tmp_path / "run")
        )
    finally:
        session.disconnect()

    assert info["chooses_its_own_folder"] is False
    output = answer["output"]
    assert output["acquisition_type"] == "overview"
    assert [Path(f).name for f in output["files"]] == [
        "overview_A1.ome.tif",
        "overview_A1.commands.json",
    ]
    assert all(Path(f).parent == tmp_path / "run" for f in output["files"])
    assert check_acquire_answer(answer, output_folder=str(tmp_path / "run")) == []


def test_the_mock_records_the_type_in_the_store(mock, tmp_path):
    session = ZmartController(mock, {"output_root": str(tmp_path), "format": "ome-zarr"})
    try:
        answer = session.acquire(position_label="A1", acquisition_type="targets")
    finally:
        session.disconnect()

    store = Path(answer["output"]["files"][0])
    assert store.name == "targets_A1.ome.zarr"
    assert store.parent == tmp_path
    zmart = json.loads((store / "zarr.json").read_text())["attributes"]["zmart"]
    assert zmart["acquisition_type"] == "targets"


def test_the_mock_names_the_default_type_when_none_is_given(mock, tmp_path):
    session = ZmartController(mock, {"output_root": str(tmp_path)})
    try:
        output = session.acquire(position_label="A1")["output"]
    finally:
        session.disconnect()

    assert output["acquisition_type"] == "acquisition"
    assert Path(output["files"][0]).name == "acquisition_A1.ome.tif"
