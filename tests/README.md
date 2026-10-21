# Run the tests

The tests run on the mock driver in [`mock_driver/`](mock_driver/), so they need no
microscope. It is a driver like any other, and only the tests use it: the `mock` fixture in
[`conftest.py`](conftest.py) registers it in each test's own configuration folder. From the
root of the repository:

```bash
pip install -e ".[test]"
python -m pytest
```

The first line installs the controller together with the test tools. The second runs every
test in this folder: `controller_tests` checks the controller and the driver contract,
`mock_tests` checks the mock driver itself, and `test_no_vendor_names.py` checks that the
repository names no vendor. A run takes about fifteen seconds.
