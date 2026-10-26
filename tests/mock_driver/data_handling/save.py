from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .collect import wait_for_file
from .ome_tiff import ome_xml, write_ome_tiff
from .ome_zarr import write_ome_zarr
from .orient import align_to_stage

FORMATS = ("ome-tiff", "ome-zarr")

_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_name(text: str) -> str:
    cleaned = _UNSAFE.sub("_", text).strip("._")
    return cleaned or "image"


def _free(folder: Path, stem: str, suffixes: list[str]) -> str:
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
    acquisition_type: str,
    folder: Path,
    image_format: str,
    position_um: dict[str, float],
    log_mark: int,
) -> dict[str, Any]:
    if image_format not in FORMATS:
        raise ValueError(f"unknown format {image_format!r}; choose one of {list(FORMATS)}")
    header, planes = wait_for_file(ctx, vendor_file)
    registration = ctx.config.image_stage_registration
    slot = str(header["objective"]["slot"])
    pixel_size = float(registration["pixel_size_um"].get(slot, header["pixel_size_um"]))
    planes, width, height = align_to_stage(
        planes, header["width"], header["height"], registration["orientation"]
    )
    corner = {
        "x": position_um["x"] - (width / 2) * pixel_size,
        "y": position_um["y"] - (height / 2) * pixel_size,
        "z": position_um["z"],
    }
    first_voxel = {
        "x": corner["x"] + pixel_size / 2,
        "y": corner["y"] + pixel_size / 2,
        "z": position_um["z"],
    }
    extra = {
        "position_label": position_label,
        "acquisition_type": acquisition_type,
        "objective": header["objective"]["name"],
        "vendor_file": str(vendor_file),
        "registration": ctx.config.sources["image_stage_registration"],
        "calibration": ctx.config.sources["optical_calibration"],
    }
    label = safe_name(f"{acquisition_type}_{position_label}")
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
            position_um=first_voxel,
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
    return {
        "files": [*files, str(log_path)],
        "planes": describe_planes(held_in, position_um, float(header["z_step_um"])),
        "command_log": str(log_path),
    }


def describe_planes(
    held_in: list[str], position_um: dict[str, float], z_step_um: float
) -> list[dict]:
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
