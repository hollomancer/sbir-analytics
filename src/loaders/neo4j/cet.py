"""CET Loader for Neo4j Graph Operations

Implements Section 12 (Neo4j CET Graph Model - Nodes):

12.1 Create CETArea node schema
12.2 Add uniqueness constraints for CETArea
12.3 Add CETArea properties (id, name, keywords, taxonomy_version)
12.4 Create Company node CET enrichment properties
12.5 Create Award node CET enrichment properties
12.6 Add batching + idempotent merges

This module provides CETLoader with helpers to:
- Create constraints and indexes for CETArea
- Upsert CETArea nodes (idempotent MERGE via Neo4jClient)
- Upsert Company and Award enrichment properties related to CET classifications

Notes:
- Relies on Neo4jClient for batching and transaction mgmt
- Properties are carefully whitelisted to avoid accidental large payloads
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any

from loguru import logger

from .base import BaseLoaderConfig, BaseNeo4jLoader
from .client import LoadMetrics, Neo4jClient


class CETLoaderConfig(BaseLoaderConfig):
    """Configuration for CET loading operations."""


class CETLoader(BaseNeo4jLoader):
    """Loads CET taxonomy and enrichment properties into Neo4j.

    Responsibilities:
      - Define CETArea schema (constraints + indexes)
      - Idempotently upsert CETArea nodes
      - Add CET enrichment properties to Company and Award nodes

    Refactored to inherit from BaseNeo4jLoader for consistency.

    Attributes:
        client: Neo4jClient for graph operations
        config: CETLoaderConfig with batch size and feature flags
        metrics: LoadMetrics for tracking operations (from base class)
    """

    def __init__(self, client: Neo4jClient, config: CETLoaderConfig | None = None) -> None:
        super().__init__(client)
        self.config = config or CETLoaderConfig()
        logger.info(
            "CETLoader initialized with batch_size={}, create_indexes={}, create_constraints={}",
            self.config.batch_size,
            self.config.create_indexes,
            self.config.create_constraints,
        )

    # -------------------------------------------------------------------------
    # Schema management
    # -------------------------------------------------------------------------

    def create_constraints(self, constraints: list[str] | None = None) -> None:  # type: ignore[override]
        """Create uniqueness constraints for CETArea and ensure existence of key entity constraints."""
        if constraints is None:
            constraints = [
            # CETArea uniqueness on cet_id
            "CREATE CONSTRAINT cetarea_cet_id IF NOT EXISTS "
            "FOR (c:CETArea) REQUIRE c.cet_id IS UNIQUE",
            # Optional: ensure Award and Company constraints exist for enrichment keys
            "CREATE CONSTRAINT award_award_id IF NOT EXISTS "
            "FOR (a:Award) REQUIRE a.award_id IS UNIQUE",
            "CREATE CONSTRAINT company_id IF NOT EXISTS "
            "FOR (c:Company) REQUIRE c.company_id IS UNIQUE",
        ]
        super().create_constraints(constraints)

    def create_indexes(self, indexes: list[str] | None = None) -> None:  # type: ignore[override]
        """Create indexes for frequently queried CETArea properties."""
        if indexes is None:
            indexes = [
            "CREATE INDEX cetarea_name_idx IF NOT EXISTS FOR (c:CETArea) ON (c.name)",
            "CREATE INDEX cetarea_taxonomy_version_idx IF NOT EXISTS "
            "FOR (c:CETArea) ON (c.taxonomy_version)",
        ]
        super().create_indexes(indexes)

    # -------------------------------------------------------------------------
    # CETArea upsert
    # -------------------------------------------------------------------------

    def load_cet_areas(
        self, areas: Iterable[dict[str, Any]], metrics: LoadMetrics | None = None
    ) -> LoadMetrics:
        """Upsert CETArea nodes.

        Each area dict may include:
          - cet_id (required)
          - name (required)
          - definition (optional)
          - keywords (list[str]) - optional
          - taxonomy_version (required)

        Args:
            areas: iterable of CET area dictionaries
            metrics: optional LoadMetrics to accumulate results

        Returns:
            LoadMetrics
        """
        metrics = metrics or LoadMetrics()

        area_nodes: list[dict[str, Any]] = []
        for raw in areas:
            cet_id = _as_str(raw.get("cet_id"))
            name = _as_str(raw.get("name"))
            taxonomy_version = _as_str(raw.get("taxonomy_version"))

            if not cet_id or not name or not taxonomy_version:
                logger.warning(
                    "Skipping CETArea missing required fields (cet_id, name, taxonomy_version): {}",
                    raw,
                )
                metrics.errors += 1
                continue

            node: dict[str, Any] = {
                "cet_id": cet_id,
                "name": name,
                "taxonomy_version": taxonomy_version,
            }

            # Optional definition
            if raw.get("definition"):
                node["definition"] = _as_str(raw.get("definition"))

            # Optional keywords (normalize to lowercase unique list)
            kw = raw.get("keywords")
            if isinstance(kw, list | tuple):
                node["keywords"] = _normalize_keywords(kw)

            area_nodes.append(node)

        if not area_nodes:
            logger.info("No CETArea nodes to upsert")
            return metrics

        # Upsert in batches using Neo4jClient
        logger.info("Upserting {} CETArea nodes", len(area_nodes))
        self.client.config.batch_size = self.config.batch_size
        metrics = self.client.batch_upsert_nodes(
            label="CETArea", key_property="cet_id", nodes=area_nodes, metrics=metrics
        )
        return metrics

    # -------------------------------------------------------------------------
    # Company enrichment properties
    # -------------------------------------------------------------------------

    def upsert_company_cet_enrichment(
        self,
        enrichments: Iterable[dict[str, Any]],
        *,
        key_property: str = "uei",
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Upsert CET enrichment properties onto Organization nodes (companies).

        Each enrichment dict must include the key property (default 'uei').
        Allowed enrichment properties:
          - cet_dominant_id: str
          - cet_dominant_score: float (0..100)
          - cet_specialization_score: float (0..1)
          - cet_areas: list[str]
          - cet_taxonomy_version: str
          - cet_profile_updated_at: ISO timestamp (auto-filled if missing)

        Args:
            enrichments: iterable of mappings with key_property and enrichment fields
            key_property: Organization key to MERGE on (default 'uei'); can be 'organization_id' or 'company_id' if that's your key
            metrics: optional LoadMetrics

        Returns:
            LoadMetrics with counts of updated nodes
        """
        metrics = metrics or LoadMetrics()
        nodes: list[dict[str, Any]] = []

        for raw in enrichments:
            key_val = _as_str(raw.get(key_property))
            if not key_val:
                logger.warning("Skipping Company enrichment missing key {}: {}", key_property, raw)
                metrics.errors += 1
                continue

            node: dict[str, Any] = {key_property: key_val}

            # Whitelisted fields
            if "cet_dominant_id" in raw and raw["cet_dominant_id"] is not None:
                node["cet_dominant_id"] = _as_str(raw["cet_dominant_id"])
            if "cet_dominant_score" in raw and raw["cet_dominant_score"] is not None:
                node["cet_dominant_score"] = float(raw["cet_dominant_score"])
            if "cet_specialization_score" in raw and raw["cet_specialization_score"] is not None:
                node["cet_specialization_score"] = float(raw["cet_specialization_score"])
            if "cet_taxonomy_version" in raw and raw["cet_taxonomy_version"] is not None:
                node["cet_taxonomy_version"] = _as_str(raw["cet_taxonomy_version"])
            if "cet_areas" in raw and isinstance(raw["cet_areas"], list | tuple):
                node["cet_areas"] = sorted({_as_str(v) for v in raw["cet_areas"] if _as_str(v)})

            # Updated timestamp (iso)
            node["cet_profile_updated_at"] = (
                _as_str(raw.get("cet_profile_updated_at")) or datetime.utcnow().isoformat()
            )

            nodes.append(node)

        if not nodes:
            logger.info("No Organization CET enrichments to upsert")
            return metrics

        logger.info(
            "Upserting {} Organization CET enrichment nodes (key={})", len(nodes), key_property
        )
        self.client.config.batch_size = self.config.batch_size
        metrics = self.client.batch_upsert_nodes(
            label="Organization", key_property=key_property, nodes=nodes, metrics=metrics
        )
        return metrics

    # -------------------------------------------------------------------------
    # Award enrichment properties
    # -------------------------------------------------------------------------

    def upsert_award_cet_enrichment(
        self,
        enrichments: Iterable[dict[str, Any]],
        *,
        key_property: str = "award_id",
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Upsert CET enrichment properties onto Award nodes.

        Each enrichment dict must include key_property (default 'award_id').
        Allowed enrichment properties:
          - cet_primary_id: str
          - cet_primary_score: float (0..100)
          - cet_supporting_ids: list[str]
          - cet_taxonomy_version: str
          - cet_classified_at: ISO timestamp
          - cet_model_version: str

        Args:
            enrichments: iterable of mappings with key_property and enrichment fields
            key_property: Award key to MERGE on (default 'award_id')
            metrics: optional LoadMetrics

        Returns:
            LoadMetrics with counts of updated nodes
        """
        metrics = metrics or LoadMetrics()
        nodes: list[dict[str, Any]] = []

        for raw in enrichments:
            key_val = _as_str(raw.get(key_property))
            if not key_val:
                logger.warning("Skipping Award enrichment missing key {}: {}", key_property, raw)
                metrics.errors += 1
                continue

            node: dict[str, Any] = {key_property: key_val}

            if "cet_primary_id" in raw and raw["cet_primary_id"] is not None:
                node["cet_primary_id"] = _as_str(raw["cet_primary_id"])
            if "cet_primary_score" in raw and raw["cet_primary_score"] is not None:
                node["cet_primary_score"] = float(raw["cet_primary_score"])
            if "cet_supporting_ids" in raw and isinstance(raw["cet_supporting_ids"], list | tuple):
                node["cet_supporting_ids"] = sorted(
                    {_as_str(v) for v in raw["cet_supporting_ids"] if _as_str(v)}
                )
            if "cet_taxonomy_version" in raw and raw["cet_taxonomy_version"] is not None:
                node["cet_taxonomy_version"] = _as_str(raw["cet_taxonomy_version"])
            if "cet_model_version" in raw and raw["cet_model_version"] is not None:
                node["cet_model_version"] = _as_str(raw["cet_model_version"])

            # classification timestamp (iso) if provided, else now
            node["cet_classified_at"] = (
                _as_str(raw.get("cet_classified_at")) or datetime.utcnow().isoformat()
            )

            nodes.append(node)

        if not nodes:
            logger.info("No Award CET enrichments to upsert")
            return metrics

        logger.info("Upserting {} Award CET enrichment nodes (key={})", len(nodes), key_property)
        self.client.config.batch_size = self.config.batch_size
        metrics = self.client.batch_upsert_nodes(
            label="Award", key_property=key_property, nodes=nodes, metrics=metrics
        )
        return metrics

    # -------------------------------------------------------------------------
    # Award -> CETArea relationships
    # -------------------------------------------------------------------------

    def create_award_cet_relationships(
        self,
        classifications: Iterable[dict[str, Any]],
        *,
        rel_type: str = "APPLICABLE_TO",
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create Award -> CETArea relationships with MERGE semantics.

        Relationship schema:
            (a:Award)-[:APPLICABLE_TO {
                score: FLOAT,
                primary: BOOLEAN,
                role: STRING,    # 'PRIMARY' or 'SUPPORTING'
                rationale: STRING,  # optional single rationale tag
                classified_at: STRING,  # ISO timestamp
                taxonomy_version: STRING
            }]->(c:CETArea)

        Input rows typically come from cet_award_classifications with fields:
            - award_id (str)
            - primary_cet (str) and primary_score (float)
            - supporting_cets (list of {cet_id: str, score: float, classification?: str})
            - classified_at (str)
            - taxonomy_version (str)
            - evidence (list of {rationale: str, excerpt: str, source: str}) [optional]
        """
        if metrics is None:
            metrics = LoadMetrics()

        relationships: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []

        for row in classifications:
            aid = _as_str(row.get("award_id"))
            if not aid:
                logger.warning("Skipping Award->CET mapping with missing award_id: {}", row)
                metrics.errors += 1
                continue

            classified_at = _as_str(row.get("classified_at")) or None
            taxonomy_version = _as_str(row.get("taxonomy_version")) or None

            # optional rationale from evidence (first rationale tag if present)
            rationale = None
            ev = row.get("evidence")
            if isinstance(ev, list) and ev:
                try:
                    rationale = _as_str((ev[0] or {}).get("rationale")) or None
                except Exception:
                    rationale = None

            # Primary
            primary_id = _as_str(row.get("primary_cet"))
            if primary_id:
                props = {
            # type: ignore[arg-type]
                    "score": float(row.get("primary_score"))
                    if row.get("primary_score") is not None
                    else None,
                    "primary": True,
                    "role": "PRIMARY",
                    "rationale": rationale,
                    "classified_at": classified_at,
                    "taxonomy_version": taxonomy_version,
                }
                # remove None values to avoid overwriting with nulls
                props = {k: v for k, v in props.items() if v is not None}
                relationships.append(
                    ("Award", "award_id", aid, "CETArea", "cet_id", primary_id, rel_type, props)
                )

            # Supporting
            supp = row.get("supporting_cets")
            if isinstance(supp, list):
                for s in supp:
                    try:
                        cid = _as_str((s or {}).get("cet_id"))
                        if not cid:
                            continue
                        score_val = s.get("score")
                        props = {
                            "score": float(score_val) if score_val is not None else None,
                            "primary": False,
                            "role": "SUPPORTING",
                            "rationale": rationale,
                            "classified_at": classified_at,
                            "taxonomy_version": taxonomy_version,
                        }
                        props = {k: v for k, v in props.items() if v is not None}
                        relationships.append(
                            ("Award", "award_id", aid, "CETArea", "cet_id", cid, rel_type, props)
                        )
                    except Exception:
                        continue

        if not relationships:
            logger.info("No Award -> CETArea relationships to create")
            return metrics

        logger.info(
            "Creating {} Award -> CETArea relationships (type={})",
            len(relationships),
            rel_type,
        )
        self.client.config.batch_size = self.config.batch_size
        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )
        return metrics

    # -------------------------------------------------------------------------
    # Company -> CETArea relationships
    # -------------------------------------------------------------------------

    def create_company_cet_relationships(
        self,
        profiles: Iterable[dict[str, Any]],
        *,
        rel_type: str = "SPECIALIZES_IN",
        key_property: str = "uei",
        metrics: LoadMetrics | None = None,
    ) -> LoadMetrics:
        """Create Organization -> CETArea relationships with MERGE semantics.

        Relationship schema:
            (o:Organization)-[:SPECIALIZES_IN {{
                score: FLOAT,
                specialization_score: FLOAT,
                primary: BOOLEAN,      # True for dominant CET
                role: STRING,          # 'DOMINANT'
                taxonomy_version: STRING
            }}]->(a:CETArea)

        Input rows typically come from cet_company_profiles or company CET enrichment with fields:
            - key_property (e.g., 'uei', 'organization_id', or 'company_id')
            - dominant_cet or cet_dominant_id
            - dominant_score or cet_dominant_score
            - specialization_score or cet_specialization_score
            - taxonomy_version or cet_taxonomy_version
        """
        if metrics is None:
            metrics = LoadMetrics()

        relationships: list[tuple[str, str, Any, str, str, Any, str, dict[str, Any] | None]] = []

        for row in profiles:
            key_val = _as_str(row.get(key_property))
            if not key_val:
                logger.warning(
                    "Skipping Company->CET mapping missing key {}: {}", key_property, row
                )
                metrics.errors += 1
                continue

            cet_id = _as_str(row.get("dominant_cet") or row.get("cet_dominant_id"))
            if not cet_id:
                logger.warning("Skipping Company->CET mapping missing dominant CET: {}", row)
                metrics.errors += 1
                continue

            score_val = row.get("dominant_score")
            if score_val is None:
                score_val = row.get("cet_dominant_score")

            spec_val = row.get("specialization_score")
            if spec_val is None:
                spec_val = row.get("cet_specialization_score")

            taxonomy_version = (
                _as_str(row.get("taxonomy_version") or row.get("cet_taxonomy_version")) or None
            )

            props = {
                "score": float(score_val) if score_val is not None else None,
                "specialization_score": float(spec_val) if spec_val is not None else None,
                "primary": True,
                "role": "DOMINANT",
                "taxonomy_version": taxonomy_version,
            }
            # remove None values to avoid overwriting with nulls
            props = {k: v for k, v in props.items() if v is not None}

            relationships.append(
                (
                    "Organization",
                    key_property,
                    key_val,
                    "CETArea",
                    "cet_id",
                    cet_id,
                    rel_type,
                    props,
                )
            )

        if not relationships:
            logger.info("No Organization -> CETArea relationships to create")
            return metrics

        logger.info(
            "Creating {} Organization -> CETArea relationships (type={}, key={})",
            len(relationships),
            rel_type,
            key_property,
        )
        self.client.config.batch_size = self.config.batch_size
        metrics = self.client.batch_create_relationships(
            relationships=relationships, metrics=metrics
        )
        return metrics


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s


def _normalize_keywords(words: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        s = _as_str(w).lower()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


__all__ = ["CETLoaderConfig", "CETLoader"]
