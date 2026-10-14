"""Saving one acquisition in the files ZMART uses, and reporting where it went.

The layout under the output folder is::

    <output_root>/<position_label>.ome.tif          one plane
    <output_root>/<position_label>_z000.ome.tif     a z-stack, one file per plane
    <output_root>/<position_label>.ome.zarr/        OME-Zarr, any number of planes
    <output_root>/<position_label>.commands.json    the command log

Every name starts with the label the workflow gave, so a workflow that wants
its acquisitions told apart says so in the label.

Nothing is ever overwritten: a second acquisition with the same label gets
``_001``, ``_002`` and so on.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .collect import wait_for_file
from .ome_tiff import ome_xml, write_ome_tiff
from .ome_zarr import write_ome_zarr
from .orient import align_to_stage

#: The file formats an acquisition can be saved in.
FORMATS = ("ome-tiff", "ome-zarr")

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_name(text: str) -> str:
    """``text`` made safe as a file name: anything unusual becomes ``_``."""
    cleaned = _UNSAFE.sub("_", text).strip("._")
    return cleaned or "image"


def _free(folder: Path, stem: str, suffixes: list[str]) -> str:
    """A stem for which none of ``stem + suffix`` exists yet in ``folder``."""
    candidate = stem
    number = 0
    while any((folder / f"{candidate}{suffix}").exists() for suffix in suffixes):
        number += 1
        candidate = f"{stem}_{number:03d}"
    return candidate


def save_acquisition(
    ctx,
    *,
    vendor_file: str,
    position_label: str,
    image_format: str,
    position_um: dict[str, float],
    log_mark: int,
) -> dict[str, Any]:
    """Turn the vendor's file into OME-TIFF or OME-Zarr, and save the command log.

    ``position_um`` is the user position at which the image was taken.
    ``log_mark`` is the command-log bookmark taken before the acquisition
    started. Returns ``{"files": [...], "planes": [...], "command_log": ...}``
    with the saved paths as text: ``files`` lists every file saved, the images
    first and the command log last, and ``planes`` says for each image plane
    which file holds it and where on the sample it was taken, as the contract
    in docs/plug_in_a_driver/README.md asks.
    """
    if image_format not in FORMATS:
        raise ValueError(f"unknown format {image_format!r}; choose one of {list(FORMATS)}")
    header, planes = wait_for_file(ctx, vendor_file)
    registration = ctx.config.image_stage_registration
    slot = str(header["objective"]["slot"])
    pixel_size = float(registration["pixel_size_um"].get(slot, header["pixel_size_um"]))
    planes, width, height = align_to_stage(
        planes, header["width"], header["height"], registration["orientation"]
    )
    # The position is the centre of the picture; OME stores the corner pixel.
    corner = {
        "x": position_um["x"] - (width / 2) * pixel_size,
        "y": position_um["y"] - (height / 2) * pixel_size,
        "z": position_um["z"],
    }
    extra = {
        "position_label": position_label,
        "objective": header["objective"]["name"],
        "vendor_file": str(vendor_file),
        "registration": ctx.config.sources["image_stage_registration"],
        "calibration": ctx.config.sources["optical_calibration"],
    }
    label = safe_name(position_label)
    folder = Path(ctx.output_root)
    folder.mkdir(parents=True, exist_ok=True)
    files: list[str] = []
    if image_format == "ome-zarr":
        stem = _free(folder, label, [".ome.zarr", ".commands.json"])
        target = folder / f"{stem}.ome.zarr"
        write_ome_zarr(
            target,
            planes,
            width,
            height,
            name=stem,
            pixel_size_um=pixel_size,
            z_step_um=float(header["z_step_um"]),
            position_um=corner,
            extra=extra,
        )
        files.append(str(target))
        held_in = [str(target)] * len(planes)
    else:
        many = len(planes) > 1
        suffixes = [".commands.json"] + (
            [f"_z{i:03d}.ome.tif" for i in range(len(planes))] if many else [".ome.tif"]
        )
        stem = _free(folder, label, suffixes)
        for index, plane in enumerate(planes):
            name = f"{stem}_z{index:03d}" if many else stem
            plane_position = {**corner, "z": corner["z"] + index * float(header["z_step_um"])}
            description = ome_xml(
                name=name,
                width=width,
                height=height,
                pixel_size_um=pixel_size,
                position_um=plane_position,
                extra={key: str(value) for key, value in extra.items()},
            )
            target = folder / f"{name}.ome.tif"
            write_ome_tiff(target, plane, width, height, description)
            files.append(str(target))
        held_in = list(files)
    log_path = folder / f"{stem}.commands.json"
    log_path.write_text(json.dumps(ctx.log.since(log_mark), indent=2))
    # Every file saved is listed, the log too, so whoever moves or archives
    # this acquisition leaves nothing behind.
    return {
        "files": [*files, str(log_path)],
        "planes": describe_planes(held_in, position_um, float(header["z_step_um"])),
        "command_log": str(log_path),
    }


def describe_planes(
    held_in: list[str], position_um: dict[str, float], z_step_um: float
) -> list[dict]:
    """Say where on the sample each saved plane was taken, one entry per plane.

    ``held_in`` names the file each plane is in, bottom plane first. The
    pretend microscope has one channel and takes a stack upwards from where
    the stage stands, so plane ``z`` sits ``z`` steps above the stage height,
    at the stage's x and y. A saved file cannot tell this; the driver can,
    because it knows where it sent the stage.
    """
    return [
        {
            "path": path,
            "c": 0,
            "z": index,
            "t": 0,
            "x_um": float(position_um["x"]),
            "y_um": float(position_um["y"]),
            "z_um": float(position_um["z"]) + index * z_step_um,
        }
        for index, path in enumerate(held_in)
    ]
