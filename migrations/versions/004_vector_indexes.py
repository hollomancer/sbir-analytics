"""Vector indexes for cross-reference support."""

from migrations.base import Migration
from neo4j import Driver  # type: ignore[attr-defined]


class VectorIndexes(Migration):
    """Create cross-reference indexes for Award nodes."""

    def __init__(self):
        super().__init__("004", "Vector indexes")

    def upgrade(self, driver: Driver) -> None:
        """Create cross-reference indexes."""
        statements = [
            # Index on Award.topic_code for solicitation cross-referencing
            "CREATE INDEX award_topic_code IF NOT EXISTS FOR (a:Award) ON (a.topic_code)",
        ]

        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:
                    from loguru import logger

                    logger.debug(f"Schema statement may already exist: {e}")

    def downgrade(self, driver: Driver) -> None:
        """Remove cross-reference indexes."""
        statements = [
            "DROP INDEX award_topic_code IF EXISTS",
        ]

        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception:
                    pass
