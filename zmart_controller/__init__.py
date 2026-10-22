"""ZMART Controller: one small, universal way to drive any microscope.

Connect to an installed driver, and drive the microscope::

    from zmart_controller import mic

    mic.connect("my-scope")
    mic.set_xyz(10, 20, 5)
    mic.acquire(position_label="A1")
    mic.disconnect()

A driver is a folder. The part the controller talks to is always in its
``zmart_controller_plugin/`` folder, as two files:
``zmart_controller_plugin.json``, the driver's name and how to reach the
microscope, and ``zmart_controller_plugin.py``, a ``ZmartControllerPlugin``
class with one method per command. Check the driver, install it once on the
computer, and connect by name::

    zmart_controller.validate_driver("path/to/my-scope")
    zmart_controller.register_driver("path/to/my-scope")
    zmart_controller.get_instruments()        # the drivers installed here, and how each connects

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

__version__ = "0.4.0rc6"
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
