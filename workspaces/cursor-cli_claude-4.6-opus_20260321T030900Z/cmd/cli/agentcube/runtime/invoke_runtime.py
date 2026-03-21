"""HTTP invoke against a running agent."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from agentcube.services.metadata_service import MetadataService

SESSION_HEADER = "X-Agentcube-Session-Id"


class InvokeRuntime:
    """POST JSON payloads to agent endpoints with session stickiness."""

    def __init__(self, timeout: float = 60.0) -> None:
        self.timeout = timeout
        self._session_id: str | None = None

    def invoke(
        self,
        workspace_path: str | Path,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> Any:
        """
        POST to agent endpoint; reuse X-Agentcube-Session-Id across calls on this instance.

        Endpoint resolution: options/metadata ``endpoint``, else metadata ``image`` is ignored;
        pass base_url via workspace .agentcube/config or metadata.endpoint.
        """
        root = Path(workspace_path).resolve()
        svc = MetadataService(root)
        meta = svc.load_metadata()
        base_url = meta.endpoint.rstrip("/") if meta.endpoint else ""
        if not base_url:
            raise ValueError(
                "No endpoint configured; set 'endpoint' in agent_metadata.yaml "
                "(e.g. http://localhost:8080)"
            )
        url = f"{base_url}/invoke" if not base_url.endswith("/invoke") else base_url
        hdrs: dict[str, str] = {"Content-Type": "application/json"}
        if headers:
            hdrs.update(headers)
        if self._session_id:
            hdrs.setdefault(SESSION_HEADER, self._session_id)
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload, headers=hdrs)
            resp.raise_for_status()
            sid = resp.headers.get("x-agentcube-session-id")
            if sid:
                self._session_id = sid
            if resp.headers.get("content-type", "").startswith("application/json"):
                return resp.json()
            return resp.text
