"""Base migration class for Neo4j schema migrations."""

from abc import ABC, abstractmethod

from neo4j import Driver


class Migration(ABC):
    """Base class for Neo4j migrations."""

    def __init__(self, version: str, description: str):
        """
        Initialize migration.

        Args:
            version: Migration version (e.g., "001", "002")
            description: Human-readable description
        """
        self.version = version
        self.description = description

    @abstractmethod
    def upgrade(self, driver: Driver) -> None:
        """Apply migration."""
        pass

    @abstractmethod
    def downgrade(self, driver: Driver) -> None:
        """Rollback migration (optional)."""
        pass

    def get_id(self) -> str:
        """Get unique migration identifier."""
        return f"{self.version}_{self.description.lower().replace(' ', '_')}"
