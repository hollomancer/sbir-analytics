import json
import hashlib
from datetime import date

import pandas as pd

from scripts.data.build_nsf_defense_funding import build_release, prepare_defense_funding
from scripts.data.export_sbir_dib_network_web import export_lineage
from sbir_etl.supply_chain.nsf_screen import screen_direct_nsf_awards
from sbir_etl.supply_chain.release_validation import validate_nsf_defense_lineage_release


def _run_release(**kwargs):
    """Prepare, screen (exploratory), and build — the production call path."""

    workset = prepare_defense_funding(**kwargs)
    award_screen = screen_direct_nsf_awards(
        workset.direct,
        funded_organization_ids=set(workset.funded_organization_ids),
    )
    return build_release(workset, award_screen=award_screen)


def _sha256(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _phase_one_products(lineage_dir) -> None:
    analysis = pd.Timestamp("2026-08-03", tz="UTC")
    pd.DataFrame(
        [
            {
                "nsf_award_id": "0620588",
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "nsf_program": "SBIR",
                "nsf_phase": "II",
                "nsf_award_title": "Advanced sensor",
                "nsf_award_abstract": "Additive manufacturing for a microelectronics sensor.",
                "nsf_start_date": pd.Timestamp("2024-06-01", tz="UTC"),
                "nsf_end_date": pd.Timestamp("2027-05-31", tz="UTC"),
                "nsf_award_performance_status": "active",
                "nsf_estimated_total_amount": 900000.0,
                "source_url": "https://api.nsf.gov/services/v1/awards/0620588.json",
                "source_path": "snapshot/0620588.json",
                "source_record_sha256": "nsf-record-hash",
                "analysis_date": analysis,
            }
        ]
    ).to_parquet(lineage_dir / "nsf_sbir_awards_direct.parquet", index=False)
    pd.DataFrame(
        [
            {
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "nsf_awardee_name": "Example Materials Inc",
                "nsf_awardee_legal_business_name": "Example Materials Inc",
                "nsf_awardee_uei": "ABCDEFGHIJKL",
                "organization_resolution_method": "direct_nsf_uei",
                "organization_resolution_confidence": "verified_identifier",
                "nsf_awardee_status": "current",
                "analysis_date": analysis,
            }
        ]
    ).to_parquet(lineage_dir / "nsf_sbir_awardee_status.parquet", index=False)
    pd.DataFrame(
        [
            {
                "nsf_award_id": "0620588",
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "nsf_awardee_name": "Example Materials Inc",
                "nsf_awardee_uei": "ABCDEFGHIJKL",
                "sbir_gov_company_name": "EXAMPLE MATERIALS, INC.",
                "sbir_gov_uei": "ABCDEFGHIJKL",
                "sbir_gov_duns": "123456789",
                "reconciliation_disposition": "matched",
                "match_method": "exact_contract_award_id",
                "match_confidence": "high",
                "analysis_date": analysis,
            }
        ]
    ).to_parquet(lineage_dir / "nsf_sbir_award_reconciliation.parquet", index=False)
    (lineage_dir / "nsf_defense_lineage_quality.json").write_text(
        json.dumps(
            {
                "analysis_date": "2026-08-03",
                "quality_gates": {"direct_award_ids_unique": True},
                "quality_gates_passed": True,
                "limitations": [],
            }
        ),
        encoding="utf-8",
    )
    direct_path = lineage_dir / "nsf_sbir_awards_direct.parquet"
    reconciliation_path = lineage_dir / "nsf_sbir_award_reconciliation.parquet"
    awardees_path = lineage_dir / "nsf_sbir_awardee_status.parquet"
    (lineage_dir / "nsf_defense_lineage_manifest.json").write_text(
        json.dumps(
            {
                "analysis_date": "2026-08-03",
                "inputs": {"direct_nsf_sources": ["snapshot"]},
                "products": {
                    "direct_awards": {
                        "path": str(direct_path),
                        "sha256": _sha256(direct_path),
                        "row_count": 1,
                    },
                    "reconciliation": {
                        "path": str(reconciliation_path),
                        "sha256": _sha256(reconciliation_path),
                        "row_count": 1,
                    },
                    "awardees": {
                        "path": str(awardees_path),
                        "sha256": _sha256(awardees_path),
                        "row_count": 1,
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def test_build_release_writes_prime_subaward_summary_evidence_and_partitions(tmp_path) -> None:
    lineage_dir = tmp_path / "lineage"
    lineage_dir.mkdir()
    _phase_one_products(lineage_dir)
    prime = tmp_path / "prime.parquet"
    pd.DataFrame(
        [
            {
                "prime_transaction_id": "CONT_TX_1",
                "dod_award_generated_id": "CONT_AWD_P1_9700",
                "dod_award_id": "P1",
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "recipient_name_source": "Example Materials Inc",
                "recipient_uei_source": "ABCDEFGHIJKL",
                "recipient_match_method": "exact_uei",
                "recipient_match_confidence": "verified_identifier",
                "funding_mode": "prime",
                "instrument_group": "prime_procurement",
                "signed_obligation_amount": 100.0,
                "action_date": "2024-09-30",
                "transaction_description": "microelectronics sensor delivery",
                "award_description": "advanced sensor system",
                "product_or_service_code": "5998",
                "naics_code": "334413",
                "source_system": "USAspending API",
                "source_kind": "FPDS prime transaction",
                "source_transaction_path": "snapshot/transactions/page-00001.json",
                "source_transaction_sha256": "prime-page-hash",
            },
            {
                "prime_transaction_id": "CONT_TX_2",
                "dod_award_generated_id": "CONT_AWD_P1_9700",
                "dod_award_id": "P1",
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "recipient_name_source": "Example Materials Inc",
                "recipient_uei_source": "ABCDEFGHIJKL",
                "recipient_match_method": "exact_uei",
                "recipient_match_confidence": "verified_identifier",
                "funding_mode": "prime",
                "instrument_group": "prime_procurement",
                "signed_obligation_amount": -10.0,
                "action_date": "2024-10-01",
                "source_system": "USAspending API",
                "source_kind": "FPDS prime transaction",
            },
        ]
    ).to_parquet(prime, index=False)
    subaward = tmp_path / "subawards.csv"
    pd.DataFrame(
        [
            {
                "prime_award_unique_key": "CONT_AWD_P2_9700",
                "prime_award_piid": "P2",
                "prime_awardee_name": "Large Prime Inc",
                "prime_awardee_uei": "MNOPQRSTUVWX",
                "prime_award_naics_code": "334511",
                "prime_award_description": "aircraft system",
                "subaward_number": "S1",
                "subaward_sam_report_id": "R1",
                "subaward_amount": 25.0,
                "subaward_action_date": "2024-10-02",
                "subawardee_uei": "ABCDEFGHIJKL",
                "subawardee_name": "Example Materials Inc",
                "subaward_description": "sensor component",
                "usaspending_permalink": "https://www.usaspending.gov/award/P2",
                "subaward_sam_report_last_modified_date": "2025-01-01",
            }
        ]
    ).to_csv(subaward, index=False)

    manifest = _run_release(
        lineage_dir=lineage_dir,
        analysis_date=date(2026, 8, 3),
        prime_api_parquets=[prime],
        subaward_sources=[subaward],
    )

    assert manifest["phase"] == "direct_nsf_and_defense_funding_lineage"
    assert manifest["products"]["prime_transactions"]["row_count"] == 2
    assert manifest["products"]["subaward_transactions"]["row_count"] == 1
    assert manifest["products"]["critical_supply_chain_screen"]["row_count"] == 1
    summary = pd.read_parquet(lineage_dir / "nsf_awardee_defense_funding_summary.parquet")
    assert summary["signed_obligation_total"].sum() == 115.0
    assert summary["negative_transaction_count"].sum() == 1
    assert set(summary["nsf_awardee_status"]) == {"current"}
    assert set(summary["specific_award_usage_status"]) == {"not_established"}
    assert set(summary["critical_supply_chain_status"]) == {"not_assessed"}
    evidence = pd.read_parquet(lineage_dir / "nsf_award_defense_evidence.parquet")
    assert set(evidence["specific_award_usage_status"]) == {"not_established"}
    assert set(evidence["critical_supply_chain_status"]) == {"not_assessed"}
    assert evidence["review_award_descriptions"].str.contains("advanced sensor system").any()
    assert evidence["review_product_service_codes"].str.contains("5998").any()
    assert evidence["cet_classifier_version"].notna().all()
    screen = pd.read_parquet(lineage_dir / "nsf_sbir_critical_supply_chain_screen.parquet")
    assert screen.loc[0, "critical_supply_chain_review_candidate"]
    assert screen.loc[0, "defense_policy_mapping_status"] == (
        "deferred_no_authoritative_dod14_or_ndis8_mapping"
    )
    # Screen-derived provenance survives the handoff into the pipelines release.
    assert set(screen["screen_version"]) == {"nsf-screen-v1"}
    assert set(evidence["screen_version"].dropna()) == {"nsf-screen-v1"}
    assert (
        lineage_dir
        / "nsf_awardee_dod_prime_transactions"
        / "fiscal_year=2024"
        / "funding_mode=prime"
        / "part-00000.parquet"
    ).is_file()
    assert (
        lineage_dir
        / "nsf_awardee_dod_prime_transactions"
        / "fiscal_year=2025"
        / "funding_mode=prime"
        / "part-00000.parquet"
    ).is_file()
    quality = json.loads((lineage_dir / "nsf_defense_lineage_quality.json").read_text())
    assert quality["quality_gates_passed"] is True
    assert quality["defense_funding"]["prime_negative_transaction_count"] == 1
    assert manifest["source_boundaries"]["foci_in_scope"] is False
    assert manifest["source_boundaries"]["grants_gov_usage"] == (
        "optional_solicitation_context_only"
    )
    validation = validate_nsf_defense_lineage_release(
        lineage_dir,
        expected_analysis_date=date(2026, 8, 3),
        as_of=date(2026, 8, 3),
    )
    assert validation["quality_gates_passed"] is True
    graph_path = tmp_path / "web" / "data" / "network.json"
    payload = export_lineage(lineage_dir, graph_path)
    assert payload["scope"]["verified_funding_edge_count"] == 2
    assert graph_path.is_file()
    assert (graph_path.parent / "nsf_award_defense_evidence.csv").is_file()


def test_build_release_partitions_archive_when_api_sources_are_configured(tmp_path) -> None:
    lineage_dir = tmp_path / "lineage"
    lineage_dir.mkdir()
    _phase_one_products(lineage_dir)
    prime_api = tmp_path / "prime-api.parquet"
    pd.DataFrame(
        [
            {
                "prime_transaction_id": "123456",
                "dod_award_generated_id": "CONT_AWD_P1_9700",
                "nsf_organization_id": "uei:ABCDEFGHIJKL",
                "recipient_match_method": "exact_uei",
                "recipient_match_confidence": "verified_identifier",
                "instrument_group": "prime_procurement",
                "signed_obligation_amount": 100.0,
                "action_date": "2024-09-30",
            }
        ]
    ).to_parquet(prime_api, index=False)
    prime_archive = tmp_path / "prime-archive.parquet"
    pd.DataFrame(
        [
            {
                "transaction_unique_id": "CONT_TX_1",
                "generated_unique_award_id": "CONT_AWD_P1_9700",
                "vendor_name": "Example Materials Inc",
                "vendor_uei": "ABCDEFGHIJKL",
                "vendor_duns": None,
                "action_date": "2024-09-30",
                "obligation_amount": 100.0,
                "contract_award_type": "A",
                "agency": "Department of Defense",
            },
            {
                "transaction_unique_id": "CONT_TX_OT_1",
                "generated_unique_award_id": "CONT_AWD_OT1_9700",
                "vendor_name": "Example Materials Inc",
                "vendor_uei": "ABCDEFGHIJKL",
                "vendor_duns": None,
                "action_date": "2024-10-01",
                "obligation_amount": -20.0,
                "contract_award_type": "R",
                "agency": "Department of Defense",
            },
        ]
    ).to_parquet(prime_archive, index=False)

    manifest = _run_release(
        lineage_dir=lineage_dir,
        analysis_date=date(2026, 8, 3),
        prime_api_parquets=[prime_api],
        prime_archive_parquets=[prime_archive],
        allow_missing_subawards=True,
    )
    prime = pd.read_parquet(lineage_dir / "nsf_awardee_dod_prime_transactions.parquet")

    assert manifest["products"]["prime_transactions"]["row_count"] == 2
    assert set(prime["prime_transaction_id"]) == {"123456", "CONT_TX_OT_1"}
    assert prime["signed_obligation_amount"].sum() == 80.0
