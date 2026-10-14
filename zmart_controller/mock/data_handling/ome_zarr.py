"""Writing OME-Zarr: a folder that holds a whole z-stack.

OME-Zarr (also called OME-NGFF, the "next-generation file format") stores
an image as a folder of small pieces with JSON descriptions. It is the
format of choice for large and cloud-hosted data, and tools such as napari
and neuroglancer open it directly. This writer produces version 0.5 of the
format, the one the rest of ZMART reads and writes, stored as Zarr version 3:
one uncompressed piece per z-plane, using only the Python standard library.

The image has one level, the full resolution. Its description still says how
smaller levels would be made, by averaging (``"type": "mean"``), because a
viewer that builds its own zoomed-out copies reads that to know it may
average the pixels too.

Author: Thom de Hoog, Center for Microscopy and Image Analysis (ZMB),
University of Zurich (thom.dehoog@zmb.uzh.ch, thomdehoog@gmail.com).
"""

from __future__ import annotations

import json
import sys
from array import array
from pathlib import Path
from typing import Any


def write_ome_zarr(
    path: Path,
    planes: list[array],
    width: int,
    height: int,
    *,
    name: str,
    pixel_size_um: float,
    z_step_um: float,
    position_um: dict[str, float],
    extra: dict[str, Any],
) -> None:
    """Write ``planes`` as one OME-Zarr image with axes z, y and x.

    ``position_um`` is the user position of the first plane's corner pixel;
    it becomes the image's translation, so viewers place it correctly.
    """
    path.mkdir(parents=True)
    axes = [{"name": axis, "type": "space", "unit": "micrometer"} for axis in ("z", "y", "x")]
    multiscale = {
        "name": name,
        "axes": axes,
        "datasets": [
            {
                "path": "0",
                "coordinateTransformations": [
                    {"type": "scale", "scale": [z_step_um, pixel_size_um, pixel_size_um]},
                    {
                        "type": "translation",
                        "translation": [position_um["z"], position_um["y"], position_um["x"]],
                    },
                ],
            }
        ],
        "type": "mean",
    }
    group = {
        "zarr_format": 3,
        "node_type": "group",
        "attributes": {"ome": {"version": "0.5", "multiscales": [multiscale]}, "zmart": extra},
    }
    (path / "zarr.json").write_text(json.dumps(group, indent=2))
    level = path / "0"
    level.mkdir()
    (level / "zarr.json").write_text(
        json.dumps(
            {
                "zarr_format": 3,
                "node_type": "array",
                "shape": [len(planes), height, width],
                "data_type": "uint16",
                "chunk_grid": {
                    "name": "regular",
                    "configuration": {"chunk_shape": [1, height, width]},
                },
                "chunk_key_encoding": {"name": "default", "configuration": {"separator": "/"}},
                "fill_value": 0,
                "codecs": [{"name": "bytes", "configuration": {"endian": "little"}}],
                "dimension_names": ["z", "y", "x"],
            },
            indent=2,
        )
    )
    for index, plane in enumerate(planes):
        piece = level / "c" / str(index) / "0"
        piece.mkdir(parents=True)
        pixels = array("H", plane)
        if sys.byteorder == "big":
            pixels.byteswap()
        (piece / "0").write_bytes(pixels.tobytes())
