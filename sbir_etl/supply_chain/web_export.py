"""Export the observed SBIR-to-prime network for the static graph explorer."""

from __future__ import annotations

import json
from typing import Any, cast

import pandas as pd


def _series(frame: pd.DataFrame, column: str, default: object = None) -> pd.Series:
    if column in frame.columns:
        return frame[column]
    return pd.Series(default, index=frame.index, dtype="object")


def _text(value: object, fallback: str = "Unknown") -> str:
    if value is None or pd.isna(cast(Any, value)):
        return fallback
    rendered = str(value).strip()
    return rendered or fallback


def _float(value: object, default: float = 0.0) -> float:
    if value is None or pd.isna(cast(Any, value)):
        return default
    return float(cast(Any, value))


def _int(value: object, default: int = 0) -> int:
    if value is None or pd.isna(cast(Any, value)):
        return default
    return int(cast(Any, value))


def _bool(value: object, default: bool = False) -> bool:
    if value is None or pd.isna(cast(Any, value)):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


def _date(value: object) -> str | None:
    if value is None or pd.isna(cast(Any, value)):
        return None
    return pd.Timestamp(cast(Any, value)).date().isoformat()


def _canonical_names(frame: pd.DataFrame, id_column: str, name_column: str) -> dict[str, str]:
    """Choose the most frequently reported non-empty name for each identifier."""
    candidates = frame[[id_column, name_column]].copy()
    candidates[name_column] = candidates[name_column].map(lambda value: _text(value, ""))
    candidates = candidates.loc[candidates[name_column].ne("")]
    counts = (
        candidates.groupby([id_column, name_column], as_index=False, dropna=False)
        .size()
        .sort_values([id_column, "size", name_column], ascending=[True, False, True])
        .drop_duplicates(id_column)
    )
    return counts.set_index(id_column)[name_column].astype(str).to_dict()


def _supplier_node(row: pd.Series, exposure: dict[str, dict[str, Any]]) -> dict[str, Any]:
    organization_id = _text(row["sbir_organization_id"])
    screen = exposure.get(organization_id, {})
    return {
        "id": f"supplier:{organization_id}",
        "organization_id": organization_id,
        "label": _text(row["sbir_awardee_name"]),
        "kind": "supplier",
        "tier": "tier_2",
        "edge_count": _int(row["edge_count"]),
        "prime_family_count": _int(row["prime_family_count"]),
        "reported_subaward_amount": round(_float(row["reported_subaward_amount"]), 2),
        "reported_subaward_count": _int(row["reported_subaward_count"]),
        "max_fiscal_years": _int(row["max_fiscal_years"]),
        "screening_status": _text(screen.get("screening_status"), "not_screened"),
        "observed_customer_hhi": round(_float(screen.get("observed_customer_hhi")), 6),
        "top_observed_prime_share": round(_float(screen.get("top_observed_prime_share")), 6),
        "nsf_sbir_awardee": _bool(screen.get("nsf_sbir_awardee")),
        "nsf_sbir_award_count": _int(screen.get("nsf_sbir_award_count")),
        "nsf_sbir_topic_codes": _text(screen.get("nsf_sbir_topic_codes"), ""),
        "nsf_sbir_first_award_year": _int(screen.get("nsf_sbir_first_award_year"), default=0),
        "nsf_sbir_latest_award_year": _int(screen.get("nsf_sbir_latest_award_year"), default=0),
        "nsf_sbir_award_amount": round(_float(screen.get("nsf_sbir_award_amount")), 2),
        "nsf_review_priority": _text(screen.get("nsf_review_priority"), "not_nsf_sbir"),
        "critical_supply_chain_review_candidate": _bool(
            screen.get("critical_supply_chain_review_candidate")
        ),
        "critical_supply_chain_candidate_award_count": _int(
            screen.get("critical_supply_chain_candidate_award_count")
        ),
        "primary_cets": _text(screen.get("primary_cets"), ""),
        "dod_supply_chain_categories": _text(screen.get("dod_supply_chain_categories"), ""),
        "cet_classifier_version": _text(screen.get("cet_classifier_version"), ""),
        "defense_crosswalk_version": _text(screen.get("defense_crosswalk_version"), ""),
        "dependency_status": "not_established",
    }


