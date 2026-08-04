#!/usr/bin/env python3
"""Build exact award-to-solicitation references from SBIR.gov bulk award data.

The bulk award export is an award source. Its solicitation number and topic code can
support exact identifier links, but award titles and abstracts remain award text; they
are never relabeled as solicitation titles, topic descriptions, or requirements.
"""

from __future__ import annotations

import argparse
from datetime import date
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

from sbir_etl.extractors.sbir_gov_api import SBIR_AWARDS_CSV_URL


SCHEMA_VERSION = "sbir-bulk-solicitation-linkage-v1"
SOURCE_SYSTEM = "SBIR.gov bulk award_data.csv"
DEFAULT_SOURCE = Path("data/raw/sbir/award_data.csv")
DEFAULT_SCHEMA = Path("docs/data/sbir_awards_columns.json")
DEFAULT_OUTPUT_DIR = Path("data/processed/solicitation_evidence")
DEFAULT_LINKS_OUTPUT = DEFAULT_OUTPUT_DIR / "award_solicitation_link_assertions.parquet"
DEFAULT_MANIFEST_OUTPUT = DEFAULT_OUTPUT_DIR / "sbir_bulk_linkage_manifest.json"
DEFAULT_SUMMARY_OUTPUT = DEFAULT_OUTPUT_DIR / "sbir_bulk_linkage_summary.md"
MINIMUM_SOURCE_ROWS = 50
NSF_AGENCY = "National Science Foundation"

REQUIRED_COLUMNS = [
    "Company",
    "Award Title",
    "Agency",
    "Branch",
    "Phase",
    "Program",
    "Agency Tracking Number",
    "Contract",
    "Proposal Award Date",
    "Contract End Date",
    "Solicitation Number",
    "Solicitation Year",
    "Solicitation Close Date",
    "Proposal Receipt Date",
    "Date of Notification",
    "Topic Code",
    "Award Year",
    "Award Amount",
    "UEI",
    "Duns",
    "Abstract",
]

LINK_ASSERTION_COLUMNS = [
    "link_assertion_id",
    "link_class",
    "link_target_grain",
    "source_award_id_type",
    "source_award_id",
    "award_record_sha256",
    "company_name",
    "company_uei",
    "company_duns",
    "award_title",
    "award_abstract",
    "agency",
    "branch",
    "phase",
    "program",
    "agency_tracking_number",
    "contract",
    "proposal_award_date",
    "contract_end_date",
    "award_year",
    "award_amount",
    "solicitation_number",
    "solicitation_year",
    "solicitation_close_date",
    "proposal_receipt_date",
    "date_of_notification",
    "topic_code",
    "source_system",
    "source_url",
    "source_snapshot_sha256",
    "analysis_date",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sql_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _sql_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _clean_source(column: str) -> str:
    return f"TRIM(COALESCE({_sql_identifier(column)}, ''))"


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _read_header(source: Path) -> list[str]:
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            return next(reader)
        except StopIteration:
            raise ValueError(f"{source} is empty") from None


def _load_expected_columns(schema_path: Path) -> list[str]:
    payload = json.loads(schema_path.read_text(encoding="utf-8"))
    columns = payload.get("columns") if isinstance(payload, dict) else payload
    if not isinstance(columns, list) or any(not isinstance(column, str) for column in columns):
        raise ValueError(f"{schema_path} does not contain a string column list")
    return columns


def _schema_report(observed: list[str], expected: list[str]) -> dict[str, Any]:
    return {
        "matches_expected": observed == expected,
        "required_columns_present": all(column in observed for column in REQUIRED_COLUMNS),
        "missing_required_columns": [
            column for column in REQUIRED_COLUMNS if column not in observed
        ],
        "missing_expected_columns": [column for column in expected if column not in observed],
        "extra_columns": [column for column in observed if column not in expected],
        "observed_columns": observed,
        "expected_columns": expected,
    }


def _source_metadata(
    source: Path,
    metadata_path: Path | None,
    *,
    source_hash: str,
) -> dict[str, Any]:
    candidate = metadata_path or source.with_suffix(".meta.json")
    if not candidate.is_file():
        return {
            "path": str(candidate),
            "status": "missing",
            "source_url": SBIR_AWARDS_CSV_URL,
        }

    payload = json.loads(candidate.read_text(encoding="utf-8"))
    hash_matches = payload.get("sha256") == source_hash
    size_matches = payload.get("size") == source.stat().st_size
    return {
        "path": str(candidate),
        "status": "match" if hash_matches and size_matches else "mismatch",
        "hash_matches": hash_matches,
        "size_matches": size_matches,
        "source_url": payload.get("source_url") or SBIR_AWARDS_CSV_URL,
        "downloaded_at": payload.get("downloaded_at"),
        "recorded_sha256": payload.get("sha256"),
        "recorded_size": payload.get("size"),
    }


def _fetch_dicts(connection: duckdb.DuckDBPyConnection, query: str) -> list[dict[str, Any]]:
    result = connection.execute(query)
    columns = [description[0] for description in result.description]
    return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]


