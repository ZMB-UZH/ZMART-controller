from __future__ import annotations

import ast
import json
import re
import struct
from pathlib import Path

import mock_driver
import mock_driver.instrument as instrument
import pytest
from mock_driver.configuration import load_configuration, save, saved_path
from mock_driver.error_handling import RULES, Kind, classify
from mock_driver.get_actions import DEFAULT_GET_TUNING
from mock_driver.set_actions import DEFAULT_SET_TUNING, Gate
from mock_driver.testing.mock_api import read_mraw
from mock_driver.testing.mock_api.sample import BACKGROUND, _spot_in_cell
from mock_driver.vendor_interface import VendorError

from zmart_controller import ZmartController

PACKAGE = Path(mock_driver.__file__).resolve().parent


def _open(mock, tmp_path, **extra):
    return ZmartController(mock, {"output_root": str(tmp_path / "images"), **extra})


@pytest.fixture
def mic(mock, tmp_path):
    session = _open(mock, tmp_path, mock_timing="instant")
    yield session
    session.disconnect()


@pytest.fixture
def slow_mic(mock, tmp_path):
    session = _open(mock, tmp_path)
    yield session
    session.disconnect()


def _full_stack(session, z_planes, z_step_um=1.0):
    answer = session.set_state({"changeable": {"z_planes": z_planes, "z_step_um": z_step_um}})
    assert answer["success"] is True, answer["output"]
    return {"trigger": "full"}


def _sent(session, command):
    return [entry for entry in session.plugin.handle.scope.history if entry["command"] == command]


class TestErrorHandling:
    def test_every_kind_has_a_rule(self):
        assert set(RULES) == set(Kind)

    @pytest.mark.parametrize(
        ("error", "kind"),
        [
            (VendorError("X", 100, "busy"), Kind.TEMPORARY),
            (VendorError("X", 201, "out of range"), Kind.BAD_REQUEST),
            (VendorError("X", 300, "fault"), Kind.PERMANENT),
            (VendorError("X", 999, "something new"), Kind.PERMANENT),
            (VendorError("X", 12345, "never seen"), Kind.PERMANENT),
            (TimeoutError("lost"), Kind.TEMPORARY),
            (ConnectionError("gone"), Kind.CONNECTION_LOST),
            (KeyError("surprise"), Kind.PERMANENT),
        ],
    )
    def test_classifier(self, error, kind):
        assert classify(error) is kind

    def test_a_reading_fits_inside_a_confirmation_window(self):
        assert DEFAULT_GET_TUNING.time_limit_s < DEFAULT_SET_TUNING.confirm_window_s


