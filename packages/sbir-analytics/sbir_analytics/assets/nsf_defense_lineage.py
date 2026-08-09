"""Recurring, fail-closed NSF SBIR to DoD funding lineage release assets.

Epistemic tier: exploratory. This is the operated asset layer that orchestrates
the NSF/defense lineage flow: it invokes the contestable CET
``screen_direct_nsf_awards`` and hands the screened frame to the pipelines
release builder, so the outputs are evidence-gated review candidates, not
citable findings (spec epistemic-tier-enforcement R3; two-populations doctrine
in docs/steering/epistemic-tiers.md). Housing the screen call here keeps
``sbir_etl.supply_chain.defense_release`` free of any exploratory import.
"""

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

from dagster import (
    AssetCheckResult,
    AssetCheckSeverity,
    AssetExecutionContext,
    MetadataValue,
    Output,
    asset,
    asset_check,
)

from sbir_etl.supply_chain.release_validation import validate_nsf_defense_lineage_release
from sbir_etl.supply_chain.web_release import export_lineage
from sbir_etl.utils.cloud_storage import get_data_root


EPISTEMIC_TIER = "exploratory"

_ENV_PREFIX = "SBIR_ETL__NSF_DEFENSE_LINEAGE__"


def _bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(f"{_ENV_PREFIX}{name}", "true" if default else "false")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _paths_env(name: str) -> list[Path]:
    value = os.getenv(f"{_ENV_PREFIX}{name}", "").strip()
    return [Path(item) for item in value.split(os.pathsep) if item] if value else []


def _analysis_date() -> date:
    value = os.getenv(f"{_ENV_PREFIX}ANALYSIS_DATE")
    return date.fromisoformat(value) if value else datetime.now(UTC).date()


def _lineage_dir() -> Path:
    configured = os.getenv(f"{_ENV_PREFIX}OUTPUT_DIR")
    return (
        Path(configured)
        if configured
        else get_data_root() / "processed" / "nsf_sbir_defense_lineage"
    )


def _metadata(manifest: dict) -> dict:
    products = manifest.get("products", {})
    return {
        "analysis_date": str(manifest.get("analysis_date")),
        "phase": str(manifest.get("phase")),
        "product_count": len(products),
        "products": MetadataValue.json(
            {
                name: {
                    "path": item.get("path"),
                    "row_count": item.get("row_count"),
                    "sha256": item.get("sha256"),
                }
                for name, item in products.items()
                if isinstance(item, dict)
            }
        ),
    }


@asset(
    group_name="nsf_defense_lineage",
    compute_kind="python",
    description="Direct NSF SBIR/STTR awards reconciled to the SBIR.gov baseline.",
)
def nsf_direct_award_release(context: AssetExecutionContext) -> Output[dict]:
    from sbir_etl.supply_chain.nsf_release import build_release

    analysis_date = _analysis_date()
    output_dir = _lineage_dir()
    awards_path = Path(
        os.getenv(
            f"{_ENV_PREFIX}SBIR_AWARDS_PATH",
            str(get_data_root() / "raw" / "sbir" / "award_data.csv"),
        )
    )
    direct_sources = _paths_env("DIRECT_NSF_SOURCES") or None
    context.log.info(f"Building direct NSF release for {analysis_date.isoformat()} in {output_dir}")
    manifest = build_release(
        awards_path=awards_path,
        output_dir=output_dir,
        analysis_date=analysis_date,
        direct_sources=direct_sources,
        snapshot_root=get_data_root() / "raw" / "nsf" / "award_api",
        max_workers=int(os.getenv(f"{_ENV_PREFIX}NSF_MAX_WORKERS", "8")),
        allow_partial=False,
    )
    return Output(manifest, metadata=_metadata(manifest))


@asset(
    group_name="nsf_defense_lineage",
    compute_kind="python",
    description="Signed DoD prime and reported-subaward funding for resolved NSF awardees.",
)
def nsf_defense_funding_release(
    context: AssetExecutionContext,
    nsf_direct_award_release: dict,
) -> Output[dict]:
    from sbir_etl.supply_chain.defense_release import build_release, prepare_defense_funding
    from sbir_etl.supply_chain.nsf_screen import screen_direct_nsf_awards

    del nsf_direct_award_release
    analysis_date = _analysis_date()
    output_dir = _lineage_dir()
    workset = prepare_defense_funding(
        lineage_dir=output_dir,
        analysis_date=analysis_date,
        prime_snapshots=_paths_env("PRIME_API_SNAPSHOTS"),
        prime_api_parquets=_paths_env("PRIME_API_PARQUETS"),
        fetch_prime_api=_bool_env("FETCH_PRIME_API"),
        prime_snapshot_root=get_data_root() / "raw" / "usaspending" / "nsf_awardee_prime",
        prime_contract_archives=_paths_env("PRIME_CONTRACT_ARCHIVES"),
        prime_archive_parquets=_paths_env("PRIME_ARCHIVE_PARQUETS"),
        archive_extract_dir=(
            get_data_root() / "interim" / "nsf_defense_lineage" / "contract_archives"
        ),
        subaward_sources=_paths_env("SUBAWARD_SOURCES"),
        allow_missing_prime=False,
        allow_missing_subawards=False,
    )
    # The contestable CET screen runs here, in the exploratory asset layer; the
    # pipelines release builder only reshapes the screened frame it is given.
    award_screen = screen_direct_nsf_awards(
        workset.direct,
        funded_organization_ids=set(workset.funded_organization_ids),
    )
    manifest = build_release(workset, award_screen=award_screen)
    return Output(manifest, metadata=_metadata(manifest))


