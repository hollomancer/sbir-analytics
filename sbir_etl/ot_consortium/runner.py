"""Orchestration helpers for the two run modes.

Kept free of Dagster so both modes are unit-testable in isolation. The Dagster
asset is a thin wrapper over :func:`classify_baseline` and :func:`classify_claims`.

* Baseline mode (population proxy): classify OT-consortium-linked records among
  the existing detected transitions. The "claiming firm" is the SBIR award
  recipient on the transition.
* Audit mode: classify firm-reported covered-sales claims, locating each against
  federal records (T4 when absent). Non-attributable aggregate claims are
  separated out and never tiered.
"""

from __future__ import annotations

from typing import Any, cast

import pandas as pd

from .classifier import assign_tier
from .models import CoveredSalesClaim, FirmUEISource, OTAward, TierAssignment
from .registry import CMFRegistry
from .usaspending_ot import build_ot_award, is_ot_record


def _populate_base_recipient(ot_award: OTAward, by_piid: dict[str, dict[str, Any]]) -> None:
    """Fill the base OT recipient by looking up the parent row, enabling the
    order-level recipient T1 route. Only fills when not already present on the row."""
    if ot_award.base_recipient_uei or ot_award.base_recipient_name:
        return
    if not ot_award.parent_piid:
        return
    base_row = by_piid.get(str(ot_award.parent_piid))
    if not base_row:
        return
    base = build_ot_award(base_row)
    ot_award.base_recipient_uei = base.recipient_uei
    ot_award.base_recipient_name = base.recipient_name


def assignments_to_records(assignments: list[TierAssignment]) -> list[dict[str, Any]]:
    """Flatten assignments into row dicts for parquet / the Neo4j loader.

    Evidence is serialized to a compact list so the per-record audit trail
    survives into the persisted table.
    """
    return [
        {
            "award_id": a.award_id,
            "tier": str(a.tier),
            "piid": a.piid,
            "parent_piid": a.parent_piid,
            "cmf_name": a.cmf_name,
            "firm_uei": a.firm_uei,
            "firm_uei_source": str(a.firm_uei_source),
            "resolution_method": a.resolution_method,
            "obligation_amount": a.obligation_amount,
            "agency": a.agency,
            "fiscal_year": a.fiscal_year,
            "is_verifiable": a.is_verifiable,
            "confidence_note": a.confidence_note,
            "evidence": [
                {"field": e.field, "value": e.value, "rule": e.rule, "note": e.note}
                for e in a.evidence
            ],
        }
        for a in assignments
    ]


def _blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _award_firm_uei(row: dict[str, Any]) -> str | None:
    for col in ("UEI", "uei", "recipient_uei", "company_uei"):
        if col in row and not _blank(row[col]):
            return str(row[col]).strip()
    return None


def _award_firm_name(row: dict[str, Any]) -> str | None:
    for col in ("Company", "company", "company_name", "recipient_name"):
        if col in row and not _blank(row[col]):
            return str(row[col]).strip()
    return None


def _is_consortium_linked(award_row: dict[str, Any], registry: CMFRegistry) -> bool:
    """Filter to records with a consortium nexus (the baseline population)."""
    if is_ot_record(award_row):
        return True
    name = award_row.get("recipient_name") or award_row.get("vendor_name")
    uei = award_row.get("recipient_uei") or award_row.get("vendor_uei")
    return registry.match(name=name, uei=uei) is not None


