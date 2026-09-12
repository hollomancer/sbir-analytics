#!/usr/bin/env python3
"""Build an exploratory SBIR-firm view of SBA's defense-critical NAICS codes.

Epistemic tier: exploratory (non-citable).

The analysis keeps four observables separate:

* a current, active SAM.gov registration that lists a target NAICS code;
* any target-coded federal prime action awarded to an exact-UEI SBIR entity;
* a positive-obligation, non-Phase-I/II-classified target action after the
  entity's first usable recorded Phase II end date;
* a first qualifying target-origin prime award after a clean pre-index archive
  coverage window; and
* a literal first-observed target entry that also satisfies that qualifying
  target-origin-award definition.

An identity-review component separately flags low name continuity within exact
UEI matches, joins evidence-backed corporate-history annotations, and records
whether dollar attribution requires a temporal split or remains unresolved.

The transition observables are not proof that the entity changed industries,
that SBIR caused the change, or that a contract is statutory Phase III. Frozen
USAspending transaction archives begin in FY2009, so all transition-style
findings are public-procurement lower bounds with left censoring.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_etl.extractors.sbir_public_awards import load_sbir_awards_csv
from sbir_etl.identity import (
    CompanyNameMetric,
    CompanyNameProfile,
    company_name_similarity,
    normalize_company_name,
)
from sbir_etl.utils.identifiers import normalize_uei
from sbir_etl.validators.sbir_awards import validate_sbir_awards


EPISTEMIC_TIER = "exploratory"
DEFAULT_IDENTITY_CROSSWALK = (
    Path(__file__).resolve().parents[2]
    / "data/reference/defense_critical_naics_identity_crosswalk.csv"
)
ARCHIVE_COVERAGE_START = date(2008, 10, 1)
CLEAN_PRE_INDEX_COVERAGE_YEARS = 3
NAME_CONTINUITY_THRESHOLD = 0.90
IDENTITY_REVIEW_TOP_DOLLAR_ENTITIES = 10
CONTRACT_TYPES = ["A", "B", "C", "D"]
PHASE_I_II_RESEARCH_CODES = {"SR1", "SR2", "ST1", "ST2"}
PHASE_III_RESEARCH_CODES = {"SR3", "ST3"}
RESEARCH_CODES = PHASE_I_II_RESEARCH_CODES | PHASE_III_RESEARCH_CODES

TARGET_NAICS = {
    "332992": "Small Arms Ammunition Manufacturing",
    "332993": "Ammunition (except Small Arms) Manufacturing",
    "336414": "Guided Missile and Space Vehicle Manufacturing",
    "336413": "Other Aircraft Parts and Auxiliary Equipment Manufacturing",
    "334511": (
        "Search, Detection, Navigation, Guidance, Aeronautical, and Nautical "
        "System and Instrument Manufacturing"
    ),
    "334419": "Other Electronic Component Manufacturing",
    "331110": "Iron and Steel Mills and Ferroalloy Manufacturing",
    "332710": "Machine Shops",
    "332999": "All Other Miscellaneous Fabricated Metal Product Manufacturing",
    "336611": "Ship Building and Repairing",
}

IDENTITY_CROSSWALK_COLUMNS = [
    "firm_uei",
    "sbir_name_key",
    "contract_name_key",
    "sbir_display_name",
    "contract_recipient_name",
    "entity_same_firm",
    "corporate_relation",
    "corporate_event_date",
    "corporate_event_date_basis",
    "successor_or_acquirer_name",
    "contract_relationship",
    "attribution_treatment",
    "review_confidence",
    "evidence_source",
    "evidence_locator",
    "secondary_evidence_locator",
    "reviewer",
    "reviewed_at",
    "review_notes",
]
IDENTITY_SAME_FIRM_VALUES = {"Y", "N", "unsure"}
IDENTITY_RELATION_VALUES = {
    "name_change",
    "merger",
    "acquisition",
    "operating_subsidiary",
    "spin_off",
    "uei_reuse_or_collision",
    "other",
    "unknown",
}
IDENTITY_CONTRACT_RELATION_VALUES = {
    "novation_confirmed",
    "change_of_name_confirmed",
    "not_established",
    "unresolved",
}
IDENTITY_ATTRIBUTION_VALUES = {
    "same_entity_continuity",
    "temporal_split_required",
    "unresolved_exclude_from_original_firm_claims",
}
IDENTITY_DATE_BASIS_VALUES = {"announced", "closed", "effective", "unknown"}
IDENTITY_CONFIDENCE_VALUES = {"H", "M", "L"}

PHASE_I_II_TEXT = re.compile(
    r"(?:\b(?:SBIR|STTR|SMALL BUSINESS INNOVATION RESEARCH|"
    r"SMALL BUSINESS TECHNOLOGY TRANSFER)\b.{0,80}?\bPHASE\s*(?:I|II|1|2)\b|"
    r"\bPHASE\s*(?:I|II|1|2)\b.{0,80}?\b(?:SBIR|STTR|"
    r"SMALL BUSINESS INNOVATION RESEARCH|SMALL BUSINESS TECHNOLOGY TRANSFER)\b)",
    flags=re.IGNORECASE,
)
PHASE_III_TEXT = re.compile(
    r"(?:\b(?:SBIR|STTR|SMALL BUSINESS INNOVATION RESEARCH|"
    r"SMALL BUSINESS TECHNOLOGY TRANSFER)\b.{0,80}?\bPHASE\s*(?:III|3)\b|"
    r"\bPHASE\s*(?:III|3)\b.{0,80}?\b(?:SBIR|STTR|"
    r"SMALL BUSINESS INNOVATION RESEARCH|SMALL BUSINESS TECHNOLOGY TRANSFER)\b)",
    flags=re.IGNORECASE,
)

RESEARCH_PHASE = re.compile(r"\bPHASE\s*(III|II|I|3|2|1)\b", flags=re.IGNORECASE)


def _normalize_research_code(value: Any) -> str:
    """Normalize FPDS compact and verbose SBIR/STTR research labels.

    Older archive rows generally use SR1/ST2-style codes.  Current rows can
    instead contain full program labels such as ``SMALL TECHNOLOGY TRANSFER
    RESEARCH PROGRAM PHASE II``.  Treat both representations identically and
    leave blank values blank so genuinely unclassified awards stay distinct.
    """

    if value is None or pd.isna(value):
        return ""
    label = re.sub(r"\s+", " ", str(value).upper()).strip()
    if not label:
        return ""
    if label in RESEARCH_CODES:
        return label

    if "TECHNOLOGY TRANSFER" in label or re.search(r"\bSTTR\b", label):
        program = "ST"
    elif "BUSINESS INNOVATION RESEARCH" in label or re.search(r"\bSBIR\b", label):
        program = "SR"
    else:
        return ""

    phase_match = RESEARCH_PHASE.search(label)
    if phase_match is None:
        return ""
    phase = {"I": "1", "II": "2", "III": "3"}.get(
        phase_match.group(1).upper(), phase_match.group(1)
    )
    return f"{program}{phase}"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical_json(payload))
    temporary.replace(path)


def _clean_award_id(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    cleaned = re.sub(r"[^A-Z0-9]", "", str(value).upper())
    return cleaned if len(cleaned) >= 4 else ""


def _first_nonblank(values: pd.Series) -> str:
    usable = values.dropna().astype(str).str.strip()
    usable = usable[usable.ne("")]
    return usable.iloc[-1] if not usable.empty else ""


@dataclass(frozen=True)
class SbirCohort:
    awards: pd.DataFrame
    firms: pd.DataFrame
    source_audit: dict[str, Any]
    known_sbir_contracts: set[tuple[str, str]]


def load_sbir_cohort(path: Path, cutoff: date) -> SbirCohort:
    """Load the official CSV through the canonical versioned award identity."""

    raw = load_sbir_awards_csv(path)
    source_row_count = int(raw["source_edition_count"].sum())
    canonical_row_count = len(raw)
    awards = raw.rename(
        columns={
            "company": "company_name",
            "contract_number": "contract",
            "recorded_end_date": "contract_end_date",
            "amount": "award_amount",
        }
    ).copy()
    awards["company_name"] = awards["company_name"].replace(r"^\s*$", pd.NA, regex=True)
    awards["award_amount"] = pd.to_numeric(awards["award_amount"], errors="coerce")
    awards["award_date"] = pd.to_datetime(awards["award_date"], errors="coerce")
    awards["contract_end_date"] = pd.to_datetime(awards["contract_end_date"], errors="coerce")
    quality = validate_sbir_awards(awards, pass_rate_threshold=0.0)
    awards = awards.loc[~awards.index.isin(quality.failing_row_indices)].copy()
    awards["firm_uei"] = awards["uei"].map(normalize_uei)
    awards["state"] = ""

    cutoff_ts = pd.Timestamp(cutoff)
    end_year = awards["contract_end_date"].dt.year.astype("Int64")
    plausible_end = (
        awards["contract_end_date"].between(pd.Timestamp("1983-01-01"), cutoff_ts)
        & awards["award_year"].notna()
        & end_year.ge(awards["award_year"] - 1)
        & end_year.le(awards["award_year"] + 10)
        & (awards["award_date"].isna() | awards["contract_end_date"].ge(awards["award_date"]))
    )
    awards["usable_phase_ii_end"] = awards["contract_end_date"].where(
        awards["phase"].eq("Phase II") & plausible_end
    )

    normalized_labels = awards["company_name"].map(
        lambda value: normalize_company_name(value, profile=CompanyNameProfile.MATCHING_V1)
        if pd.notna(value)
        else None
    )
    exact = awards.loc[awards["firm_uei"].notna()].copy()
    exact = exact.sort_values(["award_year", "award_date"], na_position="first")
    exact["is_phase_i"] = exact["phase"].eq("Phase I").astype(int)
    exact["is_phase_ii"] = exact["phase"].eq("Phase II").astype(int)
    exact["phase_i_dollars"] = exact["award_amount"].where(exact["is_phase_i"].eq(1), 0.0)
    exact["phase_ii_dollars"] = exact["award_amount"].where(exact["is_phase_ii"].eq(1), 0.0)

    recent = exact.drop_duplicates("firm_uei", keep="last").set_index("firm_uei")
    grouped = exact.groupby("firm_uei", sort=True)
    firms = grouped.agg(
        first_sbir_year=("award_year", "min"),
        last_sbir_year=("award_year", "max"),
        sbir_awards=("award_key", "nunique"),
        phase_i_awards=("is_phase_i", "sum"),
        phase_ii_awards=("is_phase_ii", "sum"),
        sbir_dollars=("award_amount", "sum"),
        phase_i_dollars=("phase_i_dollars", "sum"),
        phase_ii_dollars=("phase_ii_dollars", "sum"),
        first_phase_ii_end=("usable_phase_ii_end", "min"),
    )
    firms["display_name"] = recent["company_name"]
    firms["state"] = recent["state"].fillna("")
    firms = firms.reset_index()

    identifiers = pd.concat(
        [
            exact[["firm_uei", "contract"]].rename(columns={"contract": "source_id"}),
            exact[["firm_uei", "agency_tracking_number"]].rename(
                columns={"agency_tracking_number": "source_id"}
            ),
            exact[["firm_uei", "award_id"]].rename(columns={"award_id": "source_id"}),
        ],
        ignore_index=True,
    )
    identifiers["normalized_id"] = identifiers["source_id"].map(_clean_award_id)
    known_contracts = {
        (row.firm_uei, row.normalized_id)
        for row in identifiers.itertuples(index=False)
        if row.normalized_id
    }

    audit = {
        "source_rows": source_row_count,
        "canonical_award_rows": canonical_row_count,
        "source_editions_collapsed": source_row_count - canonical_row_count,
        "validated_award_rows": len(awards),
        "award_key_version": str(awards["award_key_version"].iloc[0]),
        "validation_failed_rows": len(quality.failing_row_indices),
        "source_company_labels": int(normalized_labels.dropna().nunique()),
        "rows_with_valid_uei": int(awards["firm_uei"].notna().sum()),
        "exact_uei_firms": int(len(firms)),
        "phase_ii_exact_uei_firms": int(firms["phase_ii_awards"].gt(0).sum()),
        "phase_ii_exact_uei_firms_with_usable_end": int(firms["first_phase_ii_end"].notna().sum()),
        "phase_ii_rows_with_unusable_end": int(
            (awards["phase"].eq("Phase II") & awards["usable_phase_ii_end"].isna()).sum()
        ),
        "phase_ii_rows_with_end_before_award_date": int(
            (
                awards["phase"].eq("Phase II")
                & awards["contract_end_date"].notna()
                & awards["award_date"].notna()
                & awards["contract_end_date"].lt(awards["award_date"])
            ).sum()
        ),
    }
    return SbirCohort(
        awards=awards,
        firms=firms,
        source_audit=audit,
        known_sbir_contracts=known_contracts,
    )


@dataclass(frozen=True)
class SamResult:
    evidence: pd.DataFrame
    audit: dict[str, Any]


def _parse_naics_list(primary: str, raw_codes: str) -> set[str]:
    codes = set(re.findall(r"(?<!\d)(\d{6})(?!\d)", raw_codes or ""))
    primary = str(primary or "").strip()
    if re.fullmatch(r"\d{6}", primary):
        codes.add(primary)
    return codes


def _parse_sba_certifications(raw_codes: str) -> tuple[bool, bool, str]:
    tokens = [token.strip() for token in str(raw_codes or "").split("~") if token.strip()]
    eight_a_dates = sorted(token[2:10] for token in tokens if re.fullmatch(r"A6\d{8}", token))
    has_eight_a = any(token == "A6" or token.startswith("A6") for token in tokens)
    has_eight_a_joint_venture = any(token == "JT" or token.startswith("JT") for token in tokens)
    return has_eight_a, has_eight_a_joint_venture, ";".join(eight_a_dates)


def load_sam_target_evidence(path: Path, sbir_ueis: set[str]) -> SamResult:
    """Read Public V2 rows, repairing its NUL-delimited quoted free text.

    The 2026-09-07 extract uses NUL characters as quote delimiters around some
    free-text values containing literal pipes.  ``QUOTE_NONE`` therefore makes
    305 valid records appear wider than the pinned 142-field schema.  Replace
    NUL with a collision-checked private-use quote character before parsing.
    """

    raw_pipe_field_counts: Counter[int] = Counter()
    repaired_field_counts: Counter[int] = Counter()
    records: list[dict[str, Any]] = []
    matched_sbir_ueis: set[str] = set()
    matched_active_sbir_ueis: set[str] = set()
    repaired_quoted_pipe_rows = 0
    header = ""
    trailer = ""
    declared_rows: int | None = None
    data_rows = 0

    with zipfile.ZipFile(path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir()]
        if len(members) != 1 or not members[0].filename.lower().endswith(".dat"):
            raise ValueError("SAM Public V2 ZIP must contain exactly one DAT member")
        with archive.open(members[0]) as raw_stream:
            text_stream = io.TextIOWrapper(raw_stream, encoding="utf-8-sig", newline="")
            sentinel = "\ue000"

            def repaired_lines():
                nonlocal repaired_quoted_pipe_rows
                for raw_line in text_stream:
                    if sentinel in raw_line:
                        raise ValueError("SAM Public V2 collides with the repair sentinel")
                    raw_pipe_field_counts[raw_line.count("|") + 1] += 1
                    if "\x00" in raw_line:
                        repaired_quoted_pipe_rows += 1
                    yield raw_line.replace("\x00", sentinel)

            reader = csv.reader(repaired_lines(), delimiter="|", quotechar=sentinel, strict=True)
            header_row = next(reader)
            if len(header_row) != 1:
                raise ValueError("SAM Public V2 BOF record has unexpected delimiters")
            header = header_row[0]
            match = re.fullmatch(
                r"BOF PUBLIC V2 \d{8} (?P<source_date>\d{8}) "
                r"(?P<row_count>\d{7}) \d{7}",
                header,
            )
            if match is None:
                raise ValueError("SAM Public V2 has an invalid BOF record")
            declared_rows = int(match.group("row_count"))
            source_date = match.group("source_date")

            for row in reader:
                repaired_field_counts[len(row)] += 1
                if len(row) == 1 and row[0].startswith("EOF PUBLIC V2 "):
                    if trailer:
                        raise ValueError("SAM Public V2 has multiple EOF records")
                    trailer = row[0]
                    continue
                if trailer:
                    raise ValueError("SAM Public V2 has data after its EOF record")
                data_rows += 1
                if len(row) != 142:
                    raise ValueError(f"SAM repaired row has {len(row)} fields, expected 142")
                if row[141] != "!end":
                    raise ValueError("SAM strict-width row lacks the end marker")
                uei = normalize_uei(row[0])
                status = row[5].strip()
                legal_name = row[11].strip()
                if uei is None or status not in {"A", "E"} or not legal_name:
                    raise ValueError("SAM strict-width row failed identity validation")
                if uei not in sbir_ueis:
                    continue
                matched_sbir_ueis.add(uei)
                if status == "A":
                    matched_active_sbir_ueis.add(uei)
                primary = row[32].strip()
                all_codes = _parse_naics_list(primary, row[34])
                target_codes = sorted(all_codes & TARGET_NAICS.keys())
                if target_codes:
                    has_8a_history, is_8a_joint_venture, eight_a_exit_dates = (
                        _parse_sba_certifications(row[117])
                    )
                    current_8a = any(
                        exit_date >= source_date
                        for exit_date in eight_a_exit_dates.split(";")
                        if exit_date
                    )
                    records.append(
                        {
                            "firm_uei": uei,
                            "registration_status": status,
                            "legal_business_name": legal_name,
                            "primary_naics": primary,
                            "primary_target_codes": primary if primary in TARGET_NAICS else "",
                            "target_codes": ";".join(target_codes),
                            "target_code_count": len(target_codes),
                            "has_primary_target": primary in TARGET_NAICS,
                            "has_any_target": True,
                            "sba_business_types": row[117].strip(),
                            "sam_8a_history_indicator": has_8a_history,
                            "sam_current_8a_indicator": current_8a,
                            "sam_8a_joint_venture_indicator": is_8a_joint_venture,
                            "sam_8a_exit_dates": eight_a_exit_dates,
                        }
                    )

    if declared_rows != data_rows:
        raise ValueError(
            f"SAM row count mismatch: declared {declared_rows:,}, observed {data_rows:,}"
        )
    if trailer != f"EOF{header[3:]}":
        raise ValueError("SAM Public V2 EOF record does not match its BOF record")

    evidence = pd.DataFrame.from_records(records)
    if evidence.empty:
        evidence = pd.DataFrame(
            columns=[
                "firm_uei",
                "registration_status",
                "legal_business_name",
                "primary_naics",
                "primary_target_codes",
                "target_codes",
                "target_code_count",
                "has_primary_target",
                "has_any_target",
                "sba_business_types",
                "sam_8a_history_indicator",
                "sam_current_8a_indicator",
                "sam_8a_joint_venture_indicator",
                "sam_8a_exit_dates",
            ]
        )
    if not evidence.empty:
        evidence = (
            evidence.groupby(["firm_uei", "registration_status"], as_index=False)
            .agg(
                legal_business_name=("legal_business_name", _first_nonblank),
                primary_naics=(
                    "primary_naics",
                    lambda values: ";".join(sorted({v for v in values if v})),
                ),
                primary_target_codes=(
                    "primary_target_codes",
                    lambda values: ";".join(sorted({v for v in values if v})),
                ),
                target_codes=(
                    "target_codes",
                    lambda values: ";".join(
                        sorted({code for value in values for code in str(value).split(";") if code})
                    ),
                ),
                target_code_count=(
                    "target_codes",
                    lambda values: len(
                        {code for value in values for code in str(value).split(";") if code}
                    ),
                ),
                has_primary_target=("has_primary_target", "max"),
                has_any_target=("has_any_target", "max"),
                sba_business_types=(
                    "sba_business_types",
                    lambda values: ";".join(sorted({v for v in values if v})),
                ),
                sam_8a_history_indicator=("sam_8a_history_indicator", "max"),
                sam_current_8a_indicator=("sam_current_8a_indicator", "max"),
                sam_8a_joint_venture_indicator=(
                    "sam_8a_joint_venture_indicator",
                    "max",
                ),
                sam_8a_exit_dates=(
                    "sam_8a_exit_dates",
                    lambda values: ";".join(
                        sorted({item for value in values for item in str(value).split(";") if item})
                    ),
                ),
            )
            .sort_values(["firm_uei", "registration_status"])
        )
    audit = {
        "source_file": path.name,
        "source_date": source_date,
        "sha256": _sha256(path),
        "declared_rows": declared_rows,
        "observed_rows": data_rows,
        "raw_pipe_field_counts": {
            str(key): value for key, value in sorted(raw_pipe_field_counts.items())
        },
        "repaired_field_counts": {
            str(key): value for key, value in sorted(repaired_field_counts.items())
        },
        "nul_quoted_pipe_rows_repaired": repaired_quoted_pipe_rows,
        "exact_uei_sbir_firms_in_sam": len(matched_sbir_ueis),
        "exact_uei_sbir_firms_in_active_sam": len(matched_active_sbir_ueis),
        "target_sbir_firms_any_status": int(evidence["firm_uei"].nunique()),
        "target_sbir_firms_active": int(
            evidence.loc[evidence["registration_status"].eq("A"), "firm_uei"].nunique()
        ),
        "target_sbir_firms_active_with_8a_history_indicator": int(
            evidence.loc[
                evidence["registration_status"].eq("A") & evidence["sam_8a_history_indicator"],
                "firm_uei",
            ].nunique()
        ),
        "target_sbir_firms_active_with_current_8a_indicator": int(
            evidence.loc[
                evidence["registration_status"].eq("A") & evidence["sam_current_8a_indicator"],
                "firm_uei",
            ].nunique()
        ),
    }
    return SamResult(evidence=evidence, audit=audit)


@dataclass(frozen=True)
class HistoricalContractResult:
    evidence: pd.DataFrame
    audit: dict[str, Any]
    coverage_end: pd.Timestamp


def load_historical_contract_evidence(
    path: Path,
    cohort: SbirCohort,
) -> HistoricalContractResult:
    """Roll a target-transaction ledger up to entity x award x target code.

    The input is produced from frozen USAspending contract archives.  It has
    already been exact-UEI filtered but remains transaction-grained, preserving
    modifications and signed obligations.  Target-code membership stays at the
    transaction grain; target-origin status requires an observed base action.
    """

    required = {
        "firm_uei",
        "vendor_name",
        "contract_id",
        "piid",
        "transaction_unique_id",
        "generated_unique_award_id",
        "award_group_key",
        "agency",
        "sub_agency",
        "action_date",
        "start_date",
        "end_date",
        "award_first_action_date",
        "award_start_date",
        "award_has_observed_base_transaction",
        "award_left_censored",
        "first_target_action_date",
        "target_naics_on_first_observed_action",
        "obligation_amount",
        "description",
        "contract_award_type",
        "research",
        "naics_code",
        "product_or_service_code",
        "source_fiscal_year",
    }
    source_sha256 = _sha256(path)
    source_manifest_path = path.with_suffix(".manifest.json")
    if not source_manifest_path.exists():
        raise ValueError("historical target ledger has no source manifest")
    source_manifest: dict[str, Any] = json.loads(source_manifest_path.read_text())
    if source_manifest.get("ok") is not True:
        raise ValueError("historical target ledger source manifest did not pass its checks")
    declared_sha256 = source_manifest.get("output", {}).get("sha256")
    if declared_sha256 != source_sha256:
        raise ValueError("historical target ledger does not match its source manifest")

    declared_codes = set(source_manifest.get("filter", {}).get("target_naics_codes", []))
    if declared_codes != set(TARGET_NAICS):
        raise ValueError("historical target ledger target codes do not match this analysis")

    expected_ueis = set(cohort.firms["firm_uei"])
    filter_info = source_manifest.get("filter", {})
    filter_path = Path(str(filter_info.get("path", "")))
    if not filter_path.exists():
        raise ValueError("historical target ledger UEI filter is unavailable")
    if _sha256(filter_path) != filter_info.get("sha256"):
        raise ValueError("historical target ledger UEI filter hash does not match")
    filter_payload = json.loads(filter_path.read_text())
    filter_ueis = {
        normalized
        for value in filter_payload.get("uei", [])
        if (normalized := normalize_uei(value)) is not None
    }
    if filter_ueis != expected_ueis:
        raise ValueError(
            "historical target ledger UEI filter does not match the current exact-UEI cohort"
        )
    raw = pd.read_parquet(path)
    source_transaction_rows = len(raw)
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"historical target ledger is missing columns: {missing}")
    if raw["transaction_unique_id"].isna().any():
        raise ValueError("historical target ledger has null transaction IDs")
    if raw["transaction_unique_id"].duplicated().any():
        raise ValueError("historical target ledger has duplicate transaction IDs")

    raw["firm_uei"] = raw["firm_uei"].map(normalize_uei)
    nonexact_rows = int((~raw["firm_uei"].isin(expected_ueis)).sum())
    raw = raw.loc[raw["firm_uei"].isin(expected_ueis)].copy()
    raw["naics_code"] = raw["naics_code"].astype(str).str.strip()
    nontarget_rows = int((~raw["naics_code"].isin(TARGET_NAICS)).sum())
    raw = raw.loc[raw["naics_code"].isin(TARGET_NAICS)].copy()
    nonprime_rows = int((~raw["contract_award_type"].isin(CONTRACT_TYPES)).sum())
    raw = raw.loc[raw["contract_award_type"].isin(CONTRACT_TYPES)].copy()

    for column in (
        "action_date",
        "start_date",
        "end_date",
        "award_first_action_date",
        "award_start_date",
        "first_target_action_date",
    ):
        raw[column] = pd.to_datetime(raw[column], errors="coerce")
    if raw["action_date"].isna().any():
        raise ValueError("historical target ledger has unusable action dates")
    target_action_end = raw["action_date"].max()
    declared_coverage_end = source_manifest.get("coverage", {}).get("fy2026_source_max_action_date")
    coverage_end = pd.to_datetime(declared_coverage_end, errors="coerce")
    if pd.isna(coverage_end):
        coverage_end = target_action_end
    if pd.isna(coverage_end):
        raise ValueError("historical target ledger has no usable coverage end")

    raw["obligation_amount"] = pd.to_numeric(raw["obligation_amount"], errors="coerce")
    if raw["obligation_amount"].isna().any():
        raise ValueError("historical target ledger has null obligations")
    raw["gross_positive_obligation"] = raw["obligation_amount"].clip(lower=0.0)
    raw["deobligation_amount"] = -raw["obligation_amount"].clip(upper=0.0)
    raw["research"] = raw["research"].fillna("").astype(str).str.upper().str.strip()
    raw["normalized_research_code"] = raw["research"].map(_normalize_research_code)
    unrecognized_research = sorted(
        set(
            raw.loc[
                raw["research"].ne("") & raw["normalized_research_code"].eq(""),
                "research",
            ]
        )
    )
    if unrecognized_research:
        raise ValueError(
            "historical target ledger has unrecognized nonblank research values: "
            f"{unrecognized_research}"
        )
    raw["description"] = raw["description"].fillna("").astype(str)
    raw["explicit_phase_i_ii"] = raw["normalized_research_code"].isin(PHASE_I_II_RESEARCH_CODES)
    raw["explicit_phase_iii"] = raw["normalized_research_code"].isin(PHASE_III_RESEARCH_CODES)
    raw["phase_i_ii_text_row"] = raw["description"].map(
        lambda value: bool(PHASE_I_II_TEXT.search(value))
    )
    raw["phase_iii_text_row"] = raw["description"].map(
        lambda value: bool(PHASE_III_TEXT.search(value))
    )

    raw["normalized_piid"] = raw["piid"].map(_clean_award_id)
    raw["normalized_contract_id"] = raw["contract_id"].map(_clean_award_id)
    raw["known_sbir_award_id_row"] = [
        (uei, piid) in cohort.known_sbir_contracts
        or (uei, contract_id) in cohort.known_sbir_contracts
        for uei, piid, contract_id in zip(
            raw["firm_uei"],
            raw["normalized_piid"],
            raw["normalized_contract_id"],
            strict=True,
        )
    ]

    raw["target_fiscal_year"] = pd.to_numeric(raw["source_fiscal_year"], errors="raise").astype(int)
    phase_ii_anchor = cohort.firms.set_index("firm_uei")["first_phase_ii_end"]
    raw["first_phase_ii_end"] = raw["firm_uei"].map(phase_ii_anchor)
    raw["post_phase_ii_target_action_date"] = raw["action_date"].where(
        raw["first_phase_ii_end"].notna() & (raw["action_date"] > raw["first_phase_ii_end"])
    )
    raw["positive_target_action_after_phase_ii_date"] = raw["action_date"].where(
        raw["first_phase_ii_end"].notna()
        & (raw["action_date"] > raw["first_phase_ii_end"])
        & raw["obligation_amount"].gt(0)
    )
    keys = ["firm_uei", "award_group_key", "naics_code"]
    first = raw.sort_values(
        ["firm_uei", "award_group_key", "naics_code", "action_date", "transaction_unique_id"]
    ).drop_duplicates(keys)
    first = first.set_index(keys)
    grouped = raw.groupby(keys, sort=True, dropna=False)
    evidence = grouped.agg(
        generated_award_id=("generated_unique_award_id", _first_nonblank),
        award_id=("piid", _first_nonblank),
        recipient_name=("vendor_name", _first_nonblank),
        award_first_action_date=("award_first_action_date", "min"),
        award_start_date=("award_start_date", "min"),
        first_target_action_date=("first_target_action_date", "min"),
        first_target_action_after_phase_ii=("post_phase_ii_target_action_date", "min"),
        first_positive_target_action_after_phase_ii=(
            "positive_target_action_after_phase_ii_date",
            "min",
        ),
        last_target_action_date=("action_date", "max"),
        end_date=("end_date", "max"),
        awarding_agency=("agency", _first_nonblank),
        awarding_sub_agency=("sub_agency", _first_nonblank),
        description=("description", _first_nonblank),
        psc_code=("product_or_service_code", _first_nonblank),
        target_transaction_count=("transaction_unique_id", "nunique"),
        target_fiscal_year_count=("target_fiscal_year", "nunique"),
        target_fiscal_years=(
            "target_fiscal_year",
            lambda values: ";".join(str(value) for value in sorted(set(values))),
        ),
        signed_target_obligations=("obligation_amount", "sum"),
        gross_positive_target_obligations=("gross_positive_obligation", "sum"),
        target_deobligations=("deobligation_amount", "sum"),
        known_sbir_award_id=("known_sbir_award_id_row", "max"),
        explicit_phase_i_ii=("explicit_phase_i_ii", "max"),
        explicit_phase_iii=("explicit_phase_iii", "max"),
        phase_i_ii_text=("phase_i_ii_text_row", "max"),
        phase_iii_text=("phase_iii_text_row", "max"),
        normalized_research_codes=(
            "normalized_research_code",
            lambda values: ";".join(sorted({value for value in values if value})),
        ),
        award_has_observed_base_transaction=("award_has_observed_base_transaction", "max"),
        award_left_censored=("award_left_censored", "max"),
        target_naics_on_first_observed_action=(
            "target_naics_on_first_observed_action",
            "max",
        ),
    )
    evidence["contract_award_type"] = first["contract_award_type"]
    evidence = evidence.reset_index()
    explicit_phase_iii = evidence["explicit_phase_iii"]
    text_phase_iii = evidence["phase_iii_text"]
    evidence["classified_phase_i_ii"] = evidence["explicit_phase_i_ii"] | (
        ~explicit_phase_iii & ~text_phase_iii & evidence["phase_i_ii_text"]
    )
    evidence["phase_iii_marker"] = explicit_phase_iii | text_phase_iii
    evidence["has_positive_target_obligation"] = evidence["gross_positive_target_obligations"].gt(0)
    evidence["positive_net_award"] = evidence["signed_target_obligations"].gt(0)
    evidence["not_classified_phase_i_ii"] = (
        ~evidence["known_sbir_award_id"] & ~evidence["classified_phase_i_ii"]
    )
    evidence["target_origin_award"] = (
        evidence["award_has_observed_base_transaction"]
        & ~evidence["award_left_censored"]
        & evidence["target_naics_on_first_observed_action"]
    )
    evidence["qualifying_target_procurement"] = (
        evidence["not_classified_phase_i_ii"]
        & evidence["target_origin_award"]
        & evidence["has_positive_target_obligation"]
    )
    evidence["event_date"] = evidence["first_target_action_date"]
    evidence["event_date_source"] = "first_target_coded_transaction_action"
    evidence["award_amount"] = evidence["signed_target_obligations"]
    evidence["naics_description"] = evidence["naics_code"].map(TARGET_NAICS)

    audit = {
        "path": str(path),
        "sha256": source_sha256,
        "source_manifest_path": str(source_manifest_path) if source_manifest else None,
        "source_manifest_sha256": (_sha256(source_manifest_path) if source_manifest else None),
        "source_transaction_rows": source_transaction_rows,
        "nonexact_uei_rows_dropped": nonexact_rows,
        "nontarget_rows_dropped": nontarget_rows,
        "nonprime_idv_rows_dropped": nonprime_rows,
        "target_prime_transaction_rows": len(raw),
        "target_prime_entities": int(raw["firm_uei"].nunique()),
        "target_prime_awards": int(raw[["firm_uei", "award_group_key"]].drop_duplicates().shape[0]),
        "coverage_start": ARCHIVE_COVERAGE_START.isoformat(),
        "coverage_end": coverage_end.date().isoformat(),
        "target_action_max_date": target_action_end.date().isoformat(),
        "signed_target_obligations": float(raw["obligation_amount"].sum()),
        "gross_positive_target_obligations": float(raw["gross_positive_obligation"].sum()),
        "target_deobligations": float(raw["deobligation_amount"].sum()),
        "entity_award_code_rows": len(evidence),
        "target_origin_award_code_rows": int(evidence["target_origin_award"].sum()),
        "later_target_reclassification_award_code_rows": int(
            (~evidence["target_naics_on_first_observed_action"]).sum()
        ),
        "normalized_research_code_counts": {
            str(key): int(value)
            for key, value in raw.loc[
                raw["normalized_research_code"].ne(""), "normalized_research_code"
            ]
            .value_counts()
            .sort_index()
            .items()
        },
        "unrecognized_nonblank_research_values": unrecognized_research,
    }
    return HistoricalContractResult(evidence=evidence, audit=audit, coverage_end=coverage_end)


def load_recent_transaction_evidence(
    path: Path | None, sbir_ueis: set[str]
) -> tuple[pd.DataFrame, dict[str, Any]]:
    columns = [
        "firm_uei",
        "naics_code",
        "generated_unique_award_id",
        "first_action_date",
        "last_action_date",
        "net_obligations",
    ]
    if path is None or not path.exists():
        return pd.DataFrame(columns=columns), {"available": False}
    raw = pd.read_parquet(
        path,
        columns=[
            "vendor_uei",
            "naics_code",
            "contract_award_type",
            "generated_unique_award_id",
            "transaction_unique_id",
            "action_date",
            "obligation_amount",
        ],
    )
    raw["firm_uei"] = raw["vendor_uei"].map(normalize_uei)
    raw["naics_code"] = raw["naics_code"].astype(str).str.strip()
    prime = raw["contract_award_type"].isin(CONTRACT_TYPES)
    selected = raw.loc[
        prime & raw["firm_uei"].isin(sbir_ueis) & raw["naics_code"].isin(TARGET_NAICS)
    ].copy()
    selected["action_date"] = pd.to_datetime(selected["action_date"], errors="coerce")
    grouped = (
        selected.groupby(["firm_uei", "naics_code", "generated_unique_award_id"], dropna=False)
        .agg(
            first_action_date=("action_date", "min"),
            last_action_date=("action_date", "max"),
            net_obligations=("obligation_amount", "sum"),
        )
        .reset_index()
    )
    positive = grouped.loc[grouped["net_obligations"].gt(0)].copy()
    audit = {
        "available": True,
        "path": str(path),
        "sha256": _sha256(path),
        "source_rows": len(raw),
        "source_min_action_date": str(pd.to_datetime(raw["action_date"]).min().date()),
        "source_max_action_date": str(pd.to_datetime(raw["action_date"]).max().date()),
        "nonprime_transaction_rows_dropped": int((~prime).sum()),
        "exact_uei_target_transaction_rows": len(selected),
        "positive_net_target_awards": len(positive),
        "positive_net_target_firms": int(positive["firm_uei"].nunique()),
    }
    return positive[columns], audit


def _expand_sam_codes(sam: pd.DataFrame, *, active_only: bool = True) -> pd.DataFrame:
    selected = sam.loc[sam["registration_status"].eq("A")] if active_only else sam
    rows = []
    for row in selected.itertuples(index=False):
        primary_targets = set(str(row.primary_target_codes).split(";"))
        for code in str(row.target_codes).split(";"):
            if code:
                rows.append(
                    {
                        "firm_uei": row.firm_uei,
                        "naics_code": code,
                        "sam_primary_for_code": code in primary_targets,
                        "sam_current_8a_indicator": row.sam_current_8a_indicator,
                    }
                )
    return pd.DataFrame.from_records(
        rows,
        columns=[
            "firm_uei",
            "naics_code",
            "sam_primary_for_code",
            "sam_current_8a_indicator",
        ],
    )


def _hhi_and_shares(frame: pd.DataFrame) -> tuple[float | None, float | None, float | None]:
    positive = frame.groupby("firm_uei")["award_amount"].sum()
    positive = positive.loc[positive.gt(0)].sort_values(ascending=False)
    total = positive.sum()
    if positive.empty or total <= 0:
        return None, None, None
    shares = positive / total
    return (
        float((shares.pow(2).sum()) * 10_000),
        float(shares.iloc[0]),
        float(shares.iloc[:4].sum()),
    )


def _wilson_interval(successes: int, total: int) -> tuple[float | None, float | None]:
    if total < 1:
        return None, None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + (z**2 / total)
    center = (proportion + z**2 / (2 * total)) / denominator
    half_width = (
        z * ((proportion * (1 - proportion) / total + z**2 / (4 * total**2)) ** 0.5) / denominator
    )
    return center - half_width, center + half_width


def _first_event_bundle(
    frame: pd.DataFrame,
    *,
    date_column: str,
    prefix: str,
) -> pd.DataFrame:
    usable = frame.loc[frame[date_column].notna()].copy()
    if usable.empty:
        return pd.DataFrame(columns=["firm_uei", f"{prefix}_date", f"{prefix}_codes"])
    usable["_first_date"] = usable.groupby("firm_uei")[date_column].transform("min")
    tied = usable.loc[usable[date_column].eq(usable["_first_date"])].copy()
    maximum_tied_award = (
        tied.groupby(["firm_uei", "award_group_key"])["gross_positive_target_obligations"]
        .sum()
        .groupby("firm_uei")
        .max()
        .rename(f"{prefix}_maximum_award_gross_positive_obligations")
    )
    bundle = (
        tied.groupby("firm_uei", as_index=False)
        .agg(
            **{
                f"{prefix}_date": (date_column, "min"),
                f"{prefix}_codes": (
                    "naics_code",
                    lambda values: ";".join(sorted(set(values))),
                ),
                f"{prefix}_award_keys": (
                    "award_group_key",
                    lambda values: ";".join(sorted(set(values))),
                ),
                f"{prefix}_gross_positive_obligations": (
                    "gross_positive_target_obligations",
                    "sum",
                ),
                f"{prefix}_phase_iii_marker": ("phase_iii_marker", "max"),
            }
        )
        .sort_values("firm_uei")
    )
    return bundle.merge(maximum_tied_award, on="firm_uei", how="left")


def _sustained_entity_set(frame: pd.DataFrame) -> set[str]:
    if frame.empty:
        return set()
    sustained: set[str] = set()
    for firm_uei, group in frame.groupby("firm_uei"):
        fiscal_years = {
            int(year)
            for value in group["target_fiscal_years"]
            for year in str(value).split(";")
            if year
        }
        if group["award_group_key"].nunique() >= 2 and len(fiscal_years) >= 2:
            sustained.add(firm_uei)
    return sustained


def _sustained_entity_count(frame: pd.DataFrame) -> int:
    return len(_sustained_entity_set(frame))


def _identity_name_key(value: Any) -> str:
    return normalize_company_name(value, profile=CompanyNameProfile.ORGANIZATION_KEY_V1)


def load_identity_crosswalk(path: Path | None) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load reviewed identity annotations without treating absent rows as negatives."""

    if path is None or not path.exists():
        return pd.DataFrame(columns=[*IDENTITY_CROSSWALK_COLUMNS, "review_state"]), {
            "available": False,
            "path": str(path) if path is not None else None,
        }

    reviews = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = sorted(set(IDENTITY_CROSSWALK_COLUMNS) - set(reviews.columns))
    if missing:
        raise ValueError(f"identity crosswalk is missing columns: {missing}")
    reviews = reviews[IDENTITY_CROSSWALK_COLUMNS].copy()
    reviews["firm_uei"] = reviews["firm_uei"].map(normalize_uei)
    if reviews["firm_uei"].isna().any():
        raise ValueError("identity crosswalk contains an invalid UEI")

    expected_sbir_keys = reviews["sbir_display_name"].map(_identity_name_key)
    expected_contract_keys = reviews["contract_recipient_name"].map(_identity_name_key)
    if not reviews["sbir_name_key"].eq(expected_sbir_keys).all():
        raise ValueError("identity crosswalk SBIR name keys do not match organization-key-v1")
    if not reviews["contract_name_key"].eq(expected_contract_keys).all():
        raise ValueError("identity crosswalk contract name keys do not match organization-key-v1")

    key_columns = ["firm_uei", "sbir_name_key", "contract_name_key"]
    if reviews.duplicated(key_columns).any():
        raise ValueError("identity crosswalk contains duplicate review keys")
    allowed_fields = {
        "entity_same_firm": IDENTITY_SAME_FIRM_VALUES,
        "corporate_relation": IDENTITY_RELATION_VALUES,
        "corporate_event_date_basis": IDENTITY_DATE_BASIS_VALUES,
        "contract_relationship": IDENTITY_CONTRACT_RELATION_VALUES,
        "attribution_treatment": IDENTITY_ATTRIBUTION_VALUES,
        "review_confidence": IDENTITY_CONFIDENCE_VALUES,
    }
    for column, allowed in allowed_fields.items():
        invalid = sorted(set(reviews[column]) - allowed)
        if invalid:
            raise ValueError(f"identity crosswalk has invalid {column} values: {invalid}")
    for column in ("corporate_event_date", "reviewed_at"):
        nonblank = reviews[column].ne("")
        parsed = pd.to_datetime(reviews.loc[nonblank, column], format="%Y-%m-%d", errors="coerce")
        if parsed.isna().any():
            raise ValueError(f"identity crosswalk has invalid ISO dates in {column}")
    documented = reviews["corporate_relation"].ne("unknown")
    if (documented & reviews["evidence_locator"].eq("")).any():
        raise ValueError("documented identity reviews require an evidence locator")

    reviews["review_state"] = documented.map(
        {True: "reviewed_supported", False: "reviewed_unresolved"}
    )
    audit = {
        "available": True,
        "path": str(path),
        "sha256": _sha256(path),
        "rows": len(reviews),
        "reviewed_supported_rows": int(documented.sum()),
        "reviewed_unresolved_rows": int((~documented).sum()),
    }
    return reviews, audit


