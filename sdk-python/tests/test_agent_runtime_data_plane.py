"""Tests for AgentRuntimeDataPlaneClient."""

from unittest.mock import patch, MagicMock

import pytest
import requests

from agentcube.clients.agent_runtime_data_plane import AgentRuntimeDataPlaneClient


class TestAgentRuntimeDataPlaneClientInit:
    """Tests for AgentRuntimeDataPlaneClient initialization."""

    def test_init_sets_base_url(self):
        """Test that base URL is constructed correctly."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )
        assert "/v1/namespaces/default/agent-runtimes/test-agent/invocations/" in client.base_url

    def test_init_default_timeouts(self):
        """Test initialization with default timeouts."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )
        assert client.timeout == 120
        assert client.connect_timeout == 5.0

    def test_init_custom_timeouts(self):
        """Test initialization with custom timeouts."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent",
            timeout=60,
            connect_timeout=3.0
        )
        assert client.timeout == 60
        assert client.connect_timeout == 3.0


class TestAgentRuntimeDataPlaneClientBootstrapSessionId:
    """Tests for AgentRuntimeDataPlaneClient.bootstrap_session_id method."""

    def test_bootstrap_session_id_success(self):
        """Test successful session ID bootstrap."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        mock_response = MagicMock()
        mock_response.headers = {"x-agentcube-session-id": "bootstrapped-session"}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        session_id = client.bootstrap_session_id()

        assert session_id == "bootstrapped-session"
        client.session.get.assert_called_once()

    def test_bootstrap_session_id_missing_header(self):
        """Test bootstrap when header is missing."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()
        client.session.get = MagicMock(return_value=mock_response)

        with pytest.raises(ValueError, match="x-agentcube-session-id"):
            client.bootstrap_session_id()

    def test_bootstrap_session_id_http_error(self):
        """Test bootstrap with HTTP error."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        client.session.get = MagicMock(side_effect=requests.exceptions.HTTPError())

        with pytest.raises(requests.exceptions.HTTPError):
            client.bootstrap_session_id()


class TestAgentRuntimeDataPlaneClientInvoke:
    """Tests for AgentRuntimeDataPlaneClient.invoke method."""

    def test_invoke_success(self):
        """Test successful invocation."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_response)

        response = client.invoke(
            session_id="test-session",
            payload={"key": "value"}
        )

        assert response == mock_response
        client.session.post.assert_called_once()

    def test_invoke_sets_session_header(self):
        """Test that session header is set."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_response)

        client.invoke(
            session_id="test-session",
            payload={"key": "value"}
        )

        assert client.session.headers.get("x-agentcube-session-id") == "test-session"

    def test_invoke_sets_content_type(self):
        """Test that content type is set."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_response)

        client.invoke(
            session_id="test-session",
            payload={"key": "value"}
        )

        assert client.session.headers.get("Content-Type") == "application/json"

    def test_invoke_with_timeout(self):
        """Test invocation with custom timeout."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        client.session.post = MagicMock(return_value=mock_response)

        client.invoke(
            session_id="test-session",
            payload={"key": "value"},
            timeout=60
        )

        call_kwargs = client.session.post.call_args[1]
        assert call_kwargs["timeout"] == (5.0, 60)


class TestAgentRuntimeDataPlaneClientClose:
    """Tests for AgentRuntimeDataPlaneClient.close method."""

    def test_close(self):
        """Test closing the client."""
        client = AgentRuntimeDataPlaneClient(
            router_url="http://router",
            namespace="default",
            agent_name="test-agent"
        )

        client.session.close = MagicMock()
        client.close()

        client.session.close.assert_called_once()

    def test_session_header_constant(self):
        """Test that SESSION_HEADER constant is defined correctly."""
        assert AgentRuntimeDataPlaneClient.SESSION_HEADER == "x-agentcube-session-id"