def classify_baseline(
    detections: pd.DataFrame,
    contracts: pd.DataFrame,
    awards: pd.DataFrame,
    registry: CMFRegistry,
) -> list[TierAssignment]:
    """Classify OT-consortium-linked transitions (baseline population proxy)."""
    if detections is None or detections.empty:
        return []

    contracts_by_id: dict[str, dict[str, Any]] = {}
    if contracts is not None and not contracts.empty:
        for c in cast("list[dict[str, Any]]", contracts.to_dict("records")):
            cid = str(c.get("contract_id") or c.get("piid") or "")
            if cid:
                contracts_by_id[cid] = c

    firm_by_award: dict[str, dict[str, Any]] = {}
    if awards is not None and not awards.empty:
        adf = awards.copy()
        if "award_id" not in adf.columns:
            adf = adf.reset_index().rename(columns={"index": "award_id"})
            adf["award_id"] = adf["award_id"].apply(lambda x: f"award_{x}")
        for a in cast("list[dict[str, Any]]", adf.to_dict("records")):
            firm_by_award[str(a.get("award_id"))] = a

    assignments: list[TierAssignment] = []
    seen: set[str] = set()
    for det in detections.to_dict("records"):
        contract_id = str(det.get("contract_id") or "")
        sbir_award_id = str(det.get("award_id") or "")
        contract_row = contracts_by_id.get(contract_id)
        if contract_row is None or not _is_consortium_linked(contract_row, registry):
            continue
        if contract_id in seen:  # one tier per OT award
            continue
        seen.add(contract_id)

        ot_award = build_ot_award(contract_row)
        if not ot_award.award_id:
            ot_award.award_id = contract_id
        _populate_base_recipient(ot_award, contracts_by_id)

        firm_row = firm_by_award.get(sbir_award_id, {})
        firm_uei = _award_firm_uei(firm_row)
        firm_source = FirmUEISource.PROVIDED if firm_uei else FirmUEISource.UNRESOLVED

        assignments.append(
            assign_tier(
                ot_award,
                firm_uei=firm_uei,
                firm_uei_source=firm_source,
                registry=registry,
            )
        )
    return assignments


def classify_claims(
    claims: list[CoveredSalesClaim],
    registry: CMFRegistry,
    *,
    federal_records: pd.DataFrame | None = None,
    resolver: Any | None = None,
) -> tuple[list[TierAssignment], list[CoveredSalesClaim]]:
    """Classify covered-sales claims (audit mode).

    Args:
        claims: Loaded claims to classify.
        registry: CMF registry for rollup detection.
        federal_records: Optional federal OT records to locate claimed awards,
            keyed on PIID. When a claim's PIID is absent here, the award is tiered
            T4 (no federal record).
        resolver: Optional ``VendorResolver`` used to recover a firm UEI from the
            firm name (flagged as name-resolved) when the claim lacks a UEI.

    Returns:
        ``(assignments, non_attributable_claims)``.
    """
    fed_by_piid: dict[str, dict[str, Any]] = {}
    if federal_records is not None and not federal_records.empty:
        for r in cast("list[dict[str, Any]]", federal_records.to_dict("records")):
            piid = str(r.get("piid") or r.get("PIID") or r.get("contract_id") or "")
            if piid:
                fed_by_piid[piid] = r

    assignments: list[TierAssignment] = []
    non_attributable: list[CoveredSalesClaim] = []
    for claim in claims:
        if not claim.is_attributable:
            non_attributable.append(claim)
            continue

        firm_uei, firm_source = _resolve_claim_firm(claim, resolver)

        fed_row = fed_by_piid.get(str(claim.claimed_award_piid or ""))
        if fed_row is not None:
            ot_award = build_ot_award(fed_row)
            if not ot_award.award_id:
                ot_award.award_id = str(claim.claimed_award_piid or claim.claim_id)
            _populate_base_recipient(ot_award, fed_by_piid)
        else:
            # No federal record located → T4. Carry claim context for the report.
            ot_award = build_ot_award(
                {
                    "award_id": claim.claimed_award_piid or claim.claim_id,
                    "piid": claim.claimed_award_piid,
                    "parent_piid": claim.claimed_parent_piid,
                    "recipient_name": claim.cmf_name,
                    "obligation_amount": claim.claimed_obligation_usd,
                    "agency": claim.agency,
                    "fiscal_year": claim.fiscal_year,
                },
                found_in_federal_data=False,
            )

        assignments.append(
            assign_tier(
                ot_award,
                firm_uei=firm_uei,
                firm_uei_source=firm_source,
                registry=registry,
            )
        )
    return assignments, non_attributable


def _resolve_claim_firm(
    claim: CoveredSalesClaim, resolver: Any | None
) -> tuple[str | None, FirmUEISource]:
    """Determine the firm UEI for a claim and its provenance."""
    if claim.firm_uei:
        return claim.firm_uei.strip(), FirmUEISource.PROVIDED
    if resolver is not None and claim.firm_name:
        match = resolver.resolve(name=claim.firm_name)
        if match.record and match.method == "name_exact" and match.record.uei:
            return str(match.record.uei).strip(), FirmUEISource.NAME_RESOLVED
        if match.record and match.record.uei and match.method.startswith("name"):
            return str(match.record.uei).strip(), FirmUEISource.NAME_RESOLVED
    return None, FirmUEISource.UNRESOLVED