def build_identity_review_candidates(
    firm_evidence: pd.DataFrame,
    contracts: pd.DataFrame,
    reviews: pd.DataFrame,
) -> pd.DataFrame:
    """Build a deterministic low-name-continuity queue at identity-pair grain."""

    firm_columns = [
        "firm_uei",
        "display_name",
        "first_sbir_year",
        "last_sbir_year",
        "clean_pre_index_qualifying_target_origin_award",
        "literal_first_observed_target_entry",
        "has_sustained_target_procurement",
    ]
    pairs = contracts.merge(firm_evidence[firm_columns], on="firm_uei", how="left")
    pairs["recipient_name"] = pairs["recipient_name"].fillna("").astype(str).str.strip()
    grouped = pairs.groupby(
        ["firm_uei", "display_name", "recipient_name"],
        as_index=False,
        dropna=False,
    ).agg(
        first_sbir_year=("first_sbir_year", "min"),
        last_sbir_year=("last_sbir_year", "max"),
        first_target_action_date=("first_target_action_date", "min"),
        last_target_action_date=("last_target_action_date", "max"),
        target_prime_awards=("award_group_key", "nunique"),
        target_prime_award_keys=(
            "award_group_key",
            lambda values: ";".join(sorted(set(values))),
        ),
        target_prime_codes=(
            "naics_code",
            lambda values: ";".join(sorted(set(values))),
        ),
        target_signed_obligations=("signed_target_obligations", "sum"),
        target_gross_positive_obligations=("gross_positive_target_obligations", "sum"),
        target_deobligations=("target_deobligations", "sum"),
        clean_pre_index_qualifying_target_origin_award=(
            "clean_pre_index_qualifying_target_origin_award",
            "max",
        ),
        literal_first_observed_target_entry=("literal_first_observed_target_entry", "max"),
        has_sustained_target_procurement=("has_sustained_target_procurement", "max"),
    )
    grouped = grouped.rename(
        columns={
            "display_name": "sbir_display_name",
            "recipient_name": "contract_recipient_name",
        }
    )
    grouped["sbir_name_key"] = grouped["sbir_display_name"].map(_identity_name_key)
    grouped["contract_name_key"] = grouped["contract_recipient_name"].map(_identity_name_key)
    both_names = grouped["sbir_name_key"].ne("") & grouped["contract_name_key"].ne("")
    grouped["sbir_to_contract_name_similarity"] = pd.NA
    grouped.loc[both_names, "sbir_to_contract_name_similarity"] = [
        company_name_similarity(
            sbir_name,
            contract_name,
            metric=CompanyNameMetric.TOKEN_SET,
            profile=CompanyNameProfile.RECIPIENT_V1,
        )
        for sbir_name, contract_name in zip(
            grouped.loc[both_names, "sbir_display_name"],
            grouped.loc[both_names, "contract_recipient_name"],
            strict=True,
        )
    ]
    similarity = pd.to_numeric(grouped["sbir_to_contract_name_similarity"], errors="coerce")
    candidates = grouped.loc[similarity.lt(NAME_CONTINUITY_THRESHOLD) | similarity.isna()].copy()
    candidates["candidate_reason"] = "name_similarity_below_threshold"
    candidates.loc[similarity.loc[candidates.index].isna(), "candidate_reason"] = (
        "missing_name_for_continuity_review"
    )

    entity_dollars = (
        candidates.groupby("firm_uei")["target_gross_positive_obligations"]
        .sum()
        .sort_values(ascending=False, kind="stable")
    )
    ranked_entities = (
        entity_dollars.rename("candidate_entity_gross_positive_obligations")
        .reset_index()
        .sort_values(
            ["candidate_entity_gross_positive_obligations", "firm_uei"],
            ascending=[False, True],
            kind="stable",
        )
    )
    ranked_entities["candidate_entity_dollar_rank"] = range(1, len(ranked_entities) + 1)
    candidates = candidates.merge(ranked_entities, on="firm_uei", how="left")
    candidates["priority_top_dollar_entity"] = candidates["candidate_entity_dollar_rank"].le(
        IDENTITY_REVIEW_TOP_DOLLAR_ENTITIES
    )
    candidates["priority_clean_pre_index_entity"] = candidates[
        "clean_pre_index_qualifying_target_origin_award"
    ].fillna(False)
    candidates["priority_review_tranche"] = candidates[
        ["priority_top_dollar_entity", "priority_clean_pre_index_entity"]
    ].any(axis=1)
    candidates["priority_reason"] = ""
    candidates.loc[candidates["priority_top_dollar_entity"], "priority_reason"] = (
        "top_10_flagged_dollars"
    )
    candidates.loc[candidates["priority_clean_pre_index_entity"], "priority_reason"] = (
        candidates.loc[candidates["priority_clean_pre_index_entity"], "priority_reason"]
        .replace("", "clean_pre_index_low_continuity")
        .replace(
            "top_10_flagged_dollars",
            "top_10_flagged_dollars;clean_pre_index_low_continuity",
        )
    )

    total_target_dollars = firm_evidence["target_gross_positive_obligations"].fillna(0.0).sum()
    total_flagged_dollars = candidates["target_gross_positive_obligations"].sum()
    candidates["share_of_all_target_gross_positive_obligations"] = (
        candidates["target_gross_positive_obligations"] / total_target_dollars
        if total_target_dollars
        else pd.NA
    )
    candidates = candidates.sort_values(
        ["candidate_entity_dollar_rank", "target_gross_positive_obligations", "contract_name_key"],
        ascending=[True, False, True],
        kind="stable",
    )
    candidates["cumulative_share_of_flagged_gross_positive_obligations"] = (
        candidates["target_gross_positive_obligations"].cumsum() / total_flagged_dollars
        if total_flagged_dollars
        else pd.NA
    )

    join_keys = ["firm_uei", "sbir_name_key", "contract_name_key"]
    review_columns = [column for column in IDENTITY_CROSSWALK_COLUMNS if column not in join_keys]
    review_annotations = reviews[join_keys + review_columns + ["review_state"]].copy()
    review_annotations = review_annotations.rename(
        columns={
            "sbir_display_name": "reviewed_sbir_display_name",
            "contract_recipient_name": "reviewed_contract_recipient_name",
        }
    )
    candidates = candidates.merge(review_annotations, on=join_keys, how="left")
    candidates["review_state"] = candidates["review_state"].fillna("unreviewed")
    return candidates.reset_index(drop=True)


