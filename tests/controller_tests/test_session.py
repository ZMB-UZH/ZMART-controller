"""Tests for the cross-vendor controller against the mock driver.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import zmart_controller.mock as mock
from zmart_controller import ZmartController


@pytest.fixture
def mic():
    session = ZmartController(mock)
    yield session
    session.disconnect()


class TestSetInstrument:
    def test_context_names_the_driver(self, mic):
        assert mic.context == {"driver": "zmart_controller.mock"}

    def test_connection_reaches_driver(self):
        # the connection dict is forwarded untouched to the driver's connect()
        session = ZmartController(mock, {"client": "my-client"})
        try:
            assert session.get_info()["content"]["client"] == "my-client"
        finally:
            session.disconnect()

    def test_a_missing_function_is_named(self):
        functions = {name: getattr(mock, name) for name in mock.__all__ if name != "set_xyz"}
        with pytest.raises(ValueError, match="set_xyz"):
            ZmartController(functions)

    def test_the_mock_is_reachable_from_the_package(self):
        import zmart_controller

        assert zmart_controller.mock is mock


class TestPosition:
    def test_set_get_roundtrip(self, mic):
        """set_xyz answers exactly what get_xyz answers, read back after the move."""
        rec = mic.set_xyz(10, 20, 5)
        assert rec["success"] is True
        pos = rec["content"]
        assert (pos["x"]["position"], pos["y"]["position"], pos["z"]["position"]) == (10, 20, 5)
        assert pos == mic.get_xyz()["content"]
        for axis in ("x", "y", "z"):
            assert list(pos[axis]) == ["position", "unit", "actuator", "actuators", "canvas"]
            assert pos[axis]["unit"] == "micrometer"

    def test_origin_is_driver_configuration(self):
        # The origin is saved by the driver's own setup step and loaded at
        # connect, never set through the controller.
        from zmart_controller import ZmartController as open_session
        from zmart_controller.mock.configuration import save

        save("origin", {"x": 50_100.0, "y": 37_500.0, "z": 5_000.0})
        session = open_session(mock)
        try:
            assert not hasattr(session, "set_origin")
            session.set_xyz(10, 0, 0)
            assert session.get_xyz()["content"]["x"]["position"] == 10
            stage = session._handle.scope.send("GetStagePosition")["result"]
            assert stage["x"] == 50_110.0  # raw stage position = saved origin + user position
        finally:
            session.disconnect()

    def test_get_actuators_names_the_options_and_the_default(self, mic):
        assert mic.get_actuators()["content"]["z"] == {
            "options": ["motoric", "piezo"],
            "default": "motoric",
        }

    def test_every_answer_says_which_motor_it_used(self, mic):
        assert mic.get_xyz()["content"]["z"]["actuator"] == "motoric"
        assert (
            mic.set_xyz(0, 0, 5, with_actuators={"z": "piezo"})["content"]["z"]["actuator"]
            == "piezo"
        )

    def test_every_motor_reports_its_raw_reading(self, mic):
        """``actuators`` lists each motor of the axis with the reading the stage itself reports."""
        pos = mic.get_xyz(with_actuators={"z": "piezo"})["content"]
        stage = mic._handle.scope.send("GetStagePosition")["result"]
        focus = mic._handle.scope.send("GetFocus")["result"]
        assert pos["x"]["actuators"] == {"motoric": stage["x"]}
        assert pos["y"]["actuators"] == {"motoric": stage["y"]}
        assert pos["z"]["actuators"] == {"motoric": focus["focus"], "piezo": focus["piezo"]}
        # Raw readings are the stage's own numbers, not the position from the origin.
        assert pos["x"]["actuators"]["motoric"] != pos["x"]["position"]

    def test_unknown_actuator_raises(self, mic):
        failed = mic.set_xyz(0, 0, 0, with_actuators={"z": "hovercraft"})
        assert failed["success"] is False and re.search("unknown actuator", failed["content"])


class TestAcquire:
    def test_acquire_returns_record(self, mic):
        rec = mic.acquire(position_label="A1")
        assert rec["success"] is True
        rec = rec["content"]
        assert rec["position_label"] == "A1"
        assert rec["settle"] == "backlash-corrected"  # the connection's default
        assert rec["format"] == "ome-tiff"  # the connection's default
        assert rec["trigger"] == "snap"  # the active trigger
        assert rec["confirmed"] is True
        assert [Path(f).name for f in rec["files"]] == ["A1.ome.tif", "A1.commands.json"]
        assert all(Path(f).is_file() for f in rec["files"])
        assert rec["files"][-1] == rec["command_log"]

    def test_saving_and_settling_are_the_connections_choice(self, tmp_path):
        session = ZmartController(
            mock, {"output_root": str(tmp_path), "format": "ome-zarr", "backlash_correction": False}
        )
        try:
            rec = session.acquire(position_label="B2")["content"]
        finally:
            session.disconnect()
        assert rec["settle"] == "direct"
        assert rec["format"] == "ome-zarr"
        assert [Path(f).name for f in rec["files"]] == ["B2.ome.zarr", "B2.commands.json"]
        assert (Path(rec["files"][0]) / "zarr.json").is_file()

    def test_acquisition_settings_only_say_how_to_trigger(self, mic):
        assert mic.get_acquisition_settings()["content"] == {
            "trigger": {"options": ["snap", "full"], "default": "snap", "active": "snap"}
        }


class TestState:
    def test_state_split_into_changeable_observed(self, mic):
        state = mic.get_state()["content"]
        assert list(state) == ["changeable", "observed"]  # changeable first
        assert "laser_power" in state["changeable"]
        assert "serial" in state["observed"]

    def test_capture_and_reapply(self, mic):
        original = mic.get_state()["content"]
        mic.set_state({"changeable": {"laser_power": 40.0}})
        assert mic.get_state()["content"]["changeable"]["laser_power"] == 40.0
        mic.set_state(original)
        laser = mic.get_state()["content"]["changeable"]["laser_power"]
        assert laser == original["changeable"]["laser_power"]

    def test_set_state_returns_driver_record(self, mic):
        rec = mic.set_state({"changeable": {"laser_power": 7.0}})
        assert rec["success"] is True
        assert rec["content"]["applied"]["laser_power"] == 7.0

    def test_soft_outcome_is_reported_not_raised(self, mic):
        # An empty "changeable" changes nothing, and it is safe to carry on,
        # so the driver says so instead of raising.
        rec = mic.set_state({"changeable": {}})
        assert rec["success"] is False
        assert rec["content"]["applied"] == {}

    def test_unknown_setting_name_is_refused(self, mic):
        # A misspelled name is refused before anything is applied, so a typo
        # never passes silently, not even beside a setting that is correct.
        before = mic.get_state()["content"]["changeable"]["gain"]
        failed = mic.set_state({"changeable": {"gain": before + 1, "gian": 1}})
        assert failed["success"] is False and "unknown settings ['gian']" in failed["content"]
        assert mic.get_state()["content"]["changeable"]["gain"] == before

    def test_observed_is_a_report_never_an_instruction(self, mic):
        # A mismatching observed part does not block applying the changeable
        # part, because set_state acts on the changeable part only.
        rec = mic.set_state({"changeable": {"laser_power": 5.0}, "observed": {"serial": "OTHER"}})
        assert rec["content"]["applied"]["laser_power"] == 5.0


class TestProcedures:
    def test_get_procedures_lists_available(self, mic):
        assert "autofocus" in mic.get_procedures()["content"]

    def test_run_procedure_returns_driver_record(self, mic):
        rec = mic.run_procedure({"name": "autofocus"})
        assert rec["success"] is True
        assert rec["content"]["ran"] == "autofocus"

    def test_unknown_procedure_is_refused(self, mic):
        failed = mic.run_procedure({"name": "make_coffee"})
        assert failed["success"] is False and re.search("unknown procedure", failed["content"])


class TestInfo:
    def test_get_info_passthrough(self, mic):
        info = mic.get_info()["content"]
        assert info["serial"] == "MOCK-0001"
        # Nothing has been set up yet, so every configuration item is a shipped default.
        assert all(source.endswith("default.json") for source in info["configuration"].values())


class TestDisconnect:
    def test_driver_refusal_reaches_the_caller_unchanged(self, mic):
        # The controller refuses nothing itself; what the driver raises comes through.
        mic.disconnect()
        mic.disconnect()  # the mock driver makes a second disconnect harmless
        failed = mic.acquire(position_label="A1")
        assert failed["success"] is False and re.search(
            "session is disconnected", failed["content"]
        )

    def test_ops_after_disconnect_raise(self, mic):
        mic.disconnect()
        failed = mic.get_xyz()
        assert failed["success"] is False and re.search("disconnected", failed["content"])

    def test_actuator_selection_does_not_persist(self, mic):
        """A motor chosen for one call applies to that call only.

        The next call is back to the default the driver names."""
        with_piezo = mic.set_xyz(0, 0, 30, with_actuators={"z": "piezo"})["content"]["z"]
        assert with_piezo["actuators"]["piezo"] == 30.0
        by_default = mic.set_xyz(0, 0, 40)["content"]["z"]
        assert by_default["actuators"]["piezo"] == 30.0  # the piezo stayed; the coarse drive moved
        assert by_default["actuators"]["motoric"] == with_piezo["actuators"]["motoric"] + 10.0

    def test_invalid_acquire_option_rejected(self, mic):
        failed = mic.acquire(position_label="A1", acquisition_settings={"tigger": "snap"})
        assert failed["success"] is False and re.search(
            "unknown acquisition setting", failed["content"]
        )
        failed = mic.acquire(position_label="A1", acquisition_settings={"trigger": "burst"})
        assert failed["success"] is False and re.search("invalid value", failed["content"])


class TestModuleStyle:
    def test_mic_connects_and_forwards_the_commands(self):
        from zmart_controller import mic

        mic.connect(mock)
        mic.set_xyz(10, 20, 5)
        assert mic.get_xyz()["content"]["x"]["position"] == 10
        mic.disconnect()

    def test_mic_before_connecting_says_so(self):
        from zmart_controller import mic

        mic.disconnect()
        with pytest.raises(RuntimeError, match="call mic.connect"):
            mic.get_xyz()

    def test_mic_itself_cannot_be_called(self):
        from zmart_controller import mic

        with pytest.raises(TypeError):
            mic("mock")

    def test_unknown_attribute_raises(self):
        import zmart_controller as m

        missing = "definitely_not_a_method"
        with pytest.raises(AttributeError):
            getattr(m, missing)


class TestCanvas:
    def test_the_canvas_is_the_travel_widened_by_half_the_widest_field(self):
        """At the edge of travel a picture still shows half a field further out.

        The mock's widest field is the 10x objective's: 64 pixels of 1.0 µm,
        so on x and y the canvas reaches 32 µm past the travel. Its z-stacks
        must stay inside the travel, so on z the canvas is the travel itself.
        """
        from zmart_controller import ZmartController as open_session
        from zmart_controller.mock.configuration import save

        save("origin", {"x": 51_000.0, "y": 37_500.0, "z": 5_000.0})
        session = open_session(mock)
        try:
            content = session.get_xyz()["content"]
            assert content["x"]["canvas"] == [-6032.0, 4032.0]
            assert content["y"]["canvas"] == [-5032.0, 5032.0]
            assert content["z"]["canvas"] == [-500.0, 500.0]  # exactly the z travel
        finally:
            session.disconnect()

    def test_a_move_outside_the_range_is_refused_before_moving(self, mic):
        mic.set_xyz(10, 0, 0)
        failed = mic.set_xyz(9999, 0, 0)
        assert failed["success"] is False and re.search(
            "outside the travel range", failed["content"]
        )
        assert mic.get_xyz()["content"]["x"]["position"] == 10  # did not move


def _driver_folder(tmp_path, name="bench", connection=None, package=False):
    """A driver folder on disk: zmart_driver.json and a class file that passes every call to the mock.

    With ``package``, the folder is a package and the file uses a relative
    import, as the ZMB drivers do.
    """
    folder = tmp_path / "drivers" / f"{name}_driver"
    folder.mkdir(parents=True)
    if package:
        (folder / "__init__.py").write_text("")
        (folder / "helpers.py").write_text("from zmart_controller.mock import *  # noqa\n")
        (folder / "zmart_driver.py").write_text("from .helpers import *  # noqa\n")
    else:
        (folder / "zmart_driver.py").write_text("from zmart_controller.mock import *  # noqa\n")
    settings = {"name": name, "driver": "zmart_driver.py", "connection": connection or {}}
    (folder / "zmart_driver.json").write_text(json.dumps(settings))
    return folder


class TestRegisteredDrivers:
    def test_the_mock_is_always_listed(self):
        import zmart_controller

        assert list(zmart_controller.get_instruments()) == ["mock"]

    def test_register_once_then_plug_in_by_name(self, tmp_path):
        import zmart_controller

        folder = _driver_folder(tmp_path, connection={"client": "bench-pc"})
        assert zmart_controller.register_driver(folder) == "bench"
        assert list(zmart_controller.get_instruments()) == ["mock", "bench"]
        session = zmart_controller.ZmartController("bench")
        assert session.context == {"driver": "bench"}
        assert session.get_info()["content"]["client"] == "bench-pc"  # its connection

    def test_a_driver_that_is_a_package_with_relative_imports(self, tmp_path):
        import zmart_controller

        zmart_controller.register_driver(_driver_folder(tmp_path, "pkg", package=True))
        session = zmart_controller.ZmartController("pkg")
        assert session.get_xyz()["success"] is True

    def test_a_folder_without_the_json_is_refused(self, tmp_path):
        import zmart_controller

        with pytest.raises(ValueError, match="zmart_driver.json"):
            zmart_controller.register_driver(tmp_path)
        assert list(zmart_controller.get_instruments()) == ["mock"]

    def test_a_driver_missing_a_function_is_refused_and_not_saved(self, tmp_path):
        import zmart_controller

        folder = _driver_folder(tmp_path)
        (folder / "zmart_driver.py").write_text("def connect(connection):\n    return None\n")
        with pytest.raises(ValueError, match="missing functions"):
            zmart_controller.register_driver(folder)
        assert list(zmart_controller.get_instruments()) == ["mock"]

    def test_the_json_itself_can_be_given(self, tmp_path):
        import zmart_controller

        assert (
            zmart_controller.register_driver(_driver_folder(tmp_path) / "zmart_driver.json")
            == "bench"
        )

    def test_a_driver_without_a_name_is_refused(self, tmp_path):
        import zmart_controller

        folder = _driver_folder(tmp_path)
        (folder / "zmart_driver.json").write_text('{"name": ""}')
        with pytest.raises(ValueError, match='must give the driver\'s "name"'):
            zmart_controller.register_driver(folder)

    def test_an_unknown_name_is_refused(self):
        import zmart_controller

        with pytest.raises(ValueError, match="no driver installed as 'ghost'"):
            zmart_controller.ZmartController("ghost")

    def test_remove_driver(self, tmp_path):
        import zmart_controller

        zmart_controller.register_driver(_driver_folder(tmp_path))
        assert zmart_controller.remove_driver("bench") is True
        assert zmart_controller.remove_driver("bench") is False
        assert list(zmart_controller.get_instruments()) == ["mock"]