class TestFaultsThroughTheDriver:
    def test_busy_is_sent_again_and_confirmed(self, mic):
        mic.plugin.handle.scope.faults.add("MoveStage", "busy", times=2)
        mic.set_xyz(10, 0, 0)
        assert mic.get_xyz()["output"]["x"]["position"] == 10
        assert [e["code"] for e in _sent(mic, "MoveStage")][-3:] == [100, 100, None]

    def test_busy_too_often_becomes_a_runtime_error(self, mic):
        mic.plugin.handle.scope.faults.add("MoveStage", "busy", times=None)
        failed = mic.set_xyz(10, 0, 0)
        assert failed["success"] is False
        assert re.search("failed 3 times", failed["output"])

    def test_lost_reply_is_read_back_not_sent_again(self, mic):
        mic.plugin.handle.scope.faults.add("MoveStage", "timeout")
        before = len(_sent(mic, "MoveStage"))
        mic.set_xyz(10, 0, 0)
        assert len(_sent(mic, "MoveStage")) == before + 1
        assert mic.get_xyz()["output"]["x"]["position"] == 10

    def test_ignored_setting_is_sent_again(self, mic):
        mic.plugin.handle.scope.faults.add("SetSetting", "ignore")
        answer = mic.set_state({"changeable": {"gain": 3.0}})
        assert answer["success"] is True
        assert len(_sent(mic, "SetSetting")) == 2

    def test_never_confirmed_is_reported_softly(self, mic):
        mic.plugin.handle.scope.faults.add("SetSetting", "ignore", times=None)
        answer = mic.set_state({"changeable": {"gain": 3.0}})
        assert answer["success"] is False
        assert answer["output"].startswith("these settings could not be confirmed: gain")
        done = instrument.set_state(mic.plugin.handle, changeable={"gain": 3.0})
        assert "gain" in done["unconfirmed"] and done["applied"] == {}

    def test_an_unconfirmed_move_is_raised(self, mic):
        mic.plugin.handle.scope.faults.add("MoveStage", "ignore", times=None)
        failed = mic.set_xyz(10, 0, 0)
        assert failed["success"] is False
        assert re.search("could not be confirmed", failed["output"])

    def test_stale_reading_only_delays_confirmation(self, mic):
        mic.get_xyz()
        mic.plugin.handle.scope.faults.add("GetStagePosition", "stale")
        mic.set_xyz(25, 0, 0)
        assert mic.get_xyz()["output"]["x"]["position"] == 25

    @pytest.mark.parametrize("fault", ["hardware_fault", "unknown_error"])
    def test_permanent_problems_are_raised_at_once(self, mic, fault):
        mic.plugin.handle.scope.faults.add("SetSetting", fault)
        failed = mic.set_state({"changeable": {"gain": 3.0}})
        assert failed["success"] is False
        assert len(_sent(mic, "SetSetting")) == 1

    def test_vendor_refusal_is_a_value_error(self, mic):
        mic.plugin.handle.scope.faults.add("MoveStage", "out_of_range")
        failed = mic.set_xyz(10, 0, 0)
        assert failed["success"] is False
        assert re.search("out of range", failed["output"])

    def test_lost_connection(self, mic):
        mic.plugin.handle.scope.faults.add("*", "disconnect")
        failed = mic.get_xyz()
        assert failed["success"] is False
        assert re.search("closed unexpectedly", failed["output"])

    def test_temporary_reading_problem_is_retried(self, mic):
        mic.plugin.handle.scope.faults.add("GetSettings", "busy")
        assert mic.get_state()["success"] is True

    def test_reading_that_stays_busy_is_unknown(self, mic):
        mic.plugin.handle.scope.faults.add("GetSettings", "busy", times=None)
        failed = mic.get_state()
        assert failed["success"] is False
        assert re.search("could not read", failed["output"])


class TestLimitsGate:
    def test_nothing_is_sent_when_the_limits_refuse(self, mic):
        before = len(_sent(mic, "MoveStage"))
        failed = mic.set_xyz(6000, 0, 0)
        assert failed["success"] is False
        assert re.search("outside the travel range", failed["output"])
        assert len(_sent(mic, "MoveStage")) == before

    def test_settings_have_limits_too(self, mic):
        failed = mic.set_state({"changeable": {"laser_power": 80.0}})
        assert failed["success"] is False
        assert re.search("laser_power = 80.0 is outside the limits", failed["output"])
        assert _sent(mic, "SetSetting") == []

    def test_a_z_stack_must_stay_inside(self, mock, tmp_path):
        session = _open(mock, tmp_path, mock_timing="instant", backlash_correction=False)
        try:
            session.set_xyz(0, 0, 490)
            failed = session.acquire(
                position_label="p", acquisition_settings=_full_stack(session, 20)
            )
        finally:
            session.disconnect()
        assert failed["success"] is False and "z-stack" in failed["output"]

    def test_without_limits_everything_is_refused(self):
        assert "not loaded" in Gate(None).check("stage", {"x": 0, "y": 0, "z": 0})

    def test_unknown_keys_are_refused(self):
        limits = load_configuration().limits
        assert "no limit" in Gate(limits).check("teleport", {})

    def test_limits_are_in_stage_coordinates(self, mock, tmp_path):
        save("origin", {"x": 54_000.0, "y": 37_500.0, "z": 5_000.0})
        session = _open(mock, tmp_path, mock_timing="instant")
        try:
            assert session.get_xyz()["output"]["x"]["canvas"] == [-9032.0, 1032.0]
            failed = session.set_xyz(1500, 0, 0)
            assert failed["success"] is False
        finally:
            session.disconnect()


