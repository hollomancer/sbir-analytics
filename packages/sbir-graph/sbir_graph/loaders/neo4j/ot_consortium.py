"""Neo4j loader for OT consortium verification tiers.

Models the consortium award chain:

    (CMF)-[:MANAGES]->(BaseOT)-[:HAS_ORDER]->(ProjectOT)-[:PERFORMED_BY]->(Firm)

The ``PERFORMED_BY`` edge is created ONLY for tier T1 (member-confirmed). For
T2/T3/T4 the member identity is not derivable from federal data, so the edge is
deliberately left absent — the graph must not imply an attribution the federal
record cannot support. Every ProjectOT node still carries its tier and confidence
note so the unverifiable population is queryable.
"""

from __future__ import annotations

import pandas as pd
from loguru import logger

from .base import BaseNeo4jLoader
from .client import Neo4jClient

# Tier value (matches sbir_etl.ot_consortium.models.VerificationTier) that earns
# a PERFORMED_BY edge. Kept as a literal to avoid a sbir_etl import in sbir-graph.
T1_MEMBER_CONFIRMED = "T1_member_confirmed"


class OTConsortiumLoader(BaseNeo4jLoader):
    """Load OT consortium tier assignments into Neo4j."""

    def __init__(self, client: Neo4jClient):
        super().__init__(client)

    def ensure_indexes(self) -> None:
        """Create indexes for the OT consortium node labels."""
        self.create_indexes(
            [
                "CREATE INDEX project_ot_award_id IF NOT EXISTS FOR (p:ProjectOT) ON (p.award_id)",
                "CREATE INDEX project_ot_tier IF NOT EXISTS FOR (p:ProjectOT) ON (p.tier)",
                "CREATE INDEX base_ot_piid IF NOT EXISTS FOR (b:BaseOT) ON (b.piid)",
                "CREATE INDEX cmf_name IF NOT EXISTS FOR (c:CMF) ON (c.name)",
                "CREATE INDEX ot_firm_uei IF NOT EXISTS FOR (f:Firm) ON (f.uei)",
            ]
        )

    def load_tier_assignments(self, df: pd.DataFrame) -> int:
        """Load tier assignments as ProjectOT nodes and their consortium chain.

        Expected columns: ``award_id``, ``tier``, ``piid``, ``parent_piid``,
        ``cmf_name``, ``firm_uei``, ``obligation_amount``, ``agency``,
        ``fiscal_year``, ``confidence_note``.

        Returns:
            Number of ProjectOT nodes created/updated.
        """
        if df is None or df.empty:
            logger.warning("No OT tier assignments to load")
            return 0

        records = df.to_dict("records")

        # 1) ProjectOT nodes (every tier — T2/T3/T4 are first-class).
        project_nodes = [
            {
                "award_id": str(r.get("award_id") or ""),
                "piid": _opt(r.get("piid")),
                "tier": str(r.get("tier") or ""),
                "obligation_amount": _num(r.get("obligation_amount")),
                "agency": _opt(r.get("agency")),
                "fiscal_year": _opt(r.get("fiscal_year")),
                "confidence_note": _opt(r.get("confidence_note")),
            }
            for r in records
            if r.get("award_id")
        ]
        self.batch_upsert_nodes("ProjectOT", "award_id", project_nodes)

        # 2) CMF and BaseOT nodes (where derivable).
        cmf_nodes = [{"name": n} for n in _distinct(records, "cmf_name")]
        base_nodes = [{"piid": p} for p in _distinct(records, "parent_piid")]
        firm_nodes = [{"uei": u} for u in _distinct(records, "firm_uei")]
        self.batch_upsert_nodes("CMF", "name", cmf_nodes)
        self.batch_upsert_nodes("BaseOT", "piid", base_nodes)
        self.batch_upsert_nodes("Firm", "uei", firm_nodes)

        # 3) Relationships.
        manages: list[tuple[str, str, dict | None]] = []
        has_order: list[tuple[str, str, dict | None]] = []
        performed_by: list[tuple[str, str, dict | None]] = []
        for r in records:
            award_id = str(r.get("award_id") or "")
            cmf = _opt(r.get("cmf_name"))
            parent = _opt(r.get("parent_piid"))
            firm = _opt(r.get("firm_uei"))
            tier = str(r.get("tier") or "")

            if cmf and parent:
                manages.append((str(cmf), str(parent), None))
            if parent and award_id:
                has_order.append((str(parent), award_id, None))
            # PERFORMED_BY only when member-confirmed (T1).
            if tier == T1_MEMBER_CONFIRMED and award_id and firm:
                performed_by.append((award_id, str(firm), {"tier": tier}))

        self.batch_create_relationships("CMF", "name", "BaseOT", "piid", "MANAGES", manages)
        self.batch_create_relationships(
            "BaseOT", "piid", "ProjectOT", "award_id", "HAS_ORDER", has_order
        )
        self.batch_create_relationships(
            "ProjectOT", "award_id", "Firm", "uei", "PERFORMED_BY", performed_by
        )

        logger.info(
            "OT consortium load: {} ProjectOT, {} PERFORMED_BY (T1 only), {} unverifiable left "
            "intentionally unlinked",
            len(project_nodes),
            len(performed_by),
            len(project_nodes) - len(performed_by),
        )
        return len(project_nodes)


def _opt(value: object) -> object | None:
    """Return a cleaned scalar or None for blank/NaN values."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _num(value: object) -> float:
    try:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return 0.0
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _distinct(records: list[dict], key: str) -> list[str]:
    seen: list[str] = []
    for r in records:
        v = _opt(r.get(key))
        if v is not None and str(v) not in seen:
            seen.append(str(v))
    return seen
