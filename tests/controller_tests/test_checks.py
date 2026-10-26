from __future__ import annotations

import json
from pathlib import Path

import pytest
from mock_driver.zmart_controller_plugin.zmart_controller_plugin import (
    ZmartControllerPlugin as MockPlugin,
)

from zmart_controller import ZmartController, check_acquire_answer, registry, validate_driver


class TestConfigRoot:
    def test_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(tmp_path))
        assert registry.config_root() == tmp_path

    def test_per_os_default(self, monkeypatch):
        monkeypatch.delenv("ZMART_MICROSCOPY_ROOT", raising=False)
        monkeypatch.setattr(registry.platform, "system", lambda: "Windows")
        monkeypatch.setenv("PROGRAMDATA", r"C:\ProgramData")
        assert str(registry.config_root()).endswith("zmart-microscopy")
        monkeypatch.setattr(registry.platform, "system", lambda: "Darwin")
        assert registry.config_root() == registry.Path(
            "/Library/Application Support/zmart-microscopy"
        )
        monkeypatch.setattr(registry.platform, "system", lambda: "Linux")
        assert registry.config_root() == registry.Path("/etc/zmart-microscopy")


def break_plugin(monkeypatch, name, method):
    monkeypatch.setattr(MockPlugin, name, method)


def test_the_mock_fits(mock):
    assert validate_driver(mock) == []


def xyz_with(**per_axis):
    def get_xyz(self, with_actuators):
        values = {
            axis: {
                "position": 0.0,
                "actuator_readings": {"motoric": 48_000.0},
                "canvas": [-150.0, 150.0],
            }
            for axis in ("x", "y", "z")
        }
        for axis, changed in per_axis.items():
            values[axis].update(changed)
        positions = tuple(values[axis]["position"] for axis in ("x", "y", "z"))
        readings = {axis: values[axis]["actuator_readings"] for axis in ("x", "y", "z")}
        canvas = tuple(end for axis in ("x", "y", "z") for end in values[axis]["canvas"])
        return True, (*positions, readings, canvas)

    return get_xyz


def info_with(description):
    def get_info(self):
        return True, (description, {}, False, {})

    return get_info


def test_problems_are_named(monkeypatch, mock):
    break_plugin(monkeypatch, "get_xyz", xyz_with(y={"position": "10"}))
    break_plugin(monkeypatch, "get_info", info_with(""))
    assert validate_driver(mock) == [
        "get_info: the output must contain description, text that describes the microscope",
        "get_xyz: axis 'y' position must be a number, in micrometres",
    ]


def test_the_motor_used_must_be_one_of_the_axis_readings(monkeypatch, mock):
    break_plugin(monkeypatch, "get_xyz", xyz_with(z={"actuator_readings": {"piezo": 37.0}}))
    assert validate_driver(mock) == [
        "get_xyz: axis 'z' used_actuator 'motoric' must be one of its actuator_readings, ['piezo']"
    ]


@pytest.mark.parametrize("readings", [{}, {"motoric": "48000"}, {"": 48000.0}])
def test_actuator_readings_must_name_each_motor_with_a_number(monkeypatch, mock, readings):
    break_plugin(monkeypatch, "get_xyz", xyz_with(z={"actuator_readings": readings}))
    problems = validate_driver(mock)
    assert problems[0] == (
        "get_xyz: axis 'z' actuator_readings must name every motor of the axis with its "
        "reading as a number, in micrometres"
    )


@pytest.mark.parametrize("canvas", [[-150.0, "far"], [True, 150.0], [150.0, -150.0]])
def test_a_canvas_that_is_not_min_then_max_is_reported(monkeypatch, mock, canvas):
    break_plugin(monkeypatch, "get_xyz", xyz_with(x={"canvas": canvas}))
    assert validate_driver(mock) == [
        "get_xyz: axis 'x' canvas must be [min, max] in micrometres, with min no larger than max"
    ]


@pytest.mark.parametrize("description", ["", "   ", 42, ["a microscope"]])
def test_a_description_that_says_nothing_is_reported(monkeypatch, mock, description):
    break_plugin(monkeypatch, "get_info", info_with(description))
    assert validate_driver(mock) == [
        "get_info: the output must contain description, text that describes the microscope"
    ]


def test_the_mock_describes_itself(mock):
    session = ZmartController(mock)
    try:
        description = session.get_info()["output"]["description"]
    finally:
        session.disconnect()
    assert isinstance(description, str) and len(description) > 200
    for word in ("stage", "objective", "exposure", "laser"):
        assert word in description.lower(), word
    for bounds in ("0 to 50", "0 to 800", "0.1 to 1000"):
        assert bounds in description, bounds


