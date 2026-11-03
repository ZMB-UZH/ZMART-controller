from __future__ import annotations

import json
import struct
import sys
import uuid
from array import array
from pathlib import Path
from xml.sax.saxutils import quoteattr

_TEXT, _SHORT, _LONG = 2, 3, 4

ZMART_NOTE = "zmart/position"


def placement(*, pixel_size_um: float, z_step_um: float, first_voxel_um: dict[str, float]) -> dict:
    return {
        "type": "mean",
        "axes": [
            {"name": "t", "type": "time"},
            {"name": "c", "type": "channel"},
            *({"name": axis, "type": "space", "unit": "micrometer"} for axis in ("z", "y", "x")),
        ],
        "datasets": [
            {
                "path": "0",
                "coordinateTransformations": [
                    {"type": "scale", "scale": [1.0, 1.0, z_step_um, pixel_size_um, pixel_size_um]},
                    {
                        "type": "translation",
                        "translation": [
                            0.0,
                            0.0,
                            first_voxel_um["z"],
                            first_voxel_um["y"],
                            first_voxel_um["x"],
                        ],
                    },
                ],
            }
        ],
    }


def ome_xml(
    *,
    name: str,
    width: int,
    height: int,
    planes: int,
    pixel_size_um: float,
    z_step_um: float,
    first_voxel_um: dict[str, float],
    extra: dict[str, str],
) -> str:
    annotations = "".join(
        f"<M K={quoteattr(key)}>{_escape(value)}</M>" for key, value in sorted(extra.items())
    )
    where = json.dumps(
        [placement(pixel_size_um=pixel_size_um, z_step_um=z_step_um, first_voxel_um=first_voxel_um)]
    )
    plane_entries = "".join(
        f'<Plane TheZ="{z}" TheC="0" TheT="0" '
        f'PositionZ="{first_voxel_um["z"] + z * z_step_um}" PositionZUnit="µm"/>'
        for z in range(planes)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06" '
        f'Creator="ZMART mock driver" UUID="urn:uuid:{uuid.uuid4()}">'
        f'<Image ID="Image:0" Name={quoteattr(name)}>'
        f'<Pixels ID="Pixels:0" DimensionOrder="XYZCT" Type="uint16" '
        f'SizeX="{width}" SizeY="{height}" SizeZ="{planes}" SizeC="1" SizeT="1" '
        f'PhysicalSizeX="{pixel_size_um}" PhysicalSizeXUnit="µm" '
        f'PhysicalSizeY="{pixel_size_um}" PhysicalSizeYUnit="µm" '
        f'PhysicalSizeZ="{z_step_um}" PhysicalSizeZUnit="µm">'
        '<Channel ID="Channel:0:0" SamplesPerPixel="1"/>'
        f'<TiffData IFD="0" PlaneCount="{planes}"/>'
        f"{plane_entries}"
        "</Pixels>"
        '<AnnotationRef ID="Annotation:0"/>'
        '<AnnotationRef ID="Annotation:1"/>'
        "</Image>"
        "<StructuredAnnotations>"
        '<MapAnnotation ID="Annotation:0" Namespace="zmart/acquisition"><Value>'
        f"{annotations}"
        "</Value></MapAnnotation>"
        f'<MapAnnotation ID="Annotation:1" Namespace="{ZMART_NOTE}"><Value>'
        f'<M K="multiscales">{_escape(where)}</M>'
        "</Value></MapAnnotation>"
        "</StructuredAnnotations>"
        "</OME>"
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_ome_tiff(
    path: Path, planes: list[array], width: int, height: int, description: str
) -> None:
    text = description.encode("utf-8") + b"\0"
    stream = bytearray(b"II*\0" + struct.pack("<I", 8))
    for index, plane in enumerate(planes):
        pixels = array("H", plane)
        if sys.byteorder == "big":
            pixels.byteswap()
        data = pixels.tobytes()
        first = index == 0
        tags = [
            (256, _LONG, 1, width),
            (257, _LONG, 1, height),
            (258, _SHORT, 1, 16),
            (259, _SHORT, 1, 1),
            (262, _SHORT, 1, 1),
            *([(270, _TEXT, len(text), None)] if first else []),
            (273, _LONG, 1, None),
            (277, _SHORT, 1, 1),
            (278, _LONG, 1, height),
            (279, _LONG, 1, len(data)),
        ]
        ifd_offset = len(stream)
        text_offset = ifd_offset + 2 + 12 * len(tags) + 4
        data_offset = text_offset + (len(text) if first else 0)
        data_offset += data_offset % 2
        next_offset = data_offset + len(data)
        next_offset += next_offset % 2
        entries = b""
        for tag, kind, count, value in tags:
            if tag == 270:
                value = text_offset
            elif tag == 273:
                value = data_offset
            if kind == _SHORT:
                entries += struct.pack("<HHIHH", tag, kind, count, value, 0)
            else:
                entries += struct.pack("<HHII", tag, kind, count, value)
        last = index == len(planes) - 1
        stream += struct.pack("<H", len(tags)) + entries
        stream += struct.pack("<I", 0 if last else next_offset)
        if first:
            stream += text
        stream += b"\0" * (data_offset - len(stream))
        stream += data
        stream += b"\0" * (next_offset - len(stream))
    path.write_bytes(bytes(stream))
