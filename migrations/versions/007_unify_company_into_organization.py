"""Unify the legacy :Company node onto :Organization.

Phase 2 of the unify-graph-node-labels spec. The authoritative SBIR loader writes
``:Organization`` nodes (key ``organization_id``, also carrying indexed ``uei`` /
``duns`` properties), while legacy enrichment loaders wrote a disjoint ``:Company``
node (matched by ``uei``) that held business-categorization and SEC-EDGAR
enrichment properties. Because the two node sets are disjoint for the same firm,
every cross-model query silently traversed nothing.

Unlike Phase 1 (:Award), ``:Company`` is a **property-only** enrichment node — no
relationship type has a ``:Company`` endpoint (``OWNS`` / ``SPECIALIZES_IN`` /
``ACHIEVED`` already use ``:Organization``), so there are no edges to re-home.

This migration, for each ``:Company`` whose ``uei`` matches an ``:Organization``:
  * copies the enrichment properties of the ``:Company`` onto the matched
    ``:Organization`` (``SET o += properties(c)``), while **preserving** the
    Organization's authoritative identity (``name`` / ``normalized_name`` /
    ``organization_id``) and dropping the legacy ``company_id`` key;
  * ``DETACH DELETE``s the consumed ``:Company``.

Orphan ``:Company`` nodes (no matching ``:Organization`` for their ``uei``, or no
``uei`` at all) are logged and LEFT IN PLACE so no data is lost.

It is idempotent (re-runs find no remaining matched ``:Company``) and batched via
apoc-free Cypher. Finally it drops the legacy ``:Company`` constraint/indexes and
creates the equivalent enrichment indexes on ``:Organization``.

WARNING: this migration ``DETACH DELETE``s nodes. Back up the graph and run a
dry-run before applying to a live database.
"""

from loguru import logger
from migrations.base import Migration
from neo4j import Driver  # type: ignore[attr-defined]

# Batch size for the re-home loop (number of :Company nodes processed per write tx).
_BATCH_SIZE = 1000

# Legacy :Company schema objects dropped on upgrade (recreated on downgrade).
_LEGACY_COMPANY_SCHEMA = (
    "DROP CONSTRAINT company_id IF EXISTS",
    "DROP INDEX company_name IF EXISTS",
    "DROP INDEX company_normalized_name IF EXISTS",
    "DROP INDEX company_uei IF EXISTS",
    "DROP INDEX company_duns IF EXISTS",
    "DROP INDEX company_classification_idx IF EXISTS",
    "DROP INDEX company_categorization_confidence_idx IF EXISTS",
    "DROP INDEX company_classification_confidence_idx IF EXISTS",
    "DROP INDEX company_sec_cik_idx IF EXISTS",
    "DROP INDEX company_sec_publicly_traded_idx IF EXISTS",
    "DROP INDEX company_sec_ticker_idx IF EXISTS",
)

# Enrichment indexes re-homed onto :Organization (so post-migration lookups on the
# categorization / SEC properties stay indexed).
_ORGANIZATION_ENRICHMENT_INDEXES = (
    "CREATE INDEX org_classification_idx IF NOT EXISTS FOR (o:Organization) ON (o.classification)",
    "CREATE INDEX org_categorization_confidence_idx IF NOT EXISTS "
    "FOR (o:Organization) ON (o.categorization_confidence)",
    "CREATE INDEX org_classification_confidence_idx IF NOT EXISTS "
    "FOR (o:Organization) ON (o.classification, o.categorization_confidence)",
    "CREATE INDEX org_sec_cik_idx IF NOT EXISTS FOR (o:Organization) ON (o.sec_cik)",
    "CREATE INDEX org_sec_publicly_traded_idx IF NOT EXISTS "
    "FOR (o:Organization) ON (o.sec_is_publicly_traded)",
    "CREATE INDEX org_sec_ticker_idx IF NOT EXISTS FOR (o:Organization) ON (o.sec_ticker)",
)


