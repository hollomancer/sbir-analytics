#!/usr/bin/env python3
"""Apply exact NIH RePORTER recovery and build the combined coverage audit."""

import argparse
import hashlib
import json
import os
import tempfile
import zipfile
from pathlib import Path

import pandas as pd

from sbir_analytics.assets.phase_iii_negative_controls import (
    NIHReporterExtractor,
    build_nih_official_keys,
    build_nih_sbir_attempts,
    reconcile_award_identity_attempts,
    resolve_award_identities,
)
from sbir_etl.utils.identifiers import normalize_duns, normalize_uei


HHS_AGENCY = "Department of Health and Human Services"


def _write_parquet(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary_path = Path(handle.name)
    try:
        frame.to_parquet(temporary_path, index=False)
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _identifier_poor_hhs_rows(sbir_awards: pd.DataFrame) -> pd.DataFrame:
    usable_uei = sbir_awards["uei"].map(normalize_uei).notna()
    usable_duns = sbir_awards["duns"].map(normalize_duns).notna()
    selected = sbir_awards.loc[
        ~usable_uei & ~usable_duns & sbir_awards["agency"].eq(HHS_AGENCY)
    ].copy()
    return selected.rename(columns={"Award Year": "award_year"})


def _write_response_bundle(extractor: NIHReporterExtractor, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        for index, body in enumerate(extractor.raw_responses):
            digest = hashlib.sha256(body).hexdigest()
            info = zipfile.ZipInfo(f"{index:05d}-{digest}.json")
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = 0o644 << 16
            archive.writestr(info, body)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _publish_combined_audit(
    *,
    input_path: Path,
    usa_attempt_audit_path: Path,
    output_dir: Path,
    sbir_awards: pd.DataFrame,
    attempts: pd.DataFrame,
    official_projects: pd.DataFrame,
    nih_attempt_audit: pd.DataFrame,
    nih_provenance: dict[str, object],
) -> dict[str, object]:
    usa_attempt_audit = pd.read_parquet(usa_attempt_audit_path)
    combined_attempt_audit = pd.concat(
        [usa_attempt_audit, nih_attempt_audit],
        ignore_index=True,
        sort=False,
    )
    recovery_audit = reconcile_award_identity_attempts(combined_attempt_audit)
    source_context = sbir_awards[
        ["source_row_sha256", "agency", "Award Year"]
    ].rename(columns={"Award Year": "award_year"})
    recovery_audit = recovery_audit.merge(
        source_context,
        on="source_row_sha256",
        how="left",
        validate="one_to_one",
    )
    coverage = (
        recovery_audit.groupby(["recovery_status", "agency", "award_year"], dropna=False)
        .size()
        .rename("source_rows")
        .reset_index()
    )
    _write_parquet(
        recovery_audit,
        output_dir / "phase_iii_identity_recovery_audit.parquet",
    )
    _write_parquet(
        coverage,
        output_dir / "phase_iii_identity_coverage.parquet",
    )
    summary: dict[str, object] = {
        "input_path": str(input_path),
        "usa_attempt_audit_path": str(usa_attempt_audit_path),
        "hhs_identifier_poor_source_rows": len(_identifier_poor_hhs_rows(sbir_awards)),
        "nih_recovery_attempts": len(attempts),
        "nih_official_rows": len(official_projects),
        "recovery_status_counts": {
            str(key): int(value)
            for key, value in recovery_audit["recovery_status"].value_counts().items()
        },
        "pre_outcome_gate": True,
        "nih_provenance": nih_provenance,
    }
    (output_dir / "phase_iii_identity_coverage.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary


def run(input_path: Path, usa_attempt_audit_path: Path, output_dir: Path) -> dict[str, object]:
    sbir_awards = pd.read_parquet(input_path)
    hhs_rows = _identifier_poor_hhs_rows(sbir_awards)
    attempts = build_nih_sbir_attempts(hhs_rows)
    extractor = NIHReporterExtractor(attempts)
    official_projects = extractor.extract()

    response_bundle_path = output_dir / "phase_iii_identity_nih_responses.zip"
    response_bundle_sha256 = _write_response_bundle(extractor, response_bundle_path)
    official_path = output_dir / "phase_iii_identity_nih_projects.parquet"
    _write_parquet(official_projects, official_path)
    official_keys = build_nih_official_keys(
        official_projects,
        source_digest=str(extractor.provenance["source_digest"]),
        snapshot_date=extractor.retrieval_time.date().isoformat(),
    )
    nih_attempt_audit = resolve_award_identities(attempts, official_keys)
    _write_parquet(
        attempts,
        output_dir / "phase_iii_identity_nih_attempts.parquet",
    )
    _write_parquet(
        nih_attempt_audit,
        output_dir / "phase_iii_identity_nih_attempt_audit.parquet",
    )

    return _publish_combined_audit(
        input_path=input_path,
        usa_attempt_audit_path=usa_attempt_audit_path,
        output_dir=output_dir,
        sbir_awards=sbir_awards,
        attempts=attempts,
        official_projects=official_projects,
        nih_attempt_audit=nih_attempt_audit,
        nih_provenance={
            **extractor.provenance,
            "response_bundle": str(response_bundle_path),
            "response_bundle_sha256": response_bundle_sha256,
        },
    )


def rebuild_from_retained_sources(
    input_path: Path,
    usa_attempt_audit_path: Path,
    output_dir: Path,
) -> dict[str, object]:
    """Rebuild the combined audit without repeating completed source requests."""

    sbir_awards = pd.read_parquet(input_path)
    attempts = pd.read_parquet(output_dir / "phase_iii_identity_nih_attempts.parquet")
    official_projects = pd.read_parquet(
        output_dir / "phase_iii_identity_nih_projects.parquet"
    )
    nih_attempt_audit = pd.read_parquet(
        output_dir / "phase_iii_identity_nih_attempt_audit.parquet"
    )
    response_bundle_path = output_dir / "phase_iii_identity_nih_responses.zip"
    response_digests: list[str] = []
    with zipfile.ZipFile(response_bundle_path) as archive:
        for name in sorted(archive.namelist()):
            body_digest = hashlib.sha256(archive.read(name)).hexdigest()
            if not name.endswith(f"-{body_digest}.json"):
                raise ValueError(f"NIH response bundle member digest mismatch: {name}")
            response_digests.append(body_digest)
    source_digest = hashlib.sha256(
        json.dumps(response_digests, separators=(",", ":")).encode()
    ).hexdigest()
    audit_digests = {
        str(item)
        for values in nih_attempt_audit["official_source_digests"]
        for item in values
    }
    if audit_digests and audit_digests != {source_digest}:
        raise ValueError("Retained NIH attempt audit has a different source digest")
    query_keys = NIHReporterExtractor(attempts, requester=lambda _: b"").query_keys_by_year
    query_digest = hashlib.sha256(
        json.dumps(query_keys, separators=(",", ":")).encode()
    ).hexdigest()
    snapshot_dates = sorted(
        {
            str(item)
            for values in nih_attempt_audit["official_snapshot_dates"]
            for item in values
        }
    )
    return _publish_combined_audit(
        input_path=input_path,
        usa_attempt_audit_path=usa_attempt_audit_path,
        output_dir=output_dir,
        sbir_awards=sbir_awards,
        attempts=attempts,
        official_projects=official_projects,
        nih_attempt_audit=nih_attempt_audit,
        nih_provenance={
            "endpoint": "https://api.reporter.nih.gov/v2/projects/search",
            "retrieval_dates": snapshot_dates,
            "request_count": len(response_digests),
            "response_sha256": response_digests,
            "source_digest": source_digest,
            "query_keys_sha256": query_digest,
            "response_bundle": str(response_bundle_path),
            "response_bundle_sha256": _file_sha256(response_bundle_path),
            "rebuilt_from_retained_sources": True,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/processed/phase_iii_census_sbir_awards.parquet"),
    )
    parser.add_argument(
        "--usa-attempt-audit",
        type=Path,
        default=Path(
            "data/processed/phase_iii_identity/"
            "phase_iii_identity_usaspending_attempt_audit.parquet"
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed/phase_iii_identity"),
    )
    parser.add_argument(
        "--reuse-existing-nih",
        action="store_true",
        help="Rebuild from retained NIH response/audit artifacts without API calls",
    )
    args = parser.parse_args()
    operation = rebuild_from_retained_sources if args.reuse_existing_nih else run
    print(json.dumps(operation(args.input, args.usa_attempt_audit, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
