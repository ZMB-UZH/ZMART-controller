"""Everything for testing the mock driver, starting with its mock API.

This folder follows the driver anatomy
(``docs/driver-anatomy.md`` in ZMART-drivers): the stand-in for the vendor
software lives here, and it ships with the package so workflows can be tried
without hardware. The mock is the one driver that imports from its testing
folder, because here the pretend vendor software is the microscope. A real
driver imports the vendor's own library instead.
"""