@asset(
    group_name="nsf_defense_lineage",
    compute_kind="validation",
    description="Manifest, freshness, schema-drift, traceability, and evidence-gate validation.",
)
def nsf_defense_lineage_validation(
    context: AssetExecutionContext,
    nsf_defense_funding_release: dict,
) -> Output[dict]:
    del nsf_defense_funding_release
    report = validate_nsf_defense_lineage_release(
        _lineage_dir(),
        expected_analysis_date=_analysis_date(),
        max_release_age_days=int(os.getenv(f"{_ENV_PREFIX}MAX_RELEASE_AGE_DAYS", "45")),
    )
    path = _lineage_dir() / "nsf_defense_lineage_validation.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)
    context.log.info(
        f"NSF defense lineage validation passed={report['quality_gates_passed']} path={path}"
    )
    return Output(
        report,
        metadata={
            "quality_gates_passed": report["quality_gates_passed"],
            "analysis_date": str(report["analysis_date"]),
            "release_age_days": report["release_age_days"],
            "validation_report": MetadataValue.path(str(path)),
            "quality_gates": MetadataValue.json(report["quality_gates"]),
        },
    )


@asset(
    group_name="nsf_defense_lineage",
    compute_kind="json",
    description="Static multi-partite graph and downloadable evidence tables for analysts.",
)
def nsf_defense_lineage_graph(
    context: AssetExecutionContext,
    nsf_defense_lineage_validation: dict,
) -> Output[dict]:
    if not nsf_defense_lineage_validation.get("quality_gates_passed"):
        raise ValueError("NSF defense lineage validation failed; refusing graph publication")
    output = Path(
        os.getenv(
            f"{_ENV_PREFIX}GRAPH_OUTPUT",
            "tools/sbir-dib-network-explorer/data/network.json",
        )
    )
    payload = export_lineage(_lineage_dir(), output)
    scope = payload["scope"]
    return Output(
        scope,
        metadata={
            "path": MetadataValue.path(str(output)),
            "node_count": scope["node_count"],
            "edge_count": scope["edge_count"],
            "verified_funding_edge_count": scope["verified_funding_edge_count"],
            "candidate_edge_count": scope["candidate_edge_count"],
        },
    )


@asset_check(
    asset=nsf_defense_lineage_validation,
    name="nsf_defense_lineage_schema_and_traceability",
)
def nsf_defense_lineage_schema_and_traceability(
    nsf_defense_lineage_validation: dict,
) -> AssetCheckResult:
    gates = nsf_defense_lineage_validation["quality_gates"]
    selected = {
        key: gates[key]
        for key in (
            "product_schemas_valid",
            "product_analysis_dates_consistent",
            "source_grain_ids_unique",
            "manifest_product_checksums_valid",
            "manifest_product_row_counts_valid",
        )
    }
    passed = all(selected.values())
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR,
        metadata=selected,
    )


@asset_check(
    asset=nsf_defense_lineage_validation,
    name="nsf_defense_lineage_freshness",
)
def nsf_defense_lineage_freshness(
    nsf_defense_lineage_validation: dict,
) -> AssetCheckResult:
    gates = nsf_defense_lineage_validation["quality_gates"]
    passed = bool(gates["release_not_future_dated"] and gates["release_is_fresh"])
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR,
        metadata={
            "analysis_date": str(nsf_defense_lineage_validation["analysis_date"]),
            "release_age_days": nsf_defense_lineage_validation["release_age_days"],
            "max_release_age_days": nsf_defense_lineage_validation["max_release_age_days"],
        },
    )


@asset_check(
    asset=nsf_defense_lineage_validation,
    name="nsf_defense_lineage_evidence_guardrails",
)
def nsf_defense_lineage_evidence_guardrails(
    nsf_defense_lineage_validation: dict,
) -> AssetCheckResult:
    gates = nsf_defense_lineage_validation["quality_gates"]
    selected = {
        key: gates[key]
        for key in (
            "conclusions_remain_evidence_gated",
            "dod14_ndis8_mapping_remains_deferred",
            "foci_excluded",
            "grants_gov_not_used_as_ledger",
        )
    }
    passed = all(selected.values())
    return AssetCheckResult(
        passed=passed,
        severity=AssetCheckSeverity.WARN if passed else AssetCheckSeverity.ERROR,
        metadata=selected,
    )


__all__ = [
    "nsf_defense_funding_release",
    "nsf_defense_lineage_evidence_guardrails",
    "nsf_defense_lineage_freshness",
    "nsf_defense_lineage_graph",
    "nsf_defense_lineage_schema_and_traceability",
    "nsf_defense_lineage_validation",
    "nsf_direct_award_release",
]
