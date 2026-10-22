from __future__ import annotations

import json
import re
from pathlib import Path

import mock_driver.instrument as instrument
import pytest
from mock_driver.configuration import save

from zmart_controller import ZmartController


@pytest.fixture
def mic(mock):
    session = ZmartController(mock)
    yield session
    session.disconnect()


class TestSetInstrument:
    def test_context_names_the_driver(self, mic):
        assert mic.context == {"driver": "mock"}

    def test_connection_reaches_driver(self, mock):
        session = ZmartController(mock, {"client": "my-client"})
        try:
            assert session.plugin.handle.client == "my-client"
        finally:
            session.disconnect()


class TestPosition:
    def test_set_get_roundtrip(self, mic):
        rec = mic.set_xyz(10, 20, 5)
        assert rec["success"] is True
        pos = rec["output"]
        assert (pos["x"]["position"], pos["y"]["position"], pos["z"]["position"]) == (10, 20, 5)
        assert pos == mic.get_xyz()["output"]
        for axis in ("x", "y", "z"):
            assert list(pos[axis]) == [
                "position",
                "unit",
                "used_actuator",
                "actuator_readings",
                "canvas",
            ]
            assert pos[axis]["unit"] == "micrometer"

    def test_origin_is_driver_configuration(self, mock):
        save("origin", {"x": 50_100.0, "y": 37_500.0, "z": 5_000.0})
        session = ZmartController(mock)
        try:
            assert not hasattr(session, "set_origin")
            session.set_xyz(10, 0, 0)
            assert session.get_xyz()["output"]["x"]["position"] == 10
            stage = session.plugin.handle.scope.send("GetStagePosition")["result"]
            assert stage["x"] == 50_110.0
        finally:
            session.disconnect()

    def test_get_actuators_names_the_options_and_the_default(self, mic):
        assert mic.get_actuators()["output"]["z"] == {
            "options": ["motoric", "piezo"],
            "default": "motoric",
        }

    def test_every_answer_says_which_motor_it_used(self, mic):
        assert mic.get_xyz()["output"]["z"]["used_actuator"] == "motoric"
        assert (
            mic.set_xyz(0, 0, 5, with_actuators={"z": "piezo"})["output"]["z"]["used_actuator"]
            == "piezo"
        )

    def test_every_motor_reports_its_raw_reading(self, mic):
        pos = mic.get_xyz(with_actuators={"z": "piezo"})["output"]
        stage = mic.plugin.handle.scope.send("GetStagePosition")["result"]
        focus = mic.plugin.handle.scope.send("GetFocus")["result"]
        assert pos["x"]["actuator_readings"] == {"motoric": stage["x"]}
        assert pos["y"]["actuator_readings"] == {"motoric": stage["y"]}
        assert pos["z"]["actuator_readings"] == {"motoric": focus["focus"], "piezo": focus["piezo"]}
        assert pos["x"]["actuator_readings"]["motoric"] != pos["x"]["position"]

    def test_unknown_actuator_is_refused(self, mic):
        failed = mic.set_xyz(0, 0, 0, with_actuators={"z": "hovercraft"})
        assert failed["success"] is False
        assert failed["output"] == (
            "ValueError: 'hovercraft' is not an actuator of axis 'z'; it has ['motoric', 'piezo']"
        )


class TestAcquire:
    def test_acquire_answers_the_label_the_type_the_files_and_the_planes(self, mic):
        rec = mic.acquire(position_label="A1")
        assert rec["success"] is True
        rec = rec["output"]
        assert list(rec) == ["position_label", "acquisition_type", "files", "planes"]
        assert rec["position_label"] == "A1"
        assert rec["acquisition_type"] == "acquisition"
        assert [Path(f).name for f in rec["files"]] == [
            "acquisition_A1.ome.tif",
            "acquisition_A1.commands.json",
        ]
        assert all(Path(f).is_file() for f in rec["files"])

    def test_the_mock_records_how_it_took_the_picture(self, mic):
        taken = instrument.acquire(
            mic.plugin.handle,
            position_label="A1",
            acquisition_type="acquisition",
            output_folder=None,
            acquisition_settings=None,
        )
        assert taken["settle"] == "backlash-corrected"
        assert taken["format"] == "ome-tiff"
        assert taken["trigger"] == "snap"
        assert taken["confirmed"] is True
        assert taken["files"][-1] == taken["command_log"]

    def test_saving_and_settling_are_the_connections_choice(self, mock, tmp_path):
        session = ZmartController(
            mock, {"output_root": str(tmp_path), "format": "ome-zarr", "backlash_correction": False}
        )
        try:
            rec = session.acquire(position_label="B2")["output"]
            assert session.plugin.handle.backlash_correction is False
        finally:
            session.disconnect()
        assert [Path(f).name for f in rec["files"]] == [
            "acquisition_B2.ome.zarr",
            "acquisition_B2.commands.json",
        ]
        assert (Path(rec["files"][0]) / "zarr.json").is_file()

    def test_acquisition_settings_only_say_how_to_trigger(self, mic):
        assert mic.get_acquisition_settings()["output"] == {
            "trigger": {"options": ["snap", "full"], "default": "snap", "active": "snap"}
        }


