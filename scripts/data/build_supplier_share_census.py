#!/usr/bin/env python3
"""Build the exploratory supplier-share census.

Epistemic tier: exploratory / non-citable.

The authoritative output is one pseudonymous canonical firm by frozen grid
cell. Required venture-channel noncoverage remains indeterminate and suppresses
the headline instead of becoming a measured zero.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from sbir_analytics.assets.agency_private_capital.form_d_inputs import load_form_d_matches
from sbir_analytics.assets.phase_transition.sbir_gov_source import (
    verify_sbir_gov_materialization,
)
from sbir_etl.identity import (
    CanonicalMergePolicy,
    CompanyNameProfile,
    build_canonical_company_map,
    normalize_company_name,
)


EPISTEMIC_TIER = "exploratory"

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SBIR_PATH = REPO_ROOT / "data/processed/phase_iii_census_sbir_awards.parquet"
DEFAULT_CONTRACTS_PATH = Path(
    "/Volumes/SSDmini/sbir-analytics/data/transition/contracts_ingestion.parquet"
)
DEFAULT_FORM_D_PATH = REPO_ROOT / "data/form_d_details.jsonl"
DEFAULT_MA_PATH = REPO_ROOT / "data/enriched_sbir_ma_events.jsonl"
DEFAULT_EFTS_SCAN_PATH = REPO_ROOT / "data/sec_edgar_scan.jsonl"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data/reports/supplier_share_census"
DEFAULT_PRIVATE_SAMPLE = REPO_ROOT / "data/private/supplier_share/validation_sample.csv"

DESIGN_PATH = REPO_ROOT / "specs/supplier-share-census/design.md"
AMENDMENTS_PATH = REPO_ROOT / "specs/supplier-share-census/amendments.md"
DESIGN_SHA256 = "c14dea2a147e46b740cc46925d7a89709a45c6aedc84c5a3324e3e75528e769f"
AMENDMENTS_SHA256 = "c1a358645131ce3792cc745f56f5b5b381384d79fde62e0a8dff1d8a76620ac9"

T_VALUES = (8, 10, 12)
N_VALUES = (4, 6, 10)
WINDOW_VALUES = (12, 15)
CENTRAL_GRID = (10, 6, 15)
RANDOM_SEED = 20260821

MATRIX_CELLS = (
    "persistent_no_venture",
    "persistent_venture",
    "not_persistent_no_venture",
    "not_persistent_venture",
    "persistent_unknown_venture",
    "not_persistent_unknown_venture",
)
SAMPLE_QUOTAS = {
    "persistent_no_venture": 13,
    "persistent_venture": 13,
    "not_persistent_no_venture": 12,
    "not_persistent_venture": 12,
}
AGENCY_ORDER = ("DoD", "HHS", "NSF", "other")
IPO_FORMS = frozenset({"S-1", "S-1/A", "F-1", "F-1/A"})
MISSING_TOKENS = frozenset({"", "NAN", "NAT", "NONE", "NULL", "<NA>", r"\N"})

REQUIRED_AWARD_COLUMNS = (
    "company_name",
    "company_uei",
    "company_duns",
    "Award Year",
    "award_amount",
    "agency",
    "phase",
    "contract_end_date",
)
CLASSIFIER_COLUMNS = (
    "firm_id",
    "observation_years",
    "award_tenure_years",
    "award_count",
    "contract_persistence_fired",
    "form_d_signal",
    "form_d_searchable",
    "ma_signal",
    "ma_searchable",
    "ipo_signal",
)


@dataclass(frozen=True)
class OutputPaths:
    root: Path

    @property
    def firm_grid(self) -> Path:
        return self.root / "supplier_share_firm_grid.parquet"

    @property
    def summary(self) -> Path:
        return self.root / "supplier_share_summary.csv"

    @property
    def readout(self) -> Path:
        return self.root / "supplier_share_readout.md"

    @property
    def manifest(self) -> Path:
        return self.root / "supplier_share_manifest.json"

    @property
    def figure(self) -> Path:
        return self.root / "analysis/supplier_share_cohort_curve.svg"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.figure.parent.mkdir(parents=True, exist_ok=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sbir-awards", type=Path, default=DEFAULT_SBIR_PATH)
    parser.add_argument("--contracts", type=Path, default=DEFAULT_CONTRACTS_PATH)
    parser.add_argument("--form-d", type=Path, default=DEFAULT_FORM_D_PATH)
    parser.add_argument("--ma-events", type=Path, default=DEFAULT_MA_PATH)
    parser.add_argument("--efts-scan", type=Path, default=DEFAULT_EFTS_SCAN_PATH)
    parser.add_argument("--ipo-signals", type=Path)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--private-validation-sample", type=Path, default=DEFAULT_PRIVATE_SAMPLE)
    parser.add_argument("--as-of-year", type=int)
    parser.add_argument(
        "--contract-history-scope",
        choices=("partial_snapshot", "full_history"),
        default="partial_snapshot",
        help="Declared coverage of the supplied prime-contract materialization.",
    )
    parser.add_argument(
        "--form-d-search-complete",
        action="store_true",
        help="Assert that the supplied positive-only Form D file came from a complete denominator scan.",
    )
    parser.add_argument(
        "--ma-search-complete",
        action="store_true",
        help="Assert complete M&A search coverage when no per-firm EFTS scan artifact is supplied.",
    )
    return parser


def _clean(value: object) -> str:
    if value is None or value is pd.NA or value is pd.NaT:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if text.upper() in MISSING_TOKENS else text


def _normalized_identifier(value: object) -> str:
    return _clean(value).upper()


def _duns_digits(value: object) -> str:
    return "".join(character for character in _clean(value) if character.isdigit())


def _name_key(value: object) -> str:
    return normalize_company_name(value, profile=CompanyNameProfile.FORM_D_JOIN_V1)


def _original_firm_key(row: pd.Series) -> str:
    uei = _clean(row.get("company_uei"))
    if uei:
        return f"UEI:{uei}"
    duns = _clean(row.get("company_duns"))
    if duns:
        return f"DUNS:{duns}"
    normalized = normalize_company_name(
        row.get("company_name"), profile=CompanyNameProfile.MATCHING_V1
    )
    return f"NAME:{normalized}"


def _firm_id(firm_key: str) -> str:
    payload = f"supplier-share-v1\0{firm_key}".encode()
    return hashlib.sha256(payload).hexdigest()[:20]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_freeze() -> dict[str, str]:
    actual_design = _sha256(DESIGN_PATH)
    actual_amendments = _sha256(AMENDMENTS_PATH)
    if actual_design != DESIGN_SHA256:
        raise RuntimeError(
            f"supplier-share design SHA mismatch: expected {DESIGN_SHA256}, found {actual_design}"
        )
    if actual_amendments != AMENDMENTS_SHA256:
        raise RuntimeError(
            "supplier-share amendments SHA mismatch: "
            f"expected {AMENDMENTS_SHA256}, found {actual_amendments}"
        )
    return {
        "design_path": str(DESIGN_PATH.relative_to(REPO_ROOT)),
        "design_sha256": actual_design,
        "amendments_path": str(AMENDMENTS_PATH.relative_to(REPO_ROOT)),
        "amendments_sha256": actual_amendments,
    }


def _parse_money(value: object) -> float | None:
    text = _clean(value)
    if not text:
        return None
    normalized = re.sub(r"[^0-9.\-]", "", text)
    if normalized in {"", "-", ".", "-."}:
        return None
    try:
        return float(normalized)
    except ValueError:
        return None


def _parse_year(value: object) -> int | None:
    text = _clean(value)
    match = re.search(r"\b(?:19|20)\d{2}\b", text)
    return int(match.group()) if match else None


def _phase_ii(value: object) -> bool:
    label = _clean(value).upper().replace("PHASE", "").strip()
    return label in {"II", "2", "IIB", "2B"}


def _agency_group(value: object) -> str:
    label = _clean(value).upper()
    if "DEFENSE" in label:
        return "DoD"
    if "HEALTH AND HUMAN SERVICES" in label:
        return "HHS"
    if "NATIONAL SCIENCE FOUNDATION" in label:
        return "NSF"
    return "other"


def _award_count_stratum(count: int) -> str:
    if count == 1:
        return "1"
    if count <= 5:
        return "2-5"
    if count <= 20:
        return "6-20"
    return "21+"


def _representative_name(values: pd.Series) -> str:
    counts = Counter(_clean(value) for value in values if _clean(value))
    if not counts:
        return ""
    maximum = max(counts.values())
    return sorted(name for name, count in counts.items() if count == maximum)[0]


def _unique_lookup(pairs: list[tuple[str, str]]) -> tuple[dict[str, str], set[str]]:
    candidates: dict[str, set[str]] = defaultdict(set)
    for key, firm_key in pairs:
        if key:
            candidates[key].add(firm_key)
    unique = {key: next(iter(firms)) for key, firms in candidates.items() if len(firms) == 1}
    ambiguous = {key for key, firms in candidates.items() if len(firms) > 1}
    return unique, ambiguous


def _prepare_awards(path: Path, as_of_year: int | None) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    if not path.exists():
        raise FileNotFoundError(f"SBIR award parquet not found: {path}")
    materialized = pd.read_parquet(path)
    verify_sbir_gov_materialization(path, materialized)
    missing = sorted(set(REQUIRED_AWARD_COLUMNS) - set(materialized.columns))
    if missing:
        raise ValueError(f"SBIR award parquet missing columns: {missing}")
    awards = materialized.loc[:, list(REQUIRED_AWARD_COLUMNS)].copy()

    awards = awards.loc[awards["company_name"].map(_clean).ne("")].copy()
    canonical_map = build_canonical_company_map(awards, policy=CanonicalMergePolicy.PRELOAD_V1)
    awards["firm_original_key"] = awards.apply(_original_firm_key, axis=1)
    awards["firm_key"] = (
        awards["firm_original_key"].map(canonical_map).fillna(awards["firm_original_key"])
    )
    awards["firm_id"] = awards["firm_key"].map(_firm_id)
    awards["source_name"] = awards["company_name"].map(_clean)
    awards["source_name_exact_key"] = awards["source_name"].str.casefold()
    awards["source_name_join_key"] = awards["source_name"].map(_name_key)
    awards["award_year"] = awards["Award Year"].map(_parse_year).astype("Int64")
    invalid_year_rows = int(awards["award_year"].isna().sum())
    if invalid_year_rows:
        raise ValueError(
            f"SBIR award parquet has {invalid_year_rows:,} retained rows without a valid award year"
        )
    awards["award_amount_numeric"] = awards["award_amount"].map(_parse_money)
    awards["agency_group"] = awards["agency"].map(_agency_group)
    awards["phase_ii_explicit_end"] = pd.NaT
    phase_ii_mask = awards["phase"].map(_phase_ii)
    awards.loc[phase_ii_mask, "phase_ii_explicit_end"] = pd.to_datetime(
        awards.loc[phase_ii_mask, "contract_end_date"], errors="coerce"
    )

    valid_years = awards["award_year"].dropna().astype(int)
    resolved_as_of = as_of_year if as_of_year is not None else int(valid_years.max())
    if resolved_as_of < int(valid_years.max()):
        raise ValueError("as-of year cannot precede the maximum observed SBIR award year")

    rows: list[dict[str, Any]] = []
    for firm_key, group in awards.groupby("firm_key", sort=True):
        years = group["award_year"].dropna().astype(int)
        if years.empty:
            continue
        agency_dollars = {
            agency: float(
                group.loc[group["agency_group"].eq(agency), "award_amount_numeric"].sum(min_count=1)
            )
            for agency in AGENCY_ORDER
        }
        agency_counts = {
            agency: int(group["agency_group"].eq(agency).sum()) for agency in AGENCY_ORDER
        }
        primary_agency = sorted(
            AGENCY_ORDER,
            key=lambda agency: (
                -agency_counts[agency],
                AGENCY_ORDER.index(agency),
            ),
        )[0]
        agency_membership_block = "+".join(
            agency for agency in AGENCY_ORDER if agency_counts[agency] > 0
        )
        phase_ii_ends = group["phase_ii_explicit_end"].dropna()
        total_dollars = float(group["award_amount_numeric"].sum(min_count=1))
        rows.append(
            {
                "firm_key": firm_key,
                "firm_id": _firm_id(str(firm_key)),
                "private_firm_name": _representative_name(group["company_name"]),
                "source_name_count": int(group["source_name"].nunique()),
                "award_count": int(len(group)),
                "award_count_stratum": _award_count_stratum(int(len(group))),
                "first_award_year": int(years.min()),
                "last_award_year": int(years.max()),
                "award_tenure_years": int(years.max() - years.min()),
                "observation_years": int(resolved_as_of - years.min()),
                "cumulative_sbir_dollars": total_dollars,
                "award_amount_observed_count": int(group["award_amount_numeric"].notna().sum()),
                "first_explicit_phase_ii_end": (
                    phase_ii_ends.min() if not phase_ii_ends.empty else pd.NaT
                ),
                "primary_agency_group": primary_agency,
                "agency_membership_block": agency_membership_block,
                **{
                    f"{agency.lower()}_award_dollars": agency_dollars[agency]
                    for agency in AGENCY_ORDER
                },
                **{
                    f"{agency.lower()}_award_count": agency_counts[agency]
                    for agency in AGENCY_ORDER
                },
            }
        )
    firms = pd.DataFrame(rows).sort_values("firm_id", kind="stable").reset_index(drop=True)

    metadata = {
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "rows": int(len(awards)),
        "source_company_labels": int(awards["source_name"].nunique()),
        "canonical_firms": int(len(firms)),
        "as_of_year": resolved_as_of,
        "min_award_year": int(valid_years.min()),
        "max_award_year": int(valid_years.max()),
        "award_amount_coverage": float(awards["award_amount_numeric"].notna().mean()),
    }
    return awards, firms, metadata


def _identity_lookups(awards: pd.DataFrame) -> dict[str, Any]:
    uei_pairs: list[tuple[str, str]] = []
    duns_pairs: list[tuple[str, str]] = []
    exact_name_pairs: list[tuple[str, str]] = []
    join_name_pairs: list[tuple[str, str]] = []
    for row in awards.itertuples(index=False):
        firm_key = str(row.firm_key)
        uei_pairs.append((_normalized_identifier(row.company_uei), firm_key))
        duns_pairs.append((_duns_digits(row.company_duns), firm_key))
        exact_name_pairs.append((str(row.source_name_exact_key), firm_key))
        join_name_pairs.append((str(row.source_name_join_key), firm_key))
    uei, uei_ambiguous = _unique_lookup(uei_pairs)
    duns, duns_ambiguous = _unique_lookup(duns_pairs)
    exact_name, exact_name_ambiguous = _unique_lookup(exact_name_pairs)
    join_name, join_name_ambiguous = _unique_lookup(join_name_pairs)
    return {
        "uei": uei,
        "duns": duns,
        "exact_name": exact_name,
        "join_name": join_name,
        "ambiguous": {
            "uei": uei_ambiguous,
            "duns": duns_ambiguous,
            "exact_name": exact_name_ambiguous,
            "join_name": join_name_ambiguous,
        },
    }


def _resolve_external_firm(
    *,
    lookups: dict[str, Any],
    uei: object = None,
    duns: object = None,
    name: object = None,
) -> tuple[str | None, str]:
    uei_key = _normalized_identifier(uei)
    if uei_key:
        match = lookups["uei"].get(uei_key)
        if match:
            return match, "uei"
        if uei_key in lookups["ambiguous"]["uei"]:
            return None, "ambiguous_uei"
    duns_key = _duns_digits(duns)
    if duns_key:
        match = lookups["duns"].get(duns_key)
        if match:
            return match, "duns"
        if duns_key in lookups["ambiguous"]["duns"]:
            return None, "ambiguous_duns"
    exact_name_key = _clean(name).casefold()
    if exact_name_key:
        match = lookups["exact_name"].get(exact_name_key)
        if match:
            return match, "exact_name"
    join_key = _name_key(name)
    if join_key:
        match = lookups["join_name"].get(join_key)
        if match:
            return match, "normalized_name"
        if join_key in lookups["ambiguous"]["join_name"]:
            return None, "ambiguous_name"
    return None, "unmatched"


def _load_contract_signals(
    path: Path,
    firms: pd.DataFrame,
    lookups: dict[str, Any],
    *,
    history_scope: str,
) -> tuple[pd.DataFrame, dict]:
    result = firms.loc[:, ["firm_key", "first_explicit_phase_ii_end"]].copy()
    result["post_phase_ii_net_prime_obligations"] = 0.0
    result["post_phase_ii_contract_action_count"] = 0
    result["contract_persistence_fired"] = False
    if not path.exists():
        return result.drop(columns="first_explicit_phase_ii_end"), {
            "path": str(path),
            "available": False,
            "rows": 0,
            "history_scope": "not_available",
            "note": "No materialized prime-contract input was supplied.",
        }

    required = {
        "vendor_uei",
        "vendor_duns",
        "vendor_name",
        "action_date",
        "obligation_amount",
    }
    contracts = pd.read_parquet(path)
    missing = sorted(required - set(contracts.columns))
    if missing:
        raise ValueError(f"contract parquet missing columns: {missing}")
    anchors = result.set_index("firm_key")["first_explicit_phase_ii_end"].to_dict()
    net: defaultdict[str, float] = defaultdict(float)
    actions: Counter[str] = Counter()
    methods: Counter[str] = Counter()
    unmatched = 0
    missing_anchor = 0
    for row in contracts.itertuples(index=False):
        firm_key, method = _resolve_external_firm(
            lookups=lookups,
            uei=row.vendor_uei,
            duns=row.vendor_duns,
            name=row.vendor_name,
        )
        methods[method] += 1
        if firm_key is None:
            unmatched += 1
            continue
        anchor = anchors.get(firm_key)
        if anchor is None or pd.isna(anchor):
            missing_anchor += 1
            continue
        action_date = pd.to_datetime(row.action_date, errors="coerce")
        if pd.isna(action_date) or action_date <= anchor:
            continue
        amount = pd.to_numeric(row.obligation_amount, errors="coerce")
        if pd.isna(amount):
            continue
        net[firm_key] += float(amount)
        actions[firm_key] += 1
    result["post_phase_ii_net_prime_obligations"] = result["firm_key"].map(net).fillna(0.0)
    result["post_phase_ii_contract_action_count"] = (
        result["firm_key"].map(actions).fillna(0).astype(int)
    )
    result["contract_persistence_fired"] = result["post_phase_ii_net_prime_obligations"].gt(0)

    action_dates = pd.to_datetime(contracts["action_date"], errors="coerce")
    metadata = {
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "available": True,
        "rows": int(len(contracts)),
        "min_action_date": (
            action_dates.min().date().isoformat() if action_dates.notna().any() else None
        ),
        "max_action_date": (
            action_dates.max().date().isoformat() if action_dates.notna().any() else None
        ),
        "matched_rows_by_method": dict(sorted(methods.items())),
        "unmatched_rows": unmatched,
        "matched_rows_without_explicit_phase_ii_end": missing_anchor,
        "history_scope": history_scope,
        "source_scope": "as materialized; absence is not treated as complete contract history",
    }
    return result.drop(columns="first_explicit_phase_ii_end"), metadata


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant: {value}")


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                raise ValueError(f"blank JSONL record at {path}:{line_number}")
            try:
                value = json.loads(line, parse_constant=_reject_json_constant)
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"malformed JSON at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"non-object JSON at {path}:{line_number}")
            rows.append(value)
    return rows


def _load_form_d_signals(
    path: Path,
    firms: pd.DataFrame,
    lookups: dict[str, Any],
    *,
    search_complete: bool,
) -> tuple[pd.DataFrame, dict]:
    result = firms.loc[:, ["firm_key"]].copy()
    result["form_d_signal"] = False
    result["form_d_searchable"] = bool(search_complete and path.exists())
    if not path.exists():
        return result, {
            "path": str(path),
            "available": False,
            "search_complete_asserted": search_complete,
            "qualifying_firms": 0,
        }

    raw_rows = _jsonl_rows(path)
    tier_counts = Counter(
        _clean((row.get("match_confidence") or {}).get("tier")).lower() for row in raw_rows
    )
    matches = load_form_d_matches(path, tier_filter={"high"})
    positive: set[str] = set()
    methods: Counter[str] = Counter()
    for row in matches.itertuples(index=False):
        firm_key, method = _resolve_external_firm(
            lookups=lookups,
            name=row.company_name,
        )
        methods[method] += 1
        if firm_key:
            positive.add(firm_key)
    result["form_d_signal"] = result["firm_key"].isin(positive)
    return result, {
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "available": True,
        "search_complete_asserted": search_complete,
        "input_rows": len(raw_rows),
        "input_tier_counts": dict(sorted(tier_counts.items())),
        "qualifying_high_rows_after_existing_filters": int(len(matches)),
        "qualifying_firms": len(positive),
        "firm_attachment_methods": dict(sorted(methods.items())),
        "threshold_policy": "existing high tier only; excluded-industry filters unchanged",
    }


def _load_ma_signals(
    events_path: Path,
    scan_path: Path,
    form_d_path: Path,
    awards: pd.DataFrame,
    firms: pd.DataFrame,
    lookups: dict[str, Any],
    *,
    search_complete: bool,
) -> tuple[pd.DataFrame, dict]:
    result = firms.loc[:, ["firm_key"]].copy()
    result["ma_signal"] = False
    result["ma_searchable"] = False
    event_rows = _jsonl_rows(events_path)
    positive: set[str] = set()
    methods: Counter[str] = Counter()
    confidence_counts: Counter[str] = Counter()
    for row in event_rows:
        confidence = _clean(row.get("confidence")).lower()
        confidence_counts[confidence] += 1
        if confidence not in {"high", "medium"}:
            continue
        firm_key, method = _resolve_external_firm(
            lookups=lookups,
            name=row.get("company_name"),
        )
        methods[method] += 1
        if firm_key:
            positive.add(firm_key)
    result["ma_signal"] = result["firm_key"].isin(positive)

    scan_rows = _jsonl_rows(scan_path)
    expected_label_rows = awards.loc[:, ["source_name", "firm_key"]].drop_duplicates()
    labels_per_firm: defaultdict[str, set[str]] = defaultdict(set)
    firms_per_label: defaultdict[str, set[str]] = defaultdict(set)
    for award_row in expected_label_rows.itertuples(index=False):
        label = str(award_row.source_name)
        firm_key = str(award_row.firm_key)
        firms_per_label[label].add(firm_key)
        labels_per_firm[firm_key].add(label)

    scan_by_name: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    scan_methods: Counter[str] = Counter()
    scan_error_rows = 0
    scan_context_incomplete_rows = 0
    for row in scan_rows:
        name = _clean(row.get("company_name"))
        if not name:
            raise ValueError("EFTS scan row is missing company_name")
        scan_by_name[name].append(row)
        mention_types = set(row.get("mention_types") or [])
        context_complete = row.get("context_classification_complete")
        inferred_incomplete = context_complete is None and "filing_mention" in mention_types
        if row.get("error") or row.get("had_server_errors") or row.get("document_fetch_errors"):
            scan_error_rows += 1
        if context_complete is False or inferred_incomplete:
            scan_context_incomplete_rows += 1
        firm_key, method = _resolve_external_firm(
            lookups=lookups,
            name=name,
        )
        scan_methods[method] += 1

    clean_labels: set[str] = set()
    duplicate_scan_labels: set[str] = set()
    for label, rows in scan_by_name.items():
        if len(rows) != 1:
            duplicate_scan_labels.add(label)
            continue
        row = rows[0]
        mention_types = set(row.get("mention_types") or [])
        context_complete = row.get("context_classification_complete")
        if context_complete is None:
            context_complete = "filing_mention" not in mention_types
        if not (
            row.get("error") or row.get("had_server_errors") or row.get("document_fetch_errors")
        ) and bool(context_complete):
            clean_labels.add(label)

    signal_keys = {
        "form_d_business_combination",
        "efts_subsidiary",
        "efts_ma_definitive",
        "efts_acquisition_text",
        "efts_ma_proxy",
        "efts_ownership_active",
    }
    expected_signals: dict[str, dict[str, bool]] = {}

    def expected_for(name: str) -> dict[str, bool]:
        return expected_signals.setdefault(name, dict.fromkeys(signal_keys, False))

    for row in _jsonl_rows(form_d_path):
        name = _clean(row.get("company_name"))
        if name and any(
            bool(offering.get("is_business_combination"))
            for offering in (row.get("offerings") or [])
            if isinstance(offering, dict)
        ):
            expected_for(name)["form_d_business_combination"] = True
    efts_signal_map = {
        "subsidiary": "efts_subsidiary",
        "ma_definitive": "efts_ma_definitive",
        "acquisition": "efts_acquisition_text",
        "ma_proxy": "efts_ma_proxy",
        "ownership_active": "efts_ownership_active",
    }
    for row in scan_rows:
        name = _clean(row.get("company_name"))
        for mention_type in set(row.get("mention_types") or []):
            signal_key = efts_signal_map.get(mention_type)
            if signal_key:
                expected_for(name)[signal_key] = True

    events_by_name: dict[str, dict[str, Any]] = {}
    duplicate_event_names: set[str] = set()
    for row in event_rows:
        name = _clean(row.get("company_name"))
        if not name:
            duplicate_event_names.add("<missing>")
        elif name in events_by_name:
            duplicate_event_names.add(name)
        else:
            events_by_name[name] = row
    ambiguous_positive_labels = {
        label
        for label, firm_keys in firms_per_label.items()
        if len(firm_keys) > 1
        and _clean(events_by_name.get(label, {}).get("confidence")).lower() in {"high", "medium"}
    }
    coverage_eligible_labels = clean_labels - ambiguous_positive_labels
    covered = {
        firm_key
        for firm_key, labels in labels_per_firm.items()
        if labels and labels.issubset(coverage_eligible_labels)
    }
    signal_mismatches = 0
    confidence_mismatches = 0
    for name in set(events_by_name) & set(expected_signals):
        event = events_by_name[name]
        actual = event.get("signals") or {}
        if any(bool(actual.get(key)) != expected_signals[name][key] for key in signal_keys):
            signal_mismatches += 1
        expected = expected_signals[name]
        direction = _clean(event.get("direction")).lower()
        if expected["form_d_business_combination"] or expected["efts_subsidiary"]:
            expected_confidence = "high"
        elif expected["efts_acquisition_text"]:
            expected_confidence = "medium" if direction in {"target", "ambiguous"} else "low"
        elif expected["efts_ma_definitive"] and direction == "target":
            expected_confidence = "medium"
        else:
            expected_confidence = "low"
        if _clean(event.get("confidence")).lower() != expected_confidence:
            confidence_mismatches += 1
    derivation_consistent = bool(
        events_path.exists()
        and scan_path.exists()
        and form_d_path.exists()
        and not duplicate_event_names
        and set(events_by_name) == set(expected_signals)
        and signal_mismatches == 0
        and confidence_mismatches == 0
    )
    artifacts_complete = derivation_consistent
    if artifacts_complete:
        if search_complete:
            result["ma_searchable"] = True
        else:
            result["ma_searchable"] = result["firm_key"].isin(covered)

    metadata = {
        "events_path": str(events_path),
        "events_available": events_path.exists(),
        "events_sha256": _sha256(events_path) if events_path.exists() else None,
        "event_rows": len(event_rows),
        "event_confidence_counts": dict(sorted(confidence_counts.items())),
        "qualifying_firms": len(positive),
        "firm_attachment_methods": dict(sorted(methods.items())),
        "scan_path": str(scan_path),
        "scan_available": scan_path.exists(),
        "scan_sha256": _sha256(scan_path) if scan_path.exists() else None,
        "scan_rows": len(scan_rows),
        "scan_error_rows": scan_error_rows,
        "scan_context_incomplete_rows": scan_context_incomplete_rows,
        "scan_expected_labels": len(firms_per_label),
        "scan_clean_labels": len(clean_labels & set(firms_per_label)),
        "scan_missing_labels": len(set(firms_per_label) - set(scan_by_name)),
        "scan_unexpected_labels": len(set(scan_by_name) - set(firms_per_label)),
        "scan_duplicate_labels": len(duplicate_scan_labels),
        "scan_ambiguous_source_labels": sum(
            len(firm_keys) > 1 for firm_keys in firms_per_label.values()
        ),
        "scan_ambiguous_positive_labels": len(ambiguous_positive_labels),
        "scan_covered_firms": len(covered),
        "scan_attachment_methods": dict(sorted(scan_methods.items())),
        "derivation_consistent": derivation_consistent,
        "derivation_expected_events": len(expected_signals),
        "derivation_event_name_mismatches": len(set(events_by_name) ^ set(expected_signals)),
        "derivation_signal_mismatches": signal_mismatches,
        "derivation_confidence_mismatches": confidence_mismatches,
        "derivation_duplicate_event_names": len(duplicate_event_names),
        "derivation_form_d_sha256": _sha256(form_d_path) if form_d_path.exists() else None,
        "search_complete_asserted": search_complete,
        "threshold_policy": (
            "existing final high plus medium M&A tiers; low excluded; legacy M&A event "
            "confidence is distinct from upstream Form D entity-match confidence"
        ),
    }
    return result, metadata


def _read_optional_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".csv":
        return pd.read_csv(path, low_memory=False)
    if suffix in {".jsonl", ".ndjson"}:
        return pd.DataFrame(_jsonl_rows(path))
    raise ValueError(f"unsupported optional table format: {path}")


def _load_ipo_signals(
    path: Path | None, firms: pd.DataFrame, lookups: dict[str, Any]
) -> tuple[pd.DataFrame, dict]:
    result = firms.loc[:, ["firm_key"]].copy()
    result["ipo_signal"] = False
    if path is None or not path.exists():
        return result, {
            "path": str(path) if path else None,
            "available": False,
            "optional": True,
            "qualifying_firms": 0,
        }
    frame = _read_optional_table(path)
    name_column = next(
        (column for column in ("company_name", "issuer_name", "recipient_name") if column in frame),
        None,
    )
    uei_column = next(
        (column for column in ("uei", "company_uei", "issuer_uei") if column in frame), None
    )
    duns_column = next(
        (column for column in ("duns", "company_duns", "issuer_duns") if column in frame), None
    )
    if name_column is None and uei_column is None and duns_column is None:
        raise ValueError("IPO signal input needs a supported UEI, DUNS, or company-name column")
    form_column = next(
        (column for column in ("form", "form_type", "filing_type") if column in frame), None
    )
    if form_column is None:
        raise ValueError("IPO signal input needs form, form_type, or filing_type")
    qualifying = frame[form_column].map(lambda value: _clean(value).upper() in IPO_FORMS)
    positive: set[str] = set()
    methods: Counter[str] = Counter()
    for _, row in frame.loc[qualifying].iterrows():
        firm_key, method = _resolve_external_firm(
            lookups=lookups,
            uei=row.get(uei_column) if uei_column else None,
            duns=row.get(duns_column) if duns_column else None,
            name=row.get(name_column) if name_column else None,
        )
        methods[method] += 1
        if firm_key:
            positive.add(firm_key)
    result["ipo_signal"] = result["firm_key"].isin(positive)
    return result, {
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "available": True,
        "optional": True,
        "rows": int(len(frame)),
        "qualifying_firms": len(positive),
        "firm_attachment_methods": dict(sorted(methods.items())),
    }


def _signal_absence_reason(
    *,
    venture_signal: bool,
    mature: bool,
    form_d_searchable: bool,
    ma_searchable: bool,
) -> tuple[str, str]:
    if venture_signal:
        return "signal_present", ""
    if not mature:
        return "window_censored", "minimum_observation_window_not_met"
    missing = []
    if not form_d_searchable:
        missing.append("form_d")
    if not ma_searchable:
        missing.append("ma")
    if missing:
        return "not_searchable", "required_channels_unsearchable:" + "+".join(missing)
    return "no_filing_found", "required_channels_searched_no_qualifying_signal"


def _matrix_cell(persistent: bool, venture_state: str) -> str:
    prefix = "persistent" if persistent else "not_persistent"
    suffix = venture_state if venture_state in {"venture", "no_venture"} else "unknown_venture"
    return f"{prefix}_{suffix}"


def _validation_status(frame: pd.DataFrame) -> str:
    eligible = frame.loc[frame["headline_eligible"]]
    if eligible.empty:
        return "blocked_no_mature_cohort"
    if not eligible["required_venture_channels_searchable"].all():
        return "blocked_missing_required_signal_inputs"
    return "pending_hand_adjudication"


def _cumulative_dollar_deciles(base: pd.DataFrame, mature: pd.Series) -> pd.Series:
    deciles = pd.Series(pd.NA, index=base.index, dtype="Int64")
    ordered_index = (
        base.loc[mature]
        .sort_values(
            ["cumulative_sbir_dollars", "firm_id"],
            ascending=[False, True],
            kind="stable",
        )
        .index.tolist()
    )
    denominator = len(ordered_index)
    for rank, row_index in enumerate(ordered_index):
        deciles.at[row_index] = min(10, rank * 10 // denominator + 1)
    return deciles


def _classify_grid(classifier: pd.DataFrame) -> pd.DataFrame:
    """Assign both axes without access to dollars, agency, or review labels."""
    grids: list[pd.DataFrame] = []
    for window in WINDOW_VALUES:
        mature = classifier["observation_years"].ge(window)
        venture_signal = classifier[["form_d_signal", "ma_signal", "ipo_signal"]].any(axis=1)
        required_channels_searchable = classifier["form_d_searchable"] & classifier["ma_searchable"]
        reasons = [
            _signal_absence_reason(
                venture_signal=bool(signal),
                mature=bool(is_mature),
                form_d_searchable=bool(form_d),
                ma_searchable=bool(ma),
            )
            for signal, is_mature, form_d, ma in zip(
                venture_signal,
                mature,
                classifier["form_d_searchable"],
                classifier["ma_searchable"],
                strict=True,
            )
        ]
        reason = pd.Series((item[0] for item in reasons), index=classifier.index)
        reason_detail = pd.Series((item[1] for item in reasons), index=classifier.index)
        venture_state = pd.Series("unknown_venture", index=classifier.index)
        venture_state.loc[venture_signal] = "venture"
        venture_state.loc[reason.eq("no_filing_found")] = "no_venture"
        for tenure in T_VALUES:
            tenure_fired = classifier["award_tenure_years"].ge(tenure)
            for awards_threshold in N_VALUES:
                award_count_fired = classifier["award_count"].ge(awards_threshold)
                persistent = (
                    tenure_fired | award_count_fired | classifier["contract_persistence_fired"]
                )
                grid = classifier.loc[:, ["firm_id"]].copy()
                grid["t_years"] = tenure
                grid["n_awards"] = awards_threshold
                grid["window_years"] = window
                grid["is_central_grid"] = (tenure, awards_threshold, window) == CENTRAL_GRID
                grid["headline_eligible"] = mature
                grid["tenure_criterion_fired"] = tenure_fired
                grid["award_count_criterion_fired"] = award_count_fired
                grid["federal_persistent"] = persistent
                grid["venture_signal"] = venture_signal
                grid["required_venture_channels_searchable"] = required_channels_searchable
                grid["venture_state"] = venture_state
                grid["signal_absent_reason"] = reason
                grid["signal_absent_detail"] = reason_detail
                grid["matrix_cell"] = [
                    _matrix_cell(bool(p_value), str(v_value))
                    for p_value, v_value in zip(persistent, venture_state, strict=True)
                ]
                grid["validation_status"] = _validation_status(grid)
                grid["epistemic_tier"] = EPISTEMIC_TIER
                grid["citable"] = False
                grids.append(grid)
    return pd.concat(grids, ignore_index=True)


def _build_grid(base: pd.DataFrame) -> pd.DataFrame:
    classifier = base.loc[:, list(CLASSIFIER_COLUMNS)].copy()
    classified = _classify_grid(classifier)
    public_base = base.drop(columns=["private_firm_name", "firm_key"])
    result = classified.merge(public_base, on="firm_id", how="left", validate="many_to_one")
    result["cumulative_dollar_decile"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    for window in WINDOW_VALUES:
        mature = base["observation_years"].ge(window)
        deciles = _cumulative_dollar_deciles(base, mature)
        decile_by_firm = pd.Series(deciles.to_numpy(), index=base["firm_id"])
        mask = result["window_years"].eq(window)
        result.loc[mask, "cumulative_dollar_decile"] = (
            result.loc[mask, "firm_id"].map(decile_by_firm).astype("Int64")
        )
    result = result.sort_values(
        ["window_years", "t_years", "n_awards", "firm_id"], kind="stable"
    ).reset_index(drop=True)
    _validate_grid(result, len(base))
    return result


def _validate_grid(frame: pd.DataFrame, firm_count: int) -> None:
    expected_rows = firm_count * len(T_VALUES) * len(N_VALUES) * len(WINDOW_VALUES)
    if len(frame) != expected_rows:
        raise RuntimeError(f"grid row mismatch: expected {expected_rows}, found {len(frame)}")
    counts = frame.groupby(["t_years", "n_awards", "window_years"], sort=False).size()
    if not counts.eq(firm_count).all():
        raise RuntimeError("at least one grid cell does not contain every canonical firm")
    if not frame["matrix_cell"].isin(MATRIX_CELLS).all():
        raise RuntimeError("unknown matrix cell emitted")
    if not frame["epistemic_tier"].eq(EPISTEMIC_TIER).all() or not frame["citable"].eq(False).all():
        raise RuntimeError("grid epistemic labeling is inconsistent")
    duplicate = frame.duplicated(["firm_id", "t_years", "n_awards", "window_years"])
    if duplicate.any():
        raise RuntimeError("firm-by-grid output is not unique")


def _supplier_concentration(subset: pd.DataFrame) -> float | None:
    suppliers = subset.loc[subset["matrix_cell"].eq("persistent_no_venture")]
    denominator = suppliers["cumulative_sbir_dollars"].sum(min_count=1)
    if suppliers.empty or pd.isna(denominator) or float(denominator) <= 0:
        return None
    top_decile = suppliers.loc[suppliers["cumulative_dollar_decile"].eq(1)]
    numerator = (
        float(top_decile["cumulative_sbir_dollars"].sum(min_count=1))
        if not top_decile.empty
        else 0.0
    )
    if pd.isna(numerator):
        return None
    return numerator / float(denominator)


def _hash_rank(value: str, *, salt: str) -> str:
    return hashlib.sha256(f"{RANDOM_SEED}\0{salt}\0{value}".encode()).hexdigest()


def _placebo_supplier_share(subset: pd.DataFrame) -> float | None:
    if subset.empty or not subset["required_venture_channels_searchable"].all():
        return None
    work = subset.copy()
    work["cohort_block"] = (work["first_award_year"] // 5) * 5
    work["placebo_venture"] = False
    for (agency_block, cohort), index in work.groupby(
        ["agency_membership_block", "cohort_block"], sort=True
    ).groups.items():
        block = work.loc[index].copy()
        original = block.sort_values("firm_id", kind="stable")["venture_signal"].tolist()
        destination = sorted(
            index,
            key=lambda row_index: _hash_rank(
                str(work.at[row_index, "firm_id"]), salt=f"{agency_block}:{cohort}"
            ),
        )
        work.loc[destination, "placebo_venture"] = original
    supplier = work["federal_persistent"] & ~work["placebo_venture"]
    denominator = work["cumulative_sbir_dollars"].sum(min_count=1)
    if pd.isna(denominator) or float(denominator) <= 0:
        return None
    numerator = (
        work.loc[supplier, "cumulative_sbir_dollars"].sum(min_count=1) if supplier.any() else 0.0
    )
    if pd.isna(numerator):
        return None
    return float(numerator / denominator)


def _summary_rows(
    subset: pd.DataFrame,
    *,
    grid: tuple[int, int, int],
    stratification: str,
    stratum: str,
    scope: str,
) -> list[dict[str, Any]]:
    tenure, awards_threshold, window = grid
    total_firms = int(len(subset))
    total_dollars = float(subset["stratum_sbir_dollars"].sum(min_count=1)) if total_firms else 0.0
    has_total_dollars = bool(pd.notna(total_dollars) and total_dollars != 0)
    measurable = subset["required_venture_channels_searchable"]
    maturity_complete = bool(total_firms and subset["headline_eligible"].all())
    headline_available = bool(maturity_complete and measurable.all())
    supplier = subset["matrix_cell"].eq("persistent_no_venture")
    supplier_dollars = (
        float(subset.loc[supplier, "stratum_sbir_dollars"].sum(min_count=1))
        if supplier.any()
        else 0.0
    )
    validation_status = (
        (str(subset["validation_status"].iloc[0]) if maturity_complete else "window_censored")
        if total_firms
        else "blocked_empty_stratum"
    )
    supplier_firm_share = float(supplier.mean()) if headline_available and total_firms else None
    supplier_dollar_share = (
        float(supplier_dollars / total_dollars)
        if headline_available
        and pd.notna(total_dollars)
        and pd.notna(supplier_dollars)
        and has_total_dollars
        else None
    )
    placebo_supplier_dollar_share = (
        _placebo_supplier_share(subset) if stratification == "overall" else None
    )
    supplier_minus_placebo_dollar_share = (
        supplier_dollar_share - placebo_supplier_dollar_share
        if supplier_dollar_share is not None and placebo_supplier_dollar_share is not None
        else None
    )
    total_row = {
        "t_years": tenure,
        "n_awards": awards_threshold,
        "window_years": window,
        "is_central_grid": grid == CENTRAL_GRID,
        "stratification": stratification,
        "stratum": str(stratum),
        "scope": scope,
        "matrix_cell": "TOTAL",
        "firm_count": total_firms,
        "total_firms": total_firms,
        "firm_share": 1.0 if total_firms else None,
        "sbir_dollars": total_dollars,
        "total_sbir_dollars": total_dollars,
        "dollar_share": 1.0 if has_total_dollars else None,
        "measurable_firm_count": int(measurable.sum()),
        "measurable_firm_share": float(measurable.mean()) if total_firms else None,
        "headline_available": headline_available,
        "supplier_firm_share": supplier_firm_share,
        "supplier_dollar_share": supplier_dollar_share,
        "supplier_top_decile_dollar_share": (
            _supplier_concentration(subset)
            if stratification == "overall" and headline_available
            else None
        ),
        "placebo_supplier_dollar_share": placebo_supplier_dollar_share,
        "supplier_minus_placebo_dollar_share": supplier_minus_placebo_dollar_share,
        "validation_status": validation_status,
        "epistemic_tier": EPISTEMIC_TIER,
        "citable": False,
    }
    rows = [total_row]
    for cell in MATRIX_CELLS:
        mask = subset["matrix_cell"].eq(cell)
        dollars = (
            float(subset.loc[mask, "stratum_sbir_dollars"].sum(min_count=1)) if mask.any() else 0.0
        )
        rows.append(
            {
                **total_row,
                "matrix_cell": cell,
                "firm_count": int(mask.sum()),
                "firm_share": float(mask.sum() / total_firms) if total_firms else None,
                "sbir_dollars": dollars,
                "dollar_share": (
                    float(dollars / total_dollars)
                    if has_total_dollars and pd.notna(dollars)
                    else None
                ),
                "supplier_firm_share": None,
                "supplier_dollar_share": None,
                "supplier_top_decile_dollar_share": None,
                "placebo_supplier_dollar_share": None,
                "supplier_minus_placebo_dollar_share": None,
            }
        )
    return rows


def _build_summary(firm_grid: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for keys, grid in firm_grid.groupby(["t_years", "n_awards", "window_years"], sort=True):
        grid_key = tuple(int(value) for value in keys)
        mature = grid.loc[grid["headline_eligible"]].copy()
        mature["stratum_sbir_dollars"] = mature["cumulative_sbir_dollars"]
        rows.extend(
            _summary_rows(
                mature,
                grid=grid_key,
                stratification="overall",
                stratum="all_mature_firms",
                scope="headline_mature",
            )
        )
        for agency in AGENCY_ORDER:
            dollars_column = f"{agency.lower()}_award_dollars"
            count_column = f"{agency.lower()}_award_count"
            agency_frame = mature.loc[mature[count_column].gt(0)].copy()
            agency_frame["stratum_sbir_dollars"] = agency_frame[dollars_column]
            rows.extend(
                _summary_rows(
                    agency_frame,
                    grid=grid_key,
                    stratification="agency",
                    stratum=agency,
                    scope="headline_mature_nonexclusive_firms",
                )
            )
        for stratum in ("1", "2-5", "6-20", "21+"):
            stratum_frame = mature.loc[mature["award_count_stratum"].eq(stratum)].copy()
            stratum_frame["stratum_sbir_dollars"] = stratum_frame["cumulative_sbir_dollars"]
            rows.extend(
                _summary_rows(
                    stratum_frame,
                    grid=grid_key,
                    stratification="award_count",
                    stratum=stratum,
                    scope="headline_mature",
                )
            )
        for decile in range(1, 11):
            decile_frame = mature.loc[mature["cumulative_dollar_decile"].eq(decile)].copy()
            decile_frame["stratum_sbir_dollars"] = decile_frame["cumulative_sbir_dollars"]
            rows.extend(
                _summary_rows(
                    decile_frame,
                    grid=grid_key,
                    stratification="cumulative_dollar_decile",
                    stratum=f"D{decile:02d}",
                    scope="headline_mature",
                )
            )
        for cohort, cohort_frame in grid.groupby("first_award_year", sort=True):
            cohort_frame = cohort_frame.copy()
            cohort_frame["stratum_sbir_dollars"] = cohort_frame["cumulative_sbir_dollars"]
            rows.extend(
                _summary_rows(
                    cohort_frame,
                    grid=grid_key,
                    stratification="first_award_year",
                    stratum=str(int(cohort)),
                    scope="all_firms_in_cohort",
                )
            )
    summary = pd.DataFrame(rows)
    return summary.sort_values(
        [
            "window_years",
            "t_years",
            "n_awards",
            "stratification",
            "stratum",
            "matrix_cell",
        ],
        kind="stable",
    ).reset_index(drop=True)


def _validate_summary(firm_grid: pd.DataFrame, summary: pd.DataFrame) -> None:
    """Reconcile matrix cells and every declared summary denominator."""

    def close(left: float, right: float) -> bool:
        if pd.isna(left) or pd.isna(right):
            return bool(pd.isna(left) and pd.isna(right))
        return math.isclose(left, right, rel_tol=1e-9, abs_tol=max(1.0, abs(right) * 1e-9))

    def summary_dollars(frame: pd.DataFrame) -> float:
        populated = frame.loc[frame["firm_count"].gt(0), "sbir_dollars"]
        return float(populated.sum(min_count=1)) if not populated.empty else 0.0

    grouping = ["t_years", "n_awards", "window_years", "stratification", "stratum"]
    for keys, group in summary.groupby(grouping, sort=False, dropna=False):
        total = group.loc[group["matrix_cell"].eq("TOTAL")]
        if len(total) != 1:
            raise RuntimeError(f"summary total missing or duplicated: {keys}")
        cells = group.loc[~group["matrix_cell"].eq("TOTAL")]
        row = total.iloc[0]
        if int(cells["firm_count"].sum()) != int(row["total_firms"]):
            raise RuntimeError(f"summary firm cells do not reconcile: {keys}")
        if not close(summary_dollars(cells), float(row["total_sbir_dollars"])):
            raise RuntimeError(f"summary dollar cells do not reconcile: {keys}")

    for keys, grid in firm_grid.groupby(["t_years", "n_awards", "window_years"], sort=False):
        totals = summary.loc[
            summary["t_years"].eq(keys[0])
            & summary["n_awards"].eq(keys[1])
            & summary["window_years"].eq(keys[2])
            & summary["matrix_cell"].eq("TOTAL")
        ]
        overall = totals.loc[totals["stratification"].eq("overall")]
        if len(overall) != 1:
            raise RuntimeError(f"overall summary total missing or duplicated: {keys}")
        overall_row = overall.iloc[0]
        mature = grid.loc[grid["headline_eligible"]]
        if int(overall_row["total_firms"]) != len(mature):
            raise RuntimeError(f"overall mature firm count does not reconcile: {keys}")

        for stratification in ("award_count", "cumulative_dollar_decile"):
            partition = totals.loc[totals["stratification"].eq(stratification)]
            if int(partition["firm_count"].sum()) != len(mature):
                raise RuntimeError(f"{stratification} firm partition does not reconcile: {keys}")
            if not close(
                summary_dollars(partition),
                float(overall_row["total_sbir_dollars"]),
            ):
                raise RuntimeError(f"{stratification} dollars do not reconcile: {keys}")

        agency = totals.loc[totals["stratification"].eq("agency")]
        if not close(
            summary_dollars(agency),
            float(overall_row["total_sbir_dollars"]),
        ):
            raise RuntimeError(f"agency dollars do not reconcile: {keys}")

        cohorts = totals.loc[totals["stratification"].eq("first_award_year")]
        if int(cohorts["firm_count"].sum()) != len(grid):
            raise RuntimeError(f"cohort firm partition does not reconcile: {keys}")
        if not close(
            summary_dollars(cohorts),
            float(grid["cumulative_sbir_dollars"].sum(min_count=1)),
        ):
            raise RuntimeError(f"cohort dollars do not reconcile: {keys}")


def _write_validation_sample(base: pd.DataFrame, firm_grid: pd.DataFrame, path: Path) -> bool:
    central = firm_grid.loc[
        firm_grid["t_years"].eq(CENTRAL_GRID[0])
        & firm_grid["n_awards"].eq(CENTRAL_GRID[1])
        & firm_grid["window_years"].eq(CENTRAL_GRID[2])
        & firm_grid["headline_eligible"]
    ]
    if central.empty or not central["required_venture_channels_searchable"].all():
        return False
    private = central.merge(
        base[["firm_id", "private_firm_name"]], on="firm_id", how="left", validate="one_to_one"
    )
    selected: list[pd.DataFrame] = []
    ranked_by_cell: dict[str, pd.DataFrame] = {}
    remainder = 0
    for cell in SAMPLE_QUOTAS:
        candidates = private.loc[private["matrix_cell"].eq(cell)].copy()
        candidates["sample_rank"] = candidates["firm_id"].map(
            lambda value, cell=cell: _hash_rank(str(value), salt=f"sample:{cell}")
        )
        candidates = candidates.sort_values(["sample_rank", "firm_id"], kind="stable")
        ranked_by_cell[cell] = candidates
        take = min(SAMPLE_QUOTAS[cell], len(candidates))
        selected.append(candidates.head(take))
        remainder += SAMPLE_QUOTAS[cell] - take
    if remainder:
        chosen_ids = {value for frame in selected for value in frame["firm_id"]}
        for cell in SAMPLE_QUOTAS:
            pool = ranked_by_cell[cell].loc[~ranked_by_cell[cell]["firm_id"].isin(chosen_ids)]
            extra = pool.head(remainder)
            selected.append(extra)
            chosen_ids.update(extra["firm_id"])
            remainder -= len(extra)
            if remainder == 0:
                break
    sample = pd.concat(selected, ignore_index=True).head(50)
    columns = [
        "firm_id",
        "private_firm_name",
        "matrix_cell",
        "first_award_year",
        "last_award_year",
        "award_count",
        "cumulative_sbir_dollars",
        "form_d_signal",
        "ma_signal",
        "ipo_signal",
        "contract_persistence_fired",
        "validation_status",
        "epistemic_tier",
        "citable",
        "sample_rank",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    sample.loc[:, columns].to_csv(path, index=False)
    return True


def _format_pct(value: object, *, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "suppressed"
    return f"{100 * float(value):.{digits}f}%"


def _format_money(value: object) -> str:
    if value is None or pd.isna(value):
        return "suppressed"
    return f"${float(value):,.0f}"


def _write_figure(summary: pd.DataFrame, *, as_of_year: int, path: Path) -> None:
    cohort_totals = summary.loc[
        summary["stratification"].eq("first_award_year")
        & summary["matrix_cell"].eq("TOTAL")
        & summary["window_years"].eq(15)
    ].copy()
    cohort_totals["cohort"] = pd.to_numeric(cohort_totals["stratum"], errors="coerce")
    cohort_totals = cohort_totals.loc[cohort_totals["cohort"].notna()]
    central = cohort_totals.loc[
        cohort_totals["t_years"].eq(CENTRAL_GRID[0]) & cohort_totals["n_awards"].eq(CENTRAL_GRID[1])
    ].sort_values("cohort")

    width, height = 1200, 620
    left, right, top, bottom = 95, 1140, 90, 520
    if central.empty or central["supplier_dollar_share"].notna().sum() == 0:
        message = (
            "Supplier-cell cohort curve suppressed: required Form D/EFTS search coverage "
            "is unavailable."
        )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
<rect width="100%" height="100%" fill="#f4f1e8"/>
<text x="600" y="62" text-anchor="middle" font-family="Georgia, serif" font-size="28" fill="#17211b">Supplier-Cell Dollar Share by First-Award Cohort</text>
<text x="600" y="290" text-anchor="middle" font-family="Menlo, monospace" font-size="17" fill="#8b2d2d">{message}</text>
<text x="600" y="330" text-anchor="middle" font-family="Menlo, monospace" font-size="13" fill="#465148">Exploratory / non-citable. Missing signals are indeterminate, not zero.</text>
</svg>'''
        path.write_text(svg, encoding="utf-8")
        return

    measurable = cohort_totals.loc[cohort_totals["supplier_dollar_share"].notna()].copy()
    envelope = measurable.groupby("cohort")["supplier_dollar_share"].agg(["min", "max"])
    central = central.loc[central["supplier_dollar_share"].notna()]
    min_year = int(measurable["cohort"].min())
    max_year = max(int(measurable["cohort"].max()), as_of_year - min(WINDOW_VALUES))
    max_share = max(float(measurable["supplier_dollar_share"].max()), 0.01)

    def x(year: float) -> float:
        span = max(max_year - min_year, 1)
        return left + (year - min_year) / span * (right - left)

    def y(share: float) -> float:
        return bottom - share / max_share * (bottom - top)

    envelope_points = [f"{x(year):.1f},{y(row['max']):.1f}" for year, row in envelope.iterrows()]
    envelope_points += [
        f"{x(year):.1f},{y(row['min']):.1f}" for year, row in reversed(list(envelope.iterrows()))
    ]
    line_points = " ".join(
        f"{x(row.cohort):.1f},{y(row.supplier_dollar_share):.1f}"
        for row in central.itertuples(index=False)
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">',
        '<rect width="100%" height="100%" fill="#f4f1e8"/>',
        '<text x="600" y="42" text-anchor="middle" font-family="Georgia, serif" font-size="28" fill="#17211b">Supplier-Cell Dollar Share by First-Award Cohort</text>',
        '<text x="600" y="68" text-anchor="middle" font-family="Menlo, monospace" font-size="12" fill="#465148">Central T=10 / N=6; shaded range spans all frozen T/N cells at the 15-year gate</text>',
        f'<line x1="{left}" y1="{bottom}" x2="{right}" y2="{bottom}" stroke="#17211b"/>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{bottom}" stroke="#17211b"/>',
        f'<polygon points="{" ".join(envelope_points)}" fill="#c7883b" opacity="0.25"/>',
        f'<polyline points="{line_points}" fill="none" stroke="#1f5b45" stroke-width="3"/>',
    ]
    for tick in range(6):
        share = max_share * tick / 5
        tick_y = y(share)
        parts.append(
            f'<text x="{left - 12}" y="{tick_y + 4:.1f}" text-anchor="end" font-family="Menlo, monospace" font-size="11" fill="#465148">{100 * share:.0f}%</text>'
        )
    for year in range(min_year, max_year + 1, max(1, math.ceil((max_year - min_year) / 8))):
        parts.append(
            f'<text x="{x(year):.1f}" y="{bottom + 25}" text-anchor="middle" font-family="Menlo, monospace" font-size="11" fill="#465148">{year}</text>'
        )
    for window, color in ((15, "#8b2d2d"), (12, "#355a91")):
        cutoff = as_of_year - window
        if min_year <= cutoff <= max_year:
            cutoff_x = x(cutoff)
            parts.append(
                f'<line x1="{cutoff_x:.1f}" y1="{top}" x2="{cutoff_x:.1f}" y2="{bottom}" stroke="{color}" stroke-dasharray="6 4"/>'
            )
            parts.append(
                f'<text x="{cutoff_x - 5:.1f}" y="{top + 16}" text-anchor="end" font-family="Menlo, monospace" font-size="11" fill="{color}">{window}-year cutoff</text>'
            )
    parts.extend(
        [
            '<text x="600" y="590" text-anchor="middle" font-family="Menlo, monospace" font-size="12" fill="#465148">Exploratory / non-citable. Annual cohorts expose censoring and source-coverage gradients.</text>',
            "</svg>",
        ]
    )
    path.write_text("\n".join(parts), encoding="utf-8")


def _render_readout(
    *,
    manifest: dict,
    summary: pd.DataFrame,
    validation_sample_written: bool,
) -> str:
    central = summary.loc[
        summary["t_years"].eq(CENTRAL_GRID[0])
        & summary["n_awards"].eq(CENTRAL_GRID[1])
        & summary["window_years"].eq(CENTRAL_GRID[2])
        & summary["stratification"].eq("overall")
        & summary["matrix_cell"].eq("TOTAL")
    ].iloc[0]
    lines = [
        "# Supplier-Share Of The SBIR/STTR Portfolio",
        "",
        "**EXPLORATORY / NON-CITABLE. Candidate assertions only.**",
        "",
        "## Neutral definition",
        "",
        "A **sustained federal performer** is a canonical SBIR/STTR firm envelope with at least ",
        "one observed federal-persistence criterion and no observed venture signal, where both ",
        "required venture channels were searchable. This is a descriptive record classification, ",
        "not a causal claim or a judgment about commercialization quality, dependence, or intent.",
        "",
        "**Declared estimand:** For each frozen grid cell, among canonical firms whose first ",
        "observed award is at least the configured window before the as-of year, report the ",
        "firm share and cumulative observed SBIR/STTR dollar share in every persistence x ",
        "venture-signal cell. Firm dollars include all observed awards through the data cut.",
        "",
        "## Frozen criteria",
        "",
        "- Identity: `CanonicalMergePolicy.PRELOAD_V1`; UEI primary, DUNS fallback, unique existing normalized-name alias last; no new fuzzy matching.",
        "- Persistence: award tenure >= T OR observed award count >= N OR positive net prime obligations after an explicit Phase II completion date.",
        "- Venture signal: existing high-confidence Form D OR existing high/medium M&A OR optional supplied IPO registration statement.",
        "- Grid: `T={8,10,12}`, `N={4,6,10}`, minimum observation window `{12,15}`; central cell `(10,6,15)`.",
        "- Window: a maturity gate, not follow-up truncation. Cumulative dollars use all observed awards through the data cut.",
        "- Required-channel noncoverage is `not_searchable`, never no venture signal.",
        "",
        "## Source and identity reconciliation",
        "",
        f"- Materialized award rows: {manifest['inputs']['sbir_awards']['rows']:,}",
        f"- Exact nonblank source-company labels: {manifest['inputs']['sbir_awards']['source_company_labels']:,}",
        f"- Canonical firm envelopes: {manifest['inputs']['sbir_awards']['canonical_firms']:,}",
        f"- Award years: {manifest['inputs']['sbir_awards']['min_award_year']}-{manifest['inputs']['sbir_awards']['max_award_year']}",
        "- Award-amount coverage: "
        f"{_format_pct(manifest['inputs']['sbir_awards']['award_amount_coverage'], digits=2)}",
        f"- Contract source available: {manifest['inputs']['contracts']['available']}",
        f"- Contract history scope: `{manifest['inputs']['contracts']['history_scope']}`",
        f"- Form D source available / complete assertion: {manifest['inputs']['form_d']['available']} / {manifest['inputs']['form_d'].get('search_complete_asserted', False)}",
        f"- M&A source available / scan available: {manifest['inputs']['ma']['events_available']} / {manifest['inputs']['ma']['scan_available']}",
        f"- M&A event/scan derivation consistent: {manifest['inputs']['ma']['derivation_consistent']}",
        "",
        "## Central-cell result",
        "",
    ]
    if bool(central["headline_available"]):
        lines.extend(
            [
                f"- Mature firms: {int(central['total_firms']):,}",
                f"- Persistent + no-observed-venture firm share: {_format_pct(central['supplier_firm_share'])}",
                f"- Persistent + no-observed-venture cumulative-dollar share: {_format_pct(central['supplier_dollar_share'])}",
                f"- Supplier-cell dollars contributed by denominator decile D01: {_format_pct(central['supplier_top_decile_dollar_share'])}",
                f"- Blocked-permutation supplier-dollar share: {_format_pct(central['placebo_supplier_dollar_share'])}",
                f"- Observed minus blocked-permutation share: {_format_pct(central['supplier_minus_placebo_dollar_share'])}",
            ]
        )
    else:
        lines.extend(
            [
                "**Headline suppressed.** Required Form D/EFTS coverage is incomplete for the ",
                "mature denominator. Firms without positive records are indeterminate, not ",
                "classified as no-venture-signal.",
                "",
                f"- Mature firms: {int(central['total_firms']):,}",
                f"- Venture-measurable firms: {int(central['measurable_firm_count']):,} ({_format_pct(central['measurable_firm_share'])})",
            ]
        )
    lines.extend(
        [
            "",
            "## Grid status",
            "",
            "| T | N | Window | Mature firms | Measurable | Supplier firm share | Supplier dollar share | Status |",
            "|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    grid_rows = summary.loc[
        summary["stratification"].eq("overall") & summary["matrix_cell"].eq("TOTAL")
    ].sort_values(["window_years", "t_years", "n_awards"])
    for row in grid_rows.itertuples(index=False):
        lines.append(
            f"| {row.t_years} | {row.n_awards} | {row.window_years} | {row.total_firms:,} | "
            f"{_format_pct(row.measurable_firm_share)} | {_format_pct(row.supplier_firm_share)} | "
            f"{_format_pct(row.supplier_dollar_share)} | `{row.validation_status}` |"
        )
    lines.extend(
        [
            "",
            "## Validation gates",
            "",
            f"- Current status: `{central['validation_status']}`.",
            f"- Private 50-firm sample emitted: {validation_sample_written}.",
            "- Hand-adjudication agreement: not run.",
            "- Face-validity anchors: not supplied or run.",
            (
                "- Blocked permutation diagnostic: reported above; no pass threshold is frozen."
                if bool(central["headline_available"])
                else "- Blocked permutation diagnostic: unavailable until the required venture axis is measurable; no pass threshold is frozen."
            ),
            "- `citable=false` remains mandatory even after exploratory gates pass; promotion is separate work.",
            "",
            "## Stratification semantics",
            "",
            "Agency dollar rows retain each award's source agency. A cross-agency firm can appear in multiple agency firm counts, so agency firm counts are non-additive. Award-count strata use full-history row counts. Cumulative-dollar deciles rank all mature firms by cumulative observed SBIR/STTR dollars with deterministic ties; the top-decile statistic is the share of supplier-cell dollars contributed by denominator decile D01. It is not an HHI or a product-market concentration measure.",
            "",
            "## Naming options",
            "",
            "| Label | Connotation and caution |",
            "|---|---|",
            "| Sustained federal performers | Preferred neutral label; observed persistence without claiming dependence or intent |",
            "| Mission suppliers | Emphasizes capability delivery; can overstate operational mission linkage |",
            "| Federal R&D incumbents | Conveys tenure; can imply market power not measured here |",
            "| Supplier-track awardees | Contrasts venture branding; `track` can imply a chosen strategy |",
            "| Federal-continuity firms | Mechanically accurate but abstract; does not imply commercial failure |",
            "",
            '**Dual-reading caution:** A large persistent-no-venture share can be read as a durable federal R&D supplier base. The same number can be described pejoratively as a "mills share." The classifier supports neither value judgment.',
            "",
            "## Limitations",
            "",
            "- FPDS/USAspending sees primes only; sub-tier supply to primes is invisible, so observed federal continuation is understated.",
            "- Coded Phase III undercounts actual Phase III, in the same direction.",
            "- Form D absence is not absence of capital. Bootstrapped growth, debt, revenue growth, unmatched private offerings, and non-Reg-D capital are invisible, which can overstate the no-venture cell.",
            "- The legacy M&A detector's event-confidence tier is distinct from Form D entity-match confidence: a business-combination filing makes an M&A event high-confidence even when the underlying Form D name link is medium or low. This channel requires hand review before citation.",
            "- Form D/EFTS coverage varies over time. Young cohorts are right-censored; old cohorts can be left-censored by electronic filing coverage.",
            "- Award-time identity is not current corporate identity; acquisitions, successors, affiliates, and aliases can split or combine apparent firms.",
            "- First observed SBIR/STTR award is only the cohort anchor; the data do not establish that a firm had no earlier federal work.",
            "- Cumulative dollars are nominal observed award amounts, not inflation-adjusted obligations or firm revenue.",
            "- Federal-continuation undercount and venture-signal undercount work in opposite directions. Net bias is ambiguous.",
            "",
            "## Governance",
            "",
            "Parquet is authoritative. These are candidate assertions only, with no new causal edges. If this work graduates, it requires a separate evidence study contract, input SHA enforcement, blocking checks, completed validation, and explicit promotion.",
            "",
        ]
    )
    return "\n".join(lines)


def run(args: argparse.Namespace) -> dict[str, Any]:
    freeze = _verify_freeze()
    paths = OutputPaths(args.output_dir)
    paths.ensure()

    awards, firms, sbir_meta = _prepare_awards(args.sbir_awards, args.as_of_year)
    lookups = _identity_lookups(awards)
    contract_signals, contracts_meta = _load_contract_signals(
        args.contracts,
        firms,
        lookups,
        history_scope=args.contract_history_scope,
    )
    form_d_signals, form_d_meta = _load_form_d_signals(
        args.form_d,
        firms,
        lookups,
        search_complete=args.form_d_search_complete,
    )
    ma_signals, ma_meta = _load_ma_signals(
        args.ma_events,
        args.efts_scan,
        args.form_d,
        awards,
        firms,
        lookups,
        search_complete=args.ma_search_complete,
    )
    ipo_signals, ipo_meta = _load_ipo_signals(args.ipo_signals, firms, lookups)

    base = firms.merge(contract_signals, on="firm_key", how="left", validate="one_to_one")
    base = base.merge(form_d_signals, on="firm_key", how="left", validate="one_to_one")
    base = base.merge(ma_signals, on="firm_key", how="left", validate="one_to_one")
    base = base.merge(ipo_signals, on="firm_key", how="left", validate="one_to_one")
    firm_grid = _build_grid(base)
    firm_grid["as_of_year"] = sbir_meta["as_of_year"]
    provenance = {
        "sbir_source_sha256": sbir_meta["sha256"],
        "contract_source_sha256": contracts_meta.get("sha256"),
        "form_d_source_sha256": form_d_meta.get("sha256"),
        "ma_events_source_sha256": ma_meta.get("events_sha256"),
        "ma_scan_source_sha256": ma_meta.get("scan_sha256"),
        "ipo_source_sha256": ipo_meta.get("sha256"),
    }
    for column, value in provenance.items():
        firm_grid[column] = pd.Series(value, index=firm_grid.index, dtype="string")
    summary = _build_summary(firm_grid)
    _validate_summary(firm_grid, summary)
    validation_sample_written = _write_validation_sample(
        base, firm_grid, args.private_validation_sample
    )

    manifest = {
        "schema_version": "supplier-share-census-v1",
        "epistemic_tier": EPISTEMIC_TIER,
        "citable": False,
        "spec_freeze": freeze,
        "grid": {
            "t_years": list(T_VALUES),
            "n_awards": list(N_VALUES),
            "window_years": list(WINDOW_VALUES),
            "central": list(CENTRAL_GRID),
            "random_seed": RANDOM_SEED,
        },
        "inputs": {
            "sbir_awards": sbir_meta,
            "contracts": contracts_meta,
            "form_d": form_d_meta,
            "ma": ma_meta,
            "ipo": ipo_meta,
        },
        "outputs": {
            "firm_grid": str(paths.firm_grid),
            "summary": str(paths.summary),
            "figure": str(paths.figure),
            "readout": str(paths.readout),
            "private_validation_sample": (
                str(args.private_validation_sample) if validation_sample_written else None
            ),
            "private_validation_sample_sha256": (
                _sha256(args.private_validation_sample) if validation_sample_written else None
            ),
        },
        "validation": {
            "status": str(firm_grid["validation_status"].mode().iloc[0]),
            "hand_adjudication": "not_run",
            "anchors": "not_run",
            "negative_control": "reported_only_when_axis_measurable",
        },
    }

    firm_grid.to_parquet(paths.firm_grid, index=False)
    summary.to_csv(paths.summary, index=False, na_rep="", float_format="%.10g")
    _write_figure(summary, as_of_year=sbir_meta["as_of_year"], path=paths.figure)
    paths.readout.write_text(
        _render_readout(
            manifest=manifest,
            summary=summary,
            validation_sample_written=validation_sample_written,
        ),
        encoding="utf-8",
    )
    manifest["outputs"]["firm_grid_sha256"] = _sha256(paths.firm_grid)
    manifest["outputs"]["summary_sha256"] = _sha256(paths.summary)
    manifest["outputs"]["figure_sha256"] = _sha256(paths.figure)
    manifest["outputs"]["readout_sha256"] = _sha256(paths.readout)
    paths.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    args = _parser().parse_args()
    manifest = run(args)
    sbir_meta = manifest["inputs"]["sbir_awards"]
    print(
        "Supplier-share census complete: "
        f"{sbir_meta['source_company_labels']:,} source labels -> "
        f"{sbir_meta['canonical_firms']:,} canonical firms"
    )
    print(f"Validation status: {manifest['validation']['status']}")
    print(f"Readout: {manifest['outputs']['readout']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
