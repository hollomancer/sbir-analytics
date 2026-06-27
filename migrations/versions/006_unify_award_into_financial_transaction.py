"""Unify the legacy :Award node onto :FinancialTransaction.

Phase 1 of the unify-graph-node-labels spec. The authoritative SBIR loader writes
``:FinancialTransaction`` nodes (key ``transaction_id``, also carrying ``award_id``),
while legacy enrichment loaders wrote a disjoint ``:Award`` node (key ``award_id``)
that held CET enrichment and was the endpoint of ``APPLICABLE_TO`` and
``GENERATED_FROM``. Because the two node sets are disjoint for the same award, every
cross-model query silently traversed nothing.

This migration re-homes, for each ``:Award`` whose ``award_id`` matches a
``:FinancialTransaction``:
  * all ``:Award`` properties (``SET ft += properties(a)``);
  * ``(a)-[:APPLICABLE_TO]->(c)``  ⇒  ``(ft)-[:APPLICABLE_TO]->(c)``;
  * ``(p)-[:GENERATED_FROM]->(a)``  ⇒  ``(p)-[:GENERATED_FROM]->(ft)``;

then ``DETACH DELETE``s the matched ``:Award``. Orphan ``:Award`` nodes (no matching
FinancialTransaction) are logged and LEFT IN PLACE so no data is lost.

It is idempotent (re-runs find no remaining matched ``:Award``) and batched via
``apoc``-free Cypher. Finally it drops the legacy ``:Award`` unique constraint and
the ``award_date`` / ``award_topic_code`` indexes.

WARNING: this migration ``DETACH DELETE``s nodes. Back up the graph and run a
dry-run before applying to a live database.
"""

from loguru import logger
from migrations.base import Migration
from neo4j import Driver  # type: ignore[attr-defined]

# Batch size for the re-home loop (number of :Award nodes processed per write tx).
_BATCH_SIZE = 1000


class UnifyAwardIntoFinancialTransaction(Migration):
    """Re-home legacy :Award nodes onto :FinancialTransaction and drop legacy schema."""

    def __init__(self) -> None:
        super().__init__("006", "Unify Award into FinancialTransaction")

    def upgrade(self, driver: Driver) -> None:
        """Re-home matched :Award nodes onto :FinancialTransaction, then drop legacy schema."""
        with driver.session() as session:
            # 1. Report orphans (no matching FinancialTransaction) up front; leave them in place.
            orphan_record = session.run(
                """
                MATCH (a:Award)
                WHERE NOT EXISTS {
                    MATCH (ft:FinancialTransaction {award_id: a.award_id})
                }
                RETURN count(a) AS n
                """
            ).single()
            orphan_count = orphan_record["n"] if orphan_record else 0
            if orphan_count:
                logger.warning(
                    "{} :Award node(s) have no matching :FinancialTransaction; "
                    "leaving them in place (data preserved, not deleted).",
                    orphan_count,
                )

            # 2. Re-home matched :Award nodes in batches until none remain.
            total_rehomed = 0
            while True:
                record = session.execute_write(self._rehome_batch)
                rehomed = record["rehomed"]
                total_rehomed += rehomed
                if rehomed < _BATCH_SIZE:
                    break

            logger.info(
                "Unified {} :Award node(s) onto :FinancialTransaction "
                "({} orphan(s) left in place).",
                total_rehomed,
                orphan_count,
            )

            # 3. Drop legacy :Award constraint and indexes (safe if already absent).
            for stmt in (
                "DROP CONSTRAINT award_id IF EXISTS",
                "DROP INDEX award_date IF EXISTS",
                "DROP INDEX award_topic_code IF EXISTS",
            ):
                try:
                    session.run(stmt)
                except Exception as e:  # pragma: no cover - defensive
                    logger.debug("Legacy schema drop statement skipped: {} ({})", stmt, e)

    @staticmethod
    def _rehome_batch(tx) -> dict:  # type: ignore[no-untyped-def]
        """Re-home a single batch of matched :Award nodes within one transaction.

        Copies :Award properties onto the matched FinancialTransaction, re-homes
        APPLICABLE_TO and GENERATED_FROM edges (copying relationship properties),
        then DETACH DELETEs the consumed :Award node. Returns the number re-homed.
        """
        result = tx.run(
            """
            MATCH (a:Award)
            MATCH (ft:FinancialTransaction {award_id: a.award_id})
            WITH a, ft
            LIMIT $batch_size

            // Copy all :Award properties onto the matched FinancialTransaction.
            SET ft += properties(a)

            // Re-home APPLICABLE_TO edges (a)->(c), copying relationship properties.
            WITH a, ft
            CALL {
                WITH a, ft
                MATCH (a)-[r:APPLICABLE_TO]->(c)
                MERGE (ft)-[r2:APPLICABLE_TO]->(c)
                SET r2 += properties(r)
                RETURN count(r) AS applicable_to
            }

            // Re-home GENERATED_FROM edges (p)->(a), copying relationship properties.
            WITH a, ft, applicable_to
            CALL {
                WITH a, ft
                MATCH (p)-[r:GENERATED_FROM]->(a)
                MERGE (p)-[r2:GENERATED_FROM]->(ft)
                SET r2 += properties(r)
                RETURN count(r) AS generated_from
            }

            // Remove the now-consumed :Award node and any remaining edges.
            WITH a, applicable_to, generated_from
            DETACH DELETE a
            RETURN count(a) AS rehomed,
                   sum(applicable_to) AS applicable_to,
                   sum(generated_from) AS generated_from
            """,
            batch_size=_BATCH_SIZE,
        )
        record = result.single()
        return {
            "rehomed": record["rehomed"] if record else 0,
            "applicable_to": (record["applicable_to"] or 0) if record else 0,
            "generated_from": (record["generated_from"] or 0) if record else 0,
        }

    def downgrade(self, driver: Driver) -> None:
        """Recreate the legacy :Award constraint and indexes.

        NOTE: this downgrade is intentionally partial. The node-split is NOT
        perfectly reversible: once :Award properties and edges have been merged
        onto :FinancialTransaction and the :Award nodes deleted, there is no
        reliable way to re-derive which properties/edges originated on the legacy
        :Award node. This restores the legacy schema objects only; it does not
        re-split nodes. Restore from a pre-migration backup if a full rollback is
        required.
        """
        statements = (
            "CREATE CONSTRAINT award_id IF NOT EXISTS FOR (a:Award) REQUIRE a.award_id IS UNIQUE",
            "CREATE INDEX award_date IF NOT EXISTS FOR (a:Award) ON (a.award_date)",
            "CREATE INDEX award_topic_code IF NOT EXISTS FOR (a:Award) ON (a.topic_code)",
        )
        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:  # pragma: no cover - defensive
                    logger.debug("Legacy schema recreate statement skipped: {} ({})", stmt, e)
