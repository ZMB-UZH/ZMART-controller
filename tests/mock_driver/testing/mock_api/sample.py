from __future__ import annotations

import hashlib
import math
import random
import struct
from array import array
from dataclasses import dataclass

CELL_UM = 20.0

SPOT_SIGMA_UM = 1.2

BLUR_PER_UM_DEFOCUS = 0.35

MAX_SIGMA_UM = 40.0

BACKGROUND = 100.0


@dataclass(frozen=True)
class Tilt:
    x0: float = 50_000.0
    y0: float = 37_500.0
    z0: float = 5_000.0
    slope_x: float = 0.001
    slope_y: float = -0.0005

    def focus_at(self, x: float, y: float) -> float:
        return self.z0 + self.slope_x * (x - self.x0) + self.slope_y * (y - self.y0)


def _spot_in_cell(seed: int, cell_x: int, cell_y: int) -> tuple[float, float, float]:
    digest = hashlib.blake2b(struct.pack("<qqq", seed, cell_x, cell_y), digest_size=12).digest()
    a, b, c = struct.unpack("<III", digest)
    scale = 1.0 / 2**32
    x = (cell_x + 0.15 + 0.7 * a * scale) * CELL_UM
    y = (cell_y + 0.15 + 0.7 * b * scale) * CELL_UM
    brightness = 0.3 + 0.7 * c * scale
    return x, y, brightness


def render(
    *,
    seed: int,
    width: int,
    height: int,
    pixel_size_um: float,
    centre_x: float,
    centre_y: float,
    defocus_um: float,
    orientation: tuple[tuple[int, int], tuple[int, int]],
    signal: float,
    noise: random.Random | None,
) -> array:
    sigma = math.hypot(SPOT_SIGMA_UM, BLUR_PER_UM_DEFOCUS * defocus_um)
    pixels = [BACKGROUND] * (width * height)
    if sigma <= MAX_SIGMA_UM:
        peak = signal * (SPOT_SIGMA_UM / sigma) ** 2
        reach_um = 4.0 * sigma
        (a, b), (c, d) = orientation
        half_w_um = width / 2 * pixel_size_um
        half_h_um = height / 2 * pixel_size_um
        span_um = max(half_w_um, half_h_um) + reach_um
        first_x = math.floor((centre_x - span_um) / CELL_UM)
        last_x = math.floor((centre_x + span_um) / CELL_UM)
        first_y = math.floor((centre_y - span_um) / CELL_UM)
        last_y = math.floor((centre_y + span_um) / CELL_UM)
        two_sigma_sq = 2.0 * sigma * sigma
        reach_px = int(math.ceil(reach_um / pixel_size_um))
        for cell_x in range(first_x, last_x + 1):
            for cell_y in range(first_y, last_y + 1):
                spot_x, spot_y, brightness = _spot_in_cell(seed, cell_x, cell_y)
                dx = spot_x - centre_x
                dy = spot_y - centre_y
                u_um = a * dx + c * dy
                v_um = b * dx + d * dy
                col_c = (u_um + half_w_um) / pixel_size_um - 0.5
                row_c = (v_um + half_h_um) / pixel_size_um - 0.5
                col_lo = max(0, int(col_c) - reach_px)
                col_hi = min(width - 1, int(col_c) + reach_px)
                row_lo = max(0, int(row_c) - reach_px)
                row_hi = min(height - 1, int(row_c) + reach_px)
                if col_lo > col_hi or row_lo > row_hi:
                    continue
                amplitude = peak * brightness
                for row in range(row_lo, row_hi + 1):
                    dv = (row - row_c) * pixel_size_um
                    base = row * width
                    for col in range(col_lo, col_hi + 1):
                        du = (col - col_c) * pixel_size_um
                        pixels[base + col] += amplitude * math.exp(
                            -(du * du + dv * dv) / two_sigma_sq
                        )
    out = array("H", bytes(2 * width * height))
    for index, value in enumerate(pixels):
        if noise is not None:
            value += noise.gauss(0.0, math.sqrt(max(value, 1.0)))
        out[index] = min(65_535, max(0, int(round(value))))
    return out
