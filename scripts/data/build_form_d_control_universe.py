#!/usr/bin/env python3
"""Build an auditable, provisional Form D control-identity universe.

The SEC DERA quarterly bulk files are the source of truth for issuer filings.
This producer intentionally stops before Phase 2 matching: Form D reports SIC,
not NAICS, and exact historical-name exclusion cannot prove that a retained
issuer has never received an SBIR award.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sbir_etl.identity import CompanyNameProfile, normalize_company_name


CATALOG_URL = "https://www.sec.gov/data-research/sec-markets-data/form-d-data-sets"
SCHEMA_URL = "https://www.sec.gov/files/Form_D.pdf"
DEFAULT_START_QUARTER = "2009Q1"
DEFAULT_END_QUARTER = "2024Q4"
DEFAULT_OUTPUT_DIR = Path("data/processed/agency_private_capital/control_universe")
DEFAULT_CACHE_DIR = Path("data/cache/sec_form_d")
NORMALIZER = CompanyNameProfile.ORGANIZATION_KEY_V1

TABLE_COLUMNS: dict[str, frozenset[str]] = {
    "FORMDSUBMISSION.tsv": frozenset(
        {
            "ACCESSIONNUMBER",
            "FILING_DATE",
            "SIC_CODE",
            "SUBMISSIONTYPE",
            "TESTORLIVE",
        }
    ),
    "ISSUERS.tsv": frozenset(
        {
            "ACCESSIONNUMBER",
            "IS_PRIMARYISSUER_FLAG",
            "CIK",
            "ENTITYNAME",
            "STATEORCOUNTRY",
            "ZIPCODE",
            "ENTITYTYPE",
            "YEAROFINC_TIMESPAN_CHOICE",
            "YEAROFINC_VALUE_ENTERED",
        }
    ),
    "OFFERING.tsv": frozenset(
        {
            "ACCESSIONNUMBER",
            "INDUSTRYGROUPTYPE",
            "ISAMENDMENT",
            "PREVIOUSACCESSIONNUMBER",
            "SALE_DATE",
            "ISEQUITYTYPE",
            "ISDEBTTYPE",
            "ISOPTIONTOACQUIRETYPE",
            "ISSECURITYTOBEACQUIREDTYPE",
            "ISPOOLEDINVESTMENTFUNDTYPE",
            "ISTENANTINCOMMONTYPE",
            "ISMINERALPROPERTYTYPE",
            "ISOTHERTYPE",
            "ISBUSINESSCOMBINATIONTRANS",
            "TOTALOFFERINGAMOUNT",
            "TOTALAMOUNTSOLD",
            "TOTALREMAINING",
        }
    ),
}

ISSUER_ALIAS_COLUMNS = (
    "ENTITYNAME",
    "ISSUER_PREVIOUSNAME_1",
    "ISSUER_PREVIOUSNAME_2",
    "ISSUER_PREVIOUSNAME_3",
    "EDGAR_PREVIOUSNAME_1",
    "EDGAR_PREVIOUSNAME_2",
    "EDGAR_PREVIOUSNAME_3",
)

SECURITY_COLUMNS = {
    "ISEQUITYTYPE": "equity",
    "ISDEBTTYPE": "debt",
    "ISOPTIONTOACQUIRETYPE": "option_to_acquire",
    "ISSECURITYTOBEACQUIREDTYPE": "security_to_be_acquired",
    "ISPOOLEDINVESTMENTFUNDTYPE": "pooled_investment_fund",
    "ISTENANTINCOMMONTYPE": "tenant_in_common",
    "ISMINERALPROPERTYTYPE": "mineral_property",
    "ISOTHERTYPE": "other",
}

CIK_FIELD_NAMES = frozenset({"cik", "form_d_cik", "sec_cik", "sec_form_d_cik"})
QUARTER_LINK_RE = re.compile(r"(?i)(20\d{2}q[1-4])_d(?:_\d+)?\.zip(?:[?#].*)?$")


class BuildError(RuntimeError):
    """Raised when a source or invariant would make the build incomplete."""


class _CatalogLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.hrefs.append(href)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _quarter_index(value: str) -> int:
    match = re.fullmatch(r"(20\d{2})Q([1-4])", value.upper())
    if not match:
        raise BuildError(f"Invalid quarter {value!r}; expected YYYQn, for example 2024Q4")
    return int(match.group(1)) * 4 + int(match.group(2)) - 1


def quarter_range(start: str, end: str) -> list[str]:
    start_index = _quarter_index(start)
    end_index = _quarter_index(end)
    if start_index > end_index:
        raise BuildError(f"Start quarter {start!r} is after end quarter {end!r}")
    return [f"{index // 4:04d}Q{index % 4 + 1}" for index in range(start_index, end_index + 1)]


def parse_catalog_links(html: bytes, *, base_url: str, expected: Iterable[str]) -> dict[str, str]:
    parser = _CatalogLinks()
    parser.feed(html.decode("utf-8", errors="strict"))
    found: dict[str, str] = {}
    for href in parser.hrefs:
        url = urllib.parse.urljoin(base_url, href)
        match = QUARTER_LINK_RE.search(url)
        if not match:
            continue
        quarter = match.group(1).upper()
        prior = found.get(quarter)
        if prior is not None and prior != url:
            raise BuildError(f"Catalog contains multiple ZIP links for {quarter}: {prior}, {url}")
        found[quarter] = url
    missing = [quarter for quarter in expected if quarter not in found]
    if missing:
        raise BuildError(f"Catalog is missing expected Form D quarters: {', '.join(missing)}")
    return {quarter: found[quarter] for quarter in expected}


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as tmp:
            tmp.write(data)
            temp_path = Path(tmp.name)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def _fetch(url: str, *, user_agent: str) -> bytes:
    if not user_agent.strip():
        raise BuildError(
            "SEC network access requires --sec-user-agent with a project name and contact email"
        )
    request = urllib.request.Request(
        url,
        headers={"User-Agent": user_agent, "Accept": "text/html,application/zip,*/*"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:  # noqa: S310
            return response.read()
    except Exception as exc:  # pragma: no cover - live network path, not exercised in tests
        raise BuildError(f"Failed to fetch {url}: {exc}") from exc


def load_catalog(
    *,
    url: str,
    cache_path: Path,
    user_agent: str,
    refresh: bool = False,
) -> bytes:
    if cache_path.exists() and not refresh:
        return cache_path.read_bytes()
    data = _fetch(url, user_agent=user_agent)
    if b".zip" not in data.lower():
        raise BuildError(f"Catalog response from {url} does not contain Form D ZIP links")
    _atomic_write(cache_path, data)
    return data


def cache_archive(*, quarter: str, url: str, cache_dir: Path, user_agent: str) -> Path:
    path = cache_dir / f"{quarter.lower()}_d.zip"
    if path.exists():
        _validate_zip(path, quarter=quarter)
        return path
    data = _fetch(url, user_agent=user_agent)
    if not data.startswith(b"PK"):
        raise BuildError(f"SEC archive for {quarter} is not a ZIP file")
    _atomic_write(path, data)
    _validate_zip(path, quarter=quarter)
    return path


def _zip_members(archive: zipfile.ZipFile, *, quarter: str) -> dict[str, str]:
    by_name: dict[str, list[str]] = defaultdict(list)
    for member in archive.namelist():
        by_name[Path(member).name.upper()].append(member)
    resolved: dict[str, str] = {}
    for required in TABLE_COLUMNS:
        matches = by_name.get(required.upper(), [])
        if len(matches) != 1:
            raise BuildError(
                f"{quarter} archive must contain exactly one {required}; found {len(matches)}"
            )
        resolved[required] = matches[0]
    return resolved


def _validate_zip(path: Path, *, quarter: str) -> None:
    try:
        with zipfile.ZipFile(path) as archive:
            bad_member = archive.testzip()
            if bad_member:
                raise BuildError(f"{quarter} archive has a corrupt member: {bad_member}")
            _zip_members(archive, quarter=quarter)
    except zipfile.BadZipFile as exc:
        raise BuildError(f"{quarter} archive is not a valid ZIP: {path}") from exc


def _read_tsv(
    archive: zipfile.ZipFile,
    member: str,
    *,
    table_name: str,
    quarter: str,
) -> tuple[list[dict[str, str]], list[str]]:
    with archive.open(member) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8-sig", errors="strict", newline="")
        reader = csv.DictReader(text, delimiter="\t")
        headers = list(reader.fieldnames or [])
        missing = sorted(TABLE_COLUMNS[table_name] - set(headers))
        if missing:
            raise BuildError(f"{quarter} {table_name} schema is missing: {', '.join(missing)}")
        return [dict(row) for row in reader], headers


def normalize_cik(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw or not raw.isdigit():
        return None
    normalized = raw.lstrip("0")
    if not normalized or len(normalized) > 10:
        return None
    return normalized


def parse_date(value: object, *, field: str, accession: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d-%b-%Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise BuildError(f"Unparseable {field} {raw!r} for accession {accession}")


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "t", "yes", "y"}


def _amount(value: object, *, counters: Counter[str]) -> float | None:
    raw = str(value or "").strip().replace(",", "")
    if not raw or raw.lower() in {"n/a", "na", "none", "indefinite"}:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        counters["invalid_amount_values"] += 1
        return None
    if not math.isfinite(parsed) or parsed < 0:
        counters["invalid_amount_values"] += 1
        return None
    return parsed


def _year(value: object, *, counters: Counter[str]) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) == 4 and raw.isdigit():
        return int(raw)
    counters["invalid_year_of_incorporation_values"] += 1
    return None


def _optional_date(
    value: object,
    *,
    field: str,
    accession: str,
    counters: Counter[str],
) -> str | None:
    try:
        return parse_date(value, field=field, accession=accession)
    except BuildError:
        counters["invalid_optional_date_values"] += 1
        return None


def _aliases(row: Mapping[str, str]) -> list[str]:
    values = (str(row.get(column) or "").strip() for column in ISSUER_ALIAS_COLUMNS)
    return sorted(
        {value for value in values if value},
        key=lambda value: (normalize_company_name(value, profile=NORMALIZER), value),
    )


def _first_nonblank(rows: Iterable[Mapping[str, Any]], key: str) -> Any:
    return next((row.get(key) for row in rows if row.get(key)), None)


def parse_quarter(path: Path, *, quarter: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    counters: Counter[str] = Counter()
    with zipfile.ZipFile(path) as archive:
        members = _zip_members(archive, quarter=quarter)
        tables: dict[str, list[dict[str, str]]] = {}
        headers: dict[str, list[str]] = {}
        for table_name, member in members.items():
            tables[table_name], headers[table_name] = _read_tsv(
                archive, member, table_name=table_name, quarter=quarter
            )

    submissions: dict[str, dict[str, str]] = {}
    selected_accessions: set[str] = set()
    for row in tables["FORMDSUBMISSION.tsv"]:
        counters["submission_rows"] += 1
        accession = str(row.get("ACCESSIONNUMBER") or "").strip()
        if not accession:
            raise BuildError(f"{quarter} FORMDSUBMISSION contains an empty accession")
        if accession in submissions:
            raise BuildError(f"{quarter} duplicate submission accession: {accession}")
        submissions[accession] = row
        if str(row.get("TESTORLIVE") or "").strip().upper() != "LIVE":
            counters["test_submissions"] += 1
            continue
        counters["live_submissions"] += 1
        submission_type = str(row.get("SUBMISSIONTYPE") or "").strip().upper()
        if submission_type not in {"D", "D/A"}:
            counters["other_submission_types"] += 1
            continue
        selected_accessions.add(accession)
        counters["selected_submissions"] += 1

    primary_issuers: dict[str, dict[str, str]] = {}
    for row in tables["ISSUERS.tsv"]:
        counters["issuer_rows"] += 1
        accession = str(row.get("ACCESSIONNUMBER") or "").strip()
        if accession not in submissions:
            raise BuildError(f"{quarter} issuer references unknown accession {accession!r}")
        if not _truthy(row.get("IS_PRIMARYISSUER_FLAG")):
            counters["non_primary_issuers"] += 1
            continue
        if accession in primary_issuers:
            raise BuildError(f"{quarter} accession {accession} has multiple primary issuers")
        primary_issuers[accession] = row
        counters["primary_issuers"] += 1

    offerings: dict[str, dict[str, str]] = {}
    for row in tables["OFFERING.tsv"]:
        counters["offering_rows"] += 1
        accession = str(row.get("ACCESSIONNUMBER") or "").strip()
        if accession not in submissions:
            raise BuildError(f"{quarter} offering references unknown accession {accession!r}")
        if accession in offerings:
            raise BuildError(f"{quarter} accession {accession} has multiple offering rows")
        offerings[accession] = row

    missing_issuers = sorted(selected_accessions - primary_issuers.keys())
    missing_offerings = sorted(selected_accessions - offerings.keys())
    if missing_issuers or missing_offerings:
        raise BuildError(
            f"{quarter} broken accession joins: {len(missing_issuers)} missing primary issuer, "
            f"{len(missing_offerings)} missing offering"
        )

    filings: list[dict[str, Any]] = []
    for accession in sorted(selected_accessions):
        submission = submissions[accession]
        issuer = primary_issuers[accession]
        offering = offerings[accession]
        cik = normalize_cik(issuer.get("CIK"))
        if cik is None:
            counters["invalid_cik_filings"] += 1
            continue
        aliases = _aliases(issuer)
        issuer_name = str(issuer.get("ENTITYNAME") or "").strip()
        if not issuer_name or not normalize_company_name(issuer_name, profile=NORMALIZER):
            counters["invalid_issuer_name_filings"] += 1
            continue
        filing_date = parse_date(
            submission.get("FILING_DATE"), field="filing date", accession=accession
        )
        if filing_date is None:
            raise BuildError(f"{quarter} selected accession {accession} has no filing date")
        security_types = sorted(
            label for column, label in SECURITY_COLUMNS.items() if _truthy(offering.get(column))
        )
        sic_code = str(submission.get("SIC_CODE") or "").strip() or None
        sale_date_raw = str(offering.get("SALE_DATE") or "").strip() or None
        offering_amount_raw = str(offering.get("TOTALOFFERINGAMOUNT") or "").strip() or None
        sold_amount_raw = str(offering.get("TOTALAMOUNTSOLD") or "").strip() or None
        remaining_amount_raw = str(offering.get("TOTALREMAINING") or "").strip() or None
        incorporation_year_raw = str(issuer.get("YEAROFINC_VALUE_ENTERED") or "").strip() or None
        filings.append(
            {
                "accession_number": accession,
                "cik": cik,
                "date_of_first_sale": _optional_date(
                    offering.get("SALE_DATE"),
                    field="sale date",
                    accession=accession,
                    counters=counters,
                ),
                "date_of_first_sale_raw": sale_date_raw,
                "entity_type": str(issuer.get("ENTITYTYPE") or "").strip() or None,
                "filing_date": filing_date,
                "industry_group": str(offering.get("INDUSTRYGROUPTYPE") or "").strip() or None,
                "is_amendment": _truthy(offering.get("ISAMENDMENT")),
                "is_business_combination": _truthy(offering.get("ISBUSINESSCOMBINATIONTRANS")),
                "issuer_name": issuer_name,
                "issuer_name_aliases": aliases,
                "previous_accession_number": str(
                    offering.get("PREVIOUSACCESSIONNUMBER") or ""
                ).strip()
                or None,
                "security_types": security_types,
                "sic2": sic_code[:2] if sic_code and len(sic_code) >= 2 else None,
                "sic_code": sic_code,
                "source_quarter": quarter,
                "state": str(issuer.get("STATEORCOUNTRY") or "").strip().upper() or None,
                "submission_type": str(submission.get("SUBMISSIONTYPE") or "").strip().upper(),
                "total_amount_sold": _amount(offering.get("TOTALAMOUNTSOLD"), counters=counters),
                "total_amount_sold_raw": sold_amount_raw,
                "total_offering_amount": _amount(
                    offering.get("TOTALOFFERINGAMOUNT"), counters=counters
                ),
                "total_offering_amount_raw": offering_amount_raw,
                "total_remaining": _amount(offering.get("TOTALREMAINING"), counters=counters),
                "total_remaining_raw": remaining_amount_raw,
                "year_of_incorporation": _year(
                    issuer.get("YEAROFINC_VALUE_ENTERED"), counters=counters
                ),
                "year_of_incorporation_basis": str(
                    issuer.get("YEAROFINC_TIMESPAN_CHOICE") or ""
                ).strip()
                or None,
                "year_of_incorporation_raw": incorporation_year_raw,
                "zip_code": str(issuer.get("ZIPCODE") or "").strip() or None,
            }
        )
        counters["emitted_filings"] += 1

    metadata = {
        "archive": {
            "sha256": sha256_path(path),
            "size_bytes": path.stat().st_size,
            "zip_members": sorted(members.values()),
        },
        "counters": dict(sorted(counters.items())),
        "headers": dict(sorted(headers.items())),
        "table_rows": {key: len(value) for key, value in sorted(tables.items())},
    }
    return filings, metadata


def aggregate_issuers(filings: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for filing in filings:
        grouped[str(filing["cik"])].append(filing)

    issuers: list[dict[str, Any]] = []
    for cik, cik_filings in grouped.items():
        ordered = sorted(
            cik_filings, key=lambda row: (str(row["filing_date"]), str(row["accession_number"]))
        )
        names = Counter(str(row["issuer_name"]) for row in ordered)
        max_count = max(names.values())
        canonical_name = min(
            (name for name, count in names.items() if count == max_count),
            key=lambda value: (normalize_company_name(value, profile=NORMALIZER), value),
        )
        aliases = sorted(
            {
                alias
                for row in ordered
                for alias in [str(row["issuer_name"]), *row["issuer_name_aliases"]]
                if alias
            },
            key=lambda value: (normalize_company_name(value, profile=NORMALIZER), value),
        )
        first = ordered[0]
        issuers.append(
            {
                "cik": cik,
                "filing_count": len(ordered),
                "filings": ordered,
                "firm_key": f"form_d_cik:{cik}",
                "first_accession_number": first["accession_number"],
                "first_filing_date": first["filing_date"],
                "first_filing_year": int(str(first["filing_date"])[:4]),
                "industry_group": _first_nonblank(ordered, "industry_group"),
                "issuer_name": canonical_name,
                "issuer_name_aliases": aliases,
                "last_filing_date": ordered[-1]["filing_date"],
                "schema_version": 1,
                "sic2": _first_nonblank(ordered, "sic2"),
                "sic_code": _first_nonblank(ordered, "sic_code"),
                "state": _first_nonblank(ordered, "state"),
            }
        )
    return sorted(issuers, key=lambda row: str(row["cik"]))


def _read_award_names(path: Path) -> tuple[dict[str, set[str]], int]:
    if not path.is_file():
        raise BuildError(f"Required full-history SBIR awards CSV is missing: {path}")
    names: dict[str, set[str]] = defaultdict(set)
    row_count = 0
    with path.open(encoding="utf-8-sig", errors="replace", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = {column.lower(): column for column in (reader.fieldnames or [])}
        name_column = columns.get("company") or columns.get("company_name")
        if name_column is None:
            raise BuildError(f"SBIR awards CSV {path} has no Company/company_name column")
        for row in reader:
            row_count += 1
            raw_name = str(row.get(name_column) or "").strip()
            normalized = normalize_company_name(raw_name, profile=NORMALIZER)
            if normalized:
                names[normalized].add(raw_name)
    return names, row_count


def _walk_ciks(value: Any, *, pointer: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(value, Mapping):
        for raw_key, nested in value.items():
            key = str(raw_key)
            child_pointer = f"{pointer}/{key}"
            if key.lower() in CIK_FIELD_NAMES:
                cik = normalize_cik(nested)
                if cik:
                    yield cik, child_pointer
            if isinstance(nested, (Mapping, list)):
                yield from _walk_ciks(nested, pointer=child_pointer)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            yield from _walk_ciks(nested, pointer=f"{pointer}/{index}")


def _explicit_cik_evidence(
    paths: Iterable[Path],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_cik: dict[str, list[dict[str, Any]]] = defaultdict(list)
    inputs: list[dict[str, Any]] = []
    for path in paths:
        if not path.is_file():
            raise BuildError(f"Explicit SBIR-CIK evidence input is missing: {path}")
        row_count = 0
        occurrence_count = 0
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                row_count += 1
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BuildError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc
                if not isinstance(record, Mapping):
                    raise BuildError(
                        f"SBIR-CIK evidence row {path}:{line_number} must be a JSON object"
                    )
                for cik, pointer in _walk_ciks(record):
                    occurrence_count += 1
                    by_cik[cik].append(
                        {
                            "json_pointer": pointer,
                            "resolution_method": "explicit_cik_evidence",
                            "source_artifact": path.name,
                            "source_line": line_number,
                        }
                    )
        inputs.append(
            {
                "cik_occurrences": occurrence_count,
                "path": path.name,
                "row_count": row_count,
                "sha256": sha256_path(path),
                "size_bytes": path.stat().st_size,
            }
        )
    return by_cik, inputs


def build_exclusions(
    issuers: list[dict[str, Any]],
    *,
    awards_csv: Path,
    explicit_evidence_paths: Iterable[Path] = (),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    award_names, award_rows = _read_award_names(awards_csv)
    issuer_names: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for issuer in issuers:
        cik = str(issuer["cik"])
        for raw_name in issuer["issuer_name_aliases"]:
            normalized = normalize_company_name(raw_name, profile=NORMALIZER)
            if normalized:
                issuer_names[normalized][cik].add(raw_name)

    evidence_by_cik, explicit_inputs = _explicit_cik_evidence(explicit_evidence_paths)
    exact_normalized_names = sorted(set(award_names) & set(issuer_names))
    for normalized in exact_normalized_names:
        cik_map = issuer_names[normalized]
        for cik in sorted(cik_map):
            evidence_by_cik[cik].append(
                {
                    "issuer_cik_count_for_normalized_name": len(cik_map),
                    "issuer_names": sorted(cik_map[cik]),
                    "normalized_name": normalized,
                    "normalizer_version": NORMALIZER.value,
                    "resolution_method": "candidate_exact_normalized_name",
                    "sbir_company_names": sorted(award_names[normalized]),
                    "sbir_raw_name_count": len(award_names[normalized]),
                    "source_artifact": awards_csv.name,
                }
            )

    exclusions: list[dict[str, Any]] = []
    for cik in sorted(evidence_by_cik):
        evidence = sorted(
            evidence_by_cik[cik],
            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
        )
        exclusions.append(
            {
                "candidate_exclusion": True,
                "cik": cik,
                "evidence": evidence,
                "evidence_count": len(evidence),
                "firm_key": f"form_d_cik:{cik}",
                "resolution_methods": sorted({str(item["resolution_method"]) for item in evidence}),
                "schema_version": 1,
            }
        )

    metadata = {
        "awards_csv": {
            "path": awards_csv.name,
            "row_count": award_rows,
            "sha256": sha256_path(awards_csv),
            "size_bytes": awards_csv.stat().st_size,
            "unique_normalized_company_names": len(award_names),
        },
        "exact_match": {
            "candidate_cik_count": sum(
                1
                for row in exclusions
                if "candidate_exact_normalized_name" in row["resolution_methods"]
            ),
            "matched_normalized_name_count": len(exact_normalized_names),
            "normalizer_version": NORMALIZER.value,
            "normalized_names_mapping_to_multiple_ciks": sum(
                1 for name in exact_normalized_names if len(issuer_names[name]) > 1
            ),
        },
        "explicit_cik_inputs": explicit_inputs,
    }
    return exclusions, metadata


def _write_product(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    size_bytes = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as tmp:
            temp_path = Path(tmp.name)
            for row in rows:
                data = (
                    json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
                    + "\n"
                ).encode("utf-8")
                tmp.write(data)
                digest.update(data)
                size_bytes += len(data)
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return {
        "path": path.name,
        "row_count": len(rows),
        "sha256": digest.hexdigest(),
        "size_bytes": size_bytes,
    }


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def build(args: argparse.Namespace) -> dict[str, Any]:
    quarters = quarter_range(args.start_quarter, args.end_quarter)
    output_dir = Path(args.output_dir)
    cache_dir = Path(args.cache_dir)
    catalog_cache = Path(args.catalog_cache) if args.catalog_cache else cache_dir / "catalog.html"
    catalog = load_catalog(
        url=args.catalog_url,
        cache_path=catalog_cache,
        user_agent=args.sec_user_agent,
        refresh=args.refresh_catalog,
    )
    links = parse_catalog_links(catalog, base_url=args.catalog_url, expected=quarters)

    all_filings: list[dict[str, Any]] = []
    quarter_metadata: dict[str, Any] = {}
    for quarter in quarters:
        path = cache_archive(
            quarter=quarter,
            url=links[quarter],
            cache_dir=cache_dir,
            user_agent=args.sec_user_agent,
        )
        filings, metadata = parse_quarter(path, quarter=quarter)
        metadata["url"] = links[quarter]
        quarter_metadata[quarter] = metadata
        all_filings.extend(filings)

    accessions = [str(row["accession_number"]) for row in all_filings]
    if len(accessions) != len(set(accessions)):
        raise BuildError("A filing accession appears in more than one selected quarter")
    issuers = aggregate_issuers(all_filings)
    exclusions, exclusion_metadata = build_exclusions(
        issuers,
        awards_csv=Path(args.awards_csv),
        explicit_evidence_paths=[Path(path) for path in args.cik_evidence_jsonl],
    )
    exclusion_ciks = {str(row["cik"]) for row in exclusions}
    broad_ciks = {str(row["cik"]) for row in issuers}
    controls = [row for row in issuers if str(row["cik"]) not in exclusion_ciks]
    control_ciks = {str(row["cik"]) for row in controls}
    excluded_broad_ciks = broad_ciks & exclusion_ciks
    ready_for_matching = False

    invariants = {
        "broad_ciks_unique": len(broad_ciks) == len(issuers),
        "broad_equals_retained_plus_excluded_intersection": len(issuers)
        == len(controls) + len(excluded_broad_ciks),
        "control_ciks_unique": len(control_ciks) == len(controls),
        "control_exclusion_overlap_count": len(control_ciks & exclusion_ciks),
        "exclusion_ciks_unique": len(exclusion_ciks) == len(exclusions),
        "ready_for_matching_is_false": ready_for_matching is False,
    }
    if not all(value is True or value == 0 for value in invariants.values()):
        raise BuildError(f"Control-universe invariant failed: {invariants}")

    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = {
        "broad_issuer_universe": _write_product(
            output_dir / "form_d_issuer_universe.identity-staging.jsonl", issuers
        ),
        "candidate_sbir_cik_exclusions": _write_product(
            output_dir / "sbir_cik_exclusion_candidates.identity-staging.jsonl", exclusions
        ),
        "provisional_control_identity_universe": _write_product(
            output_dir / "form_d_control_identity_universe.provisional.jsonl", controls
        ),
    }
    quality_counts: Counter[str] = Counter()
    for metadata in quarter_metadata.values():
        quality_counts.update(metadata["counters"])
    manifest = {
        "caveats": [
            "Exact normalized-name exclusion has unknown recall.",
            "Aliases, renames, spelling variation, acquisitions, and unmatched CIKs can remain.",
            "A retained issuer means only not exact-name-matched to the observed SBIR history.",
            "SEC Form D supplies SIC and industry group, not NAICS.",
        ],
        "code_commit": args.code_version or _git_commit(),
        "complete": True,
        "complete_sbir_exclusion": False,
        "covariates_ready": False,
        "exclusion": exclusion_metadata,
        "exclusion_recall": "unknown",
        "identity_only": True,
        "inputs": {
            "catalog": {
                "sha256": sha256_bytes(catalog),
                "size_bytes": len(catalog),
                "url": args.catalog_url,
            },
            "quarters": quarter_metadata,
            "schema_document_url": SCHEMA_URL,
        },
        "invariants": invariants,
        "outputs": outputs,
        "parameters": {
            "end_quarter": args.end_quarter.upper(),
            "quarter_count": len(quarters),
            "quarters": quarters,
            "start_quarter": args.start_quarter.upper(),
            "structural_filters": ["LIVE", "D_or_D/A", "primary_issuer", "valid_CIK"],
        },
        "quality_counts": dict(sorted(quality_counts.items())),
        "ready_for_matching": ready_for_matching,
        "retained_definition": "not exact-name-matched to the observed SBIR award history",
        "schema_version": 1,
        "source_counts": {
            "excluded_broad_ciks": len(excluded_broad_ciks),
            "filings": len(all_filings),
            "issuer_ciks": len(issuers),
            "provisional_control_ciks": len(controls),
        },
    }
    manifest_data = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    _atomic_write(output_dir / "form_d_control_universe.manifest.json", manifest_data)
    return manifest


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-quarter", default=DEFAULT_START_QUARTER)
    parser.add_argument("--end-quarter", default=DEFAULT_END_QUARTER)
    parser.add_argument("--catalog-url", default=CATALOG_URL)
    parser.add_argument("--catalog-cache")
    parser.add_argument("--refresh-catalog", action="store_true")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--awards-csv", type=Path, default=Path("data/raw/sbir/award_data.csv"))
    parser.add_argument(
        "--cik-evidence-jsonl",
        action="append",
        default=[],
        help="Optional explicit SBIR-CIK evidence JSONL; may be supplied more than once",
    )
    parser.add_argument(
        "--sec-user-agent",
        default=os.environ.get("SBIR_SEC_USER_AGENT", ""),
        help="SEC-compliant project/contact User-Agent (or SBIR_SEC_USER_AGENT)",
    )
    parser.add_argument("--code-version", help="Pinned producer commit for the manifest")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        manifest = build(parse_args(argv))
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"outputs": manifest["outputs"], "source_counts": manifest["source_counts"]}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
