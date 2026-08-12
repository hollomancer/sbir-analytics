"""Hermetic end-to-end test for the NSF-to-defense lineage Dagster job."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest
from dagster import Definitions

from sbir_analytics.assets.jobs.nsf_defense_lineage_job import (
    nsf_defense_lineage_refresh_job,
)
from sbir_analytics.assets.nsf_defense_lineage import (
    nsf_defense_funding_release,
    nsf_defense_lineage_evidence_guardrails,
    nsf_defense_lineage_freshness,
    nsf_defense_lineage_graph,
    nsf_defense_lineage_schema_and_traceability,
    nsf_defense_lineage_validation,
    nsf_direct_award_release,
)


pytestmark = pytest.mark.e2e


def _write_source_fixtures(root: Path, analysis_date: date) -> dict[str, Path]:
    """Write a minimal pinned source slice spanning every release input family."""
    start_date = analysis_date - timedelta(days=365)
    end_date = analysis_date + timedelta(days=365)
    action_date = analysis_date - timedelta(days=30)

    awards = root / "award_data.csv"
    pd.DataFrame(
        [
            {
                "Company": "Example Materials Inc",
                "Award Title": "SBIR Phase II: Materials",
                "Agency": "NSF",
                "Phase": "Phase II",
                "Program": "SBIR",
                "Agency Tracking Number": "0512345",
                "Contract": "620588",
                "Proposal Award Date": start_date.isoformat(),
                "Contract End Date": end_date.isoformat(),
                "Award Year": str(start_date.year),
                "Award Amount": "900000",
                "UEI": "ABCDEFGHIJKL",
                "Abstract": "Additive manufacturing for a microelectronics sensor.",
            }
        ]
    ).to_csv(awards, index=False)

    nsf_snapshot = root / "nsf-snapshot"
    nsf_snapshot.mkdir()
    (nsf_snapshot / "0620588.json").write_text(
        json.dumps(
            {
                "response": {
                    "award": [
                        {
                            "id": "0620588",
                            "title": "SBIR Phase II: Materials",
                            "abstractText": (
                                "Additive manufacturing for a microelectronics sensor."
                            ),
                            "fundProgramName": "Small Business Innovation Research",
                            "startDate": start_date.strftime("%m/%d/%Y"),
                            "expDate": end_date.strftime("%m/%d/%Y"),
                            "estimatedTotalAmt": "900000",
                            "fundsObligatedAmt": "900000",
                            "awardeeName": "Example Materials Inc",
                            "ueiNumber": "ABCDEFGHIJKL",
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    prime_api = root / "prime-api.parquet"
    pd.DataFrame(
        [
            {
                "prime_transaction_id": "API_TX_1",
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
                "action_date": action_date.isoformat(),
                "transaction_description": "microelectronics sensor delivery",
                "award_description": "advanced sensor system",
                "product_or_service_code": "5998",
                "naics_code": "334413",
                "source_system": "USAspending API",
                "source_kind": "FPDS prime transaction",
                "source_transaction_path": "snapshot/transactions/page-00001.json",
                "source_transaction_sha256": "prime-page-hash",
            }
        ]
    ).to_parquet(prime_api, index=False)

    subawards = root / "subawards.csv"
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
                "subaward_action_date": (action_date + timedelta(days=2)).isoformat(),
                "subawardee_uei": "ABCDEFGHIJKL",
                "subawardee_name": "Example Materials Inc",
                "subaward_description": "sensor component",
                "usaspending_permalink": "https://www.usaspending.gov/award/P2",
                "subaward_sam_report_last_modified_date": analysis_date.isoformat(),
            }
        ]
    ).to_csv(subawards, index=False)

    return {
        "awards": awards,
        "nsf_snapshot": nsf_snapshot,
        "prime_api": prime_api,
        "subawards": subawards,
    }


def _product_fingerprints(lineage_dir: Path) -> dict[str, dict[str, object]]:
    manifest = json.loads((lineage_dir / "nsf_defense_lineage_manifest.json").read_text())
    return {
        name: {"row_count": item["row_count"], "sha256": item["sha256"]}
        for name, item in manifest["products"].items()
    }


def test_nsf_defense_lineage_job_replays_pinned_sources_end_to_end(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run source reconciliation through validation and static graph publication twice."""
    analysis_date = datetime.now(UTC).date()
    sources = _write_source_fixtures(tmp_path, analysis_date)
    lineage_dir = tmp_path / "lineage"
    graph_path = tmp_path / "explorer" / "data" / "network.json"
    prefix = "SBIR_ETL__NSF_DEFENSE_LINEAGE__"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SBIR_ETL__PATHS__DATA_ROOT", str(tmp_path / "unused-data"))
    settings = {
        "ANALYSIS_DATE": analysis_date.isoformat(),
        "OUTPUT_DIR": str(lineage_dir),
        "SBIR_AWARDS_PATH": str(sources["awards"]),
        "DIRECT_NSF_SOURCES": str(sources["nsf_snapshot"]),
        "NSF_MAX_WORKERS": "1",
        "PRIME_API_SNAPSHOTS": "",
        "PRIME_API_PARQUETS": str(sources["prime_api"]),
        "PRIME_CONTRACT_ARCHIVES": "",
        "PRIME_ARCHIVE_PARQUETS": "",
        "SUBAWARD_SOURCES": str(sources["subawards"]),
        "FETCH_PRIME_API": "false",
        "MAX_RELEASE_AGE_DAYS": "1",
        "GRAPH_OUTPUT": str(graph_path),
    }
    for name, value in settings.items():
        monkeypatch.setenv(f"{prefix}{name}", value)

    def reject_network(*_args, **_kwargs):
        raise AssertionError("E2E fixture configuration attempted a live network fetch")

    monkeypatch.setattr(
        "sbir_etl.supply_chain.nsf_release.fetch_nsf_award_snapshots",
        reject_network,
    )
    monkeypatch.setattr(
        "sbir_etl.supply_chain.defense_release.run_usaspending_prime_snapshot",
        reject_network,
    )

    definitions = Definitions(
        assets=[
            nsf_direct_award_release,
            nsf_defense_funding_release,
            nsf_defense_lineage_validation,
            nsf_defense_lineage_graph,
        ],
        asset_checks=[
            nsf_defense_lineage_schema_and_traceability,
            nsf_defense_lineage_freshness,
            nsf_defense_lineage_evidence_guardrails,
        ],
        jobs=[nsf_defense_lineage_refresh_job],
    )
    job = definitions.resolve_job_def("nsf_defense_lineage_refresh_job")

    first = job.execute_in_process()
    assert first.success
    assert {
        event.asset_key.to_user_string()
        for event in first.get_asset_materialization_events()
        if event.asset_key is not None
    } == {
        "nsf_direct_award_release",
        "nsf_defense_funding_release",
        "nsf_defense_lineage_validation",
        "nsf_defense_lineage_graph",
    }
    check_results = first.get_asset_check_evaluations()
    assert {item.check_name for item in check_results} == {
        "nsf_defense_lineage_schema_and_traceability",
        "nsf_defense_lineage_freshness",
        "nsf_defense_lineage_evidence_guardrails",
    }
    assert all(item.passed for item in check_results)

    validation = json.loads((lineage_dir / "nsf_defense_lineage_validation.json").read_text())
    assert validation["quality_gates_passed"] is True
    assert all(validation["quality_gates"].values())

    payload = json.loads(graph_path.read_text())
    assert payload["schema_version"] == "2.0"
    assert payload["scope"]["quality_gates_passed"] is True
    assert payload["scope"]["node_count"] > 0
    assert payload["scope"]["edge_count"] > 0
    assert payload["scope"]["verified_funding_edge_count"] == 2
    assert len(payload["downloads"]) == 6
    for download in payload["downloads"].values():
        assert (graph_path.parent / Path(download).name).is_file()

    first_fingerprints = _product_fingerprints(lineage_dir)
    second = job.execute_in_process()
    assert second.success
    assert all(item.passed for item in second.get_asset_check_evaluations())
    assert _product_fingerprints(lineage_dir) == first_fingerprints
