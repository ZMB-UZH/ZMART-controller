from __future__ import annotations

from pathlib import Path
from typing import Any

from ..testing.mock_api import MockScope, read_mraw

NAME_LIMIT = 100


class VendorError(Exception):
    def __init__(self, command: str, code: int, message: str) -> None:
        super().__init__(f"{command} refused by the microscope software: {message} (code {code})")
        self.command = command
        self.code = code
        self.message = message


class MockScopeConnection:
    def __init__(self, scope: MockScope) -> None:
        self.scope = scope

    @classmethod
    def start(
        cls, *, output_folder: Path, token: str, instant: bool = False
    ) -> MockScopeConnection:
        output_folder.mkdir(parents=True, exist_ok=True)
        if instant:
            scope = MockScope.instant(output_folder=output_folder, token="mock-token")
        else:
            scope = MockScope(output_folder=output_folder, token="mock-token")
        connection = cls(scope)
        try:
            connection._call("Login", token=token)
        except VendorError as exc:
            scope.shutdown()
            raise RuntimeError(
                f"the microscope software refused the login ({exc.message}); "
                f"check the 'token' entry of the connection"
            ) from None
        return connection

    def _call(self, command: str, **arguments: Any) -> dict[str, Any]:
        reply = self.scope.send(command, **arguments)
        if not reply["ok"]:
            raise VendorError(command, reply["code"], reply["message"])
        return reply["result"]

    def version(self) -> dict[str, str]:
        return dict(self._call("GetVersion"))

    def close(self) -> None:
        try:
            self._call("Logout")
        except (VendorError, ConnectionError):
            pass
        self.scope.shutdown()

    def hardware(self) -> dict[str, Any]:
        return self._call("GetHardware")

    def stage_position(self) -> dict[str, float]:
        result = self._call("GetStagePosition")
        return {"x": float(result["x"]), "y": float(result["y"])}

    def focus_position(self) -> dict[str, float]:
        result = self._call("GetFocus")
        return {"focus": float(result["focus"]), "piezo": float(result["piezo"])}

    def settings(self) -> dict[str, Any]:
        return dict(self._call("GetSettings"))

    def status(self) -> dict[str, Any]:
        return self._call("GetStatus")

    def read_image_file(self, path: str | Path) -> tuple[dict[str, Any], list]:
        return read_mraw(path)

    def move_stage(self, *, x: float, y: float) -> None:
        self._call("MoveStage", x=x, y=y)

    def move_focus(self, *, focus: float, piezo: float) -> None:
        self._call("MoveFocus", focus=focus, piezo=piezo)

    def set_setting(self, name: str, value: float) -> None:
        self._call("SetSetting", name=name, value=value)

    def set_objective(self, slot: int) -> None:
        self._call("SetObjective", slot=slot)

    def start_acquisition(self, name: str, *, z_planes: int, z_step_um: float) -> str | None:
        result = self._call("StartAcquisition", name=name, z_planes=z_planes, z_step_um=z_step_um)
        return result.get("file")

    def abort(self) -> None:
        self._call("Abort")
