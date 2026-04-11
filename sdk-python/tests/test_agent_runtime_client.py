"""Tests for AgentRuntimeClient."""

import os
from unittest.mock import patch, MagicMock

import pytest

from agentcube.agent_runtime import AgentRuntimeClient


class TestAgentRuntimeClientInit:
    """Tests for AgentRuntimeClient initialization."""

    def test_init_requires_router_url(self):
        """Test that initialization requires router URL."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="ROUTER_URL"):
                AgentRuntimeClient(agent_name="test-agent")

    def test_init_with_router_url(self):
        """Test initialization with explicit router URL."""
        with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient"):
            client = AgentRuntimeClient(
                agent_name="test-agent",
                router_url="http://router"
            )
            assert client.router_url == "http://router"

    def test_init_with_env_router_url(self):
        """Test initialization with environment variable router URL."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://env-router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient"):
                client = AgentRuntimeClient(agent_name="test-agent")
                assert client.router_url == "http://env-router"

    def test_init_default_values(self):
        """Test initialization with default values."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient"):
                client = AgentRuntimeClient(agent_name="test-agent")
                assert client.agent_name == "test-agent"
                assert client.namespace == "default"
                assert client.timeout == 120
                assert client.connect_timeout == 5.0

    def test_init_custom_values(self):
        """Test initialization with custom values."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient"):
                client = AgentRuntimeClient(
                    agent_name="test-agent",
                    namespace="custom-ns",
                    timeout=60,
                    connect_timeout=3.0
                )
                assert client.namespace == "custom-ns"
                assert client.timeout == 60
                assert client.connect_timeout == 3.0

    def test_init_bootstraps_session_id(self):
        """Test that initialization bootstraps session ID."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient") as mock_dp:
                mock_dp.return_value.bootstrap_session_id = MagicMock(
                    return_value="bootstrapped-session"
                )
                client = AgentRuntimeClient(agent_name="test-agent")
                assert client.session_id == "bootstrapped-session"
                mock_dp.return_value.bootstrap_session_id.assert_called_once()

    def test_init_with_existing_session_id(self):
        """Test initialization with existing session ID."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient") as mock_dp:
                client = AgentRuntimeClient(
                    agent_name="test-agent",
                    session_id="existing-session"
                )
                assert client.session_id == "existing-session"
                mock_dp.return_value.bootstrap_session_id.assert_not_called()


class TestAgentRuntimeClientContextManager:
    """Tests for AgentRuntimeClient context manager."""

    def test_context_manager_enter(self):
        """Test context manager entry."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient"):
                with AgentRuntimeClient(agent_name="test-agent") as client:
                    assert client is not None

    def test_context_manager_exit_calls_close(self):
        """Test that context manager exit calls close."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient") as mock_dp:
                client = AgentRuntimeClient(agent_name="test-agent")
                client.dp_client = mock_dp.return_value
                client.dp_client.close = MagicMock()

                client.close()

                client.dp_client.close.assert_called_once()


class TestAgentRuntimeClientInvoke:
    """Tests for AgentRuntimeClient.invoke method."""

    def test_invoke_success(self):
        """Test successful invocation."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient") as mock_dp:
                client = AgentRuntimeClient(agent_name="test-agent")
                mock_response = MagicMock()
                mock_response.json.return_value = {"result": "success"}
                client.dp_client = mock_dp.return_value
                client.dp_client.invoke = MagicMock(return_value=mock_response)

                result = client.invoke({"key": "value"})

                assert result == {"result": "success"}

    def test_invoke_delegates_to_data_plane(self):
        """Test that invoke delegates to data plane."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient") as mock_dp:
                client = AgentRuntimeClient(agent_name="test-agent")
                mock_response = MagicMock()
                mock_response.json.return_value = {"result": "success"}
                client.dp_client = mock_dp.return_value
                client.dp_client.invoke = MagicMock(return_value=mock_response)

                client.invoke({"key": "value"}, timeout=60)

                client.dp_client.invoke.assert_called_once_with(
                    session_id=client.session_id,
                    payload={"key": "value"},
                    timeout=60
                )

    def test_invoke_without_session_id(self):
        """Test that invoke fails without session ID."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient"):
                client = AgentRuntimeClient(agent_name="test-agent")
                client.session_id = None

                with pytest.raises(ValueError, match="session_id is not initialized"):
                    client.invoke({"key": "value"})

    def test_invoke_with_timeout(self):
        """Test invocation with custom timeout."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient") as mock_dp:
                client = AgentRuntimeClient(agent_name="test-agent")
                mock_response = MagicMock()
                mock_response.json.return_value = {"result": "success"}
                client.dp_client = mock_dp.return_value
                client.dp_client.invoke = MagicMock(return_value=mock_response)

                result = client.invoke({"key": "value"}, timeout=60)

                assert result == {"result": "success"}


class TestAgentRuntimeClientClose:
    """Tests for AgentRuntimeClient.close method."""

    def test_close(self):
        """Test closing the client."""
        with patch.dict(os.environ, {"ROUTER_URL": "http://router"}):
            with patch("agentcube.agent_runtime.AgentRuntimeDataPlaneClient") as mock_dp:
                client = AgentRuntimeClient(agent_name="test-agent")
                client.dp_client = mock_dp.return_value
                client.dp_client.close = MagicMock()

                client.close()

                client.dp_client.close.assert_called_once()
