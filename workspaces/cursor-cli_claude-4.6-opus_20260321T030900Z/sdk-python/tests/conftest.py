"""Shared pytest fixtures for AgentCube SDK tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def control_plane_base() -> str:
    return "http://agentcube.test"


@pytest.fixture
def namespace() -> str:
    return "default"


@pytest.fixture
def interpreter_id() -> str:
    return "ci-test-001"


@pytest.fixture
def mock_session() -> MagicMock:
    """A ``requests.Session``-like mock with a configurable ``post`` side effect."""
    return MagicMock()


def make_json_response(
    status: int,
    payload: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.content = b"{}"
    r.headers = dict(headers or {})
    r.text = ""
    if payload is not None:
        r.json.return_value = payload
    else:
        r.json.return_value = {}
    return r
