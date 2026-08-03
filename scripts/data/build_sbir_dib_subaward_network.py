#!/usr/bin/env python3
"""Build an observable SBIR-awardee-to-DoD-prime network from USAspending subawards."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from sbir_etl.supply_chain.subaward_network import (
    EvidenceGrade,
    aggregate_supplier_prime_edges,
    build_nsf_sbir_award_candidates,
    build_sbir_awardee_registry,
    build_supplier_customer_exposure,
    build_subaward_facts,
    network_metadata,
)
from sbir_etl.supply_chain.nsf_screen import (
    aggregate_nsf_supplier_screen,
    screen_nsf_sbir_award_candidates,
)

_NETWORK_COLUMNS = {
    "prime_award_unique_key",
    "unique_award_key",
    "prime_award_piid",
    "prime_piid",
    "award_id",
    "prime_awardee_uei",
    "prime_recipient_uei",
    "prime_awardee_duns",
    "prime_recipient_duns",
    "prime_awardee_name",
    "prime_recipient_name",
    "prime_awardee_parent_uei",
    "prime_parent_uei",
    "prime_awardee_parent_name",
    "prime_parent_name",
    "prime_award_naics_code",
    "naics_code",
    "prime_award_base_transaction_description",
    "prime_award_description",
    "subaward_number",
    "subaward_id",
    "subaward_sam_report_id",
    "sam_report_id",
    "subaward_amount",
    "amount",
    "subaward_action_date",
    "action_date",
    "subawardee_uei",
    "sub_recipient_uei",
    "subawardee_duns",
    "sub_recipient_duns",
    "subawardee_name",
    "sub_recipient_name",
    "subaward_description",
    "description",
    "usaspending_permalink",
    "source_url",
    "subaward_sam_report_last_modified_date",
    "source_last_modified",
}

_AWARD_COLUMNS = {
    "company_name",
    "organization_name",
    "firm_name",
    "Company",
    "company_uei",
    "uei",
    "recipient_uei",
    "UEI",
    "company_duns",
    "duns",
    "recipient_duns",
    "Duns",
    "agency",
    "funding_agency",
    "Agency",
    "program",
    "Program",
    "topic_code",
    "Topic Code",
    "award_year",
    "Award Year",
    "award_amount",
    "Award Amount",
    "award_title",
    "Award Title",
    "phase",
    "Phase",
    "agency_tracking_number",
    "Agency Tracking Number",
    "contract",
    "Contract",
    "solicitation_number",
    "Solicitation Number",
    "proposal_award_date",
    "Proposal Award Date",
    "contract_end_date",
    "Contract End Date",
    "abstract",
    "Abstract",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_frame(
    path: Path, *, subaward_projection: bool = False, award_projection: bool = False
) -> pd.DataFrame:
    if path.suffix.lower() in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if path.suffix.lower() == ".csv":
        return pd.read_csv(
            path,
            low_memory=False,
            usecols=(
                (lambda column: column in _NETWORK_COLUMNS)
                if subaward_projection
                else (lambda column: column in _AWARD_COLUMNS)
                if award_projection
                else None
            ),
            dtype=str if award_projection else None,
        )
    if path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as temporary_directory:
            with zipfile.ZipFile(path) as archive:
                csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
                if not csv_names:
                    raise ValueError(f"archive contains no CSV files: {path}")
                archive.extractall(temporary_directory)
            frames = [
                pd.read_csv(
                    Path(temporary_directory) / name,
                    low_memory=False,
                    usecols=(lambda column: column in _NETWORK_COLUMNS)
                    if subaward_projection
                    else (lambda column: column in _AWARD_COLUMNS)
                    if award_projection
                    else None,
                    dtype=str if award_projection else None,
                )
                for name in csv_names
            ]
        return pd.concat(frames, ignore_index=True)
    raise ValueError(f"unsupported input format: {path}")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--awards",
        type=Path,
        default=Path("data/raw/sbir/award_data.csv"),
    )
    parser.add_argument("--subawards", type=Path, required=True, nargs="+")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/sbir_dib_subaward_network"),
    )
    parser.add_argument(
        "--exclude-name-candidates",
        action="store_true",
        help="Keep only exact UEI or DUNS matches.",
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    awards = _read_frame(args.awards, award_projection=True)
    subawards = pd.concat(
        [_read_frame(path, subaward_projection=True) for path in args.subawards],
        ignore_index=True,
    )
    registry = build_sbir_awardee_registry(awards)
    facts = build_subaward_facts(
        registry,
        subawards,
        include_name_candidates=not args.exclude_name_candidates,
    )
    verified_facts = facts.loc[
        facts["evidence_grade"] == EvidenceGrade.VERIFIED_IDENTIFIER.value
    ].copy()
    candidate_facts = facts.loc[
        facts["evidence_grade"] == EvidenceGrade.CANDIDATE_NAME.value
    ].copy()
    verified_edges = aggregate_supplier_prime_edges(verified_facts)
    candidate_edges = aggregate_supplier_prime_edges(candidate_facts)
    exposure = build_supplier_customer_exposure(verified_edges)
    nsf_award_candidates = screen_nsf_sbir_award_candidates(
        build_nsf_sbir_award_candidates(awards, registry, exposure)
    )
    nsf_supplier_screen = aggregate_nsf_supplier_screen(nsf_award_candidates)
    verified_edges = verified_edges.merge(
        nsf_supplier_screen,
        on="sbir_organization_id",
        how="left",
        validate="many_to_one",
    )
    exposure = exposure.merge(
        nsf_supplier_screen,
        on="sbir_organization_id",
        how="left",
        validate="one_to_one",
    )
    for frame in (verified_edges, exposure):
        frame["critical_supply_chain_review_candidate"] = frame[
            "critical_supply_chain_review_candidate"
        ].fillna(False)
        for column in (
            "nsf_specific_award_candidate_count",
            "cet_classified_nsf_award_count",
            "critical_supply_chain_candidate_award_count",
        ):
            frame[column] = frame[column].fillna(0).astype(int)
        for column in ("primary_cets", "dod_supply_chain_categories"):
            frame[column] = frame[column].fillna("")
    nsf_edges = verified_edges.loc[verified_edges["nsf_sbir_awardee"]].copy()
    nsf_candidates = exposure.loc[exposure["nsf_sbir_awardee"]].copy()
    metadata = network_metadata(
        verified_facts,
        verified_edges,
        candidate_facts=candidate_facts,
        candidate_edges=candidate_edges,
    )
    metadata.update(
        {
            "generated_at_utc": datetime.now(UTC).isoformat(),
            "awards_source": str(args.awards),
            "subawards_sources": [str(path) for path in args.subawards],
            "subawards_source_sha256": {str(path): _sha256(path) for path in args.subawards},
            "sbir_awardee_registry_rows": int(len(registry)),
            "identifier_verified_awardee_coverage": (
                metadata["identifier_verified_sbir_awardees"] / len(registry)
                if len(registry)
                else 0.0
            ),
            "source_subaward_rows": int(len(subawards)),
            "nsf_sbir_registry_awardees": int(registry["nsf_sbir_awardee"].sum()),
            "identifier_verified_nsf_sbir_awardees": int(len(nsf_candidates)),
            "identifier_verified_nsf_sbir_supplier_prime_edges": int(len(nsf_edges)),
            "persistent_nsf_sbir_supplier_prime_edges": int(
                nsf_edges["observed_fiscal_year_count"].ge(3).sum()
            ),
            "nsf_sbir_award_candidates": int(len(nsf_award_candidates)),
            "identifier_associated_nsf_sbir_award_candidates": int(
                nsf_award_candidates["awardee_association_method"]
                .isin(["exact_uei", "exact_duns"])
                .sum()
            ),
            "cet_classified_nsf_sbir_award_candidates": int(
                nsf_award_candidates["primary_cet"].notna().sum()
            ),
            "critical_supply_chain_review_candidate_awards": int(
                nsf_award_candidates["critical_supply_chain_review_candidate"].sum()
            ),
            "critical_supply_chain_review_candidate_awardees": int(
                nsf_award_candidates.loc[
                    nsf_award_candidates["critical_supply_chain_review_candidate"],
                    "sbir_organization_id",
                ].nunique()
            ),
            "cet_classifier_version": str(
                nsf_award_candidates["cet_classifier_version"].dropna().iloc[0]
            )
            if nsf_award_candidates["cet_classifier_version"].notna().any()
            else None,
            "defense_crosswalk_version": str(
                nsf_award_candidates["defense_crosswalk_version"].iloc[0]
            )
            if not nsf_award_candidates.empty
            else None,
            "matched_action_date_min": str(facts["subaward_action_date"].min()),
            "matched_action_date_max": str(facts["subaward_action_date"].max()),
        }
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    registry.to_parquet(args.output_dir / "sbir_awardee_registry.parquet", index=False)
    facts.to_parquet(args.output_dir / "sbir_dib_subaward_facts.parquet", index=False)
    verified_edges.to_parquet(
        args.output_dir / "sbir_dib_supplier_prime_edges.parquet", index=False
    )
    candidate_edges.to_parquet(
        args.output_dir / "sbir_dib_candidate_supplier_prime_edges.parquet", index=False
    )
    exposure.to_parquet(args.output_dir / "sbir_supplier_customer_exposure.parquet", index=False)
    nsf_edges.to_parquet(args.output_dir / "nsf_sbir_supplier_prime_edges.parquet", index=False)
    nsf_candidates.to_parquet(
        args.output_dir / "nsf_sbir_supply_chain_candidates.parquet", index=False
    )
    nsf_award_candidates.to_parquet(
        args.output_dir / "nsf_sbir_award_candidates.parquet", index=False
    )
    (args.output_dir / "sbir_dib_subaward_network.metadata.json").write_text(
        json.dumps(metadata, indent=2, default=str)
    )
    print(
        f"Matched {len(verified_facts):,} identifier-verified subawards into "
        f"{len(verified_edges):,} SBIR-supplier-to-prime edges; retained "
        f"{len(candidate_facts):,} name-only candidate facts separately"
    )
    print(json.dumps(metadata, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
