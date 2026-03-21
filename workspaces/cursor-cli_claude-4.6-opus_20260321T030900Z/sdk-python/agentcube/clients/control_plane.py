"""Control plane API for code interpreter sessions."""

from __future__ import annotations

from typing import Any

from requests import Session

from agentcube.exceptions import SessionError
from agentcube.utils.http import create_session


class ControlPlaneClient:
    """Create and tear down remote code-interpreter sessions."""

    def __init__(
        self,
        base_url: str,
        session: Session | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or create_session()
        self.headers = dict(headers or {})
        self.timeout = timeout
        self._owns_session = session is None

    def create_session(self, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """POST /v1/code-interpreter — returns parsed JSON including session identifiers."""
        url = f"{self.base_url}/v1/code-interpreter"
        resp = self.session.post(url, json=body or {}, headers=self.headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise SessionError(f"create_session failed: {resp.status_code} {resp.text}")
        return resp.json()

    def delete_session(self, session_id: str) -> None:
        """DELETE /v1/code-interpreter/{session_id}."""
        url = f"{self.base_url}/v1/code-interpreter/{session_id}"
        resp = self.session.delete(url, headers=self.headers, timeout=self.timeout)
        if resp.status_code >= 400:
            raise SessionError(f"delete_session failed: {resp.status_code} {resp.text}")

    def close(self) -> None:
        """Close the underlying HTTP session if owned by this client."""
        if self._owns_session:
            self.session.close()
