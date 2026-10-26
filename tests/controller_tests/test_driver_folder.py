from __future__ import annotations

import json
from pathlib import Path

import pytest

import zmart_controller
from zmart_controller import (
    ZmartController,
    get_instruments,
    load_driver,
    register_driver,
    registry,
    validate_driver,
)

TEMPLATE_PLUGIN = Path(zmart_controller.__file__).parent / "template" / "zmart_controller_plugin"

PLUGIN = """
from {helpers} import DESCRIPTION

AXIS = {{"options": ["motoric"], "default": "motoric"}}


class ZmartControllerPlugin:
    def __init__(self, connection):
        self.connection = connection

    def disconnect(self):
        pass

    def get_info(self):
        return True, (DESCRIPTION, {{}}, False, {{}})

    def get_actuators(self):
        return True, (AXIS, AXIS, AXIS)

    def get_xyz(self, with_actuators):
        motors = {{"x": {{"motoric": 0.0}}, "y": {{"motoric": 0.0}}, "z": {{"motoric": 0.0}}}}
        return True, (0.0, 0.0, 0.0, motors, (-1.0, 1.0, -1.0, 1.0, -1.0, 1.0))

    def set_xyz(self, x, y, z, with_actuators):
        return self.get_xyz(with_actuators)

    def get_state(self):
        return True, ({{}}, {{"image_size_px": [512, 512], "pixel_size_um": [1.0, 1.0]}})

    def set_state(self, changeable):
        return True, dict(changeable)

    def get_acquisition_settings(self):
        return True, {{"trigger": {{"options": ["snap"], "default": "snap", "active": "snap"}}}}

    def acquire(self, position_label, acquisition_type, output_folder, acquisition_settings):
        return True, ([], [])

    def get_procedures(self):
        return True, {{}}

    def run_procedure(self, procedure):
        return True, procedure["name"]
"""


def make_driver(folder: Path, name: str = "my-scope", package: bool = True, **json_extra) -> Path:
    plugin = folder / "zmart_controller_plugin"
    plugin.mkdir(parents=True)
    if package:
        (folder / "__init__.py").write_text("")
    (folder / "helpers.py").write_text('DESCRIPTION = "A scope in a folder. +z points up."\n')
    helpers = "..helpers" if package else "helpers"
    (plugin / "zmart_controller_plugin.py").write_text(PLUGIN.format(helpers=helpers))
    settings = {"name": name, "connection": {"host": "localhost"}, **json_extra}
    (plugin / "zmart_controller_plugin.json").write_text(json.dumps(settings))
    return folder


class TestRegisteringByTheFolder:
    @pytest.mark.parametrize("package", [True, False], ids=["package", "plain folder"])
    def test_the_driver_folder_is_registered_and_connects(self, tmp_path, package):
        folder = make_driver(tmp_path / f"driver_{package}", package=package)
        assert register_driver(folder) == "my-scope"
        assert get_instruments() == {"my-scope": {"host": "localhost"}}
        scope = ZmartController("my-scope")
        try:
            assert scope.get_info()["output"]["description"] == "A scope in a folder. +z points up."
        finally:
            scope.disconnect()

    def test_the_list_keeps_the_driver_folder(self, tmp_path):
        folder = make_driver(tmp_path / "driver")
        register_driver(folder)
        saved = json.loads(registry.registry_file().read_text())
        assert saved == {"my-scope": str(folder.resolve())}

    def test_load_and_validate_take_the_folder_too(self, tmp_path):
        folder = make_driver(tmp_path / "driver")
        assert load_driver(folder).NAME == "my-scope"
        assert validate_driver(folder) == []

    @pytest.mark.parametrize(
        "where",
        ["zmart_controller_plugin", "zmart_controller_plugin/zmart_controller_plugin.json"],
        ids=["the plugin folder", "the JSON"],
    )
    def test_anything_but_the_driver_folder_is_refused(self, tmp_path, where):
        folder = make_driver(tmp_path / "driver")
        with pytest.raises(ValueError, match="the driver's folder"):
            register_driver(folder / where)

    def test_a_folder_without_a_plugin_says_where_it_belongs(self, tmp_path):
        (tmp_path / "empty").mkdir()
        with pytest.raises(ValueError, match="zmart_controller_plugin"):
            register_driver(tmp_path / "empty")


