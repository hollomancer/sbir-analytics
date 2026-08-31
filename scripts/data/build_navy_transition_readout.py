"""Build the exploratory Navy Phase III transition readout.

This is a filter-and-report adapter over the canonical SBIR.gov input, the
phase-transition pairing helpers, the historical Phase III award-key helper,
and the existing Form D / EDGAR match artifacts.  It emits aggregate evidence
only: no firm names or row-level matched records leave the process.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections.abc import Iterable, Sequence
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from sbir_analytics.assets.agency_private_capital.form_d_inputs import (  # noqa: E402
    normalize_name,
    read_jsonl,
)
from sbir_analytics.assets.phase_transition.pairs import (  # noqa: E402
    _build_pairs,
    _build_survival,
)
from sbir_analytics.assets.phase_transition.phase_ii import (  # noqa: E402
    _prepare_sbir_gov_rows,
)
from sbir_analytics.assets.phase_transition.phase_iii import (  # noqa: E402
    _prepare_phase_iii_rows,
)
from scripts.phase3_benchmark.undercount_award_grain import (  # noqa: E402
    reconstruct_coded_award_key,
)


DEFAULT_SBIR = Path("data/processed/phase_iii_census_sbir_awards.parquet")
DEFAULT_SBIR_CHECKS = Path("data/processed/phase_iii_census_sbir_awards.checks.json")
DEFAULT_FORM_D = Path("data/form_d_details.jsonl")
DEFAULT_MA_EVENTS = Path("data/sbir_ma_events.jsonl")
DEFAULT_MARKDOWN = Path("docs/readouts/navy-transition-v1.md")
DEFAULT_SUMMARY = Path("docs/readouts/navy-transition-v1.summary.json")
DEFAULT_FIGURES = Path("docs/readouts/figures")

NAVY_AGENCY = "Department of Defense"
NAVY_BRANCH = "Navy"
NAVY_CODE = "1700"
PHASE_CODES = {"SR3", "ST3"}
MATCH_TIERS = {"high", "medium"}
TIER_RANK = {"medium": 1, "high": 2}
HISTORICAL_DOD_COMPARATOR = {
    "status": "historical_unreproduced",
    "filter": (
        "FY2016-FY2025, DoD department 9700, FPDS Element 10Q SR3/ST3, "
        "latest coded action per compound award key"
    ),
    "award_n": 6_351,
    "firm_n": 1_487,
    "description_median_chars": 42,
    "description_median_status": (
        "legacy documentation says 42; current tracked prose says 43; no committed generator"
    ),
    "conflicting_tracked_prose_median_chars": 43,
    "description_ge_40_rate": 0.536,
    "description_lt_150_rate": 0.885,
    "description_ge_150_rate": 0.115,
    "description_ge_900_rate": 0.0,
    "source_refs": [
        "git:d844f2b0:scripts/phase3_benchmark/m0a_coded_pull.py",
        "git:48f13305:scripts/phase3_benchmark/dod_within_retrieval.py",
        "git:e51574be:specs/phase3-match-benchmark/eval-validity.md",
        "repo:specs/phase3-match-benchmark/mse-dark-phase3.md",
    ],
}


def _plotting_module() -> Any:
    """Import the notebook-only plotting dependency only when figures are requested."""

    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "figure generation requires the repository's `notebooks` dependency group"
        ) from exc
    return plt


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def _series(frame: pd.DataFrame, *names: str) -> pd.Series:
    for name in names:
        if name in frame.columns:
            return frame[name]
    return pd.Series([None] * len(frame), index=frame.index, dtype="object")


def _clean_text(values: pd.Series) -> pd.Series:
    return values.fillna("").astype(str).str.strip()


def _fiscal_year(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    years = parsed.dt.year + parsed.dt.month.ge(10).astype("Int64")
    return years.astype("Int64")


def _percent(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _tier(value: object) -> str:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in MATCH_TIERS else ""


def _best_tier_by_firm(pairs: Iterable[tuple[str, str]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for firm_key, tier in pairs:
        if not firm_key or tier not in MATCH_TIERS:
            continue
        if TIER_RANK[tier] > TIER_RANK.get(result.get(firm_key, ""), 0):
            result[firm_key] = tier
    return result


def _agency_is_navy(frame: pd.DataFrame, field: str) -> pd.Series:
    candidates = [
        _clean_text(_series(frame, field)).str.upper(),
        _clean_text(_series(frame, f"{field}_name", f"{field}_description")).str.upper(),
    ]
    result = pd.Series(False, index=frame.index)
    for values in candidates:
        result |= values.eq(NAVY_CODE)
        result |= values.str.startswith(f"{NAVY_CODE} ")
        result |= values.str.startswith(f"{NAVY_CODE}:")
        result |= values.isin({"DEPARTMENT OF THE NAVY", "DEPT OF THE NAVY"})
    return result


def load_coded_inputs(
    parquet_manifest_pairs: Sequence[tuple[Path, Path]],
    data_cut: date,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Load complete, query-scoped FPDS pulls and retain compact provenance."""

    if len(parquet_manifest_pairs) != 4:
        raise ValueError("exactly four SR3/ST3 x DoN-awarding/funding pulls are required")

    frames: list[pd.DataFrame] = []
    provenance: list[dict[str, Any]] = []
    seen_scopes: set[tuple[str, str]] = set()
    required_common_terms = {
        f"SIGNED_DATE:[1980/10/01,{data_cut:%Y/%m/%d}]",
        'CONTRACT_TYPE:"AWARD"',
    }
    role_terms = {
        "awarding": 'CONTRACTING_AGENCY_ID:"1700"',
        "funding": 'FUNDING_AGENCY_ID:"1700"',
    }
    for parquet_path, manifest_path in parquet_manifest_pairs:
        manifest = _read_json(manifest_path)
        if manifest.get("retrieval_complete") is not True:
            raise ValueError(f"FPDS retrieval is incomplete: {manifest_path}")
        parameters = manifest.get("parameters") or {}
        code = str(parameters.get("research_code") or "").upper()
        terms = [str(term) for term in parameters.get("query_terms") or []]
        matched_roles = [role for role, term in role_terms.items() if term in terms]
        if code not in PHASE_CODES or len(matched_roles) != 1:
            raise ValueError(f"FPDS manifest has an invalid code/agency role: {manifest_path}")
        role = matched_roles[0]
        expected_terms = required_common_terms | {role_terms[role]}
        if set(terms) != expected_terms or len(terms) != len(expected_terms):
            raise ValueError(f"FPDS manifest has unexpected query terms: {manifest_path}")
        query = str(manifest.get("query") or "")
        if query != " ".join((f"RESEARCH:{code}", *terms)):
            raise ValueError(
                f"FPDS manifest query disagrees with structured parameters: {manifest_path}"
            )
        scope = (code, role)
        if scope in seen_scopes:
            raise ValueError(f"duplicate FPDS code/role scope {scope}: {manifest_path}")
        seen_scopes.add(scope)
        frame = pd.read_parquet(parquet_path)
        if int(manifest.get("row_count", -1)) != len(frame):
            raise ValueError(f"FPDS manifest row count disagrees with {parquet_path}")
        parsed_code = _clean_text(_series(frame, "_research_code")).str.upper()
        source_code = _clean_text(_series(frame, "research")).str.upper()
        if not parsed_code.eq(code).all() or not source_code.eq(code).all():
            raise ValueError(f"FPDS row research code disagrees with {manifest_path}")
        frame = frame.copy()
        frame["_source_query"] = query
        frames.append(frame)
        provenance.append(
            {
                "file": parquet_path.name,
                "sha256": _sha256(parquet_path),
                "manifest_file": manifest_path.name,
                "manifest_sha256": _sha256(manifest_path),
                "query": query,
                "retrieved_at": manifest.get("retrieved_at"),
                "reported_total_results": manifest.get("reported_total_results"),
                "row_count": len(frame),
                "raw_pages_sha256": manifest.get("raw_pages_sha256"),
                "retrieval_complete": True,
            }
        )

    expected_scopes = {(code, role) for code in PHASE_CODES for role in role_terms}
    if seen_scopes != expected_scopes:
        raise ValueError(f"FPDS code/role matrix is incomplete: {sorted(seen_scopes)}")

    return pd.concat(frames, ignore_index=True, sort=False), provenance


