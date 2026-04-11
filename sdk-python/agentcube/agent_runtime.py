"""Agent Runtime Client for AgentCube SDK."""

import logging
import os
from typing import Any, Dict, Optional

from .clients.agent_runtime_data_plane import AgentRuntimeDataPlaneClient
from .utils.log import get_logger


class AgentRuntimeClient:
    """High-level client for Agent Runtime operations.

    This client manages session lifecycle and provides a convenient interface
    for invoking agent runtimes.
    """

    def __init__(
        self,
        agent_name: str,
        namespace: str = "default",
        router_url: Optional[str] = None,
        verbose: bool = False,
        session_id: Optional[str] = None,
        timeout: int = 120,
        connect_timeout: float = 5.0,
    ):
        """Initialize the Agent Runtime client.

        Args:
            agent_name: Name of the agent runtime.
            namespace: Kubernetes namespace.
            router_url: URL of the Router service.
            verbose: Enable verbose logging.
            session_id: Existing session ID to reuse.
            timeout: Read timeout in seconds.
            connect_timeout: Connect timeout in seconds.

        Raises:
            ValueError: If router_url is not provided via argument or ROUTER_URL env var.
        """
        self.logger = get_logger(__name__, logging.DEBUG if verbose else logging.INFO)
        self.agent_name = agent_name
        self.namespace = namespace
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self.session_id = session_id

        self.router_url = router_url or os.getenv("ROUTER_URL")
        if not self.router_url:
            raise ValueError(
                "Router URL must be provided via argument or ROUTER_URL environment variable"
            )

        self.dp_client = AgentRuntimeDataPlaneClient(
            router_url=self.router_url,
            namespace=self.namespace,
            agent_name=self.agent_name,
            timeout=self.timeout,
            connect_timeout=self.connect_timeout,
        )

        if not self.session_id:
            self.session_id = self.dp_client.bootstrap_session_id()
            self.logger.info(f"Bootstrapped session: {self.session_id}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - cleanup resources."""
        self.close()

    def invoke(
        self,
        payload: Dict[str, Any],
        timeout: Optional[float] = None,
    ) -> Any:
        """Invoke the agent runtime with a payload.

        Args:
            payload: JSON payload to send.
            timeout: Optional timeout override.

        Returns:
            The response data.

        Raises:
            ValueError: If session_id is not initialized.
        """
        if not self.session_id:
            raise ValueError("AgentRuntime session_id is not initialized")

        response = self.dp_client.invoke(
            session_id=self.session_id,
            payload=payload,
            timeout=timeout,
        )
        return response.json()

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self.dp_client.close()