class TestState:
    def test_state_split_into_changeable_observed(self, mic):
        state = mic.get_state()["output"]
        assert list(state) == ["changeable", "observed"]
        assert "laser_power" in state["changeable"]
        assert "serial" in state["observed"]

    def test_capture_and_reapply(self, mic):
        original = mic.get_state()["output"]
        mic.set_state({"changeable": {"laser_power": 40.0}})
        assert mic.get_state()["output"]["changeable"]["laser_power"] == 40.0
        mic.set_state(original)
        laser = mic.get_state()["output"]["changeable"]["laser_power"]
        assert laser == original["changeable"]["laser_power"]

    def test_set_state_answers_what_was_applied(self, mic):
        rec = mic.set_state({"changeable": {"laser_power": 7.0}})
        assert rec == {"success": True, "output": {"applied": {"laser_power": 7.0}}}

    def test_nothing_to_apply_is_a_failure_that_says_so(self, mic):
        rec = mic.set_state({"changeable": {}})
        assert rec == {
            "success": False,
            "output": "nothing was applied: changeable names no setting",
        }

    def test_unknown_setting_name_is_refused(self, mic):
        before = mic.get_state()["output"]["changeable"]["gain"]
        failed = mic.set_state({"changeable": {"gain": before + 1, "gian": 1}})
        assert failed["success"] is False and "unknown settings ['gian']" in failed["output"]
        assert mic.get_state()["output"]["changeable"]["gain"] == before

    def test_observed_is_a_report_never_an_instruction(self, mic):
        rec = mic.set_state({"changeable": {"laser_power": 5.0}, "observed": {"serial": "OTHER"}})
        assert rec["output"]["applied"]["laser_power"] == 5.0


class TestProcedures:
    def test_get_procedures_lists_available(self, mic):
        assert "autofocus" in mic.get_procedures()["output"]

    def test_run_procedure_answers_which_ran(self, mic):
        rec = mic.run_procedure({"name": "autofocus"})
        assert rec == {"success": True, "output": {"ran": "autofocus"}}

    def test_unknown_procedure_is_refused(self, mic):
        failed = mic.run_procedure({"name": "make_coffee"})
        assert failed["success"] is False and re.search("unknown procedure", failed["output"])


class TestInfo:
    def test_get_info_answers_the_description_the_setup_and_the_folder_rule(self, mic):
        info = mic.get_info()["output"]
        assert list(info) == ["description", "setup", "chooses_its_own_folder", "connection_status"]
        assert "pretend widefield fluorescence microscope" in info["description"]
        assert list(info["connection_status"]) == ["software", "stage"]

    def test_the_mock_starts_from_its_shipped_configuration(self, mic):
        sources = instrument.get_info(mic.plugin.handle)["configuration"]
        assert all(source.endswith("default.json") for source in sources.values())


class TestDisconnect:
    def test_driver_refusal_reaches_the_caller_unchanged(self, mic):
        mic.disconnect()
        mic.disconnect()
        failed = mic.acquire(position_label="A1")
        assert failed == {"success": False, "output": "RuntimeError: session is disconnected"}

    def test_ops_after_disconnect_raise(self, mic):
        mic.disconnect()
        failed = mic.get_xyz()
        assert failed["success"] is False and re.search("disconnected", failed["output"])

    def test_actuator_selection_does_not_persist(self, mic):
        with_piezo = mic.set_xyz(0, 0, 30, with_actuators={"z": "piezo"})["output"]["z"]
        assert with_piezo["actuator_readings"]["piezo"] == 30.0
        by_default = mic.set_xyz(0, 0, 40)["output"]["z"]
        assert by_default["actuator_readings"]["piezo"] == 30.0
        assert (
            by_default["actuator_readings"]["motoric"]
            == with_piezo["actuator_readings"]["motoric"] + 10.0
        )

    def test_invalid_acquire_option_rejected(self, mic):
        failed = mic.acquire(position_label="A1", acquisition_settings={"tigger": "snap"})
        assert failed["success"] is False and re.search(
            "unknown acquisition setting", failed["output"]
        )
        failed = mic.acquire(position_label="A1", acquisition_settings={"trigger": "burst"})
        assert failed["success"] is False and re.search("invalid value", failed["output"])


