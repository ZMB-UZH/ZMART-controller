# Plan: acquire's order, `output`, the controller plugin, and the mock in tests

For ZMART Controller 0.4.0rc2. Agreed with Thom on 2026-10-21, after one review.
Steps 1 and 2 are built (2026-10-21): ZMART-drivers PR #1 is merged, and the
controller is 0.4.0rc2 on release-candidate (dfe6008, tag v0.4.0rc2), 0.4.0rc3 adds point 8,
and 0.4.0rc4 adds point 9. Steps 3 to 6 are open.

These changes break existing code, so they go out together as one version. The
controller, the drivers, the interface and the assembly move to it in the order at
the end.

## 1. `acquisition_settings` comes last in `acquire`

```python
acquire(position_label, acquisition_type=None, output_folder=None, acquisition_settings=None)
```

The order goes from the most used to the least used. Every run names its positions,
most runs give the type and the folder, and few runs change how the image is
triggered.

No caller passes `acquisition_settings` by position today. What changes is the
signature in the controller, the template, the guides and every driver class.

## 2. `content` becomes `output`

Every answer becomes:

```python
{"success": True, "output": ...}     # the values
{"success": False, "output": "..."}  # the reason it failed
```

The controller accepts no `content` during the change. There is one name, and every
block moves to it at once. Where it appears, and what says `content` but must stay,
is listed at the end.

## 3. Only one kind of driver

