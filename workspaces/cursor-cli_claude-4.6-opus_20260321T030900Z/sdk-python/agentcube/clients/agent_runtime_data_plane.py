"""Agent runtime HTTP data plane with session stickiness."""

from __future__ import annotations

import json
from typing import Any

from requests import Session

from agentcube.exceptions import DataPlaneError
from agentcube.utils.http import create_session

SESSION_HEADER = "x-agentcube-session-id"


class AgentRuntimeDataPlaneClient:
    """Invoke agent runtimes through the namespaced invocations API."""

    def __init__(
        self,
        base_url: str,
        namespace: str,
        runtime_id: str,
        session: Session | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.namespace = namespace
        self.runtime_id = runtime_id
        self.session = session or create_session()
        self.headers = dict(headers or {})
        self.timeout = timeout
        self._owns_session = session is None
        self._root = (
            f"{self.base_url}/v1/namespaces/{namespace}"
            f"/agent-runtimes/{runtime_id}/invocations/api"
        )
        self._session_id: str | None = None

    def _url(self, suffix: str) -> str:
        return f"{self._root}/{suffix.lstrip('/')}"

    def bootstrap_session_id(self) -> str:
        """
        Obtain a session id from the data plane (POST session/bootstrap).

        Subsequent ``invoke`` calls attach ``SESSION_HEADER`` automatically.
        """
        resp = self.session.post(
            self._url("session/bootstrap"),
            json={},
            headers=self.headers,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise DataPlaneError(f"bootstrap_session_id failed: {resp.status_code} {resp.text}")
        sid = resp.headers.get(SESSION_HEADER)
        if not sid and resp.content:
            try:
                payload = resp.json()
                sid = str(payload.get("sessionId") or payload.get("session_id") or "")
            except json.JSONDecodeError:
                sid = None
        if not sid:
            raise DataPlaneError("bootstrap_session_id: no session id in response")
        self._session_id = sid
        return sid

    def invoke(self, payload: dict[str, Any]) -> Any:
        """POST invoke payload; sends session header when known."""
        hdrs = dict(self.headers)
        if self._session_id:
            hdrs[SESSION_HEADER] = self._session_id
        resp = self.session.post(
            self._url("invoke"),
            json=payload,
            headers=hdrs,
            timeout=self.timeout,
        )
        if resp.status_code >= 400:
            raise DataPlaneError(f"invoke failed: {resp.status_code} {resp.text}")
        new_sid = resp.headers.get(SESSION_HEADER)
        if new_sid:
            self._session_id = new_sid
        ctype = resp.headers.get("Content-Type", "")
        if "application/json" in ctype:
            return resp.json()
        return resp.text

    def close(self) -> None:
        if self._owns_session:
            self.session.close()