def _add_rates(row: dict[str, Any]) -> dict[str, Any]:
    award_rows = int(row.get("award_rows") or 0)
    enriched = dict(row)
    for count_name, rate_name in (
        ("solicitation_reference_rows", "solicitation_reference_rate"),
        ("topic_reference_rows", "topic_reference_rate"),
        ("exact_solicitation_topic_rows", "exact_solicitation_topic_rate"),
    ):
        enriched[rate_name] = int(row.get(count_name) or 0) / award_rows if award_rows else 0.0
    return enriched


def _create_views(
    connection: duckdb.DuckDBPyConnection,
    *,
    source: Path,
    observed_columns: list[str],
    source_hash: str,
    source_url: str,
    analysis_date: date,
) -> None:
    source_literal = _sql_literal(source)
    connection.execute(
        f"""
        CREATE TEMP VIEW award_source AS
        SELECT *
        FROM read_csv_auto({source_literal}, all_varchar=true)
        """
    )

    fingerprint_fields = ", ".join(_clean_source(column) for column in observed_columns)
    record_fingerprint = f"sha256(concat_ws(chr(31), {fingerprint_fields}))"
    connection.execute(
        f"""
        CREATE TEMP VIEW normalized_awards AS
        WITH normalized AS (
            SELECT
                {_clean_source("Company")} AS company_name,
                {_clean_source("Award Title")} AS award_title,
                {_clean_source("Abstract")} AS award_abstract,
                {_clean_source("Agency")} AS agency,
                {_clean_source("Branch")} AS branch,
                {_clean_source("Phase")} AS phase,
                {_clean_source("Program")} AS program,
                {_clean_source("Agency Tracking Number")} AS agency_tracking_number,
                {_clean_source("Contract")} AS contract,
                TRY_CAST(NULLIF({_clean_source("Proposal Award Date")}, '') AS DATE)
                    AS proposal_award_date,
                TRY_CAST(NULLIF({_clean_source("Contract End Date")}, '') AS DATE)
                    AS contract_end_date,
                {_clean_source("Solicitation Number")} AS solicitation_number,
                TRY_CAST(NULLIF({_clean_source("Solicitation Year")}, '') AS INTEGER)
                    AS solicitation_year,
                TRY_CAST(NULLIF({_clean_source("Solicitation Close Date")}, '') AS DATE)
                    AS solicitation_close_date,
                TRY_CAST(NULLIF({_clean_source("Proposal Receipt Date")}, '') AS DATE)
                    AS proposal_receipt_date,
                TRY_CAST(NULLIF({_clean_source("Date of Notification")}, '') AS DATE)
                    AS date_of_notification,
                {_clean_source("Topic Code")} AS topic_code,
                TRY_CAST(NULLIF({_clean_source("Award Year")}, '') AS INTEGER) AS award_year,
                TRY_CAST(
                    NULLIF(
                        REPLACE(REPLACE({_clean_source("Award Amount")}, ',', ''), '$', ''),
                        ''
                    ) AS DOUBLE
                ) AS award_amount,
                {_clean_source("UEI")} AS company_uei,
                {_clean_source("Duns")} AS company_duns,
                {record_fingerprint} AS award_record_sha256
            FROM award_source
        )
        SELECT
            *,
            CASE
                WHEN agency_tracking_number <> '' THEN 'agency_tracking_number'
                WHEN contract <> '' THEN 'contract'
                ELSE 'record_fingerprint'
            END AS source_award_id_type,
            CASE
                WHEN agency_tracking_number <> '' THEN agency_tracking_number
                WHEN contract <> '' THEN contract
                ELSE 'sbirgov:' || substr(award_record_sha256, 1, 20)
            END AS source_award_id
        FROM normalized
        """
    )

    connection.execute(
        f"""
        CREATE TEMP VIEW link_assertions_raw AS
        SELECT
            'sbir_bulk_link:' || sha256(
                concat_ws(
                    chr(31),
                    source_award_id_type,
                    source_award_id,
                    award_record_sha256,
                    solicitation_number,
                    topic_code
                )
            ) AS link_assertion_id,
            'exact_source_identifier' AS link_class,
            CASE WHEN topic_code <> '' THEN 'solicitation_topic' ELSE 'solicitation' END
                AS link_target_grain,
            source_award_id_type,
            source_award_id,
            award_record_sha256,
            company_name,
            NULLIF(company_uei, '') AS company_uei,
            NULLIF(company_duns, '') AS company_duns,
            award_title,
            NULLIF(award_abstract, '') AS award_abstract,
            agency,
            NULLIF(branch, '') AS branch,
            phase,
            program,
            NULLIF(agency_tracking_number, '') AS agency_tracking_number,
            NULLIF(contract, '') AS contract,
            proposal_award_date,
            contract_end_date,
            award_year,
            award_amount,
            solicitation_number,
            solicitation_year,
            solicitation_close_date,
            proposal_receipt_date,
            date_of_notification,
            NULLIF(topic_code, '') AS topic_code,
            {_sql_literal(SOURCE_SYSTEM)} AS source_system,
            {_sql_literal(source_url)} AS source_url,
            {_sql_literal(source_hash)} AS source_snapshot_sha256,
            DATE {_sql_literal(analysis_date.isoformat())} AS analysis_date
        FROM normalized_awards
        WHERE solicitation_number <> ''
        """
    )
    projected_columns = ", ".join(_sql_identifier(column) for column in LINK_ASSERTION_COLUMNS)
    connection.execute(
        f"""
        CREATE TEMP VIEW link_assertions AS
        SELECT {projected_columns}
        FROM (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY link_assertion_id
                    ORDER BY source_award_id, award_record_sha256
                ) AS duplicate_rank
            FROM link_assertions_raw
        )
        WHERE duplicate_rank = 1
        """
    )


