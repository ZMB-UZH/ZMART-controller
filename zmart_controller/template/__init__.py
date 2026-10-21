"""A driver's controller plugin to copy: ``zmart_controller_plugin/`` holds its two files.

Copy ``zmart_controller_plugin/`` into your driver's folder, put the driver's
name and connection in ``zmart_controller_plugin.json``, and write the
methods of ``ZmartControllerPlugin`` in ``zmart_controller_plugin.py``.
Check it with ``zmart_controller.validate_driver`` and install it with
``zmart_controller.register_driver``, both pointed at your driver's folder,
the one that holds ``zmart_controller_plugin/``.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""
