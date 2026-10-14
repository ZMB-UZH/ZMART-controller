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

A ZMART driver is a folder with at least two files:

- `zmart_driver.json` holds the driver's name, where its ZMART-driver class file is,
  and how to reach the microscope. 
- `zmart_driver.py` holds the `ZmartDriver` class, which integrates the
  code that drives the microscope, one method per command that must comply
  with what the ZMART controller needs.
- Optional other tooling for interacting with the microscope

The drivers for the microscopes at the ZMB are in
the [ZMART drivers](https://github.com/thomdehoog/ZMART-drivers) repository.

## 2) Installing a ZMART driver

Installing a driver means pointing the controller at the driver's
`zmart_driver.json`:

```python
from zmart_controller import mic

mic.register_driver("C:/drivers/my-scope/zmart_driver.json")
```

`register_driver` writes the driver into the registry, the file
`C:\ProgramData\zmart-microscopy\zmart-controller\drivers.json` on Windows
(`zmart_controller.registry.registry_file()` names it on any system). From
then on
`get_instruments` recognises the driver, and the controller can connect to
it by name:

```python
mic.get_instruments()                        # {'mock': {}, 'my-scope': {'microscope': ..., 'host': ..., ...}}
mic.connect("my-scope")
```

`get_instruments` lists every installed driver with how it connects.

The zmart_driver.json is formatted in the following way: 

```json
{
  "name": "<the name you want the driver listed under by get_instruments()>",
  "driver": "<the file that holds your ZmartDriver class; leave it unless you moved the file>",
  "connection": {
    "microscope": "<a name for this particular instrument>",
    "api_type": "<how the vendor software is reached>",
    "host": "<if the vendor software listens on a network address, put it here>",
    "password": "<if the vendor software requires a password or token, put it here>",
    "config": "<if the vendor software has a configuration file, put its path here>"
  }
}
```


## 3) Writing a driver

Open `zmart_driver.py` and fill in the methods of the `ZmartDriver` class.
There is one method per command. When a workflow calls `mic.set_state(...)`,
the controller calls your `set_state(...)`, and so on for every command.

### Input and output

Each method returns two things: `True` and the output, or `False` and an
error message. The controller turns this into the answer the workflow sees,
with the keys `success` and `content`. If the method raises an error instead,
for example because the vendor library failed, the controller catches it and
answers `False` with the text of the error:

```python
def set_state(self, changeable):
    ...
    return True, applied                     # {"success": True,  "content": {"applied": applied}}
    return False, "<error message>"          # {"success": False, "content": "<error message>"}
    raise ValueError("unknown setting")      # anything that raises: {"success": False, "content": "ValueError: unknown setting"}
```

Apply only the settings under `changeable`. Read each one back to check
that it was applied. A setting the microscope does not have is a failure.

### Per call

<br>

#### `__init__`

```python
def __init__(self, connection):     # connection: the dict from zmart_driver.json
    # open the vendor software; load the origin, travel limits and calibration
```

The controller calls this once, when you connect. Load here everything a later command needs, so that each command can work in the sample's coordinate system.

<br>

#### `disconnect`

```python
def disconnect(self):
    # close the vendor software
```

Close cleanly, so that the vendor software can be opened again.

<br>

#### `get_info`

```python
def get_info(self):
    return True, (description, setup)
    # description   str: the settings, their units and limits, the objectives, which way +z points
    # setup         {item: {"done": bool, "says": str}}: each thing set up once on this microscope; {} if none
```

The description is what a person or an AI agent reads to understand your microscope. Write what the other commands cannot tell.

`setup` lists what is set up once on this microscope, such as its limits, a calibration, or where and in which format it saves. For each item, say whether it is done, and in words what it holds or, when it is not done, what to run. A program can then tell the operator what is missing before anything is captured.

<br>

#### `get_actuators`

```python
def get_actuators(self):
    return True, (x, y, z)
    # each axis    {"options": ["motoric", "piezo"], "default": "motoric"}
```

`options` lists the motors that move the axis. `default` is the one used when a command does not choose: you decide it, and the controller uses it for `get_xyz` and `set_xyz` alike.

<br>

#### `get_xyz`

```python
def get_xyz(self, with_actuators):              # {"x": "motoric", "y": "motoric", "z": "piezo"}
    return True, (x, y, z, actuators, canvas)
    # x, y, z      micrometres from the origin
    # actuators    {"x": {"motoric": 50000.0}, "y": {...}, "z": {"motoric": 5000.0, "piezo": 0.0}}   raw readings
    # canvas       (x_min, x_max, y_min, y_max, z_min, z_max)   travel plus half a field of view
```

`with_actuators` names a motor for every axis: the controller has filled in your defaults and refused a motor you do not list, and it tells the workflow which motor was used. Positions are in the sample's coordinate system. The raw readings are reported as the microscope gives them, with nothing subtracted or converted.

<br>

#### `set_xyz`

```python
def set_xyz(self, x, y, z, with_actuators):
    # check the limits, move, wait until arrived
    return self.get_xyz(with_actuators)
    return False, "<error message>"             # outside the limits, or never arrived
```

The call should return when the stage has arrived. `with_actuators` names a motor for every axis, as for `get_xyz`; `x`, `y` and `z` stay micrometres from the origin whichever motor moves. The answer is read from the microscope after the move, so the workflow sees the real position. If the stage never arrives, return `False`, so that the workflow stops.

<br>

#### `get_state`

```python
def get_state(self):
    return True, (changeable, observed)
    # changeable   {"exposure_ms": 10.0, ...}   what set_state can change
    # observed     {"objective": "10x", ...}    read-only
```

The keys are yours to choose. They differ between microscopes, so explain them in `get_info`.

<br>

#### `set_state`

```python
def set_state(self, changeable):
    # apply each setting, read it back
    return True, applied                        # {"exposure_ms": 20.0, ...}
    return False, "<error message>"             # did not take, or unknown setting
```

The call should return when the state has changed. Read each setting back, so that the answer shows what really took. A setting the microscope does not have is a failure.

<br>

#### `get_acquisition_settings`

```python
def get_acquisition_settings(self):
    return True, {"trigger": {"options": ["snap", "full"], "default": "snap", "active": "snap"}}
    # options   the allowed values, or a rule in words
    # default   the value you decide the microscope starts with
    # active    the value used when acquire gets none
```

Acquisition settings say only how an acquisition is triggered. For example, `snap` takes one picture with the settings as they are, and `full` runs the whole acquisition the vendor software has stored and selected. The names are yours to choose: list only the triggers your microscope has, and explain them in `get_info`. Nothing else belongs here: a z-stack, an exposure or which stored acquisition is selected are state, and how files are saved is set up once on the microscope.

<br>

#### `acquire`

```python
def acquire(self, position_label, acquisition_settings):
    # take an image, save it, never overwrite; position_label is the workflow's name, as given
    return True, (files, planes)
    # files    ["D:/images/A1.ome.tif", ...]
    # planes   [{"path": ..., "c": 0, "z": 0, "t": 0, "x_um": ..., "y_um": ..., "z_um": ...}, ...]
```

The call should return when the acquisition is done. Return every saved file and every image plane with its stage position. A workflow then finds its images in the same way on every microscope.

Every plane says where on the sample it was taken, in the frame `set_xyz` takes. A z-stack the microscope makes by itself is described the same way on every microscope: `z_um` is each slice's own height, `z = 0` is the lowest slice and each depth above it is higher, whichever way the microscope moved, and the channels of one slice share its height. `check_acquire_answer` refuses an answer that does not.

<br>

#### `get_procedures`

```python
def get_procedures(self):
    return True, {name: {"description": ...}}  # e.g. autofocus; the description names the options and defaults
```

Routines are not standardised. The description is where you tell the user what a routine does and which options it takes.

<br>

#### `run_procedure`

```python
def run_procedure(self, procedure):             # {"name": "autofocus", ...}: the routine and its options
    return True, procedure["name"]
    return False, "<error message>"             # unknown name
```

The call should return when the procedure is done. A name that `get_procedures` does not list is a failure.

<br>

### Check your driver

```python
mic.validate_driver("C:/drivers/my-scope/zmart_driver.json")   # [] when every method fits
```

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich.

If the code in this repository inspires you, or you use it or build on it, please acknowledge it.
The [CITATION.cff](../../CITATION.cff) file says how to cite it.
