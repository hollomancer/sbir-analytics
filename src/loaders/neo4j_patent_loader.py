"""
sbir-etl/src/loaders/neo4j_patent_loader.py

Neo4j loader for patent CET classifications with idempotent MERGE operations.

Features
- Import-safe: Neo4j driver is imported lazily; module import does not require the dependency.
- Idempotent upserts (MERGE) for:
  - CETArea nodes (unique by id)
  - Patent nodes (unique by patent_id)
  - CLASSIFIED_AS relationships (Patent)-[:CLASSIFIED_AS]->(CETArea)
- Batched operations to support large datasets without exceeding transaction limits.
- Optional constraints creation on first use.

Node schemas (suggested; adapt as needed)
- (:CETArea { id: STRING, name: STRING, taxonomy_version: STRING, keywords: LIST<STRING>, updated_at: INTEGER(ms) })
- (:Patent { id: STRING, title: STRING, assignee: STRING, application_year: INTEGER, updated_at: INTEGER(ms) })

Relationship schema
- (Patent)-[:CLASSIFIED_AS {
    score: FLOAT,
    primary: BOOLEAN,
    classified_at: STRING (ISO-8601),
    model_version: STRING,
    taxonomy_version: STRING,
    first_classified_at: DATETIME,
    updated_at: DATETIME
  }]->(CETArea)

Usage example
-------------
from sbir_etl.src.loaders.neo4j_patent_loader import Neo4jPatentCETLoader

loader = Neo4jPatentCETLoader(uri="bolt://localhost:7687", user="neo4j", password="password")
loader.ensure_constraints()
loader.upsert_cet_areas([{"id": "artificial_intelligence", "name": "AI", "taxonomy_version": "2025.1"}])
loader.upsert_patents([{"patent_id": "US123", "title": "ML for sensors", "assignee": "Acme", "application_year": 2022}])
loader.link_patent_cet([
    {
        "patent_id": "US123",
        "cet_id": "artificial_intelligence",
        "score": 0.92,
        "primary": True,
        "classified_at": "2025-10-27T12:00:00Z",
        "model_version": "v1",
        "taxonomy_version": "2025.1",
    }
])
loader.close()
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

# Import neo4j lazily; avoid import error at module import time
try:
    from neo4j import Driver, GraphDatabase, Transaction  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    GraphDatabase = None  # type: ignore
    Driver = None  # type: ignore
    Transaction = None  # type: ignore


@dataclass
class Neo4jConfig:
    uri: str
    user: str
    password: str
    database: str = "neo4j"
    max_connection_lifetime: int = 3600  # seconds
    # Add other driver configs here if needed


class Neo4jPatentCETLoader:
    """
    Loader for CET patent classifications into Neo4j, using idempotent MERGE operations.

    This class can either receive a pre-configured neo4j.Driver or create one
    from URI/user/password. All operations are batched to keep transactions
    modest in size.
    """

    def __init__(
        self,
        driver: Driver | None = None,
        *,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str = "neo4j",
        max_connection_lifetime: int = 3600,
        auto_create_constraints: bool = False,
        batch_size: int = 1000,
    ) -> None:
        """
        Initialize the loader.

        Either provide an existing neo4j.Driver in `driver`, or pass uri/user/password.

        Parameters
        ----------
        driver : neo4j.Driver, optional
            Pre-existing driver instance.
        uri : str, optional
            Neo4j bolt URI, e.g., "bolt://localhost:7687".
        user : str, optional
            Neo4j username.
        password : str, optional
            Neo4j password.
        database : str
            Database name ("neo4j" by default).
        max_connection_lifetime : int
            Driver max connection lifetime in seconds.
        auto_create_constraints : bool
            When True, will attempt to create uniqueness constraints on first use.
        batch_size : int
            Default batch size for batched operations.
        """
        if driver is None:
            if GraphDatabase is None:  # pragma: no cover
                raise RuntimeError(
                    "Neo4j driver is not available. Install the 'neo4j' package to use this loader."
                )
            if not (uri and user and password):
                raise ValueError("Provide either a driver or uri/user/password")
            self._driver = GraphDatabase.driver(
                uri, auth=(user, password), max_connection_lifetime=max_connection_lifetime
            )
        else:
            self._driver = driver
        self._db = database
        self._auto_create_constraints = auto_create_constraints
        self._batch_size = int(batch_size) if batch_size and batch_size > 0 else 1000

        if self._auto_create_constraints:
            self.ensure_constraints()

    # -----------------------
    # Lifecycle
    # -----------------------
    def close(self) -> None:
        """Close the underlying neo4j driver."""
        if self._driver is not None:
            self._driver.close()

    # -----------------------
    # Constraints
    # -----------------------
    def ensure_constraints(self) -> None:
        """
        Create uniqueness constraints if they do not exist:
        - CETArea.id
        - Patent.id
        """
        stmts = [
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:CETArea) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Patent) REQUIRE p.id IS UNIQUE",
        ]
        with self._driver.session(database=self._db) as session:
            for cypher in stmts:
                session.execute_write(lambda tx, c=cypher: tx.run(c).consume())

    # -----------------------
    # Upserts (MERGE)
    # -----------------------
    def upsert_cet_areas(self, areas: Iterable[dict[str, Any]]) -> int:
        """
        Upsert CETArea nodes.

        Each dict may include keys:
        - id (required)
        - name (optional)
        - taxonomy_version (optional)
        - keywords (optional list[str])

        Returns number of processed rows.
        """
        rows = [a for a in areas if a and a.get("id")]
        if not rows:
            return 0

        query = """
        UNWIND $rows AS row
        WITH row
        MERGE (c:CETArea {id: row.id})
        ON CREATE SET
            c.created_at = timestamp()
        SET
            c.name = coalesce(row.name, c.name),
            c.taxonomy_version = coalesce(row.taxonomy_version, c.taxonomy_version),
            c.keywords = coalesce(row.keywords, c.keywords),
            c.updated_at = timestamp()
        """

        return self._run_batched_write(query, rows)

    def upsert_patents(self, patents: Iterable[dict[str, Any]]) -> int:
        """
        Upsert Patent nodes.

        Each dict may include keys:
        - patent_id (required; maps to :Patent {id})
        - title (optional)
        - assignee (optional)
        - application_year (optional int)

        Returns number of processed rows.
        """
        rows = []
        for p in patents:
            if not p:
                continue
            pid = p.get("patent_id") or p.get("id")
            if not pid:
                continue
            rows.append(
                {
                    "id": str(pid),
                    "title": p.get("title"),
                    "assignee": p.get("assignee"),
                    "application_year": p.get("application_year"),
                }
            )
        if not rows:
            return 0

        query = """
        UNWIND $rows AS row
        WITH row
        MERGE (p:Patent {id: row.id})
        ON CREATE SET
            p.created_at = timestamp()
        SET
            p.title = coalesce(row.title, p.title),
            p.assignee = coalesce(row.assignee, p.assignee),
            p.application_year = coalesce(row.application_year, p.application_year),
            p.updated_at = timestamp()
        """

        return self._run_batched_write(query, rows)

    def link_patent_cet(self, rels: Iterable[dict[str, Any]]) -> int:
        """
        Create/Update CLASSIFIED_AS relationships between Patent and CETArea.

        Each dict should include:
        - patent_id (str)
        - cet_id (str)
        - score (float)
        - primary (bool)
        - classified_at (ISO-8601 string) - optional
        - model_version (str) - optional
        - taxonomy_version (str) - optional
        """
        rows = []
        for r in rels:
            if not r:
                continue
            pid = r.get("patent_id")
            cid = r.get("cet_id")
            if not pid or not cid:
                continue
            rows.append(
                {
                    "patent_id": str(pid),
                    "cet_id": str(cid),
                    "score": float(r.get("score", 0.0)) if r.get("score") is not None else None,
                    "primary": bool(r.get("primary")) if r.get("primary") is not None else None,
                    "classified_at": r.get("classified_at"),
                    "model_version": r.get("model_version"),
                    "taxonomy_version": r.get("taxonomy_version"),
                }
            )

        if not rows:
            return 0

        query = """
        UNWIND $rows AS row
        MATCH (p:Patent {id: row.patent_id})
        MATCH (c:CETArea {id: row.cet_id})
        MERGE (p)-[r:CLASSIFIED_AS]->(c)
        ON CREATE SET
            r.first_classified_at = coalesce(
                CASE
                    WHEN row.classified_at IS NOT NULL
                    THEN datetime(row.classified_at)
                    ELSE datetime({epochMillis: timestamp()})
                END,
                datetime({epochMillis: timestamp()})
            )
        SET
            r.score = coalesce(row.score, r.score),
            r.primary = coalesce(row.primary, r.primary, false),
            r.classified_at = coalesce(row.classified_at, r.classified_at),
            r.model_version = coalesce(row.model_version, r.model_version),
            r.taxonomy_version = coalesce(row.taxonomy_version, r.taxonomy_version),
            r.updated_at = datetime({epochMillis: timestamp()})
        """

        return self._run_batched_write(query, rows)

    # -----------------------
    # Composite loader
    # -----------------------
    def load_classifications(
        self,
        classifications: Sequence[dict[str, Any]],
        *,
        cet_areas: Iterable[dict[str, Any]] | None = None,
        patents: Iterable[dict[str, Any]] | None = None,
        derive_patents_from_rows: bool = True,
    ) -> dict[str, int]:
        """
        Load a batch of patent classifications end-to-end:
        - Ensure constraints
        - Upsert CET areas (if provided)
        - Upsert Patent nodes (from provided patents or derived from classification rows)
        - Link Patent -> CET relationships

        Returns a dict with counts: {"cet_areas": int, "patents": int, "relationships": int}
        """
        self.ensure_constraints()

        counts = {"cet_areas": 0, "patents": 0, "relationships": 0}

        if cet_areas:
            counts["cet_areas"] = self.upsert_cet_areas(cet_areas)

        patent_rows: list[dict[str, Any]] = []
        if patents:
            patent_rows = list(patents)
        elif derive_patents_from_rows:
            # Derive minimal patent nodes from the classification rows
            seen = set()
            for row in classifications:
                pid = row.get("patent_id")
                if not pid or pid in seen:
                    continue
                seen.add(pid)
                patent_rows.append(
                    {"patent_id": pid, "title": row.get("title"), "assignee": row.get("assignee")}
                )

        if patent_rows:
            counts["patents"] = self.upsert_patents(patent_rows)

        if classifications:
            counts["relationships"] = self.link_patent_cet(classifications)

        return counts

    # -----------------------
    # Internals
    # -----------------------
    def _run_batched_write(self, cypher: str, rows: list[dict[str, Any]]) -> int:
        """
        Execute a write query in batches. Returns number of processed rows.

        cypher must accept a parameter $rows and UNWIND it.
        """
        total = 0
        batch_size = max(1, self._batch_size)
        with self._driver.session(database=self._db) as session:
            for i in range(0, len(rows), batch_size):
                chunk = rows[i : i + batch_size]
                session.execute_write(lambda tx, c=chunk: tx.run(cypher, rows=c).consume())
                total += len(chunk)
        return total
