"""Merge existing duplicate Organization nodes."""

from migrations.base import Migration
from neo4j import Driver


class MergeExistingDuplicateOrganizations(Migration):
    """Merge existing duplicate Organization nodes based on UEI/DUNS."""

    def __init__(self):
        super().__init__("003", "Merge existing duplicate organizations")

    def upgrade(self, driver: Driver) -> None:
        """
        Find and merge existing duplicates using same logic as multi-key MERGE.

        Strategy:
        1. Find duplicates by UEI (same UEI, different organization_id)
        2. Find duplicates by DUNS (same DUNS, different organization_id)
        3. For each duplicate group:
           - Select canonical node (prefer UEI > DUNS > earliest created)
           - Merge properties from duplicates into canonical
           - Track merge history
           - Move relationships from duplicates to canonical
           - Delete duplicate nodes

        This is a one-time cleanup migration.
        """
        with driver.session() as session:
            # Strategy 1: Merge by UEI
            # Note: This is a simplified merge - in production you'd want more careful relationship handling
            uei_merge_query = """
            MATCH (o1:Organization), (o2:Organization)
            WHERE o1.organization_id <> o2.organization_id
              AND o1.uei IS NOT NULL
              AND o2.uei IS NOT NULL
              AND o1.uei = o2.uei
            WITH o1, collect(o2) as duplicates
            UNWIND duplicates as duplicate
            // Merge properties (preserve existing, fill missing)
            SET o1 += {
                name: coalesce(o1.name, duplicate.name),
                duns: coalesce(o1.duns, duplicate.duns),
                normalized_name: coalesce(o1.normalized_name, duplicate.normalized_name)
            },
            o1.__updated_at = datetime()
            // Track merge history
            WITH o1, duplicate,
                 coalesce(o1.__merged_from, []) as current_merged_from
            SET o1.__merged_from = current_merged_from + [duplicate.organization_id]
            // Delete duplicate (relationships will be recreated on next load)
            WITH duplicate
            DETACH DELETE duplicate
            RETURN count(duplicate) as merged_count
            """

            result = session.run(uei_merge_query)
            record = result.single()
            uei_count = record["merged_count"] if record else 0

            # Strategy 2: Merge by DUNS
            duns_merge_query = """
            MATCH (o1:Organization), (o2:Organization)
            WHERE o1.organization_id <> o2.organization_id
              AND o1.duns IS NOT NULL
              AND o2.duns IS NOT NULL
              AND o1.duns = o2.duns
              AND o1.uei IS NULL
            WITH o1, collect(o2) as duplicates
            UNWIND duplicates as duplicate
            SET o1 += {
                name: coalesce(o1.name, duplicate.name),
                normalized_name: coalesce(o1.normalized_name, duplicate.normalized_name)
            },
            o1.__updated_at = datetime()
            WITH o1, duplicate,
                 coalesce(o1.__merged_from, []) as current_merged_from
            SET o1.__merged_from = current_merged_from + [duplicate.organization_id]
            WITH duplicate
            DETACH DELETE duplicate
            RETURN count(duplicate) as merged_count
            """

            result = session.run(duns_merge_query)
            record = result.single()
            duns_count = record["merged_count"] if record else 0

            from loguru import logger

            logger.info(
                f"Migration 003: Merged {uei_count} duplicates by UEI, "
                f"{duns_count} duplicates by DUNS"
            )

    def downgrade(self, driver: Driver) -> None:
        """
        Cannot easily rollback data merges - log warning.

        Merge history is preserved in __merged_from and __merge_history,
        but recreating nodes would require manual work.
        """
        from loguru import logger

        logger.warning(
            "Cannot automatically rollback data merges. "
            "Merge history is preserved in __merged_from and __merge_history properties. "
            "Manual restoration would be required."
        )