def build_archive_analysis_tables(
    cohort: SbirCohort,
    contracts: pd.DataFrame,
    sam: pd.DataFrame,
    recent: pd.DataFrame,
    analysis_date: date,
    coverage_end: pd.Timestamp,
    identity_reviews: pd.DataFrame | None = None,
) -> tuple[dict[str, Any], dict[str, pd.DataFrame]]:
    """Build separate registration, activity, post-Phase-II, and entry views."""

    firms = cohort.firms.copy()
    anchor_by_entity = firms.set_index("firm_uei")["first_phase_ii_end"]
    contracts = contracts.copy()
    contracts["first_phase_ii_end"] = contracts["firm_uei"].map(anchor_by_entity)

    positive = contracts.loc[contracts["has_positive_target_obligation"]].copy()
    net_positive = contracts.loc[contracts["positive_net_award"]].copy()
    positive_not_phase_i_ii = positive.loc[positive["not_classified_phase_i_ii"]].copy()
    structural_target_origin = contracts.loc[contracts["target_origin_award"]].copy()
    qualifying_origin = positive.loc[positive["qualifying_target_procurement"]].copy()

    first_any = _first_event_bundle(
        contracts,
        date_column="first_target_action_date",
        prefix="first_any_target_action",
    )
    first_post_action = _first_event_bundle(
        positive_not_phase_i_ii,
        date_column="first_positive_target_action_after_phase_ii",
        prefix="first_post_phase_ii_positive_non_phase_i_ii_action",
    )
    post_origin = qualifying_origin.loc[
        qualifying_origin["first_phase_ii_end"].notna()
        & (qualifying_origin["award_first_action_date"] > qualifying_origin["first_phase_ii_end"])
    ].copy()
    first_post_origin = _first_event_bundle(
        post_origin,
        date_column="award_first_action_date",
        prefix="first_post_phase_ii_target_origin_award",
    )

    timeline = contracts.loc[contracts["first_phase_ii_end"].notna()].copy()
    pre_index_entities = set(
        timeline.loc[
            timeline["first_target_action_date"] <= timeline["first_phase_ii_end"],
            "firm_uei",
        ]
    )
    same_day_entities = set(
        timeline.loc[
            timeline["first_target_action_date"].eq(timeline["first_phase_ii_end"]),
            "firm_uei",
        ]
    )

    contract_rollup = contracts.groupby("firm_uei", as_index=False).agg(
        target_prime_awards=("award_group_key", "nunique"),
        target_prime_codes=(
            "naics_code",
            lambda values: ";".join(sorted(set(values))),
        ),
        target_signed_obligations=("signed_target_obligations", "sum"),
        target_gross_positive_obligations=(
            "gross_positive_target_obligations",
            "sum",
        ),
        target_deobligations=("target_deobligations", "sum"),
        last_target_action_date=("last_target_action_date", "max"),
        phase_iii_marker_awards=("phase_iii_marker", "sum"),
    )
    latest_contract_name = (
        contracts.sort_values(["last_target_action_date", "firm_uei"])
        .drop_duplicates("firm_uei", keep="last")[["firm_uei", "recipient_name"]]
        .rename(columns={"recipient_name": "latest_target_contract_recipient_name"})
    )
    positive_entities = set(positive["firm_uei"])
    net_positive_entities = set(net_positive["firm_uei"])
    positive_not_phase_i_ii_entities = set(positive_not_phase_i_ii["firm_uei"])
    structural_target_origin_entities = set(structural_target_origin["firm_uei"])
    qualifying_origin_entities = set(qualifying_origin["firm_uei"])
    sustained_entities = _sustained_entity_set(qualifying_origin)

    firm_evidence = firms.merge(contract_rollup, on="firm_uei", how="left")
    firm_evidence = firm_evidence.merge(latest_contract_name, on="firm_uei", how="left")
    for bundle in (first_any, first_post_action, first_post_origin):
        firm_evidence = firm_evidence.merge(bundle, on="firm_uei", how="left")

    active_sam = sam.loc[sam["registration_status"].eq("A")].rename(
        columns={
            "target_codes": "active_sam_target_codes",
            "primary_naics": "active_sam_primary_naics",
            "has_primary_target": "active_sam_primary_target",
            "sam_8a_history_indicator": "active_sam_8a_history_indicator",
            "sam_current_8a_indicator": "active_sam_current_8a_indicator",
            "sam_8a_exit_dates": "active_sam_8a_exit_dates",
        }
    )
    firm_evidence = firm_evidence.merge(
        active_sam[
            [
                "firm_uei",
                "active_sam_target_codes",
                "active_sam_primary_naics",
                "active_sam_primary_target",
                "active_sam_8a_history_indicator",
                "active_sam_current_8a_indicator",
                "active_sam_8a_exit_dates",
            ]
        ],
        on="firm_uei",
        how="left",
    )
    recent_rollup = recent.groupby("firm_uei", as_index=False).agg(
        recent_target_codes=(
            "naics_code",
            lambda values: ";".join(sorted(set(values))),
        ),
        recent_target_awards=("generated_unique_award_id", "nunique"),
        recent_target_net_obligations=("net_obligations", "sum"),
        recent_target_last_action=("last_action_date", "max"),
    )
    firm_evidence = firm_evidence.merge(recent_rollup, on="firm_uei", how="left")

    firm_evidence["has_any_target_prime_action"] = firm_evidence["firm_uei"].isin(
        set(contracts["firm_uei"])
    )
    firm_evidence["has_positive_target_prime_obligation"] = firm_evidence["firm_uei"].isin(
        positive_entities
    )
    firm_evidence["has_net_positive_target_prime_award_code"] = firm_evidence["firm_uei"].isin(
        net_positive_entities
    )
    firm_evidence["has_positive_non_phase_i_ii_target_prime"] = firm_evidence["firm_uei"].isin(
        positive_not_phase_i_ii_entities
    )
    firm_evidence["has_structural_target_origin_prime_award"] = firm_evidence["firm_uei"].isin(
        structural_target_origin_entities
    )
    firm_evidence["has_qualifying_target_origin_prime_award"] = firm_evidence["firm_uei"].isin(
        qualifying_origin_entities
    )
    firm_evidence["has_sustained_target_procurement"] = firm_evidence["firm_uei"].isin(
        sustained_entities
    )
    firm_evidence["has_active_sam_target"] = firm_evidence["active_sam_target_codes"].notna()
    firm_evidence["has_recent_target_activity"] = firm_evidence["recent_target_codes"].notna()
    firm_evidence["pre_index_any_target_action"] = firm_evidence["firm_uei"].isin(
        pre_index_entities
    )
    firm_evidence["same_day_target_action"] = firm_evidence["firm_uei"].isin(same_day_entities)

    anchor = pd.to_datetime(firm_evidence["first_phase_ii_end"], errors="coerce")
    lookback_start = pd.Timestamp(ARCHIVE_COVERAGE_START) + pd.DateOffset(
        years=CLEAN_PRE_INDEX_COVERAGE_YEARS
    )
    firm_evidence["has_three_year_pre_index_observation"] = anchor.ge(lookback_start)
    firm_evidence["clean_pre_index_qualifying_target_origin_award"] = (
        firm_evidence["has_three_year_pre_index_observation"]
        & ~firm_evidence["pre_index_any_target_action"]
        & firm_evidence["first_post_phase_ii_target_origin_award_date"].notna()
    )
    firm_evidence["clean_pre_index_latency_days"] = (
        pd.to_datetime(firm_evidence["first_post_phase_ii_target_origin_award_date"]) - anchor
    ).dt.days.where(firm_evidence["clean_pre_index_qualifying_target_origin_award"])
    firm_evidence["literal_first_observed_target_entry"] = firm_evidence[
        "clean_pre_index_qualifying_target_origin_award"
    ] & pd.to_datetime(firm_evidence["first_any_target_action_date"]).eq(
        pd.to_datetime(firm_evidence["first_post_phase_ii_target_origin_award_date"])
    )
    firm_evidence["literal_first_entry_latency_days"] = firm_evidence[
        "clean_pre_index_latency_days"
    ].where(firm_evidence["literal_first_observed_target_entry"])
    firm_evidence["has_any_target_evidence"] = firm_evidence[
        ["has_any_target_prime_action", "has_active_sam_target"]
    ].any(axis=1)
    has_both_names = (
        firm_evidence["display_name"].notna()
        & firm_evidence["latest_target_contract_recipient_name"].notna()
    )
    firm_evidence["sbir_to_contract_name_similarity"] = pd.NA
    firm_evidence.loc[has_both_names, "sbir_to_contract_name_similarity"] = [
        company_name_similarity(
            sbir_name,
            contract_name,
            metric=CompanyNameMetric.TOKEN_SET,
            profile=CompanyNameProfile.RECIPIENT_V1,
        )
        for sbir_name, contract_name in zip(
            firm_evidence.loc[has_both_names, "display_name"],
            firm_evidence.loc[has_both_names, "latest_target_contract_recipient_name"],
            strict=True,
        )
    ]
    firm_evidence["high_name_continuity"] = pd.to_numeric(
        firm_evidence["sbir_to_contract_name_similarity"], errors="coerce"
    ).ge(NAME_CONTINUITY_THRESHOLD)

    sam_long = _expand_sam_codes(sam)
    recent_long = recent[["firm_uei", "naics_code", "net_obligations"]].copy()
    clean_pre_index_entities = set(
        firm_evidence.loc[
            firm_evidence["clean_pre_index_qualifying_target_origin_award"], "firm_uei"
        ]
    )
    clean_pre_index_origin = post_origin.loc[
        post_origin["firm_uei"].isin(clean_pre_index_entities)
    ].copy()
    clean_pre_index_origin["_first"] = clean_pre_index_origin.groupby("firm_uei")[
        "award_first_action_date"
    ].transform("min")
    clean_pre_index_origin = clean_pre_index_origin.loc[
        clean_pre_index_origin["award_first_action_date"].eq(clean_pre_index_origin["_first"])
    ]
    literal_entry_entities = set(
        firm_evidence.loc[firm_evidence["literal_first_observed_target_entry"], "firm_uei"]
    )

    code_rows: list[dict[str, Any]] = []
    for code, title in TARGET_NAICS.items():
        c = contracts.loc[contracts["naics_code"].eq(code)]
        c_positive = positive.loc[positive["naics_code"].eq(code)]
        c_net_positive = net_positive.loc[net_positive["naics_code"].eq(code)]
        c_not_phase = positive_not_phase_i_ii.loc[positive_not_phase_i_ii["naics_code"].eq(code)]
        c_structural_origin = structural_target_origin.loc[
            structural_target_origin["naics_code"].eq(code)
        ]
        c_origin = qualifying_origin.loc[qualifying_origin["naics_code"].eq(code)]
        c_clean = clean_pre_index_origin.loc[clean_pre_index_origin["naics_code"].eq(code)]
        c_literal = c_clean.loc[c_clean["firm_uei"].isin(literal_entry_entities)]
        s = sam_long.loc[sam_long["naics_code"].eq(code)]
        r = recent_long.loc[recent_long["naics_code"].eq(code)]
        hhi_frame = c_positive.assign(award_amount=c_positive["gross_positive_target_obligations"])
        hhi, top1, top4 = _hhi_and_shares(hhi_frame)
        code_rows.append(
            {
                "naics_code": code,
                "title": title,
                "entities_with_any_target_prime_action": int(c["firm_uei"].nunique()),
                "entities_with_positive_target_obligation": int(c_positive["firm_uei"].nunique()),
                "entities_with_net_positive_award_code": int(c_net_positive["firm_uei"].nunique()),
                "entities_with_positive_non_phase_i_ii_target_prime": int(
                    c_not_phase["firm_uei"].nunique()
                ),
                "entities_with_structural_target_origin_award": int(
                    c_structural_origin["firm_uei"].nunique()
                ),
                "entities_with_qualifying_target_origin_award": int(c_origin["firm_uei"].nunique()),
                "clean_pre_index_qualifying_origin_entities": int(c_clean["firm_uei"].nunique()),
                "literal_first_observed_entry_entities": int(c_literal["firm_uei"].nunique()),
                "active_sam_any_code_entities": int(s["firm_uei"].nunique()),
                "active_sam_primary_code_entities": int(
                    s.loc[s["sam_primary_for_code"], "firm_uei"].nunique()
                ),
                "active_sam_current_8a_entities": int(
                    s.loc[s["sam_current_8a_indicator"], "firm_uei"].nunique()
                ),
                "recent_positive_net_activity_entities": int(r["firm_uei"].nunique()),
                "sustained_target_procurement_entities": _sustained_entity_count(c_origin),
                "target_prime_awards": int(
                    c[["firm_uei", "award_group_key"]].drop_duplicates().shape[0]
                ),
                "qualifying_target_origin_prime_awards": int(
                    c_origin[["firm_uei", "award_group_key"]].drop_duplicates().shape[0]
                ),
                "target_transaction_count": int(c["target_transaction_count"].sum()),
                "signed_target_obligations": float(c["signed_target_obligations"].sum()),
                "gross_positive_target_obligations": float(
                    c["gross_positive_target_obligations"].sum()
                ),
                "target_deobligations": float(c["target_deobligations"].sum()),
                "median_clean_pre_index_latency_years": (
                    float(
                        firm_evidence.loc[
                            firm_evidence["firm_uei"].isin(set(c_clean["firm_uei"])),
                            "clean_pre_index_latency_days",
                        ].median()
                        / 365.25
                    )
                    if not c_clean.empty
                    else None
                ),
                "sbir_cohort_gross_obligation_hhi_0_10000": hhi,
                "top_1_entity_gross_obligation_share": top1,
                "top_4_entity_gross_obligation_share": top4,
            }
        )
    by_code = pd.DataFrame.from_records(code_rows)

    horizons: list[dict[str, Any]] = []
    coverage_end = pd.Timestamp(coverage_end)
    for years in (1, 3, 5, 10):
        fully_observed = anchor.notna() & (anchor + pd.DateOffset(years=years) <= coverage_end)
        loose_risk = firm_evidence.loc[
            fully_observed & anchor.ge(pd.Timestamp(ARCHIVE_COVERAGE_START))
        ].copy()
        loose_event_date = pd.to_datetime(
            loose_risk["first_post_phase_ii_positive_non_phase_i_ii_action_date"]
        )
        loose_event = loose_event_date.notna() & (
            loose_event_date
            <= pd.to_datetime(loose_risk["first_phase_ii_end"]) + pd.DateOffset(years=years)
        )
        clean_risk = firm_evidence.loc[
            fully_observed
            & firm_evidence["has_three_year_pre_index_observation"]
            & ~firm_evidence["pre_index_any_target_action"]
        ].copy()
        clean_event_date = pd.to_datetime(
            clean_risk["first_post_phase_ii_target_origin_award_date"]
        )
        clean_event = clean_event_date.notna() & (
            clean_event_date
            <= pd.to_datetime(clean_risk["first_phase_ii_end"]) + pd.DateOffset(years=years)
        )
        literal_event = clean_risk["literal_first_observed_target_entry"] & clean_event
        for estimand, risk, event in (
            (
                "post_phase_ii_positive_transaction_not_classified_phase_i_ii",
                loose_risk,
                loose_event,
            ),
            (
                "clean_pre_index_qualifying_target_origin_award_3y_coverage",
                clean_risk,
                clean_event,
            ),
            (
                "literal_first_observed_target_entry_3y_coverage",
                clean_risk,
                literal_event,
            ),
        ):
            successes = int(event.sum())
            total = len(risk)
            lower, upper = _wilson_interval(successes, total)
            horizons.append(
                {
                    "estimand": estimand,
                    "horizon_years": years,
                    "eligible_exact_uei_phase_ii_entities": total,
                    "observed_events": successes,
                    "event_rate": successes / total if total else None,
                    "wilson_95_lower": lower,
                    "wilson_95_upper": upper,
                }
            )
    horizon_table = pd.DataFrame.from_records(horizons)

    threshold_rows = []
    for estimand, flag, latency_column in (
        (
            "clean_pre_index_qualifying_target_origin_award",
            "clean_pre_index_qualifying_target_origin_award",
            "clean_pre_index_latency_days",
        ),
        (
            "literal_first_observed_target_entry",
            "literal_first_observed_target_entry",
            "literal_first_entry_latency_days",
        ),
    ):
        for threshold in (0, 1_000, 10_000, 100_000, 1_000_000):
            threshold_events = firm_evidence.loc[
                firm_evidence[flag]
                & firm_evidence[
                    "first_post_phase_ii_target_origin_award_"
                    "maximum_award_gross_positive_obligations"
                ].ge(threshold)
            ]
            threshold_rows.append(
                {
                    "estimand": estimand,
                    "minimum_first_date_award_lifetime_gross_positive_obligations": (threshold),
                    "entities": int(threshold_events["firm_uei"].nunique()),
                    "median_latency_years": (
                        float(threshold_events[latency_column].median() / 365.25)
                        if not threshold_events.empty
                        else None
                    ),
                }
            )
    threshold_table = pd.DataFrame.from_records(threshold_rows)

    for column in (
        "target_gross_positive_obligations",
        "target_signed_obligations",
        "sbir_dollars",
    ):
        firm_evidence[column] = firm_evidence[column].fillna(0.0)
    if identity_reviews is None:
        identity_reviews = pd.DataFrame(columns=[*IDENTITY_CROSSWALK_COLUMNS, "review_state"])
    identity_review_candidates = build_identity_review_candidates(
        firm_evidence,
        contracts,
        identity_reviews,
    )
    leading_entities = firm_evidence.loc[firm_evidence["has_any_target_evidence"]].sort_values(
        ["target_gross_positive_obligations", "sbir_dollars"], ascending=False
    )
    transitioners = firm_evidence.loc[
        firm_evidence["clean_pre_index_qualifying_target_origin_award"]
    ].sort_values("clean_pre_index_latency_days")
    literal_first_entry_transitioners = firm_evidence.loc[
        firm_evidence["literal_first_observed_target_entry"]
    ].sort_values("literal_first_entry_latency_days")
    sustained_transitioners = transitioners.loc[
        transitioners["has_sustained_target_procurement"]
    ].sort_values("target_gross_positive_obligations", ascending=False)

    current_8a = int(firm_evidence["active_sam_current_8a_indicator"].fillna(False).sum())
    active_sam_target = int(firm_evidence["has_active_sam_target"].sum())
    procurement_entities = firm_evidence.loc[firm_evidence["has_any_target_prime_action"]]
    high_name_continuity_entities = procurement_entities.loc[
        procurement_entities["high_name_continuity"]
    ]
    identity_reviewed = identity_review_candidates.loc[
        identity_review_candidates["review_state"].ne("unreviewed")
    ]
    identity_priority = identity_review_candidates.loc[
        identity_review_candidates["priority_review_tranche"]
    ]
    identity_candidate_dollars = float(
        identity_review_candidates["target_gross_positive_obligations"].sum()
    )
    all_target_gross_positive = float(contracts["gross_positive_target_obligations"].sum())
    summary = {
        "epistemic_tier": EPISTEMIC_TIER,
        "citable": False,
        "analysis_date": analysis_date.isoformat(),
        "procurement_coverage_start": ARCHIVE_COVERAGE_START.isoformat(),
        "procurement_data_through": coverage_end.date().isoformat(),
        "target_code_count": len(TARGET_NAICS),
        "exact_uei_sbir_entities": len(firms),
        "entities_with_any_target_evidence": int(firm_evidence["has_any_target_evidence"].sum()),
        "entities_with_active_sam_target_code": active_sam_target,
        "entities_with_active_sam_primary_target_code": int(
            firm_evidence["active_sam_primary_target"].fillna(False).sum()
        ),
        "entities_with_active_sam_target_and_current_8a_indicator": current_8a,
        "active_sam_target_entities_without_current_8a_indicator": (active_sam_target - current_8a),
        "entities_with_any_target_prime_action": int(
            firm_evidence["has_any_target_prime_action"].sum()
        ),
        "target_prime_entities_with_high_name_continuity": int(len(high_name_continuity_entities)),
        "target_prime_entities_with_low_name_continuity": int(
            len(procurement_entities) - len(high_name_continuity_entities)
        ),
        "name_continuity_review_threshold": NAME_CONTINUITY_THRESHOLD,
        "identity_review_candidate_rows": len(identity_review_candidates),
        "identity_review_candidate_entities": int(identity_review_candidates["firm_uei"].nunique()),
        "identity_review_candidate_gross_positive_obligations": identity_candidate_dollars,
        "identity_review_candidate_share_of_target_gross_positive_obligations": (
            identity_candidate_dollars / all_target_gross_positive
            if all_target_gross_positive
            else None
        ),
        "identity_review_priority_tranche_entities": int(identity_priority["firm_uei"].nunique()),
        "identity_review_priority_tranche_share_of_candidate_gross_positive_obligations": (
            float(identity_priority["target_gross_positive_obligations"].sum())
            / identity_candidate_dollars
            if identity_candidate_dollars
            else None
        ),
        "identity_reviewed_candidate_rows": len(identity_reviewed),
        "identity_reviewed_candidate_entities": int(identity_reviewed["firm_uei"].nunique()),
        "identity_reviewed_share_of_candidate_gross_positive_obligations": (
            float(identity_reviewed["target_gross_positive_obligations"].sum())
            / identity_candidate_dollars
            if identity_candidate_dollars
            else None
        ),
        "identity_review_supported_rows": int(
            identity_review_candidates["review_state"].eq("reviewed_supported").sum()
        ),
        "identity_review_unresolved_rows": int(
            identity_review_candidates["review_state"].eq("reviewed_unresolved").sum()
        ),
        "identity_review_unreviewed_rows": int(
            identity_review_candidates["review_state"].eq("unreviewed").sum()
        ),
        "identity_review_temporal_split_rows": int(
            identity_review_candidates["attribution_treatment"].eq("temporal_split_required").sum()
        ),
        "identity_review_same_entity_continuity_rows": int(
            identity_review_candidates["attribution_treatment"].eq("same_entity_continuity").sum()
        ),
        "identity_review_unresolved_attribution_rows": int(
            identity_review_candidates["attribution_treatment"]
            .eq("unresolved_exclude_from_original_firm_claims")
            .sum()
        ),
        "clean_pre_index_identity_review_candidate_entities": int(
            identity_review_candidates.loc[
                identity_review_candidates["clean_pre_index_qualifying_target_origin_award"],
                "firm_uei",
            ].nunique()
        ),
        "entities_with_positive_target_prime_obligation": int(
            firm_evidence["has_positive_target_prime_obligation"].sum()
        ),
        "entities_with_net_positive_target_prime_award_code": int(
            firm_evidence["has_net_positive_target_prime_award_code"].sum()
        ),
        "entities_with_positive_non_phase_i_ii_target_prime": int(
            firm_evidence["has_positive_non_phase_i_ii_target_prime"].sum()
        ),
        "entities_with_structural_target_origin_prime_award": int(
            firm_evidence["has_structural_target_origin_prime_award"].sum()
        ),
        "entities_with_qualifying_target_origin_prime_award": int(
            firm_evidence["has_qualifying_target_origin_prime_award"].sum()
        ),
        "entities_with_post_phase_ii_positive_transaction_not_classified_phase_i_ii": int(
            firm_evidence["first_post_phase_ii_positive_non_phase_i_ii_action_date"].notna().sum()
        ),
        "entities_with_post_phase_ii_target_origin_award": int(
            firm_evidence["first_post_phase_ii_target_origin_award_date"].notna().sum()
        ),
        "clean_pre_index_qualifying_target_origin_award_entities": int(len(transitioners)),
        "literal_first_observed_target_entry_entities": int(len(literal_first_entry_transitioners)),
        "clean_pre_index_entities_with_high_name_continuity": int(
            transitioners["high_name_continuity"].sum()
        ),
        "clean_pre_index_entities_with_sustained_target_procurement": int(
            transitioners["has_sustained_target_procurement"].sum()
        ),
        "literal_entry_entities_with_sustained_target_procurement": int(
            literal_first_entry_transitioners["has_sustained_target_procurement"].sum()
        ),
        "median_clean_pre_index_latency_years": (
            float(transitioners["clean_pre_index_latency_days"].median() / 365.25)
            if not transitioners.empty
            else None
        ),
        "median_literal_first_entry_latency_years": (
            float(
                literal_first_entry_transitioners["literal_first_entry_latency_days"].median()
                / 365.25
            )
            if not literal_first_entry_transitioners.empty
            else None
        ),
        "phase_ii_exact_uei_entities_with_usable_end": int(anchor.notna().sum()),
        "same_day_ambiguous_target_action_entities": len(same_day_entities),
        "sustained_target_procurement_entities": len(sustained_entities),
        "positive_target_phase_iii_marker_entities": int(
            positive.loc[positive["phase_iii_marker"], "firm_uei"].nunique()
        ),
        "target_prime_awards": int(
            contracts[["firm_uei", "award_group_key"]].drop_duplicates().shape[0]
        ),
        "signed_target_obligations": float(contracts["signed_target_obligations"].sum()),
        "gross_positive_target_obligations": all_target_gross_positive,
        "gross_positive_target_obligations_high_name_continuity": float(
            high_name_continuity_entities["target_gross_positive_obligations"].sum()
        ),
        "target_deobligations": float(contracts["target_deobligations"].sum()),
        "overlap_active_sam_and_any_target_prime": int(
            (
                firm_evidence["has_active_sam_target"]
                & firm_evidence["has_any_target_prime_action"]
            ).sum()
        ),
    }
    return summary, {
        "firm_evidence": firm_evidence,
        "by_code": by_code,
        "horizons": horizon_table,
        "transition_threshold_sensitivity": threshold_table,
        "leading_entities": leading_entities,
        "transitioners": transitioners,
        "literal_first_entry_transitioners": literal_first_entry_transitioners,
        "sustained_transitioners": sustained_transitioners,
        "identity_review_candidates": identity_review_candidates,
    }


