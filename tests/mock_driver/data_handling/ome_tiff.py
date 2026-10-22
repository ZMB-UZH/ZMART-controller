from __future__ import annotations

import struct
import sys
import uuid
from array import array
from pathlib import Path
from xml.sax.saxutils import quoteattr

_TEXT, _SHORT, _LONG = 2, 3, 4


def ome_xml(
    *,
    name: str,
    width: int,
    height: int,
    pixel_size_um: float,
    position_um: dict[str, float],
    extra: dict[str, str],
) -> str:
    annotations = "".join(
        f"<M K={quoteattr(key)}>{_escape(value)}</M>" for key, value in sorted(extra.items())
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06" '
        f'Creator="ZMART mock driver" UUID="urn:uuid:{uuid.uuid4()}">'
        f'<Image ID="Image:0" Name={quoteattr(name)}>'
        f'<Pixels ID="Pixels:0" DimensionOrder="XYZCT" Type="uint16" '
        f'SizeX="{width}" SizeY="{height}" SizeZ="1" SizeC="1" SizeT="1" '
        f'PhysicalSizeX="{pixel_size_um}" PhysicalSizeXUnit="µm" '
        f'PhysicalSizeY="{pixel_size_um}" PhysicalSizeYUnit="µm">'
        '<Channel ID="Channel:0:0" SamplesPerPixel="1"/>'
        '<TiffData IFD="0" PlaneCount="1"/>'
        f'<Plane TheZ="0" TheC="0" TheT="0" '
        f'PositionX="{position_um["x"]}" PositionXUnit="µm" '
        f'PositionY="{position_um["y"]}" PositionYUnit="µm" '
        f'PositionZ="{position_um["z"]}" PositionZUnit="µm"/>'
        "</Pixels>"
        '<AnnotationRef ID="Annotation:0"/>'
        "</Image>"
        '<StructuredAnnotations><MapAnnotation ID="Annotation:0" '
        'Namespace="zmart/acquisition"><Value>'
        f"{annotations}"
        "</Value></MapAnnotation></StructuredAnnotations>"
        "</OME>"
    )


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_ome_tiff(path: Path, plane: array, width: int, height: int, description: str) -> None:
    text = description.encode("utf-8") + b"\0"
    pixels = array("H", plane)
    if sys.byteorder == "big":
        pixels.byteswap()
    data = pixels.tobytes()
    tags = [
        (256, _LONG, 1, width),
        (257, _LONG, 1, height),
        (258, _SHORT, 1, 16),
        (259, _SHORT, 1, 1),
        (262, _SHORT, 1, 1),
        (270, _TEXT, len(text), None),
        (273, _LONG, 1, None),
        (277, _SHORT, 1, 1),
        (278, _LONG, 1, height),
        (279, _LONG, 1, len(data)),
    ]
    ifd_offset = 8
    ifd_size = 2 + 12 * len(tags) + 4
    text_offset = ifd_offset + ifd_size
    data_offset = text_offset + len(text)
    if data_offset % 2:
        data_offset += 1
    entries = b""
    for tag, kind, count, value in tags:
        if tag == 270:
            value = text_offset
        elif tag == 273:
            value = data_offset
        if kind == _SHORT:
            field = struct.pack("<HHIHH", tag, kind, count, value, 0)
        else:
            field = struct.pack("<HHII", tag, kind, count, value)
        entries += field
    with path.open("wb") as stream:
        stream.write(b"II*\0" + struct.pack("<I", ifd_offset))
        stream.write(struct.pack("<H", len(tags)) + entries + struct.pack("<I", 0))
        stream.write(text)
        stream.write(b"\0" * (data_offset - text_offset - len(text)))
        stream.write(data)
