"""Test setup: keep every test's files in its own folder, and reset the active session.

The tests run on the mock driver, ``zmart_controller.mock``, so they need no
hardware.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

import pytest

import zmart_controller.mock.zmart_controller_plugin as mock_driver


@pytest.fixture(autouse=True)
def _config_in_a_temporary_folder(tmp_path, monkeypatch):
    """Never let a test write to the real configuration folder."""
    monkeypatch.setenv("ZMART_MICROSCOPY_ROOT", str(tmp_path / "config"))


@pytest.fixture(autouse=True)
def _images_in_a_temporary_folder(tmp_path, monkeypatch):
    """Save the mock's images in the test's own folder, never in a shared one."""
    monkeypatch.setattr(mock_driver, "DEFAULT_OUTPUT_ROOT", tmp_path / "images")


@pytest.fixture(autouse=True)
def _home_in_a_temporary_folder(tmp_path, monkeypatch):
    """Never let a test write to the real home folder's list of drivers."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
