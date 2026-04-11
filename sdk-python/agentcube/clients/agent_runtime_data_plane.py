"""Agent Runtime Data Plane client for AgentCube SDK."""

import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import requests

from ..utils.http import create_session
from ..utils.log import get_logger


class AgentRuntimeDataPlaneClient:
    """Client for interacting with the Agent Runtime data plane (Router)."""

    SESSION_HEADER = "x-agentcube-session-id"

    def __init__(
        self,
        router_url: str,
        namespace: str,
        agent_name: str,
        timeout: int = 120,
        connect_timeout: float = 5.0,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
    ):
        """Initialize the Agent Runtime Data Plane client.

        Args:
            router_url: URL of the Router service.
            namespace: Kubernetes namespace.
            agent_name: Name of the agent runtime.
            timeout: Read timeout in seconds.
            connect_timeout: Connect timeout in seconds.
            pool_connections: Number of connections to pool.
            pool_maxsize: Maximum number of connections in the pool.
        """
        self.logger = get_logger(__name__)
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.router_url = router_url

        base_path = f"/v1/namespaces/{namespace}/agent-runtimes/{agent_name}/invocations/"
        self.base_url = urljoin(router_url, base_path)

        self.session = create_session(
            pool_connections=pool_connections,
            pool_maxsize=pool_maxsize,
        )

    def bootstrap_session_id(self) -> str:
        """Bootstrap a session ID by making a GET request to the invocation endpoint.

        Returns:
            The session ID from the response header.

        Raises:
            ValueError: If the response does not contain the session ID header.
        """
        response = self.session.get(
            self.base_url,
            timeout=(self.connect_timeout, self.timeout),
        )
        response.raise_for_status()

        session_id = response.headers.get(self.SESSION_HEADER)
        if not session_id:
            raise ValueError("Missing required response header: x-agentcube-session-id")

        return session_id

    def invoke(
        self,
        session_id: str,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> requests.Response:
        """Invoke the agent runtime with a payload.

        Args:
            session_id: The session ID.
            payload: JSON payload to send.
            timeout: Optional timeout override.

        Returns:
            The HTTP response.
        """
        effective_timeout = timeout if timeout is not None else self.timeout

        self.session.headers[self.SESSION_HEADER] = session_id
        self.session.headers["Content-Type"] = "application/json"

        read_timeout = effective_timeout

        response = self.session.post(
            self.base_url,
            json=payload,
            timeout=(self.connect_timeout, read_timeout),
        )
        response.raise_for_status()

        return response

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.session.close()
