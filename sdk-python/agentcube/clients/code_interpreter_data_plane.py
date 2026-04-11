"""Code Interpreter Data Plane client for AgentCube SDK."""

import base64
import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import requests

from ..utils.http import create_session
from ..utils.log import get_logger


class CodeInterpreterDataPlaneClient:
    """Client for interacting with the Code Interpreter data plane (Router)."""

    def __init__(
        self,
        session_id: str,
        router_url: Optional[str] = None,
        namespace: Optional[str] = None,
        cr_name: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: int = 120,
        connect_timeout: float = 5.0,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
    ):
        """Initialize the Code Interpreter Data Plane client.

        Args:
            session_id: The session ID for requests.
            router_url: URL of the Router service.
            namespace: Kubernetes namespace.
            cr_name: Code Interpreter custom resource name.
            base_url: Explicit base URL (overrides router_url/namespace/cr_name).
            timeout: Read timeout in seconds.
            connect_timeout: Connect timeout in seconds.
            pool_connections: Number of connections to pool.
            pool_maxsize: Maximum number of connections in the pool.
        """
        self.logger = get_logger(__name__)
        self.session_id = session_id
        self.timeout = timeout
        self.connect_timeout = connect_timeout

        if base_url:
            self.base_url = base_url
        else:
            if not router_url:
                raise ValueError("router_url must be provided if base_url is not set")
            base_path = f"/v1/namespaces/{namespace}/code-interpreters/{cr_name}/invocations/"
            self.base_url = urljoin(router_url, base_path)

        self.session = create_session(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
        )
        self.session.headers["x-agentcube-session-id"] = session_id

    def _request(
        self,
        method: str,
        endpoint: str,
        body: Optional[bytes] = None,
        **kwargs,
    ) -> requests.Response:
        """Make an HTTP request to the data plane.

        Args:
            method: HTTP method.
            endpoint: Relative endpoint path.
            body: Optional request body bytes.
            **kwargs: Additional arguments passed to requests.

        Returns:
            The HTTP response.
        """
        url = urljoin(self.base_url, endpoint)
        headers = kwargs.pop("headers", {})
        kwargs.pop("timeout", None)

        if body:
            headers["Content-Type"] = "application/json"
            response = self.session.request(
                method,
                url,
                data=body,
                headers=headers,
                timeout=(self.connect_timeout, self.timeout),
                **kwargs,
            )
        else:
            response = self.session.request(
                method,
                url,
                headers=headers,
                timeout=(self.connect_timeout, self.timeout),
                **kwargs,
            )

        return response

    def execute_command(
        self,
        command: Union[str, List[str]],
        timeout: Optional[float] = None,
    ) -> str:
        """Execute a command in the code interpreter.

        Args:
            command: Command string or list of command parts.
            timeout: Timeout in seconds. Defaults to self.timeout.

        Returns:
            The command output (stdout).

        Raises:
            CommandExecutionError: If the command returns non-zero exit code.
        """
        effective_timeout = timeout if timeout is not None else self.timeout

        if isinstance(command, str):
            cmd_list = [command]
        else:
            cmd_list = command

        timeout_str = f"{int(effective_timeout)}s"
        payload = {
            "command": cmd_list,
            "timeout": timeout_str,
        }

        import json
        body = json.dumps(payload).encode("utf-8")

        read_timeout = effective_timeout + 2.0

        response = self._request(
            "POST",
            "api/execute",
            body=body,
            timeout=(self.connect_timeout, read_timeout),
        )
        response.raise_for_status()

        data = response.json()
        exit_code = data.get("exit_code", 0)
        stderr = data.get("stderr", "")
        stdout = data.get("stdout", "")

        if exit_code != 0:
            from ..exceptions import CommandExecutionError
            raise CommandExecutionError(
                exit_code=exit_code,
                stderr=stderr,
                command=cmd_list,
            )

        return stdout

    def run_code(
        self,
        language: str,
        code: str,
        timeout: Optional[float] = None,
    ) -> str:
        """Run code in the specified language.

        Args:
            language: Programming language (python, py, python3, etc.).
            code: Code to execute.
            timeout: Timeout in seconds.

        Returns:
            The code output.
        """
        if language in ("python", "py", "python3"):
            import time
            timestamp = int(time.time() * 1000)
            remote_path = f"/tmp/code_{timestamp}.py"
            self.write_file(code, remote_path)
            command = f"python3 {remote_path}"
            return self.execute_command(command, timeout)
        else:
            raise ValueError(f"Unsupported language: {language}")

    def write_file(self, content: str, remote_path: str) -> None:
        """Write content to a file in the remote environment.

        Args:
            content: File content.
            remote_path: Remote file path.
        """
        import json

        content_b64 = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        payload = {
            "path": remote_path,
            "content": content_b64,
            "mode": "0644",
        }

        body = json.dumps(payload).encode("utf-8")
        response = self._request("POST", "api/files", body=body)
        response.raise_for_status()

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a local file to the remote environment.

        Args:
            local_path: Path to local file.
            remote_path: Remote file path.
        """
        url = urljoin(self.base_url, "api/files")

        with open(local_path, "rb") as f:
            files = {"file": f}
            data = {
                "path": remote_path,
                "mode": "0644",
            }
            headers = {
                "x-agentcube-session-id": self.session_id,
            }

            response = self.session.post(
                url,
                files=files,
                data=data,
                headers=headers,
                timeout=(self.connect_timeout, self.timeout),
            )
            response.raise_for_status()

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the remote environment.

        Args:
            remote_path: Remote file path.
            local_path: Local file path to save to.
        """
        clean_path = remote_path.lstrip("/")
        endpoint = f"api/files/{clean_path}"

        response = self._request(
            "GET",
            endpoint,
            stream=True,
        )
        response.raise_for_status()

        with open(local_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

    def list_files(self, path: str = ".") -> Any:
        """List files in the remote environment.

        Args:
            path: Path to list.

        Returns:
            The file listing response data.
        """
        params = {"path": path}

        response = self._request(
            "GET",
            "api/files",
            params=params,
        )
        response.raise_for_status()
        return response.json()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()
