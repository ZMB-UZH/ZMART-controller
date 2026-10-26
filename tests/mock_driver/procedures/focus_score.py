from __future__ import annotations

from collections.abc import Sequence


def brenner(plane: Sequence[int], width: int) -> float:
    total = 0
    for start in range(0, len(plane), width):
        row = plane[start : start + width]
        total += sum((row[i + 2] - row[i]) ** 2 for i in range(len(row) - 2))
    return float(total)
