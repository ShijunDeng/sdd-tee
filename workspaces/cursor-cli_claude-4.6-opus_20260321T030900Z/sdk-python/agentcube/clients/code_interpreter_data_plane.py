"""Data-plane routes for an active code interpreter session."""

from __future__ import annotations

import json
from typing import Any

from requests import Session

from agentcube.exceptions import CommandExecutionError, DataPlaneError
from agentcube.utils.http import create_session


class CodeInterpreterDataPlaneClient:
    """
    Routes through ``/v1/namespaces/.../code-interpreters/.../invocations/api/...``.
    """

    def __init__(
        self,
        base_url: str,
        namespace: str,
        interpreter_id: str,
        session: Session | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.namespace = namespace
        self.interpreter_id = interpreter_id
        self.session = session or create_session()
        self.headers = dict(headers or {})
        self.timeout = timeout
        self._owns_session = session is None
        self._root = (
            f"{self.base_url}/v1/namespaces/{namespace}"
            f"/code-interpreters/{interpreter_id}/invocations/api"
        )

    def _url(self, suffix: str) -> str:
        return f"{self._root}/{suffix.lstrip('/')}"

    def _post(self, suffix: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self.session.post(self._url(suffix), json=payload, headers=self.headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise DataPlaneError(f"{suffix} failed: {resp.status_code} {resp.text}")
        if not resp.content:
            return {}
        try:
            return resp.json()
        except json.JSONDecodeError as exc:
            raise DataPlaneError(f"Invalid JSON from {suffix}: {resp.text}") from exc

    def execute_command(self, command: str, cwd: str | None = None) -> dict[str, Any]:
        """Run a shell command remotely."""
        body: dict[str, Any] = {"command": command}
        if cwd:
            body["cwd"] = cwd
        data = self._post("execute-command", body)
        exit_code = int(data.get("exitCode", data.get("exit_code", 0)))
        if exit_code != 0:
            raise CommandExecutionError(
                f"Command failed with exit code {exit_code}",
                exit_code=exit_code,
                stderr=str(data.get("stderr", "")),
                command=command,
            )
        return data

    def run_code(self, code: str, language: str = "python") -> dict[str, Any]:
        """Execute interpreted code."""
        return self._post("run-code", {"code": code, "language": language})

    def write_file(self, path: str, content: str) -> dict[str, Any]:
        """Write text content to a remote path."""
        return self._post("write-file", {"path": path, "content": content})

    def upload_file(self, path: str, data: bytes, filename: str | None = None) -> dict[str, Any]:
        """Upload a binary file to the remote workspace."""
        files = {"file": (filename or path.split("/")[-1], data)}
        resp = self.session.post(
            self._url("upload-file"),
            data={"path": path},
            files=files,
            headers={k: v for k, v in self.headers.items() if k.lower() != "content-type"},
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise DataPlaneError(f"upload_file failed: {resp.status_code} {resp.text}")
        return resp.json() if resp.content else {}

    def download_file(self, path: str) -> bytes:
        """Download a remote file as bytes."""
        resp = self.session.post(
            self._url("download-file"),
            json={"path": path},
            headers=self.headers,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise DataPlaneError(f"download_file failed: {resp.status_code} {resp.text}")
        return resp.content

    def list_files(self, path: str = ".") -> list[dict[str, Any]]:
        """List files under a remote directory."""
        data = self._post("list-files", {"path": path})
        return list(data.get("files", data.get("entries", [])))

    def close(self) -> None:
        if self._owns_session:
            self.session.close()
