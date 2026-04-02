"""LightRAG schema: vector indexes and cross-reference support."""

from migrations.base import Migration
from neo4j import Driver  # type: ignore[attr-defined]


class LightRAGSchema(Migration):
    """Create vector indexes for Award/Patent embeddings and LightRAG cross-reference indexes."""

    def __init__(self):
        super().__init__("004", "LightRAG schema and vector indexes")

    def upgrade(self, driver: Driver) -> None:
        """Create vector indexes and cross-reference indexes."""
        statements = [
            # Vector index for Award embeddings (768-dim ModernBERT-Embed, cosine similarity)
            # Enables real-time k-NN queries: CALL db.index.vector.queryNodes(...)
            """CREATE VECTOR INDEX award_embedding IF NOT EXISTS
               FOR (a:Award) ON (a.embedding)
               OPTIONS {indexConfig: {
                 `vector.dimensions`: 768,
                 `vector.similarity_function`: 'cosine'
               }}""",
            # Vector index for Patent embeddings
            """CREATE VECTOR INDEX patent_embedding IF NOT EXISTS
               FOR (p:Patent) ON (p.embedding)
               OPTIONS {indexConfig: {
                 `vector.dimensions`: 768,
                 `vector.similarity_function`: 'cosine'
               }}""",
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
        """Remove vector indexes and cross-reference indexes."""
        statements = [
            "DROP INDEX award_embedding IF EXISTS",
            "DROP INDEX patent_embedding IF EXISTS",
            "DROP INDEX award_topic_code IF EXISTS",
        ]

        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception:
                    pass