class TestActuators:
    def test_piezo_makes_the_z_change(self, mic):
        mic.set_xyz(0, 0, 30, with_actuators={"z": "piezo"})
        focus = mic.plugin.handle.scope.send("GetFocus")["result"]
        assert focus == {"focus": 5000.0, "piezo": 30.0}
        assert mic.get_xyz()["output"]["z"]["position"] == 30

    def test_beyond_the_piezo_reach(self, mic):
        failed = mic.set_xyz(0, 0, 300, with_actuators={"z": "piezo"})
        assert failed["success"] is False
        assert re.search("beyond its reach", failed["output"])


class TestProcedures:
    def test_autofocus_finds_the_sharp_height(self, mic):
        mic.set_xyz(0, 0, 6)
        found = instrument.run_procedure(
            mic.plugin.handle, procedure={"name": "autofocus", "range_um": 20, "step_um": 2}
        )
        assert abs(found["z_um"]) <= 2
        assert abs(mic.get_xyz()["output"]["z"]["position"]) <= 2

    def test_unknown_entries_are_refused(self, mic):
        failed = mic.run_procedure({"name": "zero_piezo", "speed": "fast"})
        assert failed["success"] is False
        assert re.search("does not take", failed["output"])

    def test_zero_piezo_keeps_the_height(self, mic):
        mic.set_xyz(0, 0, 30, with_actuators={"z": "piezo"})
        mic.run_procedure({"name": "zero_piezo"})
        assert mic.plugin.handle.scope.send("GetFocus")["result"] == {"focus": 5030.0, "piezo": 0.0}

    def test_record_origin_is_used_at_the_next_connect(self, mock, tmp_path):
        from mock_driver.procedures import record_origin

        session = _open(mock, tmp_path, mock_timing="instant")
        session.set_xyz(100, -50, 0)
        record_origin(session.plugin.handle)
        session.disconnect()
        again = _open(mock, tmp_path, mock_timing="instant")
        try:
            position = again.get_xyz()["output"]
            assert (position["x"]["position"], position["y"]["position"]) == (-100.0, 50.0)
        finally:
            again.disconnect()


def _tiff_description(path: Path) -> str:
    raw = path.read_bytes()
    assert raw[:4] == b"II*\0"
    (ifd,) = struct.unpack_from("<I", raw, 4)
    (count,) = struct.unpack_from("<H", raw, ifd)
    for index in range(count):
        tag, _kind, length, offset = struct.unpack_from("<HHII", raw, ifd + 2 + 12 * index)
        if tag == 270:
            return raw[offset : offset + length - 1].decode("utf-8")
    raise AssertionError("no image description")


def _centroid(pixels, width: int, *, around: tuple[float, float], reach: int = 4):
    near = [
        (r, c)
        for r in range(round(around[0]) - reach, round(around[0]) + reach + 1)
        for c in range(round(around[1]) - reach, round(around[1]) + reach + 1)
    ]
    top_r, top_c = max(near, key=lambda rc: pixels[rc[0] * width + rc[1]])
    total = row = col = 0.0
    for r in range(top_r - reach, top_r + reach + 1):
        for c in range(top_c - reach, top_c + reach + 1):
            light = max(0.0, pixels[r * width + c] - BACKGROUND)
            total += light
            row += r * light
            col += c * light
    return row / total, col / total


