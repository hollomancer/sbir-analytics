"""Mock factories for Neo4j components."""

from typing import Any
from unittest.mock import Mock


class Neo4jMocks:
    """Factory for Neo4j mock objects."""

    @staticmethod
    def driver(verify_connectivity: bool = True, **kwargs) -> Mock:
        """Create a mock Neo4j driver."""
        driver = Mock()
        driver.verify_connectivity = Mock(return_value=verify_connectivity)
        driver.close = Mock()
        driver.session = Mock(return_value=Neo4jMocks.session())

        for key, value in kwargs.items():
            setattr(driver, key, value)

        return driver

    @staticmethod
    def session(run_results: list[Any] | None = None, **kwargs) -> Mock:
        """Create a mock Neo4j session."""
        session = Mock()
        session.run = Mock(return_value=run_results or [])
        session.close = Mock()
        session.begin_transaction = Mock(return_value=Neo4jMocks.transaction())

        # Context manager support
        session.__enter__ = Mock(return_value=session)
        session.__exit__ = Mock(return_value=None)

        for key, value in kwargs.items():
            setattr(session, key, value)

        return session

    @staticmethod
    def transaction(commit_success: bool = True, **kwargs) -> Mock:
        """Create a mock Neo4j transaction."""
        tx = Mock()
        # Create a proper result mock with consume() method
        mock_result = Mock()
        mock_result.consume = Mock(return_value=None)
        mock_result.data = Mock(return_value=[])
        tx.run = Mock(return_value=mock_result)
        tx.commit = Mock(return_value=commit_success)
        tx.rollback = Mock()

        for key, value in kwargs.items():
            setattr(tx, key, value)

        return tx

    @staticmethod
    def result(records: list[dict] | None = None, **kwargs) -> Mock:
        """Create a mock Neo4j result."""
        result = Mock()
        result.data = Mock(return_value=records or [])
        result.single = Mock(return_value=records[0] if records else None)
        result.values = Mock(return_value=[list(r.values()) for r in (records or [])])
        result.__iter__ = Mock(return_value=iter(records or []))

        for key, value in kwargs.items():
            setattr(result, key, value)

        return result

    @staticmethod
    def config(uri: str = "bolt://localhost:7687", **kwargs) -> Mock:
        """Create a mock Neo4j configuration."""
        config = Mock()
        config.uri = uri
        config.username = kwargs.get("username", "neo4j")
        config.password = kwargs.get("password", "password")
        config.database = kwargs.get("database", "neo4j")
        config.batch_size = kwargs.get("batch_size", 1000)

        for key, value in kwargs.items():
            if key not in ["username", "password", "database", "batch_size"]:
                setattr(config, key, value)

        return config
