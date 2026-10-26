# How do I plug in a ZMART-driver

## Contents

1. [What is a ZMART driver](#1-what-is-a-zmart-driver)
2. [Installing a ZMART driver](#2-installing-a-zmart-driver)
3. [Writing a driver](#3-writing-a-driver)

## 1) What is a ZMART driver

The controller stands in between your workflow and the driver. It knows nothing about any particular workflow or microscope.
It takes input from your workflow through a short, fixed list of commands and hands these to the driver. You can have multiple workflows and multiple drivers, but you only have one controller.

```
your workflow ──► controller ──► driver ──► vendor software ──► microscope
```

A ZMART driver is a folder. The part the controller talks to, the driver's
plugin, is always in its `zmart_controller_plugin/` folder, as two files:

- `zmart_controller_plugin.json` holds the driver's name and how to reach the
  microscope.
- `zmart_controller_plugin.py` holds the `ZmartControllerPlugin` class, which
  integrates the code that drives the microscope, one method per command that
  must comply with what the ZMART controller needs.

Everything else in the driver's folder is yours: the code that talks to the
vendor software, and any other tooling for the microscope.

```
my_driver/                            the ZMART driver
  zmart_controller_plugin/
    zmart_controller_plugin.json      its name and how to reach the microscope
    zmart_controller_plugin.py        class ZmartControllerPlugin
  ...                                 the rest of your driver
```

To start one, copy `zmart_controller/template/zmart_controller_plugin/` into
your driver's folder.

The drivers for the microscopes at the ZMB are in
the [ZMART drivers](https://github.com/ZMB-UZH/ZMART-drivers) repository.

## 2) Installing a ZMART driver

Installing a driver means pointing the controller at the driver's folder,
the one that holds `zmart_controller_plugin/`:

```python
from zmart_controller import mic

mic.register_driver("C:/drivers/my-scope")
```

`register_driver` writes the driver into the registry, the file
`C:\ProgramData\zmart-microscopy\zmart-controller\drivers.json` on Windows
(`zmart_controller.registry.registry_file()` names it on any system). From
then on
`get_instruments` recognises the driver, and the controller can connect to
it by name:

```python
mic.get_instruments()                        # {'my-scope': {'microscope': ..., 'host': ..., ...}}
mic.connect("my-scope")
```

`get_instruments` lists every installed driver with how it connects.

The `zmart_controller_plugin.json` holds the driver's name and its
connection, nothing else:

```json
{
  "name": "<the name you want the driver listed under by get_instruments()>",
  "connection": {
    "microscope": "<a name for this particular instrument>",
    "api_type": "<how the vendor software is reached>",
    "host": "<if the vendor software listens on a network address, put it here>",
    "client": "<if the vendor software tells its clients apart by name, the name this program connects as>",
    "password": null,
    "config": "<the configuration the microscope is used with: a file's path, or the name of a saved configuration>",
    "output_root": "<the folder the driver saves under; null when the workflow gives it when connecting>"
  }
}
```

These are the words every client shows when connecting, the same for every
microscope. Leave out a key your microscope does not need, and a client shows
it as not needed. A password is never written here: keep `null` when the
microscope needs one, and it is typed when connecting. A driver with a
password, token or secret written in its file is refused.


## 3) Writing a driver

Open `zmart_controller_plugin.py` and fill in the methods of the
`ZmartControllerPlugin` class. There is one method per command. When a
workflow calls `mic.set_state(...)`, the controller calls your
`set_state(...)`, and so on for every command. The controller hands every
value over by name, so keep the parameter names shown below; their order is
up to you.

### Input and output

Each method returns two things: `True` and the output, or `False` and an
error message. The controller turns this into the answer the workflow sees,
with the keys `success` and `output`. It writes every answer itself, so the
answer holds exactly what the contract says on every microscope. If the
method raises an error instead,
for example because the vendor library failed, the controller catches it and
answers `False` with the text of the error:

```python
def set_state(self, changeable):
    ...
    return True, applied                     # {"success": True,  "output": {"applied": applied}}
    return False, "<error message>"          # {"success": False, "output": "<error message>"}
    raise ValueError("unknown setting")      # anything that raises: {"success": False, "output": "ValueError: unknown setting"}
```

Apply only the settings under `changeable`. Read each one back to check
that it was applied. A setting the microscope does not have is a failure.

### Per call

For each method, **Input** is what the controller hands your method, with
its type, and says whether the controller has already checked it. **Return**
is what your method gives back when it works, with the type of every value.
When it does not work, every method returns `False, str`: the error message.

`number` means an `int` or a `float`; `True` and `False` are not numbers.
Every number that is a length is in micrometres.

<br>

#### `__init__`

```python
def __init__(self, connection):
    # open the vendor software; load the origin, travel limits and calibration
```

**Input**

| Name | Type | What it is |
|---|---|---|
| `connection` | `dict` | A copy of the `connection` from `zmart_controller_plugin.json`, or the dictionary the workflow gave to `connect` instead. The template's keys where they fit, plus any of your own; `{}` when there is none. |

**Return:** nothing. Raise an error when the microscope cannot be reached.

The controller calls this once, when you connect. Load here everything a later command needs, so that each command can work in the sample's coordinate system.

<br>

#### `disconnect`

```python
def disconnect(self):
    # close the vendor software
```

**Input:** none. **Return:** nothing.

Close cleanly, so that the vendor software can be opened again. This method is optional.

<br>

#### `get_info`

```python
def get_info(self):
    return True, (description, setup, chooses_its_own_folder, connection_status)
```

**Input:** none.

**Return:** `True, (description, setup, chooses_its_own_folder, connection_status)`

| Name | Type | What it is |
|---|---|---|
| `description` | `str`, not empty | The settings, their units and limits, the objectives, which way +z points. |
| `setup` | `dict[str, dict]`: each value `{"done": bool, "says": str}` | Each thing set up once on this microscope; `{}` when there is none. `says` is not empty. |
| `chooses_its_own_folder` | `bool` | `False`: `acquire` saves in the `output_folder` it is given. `True`: the software always saves in its own place. |
| `connection_status` | `dict[str, str]` | The connection's checks in the order a client shows them, each with its answer in words, `"pending"` until it has one, or a text that begins with `failed`. `{}` when there is nothing to check. |

The answer the workflow sees has exactly these four keys, so the
description is where everything else about your microscope goes.

The description is what a person or an AI agent reads to understand your microscope. Write what the other commands cannot tell.

`setup` lists what is set up once on this microscope, such as its limits, a calibration, or where and in which format it saves. For each item, say whether it is done, and in words what it holds or, when it is not done, what to run. A program can then tell the operator what is missing before anything is captured.

`connection_status` is what an operator watches while connecting: did the vendor software answer, was the stage found, can the disk be written. A client asks `get_info` again until no check is `"pending"`, so a check that takes a while can answer later. A failed check stops the connection, so begin its answer with `failed` and say why.

`chooses_its_own_folder` says whether `acquire` saves where it is told. Answer `False` when your driver can choose the folder: it writes the files itself, or the vendor software takes a folder. Answer `True` only when the vendor software always saves in a place of its own, and say in `setup` where that is.

<br>

#### `get_actuators`

```python
def get_actuators(self):
    return True, (x, y, z)
```

**Input:** none.

**Return:** `True, (x, y, z)`, one `dict` per axis:

| Key | Type | What it is |
|---|---|---|
| `options` | `list[str]`, at least one | The motors that move the axis, for example `["motoric", "piezo"]`. |
| `default` | `str`, one of `options` | The motor used when a command does not choose. |

You decide the default, and the controller uses it for `get_xyz` and `set_xyz` alike.

<br>

#### `get_xyz`

```python
def get_xyz(self, with_actuators):
    return True, (x, y, z, actuator_readings, canvas)
```

**Input**

| Name | Type | What it is |
|---|---|---|
| `with_actuators` | `dict[str, str]` | One motor for every axis, for example `{"x": "motoric", "y": "motoric", "z": "piezo"}`. Checked: always the keys `"x"`, `"y"` and `"z"`, each one of that axis's `options`; the controller has filled in your defaults. |

**Return:** `True, (x, y, z, actuator_readings, canvas)`

| Name | Type | What it is |
|---|---|---|
| `x`, `y`, `z` | `number` each | The position in micrometres from the origin, in the sample's coordinate system. x and y are the centre of the field of view. |
| `actuator_readings` | `dict[str, dict[str, number]]` | For each of `"x"`, `"y"` and `"z"`, every motor of that axis with its own reading, for example `{"x": {"motoric": 50000.0}, "y": {"motoric": 37500.0}, "z": {"motoric": 5000.0, "piezo": 0.0}}`. The motor in `with_actuators` must be among them. |
| `canvas` | `tuple` of 6 `number`s | `(x_min, x_max, y_min, y_max, z_min, z_max)`, micrometres from the origin: the travel plus half a field of view. No min is larger than its max. |

The controller tells the workflow which motor was used, as `used_actuator`. The readings are reported as the microscope gives them, in micrometres from each motor's own zero, with no origin subtracted.

<br>

#### `set_xyz`

```python
def set_xyz(self, x, y, z, with_actuators):
    # check the limits, move, wait until arrived
    return self.get_xyz(with_actuators)
```

**Input**

| Name | Type | What it is |
|---|---|---|
| `x`, `y`, `z` | `number` each | Where to move, in micrometres from the origin, whichever motor moves. Not checked: passed as the workflow gave them, so refuse a value outside the limits. |
| `with_actuators` | `dict[str, str]` | As for `get_xyz`: checked, one motor for every axis. |

**Return:** the same as `get_xyz`, read from the microscope after the move.

The call should return when the stage has arrived. The answer is read from the microscope after the move, so the workflow sees the real position. If the move is outside the limits, or the stage never arrives, return `False`, so that the workflow stops.

<br>

#### `get_state`

```python
def get_state(self):
    return True, (changeable, observed)
```

**Input:** none.

**Return:** `True, (changeable, observed)`

| Name | Type | What it is |
|---|---|---|
| `changeable` | `dict[str, Any]` | What `set_state` can change, for example `{"exposure_ms": 10.0}`. |
| `observed` | `dict[str, Any]` | What can only be read, for example `{"objective": "10x"}`, and always `image_size_px` and `pixel_size_um`. |

Two keys of `observed` are the same for every microscope: the image size and pixel size
of the current settings, `image_size_px`, `[width, height]` in pixels, and
`pixel_size_um`, `[x, y]` in micrometres. A workflow plans with them before anything is
captured, for example how far apart to place the tiles of an overview.

The other keys are yours to choose. They differ between microscopes, so explain them in `get_info`. Keep the values to what JSON can hold (text, numbers, `True`/`False`, `None`, lists and dictionaries), so that a state can be saved and applied again.

<br>

#### `set_state`

```python
def set_state(self, changeable):
    # apply each setting, read it back
    return True, applied
```

**Input**

| Name | Type | What it is |
|---|---|---|
| `changeable` | `dict[str, Any]` | The settings to apply, in the form `get_state` gives them. Not checked: passed as the workflow gave it, and it may hold only some of your settings. |

**Return:** `True, applied`

| Name | Type | What it is |
|---|---|---|
| `applied` | `dict[str, Any]` | Each setting you applied, with the value read back, for example `{"exposure_ms": 20.0}`. |

The call should return when the state has changed. Apply only the settings in `changeable`, and read each one back, so that the answer shows what really took. A setting the microscope does not have is a failure.

<br>

#### `get_acquisition_settings`

```python
def get_acquisition_settings(self):
    return True, {"trigger": {"options": ["snap", "full"], "default": "snap", "active": "snap"}}
```

**Input:** none.

**Return:** `True, settings`, a `dict[str, dict]`: each setting by name, with

| Key | Type | What it is |
|---|---|---|
| `options` | `list`, or `str` | The allowed values, or a rule in words. |
| `default` | one of `options` when it is a list | The value you decide the microscope starts with. |
| `active` | one of `options` when it is a list | The value used when `acquire` gets none. |

Acquisition settings say only how an acquisition is triggered. For example, `snap` takes one picture with the settings as they are, and `full` runs the whole acquisition the vendor software has stored and selected. The names are yours to choose: list only the triggers your microscope has, and explain them in `get_info`. Nothing else belongs here: a z-stack, an exposure or which stored acquisition is selected are state, and how files are saved is set up once on the microscope.

<br>

#### `acquire`

```python
def acquire(self, position_label, acquisition_type, output_folder, acquisition_settings):
    # take an image, save it in output_folder (your own place when it is None), never overwrite
    return True, (files, planes)
```

**Input**

| Name | Type | What it is |
|---|---|---|
| `position_label` | `str` | The workflow's name for this place, for example `"A1"`. Not checked: passed as the workflow gave it. |
| `acquisition_type` | `str`, not empty | The kind of acquisition in the run, for example `"overview"`. Checked: `"acquisition"` when the workflow gave none. |
| `output_folder` | `str` or `None` | The folder to save in. Checked: a path the workflow gave is turned into text; `None` means the place set up on the microscope. |
| `acquisition_settings` | `dict[str, Any]` or `None` | How to trigger, for example `{"trigger": "full"}`. Not checked: `None` when the workflow gave none, and then you use the `active` value of each setting. |

**Return:** `True, (files, planes)`

| Name | Type | What it is |
|---|---|---|
| `files` | `list[str]` | Every file saved, by its full path, for example `["D:/runs/run-1/overview_A1.ome.tif"]`. A format that is a folder, such as OME-Zarr, is listed by its folder. Each must exist. |
| `planes` | `list[dict]` | Every image plane, each `{"path": str, "c": int, "z": int, "t": int, "x_um": number, "y_um": number, "z_um": number}`: its file, its channel, slice and time point counted from 0, and where on the sample it was taken. |

The call should return when the acquisition is done. Return every saved file and every image plane with its stage position. A workflow then finds its images in the same way on every microscope.

`acquisition_type` is the kind of acquisition in the workflow's run, such as `"overview"`, `"focussing"` or `"targets"`. Put it in your file names (for example `<acquisition_type>_<position_label>`) and in the metadata you save.

The controller fills in `acquisition_type` and `output_folder` and refuses anything else before your driver is asked, so a driver applies no default of its own for them and needs nothing from the controller's package. The controller also reports the type and the label in its answer, so you return only `files` and `planes`. When your vendor software always saves in a place of its own, save there and return the real paths; never refuse. Say so in `get_info` with `chooses_its_own_folder`. `check_acquire_answer(answer, output_folder=..., chooses_its_own_folder=...)` checks that every file lies in the folder it was given, unless the driver chooses its own.

Every plane says where on the sample it was taken, in the frame `set_xyz` takes: `x_um` and `y_um` are the centre of the field of view, the stage position, never a corner of the image. A z-stack the microscope makes by itself is described the same way on every microscope: `z_um` is each slice's own height, `z = 0` is the lowest slice and each depth above it is higher, whichever way the microscope moved, and the channels of one slice share its height. `check_acquire_answer` refuses an answer that does not.

A driver that saves OME-Zarr places the image by its translation, and the translation is the centre of the first voxel, as OME-NGFF RFC-5 defines it ("the pixel/voxel center is the origin of the continuous coordinate system"). For a plane taken with its field centred at `x_um`, `nx` pixels of size `p` wide, the x translation is `x_um - nx·p/2 + p/2`, and likewise for y; z is the lowest slice's own height. A coarser level made by averaging 2×2 pixels at level `l` starts at `first centre + (2^l - 1)·p/2`. An OME-TIFF's `PositionX` and `PositionY` are not part of the contract, and nothing in ZMART reads them.

<br>

#### `get_procedures`

```python
def get_procedures(self):
    return True, {"autofocus": {"description": "..."}}
```

**Input:** none.

**Return:** `True, procedures`, a `dict[str, dict]`: each procedure by name, with at least `{"description": str}`. The description names the options and their defaults.

Routines are not standardised. The description is where you tell the user what a routine does and which options it takes.

<br>

#### `run_procedure`

```python
def run_procedure(self, procedure):
    return True, procedure["name"]
```

**Input**

| Name | Type | What it is |
|---|---|---|
| `procedure` | `dict[str, Any]` | `"name"`, the routine to run, and its options under their own keys, for example `{"name": "autofocus", "range_um": 50}`. Not checked: passed as the workflow gave it. |

**Return:** `True, ran`

| Name | Type | What it is |
|---|---|---|
| `ran` | `str` | The name of the routine that ran. |

The call should return when the procedure is done. A name that `get_procedures` does not list is a failure.

<br>

### Check your driver

```python
mic.validate_driver("C:/drivers/my-scope")   # [] when every method fits
```

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich.

If the code in this repository inspires you, or you use it or build on it, please acknowledge it.
The [CITATION.cff](../../CITATION.cff) file says how to cite it.
