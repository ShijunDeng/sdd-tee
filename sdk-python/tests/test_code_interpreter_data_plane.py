"""Tests for CodeInterpreterDataPlaneClient."""

import base64
import json
import os
from unittest.mock import patch, MagicMock

import pytest
import requests

from agentcube.clients.code_interpreter_data_plane import CodeInterpreterDataPlaneClient
from agentcube.exceptions import CommandExecutionError


class TestCodeInterpreterDataPlaneClientInit:
    """Tests for CodeInterpreterDataPlaneClient initialization."""

    def test_init_with_base_url(self):
        """Test initialization with explicit base URL."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )
        assert client.base_url == "http://test-base"

    def test_init_with_router_url(self):
        """Test initialization with router URL."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            router_url="http://router",
            namespace="default",
            cr_name="test-interpreter"
        )
        assert "/v1/namespaces/default/code-interpreters/test-interpreter/invocations/" in client.base_url

    def test_init_requires_router_or_base_url(self):
        """Test that initialization requires router_url or base_url."""
        with pytest.raises(ValueError):
            CodeInterpreterDataPlaneClient(
                session_id="test-session",
                namespace="default",
                cr_name="test"
            )

    def test_init_sets_session_header(self):
        """Test that session ID is set in headers."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )
        assert client.session.headers.get("x-agentcube-session-id") == "test-session"

    def test_init_default_timeouts(self):
        """Test initialization with default timeouts."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )
        assert client.timeout == 120
        assert client.connect_timeout == 5.0


class TestCodeInterpreterDataPlaneClientExecuteCommand:
    """Tests for CodeInterpreterDataPlaneClient.execute_command method."""

    def test_execute_command_success(self):
        """Test successful command execution."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stdout": "output",
            "stderr": "",
            "exit_code": 0
        }
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        result = client.execute_command("ls -la")

        assert result == "output"

    def test_execute_command_string_command(self):
        """Test command execution with string command."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stdout": "output",
            "stderr": "",
            "exit_code": 0
        }
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        client.execute_command("ls -la")

        call_args = client.session.request.call_args
        body = json.loads(call_args[1]["data"])
        assert body["command"] == ["ls -la"]

    def test_execute_command_list_command(self):
        """Test command execution with list command."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stdout": "output",
            "stderr": "",
            "exit_code": 0
        }
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        client.execute_command(["ls", "-la"])

        call_args = client.session.request.call_args
        body = json.loads(call_args[1]["data"])
        assert body["command"] == ["ls", "-la"]

    def test_execute_command_non_zero_exit(self):
        """Test command execution with non-zero exit code."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stdout": "",
            "stderr": "Error occurred",
            "exit_code": 1
        }
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        with pytest.raises(CommandExecutionError) as exc_info:
            client.execute_command("failing-command")

        assert exc_info.value.exit_code == 1
        assert exc_info.value.stderr == "Error occurred"

    def test_execute_command_with_timeout(self):
        """Test command execution with timeout."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "stdout": "output",
            "stderr": "",
            "exit_code": 0
        }
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        client.execute_command("ls", timeout=30)

        call_args = client.session.request.call_args
        body = json.loads(call_args[1]["data"])
        assert body["timeout"] == "30s"


class TestCodeInterpreterDataPlaneClientRunCode:
    """Tests for CodeInterpreterDataPlaneClient.run_code method."""

    def test_run_code_python(self):
        """Test running Python code."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        client.write_file = MagicMock()
        client.execute_command = MagicMock(return_value="Python output")

        result = client.run_code("python", "print('hello')")

        assert result == "Python output"
        client.write_file.assert_called_once()
        client.execute_command.assert_called_once()

    def test_run_code_py(self):
        """Test running Python code with py language."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        client.write_file = MagicMock()
        client.execute_command = MagicMock(return_value="Python output")

        result = client.run_code("py", "print('hello')")

        assert result == "Python output"

    def test_run_code_python3(self):
        """Test running Python code with python3 language."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        client.write_file = MagicMock()
        client.execute_command = MagicMock(return_value="Python output")

        result = client.run_code("python3", "print('hello')")

        assert result == "Python output"

    def test_run_code_unsupported_language(self):
        """Test running unsupported language."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        with pytest.raises(ValueError, match="Unsupported language"):
            client.run_code("javascript", "console.log('hello')")


class TestCodeInterpreterDataPlaneClientWriteFile:
    """Tests for CodeInterpreterDataPlaneClient.write_file method."""

    def test_write_file_success(self):
        """Test successful file write."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        client.write_file("content", "/path/to/file")

        call_args = client.session.request.call_args
        body = json.loads(call_args[1]["data"])
        assert body["path"] == "/path/to/file"
        assert body["mode"] == "0644"
        assert base64.b64decode(body["content"]).decode("utf-8") == "content"


class TestCodeInterpreterDataPlaneClientUploadFile:
    """Tests for CodeInterpreterDataPlaneClient.upload_file method."""

    def test_upload_file_success(self, tmp_path):
        """Test successful file upload."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_response)

        client.upload_file(str(test_file), "/remote/path")

        client.session.post.assert_called_once()
        call_kwargs = client.session.post.call_args[1]
        assert call_kwargs["headers"]["x-agentcube-session-id"] == "test-session"


class TestCodeInterpreterDataPlaneClientDownloadFile:
    """Tests for CodeInterpreterDataPlaneClient.download_file method."""

    def test_download_file_success(self, tmp_path):
        """Test successful file download."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.iter_content = MagicMock(return_value=[b"chunk1", b"chunk2"])
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        local_path = tmp_path / "downloaded.txt"
        client.download_file("/remote/path", str(local_path))

        assert local_path.read_text() == "chunk1chunk2"


class TestCodeInterpreterDataPlaneClientListFiles:
    """Tests for CodeInterpreterDataPlaneClient.list_files method."""

    def test_list_files_success(self):
        """Test successful file listing."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {"files": ["file1.txt", "file2.txt"]}
        mock_response.raise_for_status = MagicMock()
        client.session.request = MagicMock(return_value=mock_response)

        result = client.list_files("/path")

        assert "files" in result
        client.session.request.assert_called_once()


class TestCodeInterpreterDataPlaneClientClose:
    """Tests for CodeInterpreterDataPlaneClient.close method."""

    def test_close(self):
        """Test closing the client."""
        client = CodeInterpreterDataPlaneClient(
            session_id="test-session",
            base_url="http://test-base"
        )

        client.session.close = MagicMock()
        client.close()

        client.session.close.assert_called_once()
