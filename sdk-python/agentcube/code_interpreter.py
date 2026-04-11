"""Code Interpreter Client for AgentCube SDK."""

import logging
import os
from typing import Any, Dict, List, Optional

from .clients.control_plane import ControlPlaneClient
from .clients.code_interpreter_data_plane import CodeInterpreterDataPlaneClient
from .utils.log import get_logger


class CodeInterpreterClient:
    """High-level client for Code Interpreter operations.

    This client manages session lifecycle and provides a convenient interface
    for executing commands, running code, and managing files.
    """

    def __init__(
        self,
        name: str = "my-interpreter",
        namespace: str = "default",
        ttl: int = 3600,
        workload_manager_url: Optional[str] = None,
        router_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        verbose: bool = False,
        session_id: Optional[str] = None,
    ):
        """Initialize the Code Interpreter client.

        Args:
            name: Name for the session.
            namespace: Kubernetes namespace.
            ttl: Time-to-live in seconds.
            workload_manager_url: URL of the Workload Manager.
            router_url: URL of the Router service.
            auth_token: Authentication token.
            verbose: Enable verbose logging.
            session_id: Existing session ID to reuse.

        Raises:
            ValueError: If router_url is not provided via argument or ROUTER_URL env var.
        """
        self.logger = get_logger(__name__, logging.DEBUG if verbose else logging.INFO)
        self.name = name
        self.namespace = namespace
        self.ttl = ttl
        self.verbose = verbose
        self.session_id = session_id

        self.router_url = router_url or os.getenv("ROUTER_URL")
        if not self.router_url:
            raise ValueError(
                "Router URL must be provided via argument or ROUTER_URL environment variable"
            )

        self.cp_client = ControlPlaneClient(
            workload_manager_url=workload_manager_url,
            auth_token=auth_token,
        )

        if self.session_id:
            self._init_data_plane()
        else:
            self._init_data_plane()

    def _init_data_plane(self) -> None:
        """Initialize the data plane client.

        Creates a new session if session_id was not provided.
        """
        if not self.session_id:
            self.session_id = self.cp_client.create_session(
                name=self.name,
                namespace=self.namespace,
                ttl=self.ttl,
            )
            self.logger.info(f"Created new session: {self.session_id}")

        self.dp_client = CodeInterpreterDataPlaneClient(
            session_id=self.session_id,
            router_url=self.router_url,
            namespace=self.namespace,
            cr_name=self.name,
        )

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup resources."""
        self.stop()

    def stop(self) -> None:
        """Stop the session and cleanup resources.

        Closes the data plane session, deletes the control plane session
        if session_id was set, and closes the control plane HTTP session.
        """
        if self.dp_client:
            self.dp_client.close()

        if self.session_id and self.cp_client:
            self.cp_client.delete_session(self.session_id)
            self.logger.info(f"Deleted session: {self.session_id}")
            self.session_id = None

        if self.cp_client:
            self.cp_client.close()

    def execute_command(
        self,
        command: str,
        timeout: Optional[float] = None,
    ) -> str:
        """Execute a command in the code interpreter.

        Args:
            command: Command to execute.
            timeout: Timeout in seconds.

        Returns:
            The command output.
        """
        return self.dp_client.execute_command(command, timeout)

    def run_code(
        self,
        language: str,
        code: str,
        timeout: Optional[float] = None,
    ) -> str:
        """Run code in the specified language.

        Args:
            language: Programming language.
            code: Code to execute.
            timeout: Timeout in seconds.

        Returns:
            The code output.
        """
        return self.dp_client.run_code(language, code, timeout)

    def write_file(self, content: str, remote_path: str) -> None:
        """Write content to a remote file.

        Args:
            content: File content.
            remote_path: Remote file path.
        """
        self.dp_client.write_file(content, remote_path)

    def upload_file(self, local_path: str, remote_path: str) -> None:
        """Upload a local file to the remote environment.

        Args:
            local_path: Local file path.
            remote_path: Remote file path.
        """
        self.dp_client.upload_file(local_path, remote_path)

    def download_file(self, remote_path: str, local_path: str) -> None:
        """Download a file from the remote environment.

        Args:
            remote_path: Remote file path.
            local_path: Local file path to save to.
        """
        self.dp_client.download_file(remote_path, local_path)

    def list_files(self, path: str = ".") -> Any:
        """List files in the remote environment.

        Args:
            path: Path to list.

        Returns:
            The file listing.
        """
        return self.dp_client.list_files(path)