class UnifyCompanyIntoOrganization(Migration):
    """Re-home legacy :Company enrichment onto :Organization and drop legacy schema."""

    def __init__(self) -> None:
        super().__init__("007", "Unify Company into Organization")

    def upgrade(self, driver: Driver) -> None:
        """Merge matched :Company properties onto :Organization, then drop legacy schema."""
        with driver.session() as session:
            # 1. Report orphans (no matching Organization for the uei) up front; leave in place.
            orphan_record = session.run(
                """
                MATCH (c:Company)
                WHERE c.uei IS NULL
                   OR NOT EXISTS {
                    MATCH (o:Organization {uei: c.uei})
                }
                RETURN count(c) AS n
                """
            ).single()
            orphan_count = orphan_record["n"] if orphan_record else 0
            if orphan_count:
                logger.warning(
                    "{} :Company node(s) have no matching :Organization (by uei); "
                    "leaving them in place (data preserved, not deleted).",
                    orphan_count,
                )

            # 2. Re-home matched :Company nodes in batches until none remain.
            total_rehomed = 0
            while True:
                record = session.execute_write(self._rehome_batch)
                rehomed = record["rehomed"]
                total_rehomed += rehomed
                if rehomed < _BATCH_SIZE:
                    break

            logger.info(
                "Unified {} :Company node(s) onto :Organization ({} orphan(s) left in place).",
                total_rehomed,
                orphan_count,
            )

            # 3. Drop legacy :Company constraint/indexes; create :Organization enrichment indexes.
            for stmt in (*_LEGACY_COMPANY_SCHEMA, *_ORGANIZATION_ENRICHMENT_INDEXES):
                try:
                    session.run(stmt)
                except Exception as e:  # pragma: no cover - defensive
                    logger.debug("Schema statement skipped: {} ({})", stmt, e)

    @staticmethod
    def _rehome_batch(tx) -> dict:  # type: ignore[no-untyped-def]
        """Merge a single batch of matched :Company nodes within one transaction.

        Copies :Company properties onto the matched :Organization while preserving
        the Organization's authoritative identity (name / normalized_name /
        organization_id) and dropping the legacy company_id key, then DETACH DELETEs
        the consumed :Company node. Returns the number re-homed.
        """
        result = tx.run(
            """
            MATCH (c:Company)
            MATCH (o:Organization {uei: c.uei})
            WITH c, o
            LIMIT $batch_size

            // Preserve the Organization's authoritative identity before the merge.
            WITH c, o,
                 o.name AS o_name,
                 o.normalized_name AS o_normalized_name,
                 o.organization_id AS o_organization_id

            // Copy all :Company properties onto the matched Organization.
            SET o += properties(c)

            // Restore the authoritative identity and drop the legacy key.
            SET o.name = o_name,
                o.normalized_name = o_normalized_name,
                o.organization_id = o_organization_id
            REMOVE o.company_id

            // Remove the now-consumed :Company node.
            WITH c
            DETACH DELETE c
            RETURN count(c) AS rehomed
            """,
            batch_size=_BATCH_SIZE,
        )
        record = result.single()
        return {"rehomed": record["rehomed"] if record else 0}

    def downgrade(self, driver: Driver) -> None:
        """Recreate the legacy :Company constraint and indexes.

        NOTE: this downgrade is intentionally partial. The node-merge is NOT
        perfectly reversible: once :Company enrichment properties have been merged
        onto :Organization and the :Company nodes deleted, there is no reliable way
        to re-derive which properties originated on the legacy :Company node. This
        restores the legacy schema objects only; it does not re-split nodes. Restore
        from a pre-migration backup if a full rollback is required.
        """
        statements = (
            "CREATE CONSTRAINT company_id IF NOT EXISTS "
            "FOR (c:Company) REQUIRE c.company_id IS UNIQUE",
            "CREATE INDEX company_name IF NOT EXISTS FOR (c:Company) ON (c.name)",
            "CREATE INDEX company_normalized_name IF NOT EXISTS "
            "FOR (c:Company) ON (c.normalized_name)",
            "CREATE INDEX company_uei IF NOT EXISTS FOR (c:Company) ON (c.uei)",
            "CREATE INDEX company_duns IF NOT EXISTS FOR (c:Company) ON (c.duns)",
            "CREATE INDEX company_classification_idx IF NOT EXISTS "
            "FOR (c:Company) ON (c.classification)",
            "CREATE INDEX company_categorization_confidence_idx IF NOT EXISTS "
            "FOR (c:Company) ON (c.categorization_confidence)",
            "CREATE INDEX company_classification_confidence_idx IF NOT EXISTS "
            "FOR (c:Company) ON (c.classification, c.categorization_confidence)",
            "CREATE INDEX company_sec_cik_idx IF NOT EXISTS FOR (c:Company) ON (c.sec_cik)",
            "CREATE INDEX company_sec_publicly_traded_idx IF NOT EXISTS "
            "FOR (c:Company) ON (c.sec_is_publicly_traded)",
            "CREATE INDEX company_sec_ticker_idx IF NOT EXISTS FOR (c:Company) ON (c.sec_ticker)",
        )
        with driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception as e:  # pragma: no cover - defensive
                    logger.debug("Legacy schema recreate statement skipped: {} ({})", stmt, e)
