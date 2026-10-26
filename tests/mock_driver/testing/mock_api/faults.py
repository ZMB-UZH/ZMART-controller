from __future__ import annotations

FAULTS: dict[str, str] = {
    "busy": (
        "Temporary. The software answers error 100, 'System busy, try again later'. "
        "Nothing is applied. Trying again should work."
    ),
    "out_of_range": (
        "Bad request. The software answers error 201, 'Value out of range'. Nothing is applied."
    ),
    "hardware_fault": (
        "Permanent. The software answers error 300, 'Hardware fault: controller not "
        "responding'. Nothing is applied."
    ),
    "unknown_error": (
        "Not recognisable. The software answers error 999 with a message no driver knows. "
        "A driver should treat it as permanent."
    ),
    "timeout": (
        "Temporary, and tricky. The command IS applied, but the reply is lost and the call "
        "raises TimeoutError. A driver cannot know whether it worked, so it must read back."
    ),
    "ignore": (
        "Unconfirmed. The software answers 'OK' but does not apply the command. Only "
        "reading back reveals it."
    ),
    "stale": (
        "Unknown reading. A get command returns the answer it gave last time, not the "
        "current value."
    ),
    "disconnect": (
        "Connection lost. The software closes; this and every later call raises "
        "ConnectionError until MockScope.restart()."
    ),
}


class Faults:
    def __init__(self) -> None:
        self._pending: list[dict] = []

    def add(self, command: str, fault: str, *, times: int | None = 1) -> None:
        if fault not in FAULTS:
            raise ValueError(f"unknown fault {fault!r}; choose one of {sorted(FAULTS)}")
        if times is not None and times < 1:
            raise ValueError("times must be at least 1, or None for every time")
        self._pending.append({"command": command, "fault": fault, "left": times})

    def clear(self) -> None:
        self._pending.clear()

    def take(self, command: str) -> str | None:
        for entry in self._pending:
            if entry["command"] in (command, "*"):
                if entry["left"] is not None:
                    entry["left"] -= 1
                    if entry["left"] == 0:
                        self._pending.remove(entry)
                return entry["fault"]
        return None

    def __len__(self) -> int:
        return len(self._pending)
