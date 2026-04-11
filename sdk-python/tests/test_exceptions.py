"""Tests for AgentCube SDK exceptions."""

import pytest
from agentcube.exceptions import (
    AgentCubeError,
    CommandExecutionError,
    SessionError,
    DataPlaneError,
)


class TestAgentCubeError:
    """Tests for AgentCubeError base exception."""

    def test_agent_cube_error_can_be_raised(self):
        """Test that AgentCubeError can be raised."""
        with pytest.raises(AgentCubeError):
            raise AgentCubeError("Test error")

    def test_agent_cube_error_message(self):
        """Test that AgentCubeError stores message correctly."""
        error = AgentCubeError("Test error message")
        assert str(error) == "Test error message"


class TestCommandExecutionError:
    """Tests for CommandExecutionError exception."""

    def test_command_execution_error_basic(self):
        """Test basic CommandExecutionError creation."""
        error = CommandExecutionError(
            exit_code=1,
            stderr="Error output",
            command="ls -la"
        )
        assert error.exit_code == 1
        assert error.stderr == "Error output"
        assert error.command == "ls -la"

    def test_command_execution_error_message(self):
        """Test CommandExecutionError message format."""
        error = CommandExecutionError(
            exit_code=2,
            stderr="File not found",
        )
        assert "exit 2" in str(error)
        assert "File not found" in str(error)

    def test_command_execution_error_without_command(self):
        """Test CommandExecutionError with None command."""
        error = CommandExecutionError(
            exit_code=1,
            stderr="Error",
            command=None
        )
        assert error.command is None

    def test_command_execution_error_is_agent_cube_error(self):
        """Test that CommandExecutionError is subclass of AgentCubeError."""
        error = CommandExecutionError(exit_code=1, stderr="Error")
        assert isinstance(error, AgentCubeError)

    def test_command_execution_error_can_be_caught_as_agent_cube_error(self):
        """Test that CommandExecutionError can be caught as AgentCubeError."""
        with pytest.raises(AgentCubeError):
            raise CommandExecutionError(exit_code=1, stderr="Error")


class TestSessionError:
    """Tests for SessionError exception."""

    def test_session_error_can_be_raised(self):
        """Test that SessionError can be raised."""
        with pytest.raises(SessionError):
            raise SessionError("Session failed")

    def test_session_error_message(self):
        """Test that SessionError stores message correctly."""
        error = SessionError("Session creation failed")
        assert str(error) == "Session creation failed"

    def test_session_error_is_agent_cube_error(self):
        """Test that SessionError is subclass of AgentCubeError."""
        error = SessionError("Error")
        assert isinstance(error, AgentCubeError)


class TestDataPlaneError:
    """Tests for DataPlaneError exception."""

    def test_data_plane_error_can_be_raised(self):
        """Test that DataPlaneError can be raised."""
        with pytest.raises(DataPlaneError):
            raise DataPlaneError("Data plane failed")

    def test_data_plane_error_message(self):
        """Test that DataPlaneError stores message correctly."""
        error = DataPlaneError("Operation failed")
        assert str(error) == "Operation failed"

    def test_data_plane_error_is_agent_cube_error(self):
        """Test that DataPlaneError is subclass of AgentCubeError."""
        error = DataPlaneError("Error")
        assert isinstance(error, AgentCubeError)