class TestDataHandling:
    def test_the_stack_is_state_and_the_full_trigger_takes_it(self, mic):
        mic.set_state({"changeable": {"z_planes": 3, "z_step_um": 2.0}})
        assert {"z_planes": 3, "z_step_um": 2.0}.items() <= mic.get_state()["output"][
            "changeable"
        ].items()
        snapped = mic.acquire(position_label="snap")["output"]
        taken = mic.acquire(position_label="stack", acquisition_settings={"trigger": "full"})[
            "output"
        ]
        assert len(snapped["planes"]) == 1
        assert len(taken["planes"]) == 3

    def test_a_stack_must_be_a_whole_number_of_planes(self, mic):
        failed = mic.set_state({"changeable": {"z_planes": 0}})
        assert failed["success"] is False and "z_planes" in failed["output"]

    def test_a_z_stack_is_one_file_per_plane(self, mic):
        answer = mic.acquire(position_label="cell 1", acquisition_settings=_full_stack(mic, 3))[
            "output"
        ]
        names = [Path(f).name for f in answer["files"]]
        assert names == [
            "acquisition_cell_1_z000.ome.tif",
            "acquisition_cell_1_z001.ome.tif",
            "acquisition_cell_1_z002.ome.tif",
            "acquisition_cell_1.commands.json",
        ]
        description = _tiff_description(Path(answer["files"][1]))
        assert 'PhysicalSizeX="1.0"' in description
        assert 'PositionZ="1.0"' in description

    def test_each_plane_says_which_file_channel_depth_and_place_it_is(self, mic):
        mic.set_xyz(100, 50, 3)
        answer = mic.acquire(
            position_label="cell 2",
            acquisition_settings=_full_stack(mic, 3, 2.0),
        )["output"]
        assert answer["planes"] == [
            {
                "path": answer["files"][index],
                "c": 0,
                "z": index,
                "t": 0,
                "x_um": 100.0,
                "y_um": 50.0,
                "z_um": 3.0 + 2.0 * index,
            }
            for index in range(3)
        ]

    def test_an_ome_zarr_stack_names_its_planes_inside_the_one_folder(self, mock, tmp_path):
        session = _open(mock, tmp_path, mock_timing="instant", format="ome-zarr")
        try:
            answer = session.acquire(
                position_label="zp", acquisition_settings=_full_stack(session, 2, 0.5)
            )["output"]
        finally:
            session.disconnect()
        root = answer["files"][0]
        assert [(plane["path"], plane["z"]) for plane in answer["planes"]] == [(root, 0), (root, 1)]
        bottom = answer["planes"][0]["z_um"]
        assert [plane["z_um"] for plane in answer["planes"]] == [bottom, bottom + 0.5]

    def test_the_files_land_in_the_connections_output_root(self, mic, tmp_path):
        answer = mic.acquire(position_label="A1")["output"]
        assert Path(answer["files"][0]).parent == tmp_path / "images"

    def test_get_info_says_where_it_saves_as_a_setup_item(self, mic, tmp_path):
        info = mic.get_info()["output"]
        assert "output_root" not in info
        saving = info["setup"]["saving"]
        assert saving["done"] is True
        assert str(tmp_path / "images") in saving["says"] and "OME-TIFF" in saving["says"]

    def test_never_overwrites(self, mic):
        first = mic.acquire(position_label="A1")["output"]["files"]
        second = mic.acquire(position_label="A1")["output"]["files"]
        assert Path(first[0]).name == "acquisition_A1.ome.tif"
        assert Path(second[0]).name == "acquisition_A1_001.ome.tif"

    def test_the_command_log_is_saved(self, mic):
        mic.plugin.handle.scope.faults.add("MoveStage", "busy")
        answer = mic.acquire(position_label="log")["output"]
        log = next(path for path in answer["files"] if path.endswith(".commands.json"))
        lines = json.loads(Path(log).read_text())
        messages = " ".join(line["message"] for line in lines)
        assert "sending again" in messages
        assert "confirmed" in messages

    def test_ome_zarr_holds_the_stack(self, mock, tmp_path):
        session = _open(mock, tmp_path, mock_timing="instant", format="ome-zarr")
        try:
            answer = session.acquire(
                position_label="z", acquisition_settings=_full_stack(session, 4, 2.0)
            )["output"]
        finally:
            session.disconnect()
        root = Path(answer["files"][0])
        group = json.loads((root / "zarr.json").read_text())
        assert group["zarr_format"] == 3 and group["node_type"] == "group"
        ome = group["attributes"]["ome"]
        assert ome["version"] == "0.5"
        multiscale = ome["multiscales"][0]
        assert multiscale["type"] == "mean"
        assert [axis["name"] for axis in multiscale["axes"]] == ["z", "y", "x"]
        scale = multiscale["datasets"][0]["coordinateTransformations"][0]["scale"]
        assert scale == [2.0, 1.0, 1.0]
        array = json.loads((root / "0" / "zarr.json").read_text())
        assert array["node_type"] == "array"
        assert array["shape"] == [4, 64, 64]
        assert array["data_type"] == "uint16"
        assert array["codecs"] == [{"name": "bytes", "configuration": {"endian": "little"}}]
        assert (root / "0" / "c" / "3" / "0" / "0").stat().st_size == 64 * 64 * 2

    def test_registration_lines_the_image_up_with_the_stage(self, mock, tmp_path):
        session = _open(mock, tmp_path, mock_timing="instant")
        truth = session.plugin.handle.scope.truth()["orientation"]
        session.disconnect()
        save(
            "image_stage_registration",
            {
                "orientation": [list(r) for r in truth],
                "pixel_size_um": {"1": 1.0, "2": 0.5, "3": 0.25},
            },
        )
        session = _open(mock, tmp_path, mock_timing="instant", backlash_correction=False)
        session.plugin.handle.scope._noise = False
        try:
            before = session.acquire(position_label="a")
            session.set_xyz(5, 0, 0)
            after = session.acquire(position_label="b")
            first = _tiff_pixels(before["output"]["files"][0])
            second = _tiff_pixels(after["output"]["files"][0])
            width = 64
            for row in range(64):
                for col in range(64 - 5):
                    assert abs(second[row * width + col] - first[row * width + col + 5]) <= 1
        finally:
            session.disconnect()

    def test_a_spot_lies_in_the_store_where_it_lies_on_the_sample(self, mock, tmp_path):
        session = _open(mock, tmp_path, mock_timing="instant")
        truth = session.plugin.handle.scope.truth()
        session.disconnect()
        save(
            "image_stage_registration",
            {
                "orientation": [list(r) for r in truth["orientation"]],
                "pixel_size_um": {"1": 1.0, "2": 0.5, "3": 0.25},
            },
        )
        session = _open(
            mock, tmp_path, mock_timing="instant", format="ome-zarr", backlash_correction=False
        )
        session.plugin.handle.scope._noise = False
        try:
            raw_x, raw_y, _ = _spot_in_cell(truth["seed"], 2500, 1876)
            origin = session.plugin.handle.config.origin
            spot = {"x": raw_x - origin["x"], "y": raw_y - origin["y"]}
            session.set_xyz(spot["x"] + 6.3, spot["y"] - 4.6, 0.0)
            answer = session.acquire(position_label="spot")["output"]
        finally:
            session.disconnect()
        store = Path(answer["files"][0])
        level = json.loads((store / "zarr.json").read_text())["attributes"]["ome"]
        transforms = level["multiscales"][0]["datasets"][0]["coordinateTransformations"]
        _, pixel_y, pixel_x = transforms[0]["scale"]
        _, origin_y, origin_x = transforms[1]["translation"]
        pixels = struct.unpack("<4096H", (store / "0" / "c" / "0" / "0" / "0").read_bytes())
        row, col = _centroid(pixels, 64, around=(32 + 4.6, 32 - 6.3))
        assert abs(col * pixel_x + origin_x - spot["x"]) < 0.1 * pixel_x
        assert abs(row * pixel_y + origin_y - spot["y"]) < 0.1 * pixel_y

    def test_an_unconfirmed_acquisition_saves_no_files(self, mic, tmp_path):
        mic.plugin.handle.scope.faults.add("StartAcquisition", "ignore")
        answer = mic.acquire(position_label="lost")
        assert answer["success"] is False
        assert answer["output"].startswith("the acquisition could not be confirmed")
        assert list((tmp_path / "images").glob("acquisition_lost*")) == []
        assert len(_sent(mic, "StartAcquisition")) == 1


