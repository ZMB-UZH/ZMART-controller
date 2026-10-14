"""ZMART Controller: one small, universal way to drive any microscope.

Connect to a microscope, and drive it::

    from zmart_controller import mic

    mic.connect("mock")                       # the simulated microscope
    mic.set_xyz(10, 20, 5)
    mic.acquire(position_label="A1")
    mic.disconnect()

A driver is two files: ``zmart_driver.json``, its name and how to reach the
microscope, and ``zmart_driver.py``, a ``ZmartDriver`` class with one method
per command. Check it, install it once on the computer, and connect by name::

    zmart_controller.validate_driver("path/to/my-scope/zmart_driver.json")
    zmart_controller.register_driver("path/to/my-scope/zmart_driver.json")
    zmart_controller.get_instruments()        # the drivers installed here, and how each connects

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

__version__ = "0.3.0"
__author__ = "Thom de Hoog"
__email__ = "thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com"
__affiliation__ = "Center for Microscopy and Image Analysis (ZMB), University of Zurich"

from .registry import get_instruments, load_driver, register_driver, remove_driver
from .validate import check_acquire_answer, validate_driver
from .zmart_controller import ZmartController, mic

__all__ = [
    "ZmartController",
    "mic",
    "get_instruments",
    "load_driver",
    "validate_driver",
    "check_acquire_answer",
    "register_driver",
    "remove_driver",
]


def __getattr__(name: str):
    # The mock driver is loaded only when asked for, so importing the
    # controller stays light.
    if name == "mock":
        import importlib

        return importlib.import_module(".mock", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