def _prime_node(row: pd.Series) -> dict[str, Any]:
    organization_id = _text(row["prime_family_id"])
    return {
        "id": f"prime:{organization_id}",
        "organization_id": organization_id,
        "label": _text(row["prime_family_name"]),
        "kind": "prime",
        "tier": "tier_1_prime",
        "edge_count": _int(row["edge_count"]),
        "supplier_count": _int(row["supplier_count"]),
        "reported_subaward_amount": round(_float(row["reported_subaward_amount"]), 2),
        "reported_subaward_count": _int(row["reported_subaward_count"]),
        "max_fiscal_years": _int(row["max_fiscal_years"]),
        "dependency_status": "not_established",
    }


def build_web_graph_payload(
    verified_edges: pd.DataFrame,
    supplier_exposure: pd.DataFrame,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact, stable graph payload from identifier-verified relationships.

    Prime legal entities are rolled up to their reported parent family for display.
    Supplier and prime graph IDs are role-prefixed so an organization can appear in
    both roles without collapsing the bipartite graph.
    """
    required = {
        "sbir_organization_id",
        "prime_organization_id",
        "sbir_awardee_name",
        "prime_name",
        "reported_subaward_amount",
        "observed_fiscal_year_count",
    }
    missing = sorted(required - set(verified_edges.columns))
    if missing:
        raise ValueError(f"verified edge data missing required columns: {', '.join(missing)}")

    working = verified_edges.copy()
    working["prime_family_id"] = _series(working, "prime_family_id").fillna(
        working["prime_organization_id"]
    )
    working["prime_family_name"] = _series(working, "prime_family_name").fillna(
        working["prime_name"]
    )
    supplier_names = _canonical_names(working, "sbir_organization_id", "sbir_awardee_name")
    prime_family_names = _canonical_names(working, "prime_family_id", "prime_family_name")
    working["sbir_awardee_name"] = working["sbir_organization_id"].map(supplier_names)
    working["prime_family_name"] = working["prime_family_id"].map(prime_family_names)
    working["reported_subaward_count"] = pd.to_numeric(
        _series(working, "reported_subaward_count", 0), errors="coerce"
    ).fillna(0)
    working["prime_award_count"] = pd.to_numeric(
        _series(working, "prime_award_count", 0), errors="coerce"
    ).fillna(0)
    working["identifier_verified_facts"] = pd.to_numeric(
        _series(working, "identifier_verified_facts", 0), errors="coerce"
    ).fillna(0)
    working["nsf_sbir_awardee"] = (
        _series(working, "nsf_sbir_awardee", False).fillna(False).astype(bool)
    )
    working["critical_supply_chain_review_candidate"] = (
        _series(working, "critical_supply_chain_review_candidate", False).fillna(False).astype(bool)
    )
    working["first_observed_date"] = pd.to_datetime(
        _series(working, "first_observed_date"), errors="coerce"
    )
    working["last_observed_date"] = pd.to_datetime(
        _series(working, "last_observed_date"), errors="coerce"
    )

    family_edges = (
        working.groupby(
            [
                "sbir_organization_id",
                "sbir_awardee_name",
                "prime_family_id",
                "prime_family_name",
            ],
            as_index=False,
            dropna=False,
        )
        .agg(
            reported_subaward_amount=("reported_subaward_amount", "sum"),
            reported_subaward_count=("reported_subaward_count", "sum"),
            prime_award_count=("prime_award_count", "sum"),
            observed_fiscal_year_count=("observed_fiscal_year_count", "max"),
            first_observed_date=("first_observed_date", "min"),
            last_observed_date=("last_observed_date", "max"),
            identifier_verified_facts=("identifier_verified_facts", "sum"),
            prime_legal_entity_count=("prime_organization_id", "nunique"),
            nsf_sbir_awardee=("nsf_sbir_awardee", "max"),
            critical_supply_chain_review_candidate=(
                "critical_supply_chain_review_candidate",
                "max",
            ),
        )
        .sort_values(
            ["reported_subaward_amount", "sbir_awardee_name", "prime_family_name"],
            ascending=[False, True, True],
        )
        .reset_index(drop=True)
    )

    supplier_rollup = (
        family_edges.groupby(["sbir_organization_id", "sbir_awardee_name"], as_index=False)
        .agg(
            edge_count=("prime_family_id", "size"),
            prime_family_count=("prime_family_id", "nunique"),
            reported_subaward_amount=("reported_subaward_amount", "sum"),
            reported_subaward_count=("reported_subaward_count", "sum"),
            max_fiscal_years=("observed_fiscal_year_count", "max"),
        )
        .sort_values(["reported_subaward_amount", "sbir_awardee_name"], ascending=[False, True])
    )
    prime_rollup = (
        family_edges.groupby(["prime_family_id", "prime_family_name"], as_index=False)
        .agg(
            edge_count=("sbir_organization_id", "size"),
            supplier_count=("sbir_organization_id", "nunique"),
            reported_subaward_amount=("reported_subaward_amount", "sum"),
            reported_subaward_count=("reported_subaward_count", "sum"),
            max_fiscal_years=("observed_fiscal_year_count", "max"),
        )
        .sort_values(["supplier_count", "prime_family_name"], ascending=[False, True])
    )

    exposure_by_supplier = {
        _text(row["sbir_organization_id"]): row.to_dict()
        for _, row in supplier_exposure.iterrows()
        if "sbir_organization_id" in row
    }
    family_edges["nsf_sbir_awardee"] = [
        _bool(
            exposure_by_supplier.get(_text(row["sbir_organization_id"]), {}).get(
                "nsf_sbir_awardee", row["nsf_sbir_awardee"]
            )
        )
        for _, row in family_edges.iterrows()
    ]
    family_edges["critical_supply_chain_review_candidate"] = [
        _bool(
            exposure_by_supplier.get(_text(row["sbir_organization_id"]), {}).get(
                "critical_supply_chain_review_candidate",
                row["critical_supply_chain_review_candidate"],
            )
        )
        for _, row in family_edges.iterrows()
    ]
    nodes = [
        *[_supplier_node(row, exposure_by_supplier) for _, row in supplier_rollup.iterrows()],
        *[_prime_node(row) for _, row in prime_rollup.iterrows()],
    ]
    edges = [
        {
            "id": (
                f"supplier:{_text(row['sbir_organization_id'])}=>"
                f"prime:{_text(row['prime_family_id'])}"
            ),
            "source": f"supplier:{_text(row['sbir_organization_id'])}",
            "target": f"prime:{_text(row['prime_family_id'])}",
            "reported_subaward_amount": round(_float(row["reported_subaward_amount"]), 2),
            "reported_subaward_count": _int(row["reported_subaward_count"]),
            "prime_award_count": _int(row["prime_award_count"]),
            "fiscal_years": _int(row["observed_fiscal_year_count"]),
            "first_observed_date": _date(row["first_observed_date"]),
            "last_observed_date": _date(row["last_observed_date"]),
            "verified_fact_count": _int(row["identifier_verified_facts"]),
            "prime_legal_entity_count": _int(row["prime_legal_entity_count"]),
            "evidence_grade": "verified_identifier",
            "relationship_type": "observed_sbir_supplier_to_dod_prime_family",
            "dependency_status": "not_established",
            "nsf_supply_chain_review_candidate": bool(row["nsf_sbir_awardee"]),
            "critical_supply_chain_review_candidate": bool(
                row["critical_supply_chain_review_candidate"]
            ),
        }
        for _, row in family_edges.iterrows()
    ]

    source_metadata = metadata or {}
    return {
        "schema_version": "1.0",
        "title": "SBIR awardees in the observed defense supply network",
        "generated_at_utc": source_metadata.get("generated_at_utc"),
        "scope": {
            "supplier_tier": "tier_2",
            "customer_tier": "tier_1_prime",
            "evidence_grade": "verified_identifier",
            "input_legal_entity_edge_count": int(len(verified_edges)),
            "display_prime_family_edge_count": int(len(edges)),
            "supplier_count": int(len(supplier_rollup)),
            "prime_family_count": int(len(prime_rollup)),
            "nsf_sbir_supplier_count": int(
                sum(node["nsf_sbir_awardee"] for node in nodes if node["kind"] == "supplier")
            ),
            "nsf_sbir_prime_family_edge_count": int(family_edges["nsf_sbir_awardee"].sum()),
            "critical_supply_chain_review_candidate_supplier_count": int(
                sum(
                    node["critical_supply_chain_review_candidate"]
                    for node in nodes
                    if node["kind"] == "supplier"
                )
            ),
            "critical_supply_chain_review_candidate_edge_count": int(
                family_edges["critical_supply_chain_review_candidate"].sum()
            ),
        },
        "guardrails": source_metadata.get(
            "interpretation_guardrails",
            [
                "A reported subcontract is an observed relationship, not proof of dependency.",
                "Tier 3+ relationships are not observable in first-tier subaward data.",
                "Absence of an edge is not evidence that no supplier relationship exists.",
            ],
        ),
        "nodes": nodes,
        "edges": edges,
    }


def _json_array(values: pd.Series) -> list[str]:
    items: set[str] = set()
    for raw in values:
        if raw is None or raw is pd.NA:
            continue
        parsed: object = raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for value in candidates:
            if value is not None and str(value).strip():
                items.add(str(value).strip())
    return sorted(items)


def _joined_json(values: pd.Series) -> list[str]:
    return _json_array(values)


def _instrument_label(value: str) -> str:
    labels = {
        "prime_procurement": "Prime procurement",
        "prime_assistance": "Prime assistance",
        "prime_other_transaction": "Prime other transaction",
        "contract_subaward": "Reported contract subaward",
        "assistance_subaward": "Reported assistance subaward",
        "reported_subaward_unknown": "Reported subaward",
    }
    return labels.get(value, value.replace("_", " ").title())


def build_nsf_defense_lineage_payload(
    direct_awards: pd.DataFrame,
    awardees: pd.DataFrame,
    prime_transactions: pd.DataFrame,
    subaward_transactions: pd.DataFrame,
    award_screen: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    metadata: dict[str, Any] | None = None,
    downloads: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Build a traceable multi-partite NSF-to-defense funding graph payload."""

    required_direct = {"nsf_award_id", "nsf_organization_id", "nsf_award_title"}
    if missing := sorted(required_direct - set(direct_awards.columns)):
        raise ValueError(f"direct NSF awards missing graph columns: {missing}")
    required_awardees = {"nsf_organization_id", "nsf_awardee_status"}
    if missing := sorted(required_awardees - set(awardees.columns)):
        raise ValueError(f"NSF awardees missing graph columns: {missing}")

    screen = award_screen.copy()
    if not screen.empty and screen["nsf_award_id"].duplicated().any():
        raise ValueError("NSF award screen IDs are not unique")
    screen_by_award = (
        screen.set_index("nsf_award_id").to_dict(orient="index") if not screen.empty else {}
    )
    awardee_by_id = awardees.drop_duplicates("nsf_organization_id").set_index("nsf_organization_id")

    transaction_frames: list[pd.DataFrame] = []
    for frame, identifier in (
        (prime_transactions, "prime_transaction_id"),
        (subaward_transactions, "subaward_transaction_id"),
    ):
        if frame.empty:
            continue
        required = {
            identifier,
            "nsf_organization_id",
            "dod_award_generated_id",
            "funding_mode",
            "instrument_group",
            "signed_obligation_amount",
            "action_date",
            "fiscal_year",
            "recipient_match_method",
            "recipient_match_confidence",
            "source_system",
        }
        if missing := sorted(required - set(frame.columns)):
            raise ValueError(f"defense transactions missing graph columns: {missing}")
        working = frame.copy()
        working["_source_transaction_id"] = working[identifier].astype(str)
        for column in (
            "dod_award_id",
            "award_description",
            "awarding_agency_name",
            "source_transaction_path",
            "source_transaction_sha256",
            "source_url",
        ):
            if column not in working.columns:
                working[column] = pd.NA
        working["_dod_award_key"] = working["dod_award_generated_id"].fillna(
            working["dod_award_id"]
        )
        transaction_frames.append(working)
    transactions = (
        pd.concat(transaction_frames, ignore_index=True, sort=False)
        if transaction_frames
        else pd.DataFrame()
    )
    if not transactions.empty:
        transactions = transactions.dropna(subset=["_dod_award_key"])

    entity_funding: dict[str, dict[str, float]] = {}
    if not transactions.empty:
        verified = transactions["recipient_match_confidence"].isin(
            ["verified_identifier", "verified_legacy_identifier"]
        )
        totals = (
            transactions.loc[verified]
            .groupby(["nsf_organization_id", "instrument_group"], as_index=False)[
                "signed_obligation_amount"
            ]
            .sum()
        )
        for funding_organization_id, rows in totals.groupby("nsf_organization_id"):
            entity_funding[str(funding_organization_id)] = {
                str(row["instrument_group"]): float(row["signed_obligation_amount"])
                for _, row in rows.iterrows()
            }

    nodes: list[dict[str, Any]] = []
    for organization_id, row in awardee_by_id.iterrows():
        organization_key = str(organization_id)
        funding = entity_funding.get(organization_key, {})
        organization_awards = direct_awards["nsf_organization_id"].eq(organization_key)
        candidate_count = (
            int(
                screen.loc[
                    screen["nsf_organization_id"].eq(organization_key),
                    "critical_supply_chain_review_candidate",
                ].sum()
            )
            if not screen.empty
            else 0
        )
        name = _text(
            row.get("nsf_awardee_legal_business_name"),
            _text(row.get("nsf_awardee_name"), organization_key),
        )
        nodes.append(
            {
                "id": f"entity:{organization_key}",
                "record_id": organization_key,
                "organization_id": organization_key,
                "label": name,
                "kind": "legal_entity",
                "nsf_awardee_status": _text(row.get("nsf_awardee_status"), "indeterminate"),
                "nsf_award_count": int(organization_awards.sum()),
                "signed_dod_funding_total": round(sum(funding.values()), 2),
                "funding_by_instrument": funding,
                "critical_supply_chain_review_candidate": candidate_count > 0,
                "critical_supply_chain_candidate_award_count": candidate_count,
                "match_method": _text(row.get("organization_resolution_method"), "unknown"),
                "match_confidence": _text(row.get("organization_resolution_confidence"), "unknown"),
                "specific_award_usage_status": "not_established",
                "critical_supply_chain_status": "not_assessed",
                "details": {
                    "NSF status": _text(row.get("nsf_awardee_status"), "indeterminate"),
                    "Direct NSF awards": int(organization_awards.sum()),
                    "Verified signed DoD funding": round(sum(funding.values()), 2),
                    "Identity confidence": _text(
                        row.get("organization_resolution_confidence"), "unknown"
                    ),
                },
            }
        )

    nodes.extend(
        [
            {
                "id": "agency:NSF",
                "record_id": "NSF",
                "label": "National Science Foundation",
                "kind": "agency",
                "details": {"Source role": "NSF SBIR/STTR award agency"},
            },
            {
                "id": "agency:DOD:097",
                "record_id": "097",
                "label": "Department of Defense",
                "kind": "agency",
                "details": {
                    "CGAC code": "097",
                    "Source role": "DoD awarding or funding agency",
                },
            },
        ]
    )

    edges: list[dict[str, Any]] = []
    technology_ids: set[str] = set()
    for _, row in direct_awards.iterrows():
        award_id = _text(row["nsf_award_id"])
        organization_id = _text(row["nsf_organization_id"], "")
        if not organization_id:
            continue
        award_screen_row = screen_by_award.get(award_id, {})
        primary_cet = _text(award_screen_row.get("primary_cet"), "")
        amount = _float(
            row.get("nsf_estimated_total_amount"),
            _float(row.get("nsf_obligated_amount"), 0.0),
        )
        status = (
            _text(awardee_by_id.loc[organization_id].get("nsf_awardee_status"), "indeterminate")
            if organization_id in awardee_by_id.index
            else "indeterminate"
        )
        performance_status = _text(row.get("nsf_award_performance_status"), "indeterminate")
        nodes.append(
            {
                "id": f"nsf_award:{award_id}",
                "record_id": award_id,
                "label": _text(row.get("nsf_award_title"), f"NSF award {award_id}"),
                "kind": "nsf_award",
                "nsf_awardee_status": status,
                "program": _text(row.get("nsf_program"), "Unknown"),
                "phase": _text(row.get("nsf_phase"), "Unknown"),
                "start_date": _date(row.get("nsf_start_date")),
                "end_date": _date(row.get("nsf_end_date")),
                "award_amount": round(amount, 2),
                "primary_cet": primary_cet or None,
                "critical_supply_chain_review_candidate": _bool(
                    award_screen_row.get("critical_supply_chain_review_candidate")
                ),
                "critical_supply_chain_status": "not_assessed",
                "specific_award_usage_status": "not_established",
                "source_url": _text(row.get("source_url"), ""),
                "source_path": _text(row.get("source_path"), ""),
                "source_sha256": _text(row.get("source_record_sha256"), ""),
                "details": {
                    "Program / phase": " / ".join(
                        filter(
                            None,
                            [_text(row.get("nsf_program"), ""), _text(row.get("nsf_phase"), "")],
                        )
                    ),
                    "Performance status": performance_status,
                    "Award amount": round(amount, 2),
                    "Primary CET": primary_cet or "Not classified",
                    "Policy mapping": _text(
                        award_screen_row.get("defense_policy_mapping_status"), "deferred"
                    ),
                },
            }
        )
        edges.extend(
            [
                {
                    "id": f"agency:NSF=>nsf_award:{award_id}",
                    "source": "agency:NSF",
                    "target": f"nsf_award:{award_id}",
                    "relationship_type": "issued_nsf_award",
                    "label": "Issued NSF award",
                    "evidence_grade": "direct_source",
                    "fiscal_years": 1,
                    "signed_obligation_total": amount,
                    "nsf_awardee_status": status,
                    "source_record_ids": [award_id],
                    "source_paths": [_text(row.get("source_path"), "")],
                    "source_sha256s": [_text(row.get("source_record_sha256"), "")],
                },
                {
                    "id": f"entity:{organization_id}=>nsf_award:{award_id}",
                    "source": f"entity:{organization_id}",
                    "target": f"nsf_award:{award_id}",
                    "relationship_type": "received_nsf_award",
                    "label": "Received NSF award",
                    "evidence_grade": "direct_source",
                    "fiscal_years": 1,
                    "signed_obligation_total": amount,
                    "nsf_awardee_status": status,
                    "source_record_ids": [award_id],
                    "source_paths": [_text(row.get("source_path"), "")],
                    "source_sha256s": [_text(row.get("source_record_sha256"), "")],
                },
            ]
        )
        if primary_cet:
            technology_ids.add(primary_cet)
            edges.append(
                {
                    "id": f"nsf_award:{award_id}=>technology:{primary_cet}",
                    "source": f"nsf_award:{award_id}",
                    "target": f"technology:{primary_cet}",
                    "relationship_type": "classified_as_cet",
                    "label": "CET text classification",
                    "evidence_grade": "classifier_candidate",
                    "candidate": True,
                    "fiscal_years": 1,
                    "nsf_awardee_status": status,
                    "classifier_version": _text(award_screen_row.get("cet_classifier_version"), ""),
                    "source_record_ids": [award_id],
                }
            )

    for cet_id in sorted(technology_ids):
        nodes.append(
            {
                "id": f"technology:{cet_id}",
                "record_id": cet_id,
                "label": cet_id.replace("_", " ").title(),
                "kind": "technology",
                "critical_supply_chain_status": "not_assessed",
                "details": {
                    "Taxonomy": _text(
                        screen.loc[screen["primary_cet"].eq(cet_id), "cet_taxonomy_version"].iloc[0]
                        if not screen.loc[screen["primary_cet"].eq(cet_id)].empty
                        else None,
                        "Unknown",
                    ),
                    "Policy mapping": "Deferred — no authoritative DoD-14/NDIS-8 mapping",
                },
            }
        )

    if not transactions.empty:
        group_columns = [
            "nsf_organization_id",
            "_dod_award_key",
            "funding_mode",
            "instrument_group",
            "recipient_match_method",
            "recipient_match_confidence",
        ]
        funding_edges = transactions.groupby(group_columns, as_index=False, dropna=False).agg(
            dod_award_generated_id=("dod_award_generated_id", "first"),
            dod_award_id=("dod_award_id", "first"),
            award_description=("award_description", "first"),
            signed_obligation_total=("signed_obligation_amount", "sum"),
            transaction_count=("_source_transaction_id", "nunique"),
            fiscal_years=("fiscal_year", "nunique"),
            first_action_date=("action_date", "min"),
            last_action_date=("action_date", "max"),
            source_record_ids=("_source_transaction_id", _joined_json),
            source_systems=("source_system", _joined_json),
            source_paths=("source_transaction_path", _joined_json),
            source_sha256s=("source_transaction_sha256", _joined_json),
            source_urls=("source_url", _joined_json),
        )
        dod_nodes = funding_edges.groupby("_dod_award_key", as_index=False).agg(
            dod_award_id=("dod_award_id", "first"),
            award_description=("award_description", "first"),
            signed_obligation_total=("signed_obligation_total", "sum"),
            transaction_count=("transaction_count", "sum"),
            first_action_date=("first_action_date", "min"),
            last_action_date=("last_action_date", "max"),
            instrument_groups=("instrument_group", _joined_json),
        )
        for _, row in dod_nodes.iterrows():
            award_key = _text(row["_dod_award_key"])
            nodes.append(
                {
                    "id": f"dod_award:{award_key}",
                    "record_id": award_key,
                    "label": _text(row.get("dod_award_id"), award_key),
                    "kind": "dod_award",
                    "description": _text(row.get("award_description"), ""),
                    "signed_obligation_total": round(_float(row["signed_obligation_total"]), 2),
                    "transaction_count": _int(row["transaction_count"]),
                    "first_action_date": _date(row["first_action_date"]),
                    "last_action_date": _date(row["last_action_date"]),
                    "instrument_groups": row["instrument_groups"],
                    "details": {
                        "Signed obligations": round(_float(row["signed_obligation_total"]), 2),
                        "Source transactions": _int(row["transaction_count"]),
                        "First action": _date(row["first_action_date"]) or "Unknown",
                        "Last action": _date(row["last_action_date"]) or "Unknown",
                        "Instruments": ", ".join(row["instrument_groups"]),
                    },
                }
            )
            edges.append(
                {
                    "id": f"agency:DOD:097=>dod_award:{award_key}",
                    "source": "agency:DOD:097",
                    "target": f"dod_award:{award_key}",
                    "relationship_type": "dod_funding_authority",
                    "label": "DoD award or funding authority",
                    "evidence_grade": "source_agency_filter",
                    "fiscal_years": 1,
                    "source_record_ids": [award_key],
                }
            )
        for _, row in funding_edges.iterrows():
            organization_id = _text(row["nsf_organization_id"])
            award_key = _text(row["_dod_award_key"])
            instrument = _text(row["instrument_group"])
            confidence = _text(row["recipient_match_confidence"])
            status = (
                _text(awardee_by_id.loc[organization_id].get("nsf_awardee_status"), "indeterminate")
                if organization_id in awardee_by_id.index
                else "indeterminate"
            )
            edges.append(
                {
                    "id": (
                        f"dod_award:{award_key}=>entity:{organization_id}:"
                        f"{instrument}:{_text(row['recipient_match_method'])}"
                    ),
                    "source": f"dod_award:{award_key}",
                    "target": f"entity:{organization_id}",
                    "relationship_type": (
                        "received_dod_prime_funding"
                        if row["funding_mode"] == "prime"
                        else "received_reported_dod_subaward"
                    ),
                    "label": _instrument_label(instrument),
                    "funding_mode": _text(row["funding_mode"]),
                    "instrument_group": instrument,
                    "signed_obligation_total": round(_float(row["signed_obligation_total"]), 2),
                    "transaction_count": _int(row["transaction_count"]),
                    "fiscal_years": _int(row["fiscal_years"]),
                    "first_action_date": _date(row["first_action_date"]),
                    "last_action_date": _date(row["last_action_date"]),
                    "match_method": _text(row["recipient_match_method"]),
                    "match_confidence": confidence,
                    "evidence_grade": confidence,
                    "candidate": confidence == "candidate_name",
                    "dependency_status": "not_established",
                    "specific_award_usage_status": "not_established",
                    "critical_supply_chain_status": "not_assessed",
                    "nsf_awardee_status": status,
                    "source_record_ids": row["source_record_ids"],
                    "source_systems": row["source_systems"],
                    "source_paths": row["source_paths"],
                    "source_sha256s": row["source_sha256s"],
                    "source_urls": row["source_urls"],
                }
            )

    if not evidence.empty:
        for _, row in evidence.iterrows():
            nsf_award_id = _text(row.get("nsf_award_id"), "")
            dod_award_key = _text(
                row.get("_dod_award_key"), _text(row.get("dod_award_generated_id"), "")
            )
            if not nsf_award_id or not dod_award_key:
                continue
            edges.append(
                {
                    "id": _text(
                        row.get("evidence_assertion_id"),
                        f"evidence:{nsf_award_id}:{dod_award_key}",
                    ),
                    "source": f"nsf_award:{nsf_award_id}",
                    "target": f"dod_award:{dod_award_key}",
                    "relationship_type": "candidate_temporal_association",
                    "label": _text(row.get("temporal_association"), "Temporal association"),
                    "funding_mode": _text(row.get("funding_mode"), ""),
                    "instrument_group": _text(row.get("instrument_group"), ""),
                    "signed_obligation_total": round(_float(row.get("signed_obligation_total")), 2),
                    "fiscal_years": 1,
                    "evidence_grade": "candidate_association",
                    "candidate": True,
                    "specific_award_usage_status": "not_established",
                    "critical_supply_chain_status": "not_assessed",
                    "nsf_awardee_status": (
                        _text(
                            awardee_by_id.loc[_text(row.get("nsf_organization_id"), "")].get(
                                "nsf_awardee_status"
                            ),
                            "indeterminate",
                        )
                        if _text(row.get("nsf_organization_id"), "") in awardee_by_id.index
                        else "indeterminate"
                    ),
                    "source_record_ids": _json_array(
                        pd.Series([row.get("source_transaction_ids")])
                    ),
                    "source_paths": _json_array(pd.Series([row.get("source_paths")])),
                    "source_sha256s": _json_array(pd.Series([row.get("source_sha256s")])),
                    "temporal_association_is_causal_evidence": False,
                }
            )

    unique_nodes: dict[str, dict[str, Any]] = {}
    for node in nodes:
        unique_nodes.setdefault(str(node["id"]), node)
    unique_edges: dict[str, dict[str, Any]] = {}
    for edge in edges:
        edge_id = str(edge["id"])
        if edge_id in unique_edges:
            raise ValueError(f"lineage graph edge ID is not unique: {edge_id}")
        unique_edges[edge_id] = edge
    node_ids = set(unique_nodes)
    dangling = [
        edge["id"]
        for edge in unique_edges.values()
        if edge["source"] not in node_ids or edge["target"] not in node_ids
    ]
    if dangling:
        raise ValueError(f"lineage graph has edges with missing nodes: {dangling[:5]}")
    degree = dict.fromkeys(node_ids, 0)
    for edge in unique_edges.values():
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    for node_id, node in unique_nodes.items():
        node["edge_count"] = degree[node_id]

    source_metadata = metadata or {}
    node_counts = pd.Series(
        [node["kind"] for node in unique_nodes.values()], dtype="object"
    ).value_counts()
    return {
        "schema_version": "2.0",
        "title": "NSF SBIR awardees and observed DoD funding lineage",
        "analysis_date": source_metadata.get("analysis_date"),
        "generated_at_utc": source_metadata.get("generated_at"),
        "scope": {
            "node_count": len(unique_nodes),
            "edge_count": len(unique_edges),
            "node_counts": {str(key): int(value) for key, value in node_counts.items()},
            "verified_funding_edge_count": sum(
                not bool(edge.get("candidate"))
                and edge.get("relationship_type")
                in {"received_dod_prime_funding", "received_reported_dod_subaward"}
                for edge in unique_edges.values()
            ),
            "candidate_edge_count": sum(
                bool(edge.get("candidate")) for edge in unique_edges.values()
            ),
            "quality_gates_passed": source_metadata.get("quality_gates_passed"),
        },
        "filters": {
            "nsf_awardee_statuses": sorted(
                {
                    str(node["nsf_awardee_status"])
                    for node in unique_nodes.values()
                    if node.get("kind") == "legal_entity"
                }
            ),
            "instrument_groups": sorted(
                {
                    str(edge["instrument_group"])
                    for edge in unique_edges.values()
                    if edge.get("instrument_group")
                }
            ),
        },
        "downloads": downloads or {},
        "guardrails": [
            "Observed DoD funding is not proof that a specific NSF-funded capability was used.",
            "Reported subawards omit unreported and lower-tier supplier relationships.",
            "Name-only matches and temporal award associations are candidates, not verified links.",
            "Critical supply-chain status remains not assessed; DoD-14/NDIS-8 mapping is deferred.",
        ],
        "nodes": sorted(unique_nodes.values(), key=lambda node: (node["kind"], node["label"])),
        "edges": sorted(unique_edges.values(), key=lambda edge: str(edge["id"])),
    }
