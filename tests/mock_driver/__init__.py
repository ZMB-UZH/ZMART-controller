"""The mock driver: a complete ZMART driver for a pretend microscope, for the test suite.

It is built from the same parts as every ZMART driver. Underneath it runs
MockScope Control, pretend vendor software in ``testing/mock_api``. Its plugin
is in ``zmart_controller_plugin/``, like every driver's, and the tests
register this folder (``tests/conftest.py``).
"""
