"""Mock factories for DuckDB connections and operations."""

from unittest.mock import Mock


class DuckDBMocks:
    """Factory for creating mock DuckDB connections and results."""

    @staticmethod
    def connection():
        """Create a mock DuckDB connection.

        Returns:
            Mock connection with execute, close, and fetchone methods.
        """
        conn = Mock()
        conn.execute = Mock(return_value=Mock(fetchone=Mock(return_value=(100,))))
        conn.close = Mock()
        return conn

    @staticmethod
    def connection_with_result(result):
        """Create a mock DuckDB connection with specific result.

        Args:
            result: The result to return from fetchone()

        Returns:
            Mock connection configured to return the specified result.
        """
        conn = Mock()
        conn.execute = Mock(return_value=Mock(fetchone=Mock(return_value=result)))
        conn.close = Mock()
        return conn
