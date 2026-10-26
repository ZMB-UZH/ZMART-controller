"""Your driver's controller plugin: the class the controller makes when it connects. Fill in every method.

The controller creates one ``ZmartControllerPlugin`` when it connects and
calls the method of the same name for every command, handing every value
over by name, so each parameter must keep the name it has here. Each method
hands back a pair: ``True`` and the values when the microscope did what was
asked, or ``False`` and a message when it did not. The controller turns that
into the answer the workflow sees. A method that raises is reported with the error
text, so raise ``ValueError`` for a request that is wrong, such as a
position outside the travel or an unknown setting.

Positions are micrometres from the origin, the saved zero point of this
microscope. In a saved image, right is +x and down is +y. Every method
below raises ``NotImplementedError`` until you write it, so
``validate_driver`` tells you what is still missing.
"""


class ZmartControllerPlugin:
    """One connected microscope: the vendor connection and everything to drive it."""

    def __init__(self, connection):
        """Open the connection to the vendor software and keep what you need on ``self``.

        ``connection`` is the dictionary from ``zmart_controller_plugin.json``: which
        microscope, how its software is reached, where it listens, the name
        this program connects as, its password, its configuration, and the
        folder it saves under.
        """
        raise NotImplementedError("ZmartControllerPlugin.__init__: open the connection")

    def disconnect(self):
        """Close the connection to the vendor software."""
        raise NotImplementedError("ZmartControllerPlugin.disconnect: close the connection")

    def get_info(self):
        """Return ``True, (description, setup, chooses_its_own_folder, connection_status)``.

        ``description`` is the microscope in plain words: what each
        changeable setting means, its unit and bounds, which objective sits
        in which slot, and which way +z points. ``setup`` is
        ``{item: {"done": bool, "says": text}}``: each thing set up once on
        this microscope (its limits, a calibration, where and how it saves),
        whether it is done, and in words what it holds or what to do; ``{}``
        when there is nothing to set up. ``chooses_its_own_folder`` is
        ``False`` when ``acquire`` saves in the ``output_folder`` it is
        given, and ``True`` when the vendor software always saves in a place
        of its own; say where in ``setup``. ``connection_status`` is
        ``{check: answer}``, in the order a client shows them: what the
        connection checked (the software answers, the stage was found, the
        disk can be written), each answered in words, ``"pending"`` until it
        is, or beginning with ``failed`` when it failed; ``{}`` when there is
        nothing to check.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.get_info: return True, "
            "(description, setup, chooses_its_own_folder, connection_status)"
        )

    def get_actuators(self):
        """Return ``True, (x, y, z)``, each ``{"options": [motor names], "default": one of them}``.

        ``options`` lists the motors that move the axis, at least one.
        ``default`` is the one used when a command does not choose: you
        decide it, and the controller uses it for ``get_xyz`` and
        ``set_xyz`` alike.
        """
        raise NotImplementedError("ZmartControllerPlugin.get_actuators: return True, (x, y, z)")

    def get_xyz(self, with_actuators):
        """Return ``True, (x, y, z, actuator_readings, canvas)``, everything in micrometres.

        ``x``, ``y`` and ``z`` are the position from the origin, in the
        sample's coordinate system. ``actuator_readings`` is
        ``{"x": {...}, "y": {...}, "z": {...}}``: for each axis, every motor
        ``get_actuators`` lists with its own raw reading, exactly as the
        microscope reports it and without any origin subtracted, for example
        ``{"z": {"motoric": 48211.5, "piezo": 37.0}}``. ``canvas`` is
        ``(x_min, x_max, y_min, y_max, z_min, z_max)``: the travel widened
        by half a field of view, everywhere a picture can show.
        ``with_actuators`` names the motor of every axis, such as
        ``{"x": "motoric", "y": "motoric", "z": "piezo"}``: the controller has
        already filled in your defaults and refused a motor you do not list.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.get_xyz: return True, (x, y, z, actuator_readings, canvas)"
        )

    def set_xyz(self, x, y, z, with_actuators):
        """Move the stage, then return what ``get_xyz`` returns, or ``False, message``.

        ``with_actuators`` names the motor of every axis, as for ``get_xyz``;
        ``x``, ``y`` and ``z`` stay micrometres from the origin whichever
        motor moves. Raise ``ValueError`` for a position outside the travel. Read the
        position back until the stage has arrived, then hand back the same
        ``True, (x, y, z, actuators, canvas)`` as ``get_xyz``, read from the
        microscope, so the workflow sees where the stage really is. When the
        stage never arrives, return ``False`` and say where it is, so the
        workflow can stop.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.set_xyz: move, then return what get_xyz returns"
        )

    def get_state(self):
        """Return ``True, (changeable, observed)``: two dictionaries.

        ``changeable`` holds the settings ``set_state`` applies, such as
        exposure time. ``observed`` holds what can only be read, such as the
        objective in place. Two keys in it are the same for every microscope,
        the image size and pixel size of the current settings:
        ``image_size_px``, ``[width, height]``, and ``pixel_size_um``,
        ``[x, y]``, so a workflow can plan before it captures anything.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.get_state: return True, (changeable, observed)"
        )

    def set_state(self, changeable):
        """Apply each setting and return ``True, applied``, or ``False, message``.

        Raise ``ValueError`` for a setting the microscope does not have. Read
        each setting back; when one did not take, return ``False`` and say
        which.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.set_state: apply the settings, return True, applied"
        )

    def get_acquisition_settings(self):
        """Return ``True, settings``: how an acquisition can be triggered.

        ``settings`` is ``{name: {"options": ..., "default": value, "active": value}}``,
        usually only ``trigger``, for example
        ``{"trigger": {"options": ["snap", "full"], "default": "snap", "active": "snap"}}``:
        ``snap`` takes one picture with what is set now, ``full`` runs the
        whole acquisition the vendor software has stored and selected. These
        two are examples, not fixed names. List only
        the ways your microscope has, or add one of its own and say what it
        does in ``get_info``. Nothing else belongs here: a z-stack, an
        exposure or which stored acquisition is selected are state, how files are saved is
        set up once on the microscope.

        ``options`` lists the values a setting may take, or describes them
        in words when they cannot be listed. ``default`` is the value you
        decide the microscope starts with. ``active`` is the value used when
        the setting is left out of ``acquire``; when it differs from
        ``default``, something chose another value, for example this session.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.get_acquisition_settings: return True, settings"
        )

    def acquire(self, position_label, acquisition_type, output_folder, acquisition_settings):
        """Capture here, save, and return ``True, (files, planes)``, or ``False, message``.

        ``position_label`` is the workflow's name for this capture, handed on
        as it was given. ``acquisition_type`` is the kind of acquisition in
        the run, such as ``"overview"``: put it in the file names and the
        metadata. It is always a non-empty text: the controller has filled
        in ``"acquisition"`` when the workflow gave none. ``output_folder``
        is the folder to save in, always text, or ``None`` for the place set
        up on this microscope. Lay it out as you like, such as the images in
        ``data`` and a projection in ``projections``: the layout is kept. When the
        vendor software always saves in its own place, save there, list the
        real paths, and say so in ``get_info``; never refuse for it. Never
        overwrite an earlier file. ``files`` lists the
        path of every file saved. ``planes``
        has one entry per saved image plane: its ``path``, its ``c``, ``z``
        and ``t`` counted from 0, and ``x_um``, ``y_um``, ``z_um``, the
        stage position it was taken at: x and y are the centre of the field
        of view. A store you write (OME-Zarr) is placed by the centre of its
        first voxel. Raise ``ValueError`` for an
        acquisition setting that is not listed. When no complete file ever
        appears, return ``False`` and say so.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.acquire: capture, save, then return True, (files, planes)"
        )

    def get_procedures(self):
        """Return ``True, procedures``: ``{name: {"description": ...}}``, the routines offered."""
        raise NotImplementedError("ZmartControllerPlugin.get_procedures: return True, procedures")

    def run_procedure(self, procedure):
        """Run the routine named by ``procedure["name"]`` and return ``True, name``, or ``False, message``.

        The other keys of ``procedure`` are its arguments. Raise
        ``ValueError`` for a name that ``get_procedures`` does not list.
        """
        raise NotImplementedError(
            "ZmartControllerPlugin.run_procedure: run it, then return True, name"
        )