def acquire_on_the_mock(mock, connection=None, **stack):
    session = ZmartController(mock, connection)
    try:
        if not stack:
            return session.acquire(position_label="A1")
        session.set_state({"changeable": stack})
        return session.acquire(position_label="A1", acquisition_settings={"trigger": "full"})
    finally:
        session.disconnect()


def _answer(**content):
    base = {"position_label": "A1", "acquisition_type": "acquisition"}
    return {"success": True, "output": {**base, **content}}


def _plane(path, **entries):
    return {
        "path": str(path),
        "c": 0,
        "z": 0,
        "t": 0,
        "x_um": 100.0,
        "y_um": 50.0,
        "z_um": 3.0,
        **entries,
    }


@pytest.fixture
def saved(tmp_path):
    path = tmp_path / "A1.ome.tif"
    path.write_bytes(b"")
    return path


def test_the_mocks_acquisition_fits(mock):
    assert check_acquire_answer(acquire_on_the_mock(mock)) == []


def test_files_names_everything_the_acquisition_saved(mock):
    output = acquire_on_the_mock(mock, z_planes=2)["output"]
    names = [Path(path).name for path in output["files"]]
    assert names == [
        "acquisition_A1_z000.ome.tif",
        "acquisition_A1_z001.ome.tif",
        "acquisition_A1.commands.json",
    ]


def test_an_ome_zarr_folder_counts_as_a_saved_file(mock):
    assert check_acquire_answer(acquire_on_the_mock(mock, {"format": "ome-zarr"})) == []


def test_an_answer_without_files_is_reported():
    problems = check_acquire_answer(_answer(images=["a.tif"]))
    assert problems == [
        "acquire: the output must contain files, the list of paths of every file it saved"
    ]


def test_a_file_that_is_not_there_is_reported(tmp_path, saved):
    problems = check_acquire_answer(
        _answer(files=[str(saved), str(tmp_path / "gone.tif")], planes=[_plane(saved)])
    )
    assert problems == [f"acquire: files names {tmp_path / 'gone.tif'}, which does not exist"]


def test_files_must_be_a_list_of_paths():
    assert check_acquire_answer(_answer(files="A1.ome.tif")) == [
        "acquire: files must be a list of paths, one per saved file"
    ]


def test_a_successful_acquisition_must_name_at_least_one_file():
    assert check_acquire_answer(_answer(files=[], planes=[])) == [
        "acquire: a successful acquisition must list at least one file in files",
        "acquire: a successful acquisition must describe at least one image plane in planes",
    ]


def test_a_failed_acquisition_may_list_no_files():
    answer = _answer(files=[], planes=[], reason="the image never arrived")
    answer["success"] = False
    assert check_acquire_answer(answer) == []


def test_the_mock_describes_every_plane_of_a_stack(mock):
    answer = acquire_on_the_mock(mock, z_planes=3, z_step_um=2.0)
    assert check_acquire_answer(answer) == []
    planes = answer["output"]["planes"]
    bottom = planes[0]["z_um"]
    assert [(plane["z"], plane["z_um"]) for plane in planes] == [
        (0, bottom),
        (1, bottom + 2.0),
        (2, bottom + 4.0),
    ]
    assert len({(plane["x_um"], plane["y_um"]) for plane in planes}) == 1


def test_an_answer_without_planes_is_reported(saved):
    assert check_acquire_answer(_answer(files=[str(saved)])) == [
        "acquire: the output must contain planes, one entry per saved image saying which "
        "file, channel, depth and stage position it is"
    ]


def test_planes_must_be_a_list_of_entries(saved):
    assert check_acquire_answer(_answer(files=[str(saved)], planes=3)) == [
        "acquire: planes must be a list with one dictionary per saved image plane"
    ]


def test_a_plane_missing_an_entry_is_reported(saved):
    plane = _plane(saved)
    del plane["z_um"], plane["c"]
    assert check_acquire_answer(_answer(files=[str(saved)], planes=[plane])) == [
        "acquire: planes[0] must contain c, z_um"
    ]


def test_a_plane_must_name_one_of_the_saved_files(tmp_path, saved):
    elsewhere = tmp_path / "B1.ome.tif"
    problems = check_acquire_answer(_answer(files=[str(saved)], planes=[_plane(elsewhere)]))
    assert problems == [f"acquire: planes[0] names {elsewhere}, which is not in files"]


@pytest.mark.parametrize("key, value", [("c", -1), ("z", 1.5), ("t", True), ("c", "GFP")])
def test_channel_depth_and_time_are_counted_from_zero(saved, key, value):
    problems = check_acquire_answer(
        _answer(files=[str(saved)], planes=[_plane(saved, **{key: value})])
    )
    assert problems == [f"acquire: planes[0] {key} must be a whole number from 0, got {value!r}"]