class TestProblemsFoundInReview:
    def test_lost_acquisition_reply_still_saves_the_image(self, mic):
        mic.plugin.handle.scope.faults.add("StartAcquisition", "timeout")
        answer = mic.acquire(position_label="lost")
        assert answer["success"] is True
        assert Path(answer["output"]["files"][0]).is_file()

    def test_an_ignored_acquisition_is_never_confirmed_by_an_older_one(self, mic):
        first = mic.acquire(position_label="same")
        assert first["success"] is True
        mic.plugin.handle.scope.faults.add("StartAcquisition", "ignore")
        second = mic.acquire(position_label="same")
        assert second["success"] is False
        assert "not running" in second["output"]

    def test_a_long_label_is_saved_under_its_full_name(self, mic):
        label = "well_B07_field_" + "x" * 100
        answer = mic.acquire(position_label=label)
        assert answer["success"] is True, answer["output"]
        assert Path(answer["output"]["files"][0]).name.startswith(f"acquisition_{label}")

    def test_acquire_near_the_lower_limit(self, mic):
        mic.set_xyz(-4980, -5000, 0)
        answer = mic.acquire(position_label="edge")
        assert answer["success"] is True
        assert mic.get_xyz()["output"]["x"]["position"] == -4980

    def test_lost_stage_reply_still_moves_the_focus_at_once(self, mic):
        import time

        mic.plugin.handle.scope.faults.add("MoveStage", "timeout")
        started = time.monotonic()
        mic.set_xyz(10, 10, 20)
        assert time.monotonic() - started < 0.5
        position = mic.get_xyz()["output"]
        assert [position[a]["position"] for a in ("x", "y", "z")] == [10, 10, 20]


