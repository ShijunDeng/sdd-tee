"""High-level agent runtime invoke helper."""

from __future__ import annotations

from types import TracebackType
from typing import Any

from agentcube.clients.agent_runtime_data_plane import AgentRuntimeDataPlaneClient


class AgentRuntimeClient:
    """Context manager around ``AgentRuntimeDataPlaneClient`` with session bootstrap."""

    def __init__(
        self,
        base_url: str,
        namespace: str,
        runtime_id: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._client = AgentRuntimeDataPlaneClient(
            base_url=base_url,
            namespace=namespace,
            runtime_id=runtime_id,
            headers=headers,
        )
        self._started = False

    def __enter__(self) -> AgentRuntimeClient:
        self._client.bootstrap_session_id()
        self._started = True
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def invoke(self, payload: dict[str, Any]) -> Any:
        if not self._started:
            raise RuntimeError("Client is not started; use 'with' context")
        return self._client.invoke(payload)

    def close(self) -> None:
        self._client.close()
        self._started = False
