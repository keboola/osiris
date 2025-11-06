#!/usr/bin/env python3

"""Tests for CLI chat interface."""

import logging
from unittest.mock import patch

import pytest

pytest_plugins = ("pytest_asyncio",)

try:
    from osiris.cli.chat import SessionAwareFormatter, SessionLogFilter
    from osiris.cli.chat import chat as chat_main
    from osiris.cli.chat import set_session_context

    MODULES_AVAILABLE = True
except ImportError:
    MODULES_AVAILABLE = False


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Chat modules not available")
class TestSessionAwareFormatter:
    """Test cases for SessionAwareFormatter."""

    def test_format_with_existing_session_id(self):
        """Test formatting log record with existing session_id."""
        formatter = SessionAwareFormatter("%(session_id)s - %(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.session_id = "test_session"

        result = formatter.format(record)

        assert "test_session - Test message" in result


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Chat modules not available")
class TestSessionLogFilter:
    """Test cases for SessionLogFilter."""

    def test_filter_adds_session_id(self):
        """Test that filter adds session_id to log records."""
        filter_obj = SessionLogFilter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        with patch("osiris.cli.chat._session_context") as mock_context:
            mock_context.session_id = "filtered_session"
            result = filter_obj.filter(record)

        assert result is True
        assert record.session_id == "filtered_session"


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Chat modules not available")
class TestChatFunctionality:
    """Test cases for chat functionality."""

    @pytest.mark.asyncio
    async def test_basic_functionality(self):
        """Test basic chat functionality exists."""
        # Just test that functions can be imported and called
        assert callable(chat_main)


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Chat modules not available")
class TestUtilityFunctions:
    """Test cases for utility functions."""

    def test_set_session_context(self):
        """Test setting session context."""
        with patch("osiris.cli.chat._session_context") as mock_context:
            set_session_context("new_session")
            assert mock_context.session_id == "new_session"

    def test_basic_utility_functions(self):
        """Test basic utility functions exist."""
        # Just test that functions can be imported and called
        assert callable(set_session_context)


@pytest.mark.skipif(not MODULES_AVAILABLE, reason="Chat modules not available")
class TestMainFunction:
    """Test cases for main function."""

    @pytest.mark.asyncio
    async def test_main_function_exists(self):
        """Test main function can be called."""
        # Basic test to verify main function exists and can be imported
        assert callable(chat_main)
