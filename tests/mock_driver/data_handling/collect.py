from __future__ import annotations

import time
from typing import Any

from .. import get_actions as get

POLL_INTERVAL_S = 0.01


def wait_for_file(ctx, file: str, *, timeout_s: float = 30.0) -> tuple[dict[str, Any], list]:
    deadline = time.monotonic() + timeout_s
    while True:
        status = get.status(ctx)
        if status.known and status.value["last_acquisition"] is not None:
            last = status.value["last_acquisition"]
            if last["file"] == file and last["state"] == "aborted":
                raise RuntimeError(
                    f"the acquisition writing {file} was stopped; the file is incomplete"
                )
            if last["file"] == file and last["state"] == "done":
                try:
                    return ctx.vendor.read_image_file(file)
                except ValueError:
                    pass
        if time.monotonic() >= deadline:
            raise RuntimeError(f"{file} was still incomplete after {timeout_s} s")
        time.sleep(POLL_INTERVAL_S)