def prepare_coded_transactions(raw: pd.DataFrame, data_cut: date) -> pd.DataFrame:
    """Normalize, post-filter, and deduplicate Navy-coded FPDS actions."""

    if raw.empty:
        raise ValueError("FPDS coded pulls returned no rows")
    working = raw.copy()
    working["research_code"] = _clean_text(
        _series(working, "_research_code", "research")
    ).str.upper()
    working["action_date"] = pd.to_datetime(
        _series(working, "signedDate", "signed_date", "action_date"), errors="coerce"
    )
    working["order_piid"] = _series(working, "PIID", "order_piid")
    # The generated USAspending-style award key uses awardContractID/agencyID
    # (top tier), not the contracting-office sub-tier used for Navy scope.
    working["order_agency"] = _series(working, "agencyID", "order_agency")
    working["idv_piid"] = _series(working, "referenced_idv_piid", "idv_piid")
    working["idv_agency"] = _series(working, "referenced_idv_agency_id", "idv_agency")
    if (
        _clean_text(working["order_piid"]).eq("").any()
        or _clean_text(working["order_agency"]).eq("").any()
    ):
        raise ValueError("FPDS coded pulls require nonblank award PIID and top-tier agencyID")
    working["award_key"] = reconstruct_coded_award_key(working)
    native = _clean_text(_series(working, "contract_award_unique_key")).str.upper()
    disagreement = native.ne("") & native.ne(working["award_key"])
    if disagreement.any():
        rows = list(working.index[disagreement][:5])
        raise ValueError(f"native/reconstructed FPDS award-key disagreement at rows {rows}")
    working.loc[native.ne(""), "award_key"] = native[native.ne("")]

    working["don_awarding"] = _agency_is_navy(working, "contractingOfficeAgencyID")
    working["don_funding"] = _agency_is_navy(working, "fundingRequestingAgencyID")
    working = working.loc[
        working["research_code"].isin(PHASE_CODES)
        & working["action_date"].notna()
        & working["action_date"].dt.date.le(data_cut)
        & (working["don_awarding"] | working["don_funding"])
    ].copy()
    if working.empty:
        raise ValueError("no strict SR3/ST3 actions survived the DoN/cut-date post-filter")

    working["mod_number"] = _clean_text(_series(working, "modNumber", "mod_number"))
    mod_parts = working["mod_number"].str.extract(r"^(.*?)(\d+)$")
    working["_mod_prefix_sort"] = mod_parts[0].fillna(working["mod_number"]).str.upper()
    working["_mod_number_sort"] = pd.to_numeric(mod_parts[1], errors="coerce")
    working["transaction_number"] = _clean_text(
        _series(working, "transactionNumber", "transaction_number")
    )
    working["_transaction_number_sort"] = pd.to_numeric(
        working["transaction_number"], errors="coerce"
    )
    working["_atom_modified"] = pd.to_datetime(
        _series(working, "modified"), errors="coerce", utc=True
    )
    working["description"] = _clean_text(
        _series(working, "descriptionOfContractRequirement", "description")
    )
    working["naics_code"] = _clean_text(_series(working, "principalNAICSCode", "naics_code"))
    working["psc_code"] = _clean_text(_series(working, "productOrServiceCode", "psc_code"))
    working["recipient_uei"] = _clean_text(_series(working, "UEI", "recipient_uei")).str.upper()
    working["recipient_name"] = _clean_text(_series(working, "vendorName", "recipient_name"))
    working["description_length"] = working["description"].str.len().astype(int)
    transaction_key = [
        "award_key",
        "mod_number",
        "action_date",
        "research_code",
        "transaction_number",
    ]
    working = (
        working.sort_values(
            transaction_key + ["_atom_modified", "description"],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates(transaction_key, keep="last")
        .reset_index(drop=True)
    )
    return working


def latest_award_grain(transactions: pd.DataFrame) -> pd.DataFrame:
    """Select the latest retrieved action and OR role flags across award history."""

    latest = (
        transactions.sort_values(
            [
                "action_date",
                "_mod_prefix_sort",
                "_mod_number_sort",
                "mod_number",
                "_atom_modified",
                "_transaction_number_sort",
                "description",
            ],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates("award_key", keep="last")
        .reset_index(drop=True)
    )
    role_flags = transactions.groupby("award_key", as_index=False).agg(
        don_awarding=("don_awarding", "max"),
        don_funding=("don_funding", "max"),
    )
    return latest.drop(columns=["don_awarding", "don_funding"]).merge(
        role_flags, on="award_key", how="left", validate="one_to_one"
    )


def prepare_navy_sbir(sbir_awards: pd.DataFrame, start_fy: int, end_fy: int) -> pd.DataFrame:
    phase = _clean_text(_series(sbir_awards, "phase")).str.upper()
    agency = _clean_text(_series(sbir_awards, "agency"))
    branch = _clean_text(_series(sbir_awards, "branch"))
    fiscal_year = _fiscal_year(_series(sbir_awards, "award_date"))
    mask = (
        agency.eq(NAVY_AGENCY)
        & branch.eq(NAVY_BRANCH)
        & phase.isin({"PHASE I", "PHASE II"})
        & fiscal_year.between(start_fy, end_fy)
    )
    result = sbir_awards.loc[mask].copy()
    result["analysis_phase"] = phase[mask].str.replace("PHASE ", "", regex=False)
    result["fiscal_year"] = fiscal_year[mask].astype(int)
    if result.empty:
        raise ValueError("the canonical SBIR input has no Navy Phase I/II rows in scope")
    return result


def build_annual_panel(
    navy_sbir: pd.DataFrame,
    coded_awards: pd.DataFrame,
    start_fy: int,
    end_fy: int,
) -> list[dict[str, int]]:
    coded = coded_awards.copy()
    coded["fiscal_year"] = _fiscal_year(coded["action_date"])
    rows: list[dict[str, int]] = []
    for fiscal_year in range(start_fy, end_fy + 1):
        rows.append(
            {
                "fiscal_year": fiscal_year,
                "phase_i_awards": int(
                    (
                        (navy_sbir["fiscal_year"] == fiscal_year)
                        & (navy_sbir["analysis_phase"] == "I")
                    ).sum()
                ),
                "phase_ii_awards": int(
                    (
                        (navy_sbir["fiscal_year"] == fiscal_year)
                        & (navy_sbir["analysis_phase"] == "II")
                    ).sum()
                ),
                "coded_phase_iii_contracts": int((coded["fiscal_year"] == fiscal_year).sum()),
            }
        )
    return rows


def description_summary(coded_awards: pd.DataFrame) -> dict[str, Any]:
    lengths = coded_awards["description_length"].astype(int)
    denominator = int(len(lengths))
    result: dict[str, Any] = {
        "award_n": denominator,
        "median_chars": float(lengths.median()) if denominator else None,
        "blank_count": int(lengths.eq(0).sum()),
        "bound": (
            "conditional upper-bound proxy for uncoded-population description completeness "
            "only under the untested monotonicity assumption"
        ),
    }
    for threshold in (40, 150, 900):
        count = int(lengths.ge(threshold).sum())
        result[f"ge_{threshold}_count"] = count
        result[f"ge_{threshold}_rate"] = _percent(count, denominator)
    result["lt_150_count"] = denominator - result["ge_150_count"]
    result["lt_150_rate"] = _percent(result["lt_150_count"], denominator)
    return result


def _phase_iii_contract_frame(transactions: pd.DataFrame) -> pd.DataFrame:
    contracts = pd.DataFrame(
        {
            "contract_id": transactions["award_key"],
            "vendor_uei": transactions["recipient_uei"],
            "vendor_duns": None,
            "vendor_name": transactions["recipient_name"],
            "agency": np.where(
                transactions["don_awarding"], "Department of the Navy", "Department of Defense"
            ),
            "sub_agency": np.where(transactions["don_awarding"], "Department of the Navy", ""),
            "obligation_amount": None,
            "action_date": transactions["action_date"],
            "start_date": None,
            "end_date": None,
            "research": transactions["research_code"],
            "contract_award_type": "contract",
        }
    )
    return _prepare_phase_iii_rows(contracts)


def build_latency_panel(
    navy_sbir: pd.DataFrame, transactions: pd.DataFrame, data_cut: date
) -> tuple[dict[str, Any], pd.DataFrame]:
    phase_ii = _prepare_sbir_gov_rows(navy_sbir.loc[navy_sbir["analysis_phase"].eq("II")].copy())
    end_dates = pd.to_datetime(phase_ii["period_of_performance_end"], errors="coerce")
    phase_ii = phase_ii.loc[end_dates.notna() & end_dates.dt.date.le(data_cut)].reset_index(
        drop=True
    )
    if phase_ii.empty:
        raise ValueError("no completed Navy Phase II awards are at risk by the data cut")

    # A later modification cannot turn a pre-existing Phase III contract into
    # a new post-Phase-II transition.  Pair on the first coded action of each
    # distinct compound award key, while Panel A separately uses latest action.
    first_candidates = transactions.copy()
    if "_mod_prefix_sort" not in first_candidates or "_mod_number_sort" not in first_candidates:
        mod_number = _clean_text(_series(first_candidates, "mod_number", "modNumber"))
        mod_parts = mod_number.str.extract(r"^(.*?)(\d+)$")
        first_candidates["_mod_prefix_sort"] = mod_parts[0].fillna(mod_number).str.upper()
        first_candidates["_mod_number_sort"] = pd.to_numeric(mod_parts[1], errors="coerce")
    first_award_actions = (
        first_candidates.sort_values(
            [
                "action_date",
                "_mod_prefix_sort",
                "_mod_number_sort",
                "mod_number",
                "_transaction_number_sort",
            ],
            kind="stable",
            na_position="first",
        )
        .drop_duplicates("award_key", keep="first")
        .reset_index(drop=True)
    )
    phase_iii = _phase_iii_contract_frame(first_award_actions)
    pairs = _build_pairs(phase_ii, phase_iii)
    # The reusable pair asset intentionally emits every same-firm combination.
    # For this first-transition view, remove firm history that predates the
    # specific Phase II award.  Actions during Phase II performance remain and
    # can still produce valid negative completion-to-action latency.
    phase_ii_award_dates = phase_ii.set_index("award_id")["award_date"]
    pair_award_dates = pd.to_datetime(
        pairs["phase_ii_award_id"].map(phase_ii_award_dates), errors="coerce"
    )
    pair_action_dates = pd.to_datetime(pairs["phase_iii_action_date"], errors="coerce")
    pairs = pairs.loc[
        pair_award_dates.notna() & pair_action_dates.ge(pair_award_dates)
    ].reset_index(drop=True)
    survival = _build_survival(phase_ii, pairs, data_cut)
    observed = survival.loc[survival["event_observed"]].copy()
    observed_days = pd.to_numeric(observed["time_days"], errors="coerce").dropna().astype(float)
    deciles: dict[str, dict[str, float | int]] = {}
    if not observed_days.empty:
        for percentile in range(10, 100, 10):
            days = int(np.rint(np.percentile(observed_days, percentile)))
            deciles[f"p{percentile}"] = {
                "days": days,
                "years": round(days / 365.25, 2),
            }

    identifiers = phase_ii["recipient_uei"].fillna("").astype(str).str.strip()
    phase_ii_firms = set(identifiers[identifiers.ne("")])
    observed_awards = set(observed["phase_ii_award_id"].astype(str))
    event_firms = set(
        phase_ii.loc[phase_ii["award_id"].astype(str).isin(observed_awards), "recipient_uei"]
        .fillna("")
        .astype(str)
        .str.strip()
    ) - {""}
    summary = {
        "filter": (
            "Navy Phase II award FY in scope, period-of-performance end on/before data cut; "
            "first coded action of a same-UEI distinct SR3/ST3 award on/after that Phase II "
            "award date and on/before data cut"
        ),
        "phase_ii_award_n": int(len(survival)),
        "phase_ii_firm_n": len(phase_ii_firms),
        "event_award_n": int(len(observed)),
        "event_award_rate": _percent(int(len(observed)), int(len(survival))),
        "bound": (
            "lower bound on matches captured by this public coded channel; not an identified "
            "bound on true project transitions because same-firm false matches can bias upward"
        ),
        "censored_award_n": int((~survival["event_observed"]).sum()),
        "event_firm_n": len(event_firms),
        "censored_firm_n": len(phase_ii_firms - event_firms),
        "negative_latency_n": int(observed_days.lt(0).sum()),
        "deciles": deciles,
    }
    return summary, survival


def build_mechanism_panel(coded_awards: pd.DataFrame) -> dict[str, Any]:
    description_blank = coded_awards["description"].astype(str).str.strip().eq("")
    naics_missing = coded_awards["naics_code"].astype(str).str.strip().eq("")
    psc_missing = coded_awards["psc_code"].astype(str).str.strip().eq("")
    taxonomy_missing = naics_missing | psc_missing
    denominator = int(len(coded_awards))
    result: dict[str, Any] = {
        "filter": "same Navy coded award-grain FY window as Panel A",
        "award_n": denominator,
        "description_blank_n": int(description_blank.sum()),
        "naics_missing_n": int(naics_missing.sum()),
        "psc_missing_n": int(psc_missing.sum()),
        "either_taxonomy_missing_n": int(taxonomy_missing.sum()),
        "both_description_and_taxonomy_missing_n": int(
            (description_blank & taxonomy_missing).sum()
        ),
    }
    if description_blank.nunique() < 2 or taxonomy_missing.nunique() < 2:
        result.update(
            {
                "status": "blocked_constant_input",
                "phi": None,
                "near_zero": None,
            }
        )
        return result

    phi = float(np.corrcoef(description_blank.astype(int), taxonomy_missing.astype(int))[0, 1])
    if not math.isfinite(phi):
        result.update({"status": "blocked_nonfinite", "phi": None, "near_zero": None})
    else:
        result.update(
            {
                "status": "estimated",
                "phi": round(phi, 6),
                "near_zero": abs(phi) < 0.1,
            }
        )
    return result


def build_external_signal_panel(
    navy_sbir: pd.DataFrame,
    form_d_records: Sequence[dict[str, Any]],
    ma_records: Sequence[dict[str, Any]],
    as_of: date,
) -> dict[str, Any]:
    """Aggregate dated Form D signals and fail closed on undated EFTS types."""

    navy_firms = {normalize_name(value) for value in navy_sbir["company_name"]}
    navy_firms.discard("")
    start = (pd.Timestamp(as_of) - pd.DateOffset(months=24) + pd.Timedelta(days=1)).date()

    form_d_matches: list[tuple[str, str]] = []
    form_d_latest: date | None = None
    for record in form_d_records:
        key = normalize_name(record.get("company_name"))
        tier = _tier((record.get("match_confidence") or {}).get("tier"))
        for offering in record.get("offerings") or []:
            filing = pd.to_datetime(offering.get("filing_date"), errors="coerce")
            if pd.isna(filing):
                continue
            filing_date = filing.date()
            form_d_latest = max(form_d_latest or filing_date, filing_date)
            if key not in navy_firms or not tier:
                continue
            amount_sold = pd.to_numeric(offering.get("total_amount_sold"), errors="coerce")
            if (
                start <= filing_date <= as_of
                and not bool(offering.get("is_business_combination"))
                and pd.notna(amount_sold)
                and float(amount_sold) > 0
            ):
                form_d_matches.append((key, tier))

    efts_latest: date | None = None
    for record in ma_records:
        detail = record.get("efts_detail") or {}
        mention = pd.to_datetime(detail.get("latest_mention_date"), errors="coerce")
        if pd.isna(mention):
            continue
        mention_date = mention.date()
        efts_latest = max(efts_latest or mention_date, mention_date)

    form_d = _best_tier_by_firm(form_d_matches)

    def counts(values: dict[str, str]) -> dict[str, int]:
        return {
            "high": sum(tier == "high" for tier in values.values()),
            "medium": sum(tier == "medium" for tier in values.values()),
            "total": len(values),
        }

    return {
        "filter": (
            "unique normalized Navy Phase I/II firms in the FY window; Form D filing date in "
            "the 24-month window and high/medium match tiers only; EFTS acquisition branch "
            "blocked because the source lacks type-specific mention dates"
        ),
        "window_start": start.isoformat(),
        "window_end": as_of.isoformat(),
        "navy_firm_n": len(navy_firms),
        "form_d_positive_raise_firms": counts(form_d),
        "efts_acquisition_firms": {
            "status": "blocked_missing_type_specific_dates",
            "high": None,
            "medium": None,
            "total": None,
        },
        "either_recent_signal_firms": {
            "status": "blocked_by_efts_branch",
            "high": None,
            "medium": None,
            "total": None,
        },
        "form_d_latest_observed_filing": form_d_latest.isoformat() if form_d_latest else None,
        "efts_latest_observed_mention": efts_latest.isoformat() if efts_latest else None,
    }


def _figure_heading(fig: Any, title: str, subtitle: str) -> None:
    fig.subplots_adjust(left=0.13, right=0.98, bottom=0.16, top=0.81)
    fig.text(0.02, 0.96, title, ha="left", va="top", fontsize=16, fontweight="bold")
    fig.text(0.02, 0.88, subtitle, ha="left", va="top", fontsize=9, color="#444444")


def _write_latency_figure(survival: pd.DataFrame, path: Path, data_cut: date) -> None:
    plt = _plotting_module()
    path.parent.mkdir(parents=True, exist_ok=True)
    observed = (
        pd.to_numeric(survival.loc[survival["event_observed"], "time_days"], errors="coerce")
        .dropna()
        .sort_values()
        .to_numpy(dtype=float)
        / 365.25
    )
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    if observed.size:
        probability = np.arange(1, observed.size + 1) / observed.size
        ax.step(observed, probability, where="post", color="#0B4F6C", linewidth=2.2)
        ax.axvline(0, color="#777777", linewidth=1, linestyle="--")
        ax.set_ylabel("Share of observed coded events")
        ax.set_xlabel("Years from Phase II period end to first coded Phase III action")
    else:
        ax.text(0.5, 0.5, "No coded events observed", ha="center", va="center")
        ax.set_axis_off()
    event_n = int(survival["event_observed"].sum())
    censored_n = int((~survival["event_observed"]).sum())
    _figure_heading(
        fig,
        "Navy Phase II → first coded Phase III",
        f"Conditional ECDF: n={event_n} events; {censored_n} right-censored at {data_cut}",
    )
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _write_description_figure(coded_awards: pd.DataFrame, path: Path) -> None:
    plt = _plotting_module()
    path.parent.mkdir(parents=True, exist_ok=True)
    lengths = np.sort(coded_awards["description_length"].astype(float).to_numpy())
    probability = np.arange(1, len(lengths) + 1) / len(lengths)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.step(lengths, probability, where="post", color="#0B4F6C", linewidth=2.2)
    colors = {40: "#D95F02", 150: "#7570B3", 900: "#1B9E77"}
    for threshold, color in colors.items():
        ax.axvline(threshold, color=color, linewidth=1.4, linestyle="--", label=f"{threshold}")
    upper = max(950.0, float(np.percentile(lengths, 99.5)))
    ax.set_xlim(0, upper)
    ax.set_ylim(0, 1.01)
    ax.set_xlabel("Latest retrieved Navy-attributed action description (characters)")
    ax.set_ylabel("Share of coded contract awards")
    _figure_heading(
        fig,
        "Navy coded Phase III description ECDF",
        f"n={len(lengths):,} distinct award keys; FY2016–FY2025 retrieved-action scope",
    )
    ax.legend(title="Threshold", frameon=False, ncols=3, loc="lower right")
    ax.grid(axis="y", color="#DDDDDD", linewidth=0.7)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{100 * value:.1f}%"


def render_markdown(summary: dict[str, Any]) -> str:
    study = summary["study"]
    panel_a = summary["panel_a"]
    panel_b = summary["panel_b"]
    panel_c = summary["panel_c"]
    panel_d = summary["panel_d"]
    desc = panel_a["description"]
    comparator = panel_a["historical_dod_comparator"]

    annual_rows = "\n".join(
        f"| FY{row['fiscal_year']} | {row['phase_i_awards']:,} | "
        f"{row['phase_ii_awards']:,} | {row['coded_phase_iii_contracts']:,} |"
        for row in panel_a["annual"]
    )
    decile_cells = " | ".join(panel_b["deciles"])
    decile_values = " | ".join(
        f"{panel_b['deciles'][key]['days']:,} ({panel_b['deciles'][key]['years']:.2f})"
        for key in panel_b["deciles"]
    )

    if panel_c["status"] == "estimated":
        if panel_c["near_zero"]:
            mechanism_result = (
                f"Phi = {panel_c['phi']:.3f}; this is near zero under the pre-set |phi| < 0.10 "
                "descriptive rule. Within this coded frame, blank optional descriptions varied "
                "independently of the two required classification fields."
            )
        else:
            mechanism_result = (
                f"Phi = {panel_c['phi']:.3f}; the near-zero result did not replicate under the "
                "pre-set |phi| < 0.10 descriptive rule."
            )
    else:
        mechanism_result = (
            "Correlation was not estimable because at least one binary input was constant; "
            "Panel C is therefore blocked rather than replaced with a different outcome."
        )

    return f"""# Navy Phase III transition readout v1

> **Exploratory — non-citable.** Prepared independently in a personal capacity; no agency
> affiliation is asserted. Descriptive only: no office ranking, statutory undercount
> claim, or recommendation.

**Frame.** Public SBIR.gov/FPDS data through {study["data_cut"]}; federal FY{study["start_fy"]}–FY{study["end_fy"]}.
“Navy” is SBIR.gov DoD/Navy or FPDS SR3/ST3 with awarding **or** funding sub-tier 1700.
FPDS actions are post-filtered, compound-key deduplicated, and represented by the latest
retrieved Navy-attributed action. The coded set is the observed complement of the uncoded-claim
population. Counts and coded-signal incidence are lower bounds on public coded-channel capture;
exact-UEI, no-topic pairing means they are not bounds on true project transitions. Description
completeness rates are conditional upper-bound proxies for uncoded claims only if coded records
are at least as complete—an untested assumption.

**Sources/provenance:** [SBIR.gov bulk](https://data.www.sbir.gov/mod_awarddatapublic/award_data.csv),
[FPDS public Atom](https://www.fpds.gov/ezsearch/FEEDS/ATOM?FEEDNAME=PUBLIC),
[SEC EDGAR](https://www.sec.gov/edgar), and
[SEC EFTS](https://efts.sec.gov/LATEST/search-index); hashes are in the
[aggregate summary](navy-transition-v1.summary.json).

## A — Coverage and description field

Denominators: {panel_a["phase_i_award_n"]:,} Navy Phase I and
{panel_a["phase_ii_award_n"]:,} Phase II awards; {panel_a["coded_award_n"]:,} SR3/ST3 keys in
the same FY window ({panel_a["don_awarding_award_n"]:,} DoN-awarded,
{panel_a["don_funding_award_n"]:,} DoN-funded, {panel_a["don_awarding_and_funding_award_n"]:,}
both; annual counts use the union).

| Latest retrieved-action FY | Phase I awards | Phase II awards | Coded Phase III contracts |
|---:|---:|---:|---:|
{annual_rows}

Latest retrieved-action descriptions have median {desc["median_chars"]:.0f} characters;
{desc["ge_40_count"]:,}/{desc["award_n"]:,} ({_fmt_rate(desc["ge_40_rate"])}) reach 40,
{desc["ge_150_count"]:,}/{desc["award_n"]:,} ({_fmt_rate(desc["ge_150_rate"])}) reach 150, and
{desc["ge_900_count"]:,}/{desc["award_n"]:,} ({_fmt_rate(desc["ge_900_rate"])}) reach 900.

The requested **historical, unreproduced** DoD comparator is traceable only to a legacy
[coded pull](https://github.com/hollomancer/sbir-analytics/blob/d844f2b0/scripts/phase3_benchmark/m0a_coded_pull.py),
[threshold script](https://github.com/hollomancer/sbir-analytics/blob/48f13305/scripts/phase3_benchmark/dod_within_retrieval.py),
and [median assertion](https://github.com/hollomancer/sbir-analytics/blob/e51574be/specs/phase3-match-benchmark/eval-validity.md):
FY2016–25 DoD SR3/ST3 n={comparator["award_n"]:,}, median 42, 53.6% ≥40,
88.5% <150, and 0% ≥900. The median has no committed generator and
[tracked prose](../../specs/phase3-match-benchmark/mse-dark-phase3.md) says 43; these are quoted,
not method-matched. Navy is {_fmt_rate(desc["lt_150_rate"])} <150. The 900 mark is analytic,
not a statutory §638 floor.

## B — Phase II to first coded Phase III

At risk: {panel_b["phase_ii_award_n"]:,} Phase II awards ({panel_b["phase_ii_firm_n"]:,}
exact-UEI firms) ending by the cut. {panel_b["event_award_n"]:,}
({_fmt_rate(panel_b["event_award_rate"])}) pair to the first action of a distinct same-UEI coded
award on/after the Phase II award date; {panel_b["censored_award_n"]:,} are right-censored.
At firm grain, {panel_b["censored_firm_n"]:,}/{panel_b["phase_ii_firm_n"]:,} have no coded event:
not-yet-observed, not zero.
Quantiles condition on events. They retain {panel_b["negative_latency_n"]:,} actions during
Phase II performance, so median completion-to-action latency is
{panel_b["deciles"]["p50"]["days"]:,} days ({panel_b["deciles"]["p50"]["years"]:.2f} years).
Undercoding makes the rate a coded-channel floor; unrelated same-firm awards can bias it upward
against true transitions, so it is not a true-transition bound.

| {decile_cells} |
|{"".join("---:|" for _ in panel_b["deciles"])}
| {decile_values} |

*Cells: days (years) from Phase II period end; n={panel_b["event_award_n"]:,} observed events.*

| A. Description ECDF and 40/150/900 thresholds | B. Conditional latency ECDF |
|:---:|:---:|
| ![Description ECDF](figures/navy-transition-v1-description-cdf.png) | ![Latency ECDF](figures/navy-transition-v1-latency.png) |

## C — Description emptiness versus NAICS/PSC missingness

In n={panel_c["award_n"]:,}, blank description={panel_c["description_blank_n"]:,}, missing
NAICS={panel_c["naics_missing_n"]:,}, and missing PSC={panel_c["psc_missing_n"]:,}.
{mechanism_result}

## D — Recent external capital/acquisition signals

Among {panel_d["navy_firm_n"]:,} normalized Navy firms, the {panel_d["window_start"]}–
{panel_d["window_end"]} high/medium screens are:

| Public signal | High | Medium | Unique firms |
|---|---:|---:|---:|
| Positive non-combination Form D filing | {panel_d["form_d_positive_raise_firms"]["high"]:,} | {panel_d["form_d_positive_raise_firms"]["medium"]:,} | {panel_d["form_d_positive_raise_firms"]["total"]:,} |
| EFTS acquisition in window | — | — | blocked |
| Either recent signal | — | — | blocked |

No names are emitted. Form D is participation, not verified capital received. EFTS stores
all-time types plus the latest mention of any type, so it cannot date the requested acquisition
signal; that branch and its union are blocked rather than replaced with a proxy.

## Limitations

SR3/ST3 and public/exact-UEI coverage miss transitions; firm-level pairing can reuse one event
across awards. Censoring is administrative, not evidence of no transition. Modification text
may not describe the base award.
DoN awarding/funding attribution is unioned and may differ. Form D amendments/name matches and
aggregated EFTS mentions can false-positive. Source cuts differ and are recorded. Nothing here
identifies a mechanism.
"""


def build_summary(
    *,
    sbir_path: Path,
    sbir_checks_path: Path,
    coded_pairs: Sequence[tuple[Path, Path]],
    form_d_path: Path,
    ma_events_path: Path,
    start_fy: int,
    end_fy: int,
    data_cut: date,
    as_of: date,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    sbir = pd.read_parquet(sbir_path)
    navy_sbir = prepare_navy_sbir(sbir, start_fy, end_fy)
    coded_raw, coded_provenance = load_coded_inputs(coded_pairs, data_cut)
    transactions = prepare_coded_transactions(coded_raw, data_cut)
    award_grain = latest_award_grain(transactions)
    award_grain["fiscal_year"] = _fiscal_year(award_grain["action_date"])
    scoped_awards = award_grain.loc[
        award_grain["fiscal_year"].between(start_fy, end_fy)
    ].reset_index(drop=True)
    if scoped_awards.empty:
        raise ValueError("no Navy coded award keys fall in the requested fiscal-year window")

    latency, survival = build_latency_panel(navy_sbir, transactions, data_cut)
    sbir_checks = _read_json(sbir_checks_path)
    source_provenance = sbir_checks.get("source_provenance") or {}
    annual = build_annual_panel(navy_sbir, scoped_awards, start_fy, end_fy)
    form_d_records = read_jsonl(form_d_path)
    ma_records = read_jsonl(ma_events_path)
    external = build_external_signal_panel(navy_sbir, form_d_records, ma_records, as_of)

    don_awarding = set(scoped_awards.loc[scoped_awards["don_awarding"], "award_key"])
    don_funding = set(scoped_awards.loc[scoped_awards["don_funding"], "award_key"])
    coded_firms = set(scoped_awards["recipient_uei"].astype(str).str.strip()) - {""}
    summary: dict[str, Any] = {
        "status": "exploratory_non_citable",
        "_epistemic": {
            "tier": "exploratory",
            "citable": False,
            "notice": "Exploratory analysis; do not cite as an evidence-tier result.",
        },
        "study": {
            "version": "navy-transition-v1",
            "start_fy": start_fy,
            "end_fy": end_fy,
            "data_cut": data_cut.isoformat(),
            "as_of": as_of.isoformat(),
            "capacity": "independent personal capacity; no agency affiliation",
        },
        "provenance": {
            "sbir": {
                "file": sbir_path.name,
                "sha256": _sha256(sbir_path),
                "rows": len(sbir),
                "source_system": source_provenance.get("system"),
                "source_url": source_provenance.get("url"),
                "source_sha256": source_provenance.get("sha256"),
            },
            "fpds": coded_provenance,
            "form_d": {
                "file": form_d_path.name,
                "sha256": _sha256(form_d_path),
                "record_n": len(form_d_records),
                "source_url": "https://www.sec.gov/edgar",
            },
            "efts": {
                "file": ma_events_path.name,
                "sha256": _sha256(ma_events_path),
                "record_n": len(ma_records),
                "source_url": "https://efts.sec.gov/LATEST/search-index",
            },
        },
        "panel_a": {
            "filter": (
                f"Navy SBIR Phase I/II award date FY{start_fy}-FY{end_fy}; Navy-attributed "
                "strict SR3/ST3 compound award key assigned to latest retrieved "
                "Navy-attributed coded action in window"
            ),
            "phase_i_award_n": int(navy_sbir["analysis_phase"].eq("I").sum()),
            "phase_ii_award_n": int(navy_sbir["analysis_phase"].eq("II").sum()),
            "coded_transaction_n_all_dates_through_cut": int(len(transactions)),
            "coded_award_n": int(len(scoped_awards)),
            "coded_firm_n": len(coded_firms),
            "don_awarding_award_n": len(don_awarding),
            "don_funding_award_n": len(don_funding),
            "don_awarding_and_funding_award_n": len(don_awarding & don_funding),
            "annual": annual,
            "description": description_summary(scoped_awards),
            "historical_dod_comparator": HISTORICAL_DOD_COMPARATOR,
        },
        "panel_b": latency,
        "panel_c": build_mechanism_panel(scoped_awards),
        "panel_d": external,
    }
    return summary, survival, scoped_awards


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sbir-awards", type=Path, default=DEFAULT_SBIR)
    parser.add_argument("--sbir-checks", type=Path, default=DEFAULT_SBIR_CHECKS)
    parser.add_argument(
        "--coded",
        action="append",
        nargs=2,
        required=True,
        metavar=("PARQUET", "MANIFEST"),
        help="complete FPDS coded pull and its manifest; repeat for SR3/ST3 and agency roles",
    )
    parser.add_argument("--form-d", type=Path, default=DEFAULT_FORM_D)
    parser.add_argument("--ma-events", type=Path, default=DEFAULT_MA_EVENTS)
    parser.add_argument("--start-fy", type=int, default=2016)
    parser.add_argument("--end-fy", type=int, default=2025)
    parser.add_argument("--data-cut", type=date.fromisoformat, default=date(2025, 9, 30))
    parser.add_argument("--as-of", type=date.fromisoformat, default=date(2026, 8, 31))
    parser.add_argument("--output-markdown", type=Path, default=DEFAULT_MARKDOWN)
    parser.add_argument("--output-summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--figures-dir", type=Path, default=DEFAULT_FIGURES)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.end_fy - args.start_fy != 9:
        raise ValueError("this readout requires exactly ten fiscal years")
    coded_pairs = [(Path(pair[0]), Path(pair[1])) for pair in args.coded]
    summary, survival, scoped_awards = build_summary(
        sbir_path=args.sbir_awards,
        sbir_checks_path=args.sbir_checks,
        coded_pairs=coded_pairs,
        form_d_path=args.form_d,
        ma_events_path=args.ma_events,
        start_fy=args.start_fy,
        end_fy=args.end_fy,
        data_cut=args.data_cut,
        as_of=args.as_of,
    )

    latency_figure = args.figures_dir / "navy-transition-v1-latency.png"
    description_figure = args.figures_dir / "navy-transition-v1-description-cdf.png"
    _write_latency_figure(survival, latency_figure, args.data_cut)
    _write_description_figure(scoped_awards, description_figure)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_summary.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.write_text(render_markdown(summary))
    args.output_summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
