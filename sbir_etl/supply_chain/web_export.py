"""Export the observed SBIR-to-prime network for the static graph explorer."""

from __future__ import annotations

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
