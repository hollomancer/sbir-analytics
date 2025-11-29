"""Mock factories for Dagster execution contexts."""

from unittest.mock import Mock, PropertyMock
from dagster import build_asset_context


class ContextMocks:
    """Factory for creating mock Dagster execution contexts."""

    @staticmethod
    def context_with_logging():
        """Create a mock Dagster context with logging methods.

        Returns:
            Mock context with info, warning, and error log methods.
        """
        context = build_asset_context()
        mock_log = Mock()
        mock_log.info = Mock()
        mock_log.warning = Mock()
        mock_log.error = Mock()
        type(context).log = PropertyMock(return_value=mock_log)
        return context

    @staticmethod
    def performance_monitor():
        """Create a mock performance monitor with context manager support.

        Returns:
            Mock with monitor_block() that supports with statement.
        """
        mock_monitor = Mock()
        mock_monitor.monitor_block.return_value.__enter__ = Mock()
        mock_monitor.monitor_block.return_value.__exit__ = Mock(return_value=None)
        return mock_monitor
