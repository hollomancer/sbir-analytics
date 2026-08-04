"""Build signed DoD prime/subaward funding products for direct NSF awardees."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.extractors.usaspending_award_archive import AwardArchiveContractExtractor
from sbir_etl.extractors.usaspending_prime_api import (
    USASPENDING_EARLIEST_SEARCH_DATE,
    load_usaspending_prime_snapshot,
    run_usaspending_prime_snapshot,
)
from sbir_etl.supply_chain.defense_funding import (
    DEFENSE_FUNDING_SCHEMA_VERSION,
    build_defense_funding_summary,
    build_nsf_award_defense_evidence,
    build_nsf_identity_registry,
    combine_prime_transactions,
    evaluate_defense_funding_quality,
    normalize_prime_api_transactions,
    normalize_prime_archive_transactions,
    normalize_subaward_transactions,
)
from sbir_etl.supply_chain.subaward_network import build_subaward_facts
from sbir_etl.supply_chain.nsf_screen import screen_direct_nsf_awards

DEFAULT_LINEAGE_DIR = Path("data/processed/nsf_sbir_defense_lineage")
DEFAULT_PRIME_SNAPSHOT_ROOT = Path("data/raw/usaspending/nsf_awardee_prime")
DEFAULT_ARCHIVE_EXTRACT_DIR = Path("data/interim/nsf_defense_lineage/contract_archives")

_SUBAWARD_COLUMNS = {
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _prime_snapshot_metadata(path: Path) -> dict[str, object]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        manifest_path = path / "manifest.partial.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"USAspending prime snapshot manifest not found: {path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "path": str(path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": _sha256(manifest_path),
        "retrieval_complete": manifest.get("retrieval_complete"),
    }


def _write_json(payload: object, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _read_subaward_source(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise FileNotFoundError(f"subaward source not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".parquet", ".pq"}:
        frame = pd.read_parquet(path)
    elif suffix == ".csv":
        frame = pd.read_csv(
            path,
            low_memory=False,
            usecols=lambda column: column in _SUBAWARD_COLUMNS,
        )
    elif suffix == ".zip":
        frames: list[pd.DataFrame] = []
        with zipfile.ZipFile(path) as archive:
            members = sorted(
                (
                    info
                    for info in archive.infolist()
                    if not info.is_dir() and info.filename.lower().endswith(".csv")
                ),
                key=lambda info: info.filename,
            )
            if not members:
                raise ValueError(f"subaward archive contains no CSV members: {path}")
            for member in members:
                with archive.open(member) as stream:
                    frames.append(
                        pd.read_csv(
                            stream,
                            low_memory=False,
                            usecols=lambda column: column in _SUBAWARD_COLUMNS,
                        )
                    )
        frame = pd.concat(frames, ignore_index=True)
    else:
        raise ValueError(f"unsupported subaward source format: {path}")
    frame["source_input_path"] = str(path)
    frame["source_input_sha256"] = _sha256(path)
    return frame


def _subaward_match_registry(
    identity_registry: pd.DataFrame,
    direct_awards: pd.DataFrame,
) -> pd.DataFrame:
    direct = direct_awards.dropna(subset=["nsf_organization_id"]).copy()
    program = (
        direct["nsf_program"]
        if "nsf_program" in direct.columns
        else pd.Series("", index=direct.index, dtype="object")
    )
    direct["_sbir"] = program.eq("SBIR")
    direct["_sttr"] = program.eq("STTR")
    start_dates = (
        direct["nsf_start_date"]
        if "nsf_start_date" in direct.columns
        else pd.Series(pd.NaT, index=direct.index, dtype="datetime64[ns]")
    )
    direct["_award_year"] = pd.to_datetime(start_dates, errors="coerce", utc=True).dt.year
    amount_column = (
        "nsf_estimated_total_amount"
        if "nsf_estimated_total_amount" in direct.columns
        else "nsf_obligated_amount"
    )
    amounts = (
        direct[amount_column]
        if amount_column in direct.columns
        else pd.Series(0.0, index=direct.index, dtype="float64")
    )
    direct["_amount"] = pd.to_numeric(amounts, errors="coerce").fillna(0.0)
    rollup = direct.groupby("nsf_organization_id", as_index=False).agg(
        sbir_award_count=("nsf_award_id", "nunique"),
        nsf_sbir_award_count=("_sbir", "sum"),
        nsf_sttr_award_count=("_sttr", "sum"),
        nsf_sbir_first_award_year=("_award_year", "min"),
        nsf_sbir_latest_award_year=("_award_year", "max"),
        nsf_sbir_award_amount=("_amount", "sum"),
    )
    registry = identity_registry.merge(
        rollup, on="nsf_organization_id", how="left", validate="one_to_one"
    )
    registry = registry.rename(
        columns={
            "nsf_organization_id": "sbir_organization_id",
            "recipient_uei": "sbir_uei",
            "recipient_duns": "sbir_duns",
            "nsf_awardee_name": "sbir_awardee_name",
        }
    )
    registry["sbir_funding_agency_count"] = 1
    registry["nsf_sbir_awardee"] = registry["nsf_sbir_award_count"].fillna(0).gt(0)
    registry["nsf_sbir_topic_codes"] = ""
    for column in ("sbir_award_count", "nsf_sbir_award_count", "nsf_sttr_award_count"):
        registry[column] = registry[column].fillna(0).astype(int)
    registry["nsf_sbir_award_amount"] = registry["nsf_sbir_award_amount"].fillna(0.0)
    return registry


def _archive_filters(registry: pd.DataFrame) -> dict[str, list[str]]:
    values: dict[str, set[str]] = {"uei": set(), "duns": set(), "company_names": set()}
    for _, row in registry.iterrows():
        for value in json.loads(row["recipient_uei_aliases"]):
            values["uei"].add(value)
        for value in json.loads(row["recipient_duns_aliases"]):
            values["duns"].add(value)
        for value in json.loads(row["source_name_aliases"]):
            values["company_names"].add(value.upper())
    return {key: sorted(items) for key, items in values.items()}


def _extract_contract_archive(
    archive: Path,
    registry: pd.DataFrame,
    extract_dir: Path,
) -> Path:
    archive_hash = _sha256(archive)
    destination = extract_dir / f"{archive.stem}-{archive_hash[:12]}.parquet"
    if destination.is_file():
        return destination
    extract_dir.mkdir(parents=True, exist_ok=True)
    filter_path = extract_dir / f"nsf-awardee-filters-{archive_hash[:12]}.json"
    _write_json(_archive_filters(registry), filter_path)
    AwardArchiveContractExtractor(filter_path).extract_from_archive(archive, destination)
    return destination


def _write_partitions(
    frame: pd.DataFrame, destination: Path, identifier: str
) -> list[dict[str, Any]]:
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{destination.name}-", dir=parent) as temporary:
        root = Path(temporary) / destination.name
        entries: list[dict[str, Any]] = []
        if not frame.empty:
            for (fiscal_year, funding_mode), partition in frame.groupby(
                ["fiscal_year", "funding_mode"], dropna=False
            ):
                year_label = "unknown" if pd.isna(fiscal_year) else str(int(fiscal_year))
                mode_label = str(funding_mode).replace("/", "_")
                path = (
                    root
                    / f"fiscal_year={year_label}"
                    / f"funding_mode={mode_label}"
                    / "part-00000.parquet"
                )
                _write_parquet(partition, path)
                entries.append(
                    {
                        "fiscal_year": year_label,
                        "funding_mode": mode_label,
                        "path": str(path.relative_to(root)),
                        "row_count": len(partition),
                        "distinct_source_ids": int(partition[identifier].nunique()),
                        "sha256": _sha256(path),
                    }
                )
        _write_json(
            {
                "schema_version": DEFENSE_FUNDING_SCHEMA_VERSION,
                "partition_columns": ["fiscal_year", "funding_mode"],
                "partitions": entries,
            },
            root / "partition_manifest.json",
        )
        if destination.exists():
            shutil.rmtree(destination)
        root.replace(destination)
    return entries


def _assert_analysis_date(frame: pd.DataFrame, analysis_date: date, label: str) -> None:
    if "analysis_date" not in frame.columns or frame.empty:
        return
    values = pd.to_datetime(frame["analysis_date"], errors="coerce", utc=True).dt.date.dropna()
    if not values.eq(analysis_date).all():
        raise ValueError(f"{label} does not share analysis date {analysis_date.isoformat()}")


def build_release(
    *,
    lineage_dir: Path,
    analysis_date: date,
    prime_snapshots: list[Path] | None = None,
    prime_api_parquets: list[Path] | None = None,
    fetch_prime_api: bool = False,
    prime_snapshot_root: Path = DEFAULT_PRIME_SNAPSHOT_ROOT,
    prime_contract_archives: list[Path] | None = None,
    prime_archive_parquets: list[Path] | None = None,
    archive_extract_dir: Path = DEFAULT_ARCHIVE_EXTRACT_DIR,
    subaward_sources: list[Path] | None = None,
    allow_missing_prime: bool = False,
    allow_missing_subawards: bool = False,
) -> dict[str, Any]:
    """Materialize Phase 2/3 products from pinned NSF and USAspending inputs."""

    direct_path = lineage_dir / "nsf_sbir_awards_direct.parquet"
    awardees_path = lineage_dir / "nsf_sbir_awardee_status.parquet"
    reconciliation_path = lineage_dir / "nsf_sbir_award_reconciliation.parquet"
    for path in (direct_path, awardees_path, reconciliation_path):
        if not path.is_file():
            raise FileNotFoundError(f"required Phase 1 product not found: {path}")
    direct = pd.read_parquet(direct_path)
    awardees = pd.read_parquet(awardees_path)
    reconciliation = pd.read_parquet(reconciliation_path)
    _assert_analysis_date(direct, analysis_date, "direct NSF awards")
    _assert_analysis_date(awardees, analysis_date, "NSF awardees")
    _assert_analysis_date(reconciliation, analysis_date, "NSF reconciliation")
    registry = build_nsf_identity_registry(awardees, reconciliation)

    snapshots = list(prime_snapshots or [])
    if fetch_prime_api:
        verified = awardees.loc[awardees["nsf_awardee_uei"].notna()].copy()
        uei_hash = hashlib.sha256(
            "\n".join(sorted(verified["nsf_awardee_uei"].astype(str))).encode()
        ).hexdigest()[:12]
        snapshot = prime_snapshot_root / f"{analysis_date.isoformat()}-{uei_hash}"
        run_usaspending_prime_snapshot(
            verified,
            snapshot,
            start_date=USASPENDING_EARLIEST_SEARCH_DATE,
            end_date=analysis_date,
        )
        snapshots.append(snapshot)
    api_frames = [
        normalize_prime_api_transactions(load_usaspending_prime_snapshot(path))
        for path in snapshots
    ]
    for path in prime_api_parquets or []:
        api_frames.append(normalize_prime_api_transactions(pd.read_parquet(path)))

    archive_frames: list[pd.DataFrame] = []
    archive_inputs: list[dict[str, str]] = []
    ot_only = bool(api_frames)
    for archive in prime_contract_archives or []:
        extracted = _extract_contract_archive(archive, registry, archive_extract_dir)
        archive_frames.append(
            normalize_prime_archive_transactions(
                pd.read_parquet(extracted),
                registry,
                source_path=archive,
                source_sha256=_sha256(archive),
                ot_only=ot_only,
            )
        )
        archive_inputs.append(
            {
                "archive_path": str(archive),
                "archive_sha256": _sha256(archive),
                "extracted_path": str(extracted),
            }
        )
    for path in prime_archive_parquets or []:
        archive_frames.append(
            normalize_prime_archive_transactions(
                pd.read_parquet(path),
                registry,
                source_path=path,
                source_sha256=_sha256(path),
                ot_only=ot_only,
            )
        )
        archive_inputs.append({"archive_parquet_path": str(path), "sha256": _sha256(path)})
    prime = combine_prime_transactions(*api_frames, *archive_frames)
    if prime.empty and not allow_missing_prime:
        raise ValueError("no DoD prime transaction source was configured or produced matches")

    subaward_paths = list(subaward_sources or [])
    if not subaward_paths:
        subaward_paths = sorted(Path("data/raw/usaspending").glob("dod_*subawards*.zip"))
    subaward_transactions = pd.DataFrame()
    matched_facts = pd.DataFrame()
    if subaward_paths:
        raw_subawards = pd.concat(
            [_read_subaward_source(path) for path in subaward_paths], ignore_index=True
        )
        match_registry = _subaward_match_registry(registry, direct)
        matched_facts = build_subaward_facts(match_registry, raw_subawards)
        subaward_transactions = normalize_subaward_transactions(matched_facts)
    elif not allow_missing_subawards:
        raise ValueError("no DoD subaward source was configured or discovered")

    analysis_timestamp = pd.Timestamp(analysis_date).tz_localize(UTC)
    for frame in (prime, subaward_transactions, registry):
        frame["analysis_date"] = analysis_timestamp
    summary = build_defense_funding_summary(prime, subaward_transactions)
    summary_context_columns = [
        "nsf_organization_id",
        "nsf_awardee_status",
        "organization_resolution_method",
        "organization_resolution_confidence",
    ]
    if not summary.empty:
        summary = summary.merge(
            registry[summary_context_columns],
            on="nsf_organization_id",
            how="left",
            validate="many_to_one",
        )
    else:
        for column in summary_context_columns:
            if column not in summary.columns:
                summary[column] = pd.Series(dtype="object")
    summary["prime_api_coverage_start_date"] = USASPENDING_EARLIEST_SEARCH_DATE.isoformat()
    summary["reported_subaward_coverage"] = "reported_first_tier_only"
    summary["specific_award_usage_status"] = "not_established"
    summary["critical_supply_chain_status"] = "not_assessed"
    summary["analysis_date"] = analysis_timestamp
    funded_ids: set[str] = set()
    for frame in (prime, subaward_transactions):
        if frame.empty:
            continue
        funded_ids.update(
            frame.loc[
                frame["recipient_match_confidence"].isin(
                    ["verified_identifier", "verified_legacy_identifier"]
                ),
                "nsf_organization_id",
            ].astype(str)
        )
    award_screen = screen_direct_nsf_awards(direct, funded_organization_ids=funded_ids)
    evidence = build_nsf_award_defense_evidence(
        direct,
        prime,
        subaward_transactions,
        award_screen=award_screen,
    )
    evidence["analysis_date"] = analysis_timestamp
    funding_quality = evaluate_defense_funding_quality(
        prime,
        subaward_transactions,
        summary,
        evidence,
        award_screen=award_screen,
    )
    if not funding_quality["quality_gates_passed"]:
        raise ValueError(f"defense funding quality gates failed: {funding_quality}")

    products: dict[str, tuple[Path, pd.DataFrame]] = {
        "prime_transactions": (
            lineage_dir / "nsf_awardee_dod_prime_transactions.parquet",
            prime,
        ),
        "subaward_transactions": (
            lineage_dir / "nsf_awardee_dod_subaward_transactions.parquet",
            subaward_transactions,
        ),
        "funding_summary": (
            lineage_dir / "nsf_awardee_defense_funding_summary.parquet",
            summary,
        ),
        "award_defense_evidence": (
            lineage_dir / "nsf_award_defense_evidence.parquet",
            evidence,
        ),
        "identity_registry": (
            lineage_dir / "nsf_awardee_identity_registry.parquet",
            registry,
        ),
        "critical_supply_chain_screen": (
            lineage_dir / "nsf_sbir_critical_supply_chain_screen.parquet",
            award_screen,
        ),
    }
    for path, frame in products.values():
        _write_parquet(frame, path)
    prime_partitions = _write_partitions(
        prime,
        lineage_dir / "nsf_awardee_dod_prime_transactions",
        "prime_transaction_id",
    )
    subaward_partitions = _write_partitions(
        subaward_transactions,
        lineage_dir / "nsf_awardee_dod_subaward_transactions",
        "subaward_transaction_id",
    )

    quality_path = lineage_dir / "nsf_defense_lineage_quality.json"
    phase1_quality = (
        json.loads(quality_path.read_text(encoding="utf-8")) if quality_path.is_file() else {}
    )
    phase1_gates = phase1_quality.get("quality_gates", {})
    quality = {
        **phase1_quality,
        "generated_at": datetime.now(UTC).isoformat(),
        "analysis_date": analysis_date.isoformat(),
        "defense_funding": funding_quality,
        "quality_gates": {
            **phase1_gates,
            **{
                f"defense_funding.{key}": value
                for key, value in funding_quality["quality_gates"].items()
            },
        },
        "quality_gates_passed": bool(
            phase1_quality.get("quality_gates_passed", True)
            and funding_quality["quality_gates_passed"]
        ),
        "limitations": sorted(
            set(phase1_quality.get("limitations", []))
            | {
                "USAspending Advanced Search coverage begins 2007-10-01",
                "reported subawards do not enumerate unreported or lower-tier suppliers",
                "name-only matches are candidates and are excluded from verified totals",
                "firm-level DoD funding does not establish use of a specific NSF award",
                "Grants.gov is not used as an award or funding ledger",
            }
        ),
    }
    _write_json(quality, quality_path)

    product_metadata = {
        name: {"path": str(path), "sha256": _sha256(path), "row_count": len(frame)}
        for name, (path, frame) in products.items()
    }
    manifest_path = lineage_dir / "nsf_defense_lineage_manifest.json"
    phase1_manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    )
    manifest = {
        **phase1_manifest,
        "release_schema_version": "NSF-DEFENSE-LINEAGE-2026Q3",
        "phase": "direct_nsf_and_defense_funding_lineage",
        "analysis_date": analysis_date.isoformat(),
        "generated_at": datetime.now(UTC).isoformat(),
        "inputs": {
            **phase1_manifest.get("inputs", {}),
            "prime_api_snapshots": [_prime_snapshot_metadata(path) for path in snapshots],
            "prime_api_parquets": [
                {"path": str(path), "sha256": _sha256(path)} for path in prime_api_parquets or []
            ],
            "prime_contract_archives": archive_inputs,
            "subaward_sources": [
                {"path": str(path), "sha256": _sha256(path)} for path in subaward_paths
            ],
        },
        "products": {**phase1_manifest.get("products", {}), **product_metadata},
        "partitions": {
            "prime_transactions": prime_partitions,
            "subaward_transactions": subaward_partitions,
        },
        "quality_report": {
            "path": str(quality_path),
            "sha256": _sha256(quality_path),
            "quality_gates_passed": quality["quality_gates_passed"],
        },
        "source_boundaries": {
            "grants_gov_usage": "optional_solicitation_context_only",
            "specific_award_usage_default": "not_established",
            "critical_supply_chain_default": "not_assessed",
            "foci_in_scope": False,
            "dod14_ndis8_mapping_status": "deferred_no_authoritative_mapping",
        },
    }
    _write_json(manifest, manifest_path)
    return manifest


__all__ = [
    "DEFAULT_ARCHIVE_EXTRACT_DIR",
    "DEFAULT_LINEAGE_DIR",
    "DEFAULT_PRIME_SNAPSHOT_ROOT",
    "build_release",
]
