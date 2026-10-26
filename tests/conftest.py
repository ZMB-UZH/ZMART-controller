from pathlib import Path

import mock_driver.instrument as mock_instrument
import pytest

from zmart_controller import register_driver

MOCK_DRIVER = Path(__file__).parent / "mock_driver"


@pytest.fixture(autouse=True)
def config_in_a_temporary_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(tmp_path / "config"))


@pytest.fixture(autouse=True)
def images_in_a_temporary_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(mock_instrument, "DEFAULT_OUTPUT_ROOT", tmp_path / "images")


@pytest.fixture(autouse=True)
def home_in_a_temporary_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))


@pytest.fixture
def mock():
    return register_driver(MOCK_DRIVER)