@pytest.mark.parametrize("key, value", [("x_um", "12"), ("z_um", float("nan")), ("y_um", False)])
def test_a_position_must_be_a_number_of_micrometres(saved, key, value):
    problems = check_acquire_answer(
        _answer(files=[str(saved)], planes=[_plane(saved, **{key: value})])
    )
    assert problems == [f"acquire: planes[0] {key} must be a number of micrometres, got {value!r}"]


def test_every_plane_says_where_it_is(saved):
    plane = _plane(saved, z_um=None)
    assert check_acquire_answer(_answer(files=[str(saved)], planes=[plane])) == [
        "acquire: planes[0] z_um must be a number of micrometres, got None"
    ]


def _stack(saved, heights, channels=1):
    return [
        _plane(saved, c=c, z=z, z_um=height)
        for z, height in enumerate(heights)
        for c in range(channels)
    ]


def test_a_stack_counted_upwards_fits(saved):
    planes = _stack(saved, [96.0, 98.0, 100.0], channels=2)
    assert check_acquire_answer(_answer(files=[str(saved)], planes=planes)) == []


def test_a_stack_counted_downwards_is_reported(saved):
    planes = _stack(saved, [100.0, 98.0, 96.0])
    assert check_acquire_answer(_answer(files=[str(saved)], planes=planes)) == [
        "acquire: channel 0 at time 0: depth 1 is at z_um 98.0, not above depth 0 at 100.0; "
        "z counts upwards, so the lowest slice is depth 0",
        "acquire: channel 0 at time 0: depth 2 is at z_um 96.0, not above depth 1 at 98.0; "
        "z counts upwards, so the lowest slice is depth 0",
    ]


def test_slices_at_one_height_are_reported(saved):
    planes = _stack(saved, [5.0, 5.0])
    assert check_acquire_answer(_answer(files=[str(saved)], planes=planes)) == [
        "acquire: channel 0 at time 0: depth 1 is at z_um 5.0, not above depth 0 at 5.0; "
        "z counts upwards, so the lowest slice is depth 0",
    ]


def test_the_channels_of_one_slice_share_its_height(saved):
    planes = [_plane(saved, c=0, z_um=10.0), _plane(saved, c=1, z_um=10.5)]
    assert check_acquire_answer(_answer(files=[str(saved)], planes=planes)) == [
        "acquire: depth 0 at time 0 is at z_um 10.0 in channel 0 but 10.5 in channel 1; "
        "the channels of one slice share its height",
    ]


def test_a_later_time_point_may_stand_at_other_heights(saved):
    planes = [
        *_stack(saved, [10.0, 12.0]),
        *[_plane(saved, z=z, t=1, z_um=height) for z, height in enumerate([10.5, 12.5])],
    ]
    assert check_acquire_answer(_answer(files=[str(saved)], planes=planes)) == []


def test_a_driver_may_add_its_own_entries_to_a_plane(saved):
    plane = _plane(saved, channel_name="GFP", exposure_ms=20)
    assert check_acquire_answer(_answer(files=[str(saved)], planes=[plane])) == []


def test_two_planes_in_the_same_place_are_reported(saved):
    planes = [_plane(saved), _plane(saved, z_um=4.0)]
    assert check_acquire_answer(_answer(files=[str(saved)], planes=planes)) == [
        "acquire: planes[1] repeats channel 0, depth 0 and time 0 of an earlier plane"
    ]


def test_the_label_must_come_back():
    content = {"files": [], "planes": []}
    problems = check_acquire_answer({"success": False, "output": content})
    assert problems == [
        "acquire: the output must contain position_label",
        "acquire: the output must contain acquisition_type, the kind of acquisition it was",
    ]


def test_an_acquisition_without_the_envelope_is_reported():
    problems = check_acquire_answer({"files": []})
    assert problems == ['acquire must return {"success": ..., "output": ...}, got dict']


def test_get_instruments_shows_each_connection_as_written(tmp_path):
    plugin = tmp_path / "zmart_controller_plugin"
    plugin.mkdir()
    (plugin / "zmart_controller_plugin.py").write_text(
        "from mock_driver.zmart_controller_plugin.zmart_controller_plugin import "
        "ZmartControllerPlugin  # noqa: F401\n"
    )
    (plugin / "zmart_controller_plugin.json").write_text(
        json.dumps(
            {
                "name": "pretend",
                "connection": {
                    "microscope": "pretend-01",
                    "api_type": "socket",
                    "host": "127.0.0.1",
                    "client": "pretend-client",
                    "password": None,
                    "config": "C:/pretend/config.ini",
                },
            }
        )
    )
    registry.register_driver(tmp_path)
    try:
        assert registry.get_instruments() == {
            "pretend": {
                "microscope": "pretend-01",
                "api_type": "socket",
                "host": "127.0.0.1",
                "client": "pretend-client",
                "password": None,
                "config": "C:/pretend/config.ini",
            },
        }
    finally:
        registry.remove_driver("pretend")
