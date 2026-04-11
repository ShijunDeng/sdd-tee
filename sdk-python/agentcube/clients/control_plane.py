"""Control Plane client for AgentCube SDK."""

import logging
import os
from typing import Any, Dict, Optional

import requests

from ..utils.http import create_session
from ..utils.utils import read_token_from_file
from ..utils.log import get_logger


class ControlPlaneClient:
    """Client for interacting with the Workload Manager (control plane)."""

    def __init__(
        self,
        workload_manager_url: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: int = 120,
        connect_timeout: float = 5.0,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
    ):
        """Initialize the Control Plane client.

        Args:
            workload_manager_url: URL of the Workload Manager. Defaults to WORKLOAD_MANAGER_URL env var.
            auth_token: Authentication token. Defaults to reading from SA token file.
            timeout: Read timeout in seconds.
            connect_timeout: Connect timeout in seconds.
            pool_connections: Number of connections to pool.
            pool_maxsize: Maximum number of connections in the pool.
        """
        self.logger = get_logger(__name__)
        self.timeout = timeout
        self.connect_timeout = connect_timeout

        self.base_url = workload_manager_url or os.getenv("WORKLOAD_MANAGER_URL")
        if not self.base_url:
            raise ValueError(
                "Workload Manager URL must be provided via argument or WORKLOAD_MANAGER_URL environment variable"
            )

        self.session = create_session(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
        )
        self.session.headers["Content-Type"] = "application/json"

        token = auth_token or read_token_from_file(
            "/var/run/secrets/kubernetes.io/serviceaccount/token"
        )
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def create_session(
        self,
        name: str = "my-interpreter",
        namespace: str = "default",
        metadata: Optional[Dict[str, Any]] = None,
        ttl: int = 3600,
    ) -> str:
        """Create a new Code Interpreter session.

        Args:
            name: Name for the session.
            namespace: Kubernetes namespace.
            metadata: Optional metadata dictionary.
            ttl: Time-to-live in seconds.

        Returns:
            The session ID from the response.

        Raises:
            ValueError: If the response does not contain a sessionId.
        """
        url = f"{self.base_url}/v1/code-interpreter"
        payload = {
            "name": name,
            "namespace": namespace,
            "ttl": ttl,
            "metadata": metadata or {},
        }

        response = self.session.post(
            url,
            json=payload,
            timeout=(self.connect_timeout, self.timeout),
        )
        response.raise_for_status()

        data = response.json()
        session_id = data.get("data", {}).get("sessionId")
        if not session_id:
            raise ValueError("Response does not contain sessionId")

        return session_id

    def delete_session(self, session_id: str) -> bool:
        """Delete a Code Interpreter session.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deletion succeeded or session was not found (404), False otherwise.
        """
        url = f"{self.base_url}/v1/code-interpreter/sessions/{session_id}"

        try:
            response = self.session.delete(
                url,
                timeout=(self.connect_timeout, self.timeout),
            )
            if response.status_code == 404:
                return True
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            self.logger.warning(f"Failed to delete session {session_id}: {e}")
            return False

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()
