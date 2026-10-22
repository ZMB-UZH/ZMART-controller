from __future__ import annotations

from array import array


def align_to_stage(
    planes: list[array], width: int, height: int, orientation: list[list[int]]
) -> tuple[list[array], int, int]:
    (a, b), (c, d) = orientation
    swapped = a == 0
    out_width, out_height = (height, width) if swapped else (width, height)
    aligned = []
    for plane in planes:
        out = array("H", bytes(2 * out_width * out_height))
        for row in range(height):
            v2 = 2 * row - (height - 1)
            base = row * width
            for col in range(width):
                u2 = 2 * col - (width - 1)
                x2 = a * u2 + b * v2
                y2 = c * u2 + d * v2
                out_col = (x2 + out_width - 1) // 2
                out_row = (y2 + out_height - 1) // 2
                out[out_row * out_width + out_col] = plane[base + col]
        aligned.append(out)
    return aligned, out_width, out_height
