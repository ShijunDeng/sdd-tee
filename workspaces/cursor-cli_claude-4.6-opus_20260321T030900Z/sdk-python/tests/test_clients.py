"""Tests for lower-level HTTP clients."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from agentcube.clients.agent_runtime_data_plane import SESSION_HEADER, AgentRuntimeDataPlaneClient
from agentcube.clients.code_interpreter_data_plane import CodeInterpreterDataPlaneClient
from agentcube.clients.control_plane import ControlPlaneClient
from agentcube.exceptions import CommandExecutionError, DataPlaneError, SessionError

from .conftest import make_json_response


def test_control_plane_create_and_delete(control_plane_base: str) -> None:
    session = MagicMock()
    session.post.return_value = make_json_response(200, {"id": "x", "sessionId": "s1"})
    session.delete.return_value = make_json_response(200, {})
    client = ControlPlaneClient(control_plane_base, session=session)
    body = client.create_session({"foo": "bar"})
    assert body["id"] == "x"
    client.delete_session("s1")
    session.post.assert_called_once()
    session.delete.assert_called_once()
    client.close()


def test_control_plane_create_error(control_plane_base: str) -> None:
    session = MagicMock()
    session.post.return_value = make_json_response(400, {"detail": "bad"})
    client = ControlPlaneClient(control_plane_base, session=session)
    with pytest.raises(SessionError):
        client.create_session({})


def test_code_interpreter_data_plane_run_code(control_plane_base: str, interpreter_id: str) -> None:
    session = MagicMock()
    session.post.return_value = make_json_response(200, {"stdout": "1"})
    client = CodeInterpreterDataPlaneClient(
        control_plane_base, "ns1", interpreter_id, session=session, headers={"X-Test": "1"}
    )
    out = client.run_code("1+1", language="python")
    assert out["stdout"] == "1"
    called_url = session.post.call_args[0][0]
    assert interpreter_id in called_url
    assert called_url.endswith("run-code")
    client.close()


def test_code_interpreter_execute_command_nonzero(control_plane_base: str, interpreter_id: str) -> None:
    session = MagicMock()
    session.post.return_value = make_json_response(200, {"exitCode": 2, "stderr": "oops", "stdout": ""})
    client = CodeInterpreterDataPlaneClient(control_plane_base, "ns1", interpreter_id, session=session)
    with pytest.raises(CommandExecutionError) as exc:
        client.execute_command("false")
    assert exc.value.exit_code == 2
    assert "oops" in exc.value.stderr


def test_agent_runtime_invoke_plain_text(control_plane_base: str) -> None:
    session = MagicMock()

    def post(url: str, **kwargs: object) -> MagicMock:
        if "bootstrap" in url:
            r = MagicMock()
            r.status_code = 200
            r.headers = {SESSION_HEADER: "abc"}
            r.content = b""
            return r
        r = MagicMock()
        r.status_code = 200
        r.headers = {"Content-Type": "text/plain", SESSION_HEADER: "abc"}
        r.text = "plain"
        r.json.side_effect = ValueError
        return r

    session.post.side_effect = post
    client = AgentRuntimeDataPlaneClient(control_plane_base, "ns", "rt", session=session)
    sid = client.bootstrap_session_id()
    assert sid == "abc"
    out = client.invoke({})
    assert out == "plain"
    client.close()


def test_data_plane_json_error(control_plane_base: str, interpreter_id: str) -> None:
    session = MagicMock()
    r = MagicMock()
    r.status_code = 200
    r.content = b"not-json{"
    r.json.side_effect = json.JSONDecodeError("bad json", "doc", 0)
    session.post.return_value = r
    client = CodeInterpreterDataPlaneClient(control_plane_base, "ns1", interpreter_id, session=session)
    with pytest.raises(DataPlaneError, match="Invalid JSON"):
        client.run_code("x", language="python")
