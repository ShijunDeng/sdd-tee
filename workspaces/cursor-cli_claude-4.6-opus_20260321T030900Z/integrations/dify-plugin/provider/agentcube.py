"""AgentCube tool provider: validates control-plane connectivity and credentials."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import requests
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class AgentcubeCodeInterpreterProvider(ToolProvider):
    """Registers AgentCube code-interpreter tools and validates workspace credentials."""

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        base = str(credentials.get("control_plane_url") or "").strip()
        if not base:
            raise ToolProviderCredentialValidationError("control_plane_url is required")
        parsed = urlparse(base)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ToolProviderCredentialValidationError("control_plane_url must be a valid http(s) URL")

        namespace = str(credentials.get("namespace") or "").strip()
        if not namespace:
            raise ToolProviderCredentialValidationError("namespace is required")

        headers: dict[str, str] = {}
        token = str(credentials.get("api_key") or credentials.get("bearer_token") or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"

        health_candidates = (
            f"{base.rstrip('/')}/health",
            f"{base.rstrip('/')}/healthz",
            f"{base.rstrip('/')}/readyz",
        )
        last_status: int | None = None
        last_err: str | None = None
        for url in health_candidates:
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                last_status = resp.status_code
                if resp.status_code < 500:
                    return
                last_err = resp.text[:512]
            except requests.RequestException as exc:
                last_err = str(exc)
                continue

        try:
            resp = requests.get(base.rstrip("/"), headers=headers, timeout=15, allow_redirects=True)
            last_status = resp.status_code
            if resp.status_code < 500:
                return
            last_err = resp.text[:512]
        except requests.RequestException as exc:
            last_err = str(exc)

        raise ToolProviderCredentialValidationError(
            f"Unable to reach AgentCube control plane (last HTTP {last_status}): {last_err}"
        )
