"""Drop LightRAG-era vector indexes (award_embedding, patent_embedding).

PaECTER computes cosine similarity in NumPy, not via Neo4j vector queries,
so these indexes are unused. The underlying .embedding properties on Award
and Patent nodes (if any) are preserved — only the index definitions are
dropped.
"""

from migrations.base import Migration
from neo4j import Driver  # type: ignore[attr-defined]


class DropLightRAGVectorIndexes(Migration):
    """Drop award_embedding and patent_embedding vector indexes."""

    def __init__(self):
        super().__init__("005", "Drop LightRAG-era vector indexes")

    def upgrade(self, driver: Driver) -> None:
        statements = [
            "DROP INDEX award_embedding IF EXISTS",
            "DROP INDEX patent_embedding IF EXISTS",
        ]
        with driver.session() as session:
            for stmt in statements:
                session.run(stmt)

    def downgrade(self, driver: Driver) -> None:
        statements = [
            """CREATE VECTOR INDEX award_embedding IF NOT EXISTS
               FOR (a:Award) ON (a.embedding)
               OPTIONS {indexConfig: {
                 `vector.dimensions`: 768,
                 `vector.similarity_function`: 'cosine'
               }}""",
            """CREATE VECTOR INDEX patent_embedding IF NOT EXISTS
               FOR (p:Patent) ON (p.embedding)
               OPTIONS {indexConfig: {
                 `vector.dimensions`: 768,
                 `vector.similarity_function`: 'cosine'
               }}""",
        ]
        with driver.session() as session:
            for stmt in statements:
                session.run(stmt)