def _csv_sha_manifest(output_dir: Path, tables: dict[str, pd.DataFrame]) -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for name, frame in tables.items():
        path = output_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        entries[name] = {
            "path": str(path),
            "rows": len(frame),
            "sha256": _sha256(path),
        }
    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sbir-awards", type=Path, required=True)
    parser.add_argument("--sam-public-v2", type=Path, required=True)
    parser.add_argument("--historical-contracts", type=Path, required=True)
    parser.add_argument("--recent-contracts", type=Path)
    parser.add_argument(
        "--identity-crosswalk",
        type=Path,
        default=DEFAULT_IDENTITY_CROSSWALK,
        help=("Optional tracked manual review file; absent candidate keys remain unreviewed"),
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    cohort = load_sbir_cohort(args.sbir_awards, args.as_of)
    exact_ueis = sorted(cohort.firms["firm_uei"].tolist())
    sam_result = load_sam_target_evidence(args.sam_public_v2, set(exact_ueis))
    historical = load_historical_contract_evidence(args.historical_contracts, cohort)
    contracts = historical.evidence
    recent, recent_audit = load_recent_transaction_evidence(args.recent_contracts, set(exact_ueis))
    identity_reviews, identity_review_audit = load_identity_crosswalk(args.identity_crosswalk)
    summary, tables = build_archive_analysis_tables(
        cohort,
        contracts,
        sam_result.evidence,
        recent,
        args.as_of,
        historical.coverage_end,
        identity_reviews,
    )
    review_keys = {
        tuple(row)
        for row in identity_reviews[["firm_uei", "sbir_name_key", "contract_name_key"]].itertuples(
            index=False, name=None
        )
    }
    candidate_keys = {
        tuple(row)
        for row in tables["identity_review_candidates"][
            ["firm_uei", "sbir_name_key", "contract_name_key"]
        ].itertuples(index=False, name=None)
    }
    identity_review_audit.update(
        {
            "matched_candidate_rows": len(review_keys & candidate_keys),
            "stale_or_out_of_queue_rows": len(review_keys - candidate_keys),
            "candidate_rows_without_review": len(candidate_keys - review_keys),
        }
    )
    tables.update(
        {
            "contract_evidence": contracts,
            "sam_evidence": sam_result.evidence,
            "recent_transaction_evidence": recent,
        }
    )
    output_entries = _csv_sha_manifest(args.output_dir, tables)
    summary_path = args.output_dir / "summary.json"
    _write_json(summary_path, summary)
    output_entries["summary"] = {
        "path": str(summary_path),
        "rows": 1,
        "sha256": _sha256(summary_path),
    }
    generator_path = Path(__file__).resolve()
    manifest = {
        "epistemic_tier": EPISTEMIC_TIER,
        "citable": False,
        "generated_at": datetime.now().astimezone().isoformat(),
        "as_of_date": args.as_of.isoformat(),
        "policy_source": (
            "https://legacy.sba.gov/article/2026/09/10/"
            "sba-issues-guidance-prioritize-defense-critical-firms-new-8a-program-"
            "rules-take-effect"
        ),
        "target_naics": TARGET_NAICS,
        "generator": {
            "path": str(generator_path),
            "sha256": _sha256(generator_path),
        },
        "inputs": {
            "sbir_awards": {
                "path": str(args.sbir_awards),
                "sha256": _sha256(args.sbir_awards),
            },
            "sam_public_v2": sam_result.audit,
            "recent_contracts": recent_audit,
            "historical_contracts": historical.audit,
            "identity_crosswalk": identity_review_audit,
        },
        "sbir_cohort_audit": cohort.source_audit,
        "summary": summary,
        "outputs": output_entries,
        "estimand_note": (
            "Counts are exact-UEI public-data observables. Public SAM registration, any "
            "target-coded procurement action, a positive post-Phase-II transaction not "
            "classified as Phase I/II, a first qualifying target-origin award after clean "
            "pre-index archive coverage, and literal first-observed target entry are separate "
            "estimands. None proves industry change, SBIR causation, statutory Phase III, "
            "current small-business status, or 8(a) eligibility."
            " Low name continuity is a review trigger, not proof of acquisition, novation, "
            "or successor status; missing crosswalk rows remain unreviewed."
        ),
    }
    _write_json(args.output_dir / "manifest.json", manifest)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"\nWrote exploratory outputs to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
