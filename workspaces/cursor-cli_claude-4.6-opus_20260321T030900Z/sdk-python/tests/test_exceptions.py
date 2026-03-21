"""Tests for SDK exception types."""

from __future__ import annotations

import pytest

from agentcube.exceptions import (
    AgentCubeError,
    CommandExecutionError,
    DataPlaneError,
    SessionError,
)


def test_exception_hierarchy() -> None:
    assert issubclass(SessionError, AgentCubeError)
    assert issubclass(DataPlaneError, AgentCubeError)
    assert issubclass(CommandExecutionError, DataPlaneError)


def test_command_execution_error_fields() -> None:
    err = CommandExecutionError(
        "failed",
        exit_code=7,
        stderr="err-out",
        command="ls",
    )
    assert err.exit_code == 7
    assert err.stderr == "err-out"
    assert err.command == "ls"
    with pytest.raises(CommandExecutionError):
        raise err
