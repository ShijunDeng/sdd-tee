"""Tests for ControlPlaneClient."""

import os
from unittest.mock import patch, MagicMock

import pytest
import requests

from agentcube.clients.control_plane import ControlPlaneClient
from agentcube.exceptions import AgentCubeError


class TestControlPlaneClientInit:
    """Tests for ControlPlaneClient initialization."""

    def test_init_requires_url(self):
        """Test that initialization requires URL."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="WORKLOAD_MANAGER_URL"):
                ControlPlaneClient()

    def test_init_with_url(self):
        """Test initialization with explicit URL."""
        client = ControlPlaneClient(workload_manager_url="http://test-url")
        assert client.base_url == "http://test-url"

    def test_init_with_env_url(self):
        """Test initialization with environment variable URL."""
        with patch.dict(os.environ, {"WORKLOAD_MANAGER_URL": "http://env-url"}):
            client = ControlPlaneClient()
            assert client.base_url == "http://env-url"

    def test_init_url_priority(self):
        """Test that explicit URL takes priority over environment."""
        with patch.dict(os.environ, {"WORKLOAD_MANAGER_URL": "http://env-url"}):
            client = ControlPlaneClient(workload_manager_url="http://explicit-url")
            assert client.base_url == "http://explicit-url"

    def test_init_with_auth_token(self):
        """Test initialization with auth token."""
        client = ControlPlaneClient(
            workload_manager_url="http://test-url",
            auth_token="test-token"
        )
        assert client.session.headers.get("Authorization") == "Bearer test-token"

    def test_init_without_auth_token(self):
        """Test initialization without auth token."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")
            assert "Authorization" not in client.session.headers

    def test_init_default_timeouts(self):
        """Test initialization with default timeouts."""
        client = ControlPlaneClient(workload_manager_url="http://test-url")
        assert client.timeout == 120
        assert client.connect_timeout == 5.0

    def test_init_custom_timeouts(self):
        """Test initialization with custom timeouts."""
        client = ControlPlaneClient(
            workload_manager_url="http://test-url",
            timeout=60,
            connect_timeout=3.0
        )
        assert client.timeout == 60
        assert client.connect_timeout == 3.0


class TestControlPlaneClientCreateSession:
    """Tests for ControlPlaneClient.create_session method."""

    def test_create_session_success(self):
        """Test successful session creation."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"sessionId": "test-session-id"}}
            mock_response.raise_for_status = MagicMock()
            client.session.post = MagicMock(return_value=mock_response)

            session_id = client.create_session()

            assert session_id == "test-session-id"
            client.session.post.assert_called_once()

    def test_create_session_with_params(self):
        """Test session creation with custom parameters."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {"sessionId": "test-session-id"}}
            mock_response.raise_for_status = MagicMock()
            client.session.post = MagicMock(return_value=mock_response)

            client.create_session(
                name="custom-name",
                namespace="custom-namespace",
                ttl=7200,
                metadata={"key": "value"}
            )

            call_args = client.session.post.call_args
            payload = call_args[1]["json"]
            assert payload["name"] == "custom-name"
            assert payload["namespace"] == "custom-namespace"
            assert payload["ttl"] == 7200
            assert payload["metadata"] == {"key": "value"}

    def test_create_session_missing_session_id(self):
        """Test session creation with missing session ID in response."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            mock_response = MagicMock()
            mock_response.json.return_value = {"data": {}}
            mock_response.raise_for_status = MagicMock()
            client.session.post = MagicMock(return_value=mock_response)

            with pytest.raises(ValueError, match="sessionId"):
                client.create_session()

    def test_create_session_http_error(self):
        """Test session creation with HTTP error."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            client.session.post = MagicMock(side_effect=requests.exceptions.HTTPError())

            with pytest.raises(requests.exceptions.HTTPError):
                client.create_session()


class TestControlPlaneClientDeleteSession:
    """Tests for ControlPlaneClient.delete_session method."""

    def test_delete_session_success(self):
        """Test successful session deletion."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()
            client.session.delete = MagicMock(return_value=mock_response)

            result = client.delete_session("test-session-id")

            assert result is True

    def test_delete_session_not_found(self):
        """Test session deletion when session doesn't exist (404)."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            mock_response = MagicMock()
            mock_response.status_code = 404
            client.session.delete = MagicMock(return_value=mock_response)

            result = client.delete_session("test-session-id")

            assert result is True

    def test_delete_session_error(self):
        """Test session deletion with error."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            client.session.delete = MagicMock(
                side_effect=requests.exceptions.RequestException()
            )

            result = client.delete_session("test-session-id")

            assert result is False

    def test_delete_session_http_error(self):
        """Test session deletion with HTTP error."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.raise_for_status = MagicMock(
                side_effect=requests.exceptions.HTTPError()
            )
            client.session.delete = MagicMock(return_value=mock_response)

            result = client.delete_session("test-session-id")

            assert result is False


class TestControlPlaneClientClose:
    """Tests for ControlPlaneClient.close method."""

    def test_close(self):
        """Test closing the client."""
        with patch("agentcube.clients.control_plane.read_token_from_file") as mock_read:
            mock_read.return_value = ""
            client = ControlPlaneClient(workload_manager_url="http://test-url")

            client.session.close = MagicMock()
            client.close()

            client.session.close.assert_called_once()