class TestThePluginFiles:
    def test_the_json_holds_only_name_and_connection(self, tmp_path):
        folder = make_driver(tmp_path / "driver", driver="zmart_driver.py")
        with pytest.raises(ValueError, match="'driver'"):
            register_driver(folder)

    @pytest.mark.parametrize("key", ["password", "api_token", "client_secret"])
    def test_a_password_is_never_written_in_the_json(self, tmp_path, key):
        folder = make_driver(tmp_path / "driver", connection={"host": "localhost", key: "hunter2"})
        with pytest.raises(ValueError, match=f"{key!r} must be null"):
            register_driver(folder)

    def test_the_json_is_read_as_utf_8_whatever_the_computer_s_own_encoding(self, tmp_path):
        """JSON is UTF-8; on Windows a plain read_text() took the code page and garbled it."""
        folder = make_driver(tmp_path / "driver")
        settings = folder / "zmart_controller_plugin" / "zmart_controller_plugin.json"
        written = {
            "name": "my-scope",
            "connection": {"api_type": "socket · v2", "microscope": "µscope"},
        }
        settings.write_bytes(json.dumps(written, ensure_ascii=False).encode("utf-8"))
        assert load_driver(folder).CONNECTION == written["connection"]

    def test_a_password_the_driver_needs_is_null(self, tmp_path):
        folder = make_driver(
            tmp_path / "driver", connection={"host": "localhost", "password": None}
        )
        assert load_driver(folder).CONNECTION == {"host": "localhost", "password": None}

    def test_the_old_file_names_are_not_read(self, tmp_path):
        folder = make_driver(tmp_path / "driver")
        plugin = folder / "zmart_controller_plugin"
        (plugin / "zmart_controller_plugin.json").rename(plugin / "zmart_driver.json")
        with pytest.raises(ValueError, match="zmart_controller_plugin.json"):
            register_driver(folder)

    def test_the_plugin_file_must_hold_the_class(self, tmp_path):
        folder = make_driver(tmp_path / "driver")
        (folder / "zmart_controller_plugin" / "zmart_controller_plugin.py").write_text("X = 1\n")
        with pytest.raises(ValueError, match="ZmartControllerPlugin"):
            register_driver(folder)

    def test_the_template_has_the_two_files_and_nothing_else(self):
        assert sorted(path.name for path in TEMPLATE_PLUGIN.iterdir() if path.is_file()) == [
            "zmart_controller_plugin.json",
            "zmart_controller_plugin.py",
        ]
        settings = json.loads((TEMPLATE_PLUGIN / "zmart_controller_plugin.json").read_text())
        assert set(settings) == {"name", "connection"}


class TestAnOldEntry:
    def test_an_entry_from_before_says_to_register_the_folder_again(self, tmp_path):
        old = tmp_path / "old" / "zmart_driver.json"
        old.parent.mkdir()
        old.write_text(json.dumps({"name": "old-scope", "driver": "zmart_driver.py"}))
        registry.registry_file().parent.mkdir(parents=True)
        registry.registry_file().write_text(json.dumps({"old-scope": str(old)}))
        listed = get_instruments()["old-scope"]
        assert "register the driver's folder again" in listed["error"]


class TestNoBuiltInMock:
    def test_nothing_is_listed_until_a_driver_is_registered(self):
        assert get_instruments() == {}

    def test_mock_is_not_a_name_the_controller_knows(self):
        with pytest.raises(ValueError, match="no driver installed as 'mock'"):
            ZmartController("mock")

    def test_a_driver_may_call_itself_mock(self, tmp_path):
        assert register_driver(make_driver(tmp_path / "driver", name="mock")) == "mock"

    def test_the_package_has_no_mock(self):
        assert not (Path(zmart_controller.__file__).parent / "mock").exists()
        with pytest.raises(ImportError):
            __import__("zmart_controller.mock")


def test_the_mock_driver_is_a_driver_folder(mock):
    folder = Path(__file__).parents[1] / "mock_driver"
    assert validate_driver(folder) == []
    assert get_instruments() == {"mock": {}}
