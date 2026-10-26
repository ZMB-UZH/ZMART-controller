# Using the ZMART-controller

## Contents

1. [Overview of the calls](#1-overview-of-the-calls)
2. [More information about the calls](#2-more-information-about-the-calls)

## 1) Overview of the calls

```python
from zmart_controller import mic

# 1) See which drivers are installed and how each connects, then connect to one
mic.get_instruments()
mic.connect(driver, connection=None)

# 2) Learn about the connected setup in more detail
mic.get_info()

# 3) Discover where you are in the xyz space of the canvas, and change the position
#    using the actuators that are available
mic.get_actuators()
mic.get_xyz(with_actuators=None)
mic.set_xyz(x, y, z, with_actuators=None)

# 4) Capture the instrument state, and apply it again later with optional changes
#        (the state is not standardised and differs between microscopes; capturing it
#        and applying it again is what keeps a workflow interoperable)
mic.get_state()
mic.set_state(state)

# 5) Capture and save an image with the appropriate acquisition settings
mic.get_acquisition_settings()
mic.acquire(position_label, acquisition_type=None, output_folder=None, acquisition_settings=None)

# 6) Run a routine the microscope offers (for example autofocus)
#        (the routines are not standardised either and differ between microscopes)
mic.get_procedures()
mic.run_procedure(procedure)

# 7) Close the connection
mic.disconnect()
```

## 2) More information about the calls

Below is more information about the input and output of each call.

Every call answers with the same two keys. `success` is `True` or `False`. `output` is the answer itself when it worked, or a message that says what went wrong. Check `success` first, then use `output`:

```python
answer = mic.get_xyz()
if answer["success"]:
    position = answer["output"]
else:
    print(answer["output"])
```

The values in the examples below are examples. On your microscope they will be different.

Every call waits for the microscope. It returns when the driver is done.

<br>

### mic.get_instruments()

```python
mic.get_instruments()
```

- **Input:** none
- **Output (example)**

  ```python
  {'my-scope': {'microscope': 'my-scope-room-12',
                'api_type': 'socket',
                'host': '192.168.1.20',
                'client': 'zmart',
                'config': 'C:/vendor/settings.cfg'}}
  ```

- **Note:** One entry per installed driver. The key is the name you use in `connect`. The value is the connection from the driver's `zmart_controller_plugin.json`, without the password. It needs no microscope, so it answers directly, without `success` and `output`.

<br>

### mic.connect()

```python
mic.connect(driver, connection=None)
```

- **Input**
  - `driver`: a name from `get_instruments`
  - `connection`: optional; a dictionary that is passed to the driver as it is. Default: the `connection` from the driver's `zmart_controller_plugin.json`.
- **Output:** nothing. After this call, every command below goes to that microscope.

<br>

### mic.get_info()

```python
mic.get_info()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'output': {'description': 'An inverted widefield microscope in room 12. The stage moves x and y, '
                             'the focus drive moves z; all three are in micrometres from the origin, '
                             'and +z moves the objective towards the sample. Objectives: slot 1 is '
                             '10x/0.30 air, slot 2 is 20x/0.75 air, slot 3 is 63x/1.40 oil. Channels: '
                             'DAPI, GFP and TxRed, each with its own exposure in milliseconds and '
                             'LED power in percent.',
              'setup': {'<something set up once on this microscope>': {'done': True, 'says': '<whatever context you want to provide>'}},
              'chooses_its_own_folder': False,
              'connection_status': {'software': 'answers, version 4.7', 'stage': 'found'}}}
  ```

- **Note:** Always exactly these four keys. A description of the microscope, written by the driver's author. It explains the settings and the axes. Read it once when you start on a new microscope. `setup` lists what is set up once on this microscope, such as where and how it saves, each with whether it is done. `chooses_its_own_folder` is `False` when `acquire` saves in the `output_folder` you give it, and `True` when the microscope's software always saves in its own place; `acquire` then saves there, and its answer says where. `connection_status` holds the connection's checks in order, each with its answer, `"pending"` until it has one, or a text that begins with `failed`: ask again while one is pending.

<br>

### mic.get_actuators()

```python
mic.get_actuators()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'output': {'x': {'options': ['motoric'], 'default': 'motoric'},
              'y': {'options': ['motoric'], 'default': 'motoric'},
              'z': {'options': ['motoric', 'piezo'], 'default': 'motoric'}}}
  ```

- **Note:** The motors that move each axis. `default` is the motor used when you do not choose one; the driver decides it, and `get_xyz` and `set_xyz` both use it.

<br>

### mic.get_xyz()

```python
mic.get_xyz(with_actuators=None)
```

- **Input**
  - `with_actuators`: optional; which motor to read per axis, for example `{"z": "piezo"}`. Default: the `default` in `get_actuators` for each axis you leave out.
- **Output (example)**

  ```python
  {'success': True,
   'output': {'x': {'position': 0.0, 'unit': 'micrometer', 'used_actuator': 'motoric', 'actuator_readings': {'motoric': 50000.0},               'canvas': [-5032.0, 5032.0]},
              'y': {'position': 0.0, 'unit': 'micrometer', 'used_actuator': 'motoric', 'actuator_readings': {'motoric': 37500.0},               'canvas': [-5032.0, 5032.0]},
              'z': {'position': 0.0, 'unit': 'micrometer', 'used_actuator': 'motoric', 'actuator_readings': {'motoric': 5000.0, 'piezo': 0.0},  'canvas': [-500.0, 500.0]}}}
  ```

- **Note:** One dictionary with the keys `x`, `y` and `z`. Each axis has the same five entries. All numbers are in micrometres.
  - `position`: the position of the view in the absolute coordinate system: x and y are the centre of the field of view. In a saved image, right is +x and down is +y.
  - `unit`: `'micrometer'`. This is the unit of every number in the answer. It is given as information.
  - `used_actuator`: the name of the motor this call used: the one you chose in `with_actuators`, or else the default from `get_actuators`.
  - `actuator_readings`: what each motor on this axis reads, as the microscope reports it, measured from the motor's own zero rather than from the origin. When an axis has several motors, this shows how they share the position. For information only: move with `position`.
  - `canvas`: `[min, max]`. The range on this axis where an image can be taken. It is the stage travel plus half a field of view.

<br>

### mic.set_xyz()

```python
mic.set_xyz(x, y, z, with_actuators=None)
```

- **Input**
  - `x`, `y`, `z`: the position to move to, in micrometres from the origin. All three are required.
  - `with_actuators`: optional; which motor to use per axis, for example `{"z": "piezo"}`. Default: the `default` in `get_actuators` for each axis you leave out, the same as for `get_xyz`.
- **Output (example)**

  ```python
  {'success': True,
   'output': {'x': {'position': 100.0, 'unit': 'micrometer', 'used_actuator': 'motoric', 'actuator_readings': {'motoric': 50100.0},               'canvas': [-5032.0, 5032.0]},
              'y': {'position': 50.0,  'unit': 'micrometer', 'used_actuator': 'motoric', 'actuator_readings': {'motoric': 37550.0},               'canvas': [-5032.0, 5032.0]},
              'z': {'position': 0.0,   'unit': 'micrometer', 'used_actuator': 'motoric', 'actuator_readings': {'motoric': 5000.0, 'piezo': 0.0},  'canvas': [-500.0, 500.0]}}}
  ```

- **Note:** You choose which actuator makes the move, but `x`, `y` and `z` are always positions in the absolute coordinate system of the canvas, in micrometres, never in the actuator's own units. The call should return when the stage has arrived. The answer is the same as `get_xyz`, read from the microscope. So it shows the real position, not the one you asked for. A move outside the travel returns `success: False`. So does a move the driver could not confirm.

<br>

### mic.get_state()

```python
mic.get_state()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'output': {'changeable': {'laser_power': 10.0, 'gain': 100.0, 'exposure_ms': 10.0, 'objective': 1, 'z_planes': 1, 'z_step_um': 1.0},
              'observed': {'objective': '10x/0.30 Air', 'image_size_px': [512, 512], 'pixel_size_um': [1.0, 1.0], ...}}}
  ```

- **Note:** A snapshot of the settings, in two parts. `changeable` holds the settings that `set_state` can change. `observed` holds facts you can only read, such as the objective in use. Two keys are the same on every microscope: `image_size_px` and `pixel_size_um`, the image size and pixel size of the current settings, so you can plan before capturing. The other keys are not standardised. They differ between microscopes, and `get_info` explains them for yours. A state is a plain dictionary. You can save it as JSON and apply it again later.

<br>

### mic.set_state()

```python
mic.set_state(state)
```

- **Input**
  - `state`: `{"changeable": {...}}` with some or all of the settings from `get_state`. The rest stay as they are.
- **Output (example)**

  ```python
  {'success': True,
   'output': {'applied': {'gain': 200.0}}}
  ```

- **Note:** The call should return when the state has changed. Only the settings you give are applied. All other settings keep their value. The answer lists what was applied, read back from the microscope.

<br>

### mic.get_acquisition_settings()

```python
mic.get_acquisition_settings()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'output': {'trigger': {'options': ['snap', 'full'], 'default': 'snap', 'active': 'snap'}}}
  ```

- **Note:** How an acquisition can be triggered, and nothing else. `snap` takes one picture with the settings as they are. `full` runs the whole acquisition the microscope has stored, such as a z-stack. These are example triggers: each driver names and lists only the ones its microscope has, and `get_info` explains them. `options` lists the values a setting can take, or describes them in words. `default` is the value the driver chose. `active` is the value in use now, used when you give nothing; an `active` that differs from `default` was chosen, for example by this session.

<br>

### mic.acquire()

```python
mic.acquire(position_label, acquisition_type=None, output_folder=None, acquisition_settings=None)
```

- **Input**
  - `position_label`: a name for this position, for example `"A1"`. The controller hands it to the driver as it is.
  - `acquisition_type`: optional; what kind of acquisition this is in your run, for example `"overview"`, `"focussing"` or `"targets"`. The driver puts it in the file names and the metadata, and the answer reports it beside `position_label`. Default: `"acquisition"`.
  - `output_folder`: optional; the folder to save in, for example the folder of this run. Default: the place set up on the microscope (see `setup` in `get_info`). A microscope whose software always saves in its own place saves there instead, and says so in `get_info` with `chooses_its_own_folder: True`; it is never refused for that, and `files` says where the files really are.
  - `acquisition_settings`: optional; values from `get_acquisition_settings`, for example `{"trigger": "full"}`. Default: the `active` value of every setting.
- **Output (example)**, for `mic.acquire("A1", acquisition_type="overview", output_folder="D:/runs/run-1")`

  ```python
  {'success': True,
   'output': {'position_label': 'A1',
              'acquisition_type': 'overview',
              'files': ['D:/runs/run-1/overview_A1.ome.tif', 'D:/runs/run-1/overview_A1.commands.json'],
              'planes': [{'path': 'D:/runs/run-1/overview_A1.ome.tif', 'c': 0, 'z': 0, 't': 0,
                          'x_um': 100.0, 'y_um': 50.0, 'z_um': 0.0}]}}
  ```

- **Note:** Takes an image at the current position with the current settings, and saves it to disk. The call should return when the acquisition is done. `files` lists every saved file. `planes` lists every image plane, with its file, channel, depth, time point, and the sample position where it was taken: `x_um` and `y_um` are the centre of the field of view, the position `get_xyz` reports. In a z-stack, `z = 0` is the lowest slice on every microscope, and each slice's `z_um` is its own height. An image saved as OME-Zarr says where it lies by its translation, which is the centre of its first voxel, as the format defines it (OME-NGFF RFC-5: the centre of a voxel is the origin of the coordinates). So the centre of the pixel in column `i` lies at `x = translation_x + i · pixel size`. A second acquisition with the same label is saved as a new file. The first one is never overwritten.

<br>

### mic.get_procedures()

```python
mic.get_procedures()
```

- **Input:** none
- **Output (example)**

  ```python
  {'success': True,
   'output': {'autofocus': {'description': 'Take a short z-stack around the current height, find the sharpest plane, and move there. Optional: range_um (default 20), step_um (default 2).'},
              ...}}
  ```

- **Note:** Each routine has a name and a description. The description says what the routine does, which options it takes, and their defaults.

<br>

### mic.run_procedure()

```python
mic.run_procedure(procedure)
```

- **Input**
  - `procedure`: a dictionary with the key `"name"` and the options of that routine, for example `{"name": "autofocus", "range_um": 30}`. An option you leave out takes the default from the description in `get_procedures`.
- **Output (example)**

  ```python
  {'success': True,
   'output': {'ran': 'autofocus'}}
  ```

- **Note:** The call should return when the procedure is done.

<br>

### mic.disconnect()

```python
mic.disconnect()
```

- **Input:** none
- **Output:** nothing

---

MIT license. Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich.

If the code in this repository inspires you, or you use it or build on it, please acknowledge it.
The [CITATION.cff](../../CITATION.cff) file says how to cite it.
