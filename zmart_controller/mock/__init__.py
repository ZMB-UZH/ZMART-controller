"""The mock microscope driver: a complete ZMART driver for a pretend microscope.

It is built from the same parts as every ZMART driver, described in
``docs/driver-anatomy.md`` of the ZMART-drivers repository. Underneath it runs
MockScope Control, pretend vendor software in ``testing/mock_api``. Read it as the template for a new driver,
and use it to try workflows without hardware. Plug it in with::

    zmart_controller.ZmartController(zmart_controller.mock)

The functions the controller calls, one per command, are in
``zmart_controller_plugin.py``. They are listed here, which is how the
controller finds them.
"""

from .zmart_controller_plugin import (
    CONNECTION,
    NAME,
    acquire,
    connect,
    disconnect,
    get_acquisition_settings,
    get_actuators,
    get_info,
    get_procedures,
    get_state,
    get_xyz,
    run_procedure,
    set_state,
    set_xyz,
)

__all__ = [
    "CONNECTION",
    "NAME",
    "acquire",
    "connect",
    "disconnect",
    "get_acquisition_settings",
    "get_actuators",
    "get_info",
    "get_procedures",
    "get_state",
    "get_xyz",
    "run_procedure",
    "set_state",
    "set_xyz",
]
