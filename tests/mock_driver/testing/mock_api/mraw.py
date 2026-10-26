from __future__ import annotations

import json
import sys
from array import array
from pathlib import Path
from typing import Any

FORMAT = "MRAW"
FORMAT_VERSION = 1


def write_header(path: Path, header: dict[str, Any]) -> None:
    line = json.dumps({"format": FORMAT, "version": FORMAT_VERSION, **header})
    path.write_bytes(line.encode("utf-8") + b"\n")


def append_planes(path: Path, planes: list[array]) -> None:
    with path.open("ab") as handle:
        for plane in planes:
            data = array("H", plane)
            if sys.byteorder == "big":
                data.byteswap()
            handle.write(data.tobytes())


def read_mraw(path: str | Path) -> tuple[dict[str, Any], list[array]]:
    raw = Path(path).read_bytes()
    first_line, newline, body = raw.partition(b"\n")
    if not newline:
        raise ValueError(f"{path} has no description line; it is not an .mraw file")
    try:
        header = json.loads(first_line)
    except ValueError:
        raise ValueError(f"{path} does not start with a JSON description line") from None
    if not isinstance(header, dict) or header.get("format") != FORMAT:
        raise ValueError(f"{path} is not an .mraw file")
    plane_values = header["width"] * header["height"]
    expected = plane_values * header["planes"] * 2
    if len(body) < expected:
        raise ValueError(
            f"{path} is incomplete: {len(body)} of {expected} pixel bytes are written. "
            f"The acquisition may still be running."
        )
    data = array("H")
    data.frombytes(body[:expected])
    if sys.byteorder == "big":
        data.byteswap()
    planes = [
        data[index * plane_values : (index + 1) * plane_values] for index in range(header["planes"])
    ]
    return header, planes
