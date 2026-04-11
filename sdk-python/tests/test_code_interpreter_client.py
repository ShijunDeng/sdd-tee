"""Tests for CodeInterpreterClient."""

import os
from unittest.mock import patch, MagicMock

import pytest

from agentcube.code_interpreter import CodeInterpreterClient


class TestCodeInterpreterClientInit:
    """Tests for CodeInterpreterClient initialization."""

    def test_init_requires_router_url(self):
        """Test that initialization requires router URL."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ROUTER_URL"):
                CodeInterpreterClient()

    def test_init_with_router_url(self):
        """Test initialization with explicit router URL."""
        with patch("agentcube.code_interpreter.ControlPlaneClient"):
            client = CodeInterpreterClient(router_url="http://router")
            assert client.router_url == "http://router"

    def test_init_with_env_router_url(self):
        """Test initialization with environment variable router URL."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://env-router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                client = CodeInterpreterClient()
                assert client.router_url == "http://env-router"

    def test_init_default_values(self):
        """Test initialization with default values."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                client = CodeInterpreterClient()
                assert client.name == "my-interpreter"
                assert client.namespace == "default"
                assert client.ttl == 3600

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                client = CodeInterpreterClient(
                    name="custom-name",
                    namespace="custom-ns",
                    ttl=7200
                )
                assert client.name == "custom-name"
                assert client.namespace == "custom-ns"
                assert client.ttl == 7200

    def test_init_creates_control_plane_client(self):
        """Test that control plane client is created."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient") as mock_cp:
                CodeInterpreterClient()
                mock_cp.assert_called_once()

    def test_init_with_session_id(self):
        """Test initialization with existing session ID."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                client = CodeInterpreterClient(session_id="existing-session")
                assert client.session_id == "existing-session"


class TestCodeInterpreterClientContextManager:
    """Tests for CodeInterpreterClient context manager."""

    def test_context_manager_enter(self):
        """Test context manager entry."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient"):
                    with CodeInterpreterClient() as client:
                        assert client is not None

    def test_context_manager_exit_calls_stop(self):
        """Test that context manager exit calls stop."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.close = MagicMock()
                    client.cp_client.delete_session = MagicMock()
                    client.cp_client.close = MagicMock()

                    client.stop()

                    client.dp_client.close.assert_called_once()


class TestCodeInterpreterClientStop:
    """Tests for CodeInterpreterClient.stop method."""

    def test_stop_closes_data_plane(self):
        """Test that stop closes data plane client."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.close = MagicMock()
                    client.cp_client.delete_session = MagicMock()
                    client.cp_client.close = MagicMock()

                    client.stop()

                    client.dp_client.close.assert_called_once()

    def test_stop_deletes_session(self):
        """Test that stop deletes session."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient"):
                    client = CodeInterpreterClient()
                    client.session_id = "test-session"
                    client.cp_client.delete_session = MagicMock()
                    client.cp_client.close = MagicMock()

                    client.stop()

                    client.cp_client.delete_session.assert_called_once_with("test-session")

    def test_stop_closes_control_plane(self):
        """Test that stop closes control plane client."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient") as mock_cp:
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient"):
                    client = CodeInterpreterClient()
                    client.cp_client = mock_cp.return_value
                    client.cp_client.close = MagicMock()
                    client.cp_client.delete_session = MagicMock()

                    client.stop()

                    client.cp_client.close.assert_called_once()


class TestCodeInterpreterClientExecuteCommand:
    """Tests for CodeInterpreterClient.execute_command method."""

    def test_execute_command_delegates(self):
        """Test that execute_command delegates to data plane."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.execute_command = MagicMock(return_value="output")

                    result = client.execute_command("ls", timeout=30)

                    assert result == "output"
                    client.dp_client.execute_command.assert_called_once_with("ls", 30)


class TestCodeInterpreterClientRunCode:
    """Tests for CodeInterpreterClient.run_code method."""

    def test_run_code_delegates(self):
        """Test that run_code delegates to data plane."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.run_code = MagicMock(return_value="output")

                    result = client.run_code("python", "print('hello')", timeout=30)

                    assert result == "output"
                    client.dp_client.run_code.assert_called_once_with("python", "print('hello')", 30)


class TestCodeInterpreterClientFileOperations:
    """Tests for CodeInterpreterClient file operations."""

    def test_write_file_delegates(self):
        """Test that write_file delegates to data plane."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.write_file = MagicMock()

                    client.write_file("content", "/path")

                    client.dp_client.write_file.assert_called_once_with("content", "/path")

    def test_upload_file_delegates(self):
        """Test that upload_file delegates to data plane."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.upload_file = MagicMock()

                    client.upload_file("/local", "/remote")

                    client.dp_client.upload_file.assert_called_once_with("/local", "/remote")

    def test_download_file_delegates(self):
        """Test that download_file delegates to data plane."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.download_file = MagicMock()

                    client.download_file("/remote", "/local")

                    client.dp_client.download_file.assert_called_once_with("/remote", "/local")

    def test_list_files_delegates(self):
        """Test that list_files delegates to data plane."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.code_interpreter.ControlPlaneClient"):
                with patch("agentcube.code_interpreter.CodeInterpreterDataPlaneClient") as mock_dp:
                    client = CodeInterpreterClient()
                    client.dp_client = mock_dp.return_value
                    client.dp_client.list_files = MagicMock(return_value={"files": []})

                    result = client.list_files("/path")

                    assert result == {"files": []}
                    client.dp_client.list_files.assert_called_once_with("/path")
