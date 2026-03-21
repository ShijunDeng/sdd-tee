"""High-level code interpreter session helper."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from agentcube.clients.code_interpreter_data_plane import CodeInterpreterDataPlaneClient
from agentcube.clients.control_plane import ControlPlaneClient


class CodeInterpreterClient:
    """
    Context manager tying control-plane session creation to data-plane calls.

    Uses ``ControlPlaneClient`` + ``CodeInterpreterDataPlaneClient``.
    """

    def __init__(
        self,
        control_plane_url: str,
        namespace: str,
        headers: dict[str, str] | None = None,
        create_body: dict[str, Any] | None = None,
    ) -> None:
        self._cp = ControlPlaneClient(control_plane_url, headers=headers)
        self._namespace = namespace
        self._create_body = create_body or {}
        self._dp: CodeInterpreterDataPlaneClient | None = None
        self._session_payload: dict[str, Any] | None = None
        self._interpreter_id: str | None = None

    def __enter__(self) -> CodeInterpreterClient:
        self._session_payload = self._cp.create_session(self._create_body)
        self._interpreter_id = str(
            self._session_payload.get("id")
            or self._session_payload.get("interpreterId")
            or self._session_payload.get("interpreter_id")
            or ""
        )
        if not self._interpreter_id:
            raise ValueError("create_session response missing interpreter id")
        self._dp = CodeInterpreterDataPlaneClient(
            self._cp.base_url,
            namespace=self._namespace,
            interpreter_id=self._interpreter_id,
            session=self._cp.session,
            headers=self._cp.headers,
        )
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.stop()
        self._cp.close()

    @property
    def interpreter_id(self) -> str:
        if not self._interpreter_id:
            raise RuntimeError("Client is not started; use 'with' context")
        return self._interpreter_id

    def stop(self) -> None:
        """Delete remote session and close data-plane resources."""
        if self._dp:
            self._dp.close()
            self._dp = None
        if self._session_payload:
            sid = str(
                self._session_payload.get("sessionId")
                or self._session_payload.get("session_id")
                or self._interpreter_id
                or ""
            )
            if sid:
                try:
                    self._cp.delete_session(sid)
                except Exception:
                    pass
            self._session_payload = None
        self._interpreter_id = None

    def execute_command(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        if not self._dp:
            raise RuntimeError("Client is not started")
        return self._dp.execute_command(command, cwd=cwd)

    def run_code(self, code: str, language: str = "python") -> dict[str, Any]:
        if not self._dp:
            raise RuntimeError("Client is not started")
        return self._dp.run_code(code, language=language)

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        if not self._dp:
            raise RuntimeError("Client is not started")
        return self._dp.write_file(path, content)

    def upload_file(self, path: str, data: bytes, filename: str | None = None) -> dict[str, Any]:
        if not self._dp:
            raise RuntimeError("Client is not started")
        return self._dp.upload_file(path, data, filename=filename)

    def download_file(self, path: str) -> bytes:
        if not self._dp:
            raise RuntimeError("Client is not started")
        return self._dp.download_file(path)

    def list_files(self, path: str = ".") -> list[dict[str, Any]]:
        if not self._dp:
            raise RuntimeError("Client is not started")
        return self._dp.list_files(path)