@pytest.mark.parametrize(
    "orientation",
    [
        ((1, 0), (0, 1)),
        ((-1, 0), (0, 1)),
        ((1, 0), (0, -1)),
        ((-1, 0), (0, -1)),
        ((0, 1), (1, 0)),
        ((0, -1), (1, 0)),
        ((0, 1), (-1, 0)),
        ((0, -1), (-1, 0)),
    ],
)
def test_alignment_undoes_every_camera_orientation(orientation):
    from mock_driver.data_handling import align_to_stage
    from mock_driver.testing.mock_api.sample import render

    width, height = 40, 24

    def picture(x, y):
        plane = render(
            seed=0,
            width=width,
            height=height,
            pixel_size_um=1.0,
            centre_x=50_000.0 + x,
            centre_y=37_500.0 + y,
            defocus_um=0.0,
            orientation=orientation,
            signal=2000.0,
            noise=None,
        )
        [aligned], out_width, out_height = align_to_stage(
            [plane], width, height, [list(row) for row in orientation]
        )
        return aligned, out_width, out_height

    before, out_width, out_height = picture(0, 0)
    after, _, _ = picture(5, 3)
    for row in range(out_height - 3):
        for col in range(out_width - 5):
            here = after[row * out_width + col]
            there = before[(row + 3) * out_width + col + 5]
            assert abs(here - there) <= 1


def _tiff_pixels(path: str) -> list[int]:
    raw = Path(path).read_bytes()
    (ifd,) = struct.unpack_from("<I", raw, 4)
    (count,) = struct.unpack_from("<H", raw, ifd)
    fields = {}
    for index in range(count):
        tag, kind, _length, value = struct.unpack_from("<HHII", raw, ifd + 2 + 12 * index)
        fields[tag] = value & 0xFFFF if kind == 3 else value
    start, size = fields[273], fields[279]
    return list(struct.unpack_from(f"<{size // 2}H", raw, start))


