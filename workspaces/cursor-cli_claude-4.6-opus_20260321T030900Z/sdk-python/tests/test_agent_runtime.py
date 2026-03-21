"""Tests for ``AgentRuntimeClient`` with HTTP mocked."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentcube import AgentRuntimeClient
from agentcube.clients.agent_runtime_data_plane import SESSION_HEADER
from agentcube.exceptions import DataPlaneError

from .conftest import make_json_response


def test_agent_runtime_invoke_json(control_plane_base: str, namespace: str) -> None:
    session = MagicMock()

    def post(url: str, **kwargs: object) -> MagicMock:
        if url.endswith("session/bootstrap"):
            return make_json_response(200, {}, headers={SESSION_HEADER: "sid-1"})
        if url.endswith("invoke"):
            return make_json_response(
                200,
                {"ok": True},
                headers={"Content-Type": "application/json"},
            )
        raise AssertionError(f"unexpected POST {url}")

    session.post.side_effect = post

    with patch("agentcube.clients.agent_runtime_data_plane.create_session", return_value=session):
        with AgentRuntimeClient(control_plane_base, namespace, "rt-1") as client:
            body = client.invoke({"input": "ping"})
        assert body == {"ok": True}


def test_agent_runtime_not_started(control_plane_base: str, namespace: str) -> None:
    client = AgentRuntimeClient(control_plane_base, namespace, "rt-1")
    with pytest.raises(RuntimeError, match="not started"):
        client.invoke({})


def test_bootstrap_missing_session_header(control_plane_base: str, namespace: str) -> None:
    session = MagicMock()
    session.post.return_value = make_json_response(200, {}, headers={})

    with patch("agentcube.clients.agent_runtime_data_plane.create_session", return_value=session):
        with pytest.raises(DataPlaneError, match="session id"):
            with AgentRuntimeClient(control_plane_base, namespace, "rt-1"):
                pass
