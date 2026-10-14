# Run the tests

The tests run on the mock driver, `zmart_controller.mock`, so they need no microscope.
From the root of the repository:

```bash
pip install -e ".[test]"
python -m pytest
```

The first line installs the controller together with the test tools. The second runs every
test in this folder: `controller_tests` checks the controller and the driver contract, and
`mock_tests` checks the mock driver itself. A run takes about ten seconds.

The two tutorial notebooks in `docs/` can be run the same way, from start to end, which is
what the continuous integration does on every push:

```bash
python -m pytest --nbmake docs/
```