def _coverage_query(*, where: str = "", dimension: str | None = None) -> str:
    dimension_select = f"{_sql_identifier(dimension)}," if dimension else ""
    group_by = f"GROUP BY {_sql_identifier(dimension)}" if dimension else ""
    return f"""
        SELECT
            {dimension_select}
            COUNT(*) AS award_rows,
            COUNT(DISTINCT NULLIF(company_name, '')) AS unique_company_names,
            COALESCE(SUM(award_amount), 0.0) AS award_funding,
            MIN(award_year) AS first_award_year,
            MAX(award_year) AS last_award_year,
            SUM(CASE WHEN solicitation_number <> '' THEN 1 ELSE 0 END)
                AS solicitation_reference_rows,
            SUM(CASE WHEN topic_code <> '' THEN 1 ELSE 0 END) AS topic_reference_rows,
            SUM(CASE WHEN solicitation_number <> '' AND topic_code <> '' THEN 1 ELSE 0 END)
                AS exact_solicitation_topic_rows,
            SUM(CASE WHEN solicitation_number = '' AND topic_code <> '' THEN 1 ELSE 0 END)
                AS topic_only_rows,
            SUM(CASE WHEN solicitation_number <> '' AND topic_code = '' THEN 1 ELSE 0 END)
                AS solicitation_only_rows,
            SUM(CASE WHEN solicitation_number = '' AND topic_code = '' THEN 1 ELSE 0 END)
                AS neither_reference_rows,
            COUNT(DISTINCT NULLIF(solicitation_number, '')) AS unique_solicitations,
            COUNT(DISTINCT CASE
                WHEN solicitation_number <> '' AND topic_code <> ''
                THEN concat_ws(chr(31), agency, solicitation_number, topic_code)
            END) AS unique_solicitation_topics
        FROM normalized_awards
        {where}
        {group_by}
    """


