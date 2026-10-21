"""Part 7 of the driver anatomy (``docs/driver-anatomy.md`` in ZMART-drivers): configuration.

Everything the person at the microscope sets up once and saves, loaded every
time the driver connects:

- ``machine_description``: the fixed facts about this instrument, such as its
  serial number, so a configuration is never used on the wrong microscope.
- ``image_stage_registration``: which way the camera sits on the stage, and
  the size of a pixel for each objective.
- ``origin``: the point that reads as (0, 0, 0).
- ``limits``: how far the stage may travel, and the allowed range of each
  setting.
- ``optical_calibration``: how far each objective's view is shifted from
  objective 1.

Each item has a folder here, holding the ``default.json`` the driver ships
and a check that refuses a malformed file. Once measured, the item is saved
in the computer's ZMART configuration folder and loaded from there. The
arithmetic between stage and user coordinates lives in
:mod:`.coordinates`.
"""

from .checks import AXES, SETTING_NAMES
from .coordinates import raw_from_user, sample_point, user_from_raw, user_range
from .store import IDENTITY, ITEMS, Configuration, load_configuration, save, saved_path

__all__ = [
    "AXES",
    "IDENTITY",
    "SETTING_NAMES",
    "ITEMS",
    "Configuration",
    "load_configuration",
    "raw_from_user",
    "sample_point",
    "save",
    "saved_path",
    "user_from_raw",
    "user_range",
]
