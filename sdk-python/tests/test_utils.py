"""Tests for AgentCube SDK utility functions."""

import logging
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest
import requests

from agentcube.utils.log import get_logger
from agentcube.utils.utils import read_token_from_file
from agentcube.utils.http import create_session


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_creates_logger(self):
        """Test that get_logger creates a logger."""
        logger = get_logger("test_logger")
        assert logger is not None
        assert logger.name == "test_logger"

    def test_get_logger_level_default(self):
        """Test that get_logger uses default INFO level."""
        logger = get_logger("test_logger_default")
        assert logger.level == logging.INFO

    def test_get_logger_level_custom(self):
        """Test that get_logger uses custom level."""
        logger = get_logger("test_logger_debug", level=logging.DEBUG)
        assert logger.level == logging.DEBUG

    def test_get_logger_level_string(self):
        """Test that get_logger accepts string level."""
        logger = get_logger("test_logger_string", level="DEBUG")
        assert logger.level == logging.DEBUG

    def test_get_logger_has_handler(self):
        """Test that get_logger adds a handler."""
        logger = get_logger("test_logger_handler")
        assert len(logger.handlers) > 0

    def test_get_logger_multiple_calls_same_logger(self):
        """Test that multiple calls return same logger but don't add duplicate handlers."""
        logger1 = get_logger("test_logger_multi")
        logger2 = get_logger("test_logger_multi")
        assert logger1 is logger2


class TestReadTokenFromFile:
    """Tests for read_token_from_file function."""

    def test_read_token_from_file_success(self):
        """Test reading token from existing file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("test-token-123\n")
            temp_path = f.name

        try:
            token = read_token_from_file(temp_path)
            assert token == "test-token-123"
        finally:
            os.unlink(temp_path)

    def test_read_token_from_file_strips_whitespace(self):
        """Test that read_token_from_file strips whitespace."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write("  token-with-spaces  \n")
            temp_path = f.name

        try:
            token = read_token_from_file(temp_path)
            assert token == "token-with-spaces"
        finally:
            os.unlink(temp_path)

    def test_read_token_from_file_not_found(self):
        """Test that read_token_from_file returns empty string for missing file."""
        token = read_token_from_file("/nonexistent/path/token")
        assert token == ""

    def test_read_token_from_file_empty_file(self):
        """Test reading from empty file."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            temp_path = f.name

        try:
            token = read_token_from_file(temp_path)
            assert token == ""
        finally:
            os.unlink(temp_path)


class TestCreateSession:
    """Tests for create_session function."""

    def test_create_session_creates_session(self):
        """Test that create_session creates a requests Session."""
        session = create_session()
        assert isinstance(session, requests.Session)

    def test_create_session_default_pool_size(self):
        """Test create_session with default pool sizes."""
        session = create_session()
        adapter = session.get_adapter('https://')
        assert adapter is not None

    def test_create_session_custom_pool_size(self):
        """Test create_session with custom pool sizes."""
        session = create_session(pool_connections=20, pool_maxsize=30)
        assert isinstance(session, requests.Session)

    def test_create_session_has_http_adapter(self):
        """Test that created session has HTTP adapters mounted."""
        session = create_session()
        assert session.get_adapter('http://') is not None
        assert session.get_adapter('https://') is not None