Today a driver plugs in two ways: as a class (the template, and one of our drivers)
or as loose functions (our other drivers, the mock, the interface's mock microscope). With
loose functions the controller passes the call straight through, so it checks almost
nothing, and the same call behaves differently on different microscopes.

From now on there is one way: every driver is a class, `ZmartControllerPlugin`.

- The controller asks the class for the values and writes every answer itself, with
  the same checks for every driver.
- The loose-function path goes: `driver_functions` and the module branches in
  `registry.py`, `zmart_controller.py` and `validate.py`, `filling_in_acquire` and
  `_answering`.
- The loose-function drivers, the mock and the interface's mock microscope become
  thin classes, like the template: each method calls the driver's own code and
  returns `(ok, values)`.
- The controller hands every value to the driver by name (`position_label=...`,
  `acquisition_type=...`), never by order. A driver can never get its values mixed
  up. `validate_driver` already checks the names.

### Answers hold only what the contract says

The controller writes only the fields the contract defines. Extra information a
driver used to add disappears:

- the mock's `get_info`: client, serial, software, configuration
- the mock's `set_state`: `unconfirmed`
- the mock's `acquire`: trigger, format, settle, confirmed, command_log, vendor_file,
  reason
- the mock's `run_procedure` extras
- ~~the interface mock's `get_info`: `connection_status`~~: it became part of the
  contract instead, see point 9.

The tests that read these change.

A driver that answers `success: False` itself, for example when a change is not
confirmed, returns `False, ...` from its class instead.

## 4. The plugin lives in `<driver>/zmart_controller_plugin/`

The driver is the whole package, for example `my_driver/`. The part that
faces the controller is always in its `zmart_controller_plugin/` folder:

```
my_driver/                            the ZMART driver
  zmart_controller_plugin/
    zmart_controller_plugin.json      its name and how to reach the microscope
    zmart_controller_plugin.py        class ZmartControllerPlugin
  actions/ configuration/ vendor_interface/ ...
```

This is a rule, not a convention. A driver writer makes one folder with these two
files, nothing else; the template has both.

- Two files, not one: the JSON holds what the person installing it changes on each
  microscope (host, password, configuration path), so they never edit code, and a
  password never sits in a Python file that is committed.
- No `__init__.py` is required. The controller imports the folder without one. A
  repository that packages its drivers into a wheel (ours do) takes care of that in
  its own packaging, not in the rule.

- `ZmartDriver` becomes `ZmartControllerPlugin`; `zmart_driver.json` becomes
  `zmart_controller_plugin.json` (`SETTINGS_FILE`); `zmart_driver.py` becomes
  `zmart_controller_plugin.py`. The old names are not accepted.
- The JSON holds `name` and `connection`, nothing else. The key `"driver"` that
  named the class file goes, because the file's name and place are fixed. The JSON
  is the only place `NAME` and `CONNECTION` are set.
- The template becomes `template/zmart_controller_plugin/` and stays importable as
  `zmart_controller.template.zmart_controller_plugin`; the controller's own packaging
  (package data or an `__init__.py` of its own) makes sure it ships in the wheel.
- `register_driver`, `load_driver` and `validate_driver`: a path must be the
  driver's folder; the plugin is found in its `zmart_controller_plugin/`. A folder without
  one is refused, with a message that says where the plugin should be. A class or a
  registered name is still accepted by `validate_driver`.
- `drivers.json` keeps the driver's folder. An old entry, a path to
  `zmart_driver.json`, shows in `get_instruments` as an error that says to register
  the driver's folder again. Each driver on the rig PCs is registered again.
- "Driver" keeps its meaning: the whole package. `register_driver`,
  `validate_driver`, `remove_driver`, `find_driver`, `load_driver` and
  `get_instruments` keep their names. So does `ZmartController.context["driver"]`.

Bringing our own drivers, the interface's mock microscope and the mock in line is
our migration work, listed in ZMART-drivers and ZMART-interface, not something a
driver writer does. The drivers that are loose functions today get a JSON for the
first time.

## 5. The mock leaves the package and goes into `tests/`

The mock is only for the test suite. It is no longer part of `zmart_controller`:

```
tests/
  mock_driver/                the mock, a ZMART driver
    __init__.py
    zmart_controller_plugin/
    configuration/ data_handling/ procedures/ ...
  mock_tests/                 the mock's own tests
  controller_tests/           the controller's tests, run on the mock
```

- "mock" is no longer a name the controller knows: `MOCK` in `registry.py` goes,
  `get_instruments` no longer lists it, `connect("mock")` no longer works, and a
  driver may call itself "mock".
- The mock's imports become relative (today they are `zmart_controller.mock.*`).
- One fixture in `tests/conftest.py` sets a scratch `ZMART_MICROSCOPY_ROOT` and
  registers the mock, per test. It imports the mock under the same module name the
  registry gives it, so its patches reach the one copy in use.
- A test calls every command by name on the mock and on a small class driver, and
  checks both get the same arguments, the same checks and the same answers.
- Pip users get no mock. To try the controller they need a driver. This is intended.
- The guides' examples connect to a registered driver. `tests/README.md` says where
  the mock is.

## 6. The controller's CI

- The package job imports `zmart_controller.mock` today. It becomes a smoke test
  of the installed wheel: import, register the template's folder, validate it.
- A check that the wheel contains no `mock` and does contain
  `template/zmart_controller_plugin/`.

## 7. The controller names no vendor

Nothing in the controller repository names a vendor, a microscope or vendor
software. What changes:

- the template's JSON examples, which named one microscope
- the mock's docstrings that compare it with vendor software and file formats
  (`testing/mock_api/README.md`, `scope.py`, `mraw.py`, `vendor_interface/__init__.py`)
- a test that checks the repository for vendor names, so none come back

## 8. `actuator` and `actuators` become `used_actuator` and `actuator_readings`

The two keys in every axis of `get_xyz` and `set_xyz` were too alike.
`used_actuator` is the name of the motor the call used; `actuator_readings` is
what each motor of the axis reads, from its own zero. The plugin's `get_xyz`
returns `(x, y, z, actuator_readings, canvas)`. The driver guide now gives every
input and every returned value of each plugin method its type, and says which
inputs the controller has checked. Built in the controller as
0.4.0rc3, tag `v0.4.0rc3`. What follows:

- every driver: its `get_xyz` docs and tests, and anything that reads the old
  keys from an answer
- the interface: `backend-contract.ts`, `pretend-stage.test.ts`, the bridge
  tests, the mock microscope's driver and tests, the simulator test

## 9. `connection_status` is part of `get_info`

Decided by Thom on 2026-10-21, when the interface was moved to 0.4: what a
connection checked is something any microscope can honestly report (a real
driver already did), and it is what an operator watches on Connect.

- The plugin's `get_info` returns `(description, setup, chooses_its_own_folder,
  connection_status)`; the answer has these four keys.
- `connection_status` is `{check: answer}`, in the order a client shows them:
  each answered in words, `"pending"` until it is, or beginning with `failed`;
  `{}` when there is nothing to check. `validate_driver` names a wrong shape.
- Every driver returns the fourth value: the template, the mock in `tests/`, and
  the drivers (step 3). Controller 0.4.0rc4.

## Order of work

1. **ZMART-drivers PR #1** goes into the drivers' release-candidate first. It is
   only ahead (104 commits), so this is a fast-forward. It carries changes to every
   driver, so everything after this changes once.
2. **Controller**: tests first, then the code, the template, the mock in `tests/`,
   the guides, the README and CI. Becomes 0.4.0rc2 on release-candidate, tagged
   `v0.4.0rc2`.
3. **Drivers**: every driver becomes a class in
   `zmart_controller_plugin/`, with `output`, the new order and the new motor
   keys. The controller pin goes to
   `v0.4.0rc3`, and the drivers' version goes up.
4. **Interface**: the mock microscope becomes a class in `zmart_controller_plugin/`
   (`pyproject.toml` package data, `bridge/starting.py`); `output` and the new motor keys in Python, the
   TypeScript page code and the docs; the controller pin and `CONTROLLER_VERSIONS`
   (`bridge/connecting.py`) accept only 0.4.0rc4; the tests that used the
   controller's mock are rewritten; the Connect step reads `connection_status`
   from the contract's `get_info` (point 9). The page is rebuilt.
5. **Assembly**: its tests move to the interface's release-candidate layout; it runs
   with `--branch release-candidate`; `install.py` no longer clones the controller
   for the mock; the name-refusal test goes.
6. **Promotion to `main`** only when Thom says.

## Where the old names appear (from the review, release-candidate)

### `content` as the answer key

- **Controller:** `zmart_controller.py` (every command, `_xyz_content`, the module
  docstring), `validate.py` (variables and messages), `mock/` (README,
  `procedures/stage.py`, the plugin), `template/`, `docs/use_the_controller/README.md`
  (14 example lines), `docs/plug_in_a_driver/README.md`, the tests.
- **Drivers:** `README.md`, `docs/driver-anatomy.md`, each driver's README, its
  answer wrappers and docstrings, its plugin file and its tests, including the
  hardware checks.
- **Interface, Python:** `microscope/instrument.py`, `bridge/readings.py`,
  `bridge/__init__.py`, `conftest.py`, `mock_microscope/`, and the bridge, microscope,
  mock-microscope and storage tests.
- **Interface, TypeScript:** `backend/verbs.ts` (`ControllerAnswer`), `live.ts`,
  `pretend.ts`, `backend-contract.ts`, `live-acquire.test.ts`,
  `live-focus-chain.test.ts`; `docs/architecture.md`.
- **Assembly:** `tests/test_bridge_answers.py`, `tests/test_viewer_serves.py`.

### Says `content` but is not an answer: stays

- CSS `content` and `justify-content`, the `index.html` meta tag, `content_type` in
  the interface's bridge server.
- Words in the drivers' own code that are not answers (file contents, dialog
  names, file parsers) and their tests. ZMART-drivers lists them.
- The assembly's `write_report(content)` in `tests/conftest.py`.
- Review records: the interface's `docs/REVIEW_2026-10-10.md`, the controller's
  `REVIEW_SUGGESTIONS.md`.

### `zmart_controller.mock` and the name "mock"

- **Controller:** `registry.py`, `__init__.py` (the lazy `mock`), `pyproject.toml`
  package data, `zmart_controller.py` docstring, CI package job, the tests and the
  guides.
- **Drivers:** `docs/driver-anatomy.md`.
- **Interface:** `storage/test_any_microscope.py` (uses the mock's "snap"/"full"
  triggers; needs a rewrite), `bridge/test_operator_bridge.py` (a driver file that
  imports the mock; the listed names), `backend/pretend.ts`,
  `microscope/instruments.ts` and its test, a comment in the mock microscope plugin.
- **Assembly:** `test_drivers_plug_in.py`, `test_bridge_answers.py`,
  `test_viewer_serves.py`, `install.py`.

### `ZmartDriver`, `zmart_driver.json` / `.py`, the JSON key `"driver"`

- **Controller (11 / 13 files):** `registry.py`, `zmart_controller.py`,
  `validate.py`, `__init__.py`, `template/`, both guides, the tests,
  `pyproject.toml`.
- **Drivers (9 / 12):** `README.md`, `docs/driver-anatomy.md`, a driver's
  `README.md`, `__init__.py`, plugin files and hardware/unit tests.
- **Interface (1 / 8):** `pyproject.toml` package data, the mock microscope,
  `bridge/connecting.py`, the bridge tests (one imports the controller's template),
  `docs/install-on-a-microscope.md`.
- **Assembly (2 / 3):** `test_drivers_plug_in.py`, `test_bridge_answers.py`,
  `README.md`.
- Test fixtures that write a JSON straight into a temp folder get a
  `zmart_controller_plugin/` subfolder.
- Historical session records in the drivers stay as they are.
