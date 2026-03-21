"""Tests for ``CodeInterpreterClient`` with HTTP mocked at the session layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentcube import CodeInterpreterClient
from agentcube.exceptions import SessionError

from .conftest import make_json_response


def test_code_interpreter_runs_code(control_plane_base: str, namespace: str) -> None:
    session = MagicMock()

    def post_side_effect(url: str, **kwargs: object) -> MagicMock:
        if url.endswith("/v1/code-interpreter"):
            return make_json_response(200, {"id": "interp-1", "sessionId": "sess-1"})
        if "run-code" in url:
            return make_json_response(200, {"stdout": "hello"})
        if url.endswith("/v1/code-interpreter/sess-1"):
            return make_json_response(200, {})
        raise AssertionError(f"unexpected POST {url}")

    session.post.side_effect = post_side_effect

    with patch("agentcube.clients.control_plane.create_session", return_value=session):
        with CodeInterpreterClient(control_plane_base, namespace) as client:
            out = client.run_code("print(1)", language="python")
        assert out["stdout"] == "hello"
    session.close.assert_called()


def test_code_interpreter_missing_id_raises(control_plane_base: str, namespace: str) -> None:
    session = MagicMock()
    session.post.return_value = make_json_response(200, {"sessionId": "only-session"})

    with patch("agentcube.clients.control_plane.create_session", return_value=session):
        with pytest.raises(ValueError, match="interpreter id"):
            with CodeInterpreterClient(control_plane_base, namespace):
                pass


def test_create_session_http_error(control_plane_base: str, namespace: str) -> None:
    session = MagicMock()
    session.post.return_value = make_json_response(503, {"error": "unavailable"})

    with patch("agentcube.clients.control_plane.create_session", return_value=session):
        with pytest.raises(SessionError):
            with CodeInterpreterClient(control_plane_base, namespace):
                pass
