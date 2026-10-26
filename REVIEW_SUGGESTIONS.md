# Review suggestions — ZMART Controller 0.3.0

Review of commit `f6d1563` (`main` / `release-candidate`), October 2026.

## Test results

All checks pass locally on Windows, in fresh conda environments (conda-forge), with
`ZMART_MICROSCOPY_ROOT` pointed at a scratch folder.

| Check | Python 3.11.17 | Python 3.12.15 | Python 3.13.16 |
|---|---|---|---|
| `pytest` (253 tests) | pass | pass | pass |
| `pytest --nbmake docs/` (2 notebooks) | pass | pass | pass |
| `ruff check .` | pass | pass | pass |
| `ruff format --check .` | pass | pass | pass |

The suggestions below come from reading the code and from extra edge-case runs against the
mock driver that the test suite does not cover.

## Suggestions

### 1. The credential filter in `get_instruments` leaks secrets (security)

`registry.get_instruments` hides a connection key only when its name contains `password`,
`token` or `secret`. A driver registered with this connection:

```json
{"host": "h", "api_key": "AAA", "passwd": "BBB", "Authorization": "CCC",
 "password": "DDD", "credentials": "EEE"}
```

is listed by `mic.get_instruments()` as:

```python
{'host': 'h', 'api_key': 'AAA', 'passwd': 'BBB', 'Authorization': 'CCC', 'credentials': 'EEE'}
```

Suggestion: match a wider list (`key`, `passw`, `pwd`, `auth`, `cred`, `cookie`, `session`,
`bearer`), or, more robustly, only show keys a driver declares as safe to show.

### 2. `drivers.json` is not safe against concurrent writers

`registry._save` writes the file in place, and `_installed` reads it without a lock. Six
threads each calling `register_driver` 30 times raised 4 `JSONDecodeError`s, because readers
saw a half-written file. The file was valid at the end, but entries can be lost under a
read-modify-write race. Two Python sessions or notebooks registering at once hit the same
problem.

Suggestion: write to a temporary file in the same folder and `os.replace` it onto
`drivers.json`, which is atomic. If entries must never be lost, also hold a file lock around
the read-modify-write.

### 3. Module drivers and class drivers accept different call signatures

For a class driver, `ZmartController` exposes its own methods, so `acquire("p1")` works. For a
module driver such as the mock, the controller binds the module's functions directly with
`partial`, so their own signatures apply. The mock's arguments are keyword-only:

```python
ZmartController("mock").acquire("p1")
# {'success': False, 'content': 'TypeError: acquire() takes 1 positional argument but 2 were given'}
```

`get_xyz` and `set_xyz` behave the same way for `with_actuators`. The same workflow can
therefore work on one microscope and fail on another, which is what the controller is meant to
prevent.

Suggestion: route module drivers through the same public methods, so every driver sees the
same signature, or make the mock's arguments positional-or-keyword. Add a test that calls
every command positionally on both kinds of driver.

### 4. Module drivers skip the controller's own validation

Because module drivers bypass the controller's methods, `chosen_actuators` never runs for them.
For an unknown axis the mock answers:

```python
c.set_xyz(0, 0, 0, with_actuators={"w": "x"})
# "ValueError: unknown actuator 'x' for axis 'w'"
```

The real problem is that axis `w` does not exist, which `chosen_actuators` would have said.
Fixing suggestion 3 fixes this too.

### 5. `set_state` with malformed input gives unclear answers

- On the mock, `set_state({})` returns `success: False` with an empty `applied` and no reason.
- `set_state(None)` returns `AttributeError: 'NoneType' object has no attribute 'get'`.
- On a class driver, `set_state({})` returns `KeyError: 'changeable'`.

Suggestion: check the input before calling the driver, and answer in words, for example
`'set_state needs {"changeable": {...}}, as get_state returns it'`.

### 6. `chosen_actuators` says it raises, but callers never see the exception

Its docstring says it raises `ValueError` and `RuntimeError`. It does, but `get_xyz` and
`set_xyz` call it inside their `try` blocks, so the caller always gets a
`{"success": False, ...}` answer instead. This behaviour is right; only the docstring is
misleading. Suggestion: say there that the errors reach the caller as a failed answer.

### 7. Registering a driver runs its code, and changes `sys.path` for good

`load_driver` imports the class file that `zmart_driver.json` names, and
`validate_driver(path)` calls it too. That is how plugins work, but it means registering or
validating a driver runs its code with the user's rights. `_import` also adds the driver's
folder to `sys.path` permanently, and two drivers whose packages share a name can collide in
`sys.modules`.

Suggestions:

- Say in `docs/plug_in_a_driver/README.md` that registering or validating a driver runs its
  code, so only drivers from trusted sources should be registered.
- Prefer `spec_from_file_location` with a unique module name for packaged drivers as well,
  or remove the `sys.path` entry after the import.

### 8. The default configuration folder needs administrator rights

`config_root()` defaults to `C:\ProgramData`, `/Library/Application Support` or `/etc`.
Writing there usually needs administrator or root rights on macOS and Linux, so a first
`register_driver` can fail with `PermissionError` for a normal user. `ZMART_MICROSCOPY_ROOT`
works around this, but few users will know about it.

Suggestions:

- Catch `PermissionError` in `_save` and name `ZMART_MICROSCOPY_ROOT` in the message.
- Or fall back to a per-user folder (`platformdirs`-style) when the machine-wide one cannot
  be written.

### 9. Smaller points

- The commands on `Mic` are resolved in `__getattr__`, so editors and type checkers cannot see
  them (no autocomplete for `mic.get_xyz`). Explicit forwarding methods, or a `__dir__`, would
  fix this.
- The nine methods of `ZmartController` repeat the same `try` / `except` / `if not ok` block.
  One small helper would remove the repetition and keep the three outcomes identical by
  construction.
- `get_instruments` loads (imports) every installed driver just to list them. One broken or
  slow driver import makes listing slow, and listing runs the code of every driver.
  Reading `zmart_driver.json` alone would be enough to show the connection.

## Checked and working

- Calling a command on `mic` before `connect` raises a clear `RuntimeError`.
- An unknown attribute on `mic` and an unknown driver name give clear errors.
- Connecting twice in a row, and disconnecting twice in a row, are both harmless.
- `validate_driver` reports no problems for the mock.