class TestConfiguration:
    def test_a_malformed_file_is_refused_by_name(self, mock, tmp_path):
        path = saved_path("limits")
        path.parent.mkdir(parents=True)
        path.write_text('{"stage_um": {}}')
        with pytest.raises(ValueError, match="limits.json"):
            _open(mock, tmp_path)

    def test_a_bad_value_is_never_saved(self):
        with pytest.raises(ValueError, match="lowest value must be below"):
            limits = load_configuration().limits
            save("limits", {**limits, "stage_um": {**limits["stage_um"], "x": [10.0, 5.0]}})
        assert not saved_path("limits").exists()

    def test_configuration_of_another_microscope_is_refused(self, mock, tmp_path):
        save(
            "machine_description",
            {"serial": "OTHER-9", "software": "MockScope Control", "tested_versions": ["2.4.1"]},
        )
        with pytest.raises(RuntimeError, match="belongs to OTHER-9"):
            _open(mock, tmp_path)

    def test_calibration_keeps_the_same_spot_across_objectives(self, mock, tmp_path):
        offsets = {"1": {"x": 0.0, "y": 0.0, "z": 0.0}, "2": {"x": 3.0, "y": -2.0, "z": 1.5}}
        save("optical_calibration", {"objective_offsets_um": {**offsets, "3": offsets["1"]}})
        session = _open(mock, tmp_path, mock_timing="instant")
        try:
            session.set_xyz(0, 0, 0)
            session.set_state({"changeable": {"objective": 2}})
            session.set_xyz(0, 0, 0)
            stage = session.plugin.handle.scope.send("GetStagePosition")["result"]
            assert stage == {"x": 50_000.0 - 3.0, "y": 37_500.0 + 2.0}
        finally:
            session.disconnect()

    def test_wrong_token_is_refused_without_showing_it(self, mock, tmp_path):
        with pytest.raises(RuntimeError, match="refused the login") as caught:
            _open(mock, tmp_path, token="s3cret-value")
        assert "s3cret-value" not in str(caught.value)


class TestRealisticTiming:
    def test_moves_are_confirmed_after_they_settle(self, slow_mic):
        slow_mic.set_xyz(1000, 500, 0)
        assert slow_mic.get_xyz()["output"]["x"]["position"] == 1000
        reads = _sent(slow_mic, "GetStagePosition")
        assert len(reads) > 1

    def test_stop_during_an_acquisition(self, slow_mic):
        from mock_driver import set_actions

        handle = slow_mic.plugin.handle
        handle.vendor.start_acquisition("long", z_planes=200, z_step_um=0.1)
        outcome = set_actions.stop(handle)
        assert outcome.confirmed
        status = handle.scope.send("GetStatus")["result"]
        assert status["last_acquisition"]["state"] == "aborted"
        with pytest.raises(ValueError, match="incomplete"):
            read_mraw(status["last_acquisition"]["file"])


ALLOWED = {
    "vendor_interface": {"testing"},
    "error_handling": {"vendor_interface"},
    "configuration": set(),
    "get_actions": {"error_handling", "configuration"},
    "set_actions": {"error_handling", "configuration", "get_actions"},
    "data_handling": {"get_actions"},
    "procedures": {"get_actions", "set_actions", "configuration", "data_handling"},
    "instrument": {
        "vendor_interface",
        "error_handling",
        "configuration",
        "get_actions",
        "set_actions",
        "data_handling",
        "procedures",
    },
    "zmart_controller_plugin": {"instrument"},
}


def _imported_parts(path: Path, part: str) -> set[str]:
    tree = ast.parse(path.read_text())
    here = list(path.relative_to(PACKAGE).parent.parts)
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                base = here[: len(here) - (node.level - 1)]
                target = [*base, *module.split(".")] if module else base
                if target:
                    found.add(target[0])
                else:
                    found.update(a.name for a in node.names)
            elif module.startswith("mock_driver"):
                pieces = module.split(".")
                if len(pieces) > 1:
                    found.add(pieces[1])
                else:
                    found.update(a.name for a in node.names)
    return found - {part}


@pytest.mark.parametrize("part", sorted(ALLOWED))
def test_each_part_only_uses_the_parts_below_it(part):
    folder = PACKAGE / part
    for path in folder.rglob("*.py") if folder.is_dir() else [PACKAGE / f"{part}.py"]:
        used = _imported_parts(path, part)
        assert used <= ALLOWED[part], f"{path.relative_to(PACKAGE)} imports {used - ALLOWED[part]}"


def test_only_the_vendor_interface_touches_the_mock_api():
    for path in PACKAGE.rglob("*.py"):
        relative = path.relative_to(PACKAGE)
        if relative.parts[0] in ("testing", "vendor_interface"):
            continue
        assert "testing" not in _imported_parts(path, relative.parts[0]), str(relative)