def _field_coverage(
    connection: duckdb.DuckDBPyConnection,
    *,
    award_rows: int,
) -> dict[str, dict[str, int | float]]:
    fields = {
        "Award Title": "award_title",
        "Abstract": "award_abstract",
        "Agency Tracking Number": "agency_tracking_number",
        "Contract": "contract",
        "Award Amount": "award_amount",
        "UEI": "company_uei",
        "Duns": "company_duns",
        "Solicitation Number": "solicitation_number",
        "Solicitation Year": "solicitation_year",
        "Solicitation Close Date": "solicitation_close_date",
        "Topic Code": "topic_code",
    }
    coverage: dict[str, dict[str, int | float]] = {}
    for source_field, normalized_field in fields.items():
        populated = int(
            connection.execute(
                f"SELECT COUNT(*) FROM normalized_awards "
                f"WHERE {_sql_identifier(normalized_field)} IS NOT NULL "
                f"AND CAST({_sql_identifier(normalized_field)} AS VARCHAR) <> ''"
            ).fetchone()[0]
        )
        coverage[source_field] = {
            "populated_rows": populated,
            "coverage_rate": populated / award_rows if award_rows else 0.0,
        }
    return coverage


def _materialize_links(
    connection: duckdb.DuckDBPyConnection,
    output: Path,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    if temporary.exists():
        temporary.unlink()
    projected_columns = ", ".join(_sql_identifier(column) for column in LINK_ASSERTION_COLUMNS)
    connection.execute(
        f"""
        COPY (
            SELECT {projected_columns}
            FROM link_assertions
            ORDER BY link_assertion_id
        ) TO {_sql_literal(temporary)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )
    temporary.replace(output)
    return {
        "path": str(output),
        "rows": int(connection.execute("SELECT COUNT(*) FROM link_assertions").fetchone()[0]),
        "sha256": _sha256(output),
        "bytes": output.stat().st_size,
    }


def _supersede_existing_links(output: Path) -> dict[str, Any] | None:
    """Move a stale link artifact aside without overwriting an earlier quarantine."""
    if not output.is_file():
        return None

    artifact_hash = _sha256(output)
    artifact_bytes = output.stat().st_size
    hash_prefix = artifact_hash[:12]
    superseded = output.with_name(f"{output.name}.{hash_prefix}.superseded")
    duplicate_index = 2
    while superseded.exists():
        superseded = output.with_name(f"{output.name}.{hash_prefix}.{duplicate_index}.superseded")
        duplicate_index += 1

    output.replace(superseded)
    return {
        "path": str(superseded),
        "sha256": artifact_hash,
        "bytes": artifact_bytes,
    }


def render_summary(manifest: dict[str, Any]) -> str:
    overall = manifest["coverage"]["overall"]
    nsf = manifest["coverage"]["nsf"]
    recent = manifest["coverage"]["nsf_award_year_2022_plus"]
    decision = manifest["adapter_decision"]
    return "\n".join(
        [
            "# SBIR.gov bulk award solicitation-linkage coverage",
            "",
            f"**Analysis date:** {manifest['analysis_date']}",
            "",
            f"**Adapter decision:** `{decision['status']}`",
            "",
            "## Coverage",
            "",
            "| Cohort | Awards | Company names | Solicitation ID | Topic code | Both | Funding |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
            (
                f"| All agencies | {overall['award_rows']:,} | "
                f"{overall['unique_company_names']:,} | "
                f"{overall['solicitation_reference_rows']:,} "
                f"({overall['solicitation_reference_rate']:.1%}) | "
                f"{overall['topic_reference_rows']:,} ({overall['topic_reference_rate']:.1%}) | "
                f"{overall['exact_solicitation_topic_rows']:,} "
                f"({overall['exact_solicitation_topic_rate']:.1%}) | "
                f"${overall['award_funding']:,.0f} |"
            ),
            (
                f"| NSF, all years | {nsf['award_rows']:,} | "
                f"{nsf['unique_company_names']:,} | "
                f"{nsf['solicitation_reference_rows']:,} "
                f"({nsf['solicitation_reference_rate']:.1%}) | "
                f"{nsf['topic_reference_rows']:,} ({nsf['topic_reference_rate']:.1%}) | "
                f"{nsf['exact_solicitation_topic_rows']:,} "
                f"({nsf['exact_solicitation_topic_rate']:.1%}) | "
                f"${nsf['award_funding']:,.0f} |"
            ),
            (
                f"| NSF, award years 2022+ | {recent['award_rows']:,} | "
                f"{recent['unique_company_names']:,} | "
                f"{recent['solicitation_reference_rows']:,} "
                f"({recent['solicitation_reference_rate']:.1%}) | "
                f"{recent['topic_reference_rows']:,} ({recent['topic_reference_rate']:.1%}) | "
                f"{recent['exact_solicitation_topic_rows']:,} "
                f"({recent['exact_solicitation_topic_rate']:.1%}) | "
                f"${recent['award_funding']:,.0f} |"
            ),
            "",
            "## Interpretation boundary",
            "",
            "- A solicitation number in an official bulk award row supports an exact identifier "
            "reference from that award to the named solicitation.",
            "- A topic code is linked to the solicitation only when both identifiers occur in the "
            "same award row.",
            "- Award titles and abstracts remain award text. They are not solicitation titles, "
            "topic descriptions, attachment text, or government requirement statements.",
            "- Bulk awards contain no nested solicitation subtopics or attachment bodies. Those "
            "remain separate source gaps.",
            "- Historical coverage is uneven; use the year-stratified rates in the manifest rather "
            "than generalizing the recent NSF rate backward.",
            "",
        ]
    )


def build_bulk_linkage_artifacts(
    *,
    source: Path,
    expected_schema: Path,
    links_output: Path,
    manifest_output: Path,
    summary_output: Path,
    analysis_date: date,
    metadata_path: Path | None = None,
    minimum_rows: int = MINIMUM_SOURCE_ROWS,
    require_metadata: bool = True,
) -> dict[str, Any]:
    """Build exact-link Parquet plus a source and coverage manifest."""
    if not source.is_file():
        raise FileNotFoundError(source)
    if source.resolve() == links_output.resolve():
        raise ValueError("links output cannot overwrite the bulk award source")

    observed_columns = _read_header(source)
    expected_columns = _load_expected_columns(expected_schema)
    schema = _schema_report(observed_columns, expected_columns)
    if not schema["required_columns_present"]:
        raise ValueError(
            "bulk award source is missing required columns: "
            + ", ".join(schema["missing_required_columns"])
        )

    source_hash = _sha256(source)
    metadata = _source_metadata(source, metadata_path, source_hash=source_hash)
    source_url = str(metadata.get("source_url") or SBIR_AWARDS_CSV_URL)

    connection = duckdb.connect()
    try:
        _create_views(
            connection,
            source=source,
            observed_columns=observed_columns,
            source_hash=source_hash,
            source_url=source_url,
            analysis_date=analysis_date,
        )
        overall = _add_rates(_fetch_dicts(connection, _coverage_query())[0])
        by_agency = [
            _add_rates(row)
            for row in _fetch_dicts(
                connection,
                _coverage_query(dimension="agency") + " ORDER BY award_rows DESC",
            )
        ]
        nsf = _add_rates(
            _fetch_dicts(
                connection,
                _coverage_query(where=f"WHERE agency = {_sql_literal(NSF_AGENCY)}"),
            )[0]
        )
        nsf_recent = _add_rates(
            _fetch_dicts(
                connection,
                _coverage_query(
                    where=f"WHERE agency = {_sql_literal(NSF_AGENCY)} AND award_year >= 2022"
                ),
            )[0]
        )
        nsf_by_year = [
            _add_rates(row)
            for row in _fetch_dicts(
                connection,
                _coverage_query(
                    where=f"WHERE agency = {_sql_literal(NSF_AGENCY)}",
                    dimension="award_year",
                )
                + " ORDER BY award_year DESC NULLS LAST",
            )
        ]
        raw_link_rows = int(
            connection.execute("SELECT COUNT(*) FROM link_assertions_raw").fetchone()[0]
        )
        link_rows = int(connection.execute("SELECT COUNT(*) FROM link_assertions").fetchone()[0])
        duplicate_ids = int(
            connection.execute(
                "SELECT COUNT(*) - COUNT(DISTINCT link_assertion_id) FROM link_assertions"
            ).fetchone()[0]
        )
        field_coverage = _field_coverage(
            connection,
            award_rows=int(overall["award_rows"]),
        )

        blockers: list[str] = []
        if int(overall["award_rows"]) < minimum_rows:
            blockers.append(
                f"source contains {overall['award_rows']} rows; "
                f"at least {minimum_rows} are required"
            )
        if not schema["matches_expected"]:
            blockers.append("observed bulk award columns do not match the reviewed source schema")
        if require_metadata and metadata["status"] != "match":
            blockers.append("source metadata sidecar is missing or does not match the source bytes")
        if link_rows == 0:
            blockers.append("source contains no award rows with a solicitation number")
        if duplicate_ids:
            blockers.append("candidate link assertion identifiers are not unique")

        links_artifact: dict[str, Any] = {
            "path": str(links_output),
            "rows": link_rows,
            "materialized": False,
        }
        if blockers:
            superseded_artifact = _supersede_existing_links(links_output)
            if superseded_artifact is not None:
                links_artifact["superseded_artifact"] = superseded_artifact
        else:
            links_artifact = {"materialized": True, **_materialize_links(connection, links_output)}
    finally:
        connection.close()

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "analysis_date": analysis_date.isoformat(),
        "source": {
            "system": SOURCE_SYSTEM,
            "path": str(source),
            "source_url": source_url,
            "sha256": source_hash,
            "bytes": source.stat().st_size,
            "metadata": metadata,
        },
        "schema": schema,
        "coverage": {
            "overall": overall,
            "by_agency": by_agency,
            "nsf": nsf,
            "nsf_award_year_2022_plus": nsf_recent,
            "nsf_by_award_year": nsf_by_year,
            "field_coverage": field_coverage,
        },
        "link_assertions": {
            "raw_rows_with_solicitation_number": raw_link_rows,
            "duplicate_source_assertion_rows": raw_link_rows - link_rows,
            "materialized_ids_unique": duplicate_ids == 0,
            **links_artifact,
        },
        "adapter_decision": {
            "adapter": "sbir_gov_bulk_award_linkage",
            "status": "go" if not blockers else "no_go",
            "blockers": blockers,
            "authorized_use": (
                "exact award-to-solicitation/topic identifier linkage" if not blockers else "none"
            ),
        },
        "limitations": [
            "award titles and abstracts are award text, not solicitation or requirement text",
            "topic codes without solicitation numbers are not emitted as exact links",
            "bulk awards do not contain nested solicitation subtopics or attachment bodies",
            "historical solicitation-number coverage is uneven and must be stratified by year",
            "an exact identifier link does not establish contract use or supply-chain dependency",
        ],
    }
    _atomic_write_text(manifest_output, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    _atomic_write_text(summary_output, render_summary(manifest))
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--source-metadata", type=Path)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    parser.add_argument("--links-output", type=Path, default=DEFAULT_LINKS_OUTPUT)
    parser.add_argument("--manifest-output", type=Path, default=DEFAULT_MANIFEST_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--analysis-date", type=date.fromisoformat, required=True)
    parser.add_argument("--minimum-rows", type=int, default=MINIMUM_SOURCE_ROWS)
    parser.add_argument("--allow-missing-metadata", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_bulk_linkage_artifacts(
        source=args.source,
        expected_schema=args.schema,
        links_output=args.links_output,
        manifest_output=args.manifest_output,
        summary_output=args.summary_output,
        analysis_date=args.analysis_date,
        metadata_path=args.source_metadata,
        minimum_rows=args.minimum_rows,
        require_metadata=not args.allow_missing_metadata,
    )
    print(json.dumps(manifest["adapter_decision"], indent=2, sort_keys=True))
    return 0 if manifest["adapter_decision"]["status"] == "go" else 2


if __name__ == "__main__":
    raise SystemExit(main())