class TestModuleStyle:
    def test_mic_connects_and_forwards_the_commands(self, mock):
        from zmart_controller import mic

        mic.connect(mock)
        mic.set_xyz(10, 20, 5)
        assert mic.get_xyz()["output"]["x"]["position"] == 10
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
    def test_the_canvas_is_the_travel_widened_by_half_the_widest_field(self, mock):
        save("origin", {"x": 51_000.0, "y": 37_500.0, "z": 5_000.0})
        session = ZmartController(mock)
        try:
            output = session.get_xyz()["output"]
            assert output["x"]["canvas"] == [-6032.0, 4032.0]
            assert output["y"]["canvas"] == [-5032.0, 5032.0]
            assert output["z"]["canvas"] == [-500.0, 500.0]
        finally:
            session.disconnect()

    def test_a_move_outside_the_range_is_refused_before_moving(self, mic):
        mic.set_xyz(10, 0, 0)
        failed = mic.set_xyz(9999, 0, 0)
        assert failed["success"] is False and re.search(
            "outside the travel range", failed["output"]
        )
        assert mic.get_xyz()["output"]["x"]["position"] == 10


BENCH = "from {mock} import ZmartControllerPlugin  # noqa: F401\n"


def bench_driver(tmp_path, name="bench", connection=None, package=False):
    folder = tmp_path / "drivers" / f"{name}_driver"
    plugin = folder / "zmart_controller_plugin"
    plugin.mkdir(parents=True)
    mock_plugin = "mock_driver.zmart_controller_plugin.zmart_controller_plugin"
    if package:
        (folder / "__init__.py").write_text("")
        (folder / "helpers.py").write_text(BENCH.format(mock=mock_plugin))
        (plugin / "zmart_controller_plugin.py").write_text(BENCH.format(mock="..helpers"))
    else:
        (plugin / "zmart_controller_plugin.py").write_text(BENCH.format(mock=mock_plugin))
    settings = {"name": name, "connection": connection or {}}
    (plugin / "zmart_controller_plugin.json").write_text(json.dumps(settings))
    return folder


class TestRegisteredDrivers:
    def test_nothing_is_listed_before_a_driver_is_registered(self):
        import zmart_controller

        assert zmart_controller.get_instruments() == {}

    def test_register_once_then_plug_in_by_name(self, tmp_path):
        import zmart_controller

        folder = bench_driver(tmp_path, connection={"client": "bench-pc"})
        assert zmart_controller.register_driver(folder) == "bench"
        assert list(zmart_controller.get_instruments()) == ["bench"]
        session = zmart_controller.ZmartController("bench")
        try:
            assert session.context == {"driver": "bench"}
            assert session.plugin.handle.client == "bench-pc"
        finally:
            session.disconnect()

    def test_a_driver_that_is_a_package_with_relative_imports(self, tmp_path):
        import zmart_controller

        zmart_controller.register_driver(bench_driver(tmp_path, "pkg", package=True))
        session = zmart_controller.ZmartController("pkg")
        try:
            assert session.get_xyz()["success"] is True
        finally:
            session.disconnect()

    def test_a_folder_without_the_plugin_is_refused(self, tmp_path):
        import zmart_controller

        with pytest.raises(ValueError, match="has no zmart_controller_plugin/ folder"):
            zmart_controller.register_driver(tmp_path)
        assert zmart_controller.get_instruments() == {}

    def test_a_plugin_without_the_class_is_refused_and_not_saved(self, tmp_path):
        import zmart_controller

        folder = bench_driver(tmp_path)
        (folder / "zmart_controller_plugin" / "zmart_controller_plugin.py").write_text("X = 1\n")
        with pytest.raises(ValueError, match="must hold a ZmartControllerPlugin class"):
            zmart_controller.register_driver(folder)
        assert zmart_controller.get_instruments() == {}

    def test_a_driver_without_a_name_is_refused(self, tmp_path):
        import zmart_controller

        folder = bench_driver(tmp_path)
        (folder / "zmart_controller_plugin" / "zmart_controller_plugin.json").write_text(
            '{"name": ""}'
        )
        with pytest.raises(ValueError, match='must give the driver\'s "name"'):
            zmart_controller.register_driver(folder)

    def test_an_unknown_name_is_refused(self):
        import zmart_controller

        with pytest.raises(ValueError, match="no driver installed as 'ghost'"):
            zmart_controller.ZmartController("ghost")

    def test_remove_driver(self, tmp_path):
        import zmart_controller

        zmart_controller.register_driver(bench_driver(tmp_path))
        assert zmart_controller.remove_driver("bench") is True
        assert zmart_controller.remove_driver("bench") is False
        assert zmart_controller.get_instruments() == {}
