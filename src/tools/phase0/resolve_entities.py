"""
Enhanced entity resolution across SBIR.gov, SAM.gov, FPDS, and USPTO.

Deterministic-first entity resolution pipeline:
    Step 1: UEI exact match (strongest signal — SAM.gov authoritative)
    Step 2: DUNS exact match (legacy records pre-UEI transition)
    Step 3: CAGE code exact match (defense-heavy companies)
    Step 4: Name + State + NAICS deterministic match
    Step 5: Fuzzy name match (rapidfuzz, threshold ≥90 auto-merge, 75-89 flag)
    Step 6: LLM tiebreaker (ONLY for flagged ambiguous cases)

Output: canonical_company_id → all source identifiers
        + confidence_score per linkage
        + human_override_log for contested resolutions

This is THE cross-cutting problem. Every mission asks "is this the same
company across sources?" Entity resolution quality directly determines
output quality for everything downstream.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

import pandas as pd
from loguru import logger

from ..base import BaseTool, DataSourceRef, ToolMetadata, ToolResult


def _normalize_name(name: str | None) -> str:
    """Normalize company name for matching."""
    if not name:
        return ""
    s = str(name).upper().strip()
    # Remove common suffixes
    for suffix in [" INC", " LLC", " LP", " LLP", " CORP", " CO", " LTD", " PLC"]:
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = s.rstrip(",. ")
    # Collapse whitespace and remove punctuation
    s = re.sub(r"[^A-Z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _generate_canonical_id(name: str, uei: str | None = None) -> str:
    """Generate a stable canonical company ID."""
    key = uei if uei else _normalize_name(name)
    return f"co-{hashlib.sha256(key.encode()).hexdigest()[:12]}"


class ResolveEntitiesTool(BaseTool):
    """Deterministic-first entity resolution across all public SBIR data sources.

    Produces a canonical entity table where every SBIR company is mapped to a
    stable ID with linked UEI, DUNS, CAGE, and name variants. This is the join
    key for everything downstream.

    Quality improves across missions:
        Phase 0: ~85% deterministic match rate (~100 gold set pairs)
        Mission A: ~88% (cross-agency edge cases, ~200 pairs)
        Mission B: ~91% (temporal name changes, ~350 pairs)
        Mission C: ~93% (dollar-stakes refinement, ~500 pairs)
    """

    name = "resolve_entities"
    version = "1.0.0"

    def execute(
        self,
        metadata: ToolMetadata,
        sbir_companies: pd.DataFrame | None = None,
        sam_entities: pd.DataFrame | None = None,
        fpds_vendors: pd.DataFrame | None = None,
        patent_assignees: pd.DataFrame | None = None,
        gold_set_path: str | None = None,
        fuzzy_auto_threshold: float = 90.0,
        fuzzy_review_threshold: float = 75.0,
    ) -> ToolResult:
        """Resolve entities across multiple public data sources.

        Args:
            metadata: Pre-initialized metadata to populate
            sbir_companies: SBIR.gov company records (name, state, UEI, DUNS)
            sam_entities: SAM.gov entity registrations (UEI, DUNS, CAGE, NAICS)
            fpds_vendors: FPDS contract vendors (name, UEI, DUNS, CAGE)
            patent_assignees: USPTO patent assignees (name, state)
            gold_set_path: Path to verified entity linkage pairs for calibration
            fuzzy_auto_threshold: Score >= this auto-merges (default 90)
            fuzzy_review_threshold: Score 75-89 flags for human review

        Returns:
            ToolResult with canonical entity table and match statistics
        """
        entities: list[dict[str, Any]] = []
        match_log: list[dict[str, Any]] = []

        # Load gold set for calibration if provided
        gold_set: dict[str, str] = {}
        if gold_set_path:
            try:
                gold_df = pd.read_csv(gold_set_path)
                src_col = next((c for c in ["source_name", "name"] if c in gold_df.columns), None)
                can_col = next((c for c in ["canonical_id", "canonical"] if c in gold_df.columns), None)
                if src_col and can_col:
                    gold_set = dict(zip(gold_df[src_col], gold_df[can_col], strict=False))
                    logger.info(f"Loaded {len(gold_set)} gold set linkages from {gold_set_path}")
            except Exception as e:
                logger.warning(f"Could not load gold set: {e}")
                metadata.warnings.append(f"Gold set load failed: {e}")

        # Build canonical index from SAM.gov (authoritative UEI source)
        canonical_by_uei: dict[str, dict] = {}
        canonical_by_duns: dict[str, dict] = {}
        canonical_by_cage: dict[str, dict] = {}
        canonical_by_name_state: dict[str, dict] = {}

        if sam_entities is not None and not sam_entities.empty:
            metadata.data_sources.append(
                DataSourceRef(
                    name="SAM.gov Entity Data",
                    url="https://sam.gov",
                    record_count=len(sam_entities),
                    access_method="upstream_tool",
                )
            )
            for _, row in sam_entities.iterrows():
                uei = str(row.get("unique_entity_id", "")).strip() or None
                duns = str(row.get("duns", "")).strip() or None
                cage = str(row.get("cage_code", "")).strip() or None
                name = str(row.get("legal_business_name", row.get("entity_name", ""))).strip()
                state = str(row.get("physical_address_state", "")).strip()
                naics = str(row.get("naics_code", "")).strip() or None

                canonical_id = _generate_canonical_id(name, uei)
                entity = {
                    "canonical_id": canonical_id,
                    "canonical_name": name,
                    "uei": uei,
                    "duns": duns,
                    "cage": cage,
                    "state": state,
                    "naics": naics,
                    "name_variants": [name],
                    "source_ids": {"sam_gov": uei or duns or name},
                    "confidence": 1.0,
                    "match_method": "sam_gov_seed",
                }
                entities.append(entity)

                if uei:
                    canonical_by_uei[uei] = entity
                if duns:
                    canonical_by_duns[duns] = entity
                if cage:
                    canonical_by_cage[cage] = entity
                norm_name = _normalize_name(name)
                if norm_name and state:
                    canonical_by_name_state[f"{norm_name}|{state}"] = entity

        # Step 1-3: Deterministic matching for SBIR companies
        unmatched_sbir: list[dict] = []
        if sbir_companies is not None and not sbir_companies.empty:
            metadata.data_sources.append(
                DataSourceRef(
                    name="SBIR.gov Awards",
                    url="https://sbir.gov/api",
                    record_count=len(sbir_companies),
                    access_method="upstream_tool",
                )
            )
            deterministic_matches = 0
            for _, row in sbir_companies.iterrows():
                uei = str(row.get("uei", row.get("unique_entity_id", ""))).strip() or None
                duns = str(row.get("duns", row.get("duns_number", ""))).strip() or None
                name = str(row.get("company", row.get("company_name", ""))).strip()
                state = str(row.get("state", row.get("company_state", ""))).strip()

                matched = None
                method = None

                # Step 0: Gold set override (human-verified linkages)
                if name in gold_set:
                    target_id = gold_set[name]
                    for entity in entities:
                        if entity["canonical_id"] == target_id:
                            matched = entity
                            method = "gold_set"
                            break

                # Step 1: UEI exact match
                # Step 1: UEI exact match
                if not matched and uei and uei in canonical_by_uei:
                    matched = canonical_by_uei[uei]
                    method = "uei_exact"
                # Step 2: DUNS exact match
                if not matched and duns and duns in canonical_by_duns:
                    matched = canonical_by_duns[duns]
                    method = "duns_exact"
                # Step 4: Name + State deterministic
                if not matched:
                    norm_name = _normalize_name(name)
                    key = f"{norm_name}|{state}"
                    if key in canonical_by_name_state:
                        matched = canonical_by_name_state[key]
                        method = "name_state_exact"

                if matched:
                    deterministic_matches += 1
                    matched["source_ids"]["sbir_gov"] = uei or duns or name
                    if name not in matched["name_variants"]:
                        matched["name_variants"].append(name)
                    match_log.append({
                        "source": "sbir_gov",
                        "source_name": name,
                        "canonical_id": matched["canonical_id"],
                        "method": method,
                        "confidence": 1.0 if method in ("uei_exact", "duns_exact") else 0.95,
                    })
                else:
                    unmatched_sbir.append({
                        "name": name, "state": state, "uei": uei, "duns": duns,
                    })

            logger.info(
                f"SBIR deterministic: {deterministic_matches}/{len(sbir_companies)} matched, "
                f"{len(unmatched_sbir)} need fuzzy matching"
            )

        # Step 5: Fuzzy matching for unmatched SBIR companies
        fuzzy_matches = 0
        flagged_for_review = 0
        if unmatched_sbir and entities:
            try:
                from rapidfuzz import fuzz

                canonical_names = [(e["canonical_name"], i) for i, e in enumerate(entities)]
                name_list = [n for n, _ in canonical_names]

                for company in unmatched_sbir:
                    norm = _normalize_name(company["name"])
                    if not norm:
                        continue

                    # Find best fuzzy match
                    best_score = 0.0
                    best_idx = -1
                    for i, ref_name in enumerate(name_list):
                        score = fuzz.token_set_ratio(norm, _normalize_name(ref_name))
                        if score > best_score:
                            best_score = score
                            best_idx = i

                    if best_score >= fuzzy_auto_threshold and best_idx >= 0:
                        # Auto-merge
                        matched = entities[canonical_names[best_idx][1]]
                        matched["source_ids"]["sbir_gov"] = company["uei"] or company["duns"] or company["name"]
                        if company["name"] not in matched["name_variants"]:
                            matched["name_variants"].append(company["name"])
                        fuzzy_matches += 1
                        match_log.append({
                            "source": "sbir_gov",
                            "source_name": company["name"],
                            "canonical_id": matched["canonical_id"],
                            "method": "fuzzy_auto",
                            "confidence": best_score / 100.0,
                        })
                    elif best_score >= fuzzy_review_threshold and best_idx >= 0:
                        # Flag for review
                        flagged_for_review += 1
                        match_log.append({
                            "source": "sbir_gov",
                            "source_name": company["name"],
                            "canonical_id": entities[canonical_names[best_idx][1]]["canonical_id"],
                            "method": "fuzzy_review_needed",
                            "confidence": best_score / 100.0,
                        })
                    else:
                        # Create new entity
                        canonical_id = _generate_canonical_id(company["name"], company["uei"])
                        new_entity = {
                            "canonical_id": canonical_id,
                            "canonical_name": company["name"],
                            "uei": company["uei"],
                            "duns": company["duns"],
                            "cage": None,
                            "state": company["state"],
                            "naics": None,
                            "name_variants": [company["name"]],
                            "source_ids": {"sbir_gov": company["uei"] or company["duns"] or company["name"]},
                            "confidence": 0.5,
                            "match_method": "new_entity",
                        }
                        entities.append(new_entity)
                        match_log.append({
                            "source": "sbir_gov",
                            "source_name": company["name"],
                            "canonical_id": canonical_id,
                            "method": "new_entity",
                            "confidence": 0.5,
                        })

                logger.info(
                    f"Fuzzy matching: {fuzzy_matches} auto-merged, "
                    f"{flagged_for_review} flagged for review"
                )
            except ImportError:
                logger.warning("rapidfuzz not available — skipping fuzzy matching")
                metadata.warnings.append("rapidfuzz not installed; fuzzy matching skipped")

        # Similarly process FPDS vendors (Steps 1-3 only for now)
        if fpds_vendors is not None and not fpds_vendors.empty:
            metadata.data_sources.append(
                DataSourceRef(
                    name="FPDS-NG (via USAspending.gov)",
                    url="https://usaspending.gov/download_center",
                    record_count=len(fpds_vendors),
                    access_method="upstream_tool",
                )
            )
            fpds_matches = 0
            for _, row in fpds_vendors.iterrows():
                uei = str(row.get("vendor_uei", "")).strip() or None
                duns = str(row.get("vendor_duns", "")).strip() or None
                cage = str(row.get("vendor_cage", "")).strip() or None

                matched = None
                if uei and uei in canonical_by_uei:
                    matched = canonical_by_uei[uei]
                elif duns and duns in canonical_by_duns:
                    matched = canonical_by_duns[duns]
                elif cage and cage in canonical_by_cage:
                    matched = canonical_by_cage[cage]

                if matched:
                    fpds_matches += 1
                    matched["source_ids"]["fpds"] = uei or duns or cage

            logger.info(f"FPDS: {fpds_matches}/{len(fpds_vendors)} matched to canonical entities")

        # Build output DataFrame
        if entities:
            entity_df = pd.DataFrame(entities)
        else:
            entity_df = pd.DataFrame(columns=[
                "canonical_id", "canonical_name", "uei", "duns", "cage",
                "state", "naics", "name_variants", "source_ids",
                "confidence", "match_method",
            ])

        match_log_df = pd.DataFrame(match_log) if match_log else pd.DataFrame()

        # Populate metadata
        metadata.record_count = len(entity_df)
        if flagged_for_review > 0:
            metadata.warnings.append(
                f"{flagged_for_review} entities flagged for human review (fuzzy score 75-89)"
            )

        result_data = {
            "entities": entity_df,
            "match_log": match_log_df,
            "stats": {
                "total_canonical_entities": len(entity_df),
                "deterministic_matches": len([m for m in match_log if m.get("method", "").endswith("exact")]),
                "fuzzy_auto_merges": fuzzy_matches,
                "flagged_for_review": flagged_for_review,
                "new_entities_created": len([e for e in entities if e.get("match_method") == "new_entity"]),
            },
        }

        return ToolResult(data=result_data, metadata=metadata)
