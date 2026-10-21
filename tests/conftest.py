"""Test setup: keep every test's files in its own folder, and offer the mock driver.

The tests run on the mock driver in ``tests/mock_driver/``, so they need no
hardware. It is a driver like any other: a folder with its plugin in
``zmart_controller_plugin/``. The ``mock`` fixture registers it in the test's
own configuration folder and gives its name, so ``ZmartController(mock)``
connects to it.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from pathlib import Path

import mock_driver.instrument as mock_instrument
import pytest

from zmart_controller import register_driver

#: The mock driver's folder, the one ``register_driver`` takes.
MOCK_DRIVER = Path(__file__).parent / "mock_driver"


@pytest.fixture(autouse=True)
def config_in_a_temporary_folder(tmp_path, monkeypatch):
    """Never let a test write to the real configuration folder."""
    monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(tmp_path / "config"))


@pytest.fixture(autouse=True)
def images_in_a_temporary_folder(tmp_path, monkeypatch):
    """Save the mock's images in the test's own folder, never in a shared one."""
    monkeypatch.setattr(mock_instrument, "DEFAULT_OUTPUT_ROOT", tmp_path / "images")


@pytest.fixture(autouse=True)
def home_in_a_temporary_folder(tmp_path, monkeypatch):
    """Never let a test write to the real home folder."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))


@pytest.fixture
def mock():
    """The mock driver, registered in this test's configuration folder; its name."""
    return register_driver(MOCK_DRIVER)
